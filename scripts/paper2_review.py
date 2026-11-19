#!/usr/bin/env python3
"""
Paper 2 review checks on C2, from the committed captures and the committed tool evaluation
(data/results/paper2_tool_eval_c2.json and the six tool reports data/results/leakcheck/c2_<cell>).

  2. accounting       every known leak (18: attribute x arm x view) and known non-leak (480
                      full-size permuted draws and the 6 audit_null cells) with the LEAK /
                      INCONCLUSIVE / NO LEAK verdicts of a2a-leakcheck, k-FP and the first-request
                      rule, read from the evaluation (no model run); the release-blocking rate: of
                      the permuted audits (a cell and a draw index: the four attributes' k-th
                      permuted draws on the same captures), the share in which any attribute reads
                      LEAK; and a check that no permuted labelling of a full-size draw is reused by
                      the permutation test inside any draw of its cell.
  3. escalated tasks  task_type on its escalated classes only (sensor_analysis, fault_diagnosis,
                      procedure_lookup) in every cell, through the verdict rule
                      (scripts/evaluate_leakcheck.py verdict: 5-fold grouped CV, cluster-bootstrap
                      CI, chance + margin, 99-permutation test) on all 195 trace features and on the
                      timing family alone, with the tool's attribution on all features.
  4. input size       the first-request estimator of the input size (evaluate_leakcheck
                      input_size), rebuilt out of fold and checked against the stored errors; a
                      paired cluster-bootstrap CI of (constant-overhead error - no-traffic error),
                      median and mean absolute error, per cell, overall and per task type; the
                      first-request sizes that differ from a padded arm's usual one, by trace.
  5. matches all      the attribution's rule (all - family, paired over the same prompt-group
                      resamples, CI lower bound <= 0), for task_type at lan_padmax (the tool
                      reports) and for sensor_analysis vs fault_diagnosis in every cell (the
                      evaluation's --pair, whose stored output has no paired gap: recomputed here
                      from the same out-of-fold predictions, checked against the stored scores).
  A. data             distinct prompts, prompt groups and template pools per class, C2 and D1.

Features come from evaluate_leakcheck.load_arm, as in the evaluation (own connections, each payload
byte once, header-only copies of the captures). Runs only from a clean checkout (the result records
the commit); --allow-dirty for a test run.

Usage (never overwrites):
    python scripts/paper2_review.py --out data/results/paper2_review
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import StratifiedGroupKFold

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from a2a_leakcheck.analyze import Config, analyze  # noqa: E402
from a2a_leakcheck.cli import _git  # noqa: E402
from a2a_leakcheck.rules import load_rules  # noqa: E402
from evaluation.stats import paired_bootstrap_diff  # noqa: E402
from features.families import FAMILIES, family_columns  # noqa: E402
from scripts.evaluate_leakcheck import (ESTIMATORS, INCONCLUSIVE, LEAK, SEED, VERDICTS,  # noqa: E402
                                        _cfg, attr_index, load_arm, prompt_json_bytes, size_errors,
                                        verdict, wilson)

ESCALATED = ("fault_diagnosis", "procedure_lookup", "sensor_analysis")
PAIR = ("fault_diagnosis", "sensor_analysis")
D1 = {"tls": "data/raw_tlspair_tls", "cleartext": "data/raw_tlspair_clear"}
# D1's workflows draw one content item and one ask (workflows/<name>.py): the pools behind each prompt
D1_POOLS = {"research_retrieval": {"short": ("_TOPICS", "_QUESTION_TEMPLATES"), "long": ("_LONG_QUESTIONS",)},
            "code_review": {"content": ("_CODE_SNIPPETS", "_LARGE_CODE_SNIPPETS"), "ask": ("_REVIEW_ASKS",)},
            "data_analysis": {"content": ("_SMALL_DATASETS", "_DATASETS"), "ask": ("_ANALYSIS_ASKS",)},
            "support_triage": {"content": ("_TICKETS", "_LONG_TICKETS"), "ask": ("_TRIAGE_ASKS",)}}
MATCH_RULE = ("A feature family matches all features when the 95% cluster-bootstrap CI of the paired "
              "difference macro-F1(all features) - macro-F1(family alone) has a lower bound <= 0: both are "
              "out-of-fold predictions from the same 5 folds, scored on the same 1,000 resamples of whole "
              "prompt groups (seed 42), percentile interval (evaluation/stats.py paired_bootstrap_diff; "
              "a2a_leakcheck/analyze.py attribution). It says the family is not shown to fall short of all "
              "features; it is not an equivalence test, and a family whose CI lies wholly below 0 (better "
              "than all features) also matches.")


def jsonable(x):
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, np.generic):
        return x.item()
    if isinstance(x, np.ndarray):
        return x.tolist()
    return x


# ── 2. accounting ────────────────────────────────────────────────────────────

def accounting(ev: dict) -> dict:
    methods = list(ev["methods"])
    ref = {(c, a): (s, basis) for c, a, s, basis in ev["reference"]["cells"]}
    positives, pos_tot = [], {k: {m: Counter() for m in methods} for k in ("by construction", "baseline only", "all")}
    neg_tot = {k: {m: Counter() for m in methods} for k in ("permuted", "audit_null", "all")}
    neg_attr = {}
    for cell, arm in ev["arms"].items():
        for attr, r in arm["attributes"].items():
            status, basis = ref[cell, attr]
            v = {m: r["full"][m]["verdict"] for m in methods}
            if status == "leak":
                kind = "by construction" if "by construction" in basis else "baseline only"
                positives.append({"cell": cell, "arm": arm["arm"], "view": arm["vantage"], "attribute": attr,
                                  "basis": basis, **v})
                for m in methods:
                    pos_tot[kind][m][v[m]] += 1
                    pos_tot["all"][m][v[m]] += 1
            elif status == "null":
                for m in methods:
                    neg_tot["audit_null"][m][v[m]] += 1
                    neg_tot["all"][m][v[m]] += 1
            for m in methods:                                   # every cell's permuted draws are non-leaks
                c = Counter(r["permuted"][m])
                neg_tot["permuted"][m].update(c)
                neg_tot["all"][m].update(c)
                neg_attr.setdefault(attr, {mm: Counter() for mm in methods})[m].update(c)
    fix = lambda d: {k: {m: {v: d[k][m][v] for v in VERDICTS} for m in methods} for k in d}  # noqa: E731
    # release blocking: audit (cell, k) = the k-th permuted draw of every attribute of that cell
    attrs = list(next(iter(ev["arms"].values()))["attributes"])
    blocking = {}
    for m in methods:
        n = any_leak = not_cleared = 0
        per_cell = {}
        for cell, arm in ev["arms"].items():
            draws = [arm["attributes"][a]["permuted"][m] for a in attrs]
            k_n = len(draws[0])
            if any(len(d) != k_n for d in draws):
                raise SystemExit(f"{cell}: attributes have different numbers of permuted draws")
            leaks = [any(d[k] == LEAK for d in draws) for k in range(k_n)]
            inc = [not leaks[k] and any(d[k] == INCONCLUSIVE for d in draws) for k in range(k_n)]
            per_cell[cell] = {"audits": k_n, "any_leak": sum(leaks), "inconclusive_no_leak": sum(inc)}
            n += k_n; any_leak += sum(leaks); not_cleared += sum(inc)
        blocking[m] = {"audits": n, "any_leak": any_leak, "any_leak_rate": any_leak / n,
                       "any_leak_ci": wilson(any_leak, n), "inconclusive_no_leak": not_cleared,
                       "inconclusive_no_leak_rate": not_cleared / n, "inconclusive_no_leak_ci": wilson(not_cleared, n),
                       "all_no_leak": n - any_leak - not_cleared, "per_cell": per_cell}
    return {"positives": positives, "positive_totals": fix(pos_tot), "negative_totals": fix(neg_tot),
            "negatives_by_attribute": {a: {m: {v: c[m][v] for v in VERDICTS} for m in methods} for a, c in neg_attr.items()},
            "release_blocking": {"attributes": attrs,
                                 "alignment": "audit k of a cell: the k-th full-size permuted draw of each attribute, "
                                              "on the same captures; each attribute's labels permuted with its own "
                                              "stream (seed, 1, attribute stream, k), so independently across attributes",
                                 "methods": blocking}}


def reuse_check(y: np.ndarray, ai: int, label_perms: int, permutations: int) -> dict:
    """Do the full-size permuted draws of one cell and attribute share a labelling with the permutation
    tests run inside them (or inside the real-label test)? Rebuilt with the evaluation's and analyze's
    seeds: draws rng([SEED, 1, ai, k]).permutation(y); inside every test rng(SEED).permutation, 99 times."""
    y = np.asarray(y).astype(str)
    draws = [np.random.default_rng([SEED, 1, ai, k]).permutation(y) for k in range(label_perms)]
    rng0 = np.random.default_rng(SEED)
    inner_idx = [rng0.permutation(len(y)) for _ in range(permutations)]
    # analyze permutes the labels it is given with the same generator, so its j-th shuffle of any labelling
    # is that labelling indexed by the same index permutation
    rng1 = np.random.default_rng(SEED)
    if not all(np.array_equal(rng1.permutation(y), y[ix]) for ix in inner_idx):
        raise SystemExit("rng.permutation(labels) is not labels[rng.permutation(n)]: the check below would be wrong")
    h = lambda v: hashlib.sha1(v.tobytes()).digest()  # noqa: E731
    tests = [y] + draws
    inner = {h(tests[t][ix]) for t in range(len(tests)) for ix in inner_idx}
    outer = [h(d) for d in draws]
    n_all = len(tests) * permutations + label_perms + 1
    return {"draws": label_perms, "shuffles_per_test": permutations, "labellings": n_all,
            "distinct_labellings": len(inner | set(outer) | {h(y)}),
            "draw_equal_to_a_shuffle_in_any_test": sum(o in inner for o in outer),
            "draw_equal_to_real_labels": sum(o == h(y) for o in outer)}


# ── 3. escalated task types, and attribution ─────────────────────────────────

def family_cols() -> dict:
    return {f: family_columns(f, False) for f in FAMILIES}


def attribution_rows(r: dict) -> dict:
    at = r.get("attribution") or {}
    return {f: {"macro_f1": v["macro_f1"], "ci": [v["ci_lo"], v["ci_hi"]], "dims": v["dims"],
                "all_minus_this": {k: v["all_minus_this"][k] for k in ("diff", "ci_lo", "ci_hi")},
                "matches_all": bool(v["all_minus_this"]["ci_lo"] <= 0)}
            for f, v in (at.get("families") or {}).items()}


def full_verdict(r: dict) -> dict:
    an, perm = r["analysis"] or {}, r["validation"].get("permutation") or {}
    return {"verdict": r["verdict"], "macro_f1": an.get("macro_f1"), "ci": [an.get("ci_lo"), an.get("ci_hi")],
            "p": perm.get("p_value"), "null_mean": perm.get("null_mean"), "null_max": perm.get("null_max"),
            "chance": r["chance"], "threshold": r["threshold"], "n": r["n"], "groups": r["n_groups"]}


def escalated_task_type(data: dict, a: argparse.Namespace, sev: dict) -> dict:
    s = data["samples"]["task_type"]
    keep = np.isin(s["y"], ESCALATED)
    y, g, X = s["y"][keep], s["g"][keep], s["X"]["leakcheck"][keep]
    timing = family_columns("timing", False)
    r_all = analyze(X, y, g, family_cols(), None, _cfg(a, "leakcheck"), sev)
    r_t = verdict(X[:, timing], y, g, a, "leakcheck", sev)
    return {"classes": {c: int((y == c).sum()) for c in ESCALATED}, "groups": int(len(np.unique(g))),
            "dims": {"all": int(X.shape[1]), "timing": int(len(timing))},
            "all": full_verdict(r_all), "timing": {k: r_t[k] for k in ("verdict", "macro_f1", "ci", "p", "n", "groups")},
            "attribution": attribution_rows(r_all), "top_family": (r_all.get("attribution") or {}).get("top_family")}


def pair_attribution(data: dict, stored: dict, a: argparse.Namespace, sev: dict) -> dict:
    """sensor_analysis vs fault_diagnosis: the out-of-fold predictions of the evaluation's --pair (all
    features) and of each family alone, and their paired gaps. Verdicts and p-values are the stored ones
    (permutation test not re-run: permutations=0 here changes neither the predictions nor the CIs)."""
    s = data["samples"]["task_type"]
    keep = np.isin(s["y"], PAIR)
    y, g, X = s["y"][keep], s["g"][keep], s["X"]["leakcheck"][keep]
    cfg = _cfg(a, "leakcheck")
    cfg = Config(**{**cfg.__dict__, "permutations": 0})
    r = analyze(X, y, g, family_cols(), None, cfg, sev)
    rows = attribution_rows(r)
    an = r["analysis"]
    rep = {"all_macro_f1": abs(an["macro_f1"] - stored["all"]["macro_f1"]) < 1e-12,
           "all_ci": np.allclose([an["ci_lo"], an["ci_hi"]], stored["all"]["ci"], atol=1e-12),
           "timing_macro_f1": abs(rows["timing"]["macro_f1"] - stored["timing"]["macro_f1"]) < 1e-12,
           "timing_ci": np.allclose(rows["timing"]["ci"], stored["timing"]["ci"], atol=1e-12)}
    return {"classes": {c: int((y == c).sum()) for c in PAIR}, "groups": int(len(np.unique(g))),
            "stored_verdicts": {k: {kk: stored[k][kk] for kk in ("verdict", "macro_f1", "ci", "p")} for k in ("all", "timing")},
            "attribution": rows, "top_family": (r.get("attribution") or {}).get("top_family"),
            "reproduces_stored": {**rep, "all": all(rep.values())}}


# ── 4. input size ────────────────────────────────────────────────────────────

def escalated_ids(raw: Path, key: str, value: str) -> tuple[list[str], np.ndarray]:
    """Run ids and input sizes of the traces load_arm's input-size arrays hold, in its order: captures
    sorted by name, the run not failed, the sidecar's KEY=VALUE."""
    ids, inp = [], []
    for pcap in sorted(raw.glob("*.pcap")):
        sc = json.loads(pcap.with_suffix(".json").read_text())
        if sc.get("success") is False or str(sc.get(key)) != value:
            continue
        ids.append(sc.get("run_id", pcap.stem))
        inp.append(prompt_json_bytes(sc["input_prompt"]))
    return ids, np.array(inp, dtype=float)


