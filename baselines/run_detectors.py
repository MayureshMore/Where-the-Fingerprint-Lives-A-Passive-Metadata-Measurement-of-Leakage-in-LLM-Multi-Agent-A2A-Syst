#!/usr/bin/env python3
"""
Paper 2's two traffic-analysis baselines on any a2a-leakcheck input folder.

    kfp_rf          k-FP features (features/kfp.py: packet direction and timing, no sizes) with a
                    random forest, as in website fingerprinting (Hayes and Danezis, 2016)
    first_request   the first request's size alone, with GBT: the single rule "how big was the task
                    input" (in TCP sequence space, features/first_request.py; for role: the bytes
                    each agent receives)
    leakcheck       (optional) the tool's own 195 features with GBT, without its attribution

Every method is scored by a2a-leakcheck's verdict rule, so the verdicts are comparable: 5-fold
cross-validation grouped by prompt, macro-F1 with a 1,000-resample cluster-bootstrap interval, LEAK
when the lower bound clears chance + 0.05 and the 99-permutation test passes at 0.05, NO LEAK when
the upper bound stays below it, INCONCLUSIVE otherwise or with fewer than 20 samples per class.
This is the code behind the baselines in data/results/paper2_tool_eval*.json
(scripts/evaluate_leakcheck.py: load_arm, verdict); the TLS scanners are run_tls_scanners.sh.

Usage:
    python baselines/run_detectors.py examples/c2_lan --attributes task_type --vantage v2
    python baselines/run_detectors.py data/raw_c2_padmax --attributes task_type,escalated \\
        --vantage v2 --methods kfp_rf,first_request,leakcheck --out /tmp/detectors
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from a2a_leakcheck.rules import load_rules  # noqa: E402
from scripts.evaluate_leakcheck import load_arm, verdict  # noqa: E402

METHODS = ("kfp_rf", "first_request", "leakcheck")


def run(a: argparse.Namespace) -> dict:
    attrs = [x.strip() for x in a.attributes.split(",") if x.strip()]
    methods = [x.strip() for x in a.methods.split(",") if x.strip()]
    if bad := [m for m in methods if m not in METHODS]:
        raise SystemExit(f"unknown method {bad}; choose from {', '.join(METHODS)}")
    t0 = time.perf_counter()
    data = load_arm(Path(a.captures), attributes=attrs, vantage=a.vantage)
    sev = load_rules()["severity"]
    out = {"captures": str(a.captures), "vantage": a.vantage, "traces": data["traces"],
           "parameters": {"permutations": a.permutations, "n_boot": a.n_boot, "margin": a.margin,
                          "min_per_class": a.min_per_class, "seed": 42},
           "attributes": {}}
    for attr in attrs:
        s = data["samples"].get(attr)
        if s is None:
            print(f"{attr}: no trace has this label")
            continue
        out["attributes"][attr] = {m: verdict(s["X"][m], s["y"], s["g"], a, m, sev) for m in methods}
    out["runtime_s"] = time.perf_counter() - t0
    return out


def table(out: dict) -> str:
    rows = ["| attribute | method | verdict | macro-F1 [95% CI] | p | n |", "|---|---|---|---|---|---|"]
    for attr, ms in out["attributes"].items():
        for m, r in ms.items():
            f1 = "—" if r["macro_f1"] is None else f"{r['macro_f1']:.3f} [{r['ci'][0]:.3f}, {r['ci'][1]:.3f}]"
            p = "—" if r["p"] is None else f"{r['p']:.2f}"
            rows.append(f"| {attr} | {m} | {r['verdict']} | {f1} | {p} | {r['n']} |")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("captures", help="folder of pcaps with label sidecars (payload is stripped on the fly)")
    p.add_argument("--attributes", default="role,workflow,topology")
    p.add_argument("--vantage", default=None, help="observer view from the sidecars (e.g. v1, v2)")
    p.add_argument("--methods", default="kfp_rf,first_request", help=f"comma-separated: {', '.join(METHODS)}")
    p.add_argument("--permutations", type=int, default=99)
    p.add_argument("--n-boot", type=int, default=1000, dest="n_boot")
    p.add_argument("--margin", type=float, default=0.05)
    p.add_argument("--min-per-class", type=int, default=20, dest="min_per_class")
    p.add_argument("--jobs", type=int, default=-1)
    p.add_argument("--out", default=None, help="folder for detectors.json and detectors.md")
    a = p.parse_args(argv)
    out = run(a)
    md = f"# Baselines on {out['captures']}" + (f" at {a.vantage}" if a.vantage else "") + "\n\n" + table(out) + "\n"
    print(md)
    if a.out:
        d = Path(a.out)
        d.mkdir(parents=True, exist_ok=True)
        (d / "detectors.json").write_text(json.dumps(out, indent=2, default=float) + "\n")
        (d / "detectors.md").write_text(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
