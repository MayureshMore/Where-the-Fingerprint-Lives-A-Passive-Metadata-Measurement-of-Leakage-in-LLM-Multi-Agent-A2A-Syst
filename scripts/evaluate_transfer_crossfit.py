#!/usr/bin/env python3
"""
Prompt-disjoint re-analysis of the cross-collection transfers.

Deployments A, A-model, B-logic, B and C (LangGraph) and the WAN capture were
collected with the same prompt seeds, so a transfer that trains on all of one
collection and tests on all of another tests on prompts it trained on, and the
request sizes those prompts fix are identical on both sides. Each transfer is
re-run here three ways, with the same classifier (RF, seed 42) and the same
loader as the script that produced the published number:

  full          train on all source traces (the published protocol; reproduces it)
  size_matched  per target fold, drop as many source prompt groups as crossfit
                does, but chosen at random among groups NOT in the fold
  crossfit      per target fold (5 StratifiedGroupKFold folds by prompt_group),
                train only on source traces of the OTHER prompts

full → size_matched is the cost of the smaller training set; size_matched →
crossfit is the shared-prompt effect. Intervals: cluster bootstrap over the
target's prompt groups (2000 resamples, seed 42).

Usage:
    python scripts/evaluate_transfer_crossfit.py     # → data/results/transfer_crossfit.json
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation.crossfit import crossfit_predict, shared_prompt_fraction  # noqa: E402
from evaluation.stats import bootstrap_ci  # noqa: E402
from models.random_forest import RFClassifier  # noqa: E402
from scripts import evaluate_cross_network, evaluate_defense_live, evaluate_model_vs_logic  # noqa: E402
from scripts.evaluate_cross_deployment import load_deployment  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

A, AMODEL, BLOGIC, B = "data/processed", "data/processed_amodel_sdk", "data/processed_blogic_sdk", "data/processed_b_sdk"
C, WAN = "data/processed_langgraph", "data/processed_wan"
RATE, PAD = "data/processed_defense_rate", "data/processed_defense_pad"


class _DefenseRF:
    """The defense script's own RF (random_state=0), behind the RFClassifier interface."""

    def __init__(self, task=None):
        self.clf = evaluate_defense_live._rf()

    def fit(self, X, y):
        self.clf.fit(X, np.asarray(y))
        return self

    def predict(self, X):
        return self.clf.predict(X)


def _mvl(d, task):
    X, y, g = evaluate_model_vs_logic._load(Path(d), task)
    return X, y, g


def _xdep(d, task):
    X, _, y, g = load_deployment(Path(d), task)
    return X, y, g


def _c5(d, task):
    X, y, g = evaluate_cross_network._load(Path(d), task)
    return X, y, g


# (result file, key, source, target, loader, tasks, how to read the published value[, classifier])
TRANSFERS = [
    ("model_vs_logic.json", "A_Amodel", A, AMODEL, _mvl, ("workflow", "role"), lambda r, t, k: r[t][k]["macro_f1"]),
    ("model_vs_logic.json", "A_Blogic", A, BLOGIC, _mvl, ("workflow", "role"), lambda r, t, k: r[t][k]["macro_f1"]),
    ("cross_deployment.json", "AB", A, B, _xdep, ("workflow", "role", "parallelism", "topology"),
     lambda r, t, k: r[f"{t}/{k}"]["macro_f1"]),
    ("cross_deployment.json", "BA", B, A, _xdep, ("workflow", "role", "parallelism", "topology"),
     lambda r, t, k: r[f"{t}/{k}"]["macro_f1"]),
    ("cross_framework.json", "AB", A, C, _xdep, ("workflow", "role", "parallelism", "topology"),
     lambda r, t, k: r[f"{t}/{k}"]["macro_f1"]),
    ("cross_framework.json", "BA", C, A, _xdep, ("workflow", "role", "parallelism", "topology"),
     lambda r, t, k: r[f"{t}/{k}"]["macro_f1"]),
    ("cross_network.json", "transfer", A, WAN, _c5, ("workflow", "role", "parallelism", "topology"),
     lambda r, t, k: r[t][k]["f1"]),
    ("defense/defense_live.json", "rate", A, RATE, _xdep, ("workflow",), lambda r, t, k: r[k]["macro_f1"], _DefenseRF),
    ("defense/defense_live.json", "pad", A, PAD, _xdep, ("workflow",), lambda r, t, k: r[k]["macro_f1"], _DefenseRF),
]


