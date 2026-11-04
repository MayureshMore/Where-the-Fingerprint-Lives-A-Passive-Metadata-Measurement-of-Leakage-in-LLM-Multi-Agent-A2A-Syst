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
  5. mechanism     which leftover packets move the features: the leftover packets by direction,
                   TCP flags and wire size per workflow, and the request-size feature and the
                   workflow score with only the leftover request-direction or only the leftover
                   response-direction packets put back

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

from features.connections import opened_connections  # noqa: E402
from features.extractor import FeatureExtractor  # noqa: E402
from features.kfp import tcp_packets  # noqa: E402
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
SIZE_FEATURE = "pf_mean.p75_sz_in"
FLAGS = ((0x01, "F"), (0x02, "S"), (0x04, "R"), (0x08, "P"), (0x10, "A"))
# Trace vectors per measurement. Leftover packets are those of connections opened before the capture.
VARIANTS = {"own": "own connections only",
            "all": "all connections",
            "left_request": "own + leftover request-direction packets (caller -> agent)",
            "left_response": "own + leftover response-direction packets (agent -> caller)"}


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


def own_connection_vectors(d: dict, raw: Path) -> tuple[dict, np.ndarray, list, list]:
    """Trace vectors under each VARIANTS measurement, the number of leftover flows (connections
    opened before the capture) per trace, each trace's leftover packets as
    (direction, TCP flags, wire bytes, payload bytes), and the request-size 75th percentile of each
    leftover flow (as the per-flow feature computes it: all request-direction packets, wire bytes)."""
    X, left, kinds, left_p75 = {v: [] for v in VARIANTS}, [], [], []
    for base, eps in zip(d["base"], d["endpoints"]):
        ports = {int(a.rsplit(":", 1)[1]) for a in eps.values()}
        pcap = raw / f"{base}.pcap"
        ex = FeatureExtractor(agent_ports=ports, use_scapy=True, own_connections=True)
        every = FeatureExtractor(agent_ports=ports, use_scapy=True, own_connections=False)
        keep, pk = ex._read_pcap(pcap), every._read_pcap(pcap)
        flows = {p[2] for p in keep}
        rest = [p for p in pk if p[2] not in flows]
        left.append(len({p[2] for p in rest}))
        req = defaultdict(list)
        for p in rest:
            if p[3] == -1:
                req[p[2]].append(p[1])
        left_p75.append([float(np.percentile(v, 75)) for v in req.values()])
        for v, packets in (("own", keep), ("all", pk),
                           ("left_request", sorted(keep + [p for p in rest if p[3] == -1])),
                           ("left_response", sorted(keep + [p for p in rest if p[3] == 1]))):
            X[v].append(ex._compute_features(base, packets).flat_vector())
        tp = [p for p in tcp_packets(pcap) if p[1] in ports or p[2] in ports]
        opened = opened_connections(tp, ports)
        kinds.append([("request" if p[2] in ports else "response",
                       "".join(n for bit, n in FLAGS if p[5] & bit), p[3], p[4])
                      for p in tp if (p[1], p[2]) not in opened and (p[2], p[1]) not in opened])
    return {v: np.stack(x).astype(np.float32) for v, x in X.items()}, np.array(left), kinds, left_p75


