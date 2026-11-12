#!/usr/bin/env python3
"""
Pilot check for C2's emulated WAN (docs/LAN_SETUP.md, section 7), on the home Wi-Fi. Each edge
agent on the Pi measures TCP connect times (POST /probe on its trigger port, outside any trace
capture) to the internet, to the Mac's own address (the ticket service, which the emulation never
delays) and to the cloud alias:

  a. internet   the Pi still reaches 1.1.1.1:443 (the WAN rules must not disturb the network;
                wan_emulation.sh on also checks that the main ruleset and NAT rules are unchanged)
  b. cloud      the delay added to the cloud alias, its connect time minus the base Wi-Fi round
                trip, is within ±--tolerance of the round trip in data/results/c2_wan_emulation.json
                (delay_ms)
  c. ticket     the Mac's own address is not delayed: its connect time, the base Wi-Fi round trip
                Pi <-> Mac, is under --base-limit × delay_ms (if that path were delayed it would be
                the base plus delay_ms; a base above delay_ms usually means Wi-Fi power saving is
                still on, on the Pi). The precise test is at the capture (below).

The probes are also captured on the Mac's Wi-Fi interface (C2_IFACE; tcpdump -p, filtered on the
Pi's address), and the SYN → SYN-ACK time seen there must match: about the round trip to the cloud
alias (the Pi's SYN is captured before the delay, the SYN-ACK after it: the capture sits where a
building router would) and close to zero to the ticket service (no Wi-Fi between). With the netem
fallback on the Pi the capture sees the SYN after the delay, so the cloud handshake looks undelayed
there: pass --fallback-pi to expect that. --record writes the base Wi-Fi round trip (pooled over
the three edge agents) into data/results/c2_wan_emulation.json as base_wifi_rtt. Exit 1 if any
check fails. Addresses and the interface come from configs/c2_network.conf unless given.

Usage (Mac, with scripts/serve_edge.py and scripts/serve_cloud.py running):
    python scripts/check_wan_emulation.py --record --json data/raw_c2_pilot/wan_check.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.edge import CLOUD_PORTS, TICKET_PORT, TRIGGER_PORT, c2_network, require  # noqa: E402
from features.kfp import tcp_packets  # noqa: E402


def handshakes(pcap: Path, ports: dict[int, str]) -> dict[str, list[float]]:
    """SYN → SYN-ACK times (ms) at the capture, per server port's name."""
    syn, out = {}, {name: [] for name in ports.values()}
    for ts, sp, dp, _, _, flags in tcp_packets(pcap):
        if flags & 0x12 == 0x02 and dp in ports:                  # SYN from the Pi
            syn[(sp, dp)] = ts
        elif flags & 0x12 == 0x12 and sp in ports and (dp, sp) in syn:
            out[ports[sp]].append((ts - syn.pop((dp, sp))) * 1000)
    return out


def probe(c: httpx.Client, url: str, target: str, n: int) -> dict:
    r = c.post(url, json={"n": n, "target": target})
    return r.json() if r.status_code == 200 else {"target": target, "error": r.json().get("error", r.text)}


def _quartiles(ms: list[float]) -> dict:
    q1, med, q3 = statistics.quantiles(ms, n=4) if len(ms) > 1 else (ms[0],) * 3
    return {"n": len(ms), "median_ms": med, "q1_ms": q1, "q3_ms": q3, "iqr_ms": q3 - q1,
            "min_ms": min(ms), "max_ms": max(ms)}


def _git() -> dict:
    def run(*args):
        return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()
    return {"git_commit": run("rev-parse", "HEAD") or None,
            "git_dirty": bool(run("status", "--porcelain", "--", ".", ":(exclude)data"))}


