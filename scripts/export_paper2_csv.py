#!/usr/bin/env python3
"""
Export paper 2's plotted numbers as CSV for pgfplots (the paper draws its own figures; no PNG).

Inputs (committed results; a missing one is skipped with a note):
    data/results/paper2_tool_eval.json         D1, the TLS control (both arms)
    data/results/paper2_tool_eval_c2.json      D2, C2 (three arms × two views)
    data/results/leakcheck/<name>/report.json  the audits: tls_control_{clear,tls}_own, c2_<arm>_<view>
    data/results/leakcheck_pi/<name>/report.json  the same audit on the Raspberry Pi, if present

Outputs, one row per value, long format (filter with pgfplots' `discard if not`); missing values
are `nan` (use `unbounded coords=discard`):
    verdicts.csv             dataset, cell, attribute, method, verdict, macro_f1, ci_lo, ci_hi, p, n, groups, carried_by
    permuted.csv             dataset, cell, attribute, method, runs, leak, inconclusive, no_leak
    sample_size.csv          dataset, cell, attribute, n_per_class, full_verdict, real_* and permuted_* verdict counts
    sample_size_summary.csv  dataset, n_per_class, recall [CI], false-positive rate [CI], coverage [CI] (D2)
    families.csv             dataset, report, attribute, family, macro_f1, ci_lo, ci_hi, matches_all, top
    pair.csv                 D2: cell, features (all | timing), dims, verdict, macro_f1, ci_lo, ci_hi, p
    input_size.csv           D2: cell, estimator, class (all | task type), n, median_abs_error, mae, p90, within_*B
    runtime.csv              machine, report, traces, attributes, total_s, extraction_s, analysis_s, peak_rss_mb,
                             peak_rss_children_mb, workers, platform

Usage (never overwrites: OUT must not exist):
    python scripts/export_paper2_csv.py --out data/results/paper2_csv
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from a2a_leakcheck.cli import _git  # noqa: E402

RESULTS = Path("data/results")
EVALS = {"D1": "paper2_tool_eval.json", "D2": "paper2_tool_eval_c2.json"}
REPORTS = {"D1": ["tls_control_clear_own", "tls_control_tls_own"],
           "D2": [f"c2_{a}_{v}" for a in ("lan", "lan_pad", "lan_padmax") for v in ("v1", "v2")]}
VERDICTS = ("LEAK", "INCONCLUSIVE", "NO LEAK")
NAN = "nan"


def num(x):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return NAN
    if isinstance(x, bool):
        return int(x)
    if isinstance(x, float):
        return f"{x:.6g}"
    return x


def cnt(d: dict, v: str) -> int:
    return int((d or {}).get(v, 0))


def write(path: Path, header: list[str], rows: list[list]) -> int:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow([num(x) for x in r])
    return len(rows)


def from_eval(ds: str, ev: dict, t: dict) -> None:
    for cell, arm in ev["arms"].items():
        for attr, r in arm["attributes"].items():
            for m, f in r["full"].items():
                ci = f.get("ci") or [None, None]
                t["verdicts"].append([ds, cell, attr, m, f["verdict"], f.get("macro_f1"), ci[0], ci[1], f.get("p"),
                                      f.get("n"), f.get("groups"), f.get("carried_by") if m == "leakcheck" else None])
            for m, vs in r["permuted"].items():
                t["permuted"].append([ds, cell, attr, m, len(vs), *(vs.count(v) for v in VERDICTS)])
            full_v = r["full"]["leakcheck"]["verdict"]
            for n, s in sorted(r["sample_size"].items(), key=lambda kv: int(kv[0])):
                t["sample_size"].append([ds, cell, attr, int(n), full_v, *(cnt(s["real"], v) for v in VERDICTS),
                                         *(cnt(s.get("permuted"), v) for v in VERDICTS)])
        if "pair" in arm:
            p = arm["pair"]
            for k in ("all", "timing"):
                x = p[k]
                t["pair"].append([ds, cell, p["attribute"], "/".join(p["classes"]), k, p["dims"][k], x["verdict"],
                                  x["macro_f1"], x["ci"][0], x["ci"][1], x["p"], x["n"]])
        if "input_size" in arm:
            for e, x in arm["input_size"]["estimators"].items():
                for cls, s in [("all", x["overall"]), *sorted(x["per_class"].items())]:
                    t["input_size"].append([ds, cell, e, cls, s["n"], s["median_abs_error"], s["mae"], s["p90_abs_error"],
                                            s["within_100B"], s["within_200B"], s["within_300B"],
                                            s["median_relative_error"], s["median_signed_error"]])
    summ = ev["summary"]
    cov = summ.get("coverage") or {}
    for n, s in sorted(summ["sample_size"].items(), key=lambda kv: int(kv[0])):
        lk = s.get("leakcheck", s)                    # per method in some versions; flat in others
        c = (cov.get(n) or {}).get("all") or {}
        t["sample_size_summary"].append(
            [ds, int(n), lk.get("recall"), *(lk.get("recall_ci") or [None, None]),
             lk.get("false_positive_rate"), *(lk.get("false_positive_rate_ci") or [None, None]),
             lk.get("agreement_with_full_mean"), c.get("share"), *(c.get("ci") or [None, None])])


def from_report(ds: str, name: str, machine: str, rep: dict, t: dict) -> None:
    rt = rep.get("runtime", {})
    st = rt.get("stages_s", {})
    t["runtime"].append([machine, name, rep["extraction"]["traces"], len(rep["attributes"]), rt.get("total_s"),
                         st.get("extraction"), st.get("analysis"), rt.get("peak_rss_mb"),
                         rt.get("peak_rss_children_mb"), rt.get("workers"), rt.get("platform")])
    if machine != "laptop":
        return
    for attr, r in rep["attributes"].items():
        at = r.get("attribution") or {}
        top = at.get("top_family")
        for fam, v in (at.get("families") or {}).items():
            t["families"].append([ds, name, attr, fam, v["macro_f1"], v["ci_lo"], v["ci_hi"],
                                  v["all_minus_this"]["ci_lo"] <= 0, fam == top])
        s = at.get("single_request_size")
        if s:
            t["families"].append([ds, name, attr, "first_request_size", s["macro_f1"], s["ci_lo"], s["ci_hi"],
                                  s["matches_all"], False])
        an = r.get("analysis") or {}
        t["families"].append([ds, name, attr, "all", an.get("macro_f1"), an.get("ci_lo"), an.get("ci_hi"), True, False])


HEADERS = {
    "verdicts": ["dataset", "cell", "attribute", "method", "verdict", "macro_f1", "ci_lo", "ci_hi", "p", "n", "groups",
                 "carried_by"],
    "permuted": ["dataset", "cell", "attribute", "method", "runs", "leak", "inconclusive", "no_leak"],
    "sample_size": ["dataset", "cell", "attribute", "n_per_class", "full_verdict", "real_leak", "real_inconclusive",
                    "real_no_leak", "permuted_leak", "permuted_inconclusive", "permuted_no_leak"],
    "sample_size_summary": ["dataset", "n_per_class", "recall", "recall_ci_lo", "recall_ci_hi", "fpr", "fpr_ci_lo",
                            "fpr_ci_hi", "agreement_with_full", "coverage", "coverage_ci_lo", "coverage_ci_hi"],
    "families": ["dataset", "report", "attribute", "family", "macro_f1", "ci_lo", "ci_hi", "matches_all", "top"],
    "pair": ["dataset", "cell", "attribute", "classes", "features", "dims", "verdict", "macro_f1", "ci_lo", "ci_hi",
             "p", "n"],
    "input_size": ["dataset", "cell", "estimator", "class", "n", "median_abs_error", "mae", "p90_abs_error",
                   "within_100B", "within_200B", "within_300B", "median_relative_error", "median_signed_error"],
    "runtime": ["machine", "report", "traces", "attributes", "total_s", "extraction_s", "analysis_s", "peak_rss_mb",
                "peak_rss_children_mb", "workers", "platform"],
}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--results", default=str(RESULTS), help="results folder (default data/results)")
    p.add_argument("--out", required=True, help="new folder for the CSVs (must not exist)")
    a = p.parse_args(argv)
    res, out = Path(a.results), Path(a.out)
    if out.exists():
        raise SystemExit(f"{out} exists: never overwritten; pick a new --out")
    t: dict[str, list] = {k: [] for k in HEADERS}
    sources = []
    for ds, f in EVALS.items():
        path = res / f
        if not path.exists():
            print(f"skip {ds}: {path} not found")
            continue
        ev = json.loads(path.read_text())
        from_eval(ds, ev, t)
        sources.append({"file": str(path), "git_commit": ev.get("git_commit"), "git_dirty": ev.get("git_dirty")})
    for ds, names in REPORTS.items():
        for machine, folder in (("laptop", "leakcheck"), ("pi", "leakcheck_pi")):
            for name in names:
                path = res / folder / name / "report.json"
                if path.exists():
                    rep = json.loads(path.read_text())
                    from_report(ds, name, machine, rep, t)
                    sources.append({"file": str(path), "git_commit": rep.get("git_commit"),
                                    "git_dirty": rep.get("git_dirty")})
                elif machine == "laptop":
                    print(f"skip {path}: not found")
    out.mkdir(parents=True)
    for k, header in HEADERS.items():
        print(f"{k}.csv: {write(out / f'{k}.csv', header, t[k])} rows")
    (out / "sources.json").write_text(json.dumps({"paper": "P2", **_git(), "inputs": sources}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
