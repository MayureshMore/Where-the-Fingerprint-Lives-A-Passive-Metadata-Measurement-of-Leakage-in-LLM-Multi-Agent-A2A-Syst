#!/usr/bin/env python3
"""
Check what is on the wire in a capture directory, BEFORE payload stripping.

For every pcap it counts TCP connections (client SYNs), TLS records at the
start of a segment — handshake (0x16 0x03 ..; ClientHello when the handshake
type is 0x01) and application data (0x17 0x03 0x03) — and cleartext HTTP
request/response lines. The 96-byte snaplen keeps the first 20-40 payload
bytes of each packet, enough to see a record header.

  --expect tls    every trace must carry ClientHellos and application-data
                  records and no cleartext HTTP
  --expect clear  every trace must carry cleartext HTTP and no TLS records

The summary also gives connection reuse: TLS handshakes per connection and per
trace, connections per agent port, and (from cleartext traces) HTTP requests
per connection. Stripped captures carry no payload and are rejected.

Usage:
    python scripts/check_tls_capture.py data/tls_pilot/tls --expect tls
    python scripts/check_tls_capture.py data/raw_tlspair_tls --expect tls --json data/raw_tlspair_tls/tls_check.json
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.strip_payload import _LINK_HDR, _MAGICS, _network_offset  # noqa: E402

_HTTP = (b"GET ", b"POST ", b"PUT ", b"HTTP/1.")


def _parse(linktype: int, data: bytes):
    """(dst_port, tcp_flags, payload) of a TCP packet, or None."""
    off = _network_offset(linktype, data)
    if len(data) <= off:
        return None
    version = data[off] >> 4
    if version == 4 and len(data) > off + 9:
        proto, l4 = data[off + 9], off + max((data[off] & 0x0F) * 4, 20)
    elif version == 6 and len(data) > off + 6:
        proto, l4 = data[off + 6], off + 40
    else:
        return None
    if proto != 6 or len(data) < l4 + 14:
        return None
    dport = struct.unpack(">H", data[l4 + 2:l4 + 4])[0]
    hdr = max((data[l4 + 12] >> 4) * 4, 20)
    return dport, data[l4 + 13], data[l4 + hdr:]


def scan(path: Path) -> dict:
    raw = path.read_bytes()
    endian = _MAGICS.get(raw[:4])
    if endian is None:
        raise ValueError(f"{path}: not a classic pcap")
    linktype = struct.unpack(endian + "I", raw[20:24])[0]
    if linktype not in _LINK_HDR:
        raise ValueError(f"{path}: unsupported link type {linktype}")
    c = Counter()
    conns_by_port = Counter()
    pos = 24
    while pos + 16 <= len(raw):
        incl_len = struct.unpack(endian + "I", raw[pos + 8:pos + 12])[0]
        p = _parse(linktype, raw[pos + 16:pos + 16 + incl_len])
        pos += 16 + incl_len
        c["packets"] += 1
        if p is None:
            continue
        dport, flags, pay = p
        if flags & 0x02 and not flags & 0x10:          # client SYN
            c["connections"] += 1
            conns_by_port[dport] += 1
        if pay:
            c["payload_packets"] += 1
        if len(pay) >= 3 and pay[0] == 0x16 and pay[1] == 0x03:
            c["tls_handshake_records"] += 1
            if len(pay) >= 6 and pay[5] == 0x01:
                c["client_hellos"] += 1
        elif len(pay) >= 3 and pay[:3] == b"\x17\x03\x03":
            c["tls_appdata_records"] += 1
        if pay.startswith(_HTTP[:3]):
            c["http_requests"] += 1
        elif pay.startswith(_HTTP[3]):
            c["http_responses"] += 1
    return {**c, "connections_by_port": dict(conns_by_port)}


def _failed(pcap: Path) -> bool:
    """True when the trace's label sidecar marks the run as failed (excluded from analysis)."""
    sc = pcap.with_suffix(".json")
    try:
        return json.loads(sc.read_text()).get("success") is False
    except (OSError, ValueError):
        return False


def check(stats: dict[str, dict], expect: str) -> list[str]:
    problems = []
    for name, s in stats.items():
        if not s.get("payload_packets"):
            problems.append(f"{name}: no payload bytes (stripped capture? check before stripping)")
        elif expect == "tls":
            if not s.get("client_hellos") or not s.get("tls_appdata_records"):
                problems.append(f"{name}: no TLS handshake/application-data records")
            if s.get("http_requests") or s.get("http_responses"):
                problems.append(f"{name}: cleartext HTTP seen on a TLS trace")
        elif expect == "clear":
            if not s.get("http_requests"):
                problems.append(f"{name}: no cleartext HTTP requests")
            if s.get("tls_handshake_records") or s.get("tls_appdata_records"):
                problems.append(f"{name}: TLS records seen on a cleartext trace")
    return problems


def summarize(stats: dict[str, dict]) -> dict:
    def mean(key):
        return float(np.mean([s.get(key, 0) for s in stats.values()])) if stats else 0.0
    conns = sum(s.get("connections", 0) for s in stats.values())
    hellos = sum(s.get("client_hellos", 0) for s in stats.values())
    reqs = sum(s.get("http_requests", 0) for s in stats.values())
    per_port = Counter()
    for s in stats.values():
        per_port.update(s.get("connections_by_port", {}))
    out = {
        "n_traces": len(stats),
        "connections_per_trace": mean("connections"),
        "client_hellos_per_trace": mean("client_hellos"),
        "tls_handshakes_per_connection": hellos / conns if conns else None,
        "connections_per_trace_by_port": {str(k): v / len(stats) for k, v in sorted(per_port.items())},
    }
    if reqs:
        out["http_requests_per_connection"] = reqs / conns if conns else None
    return out


def main(a: argparse.Namespace) -> None:
    stats, skipped = {}, 0
    for d in a.dirs:
        for f in sorted(Path(d).glob("*.pcap")):
            if _failed(f):
                skipped += 1
                continue
            stats[f.name] = scan(f)
    if not stats:
        sys.exit(f"no pcaps under {a.dirs}")
    summary = summarize(stats)
    problems = check(stats, a.expect) if a.expect else []
    summary.update({"expect": a.expect, "ok": not problems, "problems": problems[:50],
                    "skipped_failed_runs": skipped})
    print(json.dumps(summary, indent=2))
    if a.json:
        Path(a.json).write_text(json.dumps(summary, indent=2))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Check TLS vs cleartext records in raw captures")
    p.add_argument("dirs", nargs="+")
    p.add_argument("--expect", choices=["tls", "clear"], default=None)
    p.add_argument("--json", default=None, help="also write the summary here")
    main(p.parse_args())
