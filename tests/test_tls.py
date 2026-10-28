"""TLS control plumbing: per-agent TLS switch and the raw-capture record check."""

import struct

import pytest

from agents import tls
from scripts.check_tls_capture import check, scan
from scripts.strip_payload import strip_file


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("A2A_TLS_CERT", "A2A_TLS_KEY", "A2A_TLS_CA", "A2A_TLS_DEFAULT"):
        monkeypatch.delenv(k, raising=False)


def test_tls_off_by_default():
    assert tls.scheme() == "http" and tls.server_kwargs() == {} and tls.client_verify() is True


def test_configure_default_off_still_allows_per_agent_tls():
    tls.configure("data/tls", default_on=False)
    assert tls.scheme() == "http" and tls.server_kwargs() == {}
    assert tls.scheme(True) == "https"
    assert tls.server_kwargs(True)["ssl_certfile"].endswith("agent.pem")


def test_configure_default_on():
    tls.configure("data/tls")
    assert tls.scheme() == "https" and tls.scheme(False) == "http"


def _pcap(packets):
    """Classic little-endian pcap, DLT_NULL, IPv4/TCP packets of (flags, payload)."""
    out = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 96, 0)
    for i, (flags, payload) in enumerate(packets):
        tcp = struct.pack(">HHIIBBHHH", 50000, 8041, 0, 0, 5 << 4, flags, 0, 0, 0)
        ip = struct.pack(">BBHHHBBH4s4s", 0x45, 0, 20 + len(tcp) + len(payload), 0, 0, 64, 6, 0,
                         bytes([127, 0, 0, 1]), bytes([127, 0, 0, 1]))
        pkt = struct.pack("<I", 2) + ip + tcp + payload
        out += struct.pack("<IIII", i, 0, len(pkt), len(pkt)) + pkt
    return out


def test_scan_counts_tls_records_and_connections(tmp_path):
    f = tmp_path / "t.pcap"
    f.write_bytes(_pcap([(0x02, b""), (0x18, bytes.fromhex("160301020001") + b"\0" * 10),
                         (0x18, bytes.fromhex("17030300bb0f") + b"\0" * 10)]))
    s = scan(f)
    assert s["connections"] == 1 and s["client_hellos"] == 1 and s["tls_appdata_records"] == 1
    assert check({"t": s}, "tls") == [] and check({"t": s}, "clear")


def test_scan_cleartext_and_rejects_stripped(tmp_path):
    f = tmp_path / "c.pcap"
    f.write_bytes(_pcap([(0x02, b""), (0x18, b"POST / HTTP/1.1\r\n")]))
    s = scan(f)
    assert s["http_requests"] == 1 and check({"c": s}, "clear") == [] and check({"c": s}, "tls")
    strip_file(f, tmp_path / "s.pcap")
    assert "stripped" in check({"s": scan(tmp_path / "s.pcap")}, "clear")[0]
