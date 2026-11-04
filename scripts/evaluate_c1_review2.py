#!/usr/bin/env python3
"""
Paper 1 reviewer follow-up on collection C1 (analysis only; no new collection).

  B1  prompt length   estimate the prompt's size from the first request's on-wire size
                      (features/first_request.py) without knowing the workflow: on the training
                      folds learn one overhead c = median(first_request_bytes − prompt_json_bytes)
                      and predict prompt bytes = first_request_bytes − c on the test fold; also a
                      linear regression prompt bytes ~ first_request_bytes fitted the same way.
                      Errors overall and per workflow. For reference only, the same constant
                      learned per workflow (an estimator that does know the workflow).
  B2  role, LOTO      leave-one-topology-out role (the A7 folds of evaluate_c1_revision.py): the
                      role confusion matrix (counts) for each held-out topology.

prompt_json_bytes is the prompt as it is JSON-encoded in the request (evaluate_c1_revision.py A2).
Measurement: own connections (features/connections.py), features from data/processed_c1_own.
GBT; the 5-fold StratifiedGroupKFold by prompt group (seed 42) of scripts/evaluate_c1.py.

Writes data/results/c1_review2.{json,md}.

Usage:
    python scripts/evaluate_c1_review2.py
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import confusion_matrix

sys.path.insert(0, str(Path(__file__).parent.parent))

from features.first_request import first_request  # noqa: E402
from features.kfp import tcp_packets  # noqa: E402
from scripts.evaluate_c1 import SEED, _git, folds, load, oof_predict, score  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

WITHIN = (100, 200, 300)
ESTIMATORS = ("constant", "linear", "per_workflow_constant")


def servers_of(eps: dict) -> set[int]:
    return {int(a.rsplit(":", 1)[1]) for a in eps.values()}


# ── B1 ──────────────────────────────────────────────────────────────────────

def sizes(d: dict, raw: Path) -> tuple[np.ndarray, np.ndarray]:
    fr, pjb = [], []
    for base, eps in zip(d["base"], d["endpoints"]):
        prompt = json.loads((raw / f"{base}.json").read_text())["input_prompt"]
        pjb.append(len(json.dumps(prompt, ensure_ascii=False).encode()) - 2)
        fr.append(first_request(tcp_packets(raw / f"{base}.pcap"), servers_of(eps))["bytes"])
    return np.array(fr, float), np.array(pjb, float)


def estimate(fr: np.ndarray, pjb: np.ndarray, wf: np.ndarray, splits) -> tuple[dict, dict]:
    """Out-of-fold prompt-byte estimates, and what each fold learned."""
    pred = {e: np.empty(len(fr)) for e in ESTIMATORS}
    learned = {"constant_c": [], "linear": [], "per_workflow_c": []}
    for tr, te in splits:
        c = float(np.median(fr[tr] - pjb[tr]))
        pred["constant"][te] = fr[te] - c
        lr = LinearRegression().fit(fr[tr, None], pjb[tr])
        pred["linear"][te] = lr.predict(fr[te, None])
        cw = {w: float(np.median(fr[tr][wf[tr] == w] - pjb[tr][wf[tr] == w])) for w in sorted(set(wf.tolist()))}
        pred["per_workflow_constant"][te] = fr[te] - np.array([cw[w] for w in wf[te]])
        learned["constant_c"].append(c)
        learned["linear"].append({"slope": float(lr.coef_[0]), "intercept": float(lr.intercept_)})
        learned["per_workflow_c"].append(cw)
    return pred, learned


def errors(pred: np.ndarray, true: np.ndarray) -> dict:
    ae = np.abs(pred - true)
    return {"n": int(len(true)), "median_abs_error": float(np.median(ae)), "mae": float(ae.mean()),
            "p90_abs_error": float(np.percentile(ae, 90)),
            **{f"within_{b}B": float((ae <= b).mean()) for b in WITHIN},
            "median_relative_error": float(np.median(ae / true)),
            "median_signed_error": float(np.median(pred - true))}


def prompt_length(d: dict, raw: Path) -> dict:
    fr, pjb = sizes(d, raw)
    wf = np.array([str(w) for w in d["y"]])
    splits = folds(d["y"], d["g"])
    pred, learned = estimate(fr, pjb, wf, splits)
    out = {"n": int(len(fr)), "folds": len(splits),
           "prompt_json_bytes": {"median": float(np.median(pjb)), "range": [float(pjb.min()), float(pjb.max())],
                                 "per_workflow_median": {w: float(np.median(pjb[wf == w])) for w in sorted(set(wf))}},
           "learned_per_fold": learned, "estimators": {}}
    for e in ESTIMATORS:
        out["estimators"][e] = {"overall": errors(pred[e], pjb),
                                "per_workflow": {w: errors(pred[e][wf == w], pjb[wf == w]) for w in sorted(set(wf))}}
        o = out["estimators"][e]["overall"]
        logger.info("B1 %-22s median AE %.0f B, MAE %.0f B, p90 %.0f B, within 200 B %.0f%%",
                    e, o["median_abs_error"], o["mae"], o["p90_abs_error"], 100 * o["within_200B"])
    out["estimators"]["constant"]["description"] = (
        "one overhead c = median(first_request_bytes − prompt_json_bytes) on the training folds; "
        "prompt bytes = first_request_bytes − c (does not know the workflow)")
    out["estimators"]["linear"]["description"] = (
        "least-squares prompt_json_bytes ~ a + b·first_request_bytes on the training folds "
        "(does not know the workflow)")
    out["estimators"]["per_workflow_constant"]["description"] = (
        "reference only: c learned per workflow on the training folds and applied with the test "
        "trace's true workflow (knows the workflow)")
    return out


# ── B2 ──────────────────────────────────────────────────────────────────────

def role_loto_confusion(d_role: dict) -> dict:
    y, g, X = d_role["y"], d_role["g"], d_role["X"]
    top = np.array(d_role["topology"])
    classes = sorted(set(y.tolist()))
    held = sorted(set(top.tolist()))
    sp = [(np.where(top != t)[0], np.where(top == t)[0]) for t in held]
    p = oof_predict("gbt", "role", X, y, sp)
    out = {"classes": classes, "rows": "true role", "columns": "predicted role",
           "folds": "train on two topologies, test on the third (evaluate_c1_revision.py A7)",
           "overall": score(y, p, g, classes), "per_held_out": {}}
    for t in held:
        m = top == t
        cm = confusion_matrix(y[m], p[m], labels=classes)
        out["per_held_out"][t] = {"n": int(m.sum()), "macro_f1": score(y[m], p[m], g[m], classes)["macro_f1"],
                                  "confusion": cm.tolist(),
                                  "recall": {c: float(cm[i, i] / cm[i].sum()) if cm[i].sum() else 0.0
                                             for i, c in enumerate(classes)}}
        logger.info("B2 held-out %s: macro-F1 %.3f, confusion %s", t, out["per_held_out"][t]["macro_f1"], cm.tolist())
    return out


# ── report ──────────────────────────────────────────────────────────────────

def _err_row(name: str, e: dict) -> str:
    return (f"| {name} | {e['n']} | {e['median_abs_error']:.0f} | {e['mae']:.0f} | {e['p90_abs_error']:.0f} | "
            + " | ".join(f"{100 * e[f'within_{b}B']:.0f}%" for b in WITHIN)
            + f" | {100 * e['median_relative_error']:.1f}% |")


def write_report(out: dict, path: Path) -> None:
    R = out["results"]
    L = ["# C1 reviewer follow-up (review 2)", "",
         f"Collection {out['collection_id']}, {out['data_dir']}, {out['measurement']}. Commit "
         f"{out['git_commit'][:8]}{' (dirty)' if out['git_dirty'] else ''}, seed {out['seed']}. "
         "Analysis only; no new collection.", ""]
    b1 = R["B1_prompt_length"]
    L += ["## B1. Prompt size from the first request, without the workflow", "",
          f"{b1['n']} traces, the {b1['folds']} prompt-group folds of evaluate_c1.py. The target is the "
          "prompt's bytes as JSON-encoded in the request (median "
          f"{b1['prompt_json_bytes']['median']:.0f} B, range {b1['prompt_json_bytes']['range'][0]:.0f}–"
          f"{b1['prompt_json_bytes']['range'][1]:.0f} B). Errors are absolute, in bytes, on the test folds.", ""]
    head = ("| | n | Median AE | MAE | 90th pct | ≤100 B | ≤200 B | ≤300 B | Median relative error |",
            "|---|---|---|---|---|---|---|---|---|")
    for e in ESTIMATORS:
        r = b1["estimators"][e]
        L += [f"**{e}**: {r['description']}.", "", *head, _err_row("all", r["overall"])]
        L += [_err_row(w, v) for w, v in r["per_workflow"].items()]
        L.append("")
    cs = b1["learned_per_fold"]["constant_c"]
    lin = b1["learned_per_fold"]["linear"]
    L += [f"Learned overhead c per fold: {', '.join(f'{c:.0f}' for c in cs)} B. Linear fit per fold: "
          + "; ".join(f"slope {v['slope']:.3f}, intercept {v['intercept']:.0f}" for v in lin) + ".", ""]
    b2 = R["B2_role_loto_confusion"]
    L += ["## B2. Role, leave one topology out: confusion per held-out topology", "",
          f"{b2['folds']}; GBT on the role features. Rows are the true role, columns the predicted role "
          f"(counts). Overall macro-F1 {b2['overall']['macro_f1']:.3f} "
          f"[{b2['overall']['ci_lo']:.3f}, {b2['overall']['ci_hi']:.3f}].", ""]
    cls = b2["classes"]
    for t, v in b2["per_held_out"].items():
        L += [f"**Held out: {t}** (n = {v['n']}, macro-F1 {v['macro_f1']:.3f})", "",
              "| true \\ predicted | " + " | ".join(cls) + " | recall |",
              "|---|" + "---|" * (len(cls) + 1)]
        L += [f"| {c} | " + " | ".join(str(x) for x in row) + f" | {100 * v['recall'][c]:.0f}% |"
              for c, row in zip(cls, v["confusion"])]
        L.append("")
    L += ["## B3. Padding simulation (c1_revision A4), confirmed from the code", "", *[f"- {x}" for x in out["B3_padding_facts"]], ""]
    path.write_text("\n".join(L))


B3_FACTS = [
    "Padded trace vectors are recomputed: for each scheme, the padded packet list goes through "
    "FeatureExtractor._compute_features and role_vectors (evaluate_c1_revision.py padding()), and "
    "the unpadded rebuild matches the stored features for 600 of 600 traces.",
    "The GBT is retrained and tested on padded traffic: oof_predict fits each fold on the padded "
    "vectors of the training traces and predicts the padded vectors of the test traces; the folds "
    "are the same prompt-group folds as the unpadded run. Nothing is trained on unpadded traffic.",
    "Overhead = (padded wire bytes − unpadded wire bytes) / unpadded wire bytes, summed over every "
    "packet of each trace's own connections in both directions (handshakes, requests, responses, "
    "ACKs). Wire bytes are the captured frame length, so IP and TCP headers (and the loopback link "
    "header) are included, and each extra segment created by padding adds its own header.",
]


def main(a: argparse.Namespace) -> None:
    proc, raw = Path(a.processed), Path(a.raw)
    d_wf, d_role = load(proc, raw, "workflow"), load(proc, raw, "role")
    out = {"paper": "P1", "collection_id": "C1", "data_dir": str(proc), "raw_dir": str(raw), "seed": SEED,
           **_git(), "measurement": "own connections: only TCP connections whose SYN is in the trace "
                                    "(features/connections.py)",
           "results": {"B1_prompt_length": prompt_length(d_wf, raw),
                       "B2_role_loto_confusion": role_loto_confusion(d_role)},
           "B3_padding_facts": B3_FACTS}
    out_dir = Path(os.environ.get("A2A_RESULTS_DIR", "data/results"))
    path = out_dir / "c1_review2.json"
    path.write_text(json.dumps(out, indent=2))
    write_report(out, path.with_suffix(".md"))
    logger.info("wrote %s", path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--processed", default="data/processed_c1_own")
    ap.add_argument("--raw", default="data/raw_c1")
    main(ap.parse_args())
