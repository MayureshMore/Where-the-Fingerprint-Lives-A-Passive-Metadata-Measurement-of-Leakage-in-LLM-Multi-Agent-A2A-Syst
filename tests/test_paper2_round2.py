"""scripts/paper2_round2.py and features/timestamps.py on small inputs (no model is run)."""

import json

import numpy as np
import pytest

from features.families import family_columns
from features.timestamps import FLOW_NAMES, N_FLOWS, names, timestamp_vector
from scripts.paper2_round2 import (ARMS, ATTRS, D1_RAW, METHODS, accounting, carried, cloud_role_inconclusive, inconclusive_by_attribute, merge,
                                   template_factors, timing_columns, why)


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


def test_inconclusive_by_attribute_reads_headroom_and_width_per_sample():
    def attr(classes, n, half, f1s):
        thr = 1 / len(classes) + 0.05
        runs = [{"verdict": v, "ci_verdict": v, "macro_f1": f, "ci": [f - half, f + half], "n": n, "p": 0.5}
                for f in f1s for v in ["INCONCLUSIVE" if f + half > thr else "NO LEAK"]]
        return {"classes": classes, "groups": n - 10, "groups_per_class": {c: k - 5 for c, k in classes.items()},
                "permuted": {m: runs for m in METHODS}}
    four = {"a": 250, "b": 250, "c": 250, "d": 250}
    cell = {"attributes": {"task_type": attr(four, 1000, 0.026, [0.24, 0.25, 0.26, 0.28]),
                           "escalated": attr({"no": 250, "yes": 750}, 1000, 0.030, [0.49, 0.50, 0.51, 0.52]),
                           "cloud_role": attr({"diagnostics": 500, "knowledge": 250}, 750, 0.030 * (1000 / 750) ** 0.5,
                                              [0.49, 0.50, 0.51, 0.52]),
                           "audit_null": attr(four, 1000, 0.026, [0.25] * 4)}}
    a4 = {"cells": {"x": cell, "y": cell}}
    by = inconclusive_by_attribute(a4)
    cr, esc = by["leakcheck"]["cloud_role"], by["leakcheck"]["escalated"]
    assert cr["draws"] == 8 and cr["n"] == 750 and abs(cr["minority_share"] - 1 / 3) < 1e-9 and cr["groups_min"] == 740
    assert abs(cr["half_width_x_sqrt_n"] - esc["half_width_x_sqrt_n"]) < 1e-9     # a wider CI from n alone
    assert abs(cr["headroom"] - (0.55 - 0.505 - cr["ci_half_width_median"])) < 1e-9
    assert cr["inconclusive"] == cr["ci_straddles"] == 2 and esc["inconclusive"] == 0
    assert by["kfp_rf"]["audit_null"]["predicted_ci_inconclusive"] is None          # no spread, no prediction
    note = cloud_role_inconclusive(a4, by)
    assert note["reference"] == "escalated" and abs(note["half_width_from_reference_by_sqrt_n"] - note["half_width"]) < 1e-9
    assert note["both_inconclusive"] == 2 and note["only_leakcheck"] == note["only_kfp_rf"] == 0


def test_merge_takes_parts_that_differ_only_in_cells(tmp_path):
    params = {"cells": ["lan_v1", "lan_padmax_v2"], "draws": 20, "a10_sizes": [50], "a10_draws": 10, "permutations": 99,
              "perm_max": 999, "n_boot": 1000, "perm_unit": "group", "match_margin": 0.05}

    def part(name, sections, commit="abc", **change):
        p = tmp_path / f"{name}.json"
        p.write_text(json.dumps({"git_commit": commit, "git_dirty": False, "parameters": {**params, **change},
                                 "sections": {**sections, "seconds": {k: 1.0 for k in sections}}}))
        return p
    a5 = part("a5", {"a5": {"x": 1}}, cells=["lan_v1", "lan_v2"])
    a7 = part("a7", {"a7": {"y": 2}})
    res = merge([a5, a7])                                   # each part's seconds no longer collide
    assert res["sections"] == {"a5": {"x": 1}, "a7": {"y": 2}}
    assert res["data_dir"] == ARMS and res["d1_data_dir"] == D1_RAW and res["collection_id"] == "C2" and res["git_commit"] == "abc"
    assert [q["cells"] for q in res["parts"]] == [["lan_v1", "lan_v2"], ["lan_v1", "lan_padmax_v2"]]
    assert res["parts"][0]["sections"] == ["a5"] and res["parts"][0]["seconds"] == {"a5": 1.0}
    with pytest.raises(SystemExit, match="different parameters"):
        merge([a5, part("a8", {"a8": {}}, draws=10)])
    with pytest.raises(SystemExit, match="one clean commit"):
        merge([a5, part("a9", {"a9": {}}, commit="def")])
