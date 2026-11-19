"""scripts/paper2_review.py: the accounting of known leaks and non-leaks, the release-blocking rate,
the reuse check and the input-size comparison, on small inputs (no model is run)."""

import argparse

import numpy as np

from scripts.evaluate_leakcheck import input_size
from scripts.paper2_review import accounting, input_size_review, reuse_check

METHODS = {"leakcheck": "", "kfp_rf": "", "first_request": ""}


def _attr(full, permuted):
    return {"full": {m: {"verdict": full[m]} for m in METHODS}, "permuted": {m: permuted[m] for m in METHODS}}


def _eval():
    no, inc, leak = "NO LEAK", "INCONCLUSIVE", "LEAK"
    all_leak = {m: leak for m in METHODS}
    quiet = {m: [no] * 3 for m in METHODS}
    arms, cells = {}, []
    for cell in ("a_v1", "a_v2"):
        perm_x = {m: [no] * 3 for m in METHODS}
        if cell == "a_v2":                       # draw 1 of x and draw 1 of y: one audit, counted once
            perm_x["kfp_rf"] = [no, leak, no]
        perm_y = {m: [no] * 3 for m in METHODS}
        if cell == "a_v2":
            perm_y["kfp_rf"] = [no, leak, inc]
        arms[cell] = {"arm": "a", "vantage": cell[-2:], "attributes": {
            "x": _attr(all_leak, perm_x),
            "y": _attr({"leakcheck": leak, "kfp_rf": leak, "first_request": no}, perm_y),
            "audit_null": _attr({"leakcheck": inc, "kfp_rf": no, "first_request": no}, quiet)}}
        cells += [[cell, "x", "leak", ["kfp_rf", "first_request"]], [cell, "y", "leak", ["by construction", "kfp_rf"]],
                  [cell, "audit_null", "null", []]]
    return {"methods": METHODS, "arms": arms, "reference": {"cells": cells}}


def test_accounting_counts_every_known_leak_and_non_leak():
    acc = accounting(_eval())
    pos, neg = acc["positive_totals"], acc["negative_totals"]
    assert pos["all"]["leakcheck"] == {"LEAK": 4, "INCONCLUSIVE": 0, "NO LEAK": 0}
    assert pos["by construction"]["first_request"] == {"LEAK": 0, "INCONCLUSIVE": 0, "NO LEAK": 2}
    assert pos["baseline only"]["kfp_rf"]["LEAK"] == 2
    # 2 cells x 3 attributes x 3 draws permuted, plus the 2 audit_null cells
    assert sum(neg["permuted"]["leakcheck"].values()) == 18 and sum(neg["all"]["leakcheck"].values()) == 20
    assert neg["audit_null"]["leakcheck"] == {"LEAK": 0, "INCONCLUSIVE": 2, "NO LEAK": 0}
    assert neg["permuted"]["kfp_rf"]["LEAK"] == 2
    assert len(acc["positives"]) == 4


def test_release_blocking_lines_up_draws_by_index():
    rb = accounting(_eval())["release_blocking"]["methods"]
    k = rb["kfp_rf"]
    assert k["audits"] == 6                       # 2 cells x 3 draw indices
    assert k["any_leak"] == 1                     # a_v2 draw 1: two attributes LEAK, one audit
    assert k["inconclusive_no_leak"] == 1         # a_v2 draw 2: y INCONCLUSIVE, nothing LEAK
    assert k["all_no_leak"] == 4
    assert rb["leakcheck"]["any_leak"] == 0 and rb["leakcheck"]["any_leak_ci"][0] == 0


def test_reuse_check_finds_no_shared_labelling():
    y = np.array(["a"] * 30 + ["b"] * 30)
    r = reuse_check(y, ai=4, label_perms=5, permutations=9)
    assert r["labellings"] == 6 * 9 + 5 + 1
    assert r["distinct_labellings"] == r["labellings"]
    assert r["draw_equal_to_a_shuffle_in_any_test"] == 0 and r["draw_equal_to_real_labels"] == 0


def test_input_size_constant_overhead_beats_no_traffic_and_reproduces_stored():
    rng = np.random.default_rng(0)
    n = 120
    cls = np.array(["p", "q", "r"] * (n // 3))
    true = rng.integers(50, 5000, n).astype(float)
    d = {"fr": true + 296.0, "input": true, "cls": cls, "g": np.array([f"g{i}" for i in range(n)]),
         "link": np.array(["diagnostics"] * n), "traces": "escalated=yes", "class_attribute": "task_type"}
    stored = input_size(d)
    r = input_size_review(d, stored, [f"t{i}" for i in range(n)], argparse.Namespace(n_boot=200))
    assert r["reproduces_stored_errors"]
    assert r["errors"]["constant"]["overall"]["median_abs_error"] == 0
    gap = r["constant_minus_no_traffic"]["overall"]["median_abs_error"]
    assert gap["diff"] < 0 and gap["ci_hi"] < 0
    assert set(r["constant_minus_no_traffic"]["per_class"]) == {"p", "q", "r"}
    assert r["first_request_sizes"]["counts"] is None          # more than 10 distinct sizes
