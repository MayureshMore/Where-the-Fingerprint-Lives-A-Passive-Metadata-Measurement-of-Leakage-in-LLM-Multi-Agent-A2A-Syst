#!/usr/bin/env python3
"""
B1 size check: does B1's lan_padmax read lower than C2's because it holds 125 traces per task type?
On C2 lan_padmax (data/raw_c2_padmax, 250 per task type), each draw takes --per-type traces per
task type by whole prompt groups, the same traces at V1 and V2, and runs a2a-leakcheck's verdict
with its defaults (margin 0.05, 99 group permutations, 1000 bootstraps, gbt; no attribution) on
the real labels of that draw: task_type (four types), pair (sensor_analysis vs fault_diagnosis)
and escalated_only (the three escalated types). Per task and view: the draws' median macro-F1,
range and verdicts, beside the full C2 cell by the same code and B1's lan_padmax
(data/results/b1_audits.json). B1's value inside the draws' range points to sample size; far
outside it, to the session.

    python scripts/b1_size_check.py --out data/results/b1_size_check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from a2a_leakcheck.analyze import INCONCLUSIVE, LEAK, NO_LEAK  # noqa: E402
from a2a_leakcheck.cli import _git  # noqa: E402
from a2a_leakcheck.rules import load_rules  # noqa: E402
from scripts.evaluate_leakcheck import subsample  # noqa: E402
from scripts.paper2_round2 import ARMS, ESCALATED, PAIR, SEED, counts, load_cell, run, why  # noqa: E402

SUB_STREAM = 24          # apart from paper2_round2's (8-10, 20, 21), b1_power's (22, 23) and the tests' (seed, 7, i)
TASKS = ("task_type", "pair", "escalated_only")
VIEWS = ("v1", "v2")
ARM = "lan_padmax"
B1_AUDITS = "data/results/b1_audits.json"


def task_index(tt: np.ndarray, task: str) -> np.ndarray:
    """Positions of a task's traces among the given task types."""
    if task == "pair":
        return np.flatnonzero(np.isin(tt, PAIR))
    if task == "escalated_only":
        return np.flatnonzero(np.isin(tt, ESCALATED))
    return np.arange(len(tt))


def draw_ids(d: dict, n: int, i: int) -> list[str]:
    """Draw i: n traces per task type by whole prompt groups, as run ids (the same traces in every view)."""
    sub = subsample(d["labels"]["task_type"], d["g"], n, np.random.default_rng([SEED, SUB_STREAM, n, i]))
    return [d["ids"][j] for j in sub]


def evaluate(d: dict, ids: list[str] | None, task: str, a, sev: dict) -> dict:
    """The verdict on one task over the given traces (None: every trace of the cell)."""
    if ids is None:
        idx = np.arange(len(d["ids"]))
    else:
        pos = {r: j for j, r in enumerate(d["ids"])}
        idx = np.array([pos[r] for r in ids])
    keep = idx[task_index(d["labels"]["task_type"][idx], task)]
    y = d["labels"]["task_type"][keep]
    r = run(d["X"]["leakcheck"][keep], y, d["g"][keep], "leakcheck", a, sev)
    r["why"] = why(r)
    r["per_class"] = {c: int((y == c).sum()) for c in sorted(set(y.tolist()))}
    return r


def summary(rows: list[dict], b1: float | None) -> dict:
    f1 = [r["macro_f1"] for r in rows]
    out = {"draws": len(rows), "macro_f1_median": statistics.median(f1), "macro_f1_min": min(f1), "macro_f1_max": max(f1),
           "ci_lo_median": statistics.median(r["ci"][0] for r in rows), "ci_hi_median": statistics.median(r["ci"][1] for r in rows),
           "verdicts": counts(r["verdict"] for r in rows), "seconds_median": statistics.median(r["seconds"] for r in rows)}
    if b1 is not None:
        out["b1_macro_f1"] = b1
        out["b1_draws_below"] = sum(x < b1 for x in f1)
        out["b1_in_range"] = min(f1) <= b1 <= max(f1)
        out["b1_minus_median"] = b1 - out["macro_f1_median"]
    return out


