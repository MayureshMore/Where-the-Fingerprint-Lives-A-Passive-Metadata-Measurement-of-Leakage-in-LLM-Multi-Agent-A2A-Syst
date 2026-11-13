"""The first request in TCP sequence space (features/first_request.py, first_request_seq).

Built from C2's fault_diagnosis_edge_cloud_ed7928 (data/raw_c2_padmax): the edge agent's request
to the diagnostics agent, padded to 8192, is 8,488 B. A Wi-Fi loss held five of its segments back
(captured 50.6 ms after the last one before them; the 974 B segment after the hole came first)
and the server's TLS session ticket (510 B) arrived in between. Paper 1's measure (writes ≤ 50 ms
apart) and the one ended at the first server data both stop at 1,802 B, the 80 B Finished
included; in sequence space the request runs to the server's acknowledgment on its response.

Two more C2 traces: in fault_diagnosis_edge_cloud_efceeb (data/raw_c2) the ticket acknowledged the
HTTP header before the capture had seen any of the body, and in alert_triage_edge_cloud_0a9eaa the
same happened on the link to the ticket agent on the Mac itself (no WAN delay: the capture is
beside the server). The body segments acknowledge only the server's handshake flight, not the
ticket: the client sent them before the ticket arrived, so the request goes on.
"""

import pytest

from features.connections import own_packets
from features.first_request import first_request, first_request_seq, first_request_seq_bytes
from features.kfp import tcp_packets, tcp_records
from scripts.check_session_design import earlier_first_message, first_message

scapy_all = pytest.importorskip("scapy.all")
Ether, IP, TCP, Raw, wrpcap = (scapy_all.Ether, scapy_all.IP, scapy_all.TCP, scapy_all.Raw,
                               scapy_all.wrpcap)

PI, CLOUD = "10.0.0.171", "172.30.0.100"
C, S = 59802, 8301
ISN = {"C": 1976620251, "S": 1238149436}

# ed7928's link to the diagnostics agent as captured on the Mac (en0), up to the start of the
# response: (ms, sender, TCP flags, seq and ack relative to each side's ISN, payload bytes).
ED7928 = [
    (0.00, "C", 0x02, 0, 0, 0),
    (13.00, "S", 0x12, 0, 1, 0),
    (16.47, "C", 0x10, 1, 1, 0),
    (17.51, "C", 0x10, 1, 1, 1448),          # ClientHello, first segment
    (17.52, "C", 0x18, 1449, 1, 100),        # ClientHello, the rest
    (28.87, "S", 0x10, 1, 1, 0),
    (30.14, "S", 0x10, 1, 1549, 0),
    (31.38, "S", 0x18, 1, 1549, 1415),       # ServerHello … server Finished
    (36.25, "C", 0x10, 1549, 1416, 0),
    (37.41, "C", 0x18, 1549, 1416, 80),      # client Finished
    (38.63, "C", 0x18, 1629, 1416, 274),     # the request: HTTP header
    (39.31, "C", 0x10, 1903, 1416, 1448),
    (48.98, "S", 0x10, 1416, 1629, 0),
    (49.03, "S", 0x18, 1416, 1629, 510),     # session tickets: acknowledge the Finished only
    (51.49, "S", 0x10, 1926, 1903, 0),
    (51.52, "S", 0x10, 1926, 3351, 0),
    (89.95, "C", 0x18, 9143, 1416, 974),     # the request's last segment, past the hole
    (102.92, "S", 0x10, 1926, 3351, 0),
    (106.25, "C", 0x10, 3351, 1926, 1448),   # the hole, resent
    (119.18, "S", 0x10, 1926, 4799, 0),
    (122.63, "C", 0x10, 4799, 1926, 1448),
    (122.63, "C", 0x18, 6247, 1926, 1448),
    (135.52, "S", 0x10, 1926, 7695, 0),
    (138.78, "C", 0x10, 7695, 1926, 1448),
    (151.60, "S", 0x10, 1926, 10117, 0),
    (152.65, "S", 0x18, 1926, 10117, 243),   # the response: acknowledges every request byte
    (204.17, "C", 0x10, 10117, 2169, 0),
    (216.86, "S", 0x18, 2169, 10117, 648),
    (225.28, "C", 0x10, 10117, 2817, 0),
    (3539.48, "S", 0x18, 2817, 10117, 555),
    (3547.19, "C", 0x10, 10117, 3372, 0),
    (3559.99, "S", 0x18, 3372, 10117, 1120),
]


