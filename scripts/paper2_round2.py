#!/usr/bin/env python3
"""
Paper 2, round 2: the reviewers' checks on C2 (and D1 where stated), with a2a-leakcheck 0.3.0's
defaults: the permutation test by prompt group (--perm-unit group) and the non-inferiority match rule
(match_margin 0.05). Writes data/results/paper2_round2.{json,md} (--merge) from parts, one per group
of sections, each run from a clean commit:

  a3   "matches all features" as non-inferiority: the upper bound of the paired 95% CI of
       F1(all) − F1(family) at most 0.05; the 0.1.x rule (lower bound <= 0) kept as no_detected_deficit.
       From the six C2 and two D1 committed reports (their stored CIs), and recomputed for task_type,
       sensor_analysis vs fault_diagnosis and the escalated-only task type in all six cells. Every
       "carried by" that changes.
  a4   the 480 permuted draws (6 cells x 4 attributes x 20) and the 6 audit_null controls with group-level
       permutation, both to draw the labels and inside each test, for a2a-leakcheck, k-FP and the
       first-request rule; the real-label verdicts of every cell (structural checks and learned rows);
       groups per class for C2 and D1; a check that no draw is reused by a test.
  a5   the permutation test's model: 6 audit_null controls and 40 permuted draws with the GBT as null
       model (99 permutations), and the adaptive rule (p in [0.02, 0.20] after 99: 999); verdict changes
       and runtime, with a Raspberry Pi estimate from the committed Pi timing.
  a7   repeated grouped splits: fold seeds 43-47 next to 42 for every cell and attribute.
  a8   a timestamps-only family (features/timestamps.py: flows ordered by start time, timestamps only)
       next to the timing family and all features; which timing columns depend on sizes or direction.
  a9   template-held-out: GroupKFold by the template factor each prompt was generated from (recovered
       by regenerating the prompts), next to the prompt-held-out numbers.
  a10  review burden: INCONCLUSIVE per attribute and per audit on permuted draws, and on the audit_null
       controls, at 50/100/150/200 traces per task type (and all, from a4).
  a11  a2a-leakcheck against k-FP: runtime, a plain k-FP pipeline, verdict agreement, and where each
       method's INCONCLUSIVEs come from (from a4).
  a12  accounting: the learned rows (task_type, sensor vs fault, escalated-only) as the main table; the
       structural checks (escalated, cloud_role) apart; the known non-leaks; all-zero V2 windows (from a4).

Usage (each part from a clean checkout, nothing else running; data/round2_parts is gitignored):
    python scripts/paper2_round2.py --sections a3,a8,a9 --out data/round2_parts/fast
    python scripts/paper2_round2.py --sections a4 --out data/round2_parts/a4            # about 11 h
    python scripts/paper2_round2.py --sections a5,a7 --out data/round2_parts/a5a7       # about 3 h
    python scripts/paper2_round2.py --sections a10,a11 --out data/round2_parts/a10a11   # about 5 h
    python scripts/paper2_round2.py --merge data/round2_parts/*.json --out data/results/paper2_round2
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from sklearn.metrics import f1_score

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from a2a_leakcheck.analyze import (INCONCLUSIVE, LEAK, NO_LEAK, Config, _oof, _score, _splits,  # noqa: E402
                                   analyze, group_plan, matches, permutations, permute_group, verdict)
from a2a_leakcheck.cli import _git  # noqa: E402
from a2a_leakcheck.collect import collect  # noqa: E402
from a2a_leakcheck.extract import extract  # noqa: E402
from a2a_leakcheck.rules import load_rules  # noqa: E402
from evaluation.stats import paired_bootstrap_diff  # noqa: E402
from features.connections import own_packets  # noqa: E402
from features.extractor import FeatureExtractor  # noqa: E402
from features.families import FAMILIES, family_columns  # noqa: E402
from features.kfp import tcp_packets  # noqa: E402
from features.per_flow import PerFlowFeatures  # noqa: E402
from features.per_system import PerSystemFeatures  # noqa: E402
from features.timestamps import names as ts_names, timestamp_vector  # noqa: E402
from scripts.evaluate_leakcheck import STREAMS, kfp_rows, subsample, wilson  # noqa: E402

SEED = 42
ARMS = {"lan": "data/raw_c2", "lan_pad": "data/raw_c2_pad", "lan_padmax": "data/raw_c2_padmax"}
CELLS = [f"{arm}_{v}" for arm in ARMS for v in ("v1", "v2")]
ATTRS = ("task_type", "escalated", "cloud_role", "audit_null")
STRUCTURAL = ("escalated", "cloud_role")
LEARNED = ("task_type", "pair", "escalated_only")
ESCALATED = ("fault_diagnosis", "procedure_lookup", "sensor_analysis")
PAIR = ("fault_diagnosis", "sensor_analysis")
METHODS = {"leakcheck": "gbt", "kfp_rf": "rf", "first_request": "gbt"}
VERDICTS = (LEAK, INCONCLUSIVE, NO_LEAK)
DRAW_STREAM, SUB_STREAM, SUB_PERM_STREAM = 8, 9, 10        # new streams, apart from the tests' (seed, 7, i)
A5_CELLS, A5_DRAWS = ("lan_v1", "lan_padmax_v2"), 5
D1_REPORTS = {"tls": "data/results/leakcheck/tls_control_tls_own", "cleartext": "data/results/leakcheck/tls_control_clear_own"}
D1_RAW = {"tls": "data/raw_tlspair_tls", "cleartext": "data/raw_tlspair_clear"}
SECTIONS = ("a3", "a4", "a5", "a7", "a8", "a9", "a10", "a11", "a12")
PI_REPORT, MAC_REPORT = "data/results/leakcheck_pi/c2_lan_v1/report.json", "data/results/leakcheck/c2_lan_v1/report.json"


# ── data ─────────────────────────────────────────────────────────────────────

def load_cell(cell: str) -> dict:
    """One arm at one view, as a2a_leakcheck run --vantage sees it (collect, extract, every trace kept),
    plus the k-FP vector (scripts/evaluate_leakcheck.py) and the timestamps-only vector per trace."""
    arm, view = cell.rsplit("_", 1)
    raw = Path(ARMS[arm])
    t = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="round2_") as tmp:
        col = collect(raw, list(ATTRS), strip_dir=Path(tmp), vantage=view)
        ext = extract(col["traces"], keep_empty=True)
        traces = [col["traces"][i] for i in ext["trace_index"]]
        kfp, ts, readers = [], [], {}
        for tr in traces:
            servers = set(tr.port_role)
            kfp.append(kfp_rows(own_packets(tcp_packets(tr.pcap, dedup=True), servers), servers, None))
            ex = readers.setdefault(frozenset(servers), FeatureExtractor(agent_ports=servers, use_scapy=True,
                                                                         own_connections=True, dedup=True))
            ts.append(timestamp_vector(ex._read_pcap(tr.pcap)))
    sidecars = [json.loads((raw / f"{Path(tr.pcap).stem}.json").read_text()) for tr in traces]
    X = ext["trace_X"]
    return {"cell": cell, "arm": arm, "view": view, "ids": [tr.run_id for tr in traces],
            "X": {"leakcheck": X, "kfp_rf": np.stack(kfp), "first_request": ext["first_request"].reshape(-1, 1),
                  "timestamps": np.stack(ts)},
            "labels": {a: np.array([tr.labels.get(a, "") for tr in traces]) for a in ATTRS},
            "g": np.array([tr.group for tr in traces]), "prompts": [s["input_prompt"] for s in sidecars],
            "all_zero": ~X.any(axis=1), "load_s": time.perf_counter() - t}


def samples(d: dict, task: str) -> tuple[np.ndarray, np.ndarray]:
    """(index of the traces, labels) of an attribute or a learned task."""
    tt = d["labels"]["task_type"]
    if task == "pair":
        idx = np.flatnonzero(np.isin(tt, PAIR))
        return idx, tt[idx]
    if task == "escalated_only":
        idx = np.flatnonzero(np.isin(tt, ESCALATED))
        return idx, tt[idx]
    y = d["labels"][task]
    idx = np.flatnonzero(y != "")
    return idx, y[idx]


def stream(task: str) -> int:
    return STREAMS.get(task, {"pair": 20, "escalated_only": 21}.get(task))


# ── verdicts ─────────────────────────────────────────────────────────────────

def cfg(method: str = "leakcheck", a: argparse.Namespace | None = None, **kw) -> Config:
    base = dict(margin=0.05, n_splits=5, n_boot=getattr(a, "n_boot", 1000), permutations=getattr(a, "permutations", 99),
                alpha=0.05, min_per_class=20, seed=SEED, model=METHODS[method], null_model="rf-light",
                jobs=getattr(a, "jobs", -1), perm_unit="group")
    return Config(**{**base, **kw})


def run(X, y, g, method: str, a, sev: dict, families=None, single=None, **kw) -> dict:
    t = time.perf_counter()
    r = analyze(X, y, g, families or {}, single, cfg(method, a, **kw), sev)
    an, perm = r["analysis"] or {}, r["validation"].get("permutation") or {}
    out = {"verdict": r["verdict"], "n": r["n"], "groups": r["n_groups"],
           "ci_verdict": verdict(an["ci_lo"], an["ci_hi"], r["chance"], r["margin"]) if an else None,
           "macro_f1": an.get("macro_f1"), "ci": [an.get("ci_lo"), an.get("ci_hi")], "p": perm.get("p_value"),
           "null_mean": perm.get("null_mean"), "permutations_run": perm.get("permutations_run"),
           "seconds": time.perf_counter() - t}
    if r.get("attribution"):
        out["attribution"] = r["attribution"]
    return out


def why(r: dict) -> str:
    """Where an INCONCLUSIVE comes from."""
    if r["verdict"] != INCONCLUSIVE:
        return "-"
    if r["ci_verdict"] is None:
        return "too few samples"
    return "CI straddles the threshold" if r["ci_verdict"] == INCONCLUSIVE else \
        f"permutation test disagrees with a {r['ci_verdict']}"


def counts(vs) -> dict:
    vs = list(vs)
    return {v: vs.count(v) for v in VERDICTS}


def draw(y, g, ai: int, k: int) -> np.ndarray:
    return permute_group(y, group_plan(y, g), np.random.default_rng([SEED, DRAW_STREAM, ai, k]))


def _h(y) -> str:
    return hashlib.sha1("\x1f".join(map(str, y)).encode()).hexdigest()


def carried(at: dict, rule: str) -> str:
    """The report's "carried by" under one rule: matches_all (non-inferiority) or no_detected_deficit."""
    if not at:
        return "—"
    def ok(v):
        if rule in v:
            return v[rule]
        return matches(v["all_minus_this"], 0.05)[rule]
    single = at.get("single_request_size") or {}
    if single and ok(single):
        return f"{single['feature']} alone"
    top = at.get("top_family")
    if not top:
        return "—"
    return top + (" (alone matches all)" if ok(at["families"][top]) else "")