def input_size_review(d: dict, stored: dict, ids: list[str], a: argparse.Namespace) -> dict:
    fr, true, cls, g = d["fr"], d["input"], d["cls"], d["g"]
    classes = sorted(set(cls.tolist()))
    splits = list(StratifiedGroupKFold(5, shuffle=True, random_state=SEED).split(np.zeros(len(cls)), cls, g))
    pred = {e: np.empty(len(fr)) for e in ESTIMATORS}
    fitted = []
    for tr, te in splits:                                # as evaluate_leakcheck.input_size
        c = float(np.median(fr[tr] - true[tr]))
        lr = LinearRegression().fit(fr[tr, None], true[tr])
        cw = {k: float(np.median(fr[tr][cls[tr] == k] - true[tr][cls[tr] == k])) for k in classes}
        pred["constant"][te] = fr[te] - c
        pred["linear"][te] = lr.predict(fr[te, None])
        pred["no_traffic"][te] = float(np.median(true[tr]))
        pred["per_class_constant"][te] = fr[te] - np.array([cw[k] for k in cls[te]])
        fitted.append({"constant_overhead_c": c, "no_traffic_prediction": float(np.median(true[tr])),
                       "train": int(len(tr)), "test": int(len(te))})
    errs = {e: {"overall": size_errors(pred[e], true),
                "per_class": {k: size_errors(pred[e][cls == k], true[cls == k]) for k in classes}} for e in ESTIMATORS}
    reproduced = all(np.isclose(errs[e][part][kk], stored["estimators"][e][part][kk], atol=1e-9)
                     if part == "overall" else
                     all(np.isclose(errs[e][part][k][kk], stored["estimators"][e][part][k][kk], atol=1e-9)
                         for k in classes)
                     for e in ESTIMATORS for part in ("overall", "per_class") for kk in ("median_abs_error", "p90_abs_error", "mae"))
    med = lambda t, p: float(np.median(np.abs(p - t)))  # noqa: E731
    mean = lambda t, p: float(np.mean(np.abs(p - t)))   # noqa: E731

    def paired(mask) -> dict:
        return {name: paired_bootstrap_diff(true[mask], pred["constant"][mask], pred["no_traffic"][mask], g[mask],
                                            f, n=a.n_boot, seed=SEED) for name, f in (("median_abs_error", med),
                                                                                    ("mean_abs_error", mean))}
    vals = Counter(fr.tolist())
    common = vals.most_common(1)[0][0]
    rare = []
    if len(vals) <= 10:
        rare = [{"run_id": ids[i], "task_type": str(cls[i]), "first_request": float(fr[i]),
                 "minus_usual": float(fr[i] - common), "agent": str(d["link"][i])}
                for i in np.flatnonzero(fr != common)] if vals[common] / len(fr) > 0.99 else []
    return {"population": d["traces"], "n": int(len(fr)), "groups": int(len(np.unique(g))),
            "first_request_agent": dict(Counter(d["link"].tolist())),
            "first_request_sizes": {"distinct": len(vals),
                                    "counts": {str(int(k)): v for k, v in sorted(vals.items())} if len(vals) <= 10 else None,
                                    "usual": float(common), "unusual_traces": rare},
            "fitted_per_fold": fitted, "reproduces_stored_errors": bool(reproduced),
            "errors": {e: {"overall": {k: errs[e]["overall"][k] for k in ("median_abs_error", "p90_abs_error", "mae")},
                           "per_class": {c: {k: errs[e]["per_class"][c][k] for k in ("n", "median_abs_error", "p90_abs_error")}
                                         for c in classes}} for e in ESTIMATORS},
            "constant_minus_no_traffic": {"overall": paired(np.ones(len(fr), bool)),
                                          "per_class": {c: paired(cls == c) for c in classes}}}


