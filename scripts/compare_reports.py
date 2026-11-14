#!/usr/bin/env python3
"""
Compare two a2a-leakcheck reports field by field: are the results the same?

Compared exactly (or within --tol for numbers): every attribute's verdict, reason, classes, sample
counts, macro-F1 and interval, permutation test, severity, attribution, and the mitigation hints
(unless --ignore-hints); the collection and extraction summaries apart from folder paths; the
analysis parameters apart from --jobs and the rules path. Not compared, but listed side by side:
runtime per stage, peak memory, workers, platform, commit and date.

Uses:
  - the same audit on two machines (the Pi against the Mac): everything must match;
  - the same audit at two commits that changed only the rules: --ignore-hints, and the hints that
    changed are listed.

Exit code 0 when everything compared matches, 1 otherwise.

Usage:
    python scripts/compare_reports.py PI/report.json MAC/report.json
    python scripts/compare_reports.py NEW/report.json OLD/report.json --ignore-hints
    python scripts/compare_reports.py NEW/report.json OLD/report.json --ignore-hints --json OUT.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

NOT_COMPARED = {"parameters": {"jobs", "rules"}, "collection": {"folder"}, "input": {"folder", "label"}}


def walk(a, b, path: str, tol: float, skip: set[str], out: list) -> None:
    if path.rsplit(".", 1)[-1] in skip:
        return
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                if k not in skip:
                    out.append({"field": f"{path}.{k}", "a": a.get(k, "<absent>"), "b": b.get(k, "<absent>")})
                continue
            walk(a[k], b[k], f"{path}.{k}", tol, skip, out)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            walk(x, y, f"{path}[{i}]", tol, skip, out)
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        if abs(a - b) > tol:
            out.append({"field": path, "a": a, "b": b})
    elif a != b:
        out.append({"field": path, "a": a, "b": b})


def compare(a: dict, b: dict, tol: float = 0.0, ignore_hints: bool = False) -> dict:
    diffs: list = []
    skip = {"mitigations"} if ignore_hints else set()
    for section in ("attributes", "summary", "extraction", "collection", "parameters", "input"):
        x, y = a.get(section, {}), b.get(section, {})
        if section in NOT_COMPARED:
            x = {k: v for k, v in x.items() if k not in NOT_COMPARED[section]}
            y = {k: v for k, v in y.items() if k not in NOT_COMPARED[section]}
        walk(x, y, section, tol, skip, diffs)
    hints = {}
    for attr in sorted(set(a.get("attributes", {})) | set(b.get("attributes", {}))):
        ha = [m["id"] for m in a.get("attributes", {}).get(attr, {}).get("mitigations", [])]
        hb = [m["id"] for m in b.get("attributes", {}).get(attr, {}).get("mitigations", [])]
        if ha != hb:
            hints[attr] = {"a": ha, "b": hb}
    side = {}
    for name, r in (("a", a), ("b", b)):
        rt = r.get("runtime", {})
        side[name] = {"commit": r.get("git_commit"), "dirty": r.get("git_dirty"), "created": r.get("created"),
                      "total_s": rt.get("total_s"), "stages_s": rt.get("stages_s"),
                      "peak_rss_mb": rt.get("peak_rss_mb"), "peak_rss_children_mb": rt.get("peak_rss_children_mb"),
                      "workers": rt.get("workers"), "python": rt.get("python"), "platform": rt.get("platform")}
    rows = []
    for attr, r in a.get("attributes", {}).items():
        o = b.get("attributes", {}).get(attr, {})
        rows.append({"attribute": attr, "verdict": [r.get("verdict"), o.get("verdict")],
                     "macro_f1": [(r.get("analysis") or {}).get("macro_f1"), (o.get("analysis") or {}).get("macro_f1")],
                     "p": [(r["validation"].get("permutation") or {}).get("p_value"),
                           (o.get("validation", {}).get("permutation") or {}).get("p_value")]})
    return {"same": not diffs, "differences": diffs, "hints_changed": hints, "attributes": rows, "runtime": side}


def fmt(x) -> str:
    return "—" if x is None else f"{x:.4f}" if isinstance(x, float) else str(x)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("a", help="report.json (e.g. the new run, or the Pi's)")
    p.add_argument("b", help="report.json to compare against (e.g. the committed one, or the Mac's)")
    p.add_argument("--tol", type=float, default=0.0, help="allowed absolute difference for numbers (default 0)")
    p.add_argument("--ignore-hints", action="store_true", dest="ignore_hints",
                   help="do not count changed mitigation hints as a difference (they are still listed)")
    p.add_argument("--json", default=None, help="also write the comparison here")
    a = p.parse_args(argv)
    ra, rb = json.loads(Path(a.a).read_text()), json.loads(Path(a.b).read_text())
    c = compare(ra, rb, a.tol, a.ignore_hints)
    c["files"] = {"a": a.a, "b": a.b}
    print(f"a: {a.a}\nb: {a.b}\n")
    print("| attribute | verdict a | verdict b | macro-F1 a | macro-F1 b | p a | p b |")
    print("|---|---|---|---|---|---|---|")
    for r in c["attributes"]:
        print(f"| {r['attribute']} | {r['verdict'][0]} | {r['verdict'][1]} | {fmt(r['macro_f1'][0])} | "
              f"{fmt(r['macro_f1'][1])} | {fmt(r['p'][0])} | {fmt(r['p'][1])} |")
    print()
    if c["same"]:
        print("every compared field matches" + (" (hints not compared)" if a.ignore_hints else ""))
    else:
        print(f"{len(c['differences'])} fields differ:")
        for d in c["differences"][:40]:
            print(f"  {d['field']}: {json.dumps(d['a'])[:120]}  vs  {json.dumps(d['b'])[:120]}")
    for attr, h in c["hints_changed"].items():
        print(f"hints {attr}: {h['b']} → {h['a']}")
    print()
    for name in ("a", "b"):
        s = c["runtime"][name]
        st = ", ".join(f"{k} {v:.1f} s" for k, v in (s["stages_s"] or {}).items())
        print(f"runtime {name}: {fmt(s['total_s'])} s ({st}); peak memory main {fmt(s['peak_rss_mb'])} MB, "
              f"workers {fmt(s['peak_rss_children_mb'])} MB; {s['workers']} workers; Python {s['python']}; "
              f"{s['platform']}; commit {str(s['commit'])[:8]}{' (dirty)' if s['dirty'] else ''}")
    if a.json:
        Path(a.json).write_text(json.dumps(c, indent=2) + "\n")
    return 0 if c["same"] else 1


if __name__ == "__main__":
    sys.exit(main())