# ── a3: the match rule ───────────────────────────────────────────────────────

def a3_reports() -> dict:
    out = {}
    paths = {**{f"C2 {c}": f"data/results/leakcheck/c2_{c}" for c in CELLS}, **{f"D1 {k}": v for k, v in D1_REPORTS.items()}}
    for name, p in paths.items():
        rep = json.loads((Path(p) / "report.json").read_text())
        for attr, r in rep["attributes"].items():
            at = r.get("attribution")
            if not at:
                continue
            fams = {f: {**{k: v["all_minus_this"][k] for k in ("diff", "ci_lo", "ci_hi")},
                        **matches(v["all_minus_this"], 0.05)} for f, v in at["families"].items()}
            s = at.get("single_request_size")
            row = {"verdict": r["verdict"], "families": fams,
                   "single": None if not s else {"feature": s["feature"], **{k: s["all_minus_this"][k] for k in ("diff", "ci_lo", "ci_hi")},
                                                 **matches(s["all_minus_this"], 0.05)},
                   "top_family": at.get("top_family"),
                   "carried_0_1": carried(at, "no_detected_deficit") if r["verdict"] == LEAK else "—",
                   "carried_0_3": carried(at, "matches_all") if r["verdict"] == LEAK else "—"}
            row["changed"] = row["carried_0_1"] != row["carried_0_3"]
            out[f"{name} / {attr}"] = row
    return out


def a3_learned(data: dict, a, sev) -> dict:
    out = {}
    fams = {f: family_columns(f, False) for f in FAMILIES}
    for cell, d in data.items():
        for task in LEARNED:
            idx, y = samples(d, task)
            r = run(d["X"]["leakcheck"][idx], y, d["g"][idx], "leakcheck", a, sev, families=fams,
                    single=("first_request_bytes", d["X"]["first_request"][idx, 0]), permutations=0)
            at = r.pop("attribution")
            out[f"{cell} / {task}"] = {
                "macro_f1": r["macro_f1"], "ci": r["ci"],
                "families": {f: {"macro_f1": v["macro_f1"], **{k: v["all_minus_this"][k] for k in ("diff", "ci_lo", "ci_hi")},
                                 "matches_all": v["matches_all"], "no_detected_deficit": v["no_detected_deficit"]}
                             for f, v in at["families"].items()},
                "top_family": at["top_family"],
                "carried_0_1": carried(at, "no_detected_deficit"), "carried_0_3": carried(at, "matches_all")}
            out[f"{cell} / {task}"]["changed"] = out[f"{cell} / {task}"]["carried_0_1"] != out[f"{cell} / {task}"]["carried_0_3"]
    return out


# ── a4: group-level permutation ──────────────────────────────────────────────

def group_sizes(g) -> dict:
    _, n = np.unique(g, return_counts=True)
    return {str(k): int((n == k).sum()) for k in np.unique(n)}


def groups_per_class(y, g) -> dict:
    return {str(c): int(len(np.unique(g[y == c]))) for c in sorted(set(y.tolist()))}


def d1_groups() -> dict:
    out = {}
    for arm, p in D1_REPORTS.items():
        rep = json.loads((Path(p) / "report.json").read_text())
        out[arm] = {attr: {"samples": r["n"], "groups": r["n_groups"],
                           "groups_per_class": r["validation"]["min_samples"]["groups_per_class"]}
                    for attr, r in rep["attributes"].items()}
        with tempfile.TemporaryDirectory(prefix="round2_d1_") as tmp:
            col = collect(Path(D1_RAW[arm]), ["workflow", "topology"], strip_dir=Path(tmp), cleartext=arm == "cleartext")
        out[arm]["trace_group_sizes"] = group_sizes(np.array([t.group for t in col["traces"]]))
    return out


