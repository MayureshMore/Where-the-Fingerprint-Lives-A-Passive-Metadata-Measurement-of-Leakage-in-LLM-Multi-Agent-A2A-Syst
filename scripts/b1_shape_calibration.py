#!/usr/bin/env python3
"""
Reply shaping's parameters against C2 (paper 2 round 2, B1): would the cap cut, or the release time
delay, any of C2's cloud replies, and what does the padding cost on the wire?

From C2's header-only captures and sidecars (all three arms: the replies are not padded in any):

    reply bytes   each escalated task's cloud reply as the SDK serializes it (JSON-escaped UTF-8), from
                  the TLS record that carries its artifact event. Per SSE event the cloud sends one TLS
                  1.3 record: 5 + 17 (type, tag) + HTTP chunk ("%x\\r\\n" + "data: " + JSON + "\\r\\n\\r\\n"
                  + "\\r\\n"); with the SDK's JSON a token event is 553 + its bytes, the artifact 352 +
                  the reply's, completed + chunk terminator 351, at the end of the stream (checked
                  against the captures). Headers are visible only at a segment's start, so the
                  artifact's start is exact where a visible record ends there (exact), else taken
                  from the last visible boundary with whole token events of 557 bytes in between
                  (±4 bytes per event)
    cut           replies over the cap (REPLY_BYTES of the spec), and the margin to it
    late          escalated tasks whose cloud call (the edge agent's answer time, an upper bound on
                  the cloud's generation time) took longer than the release time
    overhead      per reply, the filler the shaping adds (every event padded to one size, the artifact
                  to one size); the shaped reply's wire bytes (events + artifact, TLS records), and
                  the same part of C2's unshaped stream (one event per token, then the artifact)

    python scripts/b1_shape_calibration.py --shape 2048/14/128/0.05/truncate --out data/results/b1_shape_calibration
"""

from __future__ import annotations

import argparse
import datetime
import json
import statistics
import struct
import subprocess
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from a2a.types import (Artifact, Message, Part, Role, SendStreamingMessageResponse,  # noqa: E402
                       SendStreamingMessageSuccessResponse, TaskArtifactUpdateEvent, TaskState, TaskStatus,
                       TaskStatusUpdateEvent, TextPart)
from scapy.utils import RawPcapReader  # noqa: E402

from defense.shaping import MAX_SLACK, ShapeConfig, wire_bytes  # noqa: E402

ARMS = ("data/raw_c2", "data/raw_c2_pad", "data/raw_c2_padmax")
TOK, ART, END = 553, 352, 324 + 27


def record(json_len: int) -> int:
    """TLS record bytes (header included) of one SSE event whose JSON is json_len bytes."""
    n = json_len + 10
    return 5 + 17 + len(f"{n:x}") + 2 + n + 2


def _ids() -> dict:
    return {"task_id": str(uuid.uuid4()), "context_id": str(uuid.uuid4())}


def status_event(text: str, meta: dict | None) -> int:
    ids = _ids()
    msg = Message(role=Role.agent, parts=[Part(root=TextPart(text=text))], message_id=str(uuid.uuid4()), metadata=meta, **ids)
    ev = TaskStatusUpdateEvent(final=False, status=TaskStatus(state=TaskState.working, message=msg,
                               timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="microseconds")), **ids)
    return wire_bytes(SendStreamingMessageResponse(root=SendStreamingMessageSuccessResponse(id=str(uuid.uuid4()), result=ev)).root)


def artifact_event(text: str, meta: dict | None) -> int:
    ev = TaskArtifactUpdateEvent(artifact=Artifact(artifact_id=str(uuid.uuid4()), name="result",
                                                   parts=[Part(root=TextPart(text=text))], metadata=meta), **_ids())
    return wire_bytes(SendStreamingMessageResponse(root=SendStreamingMessageSuccessResponse(id=str(uuid.uuid4()), result=ev)).root)


def overhead(shape: ShapeConfig) -> dict:
    """The shaped reply's sizes: each event and the artifact, as JSON and as TLS records; the filler
    for a reply of E bytes is const - 2E (every event padded to a chunk of chunk_bytes + 3 bytes, the
    artifact to a reply of reply_bytes)."""
    ev = status_event("x" * (shape.chunk_bytes + MAX_SLACK), {"_pad": ""})
    art = artifact_event("x" * shape.reply_bytes, {"_pad": ""})
    ev0, art0 = status_event("", None), artifact_event("", None)
    return {"event_json": ev, "event_record": record(ev), "artifact_json": art, "artifact_record": record(art),
            "events": shape.events, "reply_record_bytes": shape.events * record(ev) + record(art),
            "filler_const": shape.events * (ev - ev0) + (art - art0),
            "rule": "filler(E) = events × (padded event − bare event) + (padded artifact − bare artifact) − 2E"}


