#!/usr/bin/env python3
"""
Gateway view of a loopback collection: keep only the connections the orchestrator opens.

At a gateway between the orchestrator's host and the specialists' host (docs/LAN_SETUP.md) only
the orchestrator's calls cross the link: star → executor, retriever, validator; chain →
executor; mesh → executor, retriever. Forwarding between specialists stays on their host. On
loopback every call is captured, and the callers share one address, so the orchestrator's
connections are told apart by time: it opens all of them together when the task starts, while a
specialist opens its own calls only after an LLM step (seconds later). A connection is kept if
its SYN comes within --window seconds of the trace's first SYN to an agent port.

A trace whose kept connections do not reach exactly the roles its topology calls from the
orchestrator is left out and listed. The sidecar is copied with a gateway_view field; its
agent_endpoints are unchanged, so agents the gateway does not see stay listed but carry no
traffic. Output captures keep only the kept connections' packets (headers as in the input).

This is a test input for leakcheck (absent agents, unbalanced role classes), not a capture of a
real gateway.

Usage:
    python scripts/make_gateway_view.py data/raw_tlspair_tls /tmp/gateway_tls
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.strip_payload import _MAGICS, _network_offset  # noqa: E402

CALLED = {"star": {"executor", "retriever", "validator"}, "chain": {"executor"},
          "mesh": {"executor", "retriever"}}
WINDOW_S = 1.0


def _records(raw: bytes):
    """(record bytes, ts, sport, dport, tcp flags) per pcap record; ports None if not TCP."""
    endian = _MAGICS[raw[:4]]
    nano = raw[:4] in (b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d")
    linktype = struct.unpack(endian + "I", raw[20:24])[0]
    pos = 24
    while pos + 16 <= len(raw):
        sec, frac, incl, _ = struct.unpack(endian + "IIII", raw[pos:pos + 16])
        rec = raw[pos:pos + 16 + incl]
        data = rec[16:]
        pos += 16 + incl
        off = _network_offset(linktype, data)
        sp = dp = flags = None
        if len(data) > off:
            v = data[off] >> 4
            if v == 4 and len(data) > off + 9 and data[off + 9] == 6:
                l4 = off + max((data[off] & 0x0F) * 4, 20)
            elif v == 6 and len(data) > off + 6 and data[off + 6] == 6:
                l4 = off + 40
            else:
                l4 = None
            if l4 is not None and len(data) >= l4 + 14:
                sp, dp = struct.unpack(">HH", data[l4:l4 + 4])
                flags = data[l4 + 13]
        yield rec, sec + frac * (1e-9 if nano else 1e-6), sp, dp, flags


def gateway_trace(pcap: Path, sidecar: dict, window: float) -> tuple[bytes, dict]:
    eps = sidecar["agent_endpoints"]
    role = {int(str(a).rsplit(":", 1)[1]): r for r, a in eps.items()}
    raw = pcap.read_bytes()
    syns = [(ts, sp, dp) for _, ts, sp, dp, fl in _records(raw)
            if dp in role and fl is not None and fl & 0x02 and not fl & 0x10]
    if not syns:
        return b"", {"kept": [], "ok": False, "reason": "no SYN to an agent port"}
    t0 = min(ts for ts, _, _ in syns)
    keep = {(sp, dp) for ts, sp, dp in syns if ts - t0 <= window}
    roles = sorted(role[dp] for _, dp in keep)
    expected = CALLED.get(sidecar.get("topology"), set())
    out = bytearray(raw[:24])
    kept_packets = 0
    for rec, _, sp, dp, _ in _records(raw):
        if (sp, dp) in keep or (dp, sp) in keep:
            out += rec
            kept_packets += 1
    info = {"kept": roles, "dropped_connections": len(syns) - len(keep), "kept_packets": kept_packets,
            "window_s": window, "ok": sorted(set(roles)) == sorted(expected) and len(roles) == len(expected)}
    if not info["ok"]:
        info["reason"] = f"kept {roles}, the {sidecar.get('topology')} gateway sees {sorted(expected)}"
    return bytes(out), info


def main(a: argparse.Namespace) -> None:
    src, dst = Path(a.raw), Path(a.out)
    dst.mkdir(parents=True, exist_ok=True)
    seen, kept, left_out = Counter(), Counter(), []
    for side in sorted(src.glob("*.json")):
        sc = json.loads(side.read_text())
        pcap = side.with_suffix(".pcap")
        if "agent_endpoints" not in sc or not pcap.exists() or sc.get("success") is False:
            continue
        seen[sc.get("topology")] += 1
        data, info = gateway_trace(pcap, sc, a.window)
        if not info["ok"]:
            left_out.append({"run_id": sc.get("run_id", side.stem), **info})
            continue
        (dst / pcap.name).write_bytes(data)
        (dst / side.name).write_text(json.dumps({**sc, "gateway_view": info}, indent=2))
        kept[sc.get("topology")] += 1
    summary = {"source": str(src), "window_s": a.window, "called_from_orchestrator": {k: sorted(v) for k, v in CALLED.items()},
               "traces": dict(seen), "kept": dict(kept), "left_out": left_out}
    (dst / "gateway_view.json").write_text(json.dumps(summary, indent=2))
    print(f"kept {sum(kept.values())} of {sum(seen.values())} traces ({dict(kept)}); "
          f"left out {len(left_out)} → {dst}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("raw", help="collection folder: *.pcap with *.json sidecars")
    p.add_argument("out", help="output folder for the gateway-view captures")
    p.add_argument("--window", type=float, default=WINDOW_S,
                   help="seconds after the first SYN within which a connection counts as the orchestrator's")
    main(p.parse_args())