def a4_cell(d: dict, a, sev) -> dict:
    out = {"traces": len(d["ids"]), "attributes": {}, "learned": {}, "reuse": {}}
    for attr in ATTRS:
        idx, y = samples(d, attr)
        g, ai = d["g"][idx], stream(attr)
        r = {"classes": counts_by(y), "groups": int(len(np.unique(g))), "groups_per_class": groups_per_class(y, g),
             "group_sizes": group_sizes(g), "full": {}, "permuted": {m: [] for m in METHODS}}
        draws = [draw(y, g, ai, k) for k in range(a.draws)]
        for m in METHODS:
            X = d["X"][m][idx]
            r["full"][m] = run(X, y, g, m, a, sev)
            for k, yp in enumerate(draws):
                r["permuted"][m].append(run(X, yp, g, m, a, sev))
            print(f"[{d['cell']}] {attr:10s} {m:14s} real {r['full'][m]['verdict']:12s} permuted "
                  f"{counts(x['verdict'] for x in r['permuted'][m])}", flush=True)
        inner = {_h(x) for yp in draws for x in permutations(yp, g, cfg("leakcheck", a), 0, a.permutations)}
        drawn = [_h(x) for x in draws]
        out["reuse"][attr] = {"draws": len(drawn), "distinct_draws": len(set(drawn)),
                              "draw_equal_to_an_inner_permutation": sum(h in inner for h in drawn),
                              "draw_equal_to_real_labels": sum(h == _h(y) for h in drawn)}
        out["attributes"][attr] = r
    for task in LEARNED[1:]:
        idx, y = samples(d, task)
        out["learned"][task] = {"classes": counts_by(y), "groups": int(len(np.unique(d["g"][idx]))),
                                "full": {m: run(d["X"][m][idx], y, d["g"][idx], m, a, sev) for m in METHODS}}
        print(f"[{d['cell']}] {task:14s} " + ", ".join(f"{m} {v['verdict']}" for m, v in out["learned"][task]["full"].items()),
              flush=True)
    tt = d["labels"]["task_type"]
    out["all_zero_windows"] = {c: int((d["all_zero"] & (tt == c)).sum()) for c in sorted(set(tt.tolist()))}
    return out


def counts_by(y) -> dict:
    return {str(c): int((y == c).sum()) for c in sorted(set(y.tolist()))}


# ── a5: the permutation test's model ─────────────────────────────────────────

def a5(data: dict, a, sev) -> dict:
    rows = []
    for cell, d in data.items():
        items = [("audit_null", "injected", None)] + [(attr, "permuted", k) for attr in ATTRS for k in range(A5_DRAWS)]
        for attr, kind, k in items:
            idx, y = samples(d, attr)
            g = d["g"][idx]
            yy = y if k is None else draw(y, g, stream(attr), k)
            X = d["X"]["leakcheck"][idx]
            row = {"cell": cell, "attribute": attr, "kind": kind, "draw": k}
            for name, kw in (("rf_light_99", {}), ("gbt_99", {"null_model": "same"}),
                             ("rf_light_adaptive_999", {"perm_max": a.perm_max})):
                row[name] = run(X, yy, g, "leakcheck", a, sev, **kw)
            rows.append(row)
            print(f"[a5] {cell} {attr} {kind} {k}: " + ", ".join(
                f"{n} {row[n]['verdict']} p={row[n]['p']:.3f} ({row[n]['seconds']:.0f} s)"
                for n in ("rf_light_99", "gbt_99", "rf_light_adaptive_999")), flush=True)
    pi, mac = (json.loads(Path(p).read_text())["runtime"]["total_s"] for p in (PI_REPORT, MAC_REPORT))
    out = {"rows": rows, "pi_over_mac": pi / mac, "pi_basis": f"{PI_REPORT} / {MAC_REPORT}: total_s {pi:.0f} / {mac:.0f}"}
    for name in ("gbt_99", "rf_light_adaptive_999"):
        ch = [r for r in rows if r[name]["verdict"] != r["rf_light_99"]["verdict"]]
        secs = sum(r[name]["seconds"] for r in rows)
        out[name] = {"verdict_changes": len(ch), "changes": [{"cell": r["cell"], "attribute": r["attribute"], "kind": r["kind"],
                     "draw": r["draw"], "from": r["rf_light_99"]["verdict"], "to": r[name]["verdict"],
                     "p_from": r["rf_light_99"]["p"], "p_to": r[name]["p"]} for r in ch],
                     "extended": sum((r[name]["permutations_run"] or 0) > a.permutations for r in rows),
                     "seconds": secs, "seconds_baseline": sum(r["rf_light_99"]["seconds"] for r in rows),
                     "pi_estimate_s": secs * out["pi_over_mac"]}
    return out


# ── a7: repeated grouped splits ──────────────────────────────────────────────

def a7(data: dict, a, sev) -> dict:
    out = {}
    for cell, d in data.items():
        for task in (*ATTRS, *LEARNED[1:]):
            idx, y = samples(d, task)
            X, g = d["X"]["leakcheck"][idx], d["g"][idx]
            runs = {s: run(X, y, g, "leakcheck", a, sev, fold_seed=s) for s in range(SEED, SEED + 6)}
            ref = runs[SEED]["verdict"]
            rep = [runs[s] for s in range(SEED + 1, SEED + 6)]
            out[f"{cell} / {task}"] = {
                "seed_42": {k: ref if k == "verdict" else runs[SEED][k] for k in ("verdict", "macro_f1", "ci", "p")},
                "verdicts": [r["verdict"] for r in rep], "agree_with_42": sum(r["verdict"] == ref for r in rep),
                "macro_f1_range": [min(r["macro_f1"] for r in rep), max(r["macro_f1"] for r in rep)],
                "ci_lo_range": [min(r["ci"][0] for r in rep), max(r["ci"][0] for r in rep)],
                "ci_hi_range": [min(r["ci"][1] for r in rep), max(r["ci"][1] for r in rep)],
                "p_range": [min(r["p"] for r in rep), max(r["p"] for r in rep)]}
            print(f"[a7] {cell} {task}: 42 {ref}, others {[r['verdict'] for r in rep]}", flush=True)
    return out


# ── a8: timestamps only ──────────────────────────────────────────────────────

TIMING_DEPENDENCE = {
    "duration_s": "timestamps of the flow (first to last packet)",
    "mean_iat": "gaps between consecutive packets of the flow, both directions; more bytes means more packets",
    "std_iat": "as mean_iat",
    "mean_burst_dur": "bursts: runs of packets in one direction with no gap over 0.5 s (direction)",
    "mean_ibg": "gaps between those bursts (direction)",
    "total_duration_s": "timestamps of the trace",
    "flow_start_spread": "flow start times",
    "flow_end_spread": "flow end times",
    "max_concurrent_flows": "flow start and end times",
    "mean_burst_rate": "bursts per second (direction)",
}


