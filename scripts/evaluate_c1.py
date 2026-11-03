#!/usr/bin/env python3
"""
P1 evaluation of collection C1 (deployment A, llama3.2:3b, TLS on every agent link, one session,
5 balanced rounds, 50 traces per topology × workflow).

For role, workflow and topology:

  1. closed world      GBT (headline) and RF on the metadata features, 5-fold
                       StratifiedGroupKFold by prompt_group (the same folds for every model)
  2. temporal holdout  train on rounds 1–3, test on rounds 4–5; every training trace whose
                       prompt occurs in the test rounds is dropped, so the test is prompt-disjoint
  3. feature ablation  GBT on sizes only, timing only, counts and direction only (same folds)
  4. k-FP baseline     Hayes & Danezis k-FP features (direction and timing; features/kfp.py)
                       with k-FP's random forest (1000 trees), same folds

and for workflow, from the GBT closed-world predictions:

  5. confusion matrix  counts and row-normalized, with a figure
  6. per topology      workflow macro-F1 on the star, chain and mesh traces separately
  7. vs TLS control    per-workflow F1 on C1 next to the TLS control's TLS arm (its within-TLS CV
                       recomputed with that script's folds), and the prompt mix of the two sets
  8. input length      workflow from the size of the first request into the system alone, and
                       from the true prompt length alone (same folds, paired against all features)
  9. response side     workflow with every size feature that uses request-direction bytes removed
 10. length pairs      binary code_review vs data_analysis and research_retrieval vs support_triage
                       (the long- and short-prompt workflows), chance 0.5

and for role: every per-flow feature alone (top 5 with CIs), response-side sizes only and
request-side sizes only, paired against all features.

macro-F1 with 95% cluster-bootstrap CIs over prompt groups (2000 resamples, seed 42). Model
comparisons are paired: the difference in macro-F1 is bootstrapped over the same group resamples,
and a difference counts only when its CI excludes 0. Ports are never features.

The run stops unless C1's capture checks passed (tls_check.json ok, no topology with cut streams).

Usage:
    python scripts/evaluate_c1.py
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from sklearn.base import clone
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import confusion_matrix, f1_score, precision_recall_fscore_support
from sklearn.model_selection import StratifiedGroupKFold

sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation.stats import bootstrap_ci, paired_bootstrap_diff  # noqa: E402
from features.families import (  # noqa: E402
    _PF_REQUEST_SIZES, _PF_RESPONSE_SIZES, FAMILIES, _check_partition, family_columns,
    response_side_columns,
)
from features.first_request import FIRST_REQUEST_DEF, first_request_bytes  # noqa: E402
from features.kfp import N_KFP, kfp_features, packets_from_pcap  # noqa: E402
from features.per_flow import PerFlowFeatures  # noqa: E402
from features.per_system import PerSystemFeatures  # noqa: E402
from models.gradient_boosted import GBTClassifier  # noqa: E402
from models.random_forest import RFClassifier  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TASKS = ("role", "workflow", "topology")
SEED = 42
N_BOOT = 2000
TRAIN_ROUNDS, TEST_ROUNDS = (0, 1, 2), (3, 4)

TOP_SINGLE = 5
LENGTH_PAIRS = (("code_review", "data_analysis"), ("research_retrieval", "support_triage"))
# trace vector: per-flow blocks (mean, heaviest, 2nd heaviest flow) vs system-wide aggregates
AGGREGATES = {"per_flow": np.arange(0, 105), "system": np.arange(105, 195)}
LEARNING_FRACTIONS = (0.1, 0.25, 0.5, 0.75, 1.0)


# ── data ────────────────────────────────────────────────────────────────────

def load(processed: Path, raw: Path, task: str) -> dict:
    labels = json.loads((processed / "labels.json").read_text())
    rows = []
    for rid, info in sorted(labels.items()):
        is_role = "__role__" in rid
        if (task == "role") != is_role or info.get(task) is None:
            continue
        base, _, port = rid.partition("__role__")
        side = json.loads((raw / f"{base}.json").read_text())
        flat = np.load(processed / f"{rid}.npz")["flat"].astype(np.float32)
        rows.append((rid, base, int(port) if port else None, flat, info[task],
                     str(info["prompt_group"]), int(side.get("round", -1)), side["agent_endpoints"],
                     info.get("topology"), len(side.get("input_prompt", ""))))
    rid, base, port, flat, y, g, rnd, eps, top, plen = zip(*rows)
    return {"run_id": list(rid), "base": list(base), "port": list(port), "X": np.stack(flat),
            "y": np.array(y), "g": np.array(g), "round": np.array(rnd), "endpoints": list(eps),
            "topology": np.array(top), "prompt_len": np.array(plen)}


def kfp_matrix(d: dict, raw: Path) -> np.ndarray:
    cache: dict[str, list] = {}
    rows = []
    for base, port, eps in zip(d["base"], d["port"], d["endpoints"]):
        if base not in cache:
            cache[base] = packets_from_pcap(raw / f"{base}.pcap")
        servers = {int(a.rsplit(":", 1)[1]) for a in eps.values()}
        t, dirs = [], []
        for ts, sp, dp, _ in cache[base]:
            if port is not None and port not in (sp, dp):
                continue
            if dp in servers:
                t.append(ts); dirs.append(1)
            elif sp in servers:
                t.append(ts); dirs.append(-1)
        rows.append(kfp_features(t, dirs))
    return np.stack(rows)


# ── models, folds, scoring ──────────────────────────────────────────────────

def make_model(name: str, task: str):
    if name == "gbt":
        return clone(GBTClassifier(task=task).pipeline)
    if name == "rf":
        return clone(RFClassifier(task=task).pipeline)
    if name == "kfp":
        return RandomForestClassifier(n_estimators=1000, n_jobs=-1, random_state=SEED)
    raise ValueError(name)


def folds(y, g):
    return list(StratifiedGroupKFold(5, shuffle=True, random_state=SEED).split(np.zeros(len(y)), y, g))


def oof_predict(model: str, task: str, X, y, splits) -> np.ndarray:
    pred = np.empty(len(y), dtype=object)
    for tr, te in splits:
        pred[te] = make_model(model, task).fit(X[tr], y[tr]).predict(X[te])
    return pred


def oof_predict_size_matched(model: str, task: str, X, y, g, splits, n_train: int) -> np.ndarray:
    """The same group folds, but each fold trains on whole prompt groups drawn at random until
    n_train traces: the temporal holdout's training size without its time gap."""
    rng = np.random.default_rng(SEED)
    pred = np.empty(len(y), dtype=object)
    for tr, te in splits:
        groups = rng.permutation(np.unique(g[tr]))
        sizes = np.array([(g[tr] == u).sum() for u in groups])
        keep = groups[:int(np.searchsorted(np.cumsum(sizes), n_train)) + 1]
        sub = tr[np.isin(g[tr], keep)]
        pred[te] = make_model(model, task).fit(X[sub], y[sub]).predict(X[te])
    return pred


