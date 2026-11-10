#!/usr/bin/env python3
"""
C2's emulated WAN (docs/LAN_SETUP.md): the delay between the edge agent and the cloud alias is set
from a measurement, not a guess. From the Mac, curl's TCP connect time (time_connect: one round
trip) to a public cloud region endpoint, --tries times; the netem delay is the median and the
jitter half the interquartile range. Writes the raw times, the summary and the exact tc commands
for the Pi (scripts/wan_emulation.sh applies them) to data/results/c2_wan_emulation.json.

Usage (Mac, on the network the building would use):
    python scripts/measure_cloud_rtt.py                      # https://ec2.us-west-1.amazonaws.com, 30 tries
    python scripts/measure_cloud_rtt.py --endpoint https://ec2.us-east-2.amazonaws.com
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import time
from pathlib import Path

CLOUD = "192.168.2.100"
DEV = "eth0"


def tc_commands(delay_ms: int, jitter_ms: int, dev: str = DEV, cloud: str = CLOUD) -> list[str]:
    """prio qdisc with a fourth band that the default priomap never uses; netem on that band; a
    u32 filter sends only traffic to the cloud alias there. A pfifo child keeps netem from
    reordering packets when jitter is on (netem's own queue sorts by send time)."""
    return [f"tc qdisc del dev {dev} root 2>/dev/null || true",
            f"tc qdisc add dev {dev} root handle 1: prio bands 4 priomap 1 2 2 2 1 2 0 0 1 1 1 1 1 1 1 1",
            f"tc qdisc add dev {dev} parent 1:4 handle 40: netem delay {delay_ms}ms {jitter_ms}ms distribution normal",
            f"tc qdisc add dev {dev} parent 40:1 handle 41: pfifo limit 1000",
            f"tc filter add dev {dev} parent 1: protocol ip prio 1 u32 match ip dst {cloud}/32 flowid 1:4"]


def _git() -> dict:
    def run(*args):
        return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()
    return {"git_commit": run("rev-parse", "HEAD") or None,
            "git_dirty": bool(run("status", "--porcelain", "--", ".", ":(exclude)data"))}


def main(a: argparse.Namespace) -> None:
    times, failures = [], 0
    for _ in range(a.tries):
        r = subprocess.run(["curl", "-s", "-o", "/dev/null", "--connect-timeout", "5", "-w", "%{time_connect}",
                            a.endpoint], capture_output=True, text=True)
        try:
            t = float(r.stdout.strip()) * 1000
        except ValueError:
            t = 0.0
        if t > 0:
            times.append(t)
        else:
            failures += 1
        time.sleep(a.gap)
    if len(times) < a.tries // 2:
        raise SystemExit(f"only {len(times)} of {a.tries} connects succeeded to {a.endpoint}")
    q1, med, q3 = statistics.quantiles(times, n=4)
    delay, jitter = round(med), max(1, round((q3 - q1) / 2))
    out = {"paper": "P2", "collection_id": "C2", "purpose": "netem delay between the edge agent (Pi) and the cloud alias",
           "endpoint": a.endpoint, "measured_from": platform.node(), "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "method": "curl time_connect (TCP handshake, one round trip), sequential tries",
           "tries": a.tries, "failures": failures, "time_connect_ms": times,
           "median_ms": med, "q1_ms": q1, "q3_ms": q3, "iqr_ms": q3 - q1, "min_ms": min(times), "max_ms": max(times),
           "delay_ms": delay, "jitter_ms": jitter, "netem": f"delay {delay}ms {jitter}ms distribution normal",
           "applied_on": f"the Pi's egress ({DEV}) to {CLOUD} only: the whole round trip on one direction",
           "tc_commands": tc_commands(delay, jitter), "check": "scripts/check_wan_emulation.py: median within ±20%",
           **_git()}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2))
    print(f"{a.endpoint}: median {med:.1f} ms, IQR {q3 - q1:.1f} ms ({len(times)} tries) → netem {out['netem']} → {a.out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--endpoint", default="https://ec2.us-west-1.amazonaws.com")
    p.add_argument("--tries", type=int, default=30)
    p.add_argument("--gap", type=float, default=0.5, help="seconds between tries")
    p.add_argument("--out", default="data/results/c2_wan_emulation.json")
    main(p.parse_args())
