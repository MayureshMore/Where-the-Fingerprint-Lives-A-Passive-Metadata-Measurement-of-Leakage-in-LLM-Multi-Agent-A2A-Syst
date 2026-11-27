"""scripts/c2b2_results.py: C2B2's registered results in the paper's order, read from the analysis's outputs."""

import json

import pytest

from scripts import c2b2_results as cr


def _attr(verdict, f1, lo, hi, p):
    return {"verdict": verdict, "macro_f1": f1, "ci": [lo, hi], "p": p, "n": 500, "classes": ["a", "b"]}


def _audits(control="LEAK", treatment="INCONCLUSIVE"):
    runs = {}
    for arm in (cr.CONTROL, cr.TREATMENT):
        for part in ("pair", "all", "escalated_only"):
            for fs in ("all", "timing"):
                v = (control if arm == cr.CONTROL else treatment) if (part, fs) == ("pair", "timing") else "LEAK"
                runs[cr.run_name(arm, part, fs)] = {"report": f"r/{arm}/{part}/{fs}",
                                                    "attributes": {"task_type": _attr(v, 0.6, 0.55, 0.65, 0.01)}}
    return {"git_commit": "abc", "runs": runs}


def _manip(valid=True):
    ok = {"ok": True}
    return {"valid": valid, "checks": {
        "netem_pi": {**ok, "netem_packets": 9000, "captured_pi_to_cloud_packets": 8000},
        "netem_capture": {**ok, "difference_ms": 3.9, "expected_ms": 4.01},
        "reorder": {**ok, "file": "x.json"},
        "jitter_log": {**ok, "draws": 300000, "mean_ms": 4.01, "sd_ms": 1.79, "expected": {"mean_ms": 4.008, "sd_ms": 1.779}},
        "load_windows": ok, "gpu": ok, "keeper": {"ok": valid},
        "load_slowdown": {**ok, "per_task_type": {"fault_diagnosis": {"ratio": 1.6}, "procedure_lookup": {"ratio": 1.5},
                                                  "sensor_analysis": {"ratio": 1.9}}}}}


REORDER = {"margin": 0.005, "ok": True, "control": {"pi_to_cloud": {"reordered_share": 0.02}},
           "dirs": [{"pi_to_cloud": {"reordered_share": 0.013}}]}


def test_the_primary_is_read_only_when_the_control_leaks_and_the_session_is_valid():
    r = cr.results(_audits(), _manip(), REORDER)
    assert r["primary"]["control_requirement"]["met"] and r["primary"]["reading"] == cr.READING["INCONCLUSIVE"]
    assert r["primary"]["treatment"]["run"] == "c2b2_lan_padmax_jl_v2_pair_timing"
    assert r["primary"]["control"]["run"] == "c2b2_lan_padmax_v2_pair_timing"
    assert cr.results(_audits(treatment="LEAK"), _manip(), REORDER)["primary"]["reading"] == cr.READING["LEAK"]
    r = cr.results(_audits(control="INCONCLUSIVE"), _manip(), REORDER)
    assert not r["primary"]["control_requirement"]["met"] and "not read" in r["primary"]["reading"]
    r = cr.results(_audits(treatment="LEAK"), _manip(valid=False), REORDER)
    assert r["manipulation"]["verdict"] == "INVALID" and r["manipulation"]["failed"] == ["keeper"]
    assert "invalid" in r["primary"]["reading"]


def test_the_numbers_and_the_secondaries_come_from_the_inputs():
    r = cr.results(_audits(), _manip(), REORDER)
    m = r["manipulation"]
    assert m["jitter"]["mean_ms"] == 4.01 and m["slowdown"] == {"fault_diagnosis": 1.6, "procedure_lookup": 1.5,
                                                                 "sensor_analysis": 1.9}
    assert m["reorder"]["treatment_share"] == 0.013 and m["netem"]["ack_later_ms"] == 3.9 and m["keeper"]
    assert set(r["secondary"]) == {"pair_all_v2", "all_all_v2"}
    assert r["secondary"]["all_all_v2"][cr.CONTROL]["run"] == "c2b2_lan_padmax_v2"
    assert [d["commits"] for d in r["deviations"]] == [["6d228a42", "fc103506"], ["01230d36"]]
    assert cr.results(_audits(), _manip(), None)["manipulation"]["reorder"] is None


def test_the_markdown_keeps_the_paper_s_order_and_the_deviations(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps(_audits()))
    m = _manip()
    m["checks"]["reorder"]["file"] = str(tmp_path / "ro.json")
    (tmp_path / "ro.json").write_text(json.dumps(REORDER))
    (tmp_path / "m.json").write_text(json.dumps(m))
    out = tmp_path / "res"
    assert cr.main(["--audits", str(tmp_path / "a.json"), "--manipulation", str(tmp_path / "m.json"),
                    "--out", str(out), "--allow-dirty"]) == 0
    md = out.with_suffix(".md").read_text()
    i1, i2, i3, i4 = (md.index(s) for s in ("1. **Primary**", "2. **Manipulation checks: VALID**",
                                             "3. **All features at V2**", "## Deviations from the pre-registration"))
    assert i1 < i2 < i3 < i4 and "1.30% against the control's 2.00%" in md and "01230d36" in md
    assert json.loads(out.with_suffix(".json").read_text())["analysis_commit"] == "abc"
    with pytest.raises(SystemExit, match="never written over"):
        cr.main(["--audits", str(tmp_path / "a.json"), "--manipulation", str(tmp_path / "m.json"),
                 "--out", str(out), "--allow-dirty"])