def timing_columns() -> list[dict]:
    """Every column of the trace vector's timing family: where it comes from and what it depends on."""
    pf, sysn = PerFlowFeatures.FEATURE_NAMES(), PerSystemFeatures.FEATURE_NAMES()[:20]
    blocks = {0: "mean over flows", 35: "heaviest flow by bytes", 70: "second-heaviest flow by bytes",
              125: "system mean over flows", 160: "system std over flows"}
    out = []
    for c in family_columns("timing", False):
        if c >= 105 and c < 125:
            n = sysn[c - 105]
            out.append({"column": int(c), "feature": n, "block": "system", "depends_on": TIMING_DEPENDENCE[n],
                        "flow_chosen_by_bytes": False, "uses_direction": "burst" in n})
        else:
            b = max(k for k in blocks if k <= c and not (105 <= k < 125))
            n = pf[c - b]
            out.append({"column": int(c), "feature": n, "block": blocks[b], "depends_on": TIMING_DEPENDENCE[n],
                        "flow_chosen_by_bytes": b in (35, 70), "uses_direction": "burst" in n or n == "mean_ibg"})
    return out


def gaps(Xs: dict, y, g, a) -> dict:
    """Out-of-fold GBT on each feature set over the same folds; macro-F1 with CI and the paired gap
    F1(all) − F1(set) with its CI over the same group resamples."""
    c = cfg("leakcheck", a)
    classes = sorted(set(y.tolist()))
    sp = _splits(y, g, c)
    pred = {k: _oof(X, y, sp, c) for k, X in Xs.items()}
    f1 = lambda t, p: f1_score(t, p, labels=classes, average="macro", zero_division=0)  # noqa: E731
    out = {}
    for k, p in pred.items():
        s = _score(y, p, g, classes, c)
        out[k] = {"macro_f1": s["macro_f1"], "ci": [s["ci_lo"], s["ci_hi"]]}
        if k != "all":
            d = paired_bootstrap_diff(y, pred["all"], p, g, f1, n=c.n_boot, seed=SEED)
            out[k]["all_minus_this"] = {x: d[x] for x in ("diff", "ci_lo", "ci_hi")}
            out[k].update(matches(d, 0.05))
    return out


def a8(data: dict, a, sev) -> dict:
    out = {"timing_columns": timing_columns(), "timestamps_features": ts_names(), "cells": {}}
    timing = family_columns("timing", False)
    for cell, d in data.items():
        for task in LEARNED:
            idx, y = samples(d, task)
            g = d["g"][idx]
            Xs = {"all": d["X"]["leakcheck"][idx], "timing": d["X"]["leakcheck"][idx][:, timing],
                  "timestamps_only": d["X"]["timestamps"][idx]}
            row = gaps(Xs, y, g, a)
            for k in ("timing", "timestamps_only"):
                v = run(Xs[k], y, g, "leakcheck", a, sev)
                row[k].update({"verdict": v["verdict"], "p": v["p"]})
            out["cells"][f"{cell} / {task}"] = row
            print(f"[a8] {cell} {task}: all {row['all']['macro_f1']:.3f}, timing {row['timing']['macro_f1']:.3f} "
                  f"{row['timing']['verdict']}, timestamps {row['timestamps_only']['macro_f1']:.3f} "
                  f"{row['timestamps_only']['verdict']}", flush=True)
    return out


# ── a9: template-held-out ────────────────────────────────────────────────────

def template_factors(prompts_by_type: dict[str, list[str]], meta: dict) -> dict[str, dict[str, str]]:
    """Regenerate each task type's prompts with collect_session's seeds (workflows.prompt_seed), recording
    which template each came from: alert_triage the event template (_REQUESTS / _ALARMS), sensor_analysis
    the equipment kind, fault_diagnosis the device kind (and the fault scenario), procedure_lookup the
    question template. Returns {task type: {prompt: factor}}; every prompt must be regenerated."""
    from workflows import WORKFLOW_REGISTRY, WorkflowClass, prompt_seed
    orig, calls, out = random.choice, [], {}

    def traced(seq):
        r = orig(seq)
        calls.append((seq, r))
        return r
    random.choice = traced
    try:
        for w in meta["workflows"]:
            mod = importlib.import_module(f"workflows.{w}")
            wf = WORKFLOW_REGISTRY[WorkflowClass(w)]()
            random.seed(prompt_seed(0, w, meta["seed_offset"]))
            seen: dict[str, set] = {}
            for _ in range(meta.get("n", 250)):
                calls.clear()
                p = wf.generate_prompt()
                if w == "alert_triage":
                    f = next(("request" if s is mod._REQUESTS else "alarm") + f"_{s.index(r)}" for s, r in calls
                             if s is mod._REQUESTS or s is mod._ALARMS)
                elif w == "procedure_lookup":
                    f = "template_" + str(next(s.index(r) for s, r in calls if s is mod._TEMPLATES))
                else:                                       # sensor_analysis, fault_diagnosis: the kind
                    f = calls[0][1]
                seen.setdefault(p, set()).add(f)
            out[w] = {p: sorted(f)[0] for p, f in seen.items() if len(f) == 1}
    finally:
        random.choice = orig
    for w, prompts in prompts_by_type.items():
        if missing := [p for p in prompts if p not in out[w]]:
            raise SystemExit(f"{len(missing)} {w} prompts not regenerated (or from two templates)")
    return out


def a9(data: dict, a, sev) -> dict:
    meta = json.loads(Path(ARMS["lan"], "session_meta.json").read_text())
    meta.setdefault("n", 250)
    first = next(iter(data.values()))
    tt = first["labels"]["task_type"]
    factors = template_factors({w: [p for p, t in zip(first["prompts"], tt) if t == w] for w in set(tt.tolist())}, meta)
    out = {"factor": {"alert_triage": "event template (alarm or request)", "sensor_analysis": "equipment kind",
                      "fault_diagnosis": "device kind", "procedure_lookup": "question template"},
           "levels": {}, "cells": {}}
    fams = {f: family_columns(f, False) for f in FAMILIES}
    for cell, d in data.items():
        tcell = d["labels"]["task_type"]
        fac = np.array([f"{t}:{factors[t][p]}" for t, p in zip(tcell, d["prompts"])])
        if not out["levels"]:
            out["levels"] = {t: counts_by(np.array([f.split(":", 1)[1] for f in fac[tcell == t]])) for t in sorted(set(tcell.tolist()))}
        for task in ("task_type", "pair"):
            idx, y = samples(d, task)
            X = d["X"]["leakcheck"][idx]
            row = {}
            for held, g in (("prompt", d["g"][idx]), ("template", fac[idx])):
                r = run(X, y, g, "leakcheck", a, sev, families=fams)
                at = r.pop("attribution")
                row[held] = {**{k: r[k] for k in ("verdict", "macro_f1", "ci", "p", "groups")},
                             "timing": {"macro_f1": at["families"]["timing"]["macro_f1"],
                                        "all_minus_this": {k: at["families"]["timing"]["all_minus_this"][k] for k in ("diff", "ci_lo", "ci_hi")},
                                        "matches_all": at["families"]["timing"]["matches_all"]}}
            out["cells"][f"{cell} / {task}"] = row
            print(f"[a9] {cell} {task}: prompt {row['prompt']['verdict']} {row['prompt']['macro_f1']:.3f}, template "
                  f"{row['template']['verdict']} {row['template']['macro_f1']:.3f} ({row['template']['groups']} groups)", flush=True)
    return out


