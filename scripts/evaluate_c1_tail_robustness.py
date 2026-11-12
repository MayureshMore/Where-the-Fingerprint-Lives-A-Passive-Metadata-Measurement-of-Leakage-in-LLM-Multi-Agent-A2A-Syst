#!/usr/bin/env python3
"""
Paper 1: are the C1 results robust to the connection closes the old recorder lost?

Until commit f38a2828 the recorder lost the last packets before each stop (DATA.md, "Known
limitation"; scripts/check_capture_tail.py). Those packets were connection closes, and which
connection closes in that window depends on the topology and the agent's role, so the loss could
carry role information. Three parts:

  A  which connections lose their close
       tail check (data/raw_c1_tailcheck, 12 C1-style traces with a complete ground-truth capture):
       the packets lost per trace, by topology and role
       C1: how each of the trace's own connections ends inside its capture (FIN, RST, neither),
       how many packets follow its last data packet, and whether a TLS close_notify alert is
       among them, by topology × role and workflow × role; the share of traces with at least one
       connection without a FIN or RST
  B  the cut removes the loss
       on the tail check, every feature with each connection ending at its last data packet
       (features/connections.py, end_at_data) for the recorded and the complete capture: the 35
       per-connection features and the 195 trace features must be identical
  C  paper 1's numbers in the new view
       scripts/evaluate_c1.py and evaluate_c1_revision.py on features of the new view, the same folds
       (5-fold StratifiedGroupKFold by prompt group, seed 42) and bootstrap (2000 group resamples,
       seed 42):
         Table 2      closed world GBT, RF and k-FP; GBT on the k-FP features (A5)
         families     GBT on sizes only, timing only, counts and direction only (role timing only)
         one feature  role from the best feature of the cumulative byte profile (cumul_bytes_q*)
         time split   temporal holdout GBT (train rounds 1-3, test 4-5) for every task; workflow's
                      size-matched CV GBT (the same training size, no time gap)
         first request  workflow from the first request's size alone (compared trace by trace)
         role held out  leave-one-topology-out and leave-one-workflow-out folds (A7), per held-out
                      value with CIs; the star confusion when star is held out
         topology rule  the fixed rule from calls and their nesting (A6)
         all connections  evaluate_c1.py's sensitivity check (every connection on the agent ports):
                      the all-connections numbers and own − all in both views
       The old numbers are recomputed from the published features with the same code and checked
       against the committed c1_evaluation_own.json and c1_revision.json. new − old is a paired
       group bootstrap on the same resamples; a number is flagged when the new point estimate
       falls outside the old 95% CI. C1's TCP retransmissions are counted in both variants.

Variants (--variant):
  dataend   every connection ends at its last data packet (features/connections.py, end_at_data)
            → c1_tail_robustness.{json,md}; parts A and B as above
  dedup     every payload byte counted once, TCP retransmissions dropped (features/kfp.py, dedup),
            nothing else changed → c1_dedup_robustness.{json,md}

Usage:
    python scripts/extract_features.py --raw data/raw_c1 --out data/processed_c1_dataend --scapy --end-at-data
    python scripts/extract_features.py --raw data/raw_c1 --out data/processed_c1_dataend_all --scapy --end-at-data \
        --legacy-all-connections
    python scripts/evaluate_c1_tail_robustness.py
    python scripts/extract_features.py --raw data/raw_c1 --out data/processed_c1_dedup --scapy --dedup
    python scripts/extract_features.py --raw data/raw_c1 --out data/processed_c1_dedup_all --scapy --dedup \
        --legacy-all-connections
    python scripts/evaluate_c1_tail_robustness.py --variant dedup
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

import scripts.evaluate_c1 as ev  # noqa: E402
import scripts.evaluate_c1_revision as rev  # noqa: E402
from features.connections import (  # noqa: E402
    CLOSE_ALERT_LEN, FIN, RST, connection_of, data_ends, opened_connections, own_packets,
)
from features.extractor import FeatureExtractor  # noqa: E402
from features.families import FAMILIES, family_columns  # noqa: E402
from features.first_request import first_request  # noqa: E402
from features.kfp import tcp_packets  # noqa: E402
from features.names import FLAT_FEATURE_NAMES  # noqa: E402
from features.per_flow import PerFlowFeatures  # noqa: E402
from features.roles import role_vectors  # noqa: E402
from scripts.check_capture_tail import complete_capture  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

RESULTS = Path(os.environ.get("A2A_RESULTS_DIR", "data/results"))
FLAGS = ((0x02, "S"), (0x10, "A"), (0x01, "F"), (0x04, "R"), (0x08, "P"))


def _flags(f: int) -> str:
    return "".join(n for b, n in FLAGS if f & b)


def _sidecars(raw: Path):
    for side in sorted(raw.glob("*.json")):
        sc = json.loads(side.read_text())
        if "run_id" in sc and sc.get("success", True):
            yield side, sc, {int(v.rsplit(":", 1)[1]): r for r, v in sc["agent_endpoints"].items()}


# ── A: which connections lose their close ───────────────────────────────────

def tail_losses(tail_dir: Path) -> dict:
    """The packets the old recorder lost in each tail-check trace (recorded vs ground truth)."""
    stops = json.loads((tail_dir / "stops.json").read_text())
    gt = tcp_packets(tail_dir / "ground_truth.pcap")
    traces, by_role = [], defaultdict(Counter)
    for side, sc, port_role in _sidecars(tail_dir / "c1like"):
        pcap = side.with_suffix(".pcap")
        rec = tcp_packets(pcap)
        conns = opened_connections(rec, set(port_role))
        last, stop = max(p[0] for p in rec), stops[pcap.name]
        lost = [p for p in gt if last + 1e-3 < p[0] <= stop and connection_of(p[1], p[2], set(port_role)) in conns]
        roles = Counter(port_role[connection_of(p[1], p[2], set(port_role))[1]] for p in lost)
        for r in {port_role[c[1]] for c in conns}:          # roles with a connection in the capture
            by_role[sc["topology"]][r] += int(r in roles)
        traces.append({"topology": sc["topology"], "workflow": sc["workflow_class"],
                       "stop_minus_last_recorded_s": round(stop - last, 3),
                       "lost": [{"role": port_role[connection_of(p[1], p[2], set(port_role))[1]],
                                 "direction": "client→agent" if p[2] in port_role else "agent→client",
                                 "flags": _flags(p[5]), "payload": p[4]} for p in lost],
                       "lost_data_packets": sum(1 for p in lost if p[4] > 0 and p[4] != CLOSE_ALERT_LEN)})
    n_top = Counter(t["topology"] for t in traces)
    return {"traces": traces,
            "share_of_traces_losing_packets_by_topology_and_role":
                {top: {r: f"{c} of {n_top[top]}" for r, c in sorted(rs.items())} for top, rs in sorted(by_role.items())},
            "lost_data_packets": sum(t["lost_data_packets"] for t in traces)}


def census(raw: Path) -> dict:
    """How every own connection of C1 ends inside its trace's capture."""
    end = defaultdict(Counter)                 # (topology, role) → end state
    end_wf = defaultdict(Counter)              # (workflow, role) → end state
    after = defaultdict(list)                  # (topology, role) → packets after the last data packet
    alert = defaultdict(Counter)               # (topology, role) → trailing close_notify alerts
    removed, traces_open, n_conn, n_traces = [], 0, 0, 0
    for side, sc, port_role in _sidecars(raw):
        pk = tcp_packets(side.with_suffix(".pcap"))
        servers = set(port_role)
        own = own_packets(pk, servers)
        ends = data_ends(own, servers)
        per_conn = defaultdict(list)
        for p in own:
            per_conn[connection_of(p[1], p[2], servers)].append(p)
        any_open = False
        for conn, cp in per_conn.items():
            role = port_role[conn[1]]
            key, wkey = f"{sc['topology']}/{role}", f"{sc['workflow_class']}/{role}"
            state = ("rst" if any(p[5] & RST for p in cp) else
                     "fin" if any(p[5] & FIN for p in cp) else "neither")
            any_open |= state == "neither"
            end[key][state] += 1
            end_wf[wkey][state] += 1
            tail = cp[ends[conn]:]
            after[key].append(len(tail))
            alert[key]["trailing_alert" if any(p[4] == CLOSE_ALERT_LEN for p in tail) else "none"] += 1
            n_conn += 1
        removed.append(len(own) - len(own_packets(pk, servers, end_at_data=True)))
        traces_open += any_open
        n_traces += 1
    return {"connections": n_conn, "traces": n_traces,
            "traces_with_a_connection_without_fin_or_rst": traces_open,
            "end_state_by_topology_role": {k: dict(v) for k, v in sorted(end.items())},
            "end_state_by_workflow_role": {k: dict(v) for k, v in sorted(end_wf.items())},
            "packets_after_last_data_by_topology_role": {
                k: {"median": float(np.median(v)), "max": int(max(v)), "mean": float(np.mean(v))}
                for k, v in sorted(after.items())},
            "trailing_close_alert_by_topology_role": {k: dict(v) for k, v in sorted(alert.items())},
            "packets_removed_per_trace": {"median": float(np.median(removed)), "max": int(max(removed)),
                                          "total": int(sum(removed))}}


