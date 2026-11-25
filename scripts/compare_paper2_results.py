#!/usr/bin/env python3
"""
Compare a rebuilt paper 2 result with the committed one (scripts/reproduce_paper2.sh).

Three kinds of file:
  report      an a2a-leakcheck report.json: per attribute the verdict, macro-F1 and its interval and the
              permutation test's p; for a committed report from 0.3.0 on, also each feature family's
              macro-F1, interval and "matches all" (the earlier rule's attribution is not comparable)
  tool eval   paper2_tool_eval*.json: the summary, and per arm and attribute the verdicts of the full
              data, the permuted draws and the sample sizes; C2's pair and input-size parts
  any other   every field, recursively, except what measures the run rather than the data: dates,
              commits, run times, memory, the machine, and file paths (a rebuilt file points into the
              sandbox), and labels a script began to write after the committed file was made. The
              permutation null model's mean (null_mean) within 0.01, as tests/test_examples.py
              allows: the rf-light null model fits slightly differently across platforms (A6).

Numbers are equal within 1e-9. With --sections, only those sections of a paper2_round2.py output are
compared (a part such as a3,a8,a9 against the merged paper2_round2.json).

Exit code 0 when everything compared matches, 1 otherwise; each differing field is printed.

Usage:
    python scripts/compare_paper2_results.py NEW.json COMMITTED.json
    python scripts/compare_paper2_results.py SANDBOX/round2_parts/fast.json data/results/paper2_round2.json --sections a3,a8,a9
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RUN_KEYS = {
    "created", "git_commit", "git_dirty", "merge_commit", "merge_dirty", "evaluation_commit", "evaluation_dirty",
    "runtime", "runtime_s", "seconds", "seconds_median", "seconds_baseline", "collect_s", "kfp_features_s", "cv_s",
    "pi_estimate_s", "runtime_task_type", "environment", "python", "platform", "machine", "cpu_count",
    "LOKY_MAX_CPU_COUNT", "peak_rss_mb", "peak_rss_children_mb", "workers", "jobs", "parts", "tool",
    "tool_report_commits",      # paper2_review.json: the commit of the reports it read
    "title",                    # b1_audits.py's label (--title, since 8c227411): not in the files made before it
}
PATH_PREFIXES = ("data/", "examples/", "logs/", "dist/", "/")
TOLERANCE = {"null_mean": 0.01}
EPS = 1e-9


def _is_path(x) -> bool:
    return isinstance(x, str) and x.startswith(PATH_PREFIXES)


def walk(a, b, path: str, out: list) -> None:
    key = path.rsplit(".", 1)[-1].split("[", 1)[0]
    if key in RUN_KEYS:
        return
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k in RUN_KEYS:
                continue
            if k not in a or k not in b:
                if not (_is_path(a.get(k)) or _is_path(b.get(k))):
                    out.append((f"{path}.{k}", a.get(k, "<absent>"), b.get(k, "<absent>")))
                continue
            walk(a[k], b[k], f"{path}.{k}", out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append((path, f"{len(a)} items", f"{len(b)} items"))
            return
        for i, (x, y) in enumerate(zip(a, b)):
            walk(x, y, f"{path}[{i}]", out)
    elif isinstance(a, bool) or isinstance(b, bool):
        if a != b:
            out.append((path, a, b))
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if abs(a - b) > TOLERANCE.get(key, EPS):
            out.append((path, a, b))
    elif _is_path(a) and _is_path(b):
        return
    elif a != b:
        out.append((path, a, b))


def pick_report(r: dict, families: bool) -> dict:
    out = {}
    for k, a in r["attributes"].items():
        an, perm = a.get("analysis") or {}, a["validation"].get("permutation") or {}
        out[k] = {"verdict": a["verdict"], "macro_f1": an.get("macro_f1"), "ci": [an.get("ci_lo"), an.get("ci_hi")],
                  "p": perm.get("p_value")}
        fams = (a.get("attribution") or {}).get("families") or {}
        if families and fams:
            out[k]["families"] = {f: {x: v.get(x) for x in ("macro_f1", "ci_lo", "ci_hi", "matches_all")}
                                  for f, v in fams.items()}
    return out


def pick_eval(r: dict) -> dict:
    out = {"summary": r["summary"]}
    for an, arm in r["arms"].items():
        for k, a in arm["attributes"].items():
            out[f"{an}/{k}"] = {"full": {m: v["verdict"] for m, v in a["full"].items()}, "permuted": a["permuted"],
                                "sample_size": a["sample_size"]}
        for part in ("pair", "input_size"):              # C2's extras, per cell
            if part in arm:
                out[f"{an}/{part}"] = arm[part]
    return out


def kind(r: dict) -> str:
    if "arms" in r and "summary" in r and all("attributes" in a for a in r["arms"].values()):
        return "tool eval"
    if "attributes" in r and r.get("tool") == "a2a-leakcheck":
        return "report"
    return "any other"


def compare(new: dict, old: dict, sections: list[str] | None = None) -> list[tuple]:
    """[(field, new, committed)] for every field that differs."""
    out: list = []
    if sections:
        for s in sections:
            walk(new.get("sections", {}).get(s), old.get("sections", {}).get(s), f"sections.{s}", out)
        return out
    k = kind(old)
    if k == "report":
        fam = "perm_unit" in old.get("parameters", {})       # 0.3.0 on: the non-inferiority rule
        walk(pick_report(new, fam), pick_report(old, fam), "attributes", out)
    elif k == "tool eval":
        walk(pick_eval(new), pick_eval(old), "eval", out)
    else:
        walk(new, old, "", out)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("new", type=Path)
    p.add_argument("committed", type=Path)
    p.add_argument("--sections", default="", help="paper2_round2: compare only these sections")
    p.add_argument("--show", type=int, default=8, help="differing fields to print")
    a = p.parse_args(argv)
    new, old = (json.loads(x.read_text()) for x in (a.new, a.committed))
    diffs = compare(new, old, [s for s in a.sections.split(",") if s] or None)
    name = f"{a.committed.parent.name}/{a.committed.name}" if a.committed.name == "report.json" else a.committed.name
    label = name + (f" ({a.sections})" if a.sections else "")
    if not diffs:
        print(f"  {label:52s} same")
        return 0
    print(f"  {label:52s} DIFFERENT ({len(diffs)} fields)")
    for f, x, y in diffs[:a.show]:
        print(f"      {f}: rebuilt {json.dumps(x, default=str)[:80]}, committed {json.dumps(y, default=str)[:80]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
