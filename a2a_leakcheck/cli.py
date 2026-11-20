"""
leakcheck command line.

    python -m a2a_leakcheck run CAPTURE_DIR --out REPORT_DIR [options]       collect, extract, analyse
    python -m a2a_leakcheck extract CAPTURE_DIR --out FEATURES_DIR [options]  collect and extract only
    python -m a2a_leakcheck run FEATURES_DIR --out REPORT_DIR [options]       analyse saved features
    python -m a2a_leakcheck diff NEW_REPORT.json BASELINE_REPORT.json

Exit codes (report.py): 0 done (the audit completed and the release policy, if any, holds); 1 error;
2 a LEAK (with --fail-on-leak); 3 a new LEAK against --baseline (run) or against the baseline
report (diff); 4 the baseline is not comparable (a different verdict rule, view, feature schema or
attribute definition), so the verdicts were not compared; 5 the --strict or --require policy failed
(an INCONCLUSIVE, or a required attribute missing or INCONCLUSIVE). When several apply: 4, 3, 2, 5.
Runs in CI as: run ... --baseline last/report.json [--strict | --require ATTR,...].
By default INCONCLUSIVE never fails a run: it is listed for review, and a LEAK that is now
INCONCLUSIVE or missing is listed under needs_review; only a LEAK that is now NO LEAK is resolved.
"""

from __future__ import annotations

import argparse
import hashlib
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
from a2a_leakcheck.extract import extract, is_features, load_features, save_features  # noqa: E402
from a2a_leakcheck.report import (diff, release_policy, status_lines, write_html, write_json,  # noqa: E402
                                  write_markdown)
from a2a_leakcheck.rules import context, facts, hints, load_rules  # noqa: E402
from features.families import FAMILIES, family_columns  # noqa: E402
from features.per_flow import PerFlowFeatures  # noqa: E402

logger = logging.getLogger("leakcheck")
ROLE = "role"
ROLE_WITHIN = "role_within_"                     # role scored on the traces of one topology


def _peak_mb(who: int) -> float:
    rss = resource.getrusage(who).ru_maxrss
    return rss / 2**20 if sys.platform == "darwin" else rss / 2**10      # bytes on macOS, KiB on Linux


def _git() -> dict:
    """Commit of the tool's checkout, and whether its code had uncommitted changes (changes under
    data/ and examples/expected/, reports from earlier runs, do not count). A vendored copy (the
    SafeIoT pipeline tree) is not a checkout of the tool: it reports the commit it was copied from
    (SOURCE.json next to the package) and whether any copied file has changed since. Anything else
    reports null for both, not "clean"."""
    pkg = Path(__file__).resolve().parent

    def run(*args, cwd):
        return subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd, timeout=5).stdout.strip()
    try:
        root = run("rev-parse", "--show-toplevel", cwd=pkg)
        if root and Path(root).resolve() == pkg.parent:
            dirty = run("status", "--porcelain", "--", ".", ":(exclude)data", ":(exclude)examples/expected", cwd=root)
            return {"git_commit": run("rev-parse", "HEAD", cwd=root) or None, "git_dirty": bool(dirty)}
    except Exception:  # noqa: BLE001
        pass
    src = pkg.parent / "SOURCE.json"
    if src.exists():
        meta = json.loads(src.read_text())
        changed = [f for f, h in meta["files"].items() if not (pkg.parent / f).exists()
                   or hashlib.sha256((pkg.parent / f).read_bytes()).hexdigest() != h]
        return {"git_commit": meta["commit"], "git_dirty": bool(changed) or bool(meta.get("dirty")),
                "source": f"vendored copy of {meta['repository']} at {meta['commit'][:8]}"}
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


def _extraction_parameters(a: argparse.Namespace) -> dict:
    return {"strip": a.strip, "legacy_all_connections": a.legacy_all_connections,
            "keep_retransmissions": a.keep_retransmissions, **({"cleartext": True} if a.cleartext else {})}


def _attributes(a: argparse.Namespace, default: str = "role,workflow,topology") -> list[str]:
    return [x.strip() for x in (a.attributes or default).split(",") if x.strip()]