# ── a10: review burden against the amount of data ────────────────────────────

def a10(data: dict, a, sev) -> dict:
    out = {"sizes": a.a10_sizes, "draws": a.a10_draws, "cells": {}}
    for cell, d in data.items():
        tt = d["labels"]["task_type"]
        res = {}
        for n in a.a10_sizes:
            audits = []
            for k in range(a.a10_draws):
                sub = subsample(tt, d["g"], n, np.random.default_rng([SEED, SUB_STREAM, n, k]))
                row = {"permuted": {}, "injected": None}
                for attr in ATTRS:
                    y = d["labels"][attr][sub]
                    keep = y != ""
                    i2, y2, g2 = sub[keep], y[keep], d["g"][sub][keep]
                    yp = permute_group(y2, group_plan(y2, g2), np.random.default_rng([SEED, SUB_PERM_STREAM, stream(attr), n, k]))
                    row["permuted"][attr] = run(d["X"]["leakcheck"][i2], yp, g2, "leakcheck", a, sev)["verdict"]
                    if attr == "audit_null":
                        row["injected"] = run(d["X"]["leakcheck"][i2], y2, g2, "leakcheck", a, sev)["verdict"]
                audits.append(row)
            res[str(n)] = audits
            print(f"[a10] {cell} n={n}: permuted INCONCLUSIVE "
                  f"{sum(v == INCONCLUSIVE for x in audits for v in x['permuted'].values())}/{len(audits) * len(ATTRS)}, "
                  f"audits with one {sum(INCONCLUSIVE in x['permuted'].values() for x in audits)}/{len(audits)}", flush=True)
        out["cells"][cell] = res
    return out


# ── a11: a plain k-FP pipeline ───────────────────────────────────────────────

def a11_plain(a) -> dict:
    """k-FP alone, as its authors use it: k-FP features, a random forest, 5-fold grouped CV accuracy and
    macro-F1, no interval, no permutation test, no attribution. Time per cell for task_type."""
    from models.random_forest import RFClassifier
    from sklearn.base import clone
    out = {}
    for cell in a.cells:
        arm, view = cell.rsplit("_", 1)
        raw = Path(ARMS[arm])
        t = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="round2_kfp_") as tmp:
            col = collect(raw, ["task_type"], strip_dir=Path(tmp), vantage=view)
            t_col = time.perf_counter() - t
            t = time.perf_counter()
            X = np.stack([kfp_rows(own_packets(tcp_packets(tr.pcap, dedup=True), set(tr.port_role)), set(tr.port_role), None)
                          for tr in col["traces"]])
            t_feat = time.perf_counter() - t
        y = np.array([tr.labels["task_type"] for tr in col["traces"]])
        g = np.array([tr.group for tr in col["traces"]])
        t = time.perf_counter()
        c = cfg("kfp_rf", a)
        pred = np.empty(len(y), dtype=object)
        for tr_, te in _splits(y, g, c):
            pred[te] = clone(RFClassifier().pipeline).fit(X[tr_], y[tr_]).predict(X[te])
        t_cv = time.perf_counter() - t
        out[cell] = {"collect_s": t_col, "kfp_features_s": t_feat, "cv_s": t_cv, "accuracy": float((pred == y).mean()),
                     "macro_f1": float(f1_score(y, pred, average="macro"))}
        print(f"[a11] {cell}: plain k-FP task_type macro-F1 {out[cell]['macro_f1']:.3f} "
              f"({t_col + t_feat + t_cv:.0f} s)", flush=True)
    return out


# ── summaries (merge time) ───────────────────────────────────────────────────

def accounting(a4: dict) -> dict:
    """a12 and a4's table: learned rows, structural checks, known non-leaks; release blocking per audit."""
    rows, neg = [], {m: [] for m in METHODS}
    for cell, c in a4["cells"].items():
        for attr in ("task_type", *STRUCTURAL):
            rows.append({"cell": cell, "task": attr, "kind": "learned" if attr == "task_type" else "structural",
                         **{m: c["attributes"][attr]["full"][m]["verdict"] for m in METHODS}})
        for task in LEARNED[1:]:
            rows.append({"cell": cell, "task": task, "kind": "learned", **{m: c["learned"][task]["full"][m]["verdict"] for m in METHODS}})
    tot = lambda rs: {m: counts(r[m] for r in rs) for m in METHODS}  # noqa: E731
    learned = [r for r in rows if r["kind"] == "learned"]
    structural = [r for r in rows if r["kind"] == "structural"]
    perm = {m: [x["verdict"] for c in a4["cells"].values() for attr in ATTRS for x in c["attributes"][attr]["permuted"][m]]
            for m in METHODS}
    inj = {m: [c["attributes"]["audit_null"]["full"][m]["verdict"] for c in a4["cells"].values()] for m in METHODS}
    blocking = {}
    for m in METHODS:
        audits = [[c["attributes"][attr]["permuted"][m][k]["verdict"] for attr in ATTRS]
                  for c in a4["cells"].values() for k in range(len(c["attributes"]["task_type"]["permuted"][m]))]
        n, any_leak = len(audits), sum(LEAK in x for x in audits)
        inc = sum(LEAK not in x and INCONCLUSIVE in x for x in audits)
        blocking[m] = {"audits": n, "any_leak": any_leak, "any_leak_ci": wilson(any_leak, n),
                       "inconclusive_no_leak": inc, "inconclusive_no_leak_rate": inc / n if n else None,
                       "inconclusive_no_leak_ci": wilson(inc, n)}
    return {"rows": rows, "learned": tot(learned), "learned_by_task": {t: tot([r for r in learned if r["task"] == t]) for t in LEARNED},
            "structural": tot(structural), "structural_by_task": {t: tot([r for r in structural if r["task"] == t]) for t in STRUCTURAL},
            "negatives": {"permuted": {m: counts(v) for m, v in perm.items()}, "audit_null": {m: counts(v) for m, v in inj.items()}},
            "release_blocking": blocking,
            "all_zero_windows": {cell: c["all_zero_windows"] for cell, c in a4["cells"].items()}}


