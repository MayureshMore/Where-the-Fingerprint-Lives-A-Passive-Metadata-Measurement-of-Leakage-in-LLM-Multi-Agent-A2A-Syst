#!/usr/bin/env python3
"""
C2B2's results as docs/PREREG_C2B2.md registered them, in the order the paper reports them. It reads
the registered analysis's outputs and computes nothing new:

  1. the primary: sensor vs fault at V2 on timing alone, each arm (verdict, macro-F1 [95% CI], p), whether
     the control requirement holds (the control's reads LEAK), and the registered reading
  2. the manipulation checks' verdict (VALID or INVALID) with their numbers: the reply jitter's mean and
     sd, the cloud's slowdown under load, the reordering against the control, the netem delay, the keeper
  3. the all-features pair and task_type at V2, both arms

and the deviations from the pre-registration, each with when, why and what it does not touch.

    python scripts/c2b2_results.py --audits data/results/c2b2_audits.json \\
        --manipulation data/results/c2b2_manipulation.json --out data/results/c2b2_results

Inputs: scripts/b1_audits.py's summary (--prefix c2b2), scripts/check_b2_manipulation.py's result and,
for the reordering shares, the check_reorder.py result that one names. Nothing is written over;
uncommitted code is refused.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

PREFIX, CONTROL, TREATMENT = "c2b2", "lan_padmax", "lan_padmax_jl"
READING = {
    "LEAK": "the timing leak survives the WAN's jitter and the server load at this sample size",
    "NO LEAK": "jitter and load together bring it to the NO LEAK bound",
    "INCONCLUSIVE": "not shown either way",
}
DEVIATIONS = [
    {"when": "Nov 26, 2026, before the pilot (no trace collected)",
     "commits": ["6d228a42", "fc103506"],
     "what": "the Mac's pf rules: data/results/c2b2_wan.json, whose general dummynet rules match only the "
             "control's cloud ports (8101, 8102), in place of data/results/b2_wan_jitter.json's rules",
     "why": "in macOS pf a packet that leaves a dummynet pipe re-enters the ruleset at the next rule, so the Nov 21 "
            "rules put the treatment's packets through pipes 3 and 4 and then 1 and 2 as well: the first WAN check "
            "read 17.0 ms SYN -> SYN-ACK at the capture instead of 4, and 32.8 ms end to end instead of 18.6",
     "does_not_touch": "it applies the registered design (2 ms of dummynet each way for the treatment); every "
                       "delay, target, the jitter, the load, the Pi's netem, the analysis, the manipulation "
                       "checks and the primary as registered"},
    {"when": "Nov 26, 2026, after the pilot, before the full run",
     "commits": ["01230d36"],
     "what": "the guard (scripts/c2_guard.py) run with --tolerance 0.30 instead of 0.20",
     "why": "its capture-based estimate of the Pi's connect read 14.84 ms for the treatment against 0.20's lower "
            "bound of 14.9, while every direct measurement was near the 18.6 ms target (16.4, 17.8, 19.9 ms); it "
            "would have stopped the full run again and again. At 0.30 every guard check stays (bands [13.0, 24.2] "
            "and [15.8, 29.4]); replayed on the pilot, 0.20 fails and 0.30 passes. The user's decision",
     "does_not_touch": "the guard only watches the WAN during the collection; the analysis, the manipulation "
                       "checks, the primary and the collector's own WAN probes (their tolerance stayed 0.20)"},
]


def run_name(arm: str, part: str = "pair", fs: str = "timing", view: str = "v2") -> str:
    return f"{PREFIX}_{arm}_{view}" + ("" if part == "all" else f"_{part}") + ("" if fs == "all" else f"_{fs}")


def cell(audits: dict, arm: str, part: str, fs: str, view: str = "v2") -> dict:
    name = run_name(arm, part, fs, view)
    run = audits["runs"][name]
    a = run["attributes"]["task_type"]
    return {"run": name, "report": run["report"], "verdict": a["verdict"], "macro_f1": a["macro_f1"],
            "ci": a["ci"], "p": a["p"], "n": a["n"], "classes": a["classes"]}


def results(audits: dict, manip: dict, reorder: dict | None) -> dict:
    control, treatment = cell(audits, CONTROL, "pair", "timing"), cell(audits, TREATMENT, "pair", "timing")
    met = control["verdict"] == "LEAK"
    valid = bool(manip["valid"])
    if not valid:
        reading = "the session is invalid (a manipulation check failed): the primary is reported, not read"
    elif not met:
        reading = "the control's timing-alone pair does not read LEAK: the primary is reported, not read"
    else:
        reading = READING[treatment["verdict"]]
    c = manip["checks"]
    slow = {t: round(r["ratio"], 3) for t, r in c["load_slowdown"]["per_task_type"].items() if r.get("ratio")}
    ro = None
    if reorder:
        ro = {"treatment_share": reorder["dirs"][0]["pi_to_cloud"]["reordered_share"],
              "control_share": reorder["control"]["pi_to_cloud"]["reordered_share"],
              "margin": reorder["margin"], "ok": reorder["ok"]}
    manipulation = {
        "verdict": "VALID" if valid else "INVALID",
        "failed": [k for k, v in c.items() if not v["ok"]],
        "jitter": {"draws": c["jitter_log"]["draws"], "mean_ms": c["jitter_log"]["mean_ms"],
                   "sd_ms": c["jitter_log"]["sd_ms"], "expected": c["jitter_log"]["expected"]},
        "slowdown": slow,
        "reorder": ro,
        "netem": {"ack_later_ms": c["netem_capture"].get("difference_ms"), "expected_ms": c["netem_capture"].get("expected_ms"),
                  "netem_packets": c["netem_pi"].get("netem_packets"),
                  "captured_pi_to_cloud_packets": c["netem_pi"].get("captured_pi_to_cloud_packets")},
        "keeper": c["keeper"]["ok"],
        "gpu": c["gpu"]["ok"], "load_windows": c["load_windows"]["ok"],
    }
    secondary = {f"{part}_{fs}_v2": {arm: cell(audits, arm, part, fs) for arm in (CONTROL, TREATMENT)}
                 for part, fs in (("pair", "all"), ("all", "all"))}
    return {"primary": {"control": control, "treatment": treatment,
                        "control_requirement": {"met": met, "rule": "the control's timing-alone pair at V2 reads LEAK"},
                        "reading": reading},
            "manipulation": manipulation, "secondary": secondary, "deviations": DEVIATIONS}


def _f(x) -> str:
    return "-" if x is None else f"{x:.3f}"


def _cell(x: dict) -> str:
    return f"{x['verdict']} {_f(x['macro_f1'])} [{_f(x['ci'][0])}, {_f(x['ci'][1])}], p {_f(x['p'])}"


def markdown(r: dict) -> str:
    p, m, s = r["primary"], r["manipulation"], r["secondary"]
    ro = m["reorder"]
    slow = ", ".join(f"{t.split('_')[0]} x{v:.2f}" for t, v in sorted(m["slowdown"].items()))
    L = [f"# C2B2 results (docs/PREREG_C2B2.md)", "",
         f"Commit {r['git_commit']} (dirty: {r['git_dirty']}); from `{r['sources']['audits']}` (analysis commit "
         f"{r['analysis_commit']}) and `{r['sources']['manipulation']}`.", "",
         "1. **Primary**, sensor vs fault at V2 on timing alone: control "
         f"{_cell(p['control'])}; treatment {_cell(p['treatment'])}. Control requirement "
         f"{'met' if p['control_requirement']['met'] else 'NOT met'}. Reading: {p['reading']}.",
         f"2. **Manipulation checks: {m['verdict']}**"
         + (f" (failed: {', '.join(m['failed'])})" if m["failed"] else "")
         + f". Reply jitter {m['jitter']['draws']:,} draws, mean {m['jitter']['mean_ms']:.2f} ms, sd "
         f"{m['jitter']['sd_ms']:.2f} ms (registered 4.01, 1.78); cloud under load {slow}; reordering "
         + (f"{ro['treatment_share']:.2%} against the control's {ro['control_share']:.2%}" if ro else "-")
         + f"; netem: the Pi's ACK {m['netem']['ack_later_ms']:.2f} ms later than the control's (registered "
         f"{m['netem']['expected_ms']:.2f}); keeper {'PASS' if m['keeper'] else 'FAIL'}.",
         f"3. **All features at V2**: pair, control {_cell(s['pair_all_v2'][CONTROL])}, treatment "
         f"{_cell(s['pair_all_v2'][TREATMENT])}; task_type (four types), control {_cell(s['all_all_v2'][CONTROL])}, "
         f"treatment {_cell(s['all_all_v2'][TREATMENT])}.", "",
         "## Deviations from the pre-registration", ""]
    for d in r["deviations"]:
        L.append(f"- **{d['when']}** ({', '.join(d['commits'])}): {d['what']}. Why: {d['why']}. It does not touch "
                 f"{d['does_not_touch']}.")
    return "\n".join(L) + "\n"


def _git() -> dict:
    def g(*args):
        return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()
    return {"git_commit": g("rev-parse", "HEAD") or None,
            "git_dirty": bool(g("status", "--porcelain", "--", ".", ":(exclude)data"))}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--audits", default="data/results/c2b2_audits.json")
    p.add_argument("--manipulation", default="data/results/c2b2_manipulation.json")
    p.add_argument("--out", default="data/results/c2b2_results")
    p.add_argument("--allow-dirty", action="store_true", dest="allow_dirty")
    a = p.parse_args(argv)
    out = Path(a.out)
    if out.with_suffix(".json").exists() or out.with_suffix(".md").exists():
        raise SystemExit(f"{out}.json/.md exist: results are never written over")
    git = _git()
    if git["git_dirty"] and not a.allow_dirty:
        raise SystemExit("uncommitted code: commit first (or --allow-dirty for a test run)")
    audits = json.loads(Path(a.audits).read_text())
    manip = json.loads(Path(a.manipulation).read_text())
    rf = Path(manip["checks"]["reorder"]["file"])
    reorder = json.loads(rf.read_text()) if rf.exists() else None
    res = {"paper": "P2", "round": 2, "collection_id": "C2B2", "purpose": "C2B2's registered results for the paper",
           **git, "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "analysis_commit": audits.get("git_commit"),
           "sources": {"audits": a.audits, "manipulation": a.manipulation, "reorder": str(rf)},
           **results(audits, manip, reorder)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(res, indent=1, default=str))
    out.with_suffix(".md").write_text(markdown(res))
    print(markdown(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