def _collect_extract(a: argparse.Namespace, attributes: list[str], stages: dict, peaks: dict) -> tuple:
    """Stage 2: header-only check (collection) and feature extraction. (collection, extraction, traces)."""
    with tempfile.TemporaryDirectory(prefix="leakcheck_") as tmp:
        t = time.perf_counter()
        col = collect(Path(a.captures), [x for x in attributes if x != ROLE],
                      strip_dir=Path(tmp) if a.strip else None, vantage=a.vantage, cleartext=a.cleartext)
        stages["collection"] = time.perf_counter() - t
        if not col["traces"]:
            reasons = sorted({x["reason"] for x in col["summary"]["skipped"]})
            raise SystemExit(f"no usable trace in {a.captures}: " + ("; ".join(reasons) or "no pcaps"))
        peaks["collection"] = {"main_mb": _peak_mb(resource.RUSAGE_SELF)}
        logger.info("collection: %d traces from %d captures", col["summary"]["traces"], col["summary"]["pcaps"])
        t = time.perf_counter()
        ext = extract(col["traces"], legacy=a.legacy_all_connections, keep_empty=a.vantage is not None,
                      dedup=not a.keep_retransmissions)
        stages["extraction"] = time.perf_counter() - t
        peaks["extraction"] = {"main_mb": _peak_mb(resource.RUSAGE_SELF)}
        logger.info("extraction: %d traces, %d role samples", ext["summary"]["traces"], ext["summary"]["role_samples"])
    traces = [col["traces"][i] for i in ext["trace_index"]]
    col["summary"]["visible_agents"] = visible_agents(traces, ext["visible_roles"])
    return col, ext, traces


def extract_cmd(a: argparse.Namespace) -> int:
    """Stage 2 alone: write the features a later `run FEATURES_DIR` analyses."""
    t0, stages, peaks = time.perf_counter(), {}, {}
    attributes = _attributes(a)
    col, ext, traces = _collect_extract(a, attributes, stages, peaks)
    save_features(Path(a.out), col, ext, traces, {
        "tool": "a2a-leakcheck", "version": __version__, "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **_git(),
        "input": {"folder": str(Path(a.captures)), "vantage": a.vantage}, "attributes": attributes,
        "parameters": _extraction_parameters(a),
        "runtime": {"total_s": time.perf_counter() - t0, "stages_s": stages, "peak_rss_by_stage_mb": peaks,
                    "python": platform.python_version(), "platform": platform.platform()}})
    print(f"{ext['summary']['traces']} traces ({ext['summary']['empty_traces']} with nothing in view), "
          f"{ext['summary']['role_samples']} role samples → {a.out}")
    return 0


def _from_features(a: argparse.Namespace, attributes: list[str] | None, stages: dict) -> tuple:
    """Stage 3 input from `leakcheck extract`: the run must not ask for another view or extraction."""
    t = time.perf_counter()
    summary, ext, traces, meta = load_features(Path(a.captures))
    col = {"summary": summary}
    stages["features"] = time.perf_counter() - t
    saved = meta["parameters"]
    asked = {k: v for k, v in _extraction_parameters(a).items() if v}
    clash = [k for k, v in asked.items() if saved.get(k) != v]
    if a.vantage is not None and a.vantage != meta["input"]["vantage"]:
        clash.append(f"vantage {a.vantage} (extracted for {meta['input']['vantage']})")
    if clash:
        raise SystemExit(f"{a.captures} holds features extracted with other settings: {', '.join(clash)}; "
                         "drop those options or extract again")
    attributes = attributes if attributes is not None else meta["attributes"]
    have = set(meta["attributes"]) | {ROLE}
    if not set(attributes) <= have:
        raise SystemExit(f"not extracted: {', '.join(sorted(set(attributes) - have))} (have: {', '.join(meta['attributes'])})")
    return col, ext, traces, meta, attributes