def score(y, pred, g, classes) -> dict:
    ci = bootstrap_ci(list(y), list(pred), classes=classes, groups=list(g), n=N_BOOT, seed=SEED)
    return {"macro_f1": ci["macro_f1"], "ci_lo": ci["macro_f1_ci_lo"], "ci_hi": ci["macro_f1_ci_hi"],
            "accuracy": ci["accuracy"], "n": int(len(y)), "ci_method": ci["ci_method"],
            "ci_n_clusters": ci["n_clusters"]}


def paired_diff(y, pa, pb, g, classes) -> dict:
    """macro-F1(a) − macro-F1(b), group bootstrap over the same resamples for both."""
    f1 = lambda t, p: f1_score(t, p, labels=classes, average="macro", zero_division=0)  # noqa: E731
    return paired_bootstrap_diff(y, pa, pb, g, f1, n=N_BOOT, seed=SEED)


def _boot_class_f1(y, pred, g, classes, rng) -> np.ndarray:
    """(N_BOOT, n_classes) per-class F1 over group-bootstrap resamples."""
    uniq = np.unique(g)
    idx_by = {u: np.where(g == u)[0] for u in uniq}
    out = np.empty((N_BOOT, len(classes)))
    for i in range(N_BOOT):
        idx = np.concatenate([idx_by[u] for u in rng.choice(uniq, len(uniq), replace=True)])
        out[i] = f1_score(y[idx], pred[idx], labels=classes, average=None, zero_division=0)
    return out


def per_class(y, pred, g, classes) -> tuple[dict, np.ndarray]:
    """Per-class precision, recall and F1, with a group-bootstrap 95% CI on F1."""
    y, pred, g = (np.asarray(v) for v in (y, pred, g))
    p, r, f, n = precision_recall_fscore_support(y, pred, labels=classes, zero_division=0)
    boot = _boot_class_f1(y, pred, g, classes, np.random.default_rng(SEED))
    lo, hi = np.percentile(boot, [2.5, 97.5], axis=0)
    return ({c: {"f1": float(f[i]), "ci_lo": float(lo[i]), "ci_hi": float(hi[i]),
                 "precision": float(p[i]), "recall": float(r[i]), "support": int(n[i])}
             for i, c in enumerate(classes)}, boot)


def prompt_mix(a: dict, b: dict, classes) -> dict:
    """Per workflow: how the prompts of trace sets a and b differ (prompt_group = sha1 of the prompt)."""
    out = {}
    for c in classes:
        ga, gb = a["g"][a["y"] == c], b["g"][b["y"] == c]
        ua, ca = np.unique(ga, return_counts=True)
        ub, cb = np.unique(gb, return_counts=True)
        pa, pb = dict(zip(ua, ca / ca.sum())), dict(zip(ub, cb / cb.sum()))
        shared = set(ua) & set(ub)
        out[c] = {"n_a": int(len(ga)), "n_b": int(len(gb)),
                  "distinct_a": int(len(ua)), "distinct_b": int(len(ub)), "shared_distinct": len(shared),
                  "traces_a_with_shared_prompt": float(np.isin(ga, list(shared)).mean()),
                  "traces_b_with_shared_prompt": float(np.isin(gb, list(shared)).mean()),
                  "total_variation": float(0.5 * sum(abs(pa.get(u, 0) - pb.get(u, 0)) for u in set(pa) | set(pb))),
                  "median_prompt_chars_a": float(np.median(a["prompt_len"][a["y"] == c])),
                  "median_prompt_chars_b": float(np.median(b["prompt_len"][b["y"] == c]))}
    return out


