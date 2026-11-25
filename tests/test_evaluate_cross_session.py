"""scripts/evaluate_cross_session.py's subsets, C2 reference and refusals (no model is run)."""

import pytest

from scripts.b1_audits import markdown as audits_markdown
from scripts.evaluate_cross_session import _row, main, reference, subsets


def test_subsets_take_the_pair_and_named_subsets_of_two_or_more_classes():
    s = subsets("task_type:sensor_analysis,fault_diagnosis",
                ["escalated_only=task_type:fault_diagnosis,procedure_lookup,sensor_analysis"])
    assert s == [("task_type:sensor_analysis,fault_diagnosis", "task_type", ["sensor_analysis", "fault_diagnosis"]),
                 ("escalated_only", "task_type", ["fault_diagnosis", "procedure_lookup", "sensor_analysis"])]
    with pytest.raises(SystemExit, match="NAME=ATTR"):
        subsets("", ["pair=task_type:sensor_analysis"])
    with pytest.raises(SystemExit, match="same name"):
        subsets("", ["x=task_type:a,b", "x=task_type:c,d"])


def test_the_reference_is_c2s_lan_cell_of_the_view_from_section_a7():
    r = reference("data/results/paper2_round2.json", "v2")
    assert set(r["tasks"]) == {"task_type", "escalated", "cloud_role", "audit_null", "pair", "escalated_only"}
    assert r["clean"] and r["data_dir"] == "data/raw_c2" and r["view"] == "v2"
    assert set(r["tasks"]["pair"]) >= {"verdict", "macro_f1", "ci", "p"}
    with pytest.raises(SystemExit, match="no lan_v9"):
        reference("data/results/paper2_round2.json", "v9")


def test_a_row_shows_the_transfer_the_test_side_and_c2():
    r = {"train": {"n": 500}, "test": {"n": 471, "dropped_shared": 29},
         "transfer": {"verdict": "LEAK", "macro_f1": 0.8, "ci": [0.75, 0.85], "p": 0.01},
         "within_test": {"verdict": "INCONCLUSIVE", "macro_f1": None, "ci": [None, None]}, "seconds": 3.0}
    ref = {"tasks": {"pair": {"verdict": "LEAK", "macro_f1": 0.93, "ci": [0.91, 0.95]}}}
    row = _row("pair", r, ref, table=True)
    assert "| pair | 500 | 471 (29) | 0.800 [0.750, 0.850] | 0.01 | LEAK | INCONCLUSIVE - [-, -] | LEAK 0.930 [0.910, 0.950] |" == row
    assert _row("audit_null", r, ref).endswith("C2 within - (3 s)")


def test_results_are_never_written_over(tmp_path):
    (tmp_path / "x.md").write_text("")
    with pytest.raises(SystemExit, match="not written over"):
        main(["--train", "a", "--test", "b", "--out", str(tmp_path / "x"), "--allow-dirty"])


def test_the_audits_summary_carries_its_title():
    r = {"title": "B3 audits", "collection_id": ["C2B3"], "git_commit": "abc", "git_dirty": False, "seed": 42,
         "parameters": {"tool_defaults": "defaults"}, "runs": {}}
    assert audits_markdown(r).startswith("# B3 audits (C2B3)")
    r.pop("title")                                   # the summaries written before --title
    assert audits_markdown(r).startswith("# B1 audits (C2B3)")
