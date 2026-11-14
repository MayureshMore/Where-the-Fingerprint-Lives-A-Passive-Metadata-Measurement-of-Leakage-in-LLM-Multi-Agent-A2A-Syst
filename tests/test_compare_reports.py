"""scripts/compare_reports.py: same results, or which fields differ."""

import copy

from scripts.compare_reports import compare


def _report(f1=0.9, hint="pad-task-inputs", jobs=4, total=10.0):
    return {"git_commit": "abc", "runtime": {"total_s": total, "peak_rss_mb": 100.0},
            "parameters": {"jobs": jobs, "rules": "default", "seed": 42},
            "collection": {"folder": "x", "traces": 40}, "input": {"folder": "x", "vantage": "v2"},
            "summary": {"LEAK": ["task_type"]},
            "attributes": {"task_type": {"verdict": "LEAK", "analysis": {"macro_f1": f1},
                                         "validation": {"permutation": {"p_value": 0.01}},
                                         "mitigations": [{"id": hint, "hint": "..."}]}}}


def test_same_apart_from_runtime_jobs_and_paths():
    a, b = _report(), _report(jobs=14, total=99.0)
    b["collection"]["folder"] = b["input"]["folder"] = "elsewhere"
    c = compare(a, b)
    assert c["same"] and c["runtime"]["a"]["total_s"] == 10.0 and c["runtime"]["b"]["total_s"] == 99.0


def test_score_difference_and_tolerance():
    a, b = _report(f1=0.9), _report(f1=0.9 + 1e-12)
    assert not compare(a, b)["same"]
    assert compare(a, b, tol=1e-9)["same"]
    assert compare(a, b)["differences"][0]["field"] == "attributes.task_type.analysis.macro_f1"


def test_hints_counted_unless_ignored_and_always_listed():
    a, b = _report(hint="shape-timing"), _report()
    assert not compare(a, b)["same"]
    c = compare(a, b, ignore_hints=True)
    assert c["same"] and c["hints_changed"] == {"task_type": {"a": ["shape-timing"], "b": ["pad-task-inputs"]}}


def test_missing_attribute_is_a_difference():
    a, b = _report(), _report()
    b["attributes"]["escalated"] = copy.deepcopy(b["attributes"]["task_type"])
    assert [d["field"] for d in compare(a, b)["differences"]] == ["attributes.escalated"]