# ── B: the cut removes the loss ─────────────────────────────────────────────

def _vectors(pcap: Path, port_role: dict[int, str], end_at_data: bool):
    ex = FeatureExtractor(agent_ports=set(port_role), use_scapy=True, own_connections=True, end_at_data=end_at_data)
    packets = ex._read_pcap(pcap)
    trace = np.asarray(ex._compute_features(pcap.stem, packets).flat_vector(), float)
    roles = {role: np.asarray(vec, float) for _, (role, vec, _, _) in
             role_vectors(ex, packets, {str(p): r for p, r in port_role.items()}).items()}
    return trace, roles


def cut_check(tail_dir: Path) -> dict:
    stops = json.loads((tail_dir / "stops.json").read_text())
    gt_raw = (tail_dir / "ground_truth.pcap").read_bytes()
    pf_names, tr_names = PerFlowFeatures.FEATURE_NAMES(), FLAT_FEATURE_NAMES()
    rows = []
    with tempfile.TemporaryDirectory(prefix="tailrobust_") as tmp:
        for side, sc, port_role in _sidecars(tail_dir / "c1like"):
            pcap = side.with_suffix(".pcap")
            conns = opened_connections(tcp_packets(pcap), set(port_role))
            full = Path(tmp) / pcap.name
            n_tail, n_missing = complete_capture(pcap.read_bytes(), gt_raw, conns, stops[pcap.name], full)
            assert n_tail == n_missing, (pcap.name, n_tail, n_missing)
            r = {"trace": pcap.stem, "lost": n_tail}
            for cut in (False, True):
                t_rec, r_rec = _vectors(pcap, port_role, cut)
                t_full, r_full = _vectors(full, port_role, cut)
                assert set(r_rec) == set(r_full)
                pf_diff = [i for role in r_full for i in np.flatnonzero(r_full[role] != r_rec[role])]
                r["cut" if cut else "as_recorded"] = {
                    "trace_features_changed": [tr_names[i] for i in np.flatnonzero(t_full != t_rec)],
                    "per_connection_features_changed": sorted({pf_names[i] for i in pf_diff})}
            rows.append(r)
    n_changed = lambda k, f: sum(1 for r in rows if r[k][f])             # noqa: E731
    return {"traces": rows,
            "as_recorded": {"traces_with_a_changed_trace_feature": n_changed("as_recorded", "trace_features_changed"),
                            "traces_with_a_changed_per_connection_feature":
                                n_changed("as_recorded", "per_connection_features_changed")},
            "cut": {"traces_with_a_changed_trace_feature": n_changed("cut", "trace_features_changed"),
                    "traces_with_a_changed_per_connection_feature": n_changed("cut", "per_connection_features_changed")},
            "identical_with_cut": all(not r["cut"]["trace_features_changed"] and
                                      not r["cut"]["per_connection_features_changed"] for r in rows)}


