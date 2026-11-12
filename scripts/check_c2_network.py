#!/usr/bin/env python3
"""
C2 network check (docs/LAN_SETUP.md), run before each session (scripts/collect_session.py runs it
for --placement edge-cloud) and on its own:

  mac      the Mac's interface C2_IFACE has the address C2_MAC (the ticket service and the Pi's
           route both depend on it; a new DHCP lease or a move to Ethernet changes it)
  alias    the cloud alias C2_CLOUD is on C2_IFACE (it goes away when the Mac rejoins the network)
  route    every edge agent's gateway routes C2_CLOUD via C2_MAC (the host route on the Pi:
           `ip route get C2_CLOUD` → via C2_MAC), read from the edge agent's GET /health

Addresses from configs/c2_network.conf. Exit 1 if any check fails.

Usage (Mac, with scripts/serve_edge.py running on the Pi):
    python scripts/check_c2_network.py
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.edge import TRIGGER_PORT, c2_network, require  # noqa: E402


def interface_addresses(iface: str) -> list[str]:
    out = subprocess.run(["ifconfig", iface], capture_output=True, text=True).stdout
    return re.findall(r"\binet (\d+\.\d+\.\d+\.\d+)", out)


def check_network(net: dict, bases: list[int], edge_host: str | None = None, timeout: float = 10) -> dict:
    iface = require(net["C2_IFACE"], "the Mac's interface (C2_IFACE)")
    mac = require(net["C2_MAC"], "the Mac's address (C2_MAC)")
    cloud = require(net["C2_CLOUD"], "the cloud alias (C2_CLOUD)")
    pi = edge_host or require(net["C2_PI"], "the Pi's address (C2_PI)")
    have = interface_addresses(iface)
    checks = [{"check": "mac", "ok": mac in have, "detail": f"{iface} has {', '.join(have) or 'no IPv4 address'}; "
                                                              f"expected {mac}"},
              {"check": "alias", "ok": cloud in have, "detail": f"cloud alias {cloud} on {iface}"}]
    for b in bases:
        try:
            info = httpx.get(f"http://{pi}:{b + TRIGGER_PORT}/health", timeout=timeout).json()
            route = info.get("route_to_cloud") or {}
            ok = route.get("via") == mac
            detail = f"edge {b}: ip route get {cloud} → {route or 'no route reported'}; expected via {mac}"
        except (httpx.HTTPError, ValueError) as exc:
            ok, detail = False, f"edge {b} at {pi}:{b + TRIGGER_PORT} not answering: {exc}"
        checks.append({"check": "route", "ok": ok, "detail": detail})
    return {"iface": iface, "mac": mac, "cloud": cloud, "pi": pi, "checks": checks,
            "ok": all(c["ok"] for c in checks)}


def main(a: argparse.Namespace) -> int:
    net = c2_network()
    bases = [int(b) for b in (a.bases or net["C2_BASES"] or "8100,8200,8300").split(",")]
    r = check_network(net, bases)
    for c in r["checks"]:
        print(f"{c['check']:6s} {'ok  ' if c['ok'] else 'FAIL'}  {c['detail']}")
    print("PASS" if r["ok"] else "FAIL")
    if a.json:
        Path(a.json).write_text(json.dumps(r, indent=2))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--bases", default=None, help="default: C2_BASES")
    p.add_argument("--json", default=None)
    sys.exit(main(p.parse_args()))
