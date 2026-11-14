"""Paper 2's helper scripts: the scanner summary, the CSV export, the on-wire count, the baselines."""

import csv
import struct
from pathlib import Path

import pytest

from baselines.summarize_tls_scanners import summarize
from scripts.c2_setup_numbers import wire_bytes
from scripts.export_paper2_csv import main as export_csv

ROOT = Path(__file__).resolve().parent.parent
SCANNERS = ROOT / "data" / "results" / "tls_scanners"


@pytest.mark.skipif(not (SCANNERS / "scanners.json").exists(), reason="no committed scanner output")
def test_scanner_summary_groups_identical_endpoints():
    s = summarize(SCANNERS)
    assert sum(len(g["endpoints"]) for g in s["groups"]) == 9
    g = s["groups"][0]
    assert "TLS 1.3" in g["sslyze"]["versions"] and g["testssl"]["grade"]
    assert s["traffic_metadata_checks"] == 0 and "\x1b" not in s["scanners"]["testssl"]


@pytest.mark.skipif(not (ROOT / "data" / "results" / "paper2_tool_eval.json").exists(), reason="no D1 evaluation")
def test_csv_export_from_committed_results(tmp_path):
    out = tmp_path / "csv"
    assert export_csv(["--results", str(ROOT / "data" / "results"), "--out", str(out)]) == 0
    rows = list(csv.DictReader((out / "sample_size_summary.csv").open()))
    assert [r["dataset"] for r in rows][:1] == ["D1"] and {r["n_per_class"] for r in rows} >= {"20", "50"}
    v = list(csv.DictReader((out / "verdicts.csv").open()))
    assert {r["method"] for r in v} == {"leakcheck", "kfp_rf", "first_request"}
    with pytest.raises(SystemExit):                          # never overwrites
        export_csv(["--results", str(ROOT / "data" / "results"), "--out", str(out)])


def test_wire_bytes_counts_only_the_view_endpoints(tmp_path):
    """Ethernet pcap: two segments to the cloud agent, one to the ticket service, one trigger to the edge."""
    out = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 96, 1)
    segs = [("10.0.0.171", 50000, "172.30.0.100", 8101, 1000), ("172.30.0.100", 8101, "10.0.0.171", 50000, 500),
            ("10.0.0.171", 50001, "10.0.0.228", 8105, 300), ("10.0.0.228", 50002, "10.0.0.171", 8100, 200)]
    for i, (s, sp, d, dp, length) in enumerate(segs):
        ip = struct.pack(">BBHHHBBH4s4s", 0x45, 0, length, 0, 0, 64, 6, 0,
                         bytes(map(int, s.split("."))), bytes(map(int, d.split("."))))
        tcp = struct.pack(">HHIIBBHHH", sp, dp, 0, 0, 5 << 4, 0x18, 0, 0, 0)
        frame = b"\x02" * 12 + b"\x08\x00" + ip + tcp
        out += struct.pack("<IIII", i, 0, len(frame), len(frame) + length - 40) + frame
    f = tmp_path / "t.pcap"
    f.write_bytes(out)
    assert wire_bytes(f, {("172.30.0.100", 8101)}) == (1500, 2)
    assert wire_bytes(f, {("172.30.0.100", 8101), ("10.0.0.228", 8105)}) == (1800, 3)


@pytest.mark.skipif(not (ROOT / "examples" / "c2_lan").exists(), reason="no C2 examples")
def test_baseline_detectors_run_on_the_c2_example():
    from baselines.run_detectors import main as detectors
    assert detectors([str(ROOT / "examples" / "c2_lan"), "--attributes", "task_type", "--vantage", "v2",
                      "--permutations", "0", "--n-boot", "50", "--jobs", "2"]) == 0