def tls_control_oof(d: dict) -> np.ndarray:
    """The TLS control's within-TLS GBT CV (GBTClassifier.cross_validate: unshuffled
    StratifiedGroupKFold(5) by prompt_group), returning its out-of-fold predictions. Scored here
    on the pooled predictions; tls_control.json reports the mean of the five fold scores."""
    classes = sorted(set(d["y"].tolist()))
    y_enc = np.searchsorted(classes, d["y"])
    pred = np.empty(len(d["y"]), dtype=object)
    for tr, te in StratifiedGroupKFold(5).split(d["X"], y_enc, d["g"]):
        pred[te] = make_model("gbt", "workflow").fit(d["X"][tr], d["y"][tr]).predict(d["X"][te])
    return pred


def workflow_detail(d: dict, pred: np.ndarray, classes, tls: tuple[Path, Path] | None) -> dict:
    y, g = d["y"], d["g"]
    cm = confusion_matrix(y, pred, labels=classes)
    pc, boot_c1 = per_class(y, pred, g, classes)
    res = {"classes": classes,
           "confusion": {"counts": cm.tolist(), "row_normalized": (cm / cm.sum(1, keepdims=True)).tolist(),
                         "rows": "true", "columns": "predicted"},
           "per_class": pc,
           "per_topology": {t: score(y[d["topology"] == t], pred[d["topology"] == t],
                                     g[d["topology"] == t], classes)
                            for t in sorted(set(d["topology"].tolist()))}}
    if tls is None:
        res["vs_tls_control"] = None
        return res
    t = load(tls[0], tls[1], "workflow")
    tpred = tls_control_oof(t)
    tpc, boot_tls = per_class(t["y"], tpred, t["g"], classes)
    diff = boot_c1 - boot_tls                       # independent sets: independent resamples
    lo, hi = np.percentile(diff, [2.5, 97.5], axis=0)
    shared = np.isin(g, np.unique(t["g"]))
    res["vs_tls_control"] = {
        "tls_processed": str(tls[0]), "tls_raw": str(tls[1]),
        "tls_macro_f1": score(t["y"], tpred, t["g"], classes),
        "tls_per_class": tpc,
        "c1_minus_tls": {c: {"diff": pc[c]["f1"] - tpc[c]["f1"], "ci_lo": float(lo[i]),
                             "ci_hi": float(hi[i]), "significant": bool(lo[i] > 0 or hi[i] < 0)}
                         for i, c in enumerate(classes)},
        "prompt_mix": prompt_mix(d, t, classes),
        "c1_by_prompt_overlap": {"shared_with_tls": score(y[shared], pred[shared], g[shared], classes),
                                 "c1_only": score(y[~shared], pred[~shared], g[~shared], classes)},
        "note": "a = C1, b = TLS control TLS arm; per-class difference CIs from independent group "
                "bootstraps of the two sets",
    }
    return res


def _sub_splits(splits, mask: np.ndarray):
    """The same folds restricted to the rows in mask, as indices into the subset."""
    pos = np.full(len(mask), -1)
    pos[mask] = np.arange(mask.sum())
    return [(pos[tr[mask[tr]]], pos[te[mask[te]]]) for tr, te in splits]


def length_checks(d: dict, raw: Path, pred_all: np.ndarray, splits, classes) -> dict:
    y, g = d["y"], d["g"]
    first = np.array([first_request_bytes(raw / f"{b}.pcap", {int(a.rsplit(":", 1)[1]) for a in e.values()})
                      for b, e in zip(d["base"], d["endpoints"])], dtype=np.float32)
    chars = d["prompt_len"].astype(np.float32)
    single = {"first_request_bytes": first[:, None], "prompt_chars": chars[:, None]}
    res = {"first_request": {
        "definition": FIRST_REQUEST_DEF,
        "n_zero": int((first == 0).sum()),
        "pearson_with_prompt_chars": float(np.corrcoef(first, chars)[0, 1]),
        "median_by_workflow": {c: {"first_request_bytes": float(np.median(first[y == c])),
                                   "prompt_chars": float(np.median(chars[y == c])),
                                   "overhead": float(np.median(first[y == c] - chars[y == c]))}
                               for c in classes}}}
    for name, X1 in single.items():
        p = oof_predict("gbt", "workflow", X1, y, splits)
        res[name] = {**score(y, p, g, classes), "all_minus_this": paired_diff(y, pred_all, p, g, classes)}
    cols = response_side_columns()
    p = oof_predict("gbt", "workflow", d["X"][:, cols], y, splits)
    res["response_side_only"] = {**score(y, p, g, classes), "dims": int(len(cols)),
                                 "all_minus_this": paired_diff(y, pred_all, p, g, classes)}
    res["pairs"] = {}
    for a, b in LENGTH_PAIRS:
        m = np.isin(y, [a, b])
        sub, pc = _sub_splits(splits, m), [a, b]
        ym, gm = y[m], g[m]
        pa = oof_predict("gbt", "workflow", d["X"][m], ym, sub)
        r = {"chance": 0.5, "n": int(m.sum()), "all": score(ym, pa, gm, pc)}
        for name, X1 in single.items():
            p1 = oof_predict("gbt", "workflow", X1[m], ym, sub)
            r[name] = {**score(ym, p1, gm, pc), "all_minus_this": paired_diff(ym, pa, p1, gm, pc)}
        res["pairs"][f"{a}_vs_{b}"] = r
    return res


