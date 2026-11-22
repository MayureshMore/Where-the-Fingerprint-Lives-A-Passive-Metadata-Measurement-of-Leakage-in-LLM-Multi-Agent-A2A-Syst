#!/usr/bin/env python3
"""
B1 power check: can an audit of sensor_analysis vs fault_diagnosis say NO LEAK at all at B1's size?
On C2 lan_padmax at V2 (data/raw_c2_padmax), with permuted labels (no signal by construction), at
--sizes traces per class (C2 holds 250 per class): each draw takes n per class by whole prompt
groups, permutes the labels by group, and runs a2a-leakcheck with its defaults (margin 0.05, 99
group permutations, 1000 bootstraps). Per size: the verdicts, the CI verdicts, the median CI upper
bound against chance + margin, and the CI's upper half-width.

Sizes past C2's 250 per class: --predict scales each draw at the largest measured size to n per
class by 1/sqrt(n) (macro-F1's distance from chance and the CI's half-width; A11 found half-width x
sqrt(n) constant across attributes) and counts the draws whose CI would end at or under chance +
margin. --pooled-check measures one size on lan_pad and lan_padmax at V2 together (the same
prompts in both arms: a group is a prompt in both), as a check of that prediction.

    python scripts/b1_power.py --out data/results/b1_power
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from a2a_leakcheck.analyze import INCONCLUSIVE, LEAK, NO_LEAK, group_plan, permute_group  # noqa: E402
from a2a_leakcheck.cli import _git  # noqa: E402
from a2a_leakcheck.rules import load_rules  # noqa: E402
from scripts.evaluate_leakcheck import subsample  # noqa: E402
from scripts.paper2_round2 import ARMS, PAIR, SEED, counts, load_cell, run, why  # noqa: E402

SUB_STREAM, PERM_STREAM = 22, 23          # apart from paper2_round2's streams (8-10, 20, 21) and the tests' (seed, 7, i)
MARGIN = 0.05


def pair(d: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    tt = d["labels"]["task_type"]
    idx = np.flatnonzero(np.isin(tt, PAIR))
    return d["X"]["leakcheck"][idx], tt[idx], d["g"][idx]


def draws(X, y, g, n: int, k: int, a, sev, tag: int) -> list[dict]:
    out = []
    for i in range(k):
        sub = subsample(y, g, n, np.random.default_rng([SEED, SUB_STREAM, tag, n, i]))
        ys, gs = y[sub], g[sub]
        yp = permute_group(ys, group_plan(ys, gs), np.random.default_rng([SEED, PERM_STREAM, tag, n, i]))
        r = run(X[sub], yp, gs, "leakcheck", a, sev)
        r["why"] = why(r)
        r["per_class"] = {c: int((yp == c).sum()) for c in sorted(set(yp.tolist()))}
        out.append(r)
        print(f"  n={n} draw {i}: {r['verdict']:12s} F1 {r['macro_f1']} CI {r['ci']} p {r['p']} ({r['seconds']:.0f} s)", flush=True)
    return out


def summary(rows: list[dict], chance: float = 0.5) -> dict:
    hi = [r["ci"][1] for r in rows]
    half = [r["ci"][1] - r["macro_f1"] for r in rows]
    return {"draws": len(rows), "verdicts": counts(r["verdict"] for r in rows),
            "ci_verdicts": counts(r["ci_verdict"] for r in rows), "why": {w: sum(r["why"] == w for r in rows) for w in {r["why"] for r in rows}},
            "threshold": chance + MARGIN, "ci_hi_median": statistics.median(hi), "ci_hi_min": min(hi), "ci_hi_max": max(hi),
            "macro_f1_median": statistics.median(r["macro_f1"] for r in rows), "upper_half_width_median": statistics.median(half),
            "p_under_0_05": sum(r["p"] is not None and r["p"] < 0.05 for r in rows),
            "seconds_median": statistics.median(r["seconds"] for r in rows)}


def predict(rows: list[dict], n_from: int, n_to: int, chance: float = 0.5) -> dict:
    s = (n_from / n_to) ** 0.5
    hi = [chance + (r["macro_f1"] - chance) * s + (r["ci"][1] - r["macro_f1"]) * s for r in rows]
    return {"from_per_class": n_from, "scale": s, "ci_no_leak": sum(h <= chance + MARGIN for h in hi), "draws": len(rows),
            "ci_hi_median": statistics.median(hi), "ci_hi_max": max(hi),
            "note": "CI verdicts only; the permutation test turns about 1 in 20 null draws INCONCLUSIVE on its own (p < 0.05)"}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--out", required=True, help="output path without extension (.json, .md)")
    p.add_argument("--cell", default="lan_padmax_v2")
    p.add_argument("--sizes", default="125,250", help="traces per class, at most C2's 250")
    p.add_argument("--draws", type=int, default=20)
    p.add_argument("--predict", default="375,500", help="per-class sizes to predict from the largest measured size")
    p.add_argument("--pooled-check", type=int, default=375, dest="pooled_check",
                   help="per-class size measured on lan_pad and lan_padmax pooled at the same view (0: skip)")
    p.add_argument("--pooled-draws", type=int, default=None, dest="pooled_draws")
    p.add_argument("--permutations", type=int, default=99)
    p.add_argument("--n-boot", type=int, default=1000, dest="n_boot")
    p.add_argument("--jobs", type=int, default=-1)
    p.add_argument("--allow-dirty", action="store_true", dest="allow_dirty")
    a = p.parse_args(argv)
    out = Path(a.out)
    for ext in (".json", ".md"):
        if out.with_suffix(ext).exists():
            raise SystemExit(f"{out.with_suffix(ext)} exists: results are not written over")
    git = _git()
    if git["git_dirty"] is not False and not a.allow_dirty:
        raise SystemExit("uncommitted code: commit first (or --allow-dirty for a test run)")
    sizes = [int(x) for x in a.sizes.split(",") if x]
    sev = load_rules()["severity"]
    t0 = time.perf_counter()
    d = load_cell(a.cell)
    X, y, g = pair(d)
    print(f"[{a.cell}] pair: {dict(zip(*np.unique(y, return_counts=True)))} traces, {len(np.unique(g))} groups "
          f"({d['load_s']:.0f} s to load)", flush=True)
    if max(sizes) > min(int((y == c).sum()) for c in PAIR):
        raise SystemExit(f"{a.cell} holds {min(int((y == c).sum()) for c in PAIR)} traces per class, fewer than {max(sizes)}")
    res = {"paper": "P2", "purpose": "B1 power: permuted sensor vs fault at B1's size", "collection_id": "C2",
           "data_dir": {d["arm"]: ARMS[d["arm"]]}, "cell": a.cell, "seed": SEED, **{k: git[k] for k in ("git_commit", "git_dirty")},
           "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "parameters": {"sizes_per_class": sizes, "draws": a.draws, "margin": MARGIN, "permutations": a.permutations,
                          "n_boot": a.n_boot, "perm_unit": "group", "streams": [SUB_STREAM, PERM_STREAM]},
           "measured": {}, "predicted": {}}
    raw = {}
    for n in sizes:
        print(f"[{a.cell}] {n} + {n}", flush=True)
        raw[n] = draws(X, y, g, n, a.draws, a, sev, tag=0)
        res["measured"][str(n)] = {**summary(raw[n]), "rows": raw[n]}
    for n in [int(x) for x in a.predict.split(",") if x]:
        res["predicted"][str(n)] = predict(raw[max(sizes)], max(sizes), n)
    if a.pooled_check:
        view = a.cell.rsplit("_", 1)[1]
        other = load_cell(f"lan_pad_{view}") if d["arm"] == "lan_padmax" else load_cell(f"lan_padmax_{view}")
        X2, y2, g2 = pair(other)
        Xp, yp, gp = np.vstack([X, X2]), np.concatenate([y, y2]), np.concatenate([g, g2])
        n = a.pooled_check
        print(f"[pooled {d['arm']} + {other['arm']} at {view}] {n} + {n} of {dict(zip(*np.unique(yp, return_counts=True)))}, "
              f"{len(np.unique(gp))} groups", flush=True)
        rows = draws(Xp, yp, gp, n, a.pooled_draws or a.draws, a, sev, tag=1)
        res["pooled_check"] = {"arms": [d["arm"], other["arm"]], "data_dir": {k: ARMS[k] for k in (d["arm"], other["arm"])},
                               "per_class": n, "groups": int(len(np.unique(gp))), **summary(rows), "rows": rows}
    res["runtime_s"] = time.perf_counter() - t0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(res, indent=1, default=str))
    out.with_suffix(".md").write_text(markdown(res))
    print(f"→ {out}.json, {out}.md ({res['runtime_s']:.0f} s)")
    return 0


def markdown(r: dict) -> str:
    thr = 0.5 + MARGIN
    L = [f"# B1 power check: permuted sensor_analysis vs fault_diagnosis ({r['cell']})", "",
         f"Commit {r['git_commit']} (dirty: {r['git_dirty']}), seed {r['seed']}, {r['parameters']['draws']} draws per size, "
         f"margin {MARGIN}: NO LEAK needs the CI's upper bound at or under {thr:.2f} and no significant permutation test.", "",
         "| per class | NO LEAK | INCONCLUSIVE | LEAK | CI NO LEAK | median CI upper | range | median upper half-width | p < 0.05 |",
         "|---|---|---|---|---|---|---|---|---|"]
    rows = [(f"{n} + {n}", s) for n, s in r["measured"].items()]
    if "pooled_check" in r:
        pc = r["pooled_check"]
        rows.append((f"{pc['per_class']} + {pc['per_class']} (pooled {' + '.join(pc['arms'])})", pc))
    for name, s in rows:
        v, c = s["verdicts"], s["ci_verdicts"]
        L.append(f"| {name} | {v[NO_LEAK]} | {v[INCONCLUSIVE]} | {v[LEAK]} | {c[NO_LEAK]} | {s['ci_hi_median']:.3f} | "
                 f"{s['ci_hi_min']:.3f}-{s['ci_hi_max']:.3f} | {s['upper_half_width_median']:.3f} | {s['p_under_0_05']} |")
    L += ["", "Predicted from the largest measured size by 1/sqrt(n) (CI verdicts only):", "",
          "| per class | CI NO LEAK | median CI upper | largest CI upper |", "|---|---|---|---|"]
    for n, s in r["predicted"].items():
        L.append(f"| {n} + {n} | {s['ci_no_leak']} of {s['draws']} | {s['ci_hi_median']:.3f} | {s['ci_hi_max']:.3f} |")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
