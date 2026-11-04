#!/usr/bin/env python3
"""
What the own-connection rule (features/connections.py) drops, per trace.

For every capture: the agent-port connections whose SYN is not in the capture, with their
packets, bytes, TCP flags, payload sizes, and whether any carries application data beyond the
close. A close is FIN/ACK/RST segments without payload and, under TLS 1.3, close_notify alerts
(one encrypted alert record: 5 B header + 2 B alert + 1 B content type + 16 B tag = 24 B). Any
other payload on a dropped connection is request or response data: either the previous trace's
data still in flight, or one of this trace's own connections whose SYN the capture missed.

Writes data/results/dropped_connections_<set>.json and prints a summary.

Usage:
    python scripts/audit_dropped_connections.py --raw data/raw_c1 --name c1
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from features.connections import opened_connections  # noqa: E402
from features.kfp import tcp_packets  # noqa: E402

CLOSE_NOTIFY = 24
FLAG_NAMES = ((0x01, "F"), (0x02, "S"), (0x04, "R"), (0x08, "P"), (0x10, "A"), (0x20, "U"))


def flag_str(fl: int) -> str:
    return "".join(n for bit, n in FLAG_NAMES if fl & bit) or "."


def _git() -> dict:
    run = lambda *a: subprocess.run(["git", *a], capture_output=True, text=True).stdout.strip()  # noqa: E731
    return {"git_commit": run("rev-parse", "HEAD"),
            "git_dirty": bool(run("status", "--porcelain", "--", ".", ":(exclude)data"))}


def audit_trace(pcap: Path, servers: set[int], tls: bool) -> dict:
    pk = [p for p in tcp_packets(pcap) if p[1] in servers or p[2] in servers]
    opened = opened_connections(pk, servers)
    conns: dict[tuple[int, int], list] = {}
    for p in pk:
        key = (p[1], p[2]) if p[2] in servers else (p[2], p[1])      # (client port, agent port)
        if key not in opened:
            conns.setdefault(key, []).append(p)
    out = []
    for (cport, aport), ps in sorted(conns.items()):
        data = [(("request" if p[2] == aport else "response"), p[4], flag_str(p[5])) for p in ps if p[4] > 0]
        close_only = all(tls and n == CLOSE_NOTIFY for _, n, _ in data)
        out.append({"client_port": cport, "agent_port": aport, "packets": len(ps),
                    "bytes": sum(p[3] for p in ps), "payload_bytes": sum(p[4] for p in ps),
                    "flags": dict(Counter(flag_str(p[5]) for p in ps)),
                    "payload_segments": [{"dir": d, "len": n, "flags": f} for d, n, f in data],
                    "first_offset_s": round(ps[0][0] - pk[0][0], 6),
                    "last_offset_s": round(ps[-1][0] - pk[0][0], 6),
                    "application_data": not close_only})
    return {"packets_total": len(pk), "dropped_packets": sum(c["packets"] for c in out),
            "dropped_bytes": sum(c["bytes"] for c in out), "connections": out,
            "application_data": any(c["application_data"] for c in out)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--name", required=True)
    a = ap.parse_args()
    raw = Path(a.raw)
    per, flags, sizes = {}, Counter(), Counter()
    for side in sorted(raw.glob("*.json")):
        sc = json.loads(side.read_text())
        if "run_id" not in sc or sc.get("success") is False or not side.with_suffix(".pcap").exists():
            continue
        eps = sc["agent_endpoints"]
        eps = ast.literal_eval(eps) if isinstance(eps, str) else eps
        servers = {int(str(v).rsplit(":", 1)[1]) for v in eps.values()}
        r = audit_trace(side.with_suffix(".pcap"), servers, bool(sc.get("tls", True)))
        per[sc["run_id"]] = r
        for c in r["connections"]:
            flags.update(c["flags"])
            sizes.update(f"{s['dir']} {s['len']}" for s in c["payload_segments"])
    flagged = sorted(k for k, r in per.items() if r["application_data"])
    with_drop = [r for r in per.values() if r["dropped_packets"]]
    summary = {
        "traces": len(per), "traces_with_dropped_packets": len(with_drop),
        "dropped_connections": sum(len(r["connections"]) for r in per.values()),
        "dropped_packets": sum(r["dropped_packets"] for r in per.values()),
        "dropped_bytes": sum(r["dropped_bytes"] for r in per.values()),
        "dropped_share_of_packets": sum(r["dropped_packets"] for r in per.values()) /
                                    max(sum(r["packets_total"] for r in per.values()), 1),
        "flags": dict(flags.most_common()), "payload_segments": dict(sizes.most_common()),
        "traces_with_application_data": len(flagged), "flagged_traces": flagged,
        "max_dropped_last_offset_s": max((c["last_offset_s"] for r in per.values() for c in r["connections"]),
                                         default=0.0),
    }
    out = {"paper": "P1", "check": "packets the own-connection rule drops", "raw_dir": str(raw), **_git(),
           "close_definition": "FIN/ACK/RST without payload; under TLS a 24 B close_notify record",
           "summary": summary, "traces": per}
    path = Path(f"data/results/dropped_connections_{a.name}.json")
    path.write_text(json.dumps(out, indent=1))
    print(json.dumps(summary, indent=1))
    print("wrote", path)


if __name__ == "__main__":
    main()
