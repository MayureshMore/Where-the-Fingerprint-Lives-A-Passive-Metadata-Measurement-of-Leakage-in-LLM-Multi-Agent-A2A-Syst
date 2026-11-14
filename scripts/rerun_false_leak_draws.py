#!/usr/bin/env python3
"""
Re-run the permuted-label subsample draws behind the false LEAKs of a tool evaluation, to record what
the evaluation stores only as a verdict count: for each false LEAK, the arm, view, attribute, size,
draw index, p-value, macro-F1 with its interval, and the prompt groups.

For every cell, attribute and size whose permuted draws include a LEAK (from the evaluation's JSON),
all its draws are rebuilt exactly as scripts/evaluate_leakcheck.py built them: the same features
(load_arm), the same seeded subsample (SEED, 2, attribute stream, size, draw) and label permutation
(SEED, 3, ...), and the same verdict rule and parameters (permutations, bootstrap, margin, workers).
The verdict counts must equal the stored ones; a mismatch is reported and the exit code is 1.
evaluate_leakcheck's stored outputs are not touched.

Runs only from a clean checkout (the result records the commit); --allow-dirty for testing.

Usage (never overwrites):
    python scripts/rerun_false_leak_draws.py --eval data/results/paper2_tool_eval_c2.json \\
        --out data/results/paper2_false_leak_draws
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from a2a_leakcheck.cli import _git  # noqa: E402
from a2a_leakcheck.rules import load_rules  # noqa: E402
from scripts.evaluate_leakcheck import LEAK, SEED, VERDICTS, attr_index, load_arm, subsample, verdict  # noqa: E402


def draw(y: np.ndarray, g: np.ndarray, ai: int, n: int, k: int) -> tuple[np.ndarray, np.ndarray]:
    """Draw k of size n, as evaluate_arm makes it: the subsample's indices and its permuted labels."""
    idx = subsample(y, g, n, np.random.default_rng([SEED, 2, ai, n, k]))
    return idx, np.random.default_rng([SEED, 3, ai, n, k]).permutation(y[idx])


def targets(ev: dict) -> list[tuple[str, str, int]]:
    return [(cell, attr, int(n)) for cell, arm in ev["arms"].items() for attr, r in arm["attributes"].items()
            for n, s in r["sample_size"].items() if s["permuted"].get(LEAK, 0)]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--eval", default="data/results/paper2_tool_eval_c2.json")
    p.add_argument("--out", required=True, help="path stem for .json and .md (not overwritten)")
    p.add_argument("--allow-dirty", action="store_true", dest="allow_dirty")
    a = p.parse_args(argv)
    git = _git()
    if git["git_dirty"] and not a.allow_dirty:
        raise SystemExit("uncommitted code: commit first (or --allow-dirty for a test run)")
    for ext in (".json", ".md"):
        if Path(a.out + ext).exists():
            raise SystemExit(f"{a.out + ext} exists: not overwritten")
    ev = json.loads(Path(a.eval).read_text())
    prm = ev["parameters"]
    cfg = argparse.Namespace(margin=prm["margin"], n_boot=prm["n_boot"], permutations=prm["permutations"],
                             min_per_class=prm["min_per_class"], jobs=prm["jobs"])
    sev = load_rules()["severity"]
    t0 = time.perf_counter()
    cache, groups_out, combos, leaks = {}, {}, [], []
    for cell, attr, n in targets(ev):
        arm = ev["arms"][cell]
        if cell not in cache:
            cache[cell] = load_arm(Path(arm["data_dir"]), attributes=prm["attributes"], vantage=arm.get("vantage"))
        s = cache[cell]["samples"][attr]
        y, g, X = s["y"], s["g"], s["X"]["leakcheck"]
        ai = attr_index(attr, prm.get("role_within") or [])
        rows = []
        for k in range(prm["subsamples"]):
            idx, yp = draw(y, g, ai, n, k)
            v = verdict(X[idx], yp, g[idx], cfg, "leakcheck", sev)
            rows.append({"draw": k, "verdict": v["verdict"], "p": v["p"], "macro_f1": v["macro_f1"], "ci": v["ci"],
                         "n": v["n"], "groups": v["groups"]})
            if v["verdict"] == LEAK:
                leaks.append({"cell": cell, "arm": arm.get("arm", cell), "view": arm.get("vantage"), "attribute": attr,
                              "size": n, "draw": k, "p": v["p"], "macro_f1": v["macro_f1"], "ci": v["ci"],
                              "n": v["n"], "prompt_groups": sorted(set(g[idx].tolist())),
                              "permuted_labels": dict(sorted(zip(g[idx].tolist(), yp.tolist())))})
        stored = ev["arms"][cell]["attributes"][attr]["sample_size"][str(n)]["permuted"]
        got = {x: sum(r["verdict"] == x for r in rows) for x in VERDICTS}
        combos.append({"cell": cell, "attribute": attr, "size": n, "stored": stored, "reproduced": got,
                       "match": all(stored.get(x, 0) == got[x] for x in VERDICTS), "draws": rows})
        print(f"{cell} {attr} n={n}: stored {stored}, reproduced {got}"
              f"{'' if combos[-1]['match'] else '  MISMATCH'}", flush=True)
    shared = []
    for x, z in itertools.combinations(leaks, 2):
        common = len(set(x["prompt_groups"]) & set(z["prompt_groups"]))
        if common:
            same = (x["attribute"], x["size"], x["draw"]) == (z["attribute"], z["size"], z["draw"])
            shared.append([f"{x['cell']} {x['attribute']} n={x['size']} draw {x['draw']}",
                           f"{z['cell']} {z['attribute']} n={z['size']} draw {z['draw']}", common, same])
    out = {"paper": "P2", **git, "source": a.eval, "evaluation_commit": ev.get("git_commit"),
           "parameters": {k: prm[k] for k in ("subsamples", "permutations", "n_boot", "margin", "min_per_class", "jobs")},
           "all_counts_reproduced": all(c["match"] for c in combos), "combinations": combos,
           "false_leaks": leaks, "shared": shared, "runtime_s": time.perf_counter() - t0}
    md = ["# The permuted-label draws behind the false LEAKs, re-run\n",
          f"From `{a.eval}` (evaluation commit {str(ev.get('git_commit'))[:8]}); re-run at commit "
          f"{str(git['git_commit'])[:8]}{' (uncommitted changes)' if git['git_dirty'] else ''}. Stored verdict counts "
          f"reproduced in every combination: {out['all_counts_reproduced']}.\n",
          "| Arm | View | Attribute | Per class | Draw | p | macro-F1 [95% CI] | Prompt groups |", "|---|---|---|---|---|---|---|---|"]
    md += [f"| {x['arm']} | {x['view']} | {x['attribute']} | {x['size']} | {x['draw']} | {x['p']:.2f} | "
           f"{x['macro_f1']:.3f} [{x['ci'][0]:.3f}, {x['ci'][1]:.3f}] | {len(x['prompt_groups'])} |" for x in leaks]
    if shared:
        md += ["", "Shared prompt groups between false LEAKs:", ""]
        md += [f"- {a_} and {b_}: {n_} in common" + (" (same draw index: the same subsample)" if s_ else "")
               for a_, b_, n_, s_ in shared]
    md += ["", "Each false LEAK's prompt groups and permuted labels are in the JSON (`false_leaks`)."]
    Path(a.out + ".json").write_text(json.dumps(out, indent=2, default=float) + "\n")
    Path(a.out + ".md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    return 0 if out["all_counts_reproduced"] else 1


if __name__ == "__main__":
    sys.exit(main())