# efceeb, link to the diagnostics agent (port 8101 in the lan arm), up to the response
EFCEEB = [
    (0.00, "C", 0x02, 0, 0, 0), (13.22, "S", 0x12, 0, 1, 0), (16.96, "C", 0x10, 1, 1, 0),
    (18.49, "C", 0x10, 1, 1, 1448), (18.86, "C", 0x18, 1449, 1, 100),
    (29.73, "S", 0x10, 1, 1, 0), (30.98, "S", 0x10, 1, 1449, 0), (31.02, "S", 0x10, 1, 1549, 0),
    (32.24, "S", 0x18, 1, 1549, 1415), (35.63, "C", 0x10, 1549, 1416, 0),
    (36.97, "C", 0x18, 1549, 1416, 80),      # client Finished
    (37.59, "C", 0x18, 1629, 1416, 274),     # HTTP header
    (49.67, "S", 0x10, 1416, 1629, 0), (49.72, "S", 0x10, 1416, 1903, 0),
    (49.74, "S", 0x18, 1416, 1903, 510),     # tickets: acknowledge the header, all the capture has seen
    (50.08, "C", 0x10, 1903, 1416, 1448),    # the body: acknowledges 1416, sent before the tickets arrived
    (50.87, "C", 0x10, 3351, 1416, 1448), (50.88, "C", 0x10, 4799, 1416, 1448),
    (51.41, "C", 0x18, 6247, 1416, 830),
    (62.58, "S", 0x10, 1926, 3351, 0), (62.64, "S", 0x10, 1926, 6247, 0), (63.68, "S", 0x10, 1926, 7077, 0),
    (97.82, "C", 0x10, 7077, 1926, 0),
    (110.57, "S", 0x18, 1926, 7077, 891),    # the response
    (113.75, "C", 0x10, 7077, 2817, 0),
]

# 0a9eaa, link to the ticket agent on the Mac (port 8105): no WAN delay, the capture is beside it
A9EAA = [
    (0.00, "C", 0x02, 0, 0, 0), (0.81, "S", 0x12, 0, 1, 0), (7.08, "C", 0x10, 1, 1, 0), (7.34, "S", 0x10, 1, 1, 0),
    (8.72, "C", 0x10, 1, 1, 1448), (8.72, "C", 0x18, 1449, 1, 100), (8.89, "S", 0x10, 1, 1549, 0),
    (12.02, "S", 0x18, 1, 1549, 1415), (17.31, "C", 0x10, 1549, 1416, 0),
    (17.84, "C", 0x18, 1549, 1416, 80),      # client Finished
    (17.85, "C", 0x18, 1629, 1416, 226),     # HTTP header
    (17.99, "S", 0x10, 1416, 1855, 0),
    (18.54, "S", 0x18, 1416, 1855, 510),     # tickets: acknowledge the header
    (18.62, "C", 0x18, 1855, 1416, 154),     # the body, sent before the tickets arrived
    (18.72, "S", 0x10, 1926, 2009, 0), (70.16, "C", 0x10, 2009, 1926, 0),
    (70.30, "S", 0x18, 1926, 2009, 214),     # the response
    (73.25, "C", 0x10, 2009, 2140, 0), (74.73, "C", 0x11, 2009, 2140, 0), (74.82, "S", 0x10, 2140, 2010, 0),
    (75.07, "S", 0x11, 2140, 2010, 0), (79.11, "C", 0x10, 2010, 2141, 0),
]


def _write(path, rows, isn=ISN, t0=1_762_000_000.0):
    pkts = []
    for ms, who, flags, seq, ack, n in rows:
        src, dst, sp, dp = (PI, CLOUD, C, S) if who == "C" else (CLOUD, PI, S, C)
        other = "S" if who == "C" else "C"
        p = Ether(src="02:00:00:00:00:01", dst="02:00:00:00:00:02") / IP(src=src, dst=dst) / TCP(
            sport=sp, dport=dp, flags=flags, seq=(isn[who] + seq) % 2 ** 32,
            ack=(isn[other] + ack) % 2 ** 32 if flags & 0x10 else 0)
        if n:
            p = p / Raw(b"\x17" * n)
        p.time = t0 + ms / 1000
        pkts.append(p)
    wrpcap(str(path), pkts)
    return path