def role_checks(d: dict, pred_all: np.ndarray, splits, classes) -> dict:
    """Role (one flow per sample): each per-flow feature alone, and one direction's sizes alone."""
    y, g, X = d["y"], d["g"], d["X"]
    names = PerFlowFeatures.FEATURE_NAMES()
    f1 = {n: float(f1_score(y, oof_predict("gbt", "role", X[:, [i]], y, splits), labels=classes,
                            average="macro", zero_division=0)) for i, n in enumerate(names)}
    ranked = sorted(names, key=lambda n: -f1[n])
    res = {"single_feature_macro_f1": dict(sorted(f1.items(), key=lambda kv: -kv[1])),
           "note": f"top {TOP_SINGLE} chosen on these folds out of {len(names)} features, so their "
                   "scores are optimistic", "top": []}
    for n in ranked[:TOP_SINGLE]:
        p = oof_predict("gbt", "role", X[:, [names.index(n)]], y, splits)
        res["top"].append({"feature": n, **score(y, p, g, classes),
                           "all_minus_this": paired_diff(y, pred_all, p, g, classes)})
    for key, fset in (("response_sizes_only", _PF_RESPONSE_SIZES), ("request_sizes_only", _PF_REQUEST_SIZES)):
        cols = [i for i, n in enumerate(names) if n in fset]
        p = oof_predict("gbt", "role", X[:, cols], y, splits)
        res[key] = {**score(y, p, g, classes), "features": [names[i] for i in cols],
                    "all_minus_this": paired_diff(y, pred_all, p, g, classes)}
    return res


def temporal(task: str, d: dict, model: str, classes) -> dict:
    tr_all = np.isin(d["round"], TRAIN_ROUNDS)
    te = np.isin(d["round"], TEST_ROUNDS)
    test_groups = np.unique(d["g"][te])
    tr = tr_all & ~np.isin(d["g"], test_groups)
    pred = make_model(model, task).fit(d["X"][tr], d["y"][tr]).predict(d["X"][te])
    r = score(d["y"][te], pred, d["g"][te], classes)
    r.update({"n_train": int(tr.sum()), "n_train_before_prompt_removal": int(tr_all.sum()),
              "train_classes": sorted(set(d["y"][tr].tolist())),
              "train_rounds": [x + 1 for x in TRAIN_ROUNDS], "test_rounds": [x + 1 for x in TEST_ROUNDS]})
    return r


# ── provenance and capture checks ───────────────────────────────────────────

def _git() -> dict:
    """Commit, and whether the code differs from it. Changes under data/ (results written by
    earlier runs) do not count, so several result scripts can run one after another."""
    def run(*a):
        return subprocess.run(["git", *a], capture_output=True, text=True).stdout.strip()
    return {"git_commit": run("rev-parse", "HEAD"),
            "git_dirty": bool(run("status", "--porcelain", "--", ".", ":(exclude)data"))}


def capture_checks(raw: Path) -> dict:
    tls = json.loads((raw / "tls_check.json").read_text())
    streams = json.loads((raw / "stream_integrity.json").read_text())["sets"]
    per_top = {t: {"median_largest_reply_pkts": s["median_largest_reply_pkts"], "share_cut": s["share_cut"]}
               for tops in streams.values() for t, s in tops.items()}
    ok = bool(tls.get("ok")) and all(s["share_cut"] <= 0.05 for s in per_top.values())
    return {"ok": ok, "tls_ok": bool(tls.get("ok")), "n_traces": tls.get("n_traces"),
            "tls_handshakes_per_connection": tls.get("tls_handshakes_per_connection"),
            "streams": per_top}


# ── main ────────────────────────────────────────────────────────────────────

