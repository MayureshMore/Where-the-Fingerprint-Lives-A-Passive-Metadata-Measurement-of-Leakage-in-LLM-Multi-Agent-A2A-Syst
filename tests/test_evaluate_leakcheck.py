"""scripts/evaluate_leakcheck.py on C2-like data: observer views, sidecar attributes, the reference
"the full-data attack", the tool's reports read instead of rerun, and a run split by arm and
merged, which must give what one run gives. Synthetic edge-cloud captures (tests/test_edge_cloud.py)."""

import json
import subprocess

import numpy as np
import pytest

import scripts.evaluate_leakcheck as ev
from a2a_leakcheck.analyze import INCONCLUSIVE, LEAK, NO_LEAK
VERDICTS = (LEAK, INCONCLUSIVE, NO_LEAK)
from a2a_leakcheck.cli import main as leakcheck
from tests.test_edge_cloud import make_edge_dataset

# 19 permutations: p can reach 0.05, so a LEAK is possible at alpha 0.05
TINY = ["--sizes", "20", "--subsamples", "1", "--label-perms", "1", "--permutations", "19", "--n-boot", "50",
        "--min-per-class", "10", "--jobs", "2"]
CLEAN = {"git_commit": "c0ffee" * 6 + "c0ff", "git_dirty": False}


@pytest.fixture(scope="module")
def edge(tmp_path_factory):
    d = make_edge_dataset(tmp_path_factory.mktemp("edge"), per_type=20)
    rng = np.random.default_rng(3)
    for side in sorted(d.glob("*.json")):                 # audit_null: drawn per prompt group, as in C2
        sc = json.loads(side.read_text())
        sc["audit_null"] = str(rng.choice(["a", "b"]))
        side.write_text(json.dumps(sc))
    return d


def test_random_streams_of_the_tls_control_are_unchanged():
    assert [ev.attr_index(x, []) for x in ("role", "workflow", "topology", "audit_null")] == [0, 1, 2, 3]
    assert ev.attr_index("role_within_star", ["star"]) == 10
    assert len({ev.attr_index(x, []) for x in ev.STREAMS}) == len(ev.STREAMS)
    with pytest.raises(SystemExit):
        ev.attr_index("colour", [])


def test_views_and_sidecar_attributes(edge):
    d2 = ev.load_arm(edge, (), ["task_type", "escalated", "cloud_role", "audit_null"], "v2")
    assert d2["traces"] == 80 and d2["empty_traces"] == 20                        # every alert_triage
    assert set(d2["samples"]) == {"task_type", "escalated", "cloud_role", "audit_null"}
    esc = d2["samples"]["escalated"]
    empty = esc["y"] == "no"
    for m in ev.METHODS:                                   # nothing in view: zero leakcheck features, zero size
        assert esc["X"][m].shape[0] == 80
    assert not esc["X"]["leakcheck"][empty].any() and not esc["X"]["first_request"][empty].any()
    assert len(d2["samples"]["cloud_role"]["y"]) == 60                            # escalated tasks only
    d1 = ev.load_arm(edge, (), ["escalated"], "v1")
    assert d1["empty_traces"] == 0 and set(d1["samples"]) == {"escalated", "audit_null"}
    for m in ("leakcheck", "kfp_rf"):                     # at v1 the ticket post of every task is in view
        assert d1["samples"]["escalated"]["X"][m].any(axis=1).all()


def _cell(verdicts: dict, permuted=(NO_LEAK,), real=(1, 0, 0), top=None) -> dict:
    full = {m: {"verdict": v} for m, v in verdicts.items()}
    if top:
        full["leakcheck"].update({"carried_by": top, "attribution": {
            "top_family": top, "top_family_matches_all": True, "single_request_size": None,
            "families": {top: {"macro_f1": 0.9, "ci": [0.85, 0.95], "dims": 30, "matches_all": True}}}})
    return {"full": full, "permuted": {m: list(permuted) for m in ev.METHODS},
            "sample_size": {"20": {"real": dict(zip((LEAK, INCONCLUSIVE, NO_LEAK), real)), "agreement_with_full": 1.0,
                                   "permuted": {LEAK: 0, INCONCLUSIVE: 1, NO_LEAK: 0}}}}