def test_ed7928(tmp_path):
    pcap = _write(tmp_path / "ed7928.pcap", ED7928)
    recs = tcp_records(pcap, ack=True)
    assert len(recs[0]) == 8 and len(tcp_records(pcap)[0]) == 7
    assert recs[13][7] == (ISN["C"] + 1629) % 2 ** 32                  # the ticket's ack, read back
    fr = first_request_seq(recs, {S})
    assert fr == {"bytes": 8488, "link": (C, S), "start": 1628, "end": 10116, "acked": True, "skipped": []}
    assert 8488 - 8192 == 296                                           # in the 8192 bucket
    assert first_request_seq_bytes(pcap, {S}) == 8488
    assert first_message(pcap, {S}, True)["bytes"] == 8488
    # both measures used before: 80 (Finished) + 274 + 1448 B
    assert first_request(own_packets(tcp_packets(pcap, dedup=True), {S}), {S})["bytes"] == 1802
    assert earlier_first_message(pcap, {S}, True) == (1802, 1802)


def test_ticket_acknowledges_the_header(tmp_path):
    """efceeb and 0a9eaa: the earlier measures count the 80 B Finished; the request itself is
    5,448 and 380 B."""
    for rows, n, before in ((EFCEEB, 5448, 5528), (A9EAA, 380, 460)):
        pcap = _write(tmp_path / f"{n}.pcap", rows)
        assert first_request_seq(tcp_records(pcap, ack=True), {S}) == {
            "bytes": n, "link": (C, S), "start": 1628, "end": 1628 + n, "acked": True, "skipped": []}
        assert first_request(own_packets(tcp_packets(pcap, dedup=True), {S}), {S})["bytes"] == before


def _request(isn, ticket_at: int | None, pause_ms: float = 20.0, size: int = 20000, card: bool = False,
             finished_alone: bool = True, respond: bool = True):
    """A handshake (517 B ClientHello, 80 B Finished) and a request of `size` B in two windows
    of 1448 B segments, `pause_ms` apart; ticket_at: the client byte (relative) the server's
    ticket acknowledges, sent between the windows. card: a 197 B GET answered first."""
    rows = [(0, "C", 0x02, 0, 0, 0), (1, "S", 0x12, 0, 1, 0), (2, "C", 0x10, 1, 1, 0),
            (3, "C", 0x18, 1, 1, 517), (4, "S", 0x18, 1, 518, 1400)]
    c, s, t = 518, 1401, 5.0
    if finished_alone:
        rows.append((t, "C", 0x18, c, s, 80))
        c += 80
        t += 0.5
    if card:
        rows += [(t, "C", 0x18, c, s, 197), (t + 2, "S", 0x18, s, c + 197, 900)]
        c, s, t = c + 197, s + 900, t + 3
    first = c
    half = size // 2
    for chunk in (half, size - half):
        while chunk > 0:
            n = min(1448, chunk)
            rows.append((t, "C", 0x18 if n < 1448 else 0x10, c, s, n))
            c, chunk, t = c + n, chunk - n, t + 0.1
        if ticket_at is not None and c - first == half:
            rows.append((t + 1, "S", 0x18, s, ticket_at, 510))
            s += 510
        t += pause_ms
    if respond:
        rows.append((t + 5, "S", 0x18, s, c, 300))
    return rows


def test_ticket_mid_request_without_loss(tmp_path):
    """No loss: the server's ticket arrives between two windows of a 20,000 B request. Ended at
    the first server data, the request is cut in half; in sequence space it is whole."""
    pcap = _write(tmp_path / "t.pcap", _request(ISN, ticket_at=598))
    assert first_request_seq_bytes(pcap, {S}) == 20000
    assert earlier_first_message(pcap, {S}, True) == (20000, 10000)


def test_sequence_numbers_wrap(tmp_path):
    pcap = _write(tmp_path / "w.pcap", _request({"C": 2 ** 32 - 700, "S": 2 ** 32 - 5}, ticket_at=598))
    assert first_request_seq(tcp_records(pcap, ack=True), {S})["bytes"] == 20000


def test_ticket_that_acknowledges_part_of_the_request(tmp_path):
    """A ticket written after the server read part of the request still acknowledges less than
    the client has sent, and does not end it."""
    pcap = _write(tmp_path / "p.pcap", _request(ISN, ticket_at=598 + 4000))
    assert first_request_seq_bytes(pcap, {S}) == 20000


def test_card_get_first(tmp_path):
    """An agent-card GET answered before the A2A message is a request of its own, under 300 B."""
    fr = first_request_seq(tcp_records(_write(tmp_path / "c.pcap", _request(ISN, None, card=True)), ack=True), {S})
    assert (fr["bytes"], fr["skipped"]) == (20000, [197])


def test_finished_sent_with_the_request(tmp_path):
    """No separate Finished segment: everything after the ClientHello is counted (old and new)."""
    pcap = _write(tmp_path / "f.pcap", _request(ISN, None, finished_alone=False, pause_ms=1))
    assert first_request_seq_bytes(pcap, {S}) == 20000