def main(a: argparse.Namespace) -> None:
    _check_partition()
    processed, raw = Path(a.processed), Path(a.raw)
    checks = capture_checks(raw)
    if not checks["ok"]:
        raise SystemExit(f"C1 capture checks failed — not evaluating: {checks}")
    meta = json.loads((raw / "session_meta.json").read_text())

    out = {
        "paper": "P1", "collection_id": meta.get("collection_id", "C1"),
        "data_dir": str(processed), "raw_dir": str(raw), "seed": SEED, **_git(),
        "method": "GBT headline, RF baseline; 5-fold StratifiedGroupKFold by prompt_group "
                  "(shuffle, seed 42), identical folds for every model and ablation; temporal "
                  "holdout trains on rounds 1–3 minus every prompt seen in rounds 4–5; macro-F1 with "
                  "95% cluster bootstrap over prompt groups (2000 resamples); model comparisons "
                  "are paired group-bootstrap differences. Ports never features.",
        "session": {k: meta.get(k) for k in ("design", "arms", "num_predict", "n_per_condition", "rounds",
                                             "seed_offset", "started", "finished", "failures",
                                             "complete_items")},
        "capture_checks": checks,
        "feature_families": {f: {"trace_dims": int(len(family_columns(f, False))),
                                 "role_dims": int(len(family_columns(f, True)))} for f in FAMILIES},
        "kfp": {"dims": N_KFP, "classifier": "RandomForest, 1000 trees (k-FP closed world)",
                "uses": "packet direction and timing only"},
        "results": {},
    }
    tls = (Path(a.tls_processed), Path(a.tls_raw))
    if not ((tls[0] / "labels.json").exists() and tls[1].is_dir()):
        logger.warning("TLS control set not found (%s, %s): skipping the comparison", *tls)
        tls = None
    for task in TASKS:
        d = load(processed, raw, task)
        X, y, g = d["X"], d["y"], d["g"]
        classes = sorted(set(y.tolist()))
        splits = folds(y, g)
        logger.info("[%s] n=%d, %d prompt groups, classes %s", task, len(y), len(set(g)), classes)
        preds = {m: oof_predict(m, task, X, y, splits) for m in ("gbt", "rf")}
        Xk = kfp_matrix(d, raw)
        preds["kfp"] = oof_predict("kfp", task, Xk, y, splits)
        res = {
            "chance": 1.0 / len(classes), "n": int(len(y)), "n_prompt_groups": int(len(set(g))),
            "classes": classes,
            "closed_world": {"gbt": score(y, preds["gbt"], g, classes),
                             "rf": score(y, preds["rf"], g, classes)},
            "kfp": score(y, preds["kfp"], g, classes),
            "temporal": {m: temporal(task, d, m, classes) for m in ("gbt", "rf")},
            "ablation": {},
            "size_matched_cv": {},
            "aggregates": {},
            "learning_curve": [],
            "paired": {"gbt_minus_rf": paired_diff(y, preds["gbt"], preds["rf"], g, classes),
                       "gbt_minus_kfp": paired_diff(y, preds["gbt"], preds["kfp"], g, classes)},
        }
        for m in ("gbt", "rf"):
            n_tr = res["temporal"][m]["n_train"]
            p = oof_predict_size_matched(m, task, X, y, g, splits, n_tr)
            res["size_matched_cv"][m] = {**score(y, p, g, classes), "n_train_per_fold": n_tr}
        for fam in FAMILIES:
            cols = family_columns(fam, task == "role")
            p = oof_predict("gbt", task, X[:, cols], y, splits)
            res["ablation"][fam] = score(y, p, g, classes)
            res["ablation"][fam]["dims"] = int(len(cols))
            res["ablation"][fam]["all_minus_this"] = paired_diff(y, preds["gbt"], p, g, classes)
        if task != "role":                       # a role sample is one flow: no system aggregates
            for agg, cols in AGGREGATES.items():
                p = oof_predict("gbt", task, X[:, cols], y, splits)
                res["aggregates"][agg] = {**score(y, p, g, classes), "dims": int(len(cols)),
                                          "all_minus_this": paired_diff(y, preds["gbt"], p, g, classes)}
        full = int(np.mean([len(tr) for tr, _ in splits]))
        for frac in LEARNING_FRACTIONS:
            n_tr = int(round(frac * full))
            p = (preds["gbt"] if frac == 1.0 else
                 oof_predict_size_matched("gbt", task, X, y, g, splits, n_tr))
            res["learning_curve"].append({**score(y, p, g, classes), "fraction": frac, "n_train": n_tr,
                                          "train_per_class": round(n_tr / len(classes), 1)})
        if task == "role":
            res["single_feature"] = role_checks(d, preds["gbt"], splits, classes)
        if task == "workflow":
            res["detail"] = workflow_detail(d, preds["gbt"], classes, tls)
            res["length_checks"] = length_checks(d, raw, preds["gbt"], splits, classes)
        out["results"][task] = res
        cw = res["closed_world"]
        logger.info("[%s] GBT %.3f RF %.3f kFP %.3f temporal-GBT %.3f | sizes %.3f timing %.3f counts %.3f",
                    task, cw["gbt"]["macro_f1"], cw["rf"]["macro_f1"], res["kfp"]["macro_f1"],
                    res["temporal"]["gbt"]["macro_f1"], *(res["ablation"][f]["macro_f1"] for f in FAMILIES))

    out_dir = Path(os.environ.get("A2A_RESULTS_DIR", "data/results"))
    (out_dir / "figures").mkdir(parents=True, exist_ok=True)
    (out_dir / "c1_evaluation.json").write_text(json.dumps(out, indent=2))
    write_report(out, out_dir / "c1_evaluation.md")
    make_figure(out, out_dir / "figures" / "c1_evaluation.png")
    make_confusion_figure(out, out_dir / "figures" / "c1_workflow_confusion.png")
    logger.info("wrote %s", out_dir / "c1_evaluation.json")


def _cell(r: dict) -> str:
    return f"{r['macro_f1']:.3f} [{r['ci_lo']:.3f}, {r['ci_hi']:.3f}]"


def _diff(r: dict) -> str:
    return f"{r['diff']:+.3f} [{r['ci_lo']:+.3f}, {r['ci_hi']:+.3f}]{'' if r['significant'] else ' (n.s.)'}"


