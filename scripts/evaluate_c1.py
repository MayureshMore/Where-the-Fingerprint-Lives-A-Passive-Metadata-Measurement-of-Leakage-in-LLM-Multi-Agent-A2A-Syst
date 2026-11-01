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
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedGroupKFold

sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation.stats import bootstrap_ci  # noqa: E402
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

# ── feature families (indices into the 35-dim per-flow and 20-dim per-system scalar blocks) ──
_PF_SIZES = {"bytes_out", "bytes_in", "mean_sz_out", "std_sz_out", "p25_sz_out", "p75_sz_out",
             "mean_sz_in", "std_sz_in", "p25_sz_in", "p75_sz_in", "mean_burst_bytes",
             "std_burst_bytes", "bytes_out_ratio", "pkt_size_asymmetry", "n_small_inbound",
             "iqr_size_in"} | {f"cumul_bytes_q{i}" for i in range(10)}
_PF_TIMING = {"duration_s", "mean_iat", "std_iat", "mean_burst_dur", "mean_ibg"}
_PF_COUNTS = {"n_pkts_out", "n_pkts_in", "n_bursts", "n_response_bursts"}
_SYS_SIZES = {"total_bytes", "bytes_out_ratio", "heaviest_flow_bytes_frac", "flow_bytes_cv",
              "n_response_heavy_flows", "mean_flow_response_ratio", "max_flow_bytes_out_ratio",
              "min_flow_bytes_out_ratio", "max_flow_bytes_in"}
_SYS_TIMING = {"total_duration_s", "flow_start_spread", "flow_end_spread", "max_concurrent_flows",
               "mean_burst_rate"}
_SYS_COUNTS = {"n_flows", "n_src_hosts", "n_dst_hosts", "n_host_pairs", "total_packets",
               "total_bursts"}
FAMILIES = {"sizes": (_PF_SIZES, _SYS_SIZES), "timing": (_PF_TIMING, _SYS_TIMING),
            "counts_direction": (_PF_COUNTS, _SYS_COUNTS)}
# trace vector: per-flow blocks (mean, heaviest, 2nd heaviest flow) vs system-wide aggregates
AGGREGATES = {"per_flow": np.arange(0, 105), "system": np.arange(105, 195)}
LEARNING_FRACTIONS = (0.1, 0.25, 0.5, 0.75, 1.0)


def family_columns(family: str, role: bool) -> np.ndarray:
    """Column indices of one feature family in the role (35) or trace (195) flat vector."""
    pf_names = PerFlowFeatures.FEATURE_NAMES()
    sys_names = PerSystemFeatures.FEATURE_NAMES()[:20]
    pf_set, sys_set = FAMILIES[family]
    pf_idx = [i for i, n in enumerate(pf_names) if n in pf_set]
    if role:
        return np.array(pf_idx)
    cols = [b + i for b in (0, 35, 70, 125, 160) for i in pf_idx]   # pf blocks + sys pf mean/std
    cols += [105 + i for i, n in enumerate(sys_names) if n in sys_set]
    return np.array(sorted(cols))


def _check_partition() -> None:
    pf = set(PerFlowFeatures.FEATURE_NAMES())
    sysn = set(PerSystemFeatures.FEATURE_NAMES()[:20])
    fams = list(FAMILIES.values())
    assert set().union(*(f[0] for f in fams)) == pf and sum(len(f[0]) for f in fams) == len(pf)
    assert set().union(*(f[1] for f in fams)) == sysn and sum(len(f[1]) for f in fams) == len(sysn)


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
                     str(info["prompt_group"]), int(side["round"]), side["agent_endpoints"]))
    rid, base, port, flat, y, g, rnd, eps = zip(*rows)
    return {"run_id": list(rid), "base": list(base), "port": list(port), "X": np.stack(flat),
            "y": np.array(y), "g": np.array(g), "round": np.array(rnd), "endpoints": list(eps)}


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
    y, pa, pb, g = (np.asarray(v) for v in (y, pa, pb, g))
    f1 = lambda t, p: f1_score(t, p, labels=classes, average="macro", zero_division=0)  # noqa: E731
    uniq = np.unique(g)
    idx_by = {u: np.where(g == u)[0] for u in uniq}
    rng = np.random.default_rng(SEED)
    diffs = np.empty(N_BOOT)
    for i in range(N_BOOT):
        idx = np.concatenate([idx_by[u] for u in rng.choice(uniq, len(uniq), replace=True)])
        diffs[i] = f1(y[idx], pa[idx]) - f1(y[idx], pb[idx])
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return {"diff": float(f1(y, pa) - f1(y, pb)), "ci_lo": float(lo), "ci_hi": float(hi),
            "significant": bool(lo > 0 or hi < 0)}


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
    def run(*a):
        return subprocess.run(["git", *a], capture_output=True, text=True).stdout.strip()
    return {"git_commit": run("rev-parse", "HEAD"), "git_dirty": bool(run("status", "--porcelain"))}


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
          "whole prompt groups up to the same number of traces, with no time gap. Temporal below "
          "size-matched = drift; equal = training size.", "",
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
    L += ["", f"k-FP: {out['kfp']['dims']} features from packet direction and timing only "
          f"(Hayes & Danezis 2016), {out['kfp']['classifier']}."]
    path.write_text("\n".join(L) + "\n")


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
    main(p.parse_args())