def run(a: argparse.Namespace) -> int:
    t0 = time.perf_counter()
    stages: dict[str, float] = {}
    peaks: dict[str, dict] = {}                      # running peak memory at the end of each stage
    cfg = Config(margin=a.margin, n_splits=a.folds, n_boot=a.n_boot, permutations=a.permutations,
                 alpha=a.alpha, min_per_class=a.min_per_class, seed=a.seed, model=a.model,
                 null_model=a.null_model, jobs=a.jobs, perm_unit=a.perm_unit, perm_max=a.perm_max,
                 match_margin=a.match_margin)
    rules = load_rules(a.rules)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    require = [x.strip() for x in (a.require or "").split(",") if x.strip()]

    if is_features(Path(a.captures)):
        col, ext, traces, meta, attributes = _from_features(a, a.attributes and _attributes(a), stages)
        source = {"folder": meta["input"]["folder"], "features": str(Path(a.captures))}
        vantage, xparams = meta["input"]["vantage"], meta["parameters"]
    else:
        attributes = _attributes(a)
        col, ext, traces = _collect_extract(a, attributes, stages, peaks)
        source, vantage, xparams = {"folder": str(Path(a.captures))}, a.vantage, _extraction_parameters(a)

    ctx = context(traces, vantage)                   # for the rules only; not written to the report
    groups = np.array([tr.group for tr in traces])
    within = [x.strip() for x in a.role_within.split(",") if x.strip()]
    tops = np.array([tr.topology for tr in traces], dtype=object)
    for top in within:
        if not (tops == top).any():
            raise SystemExit(f"--role-within {top}: no trace has topology {top} "
                             f"(have: {', '.join(sorted({str(x) for x in tops}))})")
    tasks = attributes + [f"{ROLE_WITHIN}{top}" for top in within]   # role_within_* right after role
    if ROLE in attributes:
        i = attributes.index(ROLE) + 1
        tasks = attributes[:i] + tasks[len(attributes):] + attributes[i:]
    results, by_attr = {}, {}
    t = time.perf_counter()
    for attr in tasks:
        ta = time.perf_counter()
        logger.info("analysis: %s", attr)
        if attr == ROLE or attr.startswith(ROLE_WITHIN):
            keep = np.ones(len(ext["role_y"]), bool) if attr == ROLE else \
                tops[ext["role_trace"]] == attr[len(ROLE_WITHIN):]
            X, y, g = ext["role_X"][keep], ext["role_y"][keep], groups[ext["role_trace"][keep]]
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
        if attr.startswith(ROLE_WITHIN):
            r["within_topology"] = attr[len(ROLE_WITHIN):]
        r["mitigations"] = hints(facts(ROLE if attr.startswith(ROLE_WITHIN) else attr, r, ctx), rules)
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
        "input": {**source, "label": a.label, "vantage": vantage},
        "parameters": {"attributes": attributes, "role_within": within, "margin": cfg.margin,
                       "folds": cfg.n_splits, "n_boot": cfg.n_boot, "permutations": cfg.permutations,
                       "alpha": cfg.alpha,
                       "min_per_class": cfg.min_per_class, "seed": cfg.seed, "model": cfg.model,
                       "null_model": cfg.null_model, "jobs": cfg.jobs, "perm_unit": cfg.perm_unit,
                       "perm_max": cfg.perm_max, "perm_window": list(cfg.perm_window), "match_margin": cfg.match_margin,
                       "rules": str(a.rules or "default"), **xparams},
        "collection": col["summary"],
        "extraction": ext["summary"],
        "attributes": results,
        "summary": {v: [k for k, r in results.items() if r["verdict"] == v]
                    for v in ("LEAK", "NO LEAK", "INCONCLUSIVE")},
    }
    if a.baseline:
        report["diff"] = diff(report, json.loads(Path(a.baseline).read_text()), str(a.baseline))
    report["status"] = release_policy(report, report.get("diff"), a.fail_on_leak, a.strict, require)
    code = report["status"]["release_policy"]["exit_code"]

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
    for line in status_lines(report):
        if line:
            print(line.replace("**", ""))
    return code


def diff_cmd(a: argparse.Namespace) -> int:
    new, old = json.loads(Path(a.new).read_text()), json.loads(Path(a.baseline).read_text())
    d = diff(new, old, str(a.baseline))
    require = [x.strip() for x in (a.require or "").split(",") if x.strip()]
    st = release_policy(new, d, False, a.strict, require)
    if not d["compatible"]:
        print("not comparable with the baseline, verdicts not compared: "
              + "; ".join(f"{x['field']} {x['new']} vs {x['baseline']}" for x in d["incompatible"]))
    else:
        for x in d["changes"]:
            print(f"{x['attribute']}: {x['before']} → {x['after']}")
        if not d["changes"]:
            print("no verdict changed")
        for x in d["needs_review"]:
            print(f"needs review: {x['attribute']} (LEAK → {x['after']}, {x['reason']})")
        if d["new_leaks"]:
            print("new LEAK: " + ", ".join(d["new_leaks"]))
    for f in st["release_policy"]["failures"]:
        if f["check"] != "baseline":
            print(f"{f['check']}: {f['reason']}")
    return st["release_policy"]["exit_code"]


def _extraction_args(r: argparse.ArgumentParser) -> None:
    r.add_argument("--attributes", default=None,
                   help="comma-separated; role comes from agent_endpoints, others from sidecar keys (default "
                        "role,workflow,topology; for a features folder, the attributes it was extracted for)")
    r.add_argument("--strip", action="store_true",
                   help="analyse header-only copies of captures that still hold payload bytes")
    r.add_argument("--legacy-all-connections", action="store_true", dest="legacy_all_connections",
                   help="use every connection on the agent ports, not only those each capture opens "
                        "itself (the earlier measurement)")
    r.add_argument("--keep-retransmissions", action="store_true", dest="keep_retransmissions",
                   help="count retransmitted TCP segments again (default: every payload byte once)")
    r.add_argument("--cleartext", action="store_true",
                   help="the captures have no TLS: measure the first request from the first client byte instead of "
                        "after a TLS handshake (a sidecar can say so itself with \"tls\": false)")
    r.add_argument("--vantage", default=None,
                   help="observer view from the sidecars' vantages (e.g. v1, v2): keep only the flows of "
                        "the endpoints it sees; a trace with none in view stays, with all-zero features")