def reply_stream(pcap: Path, ip: str, port: int, chars: int) -> dict | None:
    sip = bytes(int(x) for x in ip.split("."))
    by: dict[int, dict] = defaultdict(dict)
    for data, _ in RawPcapReader(str(pcap)):
        if len(data) < 34 or data[12:14] != b"\x08\x00" or data[23] != 6 or data[26:30] != sip:
            continue
        ihl = (data[14] & 0x0F) * 4
        t = 14 + ihl
        sport, dport = struct.unpack("!HH", data[t:t + 4])
        if sport != port:
            continue
        seq = struct.unpack("!I", data[t + 4:t + 8])[0]
        thl = (data[t + 12] >> 4) * 4
        plen = struct.unpack("!H", data[16:18])[0] - ihl - thl
        if plen > 0:
            by[dport].setdefault(seq, (data[t + thl:], plen))
    if not by:
        return None
    segs = max(by.values(), key=lambda d: sum(p for _, p in d.values()))
    end = max(s + p for s, (_, p) in segs.items())
    art_end = end - END
    bounds, first_tok = set(), None
    for s in sorted(segs):
        cap, _ = segs[s]
        if len(cap) >= 5 and cap[:3] == b"\x17\x03\x03":
            n = struct.unpack("!H", cap[3:5])[0]
            bounds |= {s, s + 5 + n}
            if first_tok is None and TOK <= n + 5 <= TOK + 64:
                first_tok = s
    before = [b for b in bounds if b < art_end - ART]
    if not before:
        return None
    B = max(before)
    S = art_end - B
    j = max(0, round((S - ART - chars) / (TOK + 4)))
    E = S - ART - j * (TOK + 4)
    art_start = art_end - ART - E
    return {"bytes": int(E), "exact": j == 0, "token_events_bytes": int(art_start - first_tok) if first_tok is not None else None,
            "artifact_bytes": int(ART + E), "server_bytes": int(sum(p for _, p in segs.values()))}


def _git() -> dict:
    def run(*args):
        return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()
    return {"git_commit": run("rev-parse", "HEAD") or None,
            "git_dirty": bool(run("status", "--porcelain", "--", ".", ":(exclude)data"))}