def main(a: argparse.Namespace) -> int:
    net = c2_network()
    a.edge_host = require(a.edge_host or net["C2_PI"], "the Pi's address (C2_PI)")
    iface = None if a.no_capture else (a.interface or require(net["C2_IFACE"], "the capture interface (C2_IFACE)"))
    target = json.loads(Path(a.target).read_text())
    rtt = float(target["fallback_pi_netem"]["delay_ms"] if a.fallback_pi else target["delay_ms"])
    bases = [int(b) for b in a.bases.split(",")]
    ports = {b + CLOUD_PORTS["diagnostics"]: "cloud" for b in bases} | {b + TICKET_PORT: "ticket" for b in bases}
    cap, pcap = None, None
    if iface:
        pcap = Path(tempfile.mkdtemp(prefix="wancheck_")) / "probe.pcap"
        flt = f"tcp and host {a.edge_host} and (" + " or ".join(f"port {p}" for p in ports) + ")"
        cap = subprocess.Popen(["tcpdump", "-i", iface, "-p", "-n", "-s", "96", "-w", str(pcap), flt],
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        time.sleep(1.5)
        if cap.poll() is not None:
            raise SystemExit(f"tcpdump on {iface}: {cap.stderr.read().decode().strip()}")
    rows = []
    with httpx.Client(timeout=300) as c:
        for base in bases:
            url = f"http://{a.edge_host}:{base + TRIGGER_PORT}/probe"
            rows.append({"base": base, **{t: probe(c, url, t, a.n if t != "internet" else 3)
                                          for t in ("internet", "ticket", "cloud")}})
    if cap:
        time.sleep(1.0)
        cap.terminate()
        cap.wait(timeout=10)
    lo, hi = rtt * (1 - a.tolerance), rtt * (1 + a.tolerance)
    checks = []
    for r in rows:
        b, inet, cloud, ticket = r["base"], r["internet"], r["cloud"], r["ticket"]
        ok_c, ok_t = "median_ms" in cloud, "median_ms" in ticket
        added = cloud["median_ms"] - ticket["median_ms"] if ok_c and ok_t else None
        r["added_ms"] = added
        checks.append({"check": "a. internet", "edge": b, "ok": "median_ms" in inet,
                       "value": inet.get("median_ms"), "detail": inet.get("error", "1.1.1.1:443 reachable")})
        checks.append({"check": "b. cloud − base", "edge": b, "ok": added is not None and lo <= added <= hi,
                       "value": added, "detail": f"added delay, target {rtt:g} ms ±{a.tolerance:.0%}"})
        checks.append({"check": "c. ticket (base Wi-Fi)", "edge": b,
                       "ok": ok_t and ticket["median_ms"] < rtt * a.base_limit, "value": ticket.get("median_ms"),
                       "detail": f"the Mac's own address, never delayed: under {rtt * a.base_limit:.1f} ms"})
    capture = None
    if pcap:
        hs = handshakes(pcap, ports)
        capture = {k: {"n": len(v), "median_ms": statistics.median(v) if v else None} for k, v in hs.items()}
        cm, tm = capture["cloud"]["median_ms"], capture["ticket"]["median_ms"]
        undelayed = rtt * a.undelayed
        expect_cloud = (cm is not None and cm < undelayed) if a.fallback_pi else (cm is not None and lo <= cm <= hi)
        checks.append({"check": "b. cloud at the capture", "edge": "all", "ok": expect_cloud, "value": cm,
                       "detail": "SYN → SYN-ACK; " + ("fallback on the Pi: undelayed here" if a.fallback_pi
                                                      else f"target {rtt:g} ms ±{a.tolerance:.0%}")})
        checks.append({"check": "c. ticket at the capture", "edge": "all", "ok": tm is not None and tm < undelayed,
                       "value": tm, "detail": f"SYN → SYN-ACK under {undelayed:.1f} ms"})
    base_ms = [x for r in rows for x in (r["ticket"].get("connect_ms") or [])]
    base_rtt = {**_quartiles(base_ms), "per_edge_median_ms": {str(r["base"]): r["ticket"].get("median_ms") for r in rows},
                "method": "the edge agent's TCP connect time from the Pi to the Mac's own address (the ticket "
                          "service), which the WAN emulation never delays: the base Wi-Fi round trip Pi <-> Mac",
                "pi": a.edge_host, "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **_git()} if base_ms else None
    for x in checks:
        v = "—" if x["value"] is None else f"{x['value']:.1f} ms"
        print(f"{x['check']:26s} edge {x['edge']!s:5s} {v:>9s}  {x['detail']}  {'ok' if x['ok'] else 'FAIL'}")
    if base_rtt:
        print(f"base Wi-Fi round trip Pi <-> Mac: median {base_rtt['median_ms']:.1f} ms, IQR {base_rtt['iqr_ms']:.1f} ms "
              f"({base_rtt['n']} connects)")
    out = {"target": {k: target.get(k) for k in ("endpoint", "median_ms", "delay_ms", "jitter_ms")},
           "emulation": "fallback netem on the Pi" if a.fallback_pi else "dummynet on the Mac",
           "tolerance": a.tolerance, "base_wifi_rtt": base_rtt, "probes": rows, "capture": capture, "checks": checks,
           "pass": all(x["ok"] for x in checks)}
    print("PASS" if out["pass"] else "FAIL")
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=2))
    if a.record and base_rtt:
        target["base_wifi_rtt"] = base_rtt
        Path(a.target).write_text(json.dumps(target, indent=2))
        print(f"base Wi-Fi round trip recorded in {a.target}")
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--target", default="data/results/c2_wan_emulation.json")
    p.add_argument("--edge-host", default=None, dest="edge_host", help="the Pi (default C2_PI)")
    p.add_argument("--bases", default="8100,8200,8300")
    p.add_argument("--interface", default=None, help="capture the probes here (default C2_IFACE)")
    p.add_argument("--no-capture", action="store_true", dest="no_capture", help="probes only")
    p.add_argument("--base-limit", type=float, default=1.0, dest="base_limit",
                   help="the base Wi-Fi round trip must be under this × the target (not delayed, power saving off)")
    p.add_argument("--record", action="store_true",
                   help="write the base Wi-Fi round trip into --target (base_wifi_rtt)")
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--tolerance", type=float, default=0.20)
    p.add_argument("--undelayed", type=float, default=0.20, help="ticket service: median under this × delay_ms")
    p.add_argument("--fallback-pi", action="store_true", dest="fallback_pi",
                   help="the WAN delay is netem on the Pi (the capture is on the cloud side of it)")
    p.add_argument("--json", default=None)
    sys.exit(main(p.parse_args()))
