#!/usr/bin/env python3
"""
False LEAKs on permuted labels in a tool evaluation (scripts/evaluate_leakcheck.py), summarized from
its stored output: no model is run.

  1. Pooled rate per sample size over every permuted subsample draw (all cells, attributes and views),
     with a Wilson 95% interval; also split by the number of classes and per attribute, and the
     full-data label permutations per method.
  2. The test behind each draw: the permutations it runs, the smallest p-value they allow, and the
     other condition a LEAK needs (the interval's lower bound above chance + margin).
  3. The cells with false LEAKs, and how the draws relate. A draw's subsample is seeded by attribute,
     size and draw index only, so for one attribute, size and draw index every arm and view takes the
     same prompt groups; both views of an arm also get the same permuted labels (the traces and their
     order are the same). This is rebuilt from the sidecars with the evaluation's own subsample().
     With --draws (the output of scripts/rerun_false_leak_draws.py): each false LEAK's draw index,
     p-value, macro-F1 with its interval and prompt groups.

The Wilson intervals treat the draws as independent. They are not fully independent: the two views
of an arm share subsamples and permuted labels, and arms share prompt groups for the same draw index;
so the intervals are somewhat too narrow. The summary says so.

Usage (never overwrites):
    python scripts/permuted_false_leaks.py --eval data/results/paper2_tool_eval_c2.json \\
        --out data/results/paper2_permuted_false_leaks [--draws data/results/paper2_false_leak_draws.json]
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from a2a_leakcheck.cli import _git  # noqa: E402
from scripts.evaluate_leakcheck import LEAK, SEED, VERDICTS, attr_index, subsample, wilson  # noqa: E402

INDEPENDENCE = ("The Wilson intervals assume independent draws. The draws are not fully independent: for one "
                "attribute, size and draw index, every arm and view takes the same prompt groups, and the two "
                "views of an arm also get the same permuted labels (only the features differ). The intervals "
                "are therefore somewhat too narrow.")


def rate(k: int, n: int) -> dict:
    return {"false_leaks": k, "draws": n, "rate": k / n if n else None, "ci": wilson(k, n)}


def pooled(ev: dict) -> dict:
    p = ev["parameters"]
    sizes = [str(n) for n in p["sizes"]]
    all_, by_k, by_attr, cells = {}, {}, {}, []
    for n in sizes:
        tot = [0, 0]
        for cell, arm in ev["arms"].items():
            for attr, r in arm["attributes"].items():
                pm = r["sample_size"][n]["permuted"]
                k, t = pm.get(LEAK, 0), sum(pm.values())
                tot[0] += k; tot[1] += t
                nc = "binary" if len(r["classes"]) == 2 else f"{len(r['classes'])}-class"
                by_k.setdefault(nc, {}).setdefault(n, [0, 0, set()])
                by_k[nc][n][0] += k; by_k[nc][n][1] += t; by_k[nc][n][2].add(attr)
                by_attr.setdefault(attr, {}).setdefault(n, [0, 0])
                by_attr[attr][n][0] += k; by_attr[attr][n][1] += t
                if k:
                    cells.append({"cell": cell, "arm": arm.get("arm", cell), "view": arm.get("vantage"),
                                  "attribute": attr, "size": int(n), "false_leaks": k, "draws": t,
                                  "classes": len(r["classes"]),
                                  "leak_threshold": 1 / len(r["classes"]) + p["margin"]})
        all_[n] = rate(*tot)
    full = {}
    for cell, arm in ev["arms"].items():
        for attr, r in arm["attributes"].items():
            for m, vs in r["permuted"].items():
                full.setdefault(m, [0, 0])
                full[m][0] += vs.count(LEAK); full[m][1] += len(vs)
    return {"per_size": all_,
            "per_size_by_classes": {nc: {"attributes": sorted(set().union(*(v[2] for v in d.values()))),
                                         **{n: rate(v[0], v[1]) for n, v in d.items()}} for nc, d in by_k.items()},
            "per_size_by_attribute": {a: {n: rate(*v) for n, v in d.items()} for a, d in by_attr.items()},
            "full_data_by_method": {m: rate(*v) for m, v in full.items()},
            "cells_with_false_leaks": cells}


def test_behind(ev: dict) -> dict:
    p = ev["parameters"]
    return {"draws_per_cell_attribute_size": p["subsamples"], "label_permutations_per_draw": 1,
            "permutation_test": {"permutations": p["permutations"], "null_model": p.get("null_model", "rf-light"),
                                 "alpha": p.get("alpha", 0.05),
                                 "smallest_p": 1 / (p["permutations"] + 1)},
            "also_needed_for_leak": f"the cluster-bootstrap ({p['n_boot']} resamples) interval's lower bound above "
                                    f"chance + {p['margin']} (two classes: {0.5 + p['margin']:.2f})",
            "stored_per_draw": "the verdict only (p-value and macro-F1 are not stored; scripts/rerun_false_leak_draws.py "
                               "recomputes them)",
            "full_data_permutations_per_cell_attribute": p.get("label_perms")}


def labels_groups(raw: Path, attr: str) -> tuple[np.ndarray, np.ndarray]:
    """Labels and prompt groups in the evaluation's order: captures sorted by name, those with the label."""
    y, g = [], []
    for pcap in sorted(raw.glob("*.pcap")):
        s = json.loads(pcap.with_suffix(".json").read_text())
        if s.get("success") is False or s.get(attr) in (None, ""):
            continue
        y.append(str(s[attr])); g.append(s.get("prompt_group") or pcap.stem)
    return np.array(y), np.array(g)


