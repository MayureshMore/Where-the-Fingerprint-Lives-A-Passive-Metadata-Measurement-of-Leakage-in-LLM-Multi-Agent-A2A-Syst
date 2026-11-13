"""
Size of the first request message that reaches an agent, read from packet headers alone.

In C1 this one number explains the whole workflow result (RESULTS.md, P1 workflow), so it is
both an analysis feature and the input-padding check.

    first_request        paper 1's measure (C1): request writes ≤ 50 ms apart. Kept unchanged so
                         that paper 1's numbers reproduce.
    first_request_seq    the request in TCP sequence space (a2a-leakcheck, the padding check in
                         scripts/check_session_design.py, scripts/evaluate_leakcheck.py): each byte
                         once, ended by the server's acknowledgment rather than by a pause or by the
                         first server data. In C2 a Wi-Fi loss held part of a request back by 50.6 ms
                         and a TLS session ticket arrived mid-request
                         (fault_diagnosis_edge_cloud_ed7928): the ≤ 50 ms measure ended that 8,488 B
                         request after 1,802 B, and one ended at the first server data would have
                         ended it at the ticket (tests/test_first_request_seq.py). The Pi's ClientHello
                         spans two segments (1,448 + 100 B); first_request takes the second for the
                         Finished and counts the real one (80 B) in the request, first_request_seq
                         skips both.
"""

from __future__ import annotations

from pathlib import Path

from features.connections import own_packets
from features.kfp import tcp_packets, tcp_records

REQUEST_GAP_S = 0.05      # one request = request-direction writes on a connection ≤ 50 ms apart
MIN_REQUEST = 300         # bytes: a close_notify or an agent-card GET is under it, an A2A message over
FINISHED_MAX = 100        # bytes: the client's Finished (with its ChangeCipherSpec) in TLS 1.3
_SYN, _ACK = 0x02, 0x10
FIRST_REQUEST_DEF = ("TCP payload bytes of the first request message that reaches an agent (the "
                     "caller → orchestrator link is not captured): on the agent link, opened by the trace, whose first "
                     "post-handshake request starts earliest, the request-direction writes ≤ 50 ms "
                     "apart, TLS ClientHello and client Finished excluded; from headers only.")
FIRST_REQUEST_SEQ_DEF = ("Bytes of the first request message that reaches an agent, in TCP sequence space "
                         "(each byte once; IP and TCP headers only): on each agent link the trace opened, "
                         "after the TLS handshake (the client's bytes before the server's first data are "
                         "the ClientHello, its next segment of at most 100 B the Finished), a request runs "
                         "from the end of the previous one to the acknowledgment number of the first "
                         "server data segment that acknowledges every client byte seen so far and that "
                         "the client has received before it sends its next byte (its next data segment "
                         "acknowledges it). A server answers only once it holds the whole request, and "
                         "the client sends nothing more until it has the answer; a record the server "
                         "sends mid-request (a TLS session ticket) acknowledges less than the client has "
                         "sent, or the client goes on with the request without having received it. Per "
                         "link the first request of at least 300 B; of those, the one that starts "
                         "earliest.")


def first_request_bytes(pcap: Path, servers: set[int], legacy: bool = False, dedup: bool = False) -> int:
    """TCP payload bytes of the first request message that reaches an agent: on the agent link
    whose first post-handshake request starts earliest, the request-direction payload written in
    one go (writes ≤ REQUEST_GAP_S apart). On a connection opened in the trace, the TLS ClientHello
    and the client Finished (≤ 100 B) are skipped. Headers only, so it works on stripped pcaps.
    Only links the trace opened count (features/connections.py), unless legacy. dedup: each payload
    byte counted once (a TCP retransmission is not counted again; features/kfp.py)."""
    return first_request(tcp_packets(pcap, dedup=dedup), servers, legacy)["bytes"]


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


def first_request_seq_bytes(pcap: Path, servers: set[int], legacy: bool = False, tls: bool = True) -> int:
    """first_request_seq on a pcap: the bytes of its first request message, in TCP sequence space."""
    return first_request_seq(tcp_records(pcap, ack=True), servers, legacy, tls)["bytes"]


def _rel(x: int, base: int) -> int:
    return ((x - base + 2 ** 31) % 2 ** 32) - 2 ** 31


