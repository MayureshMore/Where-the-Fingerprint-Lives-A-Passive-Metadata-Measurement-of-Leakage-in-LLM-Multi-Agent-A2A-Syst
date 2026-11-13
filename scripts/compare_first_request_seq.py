#!/usr/bin/env python3
"""
Where the first request in TCP sequence space (features/first_request.py, first_request_seq)
differs from the measure used before (first_request: request writes ≤ 50 ms apart), per arm and
task type, on a session collection (scripts/collect_session.py).

Two scopes: the leakcheck's first-request size (every agent link the trace opened,
a2a_leakcheck/extract.py) and the padding check's (the padded endpoints' links only,
scripts/check_session_design.py [c]; a trace that does not reach them, alert_triage, is left
out there as in [c]). A change has two parts:

  start   bytes the earlier measure counts at the start that the new one does not: when the
          ClientHello spans two segments (the Pi's: 1,448 + 100 B), first_request takes the second
          for the client Finished and counts the real Finished (80 B) in the request
  end     where the request ends: new end − earlier end, both from the earlier start

so new − earlier = end − start. The split assumes the ClientHello's segments arrived in order: when
its first segment was lost and arrived after the second, first_request counts it in the request
and the difference shows up as "end". Traces where the two measures pick different links are
counted apart.

Usage:
    python scripts/compare_first_request_seq.py data/raw_c2 data/raw_c2_pad data/raw_c2_padmax \\
        --json data/raw_c2/first_request_seq_change.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from features.connections import own_packets  # noqa: E402
from features.first_request import FINISHED_MAX, first_request, first_request_seq  # noqa: E402
from features.kfp import dedup_view, duplicate_bytes, is_retransmission, tcp_records  # noqa: E402
from scripts.check_session_design import _padded_ports, _ports, _sidecars  # noqa: E402


def earlier_start(records, link: tuple[int, int]) -> int | None:
    """Client sequence number (relative to its first byte) where first_request's request starts on
    `link`: after its first data segment and, if the next is at most 100 B, that one too, each byte
    once (as first_request on tcp_packets(dedup=True))."""
    recs = [r for r in records if (r[1], r[2]) == link or (r[2], r[1]) == link]
    dups = duplicate_bytes([r[:7] for r in recs])
    base, n, start = None, 0, None
    for r, d in zip(recs, dups):
        ts, sp, dp, wl, pl, fl, seq = r[:7]
        if (sp, dp) != link:
            continue
        if fl & 0x02:
            base = (seq + 1) % 2 ** 32
            continue
        if pl == 0 or is_retransmission(r[:6], d) or base is None:
            continue
        end = (seq - base) % 2 ** 32 + pl
        n += 1
        if n == 1:
            start = end
        elif n == 2 and pl - d <= FINISHED_MAX:
            start = end
        else:
            break
    return start


def measure(records, servers: set[int], tls: bool) -> dict:
    old = first_request(own_packets(dedup_view([r[:7] for r in records]), servers), servers)
    new = first_request_seq(records, servers, tls=tls)
    out = {"earlier": old["bytes"], "new": new["bytes"], "same_link": old["link"] == new["link"],
           "acked": new["acked"], "skipped": new["skipped"]}
    if out["same_link"] and new["link"]:
        h = earlier_start(records, new["link"])
        out["start"] = new["start"] - h
        out["end"] = new["bytes"] + out["start"] - old["bytes"]
    return out


def summarise(rows: list[dict]) -> dict:
    changed = [r for r in rows if r["new"] != r["earlier"]]
    same = [r for r in rows if r["same_link"] and "end" in r]
    ends = [r for r in same if r["end"] != 0]
    big = max(changed, key=lambda r: (abs(r["new"] - r["earlier"]), r["run_id"]), default=None)
    big_end = max(ends, key=lambda r: (abs(r["end"]), r["run_id"]), default=None)
    return {"traces": len(rows), "changed": len(changed),
            "change_bytes": dict(Counter(r["new"] - r["earlier"] for r in changed).most_common(8)),
            "largest_change": big and {k: big[k] for k in ("run_id", "earlier", "new")},
            "start_bytes": dict(Counter(r["start"] for r in same).most_common(5)),
            "end_changed": len(ends),
            "largest_end_change": big_end and {k: big_end[k] for k in ("run_id", "earlier", "new", "start", "end")},
            "other_link": sum(1 for r in rows if not r["same_link"]),
            "not_acknowledged": sum(1 for r in rows if not r["acked"]),
            "short_request_before": sum(1 for r in rows if r["skipped"])}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("raw", nargs="+")
    ap.add_argument("--json")
    a = ap.parse_args()
    git = {"git_commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
           "git_dirty": bool(subprocess.run(["git", "status", "--porcelain", "--", ".", ":(exclude)data"],
                                            capture_output=True, text=True).stdout.strip())}
    out = {**git, "scopes": {"leakcheck": "every agent link the trace opened",
                             "padding": "the padded endpoints' links (edge agent → cloud agents)"},
           "arms": {}}
    for raw in map(Path, a.raw):
        meta = json.loads((raw / "session_meta.json").read_text())
        arm = next((x["name"] for x in meta["arms"] if Path(x["out"]).resolve() == raw.resolve()), raw.name)
        rows = defaultdict(lambda: defaultdict(list))
        for side, sc in _sidecars(raw):
            if sc.get("success") is False:
                continue
            recs = tcp_records(side.with_suffix(".pcap"), ack=True)
            tls, task = bool(sc.get("tls", True)), sc.get("task_type") or sc.get("workflow")
            rows["leakcheck"][task].append({"run_id": sc["run_id"], **measure(recs, _ports(sc), tls)})
            padded = _padded_ports(sc)
            if padded:
                m = measure(recs, padded, tls)
                if m["earlier"] or m["new"]:
                    rows["padding"][task].append({"run_id": sc["run_id"], **m})
        res = {}
        for scope, by_task in rows.items():
            res[scope] = {"all": summarise([r for v in by_task.values() for r in v]),
                          "by_task_type": {t: summarise(v) for t, v in sorted(by_task.items())}}
        out["arms"][arm] = {"raw_dir": str(raw), "collection_id": meta.get("collection_id"), **res}
        for scope, r in res.items():
            for t, s in [("all", r["all"]), *r["by_task_type"].items()]:
                print(f"{arm:10s} {scope:9s} {t:20s} {s['changed']:4d} of {s['traces']:4d} changed "
                      f"{s['change_bytes']}; start {s['start_bytes']}; end changed {s['end_changed']}, "
                      f"largest {s['largest_end_change']}; other link {s['other_link']}, "
                      f"not acknowledged {s['not_acknowledged']}, short request before {s['short_request_before']}")
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
