"""
Which TCP connections belong to a trace, and where each one ends.

A capture starts while the previous trace's connections on the same agent ports are still
closing (keep-alive timeouts, TLS close_notify alerts, FINs). Those packets carry the previous
trace's timing, not this trace's, and when traces run in a fixed order they leak the previous
trace's label (data/results/tls_control_gap.md). So a trace uses only the connections it opens
itself: the client's SYN to an agent port is inside the capture. Every later packet of such a
connection counts; packets of connections opened before the capture are dropped.

`legacy=True` everywhere keeps the earlier behaviour (every connection on the agent ports), which
produced the results committed before the own-connections rule.

`end_at_data=True` also ends every connection at its last packet that carries data (TCP payload
> 0, a TLS close_notify alert not counted): the closing packets after it (the alert, ACKs, FINs,
RSTs) are dropped. Until commit f38a2828 the recorder lost the last packets before each stop, and
those were connection closes (DATA.md, "Known limitation"), so with this option no feature depends
on whether a close was written (scripts/evaluate_c1_tail_robustness.py).
"""

from __future__ import annotations

from collections import Counter

FIN, SYN, RST, ACK = 0x01, 0x02, 0x04, 0x10
# A TLS 1.3 close_notify alert on the wire: 5-byte record header, then the 2-byte alert, the 1-byte
# inner content type and the 16-byte AEAD tag. In C1 every 24-byte record is the last data its
# connection carries (the agent's alert before the close), so it never ends a connection's data.
CLOSE_ALERT_LEN = 24


def opened_connections(packets, servers: set[int]) -> set[tuple[int, int]]:
    """(client port, agent port) of every connection whose SYN is in the capture.
    packets: (ts, sport, dport, wire_len, payload_len, tcp_flags), as features.kfp.tcp_packets."""
    return {(sp, dp) for _, sp, dp, _, _, fl in packets
            if dp in servers and fl & SYN and not fl & ACK}


def connection_of(sport: int, dport: int, servers: set[int]) -> tuple[int, int] | None:
    """(client port, agent port) of a packet on an agent port, either direction."""
    if dport in servers:
        return sport, dport
    if sport in servers:
        return dport, sport
    return None


def data_ends(packets, servers: set[int]) -> dict[tuple[int, int], int]:
    """(client port, agent port) → how many of the connection's packets, in capture order, come up
    to and including its last data packet (TCP payload > 0 and not a close_notify alert). A
    connection without data keeps its packets before its first FIN or RST."""
    seen: Counter = Counter()
    last_data: dict[tuple[int, int], int] = {}
    first_close: dict[tuple[int, int], int] = {}
    for _, sp, dp, _, pl, fl in packets:
        conn = connection_of(sp, dp, servers)
        if conn is None:
            continue
        seen[conn] += 1
        if pl > 0 and pl != CLOSE_ALERT_LEN:
            last_data[conn] = seen[conn]
        if fl & (FIN | RST) and conn not in first_close:
            first_close[conn] = seen[conn] - 1
    return {c: last_data.get(c, first_close.get(c, n)) for c, n in seen.items()}


def cut_at_data(packets, servers: set[int]) -> list:
    """The packets with every agent connection cut after its last data packet (data_ends)."""
    keep = data_ends(packets, servers)
    seen: Counter = Counter()
    out = []
    for p in packets:
        conn = connection_of(p[1], p[2], servers)
        if conn is not None:
            seen[conn] += 1
            if seen[conn] > keep[conn]:
                continue
        out.append(p)
    return out


def own_packets(packets, servers: set[int], legacy: bool = False, end_at_data: bool = False) -> list:
    """The packets of connections the trace opened (both directions); with end_at_data, each one
    cut after its last data packet."""
    if legacy:
        packets = list(packets)
    else:
        opened = opened_connections(packets, servers)
        packets = [p for p in packets if (p[1], p[2]) in opened or (p[2], p[1]) in opened]
    return cut_at_data(packets, servers) if end_at_data else packets