def mechanism(y, g, cl, sp, X: dict, kinds: list, left_p75: list) -> dict:
    """Which leftover packets move the request-size feature and the workflow score."""
    j = FLAT_FEATURE_NAMES().index(SIZE_FEATURE)
    pred = {v: oof_predict("gbt", "workflow", X[v], y, sp) for v in VARIANTS}
    packets = {}
    for w in cl:
        c = Counter(f"{dr} {fl} {wire} B" + (f" (payload {pl} B)" if pl else "")
                    for k, kd in zip(y, kinds) if k == w for dr, fl, wire, pl in kd)
        packets[w] = dict(c.most_common())
    ends = {}
    for w in cl:
        t = [kd for k, kd in zip(y, kinds) if k == w]
        ends[w] = {"traces_with_leftover": int(sum(bool(kd) for kd in t)),
                   "traces_with_caller_rst": int(sum(any(dr == "request" and "R" in fl for dr, fl, _, _ in kd) for kd in t)),
                   "traces_with_close_notify": int(sum(any(dr == "response" and pl == 24 for dr, _, _, pl in kd) for kd in t)),
                   "traces": len(t)}
    return {
        "size_feature": SIZE_FEATURE, "variants": VARIANTS,
        "size_feature_by_workflow": {v: {w: {"mean": float(X[v][y == w, j].mean()),
                                             "median": float(np.median(X[v][y == w, j]))} for w in cl}
                                     for v in VARIANTS},
        "size_feature_auc_rr_over_st": {v: auc(X[v][y == RR, j], X[v][y == ST, j]) for v in VARIANTS},
        "workflow_gbt": {v: score(y, pred[v], g, cl) for v in VARIANTS},
        "minus_own": {v: paired_diff(y, pred[v], pred["own"], g, cl) for v in VARIANTS if v != "own"},
        "leftover_packets_by_workflow": packets,
        "leftover_endings_by_workflow": ends,
        "leftover_flow_request_p75_by_workflow": {
            w: {f"{k:g}": n for k, n in sorted(Counter(v for k2, lp in zip(y, left_p75) if k2 == w
                                                         for v in lp).items())} for w in cl},
    }


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
        V, left, kinds, left_p75 = own_connection_vectors(d, Path(raw))
        Xo = V["own"]
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
        res["mechanism"] = mechanism(y, g, cl, sp, V, kinds, left_p75)
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
    L += mechanism_report(R)
    path.write_text("\n".join(L) + "\n")