def pct(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--shape", default="2048/14/128/0.05/truncate")
    p.add_argument("--arms", default=",".join(ARMS))
    p.add_argument("--out", required=True, help="path without extension (.json, .md)")
    p.add_argument("--allow-dirty", action="store_true", dest="allow_dirty")
    a = p.parse_args(argv)
    git = _git()
    if git["git_dirty"] and not a.allow_dirty:
        raise SystemExit("uncommitted code: commit first (or --allow-dirty for a dry run)")
    for ext in (".json", ".md"):
        if Path(a.out + ext).exists():
            raise SystemExit(f"{a.out + ext} exists: results are never written over")
    shape = ShapeConfig.parse(a.shape)
    oh = overhead(shape)
    rows, answers = [], []
    for raw in a.arms.split(","):
        for side in sorted(Path(raw).glob("*_edge_cloud_*.json")):
            sc = json.loads(side.read_text())
            er = sc.get("edge_report") or {}
            if not sc.get("success") or not er.get("escalated") or not er.get("cloud_role"):
                continue
            answers.append({"arm": sc["arm"], "task_type": sc["task_type"], "seconds": er["seconds"]["answer"],
                            "total": sc["end_ts"] - sc["start_ts"]})
            ip, port = sc["agent_endpoints"][er["cloud_role"]].split(":")
            r = reply_stream(side.with_suffix(".pcap"), ip, int(port), er["answer_chars"])
            if r:
                rows.append({"run": side.stem, "arm": sc["arm"], "task_type": sc["task_type"], "role": er["cloud_role"],
                             "chars": er["answer_chars"], **r})
    E = [r["bytes"] for r in rows]
    filler = [oh["filler_const"] - 2 * e for e in E]
    unshaped = [r["token_events_bytes"] + r["artifact_bytes"] for r in rows if r["token_events_bytes"] is not None]
    secs = [x["seconds"] for x in answers]
    by_type = {}
    for tt in sorted({r["task_type"] for r in rows}):
        sub = [r["bytes"] for r in rows if r["task_type"] == tt]
        st = [x["seconds"] for x in answers if x["task_type"] == tt]
        by_type[tt] = {"n": len(sub), "bytes_max": max(sub), "bytes_p99": pct(sub, 0.99), "bytes_median": statistics.median(sub),
                       "cut": sum(e > shape.reply_bytes for e in sub), "answer_s_max": max(st),
                       "late": sum(s > shape.deadline_s for s in st)}
    res = {"paper": "P2", "round": 2, "check": "B1 reply shaping against C2", "collection_id": "C2",
           "data_dir": a.arms.split(","), **git, "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "seed": None,
           "shape": shape.spec(), "release_s": shape.release_s(), "arms": a.arms.split(","),
           "replies": {"n": len(rows), "exact": sum(r["exact"] for r in rows), "bytes_max": max(E),
                       "bytes_p99": pct(E, 0.99), "bytes_median": statistics.median(E),
                       "chars_max": max(r["chars"] for r in rows),
                       "bytes_minus_chars": {"min": min(r["bytes"] - r["chars"] for r in rows),
                                             "median": statistics.median(r["bytes"] - r["chars"] for r in rows),
                                             "max": max(r["bytes"] - r["chars"] for r in rows)}},
           "cut": {"cap": shape.reply_bytes, "n": sum(e > shape.reply_bytes for e in E), "margin_bytes": shape.reply_bytes - max(E)},
           "late": {"deadline_s": shape.deadline_s, "n": sum(s > shape.deadline_s for s in secs), "answer_s_max": max(secs),
                    "answer_s_p99": pct(secs, 0.99), "margin_s": shape.deadline_s - max(secs),
                    "note": "the edge agent's answer time spans the whole cloud call (connect, TLS, request, generation, "
                            "stream): an upper bound on the generation time the deadline is measured against"},
           "by_task_type": by_type,
           "overhead": {**oh, "filler_bytes": {"median": statistics.median(filler), "p95": pct(filler, 0.95),
                                               "max": max(filler), "min": min(filler)},
                        "filler_share_of_shaped": statistics.median(filler) / oh["reply_record_bytes"],
                        "unshaped_reply_bytes": {"n": len(unshaped), "median": statistics.median(unshaped),
                                                 "p95": pct(unshaped, 0.95), "max": max(unshaped)},
                        "shaped_minus_unshaped_median": oh["reply_record_bytes"] - statistics.median(unshaped),
                        "unshaped_note": "C2's reply part of the stream: the token events (one per token) and the "
                                         "artifact, from the first token event's record to the artifact's end"},
           "replies_by_run": rows}
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(res, indent=1))
    o, f = res["overhead"], res["overhead"]["filler_bytes"]
    L = [f"# B1: reply shaping {shape.spec()} against C2", "",
         f"Commit `{(git['git_commit'] or '')[:8]}` (clean: {git['git_dirty'] is False}). {len(rows)} escalated cloud "
         f"replies from {', '.join(res['arms'])} ({res['replies']['exact']} measured exactly).", "",
         "| | |", "|---|---|",
         f"| Reply bytes (JSON-encoded): max / p99 / median | {max(E)} / {pct(E, 0.99)} / {statistics.median(E):.0f} |",
         f"| Cap | {shape.reply_bytes} B: {res['cut']['n']} cut, margin {res['cut']['margin_bytes']} B |",
         f"| Cloud call (edge's answer time): max / p99 | {max(secs):.1f} / {pct(secs, 0.99):.1f} s |",
         f"| Release | first event at {shape.deadline_s:g} s, last at {shape.release_s():g} s: {res['late']['n']} late, "
         f"margin {res['late']['margin_s']:.1f} s |",
         f"| Shaped reply on the wire | {o['events']} events × {o['event_record']} B + artifact {o['artifact_record']} B = "
         f"{o['reply_record_bytes']} B |",
         f"| Filler per reply: median / p95 / max | {f['median']:.0f} / {f['p95']:.0f} / {f['max']:.0f} B "
         f"({o['filler_share_of_shaped']:.0%} of the shaped reply) |",
         f"| C2's unshaped reply part: median / p95 / max | {o['unshaped_reply_bytes']['median']:.0f} / "
         f"{o['unshaped_reply_bytes']['p95']:.0f} / {o['unshaped_reply_bytes']['max']:.0f} B |", "",
         "| Task type | Replies | Bytes max | Cut | Answer max (s) | Late |", "|---|---|---|---|---|---|"]
    L += [f"| {k} | {v['n']} | {v['bytes_max']} | {v['cut']} | {v['answer_s_max']:.1f} | {v['late']} |" for k, v in by_type.items()]
    out.with_suffix(".md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
