#!/usr/bin/env python3
"""
Check from the captures themselves whether specialist SSE replies streamed in full.

Until agents/base.py disabled sse-starlette's automatic graceful drain, a collector
that stopped one agent set and started another in the same process got every later
SSE response cut after its first event (sse-starlette sets a process-wide
AppStatus.should_exit when any uvicorn server exits). A cut reply is a handful of
packets; a streamed one carries one packet per generated chunk.

For every trace this takes the largest specialist reply: the most packets any
specialist agent port sent on one TCP connection. Specialist ports come from the
trace's label sidecar (agent_endpoints minus the orchestrator and the MCP server).
Per data set and topology it reports the median and the share of traces at or below
--cut-at packets. Failed runs are included: a cut stream is often what made them fail.
Headers only, so it works on payload-stripped captures.

Usage:
    python scripts/check_stream_integrity.py data/raw data/raw_b_sdk ...
    python scripts/check_stream_integrity.py --all --json data/results/stream_integrity.json
"""

from __future__ import annotations

import argparse
import ast
import json
import statistics
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.strip_payload import _MAGICS, _network_offset  # noqa: E402

NOT_SPECIALIST = {"orchestrator", "mcp"}


def specialist_ports(sidecar: dict) -> set[int]:
    eps = sidecar.get("agent_endpoints") or {}
    if isinstance(eps, str):                       # some collectors stored the dict's repr
        eps = ast.literal_eval(eps)
    return {int(str(v).rsplit(":", 1)[1]) for k, v in eps.items() if k not in NOT_SPECIALIST}


def largest_reply(pcap: Path, ports: set[int]) -> int:
    """Most packets sent by one specialist port on one connection."""
    raw = pcap.read_bytes()
    endian = _MAGICS.get(raw[:4])
    if endian is None:
        return 0
    linktype = struct.unpack(endian + "I", raw[20:24])[0]
    per_conn, pos = Counter(), 24
    while pos + 16 <= len(raw):
        incl = struct.unpack(endian + "I", raw[pos + 8:pos + 12])[0]
        d = raw[pos + 16:pos + 16 + incl]
        pos += 16 + incl
        off = _network_offset(linktype, d)
        if len(d) <= off:
            continue
        if d[off] >> 4 == 4:
            l4 = off + (d[off] & 0x0F) * 4
            proto = d[off + 9] if len(d) > off + 9 else None
        elif d[off] >> 4 == 6:
            l4, proto = off + 40, d[off + 6] if len(d) > off + 6 else None
        else:
            continue
        if proto != 6 or len(d) < l4 + 4:
            continue
        sport, dport = struct.unpack(">HH", d[l4:l4 + 4])
        if sport in ports:
            per_conn[(sport, dport)] += 1
    return max(per_conn.values(), default=0)


def scan(d: Path, cut_at: int) -> dict:
    by_topo = defaultdict(list)
    for pcap in sorted(d.glob("*.pcap")):
        sc_path = pcap.with_suffix(".json")
        if not sc_path.exists():                   # AutoGen / CrewAI name it <trace>.labels.json
            sc_path = pcap.with_suffix(".labels.json")
        try:
            sc = json.loads(sc_path.read_text())
        except (OSError, ValueError):
            continue
        ports = specialist_ports(sc)
        if not ports:
            continue
        by_topo[sc.get("topology") or "-"].append(largest_reply(pcap, ports))
    out = {}
    for topo, v in sorted(by_topo.items()):
        out[topo] = {"n": len(v), "median_largest_reply_pkts": statistics.median(v),
                     "min": min(v), "max": max(v),
                     "share_cut": sum(x <= cut_at for x in v) / len(v)}
    return out


def main(a: argparse.Namespace) -> None:
    dirs = sorted(p for p in Path("data").glob("raw*") if p.is_dir()) if a.all else [Path(x) for x in a.dirs]
    report = {"cut_at_pkts": a.cut_at, "sets": {}}
    for d in dirs:
        r = scan(d, a.cut_at)
        report["sets"][str(d)] = r
        if not r:
            print(f"{str(d):36s} no A2A specialist endpoints in the sidecars (not applicable)")
            continue
        cells = "  ".join(f"{t}: median {s['median_largest_reply_pkts']:g} pkts, "
                          f"cut {s['share_cut']:.0%} (n={s['n']})" for t, s in r.items())
        print(f"{str(d):36s} {cells}")
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Detect SSE replies cut after their first event")
    p.add_argument("dirs", nargs="*")
    p.add_argument("--all", action="store_true", help="every data/raw* directory")
    p.add_argument("--cut-at", type=int, default=15,
                   help="a largest reply at or below this many packets counts as cut (default 15)")
    p.add_argument("--json", default=None)
    main(p.parse_args())
