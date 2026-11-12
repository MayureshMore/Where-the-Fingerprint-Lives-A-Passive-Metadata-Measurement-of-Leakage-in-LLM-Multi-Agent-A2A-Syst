#!/usr/bin/env python3
"""
C2's emulated WAN (docs/LAN_SETUP.md, section 8): the delay between the edge agent and the cloud
alias is set from measurements, not a guess, so that the Pi's round trip to the cloud alias matches
a real one end to end. From the Mac: curl's TCP connect time (time_connect: one round trip) to a
public cloud region endpoint, --tries times (the cloud round trip), and pings to the Pi, the round
trip the home network itself adds between the Pi and the Mac (the base round trip). The dummynet
delay is the median cloud round trip minus the median base round trip, split evenly each way,
floored at 0. Writes the raw times, the three numbers (target_rtt_ms, base_rtt, total_delay_ms;
delay_ms is the round trip dummynet applies in whole milliseconds) and the emulation settings to
data/results/c2_wan_emulation.json:

  emulation           primary, on the Mac (scripts/wan_emulation.sh): pf dummynet in the anchor
                      com.apple/c2-wan on the Mac's interface (C2_IFACE), half the delay each way
                      (Pi → cloud alias as it enters the Mac, cloud alias → Pi as it leaves), so
                      the capture sits on the building side of the delay; the same anchor's port
                      lock lets only the Pi reach the cloud and ticket ports. dummynet has no
                      jitter: the delay is constant and the cloud round trip's spread is not
                      reproduced.
  fallback_pi_netem   only if the Mac emulation cannot run (scripts/wan_emulation_pi.sh): netem on
                      the Pi's egress to the cloud alias, the same delay, jitter = half the cloud
                      round trip's IQR; the capture then sits on the cloud side of the delay.

Addresses and interfaces come from configs/c2_network.conf. Usage (Mac, the Pi reachable):
    python scripts/measure_cloud_rtt.py                      # https://ec2.us-west-1.amazonaws.com, 30 tries
    python scripts/measure_cloud_rtt.py --endpoint https://ec2.us-east-2.amazonaws.com
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import statistics
import subprocess
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.edge import c2_network, require  # noqa: E402

ANCHOR = "com.apple/c2-wan"


def lock_ports(bases: list[int]) -> list[int]:
    """The Mac's C2 ports: the cloud agents (B+1, B+2) and the ticket service (B+5) of every arm."""
    return sorted(p for b in bases for p in (b + 1, b + 2, b + 5))


def anchor_rules(one_way_ms: int, iface: str, pi: str, cloud: str, mac: str, bases: list[int]) -> list[str]:
    """The anchor's rules: dummynet both ways between the Pi and the cloud alias, then the port lock
    (the cloud agents' and ticket service's ports on the Mac's two addresses accept the Pi only).
    pf requires dummynet rules before filter rules."""
    ports = " ".join(str(p) for p in lock_ports(bases))
    return [f"dummynet in quick on {iface} proto tcp from {pi} to {cloud} pipe 1",
            f"dummynet out quick on {iface} proto tcp from {cloud} to {pi} pipe 2",
            f"pass in quick on {iface} proto tcp from {pi} to {{ {mac} {cloud} }} port {{ {ports} }}",
            f"block in quick on {iface} proto tcp from any to {{ {mac} {cloud} }} port {{ {ports} }}"]


def mac_commands(one_way_ms: int, iface: str, pi: str, cloud: str, mac: str, bases: list[int]) -> list[str]:
    """What scripts/wan_emulation.sh on runs (as root): two dummynet pipes and the anchor's rules,
    which /etc/pf.conf's dummynet-anchor and anchor "com.apple/*" evaluate; pfctl -E returns a token
    that off releases."""
    rules = "\\n".join(anchor_rules(one_way_ms, iface, pi, cloud, mac, bases))
    return [f"dnctl pipe 1 config delay {one_way_ms}", f"dnctl pipe 2 config delay {one_way_ms}",
            f"printf '{rules}\\n' | pfctl -a {ANCHOR} -f -", "pfctl -E"]


def emulated_delay(cloud_median_ms: float, base_median_ms: float) -> tuple[float, int, int]:
    """End-to-end match: (total delay = cloud − base floored at 0, one way in whole ms, applied
    round trip = twice that). The Pi's round trip to the cloud alias is then base + applied."""
    total = max(0.0, cloud_median_ms - base_median_ms)
    one_way = round(total / 2)
    return total, one_way, 2 * one_way


def ping_rtt(host: str, n: int, gap: float) -> list[float]:
    """Round trips to host in ms (ping from this machine; ICMP echo, one round trip each)."""
    out = subprocess.run(["ping", "-c", str(n), "-i", str(gap), host], capture_output=True, text=True).stdout
    return [float(m) for m in re.findall(r"time=([\d.]+) ms", out)]