# ── C: paper 1's numbers in the new view ────────────────────────────────────

VARIANTS = {
    "dataend": {"new": "data/processed_c1_dataend", "all": "data/processed_c1_dataend_all", "end_at_data": True,
                "dedup": False, "name": "c1_tail_robustness", "label": "with the cut",
                "view": "every own connection ends at its last packet with TCP payload > 0, a 24-byte TLS "
                        "close_notify alert not counted (features/connections.py, end_at_data); every later "
                        "packet is dropped"},
    "dedup": {"new": "data/processed_c1_dedup", "all": "data/processed_c1_dedup_all", "end_at_data": False,
              "dedup": True, "name": "c1_dedup_robustness", "label": "deduplicated",
              "view": "every payload byte counted once: a TCP retransmission is dropped (features/kfp.py, dedup); "
                      "nothing else changes"},
}
V: dict = VARIANTS["dataend"]


def view(pcap: Path, servers: set[int], new: bool, legacy: bool = False) -> list:
    """The packets the features see: the published measurement (new=False) or this variant's."""
    return own_packets(tcp_packets(pcap, dedup=new and V["dedup"]), servers, legacy, new and V["end_at_data"])


def compare(name: str, task: str, y, g, classes, p_old, p_new, committed: float | None) -> dict:
    old, new = ev.score(y, p_old, g, classes), ev.score(y, p_new, g, classes)
    return {"name": name, "task": task, "old": old, "new": new,
            "committed": committed,
            "old_matches_committed": None if committed is None else bool(abs(old["macro_f1"] - committed) < 1e-9),
            "new_minus_old": ev.paired_diff(y, p_new, p_old, g, classes),
            "outside_old_ci": bool(not old["ci_lo"] <= new["macro_f1"] <= old["ci_hi"])}


def _same_rows(a: dict, b: dict) -> None:
    assert a["run_id"] == b["run_id"], "the new view changed which samples exist"
    assert (a["y"] == b["y"]).all() and (a["g"] == b["g"]).all()


def held_out_predictions(d: dict, key: np.ndarray):
    sp = [(np.where(key != v)[0], np.where(key == v)[0]) for v in sorted(set(key.tolist()))]
    return ev.oof_predict("gbt", "role", d["X"], d["y"], sp), sorted(set(key.tolist()))


