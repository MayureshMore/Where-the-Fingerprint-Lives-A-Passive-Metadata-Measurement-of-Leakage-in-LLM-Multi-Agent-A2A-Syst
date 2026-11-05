"""
leakcheck command line.

    python -m a2a_leakcheck run CAPTURE_DIR --out REPORT_DIR [options]
    python -m a2a_leakcheck diff NEW_REPORT.json BASELINE_REPORT.json

Exit codes: 0 done; 1 error; 2 a LEAK (with --fail-on-leak); 3 a new LEAK against --baseline
(run) or against the baseline report (diff). Runs in CI as: run ... --baseline last/report.json.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from a2a_leakcheck import __version__  # noqa: E402
from a2a_leakcheck.analyze import LEAK, Config, analyze  # noqa: E402
from a2a_leakcheck.collect import collect  # noqa: E402
from a2a_leakcheck.extract import extract  # noqa: E402
from a2a_leakcheck.report import diff, write_html, write_json, write_markdown  # noqa: E402
from a2a_leakcheck.rules import facts, hints, load_rules  # noqa: E402
from features.families import FAMILIES, family_columns  # noqa: E402
from features.per_flow import PerFlowFeatures  # noqa: E402

logger = logging.getLogger("leakcheck")
ROLE = "role"


def _peak_mb(who: int) -> float:
    rss = resource.getrusage(who).ru_maxrss
    return rss / 2**20 if sys.platform == "darwin" else rss / 2**10      # bytes on macOS, KiB on Linux


def _git() -> dict:
    """Commit of the tool's checkout, and whether its code had uncommitted changes (changes under
    data/, such as reports from earlier runs, do not count)."""
    def run(*args):
        return subprocess.run(["git", *args], capture_output=True, text=True,
                              cwd=Path(__file__).resolve().parent, timeout=5).stdout.strip()
    try:
        root = run("rev-parse", "--show-toplevel")
        dirty = subprocess.run(["git", "status", "--porcelain", "--", ".", ":(exclude)data"], capture_output=True,
                               text=True, cwd=root or None, timeout=5).stdout.strip()
        return {"git_commit": run("rev-parse", "HEAD") or None, "git_dirty": bool(dirty)}
    except Exception:  # noqa: BLE001
        return {"git_commit": None, "git_dirty": None}


def _stop_workers() -> None:
    """Worker processes count toward RUSAGE_CHILDREN only once they exit and are reaped, so the
    (reusable) worker pool is stopped after each attribute before measuring. ru_maxrss of the
    children is the largest single worker; peak use is about the main process plus workers × that.
    Peaks are running maxima: the value at the end of a stage covers that stage and all before."""
    from joblib.externals.loky import get_reusable_executor
    get_reusable_executor().shutdown(wait=True)


def visible_agents(traces: list, visible: list[list[str]]) -> dict:
    """Per topology: traces, and in how many of them each listed agent carries traffic. An agent
    that is listed in agent_endpoints but never seen gives no role samples."""
    out: dict[str, dict] = {}
    for tr, seen in zip(traces, visible):
        t = out.setdefault(tr.topology or "all", {"traces": 0, "roles": {}})
        t["traces"] += 1
        for role in tr.port_role.values():
            t["roles"].setdefault(role, 0)
        for role in seen:
            t["roles"][role] += 1
    for t in out.values():
        t["never_seen"] = sorted(r for r, n in t["roles"].items() if n == 0)
        t["roles"] = dict(sorted(t["roles"].items()))
    return dict(sorted(out.items()))


def run(a: argparse.Namespace) -> int:
    t0 = time.perf_counter()
    stages: dict[str, float] = {}
    peaks: dict[str, dict] = {}                      # running peak memory at the end of each stage
    attributes = [x.strip() for x in a.attributes.split(",") if x.strip()]
    cfg = Config(margin=a.margin, n_splits=a.folds, n_boot=a.n_boot, permutations=a.permutations,
                 alpha=a.alpha, min_per_class=a.min_per_class, seed=a.seed, model=a.model,
                 null_model=a.null_model, jobs=a.jobs)
    rules = load_rules(a.rules)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="leakcheck_") as tmp:
        t = time.perf_counter()
        col = collect(Path(a.captures), [x for x in attributes if x != ROLE],
                      strip_dir=Path(tmp) if a.strip else None)
        stages["collection"] = time.perf_counter() - t
        peaks["collection"] = {"main_mb": _peak_mb(resource.RUSAGE_SELF)}
        logger.info("collection: %d traces from %d captures", col["summary"]["traces"], col["summary"]["pcaps"])
        t = time.perf_counter()
        ext = extract(col["traces"], legacy=a.legacy_all_connections)
        stages["extraction"] = time.perf_counter() - t
        peaks["extraction"] = {"main_mb": _peak_mb(resource.RUSAGE_SELF)}
        logger.info("extraction: %d traces, %d role samples", ext["summary"]["traces"], ext["summary"]["role_samples"])

    traces = [col["traces"][i] for i in ext["trace_index"]]
    col["summary"]["visible_agents"] = visible_agents(traces, ext["visible_roles"])
    groups = np.array([tr.group for tr in traces])
    results, by_attr = {}, {}
    t = time.perf_counter()
    for attr in attributes:
        ta = time.perf_counter()
        logger.info("analysis: %s", attr)
        if attr == ROLE:
            X, y, g = ext["role_X"], ext["role_y"], groups[ext["role_trace"]]
            fams = {f: family_columns(f, True) for f in FAMILIES}
            single = ("bytes_in", X[:, PerFlowFeatures.FEATURE_NAMES().index("bytes_in")])
        else:
            have = np.array([attr in tr.labels for tr in traces])
            X = ext["trace_X"][have]
            y = np.array([tr.labels[attr] for tr, h in zip(traces, have) if h])
            g = groups[have]
            fams = {f: family_columns(f, False) for f in FAMILIES}
            single = ("first_request_bytes", ext["first_request"][have])
        r = analyze(X, y, g, fams, single, cfg, rules["severity"])
        r["mitigations"] = hints(facts(attr, r), rules)
        results[attr] = r
        by_attr[attr] = time.perf_counter() - ta
        _stop_workers()
        peaks[f"analysis:{attr}"] = {"main_mb": _peak_mb(resource.RUSAGE_SELF),
                                     "worker_mb": _peak_mb(resource.RUSAGE_CHILDREN)}
        logger.info("  %s: %s (%s)", attr, r["verdict"], r["reason"])
    stages["analysis"] = time.perf_counter() - t

    report = {
        "tool": "a2a-leakcheck", "version": __version__,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **_git(),
        "input": {"folder": str(Path(a.captures)), "label": a.label},
        "parameters": {"attributes": attributes, "margin": cfg.margin, "folds": cfg.n_splits,
                       "n_boot": cfg.n_boot, "permutations": cfg.permutations, "alpha": cfg.alpha,
                       "min_per_class": cfg.min_per_class, "seed": cfg.seed, "model": cfg.model,
                       "null_model": cfg.null_model, "jobs": cfg.jobs,
                       "rules": str(a.rules or "default"), "strip": a.strip,
                       "legacy_all_connections": a.legacy_all_connections},
        "collection": col["summary"],
        "extraction": ext["summary"],
        "attributes": results,
        "summary": {v: [k for k, r in results.items() if r["verdict"] == v]
                    for v in ("LEAK", "NO LEAK", "INCONCLUSIVE")},
    }
    code = 0
    if a.baseline:
        report["diff"] = diff(report, json.loads(Path(a.baseline).read_text()), str(a.baseline))
        if report["diff"]["new_leaks"]:
            code = 3
    if a.fail_on_leak and report["summary"]["LEAK"] and code == 0:
        code = 2

    # measured up to here; writing the reports takes milliseconds
    report["runtime"] = {"total_s": time.perf_counter() - t0, "stages_s": stages,
                         "analysis_by_attribute_s": by_attr, "peak_rss_by_stage_mb": peaks,
                         "peak_rss_mb": _peak_mb(resource.RUSAGE_SELF),
                         "peak_rss_children_mb": _peak_mb(resource.RUSAGE_CHILDREN),
                         "workers": os.cpu_count() if cfg.jobs in (-1, 0) else cfg.jobs,
                         "python": platform.python_version(), "platform": platform.platform()}
    write_json(report, out / "report.json")
    write_markdown(report, out / "report.md")
    if a.html:
        write_html(report, out / "report.html")
    print(f"{', '.join(f'{k}: {r['verdict']}' for k, r in results.items())} → {out}/report.md")
    if report.get("diff", {}).get("new_leaks"):
        print("new LEAK against the baseline: " + ", ".join(report["diff"]["new_leaks"]))
    return code


def diff_cmd(a: argparse.Namespace) -> int:
    new, old = json.loads(Path(a.new).read_text()), json.loads(Path(a.baseline).read_text())
    d = diff(new, old, str(a.baseline))
    for x in d["changes"]:
        print(f"{x['attribute']}: {x['before']} → {x['after']}")
    if not d["changes"]:
        print("no verdict changed")
    if d["new_leaks"]:
        print("new LEAK: " + ", ".join(d["new_leaks"]))
        return 3
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="leakcheck", description="Do encrypted agent-to-agent captures leak "
                                "agent role, workflow or topology?")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="analyse a folder of header-only pcaps with label sidecars")
    r.add_argument("captures", help="folder of *.pcap, each with a *.json label sidecar")
    r.add_argument("--out", required=True, help="report folder (report.json, report.md[, report.html])")
    r.add_argument("--attributes", default="role,workflow,topology",
                   help="comma-separated; role comes from agent_endpoints, others from sidecar keys")
    r.add_argument("--margin", type=float, default=0.05, help="macro-F1 above chance that counts as a leak")
    r.add_argument("--permutations", type=int, default=99,
                   help="label permutations (0 = skip the test); 99 lets p reach 0.01")
    r.add_argument("--null-model", choices=["rf-light", "gbt", "rf", "same"], default="rf-light",
                   dest="null_model", help="model of the permutation test (scores real and permuted labels)")
    r.add_argument("--jobs", type=int, default=-1, help="parallel CV runs (-1: one per core)")
    r.add_argument("--alpha", type=float, default=0.05, help="permutation-test level a LEAK must pass")
    r.add_argument("--n-boot", type=int, default=1000, dest="n_boot", help="cluster-bootstrap resamples")
    r.add_argument("--min-per-class", type=int, default=20, dest="min_per_class")
    r.add_argument("--folds", type=int, default=5)
    r.add_argument("--model", choices=["gbt", "rf", "rf-light"], default="gbt")
    r.add_argument("--seed", type=int, default=42)
    r.add_argument("--rules", type=Path, default=None, help="rules YAML (default: a2a_leakcheck/rules.yaml)")
    r.add_argument("--strip", action="store_true",
                   help="analyse header-only copies of captures that still hold payload bytes")
    r.add_argument("--html", action="store_true", help="also write report.html")
    r.add_argument("--legacy-all-connections", action="store_true", dest="legacy_all_connections",
                   help="use every connection on the agent ports, not only those each capture opens "
                        "itself (the earlier measurement)")
    r.add_argument("--label", default="", help="name for this run in the report")
    r.add_argument("--baseline", type=Path, default=None,
                   help="previous report.json; exit 3 if an attribute is newly LEAK")
    r.add_argument("--fail-on-leak", action="store_true", dest="fail_on_leak", help="exit 2 on any LEAK")
    d = sub.add_parser("diff", help="compare two reports; exit 3 on a new LEAK")
    d.add_argument("new")
    d.add_argument("baseline")
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for noisy in ("models", "features", "scapy"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    a = parser().parse_args(argv)
    return run(a) if a.cmd == "run" else diff_cmd(a)
