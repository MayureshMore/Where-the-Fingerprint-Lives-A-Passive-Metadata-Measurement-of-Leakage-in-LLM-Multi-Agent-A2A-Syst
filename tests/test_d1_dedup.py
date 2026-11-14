"""D1 with every payload byte counted once: the on-wire volume and the before/after comparison."""

import json
import struct

from scripts.compare_d1_dedup import compare, fmt, paired_numbers
from scripts.evaluate_tls_control import trace_volume


def _pcap(segments):
    """DLT_NULL pcap; segments: (flags, seq, payload_len) from client port 50000 to agent port 8041."""
    out = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 96, 0)
    for i, (flags, seq, n) in enumerate(segments):
        tcp = struct.pack(">HHIIBBHHH", 50000, 8041, seq, 0, 5 << 4, flags, 0, 0, 0)
        ip = struct.pack(">BBHHHBBH4s4s", 0x45, 0, 40 + n, 0, 0, 64, 6, 0, bytes([127, 0, 0, 1]), bytes([127, 0, 0, 1]))
        pkt = struct.pack("<I", 2) + ip + tcp
        out += struct.pack("<IIII", i, 0, len(pkt), len(pkt) + n) + pkt
    return out


def test_trace_volume_drops_a_retransmitted_segment(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "t.pcap").write_bytes(_pcap([(0x02, 0, 0), (0x18, 1, 100), (0x18, 1, 100), (0x18, 101, 50)]))
    (raw / "t.json").write_text(json.dumps({"agent_endpoints": {"executor": "127.0.0.1:8041"}}))
    kept, once = trace_volume(raw, dedup=False), trace_volume(raw)              # dedup is the default
    assert kept["packets_mean"] == 4 and once["packets_mean"] == 3
    assert kept["bytes_mean"] - once["bytes_mean"] == 4 + 40 + 100                # the retransmitted frame


def test_compare_marks_same_changed_and_pending():
    rows = compare({"a": 0.61, "b": [0.5, 0.4, 0.6], "c": "LEAK"}, {"a": 0.58, "b": [0.5, 0.4, 0.6]})
    assert [r["same"] for r in rows] == [False, True, None]
    assert fmt(None) == "pending" and fmt([0.5, 0.4, 0.6]) == "0.5000 [0.4000, 0.6000]"


def test_paired_difference_significance():
    r = {"within_clear": {"macro_f1": 0.66, "ci_lo": 0.6, "ci_hi": 0.71}, "within_tls": {"macro_f1": 0.58, "ci_lo": 0.52, "ci_hi": 0.63},
         "clear_to_tls": {"macro_f1": 0.45, "ci_lo": 0.4, "ci_hi": 0.5},
         "tls_minus_clear": {"diff": -0.08, "ci_lo": -0.14, "ci_hi": -0.02, "shared_groups": 231}}
    t = {"results": {"role": r, "workflow": r, "topology": r}, "overhead": {"bytes_ratio": 1.09, "packets_ratio": 1.05}}
    p = paired_numbers(t)
    assert p["workflow: TLS − cleartext interval contains 0 (not significant)"] is False
    assert p["tls_control_own: retransmissions"].startswith("kept")
