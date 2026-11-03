"""
Size of the first request message that reaches an agent, read from packet headers alone.

In C1 this one number explains the whole workflow result (RESULTS.md, P1 workflow), so it is
both an analysis feature and the input-padding check.
"""

from __future__ import annotations

from pathlib import Path

from features.connections import own_packets
from features.kfp import tcp_packets

REQUEST_GAP_S = 0.05      # one request = request-direction writes on a connection ≤ 50 ms apart
FIRST_REQUEST_DEF = ("TCP payload bytes of the first request message that reaches an agent (the "
                     "caller → orchestrator link is not captured): on the agent link, opened by the trace, whose first "
                     "post-handshake request starts earliest, the request-direction writes ≤ 50 ms "
                     "apart, TLS ClientHello and client Finished excluded; from headers only.")


def first_request_bytes(pcap: Path, servers: set[int], legacy: bool = False) -> int:
    """TCP payload bytes of the first request message that reaches an agent: on the agent link
    whose first post-handshake request starts earliest, the request-direction payload written in
    one go (writes ≤ REQUEST_GAP_S apart). On a connection opened in the trace, the TLS ClientHello
    and the client Finished (≤ 100 B) are skipped. Headers only, so it works on stripped pcaps.
    Only links the trace opened count (features/connections.py), unless legacy."""
    return first_request(tcp_packets(pcap), servers, legacy)["bytes"]


def first_request(packets, servers: set[int], legacy: bool = False) -> dict:
    """first_request_bytes on (ts, sport, dport, wire_len, payload_len, tcp_flags) packets in
    time order: {"bytes", "packets" (segments it spans), "first_payload" (its first segment),
    "link" ((client port, agent port) it was on)}."""
    packets = own_packets(packets, servers, legacy)
    opened, skipped, first = set(), {}, {}
    for ts, sp, dp, _, pl, flags in packets:
        if dp not in servers:
            continue
        conn = (sp, dp)
        if flags & 0x02:                                   # SYN: the connection opens in this trace
            opened.add(conn)
            continue
        if pl == 0 or conn in first and first[conn][2]:
            continue
        if conn in opened and skipped.get(conn, 0) == 0:   # ClientHello
            skipped[conn] = 1
            continue
        if conn in opened and skipped[conn] == 1 and pl <= 100:   # client Finished
            skipped[conn] = 2
            continue
        if conn not in first:
            first[conn] = [ts, pl, False, ts, 1, pl, conn]
        elif ts - first[conn][3] <= REQUEST_GAP_S:
            first[conn][1] += pl
            first[conn][3] = ts
            first[conn][4] += 1
        else:
            first[conn][2] = True                          # first request on this link complete
    reqs = sorted((v[0], v[1], v[4], v[5], v[6]) for v in first.values() if v[1] >= 300)   # not a close_notify
    if not reqs:
        return {"bytes": 0, "packets": 0, "first_payload": 0, "link": None}
    return {"bytes": reqs[0][1], "packets": reqs[0][2], "first_payload": reqs[0][3], "link": reqs[0][4]}