def a11_summary(a4: dict, plain: dict | None) -> dict:
    out = {"methods": {}, "agreement": {}}
    for m in METHODS:
        perm = [x for c in a4["cells"].values() for attr in ATTRS for x in c["attributes"][attr]["permuted"][m]]
        inc = [x for x in perm if x["verdict"] == INCONCLUSIVE]
        widths = [x["ci"][1] - x["ci"][0] for x in perm if x["ci"][0] is not None]
        out["methods"][m] = {
            "permuted_draws": len(perm), "inconclusive": len(inc),
            "inconclusive_why": {w: sum(why(x) == w for x in inc) for w in sorted({why(x) for x in inc})},
            "ci_width_median": float(np.median(widths)), "ci_width_p90": float(np.percentile(widths, 90)),
            "macro_f1_sd": float(np.std([x["macro_f1"] for x in perm])),
            "p_le_0_05": sum(x["p"] <= 0.05 for x in perm if x["p"] is not None),
            "seconds_median": float(np.median([x["seconds"] for x in perm]))}
    for m in ("kfp_rf", "first_request"):
        full = [(c["attributes"][attr]["full"]["leakcheck"]["verdict"], c["attributes"][attr]["full"][m]["verdict"])
                for c in a4["cells"].values() for attr in ATTRS]
        full += [(c["learned"][t]["full"]["leakcheck"]["verdict"], c["learned"][t]["full"][m]["verdict"])
                 for c in a4["cells"].values() for t in LEARNED[1:]]
        perm = [(x["verdict"], y["verdict"]) for c in a4["cells"].values() for attr in ATTRS
                for x, y in zip(c["attributes"][attr]["permuted"]["leakcheck"], c["attributes"][attr]["permuted"][m])]
        out["agreement"][m] = {"real_labels": {"cells": len(full), "same_verdict": sum(a == b for a, b in full)},
                               "permuted": {"draws": len(perm), "same_verdict": sum(a == b for a, b in perm),
                                            "both_inconclusive": sum(a == b == INCONCLUSIVE for a, b in perm),
                                            "only_leakcheck_inconclusive": sum(a == INCONCLUSIVE != b for a, b in perm),
                                            "only_other_inconclusive": sum(b == INCONCLUSIVE != a for a, b in perm)}}
    out["plain_kfp"] = plain
    full_tt = {cell: c["attributes"]["task_type"]["full"] for cell, c in a4["cells"].items()}
    out["runtime_task_type"] = {cell: {m: v["seconds"] for m, v in f.items()} for cell, f in full_tt.items()}
    return out


def a10_summary(a10: dict, a4: dict | None) -> dict:
    out = {}
    for n in [str(x) for x in a10["sizes"]]:
        audits = [x for c in a10["cells"].values() for x in c[n]]
        per_attr = {attr: counts(x["permuted"][attr] for x in audits) for attr in ATTRS}
        k = sum(INCONCLUSIVE in x["permuted"].values() for x in audits)
        out[n] = {"audits": len(audits), "per_attribute": per_attr,
                  "inconclusive_rate": sum(v[INCONCLUSIVE] for v in per_attr.values()) / (len(audits) * len(ATTRS)),
                  "audits_with_inconclusive": k, "audit_rate": k / len(audits), "audit_rate_ci": wilson(k, len(audits)),
                  "injected": counts(x["injected"] for x in audits)}
    if a4:
        audits = [[c["attributes"][attr]["permuted"]["leakcheck"][k]["verdict"] for attr in ATTRS]
                  for c in a4["cells"].values() for k in range(len(c["attributes"]["task_type"]["permuted"]["leakcheck"]))]
        k = sum(INCONCLUSIVE in x for x in audits)
        per_attr = {attr: counts(c["attributes"][attr]["permuted"]["leakcheck"][i]["verdict"]
                                 for c in a4["cells"].values() for i in range(len(c["attributes"][attr]["permuted"]["leakcheck"])))
                    for attr in ATTRS}
        out["all"] = {"audits": len(audits), "per_attribute": per_attr,
                      "inconclusive_rate": sum(v[INCONCLUSIVE] for v in per_attr.values()) / (len(audits) * len(ATTRS)),
                      "audits_with_inconclusive": k, "audit_rate": k / len(audits), "audit_rate_ci": wilson(k, len(audits)),
                      "injected": counts(c["attributes"]["audit_null"]["full"]["leakcheck"]["verdict"] for c in a4["cells"].values())}
    return out


# ── output ───────────────────────────────────────────────────────────────────

def _f(x, d=3):
    return "—" if x is None else f"{x:.{d}f}"


def _ci(v, d=3):
    return f"{_f(v['macro_f1'], d)} [{_f(v['ci'][0], d)}, {_f(v['ci'][1], d)}]"


def _gap(x):
    return f"{x['diff']:+.3f} [{x['ci_lo']:+.3f}, {x['ci_hi']:+.3f}]"


def _w(ci) -> str:
    return "—" if ci is None else f"[{ci[0]:.3f}, {ci[1]:.3f}]"


def _c(c: dict) -> str:
    return f"{c[LEAK]} / {c[INCONCLUSIVE]} / {c[NO_LEAK]}"


