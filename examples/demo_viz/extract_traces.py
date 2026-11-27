#!/usr/bin/env python3
"""
The packets of a few C2B1 captures, in the compact form replay_template.html replays.

For each run id, found in DATA_DIR/raw_c2b1_padmax (arm "padded") or DATA_DIR/raw_c2b1_shaped
(arm "shaped"): its task type, the cloud agent that answered (role; null when the edge answered
itself) and every TCP packet between the edge and an agent endpoint its sidecar names, as
[t, agent, up, payload]:
  t        seconds from the run's first such packet, 4 decimals
  agent    "d" diagnostics, "k" knowledge, "t" ticket
  up       1 edge -> agent, 0 agent -> edge
  payload  TCP payload bytes, from the IP and TCP headers (header-only captures give the same)

    python examples/demo_viz/extract_traces.py --data-dir data --out examples/demo_viz/traces.json

Works on data/ as collected or as unzipped from the Zenodo archive (version 1.1, C2B1).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scapy.all import IP, TCP, rdpcap

ARMS = {"raw_c2b1_padmax": "padded", "raw_c2b1_shaped": "shaped"}
AGENTS = {"diagnostics": "d", "knowledge": "k", "ticket": "t"}
DEFAULT_IDS = [
    "sensor_analysis_edge_cloud_0085ae", "fault_diagnosis_edge_cloud_002c33",        # padded (raw_c2b1_padmax)
    "alert_triage_edge_cloud_03833a", "procedure_lookup_edge_cloud_05a417",
    "sensor_analysis_edge_cloud_019315", "fault_diagnosis_edge_cloud_01545a",        # shaped (raw_c2b1_shaped)
    "alert_triage_edge_cloud_011a15", "procedure_lookup_edge_cloud_007895",
]
HERE = Path(__file__).resolve().parent


def find(data_dir: Path, run_id: str) -> tuple[str, Path]:
    hits = [(arm, data_dir / folder / f"{run_id}.json") for folder, arm in ARMS.items()
            if (data_dir / folder / f"{run_id}.json").exists()]
    if len(hits) != 1:
        raise SystemExit(f"{run_id}: found in {len(hits)} of {', '.join(ARMS)} under {data_dir}")
    return hits[0]


def trace(arm: str, sidecar: Path) -> dict:
    sc = json.loads(sidecar.read_text())
    endpoints = {addr: AGENTS[role] for role, addr in sc["agent_endpoints"].items()}
    pkts = []
    for p in rdpcap(str(sidecar.with_suffix(".pcap"))):
        if IP not in p or TCP not in p:
            continue
        ip, tcp = p[IP], p[TCP]
        src, dst = f"{ip.src}:{tcp.sport}", f"{ip.dst}:{tcp.dport}"
        if dst in endpoints:
            agent, up = endpoints[dst], 1
        elif src in endpoints:
            agent, up = endpoints[src], 0
        else:
            continue
        pkts.append((float(p.time), agent, up, max(0, ip.len - ip.ihl * 4 - tcp.dataofs * 4)))
    if not pkts:
        raise SystemExit(f"{sidecar.stem}: no packet to or from an agent endpoint")
    t0 = pkts[0][0]
    return {"arm": arm, "task": sc["task_type"], "role": (sc.get("edge_report") or {}).get("cloud_role"),
            "p": [[round(t - t0, 4), a, u, n] for t, a, u, n in pkts]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    ap.add_argument("--data-dir", default="data", dest="data_dir", help="the folder holding raw_c2b1_padmax and raw_c2b1_shaped")
    ap.add_argument("--out", default=str(HERE / "traces.json"))
    ap.add_argument("--ids", nargs="+", default=DEFAULT_IDS, help="run ids (default: the demo's eight)")
    a = ap.parse_args(argv)
    out = [trace(*find(Path(a.data_dir), run_id)) for run_id in a.ids]
    Path(a.out).write_text(json.dumps(out, separators=(",", ":")) + "\n")
    for run_id, r in zip(a.ids, out):
        up = sum(x[3] for x in r["p"] if x[2])
        down = sum(x[3] for x in r["p"] if not x[2])
        print(f"{r['arm']:<6} {r['task']:<16} {run_id[-6:]}  {len(r['p']):>4} packets, last at {r['p'][-1][0]:6.2f} s, "
              f"up {up:>6} B, down {down:>6} B, role {r['role']}")
    print(f"-> {a.out} ({Path(a.out).stat().st_size:,} B)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
