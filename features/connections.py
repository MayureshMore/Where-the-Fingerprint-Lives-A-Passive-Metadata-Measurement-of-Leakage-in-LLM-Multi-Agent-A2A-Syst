"""
Which TCP connections belong to a trace.

A capture starts while the previous trace's connections on the same agent ports are still
closing (keep-alive timeouts, TLS close_notify alerts, FINs). Those packets carry the previous
trace's timing, not this trace's, and when traces run in a fixed order they leak the previous
trace's label (data/results/tls_control_gap.md). So a trace uses only the connections it opens
itself: the client's SYN to an agent port is inside the capture. Every later packet of such a
connection counts; packets of connections opened before the capture are dropped.

`legacy=True` everywhere keeps the earlier behaviour (every connection on the agent ports), which
produced the results committed before the own-connections rule.
"""

from __future__ import annotations

SYN, ACK = 0x02, 0x10


def opened_connections(packets, servers: set[int]) -> set[tuple[int, int]]:
    """(client port, agent port) of every connection whose SYN is in the capture.
    packets: (ts, sport, dport, wire_len, payload_len, tcp_flags), as features.kfp.tcp_packets."""
    return {(sp, dp) for _, sp, dp, _, _, fl in packets
            if dp in servers and fl & SYN and not fl & ACK}


def own_packets(packets, servers: set[int], legacy: bool = False) -> list:
    """The packets of connections the trace opened (both directions)."""
    if legacy:
        return list(packets)
    opened = opened_connections(packets, servers)
    return [p for p in packets if (p[1], p[2]) in opened or (p[2], p[1]) in opened]