def structure(ev: dict, cells: list[dict], root: Path) -> dict:
    """For each attribute and size with false LEAKs: are the prompt groups of draw k the same in every cell,
    and how much do different draws overlap."""
    p = ev["parameters"]
    out = {}
    for attr, n in sorted({(c["attribute"], c["size"]) for c in cells}):
        ai = attr_index(attr, p.get("role_within") or [])
        groups, labels = {}, {}
        for cell, arm in ev["arms"].items():
            raw = root / arm["data_dir"]
            if not raw.is_dir():
                return {"skipped": f"{raw} not found"}
            y, g = labels_groups(raw, attr)
            groups[cell], labels[cell] = [], []
            for k in range(p["subsamples"]):
                idx = subsample(y, g, n, np.random.default_rng([SEED, 2, ai, n, k]))
                yp = np.random.default_rng([SEED, 3, ai, n, k]).permutation(y[idx])
                groups[cell].append(frozenset(g[idx].tolist()))
                labels[cell].append(tuple(zip(g[idx].tolist(), yp.tolist())))
        c0 = next(iter(groups))
        same_groups = all(groups[c][k] == groups[c0][k] for c in groups for k in range(p["subsamples"]))
        views = {}
        for cell, arm in ev["arms"].items():
            views.setdefault(arm.get("arm", cell), []).append(cell)
        same_labels_views = all(labels[cs[0]][k] == labels[c][k] for cs in views.values() for c in cs
                                for k in range(p["subsamples"]))
        ov = [len(a & b) / len(a) for a, b in itertools.combinations(groups[c0], 2)]
        out[f"{attr}/{n}"] = {"same_prompt_groups_in_every_cell_for_a_draw_index": same_groups,
                              "same_permuted_labels_in_both_views_of_an_arm": same_labels_views,
                              "prompt_groups_per_draw": len(groups[c0][0]),
                              "overlap_between_draw_indices": {"median": float(np.median(ov)), "max": float(max(ov))}}
    return out