def first_request_sizes(d: dict, raw: Path, new: bool, legacy: bool = False) -> np.ndarray:
    return np.array([first_request(view(raw / f"{b}.pcap", servers, new, legacy), servers, legacy)["bytes"]
                     for b, servers in ((b, {int(a.rsplit(":", 1)[1]) for a in e.values()})
                                        for b, e in zip(d["base"], d["endpoints"]))], dtype=np.float32)


def topology_rule_predictions(d: dict, raw: Path, new: bool) -> np.ndarray:
    pred = []
    for base, eps in zip(d["base"], d["endpoints"]):
        servers = rev.servers_of(eps)
        cs = rev.calls(view(raw / f"{base}.pcap", servers, new), servers)
        pred.append(rev.topology_rule(len(cs), rev.nesting(cs)))
    return np.array(pred)


def kfp_matrices(d_old: dict, d_new: dict, raw: Path):
    ev.END_AT_DATA, ev.DEDUP = False, False
    k_old = ev.kfp_matrix(d_old, raw)
    ev.END_AT_DATA, ev.DEDUP = V["end_at_data"], V["dedup"]
    k_new = ev.kfp_matrix(d_new, raw)
    ev.END_AT_DATA, ev.DEDUP = False, False
    return k_old, k_new


def temporal_predictions(task: str, d: dict):
    """The temporal holdout of evaluate_c1.temporal: train rounds 1–3 minus every prompt in rounds
    4–5, test rounds 4–5; returns (test mask, predictions, training size)."""
    tr_all, te = np.isin(d["round"], ev.TRAIN_ROUNDS), np.isin(d["round"], ev.TEST_ROUNDS)
    tr = tr_all & ~np.isin(d["g"], np.unique(d["g"][te]))
    return te, ev.make_model("gbt", task).fit(d["X"][tr], d["y"][tr]).predict(d["X"][te]), int(tr.sum())


def star_loto_confusion(y, p_old, p_new, top, classes) -> dict:
    m = top == "star"
    conf = lambda p: {t: {q: int(((y[m] == t) & (p[m] == q)).sum()) for q in classes} for t in classes}  # noqa: E731
    out = {"classes": classes, "old": conf(p_old), "new": conf(p_new)}
    for k in ("old", "new"):
        c = out[k]
        out[f"{k}_executor_retriever_as_validator"] = sum(c[t].get("validator", 0) for t in ("executor", "retriever"))
        out[f"{k}_executor_retriever"] = sum(sum(c[t].values()) for t in ("executor", "retriever"))
    return out