# ── A. data ──────────────────────────────────────────────────────────────────

def sidecars(raw: Path) -> list[dict]:
    out = []
    for pcap in sorted(raw.glob("*.pcap")):
        sc = json.loads(pcap.with_suffix(".json").read_text())
        if sc.get("success") is not False:
            out.append(sc)
    return out


def group_of(sc: dict) -> str:
    """As a2a_leakcheck/collect.py: prompt_group, else sha1 of the prompt (8 hex digits)."""
    return str(sc["prompt_group"]) if sc.get("prompt_group") else hashlib.sha1(sc["input_prompt"].encode()).hexdigest()[:8]


def data_section(ev: dict) -> dict:
    c2, prompts = {}, {}
    for arm, raw in ev["data_dir"].items():
        scs = sidecars(Path(raw))
        meta = json.loads((Path(raw) / "session_meta.json").read_text())
        pools = meta.get("prompt_pool") or {}
        per = {}
        for t in sorted({s["task_type"] for s in scs}):
            ss = [s for s in scs if s["task_type"] == t]
            prompts.setdefault(t, {})[arm] = {s["input_prompt"] for s in ss}
            per[t] = {"traces": len(ss), "distinct_prompts": len({s["input_prompt"] for s in ss}),
                      "prompt_groups": len({group_of(s) for s in ss}),
                      "template_pools": (pools.get(t) or {}).get("template_pools")}
        c2[arm] = {"traces": len(scs), "prompt_groups": len({group_of(s) for s in scs}), "per_task_type": per}
    same = {t: all(v == next(iter(arms.values())) for v in arms.values()) for t, arms in prompts.items()}
    d1, d1_prompts = {}, {}
    for arm, raw in D1.items():
        scs = sidecars(Path(raw))
        per = {}
        for w in sorted({s["workflow_class"] for s in scs}):
            ss = [s for s in scs if s["workflow_class"] == w]
            d1_prompts.setdefault(w, {})[arm] = Counter(s["input_prompt"] for s in ss)
            mod = importlib.import_module(f"workflows.{w}")
            pools = {n: len(getattr(mod, n)) for part in D1_POOLS[w].values() for n in part}
            if w == "research_retrieval":
                possible = len(mod._TOPICS) * len(mod._QUESTION_TEMPLATES) + len(mod._LONG_QUESTIONS)
            else:
                c, k = D1_POOLS[w]["content"], D1_POOLS[w]["ask"]
                possible = sum(len(getattr(mod, n)) for n in c) * len(getattr(mod, k[0]))
            per[w] = {"traces": len(ss), "distinct_prompts": len({s["input_prompt"] for s in ss}),
                      "prompt_groups": len({group_of(s) for s in ss}), "pools": pools,
                      "possible_distinct_prompts": possible}
        d1[arm] = {"traces": len(scs), "prompt_groups": len({group_of(s) for s in scs}),
                   "group_source": "sha1(input_prompt)[:8] (no prompt_group in the sidecars)", "per_workflow": per}
    d1_same = {w: all(v == next(iter(arms.values())) for v in arms.values()) for w, arms in d1_prompts.items()}
    return {"C2": {"arms": c2, "arms_share_prompts_per_task_type": same},
            "D1": {**d1, "arms_share_prompts_per_workflow": d1_same}}


