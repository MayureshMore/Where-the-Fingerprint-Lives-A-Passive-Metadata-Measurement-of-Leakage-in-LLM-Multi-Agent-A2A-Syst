"""Every payload byte counted once (features/kfp.py, dedup).

A TCP retransmission repeats bytes the observer has already seen. With dedup the features, the
first-request size and the k-FP packets of a capture with a retransmitted segment equal those of
the same capture without it; a partial retransmission keeps only its new bytes; a SYN starts a
reused port pair afresh.
"""

import numpy as np
import pytest

from features.connections import own_packets
from features.extractor import FeatureExtractor
from features.first_request import first_request_bytes
from features.kfp import duplicate_bytes, tcp_packets

scapy_all = pytest.importorskip("scapy.all")
Ether, IP, TCP, Raw, wrpcap = (scapy_all.Ether, scapy_all.IP, scapy_all.TCP, scapy_all.Raw,
                               scapy_all.wrpcap)

A, C = 9001, 50001
ISN_C, ISN_A = 1000, 50000


def _pkt(t, sport, dport, flags, seq, n=0):
    p = Ether(src="02:00:00:00:00:01", dst="02:00:00:00:00:02") / IP(src="127.0.0.1", dst="127.0.0.1") \
        / TCP(sport=sport, dport=dport, flags=flags, seq=seq)
    if n:
        p = p / Raw(b"\x17" * n)
    p.time = t
    return p


def _trace(resend: str | None):
    """Handshake, ClientHello, server flight, client Finished, a 3000 B request in two segments,
    a streamed reply. resend: None, "full" (the second request segment again) or "partial" (a
    segment repeating its last 500 B plus 200 new ones, with the 200 then missing from the
    original)."""
    c, a = ISN_C + 1, ISN_A + 1
    out = [_pkt(0.000, C, A, "S", ISN_C), _pkt(0.001, A, C, "SA", ISN_A), _pkt(0.002, C, A, "A", c)]
    t = 0.003
    for sport, dport, n in ((C, A, 517), (A, C, 1374), (C, A, 80)):
        seq = c if sport == C else a
        out.append(_pkt(t, sport, dport, "PA", seq, n))
        c, a = (c + n, a) if sport == C else (c, a + n)
        t += 0.001
    out.append(_pkt(t, C, A, "PA", c, 1500))
    first2 = c + 1500
    if resend == "partial":
        out.append(_pkt(t + 0.001, C, A, "PA", first2, 1300))
        out.append(_pkt(t + 0.020, C, A, "PA", first2 + 800, 700))     # repeats 500, adds 200
    else:
        out.append(_pkt(t + 0.001, C, A, "PA", first2, 1500))
        if resend == "full":
            out.append(_pkt(t + 0.020, C, A, "PA", first2, 1500))
    c = first2 + 1500
    t += 0.2
    for i in range(6):
        out.append(_pkt(t + 0.01 * i, A, C, "PA", a, 400))
        a += 400
    return out


@pytest.fixture()
def pcaps(tmp_path):
    paths = {k: tmp_path / f"{k}.pcap" for k in ("clean", "full", "partial")}
    for k, p in paths.items():
        wrpcap(str(p), _trace(None if k == "clean" else k))
    return paths


def test_duplicate_bytes_counts_repeated_bytes():
    recs = [(0, C, A, 0, 0, 0x02, 10), (1, C, A, 1500, 1448, 0x18, 11), (2, C, A, 1500, 1448, 0x18, 11),
            (3, C, A, 800, 700, 0x18, 11 + 1000), (4, C, A, 0, 0, 0x02, 99), (5, C, A, 1500, 1448, 0x18, 100)]
    assert duplicate_bytes(recs) == [0, 0, 1448, 448, 0, 0]       # the SYN at 4 starts afresh


def test_dedup_drops_the_retransmission(pcaps):
    clean = tcp_packets(pcaps["clean"])
    full = tcp_packets(pcaps["full"])
    assert len(full) == len(clean) + 1
    assert tcp_packets(pcaps["full"], dedup=True) == [p for p in full if p != full[8]]
    assert sum(p[4] for p in tcp_packets(pcaps["full"], dedup=True)) == sum(p[4] for p in clean)
    assert sum(p[4] for p in tcp_packets(pcaps["partial"], dedup=True)) == sum(p[4] for p in clean)


def test_first_request_counts_each_byte_once(pcaps):
    assert first_request_bytes(pcaps["clean"], {A}) == 3000
    assert first_request_bytes(pcaps["full"], {A}) == 4500                 # the published measurement
    assert first_request_bytes(pcaps["full"], {A}, dedup=True) == 3000
    assert first_request_bytes(pcaps["partial"], {A}, dedup=True) == 3000


@pytest.mark.parametrize("end_at_data", [False, True])
def test_features_with_dedup_equal_the_clean_capture(pcaps, end_at_data):
    def vec(k, dedup):
        ex = FeatureExtractor(agent_ports={A}, use_scapy=True, dedup=dedup, end_at_data=end_at_data)
        return ex._compute_features(k, ex._read_pcap(pcaps[k])).flat_vector()
    clean = vec("clean", False)
    assert not np.array_equal(vec("full", False), clean)
    assert np.array_equal(vec("full", True), clean)          # every feature, timing included


def test_kfp_packets_drop_the_retransmission(pcaps):
    full = own_packets(tcp_packets(pcaps["full"], dedup=True), {A})
    clean = own_packets(tcp_packets(pcaps["clean"]), {A})
    assert [p[1:] for p in full] == [p[1:] for p in clean]