def write_report(out: dict, path: Path) -> None:
    R = out["results"]
    s, c = out["session"], out["capture_checks"]
    L = ["# C1 evaluation (P1)", "",
         f"Collection {out['collection_id']}: deployment A, llama3.2:3b, TLS on every agent link, one "
         f"session ({s['started']} → {s['finished']}), {s['complete_items']} traces in {s['rounds']} "
         f"balanced rounds, {s['failures']} failed attempts. Data `{out['data_dir']}`, commit "
         f"`{out['git_commit'][:8]}`{' (uncommitted changes)' if out['git_dirty'] else ''}, seed {out['seed']}.",
         "", f"Capture checks: TLS record check {'passed' if c['tls_ok'] else 'FAILED'} "
         f"({c['tls_handshakes_per_connection']} handshakes per connection); median largest specialist "
         "reply " + ", ".join(f"{t} {v['median_largest_reply_pkts']:g} pkts ({v['share_cut']:.0%} cut)"
                              for t, v in sorted(c["streams"].items())) + ".",
         "", "macro-F1 with 95% cluster-bootstrap CIs over prompt groups. Same 5 group folds for every "
         "row except the temporal holdout.", "",
         "## Closed world, temporal holdout, k-FP", "",
         "| Task | Chance | n (groups) | GBT | RF | k-FP | Temporal GBT | Temporal RF |",
         "|---|---|---|---|---|---|---|---|"]
    for t, r in R.items():
        L.append(f"| {t} | {r['chance']:.3f} | {r['n']} ({r['n_prompt_groups']}) | "
                 f"{_cell(r['closed_world']['gbt'])} | {_cell(r['closed_world']['rf'])} | {_cell(r['kfp'])} | "
                 f"{_cell(r['temporal']['gbt'])} | {_cell(r['temporal']['rf'])} |")
    L += ["", "Temporal holdout: train rounds 1–3, test rounds 4–5; training traces whose prompt occurs "
          "in the test rounds are removed.", "",
          "Removing those prompts shrinks training, so the size-matched CV trains each fold on random "
          "whole prompt groups up to the same number of traces, with no time gap: the gap between "
          "the two is what drift could add beyond training size. Conditions are interleaved within "
          "rounds, so drift cannot correlate with labels.", "",
          "| Task | Train (after / before prompt removal) | Test | Temporal GBT | Size-matched CV GBT | "
          "Temporal RF | Size-matched CV RF |", "|---|---|---|---|---|---|---|"]
    for t, r in R.items():
        tg, sm = r["temporal"], r["size_matched_cv"]
        L.append(f"| {t} | {tg['gbt']['n_train']} / {tg['gbt']['n_train_before_prompt_removal']} | "
                 f"{tg['gbt']['n']} | {_cell(tg['gbt'])} | {_cell(sm['gbt'])} | {_cell(tg['rf'])} | "
                 f"{_cell(sm['rf'])} |")
    L += ["", "## Paired differences (GBT minus …)", "",
          "| Task | GBT − RF | GBT − k-FP |", "|---|---|---|"]
    for t, r in R.items():
        L.append(f"| {t} | {_diff(r['paired']['gbt_minus_rf'])} | {_diff(r['paired']['gbt_minus_kfp'])} |")
    fams = list(out["feature_families"])
    L += ["", "## Feature ablation (GBT, same folds)", "",
          "| Task | All | " + " | ".join(f.replace("_", " and ") + " only" for f in fams) + " |",
          "|---|---|" + "---|" * len(fams)]
    for t, r in R.items():
        L.append(f"| {t} | {_cell(r['closed_world']['gbt'])} | " +
                 " | ".join(f"{_cell(r['ablation'][f])} ({r['ablation'][f]['dims']} dims)" for f in fams) + " |")
    L += ["", "Drop from all features to one family (paired, all − family):", "",
          "| Task | " + " | ".join(fams) + " |", "|---|" + "---|" * len(fams)]
    for t, r in R.items():
        L.append(f"| {t} | " + " | ".join(_diff(r["ablation"][f]["all_minus_this"]) for f in fams) + " |")
    L += ["", "Per-flow vs system aggregates (GBT, same folds; trace tasks only — a role sample is one "
          "flow). Per-flow = mean, heaviest and second-heaviest flow (105 dims); system = system-wide "
          "aggregates (90 dims).", "",
          "| Task | Per-flow only | System only | All − per-flow | All − system |", "|---|---|---|---|---|"]
    for t, r in R.items():
        if r["aggregates"]:
            a = r["aggregates"]
            L.append(f"| {t} | {_cell(a['per_flow'])} | {_cell(a['system'])} | "
                     f"{_diff(a['per_flow']['all_minus_this'])} | {_diff(a['system']['all_minus_this'])} |")
    L += ["", "## Learning curve (GBT, same folds, training cut to whole prompt groups)", "",
          "Share of each fold's training set; each cell gives the training traces per class.", "",
          "| Task | " + " | ".join(f"{int(f * 100)}%" for f in LEARNING_FRACTIONS) + " |",
          "|---|" + "---|" * len(LEARNING_FRACTIONS)]
    for t, r in R.items():
        L.append(f"| {t} | " + " | ".join(f"{_cell(p)} ({p['train_per_class']:g}/class)"
                                          for p in r["learning_curve"]) + " |")
    L += workflow_report(R["workflow"]["detail"])
    L += length_report(R["workflow"]["closed_world"]["gbt"], R["workflow"]["length_checks"])
    L += role_report(R["role"]["closed_world"]["gbt"], R["role"]["single_feature"])
    L += ["", f"k-FP: {out['kfp']['dims']} features from packet direction and timing only "
          f"(Hayes & Danezis 2016), {out['kfp']['classifier']}."]
    path.write_text("\n".join(L) + "\n")