# ── markdown ─────────────────────────────────────────────────────────────────

def _f(x, d=3) -> str:
    return "—" if x is None else f"{x:.{d}f}"


def _ci(v, ci, d=3) -> str:
    return f"{_f(v, d)} [{_f(ci[0], d)}, {_f(ci[1], d)}]"


def _gap(x: dict, d=3) -> str:
    return f"{x['diff']:+.{d}f} [{x['ci_lo']:+.{d}f}, {x['ci_hi']:+.{d}f}]"


def _vc(c: dict) -> str:
    return " / ".join(str(c[v]) for v in VERDICTS)


def markdown(s: dict) -> str:
    acc, methods = s["accounting"], s["methods"]
    mname = {"leakcheck": "a2a-leakcheck", "kfp_rf": "k-FP", "first_request": "first request"}
    L = ["# Paper 2 review checks (C2)", "",
         f"Commit `{s['git_commit'][:8]}` (clean: {not s['git_dirty']}); seed {s['seed']}. Inputs: "
         f"`{s['source']['evaluation']}` (commit `{s['source']['evaluation_commit'][:8]}`) and the six tool reports "
         f"`{s['source']['tool_reports'].replace('{cell}', '<cell>')}` (commit "
         f"{', '.join(f'`{c[:8]}`' for c in s['source']['tool_report_commits'])}); captures "
         + ", ".join(f"`{v}`" for v in s["data_dir"].values()) + ". Features as in the evaluation (own connections, "
         "each payload byte once). Verdict rule throughout: 5-fold StratifiedGroupKFold by prompt group, macro-F1 with "
         f"a {s['parameters']['n_boot']}-resample cluster-bootstrap 95% CI, LEAK when the lower bound exceeds 1/k + "
         f"{s['parameters']['margin']}, and a {s['parameters']['permutations']}-permutation test (rf-light) at 0.05.", "",
         "## 2. Accounting: every known leak and known non-leak", "",
         "Verdict counts are LEAK / INCONCLUSIVE / NO LEAK.", "",
         "| Set | Cells or draws | " + " | ".join(mname[m] for m in methods) + " |", "|---|---|" + "---|" * len(methods)]
    for k, label in (("by construction", "Known leaks by construction (escalated, cloud_role)"),
                     ("baseline only", "Known leaks only because a baseline reads LEAK (task_type)"),
                     ("all", "**All known leaks**")):
        t = acc["positive_totals"][k]
        L.append(f"| {label} | {sum(t[methods[0]].values())} | " + " | ".join(_vc(t[m]) for m in methods) + " |")
    for k, label in (("permuted", "Full-size permuted draws (6 cells × 4 attributes × 20)"),
                     ("audit_null", "audit_null, real labels (6 cells)"), ("all", "**All known non-leaks**")):
        t = acc["negative_totals"][k]
        L.append(f"| {label} | {sum(t[methods[0]].values())} | " + " | ".join(_vc(t[m]) for m in methods) + " |")
    L += ["", "The task_type cells are known leaks because k-FP and the first-request rule read LEAK on them, so "
          "those two methods' recall there is true by definition; only the 12 cells by construction score all three "
          "methods without that circularity.", "",
          "Permuted draws per attribute (6 cells × 20):", "",
          "| Attribute | " + " | ".join(mname[m] for m in methods) + " |", "|---|" + "---|" * len(methods)]
    for attr, t in acc["negatives_by_attribute"].items():
        L.append(f"| {attr} | " + " | ".join(_vc(t[m]) for m in methods) + " |")
    L += ["", "Each known leak:", "", "| Cell | Attribute | Why it is a known leak | " + " | ".join(mname[m] for m in methods)
          + " |", "|---|---|---|" + "---|" * len(methods)]
    for p in acc["positives"]:
        L.append(f"| {p['cell']} | {p['attribute']} | {', '.join(p['basis'])} | " + " | ".join(p[m] for m in methods) + " |")
    rb = acc["release_blocking"]
    L += ["", "**Release-blocking rate.** A permuted audit is one cell and one draw index k: the k-th full-size "
          "permuted draw of each of the four attributes, on the same captures (each attribute's labels permuted "
          "independently, with its own random stream). It blocks a release if any attribute reads LEAK.", "",
          "| Method | Audits | Any LEAK [Wilson 95% CI] | No LEAK, some INCONCLUSIVE [95% CI] | All NO LEAK |", "|---|---|---|---|---|"]
    for m in methods:
        b = rb["methods"][m]
        L.append(f"| {mname[m]} | {b['audits']} | {b['any_leak']} ({_ci(b['any_leak_rate'], b['any_leak_ci'])}) | "
                 f"{b['inconclusive_no_leak']} ({_ci(b['inconclusive_no_leak_rate'], b['inconclusive_no_leak_ci'])}) | "
                 f"{b['all_no_leak']} |")
    ru = s["reuse"]
    L += ["", f"**Reuse between draws and the permutation tests inside them.** For each of the {len(ru)} (cell, "
          "attribute) pairs, the 20 permuted draws, the real labels, and the 99 shuffles inside each of those 21 tests: "
          f"{sum(r['distinct_labellings'] for r in ru.values())} distinct labellings of "
          f"{sum(r['labellings'] for r in ru.values())}; a draw equal to a shuffle in any test: "
          f"{sum(r['draw_equal_to_a_shuffle_in_any_test'] for r in ru.values())}; a draw equal to the real labels: "
          f"{sum(r['draw_equal_to_real_labels'] for r in ru.values())}. Every test in a cell uses the same 99 index "
          "permutations (generator seeded 42) applied to its own labels, and the same 1,000 bootstrap resamples, so "
          "the draws are not fully independent of each other, but no labelling is reused.", "",
          "## 3. task_type on the escalated tasks only", "",
          "sensor_analysis, fault_diagnosis and procedure_lookup (alert_triage, which never leaves the building and "
          "is answered on the edge, left out): three classes, chance 1/3, so a LEAK needs the CI's lower bound above "
          "0.383. Verdict, macro-F1 [95% CI] and permutation p.", "",
          "| Cell | Traces | All 195 features | Timing alone (30) | Timing gap: all − timing [95% CI] | Sizes alone | "
          "Sizes gap | Top family |", "|---|---|---|---|---|---|---|---|"]
    for cell, r in s["escalated_task_type"].items():
        at = r["attribution"]
        L.append(f"| {cell} | {sum(r['classes'].values())} | {r['all']['verdict']} {_ci(r['all']['macro_f1'], r['all']['ci'])}, "
                 f"p {r['all']['p']:.2f} | {r['timing']['verdict']} {_ci(r['timing']['macro_f1'], r['timing']['ci'])}, "
                 f"p {r['timing']['p']:.2f} | {_gap(at['timing']['all_minus_this'])} | "
                 f"{_ci(at['sizes']['macro_f1'], at['sizes']['ci'])} | {_gap(at['sizes']['all_minus_this'])} | {r['top_family']} |")
    L += ["", "## 4. Input-size estimator", "",
          "**Population.** The escalated traces of each arm (sidecar `escalated=yes`, 750: 250 per task type), the only "
          "tasks whose prompt crosses a captured link, to a cloud agent. **Truth:** the prompt as JSON-encoded in the "
          "request, without its quotes (`prompt_json_bytes`). **Observation:** the first request's size as the leakcheck "
          "measures it (`first_request_seq`, TCP sequence space, after the TLS handshake). **Error:** |estimate − truth| "
          "in bytes, out of fold: 5-fold StratifiedGroupKFold by prompt group over task_type, seed 42. **Constant "
          "overhead:** on the training folds c = median(first request − input); estimate = first request − c. **No "
          "traffic:** on the training folds the median input; every test trace gets that number. Linear (least squares "
          "of input on first request) and per-class constant (c per task type, applied with the true type, reference "
          "only) as stored. The cloud agents are in both views, so v1 and v2 see the same first request; results "
          "identical at v1 and v2: " + ", ".join(f"{k} {v}" for k, v in s["input_size_views_identical"].items())
          + ". Each arm is shown once.", ""]
    for cell, r in s["input_size"].items():
        if cell.endswith("_v2"):
            continue
        fs = r["first_request_sizes"]
        L += [f"**{cell[:-3]}** ({r['n']} traces, {r['groups']} prompt groups; first request to "
              f"{', '.join(f'{k} {v}' for k, v in r['first_request_agent'].items())}; {fs['distinct']} distinct "
              f"first-request sizes; stored errors reproduced: {r['reproduces_stored_errors']}; c per fold "
              f"{', '.join(_f(f['constant_overhead_c'], 1) for f in r['fitted_per_fold'])} B; no-traffic estimate per fold "
              f"{', '.join(_f(f['no_traffic_prediction'], 1) for f in r['fitted_per_fold'])} B)", "",
              "| | Constant: median / P90 | No traffic: median / P90 | Constant − no traffic, median abs error [95% CI] | "
              "Mean abs error [95% CI] |", "|---|---|---|---|---|"]
        e, cm = r["errors"], r["constant_minus_no_traffic"]
        rows = [("all", e["constant"]["overall"], e["no_traffic"]["overall"], cm["overall"])]
        rows += [(c, e["constant"]["per_class"][c], e["no_traffic"]["per_class"][c], cm["per_class"][c])
                 for c in e["constant"]["per_class"]]
        for name, ec, en, d in rows:
            L.append(f"| {name} | {ec['median_abs_error']:.0f} / {ec['p90_abs_error']:.0f} | {en['median_abs_error']:.0f} / "
                     f"{en['p90_abs_error']:.0f} | {_gap(d['median_abs_error'], 1)} | {_gap(d['mean_abs_error'], 1)} |")
        if fs["counts"] and fs["unusual_traces"]:
            L += ["", "First-request sizes: " + ", ".join(f"{k} B × {v}" for k, v in fs["counts"].items()) + ". "
                  + "; ".join(f"`{u['run_id']}` ({u['task_type']}, {u['agent']}): {u['first_request']:.0f} B, "
                              f"{u['minus_usual']:+.0f} B" for u in fs["unusual_traces"])
                  + ". DATA.md (C2: the first request measured in TCP sequence space) explains it: that trace's client "
                    "Finished (80 B) and HTTP header were lost and resent as one segment, and from headers alone the "
                    "Finished's end inside it is unknown, so it is counted in the request."]
        L.append("")
    L += ["## 5. \"Matches all features\"", "", MATCH_RULE, "",
          "**task_type at lan_padmax (four classes; the tool reports):**", "",
          "| View | All features | Family | Alone | All − family [95% CI] | Matches all |", "|---|---|---|---|---|---|"]
    for cell, r in s["matches_all"]["padmax_task_type"].items():
        for f, v in r["families"].items():
            L.append(f"| {cell[-2:]} | {_ci(r['all']['macro_f1'], r['all']['ci'])} | {f}{' (top)' if f == r['top_family'] else ''} | "
                     f"{_ci(v['macro_f1'], v['ci'])} | {_gap(v['all_minus_this'])} | {'yes' if v['matches_all'] else 'no'} |")
    L += ["", "**sensor_analysis vs fault_diagnosis (the evaluation's --pair), every cell:**", "",
          "| Cell | All features (stored) | Timing alone (stored) | All − timing [95% CI] | Sizes alone | All − sizes [95% CI] | "
          "Reproduces stored |", "|---|---|---|---|---|---|---|"]
    for cell, r in s["matches_all"]["pair"].items():
        sv, at = r["stored_verdicts"], r["attribution"]
        L.append(f"| {cell} | {sv['all']['verdict']} {_ci(sv['all']['macro_f1'], sv['all']['ci'])} | {sv['timing']['verdict']} "
                 f"{_ci(sv['timing']['macro_f1'], sv['timing']['ci'])} | {_gap(at['timing']['all_minus_this'])} "
                 f"({'matches' if at['timing']['matches_all'] else 'short of all'}) | {_ci(at['sizes']['macro_f1'], at['sizes']['ci'])} | "
                 f"{_gap(at['sizes']['all_minus_this'])} | {r['reproduces_stored']['all']} |")
    d = s["data"]
    L += ["", "## A. Prompts and template pools", "", "C2 (the three arms share each item's prompt: "
          + ", ".join(f"{t} {v}" for t, v in d["C2"]["arms_share_prompts_per_task_type"].items()) + "):", "",
          "| Task type | Traces per arm | Distinct prompts | Prompt groups | Template pools |", "|---|---|---|---|---|"]
    arm0 = next(iter(d["C2"]["arms"].values()))
    for t, v in arm0["per_task_type"].items():
        L.append(f"| {t} | {v['traces']} | {v['distinct_prompts']} | {v['prompt_groups']} | "
                 + ", ".join(f"{k} {n}" for k, n in (v["template_pools"] or {}).items()) + " |")
    L += ["", f"D1 (TLS control; each arm {d['D1']['tls']['traces']} traces, {d['D1']['tls']['prompt_groups']} prompt groups, "
          f"grouped by {d['D1']['tls']['group_source']}; the two arms hold the same prompts, with the same counts: "
          + ", ".join(f"{w} {v}" for w, v in d["D1"]["arms_share_prompts_per_workflow"].items()) + "):", "",
          "| Workflow | Traces per arm | Distinct prompts | Possible prompts | Pools |", "|---|---|---|---|---|"]
    for w, v in d["D1"]["tls"]["per_workflow"].items():
        L.append(f"| {w} | {v['traces']} | {v['distinct_prompts']} | {v['possible_distinct_prompts']} | "
                 + ", ".join(f"{k.strip('_').lower()} {n}" for k, n in v["pools"].items()) + " |")
    return "\n".join(L) + "\n"


