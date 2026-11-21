#!/usr/bin/env python3
"""
Reply shaping as the capture sees it (paper 2 round 2, B1): is every shaped cloud reply the same
number of bytes on the wire, released at the same time after its request, and never cut or late? And
what does the shaping cost, per task type, against an unshaped control arm collected in the same
session (B1: lan_shaped against lan_padmax)?

Per successful trace, from its header-only capture and sidecar. Bytes come from TCP sequence numbers
(the highest byte sent minus the first), so they do not depend on how TCP cuts or coalesces the
stream, nor on retransmissions; times are the capture's (the Mac's interface, where the cloud's
packets are sent and the Pi's arrive):

    cloud call     an escalated task's connections from the edge to its cloud agent; the one with the
                   most request bytes carries the task (the POST and its SSE reply)
    reply_bytes    the cloud → edge bytes of that connection: its TLS handshake and session tickets, the
                   HTTP headers, every SSE event, the end of the stream
    release_s      from the request's last byte to the reply's last byte; first_s to the first cloud
                   byte after the request (the session tickets go out before the request has ended)
    trace_bytes    the TCP payload bytes of the whole capture, both directions, every connection
    total_s        the task, as the collector timed it (sidecar end_ts − start_ts)
    cloud_s        the edge agent's cloud call (edge_report.seconds.answer)

Checks on the shaped arm (exit 1 if any fails):

    identical      one reply_bytes value over every shaped reply
    release        every release_s within --tolerance-ms of their median, and the median within
                   --tolerance-ms of the spec's release time (the last event's time plus the artifact)
                   plus the emulated WAN's round trip (--wan-ms)
    cut, overrun   0 in the cloud's own record (each sidecar's cloud_replies), and every escalated
                   shaped trace has that record, with the spec

With --control, the same measures for the control arm and, per task type, the medians of both arms and
the shaped arm's overhead (shaped − control) in bytes and seconds. With --out, a results JSON and .md
with commit, collection_id and data folders, refused from uncommitted code (unless --allow-dirty) and
never written over an existing file.

    python scripts/check_shaping.py data/raw_c2b1_shaped --control data/raw_c2b1_padmax --wan-ms 12 \\
        --json data/raw_c2b1_shaped/shaping_check.json
    python scripts/check_shaping.py data/raw_c2b1_shaped --control data/raw_c2b1_padmax --wan-ms 12 \\
        --out data/results/b1_shaping_overhead
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from defense.shaping import ShapeConfig  # noqa: E402
from features.kfp import tcp_records  # noqa: E402

SYN, FIN = 0x02, 0x01


def connections(pcap: Path, port: int) -> list[dict]:
    """Per connection to port (keyed by the edge's port): bytes and first/last payload time per direction."""
    conns: dict[int, dict] = {}
    for ts, sp, dp, _, pl, fl, seq in tcp_records(pcap):
        if dp == port:
            k, d = sp, "req"
        elif sp == port:
            k, d = dp, "rep"
        else:
            continue
        c = conns.setdefault(k, {"edge_port": k, "req": {}, "rep": {}})[d]
        if fl & SYN:
            c.clear()
            c["isn"] = seq
            continue
        if pl <= 0:
            continue
        lo = seq if "isn" not in c else c["isn"] + 1
        c["lo"] = min(c.get("lo", lo), lo, seq)
        if seq + pl > c.get("hi", -1):                  # new bytes at the top: a retransmission is not the end
            c["hi"], c["last"] = seq + pl, ts
        c.setdefault("times", []).append(ts)
    out = []
    for c in conns.values():
        row = {"edge_port": c["edge_port"]}
        for d in ("req", "rep"):
            s = c[d]
            row[f"{d}_bytes"] = (s["hi"] - s["lo"]) % 2**32 if "hi" in s else 0
            row[f"{d}_last"] = s.get("last")
        after = [t for t in c["rep"].get("times", []) if row["req_last"] is not None and t > row["req_last"]]
        row["rep_first"] = min(after) if after else None
        out.append(row)
    return out


def trace_bytes(pcap: Path) -> int:
    return sum(r[4] for r in tcp_records(pcap))


def measure(folder: Path) -> list[dict]:
    rows = []
    for side in sorted(folder.glob("*_edge_cloud_*.json")):
        sc = json.loads(side.read_text())
        pcap = side.with_suffix(".pcap")
        if not sc.get("success") or not pcap.exists():
            continue
        er = sc.get("edge_report") or {}
        row = {"run": side.stem, "arm": sc.get("arm"), "round": sc.get("round"), "task_type": sc.get("task_type"),
               "escalated": bool(er.get("escalated")), "total_s": sc["end_ts"] - sc["start_ts"],
               "cloud_s": (er.get("seconds") or {}).get("answer"), "trace_bytes": trace_bytes(pcap)}
        if er.get("escalated") and er.get("cloud_role"):
            port = int(sc["agent_endpoints"][er["cloud_role"]].rsplit(":", 1)[1])
            conns = connections(pcap, port)
            if conns:
                c = max(conns, key=lambda r: r["req_bytes"])
                ok = c["req_last"] is not None and c["rep_last"] is not None
                row.update({"cloud_port": port, "connections": len(conns), "request_bytes": c["req_bytes"],
                            "reply_bytes": c["rep_bytes"],
                            "other_reply_bytes": sum(r["rep_bytes"] for r in conns if r is not c),
                            "release_s": c["rep_last"] - c["req_last"] if ok else None,
                            "first_s": c["rep_first"] - c["req_last"] if ok and c["rep_first"] else None})
            recs = [r for r in sc.get("cloud_replies") or [] if r.get("port") == port]
            row["shaping"] = recs[-1]["shaping"] if recs and recs[-1].get("shaping") else None
        rows.append(row)
    return rows


def _med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def summary(rows: list[dict]) -> dict:
    out = {}
    for tt in sorted({r["task_type"] for r in rows}):
        sub = [r for r in rows if r["task_type"] == tt]
        esc = [r for r in sub if "reply_bytes" in r]
        out[tt] = {"n": len(sub), "escalated": len(esc),
                   "trace_bytes": _med(r["trace_bytes"] for r in sub), "total_s": _med(r["total_s"] for r in sub),
                   "cloud_s": _med(r["cloud_s"] for r in esc), "request_bytes": _med(r["request_bytes"] for r in esc),
                   "reply_bytes": _med(r["reply_bytes"] for r in esc), "release_s": _med(r["release_s"] for r in esc)}
    return out


def checks(rows: list[dict], spec: str, wan_ms: float, tol_ms: float) -> dict:
    shape = ShapeConfig.parse(spec)
    esc = [r for r in rows if "reply_bytes" in r]
    sizes = sorted({r["reply_bytes"] for r in esc})
    rel = [r["release_s"] for r in esc if r["release_s"] is not None]
    med = statistics.median(rel) if rel else None
    expect = shape.release_s() + wan_ms / 1000
    recs = [r["shaping"] for r in esc if r.get("shaping")]
    missing = [r["run"] for r in esc if not r.get("shaping") or r["shaping"].get("spec") != shape.spec()]
    res = {
        "identical": {"ok": len(sizes) == 1 and len(esc) > 0, "replies": len(esc), "reply_bytes": sizes,
                      "other_reply_bytes": sorted({r["other_reply_bytes"] for r in esc}),
                      "request_bytes": sorted({r["request_bytes"] for r in esc})},
        "release": {"ok": bool(rel) and len(rel) == len(esc) and max(abs(x - med) for x in rel) * 1000 <= tol_ms
                    and abs(med - expect) * 1000 <= tol_ms,
                    "median_s": med, "min_s": min(rel) if rel else None, "max_s": max(rel) if rel else None,
                    "spread_ms": (max(rel) - min(rel)) * 1000 if rel else None, "expected_s": expect,
                    "tolerance_ms": tol_ms, "first_s_median": _med(r["first_s"] for r in esc),
                    "spec_release_s": shape.release_s(), "wan_ms": wan_ms},
        "cut_overrun": {"ok": not missing and not any(s.get("truncated") or s.get("overrun") for s in recs),
                        "records": len(recs), "cut": sum(bool(s.get("truncated")) for s in recs),
                        "overrun": sum(bool(s.get("overrun")) for s in recs), "missing_or_other_spec": missing,
                        "generated_s_max": max((s["generated_s"] for s in recs), default=None),
                        "released_s": sorted({round(s["released_s"], 2) for s in recs})},
    }
    res["ok"] = all(v["ok"] for v in res.values())
    return res


def overhead(shaped: dict, control: dict) -> dict:
    out = {}
    for tt in sorted(set(shaped) & set(control)):
        s, c = shaped[tt], control[tt]
        out[tt] = {k: (s[k] - c[k]) if s[k] is not None and c[k] is not None else None
                   for k in ("trace_bytes", "total_s", "cloud_s", "reply_bytes", "release_s")}
        if c["trace_bytes"]:
            out[tt]["trace_bytes_ratio"] = s["trace_bytes"] / c["trace_bytes"]
    return out


def _git() -> dict:
    def run(*args):
        return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()
    return {"git_commit": run("rev-parse", "HEAD") or None,
            "git_dirty": bool(run("status", "--porcelain", "--", ".", ":(exclude)data"))}


def _collection(folder: Path) -> str | None:
    m = folder / "session_meta.json"
    return json.loads(m.read_text()).get("collection_id") if m.exists() else None


def markdown(res: dict) -> str:
    c = res["checks"]
    lines = [f"# Reply shaping {res['shape']} on the wire: {res['arm']['name']}"
             + (f" against {res['control']['name']}" if res.get("control") else ""), "",
             f"Commit `{res['git_commit'][:8]}` (clean: {not res['git_dirty']}); {res['collection_id']}, "
             f"`{res['data_dir']['shaped']}`" + (f" against `{res['data_dir']['control']}`" if res.get("control") else "") + ".", "",
             "| Check | Result | |", "|---|---|---|",
             f"| Identical replies | {'PASS' if c['identical']['ok'] else 'FAIL'} | {c['identical']['replies']} replies, "
             f"bytes {c['identical']['reply_bytes']} |",
             f"| Release time | {'PASS' if c['release']['ok'] else 'FAIL'} | median {c['release']['median_s']:.3f} s "
             f"(expected {c['release']['expected_s']:.3f}), spread {c['release']['spread_ms']:.1f} ms |"
             if c["release"]["median_s"] is not None else f"| Release time | FAIL | no replies |",
             f"| Cut, overrun | {'PASS' if c['cut_overrun']['ok'] else 'FAIL'} | {c['cut_overrun']['cut']} cut, "
             f"{c['cut_overrun']['overrun']} overrun, {len(c['cut_overrun']['missing_or_other_spec'])} without the record |", ""]
    if res.get("control"):
        lines += ["| Task type | Arm | n | Trace bytes | Reply bytes | Task s | Cloud call s |", "|---|---|---|---|---|---|---|"]
        f = lambda v, p=0: "-" if v is None else f"{v:,.{p}f}"  # noqa: E731
        for tt in res["arm"]["by_task_type"]:
            for name, s in (("shaped", res["arm"]["by_task_type"][tt]), ("control", res["control"]["by_task_type"].get(tt))):
                if s:
                    lines.append(f"| {tt} | {name} | {s['n']} | {f(s['trace_bytes'])} | {f(s['reply_bytes'])} | "
                                 f"{f(s['total_s'], 2)} | {f(s['cloud_s'], 2)} |")
            o = res["overhead"].get(tt)
            if o:
                lines.append(f"| {tt} | shaped − control | | {f(o['trace_bytes'])} | {f(o['reply_bytes'])} | "
                             f"{f(o['total_s'], 2)} | {f(o['cloud_s'], 2)} |")
        lines.append("")
        lines.append("Medians per task type; bytes from TCP sequence numbers in header-only captures.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("shaped", type=Path)
    p.add_argument("--control", type=Path)
    p.add_argument("--shape", default="2048/14/128/0.05/truncate")
    p.add_argument("--wan-ms", type=float, default=12.0, dest="wan_ms", help="the emulated round trip (C2: 12 ms)")
    p.add_argument("--tolerance-ms", type=float, default=50.0, dest="tol_ms")
    p.add_argument("--json", type=Path)
    p.add_argument("--out", help="results path without extension (.json, .md)")
    p.add_argument("--allow-dirty", action="store_true", dest="allow_dirty")
    a = p.parse_args(argv)
    git = _git()
    if a.out:
        if git["git_dirty"] and not a.allow_dirty:
            raise SystemExit("uncommitted code: commit first (or --allow-dirty for a dry run)")
        for ext in (".json", ".md"):
            if Path(a.out + ext).exists():
                raise SystemExit(f"{a.out + ext} exists: results are never written over")
    rows = measure(a.shaped)
    arm = {"name": rows[0]["arm"] if rows else None, "traces": len(rows), "by_task_type": summary(rows)}
    res = {"paper": "P2", "round": 2, "collection_id": _collection(a.shaped), "shape": a.shape,
           "data_dir": {"shaped": str(a.shaped)}, **git, "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "seed": None,
           "checks": checks(rows, a.shape, a.wan_ms, a.tol_ms), "arm": arm}
    if a.control:
        crows = measure(a.control)
        res["data_dir"]["control"] = str(a.control)
        res["control"] = {"name": crows[0]["arm"] if crows else None, "traces": len(crows), "by_task_type": summary(crows),
                          "collection_id": _collection(a.control)}
        res["overhead"] = overhead(arm["by_task_type"], res["control"]["by_task_type"])
        res["control_runs"] = crows
    res["runs"] = rows
    md = markdown(res)
    print(md)
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(res, indent=2))
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out + ".json").write_text(json.dumps(res, indent=2))
        Path(a.out + ".md").write_text(md)
    return 0 if res["checks"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