def markdown(s: dict) -> str:
    S = s["sections"]
    L = ["# Paper 2, round 2: the reviewers' checks", "",
         f"Commit `{(s['git_commit'] or '')[:8]}` (clean: {s['git_dirty'] is False}); seed {SEED}; a2a-leakcheck 0.3.0 defaults "
         "(permutation test by prompt group; a feature set matches all features when the upper bound of the paired 95% CI "
         "of F1(all) − F1(set) is at most 0.05). Verdict counts are LEAK / INCONCLUSIVE / NO LEAK.", ""]
    if "a12" in S:
        acc = S["a12"]
        L += ["## A12 / A4. Accounting (group-level permutation)", "",
              "| Set | n | a2a-leakcheck | k-FP | first request |", "|---|---|---|---|---|"]
        L += [f"| Learned: {t} | {sum(acc['learned_by_task'][t]['leakcheck'].values())} | "
              + " | ".join(_c(acc["learned_by_task"][t][m]) for m in METHODS) + " |" for t in LEARNED]
        L.append(f"| **Learned, all** | {sum(acc['learned']['leakcheck'].values())} | " + " | ".join(_c(acc["learned"][m]) for m in METHODS) + " |")
        L += [f"| Structural check: {t} | {sum(acc['structural_by_task'][t]['leakcheck'].values())} | "
              + " | ".join(_c(acc["structural_by_task"][t][m]) for m in METHODS) + " |" for t in STRUCTURAL]
        for k, v in acc["negatives"].items():
            L.append(f"| Known non-leaks: {k} | {sum(v['leakcheck'].values())} | " + " | ".join(_c(v[m]) for m in METHODS) + " |")
        if "current" in acc:
            cur = acc["current"]
            L += ["", "The same with the per-sample permutation of v1.0 (`paper2_review.json`):", "",
                  "| Set | a2a-leakcheck | k-FP | first request |", "|---|---|---|---|"]
            for k in ("permuted", "audit_null"):
                L.append(f"| Known non-leaks: {k} | " + " | ".join(_c(cur["negative_totals"][k][m]) for m in METHODS) + " |")
            for k in ("by construction", "baseline only"):
                L.append(f"| Known leaks: {k} | " + " | ".join(_c(cur["positive_totals"][k][m]) for m in METHODS) + " |")
        L += ["", "Release blocking over the permuted audits (one cell, one draw index, four attributes):", "",
              "| Method | Audits | Any LEAK | No LEAK but an INCONCLUSIVE |", "|---|---|---|---|"]
        for m, b in acc["release_blocking"].items():
            L.append(f"| {m} | {b['audits']} | {b['any_leak']} {_w(b['any_leak_ci'])} | {b['inconclusive_no_leak']} "
                     f"({_f(b['inconclusive_no_leak_rate'])}) {_w(b['inconclusive_no_leak_ci'])} |")
        L += ["", "All-zero windows (nothing in view) per cell and task type: "
              + "; ".join(f"{c}: " + ", ".join(f"{k} {v}" for k, v in w.items() if v) for c, w in acc["all_zero_windows"].items()) + ".", ""]
    if "a4" in S:
        a4 = S["a4"]
        L += ["## A4. Groups per class and draw reuse", "",
              "| Cell | Attribute | Samples | Groups | Group sizes (size: groups) |", "|---|---|---|---|---|"]
        for cell, c in a4["cells"].items():
            for attr, r in c["attributes"].items():
                L.append(f"| {cell} | {attr} | {sum(r['classes'].values())} | {r['groups']} | "
                         + ", ".join(f"{k}: {v}" for k, v in r["group_sizes"].items()) + " |")
        L += ["", "D1: " + "; ".join(f"{arm}: " + ", ".join(f"{attr} {v['samples']} samples in {v['groups']} groups"
                                                            for attr, v in d.items() if attr != "trace_group_sizes")
                                     + f" (trace group sizes {d['trace_group_sizes']})" for arm, d in a4["d1"].items()), "",
              "Reuse: " + ", ".join(f"{cell} {attr}: {r['distinct_draws']}/{r['draws']} distinct, "
                                    f"{r['draw_equal_to_an_inner_permutation']} equal to an inner permutation"
                                    for cell, c in a4["cells"].items() for attr, r in c["reuse"].items()) + ".", ""]
    if "a3" in S:
        a3 = S["a3"]
        L += ["## A3. \"Matches all features\": non-inferiority (δ = 0.05) against 0.1.x's rule", "",
              "Committed reports, every LEAK whose \"carried by\" changes:", "",
              "| Report / attribute | 0.1.x | 0.3.0 |", "|---|---|---|"]
        L += [f"| {k} | {v['carried_0_1']} | {v['carried_0_3']} |" for k, v in a3["reports"].items() if v["changed"]] or ["| none | | |"]
        L += ["", "Recomputed (permutations 0; the gap of each family against all features):", "",
              "| Cell / task | all | sizes: gap | timing: gap | counts: gap | 0.1.x | 0.3.0 |", "|---|---|---|---|---|---|---|"]
        for k, v in a3["learned"].items():
            fam = v["families"]
            L.append(f"| {k} | {_ci(v)} | " + " | ".join(
                f"{_gap(fam[f])} {'✓' if fam[f]['matches_all'] else ''}" for f in ("sizes", "timing", "counts_direction"))
                + f" | {v['carried_0_1']} | {v['carried_0_3']} |")
        L.append("")
    if "a5" in S:
        a5_ = S["a5"]
        L += ["## A5. The permutation test's model", "",
              f"{len(a5_['rows'])} cases ({A5_CELLS}: audit_null and {A5_DRAWS} permuted draws per attribute). "
              f"Pi estimate: Mac time × {a5_['pi_over_mac']:.2f} ({a5_['pi_basis']}).", "",
              "| Option | Verdicts changed | Extended to 999 | Mac time (s) | Baseline (s) | Pi estimate (s) |", "|---|---|---|---|---|---|"]
        for n in ("gbt_99", "rf_light_adaptive_999"):
            v = a5_[n]
            L.append(f"| {n} | {v['verdict_changes']} | {v['extended']} | {v['seconds']:.0f} | {v['seconds_baseline']:.0f} | {v['pi_estimate_s']:.0f} |")
        for n in ("gbt_99", "rf_light_adaptive_999"):
            for ch in a5_[n]["changes"]:
                L.append(f"- {n}: {ch['cell']} {ch['attribute']} {ch['kind']} {ch['draw']}: {ch['from']} (p {ch['p_from']:.2f}) → "
                         f"{ch['to']} (p {ch['p_to']:.3f})")
        L.append("")
    if "a7" in S:
        L += ["## A7. Repeated grouped splits (fold seeds 43–47 against 42)", "",
              "| Cell / task | seed 42 | agree of 5 | macro-F1 range | CI lower | CI upper | p range |", "|---|---|---|---|---|---|---|"]
        for k, v in S["a7"].items():
            L.append(f"| {k} | {v['seed_42']['verdict']} {_f(v['seed_42']['macro_f1'])} | {v['agree_with_42']} | "
                     f"{_f(v['macro_f1_range'][0])}–{_f(v['macro_f1_range'][1])} | {_f(v['ci_lo_range'][0])}–{_f(v['ci_lo_range'][1])} | "
                     f"{_f(v['ci_hi_range'][0])}–{_f(v['ci_hi_range'][1])} | {_f(v['p_range'][0], 2)}–{_f(v['p_range'][1], 2)} |")
        L.append("")
    if "a8" in S:
        a8_ = S["a8"]
        byb = sum(c["flow_chosen_by_bytes"] for c in a8_["timing_columns"])
        dirn = sum(c["uses_direction"] for c in a8_["timing_columns"])
        L += ["## A8. Timing family against timestamps only", "",
              f"The timing family has {len(a8_['timing_columns'])} columns: {byb} come from flows chosen by bytes (heaviest, "
              f"second heaviest), {dirn} from bursts split at changes of direction; the inter-arrival times run over every "
              f"packet, whose number follows the bytes sent. Timestamps only: {len(a8_['timestamps_features'])} features "
              "(features/timestamps.py).", "",
              "| Cell / task | all | timing | all − timing | timestamps only | all − timestamps |", "|---|---|---|---|---|---|"]
        for k, v in a8_["cells"].items():
            L.append(f"| {k} | {_ci(v['all'])} | {_ci(v['timing'])} {v['timing']['verdict']} | {_gap(v['timing']['all_minus_this'])} | "
                     f"{_ci(v['timestamps_only'])} {v['timestamps_only']['verdict']} | {_gap(v['timestamps_only']['all_minus_this'])} |")
        L.append("")
    if "a9" in S:
        a9_ = S["a9"]
        L += ["## A9. Template-held-out", "",
              "Factors: " + "; ".join(f"{t}: {f} ({len(a9_['levels'].get(t, {}))} levels)" for t, f in a9_["factor"].items()) + ".", "",
              "| Cell / task | held out by prompt | by template | timing alone, by template |", "|---|---|---|---|"]
        for k, v in a9_["cells"].items():
            L.append(f"| {k} | {v['prompt']['verdict']} {_ci(v['prompt'])} | {v['template']['verdict']} {_ci(v['template'])} "
                     f"({v['template']['groups']} groups) | {_f(v['template']['timing']['macro_f1'])}, gap {_gap(v['template']['timing']['all_minus_this'])} |")
        L.append("")
    if "a10" in S:
        L += ["## A10. Review burden against traces per task type (a2a-leakcheck, permuted draws)", "",
              "| Traces per task type | Audits | INCONCLUSIVE per attribute | Audits with one | audit_null (real) |", "|---|---|---|---|---|"]
        for n, v in S["a10"].items():
            L.append(f"| {n} | {v['audits']} | {_f(v['inconclusive_rate'])} | {v['audits_with_inconclusive']} ({_f(v['audit_rate'])}) "
                     f"{_w(v['audit_rate_ci'])} | {_c(v['injected'])} |")
        L.append("")
    if "a11" in S:
        a11_ = S["a11"]
        L += ["## A11. a2a-leakcheck against k-FP", "",
              "| Method | INCONCLUSIVE on permuted | why | CI width (median, P90) | p ≤ 0.05 | time per test (s) |", "|---|---|---|---|---|---|"]
        for m, v in a11_["methods"].items():
            L.append(f"| {m} | {v['inconclusive']}/{v['permuted_draws']} | " + ", ".join(f"{k} {n}" for k, n in v["inconclusive_why"].items())
                     + f" | {_f(v['ci_width_median'])}, {_f(v['ci_width_p90'])} | {v['p_le_0_05']} | {_f(v['seconds_median'], 1)} |")
        for m, v in a11_["agreement"].items():
            L.append(f"\nAgreement with {m}: real labels {v['real_labels']['same_verdict']}/{v['real_labels']['cells']}; permuted "
                     f"{v['permuted']['same_verdict']}/{v['permuted']['draws']} (both INCONCLUSIVE {v['permuted']['both_inconclusive']}, "
                     f"only a2a-leakcheck {v['permuted']['only_leakcheck_inconclusive']}, only {m} {v['permuted']['only_other_inconclusive']}).")
        if a11_.get("plain_kfp"):
            L += ["", "| Cell | plain k-FP task_type macro-F1 | its time (s) | a2a-leakcheck task_type test (s) |", "|---|---|---|---|"]
            for cell, v in a11_["plain_kfp"].items():
                L.append(f"| {cell} | {_f(v['macro_f1'])} | {v['collect_s'] + v['kfp_features_s'] + v['cv_s']:.0f} | "
                         f"{a11_['runtime_task_type'].get(cell, {}).get('leakcheck', 0):.0f} |")
        L.append("")
    return "\n".join(L) + "\n"