# ── main ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--eval", default="data/results/paper2_tool_eval_c2.json")
    p.add_argument("--reports", default="data/results/leakcheck/c2_{cell}")
    p.add_argument("--out", required=True, help="path stem for .json and .md (not overwritten)")
    p.add_argument("--jobs", type=int, default=-1)
    p.add_argument("--cells", default="", help="comma-separated cells (default: all; for a test run)")
    p.add_argument("--allow-dirty", action="store_true", dest="allow_dirty")
    a = p.parse_args(argv)
    git = _git()
    if git["git_dirty"] and not a.allow_dirty:
        raise SystemExit("uncommitted code: commit first (or --allow-dirty for a test run)")
    for ext in (".json", ".md"):
        if Path(a.out + ext).exists():
            raise SystemExit(f"{a.out}{ext} exists: not overwritten")
    t0 = time.perf_counter()
    ev = json.loads(Path(a.eval).read_text())
    if ev.get("git_dirty") is not False:
        raise SystemExit(f"{a.eval} was not made from a clean checkout")
    par = ev["parameters"]
    a.margin, a.n_boot, a.permutations, a.min_per_class = par["margin"], par["n_boot"], par["permutations"], par["min_per_class"]
    sev = load_rules(None)["severity"]
    cells = [c for c in ev["arms"] if not a.cells or c in a.cells.split(",")]
    reports = {c: json.loads((Path(a.reports.format(cell=c)) / "report.json").read_text()) for c in ev["arms"]}
    key, value = par["input_size"].split("=", 1)

    out = {"paper": "P2", "collection_id": "C2", "seed": SEED, **git, "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "task": "review checks: accounting of known leaks and non-leaks, escalated-only task type, input-size "
                   "estimator, 'matches all features', prompts and template pools",
           # paths and commits of the inputs (not compared by scripts/reproduce_paper2.sh)
           "source": {"evaluation": a.eval, "evaluation_commit": ev["git_commit"], "tool_reports": a.reports,
                      "tool_report_commits": sorted({r["git_commit"] for r in reports.values()})},
           "data_dir": ev["data_dir"], "d1_data_dir": D1,
           "parameters": {k: par[k] for k in ("permutations", "n_boot", "margin", "min_per_class", "folds", "null_model",
                                              "alpha", "label_perms", "attributes", "input_size")},
           "methods": list(ev["methods"]), "cells": cells}
    out["accounting"] = accounting(ev)
    out["reuse"], out["escalated_task_type"], out["input_size"] = {}, {}, {}
    out["matches_all"] = {"rule": MATCH_RULE, "padmax_task_type": {}, "pair": {}}
    for c in ("lan_padmax_v1", "lan_padmax_v2"):
        r = reports[c]["attributes"]["task_type"]
        out["matches_all"]["padmax_task_type"][c] = {"all": full_verdict(r), "families": attribution_rows(r),
                                                     "top_family": r["attribution"]["top_family"]}
    for cell in cells:
        arm = ev["arms"][cell]
        raw = Path(arm["data_dir"])
        t = time.perf_counter()
        data = load_arm(raw, [], par["attributes"], arm["vantage"], par["input_size"])
        if data["traces"] != arm["traces"]:
            raise SystemExit(f"{cell}: {data['traces']} traces here, {arm['traces']} in the evaluation")
        print(f"[{cell}] loaded {data['traces']} traces ({time.perf_counter() - t:.0f} s)", flush=True)
        for attr in par["attributes"]:
            out["reuse"][f"{cell}/{attr}"] = reuse_check(data["samples"][attr]["y"], attr_index(attr, []),
                                                         par["label_perms"], par["permutations"])
        t = time.perf_counter()
        out["escalated_task_type"][cell] = r = escalated_task_type(data, a, sev)
        print(f"[{cell}] escalated task_type: all {r['all']['verdict']} {r['all']['macro_f1']:.3f}, timing "
              f"{r['timing']['verdict']} {r['timing']['macro_f1']:.3f} ({time.perf_counter() - t:.0f} s)", flush=True)
        t = time.perf_counter()
        out["matches_all"]["pair"][cell] = r = pair_attribution(data, arm["pair"], a, sev)
        print(f"[{cell}] pair: all - timing {r['attribution']['timing']['all_minus_this']['diff']:+.3f}, reproduces "
              f"stored {r['reproduces_stored']['all']} ({time.perf_counter() - t:.0f} s)", flush=True)
        ids, inp = escalated_ids(raw, key, value)
        if len(ids) != len(data["input_size"]["input"]) or not np.array_equal(inp, data["input_size"]["input"]):
            raise SystemExit(f"{cell}: the escalated traces do not line up with load_arm's order")
        out["input_size"][cell] = r = input_size_review(data["input_size"], arm["input_size"], ids, a)
        print(f"[{cell}] input size: reproduces stored errors {r['reproduces_stored_errors']}", flush=True)
    out["input_size_views_identical"] = {}
    for arm_name in sorted({ev["arms"][c]["arm"] for c in cells}):
        v1, v2 = out["input_size"].get(f"{arm_name}_v1"), out["input_size"].get(f"{arm_name}_v2")
        if v1 and v2:
            same = json.dumps(jsonable(v1), sort_keys=True) == json.dumps(jsonable(v2), sort_keys=True)
            out["input_size_views_identical"][arm_name] = same
            if not same:
                print(f"note: {arm_name}: input-size results differ between v1 and v2", flush=True)
    out["data"] = data_section(ev)
    out["runtime_s"] = time.perf_counter() - t0
    out = jsonable(out)
    md = markdown(out) if len(cells) == len(ev["arms"]) else None
    Path(a.out + ".json").write_text(json.dumps(out, indent=2) + "\n")
    if md:
        Path(a.out + ".md").write_text(md)
        print(md)
    print(f"→ {a.out}.json" + (f", {a.out}.md" if md else " (no .md: not every cell)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