def _score(y_te, pred, g_te, classes) -> dict:
    ci = bootstrap_ci(list(y_te), list(pred), classes=classes, groups=list(g_te))
    return {"macro_f1": ci["macro_f1"], "ci_lo": ci["macro_f1_ci_lo"], "ci_hi": ci["macro_f1_ci_hi"],
            "accuracy": ci["accuracy"]}


def run_one(src, tgt, loader, task, clf=RFClassifier) -> dict:
    Xs, ys, gs = loader(src, task)
    Xt, yt, gt = loader(tgt, task)
    classes = sorted(set(ys) | set(yt))
    make = lambda: clf(task=task)  # noqa: E731
    full = make().fit(Xs, list(ys)).predict(Xt)
    out = {
        "n_source": len(ys), "n_target": len(yt), "chance": 1.0 / len(set(yt)),
        "shared_prompt_fraction": shared_prompt_fraction(gs, gt),
        "full": _score(yt, full, gt, classes),
        "size_matched": _score(yt, crossfit_predict(make, Xs, ys, gs, Xt, yt, gt, size_matched=True), gt, classes),
        "crossfit": _score(yt, crossfit_predict(make, Xs, ys, gs, Xt, yt, gt), gt, classes),
    }
    out["shared_prompt_effect"] = out["size_matched"]["macro_f1"] - out["crossfit"]["macro_f1"]
    return out


def main() -> None:
    res_dir = Path(os.environ.get("A2A_RESULTS_DIR", "data/results"))
    out = {
        "task": "Prompt-disjoint re-analysis of cross-collection transfers",
        "method": "Same RF and loader as the published transfer. full = train on all source "
                  "(published protocol); crossfit = per target fold (StratifiedGroupKFold by "
                  "prompt_group, 5 folds, seed 42) train only on source traces of other prompts; "
                  "size_matched = drop the same number of source groups at random among groups not "
                  "in the fold. macro-F1 with cluster (group) bootstrap 95% CI over target prompt groups.",
        "results": {},
    }
    canon = Path("data/results")
    for fname, key, src, tgt, loader, tasks, published, *clf in TRANSFERS:
        if not (Path(src, "labels.json").exists() and Path(tgt, "labels.json").exists()):
            print(f"skip {fname}:{key} ({src} or {tgt} missing)")
            continue
        pub = json.loads((canon / fname).read_text()) if (canon / fname).exists() else None
        for task in tasks:
            try:
                r = run_one(src, tgt, loader, task, *clf)
            except (ValueError, KeyError) as e:
                print(f"skip {fname}:{key}:{task} ({e})")
                continue
            try:
                r["published"] = float(published(pub, task, key)) if pub else None
            except (KeyError, TypeError):
                r["published"] = None
            name = f"{Path(fname).stem}/{key}/{task}"
            r.update({"source": src, "target": tgt})
            out["results"][name] = r
            print(f"{name:<38} shared {r['shared_prompt_fraction']:.2f}  published "
                  f"{r['published'] if r['published'] is None else round(r['published'], 3)}  full "
                  f"{r['full']['macro_f1']:.3f}  size-matched {r['size_matched']['macro_f1']:.3f}  "
                  f"crossfit {r['crossfit']['macro_f1']:.3f} [{r['crossfit']['ci_lo']:.3f}, "
                  f"{r['crossfit']['ci_hi']:.3f}]  chance {r['chance']:.3f}")
    res_dir.mkdir(parents=True, exist_ok=True)
    (res_dir / "transfer_crossfit.json").write_text(json.dumps(out, indent=2))
    print(f"→ {res_dir / 'transfer_crossfit.json'}")


if __name__ == "__main__":
    main()
