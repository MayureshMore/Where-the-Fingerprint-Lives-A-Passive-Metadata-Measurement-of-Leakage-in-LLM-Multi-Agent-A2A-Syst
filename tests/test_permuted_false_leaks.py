"""scripts/permuted_false_leaks.py and the draw rebuild in scripts/rerun_false_leak_draws.py."""

import json

import numpy as np

from scripts.evaluate_leakcheck import SEED, subsample
from scripts.permuted_false_leaks import markdown, pooled, structure, summarize
from scripts.rerun_false_leak_draws import draw, targets


def _attr(classes, perm_leaks):
    sizes = {}
    for n, k in perm_leaks.items():
        sizes[str(n)] = {"real": {"LEAK": 20, "INCONCLUSIVE": 0, "NO LEAK": 0},
                         "permuted": {"LEAK": k, "INCONCLUSIVE": 20 - k - 5, "NO LEAK": 5}}
    return {"classes": {c: 40 for c in classes}, "sample_size": sizes,
            "permuted": {"leakcheck": ["NO LEAK"] * 20, "kfp_rf": ["NO LEAK"] * 19 + ["INCONCLUSIVE"]}}


def _eval(data_dirs=("raw_a", "raw_b")):
    arms = {}
    for i, d in enumerate(data_dirs):
        for v in ("v1", "v2"):
            arms[f"{d}_{v}"] = {"data_dir": d, "arm": d, "vantage": v, "attributes": {
                "escalated": _attr(["no", "yes"], {20: 1 if (i, v) == (0, "v2") else 0, 30: 0}),
                "task_type": _attr(["a", "b", "c", "d"], {20: 0, 30: 0})}}
    return {"git_commit": "abc", "git_dirty": False, "arms": arms,
            "parameters": {"sizes": [20, 30], "subsamples": 20, "permutations": 99, "n_boot": 1000, "margin": 0.05,
                           "min_per_class": 20, "jobs": 5, "label_perms": 20, "null_model": "rf-light", "alpha": 0.05,
                           "attributes": ["task_type", "escalated"], "role_within": []}}


def test_pooled_rates_and_cells():
    s = pooled(_eval())
    assert s["per_size"]["20"]["false_leaks"] == 1 and s["per_size"]["20"]["draws"] == 160
    assert s["per_size"]["30"]["false_leaks"] == 0 and s["per_size"]["30"]["ci"][0] == 0
    assert s["per_size_by_classes"]["binary"]["20"]["draws"] == 80
    assert s["per_size_by_classes"]["4-class"]["attributes"] == ["task_type"]
    assert s["full_data_by_method"]["leakcheck"] == {"false_leaks": 0, "draws": 160, "rate": 0.0,
                                                      "ci": s["full_data_by_method"]["leakcheck"]["ci"]}
    assert s["cells_with_false_leaks"] == [{"cell": "raw_a_v2", "arm": "raw_a", "view": "v2", "attribute": "escalated",
                                            "size": 20, "false_leaks": 1, "draws": 20, "classes": 2,
                                            "leak_threshold": 0.55}]
    assert targets(_eval()) == [("raw_a_v2", "escalated", 20)]


def test_summary_states_independence_and_smallest_p():
    md = markdown(summarize(_eval(), "x.json"))
    assert "assume independent draws" in md and "smallest p-value is 0.01" in md and "| raw_a | v2 | escalated | 20 | 1/20 |" in md


def test_draw_matches_the_evaluation_seeds():
    y = np.array(["no", "yes"] * 60)
    g = np.array([f"g{i // 2}" for i in range(120)])
    idx, yp = draw(y, g, 5, 20, 3)
    assert np.array_equal(idx, subsample(y, g, 20, np.random.default_rng([SEED, 2, 5, 20, 3])))
    assert np.array_equal(yp, np.random.default_rng([SEED, 3, 5, 20, 3]).permutation(y[idx]))
    assert sorted(yp.tolist()) == sorted(y[idx].tolist())


def test_structure_same_groups_across_arms_and_labels_across_views(tmp_path):
    rng = np.random.default_rng(0)
    groups = [f"{i:06x}" for i in range(120)]
    labels = {gr: ("yes" if i % 2 else "no") for i, gr in enumerate(groups)}
    for d in ("raw_a", "raw_b"):                  # same prompts and labels, different capture names and order
        (tmp_path / d).mkdir()
        for gr in groups:
            name = f"t_{rng.integers(1 << 30):08x}"
            (tmp_path / d / f"{name}.pcap").write_bytes(b"")
            (tmp_path / d / f"{name}.json").write_text(json.dumps({"escalated": labels[gr], "prompt_group": gr}))
    ev = _eval()
    st = structure(ev, pooled(ev)["cells_with_false_leaks"], tmp_path)["escalated/20"]
    assert st["same_prompt_groups_in_every_cell_for_a_draw_index"] is True
    assert st["same_permuted_labels_in_both_views_of_an_arm"] is True
    assert st["prompt_groups_per_draw"] == 40 and 0 <= st["overlap_between_draw_indices"]["median"] < 1