def workflow_report(w: dict) -> list[str]:
    cl = w["classes"]
    L = ["", "## Workflow detail (GBT closed-world predictions)", "",
         "Confusion matrix, rows = true, columns = predicted (count, row share):", "",
         "| True (row) / predicted (column) | " + " | ".join(cl) + " |", "|---|" + "---|" * len(cl)]
    for c, row, nrow in zip(cl, w["confusion"]["counts"], w["confusion"]["row_normalized"]):
        L.append(f"| {c} | " + " | ".join(f"{k} ({v:.0%})" for k, v in zip(row, nrow)) + " |")
    L += ["", "Workflow macro-F1 on each topology's traces (same predictions, sliced):", "",
          "| Topology | n (groups) | macro-F1 |", "|---|---|---|"]
    for t, r in w["per_topology"].items():
        L.append(f"| {t} | {r['n']} ({r['ci_n_clusters']}) | {_cell(r)} |")
    v = w["vs_tls_control"]
    if v is None:
        return L + ["", "TLS control set not available: no comparison."]
    L += ["", f"Per-workflow F1, C1 vs the TLS control's TLS arm (its within-TLS CV recomputed with the "
          f"same folds; pooled macro-F1 {_cell(v['tls_macro_f1'])}, where tls_control.json gives the "
          f"mean of the five fold scores). Difference CIs come from independent group bootstraps.", "",
          "| Workflow | C1 F1 | C1 P / R | TLS arm F1 | TLS arm P / R | C1 − TLS arm |", "|---|---|---|---|---|---|"]
    for c in cl:
        a, b = w["per_class"][c], v["tls_per_class"][c]
        L.append(f"| {c} | {a['f1']:.3f} [{a['ci_lo']:.3f}, {a['ci_hi']:.3f}] | {a['precision']:.2f} / "
                 f"{a['recall']:.2f} | {b['f1']:.3f} [{b['ci_lo']:.3f}, {b['ci_hi']:.3f}] | "
                 f"{b['precision']:.2f} / {b['recall']:.2f} | {_diff(v['c1_minus_tls'][c])} |")
    L += ["", "Prompt mix (prompt_group = sha1 of the prompt). TV = total-variation distance between "
          "the two sets' prompt frequencies (0 = same mix, 1 = disjoint).", "",
          "| Workflow | Traces C1 / TLS | Distinct prompts C1 / TLS | Shared distinct | C1 traces with a "
          "shared prompt | TLS traces with a shared prompt | TV | Median prompt chars C1 / TLS |",
          "|---|---|---|---|---|---|---|---|"]
    for c in cl:
        m = v["prompt_mix"][c]
        L.append(f"| {c} | {m['n_a']} / {m['n_b']} | {m['distinct_a']} / {m['distinct_b']} | "
                 f"{m['shared_distinct']} | {m['traces_a_with_shared_prompt']:.0%} | "
                 f"{m['traces_b_with_shared_prompt']:.0%} | {m['total_variation']:.2f} | "
                 f"{m['median_prompt_chars_a']:g} / {m['median_prompt_chars_b']:g} |")
    o = v["c1_by_prompt_overlap"]
    L += ["", f"C1 workflow macro-F1 on traces whose prompt also occurs in the TLS arm: "
          f"{_cell(o['shared_with_tls'])} (n = {o['shared_with_tls']['n']}); on C1-only prompts: "
          f"{_cell(o['c1_only'])} (n = {o['c1_only']['n']})."]
    return L


def length_report(full: dict, c: dict) -> list[str]:
    f = c["first_request"]
    L = ["", "## Workflow: input length and response side (GBT, same folds)", "",
         f"First request into the system: {f['definition']} Pearson r with the true prompt length "
         f"{f['pearson_with_prompt_chars']:.3f}; {f['n_zero']} traces without one.", "",
         "| Features | Dims | macro-F1 | All − this |", "|---|---|---|---|",
         f"| all | 195 | {_cell(full)} | — |",
         f"| first-request size only | 1 | {_cell(c['first_request_bytes'])} | "
         f"{_diff(c['first_request_bytes']['all_minus_this'])} |",
         f"| true prompt length only (not observable) | 1 | {_cell(c['prompt_chars'])} | "
         f"{_diff(c['prompt_chars']['all_minus_this'])} |",
         f"| response side only (no request-byte sizes) | {c['response_side_only']['dims']} | "
         f"{_cell(c['response_side_only'])} | {_diff(c['response_side_only']['all_minus_this'])} |",
         "", "| Workflow | Median first request (B) | Median prompt (chars) | Median first request − "
         "prompt |", "|---|---|---|---|"]
    for w, m in f["median_by_workflow"].items():
        L.append(f"| {w} | {m['first_request_bytes']:g} | {m['prompt_chars']:g} | {m['overhead']:g} |")
    L += ["", "Within-length pairs (binary, the same folds restricted to the pair, chance 0.5):", "",
          "| Pair | n | All features | First-request size only | Prompt length only | "
          "All − first request | All − prompt length |", "|---|---|---|---|---|---|---|"]
    for pair, r in c["pairs"].items():
        L.append(f"| {pair.replace('_vs_', ' vs ')} | {r['n']} | {_cell(r['all'])} | "
                 f"{_cell(r['first_request_bytes'])} | {_cell(r['prompt_chars'])} | "
                 f"{_diff(r['first_request_bytes']['all_minus_this'])} | "
                 f"{_diff(r['prompt_chars']['all_minus_this'])} |")
    return L


