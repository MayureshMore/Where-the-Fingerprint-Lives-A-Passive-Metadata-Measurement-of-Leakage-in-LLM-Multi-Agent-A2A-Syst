"""
Agent endpoints keyed by host and port.

A sidecar's agent_endpoints gives each agent's address as "host:port" ("10.0.0.2:8101",
"[::1]:8101"). a2a-leakcheck keys an endpoint by both (before 0.3.1, by its port alone):

  * a packet on an agent port counts only if its server side (the destination of a request, the
    source of a response) is that agent's host: traffic of another host on the same port is dropped
    before feature extraction, into a filtered copy of the capture (as --strip writes header-only
    copies), and the collection summary counts it (other_host_packets);
  * two agents on different hosts may share a port (443 behind two addresses): their role samples
    are kept apart by host and port (role_keys; features/roles.py).

Loopback is one host: 127.0.0.1, any other 127.x address, ::1 and the name "localhost" match each
other, since a local service answers on whichever the client picked (paper 1's off-the-shelf
captures list 127.0.0.1 and run on ::1). Any other host that is not an IP address is matched by its
port alone, since resolving names offline would guess. A sidecar is refused when two agents share
one address, or when a port is listed both with and without a host: either way a packet's agent
would be a guess.

The trace features and the first request (features/) still match connections on (client port, agent
port): where two agents share a port, a client that used one ephemeral port for both at once would
merge them there. Clients pick a fresh port per connection in practice; the role samples, keyed by
host, are unaffected.
"""

from __future__ import annotations

import ipaddress
import struct
from pathlib import Path

from scripts.strip_payload import _MAGICS, _network_offset

LOOPBACK = "loopback"


def _host(text: str) -> str | None:
    """The canonical IP address in text, LOOPBACK for any loopback address or "localhost", or None when
    text is neither (any host on the port)."""
    text = text.strip("[]")
    if text.lower() == "localhost":
        return LOOPBACK
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return None
    return LOOPBACK if ip.is_loopback else str(ip)


def _ip(raw: bytes) -> str:
    ip = ipaddress.ip_address(raw)
    return LOOPBACK if ip.is_loopback else str(ip)


def parse_endpoints(eps: dict) -> tuple[dict[tuple, str], str]:
    """({(host, port): role}, "") from a sidecar's agent_endpoints, or ({}, reason) when an agent's address
    is ambiguous. host is an IP address, LOOPBACK, or None (any host on that port). An address without a
    port is left out."""
    out: dict[tuple, str] = {}
    for role, addr in eps.items():
        host, _, port = str(addr).rpartition(":")
        if not port.isdigit():
            continue
        key = (_host(host) if host else None, int(port))
        if key in out:
            return {}, f"agent_endpoints: {out[key]} and {role} share the address {addr}"
        out[key] = role
    for port in {p for _, p in out}:
        hosts = [h for h, p in out if p == port]
        if None in hosts and len(hosts) > 1:
            return {}, (f"agent_endpoints: port {port} is listed with and without a host; give every agent on "
                        "it an IP address")
    return out, ""


def role_keys(endpoints: dict[tuple, str]) -> dict[str, str]:
    """The keys features/roles.py matches a flow's agent side against: "ip:port" for an agent with an IP
    address, the port alone for loopback or a named host (its flows may show any loopback address)."""
    return {(f"{h}:{p}" if h not in (None, LOOPBACK) else str(p)): r for (h, p), r in endpoints.items()}


def _records(raw: bytes):
    """(offset, length, src, dst, sport, dport) of every TCP packet record in a classic pcap; other records
    as (offset, length, None, None, None, None)."""
    endian = _MAGICS.get(raw[:4])
    if endian is None:
        raise ValueError("not a classic pcap file (pcapng is not supported)")
    linktype = struct.unpack(endian + "I", raw[20:24])[0]
    pos = 24
    while pos + 16 <= len(raw):
        incl = struct.unpack(endian + "I", raw[pos + 8:pos + 12])[0]
        data = raw[pos + 16:pos + 16 + incl]
        start, pos = pos, pos + 16 + incl
        off = _network_offset(linktype, data)
        v = data[off] >> 4 if len(data) > off else 0
        if v == 4 and len(data) >= off + 20:
            proto, l4 = data[off + 9], off + max((data[off] & 0x0F) * 4, 20)
            src, dst = data[off + 12:off + 16], data[off + 16:off + 20]
        elif v == 6 and len(data) >= off + 40:
            proto, l4 = data[off + 6], off + 40
            src, dst = data[off + 8:off + 24], data[off + 24:off + 40]
        else:
            yield start, pos - start, None, None, None, None
            continue
        if proto != 6 or len(data) < l4 + 4:
            yield start, pos - start, None, None, None, None
            continue
        sport, dport = struct.unpack(">HH", data[l4:l4 + 4])
        yield start, pos - start, _ip(src), _ip(dst), sport, dport


def foreign_packets(pcap: Path, endpoints: dict[tuple, str]) -> tuple[list[int], dict[str, int]]:
    """The packets on an agent port whose server host is not an agent's on that port: ([record offset],
    {"host:port": packets}). The server side is the destination when the destination port is an agent
    port (a request), else the source, as features/extractor.py decides direction."""
    hosts: dict[int, set] = {}
    for host, port in endpoints:
        hosts.setdefault(port, set()).add(host)
    drop, seen = [], {}
    for start, _, src, dst, sport, dport in _records(Path(pcap).read_bytes()):
        if sport is None:
            continue
        if dport in hosts:
            server, port = dst, dport
        elif sport in hosts:
            server, port = src, sport
        else:
            continue
        if None in hosts[port] or server in hosts[port]:
            continue
        drop.append(start)
        key = f"{server}:{port}"
        seen[key] = seen.get(key, 0) + 1
    return drop, seen


def write_without(src: Path, dst: Path, drop: list[int]) -> None:
    """A copy of src without the packet records that start at the offsets in drop."""
    raw = Path(src).read_bytes()
    skip = set(drop)
    out = bytearray(raw[:24])
    for start, length, *_ in _records(raw):
        if start not in skip:
            out += raw[start:start + length]
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    Path(dst).write_bytes(bytes(out))
