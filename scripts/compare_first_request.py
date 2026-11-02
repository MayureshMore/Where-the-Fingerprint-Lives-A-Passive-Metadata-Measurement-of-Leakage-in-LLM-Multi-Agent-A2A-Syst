#!/usr/bin/env python3
"""
Why does the first-request size match all features for workflow on C1 but not on the TLS control?

On C1 (paper 1) the size of the first request that reaches an agent gives workflow macro-F1 0.641
against 0.626 for all 195 features; on the TLS control's TLS arm leakcheck found 0.58 against 0.74.
For C1, the TLS control's TLS arm and its cleartext arm, with the same protocol (GBT, 5-fold
StratifiedGroupKFold by prompt group, seed 42, cluster-bootstrap CIs, paired differences):

  1. first-request size per workflow: median, quartiles, and the bytes on top of the prompt
  2. per-class F1 from the first request alone and from all features, and their difference
  3. what adds to the first request: the first request plus one feature family (sizes, timing,
     counts and direction), or plus response-side sizes only, each paired against the first
     request alone, per class
  4. shared prompts: each set restricted to the prompts that occur in both C1 and the TLS control
  5. training size: C1 with each fold's training cut to the TLS control's training size

Writes data/results/first_request_c1_vs_tls.{json,md}.

Usage:
    python scripts/compare_first_request.py
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import f1_score

sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation.stats import paired_bootstrap_diff  # noqa: E402
from scripts.evaluate_c1 import (  # noqa: E402
    N_BOOT, SEED, _git, _sub_splits, family_columns, first_request_bytes, folds, load, oof_predict,
    oof_predict_size_matched, paired_diff, per_class, response_side_columns, score,
)
from features.families import FAMILIES  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SETS = {"C1": ("data/processed_c1", "data/raw_c1"),
        "TLS control, TLS arm": ("data/processed_tlspair_tls", "data/raw_tlspair_tls"),
        "TLS control, cleartext arm": ("data/processed_tlspair_clear", "data/raw_tlspair_clear")}


def _first(d: dict, raw: Path) -> np.ndarray:
    return np.array([first_request_bytes(raw / f"{b}.pcap", {int(a.rsplit(":", 1)[1]) for a in e.values()})
                     for b, e in zip(d["base"], d["endpoints"])], dtype=np.float32)


def _class_diff(y, pa, pb, g, c) -> dict:
    f1c = lambda t, p: f1_score(t, p, labels=[c], average="macro", zero_division=0)  # noqa: E731
    return paired_bootstrap_diff(y, pa, pb, g, f1c, n=N_BOOT, seed=SEED)


def analyse(name: str, processed: str, raw: str) -> dict:
    d = load(Path(processed), Path(raw), "workflow")
    X, y, g = d["X"], d["y"], d["g"]
    first = _first(d, Path(raw))
    classes = sorted(set(y.tolist()))
    splits = folds(y, g)
    logger.info("[%s] n=%d, %d prompt groups", name, len(y), len(set(g)))
    p_all = oof_predict("gbt", "workflow", X, y, splits)
    p_first = oof_predict("gbt", "workflow", first[:, None], y, splits)
    out = {"n": int(len(y)), "n_groups": int(len(set(g))), "classes": classes,
           "all": score(y, p_all, g, classes), "first": score(y, p_first, g, classes),
           "all_minus_first": paired_diff(y, p_all, p_first, g, classes)}

    chars = d["prompt_len"].astype(np.float32)
    out["distribution"] = {c: {"first_median": float(np.median(first[y == c])),
                               "first_q1": float(np.percentile(first[y == c], 25)),
                               "first_q3": float(np.percentile(first[y == c], 75)),
                               "prompt_chars_median": float(np.median(chars[y == c])),
                               "overhead_median": float(np.median(first[y == c] - chars[y == c]))}
                           for c in classes}

    pc_all, _ = per_class(y, p_all, g, classes)
    pc_first, _ = per_class(y, p_first, g, classes)
    out["per_class"] = {c: {"all": pc_all[c], "first": pc_first[c],
                            "all_minus_first": _class_diff(y, p_all, p_first, g, c)} for c in classes}

    adds = {f"first + {f}": np.column_stack([first, X[:, family_columns(f, False)]]) for f in FAMILIES}
    adds["first + response-side features"] = np.column_stack([first, X[:, response_side_columns()]])
    out["additions"] = {}
    for label, Xa in adds.items():
        p = oof_predict("gbt", "workflow", Xa, y, splits)
        out["additions"][label] = {**score(y, p, g, classes),
                                   "minus_first": paired_diff(y, p, p_first, g, classes),
                                   "per_class_minus_first": {c: _class_diff(y, p, p_first, g, c) for c in classes}}
    out["_data"] = (d, first, splits, p_all, p_first)
    return out


def restrict(res: dict, keep_groups: set, classes) -> dict:
    d, first, splits, _, _ = res["_data"]
    m = np.isin(d["g"], list(keep_groups))
    y, g = d["y"][m], d["g"][m]
    sub = _sub_splits(splits, m)
    pa = oof_predict("gbt", "workflow", d["X"][m], y, sub)
    pf = oof_predict("gbt", "workflow", first[m][:, None], y, sub)
    return {"n": int(m.sum()), "n_groups": int(len(set(g))),
            "per_class_n": {c: int((y == c).sum()) for c in classes},
            "all": score(y, pa, g, classes), "first": score(y, pf, g, classes),
            "all_minus_first": paired_diff(y, pa, pf, g, classes)}


def main() -> None:
    res = {name: analyse(name, *paths) for name, paths in SETS.items()}
    c1, tls = res["C1"], res["TLS control, TLS arm"]
    classes = c1["classes"]
    shared = set(c1["_data"][0]["g"]) & set(tls["_data"][0]["g"])
    logger.info("%d prompts shared by C1 and the TLS control", len(shared))
    shared_res = {name: restrict(r, shared, classes) for name, r in res.items()}

    d, first, splits, _, _ = c1["_data"]
    n_tls_train = int(np.mean([len(tr) for tr, _ in tls["_data"][2]]))
    pa = oof_predict_size_matched("gbt", "workflow", d["X"], d["y"], d["g"], splits, n_tls_train)
    pf = oof_predict_size_matched("gbt", "workflow", first[:, None], d["y"], d["g"], splits, n_tls_train)
    size_matched = {"n_train_per_fold": n_tls_train, "all": score(d["y"], pa, d["g"], classes),
                    "first": score(d["y"], pf, d["g"], classes),
                    "all_minus_first": paired_diff(d["y"], pa, pf, d["g"], classes)}

    for r in res.values():
        r.pop("_data")
    out = {"paper": "P1", "question": "first-request size vs all features for workflow, C1 vs TLS control",
           "seed": SEED, **_git(), "sets": {k: {"processed": v[0], "raw": v[1]} for k, v in SETS.items()},
           "method": "GBT, 5-fold StratifiedGroupKFold by prompt group (shuffle, seed 42), the same folds "
                     "for every model of a set; macro-F1 and per-class F1 with 95% cluster-bootstrap CIs "
                     "over prompt groups; paired differences on the same group resamples",
           "results": res, "shared_prompts": {"n_shared_prompts": len(shared), "results": shared_res},
           "c1_at_tls_training_size": size_matched}
    path = Path("data/results/first_request_c1_vs_tls.json")
    path.write_text(json.dumps(out, indent=2))
    write_report(out, path.with_suffix(".md"))
    logger.info("wrote %s", path)


def _c(r):
    return f"{r['macro_f1']:.3f} [{r['ci_lo']:.3f}, {r['ci_hi']:.3f}]"


def _d(r):
    return f"{r['diff']:+.3f} [{r['ci_lo']:+.3f}, {r['ci_hi']:+.3f}]{'' if r['significant'] else ' (n.s.)'}"


def _f(r):
    return f"{r['f1']:.3f} [{r['ci_lo']:.3f}, {r['ci_hi']:.3f}]"


def write_report(out: dict, path: Path) -> None:
    R = out["results"]
    cl = next(iter(R.values()))["classes"]
    L = ["# First-request size vs all features for workflow: C1 and the TLS control", "",
         f"{out['method']}. Commit `{out['git_commit'][:8]}`{' (uncommitted changes)' if out['git_dirty'] else ''}.",
         "", "## Overall", "", "| Set | n (groups) | All features | First request only | All − first |",
         "|---|---|---|---|---|"]
    for k, r in R.items():
        L.append(f"| {k} | {r['n']} ({r['n_groups']}) | {_c(r['all'])} | {_c(r['first'])} | {_d(r['all_minus_first'])} |")
    L += ["", "## First-request size per workflow (bytes; prompt in characters)", "",
          "| Workflow | " + " | ".join(f"{k}: median [Q1, Q3]" for k in R) + " | " +
          " | ".join(f"{k}: overhead" for k in R) + " |", "|---|" + "---|" * (2 * len(R))]
    for c in cl:
        L.append(f"| {c} | " + " | ".join(
            f"{R[k]['distribution'][c]['first_median']:g} [{R[k]['distribution'][c]['first_q1']:g}, "
            f"{R[k]['distribution'][c]['first_q3']:g}]" for k in R) + " | " +
            " | ".join(f"{R[k]['distribution'][c]['overhead_median']:g}" for k in R) + " |")
    L += ["", "Overhead = median of (first-request bytes − prompt characters).", "",
          "## Per-class F1", "", "| Workflow | " + " | ".join(
              f"{k}: all | {k}: first | {k}: all − first" for k in R) + " |", "|---|" + "---|" * (3 * len(R))]
    for c in cl:
        L.append(f"| {c} | " + " | ".join(
            f"{_f(R[k]['per_class'][c]['all'])} | {_f(R[k]['per_class'][c]['first'])} | "
            f"{_d(R[k]['per_class'][c]['all_minus_first'])}" for k in R) + " |")
    L += ["", "## What adds to the first request (paired against the first request alone)", ""]
    for k, r in R.items():
        L += [f"**{k}** (first request alone {_c(r['first'])})", "",
              "| Features | macro-F1 | − first | " + " | ".join(f"{c} − first" for c in cl) + " |",
              "|---|---|---|" + "---|" * len(cl)]
        for label, a in r["additions"].items():
            L.append(f"| {label} | {_c(a)} | {_d(a['minus_first'])} | " +
                     " | ".join(_d(a["per_class_minus_first"][c]) for c in cl) + " |")
        L.append("")
    S = out["shared_prompts"]
    L += [f"## Restricted to the {S['n_shared_prompts']} prompts shared by C1 and the TLS control", "",
          "| Set | n (groups) | All features | First request only | All − first |", "|---|---|---|---|---|"]
    for k, r in S["results"].items():
        L.append(f"| {k} | {r['n']} ({r['n_groups']}) | {_c(r['all'])} | {_c(r['first'])} | {_d(r['all_minus_first'])} |")
    m = out["c1_at_tls_training_size"]
    L += ["", f"## C1 with training cut to the TLS control's size ({m['n_train_per_fold']} traces per fold)", "",
          f"All features {_c(m['all'])}; first request only {_c(m['first'])}; all − first {_d(m['all_minus_first'])}."]
    path.write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