def tc_commands(delay_ms: int, jitter_ms: int, dev: str, cloud: str) -> list[str]:
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
    net = c2_network()                 # the commands name these addresses and interfaces
    iface = require(net["C2_IFACE"], "the Mac's interface (C2_IFACE)")
    pi = require(net["C2_PI"], "the Pi's address (C2_PI)")
    cloud = require(net["C2_CLOUD"], "the cloud alias (C2_CLOUD)")
    mac = require(net["C2_MAC"], "the Mac's address (C2_MAC)")
    dev = net["C2_PI_IFACE"] or "wlan0"
    bases = [int(b) for b in (net["C2_BASES"] or "8100,8200,8300").split(",")]
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
    base = ping_rtt(pi, a.base_tries, a.base_gap)
    if len(base) < a.base_tries // 2:
        raise SystemExit(f"only {len(base)} of {a.base_tries} pings answered by the Pi at {pi}")
    q1, med, q3 = statistics.quantiles(times, n=4)
    b1, bmed, b3 = statistics.quantiles(base, n=4)
    total, one_way, applied = emulated_delay(med, bmed)
    jitter = max(1, round((q3 - q1) / 2))
    out = {"paper": "P2", "collection_id": "C2", "purpose": "emulated WAN between the edge agent (Pi) and the cloud alias",
           "rule": "end-to-end match: dummynet delay = median cloud round trip (Mac → endpoint) − median base round "
                   "trip (Pi ↔ Mac), split evenly each way, floored at 0; the Pi's round trip to the cloud alias "
                   "should then equal the measured cloud round trip",
           "endpoint": a.endpoint, "measured_from": platform.node(), "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "cloud_rtt": {"method": "curl time_connect from the Mac (TCP handshake, one round trip), sequential tries",
                         "tries": a.tries, "failures": failures, "time_connect_ms": times, "median_ms": med,
                         "q1_ms": q1, "q3_ms": q3, "iqr_ms": q3 - q1, "min_ms": min(times), "max_ms": max(times)},
           "base_rtt": {"method": f"ping from the Mac to the Pi ({pi}), {a.base_tries} echoes {a.base_gap} s apart: "
                                  "the round trip the home network adds between the Pi and the Mac",
                        "rtt_ms": base, "median_ms": bmed, "q1_ms": b1, "q3_ms": b3, "iqr_ms": b3 - b1,
                        "min_ms": min(base), "max_ms": max(base)},
           "total_delay_ms": total, "target_rtt_ms": med, "delay_ms": applied, "jitter_ms": 0,
           "emulation": {
               "where": f"Mac, pf dummynet in anchor {ANCHOR} on {iface}: the capture point is on the building side",
               "iface": iface, "pi": pi, "cloud": cloud, "mac": mac, "bases": bases,
               "one_way_ms": one_way, "round_trip_ms": applied, "jitter_ms": 0,
               "jitter_note": f"dummynet has no jitter: the delay is constant; the cloud round trip's spread "
                              f"(IQR {q3 - q1:.1f} ms) is not reproduced, the Wi-Fi's own spread (IQR "
                              f"{b3 - b1:.1f} ms) is there",
               "port_lock": f"the Mac's ports {lock_ports(bases)} on {mac} and {cloud} accept only {pi}",
               "rules": anchor_rules(one_way, iface, pi, cloud, mac, bases),
               "commands": mac_commands(one_way, iface, pi, cloud, mac, bases)},
           "fallback_pi_netem": {
               "where": f"Pi egress ({dev}) to {cloud} only, the whole delay on one direction: the capture then "
                        "sits on the cloud side of the delay",
               "dev": dev, "cloud": cloud,
               "delay_ms": applied, "jitter_ms": jitter, "netem": f"delay {applied}ms {jitter}ms distribution normal",
               "tc_commands": tc_commands(applied, jitter, dev, cloud)},
           "check": "scripts/check_wan_emulation.py: (b) the Pi's connect time to the cloud alias within ±20% of "
                    "target_rtt_ms, and SYN to SYN-ACK at the capture within ±20% of delay_ms; (c) the Mac's own "
                    "address not delayed",
           **_git()}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2))
    print(f"cloud round trip (Mac → {a.endpoint}): median {med:.1f} ms, IQR {q3 - q1:.1f} ms ({len(times)} tries)\n"
          f"base round trip (Pi ↔ Mac): median {bmed:.1f} ms, IQR {b3 - b1:.1f} ms ({len(base)} pings)\n"
          f"dummynet: {med:.1f} − {bmed:.1f} = {total:.1f} ms → {one_way} ms each way ({applied} ms) on the Mac → {a.out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--endpoint", default="https://ec2.us-west-1.amazonaws.com")
    p.add_argument("--tries", type=int, default=30)
    p.add_argument("--gap", type=float, default=0.5, help="seconds between tries")
    p.add_argument("--base-tries", type=int, default=40, dest="base_tries", help="pings to the Pi")
    p.add_argument("--base-gap", type=float, default=0.25, dest="base_gap")
    p.add_argument("--out", default="data/results/c2_wan_emulation.json")
    main(p.parse_args())