def role_report(full: dict, r: dict) -> list[str]:
    L = ["", "## Role: single features and one direction's sizes (GBT, same folds)", "",
         f"Each of the {len(r['single_feature_macro_f1'])} per-flow features alone; the top "
         f"{len(r['top'])} are shown with CIs ({r['note']}). Response = agent → caller, "
         "request = caller → agent.", "",
         "| Features | macro-F1 | All − this |", "|---|---|---|", f"| all 35 | {_cell(full)} | — |"]
    for t in r["top"]:
        L.append(f"| {t['feature']} only | {_cell(t)} | {_diff(t['all_minus_this'])} |")
    for key, label in (("response_sizes_only", "response-side sizes"), ("request_sizes_only", "request-side sizes")):
        x = r[key]
        L.append(f"| {label} only ({', '.join(x['features'])}) | {_cell(x)} | {_diff(x['all_minus_this'])} |")
    L += ["", "All single features: " + ", ".join(f"{n} {v:.3f}" for n, v in r["single_feature_macro_f1"].items()) + "."]
    return L


def make_confusion_figure(out: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    w = out["results"]["workflow"]["detail"]
    cl = w["classes"]
    names = [c.replace("_", "\n") for c in cl]
    counts, norm = np.array(w["confusion"]["counts"]), np.array(w["confusion"]["row_normalized"])
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    for ax, m, title, fmt in ((axes[0], counts, "Counts", "{:d}"),
                              (axes[1], norm, "Row-normalized (recall on the diagonal)", "{:.2f}")):
        ax.imshow(norm, cmap="Greens", vmin=0, vmax=1)
        for i in range(len(cl)):
            for j in range(len(cl)):
                ax.text(j, i, fmt.format(m[i, j].item()), ha="center", va="center", fontsize=9,
                        color="white" if norm[i, j] > 0.6 else "black")
        ax.set_xticks(range(len(cl)))
        ax.set_xticklabels(names, fontsize=8)
        ax.set_yticks(range(len(cl)))
        ax.set_yticklabels(names, fontsize=8)
        ax.set_xlabel("predicted")
        ax.set_ylabel("true")
        ax.set_title(title, fontsize=9)
    fig.suptitle("C1 workflow — GBT closed world, 5 prompt-group folds, 600 traces", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def make_figure(out: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    R, tasks = out["results"], list(out["results"])
    left = (("GBT", lambda r: r["closed_world"]["gbt"], "#1b5e20"),
            ("RF", lambda r: r["closed_world"]["rf"], "#66bb6a"),
            ("k-FP", lambda r: r["kfp"], "#9e9e9e"),
            ("temporal GBT", lambda r: r["temporal"]["gbt"], "#1565c0"),
            ("size-matched CV GBT", lambda r: r["size_matched_cv"]["gbt"], "#90caf9"))
    right = (("all", lambda r: r["closed_world"]["gbt"], "#1b5e20"),
             ("sizes", lambda r: r["ablation"]["sizes"], "#ef6c00"),
             ("timing", lambda r: r["ablation"]["timing"], "#6a1b9a"),
             ("counts + direction", lambda r: r["ablation"]["counts_direction"], "#00838f"))
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.4), sharey=True)
    for ax, series, title in ((axes[0], left, "Classifiers and temporal holdout"),
                              (axes[1], right, "Feature ablation (GBT)")):
        w = 0.8 / len(series)
        for j, (label, get, color) in enumerate(series):
            xs = np.arange(len(tasks)) + (j - (len(series) - 1) / 2) * w
            rs = [get(R[t]) for t in tasks]
            v = [r["macro_f1"] for r in rs]
            ax.bar(xs, v, w, label=label, color=color,
                   yerr=[[a - r["ci_lo"] for a, r in zip(v, rs)], [r["ci_hi"] - a for a, r in zip(v, rs)]],
                   capsize=2)
            for x, a, r in zip(xs, v, rs):
                ax.text(x, r["ci_hi"] + 0.015, f"{a:.2f}", ha="center", fontsize=6.5)
        for i, t in enumerate(tasks):
            ax.hlines(R[t]["chance"], i - 0.45, i + 0.45, colors="crimson", linestyles="--", lw=1)
        ax.set_xticks(range(len(tasks)))
        ax.set_xticklabels(tasks)
        ax.set_ylim(0, 1.3)
        ax.set_title(title, fontsize=9)
        ax.legend(fontsize=7, loc="upper center", ncol=len(series), frameon=False)
    axes[0].set_ylabel("macro-F1 (95% cluster-bootstrap CI)")
    fig.suptitle("C1 — deployment A, TLS on, one session, 600 traces (dashed = chance)", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(path, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="P1 evaluation of collection C1")
    p.add_argument("--processed", default="data/processed_c1")
    p.add_argument("--raw", default="data/raw_c1")
    p.add_argument("--tls-processed", default="data/processed_tlspair_tls")
    p.add_argument("--tls-raw", default="data/raw_tlspair_tls")
    main(p.parse_args())
