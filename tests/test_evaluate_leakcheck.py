"""scripts/evaluate_leakcheck.py on C2-like data: observer views, sidecar attributes, the reference
"the full-data attack", the tool's reports read instead of rerun, and a run split by arm and
merged, which must give what one run gives. Synthetic edge-cloud captures (tests/test_edge_cloud.py)."""

import json
import subprocess

import numpy as np
import pytest

import scripts.evaluate_leakcheck as ev
from a2a_leakcheck.analyze import INCONCLUSIVE, LEAK, NO_LEAK
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


def _cell(verdicts: dict, permuted=(NO_LEAK,)) -> dict:
    return {"full": {m: {"verdict": v} for m, v in verdicts.items()},
            "permuted": {m: list(permuted) for m in ev.METHODS},
            "sample_size": {"20": {"real": {LEAK: 1, INCONCLUSIVE: 0, NO_LEAK: 0}, "agreement_with_full": 1.0,
                                   "permuted": {LEAK: 0, INCONCLUSIVE: 1, NO_LEAK: 0}}}}


def test_reference_the_full_data_attack():
    arms = {"pad_v2": {"arm": "pad", "attributes": {
        "task_type": _cell({"leakcheck": INCONCLUSIVE, "kfp_rf": LEAK, "first_request": NO_LEAK}),
        "cloud_role": _cell({m: INCONCLUSIVE for m in ev.METHODS}),
        "escalated": _cell({m: LEAK for m in ev.METHODS}),
        "audit_null": _cell({m: NO_LEAK for m in ev.METHODS})}}}
    st = ev.reference(arms, set(), "full-attack")
    assert st == {("pad_v2", "task_type"): "leak", ("pad_v2", "cloud_role"): "no attack",
                  ("pad_v2", "escalated"): "leak", ("pad_v2", "audit_null"): "null"}
    s = ev.summarize(arms, set(), [20], "full-attack")["full_data"]
    assert s["leakcheck"]["known_leaks"] == 2 and s["leakcheck"]["recall"] == 0.5     # misses what k-FP finds
    assert s["kfp_rf"]["recall"] == 1.0 and s["first_request"]["no_leak_on_leaks"] == 1
    assert s["leakcheck"]["known_non_leaks"] == 1 + 4                                 # audit_null + 4 permuted sets
    lab = ev.summarize(arms, set(), [20])["full_data"]["leakcheck"]                 # every real label a leak
    assert lab["known_leaks"] == 3
    assert ev.reference(arms, {("pad", "task_type")}, "labels")["pad_v2", "task_type"] == "not known"   # by arm
    assert ev.reference(arms, {("pad_v2", "task_type")}, "labels")["pad_v2", "task_type"] == "not known"  # by cell


def _run(args, results, monkeypatch, name):
    monkeypatch.setattr(ev, "RESULTS", results)
    monkeypatch.setattr(ev, "_git", lambda: dict(CLEAN))
    ev.main(ev.parser().parse_args([*args, "--name", name]))
    return json.loads((results / f"{name}.json").read_text())


def test_split_run_merges_to_the_single_run(edge, tmp_path, monkeypatch):
    common = ["--collection-id", "C2", "--attributes", "escalated,audit_null", "--vantage", "v2",
              "--reference", "full-attack", *TINY]
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
    md = (tmp_path / "merged.md").read_text()
    assert "2 parallel parts" in md and "full-data attack finds a leak" in md
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