def test_reference_by_construction_and_the_baselines():
    arms = {"pad_v2": {"arm": "pad", "attributes": {
        "task_type": _cell({"leakcheck": INCONCLUSIVE, "kfp_rf": LEAK, "first_request": NO_LEAK}, real=(0, 1, 0)),
        "cloud_role": _cell({"leakcheck": LEAK, "kfp_rf": INCONCLUSIVE, "first_request": NO_LEAK}, top="sizes"),
        "escalated": _cell({"leakcheck": NO_LEAK, "kfp_rf": NO_LEAK, "first_request": NO_LEAK}, real=(1, 1, 2)),
        "workflow": _cell({"leakcheck": LEAK, "kfp_rf": NO_LEAK, "first_request": INCONCLUSIVE}, top="timing"),
        "audit_null": _cell({m: NO_LEAK for m in ev.METHODS}, real=(0, 0, 1))}}}
    bc = ["escalated", "cloud_role"]
    st = ev.reference(arms, set(), "baselines", bc)
    assert st == {("pad_v2", "task_type"): "leak", ("pad_v2", "cloud_role"): "leak", ("pad_v2", "escalated"): "leak",
                  ("pad_v2", "workflow"): "no baseline", ("pad_v2", "audit_null"): "null"}
    assert ev.leak_basis("task_type", arms["pad_v2"]["attributes"]["task_type"], bc) == ["kfp_rf"]
    assert ev.leak_basis("cloud_role", arms["pad_v2"]["attributes"]["cloud_role"], bc) == ["by construction"]
    s = ev.summarize(arms, set(), [20], "baselines", bc)["full_data"]
    # a2a-leakcheck's LEAK on workflow is not counted: no baseline and no construction stands behind it
    assert s["leakcheck"]["known_leaks"] == 3 and s["leakcheck"]["true_positives"] == 1
    assert s["leakcheck"]["no_leak_on_leaks"] == 1 and s["kfp_rf"]["recall"] == pytest.approx(1 / 3)
    assert s["leakcheck"]["known_non_leaks"] == 1 + 5                                 # audit_null + 5 permuted sets
    b = ev.baseline_summary(arms, [20], bc)
    assert b["beyond_baselines"] == [{"cell": "pad_v2", "attribute": "cloud_role", "by_construction": True},
                                     {"cell": "pad_v2", "attribute": "workflow", "by_construction": False}]
    assert [(c["attribute"], c["carried_by"]) for c in b["carried_by"]] == \
           [("task_type", None), ("cloud_role", "sizes"), ("workflow", "timing")]
    cov = b["coverage"]["20"]                       # draws matching the tool's own full-data verdict
    assert (cov["all"]["agree"], cov["all"]["draws"]) == (1 + 1 + 2 + 1 + 1, 1 + 1 + 4 + 1 + 1)
    assert (cov["leak"]["agree"], cov["leak"]["draws"]) == (2, 2)
    assert (cov["other"]["agree"], cov["other"]["draws"]) == (4, 6)
    lab = ev.summarize(arms, set(), [20])["full_data"]["leakcheck"]                 # every real label a leak
    assert lab["known_leaks"] == 4
    assert ev.reference(arms, {("pad", "task_type")}, "labels")["pad_v2", "task_type"] == "not known"   # by arm
    assert ev.reference(arms, {("pad_v2", "task_type")}, "labels")["pad_v2", "task_type"] == "not known"  # by cell


