#!/usr/bin/env python3
"""
Train on one session, test on another (paper 2 round 2, B3: a second day of the lan arm). Within one
session the folds share the day, the network and the models' state; this asks whether a model fitted on
day 1 still reads day 2.

Both sides are features folders from `python -m a2a_leakcheck extract` (with `round` among the
attributes to split one session by rounds instead: --train-rounds / --test-rounds), of the same view.
Per attribute (and --pair ATTR:A,B, and each --subset NAME=ATTR:A,B[,C...] on those classes only),
with the tool's GBT on the 195 trace features:

    transfer      fitted on all of the training side, scored on the test side: macro-F1 with a 95%
                  cluster-bootstrap CI over the test side's prompt groups; the verdict rule as the tool's
                  (LEAK if the lower bound > 1/k + margin, NO LEAK if the upper bound <= it)
    test          a permutation test of the transfer: the training labels permuted by prompt group
                  (a2a_leakcheck.analyze.permutations, group unit), refitted, scored on the real test
                  labels; p = (1 + #null >= observed) / (R + 1). A LEAK needs p <= alpha
    within        the tool's own cross-validation on the test side alone (the same-session figure)
    reference     with --reference data/results/paper2_round2.json: C2's within-session figure of the
                  same view from its section a7 (seed 42, every trace of C2's lan arm), by the same name
                  (task_type, escalated, cloud_role, audit_null, pair, escalated_only)

A prompt drawn in both sessions (same text, so the same prompt group) would let the model recognise
the prompt rather than read the traffic: test traces whose prompt group is also in the training side
are dropped (--keep-shared keeps them), and the count is reported. With seed offsets 30000 (C2) and
33000 (B3), 23 procedure_lookup and 4 alert_triage prompts occur in both (docs/PROMPT_REGISTRY.md).

Usage (a dry run on C2 itself: rounds 0-2 against rounds 3-4 of the lan arm at V2):
    python -m a2a_leakcheck extract data/raw_c2 --vantage v2 --strip \\
        --attributes task_type,escalated,cloud_role,audit_null,round --out data/round2_parts/features_c2_lan_v2_rounds
    python scripts/evaluate_cross_session.py --train data/round2_parts/features_c2_lan_v2_rounds --train-rounds 0,1,2 \\
        --test data/round2_parts/features_c2_lan_v2_rounds --test-rounds 3,4 --pair task_type:sensor_analysis,fault_diagnosis \\
        --out data/round2_parts/cross_rounds
    # B3: day 1 (C2's lan arm) against day 2, and the reverse, per view
    python scripts/evaluate_cross_session.py --train FEATURES_C2_LAN_V2 --test FEATURES_B3_LAN_V2 \
        --subset pair=task_type:sensor_analysis,fault_diagnosis \
        --subset escalated_only=task_type:fault_diagnosis,procedure_lookup,sensor_analysis \
        --reference data/results/paper2_round2.json --out data/results/b3_cross_session_c2_to_b3_v2
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from sklearn.metrics import f1_score

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from a2a_leakcheck.analyze import Config, _model, _parallel, analyze, group_plan, permutations, verdict  # noqa: E402
from a2a_leakcheck.cli import _git  # noqa: E402
from a2a_leakcheck.extract import load_features  # noqa: E402
from a2a_leakcheck.rules import load_rules  # noqa: E402
from evaluation.stats import bootstrap_ci  # noqa: E402

SEED = 42


def side(folder: str, rounds: str) -> dict:
    _, ext, traces, meta = load_features(Path(folder))
    keep = np.ones(len(traces), bool)
    if rounds:
        want = {r.strip() for r in rounds.split(",")}
        if "round" not in meta["attributes"]:
            raise SystemExit(f"{folder}: extracted without the round attribute")
        keep = np.array([t.labels.get("round") in want for t in traces])
    data_dir = (meta.get("input") or {}).get("folder")
    sm = Path(data_dir) / "session_meta.json" if data_dir else None
    collection_id = json.loads(sm.read_text()).get("collection_id") if sm and sm.exists() else None
    return {"X": ext["trace_X"][keep], "traces": [t for t, k in zip(traces, keep) if k], "folder": folder,
            "rounds": rounds or None, "data_dir": data_dir, "collection_id": collection_id,
            "view": (meta.get("input") or {}).get("vantage"),
            "meta": {k: meta[k] for k in ("input", "parameters", "created", "git_commit")}}


def labels(s: dict, attr: str, classes: list[str] | None = None):
    y = np.array([t.labels.get(attr, "") for t in s["traces"]])
    g = np.array([t.group for t in s["traces"]])
    keep = y != "" if classes is None else np.isin(y, classes)
    return s["X"][keep], y[keep], g[keep]


def subsets(pair: str, specs: list[str]) -> list[tuple[str, str, list[str]]]:
    """(name, attribute, classes) of --pair ATTR:A,B (named ATTR:A,B) and each --subset NAME=ATTR:A,B[,C...]."""
    out = []
    if pair:
        attr, _, cl = pair.partition(":")
        out.append((f"{attr}:{cl}", attr, [c.strip() for c in cl.split(",")]))
    for spec in specs:
        nm, _, rest = spec.partition("=")
        attr, _, cl = rest.partition(":")
        classes = [c.strip() for c in cl.split(",") if c.strip()]
        if not nm or not attr or len(classes) < 2:
            raise SystemExit(f"--subset {spec}: give NAME=ATTR:A,B[,C...]")
        out.append((nm, attr, classes))
    if len({n for n, _, _ in out}) != len(out):
        raise SystemExit("two subsets of the same name")
    return out


def reference(path: str, view: str | None) -> dict:
    """C2's within-session figures of this view from paper2_round2.json's section a7 (seed 42), by task name."""
    d = json.loads(Path(path).read_text())
    a7 = d["sections"]["a7"]
    out = {"source": path, "section": "a7", "git_commit": d.get("merge_commit") or d.get("git_commit"),
           "clean": (d.get("merge_dirty") if "merge_dirty" in d else d.get("git_dirty")) is False,
           "collection_id": d.get("collection_id"), "data_dir": (d.get("data_dir") or {}).get("lan"), "view": view,
           "tasks": {}}
    for key, x in a7.items():
        cell, _, task = key.partition(" / ")
        if cell == f"lan_{view}":
            out["tasks"][task] = x["seed_42"]
    if not out["tasks"]:
        raise SystemExit(f"{path}: no lan_{view} cells in section a7")
    return out


def _fit_score(Xtr, ytr, Xte, yte, classes, seed) -> float:
    m = _model("gbt", seed, len(ytr), len(set(ytr.tolist())))
    return float(f1_score(yte, m.fit(Xtr, ytr).predict(Xte), labels=classes, average="macro", zero_division=0))


def transfer(train: dict, test: dict, attr: str, a, classes: list[str] | None = None) -> dict:
    Xtr, ytr, gtr = labels(train, attr, classes)
    Xte, yte, gte = labels(test, attr, classes)
    shared = np.isin(gte, gtr)
    dropped = int(shared.sum()) if not a.keep_shared else 0
    if not a.keep_shared:
        Xte, yte, gte = Xte[~shared], yte[~shared], gte[~shared]
    cls = sorted(set(ytr.tolist()) | set(yte.tolist()))
    t = time.perf_counter()
    m = _model("gbt", SEED, len(ytr), len(set(ytr.tolist())))
    pred = m.fit(Xtr, ytr).predict(Xte)
    ci = bootstrap_ci(list(yte), list(pred), classes=cls, groups=list(gte), n=a.n_boot, seed=SEED)
    chance = 1.0 / len(cls)
    v = verdict(ci["macro_f1_ci_lo"], ci["macro_f1_ci_hi"], chance, a.margin)
    cfg = Config(seed=SEED, perm_unit="group", permutations=a.permutations, jobs=a.jobs)
    perms = permutations(ytr, gtr, cfg, 0, a.permutations, group_plan(ytr, gtr))
    null = _parallel([(_fit_score, Xtr, yp, Xte, yte, cls, SEED) for yp in perms], a.jobs)
    p = (1 + sum(x >= ci["macro_f1"] for x in null)) / (len(null) + 1)
    if v == "LEAK" and p > a.alpha:
        v = "INCONCLUSIVE"
    elif v == "NO LEAK" and p <= a.alpha:
        v = "INCONCLUSIVE"
    within = analyze(Xte, yte, gte, {}, None, Config(seed=SEED, perm_unit="group", permutations=a.permutations,
                                                      n_boot=a.n_boot, jobs=a.jobs), load_rules()["severity"])
    wa = within["analysis"] or {}
    return {"classes": cls, "train": {"n": int(len(ytr)), "groups": int(len(np.unique(gtr)))},
            "test": {"n": int(len(yte)), "groups": int(len(np.unique(gte))), "shared_prompts": int(shared.sum()),
                     "dropped_shared": dropped},
            "transfer": {"verdict": v, "macro_f1": ci["macro_f1"], "ci": [ci["macro_f1_ci_lo"], ci["macro_f1_ci_hi"]],
                         "p": p, "null_mean": float(np.mean(null)), "chance": chance},
            "within_test": {"verdict": within["verdict"], "macro_f1": wa.get("macro_f1"),
                            "ci": [wa.get("ci_lo"), wa.get("ci_hi")],
                            "p": (within["validation"].get("permutation") or {}).get("p_value")},
            "seconds": time.perf_counter() - t}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--train", required=True)
    p.add_argument("--test", required=True)
    p.add_argument("--train-rounds", default="", dest="train_rounds")
    p.add_argument("--test-rounds", default="", dest="test_rounds")
    p.add_argument("--attributes", default="task_type,escalated,cloud_role,audit_null")
    p.add_argument("--pair", default="", help="ATTR:A,B (e.g. task_type:sensor_analysis,fault_diagnosis)")
    p.add_argument("--subset", action="append", default=[], metavar="NAME=ATTR:A,B[,C...]",
                   help="the attribute on these classes only, reported as NAME (repeatable)")
    p.add_argument("--reference", default=None,
                   help="paper2_round2.json: C2's within-session figures of the same view (section a7) beside each row")
    p.add_argument("--permutations", type=int, default=99)
    p.add_argument("--n-boot", type=int, default=1000, dest="n_boot")
    p.add_argument("--margin", type=float, default=0.05)
    p.add_argument("--alpha", type=float, default=0.05)
    p.add_argument("--jobs", type=int, default=-1)
    p.add_argument("--out", required=True, help="path without extension")
    p.add_argument("--keep-shared", action="store_true", dest="keep_shared",
                   help="keep test traces whose prompt also occurs in the training side")
    p.add_argument("--allow-dirty", action="store_true", dest="allow_dirty")
    a = p.parse_args(argv)
    out = Path(a.out)
    for ext in (".json", ".md"):
        if out.with_suffix(ext).exists():
            raise SystemExit(f"{out.with_suffix(ext)} exists: results are not written over")
    t0 = time.perf_counter()
    git = _git()
    if git["git_dirty"] is not False and not a.allow_dirty:
        raise SystemExit("uncommitted code: commit first (or --allow-dirty for a dry run)")
    subs = subsets(a.pair, a.subset)
    train, test = side(a.train, a.train_rounds), side(a.test, a.test_rounds)
    if train["view"] != test["view"]:
        raise SystemExit(f"the sides are of different views: {train['view']} and {test['view']}")
    ref = reference(a.reference, train["view"]) if a.reference else None
    res = {"paper": "P2", "round": 2, "check": "B3 cross-session transfer", "seed": SEED, **git, "view": train["view"],
           "collection_id": {"train": train["collection_id"], "test": test["collection_id"]},
           "data_dir": {"train": train["data_dir"], "test": test["data_dir"]},
           "train": {k: train[k] for k in ("folder", "rounds", "meta")}, "test": {k: test[k] for k in ("folder", "rounds", "meta")},
           "parameters": {**{k: getattr(a, k) for k in ("permutations", "n_boot", "margin", "alpha", "keep_shared")},
                          "subsets": {n: {"attribute": at, "classes": cl} for n, at, cl in subs}},
           "reference": ref, "attributes": {}}
    for attr in [x.strip() for x in a.attributes.split(",") if x.strip()]:
        res["attributes"][attr] = transfer(train, test, attr, a)
        print(f"[{attr}] {_row(attr, res['attributes'][attr], ref)}", flush=True)
    for nm, attr, cl in subs:
        res["attributes"][nm] = transfer(train, test, attr, a, cl)
        print(f"[{nm}] {_row(nm, res['attributes'][nm], ref)}", flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    res["runtime_s"] = time.perf_counter() - t0
    out.with_suffix(".json").write_text(json.dumps(res, indent=1))
    L = [f"# Cross-session transfer, view {train['view']}: {train['collection_id']} ({a.train_rounds or 'all'}) → "
         f"{test['collection_id']} ({a.test_rounds or 'all'})", "",
         f"Commit `{(git['git_commit'] or '')[:8]}` (clean: {git['git_dirty'] is False}); seed {SEED}; train {train['collection_id']} "
         f"(`{train['data_dir']}`, features `{a.train}`), test {test['collection_id']} (`{test['data_dir']}`, features `{a.test}`). "
         f"Test traces whose prompt also occurs in the training side are "
         f"{'kept' if a.keep_shared else 'dropped'}.", "",
         "| Attribute | train n | test n (shared dropped) | transfer macro-F1 [95% CI] | p | verdict | within the test session "
         "| C2 within (a7) |", "|---|---|---|---|---|---|---|---|"]
    for k, r in res["attributes"].items():
        L.append(_row(k, r, ref, table=True))
    if ref:
        L += ["", f"C2 within: `{ref['source']}` section a7, lan_{ref['view']}, seed 42 (commit {str(ref['git_commit'])[:8]}, "
              f"clean: {ref['clean']})."]
    out.with_suffix(".md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


def _ci(x: dict) -> str:
    f = lambda v: "-" if v is None else f"{v:.3f}"  # noqa: E731
    return f"{f(x.get('macro_f1'))} [{f(x['ci'][0])}, {f(x['ci'][1])}]"


def _row(name: str, r: dict, ref: dict | None, table: bool = False) -> str:
    t, w = r["transfer"], r["within_test"]
    c = (ref or {}).get("tasks", {}).get(name)
    cref = f"{c['verdict']} {_ci(c)}" if c else "-"
    if table:
        return (f"| {name} | {r['train']['n']} | {r['test']['n']} ({r['test']['dropped_shared']}) | {_ci(t)} | {t['p']:.2f} | "
                f"{t['verdict']} | {w['verdict']} {_ci(w)} | {cref} |")
    return (f"transfer {t['verdict']} {_ci(t)} p {t['p']:.2f}; within the test side {w['verdict']} {_ci(w)}; "
            f"C2 within {cref} ({r['seconds']:.0f} s)")


if __name__ == "__main__":
    sys.exit(main())
