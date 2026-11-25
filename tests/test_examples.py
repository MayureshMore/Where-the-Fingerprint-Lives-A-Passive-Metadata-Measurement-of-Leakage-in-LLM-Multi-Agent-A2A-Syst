"""The C2 examples audit to their expected reports, and the CI gate fires against the baseline.

Both audits together take under a minute on a laptop with all cores free (about 35 s with 14
workers). Set A2A_CHECK_TIME=1 to assert it; it is off by default because a busy machine is slower.
"""

import json
import os
import time
from pathlib import Path

import pytest

from a2a_leakcheck.cli import main as leakcheck
from scripts.compare_reports import compare

EX = Path(__file__).resolve().parent.parent / "examples"
SETS = [("c2_lan", "c2_lan_v2"), ("c2_lan_padmax", "c2_lan_padmax_v2")]

# The permutation test's null model (rf-light, a light random forest) fits slightly differently across
# platforms: on Linux x86_64 with the pinned requirements, c2_lan's task_type has null_mean 0.50328
# against 0.50380 in examples/expected (built on the Mac, arm64), with the same permutations, verdicts
# and p-value, as on the Pi in A6. The GBT model's numbers are identical. So null_mean is compared within
# NULL_TOL; every other field, p_value, null_max, null_verdicts and false_positive_rate included, exactly.
NULL_TOL = {"null_mean": 0.01}
pytestmark = pytest.mark.skipif(not all((EX / "expected" / e / "report.json").exists() for _, e in SETS),
                                reason="expected C2 example reports not built yet (scripts/make_c2_examples.py)")


def differences(report: dict, expected: dict) -> list[dict]:
    """compare_reports' differences, less the null model's fields within NULL_TOL."""
    out = []
    for d in compare(report, expected)["differences"]:
        path, _, key = d["field"].rpartition(".")
        tol = NULL_TOL.get(key) if path.endswith(".validation.permutation") else None
        if tol is not None and all(isinstance(x, (int, float)) for x in (d["a"], d["b"])) and abs(d["a"] - d["b"]) <= tol:
            continue
        out.append(d)
    return out


def test_only_the_null_mean_has_a_tolerance():
    exp = json.loads((EX / "expected" / "c2_lan_v2" / "report.json").read_text())
    perm = lambda r: r["attributes"]["task_type"]["validation"]["permutation"]  # noqa: E731

    def changed(key, delta):
        r = json.loads(json.dumps(exp))
        perm(r)[key] += delta
        return [d["field"].rsplit(".", 1)[-1] for d in differences(r, exp)]

    assert changed("null_mean", 0.50328 - 0.50380) == [] and changed("null_mean", -0.0099) == []
    assert changed("null_mean", 0.011) == ["null_mean"]
    assert changed("p_value", 0.01) == ["p_value"] and changed("null_max", 0.001) == ["null_max"]
    assert changed("false_positive_rate", 0.001) == ["false_positive_rate"]
    r = json.loads(json.dumps(exp))
    r["attributes"]["task_type"]["analysis"]["macro_f1"] += 0.001                # not the null model: exact
    assert [d["field"] for d in differences(r, exp)] == ["attributes.task_type.analysis.macro_f1"]


def test_c2_examples_give_their_expected_reports(tmp_path):
    t0 = time.perf_counter()
    for src, exp in SETS:
        out = tmp_path / exp
        assert leakcheck(["run", str(EX / src), "--vantage", "v2", "--attributes", "task_type",
                          "--label", f"example: {src}, view v2", "--out", str(out)]) == 0
        diffs = differences(json.loads((out / "report.json").read_text()),
                            json.loads((EX / "expected" / exp / "report.json").read_text()))
        assert not diffs, diffs[:5]
    elapsed = time.perf_counter() - t0
    print(f"both C2 examples audited in {elapsed:.0f} s")
    if os.environ.get("A2A_CHECK_TIME") == "1":
        assert elapsed < 60


def test_ci_gate_exits_3_on_the_new_leak():
    base = EX / "expected" / "c2_ci_baseline_v2" / "report.json"
    if not base.exists():
        pytest.skip("no CI baseline report")
    assert json.loads(base.read_text())["attributes"]["task_type"]["verdict"] != "LEAK"
    assert leakcheck(["diff", str(EX / "expected" / "c2_lan_v2" / "report.json"), str(base)]) == 3
