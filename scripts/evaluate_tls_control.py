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
cross-fitted (evaluation/crossfit.py). For workflow, topology and role it reports:

  1. within-cleartext — GBT, 5-fold group-safe CV on the session's cleartext arm
  2. within-TLS       — the same CV on the TLS arm
  4. TLS − cleartext  — paired difference: out-of-fold predictions in each arm (the same 5-fold
                        StratifiedGroupKFold as scripts/evaluate_c1.py), macro-F1 of the TLS arm
                        minus the cleartext arm, with a cluster bootstrap that resamples the
                        shared prompt groups and scores both arms on the same resample
  3. cleartext → TLS  — cross-fitted transfer: for each of 5 group folds of the
                        TLS arm, train on the cleartext traces of the OTHER prompt
                        groups and predict the held-out TLS traces, so no test
                        prompt is ever seen in training

plus the on-wire overhead (bytes, packets, TCP connections per trace and per
agent port, read from packet headers), the negotiated TLS parameters recorded
at collection (session_meta.json) and the pre-strip record check
(tls_check.json, scripts/check_tls_capture.py). Every interval is a cluster
bootstrap over prompt groups.

There is no cross-session comparison against the original cleartext capture:
its chain and mesh traces were collected while every specialist stream was cut
after its first event (sse-starlette drain bug, fixed in agents/base.py), so it
is not the same traffic.

Measurement: own connections by default (features/connections.py): the processed sets are
data/processed_tlspair_{clear,tls}_own and the on-wire volume counts only the connections each
trace opens itself; writes tls_control_own.{json,md}. --legacy-all-connections reads the
all-connections sets and writes tls_control.{json,md}, as committed before the rule.

Usage:
    python scripts/evaluate_tls_control.py
    python scripts/evaluate_tls_control.py --legacy-all-connections
    python scripts/evaluate_tls_control.py --clear data/processed_tlspair_clear \\
        --tls data/processed_tlspair_tls