def rerun(old_dir: Path, new_dir: Path, raw: Path, committed_eval: dict, committed_rev: dict) -> tuple[list, dict]:
    out, extra = [], {}
    ce_all = committed_eval["results"]
    a5 = committed_rev["results"]["A5_kfp_features_gbt"]
    for task in ev.TASKS:
        d_old, d_new = ev.load(old_dir, raw, task), ev.load(new_dir, raw, task)
        _same_rows(d_old, d_new)
        y, g = d_old["y"], d_old["g"]
        classes = sorted(set(y.tolist()))
        splits = ev.folds(y, g)
        ce = ce_all[task]
        logger.info("[%s] n=%d", task, len(y))
        for m in ("gbt", "rf"):
            out.append(compare(f"closed world {m.upper()}", task, y, g, classes,
                               ev.oof_predict(m, task, d_old["X"], y, splits),
                               ev.oof_predict(m, task, d_new["X"], y, splits), ce["closed_world"][m]["macro_f1"]))
        k_old, k_new = kfp_matrices(d_old, d_new, raw)
        out.append(compare("closed world k-FP", task, y, g, classes, ev.oof_predict("kfp", task, k_old, y, splits),
                           ev.oof_predict("kfp", task, k_new, y, splits), ce["kfp"]["macro_f1"]))
        out.append(compare("GBT on the k-FP features (A5)", task, y, g, classes,           # (a)
                           ev.oof_predict("gbt", task, k_old, y, splits), ev.oof_predict("gbt", task, k_new, y, splits),
                           a5[task]["gbt_kfp_features"]["macro_f1"]))
        for fam in FAMILIES:
            cols = family_columns(fam, task == "role")
            out.append(compare(f"GBT, {fam.replace('_', ' and ')} only", task, y, g, classes,
                               ev.oof_predict("gbt", task, d_old["X"][:, cols], y, splits),
                               ev.oof_predict("gbt", task, d_new["X"][:, cols], y, splits),
                               ce["ablation"][fam]["macro_f1"]))
        te, t_old, n_tr = temporal_predictions(task, d_old)                                # (c)
        _, t_new, _ = temporal_predictions(task, d_new)
        r = compare("temporal holdout GBT (train rounds 1–3, test 4–5)", task, y[te], g[te], classes, t_old, t_new,
                    ce["temporal"]["gbt"]["macro_f1"])
        r["n_train"] = n_tr
        out.append(r)
        if task == "workflow":
            out.append(compare("size-matched CV GBT (no time gap)", task, y, g, classes,
                               ev.oof_predict_size_matched("gbt", task, d_old["X"], y, g, splits, n_tr),
                               ev.oof_predict_size_matched("gbt", task, d_new["X"], y, g, splits, n_tr),
                               ce["size_matched_cv"]["gbt"]["macro_f1"]))
            f_old, f_new = first_request_sizes(d_old, raw, False), first_request_sizes(d_new, raw, True)
            r = compare("GBT, first-request size alone", task, y, g, classes,
                        ev.oof_predict("gbt", task, f_old[:, None], y, splits),
                        ev.oof_predict("gbt", task, f_new[:, None], y, splits),
                        ce["length_checks"]["first_request_bytes"]["macro_f1"])
            r["first_request_identical_in_every_trace"] = bool(np.array_equal(f_old, f_new))
            out.append(r)
        if task == "role":
            names = PerFlowFeatures.FEATURE_NAMES()                                         # (b)
            single = ce["single_feature"]["single_feature_macro_f1"]
            cumul = [n for n in names if n.startswith("cumul_bytes_q")]
            best_old = max(cumul, key=lambda n: single[n])
            f1_new = {n: ev.score(y, ev.oof_predict("gbt", task, d_new["X"][:, [names.index(n)]], y, splits), g,
                                  classes)["macro_f1"] for n in cumul}
            best_new = max(cumul, key=lambda n: f1_new[n])
            col = names.index(best_old)
            out.append(compare(f"GBT, {best_old} alone (best of the cumulative byte profile)", task, y, g, classes,
                               ev.oof_predict("gbt", task, d_old["X"][:, [col]], y, splits),
                               ev.oof_predict("gbt", task, d_new["X"][:, [col]], y, splits), single[best_old]))
            if best_new != best_old:
                col = names.index(best_new)
                out.append(compare(f"GBT, {best_new} alone (best of the cumulative byte profile in the new view)",
                                   task, y, g, classes, ev.oof_predict("gbt", task, d_old["X"][:, [col]], y, splits),
                                   ev.oof_predict("gbt", task, d_new["X"][:, [col]], y, splits), single[best_new]))
            extra["cumulative_byte_profile_single_feature"] = {
                n: {"old": single[n], "new": f1_new[n]} for n in cumul}
            wf_of = {b: w for b, w in zip(*_trace_labels(old_dir, "workflow"))}
            a7 = committed_rev["results"]["A7_role_held_out"]
            top = np.array(d_old["topology"])
            for name, key in (("leave_one_topology_out", top),
                              ("leave_one_workflow_out", np.array([wf_of[b] for b in d_old["base"]]))):
                (p_old, held), (p_new, _) = held_out_predictions(d_old, key), held_out_predictions(d_new, key)
                r = compare(f"GBT, role {name.replace('_', '-')}", task, y, g, classes, p_old, p_new,
                            a7[name]["macro_f1"])
                r["per_held_out"] = {v: {"old": ev.score(y[key == v], p_old[key == v], g[key == v], classes),
                                         "new": ev.score(y[key == v], p_new[key == v], g[key == v], classes),
                                         "new_minus_old": ev.paired_diff(y[key == v], p_new[key == v], p_old[key == v],
                                                                         g[key == v], classes)}
                                     for v in held}
                out.append(r)
                if name == "leave_one_topology_out":                                        # (d)
                    extra["star_loto_confusion"] = star_loto_confusion(y, p_old, p_new, top, classes)
        if task == "topology":
            out.append(compare("fixed rule (A6)", task, y, g, classes,
                               topology_rule_predictions(d_old, raw, False), topology_rule_predictions(d_new, raw, True),
                               committed_rev["results"]["A6_topology_rule"]["macro_f1"]["macro_f1"]))
        logger.info("[%s] done: %s", task, ", ".join(f"{r['name']} {r['old']['macro_f1']:.3f}→{r['new']['macro_f1']:.3f}"
                                                     for r in out if r["task"] == task))
    return out, extra


def all_connections(own_old: Path, all_old: Path, own_new: Path, all_new: Path, raw: Path, committed: dict) -> list:
    """(e) evaluate_c1's sensitivity check, every connection on the agent ports instead of the
    trace's own, in the published view and in the new one: the all-connections numbers old vs
    new, and own − all in each view."""
    rows = []
    for task in ev.TASKS:
        dOo, dAo, dOn, dAn = (ev.load(p, raw, task) for p in (own_old, all_old, own_new, all_new))
        for d in (dAo, dOn, dAn):
            _same_rows(dOo, d)
        y, g = dOo["y"], dOo["g"]
        classes, sp = sorted(set(y.tolist())), ev.folds(y, g)
        cs = committed["tasks"][task]
        sets = [("GBT", "gbt"), ("RF", "rf")] + ([("first request only (GBT)", "first_request")] if task != "role" else [])
        for label, key in sets:
            model = "rf" if key == "rf" else "gbt"
            if key == "first_request":
                XOo, XAo, XOn, XAn = (first_request_sizes(dOo, raw, new, legacy)[:, None]
                                      for new, legacy in ((False, False), (False, True), (True, False), (True, True)))
            else:
                XOo, XAo, XOn, XAn = (d["X"] for d in (dOo, dAo, dOn, dAn))
            pOo, pAo, pOn, pAn = (ev.oof_predict(model, task, X, y, sp) for X in (XOo, XAo, XOn, XAn))
            r = compare(f"all connections, {label}", task, y, g, classes, pAo, pAn, cs[key]["legacy"]["macro_f1"])
            r["own_minus_all_old"] = ev.paired_diff(y, pOo, pAo, g, classes)
            r["own_minus_all_new"] = ev.paired_diff(y, pOn, pAn, g, classes)
            rows.append(r)
    return rows


