"""scripts/b1_power.py's summary and 1/sqrt(n) prediction on small inputs (no model is run)."""

import pytest

from scripts.b1_power import main, predict, summary


def _row(f1, hi, verdict, ci_verdict, p=0.5):
    return {"macro_f1": f1, "ci": [2 * f1 - hi, hi], "verdict": verdict, "ci_verdict": ci_verdict, "p": p, "seconds": 1.0,
            "why": "-" if verdict != "INCONCLUSIVE" else "CI straddles the threshold"}


def test_summary_counts_verdicts_and_the_median_upper_bound():
    rows = [_row(0.50, 0.56, "INCONCLUSIVE", "INCONCLUSIVE"), _row(0.48, 0.54, "NO LEAK", "NO LEAK"),
            _row(0.49, 0.545, "INCONCLUSIVE", "NO LEAK", p=0.03)]
    s = summary(rows)
    assert s["verdicts"] == {"LEAK": 0, "INCONCLUSIVE": 2, "NO LEAK": 1}
    assert s["ci_verdicts"]["NO LEAK"] == 2 and s["p_under_0_05"] == 1
    assert s["ci_hi_median"] == pytest.approx(0.545) and s["threshold"] == pytest.approx(0.55)
    assert s["upper_half_width_median"] == pytest.approx(0.06)          # half-widths 0.06, 0.06, 0.055


def test_predict_shrinks_the_distance_from_chance_and_the_half_width_by_sqrt_n():
    rows = [_row(0.52, 0.58, "INCONCLUSIVE", "INCONCLUSIVE")]   # 0.02 above chance, half-width 0.06
    p = predict(rows, 250, 1000)                                  # scale 1/2
    assert p["scale"] == pytest.approx(0.5)
    assert p["ci_hi_median"] == pytest.approx(0.5 + 0.01 + 0.03)
    assert p["ci_no_leak"] == 1
    assert predict(rows, 250, 250)["ci_no_leak"] == 0


def test_results_are_never_written_over(tmp_path):
    (tmp_path / "power.json").write_text("{}")
    with pytest.raises(SystemExit, match="not written over"):
        main(["--out", str(tmp_path / "power"), "--allow-dirty"])
