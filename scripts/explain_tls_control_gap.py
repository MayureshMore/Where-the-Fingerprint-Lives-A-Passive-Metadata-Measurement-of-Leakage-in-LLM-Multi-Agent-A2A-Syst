#!/usr/bin/env python3
"""
Why do all features beat the first-request size for workflow on the TLS control, but not on C1?

data/results/first_request_c1_vs_tls.md shows the gap (TLS arm: all features 0.741, first request
0.582; C1: 0.626 vs 0.641) and that neither shared prompts nor training size close it. This script
tests the remaining explanations, for C1 and both TLS-control arms:

  1. schedule      which workflow ran last on the same agent ports before each trace
                   (session_meta.json); a capture starts with the tail of that trace's connections
  2. specialists   response bytes, duration and response bursts per specialist, and research
                   retrieval vs support triage separation (AUC) for each
  3. features      the single trace features that best separate research retrieval from support
                   triage on the TLS arm, and their separation on C1 and the cleartext arm
  4. own flows     features re-extracted from only the connections a trace opens itself (its SYN
                   is in the capture; features/connections.py, now the primary measurement); all
                   features vs the first request again. "All features" are the earlier
                   all-connections features in data/processed_tlspair_* and data/processed_c1; the
                   first request is measured on own connections

Writes data/results/tls_control_gap.{json,md}.

Usage:
    python scripts/explain_tls_control_gap.py
"""

from __future__ import annotations

