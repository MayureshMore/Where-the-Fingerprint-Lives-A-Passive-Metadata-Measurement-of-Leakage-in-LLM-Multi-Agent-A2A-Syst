#!/usr/bin/env python3
"""
Paper 2: how well a2a-leakcheck's verdicts hold up, on collections whose answer is known.

  known leaks       --reference labels (default): the real labels, role, workflow and topology on
                    each arm (paper 1 and the TLS control: all three leak, with and without TLS),
                    and with --role-within TOPOLOGY role scored on that topology's traces only
                    (role_within_<topology>). --not-known ARM:ATTR leaves a cell out of the known
                    leaks; it is still reported.
                    --reference full-attack (C2): no attribute of a padded arm is known to leak
                    beforehand, so the reference is the full-data attack: a cell (arm, view,
                    attribute) is a known leak when an attack on all of its data finds one, that
                    is, when any of the three methods below reads LEAK on the full data. A cell in
                    which none does is neither a known leak nor a known non-leak.
  known non-leaks   permuted labels: --label-perms random permutations of each attribute's labels
                    over its samples (labels independent of the traffic), and audit_null, a
                    sidecar label drawn from the prompt group alone (C2 sidecars,
                    scripts/collect_session.py), where present.

  Attributes        --attributes (default role,workflow,topology): role from agent_endpoints, the
                    others from sidecar keys (C2: task_type, escalated, cloud_role, audit_null);
                    an attribute missing from some sidecars (C2's cloud_role, escalated tasks only)
                    is scored on the traces that have it.
  Views             --vantage v1,v2 scores each arm at each observer view (the sidecars'
                    vantages, as python -m a2a_leakcheck run --vantage): only the flows of the
                    endpoints in view are kept, and a trace with none in view stays in with
                    all-zero features and a first-request size of 0 (C2's alert_triage at v2).
                    One cell per arm and view, named ARM_VIEW.

  1. Full data      the tool as shipped (python -m a2a_leakcheck run, a fresh process per cell)
                    gives the full-data verdicts on the real labels and the runtime and peak memory
                    per stage; --tool-reports TEMPLATE reads those reports instead (TEMPLATE with
                    {cell}, e.g. data/results/leakcheck/c2_{cell}), after checking that each was
                    made from a clean checkout with the same folder, view, attributes and verdict
                    parameters, and that the tool's code has not changed since its commit. Their
                    runtime and memory were then measured with nothing else running, which a
                    split run (--merge) cannot promise. The permuted labels run through the same verdict rule
                    (a2a_leakcheck.analyze with the same Config: 5-fold grouped CV, cluster-
                    bootstrap CI, chance + margin, 99-permutation test with the rf-light null).
                    Feature attribution is skipped there: the verdict does not use it.
  2. Baselines      inside the same verdict rule, on the same real and permuted labels:
                    k-FP features (features/kfp.py, direction and timing only) with the tool's RF
                    (--model rf); and the first request's size alone with GBT (for role, the bytes
                    the agent receives, the tool's single request-size feature). The first request
                    is measured in TCP sequence space (features/first_request.py,
                    first_request_seq, since Nov 13): a TLS session ticket arriving mid-request, or
                    part of a request held back by a loss, no longer ends it early.
  3. Sample size    n = 5/10/20/30/50 samples per class, --subsamples draws each, by whole prompt
                    groups (per class, groups in random order until n samples; the last group's
                    surplus is dropped), on the real labels and on one label permutation per draw.
                    Share of LEAK / INCONCLUSIVE / NO LEAK, and agreement with the full-data verdict.

Rates (Wilson 95% intervals): recall = LEAK on known leaks; false-negative rate = 1 − recall,
split into INCONCLUSIVE and NO LEAK (a wrong all-clear); false-positive rate = LEAK on known
non-leaks; precision = LEAK on known leaks / all LEAK verdicts in the set.

Writes data/results/paper2_tool_eval.{json,md} (A2A_RESULTS_DIR overrides data/results) and
data/results/figures/paper2_tool_eval.png.

Split runs: every random stream is fixed by (attribute, draw), and no verdict depends on the
number of workers, so cells can be scored in separate processes (one per arm, each writing its
own JSON) and joined with --merge PART.json ...: the parts must share the commit (clean), the
parameters and the reference; the summary is computed over all their cells, as one run would.

Usage:
    python scripts/evaluate_leakcheck.py                                  # TLS control, both arms
    python scripts/evaluate_leakcheck.py --collection-id C2 --name paper2_tool_eval_c2 \\
        --attributes task_type,escalated,cloud_role,audit_null --vantage v1,v2 --reference full-attack \\
        --arm lan=data/raw_c2 --arm lan_pad=data/raw_c2_pad --arm lan_padmax=data/raw_c2_padmax
    # the same, split by arm: one process per arm (A2A_RESULTS_DIR=data/c2_tool_eval_parts,
    # --name c2_part_<arm>, --tool-reports data/results/leakcheck/c2_{cell}), then
    python scripts/evaluate_leakcheck.py --name paper2_tool_eval_c2 \\
        --merge data/c2_tool_eval_parts/c2_part_lan.json data/c2_tool_eval_parts/c2_part_lan_pad.json \\
        data/c2_tool_eval_parts/c2_part_lan_padmax.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from a2a_leakcheck.analyze import INCONCLUSIVE, LEAK, NO_LEAK, Config, analyze  # noqa: E402
from a2a_leakcheck.collect import collect  # noqa: E402
from a2a_leakcheck.extract import extract  # noqa: E402
from a2a_leakcheck.rules import load_rules  # noqa: E402
from features.connections import own_packets  # noqa: E402
from features.kfp import N_KFP, kfp_features, tcp_packets  # noqa: E402
from features.per_flow import PerFlowFeatures  # noqa: E402

SEED = 42
ATTRS = ("role", "workflow", "topology")
NULL_ATTR = "audit_null"
ROLE_WITHIN = "role_within_"
# each attribute's random streams (label permutations, subsamples); fixed so that adding an
# attribute leaves the others' draws unchanged (role_within_* use 10 + their position)
STREAMS = {"role": 0, "workflow": 1, "topology": 2, NULL_ATTR: 3, "task_type": 4, "escalated": 5, "cloud_role": 6}
REFERENCES = ("labels", "full-attack")
# what python -m a2a_leakcheck run reads: a report made at another commit stands for this one only
# if none of these changed in between (--tool-reports)
TOOL_CODE = ("a2a_leakcheck", "features", "models", "evaluation", "scripts/strip_payload.py")
SIZES = (5, 10, 20, 30, 50)
VERDICTS = (LEAK, INCONCLUSIVE, NO_LEAK)
METHODS = {"leakcheck": "a2a-leakcheck: GBT on the header-only features (195 per trace, 35 per agent)",
           "kfp_rf": f"k-FP features ({N_KFP}, direction and timing only) with the tool's RF",
           "first_request": "first-request size alone with GBT (in TCP sequence space, "
                            "features/first_request.py first_request_seq; role: bytes the agent receives)"}
RESULTS = Path(os.environ.get("A2A_RESULTS_DIR", "data/results"))


def _git() -> dict:
    """Commit, and whether the code differs from it (changes under data/ do not count)."""
    def run(*a):
        return subprocess.run(["git", *a], capture_output=True, text=True).stdout.strip()
    return {"git_commit": run("rev-parse", "HEAD"),
            "git_dirty": bool(run("status", "--porcelain", "--", ".", ":(exclude)data"))}


def wilson(k: int, n: int) -> list[float] | None:
    if not n:
        return None
    z, p = 1.959964, k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [max(0.0, c - h), min(1.0, c + h)]


# ── data ─────────────────────────────────────────────────────────────────────

def kfp_rows(packets: list, servers: set[int], port: int | None) -> np.ndarray:
    t, d = [], []
    for ts, sp, dp, *_ in packets:
        if port is not None and port not in (sp, dp):
            continue
        if dp in servers:
            t.append(ts); d.append(1)
        elif sp in servers:
            t.append(ts); d.append(-1)
    return kfp_features(t, d)


def attr_index(attr: str, role_within: list[str]) -> int:
    """Fixed index of an attribute for its random streams, so adding role_within_* attributes
    leaves the draws of the others unchanged."""
    if attr.startswith(ROLE_WITHIN):
        return 10 + role_within.index(attr[len(ROLE_WITHIN):])
    if attr not in STREAMS:
        raise SystemExit(f"attribute {attr!r} has no fixed random stream: add it to STREAMS")
    return STREAMS[attr]


def trace_attributes(attributes) -> list[str]:
    """The sidecar attributes to read (every one but role), and audit_null where present."""
    return list(dict.fromkeys([*(x for x in attributes if x != "role"), NULL_ATTR]))


def load_arm(raw: Path, role_within: list[str] = (), attributes=ATTRS, vantage: str | None = None) -> dict:
    """Collect and extract once per cell, as the tool does, plus k-FP vectors per trace and per
    agent. Samples per attribute: (X per method, labels, groups). role_within: topologies whose
    role samples also form an attribute of their own (role_within_<topology>). vantage: an observer
    view from the sidecars (only the flows of the endpoints in view; a trace with none in view is
    kept with all-zero features, as python -m a2a_leakcheck run --vantage does)."""
    want_role = "role" in attributes
    if role_within and not want_role:
        raise SystemExit("--role-within needs role in --attributes")
    with tempfile.TemporaryDirectory(prefix="leakeval_") as tmp:
        col = collect(raw, trace_attributes(attributes), strip_dir=Path(tmp), vantage=vantage)
        ext = extract(col["traces"], keep_empty=vantage is not None)
        traces = [col["traces"][i] for i in ext["trace_index"]]
        kfp_trace, kfp_role = [], []
        for i, tr in enumerate(traces):
            servers = set(tr.port_role)
            pk = own_packets(tcp_packets(tr.pcap, dedup=True), servers)   # as extract(): each byte once
            kfp_trace.append(kfp_rows(pk, servers, None))
            port_of = {r: p for p, r in tr.port_role.items()}
            for j in np.flatnonzero(ext["role_trace"] == i) if want_role else ():
                kfp_role.append(kfp_rows(pk, servers, port_of[ext["role_y"][j]]))
    groups = np.array([tr.group for tr in traces])
    out = {"traces": len(traces), "empty_traces": ext["summary"]["empty_traces"], "samples": {}}
    if want_role:
        bytes_in = PerFlowFeatures.FEATURE_NAMES().index("bytes_in")
        role = {"X": {"leakcheck": ext["role_X"], "kfp_rf": np.stack(kfp_role),
                      "first_request": ext["role_X"][:, [bytes_in]]},
                "y": ext["role_y"].astype(str), "g": groups[ext["role_trace"]]}
        out["samples"]["role"] = role
        tops = np.array([tr.topology for tr in traces], dtype=object)[ext["role_trace"]]
        for top in role_within:
            keep = tops == top
            if not keep.any():
                raise SystemExit(f"--role-within {top}: no role samples from {top} traces in {raw}")
            out["samples"][f"{ROLE_WITHIN}{top}"] = {"X": {m: x[keep] for m, x in role["X"].items()},
                                                     "y": role["y"][keep], "g": role["g"][keep]}
    kt = np.stack(kfp_trace)
    for attr in trace_attributes(attributes):
        have = np.array([attr in tr.labels for tr in traces])
        if not have.any():
            continue
        out["samples"][attr] = {"X": {"leakcheck": ext["trace_X"][have], "kfp_rf": kt[have],
                                      "first_request": ext["first_request"][have].reshape(-1, 1)},
                                "y": np.array([tr.labels[attr] for tr, h in zip(traces, have) if h]),
                                "g": groups[have]}
    return out


def subsample(y: np.ndarray, g: np.ndarray, n: int, rng: np.random.Generator) -> np.ndarray:
    """n samples per class by whole prompt groups (the last group's surplus dropped)."""
    idx = []
    for c in sorted(set(y.tolist())):
        ci = np.flatnonzero(y == c)
        take: list[int] = []
        for grp in rng.permutation(np.unique(g[ci])):
            take += rng.permutation(ci[g[ci] == grp]).tolist()
            if len(take) >= n:
                break
        idx += take[:n]
    return np.array(sorted(idx))


# ── verdicts ─────────────────────────────────────────────────────────────────

def _cfg(a: argparse.Namespace, method: str) -> Config:
    return Config(margin=a.margin, n_splits=5, n_boot=a.n_boot, permutations=a.permutations, alpha=0.05,
                  min_per_class=a.min_per_class, seed=SEED, model="rf" if method == "kfp_rf" else "gbt",
                  null_model="rf-light", jobs=a.jobs)


def verdict(X, y, g, a, method: str, sev: dict) -> dict:
    r = analyze(X, y, g, {}, None, _cfg(a, method), sev)
    an, perm = r["analysis"] or {}, r["validation"].get("permutation") or {}
    return {"verdict": r["verdict"], "macro_f1": an.get("macro_f1"), "ci": [an.get("ci_lo"), an.get("ci_hi")],
            "p": perm.get("p_value"), "n": r["n"], "groups": r["n_groups"],
            "sample_check_ok": r["validation"]["min_samples"]["ok"]}


def run_tool(raw: Path, attrs: list[str], a: argparse.Namespace, out: Path, vantage: str | None = None) -> dict:
    """The tool as shipped, in a fresh process: full-data verdicts, runtime and memory."""
    cmd = [sys.executable, "-m", "a2a_leakcheck", "run", str(raw), "--out", str(out), "--strip",
           "--attributes", ",".join(x for x in attrs if not x.startswith(ROLE_WITHIN)),
           "--jobs", str(a.jobs), "--permutations", str(a.permutations),
           "--n-boot", str(a.n_boot), "--margin", str(a.margin), "--min-per-class", str(a.min_per_class)]
    if a.role_within:
        cmd += ["--role-within", ",".join(a.role_within)]
    if vantage:
        cmd += ["--vantage", vantage]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return tool_summary(json.loads((out / "report.json").read_text()))


def tool_report(path: Path, raw: Path, attrs: list[str], a: argparse.Namespace, vantage: str | None) -> dict:
    """A report of python -m a2a_leakcheck run made beforehand (--tool-reports), if it stands for
    the run this evaluation would make: same folder, view, attributes and verdict parameters, a
    clean checkout, and the tool's code unchanged between its commit and this one."""
    rep = json.loads((path / "report.json").read_text())
    p, want = rep["parameters"], {
        "attributes": [x for x in attrs if not x.startswith(ROLE_WITHIN)], "role_within": list(a.role_within),
        "margin": a.margin, "folds": 5, "n_boot": a.n_boot, "permutations": a.permutations, "alpha": 0.05,
        "min_per_class": a.min_per_class, "seed": SEED, "model": "gbt", "null_model": "rf-light",
        "rules": "default", "strip": True, "legacy_all_connections": False, "keep_retransmissions": False}
    bad = {k: [p.get(k), v] for k, v in want.items() if p.get(k) != v}
    if Path(rep["input"]["folder"]).resolve() != Path(raw).resolve():
        bad["folder"] = [rep["input"]["folder"], str(raw)]
    if rep["input"].get("vantage") != vantage:
        bad["vantage"] = [rep["input"].get("vantage"), vantage]
    if rep.get("git_dirty") is not False or not rep.get("git_commit"):
        bad["git"] = [rep.get("git_commit"), rep.get("git_dirty")]
    if bad:
        raise SystemExit(f"{path}/report.json does not stand for this evaluation: {bad}")
    changed = subprocess.run(["git", "diff", "--quiet", rep["git_commit"], "HEAD", "--", *TOOL_CODE]).returncode
    if changed:
        raise SystemExit(f"{path}/report.json: the tool's code changed since {rep['git_commit'][:8]} "
                         f"(git diff {rep['git_commit'][:8]} HEAD -- {' '.join(TOOL_CODE)})")
    return {**tool_summary(rep), "report": str(path / "report.json")}


def tool_summary(rep: dict) -> dict:
    return {"attributes": {k: {"verdict": r["verdict"], "reason": r["reason"],
                               "macro_f1": (r["analysis"] or {}).get("macro_f1"),
                               "ci": [(r["analysis"] or {}).get("ci_lo"), (r["analysis"] or {}).get("ci_hi")],
                               "p": (r["validation"].get("permutation") or {}).get("p_value"),
                               "false_positive_rate_on_permutations":
                                   (r["validation"].get("permutation") or {}).get("false_positive_rate"),
                               "carried_by": (r.get("attribution") or {}).get("top_family"),
                               "n": r["n"], "groups": r["n_groups"]}
                           for k, r in rep["attributes"].items()},
            "runtime": rep["runtime"], "git_commit": rep.get("git_commit"), "git_dirty": rep.get("git_dirty"),
            "visible_agents": rep["collection"].get("visible_agents")}


def evaluate_arm(name: str, raw: Path, a: argparse.Namespace, sev: dict, tmp: Path,
                 arm: str | None = None, vantage: str | None = None) -> dict:
    """One cell: an arm (name, or arm at a view)."""
    t = time.perf_counter()
    data = load_arm(raw, a.role_within, a.attributes, vantage)
    order = ("role", *(ROLE_WITHIN + t for t in a.role_within), *trace_attributes(a.attributes))
    attrs = [x for x in dict.fromkeys(order) if x in data["samples"]]
    print(f"[{name}] {data['traces']} traces ({data['empty_traces']} with nothing in view); attributes {attrs} "
          f"({time.perf_counter() - t:.0f} s)", flush=True)
    tool = (tool_report(Path(a.tool_reports.format(cell=name)), raw, attrs, a, vantage) if a.tool_reports
            else run_tool(raw, attrs, a, tmp / name, vantage))
    print(f"[{name}] tool: " + ", ".join(f"{k} {v['verdict']}" for k, v in tool["attributes"].items()), flush=True)
    res = {"data_dir": str(raw), "traces": data["traces"], "tool": tool, "attributes": {}}
    if vantage is not None:
        res.update({"arm": arm, "vantage": vantage, "empty_traces": data["empty_traces"]})
    for attr in attrs:
        ai = attr_index(attr, a.role_within)
        s = data["samples"][attr]
        y, g = s["y"], s["g"]
        perms = [np.random.default_rng([SEED, 1, ai, k]).permutation(y) for k in range(a.label_perms)]
        r = {"classes": {c: int((y == c).sum()) for c in sorted(set(y.tolist()))},
             "groups": int(len(np.unique(g))), "full": {}, "permuted": {}, "sample_size": {}}
        for m in METHODS:
            t = time.perf_counter()
            r["full"][m] = ({**tool["attributes"][attr], "source": "a2a_leakcheck run"} if m == "leakcheck"
                            else verdict(s["X"][m], y, g, a, m, sev))
            r["permuted"][m] = [verdict(s["X"][m], yp, g, a, m, sev)["verdict"] for yp in perms]
            print(f"[{name}] {attr:10s} {m:14s} real {r['full'][m]['verdict']:12s} permuted "
                  f"{ {v: r['permuted'][m].count(v) for v in VERDICTS} } ({time.perf_counter() - t:.0f} s)", flush=True)
        full_v = r["full"]["leakcheck"]["verdict"]
        for n in a.sizes:
            t = time.perf_counter()
            real, null = [], []
            for k in range(a.subsamples):
                idx = subsample(y, g, n, np.random.default_rng([SEED, 2, ai, n, k]))
                X = s["X"]["leakcheck"][idx]
                real.append(verdict(X, y[idx], g[idx], a, "leakcheck", sev)["verdict"])
                yp = np.random.default_rng([SEED, 3, ai, n, k]).permutation(y[idx])
                null.append(verdict(X, yp, g[idx], a, "leakcheck", sev)["verdict"])
            r["sample_size"][str(n)] = {
                "real": {v: real.count(v) for v in VERDICTS},
                "agreement_with_full": sum(v == full_v for v in real) / len(real),
                "permuted": {v: null.count(v) for v in VERDICTS}}
            print(f"[{name}] {attr:10s} n={n:<3d} real { {v: real.count(v) for v in VERDICTS} } permuted "
                  f"{ {v: null.count(v) for v in VERDICTS} } ({time.perf_counter() - t:.0f} s)", flush=True)
        res["attributes"][attr] = r
    return res


# ── rates ────────────────────────────────────────────────────────────────────

def rates(leak_verdicts: list[str], null_verdicts: list[str]) -> dict:
    tp, nl = leak_verdicts.count(LEAK), len(leak_verdicts)
    fp, nn = null_verdicts.count(LEAK), len(null_verdicts)
    return {"known_leaks": nl, "known_non_leaks": nn, "true_positives": tp, "false_positives": fp,
            "recall": tp / nl if nl else None, "recall_ci": wilson(tp, nl),
            "false_negative_rate": (nl - tp) / nl if nl else None, "false_negative_rate_ci": wilson(nl - tp, nl),
            "inconclusive_on_leaks": leak_verdicts.count(INCONCLUSIVE),
            "no_leak_on_leaks": leak_verdicts.count(NO_LEAK),
            "false_positive_rate": fp / nn if nn else None, "false_positive_rate_ci": wilson(fp, nn),
            "precision": tp / (tp + fp) if tp + fp else None, "precision_ci": wilson(tp, tp + fp)}


REF_STATUS = {"leak": "", "null": " (known non-leak)", "not known": " (not a known leak)",
              "no attack": " (no full-data attack finds a leak)"}


def reference(arms: dict, not_known: set[tuple[str, str]], ref: str = "labels") -> dict:
    """(cell, attribute) → "leak" (a known leak), "null" (a known non-leak: audit_null), "not known"
    (--not-known, by cell or by arm) or "no attack" (--reference full-attack: no method reads LEAK on
    the full data)."""
    out = {}
    for an, arm in arms.items():
        for attr, r in arm["attributes"].items():
            if attr == NULL_ATTR:
                out[an, attr] = "null"
            elif (an, attr) in not_known or (arm.get("arm"), attr) in not_known:
                out[an, attr] = "not known"
            elif ref == "labels" or any(r["full"][m]["verdict"] == LEAK for m in METHODS):
                out[an, attr] = "leak"
            else:
                out[an, attr] = "no attack"
    return out


def summarize(arms: dict, not_known: set[tuple[str, str]], sizes: list[int], ref: str = "labels") -> dict:
    status = reference(arms, not_known, ref)
    out = {"full_data": {}, "sample_size": {}}
    for m in METHODS:
        leaks, nulls = [], []
        for an, arm in arms.items():
            for attr, r in arm["attributes"].items():
                if status[an, attr] == "null":
                    nulls.append(r["full"][m]["verdict"])
                elif status[an, attr] == "leak":
                    leaks.append(r["full"][m]["verdict"])
                nulls += r["permuted"][m]
        out["full_data"][m] = rates(leaks, nulls)
    for n in sizes:
        leaks, nulls, agree = [], [], []
        for an, arm in arms.items():
            for attr, r in arm["attributes"].items():
                s = r["sample_size"][str(n)]
                expand = [v for v, c in s["real"].items() for _ in range(c)]
                if status[an, attr] == "null":
                    nulls += expand
                elif status[an, attr] == "leak":
                    leaks += expand
                    agree.append(s["agreement_with_full"])
                nulls += [v for v, c in s["permuted"].items() for _ in range(c)]
        out["sample_size"][str(n)] = {**rates(leaks, nulls),
                                      "agreement_with_full_mean": float(np.mean(agree)) if agree else None}
    return out


# ── outputs ──────────────────────────────────────────────────────────────────

def _r(x, ci=None) -> str:
    if x is None:
        return "—"
    return f"{x:.2f}" + (f" [{ci[0]:.2f}, {ci[1]:.2f}]" if ci else "")


def _cell(k: str, v: dict) -> str:
    if "vantage" not in v:
        return f"{k} (`{v['data_dir']}`, {v['traces']} traces)"
    return (f"{k} (`{v['data_dir']}` at view {v['vantage']}, {v['traces']} traces, "
            f"{v['empty_traces']} with nothing in view)")


def write_md(out: dict, path: Path) -> None:
    p = out["parameters"]
    ref = out.get("reference")
    status = reference(out["arms"], {tuple(x) for x in p["not_known"]}, p.get("reference", "labels"))
    L = [f"# a2a-leakcheck on known answers ({out['collection_id']})", "",
         f"Commit `{out['git_commit'][:8]}` (dirty: {out['git_dirty']}), seed {out['seed']}. "
         f"{'Cells' if p.get('vantage') else 'Arms'}: " + ", ".join(_cell(k, v) for k, v in out["arms"].items()) + ".",
         "", out["method"], *(["", ref["definition"]] if ref else []), "",
         "## Full data", "",
         "| Method | Recall [95% CI] | False-negative rate | of which NO LEAK | False-positive rate [95% CI] | "
         "Precision [95% CI] | Known leaks | Known non-leaks |", "|---|---|---|---|---|---|---|---|"]
    for m, r in out["summary"]["full_data"].items():
        L.append(f"| {m} | {_r(r['recall'], r['recall_ci'])} | {_r(r['false_negative_rate'])} | "
                 f"{r['no_leak_on_leaks']} | {_r(r['false_positive_rate'], r['false_positive_rate_ci'])} | "
                 f"{_r(r['precision'], r['precision_ci'])} | {r['known_leaks']} | {r['known_non_leaks']} |")
    L += ["", "| Arm | Attribute | Classes | " + " | ".join(f"{m}: real" for m in METHODS) + " | "
          + " | ".join(f"{m}: permuted L/I/N" for m in METHODS) + " |", "|---|---|---|" + "---|" * 2 * len(METHODS)]
    for an, arm in out["arms"].items():
        for attr, r in arm["attributes"].items():
            cells = []
            for m in METHODS:
                f = r["full"][m]
                cells.append(f"{f['verdict']} {_r(f['macro_f1'], f['ci'] if f['ci'][0] is not None else None)}")
            perm = [f"{r['permuted'][m].count(LEAK)}/{r['permuted'][m].count(INCONCLUSIVE)}/"
                    f"{r['permuted'][m].count(NO_LEAK)}" for m in METHODS]
            known = REF_STATUS[status[an, attr]]
            L.append(f"| {an} | {attr}{known} | {len(r['classes'])} | " + " | ".join(cells) + " | " + " | ".join(perm) + " |")
    L += ["", "## Sample size (a2a-leakcheck)", "",
          f"{p['subsamples']} draws per size, attribute and arm, by whole prompt groups; each draw also "
          "scored with its labels permuted.", "",
          "| Samples per class | Recall [95% CI] | INCONCLUSIVE on leaks | NO LEAK on leaks | Agreement with full data | "
          "False-positive rate [95% CI] |", "|---|---|---|---|---|---|"]
    for n, r in out["summary"]["sample_size"].items():
        L.append(f"| {n} | {_r(r['recall'], r['recall_ci'])} | {r['inconclusive_on_leaks']} of {r['known_leaks']} | "
                 f"{r['no_leak_on_leaks']} | {_r(r['agreement_with_full_mean'])} | "
                 f"{_r(r['false_positive_rate'], r['false_positive_rate_ci'])} |")
    L += ["", "| Arm | Attribute | " + " | ".join(f"n={n} L/I/N (agree)" for n in p["sizes"]) + " |",
          "|---|---|" + "---|" * len(p["sizes"])]
    for an, arm in out["arms"].items():
        for attr, r in arm["attributes"].items():
            L.append(f"| {an} | {attr} | " + " | ".join(
                f"{s['real'][LEAK]}/{s['real'][INCONCLUSIVE]}/{s['real'][NO_LEAK]} ({s['agreement_with_full']:.2f})"
                for s in r["sample_size"].values()) + " |")
    L += ["", "## Runtime and memory (a2a-leakcheck run, full data)", "",
          "| Arm | Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |", "|---|---|---|---|---|"]
    for an, arm in out["arms"].items():
        rt = arm["tool"]["runtime"]
        times = {**{k: v for k, v in rt["stages_s"].items() if k != "analysis"},
                 **{f"analysis:{k}": v for k, v in rt.get("analysis_by_attribute_s", {}).items()}}
        for k, m in rt.get("peak_rss_by_stage_mb", {}).items():
            w = m.get("worker_mb")
            L.append(f"| {an} | {k} | {times.get(k, 0):.1f} | {m['main_mb']:.0f} | {'—' if w is None else f'{w:.0f}'} |")
        L.append(f"| {an} | total | {rt['total_s']:.1f} | {rt['peak_rss_mb']:.0f} | {rt['peak_rss_children_mb']:.0f} |")
    first = out["arms"][next(iter(out["arms"]))]["tool"]
    took = (f"This evaluation ran in {len(out['parts'])} parallel parts; the longest took {out['runtime_s'] / 60:.0f} min."
            if out.get("parts") else f"This evaluation took {out['runtime_s'] / 60:.0f} min.")
    L += ["", f"{first['runtime']['workers']} worker processes; {first['runtime']['platform']}. {took}"]
    if first.get("report"):
        L += ["", "The tool's verdicts, runtime and memory come from its reports, each run alone beforehand "
              "(--tool-reports): " + ", ".join(f"`{v['tool']['report']}` (commit `{v['tool']['git_commit'][:8]}`)"
                                                for v in out["arms"].values()) + "."]
    path.write_text("\n".join(L) + "\n")


def make_figure(out: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = {LEAK: "#c0392b", INCONCLUSIVE: "#d9a400", NO_LEAK: "#2e7d4f"}
    arms = list(out["arms"])
    attrs = list(dict.fromkeys(x for a in arms for x in out["arms"][a]["attributes"]))
    sizes = out["parameters"]["sizes"]
    fig, axes = plt.subplots(len(arms), len(attrs), figsize=(3.0 * len(attrs), 2.6 * len(arms)),
                             sharex=True, sharey=True, squeeze=False)
    x = np.arange(len(sizes))
    for i, an in enumerate(arms):
        for j, attr in enumerate(attrs):
            ax = axes[i][j]
            r = out["arms"][an]["attributes"].get(attr)
            if r is None:
                ax.axis("off")
                continue
            bottom = np.zeros(len(sizes))
            for v in VERDICTS:
                h = np.array([r["sample_size"][str(n)]["real"][v] for n in sizes]) / out["parameters"]["subsamples"]
                ax.bar(x, h, bottom=bottom, color=colors[v], width=0.7, label=v, edgecolor="white", linewidth=0.5)
                bottom += h
            fp = [r["sample_size"][str(n)]["permuted"][LEAK] / out["parameters"]["subsamples"] for n in sizes]
            ax.plot(x, fp, "k^--", ms=4, lw=1, label="LEAK on permuted labels")
            ax.set_title(f"{an}: {attr} (full: {r['full']['leakcheck']['verdict']})", fontsize=9)
            ax.set_xticks(x, [str(n) for n in sizes])
            ax.spines[["top", "right"]].set_visible(False)
            if i == len(arms) - 1:
                ax.set_xlabel("samples per class")
            if j == 0:
                ax.set_ylabel("share of draws")
    h, lab = axes[0][0].get_legend_handles_labels()
    fig.legend(h, lab, loc="lower center", ncol=4, frameon=False, fontsize=8)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200)
    plt.close(fig)


REFERENCE_DEF = {
    "labels": "Known leaks: the real labels of every attribute but audit_null (and the cells named by "
              "--not-known). Known non-leaks: audit_null and the permuted labels.",
    "full-attack": "Known leaks: the cells (arm, view, attribute) in which the full-data attack finds a leak, that "
                   "is, in which a2a-leakcheck, k-FP or the first request's size reads LEAK on all of the cell's "
                   "data; recall is measured against them. A cell in which none does is neither a known leak nor "
                   "a known non-leak. Known non-leaks: audit_null and the permuted labels."}


def finish(out: dict, a: argparse.Namespace) -> None:
    p = out["parameters"]
    not_known = {tuple(x) for x in p["not_known"]}
    ref = p.get("reference", "labels")
    out["summary"] = summarize(out["arms"], not_known, p["sizes"], ref)
    status = reference(out["arms"], not_known, ref)
    out["reference"] = {"definition": REFERENCE_DEF[ref], "cells": [[an, attr, s] for (an, attr), s in status.items()]}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{a.name}.json").write_text(json.dumps(out, indent=2, default=float))
    write_md(out, RESULTS / f"{a.name}.md")
    make_figure(out, Path(a.figure or RESULTS / "figures" / f"{a.name}.png"))
    for m, r in out["summary"]["full_data"].items():
        print(f"{m:14s} recall {_r(r['recall'], r['recall_ci'])}  FPR {_r(r['false_positive_rate'], r['false_positive_rate_ci'])}"
              f"  precision {_r(r['precision'], r['precision_ci'])}")
    print(f"→ {RESULTS / a.name}.{{json,md}} ({out['runtime_s'] / 60:.0f} min, git_dirty {out['git_dirty']})")


def merge(a: argparse.Namespace) -> None:
    """Join the JSON outputs of runs over disjoint cells (one process per arm) into one evaluation."""
    parts = [(Path(f), json.loads(Path(f).read_text())) for f in a.merge]
    (f0, base), git = parts[0], _git()
    if git["git_dirty"]:
        raise SystemExit("--merge: the checkout has uncommitted code changes")
    out = {k: v for k, v in base.items() if k not in ("arms", "summary", "reference", "runtime_s", "data_dir")}
    out.update({"data_dir": {}, "arms": {}, "parts": []})
    for f, p in parts:
        for k in ("paper", "collection_id", "seed", "git_commit", "git_dirty", "task", "method", "parameters", "methods"):
            if p[k] != base[k]:
                raise SystemExit(f"--merge: {f} differs from {f0} in {k}")
        if p["git_commit"] != git["git_commit"] or p["git_dirty"]:
            raise SystemExit(f"--merge: {f} was made at {p['git_commit'][:8]} (dirty {p['git_dirty']}), "
                             f"not at this clean checkout ({git['git_commit'][:8]})")
        if set(p["arms"]) & set(out["arms"]):
            raise SystemExit(f"--merge: {f} repeats cells {sorted(set(p['arms']) & set(out['arms']))}")
        out["data_dir"].update(p["data_dir"])
        out["arms"].update(p["arms"])
        out["parts"].append({"file": str(f), "cells": list(p["arms"]), "runtime_s": p["runtime_s"]})
    out["runtime_s"] = max(x["runtime_s"] for x in out["parts"])
    print(f"merged {len(parts)} parts: {len(out['arms'])} cells", flush=True)
    finish(out, a)


def main(a: argparse.Namespace) -> None:
    if a.merge:
        return merge(a)
    t0 = time.perf_counter()
    arms = dict(x.split("=", 1) for x in a.arm) if a.arm else \
        {"tls": "data/raw_tlspair_tls", "cleartext": "data/raw_tlspair_clear"}
    cells = {(n if v is None else f"{n}_{v}"): (n, raw, v) for n, raw in arms.items() for v in (a.vantage or [None])}
    not_known = {tuple(x.split(":", 1)) for x in a.not_known}
    sev = load_rules(None)["severity"]
    unit = "arm and view" if a.vantage else "arm"
    out = {"paper": "P2", "collection_id": a.collection_id, "data_dir": arms, "seed": SEED, **_git(),
           "task": "a2a-leakcheck verdicts on known leaks (real labels) and known non-leaks (permuted labels, "
                   "audit_null)",
           "method": ("Full-data verdicts on the real labels, and runtime and memory, from `python -m a2a_leakcheck "
                      f"run --strip` in a fresh process per {unit}. Permuted labels, baselines and subsamples go through "
                      "the same verdict rule (a2a_leakcheck.analyze: 5-fold StratifiedGroupKFold by prompt group, "
                      f"macro-F1 with a {a.n_boot}-resample cluster-bootstrap 95% CI, LEAK above chance + "
                      f"{a.margin}, {a.permutations}-permutation test with the rf-light null at alpha 0.05, at least "
                      f"{a.min_per_class} samples per class in 5 groups), without feature attribution, which the "
                      "verdict does not use. Own connections only. Ports are never features."),
           "parameters": {"sizes": a.sizes, "subsamples": a.subsamples, "label_perms": a.label_perms,
                          "permutations": a.permutations, "n_boot": a.n_boot, "margin": a.margin,
                          "min_per_class": a.min_per_class, "folds": 5, "null_model": "rf-light", "alpha": 0.05,
                          "jobs": a.jobs, "not_known": sorted([list(x) for x in not_known]),
                          "role_within": a.role_within, "attributes": a.attributes, "vantage": a.vantage,
                          "reference": a.reference, "tool_reports": a.tool_reports},
           "methods": METHODS, "arms": {}}
    with tempfile.TemporaryDirectory(prefix="leakeval_reports_") as tmp:
        for name, (arm, raw, v) in cells.items():
            out["arms"][name] = evaluate_arm(name, Path(raw), a, sev, Path(tmp), arm, v)
    out["runtime_s"] = time.perf_counter() - t0
    finish(out, a)


def parser() -> argparse.ArgumentParser:
    lst = lambda v: [x.strip() for x in v.split(",") if x.strip()]  # noqa: E731
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--arm", action="append", default=[], help="NAME=CAPTURE_DIR (repeat); default: the TLS control")
    p.add_argument("--collection-id", default="TLS control", dest="collection_id")
    p.add_argument("--attributes", type=lst, default=list(ATTRS),
                   help="comma-separated: role (from agent_endpoints) and sidecar keys; audit_null is added where "
                        "present (default role,workflow,topology)")
    p.add_argument("--vantage", type=lst, default=[], metavar="VIEWS",
                   help="comma-separated observer views (the sidecars' vantages): each arm is scored at each")
    p.add_argument("--reference", choices=REFERENCES, default="labels",
                   help="known leaks: the real labels (labels), or the cells in which the full-data attack finds a "
                        "leak (full-attack)")
    p.add_argument("--not-known", action="append", default=[], dest="not_known",
                   help="ARM:ATTRIBUTE (ARM: an arm or an ARM_VIEW cell) whose real labels are not a known leak (repeat)")
    p.add_argument("--role-within", default="", dest="role_within", metavar="TOPOLOGIES", type=lst,
                   help="comma-separated topologies: also score role on each one's traces only, as a known leak")
    p.add_argument("--tool-reports", default=None, dest="tool_reports", metavar="TEMPLATE",
                   help="read the tool's full-data reports from TEMPLATE/report.json ({cell} = ARM or ARM_VIEW) "
                        "instead of running it")
    p.add_argument("--merge", nargs="+", default=None, metavar="PART_JSON",
                   help="join the JSON outputs of runs over disjoint cells (same commit and parameters)")
    p.add_argument("--sizes", type=int, nargs="+", default=list(SIZES))
    p.add_argument("--subsamples", type=int, default=20)
    p.add_argument("--label-perms", type=int, default=20, dest="label_perms",
                   help="permuted-label sets per attribute and arm (known non-leaks on full data)")
    p.add_argument("--permutations", type=int, default=99, help="the tool's permutation test")
    p.add_argument("--n-boot", type=int, default=1000, dest="n_boot")
    p.add_argument("--margin", type=float, default=0.05)
    p.add_argument("--min-per-class", type=int, default=20, dest="min_per_class")
    p.add_argument("--jobs", type=int, default=-1)
    p.add_argument("--name", default="paper2_tool_eval", help="output name under data/results/")
    p.add_argument("--figure", default=None)
    return p


if __name__ == "__main__":
    main(parser().parse_args())