class _Link:
    """One agent link (client port, agent port), scanned in capture order."""

    def __init__(self, handshake: bool):
        self.handshake = handshake       # skip the TLS ClientHello and Finished
        self.base = None                 # client sequence number of its first byte (ISN + 1)
        self.phase = "hello" if handshake else "request"
        self.top = 0                     # highest client byte seen + 1, relative to base
        self.start = 0                   # where the current request starts
        self.start_ts = None             # capture time of its first byte, once seen
        self.skipped: list[int] = []     # requests under MIN_REQUEST before the first one counted
        self.pending = None              # (end, server's next byte): a server segment that may answer it
        self.found = None

    def client(self, ts: float, pl: int, fl: int, seq: int, ack: int) -> None:
        if fl & _SYN:
            self.__init__(self.handshake)
            self.base = (seq + 1) % 2 ** 32
            return
        if pl == 0 or self.found:
            return
        if self.base is None:            # opened before the capture (legacy): no handshake in it
            self.base, self.phase = seq, "request"
        lo = _rel(seq, self.base)
        hi = lo + pl
        if self.phase == "finished" and hi > self.top:
            self.phase = "request"
            if lo == self.top and pl <= FINISHED_MAX:
                self.start = hi          # the client Finished
                self.top = hi
                return
            self.start = self.top        # Finished sent with the request: counted in it
        if self.phase == "request" and hi > self.top and self.pending:
            end, server_next = self.pending
            self.pending = None
            if (ack - server_next) % 2 ** 32 < 2 ** 31:    # sent after the client received it: an answer
                self.finish(end, True)
                if self.found:
                    return
            # otherwise the client went on with the request without it (a session ticket)
        if self.phase == "request" and hi > self.start and self.start_ts is None:
            self.start_ts = ts
        self.top = max(self.top, hi)

    def server(self, pl: int, seq: int, ack: int) -> None:
        if pl == 0 or self.found or self.base is None:
            return
        if self.phase == "hello":        # the ServerHello: the client's bytes so far were its ClientHello
            self.phase = "finished"
            return
        if self.phase != "request" or self.start_ts is None or self.pending:
            return
        end = _rel(ack, self.base)
        if end > self.start and end >= self.top:     # it holds every byte the client has sent
            self.pending = (end, (seq + pl) % 2 ** 32)

    def finish(self, end: int, acked: bool) -> None:
        if end - self.start >= MIN_REQUEST:
            self.found = {"start_ts": self.start_ts, "bytes": end - self.start, "start": self.start,
                          "end": end, "acked": acked, "skipped": list(self.skipped)}
        else:                            # an agent-card GET, or a close_notify
            self.skipped.append(end - self.start)
            self.start, self.start_ts = end, None


def first_request_seq(records, servers: set[int], legacy: bool = False, tls: bool = True) -> dict:
    """The first request message that reaches an agent, in TCP sequence space (FIRST_REQUEST_SEQ_DEF).

    records: features.kfp.tcp_records(pcap, ack=True), in capture order. Only links the trace
    opened count (their SYN is in the capture, features/connections.py), unless legacy; on a link
    opened before the capture there is no handshake to skip. tls=False: no handshake on any link.

    Returns {"bytes", "link" ((client port, agent port)), "start" and "end" (client sequence
    numbers relative to its first byte), "acked" (False: no server data acknowledged the whole
    request before the capture ended, so it ends at the client's last byte), "skipped" (requests
    under 300 B on that link before it)}.

    A session ticket can acknowledge every request byte the capture has seen so far: at a vantage
    point beside the server, or when the client writes the HTTP header and body apart (C2:
    fault_diagnosis_edge_cloud_efceeb, alert_triage_edge_cloud_0a9eaa). The client's next data
    segment then does not acknowledge the ticket: it was sent before the ticket arrived, so the
    request goes on. Only if that segment was lost and resent after the ticket arrived would the
    request still end at the ticket. A client Finished that was lost and resent together with the
    start of the request is counted in it (C2: sensor_analysis_edge_cloud_274df9, 80 B), as the
    earlier measure does too: from headers alone its end inside that segment is unknown."""
    opened = {(sp, dp) for _, sp, dp, _, _, fl, *_ in records if dp in servers and fl & _SYN and not fl & _ACK}
    links: dict[tuple[int, int], _Link] = {}
    for ts, sp, dp, _, pl, fl, seq, ack in records:
        if dp in servers:
            conn, from_client = (sp, dp), True
        elif sp in servers:
            conn, from_client = (dp, sp), False
        else:
            continue
        if not legacy and conn not in opened:
            continue
        link = links.setdefault(conn, _Link(tls and conn in opened))
        if from_client:
            link.client(ts, pl, fl, seq, ack)
        else:
            link.server(pl, seq, ack)
    reqs = []
    for conn, link in links.items():
        if not link.found and link.pending:              # answered; the client sent nothing after
            link.finish(link.pending[0], True)
        if not link.found and link.phase == "request" and link.start_ts is not None:
            link.finish(link.top, False)                 # never acknowledged within the capture
        if link.found:
            reqs.append((link.found["start_ts"], conn, link.found))
    if not reqs:
        return {"bytes": 0, "link": None, "start": 0, "end": 0, "acked": False, "skipped": []}
    _, conn, f = min(reqs)
    return {"bytes": f["bytes"], "link": conn, "start": f["start"], "end": f["end"], "acked": f["acked"],
            "skipped": f["skipped"]}
