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
pytestmark = pytest.mark.skipif(not all((EX / "expected" / e / "report.json").exists() for _, e in SETS),
                                reason="expected C2 example reports not built yet (scripts/make_c2_examples.py)")


def test_c2_examples_give_their_expected_reports(tmp_path):
    t0 = time.perf_counter()
    for src, exp in SETS:
        out = tmp_path / exp
        assert leakcheck(["run", str(EX / src), "--vantage", "v2", "--attributes", "task_type",
                          "--label", f"example: {src}, view v2", "--out", str(out)]) == 0
        c = compare(json.loads((out / "report.json").read_text()),
                    json.loads((EX / "expected" / exp / "report.json").read_text()))
        assert c["same"], c["differences"][:5]
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
