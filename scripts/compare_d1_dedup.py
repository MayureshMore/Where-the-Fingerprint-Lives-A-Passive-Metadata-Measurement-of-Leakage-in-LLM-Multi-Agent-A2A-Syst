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
    retransmissions  per arm, from the captures (no model): the TCP segments that counting each byte once
                drops (features/kfp.py is_retransmission, on each trace's own agent connections),
                their payload sizes and direction, how many come after their connection's last packet
                with new data, partial retransmissions, and the count per workflow and per topology
                with a chi-square test (traces with at least one, by class) and a Kruskal-Wallis test
                (retransmissions per trace, by class)

Usage (never overwrites):
    python scripts/compare_d1_dedup.py --out data/results/d1_dedup_comparison
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

from scipy.stats import chi2_contingency, kruskal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from a2a_leakcheck.cli import _git  # noqa: E402
from features.connections import opened_connections  # noqa: E402
from features.kfp import duplicate_bytes, is_retransmission, tcp_records  # noqa: E402

RES = Path("data/results")
OLD = RES / "superseded" / "d1_before_dedup"
ARMS = {"tls": "TLS", "clear": "cleartext"}
ATTRS = ("role", "workflow", "topology")
RAW = {"tls": "raw_tlspair_tls", "clear": "raw_tlspair_clear"}
SIZE_BINS = ((0, 100), (101, 1000), (1001, None))


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


def trace_retransmissions(pcap: Path, servers: set[int]) -> dict:
    """One capture: the retransmitted segments on its own agent connections (what dedup drops)."""
    recs = [r for r in tcp_records(pcap) if r[1] in servers or r[2] in servers]
    opened = opened_connections([r[:6] for r in recs], servers)           # own connections, as the features
    recs = [r for r in recs if (r[1], r[2]) in opened or (r[2], r[1]) in opened]
    dups = duplicate_bytes(recs)
    conn = lambda r: (min(r[1], r[2]), max(r[1], r[2]))  # noqa: E731  one connection, both directions
    last_new: dict = {}
    for r, d in zip(recs, dups):
        if r[4] > d:                                 # carries at least one new payload byte
            last_new[conn(r)] = max(last_new.get(conn(r), r[0]), r[0])
    out = {"segments": 0, "sizes": [], "requests": 0, "after_last_data": 0, "partial": 0, "bytes_dropped": 0,
           "payload_bytes": sum(r[4] - d for r, d in zip(recs, dups))}
    for r, d in zip(recs, dups):
        if is_retransmission(r, d):
            out["segments"] += 1
            out["sizes"].append(r[4])
            out["bytes_dropped"] += r[4]
            out["requests"] += r[2] in servers
            out["after_last_data"] += r[0] > last_new.get(conn(r), float("inf"))
        elif 0 < d < r[4]:
            out["partial"] += 1
            out["bytes_dropped"] += d
    return out


def by_class(rows: list[dict], key: str) -> dict:
    """Retransmissions per class of key: counts, a chi-square test on traces with at least one (by
    class) and a Kruskal-Wallis test on retransmissions per trace (by class)."""
    classes = sorted({r[key] for r in rows})
    per = {c: [r["segments"] for r in rows if r[key] == c] for c in classes}
    table = [[sum(n > 0 for n in v), sum(n == 0 for n in v)] for v in per.values()]
    out = {"classes": {c: {"traces": len(v), "traces_with_retransmissions": sum(n > 0 for n in v),
                           "segments": sum(v), "per_trace_mean": sum(v) / len(v)} for c, v in per.items()}}
    if len(classes) > 1 and all(sum(col) > 0 for col in zip(*table)):
        chi2, p, dof, _ = chi2_contingency(table)
        out["chi_square_traces_with_any"] = {"chi2": float(chi2), "dof": int(dof), "p": float(p)}
    else:
        out["chi_square_traces_with_any"] = None
    vals = list(per.values())
    if len(vals) > 1 and len({n for v in vals for n in v}) > 1:
        h, p = kruskal(*vals)
        out["kruskal_per_trace"] = {"H": float(h), "p": float(p)}
    else:
        out["kruskal_per_trace"] = None
    return out


def retransmissions(raw: Path) -> dict | None:
    """Per arm: what counting each payload byte once drops, and whether it depends on the workflow."""
    if not raw.is_dir():
        return None
    rows, sizes, tot = [], [], Counter()
    for pcap in sorted(raw.glob("*.pcap")):
        sc = json.loads(pcap.with_suffix(".json").read_text())
        if sc.get("success") is False:
            continue
        servers = {int(str(v).rsplit(":", 1)[1]) for v in sc["agent_endpoints"].values()}
        t = trace_retransmissions(pcap, servers)
        sizes += t.pop("sizes")
        tot.update(t)
        rows.append({"workflow": sc.get("workflow_class"), "topology": sc.get("topology"), "segments": t["segments"]})
    bins = {f"{lo}-{hi} B" if hi else f">{lo - 1} B": sum(lo <= x and (hi is None or x <= hi) for x in sizes)
            for lo, hi in SIZE_BINS}
    return {"traces": len(rows), "traces_with_retransmissions": sum(r["segments"] > 0 for r in rows),
            "segments": tot["segments"], "requests": tot["requests"], "responses": tot["segments"] - tot["requests"],
            "after_last_data": tot["after_last_data"], "partial": tot["partial"],
            "bytes_dropped": tot["bytes_dropped"], "payload_bytes": tot["payload_bytes"],
            "payload_size": {"min": min(sizes), "median": statistics.median(sizes), "max": max(sizes),
                             "bins": bins} if sizes else None,
            "per_workflow": by_class(rows, "workflow"), "per_topology": by_class(rows, "topology")}


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


def retx_markdown(retx: dict) -> list[str]:
    arms = [a for a in ARMS if retx.get(a)]
    if not arms:
        return []
    r = {a: retx[a] for a in arms}
    pct = lambda a: 100 * r[a]["bytes_dropped"] / r[a]["payload_bytes"] if r[a]["payload_bytes"] else 0.0  # noqa: E731
    size = lambda a, k: "—" if not r[a]["payload_size"] else f"{r[a]['payload_size'][k]:,.0f}"  # noqa: E731
    L = ["", "## TCP retransmissions in each arm (what counting each byte once drops)", "",
         "Each trace's own agent connections; a retransmission carries no new payload byte (features/kfp.py).", "",
         "| | " + " | ".join(ARMS[a] for a in arms) + " |", "|---|" + "---|" * len(arms)]
    rows = [("traces", lambda a: f"{r[a]['traces']}"),
            ("traces with at least one", lambda a: f"{r[a]['traces_with_retransmissions']}"),
            ("retransmitted segments", lambda a: f"{r[a]['segments']}"),
            ("of which requests / responses", lambda a: f"{r[a]['requests']} / {r[a]['responses']}"),
            ("after their connection's last data packet", lambda a: f"{r[a]['after_last_data']}"),
            ("partial retransmissions (only the new bytes kept)", lambda a: f"{r[a]['partial']}"),
            ("payload bytes dropped (share of all payload)", lambda a: f"{r[a]['bytes_dropped']:,} ({pct(a):.2f}%)"),
            ("payload size min / median / max (B)", lambda a: f"{size(a, 'min')} / {size(a, 'median')} / {size(a, 'max')}")]
    for label, f in rows:
        L.append(f"| {label} | " + " | ".join(f(a) for a in arms) + " |")
    if any(r[a]["payload_size"] for a in arms):
        for b in next(r[a]["payload_size"]["bins"] for a in arms if r[a]["payload_size"]):
            L.append(f"| payload {b} | " + " | ".join(
                str(r[a]["payload_size"]["bins"][b]) if r[a]["payload_size"] else "0" for a in arms) + " |")
    for key in ("per_workflow", "per_topology"):
        for a in arms:
            d = r[a][key]
            L += ["", f"{ARMS[a]} arm, {key.replace('per_', 'per ')}:", "",
                  "| Class | Traces | With at least one | Segments | Per trace |", "|---|---|---|---|---|"]
            L += [f"| {c} | {x['traces']} | {x['traces_with_retransmissions']} | {x['segments']} | {x['per_trace_mean']:.2f} |"
                  for c, x in d["classes"].items()]
            chi, kw = d["chi_square_traces_with_any"], d["kruskal_per_trace"]
            L.append("")
            L.append("Chi-square (traces with at least one, by class): "
                     + (f"χ² = {chi['chi2']:.2f}, dof {chi['dof']}, p = {chi['p']:.3g}" if chi else "not defined")
                     + "; Kruskal-Wallis (retransmissions per trace): "
                     + (f"H = {kw['H']:.2f}, p = {kw['p']:.3g}" if kw else "not defined") + ".")
    return L


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--old", default=str(OLD))
    p.add_argument("--new", default=str(RES))
    p.add_argument("--raw-root", default="data", dest="raw_root",
                   help="folder holding raw_tlspair_{tls,clear} (the retransmission counts)")
    p.add_argument("--out", default=None, help="path stem for .json and .md (not overwritten)")
    a = p.parse_args(argv)
    old, new = numbers(Path(a.old)), numbers(Path(a.new))
    if not old:
        raise SystemExit(f"nothing under {a.old}")
    rows = compare(old, new)
    paired = {attr: new.get(f"{attr}: TLS − cleartext interval contains 0 (not significant)") for attr in ATTRS}
    retx = {arm: retransmissions(Path(a.raw_root) / d) for arm, d in RAW.items()}
    out = {"paper": "P2", "collection_id": "TLS control", **_git(), "old": a.old, "new": a.new,
           "paired_difference_not_significant": paired, "rows": rows, "retransmissions": retx}
    md = ["# D1 before and after counting every payload byte once", "",
          f"Old: `{a.old}` (retransmitted segments counted again). New: `{a.new}` (each payload byte once). "
          "Pending: not rebuilt yet.", "",
          "Paired TLS − cleartext difference still not significant (interval contains 0): "
          + ", ".join(f"{k} {fmt(v)}" for k, v in paired.items()) + ".", "",
          "| Number | Old | New | Same |", "|---|---|---|---|"]
    md += [f"| {r['number']} | {fmt(r['old'])} | {fmt(r['new'])} | {fmt(r['same']) if r['same'] is not None else '—'} |"
           for r in rows]
    md += retx_markdown(retx)
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