def markdown(s: dict) -> str:
    f = lambda r: f"{r['false_leaks']}/{r['draws']} | {r['rate']:.4f} | [{r['ci'][0]:.4f}, {r['ci'][1]:.4f}]"  # noqa: E731
    t = s["test"]
    L = ["# False LEAKs on permuted labels\n",
         f"From `{s['source']}` (evaluation commit {str(s['evaluation_commit'])[:8]}); no model run here.\n",
         "## 1. Pooled over every permuted subsample draw (all cells, attributes and views)\n",
         "| Traces per class | False LEAK | Rate | Wilson 95% CI |", "|---|---|---|---|"]
    L += [f"| {n} | {f(r)} |" for n, r in s["pooled"]["per_size"].items()]
    for nc, d in s["pooled"]["per_size_by_classes"].items():
        L += ["", f"{nc.capitalize()} attributes ({', '.join(d['attributes'])}):", "",
              "| Traces per class | False LEAK | Rate | Wilson 95% CI |", "|---|---|---|---|"]
        L += [f"| {n} | {f(r)} |" for n, r in d.items() if n != "attributes"]
    L += ["", "Full data, the label permutations of each cell and attribute:", "",
          "| Method | False LEAK | Rate | Wilson 95% CI |", "|---|---|---|---|"]
    L += [f"| {m} | {f(r)} |" for m, r in s["pooled"]["full_data_by_method"].items()]
    L += ["", f"**Independence.** {INDEPENDENCE}", "",
          "## 2. The test behind each draw\n",
          f"- {t['draws_per_cell_attribute_size']} draws per cell, attribute and size, each with "
          f"{t['label_permutations_per_draw']} label permutation of its subsample;",
          f"- each permuted draw goes through the full verdict rule: a permutation test with "
          f"{t['permutation_test']['permutations']} permutations ({t['permutation_test']['null_model']}), so the "
          f"smallest p-value is {t['permutation_test']['smallest_p']:.2f}; a LEAK needs p ≤ "
          f"{t['permutation_test']['alpha']} and {t['also_needed_for_leak']};",
          f"- stored per draw: {t['stored_per_draw']}.", "",
          "## 3. The false LEAKs\n",
          "| Arm | View | Attribute | Per class | False LEAK | LEAK needs CI lower bound above |", "|---|---|---|---|---|---|"]
    L += [f"| {c['arm']} | {c['view']} | {c['attribute']} | {c['size']} | {c['false_leaks']}/{c['draws']} | "
          f"{c['leak_threshold']:.2f} |" for c in s["pooled"]["cells_with_false_leaks"]]
    st = s.get("structure") or {}
    if st and "skipped" not in st:
        L += ["", "How the draws relate (rebuilt from the sidecars with the evaluation's seeds):", ""]
        for key, x in st.items():
            L.append(f"- {key}: same prompt groups in every cell for a draw index: "
                     f"{x['same_prompt_groups_in_every_cell_for_a_draw_index']}; same permuted labels in both views "
                     f"of an arm: {x['same_permuted_labels_in_both_views_of_an_arm']}; {x['prompt_groups_per_draw']} "
                     f"groups per draw; different draw indices share {x['overlap_between_draw_indices']['median']:.0%} "
                     f"of their groups (median; max {x['overlap_between_draw_indices']['max']:.0%})")
    d = s.get("draws")
    if d:
        L += ["", f"Each false LEAK, re-run by `scripts/rerun_false_leak_draws.py` (commit {str(d.get('git_commit'))[:8]}; "
              f"stored verdict counts reproduced: {d['all_counts_reproduced']}):", "",
              "| Arm | View | Attribute | Per class | Draw | p | macro-F1 [95% CI] | Prompt groups |", "|---|---|---|---|---|---|---|---|"]
        for x in d["false_leaks"]:
            L.append(f"| {x['arm']} | {x['view']} | {x['attribute']} | {x['size']} | {x['draw']} | {x['p']:.2f} | "
                     f"{x['macro_f1']:.3f} [{x['ci'][0]:.3f}, {x['ci'][1]:.3f}] | {len(x['prompt_groups'])} |")
        if d.get("shared"):
            L += ["", "False LEAKs that share prompt groups:", ""]
            L += [f"- {a} and {b}: {n} groups in common" + (" (same draw index: the same subsample)" if same else "")
                  for a, b, n, same in d["shared"]]
    return "\n".join(L) + "\n"


def summarize(ev: dict, source: str, root: Path | None = None, draws: dict | None = None) -> dict:
    s = {"paper": "P2", **_git(), "source": source, "evaluation_commit": ev.get("git_commit"),
         "evaluation_dirty": ev.get("git_dirty"), "pooled": pooled(ev), "test": test_behind(ev),
         "independence": INDEPENDENCE}
    if root is not None:
        s["structure"] = structure(ev, s["pooled"]["cells_with_false_leaks"], root)
    if draws is not None:
        s["draws"] = draws
    return s


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--eval", default="data/results/paper2_tool_eval_c2.json")
    p.add_argument("--root", default=".", help="repository root the evaluation's data_dir paths are relative to")
    p.add_argument("--draws", default=None, help="scripts/rerun_false_leak_draws.py output (JSON)")
    p.add_argument("--out", default=None, help="path stem for .json and .md (not overwritten)")
    a = p.parse_args(argv)
    ev = json.loads(Path(a.eval).read_text())
    draws = json.loads(Path(a.draws).read_text()) if a.draws else None
    s = summarize(ev, a.eval, Path(a.root), draws)
    md = markdown(s)
    print(md)
    if a.out:
        for ext, text in ((".json", json.dumps(s, indent=2, default=float) + "\n"), (".md", md)):
            f = Path(a.out + ext)
            if f.exists():
                raise SystemExit(f"{f} exists: not overwritten")
            f.write_text(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
