#!/usr/bin/env python3
"""
Pilot check for C2's emulated WAN (docs/LAN_SETUP.md, section 7). Each edge agent on the Pi
measures TCP connect times (POST /probe on its trigger port, outside any trace capture):

  a. internet   the Pi still reaches 1.1.1.1:443 through the Mac's NAT (the WAN rules must not
                break Internet Sharing; wan_emulation.sh on also checks that the main ruleset and
                NAT rules are unchanged)
  b. cloud      the Pi's connect time to the cloud alias is within ±--tolerance of the round trip
                in data/results/c2_wan_emulation.json (delay_ms)
  c. ticket     the ticket service on the building server is not delayed (median under
                --undelayed × delay_ms)

With --interface (bridge100) the probes are also captured, and the SYN → SYN-ACK time seen at the
capture must match: about the round trip to the cloud alias (the Pi's SYN is captured before the
delay, the SYN-ACK after it: the capture sits where a building router would) and close to zero to
the ticket service. With the netem fallback on the Pi the capture sees the SYN after the delay,
so the cloud handshake looks undelayed there: pass --fallback-pi to expect that.
Exit 1 if any check fails.

Usage (Mac, with scripts/serve_edge.py and scripts/serve_cloud.py running):
    python scripts/check_wan_emulation.py --interface bridge100 --json data/raw_c2_pilot/wan_check.json
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

from agents.edge import CLOUD_PORTS, TICKET_PORT, TRIGGER_PORT  # noqa: E402
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


def main(a: argparse.Namespace) -> int:
    target = json.loads(Path(a.target).read_text())
    rtt = float(target["delay_ms"])
    bases = [int(b) for b in a.bases.split(",")]
    ports = {b + CLOUD_PORTS["diagnostics"]: "cloud" for b in bases} | {b + TICKET_PORT: "ticket" for b in bases}
    cap, pcap = None, None
    if a.interface:
        pcap = Path(tempfile.mkdtemp(prefix="wancheck_")) / "probe.pcap"
        flt = f"tcp and host {a.edge_host} and (" + " or ".join(f"port {p}" for p in ports) + ")"
        cap = subprocess.Popen(["tcpdump", "-i", a.interface, "-n", "-s", "96", "-w", str(pcap), flt],
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        time.sleep(1.5)
        if cap.poll() is not None:
            raise SystemExit(f"tcpdump on {a.interface}: {cap.stderr.read().decode().strip()}")
    rows = []
    with httpx.Client(timeout=300) as c:
        for base in bases:
            url = f"http://{a.edge_host}:{base + TRIGGER_PORT}/probe"
            rows.append({"base": base, **{t: probe(c, url, t, a.n if t != "internet" else 3)
                                          for t in ("internet", "cloud", "ticket")}})
    if cap:
        time.sleep(1.0)
        cap.terminate()
        cap.wait(timeout=10)
    lo, hi, undelayed = rtt * (1 - a.tolerance), rtt * (1 + a.tolerance), rtt * a.undelayed
    checks = []
    for r in rows:
        b, inet, cloud, ticket = r["base"], r["internet"], r["cloud"], r["ticket"]
        checks.append({"check": "a. internet", "edge": b, "ok": "median_ms" in inet,
                       "value": inet.get("median_ms"), "detail": inet.get("error", "1.1.1.1:443 reachable")})
        checks.append({"check": "b. cloud", "edge": b, "ok": "median_ms" in cloud and lo <= cloud["median_ms"] <= hi,
                       "value": cloud.get("median_ms"), "detail": f"target {rtt:g} ms ±{a.tolerance:.0%}"})
        checks.append({"check": "c. ticket", "edge": b, "ok": "median_ms" in ticket and ticket["median_ms"] < undelayed,
                       "value": ticket.get("median_ms"), "detail": f"under {undelayed:.1f} ms"})
    capture = None
    if pcap:
        hs = handshakes(pcap, ports)
        capture = {k: {"n": len(v), "median_ms": statistics.median(v) if v else None} for k, v in hs.items()}
        cm, tm = capture["cloud"]["median_ms"], capture["ticket"]["median_ms"]
        expect_cloud = (cm is not None and cm < undelayed) if a.fallback_pi else (cm is not None and lo <= cm <= hi)
        checks.append({"check": "b. cloud at the capture", "edge": "all", "ok": expect_cloud, "value": cm,
                       "detail": "SYN → SYN-ACK; " + ("fallback on the Pi: undelayed here" if a.fallback_pi
                                                      else f"target {rtt:g} ms ±{a.tolerance:.0%}")})
        checks.append({"check": "c. ticket at the capture", "edge": "all", "ok": tm is not None and tm < undelayed,
                       "value": tm, "detail": f"SYN → SYN-ACK under {undelayed:.1f} ms"})
    for x in checks:
        v = "—" if x["value"] is None else f"{x['value']:.1f} ms"
        print(f"{x['check']:26s} edge {x['edge']!s:5s} {v:>9s}  {x['detail']}  {'ok' if x['ok'] else 'FAIL'}")
    out = {"target": {k: target.get(k) for k in ("endpoint", "median_ms", "delay_ms", "jitter_ms")},
           "emulation": "fallback netem on the Pi" if a.fallback_pi else "dummynet on the Mac",
           "tolerance": a.tolerance, "probes": rows, "capture": capture, "checks": checks,
           "pass": all(x["ok"] for x in checks)}
    print("PASS" if out["pass"] else "FAIL")
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=2))
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--target", default="data/results/c2_wan_emulation.json")
    p.add_argument("--edge-host", default="192.168.2.2", dest="edge_host")
    p.add_argument("--bases", default="8100,8200,8300")
    p.add_argument("--interface", default=None, help="also capture the probes here (bridge100)")
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--tolerance", type=float, default=0.20)
    p.add_argument("--undelayed", type=float, default=0.20, help="ticket service: median under this × delay_ms")
    p.add_argument("--fallback-pi", action="store_true", dest="fallback_pi",
                   help="the WAN delay is netem on the Pi (the capture is on the cloud side of it)")
    p.add_argument("--json", default=None)
    sys.exit(main(p.parse_args()))
