"""scripts/paper2_round2.py and features/timestamps.py on small inputs (no model is run)."""

import numpy as np

from features.families import family_columns
from features.timestamps import FLOW_NAMES, N_FLOWS, names, timestamp_vector
from scripts.paper2_round2 import ATTRS, METHODS, accounting, carried, template_factors, timing_columns, why


def _packets(sizes=(100, 9000), directions=(1, -1)):
    """Two flows: A starts first and is small, B starts later and is heavy."""
    out = []
    for i, t in enumerate((0.0, 0.1, 0.25, 1.4)):
        out.append((10.0 + t, sizes[0], "A", directions[i % 2]))
    for i, t in enumerate((0.5, 0.52, 0.9)):
        out.append((10.0 + t, sizes[1], "B", directions[i % 2]))
    return out


def test_timestamps_only_orders_flows_by_start_and_ignores_size_and_direction():
    v = timestamp_vector(_packets())
    assert len(v) == len(names())
    w = len(FLOW_NAMES)
    assert v[0] == 0.0 and abs(v[1] - 1.4) < 1e-6                 # flow 1 is A (first to start), not B (heaviest)
    assert abs(v[w] - 0.5) < 1e-6 and abs(v[w + 1] - 0.4) < 1e-6  # flow 2: B starts 0.5 s in, lasts 0.4 s
    assert (v[2 * w:3 * w] == 0).all()                            # no third flow
    np.testing.assert_array_equal(v, timestamp_vector(_packets(sizes=(1500, 60), directions=(-1, 1))))
    assert (timestamp_vector([]) == 0).all() and N_FLOWS == 3


def test_timing_columns_name_what_depends_on_bytes_or_direction():
    cols = timing_columns()
    assert [c["column"] for c in cols] == family_columns("timing", False).tolist()
    assert sum(c["flow_chosen_by_bytes"] for c in cols) == 10           # 5 timing features x 2 heaviest-flow blocks
    assert {c["feature"] for c in cols if c["uses_direction"]} == {"mean_burst_dur", "mean_ibg", "mean_burst_rate"}


def test_template_factors_regenerate_the_prompts():
    from workflows import WORKFLOW_REGISTRY, WorkflowClass, prompt_seed
    meta = {"workflows": ["procedure_lookup", "fault_diagnosis", "alert_triage", "sensor_analysis"], "seed_offset": 30000, "n": 15}
    prompts = {}
    for w in meta["workflows"]:
        prompts[w] = WORKFLOW_REGISTRY[WorkflowClass(w)]().sample_prompts(n=15, seed=prompt_seed(0, w, 30000))
    f = template_factors(prompts, meta)
    assert all(f[w][p].startswith("template_") for p in prompts["procedure_lookup"] for w in ["procedure_lookup"])
    assert {f["alert_triage"][p].split("_")[0] for p in prompts["alert_triage"]} <= {"alarm", "request"}
    assert all(f["fault_diagnosis"][p] for p in prompts["fault_diagnosis"])


def test_why_names_where_an_inconclusive_comes_from():
    assert why({"verdict": "LEAK", "ci_verdict": "LEAK"}) == "-"
    assert why({"verdict": "INCONCLUSIVE", "ci_verdict": None}) == "too few samples"
    assert why({"verdict": "INCONCLUSIVE", "ci_verdict": "INCONCLUSIVE"}) == "CI straddles the threshold"
    assert why({"verdict": "INCONCLUSIVE", "ci_verdict": "NO LEAK"}) == "permutation test disagrees with a NO LEAK"


def test_carried_by_under_each_rule():
    fam = lambda lo, hi: {"all_minus_this": {"diff": (lo + hi) / 2, "ci_lo": lo, "ci_hi": hi}}  # noqa: E731
    at = {"top_family": "timing", "families": {"timing": fam(-0.010, 0.062)},
          "single_request_size": {"feature": "first_request_bytes", **fam(0.2, 0.3)}}
    assert carried(at, "no_detected_deficit") == "timing (alone matches all)"
    assert carried(at, "matches_all") == "timing"


def _res(v):
    return {"verdict": v}


def test_accounting_keeps_learned_rows_apart_from_structural_checks():
    def attr(full, perm):
        return {"full": {m: _res(full) for m in METHODS}, "permuted": {m: [_res(x) for x in perm] for m in METHODS}}
    cell = {"attributes": {"task_type": attr("LEAK", ["NO LEAK", "INCONCLUSIVE"]), "escalated": attr("LEAK", ["NO LEAK", "NO LEAK"]),
                           "cloud_role": attr("LEAK", ["NO LEAK", "NO LEAK"]), "audit_null": attr("NO LEAK", ["NO LEAK", "LEAK"])},
            "learned": {"pair": {"full": {m: _res("LEAK") for m in METHODS}},
                        "escalated_only": {"full": {m: _res("INCONCLUSIVE") for m in METHODS}}},
            "all_zero_windows": {"alert_triage": 250, "sensor_analysis": 0}}
    acc = accounting({"cells": {"lan_v2": cell, "lan_pad_v2": cell}})
    assert acc["learned"]["leakcheck"] == {"LEAK": 4, "INCONCLUSIVE": 2, "NO LEAK": 0}
    assert acc["structural"]["kfp_rf"] == {"LEAK": 4, "INCONCLUSIVE": 0, "NO LEAK": 0}
    assert acc["negatives"]["permuted"]["leakcheck"] == {"LEAK": 2, "INCONCLUSIVE": 2, "NO LEAK": 12}
    assert acc["negatives"]["audit_null"]["first_request"] == {"LEAK": 0, "INCONCLUSIVE": 0, "NO LEAK": 2}
    rb = acc["release_blocking"]["leakcheck"]
    assert rb["audits"] == 4 and rb["any_leak"] == 2 and rb["inconclusive_no_leak"] == 0
    assert len(ATTRS) == 4
