"""Every connection can end at its last data packet (features/connections.py, end_at_data).

The recorder before commit f38a2828 lost the last packets before each stop, and those were
connection closes: a TLS close_notify alert, ACKs, FINs, an RST. With end_at_data the features of
a capture that kept its closes and of one that lost them must be identical, and the first request
must not change.
"""

import numpy as np
import pytest

from features.connections import CLOSE_ALERT_LEN, data_ends, own_packets
from features.extractor import FeatureExtractor
from features.first_request import first_request
from features.kfp import tcp_packets
from features.roles import role_vectors

scapy_all = pytest.importorskip("scapy.all")
Ether, IP, TCP, Raw, wrpcap = (scapy_all.Ether, scapy_all.IP, scapy_all.TCP, scapy_all.Raw,
                               scapy_all.wrpcap)

A, B, C1, C2 = 9001, 9002, 50001, 50002


def _pkt(t, sport, dport, flags, n=0):
    p = Ether(src="02:00:00:00:00:01", dst="02:00:00:00:00:02") / IP(src="127.0.0.1", dst="127.0.0.1") \
        / TCP(sport=sport, dport=dport, flags=flags)
    if n:
        p = p / Raw(b"\x17" * n)
    p.time = t
    return p


def _conn(c, a, t0, replies=8):
    """Handshake, a 1500 B request, a streamed reply and a last ACK; then the close."""
    data = [(c, a, "S", 0), (a, c, "SA", 0), (c, a, "A", 0), (c, a, "PA", 517), (a, c, "PA", 1374),
            (c, a, "PA", 80), (c, a, "PA", 1500)] + [(a, c, "PA", 400)] * replies + [(c, a, "A", 0)]
    close = [(a, c, "PA", CLOSE_ALERT_LEN), (c, a, "A", 0), (c, a, "FA", 0), (a, c, "A", 0), (c, a, "RA", 0)]
    return ([_pkt(t0 + 0.01 * i, s, d, f, n) for i, (s, d, f, n) in enumerate(data)],
            [_pkt(t0 + 0.01 * len(data) + 1.5 + 0.001 * i, s, d, f, n) for i, (s, d, f, n) in enumerate(close)])


@pytest.fixture()
def pcaps(tmp_path):
    """complete: both connections with their closes; recorded: the last connection's close lost
    (as the old recorder lost it); cut: both closes removed by hand."""
    a_data, a_close = _conn(C1, A, 100.0)
    b_data, b_close = _conn(C2, B, 100.05, replies=5)
    paths = {k: tmp_path / f"{k}.pcap" for k in ("complete", "recorded", "cut")}
    by_time = lambda ps: sorted(ps, key=lambda p: float(p.time))          # noqa: E731
    wrpcap(str(paths["complete"]), by_time(a_data + b_data + a_close + b_close))
    wrpcap(str(paths["recorded"]), by_time(a_data + b_data + a_close))
    wrpcap(str(paths["cut"]), by_time(a_data[:-1] + b_data[:-1]))       # up to the last reply
    return paths


def test_data_ends_skips_the_close_and_the_alert(pcaps):
    pk = tcp_packets(pcaps["complete"])
    ends = data_ends(pk, {A, B})
    assert ends == {(C1, A): 15, (C2, B): 12}            # the last 400 B reply; the ACK after it is a close-side packet
    cut = own_packets(pk, {A, B}, end_at_data=True)
    assert all(p[4] != CLOSE_ALERT_LEN and not p[5] & 0x05 for p in cut)
    assert len(own_packets(pk, {A, B})) == len(pk)


def test_a_connection_without_data_keeps_its_packets_before_the_close():
    pk = [(0.0, C1, A, 0, 0, 0x02), (0.1, A, C1, 0, 0, 0x12), (0.2, C1, A, 0, 0, 0x10),
          (0.3, C1, A, 0, 0, 0x11), (0.4, A, C1, 0, 0, 0x10)]
    assert data_ends(pk, {A}) == {(C1, A): 3}


@pytest.mark.parametrize("role", [False, True])
def test_features_identical_with_and_without_the_lost_close(pcaps, role):
    ex = FeatureExtractor(agent_ports={A, B}, use_scapy=True, end_at_data=True)
    plain = FeatureExtractor(agent_ports={A, B}, use_scapy=True)
    port_role = {str(A): "executor", str(B): "validator"}

    def vec(e, k):
        packets = e._read_pcap(pcaps[k])
        if role:
            return np.concatenate([v[1] for _, v in sorted(role_vectors(e, packets, port_role).items())])
        return e._compute_features(k, packets).flat_vector()

    assert np.array_equal(vec(ex, "complete"), vec(ex, "recorded"))
    assert np.array_equal(vec(ex, "complete"), vec(plain, "cut"))
    assert not np.array_equal(vec(plain, "complete"), vec(plain, "recorded"))


def test_the_first_request_does_not_change(pcaps):
    for k in pcaps:
        pk = tcp_packets(pcaps[k])
        assert first_request(own_packets(pk, {A, B}, end_at_data=True), {A, B}) == first_request(pk, {A, B})