def _trace_labels(processed: Path, key: str):
    labels = json.loads((processed / "labels.json").read_text())
    rows = [(rid, info[key]) for rid, info in sorted(labels.items()) if "__role__" not in rid]
    return [r for r, _ in rows], [v for _, v in rows]


def baseline_check(old_dir: Path, recheck_dir: Path | None) -> dict | None:
    """A fresh extraction of the published view against the committed features (same code path)."""
    if recheck_dir is None:
        return None
    names = sorted(p.name for p in old_dir.glob("*.npz"))
    diffs = [float(np.max(np.abs(np.load(old_dir / n)["flat"] - np.load(recheck_dir / n)["flat"]))) for n in names]
    return {"dir": str(recheck_dir), "files": len(names), "max_abs_difference": max(diffs),
            "identical": max(diffs) == 0.0}


def retransmissions(raw: Path) -> dict:
    """C1's TCP retransmissions (features/kfp.py): count, sizes, own connections or not, and how
    many come before their connection's last data packet (the cut keeps those)."""
    from features.kfp import duplicate_bytes, is_retransmission, tcp_records
    n = traces = before_last_data = own = 0
    sizes, roles = Counter(), Counter()
    for side, sc, port_role in _sidecars(raw):
        recs = tcp_records(side.with_suffix(".pcap"))
        servers = set(port_role)
        opened = opened_connections([r[:6] for r in recs], servers)
        ends = data_ends([r[:6] for r in recs], servers)
        dups, seen, hit = duplicate_bytes(recs), Counter(), False
        for r, d in zip(recs, dups):
            c = connection_of(r[1], r[2], servers)
            if c is not None:
                seen[c] += 1
            if not (is_retransmission(r[:6], d) or 0 < d < r[4]):
                continue
            n += 1
            hit = True
            sizes[r[4]] += 1
            if c in opened:
                own += 1
                roles[port_role[c[1]]] += 1
            if c is not None and seen[c] <= ends.get(c, 0):
                before_last_data += 1
        traces += hit
    return {"segments": n, "traces_with_any": traces, "payload_sizes": dict(sizes),
            "on_the_traces_own_connections": own, "by_role_own": dict(roles),
            "before_their_connections_last_data_packet": before_last_data}


# ── report ──────────────────────────────────────────────────────────────────

def _git() -> dict:
    return ev._git()


def main(a: argparse.Namespace) -> None:
    global V
    V = VARIANTS[a.variant]
    raw, old_dir, tail_dir = Path(a.raw), Path(a.old), Path(a.tail)
    new_dir, all_new, all_old = Path(a.new or V["new"]), Path(a.all_new or V["all"]), Path(a.all_old)
    for d, legacy in ((new_dir, False), (all_new, True)):
        meta = json.loads((d / "extraction_meta.json").read_text())
        want = {"end_at_data": V["end_at_data"], "dedup": V["dedup"]}
        if {k: bool(meta.get(k)) for k in want} != want or ("legacy" in meta["measurement"]) != legacy:
            raise SystemExit(f"{d} was not extracted for this variant ({want}, all connections: {legacy}): {meta}")
    committed_eval = json.loads((RESULTS / "c1_evaluation_own.json").read_text())
    committed_rev = json.loads((RESULTS / "c1_revision.json").read_text())
    session = json.loads((raw / "session_meta.json").read_text())
    out = {"paper": "P1", "collection_id": session.get("collection_id", "C1"), "variant": a.variant,
           "data_dir": str(new_dir), "old_data_dir": str(old_dir), "all_connections_dirs": [str(all_old), str(all_new)],
           "raw_dir": str(raw), "seed": ev.SEED, **_git(),
           "task": "robustness of paper 1's results to the capture tail (connection closes the recorder lost "
                   "before f38a2828) and to TCP retransmissions",
           "view": V["view"], "label": V["label"],
           "committed": {"c1_evaluation_own": committed_eval["git_commit"], "c1_revision": committed_rev["git_commit"]}}
    out["retransmissions"] = retransmissions(raw)
    if a.variant == "dataend":
        logger.info("A: tail-check losses and the C1 census")
        out["tail_check_dir"] = str(tail_dir)
        out["tail_check_losses"] = tail_losses(tail_dir)
        out["census"] = census(raw)
        logger.info("B: the cut on the tail check")
        out["cut_check"] = cut_check(tail_dir)
        if not out["cut_check"]["identical_with_cut"]:
            raise SystemExit("the cut leaves recorded and complete tail-check features different: not rerunning")
    out["baseline_check"] = baseline_check(old_dir, Path(a.recheck) if a.recheck else None)
    logger.info("C: paper 1's numbers")
    out["comparisons"], out["detail"] = rerun(old_dir, new_dir, raw, committed_eval, committed_rev)
    logger.info("C (e): all connections in the capture")
    out["comparisons"] += all_connections(old_dir, all_old, new_dir, all_new, raw, committed_eval["sensitivity"])
    out["flagged"] = [f"{r['task']}: {r['name']}" for r in out["comparisons"] if r["outside_old_ci"]]
    out["old_reproduces_committed"] = all(r["old_matches_committed"] in (True, None) for r in out["comparisons"])
    out["old_not_matching_committed"] = [f"{r['task']}: {r['name']}" for r in out["comparisons"]
                                         if r["old_matches_committed"] is False]
    RESULTS.mkdir(parents=True, exist_ok=True)
    name = a.name or V["name"]
    (RESULTS / f"{name}.json").write_text(json.dumps(out, indent=2, default=str))
    (RESULTS / f"{name}.md").write_text(report(out))
    print(report(out))