def mechanism_report(R: dict) -> list[str]:
    t = R["TLS control, TLS arm"]["mechanism"]
    c = R["TLS control, cleartext arm"]["mechanism"]
    f = t["size_feature"]
    L = ["", "## 5. Which leftover packets move the features", "",
         "Wire sizes are on the loopback capture (4 B link header): a header-only ACK or FIN with TCP "
         "timestamps is 56 B, a caller RST without options 44 B, an ACK with SACK blocks 68 B, and a TLS "
         "1.3 close_notify alert record 24 B of payload (80 B on the wire).", "",
         "Leftover packets per workflow (packets in all traces of that workflow; direction, TCP flags, "
         "wire size):", "", "| Workflow | " + " | ".join(R) + " |", "|---|" + "---|" * len(R)]
    for w in t["leftover_packets_by_workflow"]:
        L.append(f"| {w} | " + " | ".join(
            ", ".join(f"{k} ×{n}" for k, n in R[s]["mechanism"]["leftover_packets_by_workflow"][w].items())
            for s in R) + " |")
    L += ["", "Traces whose leftover connections include a caller RST / an agent close_notify "
          "(of traces with leftover packets):", "", "| Workflow | " + " | ".join(R) + " |",
          "|---|" + "---|" * len(R)]
    for w in t["leftover_endings_by_workflow"]:
        L.append(f"| {w} | " + " | ".join(
            "{traces_with_caller_rst} / {traces_with_close_notify} of {traces_with_leftover}".format(
                **R[s]["mechanism"]["leftover_endings_by_workflow"][w]) for s in R) + " |")
    L += ["", "Request-size 75th percentile of each leftover flow (wire bytes: number of leftover flows); own "
          "flows almost always sit at 56 B, the header-only ACK that dominates a flow's request direction:", "",
          "| Workflow | " + " | ".join(R) + " |", "|---|" + "---|" * len(R)]
    for w in t["leftover_flow_request_p75_by_workflow"]:
        L.append(f"| {w} | " + " | ".join(
            ", ".join(f"{k} B: {n}" for k, n in R[s]["mechanism"]["leftover_flow_request_p75_by_workflow"][w].items())
            for s in R) + " |")
    L += ["", f"`{f}` (mean per workflow; research retrieval vs support triage AUC) and GBT workflow "
          "macro-F1, with only the leftover packets of one direction put back on top of own connections; "
          "paired difference to own connections only:", "",
          "| Set | Measurement | " + " | ".join(t["size_feature_by_workflow"]["own"]) +
          " | AUC RR/ST | Workflow macro-F1 | − own |", "|---|---|" + "---|" * (len(t["size_feature_by_workflow"]["own"]) + 3)]
    for s in R:
        m = R[s]["mechanism"]
        for v, label in m["variants"].items():
            L.append(f"| {s} | {label} | " + " | ".join(f"{m['size_feature_by_workflow'][v][w]['mean']:.2f}"
                                                         for w in m["size_feature_by_workflow"][v]) +
                     f" | {m['size_feature_auc_rr_over_st'][v]:.2f} | {_c(m['workflow_gbt'][v])} | " +
                     (_d(m["minus_own"][v]) if v in m["minus_own"] else "") + " |")
    a, sw = t["size_feature_auc_rr_over_st"], t["size_feature_by_workflow"]
    e, ce = t["leftover_endings_by_workflow"], c["leftover_endings_by_workflow"]
    m = lambda v, w: sw[v][w]["mean"]  # noqa: E731
    others = [w for w in sw["own"] if w != RR]
    L += ["", f"Mechanism. The 24 B close_notify alerts travel agent → caller (response direction), so they "
          f"cannot move request-size features. With only the leftover response-direction packets put back "
          f"(close_notify alerts, the agent's ACKs and FINs), every leftover flow adds a request size of 0 to "
          f"the mean over flows: `{f}` falls for all workflows alike "
          f"({min(m('left_response', w) for w in sw['own']):.1f}–{max(m('left_response', w) for w in sw['own']):.1f} B) "
          f"and separates research retrieval from support triage at AUC {a['left_response']:.2f}. With only the "
          f"caller's leftover packets put back (header-only ACKs, FINs and RSTs), AUC is {a['left_request']:.2f}, "
          f"as with every leftover packet ({a['all']:.2f}). Every own flow's request direction is dominated "
          f"by 56 B header-only ACKs, so its 75th percentile is almost always 56 B. A leftover connection the caller ends with "
          f"a FIN (56 B) and an RST (44 B) has a lower percentile and pulls the trace mean down: for "
          + ", ".join(f"{w} {m('own', w):.2f} → {m('left_request', w):.2f} B" for w in others) +
          f". The connections left by support triage, the fixed predecessor of research retrieval, end "
          f"differently: in {e[RR]['traces_with_close_notify']} of {e[RR]['traces_with_leftover']} research "
          f"retrieval traces with leftovers the agent closes with close_notify and the caller answers with "
          f"ACKs (56 B, 68 B with SACK blocks), keeping that flow's percentile at or above 56 B, so research "
          f"retrieval stays at {m('left_request', RR):.2f} B ({m('own', RR):.2f} B on own connections). No "
          f"other workflow's leftovers on the TLS arm contain a close_notify "
          f"({', '.join(str(e[w]['traces_with_close_notify']) for w in others)} traces).", "",
          f"Both directions carry the predecessor. On the TLS arm, workflow macro-F1 rises over own "
          f"connections by {_d(t['minus_own']['left_request'])} with the caller's leftover packets, "
          f"{_d(t['minus_own']['left_response'])} with the agent's (the close_notify itself marks research "
          f"retrieval) and {_d(t['minus_own']['all'])} with both. On the cleartext arm the leftover "
          f"connections end with FINs and ACKs only (caller RSTs in "
          f"{sum(x['traces_with_caller_rst'] for x in ce.values())} traces, close_notify in none); `{f}` "
          f"separates at AUC {c['size_feature_auc_rr_over_st']['all']:.2f} and all − own is "
          f"{_d(c['minus_own']['all'])}.", "",
          "Conclusion: removing leftover connections removes the effect (section 4)."]
    return L


if __name__ == "__main__":
    main()
