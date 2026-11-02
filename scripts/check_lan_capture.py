#!/usr/bin/env python3
"""
LAN pilot check: is every cross-host agent call in the capture?

In the LAN setup (docs/LAN_SETUP.md) the orchestrator runs on the Mac and the specialists on the
Raspberry Pi, so the calls that cross the link are the orchestrator's calls to specialists:
star → executor, retriever, validator; chain → executor; mesh → executor, retriever.
(Chain and mesh forwarding between specialists stays on the Pi and never reaches the link.)

For every successful trace this checks, from packet headers alone, that each expected specialist
port carries a complete call: a request after the TLS handshake (a request-direction write of
more than 100 B) and response data. It also flags requests to specialist ports the topology does
not call from the Mac. Specialist ports come from the trace's label sidecar.

Usage:
    python scripts/check_lan_capture.py data/raw_c2_pilot --json data/raw_c2_pilot/lan_check.json
Exit 1 if any trace misses a call.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from features.kfp import tcp_packets  # noqa: E402

CALLED = {"star": {"executor", "retriever", "validator"}, "chain": {"executor"},
          "mesh": {"executor", "retriever"}}
MIN_REQUEST = 100          # bytes; the TLS client Finished is 80, an A2A request several hundred


def check_trace(pcap: Path, sidecar: dict) -> dict:
    eps = sidecar["agent_endpoints"]
    port_role = {int(a.rsplit(":", 1)[1]): r for r, a in eps.items() if r != "orchestrator"}
    expected = CALLED[sidecar["topology"]]
    seen: dict[str, dict] = defaultdict(lambda: {"connections": set(), "requests": 0, "response_pkts": 0})
    hello: set = set()
    for _, sp, dp, _, pl, flags in tcp_packets(pcap):
        if dp in port_role:                                        # request direction
            s = seen[port_role[dp]]
            s["connections"].add(sp)
            if flags & 0x02 or pl == 0:
                continue
            if (sp, dp) not in hello:                              # first data: the ClientHello
                hello.add((sp, dp))
                continue
            if pl > MIN_REQUEST:
                s["requests"] += 1
        elif sp in port_role and pl > 0:
            seen[port_role[sp]]["response_pkts"] += 1
    missing = sorted(r for r in expected if seen[r]["requests"] == 0 or seen[r]["response_pkts"] == 0)
    # a request, not just packets: a previous trace's connections can close inside this capture
    unexpected = sorted(r for r in port_role.values() if r not in expected and seen[r]["requests"])
    return {"run_id": sidecar.get("run_id", pcap.stem), "topology": sidecar["topology"],
            "ok": not missing and not unexpected, "missing": missing, "unexpected": unexpected,
            "calls": {r: {"connections": len(v["connections"]), "request_writes": v["requests"],
                          "response_packets": v["response_pkts"]} for r, v in sorted(seen.items())}}


def main(a: argparse.Namespace) -> int:
    rows = []
    for d in a.dirs:
        for pcap in sorted(Path(d).glob("*.pcap")):
            side = pcap.with_suffix(".json")
            if not side.exists():
                continue
            sc = json.loads(side.read_text())
            if sc.get("success") is False:
                continue
            rows.append(check_trace(pcap, sc))
    bad = [r for r in rows if not r["ok"]]
    by_top = {t: {"traces": sum(r["topology"] == t for r in rows),
                  "ok": sum(r["topology"] == t and r["ok"] for r in rows)} for t in CALLED}
    summary = {"dirs": a.dirs, "traces": len(rows), "ok": len(rows) - len(bad), "by_topology": by_top,
               "failures": bad[:50], "pass": bool(rows) and not bad}
    for t, v in by_top.items():
        print(f"{t:6s} {v['ok']}/{v['traces']} traces with every cross-host call captured")
    for r in bad[:10]:
        print(f"  {r['run_id']}: missing {r['missing'] or '-'}, unexpected {r['unexpected'] or '-'}")
    print("PASS" if summary["pass"] else "FAIL")
    if a.json:
        Path(a.json).write_text(json.dumps(summary, indent=2))
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Check that every cross-host agent call was captured")
    p.add_argument("dirs", nargs="+")
    p.add_argument("--json", default=None)
    sys.exit(main(p.parse_args()))
