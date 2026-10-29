#!/usr/bin/env python3
"""
TLS control — does the fingerprint survive real TLS on the agent links?

The main experiments run the agents over cleartext HTTP and restrict the
observer to the metadata TLS would leave visible. TLS still changes that
metadata (per-record overhead, a handshake per connection), so this control
collects deployment A in ONE session with cleartext and TLS traces alternating
(scripts/collect_tls_session.py; same prompt for both traces of a pair), so session
drift cannot masquerade as a TLS effect. The generators draw from small template
pools, so prompts recur across collections; every transfer below is therefore
cross-fitted (evaluation/crossfit.py). For workflow and role it reports:

  1. within-cleartext — GBT, 5-fold group-safe CV on the session's cleartext arm
  2. within-TLS       — the same CV on the TLS arm
  3. cleartext → TLS  — cross-fitted transfer: for each of 5 group folds of the
                        TLS arm, train on the cleartext traces of the OTHER prompt
                        groups and predict the held-out TLS traces, so no test
                        prompt is ever seen in training

plus the on-wire overhead (bytes, packets, TCP connections per trace and per
agent port, read from packet headers), the negotiated TLS parameters recorded
at collection (session_meta.json) and the pre-strip record check
(tls_check.json, scripts/check_tls_capture.py). A cross-session comparison
(the original cleartext capture → TLS, also cross-fitted) is reported as
secondary only. Every
interval is a cluster bootstrap over prompt groups.

Usage:
    python scripts/evaluate_tls_control.py
    python scripts/evaluate_tls_control.py --clear data/processed_tlspair_clear \\
        --tls data/processed_tlspair_tls --secondary-clear data/processed
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import struct
import sys
from collections import Counter
from pathlib import Path

import numpy as np
sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation.crossfit import crossfit_predict, shared_prompt_fraction  # noqa: E402
from evaluation.stats import bootstrap_ci  # noqa: E402
from models.gradient_boosted import GBTClassifier  # noqa: E402
from scripts.check_tls_capture import _parse  # noqa: E402
from scripts.evaluate_cross_deployment import load_deployment  # noqa: E402
from scripts.strip_payload import _MAGICS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TASKS = ("workflow", "role")
SEED = 42


def within(X, y, g, task: str) -> dict:
    r = GBTClassifier(task=task).cross_validate(X, list(y), n_splits=5, groups=list(g))
    f = r["f1_macro"]
    return {"macro_f1": f["mean"], "ci_lo": f["ci_lo"], "ci_hi": f["ci_hi"],
            "accuracy": r["accuracy"]["mean"], "n": int(len(y)),
            "ci_method": r["ci_method"], "ci_n_clusters": r["ci_n_clusters"]}


def _scored(yt, yp, gt, classes, **extra) -> dict:
    ci = bootstrap_ci(list(yt), list(yp), classes=classes, groups=list(gt))
    return {"macro_f1": ci["macro_f1"], "ci_lo": ci["macro_f1_ci_lo"], "ci_hi": ci["macro_f1_ci_hi"],
            "accuracy": ci["accuracy"], "n_test": int(len(yt)),
            "ci_method": ci["ci_method"], "ci_n_clusters": ci["n_clusters"], **extra}


def transfer_crossfit(Xtr, ytr, gtr, Xte, yte, gte, task: str) -> dict:
    """Train on source traces whose prompt group is outside each target fold."""
    pred = crossfit_predict(lambda: GBTClassifier(task=task), Xtr, ytr, gtr, Xte, yte, gte)
    return _scored(yte, pred, gte, sorted(set(ytr) | set(yte)),
                   shared_prompt_fraction=shared_prompt_fraction(gtr, gte),
                   protocol="cross-fitted: 5 group folds of the target; trained on source traces "
                            "of the other prompt groups only")


def trace_volume(raw_dir: Path) -> dict:
    """Per-trace on-wire bytes, packets and TCP connections, from packet headers only
    (so it works on payload-stripped captures)."""
    rows, by_port = [], Counter()
    for f in sorted(raw_dir.glob("*.pcap")):
        raw = f.read_bytes()
        endian = _MAGICS[raw[:4]]
        linktype = struct.unpack(endian + "I", raw[20:24])[0]
        pos, nbytes, npk, nconn = 24, 0, 0, 0
        while pos + 16 <= len(raw):
            incl_len, orig_len = struct.unpack(endian + "II", raw[pos + 8:pos + 16])
            p = _parse(linktype, raw[pos + 16:pos + 16 + incl_len])
            if p and p[1] & 0x02 and not p[1] & 0x10:
                nconn += 1
                by_port[p[0]] += 1
            nbytes += orig_len
            npk += 1
            pos += 16 + incl_len
        rows.append((nbytes, npk, nconn))
    if not rows:
        return {}
    b, pk, c = (np.array(col, dtype=float) for col in zip(*rows))
    return {"n_traces": len(rows), "bytes_mean": float(b.mean()), "packets_mean": float(pk.mean()),
            "connections_mean": float(c.mean()),
            "connections_per_trace_by_port": {str(k): v / len(rows) for k, v in sorted(by_port.items())}}


def _read_json(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def main(a: argparse.Namespace) -> None:
    clear, tls = Path(a.clear), Path(a.tls)
    out = {
        "task": "TLS control — fingerprinting with TLS on every agent link (same-session, paired)",
        "method": "Deployment A collected in one session with cleartext and TLS traces alternating "
                  "(same prompt per pair, arm order counterbalanced). GBT; "
                  "group-safe 5-fold StratifiedGroupKFold by prompt_group; every transfer (cleartext→TLS "
                  "and the secondary cross-session one) is cross-fitted so no test prompt is in training; macro-F1 with cluster (group) "
                  "bootstrap 95% CI; seed 42. Port never a feature.",
        "clear_dir": str(clear), "tls_dir": str(tls),
        "results": {},
    }
    for task in TASKS:
        Xc, _, yc, gc = load_deployment(clear, task)
        Xt, _, yt, gt = load_deployment(tls, task)
        res = {
            "chance": 1.0 / len(set(yt)),
            "within_clear": within(Xc, yc, gc, task),
            "within_tls": within(Xt, yt, gt, task),
            "clear_to_tls": transfer_crossfit(Xc, yc, gc, Xt, yt, gt, task),
        }
        if a.secondary_clear and Path(a.secondary_clear, "labels.json").exists():
            Xs, _, ys, gs = load_deployment(Path(a.secondary_clear), task)
            res["secondary_cross_session"] = {
                "source": a.secondary_clear,
                "note": "earlier cleartext collection → this session's TLS arm; mixes the TLS "
                        "effect with session drift, reported for reference only",
                **transfer_crossfit(Xs, ys, gs, Xt, yt, gt, task),
            }
        out["results"][task] = res
        logger.info("[%s] within-clear %.3f  within-TLS %.3f  clear→TLS %.3f  (chance %.3f)", task,
                    res["within_clear"]["macro_f1"], res["within_tls"]["macro_f1"],
                    res["clear_to_tls"]["macro_f1"], res["chance"])

    if a.clear_raw and a.tls_raw:
        vc, vt = trace_volume(Path(a.clear_raw)), trace_volume(Path(a.tls_raw))
        if vc and vt:
            out["overhead"] = {
                "cleartext": vc, "tls": vt,
                "bytes_ratio": vt["bytes_mean"] / vc["bytes_mean"],
                "packets_ratio": vt["packets_mean"] / vc["packets_mean"],
            }
        meta = _read_json(Path(a.tls_raw) / "session_meta.json")
        if meta:
            out["tls_params"] = meta.get("tls_params")
            out["session"] = {k: meta.get(k) for k in ("design", "model", "n_per_condition",
                                                       "seed_offset", "started", "finished", "failures")}
        check = _read_json(Path(a.tls_raw) / "tls_check.json")
        if check:
            out["record_check"] = check

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
    ax.set_title("TLS control, same session (dashed = chance)", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="TLS control evaluation (same-session paired design)")
    p.add_argument("--clear", default="data/processed_tlspair_clear")
    p.add_argument("--tls", default="data/processed_tlspair_tls")
    p.add_argument("--clear-raw", default="data/raw_tlspair_clear")
    p.add_argument("--tls-raw", default="data/raw_tlspair_tls")
    p.add_argument("--secondary-clear", default="data/processed",
                   help="an earlier cleartext collection, compared cross-session (secondary only)")
    main(p.parse_args())
