"""Release preparation: placeholder MAC addresses, the watcher-log cut, the per-capture checks."""

import json
import struct

from scripts.package_paper2_data import check_pcap, cut_jsonl, leaked_originals, sidecar_hosts, with_home
from scripts.strip_payload import MacPlaceholders, payload_bytes, real_macs, strip_file

MAC_A = bytes.fromhex("a4b1c2d3e4f5")       # stand-ins for two hosts' hardware addresses
MAC_B = bytes.fromhex("dca632001122")
BCAST = b"\xff" * 6


def _eth_pcap(frames, snaplen=96):
    """Classic little-endian pcap, DLT_EN10MB; frames: (dst, src, src_ip, dst_ip, payload)."""
    out = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, snaplen, 1)
    for i, (dst, src, sip, dip, payload) in enumerate(frames):
        tcp = struct.pack(">HHIIBBHHH", 50000, 8101, 0, 0, 5 << 4, 0x18, 0, 0, 0)
        ip = struct.pack(">BBHHHBBH4s4s", 0x45, 0, 20 + len(tcp) + len(payload), 0, 0, 64, 6, 0,
                         bytes(map(int, sip.split("."))), bytes(map(int, dip.split("."))))
        frame = dst + src + b"\x08\x00" + ip + tcp + payload
        kept = frame[:snaplen]
        out += struct.pack("<IIII", i, 0, len(kept), len(frame)) + kept
    return out


def _frames():
    return [(MAC_A, MAC_B, "10.0.0.171", "172.30.0.100", b"x" * 40),
            (MAC_B, MAC_A, "172.30.0.100", "10.0.0.171", b"y" * 40),
            (BCAST, MAC_B, "10.0.0.171", "10.0.0.228", b"")]


def test_placeholders_replace_unicast_addresses_consistently(tmp_path):
    a, b = tmp_path / "a.pcap", tmp_path / "b.pcap"
    a.write_bytes(_eth_pcap(_frames()))
    b.write_bytes(_eth_pcap(_frames()[::-1]))
    macs = MacPlaceholders()
    strip_file(a, tmp_path / "s" / "a.pcap", macs)
    strip_file(b, tmp_path / "s" / "b.pcap", macs)
    for f in ("a.pcap", "b.pcap"):
        out = (tmp_path / "s" / f).read_bytes()
        assert MAC_A not in out and MAC_B not in out and BCAST in out
        assert payload_bytes(tmp_path / "s" / f) == 0 and real_macs(tmp_path / "s" / f) == 0
    assert real_macs(a) == 5                       # the broadcast address is not counted
    table = {r["placeholder"]: r["ipv4"] for r in macs.table()}
    assert table == {"02:00:00:00:00:01": ["172.30.0.100"],        # MAC_A: the first frame's destination
                     "02:00:00:00:00:02": ["10.0.0.171"]}
    assert macs.originals() == [MAC_A, MAC_B]


def test_strip_without_placeholders_keeps_addresses(tmp_path):
    a = tmp_path / "a.pcap"
    a.write_bytes(_eth_pcap(_frames()))
    strip_file(a, tmp_path / "s.pcap")
    assert MAC_A in (tmp_path / "s.pcap").read_bytes() and real_macs(tmp_path / "s.pcap") == 5


def test_check_pcap_flags_snaplen_payload_hosts_and_macs(tmp_path):
    a = tmp_path / "a.pcap"
    a.write_bytes(_eth_pcap(_frames(), snaplen=128))
    bad = " | ".join(check_pcap(a, {"10.0.0.171", "172.30.0.100"}))
    assert "snaplen 128" in bad and "payload bytes" in bad and "real MAC" in bad and "10.0.0.228" in bad
    strip_file(a, tmp_path / "s.pcap", MacPlaceholders())
    assert check_pcap(tmp_path / "s.pcap", {"10.0.0.171", "172.30.0.100", "10.0.0.228"}) == [
        "snaplen 128"]                              # the file header's snaplen is kept as captured


def test_cut_jsonl_keeps_the_window(tmp_path):
    src = tmp_path / "w.jsonl"
    src.write_text("".join(json.dumps({"time": t, "at": str(t)}) + "\n" for t in (5, 10, 15, 20, 25)))
    assert cut_jsonl(src, tmp_path / "c.jsonl", 10, 20) == {"kept": 3, "dropped": 2}
    assert [json.loads(x)["time"] for x in (tmp_path / "c.jsonl").read_text().splitlines()] == [10, 15, 20]


def test_leaked_originals_finds_bytes_and_text(tmp_path):
    (tmp_path / "a.json").write_text('{"ether": "A4:B1:C2:D3:E4:F5"}')
    (tmp_path / "b.bin").write_bytes(b"\0" + MAC_B + b"\0")
    (tmp_path / "c.json").write_text('{"ok": 1}')
    assert leaked_originals(tmp_path, [MAC_A, MAC_B]) == ["a.json", "b.bin"]


def test_sidecar_hosts(tmp_path):
    s = tmp_path / "t.json"
    s.write_text(json.dumps({"agent_endpoints": {"diagnostics": "172.30.0.100:8101", "ticket": "10.0.0.228:8105"},
                             "edge_host": "10.0.0.171"}))
    assert sidecar_hosts(s) == {"172.30.0.100", "10.0.0.228", "10.0.0.171"}


def test_with_home_finds_the_home_path(tmp_path):
    from pathlib import Path
    (tmp_path / "a.json").write_text(f'{{"data": "{Path.home()}/x"}}')
    (tmp_path / "b.json").write_text('{"data": "data/raw_c2"}')
    assert with_home(tmp_path) == ["a.json"]
