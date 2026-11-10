#!/usr/bin/env python3
"""
Pilot check for C2's emulated WAN (docs/LAN_SETUP.md): the edge agent on the Pi measures its TCP
connect time to the cloud alias (POST /probe on its trigger port, outside any capture), and the
median must be within ±--tolerance of the target delay that scripts/measure_cloud_rtt.py set.
Exit 1 otherwise (the emulation is off, or applied to the wrong address or interface).

Usage (Mac, with scripts/serve_edge.py and scripts/serve_cloud.py running):
    python scripts/check_wan_emulation.py --json data/raw_c2_pilot/wan_check.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.edge import TRIGGER_PORT  # noqa: E402


def main(a: argparse.Namespace) -> int:
    target = json.loads(Path(a.target).read_text())
    rows = []
    for base in (int(b) for b in a.bases.split(",")):
        r = httpx.post(f"http://{a.edge_host}:{base + TRIGGER_PORT}/probe", json={"n": a.n}, timeout=300).json()
        dev = (r["median_ms"] - target["delay_ms"]) / target["delay_ms"]
        rows.append({"base": base, **r, "target_ms": target["delay_ms"], "deviation": dev,
                     "ok": abs(dev) <= a.tolerance})
        print(f"edge {base}: connect to {r['host']}:{r['port']} median {r['median_ms']:.1f} ms "
              f"(target {target['delay_ms']} ms, {dev:+.0%})  {'ok' if abs(dev) <= a.tolerance else 'FAIL'}")
    out = {"target": {k: target[k] for k in ("endpoint", "median_ms", "delay_ms", "jitter_ms", "netem")},
           "tolerance": a.tolerance, "edges": rows, "pass": all(r["ok"] for r in rows)}
    print("PASS" if out["pass"] else "FAIL")
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=2))
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--target", default="data/results/c2_wan_emulation.json")
    p.add_argument("--edge-host", default="192.168.2.2", dest="edge_host")
    p.add_argument("--bases", default="8100,8200,8300")
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--tolerance", type=float, default=0.20)
    p.add_argument("--json", default=None)
    sys.exit(main(p.parse_args()))