"""

from __future__ import annotations

import argparse
import json
import logging
import ast
import os
import struct
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np
sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation.crossfit import crossfit_predict, shared_prompt_fraction  # noqa: E402
from evaluation.stats import bootstrap_ci  # noqa: E402
from features.connections import own_packets  # noqa: E402
from features.kfp import tcp_packets  # noqa: E402
from models.gradient_boosted import GBTClassifier  # noqa: E402
from scripts.check_tls_capture import _parse  # noqa: E402
from scripts.evaluate_c1 import N_BOOT, folds, oof_predict  # noqa: E402
from scripts.evaluate_cross_deployment import load_deployment  # noqa: E402
from scripts.strip_payload import _MAGICS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TASKS = ("workflow", "topology", "role")
SEED = 42


def within(X, y, g, task: str) -> dict:
    r = GBTClassifier(task=task).cross_validate(X, list(y), n_splits=5, groups=list(g))
    f = r["f1_macro"]
    return {"macro_f1": f["mean"], "ci_lo": f["ci_lo"], "ci_hi": f["ci_hi"],
            "accuracy": r["accuracy"]["mean"], "n": int(len(y)),
            "ci_method": r["ci_method"], "ci_n_clusters": r["ci_n_clusters"]}


def paired_arms(Xc, yc, gc, Xt, yt, gt, task: str) -> dict:
    """macro-F1(TLS) − macro-F1(cleartext) on out-of-fold predictions, cluster bootstrap over the
    prompt groups the two arms share (the same prompt runs in both arms of a pair)."""
    from sklearn.metrics import f1_score
    yc, gc, yt, gt = (np.asarray(v) for v in (yc, gc, yt, gt))
    pc = oof_predict("gbt", task, Xc, yc, folds(yc, gc))
    pt = oof_predict("gbt", task, Xt, yt, folds(yt, gt))
    classes = sorted(set(yc.tolist()) | set(yt.tolist()))
    f1 = lambda y, p: f1_score(y, p, labels=classes, average="macro", zero_division=0)  # noqa: E731
    shared = np.intersect1d(np.unique(gc), np.unique(gt))
    ic = {u: np.where(gc == u)[0] for u in shared}
    it = {u: np.where(gt == u)[0] for u in shared}
    rng = np.random.default_rng(SEED)
    diffs = np.empty(N_BOOT)
    for b in range(N_BOOT):
        pick = rng.choice(shared, len(shared), replace=True)
        c = np.concatenate([ic[u] for u in pick])
        t = np.concatenate([it[u] for u in pick])
        diffs[b] = f1(yt[t], pt[t]) - f1(yc[c], pc[c])
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return {"clear_oof_macro_f1": float(f1(yc, pc)), "tls_oof_macro_f1": float(f1(yt, pt)),
            "diff": float(f1(yt, pt) - f1(yc, pc)), "ci_lo": float(lo), "ci_hi": float(hi),
            "significant": bool(lo > 0 or hi < 0), "shared_groups": int(len(shared)),
            "groups_only_clear": int(len(np.setdiff1d(np.unique(gc), shared))),
            "groups_only_tls": int(len(np.setdiff1d(np.unique(gt), shared))), "n_boot": N_BOOT,
            "protocol": "out-of-fold GBT predictions per arm (pooled over folds); cluster bootstrap "
                        "over shared prompt groups, both arms scored on the same resample"}


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


def _git() -> dict:
    """Commit, and whether the code differs from it (changes under data/ do not count)."""
    def run(*a):
        return subprocess.run(["git", *a], capture_output=True, text=True).stdout.strip()
    return {"git_commit": run("rev-parse", "HEAD"),
            "git_dirty": bool(run("status", "--porcelain", "--", ".", ":(exclude)data"))}


def _agent_ports(pcap: Path) -> set[int]:
    sc = json.loads(pcap.with_suffix(".json").read_text())
    eps = sc["agent_endpoints"]
    eps = ast.literal_eval(eps) if isinstance(eps, str) else eps
    return {int(str(v).rsplit(":", 1)[1]) for v in eps.values()}


def trace_volume(raw_dir: Path, legacy: bool = False) -> dict:
    """Per-trace on-wire bytes, packets and TCP connections, from packet headers only
    (so it works on payload-stripped captures). Own connections (default): only the agent-port
    connections each trace opens itself; legacy: every packet in the capture."""
    rows, by_port = [], Counter()
    for f in sorted(raw_dir.glob("*.pcap")):
        if not legacy:
            ports = _agent_ports(f)
            pk = own_packets([p for p in tcp_packets(f) if p[1] in ports or p[2] in ports], ports)
            syn = [p for p in pk if p[5] & 0x02 and not p[5] & 0x10]
            by_port.update(p[2] for p in syn)
            rows.append((sum(p[3] for p in pk), len(pk), len(syn)))
            continue
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
    legacy = a.legacy_all_connections
    clear = Path(a.clear or ("data/processed_tlspair_clear" if legacy else "data/processed_tlspair_clear_own"))
    tls = Path(a.tls or ("data/processed_tlspair_tls" if legacy else "data/processed_tlspair_tls_own"))
    out = {
        "paper": "P1", "collection_id": "TLS control", "seed": SEED, **_git(),
        "measurement": "all connections on the agent ports (legacy)" if legacy else
                       "own connections: only TCP connections whose SYN is in the trace (features/connections.py)",
        "task": "TLS control — fingerprinting with TLS on every agent link (same-session, paired)",
        "method": "Deployment A collected in one session with cleartext and TLS traces alternating "
                  "(same prompt per pair, arm order counterbalanced). GBT; "
                  "group-safe 5-fold StratifiedGroupKFold by prompt_group; the cleartext→TLS "
                  "transfer is cross-fitted so no test prompt is in training; macro-F1 with cluster (group) "
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
            "tls_minus_clear": paired_arms(Xc, yc, gc, Xt, yt, gt, task),
        }
        out["results"][task] = res
        d = res["tls_minus_clear"]
        logger.info("[%s] within-clear %.3f  within-TLS %.3f  clear→TLS %.3f  TLS − clear %+.3f [%+.3f, %+.3f]"
                    "  (chance %.3f)", task, res["within_clear"]["macro_f1"], res["within_tls"]["macro_f1"],
                    res["clear_to_tls"]["macro_f1"], d["diff"], d["ci_lo"], d["ci_hi"], res["chance"])

    if a.clear_raw and a.tls_raw:
        vc, vt = trace_volume(Path(a.clear_raw), legacy), trace_volume(Path(a.tls_raw), legacy)
        if vc and vt:
            out["overhead"] = {
                "cleartext": vc, "tls": vt,
                "bytes_ratio": vt["bytes_mean"] / vc["bytes_mean"],
                "packets_ratio": vt["packets_mean"] / vc["packets_mean"],
            }
        meta = _read_json(Path(a.tls_raw) / "session_meta.json")
        if meta:
            out["tls_params"] = meta.get("tls_params")
            out["session"] = {k: meta.get(k) for k in ("design", "model", "n_per_condition", "rounds",
                                                       "seed_offset", "started", "finished", "failures",
                                                       "complete_pairs", "stopped_at_deadline")}
        check = _read_json(Path(a.tls_raw) / "tls_check.json")
        if check:
            out["record_check"] = check

    out_dir = Path(os.environ.get("A2A_RESULTS_DIR", "data/results"))
    (out_dir / "figures").mkdir(parents=True, exist_ok=True)
    stem = "tls_control" if legacy else "tls_control_own"
    (out_dir / f"{stem}.json").write_text(json.dumps(out, indent=2))
    make_figure(out, out_dir / "figures" / f"{stem}.png")
    write_report(out, out_dir / f"{stem}.md")
    print(json.dumps({t: {k: round(v["macro_f1"], 3) for k, v in r.items() if isinstance(v, dict) and "macro_f1" in v}
                      for t, r in out["results"].items()}, indent=2))


def make_figure(out: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    arms = (("within_clear", "cleartext (CV)", "#9e9e9e"),
            ("within_tls", "TLS (CV)", "#2e7d32"),
            ("clear_to_tls", "cleartext → TLS (prompt-disjoint)", "#c62828"))
    tasks = list(out["results"])
    ov = out.get("overhead")
    fig, axes = plt.subplots(1, 2 if ov else 1, figsize=(11.5 if ov else 7.0, 4.2),
                             gridspec_kw={"width_ratios": [1.4, 1]} if ov else None)
    ax = axes[0] if ov else axes
    w = 0.26
    for j, (key, label, color) in enumerate(arms):
        xs = np.arange(len(tasks)) + (j - 1) * w
        vals = [out["results"][t][key]["macro_f1"] for t in tasks]
        lo = [v - out["results"][t][key]["ci_lo"] for v, t in zip(vals, tasks)]
        hi = [out["results"][t][key]["ci_hi"] - v for v, t in zip(vals, tasks)]
        ax.bar(xs, vals, w, label=label, color=color, yerr=[lo, hi], capsize=3)
        for x, v, t in zip(xs, vals, tasks):
            ax.text(x, out["results"][t][key]["ci_hi"] + 0.015, f"{v:.2f}", ha="center", fontsize=7)
    for i, t in enumerate(tasks):
        ax.hlines(out["results"][t]["chance"], i - 0.45, i + 0.45, colors="crimson",
                  linestyles="--", lw=1.1)
    ax.set_xticks(range(len(tasks)))
    ax.set_xticklabels(tasks)
    ax.set_ylabel("macro-F1 (95% cluster-bootstrap CI)")
    ax.set_ylim(0, 1.3)
    ax.legend(fontsize=7.5, loc="upper center", ncol=3, frameon=False)
    ax.set_title("Attack accuracy, same session (dashed = chance)", fontsize=9)
    if ov:
        a2 = axes[1]
        keys = [("bytes_mean", "bytes / trace"), ("packets_mean", "packets / trace"),
                ("connections_mean", "TCP connections / trace")]
        ratios = [ov["tls"][k] / ov["cleartext"][k] if ov["cleartext"].get(k) else np.nan for k, _ in keys]
        a2.barh([lbl for _, lbl in keys], ratios, color="#2e7d32")
        a2.axvline(1.0, color="#444", lw=1)
        for y, r in enumerate(ratios):
            a2.text(r, y, f" ×{r:.2f}", va="center", fontsize=8)
        a2.set_xlim(0, max(1.5, np.nanmax(ratios) * 1.25))
        a2.set_xlabel("TLS ÷ cleartext")
        a2.set_title("On-wire cost of TLS", fontsize=9)
    params = out.get("tls_params") or {}
    sub = (f"{params.get('tls_version', 'TLS')} · {params.get('cipher', '')} · "
           f"{params.get('http_version', '')}").strip(" ·")
    fig.suptitle(f"TLS control — deployment A, cleartext and TLS alternating in one session ({sub})",
                 fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def write_report(out: dict, path: Path) -> None:
    """Short Markdown summary of tls_control.json for the paper."""
    def cell(r):
        return f"{r['macro_f1']:.3f} [{r['ci_lo']:.3f}, {r['ci_hi']:.3f}]"
    lines = ["# TLS control — summary", "",
             "Deployment A, cleartext and TLS traces alternating in one session (same prompt per "
             "pair). macro-F1 with 95% cluster-bootstrap CIs over prompt groups; cleartext → TLS "
             f"is prompt-disjoint. Measurement: {out.get('measurement', 'all connections')}; commit "
             f"`{out.get('git_commit', '?')[:8]}`{' (uncommitted changes)' if out.get('git_dirty') else ''}.", "",
             "| Task | Chance | Within cleartext | Within TLS | TLS − cleartext (paired) | Cleartext → TLS | n (TLS) |",
             "|---|---|---|---|---|---|---|"]
    for t, r in out["results"].items():
        d = r.get("tls_minus_clear")
        dc = (f"{d['diff']:+.3f} [{d['ci_lo']:+.3f}, {d['ci_hi']:+.3f}]{'' if d['significant'] else ' (n.s.)'}"
              if d else "—")
        lines.append(f"| {t} | {r['chance']:.3f} | {cell(r['within_clear'])} | {cell(r['within_tls'])} | {dc} | "
                     f"{cell(r['clear_to_tls'])} | {r['within_tls']['n']} |")
    if any("tls_minus_clear" in r for r in out["results"].values()):
        d = next(r["tls_minus_clear"] for r in out["results"].values() if "tls_minus_clear" in r)
        lines += ["", f"Within-arm cells: mean over the 5 folds (CI from the cluster bootstrap). The paired "
                  f"difference scores pooled out-of-fold predictions of each arm and resamples the "
                  f"{d['shared_groups']} prompt groups both arms share ({d['n_boot']} resamples)."]
    ov = out.get("overhead")
    if ov:
        c, t = ov["cleartext"], ov["tls"]
        lines += ["", "| On-wire, mean per trace | Cleartext | TLS | Ratio |", "|---|---|---|---|"]
        for k, lbl in (("bytes_mean", "bytes"), ("packets_mean", "packets"),
                       ("connections_mean", "TCP connections")):
            fmt = ",.2f" if k == "connections_mean" else ",.0f"
            lines.append(f"| {lbl} | {c[k]:{fmt}} | {t[k]:{fmt}} | ×{t[k] / c[k]:.3f} |")
    params = out.get("tls_params")
    if params:
        lines += ["", f"TLS parameters: {params.get('tls_version')}, {params.get('cipher')} "
                  f"({params.get('cipher_bits')}-bit), {params.get('http_version')}."]
    chk = out.get("record_check")
    if chk:
        lines.append(f"Record check (raw captures, before stripping): "
                     f"{'passed' if chk.get('ok') else 'FAILED'}; "
                     f"{chk.get('tls_handshakes_per_connection')} TLS handshakes per connection, "
                     f"{chk.get('connections_per_trace'):.2f} connections per trace.")
    sess = out.get("session")
    if sess:
        lines.append(f"Session: {sess.get('started')} → {sess.get('finished')}; "
                     f"{sess.get('complete_pairs', '?')} complete pairs; "
                     f"{sess.get('failures')} failed attempts (retried)"
                     f"{'; stopped at the time limit' if sess.get('stopped_at_deadline') else ''}.")
    path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="TLS control evaluation (same-session paired design)")
    p.add_argument("--clear", help="default: data/processed_tlspair_clear_own (legacy: without _own)")
    p.add_argument("--tls", help="default: data/processed_tlspair_tls_own (legacy: without _own)")
    p.add_argument("--clear-raw", default="data/raw_tlspair_clear")
    p.add_argument("--tls-raw", default="data/raw_tlspair_tls")
    p.add_argument("--legacy-all-connections", action="store_true",
                   help="every connection on the agent ports (the earlier measurement); writes tls_control.*")
    main(p.parse_args())
