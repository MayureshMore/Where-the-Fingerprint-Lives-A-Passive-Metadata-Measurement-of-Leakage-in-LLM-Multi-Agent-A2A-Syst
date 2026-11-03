"""A trace uses only the TCP connections it opens itself (features/connections.py).

The fixture is a capture that begins with the tail of an earlier trace's connection to the same
agent (no SYN in the capture: a TLS close_notify from the agent, a stray client write, the FINs),
followed by the trace's own connection. The tail must not reach the features, the first-request
measure or the role samples; the legacy option keeps it.
"""

import numpy as np
import pytest

from features.connections import opened_connections, own_packets
from features.extractor import FeatureExtractor
from features.first_request import first_request_bytes
from features.kfp import tcp_packets
from features.roles import role_vectors

scapy_all = pytest.importorskip("scapy.all")
Ether, IP, TCP, Raw, wrpcap = (scapy_all.Ether, scapy_all.IP, scapy_all.TCP, scapy_all.Raw,
                               scapy_all.wrpcap)

AGENT, OLD, NEW = 9001, 50000, 50001


def _pkt(t, sport, dport, flags, n=0):
    p = Ether(src="02:00:00:00:00:01", dst="02:00:00:00:00:02") / IP(src="127.0.0.1", dst="127.0.0.1") \
        / TCP(sport=sport, dport=dport, flags=flags)
    if n:
        p = p / Raw(b"\x17" * n)
    p.time = t
    return p


def _leftover(t0=100.0):
    """The previous trace's connection closing: close_notify, a stray 2000 B client write, FINs."""
    return [_pkt(t0, AGENT, OLD, "PA", 24), _pkt(t0 + 0.001, OLD, AGENT, "A"),
            _pkt(t0 + 0.002, OLD, AGENT, "PA", 2000), _pkt(t0 + 0.003, OLD, AGENT, "FA"),
            _pkt(t0 + 0.004, AGENT, OLD, "FA")]


def _own(t0=100.1):
    """This trace's connection: handshake, a 1500 B request, a streamed reply, close."""
    seq = [(NEW, AGENT, "S", 0), (AGENT, NEW, "SA", 0), (NEW, AGENT, "A", 0),
           (NEW, AGENT, "PA", 517), (AGENT, NEW, "PA", 1374), (NEW, AGENT, "PA", 80),
           (NEW, AGENT, "PA", 1500)] + [(AGENT, NEW, "PA", 400)] * 12 + [(NEW, AGENT, "FA", 0), (AGENT, NEW, "FA", 0)]
    return [_pkt(t0 + 0.01 * i, s, d, f, n) for i, (s, d, f, n) in enumerate(seq)]


@pytest.fixture()
def pcaps(tmp_path):
    with_tail, clean = tmp_path / "with_tail.pcap", tmp_path / "clean.pcap"
    wrpcap(str(with_tail), _leftover() + _own())
    wrpcap(str(clean), _own())
    return with_tail, clean


def test_only_connections_opened_in_the_capture_are_kept(pcaps):
    pk = tcp_packets(pcaps[0])
    assert opened_connections(pk, {AGENT}) == {(NEW, AGENT)}
    kept = own_packets(pk, {AGENT})
    assert {p[1] for p in kept} | {p[2] for p in kept} == {NEW, AGENT}
    assert len(own_packets(pk, {AGENT}, legacy=True)) == len(pk)


def test_features_ignore_the_previous_trace_tail(pcaps):
    with_tail, clean = pcaps
    own = FeatureExtractor(agent_ports={AGENT}, use_scapy=True)
    legacy = FeatureExtractor(agent_ports={AGENT}, use_scapy=True, own_connections=False)
    v_tail = own._compute_features("t", own._read_pcap(with_tail)).flat_vector()
    v_clean = own._compute_features("t", own._read_pcap(clean)).flat_vector()
    v_legacy = legacy._compute_features("t", legacy._read_pcap(with_tail)).flat_vector()
    assert np.array_equal(v_tail, v_clean)
    assert not np.array_equal(v_legacy, v_clean)


def test_first_request_is_on_a_link_the_trace_opened(pcaps):
    with_tail, clean = pcaps
    assert first_request_bytes(with_tail, {AGENT}) == first_request_bytes(clean, {AGENT}) == 1500
    assert first_request_bytes(with_tail, {AGENT}, legacy=True) == 2000      # the old, earlier link


def test_role_pooling_ignores_the_tail(pcaps):
    with_tail, clean = pcaps
    port_role = {str(AGENT): "executor"}
    own = FeatureExtractor(agent_ports={AGENT}, use_scapy=True)
    legacy = FeatureExtractor(agent_ports={AGENT}, use_scapy=True, own_connections=False)
    r_tail = role_vectors(own, own._read_pcap(with_tail), port_role)[str(AGENT)][1]
    r_clean = role_vectors(own, own._read_pcap(clean), port_role)[str(AGENT)][1]
    r_legacy = role_vectors(legacy, legacy._read_pcap(with_tail), port_role)[str(AGENT)][1]
    assert np.array_equal(r_tail, r_clean)
    assert not np.array_equal(r_legacy, r_clean)


def test_a_capture_with_only_a_tail_yields_no_role_sample(tmp_path):
    p = tmp_path / "tail_only.pcap"
    wrpcap(str(p), _leftover())
    own = FeatureExtractor(agent_ports={AGENT}, use_scapy=True)
    assert own._read_pcap(p) == []
    assert role_vectors(own, own._read_pcap(p), {str(AGENT): "executor"}) == {}
