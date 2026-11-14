"""Cleartext captures: the first request starts at the first client byte, not after a TLS handshake."""

import json
import struct

from a2a_leakcheck.collect import collect, read_trace
from a2a_leakcheck.extract import extract
from features.first_request import first_request_seq_bytes

C, S = 50000, 8041


def _pcap(path):
    """One cleartext request–response on its own connection (DLT_NULL): a 600 B request, a 400 B answer."""
    segs = [(C, S, 100, 0, 0x02, 0), (S, C, 500, 101, 0x12, 0), (C, S, 101, 501, 0x10, 0),
            (C, S, 101, 501, 0x18, 600), (S, C, 501, 701, 0x10, 0), (S, C, 501, 701, 0x18, 400),
            (C, S, 701, 901, 0x10, 0)]
    out = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 96, 0)
    for i, (sp, dp, seq, ack, flags, n) in enumerate(segs):
        tcp = struct.pack(">HHIIBBHHH", sp, dp, seq, ack, 5 << 4, flags, 65535, 0, 0)
        ip = struct.pack(">BBHHHBBH4s4s", 0x45, 0, 40 + n, 0, 0, 64, 6, 0, bytes([127, 0, 0, 1]), bytes([127, 0, 0, 1]))
        pkt = struct.pack("<I", 2) + ip + tcp
        out += struct.pack("<IIII", i, 0, len(pkt), len(pkt) + n) + pkt
    path.write_bytes(out)


def _trace(tmp_path, name="t", **side):
    _pcap(tmp_path / f"{name}.pcap")
    (tmp_path / f"{name}.json").write_text(json.dumps({"agent_endpoints": {"executor": f"127.0.0.1:{S}"},
                                                       "workflow_class": "w", **side}))
    return tmp_path / f"{name}.pcap"


def test_tls_assumption_skips_a_cleartext_request(tmp_path):
    p = _trace(tmp_path)
    assert first_request_seq_bytes(p, {S}, tls=False) == 600
    assert first_request_seq_bytes(p, {S}) == 0                     # the request taken for a ClientHello


def test_sidecar_and_flag_mark_cleartext(tmp_path):
    p = _trace(tmp_path, "a", tls=False)
    q = _trace(tmp_path, "b")
    assert read_trace(p, [])[0].tls is False and read_trace(q, [])[0].tls is True
    assert read_trace(q, [], cleartext=True)[0].tls is False
    col = collect(tmp_path, [], cleartext=True)
    assert col["summary"]["cleartext_traces"] == 2
    assert collect(tmp_path, [])["summary"]["cleartext_traces"] == 1    # only the sidecar that says so


def test_extract_measures_cleartext_from_the_first_byte(tmp_path):
    _trace(tmp_path, "a", tls=False)
    ext = extract(collect(tmp_path, [])["traces"])
    assert list(ext["first_request"]) == [600.0]
    assert "first_request_cleartext" in ext["summary"]
