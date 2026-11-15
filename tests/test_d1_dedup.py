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


def _conn_pcap(path, segs):
    """DLT_NULL pcap of one connection: (t, sport, dport, seq, flags, payload)."""
    out = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 96, 0)
    for t, sp, dp, seq, flags, n in segs:
        tcp = struct.pack(">HHIIBBHHH", sp, dp, seq, 0, 5 << 4, flags, 0, 0, 0)
        ip = struct.pack(">BBHHHBBH4s4s", 0x45, 0, 40 + n, 0, 0, 64, 6, 0, bytes([127, 0, 0, 1]), bytes([127, 0, 0, 1]))
        pkt = struct.pack("<I", 2) + ip + tcp
        out += struct.pack("<IIII", t, 0, len(pkt), len(pkt) + n) + pkt
    path.write_bytes(out)


def test_retransmission_after_the_last_data_packet(tmp_path):
    from scripts.compare_d1_dedup import trace_retransmissions
    c, s = 50000, 8041
    _conn_pcap(tmp_path / "t.pcap", [(0, c, s, 0, 0x02, 0), (1, c, s, 1, 0x18, 300), (2, s, c, 1, 0x18, 500),
                                      (3, s, c, 501, 0x18, 24), (4, s, c, 501, 0x18, 24),      # the 24 B record resent
                                      (5, c, s, 301, 0x18, 300), (6, c, s, 401, 0x18, 300)])    # 200 B of it again
    r = trace_retransmissions(tmp_path / "t.pcap", {s})
    assert (r["segments"], r["sizes"], r["requests"], r["partial"]) == (1, [24], 0, 1)
    assert r["after_last_data"] == 0                     # new client bytes came later on the same connection
    _conn_pcap(tmp_path / "u.pcap", [(0, c, s, 0, 0x02, 0), (1, c, s, 1, 0x18, 300), (2, s, c, 1, 0x18, 500),
                                      (3, s, c, 501, 0x18, 24), (4, s, c, 501, 0x18, 24)])
    assert trace_retransmissions(tmp_path / "u.pcap", {s})["after_last_data"] == 1


def test_retransmissions_by_class_tests():
    from scripts.compare_d1_dedup import by_class
    rows = [{"workflow": w, "segments": n} for w, ns in (("a", [0, 0, 1, 2] * 5), ("b", [0, 1, 0, 1] * 5)) for n in ns]
    d = by_class(rows, "workflow")
    assert d["classes"]["a"] == {"traces": 20, "traces_with_retransmissions": 10, "segments": 15, "per_trace_mean": 0.75}
    assert 0 <= d["chi_square_traces_with_any"]["p"] <= 1 and d["kruskal_per_trace"]["p"] > 0.05
    assert by_class([{"workflow": "a", "segments": 0}, {"workflow": "b", "segments": 0}], "workflow")["kruskal_per_trace"] is None


def test_same_folds_identical_features_give_zero():
    import numpy as np
    from scripts.compare_d1_dedup import same_folds
    rng = np.random.default_rng(0)
    y = np.array(["a", "b"] * 30)
    g = np.array([f"g{i}" for i in range(60)])
    X = rng.normal(size=(60, 8)) + (y == "a")[:, None] * 0.8
    r = same_folds(X, X.copy(), y, g, "workflow")
    assert r["predictions_differ"] == 0 and r["new_minus_old"]["diff"] == 0.0
    assert r["new_minus_old"]["ci_lo"] == 0.0 == r["new_minus_old"]["ci_hi"] and not r["new_minus_old"]["significant"]
    assert r["old"]["macro_f1"] == r["new"]["macro_f1"] and r["n"] == 60
