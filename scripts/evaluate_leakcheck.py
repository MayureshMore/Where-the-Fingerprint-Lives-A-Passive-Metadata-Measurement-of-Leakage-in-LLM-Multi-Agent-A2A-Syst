#!/usr/bin/env python3
"""
Paper 2: how well a2a-leakcheck's verdicts hold up, on collections whose answer is known.

  known leaks       the real labels: role, workflow and topology on each arm (paper 1 and the TLS
                    control: all three leak, with and without TLS). --not-known ARM:ATTR leaves a
                    cell out of the known leaks (the padded C2 arm's workflow, which is the open
                    question there); it is still reported.
  known non-leaks   permuted labels: --label-perms random permutations of each attribute's labels
                    over its samples (labels independent of the traffic), and audit_null, a
                    sidecar label drawn from the prompt group alone (C2 sidecars,
                    scripts/collect_session.py), where present.

  1. Full data      the tool as shipped (python -m a2a_leakcheck run, a fresh process per arm)
                    gives the full-data verdicts on the real labels and the runtime and peak memory
                    per stage. The permuted labels run through the same verdict rule
                    (a2a_leakcheck.analyze with the same Config: 5-fold grouped CV, cluster-
                    bootstrap CI, chance + margin, 99-permutation test with the rf-light null).
                    Feature attribution is skipped there: the verdict does not use it.
  2. Baselines      inside the same verdict rule, on the same real and permuted labels:
                    k-FP features (features/kfp.py, direction and timing only) with the tool's RF
                    (--model rf); and the first request's size alone with GBT (for role, the bytes
                    the agent receives, the tool's single request-size feature).
  3. Sample size    n = 5/10/20/30/50 samples per class, --subsamples draws each, by whole prompt
                    groups (per class, groups in random order until n samples; the last group's
                    surplus is dropped), on the real labels and on one label permutation per draw.
                    Share of LEAK / INCONCLUSIVE / NO LEAK, and agreement with the full-data verdict.

Rates (Wilson 95% intervals): recall = LEAK on known leaks; false-negative rate = 1 − recall,
split into INCONCLUSIVE and NO LEAK (a wrong all-clear); false-positive rate = LEAK on known
non-leaks; precision = LEAK on known leaks / all LEAK verdicts in the set.

Writes data/results/paper2_tool_eval.{json,md} (A2A_RESULTS_DIR overrides data/results) and
data/results/figures/paper2_tool_eval.png.

Usage:
    python scripts/evaluate_leakcheck.py                                  # TLS control, both arms
    python scripts/evaluate_leakcheck.py --collection-id C2 \\
        --arm unpadded=data/raw_c2 --arm padded=data/raw_c2_pad --not-known padded:workflow
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
SIZES = (5, 10, 20, 30, 50)
VERDICTS = (LEAK, INCONCLUSIVE, NO_LEAK)
METHODS = {"leakcheck": "a2a-leakcheck: GBT on the header-only features (195 per trace, 35 per agent)",
           "kfp_rf": f"k-FP features ({N_KFP}, direction and timing only) with the tool's RF",
           "first_request": "first-request size alone with GBT (role: bytes the agent receives)"}
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


def load_arm(raw: Path) -> dict:
    """Collect and extract once per arm, as the tool does, plus k-FP vectors per trace and per
    agent. Samples per attribute: (X per method, labels, groups)."""
    with tempfile.TemporaryDirectory(prefix="leakeval_") as tmp:
        col = collect(raw, ["workflow", "topology", NULL_ATTR], strip_dir=Path(tmp))
        ext = extract(col["traces"])
        traces = [col["traces"][i] for i in ext["trace_index"]]
        kfp_trace, kfp_role = [], []
        for i, tr in enumerate(traces):
            servers = set(tr.port_role)
            pk = own_packets(tcp_packets(tr.pcap), servers)
            kfp_trace.append(kfp_rows(pk, servers, None))
            port_of = {r: p for p, r in tr.port_role.items()}
            for j in np.flatnonzero(ext["role_trace"] == i):
                kfp_role.append(kfp_rows(pk, servers, port_of[ext["role_y"][j]]))
    groups = np.array([tr.group for tr in traces])
    out = {"traces": len(traces), "samples": {}}
    bytes_in = PerFlowFeatures.FEATURE_NAMES().index("bytes_in")
    out["samples"]["role"] = {"X": {"leakcheck": ext["role_X"], "kfp_rf": np.stack(kfp_role),
                                    "first_request": ext["role_X"][:, [bytes_in]]},
                              "y": ext["role_y"].astype(str), "g": groups[ext["role_trace"]]}
    kt = np.stack(kfp_trace)
    for attr in ("workflow", "topology", NULL_ATTR):
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


def run_tool(raw: Path, attrs: list[str], a: argparse.Namespace, out: Path) -> dict:
    """The tool as shipped, in a fresh process: full-data verdicts, runtime and memory."""
    cmd = [sys.executable, "-m", "a2a_leakcheck", "run", str(raw), "--out", str(out), "--strip",
           "--attributes", ",".join(attrs), "--jobs", str(a.jobs), "--permutations", str(a.permutations),
           "--n-boot", str(a.n_boot), "--margin", str(a.margin), "--min-per-class", str(a.min_per_class)]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    rep = json.loads((out / "report.json").read_text())
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


def evaluate_arm(name: str, raw: Path, a: argparse.Namespace, sev: dict, tmp: Path) -> dict:
    t = time.perf_counter()
    data = load_arm(raw)
    attrs = [x for x in (*ATTRS, NULL_ATTR) if x in data["samples"]]
    print(f"[{name}] {data['traces']} traces; attributes {attrs} ({time.perf_counter() - t:.0f} s)", flush=True)
    tool = run_tool(raw, attrs, a, tmp / name)
    print(f"[{name}] tool: " + ", ".join(f"{k} {v['verdict']}" for k, v in tool["attributes"].items()), flush=True)
    res = {"data_dir": str(raw), "traces": data["traces"], "tool": tool, "attributes": {}}
    for ai, attr in enumerate(attrs):
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


def summarize(arms: dict, not_known: set[tuple[str, str]], sizes: list[int]) -> dict:
    out = {"full_data": {}, "sample_size": {}}
    for m in METHODS:
        leaks, nulls = [], []
        for an, arm in arms.items():
            for attr, r in arm["attributes"].items():
                if attr == NULL_ATTR:
                    nulls.append(r["full"][m]["verdict"])
                elif (an, attr) not in not_known:
                    leaks.append(r["full"][m]["verdict"])
                nulls += r["permuted"][m]
        out["full_data"][m] = rates(leaks, nulls)
    for n in sizes:
        leaks, nulls, agree = [], [], []
        for an, arm in arms.items():
            for attr, r in arm["attributes"].items():
                s = r["sample_size"][str(n)]
                expand = [v for v, c in s["real"].items() for _ in range(c)]
                if attr == NULL_ATTR:
                    nulls += expand
                elif (an, attr) not in not_known:
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


def write_md(out: dict, path: Path) -> None:
    p = out["parameters"]
    L = [f"# a2a-leakcheck on known answers ({out['collection_id']})", "",
         f"Commit `{out['git_commit'][:8]}` (dirty: {out['git_dirty']}), seed {out['seed']}. "
         f"Arms: " + ", ".join(f"{k} (`{v['data_dir']}`, {v['traces']} traces)" for k, v in out["arms"].items()) + ".",
         "", out["method"], "",
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
            known = " (not a known leak)" if [an, attr] in p["not_known"] else (" (known non-leak)" if attr == NULL_ATTR else "")
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
    L += ["", f"{out['arms'][next(iter(out['arms']))]['tool']['runtime']['workers']} worker processes; "
          f"{out['arms'][next(iter(out['arms']))]['tool']['runtime']['platform']}. This evaluation took "
          f"{out['runtime_s'] / 60:.0f} min."]
    path.write_text("\n".join(L) + "\n")


def make_figure(out: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = {LEAK: "#c0392b", INCONCLUSIVE: "#d9a400", NO_LEAK: "#2e7d4f"}
    arms = list(out["arms"])
    attrs = [x for x in (*ATTRS, NULL_ATTR) if any(x in out["arms"][a]["attributes"] for a in arms)]
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


def main(a: argparse.Namespace) -> None:
    t0 = time.perf_counter()
    arms = dict(x.split("=", 1) for x in a.arm) if a.arm else \
        {"tls": "data/raw_tlspair_tls", "cleartext": "data/raw_tlspair_clear"}
    not_known = {tuple(x.split(":", 1)) for x in a.not_known}
    sev = load_rules(None)["severity"]
    out = {"paper": "P2", "collection_id": a.collection_id, "data_dir": arms, "seed": SEED, **_git(),
           "task": "a2a-leakcheck verdicts on known leaks (real labels) and known non-leaks (permuted labels, "
                   "audit_null)",
           "method": ("Full-data verdicts on the real labels, and runtime and memory, from `python -m a2a_leakcheck "
                      "run --strip` in a fresh process per arm. Permuted labels, baselines and subsamples go through "
                      "the same verdict rule (a2a_leakcheck.analyze: 5-fold StratifiedGroupKFold by prompt group, "
                      f"macro-F1 with a {a.n_boot}-resample cluster-bootstrap 95% CI, LEAK above chance + "
                      f"{a.margin}, {a.permutations}-permutation test with the rf-light null at alpha 0.05, at least "
                      f"{a.min_per_class} samples per class in 5 groups), without feature attribution, which the "
                      "verdict does not use. Own connections only. Ports are never features."),
           "parameters": {"sizes": a.sizes, "subsamples": a.subsamples, "label_perms": a.label_perms,
                          "permutations": a.permutations, "n_boot": a.n_boot, "margin": a.margin,
                          "min_per_class": a.min_per_class, "folds": 5, "null_model": "rf-light", "alpha": 0.05,
                          "jobs": a.jobs, "not_known": sorted([list(x) for x in not_known])},
           "methods": METHODS, "arms": {}}
    with tempfile.TemporaryDirectory(prefix="leakeval_reports_") as tmp:
        for name, raw in arms.items():
            out["arms"][name] = evaluate_arm(name, Path(raw), a, sev, Path(tmp))
    out["summary"] = summarize(out["arms"], not_known, a.sizes)
    out["runtime_s"] = time.perf_counter() - t0
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{a.name}.json").write_text(json.dumps(out, indent=2, default=float))
    write_md(out, RESULTS / f"{a.name}.md")
    make_figure(out, Path(a.figure or RESULTS / "figures" / f"{a.name}.png"))
    for m, r in out["summary"]["full_data"].items():
        print(f"{m:14s} recall {_r(r['recall'], r['recall_ci'])}  FPR {_r(r['false_positive_rate'], r['false_positive_rate_ci'])}"
              f"  precision {_r(r['precision'], r['precision_ci'])}")
    print(f"→ {RESULTS / a.name}.{{json,md}} ({out['runtime_s'] / 60:.0f} min, git_dirty {out['git_dirty']})")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--arm", action="append", default=[], help="NAME=CAPTURE_DIR (repeat); default: the TLS control")
    p.add_argument("--collection-id", default="TLS control", dest="collection_id")
    p.add_argument("--not-known", action="append", default=[], dest="not_known",
                   help="ARM:ATTRIBUTE whose real labels are not a known leak (repeat)")
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
    main(p.parse_args())
