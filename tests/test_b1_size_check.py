"""scripts/b1_size_check.py's draws, task subsets and summary on small inputs (no model is run)."""

import numpy as np
import pytest

from scripts.b1_size_check import b1_values, draw_ids, main, summary, task_index

TYPES = ("alert_triage", "fault_diagnosis", "procedure_lookup", "sensor_analysis")


def _cell(per_type=20, repeat=2):
    tt = np.array([t for t in TYPES for _ in range(per_type)])
    g = np.array([f"{t}-{i // repeat}" for t in TYPES for i in range(per_type)])     # prompts used twice
    return {"ids": [f"run{i:03d}" for i in range(len(tt))], "labels": {"task_type": tt}, "g": g}


def test_task_index_picks_the_pair_and_the_escalated_types():
    tt = np.array(["alert_triage", "fault_diagnosis", "procedure_lookup", "sensor_analysis"])
    assert task_index(tt, "pair").tolist() == [1, 3]
    assert task_index(tt, "escalated_only").tolist() == [1, 2, 3]
    assert task_index(tt, "task_type").tolist() == [0, 1, 2, 3]


def test_a_draw_takes_n_per_type_by_prompt_group_and_is_the_same_for_the_same_index():
    d = _cell()
    ids = draw_ids(d, 6, 0)
    pos = {r: j for j, r in enumerate(d["ids"])}
    tt = d["labels"]["task_type"][[pos[r] for r in ids]]
    assert {t: int((tt == t).sum()) for t in TYPES} == {t: 6 for t in TYPES}
    groups = d["g"][[pos[r] for r in ids]]
    assert all((groups == x).sum() == 2 for x in set(groups.tolist()))     # whole groups (6 per type is 3 groups of 2)
    assert draw_ids(d, 6, 0) == ids and draw_ids(d, 6, 1) != ids


def test_summary_places_b1_among_the_draws():
    rows = [{"macro_f1": f, "ci": [f - 0.03, f + 0.03], "verdict": "LEAK", "seconds": 1.0} for f in (0.60, 0.65, 0.70)]
    s = summary(rows, 0.62)
    assert s["macro_f1_median"] == pytest.approx(0.65) and s["macro_f1_min"] == pytest.approx(0.60)
    assert s["b1_draws_below"] == 1 and s["b1_in_range"] and s["b1_minus_median"] == pytest.approx(-0.03)
    assert not summary(rows, 0.80)["b1_in_range"]


def test_b1_values_come_from_the_committed_b1_audits():
    b = b1_values()
    assert b["collection_id"] == ["C2B1"]
    assert b["values"]["pair_v1"]["run"] == "c2b1_lan_padmax_v1_pair"
    assert b["values"]["task_type_v2"]["n"] == 500 and b["values"]["escalated_only_v1"]["n"] == 375


def test_results_are_never_written_over(tmp_path):
    (tmp_path / "size.md").write_text("")
    with pytest.raises(SystemExit, match="not written over"):
        main(["--out", str(tmp_path / "size"), "--allow-dirty"])
