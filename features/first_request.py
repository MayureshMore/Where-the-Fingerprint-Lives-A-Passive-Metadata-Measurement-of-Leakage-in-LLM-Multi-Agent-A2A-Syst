"""
Size of the first request message that reaches an agent, read from packet headers alone.

In C1 this one number explains the whole workflow result (RESULTS.md, P1 workflow), so it is
both an analysis feature and the input-padding check.
"""

from __future__ import annotations

from pathlib import Path

from features.kfp import tcp_packets

REQUEST_GAP_S = 0.05      # one request = request-direction writes on a connection ≤ 50 ms apart
FIRST_REQUEST_DEF = ("TCP payload bytes of the first request message that reaches an agent (the "
                     "caller → orchestrator link is not captured): on the agent link whose first "
                     "post-handshake request starts earliest, the request-direction writes ≤ 50 ms "
                     "apart, TLS ClientHello and client Finished excluded; from headers only.")


def first_request_bytes(pcap: Path, servers: set[int]) -> int:
    """TCP payload bytes of the first request message that reaches an agent: on the agent link
    whose first post-handshake request starts earliest, the request-direction payload written in
    one go (writes ≤ REQUEST_GAP_S apart). On a connection opened in the trace, the TLS ClientHello
    and the client Finished (≤ 100 B) are skipped. Headers only, so it works on stripped pcaps."""
    opened, skipped, first = set(), {}, {}
    for ts, sp, dp, _, pl, flags in tcp_packets(pcap):
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
            first[conn] = [ts, pl, False, ts]
        elif ts - first[conn][3] <= REQUEST_GAP_S:
            first[conn][1] += pl
            first[conn][3] = ts
        else:
            first[conn][2] = True                          # first request on this link complete
    reqs = [(t0, b) for t0, b, _, _ in first.values() if b >= 300]   # not a close_notify
    return min(reqs)[1] if reqs else 0