def _policy_args(r: argparse.ArgumentParser) -> None:
    r.add_argument("--strict", action="store_true",
                   help="release policy: exit 5 if any attribute is INCONCLUSIVE")
    r.add_argument("--require", default="", metavar="ATTR[,ATTR]",
                   help="release policy: exit 5 if a listed attribute is missing or INCONCLUSIVE")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="leakcheck", description="Do encrypted agent-to-agent captures leak "
                                "agent role, workflow or topology?",
                                epilog="exit codes: 0 done; 1 error; 2 a LEAK (--fail-on-leak); 3 a new LEAK against "
                                       "the baseline; 4 the baseline is not comparable; 5 --strict or --require failed")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="analyse a folder of header-only pcaps with label sidecars, or the features "
                                   "`extract` wrote")
    r.add_argument("captures", help="folder of *.pcap, each with a *.json label sidecar; or a features folder "
                                    "from `extract` (features.npz, features.json)")
    r.add_argument("--out", required=True, help="report folder (report.json, report.md[, report.html])")
    _extraction_args(r)
    r.add_argument("--role-within", default="", dest="role_within", metavar="TOPOLOGIES",
                   help="comma-separated topologies; for each, also score role on that topology's traces "
                        "only (attribute role_within_<topology>), next to the pooled role score. Use it "
                        "when the agents a capture sees depend on the topology, as at a gateway")
    r.add_argument("--margin", type=float, default=0.05, help="macro-F1 above chance that counts as a leak")
    r.add_argument("--permutations", type=int, default=99,
                   help="label permutations (0 = skip the test); 99 lets p reach 0.01")
    r.add_argument("--null-model", choices=["rf-light", "gbt", "rf", "same"], default="rf-light",
                   dest="null_model", help="model of the permutation test (scores real and permuted labels)")
    r.add_argument("--perm-unit", choices=["group", "sample"], default="group", dest="perm_unit",
                   help="permutation test: permute labels by prompt group (default; whole groups exchange labels, "
                        "or labels move within a group when they vary there) or over the samples (0.1.x)")
    r.add_argument("--perm-max", type=int, default=0, dest="perm_max",
                   help="if > --permutations and p falls in [0.02, 0.20], add permutations up to this many "
                        "(e.g. 999); off by default")
    r.add_argument("--match-margin", type=float, default=0.05, dest="match_margin",
                   help="attribution: a feature family matches all features when the upper bound of the paired "
                        "95%% CI of all − family is at most this")
    r.add_argument("--jobs", type=int, default=-1, help="parallel CV runs (-1: one per core)")
    r.add_argument("--alpha", type=float, default=0.05, help="permutation-test level a LEAK must pass")
    r.add_argument("--n-boot", type=int, default=1000, dest="n_boot", help="cluster-bootstrap resamples")
    r.add_argument("--min-per-class", type=int, default=20, dest="min_per_class")
    r.add_argument("--folds", type=int, default=5)
    r.add_argument("--model", choices=["gbt", "rf", "rf-light"], default="gbt")
    r.add_argument("--seed", type=int, default=42)
    r.add_argument("--rules", type=Path, default=None, help="rules YAML (default: a2a_leakcheck/rules.yaml)")
    r.add_argument("--html", action="store_true", help="also write report.html")
    r.add_argument("--label", default="", help="name for this run in the report")
    r.add_argument("--baseline", type=Path, default=None,
                   help="previous report.json: exit 3 if an attribute is newly LEAK, 4 if the baseline is not "
                        "comparable (another verdict rule, view, feature schema or attribute definition); a LEAK "
                        "that is now INCONCLUSIVE or missing is listed for review (exit 0)")
    r.add_argument("--fail-on-leak", action="store_true", dest="fail_on_leak", help="exit 2 on any LEAK")
    _policy_args(r)
    e = sub.add_parser("extract", help="collect and extract only: the header-only check and the features, for a "
                                       "later `run FEATURES_DIR`")
    e.add_argument("captures", help="folder of *.pcap, each with a *.json label sidecar")
    e.add_argument("--out", required=True, help="features folder (features.npz, features.json)")
    _extraction_args(e)
    d = sub.add_parser("diff", help="compare two reports: exit 3 on a new LEAK, 4 if they are not comparable; "
                                    "list a LEAK that is now INCONCLUSIVE or missing for review")
    d.add_argument("new")
    d.add_argument("baseline")
    _policy_args(d)
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for noisy in ("models", "features", "scapy"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    a = parser().parse_args(argv)
    return {"run": run, "extract": extract_cmd, "diff": diff_cmd}[a.cmd](a)