import json
import logging
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from features.extractor import FeatureExtractor  # noqa: E402
from features.names import FLAT_FEATURE_NAMES  # noqa: E402
from features.per_flow import PerFlowFeatures  # noqa: E402
from scripts.evaluate_c1 import (  # noqa: E402
    SEED, _git, first_request_bytes, folds, load, oof_predict, paired_diff, per_class, score,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SETS = {"C1": ("data/processed_c1", "data/raw_c1"),
        "TLS control, TLS arm": ("data/processed_tlspair_tls", "data/raw_tlspair_tls"),
        "TLS control, cleartext arm": ("data/processed_tlspair_clear", "data/raw_tlspair_clear")}
SCHEDULES = {"C1": ("data/raw_c1/session_meta.json", "a_tls", "item"),
             "TLS control, TLS arm": ("data/raw_tlspair_tls/session_meta.json", "tls", "pair"),
             "TLS control, cleartext arm": ("data/raw_tlspair_tls/session_meta.json", "clear", "pair")}
RR, ST = "research_retrieval", "support_triage"
SPECIALIST_FEATURES = ("bytes_out", "duration_s", "n_response_bursts")


def auc(a, b) -> float:
    """P(a > b) + ½ P(a = b): 0.5 = no separation."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    return float((a[:, None] > b[None, :]).mean() + 0.5 * (a[:, None] == b[None, :]).mean())


def predecessors(meta_path: str, arm: str, key: str) -> dict:
    m = json.loads(Path(meta_path).read_text())
    sched = sorted((e for e in m["schedule"] if e["success"]), key=lambda e: e["start_ts"])
    last, out = {}, defaultdict(Counter)
    for e in sched:
        top, wf, _ = e[key].split("/")
        ports = (e["arm"], top)                      # one agent set per arm and topology
        if e["arm"] == arm:
            prev = last.get(ports)
            out[wf][prev or "none"] += 1
        last[ports] = wf
    return {wf: {p: n / sum(c.values()) for p, n in c.most_common()} for wf, c in sorted(out.items())}


def specialists(processed: str) -> dict:
    lab = json.loads((Path(processed) / "labels.json").read_text())
    names = PerFlowFeatures.FEATURE_NAMES()
    rows = defaultdict(lambda: defaultdict(list))
    for k, v in lab.items():
        if "__role__" in k:
            f = np.load(Path(processed) / f"{k}.npz")["flat"]
            for feat in SPECIALIST_FEATURES:
                rows[(v["role"], feat)][v["workflow"]].append(float(f[names.index(feat)]))
    return {f"{role}.{feat}": {"median_research_retrieval": float(np.median(w[RR])),
                               "median_support_triage": float(np.median(w[ST])),
                               "auc_rr_over_st": auc(w[RR], w[ST])}
            for (role, feat), w in sorted(rows.items())}


def own_connection_vectors(d: dict, raw: Path) -> tuple[np.ndarray, np.ndarray]:
    """Trace vectors from the connections each trace opens itself (features/connections.py), and
    the number of leftover flows (connections opened before the capture) per trace."""
    X, left = [], []
    for base, eps in zip(d["base"], d["endpoints"]):
        ports = {int(a.rsplit(":", 1)[1]) for a in eps.values()}
        pcap = raw / f"{base}.pcap"
        own = FeatureExtractor(agent_ports=ports, use_scapy=True, own_connections=True)
        every = FeatureExtractor(agent_ports=ports, use_scapy=True, own_connections=False)
        keep, pk = own._read_pcap(pcap), every._read_pcap(pcap)
        left.append(len({p[2] for p in pk}) - len({p[2] for p in keep}))
        X.append(own._compute_features(base, keep).flat_vector())
    return np.stack(X).astype(np.float32), np.array(left)


def main() -> None:
    names = FLAT_FEATURE_NAMES()
    out = {"paper": "P1", "question": "why all features beat the first request for workflow on the TLS "
                                      "control but not on C1", "seed": SEED, **_git(), "results": {}}
    data = {}
    for name, (proc, raw) in SETS.items():
        d = load(Path(proc), Path(raw), "workflow")
        data[name] = d
        X, y = d["X"], d["y"]
        res = {"predecessor_on_same_ports": predecessors(*SCHEDULES[name]),
               "specialists": specialists(proc),
               "feature_auc_rr_over_st": [auc(X[y == RR, j], X[y == ST, j]) for j in range(X.shape[1])]}
        logger.info("[%s] own-connection re-extraction", name)
        Xo, left = own_connection_vectors(d, Path(raw))
        g, cl = d["g"], sorted(set(y.tolist()))
        sp = folds(y, g)
        first = np.array([first_request_bytes(Path(raw) / f"{b}.pcap", {int(a.rsplit(":", 1)[1]) for a in e.values()})
                          for b, e in zip(d["base"], d["endpoints"])], dtype=np.float32)
        p_all = oof_predict("gbt", "workflow", X, y, sp)
        p_own = oof_predict("gbt", "workflow", Xo, y, sp)
        p_first = oof_predict("gbt", "workflow", first[:, None], y, sp)
        res["own_connections"] = {
            "leftover_flows_per_trace": {w: float(left[y == w].mean()) for w in cl},
            "traces_with_leftover_flows": float((left > 0).mean()),
            "all_features": score(y, p_all, g, cl), "all_features_own_connections": score(y, p_own, g, cl),
            "first_request": score(y, p_first, g, cl),
            "all_minus_own": paired_diff(y, p_all, p_own, g, cl),
            "own_minus_first": paired_diff(y, p_own, p_first, g, cl),
            "all_minus_first": paired_diff(y, p_all, p_first, g, cl),
            "per_class_all": {c: v for c, v in per_class(y, p_all, g, cl)[0].items()},
            "per_class_own": {c: v for c, v in per_class(y, p_own, g, cl)[0].items()},
        }
        out["results"][name] = res
    tls = np.array(out["results"]["TLS control, TLS arm"]["feature_auc_rr_over_st"])
    top = np.argsort(-np.abs(tls - 0.5))[:12]
    out["top_features_tls_arm"] = [{"feature": names[j], **{k: out["results"][k]["feature_auc_rr_over_st"][j]
                                                           for k in SETS}} for j in top]
    for k in SETS:
        a = np.array(out["results"][k].pop("feature_auc_rr_over_st"))
        out["results"][k]["max_feature_separation"] = float(np.abs(a - 0.5).max())
    path = Path("data/results/tls_control_gap.json")
    path.write_text(json.dumps(out, indent=2))
    write_report(out, path.with_suffix(".md"))
    logger.info("wrote %s", path)


def _c(r):
    return f"{r['macro_f1']:.3f} [{r['ci_lo']:.3f}, {r['ci_hi']:.3f}]"


def _d(r):
    return f"{r['diff']:+.3f} [{r['ci_lo']:+.3f}, {r['ci_hi']:+.3f}]{'' if r['significant'] else ' (n.s.)'}"


def write_report(out: dict, path: Path) -> None:
    R = out["results"]
    L = ["# Why all features beat the first request on the TLS control but not on C1", "",
         f"Commit `{out['git_commit'][:8]}`{' (uncommitted changes)' if out['git_dirty'] else ''}; GBT, "
         "5-fold StratifiedGroupKFold by prompt group, seed 42; 95% cluster-bootstrap CIs.", "",
         "## 1. Workflow that ran last on the same agent ports", "",
         "A capture starts while the previous trace's connections on the same ports are still closing.",
         "", "| Workflow | " + " | ".join(R) + " |", "|---|" + "---|" * len(R)]
    for w in sorted(next(iter(R.values()))["predecessor_on_same_ports"]):
        L.append(f"| {w} | " + " | ".join(
            ", ".join(f"{p} {s:.0%}" for p, s in list(R[k]["predecessor_on_same_ports"][w].items())[:4])
            for k in R) + " |")
    L += ["", "## 2. Per specialist, research retrieval vs support triage (median; AUC)", "",
          "| Specialist feature | " + " | ".join(R) + " |", "|---|" + "---|" * len(R)]
    for key in R["C1"]["specialists"]:
        L.append(f"| {key} | " + " | ".join(
            f"{R[k]['specialists'][key]['median_research_retrieval']:g} vs "
            f"{R[k]['specialists'][key]['median_support_triage']:g}; "
            f"{R[k]['specialists'][key]['auc_rr_over_st']:.2f}" for k in R) + " |")
    L += ["", "## 3. Trace features that best separate research retrieval from support triage on the TLS arm "
          "(AUC; 0.5 = none)", "", "| Feature | " + " | ".join(R) + " |", "|---|" + "---|" * len(R)]
    for t in out["top_features_tls_arm"]:
        L.append(f"| {t['feature']} | " + " | ".join(f"{t[k]:.2f}" for k in R) + " |")
    L += ["", "Largest separation of any single feature (|AUC − 0.5|): " +
          ", ".join(f"{k} {R[k]['max_feature_separation']:.3f}" for k in R) + ".", "",
          "## 4. Only the connections a trace opens itself", "",
          "| Set | Leftover flows per trace | All features | All, own connections | First request | "
          "All − own | Own − first |", "|---|---|---|---|---|---|---|"]
    for k, r in R.items():
        o = r["own_connections"]
        L.append(f"| {k} | {np.mean(list(o['leftover_flows_per_trace'].values())):.2f} "
                 f"({o['traces_with_leftover_flows']:.0%} of traces) | {_c(o['all_features'])} | "
                 f"{_c(o['all_features_own_connections'])} | {_c(o['first_request'])} | "
                 f"{_d(o['all_minus_own'])} | {_d(o['own_minus_first'])} |")
    L += ["", "Per-class F1, all features → own connections only:", ""]
    for k, r in R.items():
        o = r["own_connections"]
        L.append(f"- {k}: " + ", ".join(f"{c} {o['per_class_all'][c]['f1']:.3f} → {o['per_class_own'][c]['f1']:.3f}"
                                         for c in o["per_class_all"]))
    path.write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
