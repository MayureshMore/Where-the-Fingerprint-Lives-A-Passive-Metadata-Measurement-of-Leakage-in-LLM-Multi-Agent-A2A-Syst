#!/usr/bin/env python3
"""
D1 (the TLS control) before and after counting every payload byte once: every D1 number paper 2 cites,
old against new.

Old: the results computed with retransmitted segments counted again, kept in
data/results/superseded/d1_before_dedup/. New: the same results with each payload byte counted once
(the default of a2a-leakcheck and, since Nov 14, of scripts/evaluate_tls_control.py), at their usual
paths. A result not rebuilt yet is shown as pending.

    audits      leakcheck/tls_control_{tls,clear}_own: verdict, macro-F1 [CI] and p per arm and attribute;
                permuted-label verdicts (false LEAKs out of 99 per attribute, totals); attribution
                (the first request alone, timing alone for role); traces; runtime and memory
    paired      tls_control_own: within-arm macro-F1 [CI], TLS − cleartext [CI] and whether its interval
                contains 0, cleartext → TLS transfer, on-wire bytes and packets per trace (TLS / cleartext)
    tool eval   paper2_tool_eval: recall, false-positive rate and precision per method; recall and
                false-positive rate at 20, 30 and 50 samples per class

Usage (never overwrites):
    python scripts/compare_d1_dedup.py --out data/results/d1_dedup_comparison
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from a2a_leakcheck.cli import _git  # noqa: E402

RES = Path("data/results")
OLD = RES / "superseded" / "d1_before_dedup"
ARMS = {"tls": "TLS", "clear": "cleartext"}
ATTRS = ("role", "workflow", "topology")


def load(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def f1ci(a: dict | None) -> list | None:
    return None if not a else [a.get("macro_f1"), a.get("ci_lo"), a.get("ci_hi")]


def audit_numbers(r: dict | None, arm: str) -> dict:
    if r is None:
        return {}
    out = {f"D1 {ARMS[arm]}: traces": r["extraction"]["traces"],
           f"D1 {ARMS[arm]}: runtime total (s)": r["runtime"]["total_s"],
           f"D1 {ARMS[arm]}: runtime analysis (s)": r["runtime"]["stages_s"]["analysis"],
           f"D1 {ARMS[arm]}: peak memory per worker (MB)": r["runtime"]["peak_rss_children_mb"]}
    for attr in ATTRS:
        a = r["attributes"][attr]
        perm = a["validation"].get("permutation") or {}
        nv = perm.get("null_verdicts") or {}
        out[f"D1 {ARMS[arm]} {attr}: verdict"] = a["verdict"]
        out[f"D1 {ARMS[arm]} {attr}: macro-F1 [CI]"] = f1ci(a["analysis"])
        out[f"D1 {ARMS[arm]} {attr}: p"] = perm.get("p_value")
        out[f"D1 {ARMS[arm]} {attr}: permuted LEAK / INCONCLUSIVE of {perm.get('permutations')}"] = \
            [nv.get("LEAK", 0), nv.get("INCONCLUSIVE", 0)]
        at = a.get("attribution") or {}
        single = at.get("single_request_size") or {}
        if attr == "workflow":
            out[f"D1 {ARMS[arm]} workflow: first request alone, macro-F1 [CI]"] = f1ci(single)
            out[f"D1 {ARMS[arm]} workflow: first request alone matches all"] = single.get("matches_all")
            if single.get("macro_f1") is not None:
                out[f"D1 {ARMS[arm]} workflow: all − first request alone"] = a["analysis"]["macro_f1"] - single["macro_f1"]
        if attr == "role":
            out[f"D1 {ARMS[arm]} role: timing alone, macro-F1 [CI]"] = f1ci((at.get("families") or {}).get("timing"))
    return out


def totals(rs: list[dict | None]) -> dict:
    if any(r is None for r in rs):
        return {}
    k = [0, 0, 0]
    for r in rs:
        for attr in ATTRS:
            p = r["attributes"][attr]["validation"].get("permutation") or {}
            nv = p.get("null_verdicts") or {}
            k[0] += nv.get("LEAK", 0); k[1] += nv.get("INCONCLUSIVE", 0); k[2] += p.get("permutations", 0)
    return {"D1 both arms: permuted-label LEAK / INCONCLUSIVE / runs": k}


def paired_numbers(t: dict | None) -> dict:
    if t is None:
        return {}
    out = {"tls_control_own: retransmissions": t.get("retransmissions", "kept (before Nov 14)")}
    for attr in ATTRS:
        r = t["results"][attr]
        d = r["tls_minus_clear"]
        out[f"{attr}: within cleartext, macro-F1 [CI]"] = f1ci(r["within_clear"])
        out[f"{attr}: within TLS, macro-F1 [CI]"] = f1ci(r["within_tls"])
        out[f"{attr}: TLS − cleartext [CI]"] = [d["diff"], d["ci_lo"], d["ci_hi"]]
        out[f"{attr}: TLS − cleartext interval contains 0 (not significant)"] = d["ci_lo"] <= 0 <= d["ci_hi"]
        out[f"{attr}: shared prompt groups"] = d.get("shared_groups")
        out[f"{attr}: cleartext → TLS, macro-F1 [CI]"] = f1ci(r["clear_to_tls"])
    o = t.get("overhead") or {}
    out["on-wire bytes per trace, TLS / cleartext"] = o.get("bytes_ratio")
    out["on-wire packets per trace, TLS / cleartext"] = o.get("packets_ratio")
    return out


def tool_eval_numbers(e: dict | None) -> dict:
    if e is None:
        return {}
    out = {}
    for m, r in e["summary"]["full_data"].items():
        out[f"tool eval {m}: recall (TP of known leaks)"] = [r["recall"], r["true_positives"], r["known_leaks"]]
        out[f"tool eval {m}: false-positive rate (FP of known non-leaks)"] = [r["false_positive_rate"], r["false_positives"],
                                                                             r["known_non_leaks"]]
        out[f"tool eval {m}: precision"] = r["precision"]
    for n in ("20", "30", "50"):
        r = e["summary"]["sample_size"].get(n) or {}
        r = r.get("leakcheck", r)
        out[f"tool eval sample size {n}: recall [CI]"] = [r.get("recall"), *(r.get("recall_ci") or [None, None])]
        out[f"tool eval sample size {n}: false-positive rate"] = r.get("false_positive_rate")
    return out


def numbers(root: Path) -> dict:
    out = {}
    for arm in ARMS:
        out.update(audit_numbers(load(root / "leakcheck" / f"tls_control_{arm}_own" / "report.json"), arm))
    out.update(totals([load(root / "leakcheck" / f"tls_control_{arm}_own" / "report.json") for arm in ARMS]))
    out.update(paired_numbers(load(root / "tls_control_own.json")))
    out.update(tool_eval_numbers(load(root / "paper2_tool_eval.json")))
    return out


def fmt(v) -> str:
    if v is None:
        return "pending"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:.4f}"
    if isinstance(v, list):
        if len(v) == 3 and all(isinstance(x, float) for x in v):
            return f"{v[0]:.4f} [{v[1]:.4f}, {v[2]:.4f}]"
        return " / ".join(fmt(x) for x in v)
    return str(v)


def compare(old: dict, new: dict) -> list[dict]:
    rows = []
    for k in list(old) + [k for k in new if k not in old]:
        o, n = old.get(k), new.get(k)
        rows.append({"number": k, "old": o, "new": n, "same": None if n is None or o is None else fmt(o) == fmt(n)})
    return rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--old", default=str(OLD))
    p.add_argument("--new", default=str(RES))
    p.add_argument("--out", default=None, help="path stem for .json and .md (not overwritten)")
    a = p.parse_args(argv)
    old, new = numbers(Path(a.old)), numbers(Path(a.new))
    if not old:
        raise SystemExit(f"nothing under {a.old}")
    rows = compare(old, new)
    paired = {attr: new.get(f"{attr}: TLS − cleartext interval contains 0 (not significant)") for attr in ATTRS}
    out = {"paper": "P2", "collection_id": "TLS control", **_git(), "old": a.old, "new": a.new,
           "paired_difference_not_significant": paired, "rows": rows}
    md = ["# D1 before and after counting every payload byte once", "",
          f"Old: `{a.old}` (retransmitted segments counted again). New: `{a.new}` (each payload byte once). "
          "Pending: not rebuilt yet.", "",
          "Paired TLS − cleartext difference still not significant (interval contains 0): "
          + ", ".join(f"{k} {fmt(v)}" for k, v in paired.items()) + ".", "",
          "| Number | Old | New | Same |", "|---|---|---|---|"]
    md += [f"| {r['number']} | {fmt(r['old'])} | {fmt(r['new'])} | {fmt(r['same']) if r['same'] is not None else '—'} |"
           for r in rows]
    text = "\n".join(md) + "\n"
    print(text)
    if a.out:
        for ext, body in ((".json", json.dumps(out, indent=2, default=str) + "\n"), (".md", text)):
            f = Path(a.out + ext)
            if f.exists():
                raise SystemExit(f"{f} exists: not overwritten")
            f.write_text(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