def test_pair_and_input_size_at_both_views(edge):
    a = ev.parser().parse_args(["--pair", "task_type:sensor_analysis,fault_diagnosis", *TINY])
    sev = ev.load_rules(None)["severity"]
    arms = {}
    for v in ("v1", "v2"):
        data = ev.load_arm(edge, (), ["task_type", "escalated"], v, "escalated=yes")
        size = ev.input_size(data["input_size"])
        assert size["n"] == 60 and size["class_attribute"] == "task_type"
        # the agent each first request went to; the ticket service is out of view at v2 (in these synthetic
        # captures every TCP sequence number is 0, so at v1 some first requests land on the ticket link)
        assert set(size["first_request_link"]) <= {"diagnostics", "knowledge", "none"} | ({"ticket"} if v == "v1" else set())
        pair = ev.pair_verdicts(data, a.pair, a, sev)
        assert pair["classes"] == {"sensor_analysis": 20, "fault_diagnosis": 20}
        assert pair["dims"] == {"all": 195, "timing": 30} and pair["all"]["verdict"] in VERDICTS
        arms[f"a_{v}"] = {"arm": "a", "vantage": v, "pair": pair, "input_size": size, "attributes": {}}
    out = {"summary": ev.extras_summary(arms), "arms": arms}
    assert set(out["summary"]) == {"pair", "input_size"}
    md = "\n".join(ev.md_extras(out))
    assert "## task_type: sensor_analysis vs fault_diagnosis" in md and "| a_v2 | 20 / 20 |" in md
    same = arms["a_v1"]["input_size"]["estimators"] == arms["a_v2"]["input_size"]["estimators"]
    assert ("The views give identical estimates on a" in md) == same
    with pytest.raises(SystemExit):
        ev.parse_pair("task_type:sensor_analysis")


def test_input_size_estimators():
    rng = np.random.default_rng(0)
    cls = np.array(["a", "b"] * 50)
    true = np.where(cls == "a", 300.0, 3000.0) + rng.integers(0, 200, 100)
    g = np.array([f"g{i}" for i in range(100)])
    d = {"traces": "escalated=yes", "class_attribute": "task_type", "g": g, "cls": cls,
         "link": np.array(["diagnostics"] * 100)}
    r = ev.input_size({**d, "fr": true + 500, "input": true})            # unpadded: a fixed overhead
    e = r["estimators"]
    assert e["constant"]["overall"]["median_abs_error"] == 0 and e["linear"]["overall"]["mae"] < 1e-6
    assert e["no_traffic"]["overall"]["median_abs_error"] > 1000
    assert r["first_request_link"] == {"diagnostics": 100} and r["folds"] == 5
    p = ev.input_size({**d, "fr": np.full(100, 8192.0), "input": true})  # padded to one bucket
    assert p["first_request_bytes"]["distinct"] == 1
    assert p["estimators"]["constant"]["overall"]["median_abs_error"] > 1000
    assert p["estimators"]["per_class_constant"]["overall"]["median_abs_error"] < 200   # knows the class
    assert ev.prompt_json_bytes('a "b"\nc') == len('a \\"b\\"\\nc')


def _run(args, results, monkeypatch, name):
    monkeypatch.setattr(ev, "RESULTS", results)
    monkeypatch.setattr(ev, "_git", lambda: dict(CLEAN))
    ev.main(ev.parser().parse_args([*args, "--name", name]))
    return json.loads((results / f"{name}.json").read_text())