# ── main ─────────────────────────────────────────────────────────────────────

def run_sections(a) -> dict:
    sev = load_rules()["severity"]
    out, data = {}, {}
    need = set(a.sections) & {"a3", "a4", "a5", "a7", "a8", "a9", "a10"}
    for cell in (a.cells if need else []):
        data[cell] = load_cell(cell)
        print(f"[{cell}] loaded {len(data[cell]['ids'])} traces ({data[cell]['load_s']:.0f} s)", flush=True)
    t = {}
    for sec in a.sections:
        t0 = time.perf_counter()
        if sec == "a3":
            out["a3"] = {"reports": a3_reports(), "learned": a3_learned(data, a, sev)}
        elif sec == "a4":
            out["a4"] = {"cells": {cell: a4_cell(data[cell], a, sev) for cell in a.cells}, "d1": d1_groups()}
        elif sec == "a5":
            out["a5"] = a5({c: data[c] for c in A5_CELLS if c in data}, a, sev)
        elif sec == "a7":
            out["a7"] = a7(data, a, sev)
        elif sec == "a8":
            out["a8"] = a8(data, a, sev)
        elif sec == "a9":
            out["a9"] = a9(data, a, sev)
        elif sec == "a10":
            out["a10"] = a10(data, a, sev)
        elif sec == "a11":
            out["a11_plain"] = a11_plain(a)
        t[sec] = time.perf_counter() - t0
    out["seconds"] = t
    return out


def merge(paths: list[Path], allow_dirty: bool = False) -> dict:
    parts = [json.loads(p.read_text()) for p in paths]
    commits = {p["git_commit"] for p in parts}
    if len(commits) != 1 or (any(p["git_dirty"] is not False for p in parts) and not allow_dirty):
        raise SystemExit(f"the parts must come from one clean commit: {[(str(p), q['git_commit'], q['git_dirty']) for p, q in zip(paths, parts)]}")
    if len({json.dumps(p["parameters"], sort_keys=True) for p in parts}) != 1:
        raise SystemExit("the parts were run with different parameters")
    raw: dict = {}
    for p in parts:
        for k, v in p["sections"].items():
            if k in raw:
                raise SystemExit(f"section {k} is in two parts")
            raw[k] = v
    sec = {k: v for k, v in raw.items() if k in ("a3", "a5", "a7", "a8", "a9")}
    a4 = raw.get("a4")
    if a4:
        sec["a4"] = a4
        acc = accounting(a4)
        acc["current"] = json.loads(Path("data/results/paper2_review.json").read_text())["accounting"]
        sec["a12"] = acc
        sec["a11"] = a11_summary(a4, raw.get("a11_plain"))
    if "a10" in raw:
        sec["a10"] = a10_summary(raw["a10"], a4)
        sec["a10_draws"] = raw["a10"]
    return {"paper": "P2", "collection_id": "C2", "round": 2, "seed": SEED, "git_commit": commits.pop(),
            "git_dirty": any(p["git_dirty"] is not False for p in parts), "parameters": parts[0]["parameters"],
            "parts": [{"file": str(p), "sections": list(q["sections"]), "seconds": q["sections"].get("seconds")} for p, q in zip(paths, parts)],
            "sections": sec}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--sections", default="a3,a8,a9", help=f"comma-separated: {', '.join(SECTIONS)}")
    p.add_argument("--cells", default=",".join(CELLS))
    p.add_argument("--out", required=True, help="output path without extension (.json; with --merge also .md)")
    p.add_argument("--merge", nargs="+", type=Path, default=None, help="part JSONs to merge")
    p.add_argument("--draws", type=int, default=20, help="a4: permuted draws per cell and attribute")
    p.add_argument("--a10-sizes", default="50,100,150,200", dest="a10_sizes")
    p.add_argument("--a10-draws", type=int, default=10, dest="a10_draws")
    p.add_argument("--permutations", type=int, default=99)
    p.add_argument("--perm-max", type=int, default=999, dest="perm_max", help="a5: the adaptive rule's ceiling")
    p.add_argument("--n-boot", type=int, default=1000, dest="n_boot")
    p.add_argument("--jobs", type=int, default=-1)
    p.add_argument("--allow-dirty", action="store_true", dest="allow_dirty")
    a = p.parse_args(argv)
    out = Path(a.out)
    if out.with_suffix(".json").exists():
        raise SystemExit(f"{out.with_suffix('.json')} exists: committed results are not overwritten")
    out.parent.mkdir(parents=True, exist_ok=True)
    if a.merge:
        res = merge(a.merge, a.allow_dirty)
        out.with_suffix(".json").write_text(json.dumps(res, indent=1, default=str))
        out.with_suffix(".md").write_text(markdown(res))
        print(f"→ {out}.json, {out}.md")
        return 0
    git = _git()
    if git["git_dirty"] is not False and not a.allow_dirty:
        raise SystemExit("uncommitted code: commit first (or --allow-dirty for a test run)")
    a.sections = [s.strip() for s in a.sections.split(",") if s.strip()]
    if bad := set(a.sections) - set(SECTIONS):
        raise SystemExit(f"unknown sections {bad}")
    a.cells = [c.strip() for c in a.cells.split(",") if c.strip()]
    a.a10_sizes = [int(x) for x in str(a.a10_sizes).split(",")]
    t0 = time.perf_counter()
    res = {"paper": "P2", "collection_id": "C2", "round": 2, "seed": SEED, **{k: git[k] for k in ("git_commit", "git_dirty")},
           "parameters": {"cells": a.cells, "draws": a.draws, "a10_sizes": a.a10_sizes, "a10_draws": a.a10_draws,
                          "permutations": a.permutations, "perm_max": a.perm_max, "n_boot": a.n_boot, "perm_unit": "group",
                          "match_margin": 0.05},
           "sections": run_sections(a)}
    res["runtime_s"] = time.perf_counter() - t0
    out.with_suffix(".json").write_text(json.dumps(res, indent=1, default=str))
    print(f"→ {out}.json ({res['runtime_s']:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
