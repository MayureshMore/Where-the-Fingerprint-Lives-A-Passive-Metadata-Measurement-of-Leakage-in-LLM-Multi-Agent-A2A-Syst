"""scripts/reproduce_paper2.sh fails loudly on a missing input, and scripts/compare_paper2_results.py compares
what the data decide (no audit is run here)."""

import json
import subprocess
from pathlib import Path

import pytest

from scripts.compare_paper2_results import compare, kind, main

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "reproduce_paper2.sh"


def _run(cwd, *args, env=None):
    return subprocess.run(["bash", str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True, timeout=60,
                          env={"PATH": "/usr/bin:/bin", **(env or {})})


def test_a_missing_input_stops_the_run_before_anything_runs(tmp_path):
    r = _run(tmp_path, "--section", "d3,b3")
    assert r.returncode == 2
    assert "FAIL: required inputs missing" in r.stderr and "PASS" not in r.stdout + r.stderr
    assert "data/raw_c2b1x_shaped   (from Zenodo version 1.1, c2b1x-raw-pcaps-headers-only.zip)" in r.stderr
    assert "data/raw_c2b3_lan   (from Zenodo version 1.1, c2b3-raw-pcaps-headers-only.zip)" in r.stderr
    assert not (tmp_path / "data" / "results_paper2_demo").exists() and not (tmp_path / "logs").exists()


def test_only_the_missing_inputs_are_listed(tmp_path):
    for d in ("raw_c2", "raw_c2_pad", "raw_c2_padmax", "raw_c2b1_padmax", "raw_c2b1_shaped", "results"):
        (tmp_path / "data" / d).mkdir(parents=True)
    (tmp_path / "data" / "results" / "b1_audits.json").write_text("{}")
    r = _run(tmp_path, "--section", "d3")
    assert r.returncode == 2
    listed = [x.split()[0] for x in r.stderr.splitlines() if x.startswith("  ")]
    assert listed == ["data/raw_c2b1x_shaped"]


def test_every_section_names_its_inputs(tmp_path):
    r = _run(tmp_path)                                   # all four sections
    assert r.returncode == 2
    for p in ("data/raw_tlspair_tls", "data/processed_tlspair_tls_own_dedup", "data/raw_c2", "data/raw_c2b1_shaped",
              "data/raw_c2b3_lan"):
        assert f"  {p}   (from Zenodo version 1." in r.stderr
    assert r.stderr.count("  data/raw_c2   ") == 1           # listed once though three sections need it


@pytest.mark.parametrize("args, env, msg", [
    (["--section", "d4"], None, "unknown section: d4"),
    (["--fast"], None, "unknown option: --fast"),
    (["--section", "d3"], {"A2A_RESULTS_DIR": "data/results/sub"}, "REFUSING"),
])
def test_bad_options_and_the_canonical_folder_are_refused(tmp_path, args, env, msg):
    r = _run(tmp_path, *args, env=env)
    assert r.returncode == 2 and msg in r.stderr


def test_run_details_and_paths_are_not_compared_but_every_number_is():
    old = {"git_commit": "a", "created": "x", "runtime_s": 3.0, "data_dir": {"train": "data/raw_c2"},
           "attributes": {"pair": {"transfer": {"macro_f1": 0.726, "ci": [0.66, 0.78], "null_mean": 0.503,
                                                "verdict": "LEAK"}, "folder": "data/features_b3_cross/c2_lan_v1",
                                   "seconds": 140.0}}}
    new = json.loads(json.dumps(old))
    new.update(git_commit="b", created="y", runtime_s=9.0)
    new["data_dir"]["train"] = "data/results_paper2_demo/20261125/x"
    new["attributes"]["pair"]["folder"] = "data/results_paper2_demo/20261125/features_b3_cross/c2_lan_v1"
    new["attributes"]["pair"]["seconds"] = 99.0
    new["attributes"]["pair"]["transfer"]["null_mean"] = 0.509          # the null model, across platforms
    assert compare(new, old) == []
    new["attributes"]["pair"]["transfer"]["macro_f1"] = 0.7261
    new["attributes"]["pair"]["transfer"]["verdict"] = "INCONCLUSIVE"
    assert [d[0] for d in compare(new, old)] == [".attributes.pair.transfer.macro_f1",
                                                 ".attributes.pair.transfer.verdict"]
    new["attributes"]["pair"]["transfer"].update(macro_f1=0.726, verdict="LEAK", null_mean=0.52)
    assert [d[0] for d in compare(new, old)] == [".attributes.pair.transfer.null_mean"]


def _report(version, timing_f1, perm_unit=True):
    return {"tool": "a2a-leakcheck", "version": version,
            "parameters": {"perm_unit": "group"} if perm_unit else {},
            "attributes": {"task_type": {"verdict": "NO LEAK", "analysis": {"macro_f1": 0.514, "ci_lo": 0.485, "ci_hi": 0.54},
                                         "validation": {"permutation": {"p_value": 0.26, "null_mean": 0.5}},
                                         "attribution": {"families": {"timing": {"macro_f1": timing_f1, "ci_lo": 0.51,
                                                                                 "ci_hi": 0.569, "matches_all": True}}}}}}


def test_reports_compare_the_families_from_0_3_0_on():
    old = _report("0.3.0", 0.539)
    assert kind(old) == "report" and compare(_report("0.3.0", 0.539), old) == []
    assert [d[0] for d in compare(_report("0.3.0", 0.538), old)] == ["attributes.task_type.families.timing.macro_f1"]
    legacy = _report("0.1.0", 0.539, perm_unit=False)          # 0.1.x's attribution rule: not compared
    assert compare(_report("0.3.0", 0.538), legacy) == []


def test_round2_parts_are_compared_section_by_section(tmp_path):
    merged = {"git_commit": "a", "sections": {"a3": {"x": 1}, "a4": {"y": 2}, "a8": {"z": 3}}}
    part = {"git_commit": "b", "sections": {"a3": {"x": 1}, "a8": {"z": 3}, "seconds": {"a3": 5}}}
    assert compare(part, merged, ["a3", "a8"]) == []
    assert compare(part, merged, ["a3", "a4"]) == [("sections.a4", None, {"y": 2})]
    (tmp_path / "p.json").write_text(json.dumps(part))
    (tmp_path / "m.json").write_text(json.dumps(merged))
    assert main([str(tmp_path / "p.json"), str(tmp_path / "m.json"), "--sections", "a3,a8"]) == 0
    assert main([str(tmp_path / "p.json"), str(tmp_path / "m.json")]) == 1


def test_b1_audits_takes_a_reports_folder(tmp_path):
    from scripts.b1_audits import main as audits
    (tmp_path / "caps").mkdir()
    (tmp_path / "r" / "x_lan_v1").mkdir(parents=True)                 # an earlier report: never written over
    with pytest.raises(SystemExit, match="not written over: .*r/x_lan_v1"):
        audits(["--arm", f"lan={tmp_path / 'caps'}", "--prefix", "x", "--views", "v1", "--parts", "all",
                "--reports", str(tmp_path / "r"), "--out", str(tmp_path / "s"), "--allow-dirty"])