def test_no_response_in_the_capture(tmp_path):
    fr = first_request_seq(tcp_records(_write(tmp_path / "n.pcap", _request(ISN, 598, respond=False)), ack=True), {S})
    assert (fr["bytes"], fr["acked"]) == (20000, False)


def test_only_links_the_trace_opened(tmp_path):
    rows = [r for r in ED7928 if r[2] != 0x02 and r[2] != 0x12]       # no SYN: opened before the capture
    pcap = _write(tmp_path / "o.pcap", rows)
    assert first_request_seq_bytes(pcap, {S}) == 0
    fr = first_request_seq(tcp_records(pcap, ack=True), {S}, legacy=True)
    # no handshake is skipped on a link opened before the capture: its first message here is the
    # ClientHello, which the ServerHello acknowledges
    assert (fr["link"], fr["bytes"], fr["start"], fr["end"]) == ((C, S), 1548, 0, 1548)


def test_answer_then_a_second_request(tmp_path):
    """A response, then a second request on the same link that acknowledges it: two requests."""
    rows = [(0, "C", 0x02, 0, 0, 0), (1, "S", 0x12, 0, 1, 0), (2, "C", 0x10, 1, 1, 0),
            (3, "C", 0x18, 1, 1, 517), (4, "S", 0x18, 1, 518, 1400), (5, "C", 0x18, 518, 1401, 80),
            (6, "C", 0x18, 598, 1401, 400),      # request 1
            (9, "S", 0x18, 1401, 998, 300),      # its response
            (12, "C", 0x18, 998, 1701, 700),     # request 2, after the response
            (15, "S", 0x18, 1701, 1698, 300)]
    fr = first_request_seq(tcp_records(_write(tmp_path / "k.pcap", rows), ack=True), {S})
    assert (fr["bytes"], fr["start"], fr["end"]) == (400, 597, 997)


def test_client_had_the_ticket_before_it_went_on(tmp_path):
    """The case left: the client receives the ticket before it sends the rest of the request
    (its next segment acknowledges the ticket). From headers alone this is a 274 B request and its
    answer, then another request; under 300 B the first is skipped, and the rest is measured."""
    rows = [(r[0], r[1], r[2], r[3], 1926 if r[1] == "C" and r[3] >= 1903 else r[4], r[5]) for r in EFCEEB]
    fr = first_request_seq(tcp_records(_write(tmp_path / "h.pcap", rows), ack=True), {S})
    assert (fr["bytes"], fr["skipped"]) == (5448 - 274, [274])


def test_finished_resent_with_the_header(tmp_path):
    """sensor_analysis_edge_cloud_274df9 (data/raw_c2_padmax): the Finished and the HTTP header were
    lost and resent as one 354 B segment, after the body. The Finished is then counted (80 B)."""
    rows = [
        (0.00, "C", 0x02, 0, 0, 0), (12.15, "S", 0x12, 0, 1, 0), (17.27, "C", 0x10, 1, 1, 0),
        (17.87, "C", 0x10, 1, 1, 1448), (17.88, "C", 0x18, 1449, 1, 100),
        (30.36, "S", 0x10, 1, 1, 0), (30.46, "S", 0x10, 1, 1549, 0), (31.65, "S", 0x18, 1, 1549, 1415),
        (40.05, "C", 0x10, 1549, 1416, 0),
        (59.00, "C", 0x10, 1903, 1416, 1448), (59.61, "C", 0x10, 3351, 1416, 1448),
        (63.58, "C", 0x10, 4799, 1416, 1448), (63.59, "C", 0x18, 6247, 1416, 1448),
        (71.74, "S", 0x10, 1416, 1549, 0), (75.54, "S", 0x10, 1416, 1549, 0),
        (95.98, "C", 0x18, 9143, 1416, 974),
        (95.98, "C", 0x18, 1549, 1416, 354),     # Finished + header, resent together
        (107.38, "S", 0x10, 1416, 1549, 0), (107.40, "S", 0x10, 1416, 7695, 0),
        (107.41, "S", 0x18, 1416, 7695, 510),    # tickets
        (111.92, "C", 0x10, 7695, 1416, 1448),
        (124.58, "S", 0x10, 1926, 10117, 0), (159.35, "C", 0x10, 10117, 1926, 0),
        (172.28, "S", 0x18, 1926, 10117, 891),   # the response
    ]
    fr = first_request_seq(tcp_records(_write(tmp_path / "r.pcap", rows), ack=True), {S})
    assert (fr["bytes"], fr["start"], fr["end"]) == (8488 + 80, 1548, 10116)