def test_split_run_merges_to_the_single_run(edge, tmp_path, monkeypatch):
    common = ["--collection-id", "C2", "--attributes", "escalated,audit_null", "--vantage", "v2",
              "--reference", "baselines", "--by-construction", "escalated", "--input-size", "escalated=yes", *TINY]
    one = _run([*common, "--arm", f"a={edge}", "--arm", f"b={edge}"], tmp_path, monkeypatch, "one")
    _run([*common, "--arm", f"a={edge}"], tmp_path, monkeypatch, "part_a")
    _run([*common, "--arm", f"b={edge}"], tmp_path, monkeypatch, "part_b")
    both = _run(["--merge", str(tmp_path / "part_a.json"), str(tmp_path / "part_b.json")], tmp_path, monkeypatch,
                "merged")
    assert list(both["arms"]) == list(one["arms"]) == ["a_v2", "b_v2"]
    assert both["summary"] == one["summary"] and both["reference"] == one["reference"]
    for c in one["arms"]:
        for attr, r in one["arms"][c]["attributes"].items():
            m = both["arms"][c]["attributes"][attr]
            assert {k: m[k] for k in ("full", "permuted", "sample_size")} == \
                   {k: r[k] for k in ("full", "permuted", "sample_size")}
    assert one["arms"]["a_v2"]["empty_traces"] == 20 and one["arms"]["a_v2"]["vantage"] == "v2"
    assert one["arms"]["a_v2"]["attributes"]["escalated"]["full"]["leakcheck"]["verdict"] == LEAK
    assert [c[2] for c in one["reference"]["cells"] if c[1] == "audit_null"] == ["null", "null"]
    assert ["by construction"] == [c[3] for c in one["reference"]["cells"] if c[1] == "escalated"][0][:1]
    assert one["arms"]["a_v2"]["input_size"]["n"] == 60                            # escalated tasks
    assert set(one["summary"]) >= {"coverage", "beyond_baselines", "carried_by", "input_size"}
    assert all("agreement_with_full_mean" not in r for r in one["summary"]["sample_size"].values())
    md = (tmp_path / "merged.md").read_text()
    assert "2 parallel parts" in md and "## Coverage" in md and "## Beyond the baselines" in md
    assert "## Input size from the first request" in md
    with pytest.raises(SystemExit):                       # the same cells twice
        _run(["--merge", str(tmp_path / "part_a.json"), str(tmp_path / "part_a.json")], tmp_path, monkeypatch, "x")
    (tmp_path / "part_c.json").write_text(json.dumps({**json.loads((tmp_path / "part_b.json").read_text()),
                                                      "git_commit": "0" * 40}))
    with pytest.raises(SystemExit):                       # another commit
        _run(["--merge", str(tmp_path / "part_a.json"), str(tmp_path / "part_c.json")], tmp_path, monkeypatch, "y")


def test_tool_reports_must_stand_for_the_run(edge, tmp_path):
    rep_dir = tmp_path / "c2_a_v2"
    assert leakcheck(["run", str(edge), "--out", str(rep_dir), "--strip", "--vantage", "v2",
                      "--attributes", "escalated,audit_null", "--permutations", "19", "--n-boot", "50",
                      "--min-per-class", "10", "--jobs", "2"]) == 0
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    rep = json.loads((rep_dir / "report.json").read_text())
    (rep_dir / "report.json").write_text(json.dumps({**rep, "git_commit": head, "git_dirty": False}))
    a = ev.parser().parse_args(["--attributes", "escalated,audit_null", "--vantage", "v2",
                                "--tool-reports", str(tmp_path / "c2_{cell}"), *TINY])
    attrs = ["escalated", "audit_null"]
    tool = ev.tool_report(rep_dir, edge, attrs, a, "v2")
    assert tool["attributes"]["escalated"]["verdict"] == LEAK and tool["report"].endswith("report.json")
    assert tool["runtime"]["total_s"] > 0
    for wrong in [dict(vantage="v1"), dict(raw=tmp_path), dict(attrs=["escalated"])]:
        with pytest.raises(SystemExit):
            ev.tool_report(rep_dir, wrong.get("raw", edge), wrong.get("attrs", attrs), a, wrong.get("vantage", "v2"))
    b = ev.parser().parse_args(["--attributes", "escalated,audit_null", "--vantage", "v2", *TINY])
    b.permutations = 39
    with pytest.raises(SystemExit):                       # another permutation count
        ev.tool_report(rep_dir, edge, attrs, b, "v2")
    (rep_dir / "report.json").write_text(json.dumps({**rep, "git_commit": head, "git_dirty": True}))
    with pytest.raises(SystemExit):                       # made from uncommitted code
        ev.tool_report(rep_dir, edge, attrs, a, "v2")