def b1_values(path: str = B1_AUDITS) -> dict:
    """B1's lan_padmax macro-F1 and CI per task and view, from the committed B1 audits."""
    d = json.loads(Path(path).read_text())
    out = {"source": path, "git_commit": d.get("git_commit"), "collection_id": d.get("collection_id"), "values": {}}
    for v in VIEWS:
        for task in TASKS:
            run_name = f"c2b1_{ARM}_{v}" + ("" if task == "task_type" else f"_{task}")
            t = d["runs"][run_name]["attributes"]["task_type"]
            out["values"][f"{task}_{v}"] = {"run": run_name, "n": t["n"], "macro_f1": t["macro_f1"], "ci": t["ci"],
                                            "verdict": t["verdict"]}
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--out", required=True, help="output path without extension (.json, .md)")
    p.add_argument("--per-type", type=int, default=125, dest="per_type", help="traces per task type in a draw (B1: 125)")
    p.add_argument("--draws", type=int, default=10)
    p.add_argument("--permutations", type=int, default=99)
    p.add_argument("--n-boot", type=int, default=1000, dest="n_boot")
    p.add_argument("--jobs", type=int, default=-1)
    p.add_argument("--allow-dirty", action="store_true", dest="allow_dirty")
    a = p.parse_args(argv)
    out = Path(a.out)
    for ext in (".json", ".md"):
        if out.with_suffix(ext).exists():
            raise SystemExit(f"{out.with_suffix(ext)} exists: results are not written over")
    git = _git()
    if git["git_dirty"] is not False and not a.allow_dirty:
        raise SystemExit("uncommitted code: commit first (or --allow-dirty for a test run)")
    sev = load_rules()["severity"]
    b1 = b1_values()
    t0 = time.perf_counter()
    cells = {v: load_cell(f"{ARM}_{v}") for v in VIEWS}
    if set(cells["v1"]["ids"]) != set(cells["v2"]["ids"]):
        raise SystemExit("the V1 and V2 cells hold different traces")
    d1 = cells["v1"]
    per_type = dict(zip(*np.unique(d1["labels"]["task_type"], return_counts=True)))
    if a.per_type > min(per_type.values()):
        raise SystemExit(f"{ARM} holds {min(per_type.values())} traces per task type, fewer than {a.per_type}")
    print(f"[{ARM}] {per_type}, {len(np.unique(d1['g']))} groups", flush=True)
    res = {"paper": "P2", "round": 2, "purpose": "B1 size check: C2 lan_padmax at B1's 125 per task type",
           "collection_id": "C2", "data_dir": {ARM: ARMS[ARM]}, "reference": {"b1": b1}, "seed": SEED,
           **{k: git[k] for k in ("git_commit", "git_dirty")}, "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "parameters": {"per_type": a.per_type, "draws": a.draws, "margin": 0.05, "permutations": a.permutations,
                          "n_boot": a.n_boot, "perm_unit": "group", "model": "gbt", "null_model": "rf-light",
                          "stream": SUB_STREAM, "attribution": False},
           "draws": [], "full": {}, "summary": {}}
    ids = [draw_ids(d1, a.per_type, i) for i in range(a.draws)]
    for i, sel in enumerate(ids):
        res["draws"].append({"draw": i, "traces": len(sel), "sha1": hashlib.sha1("\n".join(sorted(sel)).encode()).hexdigest(),
                             "groups": int(len(np.unique(d1["g"][[d1["ids"].index(r) for r in sel]])))})
    rows: dict[str, list[dict]] = {}
    for v in VIEWS:
        for task in TASKS:
            key = f"{task}_{v}"
            res["full"][key] = evaluate(cells[v], None, task, a, sev)
            f = res["full"][key]
            print(f"[{key}] full: {f['verdict']} F1 {f['macro_f1']:.3f} ({f['seconds']:.0f} s)", flush=True)
            rows[key] = []
            for i, sel in enumerate(ids):
                r = evaluate(cells[v], sel, task, a, sev)
                r["draw"] = i
                rows[key].append(r)
                print(f"[{key}] draw {i}: {r['verdict']:12s} F1 {r['macro_f1']:.3f} CI {r['ci']} p {r['p']} "
                      f"({r['seconds']:.0f} s)", flush=True)
            res["summary"][key] = {**summary(rows[key], b1["values"][key]["macro_f1"]), "rows": rows[key]}
    res["runtime_s"] = time.perf_counter() - t0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(res, indent=1, default=str))
    out.with_suffix(".md").write_text(markdown(res))
    print(f"→ {out}.json, {out}.md ({res['runtime_s']:.0f} s)")
    return 0


def markdown(r: dict) -> str:
    p = r["parameters"]
    L = [f"# B1 size check: C2 {ARM} at {p['per_type']} per task type", "",
         f"Commit {r['git_commit']} (dirty: {r['git_dirty']}), seed {r['seed']}, {p['draws']} draws by whole prompt groups "
         f"(the same traces at V1 and V2), a2a-leakcheck's verdict with margin {p['margin']}, {p['permutations']} group "
         f"permutations, {p['n_boot']} bootstraps. B1: `{r['reference']['b1']['source']}` "
         f"(commit {str(r['reference']['b1']['git_commit'])[:8]}).", "",
         "| Task | View | B1 lan_padmax | C2 at B1's size: median [range] | draws under B1 | verdicts L/I/N | C2 full |",
         "|---|---|---|---|---|---|---|"]
    for v in VIEWS:
        for task in TASKS:
            key = f"{task}_{v}"
            s, f, b = r["summary"][key], r["full"][key], r["reference"]["b1"]["values"][key]
            vd = s["verdicts"]
            L.append(f"| {task} | {v} | {b['macro_f1']:.3f} [{b['ci'][0]:.3f}, {b['ci'][1]:.3f}] | "
                     f"{s['macro_f1_median']:.3f} [{s['macro_f1_min']:.3f}, {s['macro_f1_max']:.3f}] | "
                     f"{s['b1_draws_below']} of {s['draws']} | {vd[LEAK]}/{vd[INCONCLUSIVE]}/{vd[NO_LEAK]} | "
                     f"{f['macro_f1']:.3f} [{f['ci'][0]:.3f}, {f['ci'][1]:.3f}] |")
    L += ["", "\"draws under B1\": draws whose macro-F1 is below B1's. B1 inside the range points to sample size; "
          "far outside it, to the session."]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