def _ci(s: dict) -> str:
    return f"{s['macro_f1']:.3f} [{s['ci_lo']:.3f}, {s['ci_hi']:.3f}]"


def _d(d: dict) -> str:
    return f"{d['diff']:+.3f} [{d['ci_lo']:+.3f}, {d['ci_hi']:+.3f}]{'' if d['significant'] else ' (n.s.)'}"


def report(o: dict) -> str:
    lab = o["label"]
    title = ("robustness to the connection closes the old recorder lost" if o["variant"] == "dataend"
             else "robustness to TCP retransmissions")
    L = [f"# Paper 1: {title}", "",
         f"Commit `{o['git_commit'][:8]}` (dirty: {o['git_dirty']}), seed {o['seed']}. New features `{o['data_dir']}`; "
         f"old (published) features `{o['old_data_dir']}`; captures `{o['raw_dir']}`. Old numbers recomputed with "
         f"this code ({'identical to' if o['old_reproduces_committed'] else 'DIFFERENT from'} the committed "
         f"c1_evaluation_own and c1_revision, commit `{o['committed']['c1_evaluation_own'][:8]}`"
         + (f"; differing: {', '.join(o['old_not_matching_committed'])}" if o["old_not_matching_committed"] else "")
         + ").", "", f"New view: {o['view']}.", ""]
    rt = o["retransmissions"]
    L += ["## TCP retransmissions in C1", "",
          f"{rt['segments']} retransmitted data segments in {rt['traces_with_any']} of 600 traces (payload sizes "
          f"{rt['payload_sizes']}); {rt['on_the_traces_own_connections']} on the traces' own connections (by role "
          f"{rt['by_role_own']}); {rt['before_their_connections_last_data_packet']} before their connection's last "
          "data packet. The published extraction counts them; the cut drops every one after the last data packet.", ""]
    if o["variant"] == "dataend":
        c, t, k = o["census"], o["tail_check_losses"], o["cut_check"]
        L += ["## Which connections lose their close", "",
              "Tail check (12 C1-style traces with a complete ground-truth capture): traces in which a role's "
              "connection lost packets, by topology:", "",
              "| Topology | " + " | ".join(roles := sorted({r for v in t["share_of_traces_losing_packets_by_topology_and_role"].values()
                                                          for r in v})) + " |", "|---" * (len(roles) + 1) + "|"]
        for top, v in t["share_of_traces_losing_packets_by_topology_and_role"].items():
            L.append(f"| {top} | " + " | ".join(v.get(r, "–") for r in roles) + " |")
        L += ["", f"Lost data packets (payload > 0, not a close alert): {t['lost_data_packets']}.", "",
              f"C1 ({c['traces']} traces, {c['connections']} own connections): how each connection ends inside its "
              f"capture. {c['traces_with_a_connection_without_fin_or_rst']} of {c['traces']} traces have at least one "
              "connection with neither a FIN nor an RST.", "",
              "| Topology / role | FIN | RST | neither | packets after the last data packet (median, max) | trailing close alert |",
              "|---|---|---|---|---|---|"]
        for key, st in c["end_state_by_topology_role"].items():
            a, al = c["packets_after_last_data_by_topology_role"][key], c["trailing_close_alert_by_topology_role"][key]
            L.append(f"| {key} | {st.get('fin', 0)} | {st.get('rst', 0)} | {st.get('neither', 0)} | "
                     f"{a['median']:.0f}, {a['max']} | {al.get('trailing_alert', 0)} of {sum(st.values())} |")
        L += ["", "By workflow and role (FIN / RST / neither): " + "; ".join(
                  f"{k} {v.get('fin', 0)}/{v.get('rst', 0)}/{v.get('neither', 0)}"
                  for k, v in c["end_state_by_workflow_role"].items()) + ".", "",
              f"Packets the cut removes per trace: median {c['packets_removed_per_trace']['median']:.0f}, "
              f"max {c['packets_removed_per_trace']['max']}.", "",
              "## The cut removes the loss", "",
              f"Tail check, recorded vs complete capture: as recorded, {k['as_recorded']['traces_with_a_changed_trace_feature']} "
              f"of {len(k['traces'])} traces change in a trace feature and "
              f"{k['as_recorded']['traces_with_a_changed_per_connection_feature']} in a per-connection feature; with the "
              f"cut, {k['cut']['traces_with_a_changed_trace_feature']} and "
              f"{k['cut']['traces_with_a_changed_per_connection_feature']} "
              f"({'identical' if k['identical_with_cut'] else 'NOT identical'}).", ""]
    if o.get("baseline_check"):
        b = o["baseline_check"]
        L += [f"Re-extraction of the published view vs `{o['old_data_dir']}`: {b['files']} files, max |difference| "
              f"{b['max_abs_difference']:g} ({'identical' if b['identical'] else 'different'}).", ""]
    L += [f"## Paper 1's numbers: published vs {lab}", "",
          "macro-F1 with 95% cluster-bootstrap CIs over prompt groups; new − old paired on the same resamples "
          "(the temporal rows on the test rounds). Flag: the new point estimate is outside the old 95% CI.", "",
          f"| Task | Result | Published | {lab.capitalize()} | New − old | Flag |", "|---|---|---|---|---|---|"]
    for r in o["comparisons"]:
        L.append(f"| {r['task']} | {r['name']} | {_ci(r['old'])} | {_ci(r['new'])} | {_d(r['new_minus_old'])} | "
                 f"{'**outside**' if r['outside_old_ci'] else ''} |")
    for r in o["comparisons"]:
        if "per_held_out" in r:
            L += ["", f"{r['name']}, per held-out value (published → {lab}, paired difference):", ""] + [
                f"- {v}: {_ci(s['old'])} → {_ci(s['new'])}, {_d(s['new_minus_old'])}" for v, s in r["per_held_out"].items()]
        if "first_request_identical_in_every_trace" in r:
            L += ["", f"First-request size identical in both views in every trace: "
                      f"{r['first_request_identical_in_every_trace']}."]
        if "own_minus_all_old" in r:
            L += ["", f"{r['task']}, {r['name']}: own − all connections, published {_d(r['own_minus_all_old'])}; "
                      f"{lab} {_d(r['own_minus_all_new'])}."]
    s = o["detail"]["star_loto_confusion"]
    L += ["", "## Leave one topology out: the star traces (GBT trained on chain and mesh)", "",
          f"Star executors and retrievers labeled validator: published {s['old_executor_retriever_as_validator']} of "
          f"{s['old_executor_retriever']}; {lab} {s['new_executor_retriever_as_validator']} of {s['new_executor_retriever']}.",
          "", "| True / predicted | " + " | ".join(s["classes"]) + " |", "|---" * (len(s["classes"]) + 1) + "|"]
    for k in ("old", "new"):
        for t in s["classes"]:
            L.append(f"| {t} ({'published' if k == 'old' else lab}) | " + " | ".join(str(s[k][t][q]) for q in s["classes"]) + " |")
    cb = o["detail"]["cumulative_byte_profile_single_feature"]
    L += ["", "Role from one cumulative-byte feature alone (GBT macro-F1, published → " + lab + "): "
          + ", ".join(f"{n} {v['old']:.3f} → {v['new']:.3f}" for n, v in cb.items()) + ".",
          "", f"Flagged: {', '.join(o['flagged']) or 'none'}."]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--variant", choices=sorted(VARIANTS), default="dataend",
                   help="dataend: every connection cut at its last data packet; dedup: retransmissions dropped")
    p.add_argument("--raw", default="data/raw_c1")
    p.add_argument("--old", default="data/processed_c1_own")
    p.add_argument("--new", default=None, help="default per variant")
    p.add_argument("--all-old", default="data/processed_c1", dest="all_old",
                   help="the published all-connections features (evaluate_c1.py's sensitivity check)")
    p.add_argument("--all-new", default=None, dest="all_new", help="default per variant")
    p.add_argument("--tail", default="data/raw_c1_tailcheck")
    p.add_argument("--recheck", default=None,
                   help="a fresh extraction of the published view, compared with --old (same code path)")
    p.add_argument("--name", default=None, help="default per variant")
    main(p.parse_args())
