#!/usr/bin/env python3
"""
TLS control — does the fingerprint survive real TLS on the agent links?

The main experiments run the agents over cleartext HTTP and restrict the
observer to the metadata TLS would leave visible. TLS still changes that
metadata (per-record overhead, a handshake per connection), so this control
re-collects deployment A with TLS on every agent link (run_pilot.py --tls-dir)
and reports, for workflow and role:

  1. within-TLS    — GBT, 5-fold group-safe CV on the TLS capture
  2. cleartext→TLS — GBT trained on the cleartext capture, tested on TLS
  3. cleartext     — the same GBT CV on the cleartext capture, for reference

plus the TLS overhead in bytes and packets per trace (from the raw captures'
on-wire lengths). Every interval is a cluster bootstrap over prompt groups.

Usage:
    python scripts/evaluate_tls_control.py --clear data/processed --tls data/processed_tls \\
        --clear-raw data/raw --tls-raw data/raw_tls
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation.stats import bootstrap_ci  # noqa: E402
from models.gradient_boosted import GBTClassifier  # noqa: E402
from scripts.evaluate_cross_deployment import load_deployment  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TASKS = ("workflow", "role")


def within(X, y, g, task: str) -> dict:
    r = GBTClassifier(task=task).cross_validate(X, list(y), n_splits=5, groups=list(g))
    f = r["f1_macro"]
    return {"macro_f1": f["mean"], "ci_lo": f["ci_lo"], "ci_hi": f["ci_hi"],
            "accuracy": r["accuracy"]["mean"], "n": int(len(y)),
            "ci_method": r["ci_method"], "ci_n_clusters": r["ci_n_clusters"]}


def transfer(Xtr, ytr, Xte, yte, gte, task: str) -> dict:
    pred = GBTClassifier(task=task).fit(Xtr, list(ytr)).predict(Xte)
    classes = sorted(set(ytr) | set(yte))
    ci = bootstrap_ci(list(yte), list(pred), classes=classes, groups=list(gte))
    return {"macro_f1": ci["macro_f1"], "ci_lo": ci["macro_f1_ci_lo"], "ci_hi": ci["macro_f1_ci_hi"],
            "accuracy": ci["accuracy"], "n_test": int(len(yte)),
            "ci_method": ci["ci_method"], "ci_n_clusters": ci["n_clusters"]}


def trace_volume(raw_dir: Path) -> dict:
    """Mean on-wire bytes and packets per trace, read from the pcap record headers."""
    totals_b, totals_p = [], []
    for f in sorted(raw_dir.glob("*.pcap")):
        raw = f.read_bytes()
        endian = "<" if raw[:4] in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1") else ">"
        pos, nbytes, npk = 24, 0, 0
        while pos + 16 <= len(raw):
            incl_len, orig_len = struct.unpack(endian + "II", raw[pos + 8:pos + 16])
            nbytes += orig_len
            npk += 1
            pos += 16 + incl_len
        totals_b.append(nbytes)
        totals_p.append(npk)
    if not totals_b:
        return {}
    return {"n_traces": len(totals_b), "bytes_mean": float(np.mean(totals_b)),
            "packets_mean": float(np.mean(totals_p))}


def main(a: argparse.Namespace) -> None:
    clear, tls = Path(a.clear), Path(a.tls)
    out = {
        "task": "TLS control — fingerprinting with TLS on every agent link",
        "method": "GBT; group-safe 5-fold StratifiedGroupKFold by prompt_group; macro-F1 with "
                  "cluster (group) bootstrap 95% CI; seed 42. Port never a feature.",
        "clear_dir": str(clear), "tls_dir": str(tls),
        "results": {},
    }
    for task in TASKS:
        Xc, _, yc, gc = load_deployment(clear, task)
        Xt, _, yt, gt = load_deployment(tls, task)
        chance = 1.0 / len(set(yt))
        res = {
            "chance": chance,
            "within_tls": within(Xt, yt, gt, task),
            "clear_to_tls": transfer(Xc, yc, Xt, yt, gt, task),
            "within_clear": within(Xc, yc, gc, task),
        }
        out["results"][task] = res
        logger.info("[%s] within-TLS %.3f  clear→TLS %.3f  within-clear %.3f  (chance %.3f)", task,
                    res["within_tls"]["macro_f1"], res["clear_to_tls"]["macro_f1"],
                    res["within_clear"]["macro_f1"], chance)

    if a.clear_raw and a.tls_raw:
        vc, vt = trace_volume(Path(a.clear_raw)), trace_volume(Path(a.tls_raw))
        if vc and vt:
            out["overhead"] = {
                "cleartext": vc, "tls": vt,
                "bytes_ratio": vt["bytes_mean"] / vc["bytes_mean"],
                "packets_ratio": vt["packets_mean"] / vc["packets_mean"],
            }

    out_dir = Path(os.environ.get("A2A_RESULTS_DIR", "data/results"))
    (out_dir / "figures").mkdir(parents=True, exist_ok=True)
    (out_dir / "tls_control.json").write_text(json.dumps(out, indent=2))
    make_figure(out, out_dir / "figures" / "tls_control.png")
    print(json.dumps({t: {k: round(v["macro_f1"], 3) for k, v in r.items() if isinstance(v, dict)}
                      for t, r in out["results"].items()}, indent=2))


def make_figure(out: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    arms = (("within_clear", "cleartext (CV)", "#9e9e9e"),
            ("within_tls", "TLS (CV)", "#2e7d32"),
            ("clear_to_tls", "cleartext → TLS", "#c62828"))
    tasks = list(out["results"])
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    w = 0.26
    for j, (key, label, color) in enumerate(arms):
        xs = np.arange(len(tasks)) + (j - 1) * w
        vals = [out["results"][t][key]["macro_f1"] for t in tasks]
        lo = [v - out["results"][t][key]["ci_lo"] for v, t in zip(vals, tasks)]
        hi = [out["results"][t][key]["ci_hi"] - v for v, t in zip(vals, tasks)]
        ax.bar(xs, vals, w, label=label, color=color, yerr=[lo, hi], capsize=3)
    for i, t in enumerate(tasks):
        ax.hlines(out["results"][t]["chance"], i - 0.45, i + 0.45, colors="crimson",
                  linestyles="--", lw=1.1)
    ax.set_xticks(range(len(tasks)))
    ax.set_xticklabels(tasks)
    ax.set_ylabel("macro-F1 (95% cluster-bootstrap CI)")
    ax.set_ylim(0, 1.05)
    ax.legend(fontsize=8, loc="lower right")
    ax.set_title("TLS control: fingerprinting with TLS on every agent link (dashed = chance)", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="TLS control evaluation")
    p.add_argument("--clear", default="data/processed")
    p.add_argument("--tls", default="data/processed_tls")
    p.add_argument("--clear-raw", default="data/raw")
    p.add_argument("--tls-raw", default="data/raw_tls")
    main(p.parse_args())
