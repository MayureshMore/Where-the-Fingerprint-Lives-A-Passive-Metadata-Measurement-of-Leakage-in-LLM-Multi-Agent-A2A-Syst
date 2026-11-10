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

Edge-cloud placement (sidecar topology edge_cloud; scripts/collect_session.py --placement
edge-cloud): the edge agent on the Pi calls the cloud agents and the ticket service. Each trace
must show
  * escalated tasks: a complete call to the cloud agent the routing rule names (agents/edge.py:
    diagnostics for sensor_analysis and fault_diagnosis, knowledge for procedure_lookup), and no
    request to the other cloud agent;
  * every task: exactly one ticket POST (one connection to the ticket service with a request
    after the handshake and response data);
  * alert_triage: nothing reaches the cloud alias (no connection opened to a cloud agent);
  * the edge agent's own report (sidecar edge_report) agrees with the rule.
Traces taken while the Pi was throttled (sidecar pi_throttled) are counted, not failed.

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

from agents.edge import ROUTES  # noqa: E402
from features.kfp import tcp_packets  # noqa: E402

CALLED = {"star": {"executor", "retriever", "validator"}, "chain": {"executor"},
          "mesh": {"executor", "retriever"}}
MIN_REQUEST = 100          # bytes; the TLS client Finished is 80, an A2A request several hundred


def _calls(pcap: Path, port_role: dict[int, str]) -> dict[str, dict]:
    """Per endpoint: connections opened (SYN seen), request writes after the ClientHello of more
    than MIN_REQUEST bytes, and response packets with data."""
    seen: dict[str, dict] = defaultdict(lambda: {"opened": set(), "connections": set(), "requests": 0,
                                                 "response_pkts": 0})
    hello: set = set()
    for _, sp, dp, _, pl, flags in tcp_packets(pcap):
        if dp in port_role:
            s = seen[port_role[dp]]
            s["connections"].add(sp)
            if flags & 0x02 and not flags & 0x10:
                s["opened"].add(sp)
            if flags & 0x02 or pl == 0:
                continue
            if (sp, dp) not in hello:
                hello.add((sp, dp))
                continue
            if pl > MIN_REQUEST:
                s["requests"] += 1
        elif sp in port_role and pl > 0:
            seen[port_role[sp]]["response_pkts"] += 1
    return seen


def check_edge_trace(pcap: Path, sidecar: dict) -> dict:
    eps = sidecar["agent_endpoints"]
    port_role = {int(a.rsplit(":", 1)[1]): r for r, a in eps.items()}
    seen = _calls(pcap, port_role)
    task = sidecar.get("task_type") or sidecar["workflow_class"]
    route = ROUTES[task]
    cloud = [r for r in eps if r != "ticket"]
    problems = []
    if route and (seen[route]["requests"] == 0 or seen[route]["response_pkts"] == 0):
        problems.append(f"no complete call to {route}")
    for r in cloud:
        if r != route and (seen[r]["requests"] or seen[r]["opened"]):
            problems.append(f"{'alert_triage reaches the cloud' if route is None else 'unexpected call'}: {r}")
    t = seen["ticket"]
    if len(t["opened"]) != 1 or t["requests"] == 0 or t["response_pkts"] == 0:
        problems.append(f"ticket POST: {len(t['opened'])} connections, {t['requests']} request writes")
    rep = sidecar.get("edge_report") or {}
    if rep.get("mismatch") or (rep.get("escalated") is not None and rep["escalated"] != bool(route)):
        problems.append("edge report disagrees with the routing rule")
    return {"run_id": sidecar.get("run_id", pcap.stem), "topology": "edge_cloud", "task_type": task,
            "ok": not problems, "problems": problems, "missing": [p for p in problems if p.startswith("no ")],
            "unexpected": [p for p in problems if not p.startswith("no ")], "pi_throttled": sidecar.get("pi_throttled"),
            "calls": {r: {"connections_opened": len(v["opened"]), "request_writes": v["requests"],
                          "response_packets": v["response_pkts"]} for r, v in sorted(seen.items())}}


def check_trace(pcap: Path, sidecar: dict) -> dict:
    if sidecar.get("topology") == "edge_cloud":
        return check_edge_trace(pcap, sidecar)
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
    groups = sorted({r.get("task_type") or r["topology"] for r in rows}) if any(
        r["topology"] == "edge_cloud" for r in rows) else list(CALLED)
    key = (lambda r: r.get("task_type") or r["topology"])
    by_top = {t: {"traces": sum(key(r) == t for r in rows), "ok": sum(key(r) == t and r["ok"] for r in rows)}
              for t in groups}
    throttled = sum(1 for r in rows if r.get("pi_throttled"))
    summary = {"dirs": a.dirs, "traces": len(rows), "ok": len(rows) - len(bad), "by_topology": by_top,
               "throttled_traces": throttled, "failures": bad[:50], "pass": bool(rows) and not bad}
    for t, v in by_top.items():
        print(f"{t:16s} {v['ok']}/{v['traces']} traces with every expected call captured")
    if throttled:
        print(f"{throttled} traces taken while the Pi was throttled (sidecar pi_throttled)")
    for r in bad[:10]:
        print(f"  {r['run_id']}: " + ("; ".join(r["problems"]) if "problems" in r else
                                      f"missing {r['missing'] or '-'}, unexpected {r['unexpected'] or '-'}"))
    print("PASS" if summary["pass"] else "FAIL")
    if a.json:
        Path(a.json).write_text(json.dumps(summary, indent=2))
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Check that every cross-host agent call was captured")
    p.add_argument("dirs", nargs="+")
    p.add_argument("--json", default=None)
    sys.exit(main(p.parse_args()))
