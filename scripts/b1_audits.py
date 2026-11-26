#!/usr/bin/env python3
"""
Round-2 audits of B1's arms with a2a-leakcheck (its defaults: the permutation test by prompt group,
the match margin 0.05), per arm and observer view, in three parts:

  all             the arm's traces: task_type, escalated, cloud_role, audit_null
  pair            sensor_analysis and fault_diagnosis only: task_type (sensor vs fault)
  escalated_only  the three escalated task types only: task_type

A part other than all, or an arm given several capture folders (B1 and C2B1X pooled), runs on a
folder of relative symlinks to the chosen traces under --subset-dir (data/subsets, not committed),
with a manifest of its sources: folder, collection id and traces per task type. With --baseline-arm,
every other arm's report of a view and part is run with --baseline against that arm's report of the
same view and part (the CI gate: exit code, changes, new leaks, needs_review, resolved).

--feature-sets all,timing also audits each arm, view and part on the timing family alone (B2): the
traces are extracted (`a2a_leakcheck extract`, the same view, --strip and attributes) into
--features-dir (data/features_audits, not committed), every column of the trace and role vectors
outside features/families.py's timing family is set to 0 and so is the first-request size, and
`run` audits that features folder: the full verdict (interval and permutation test) on timing alone,
since a column that is 0 everywhere is never split on. Its report folder ends in _timing, and a
baseline arm's timing report is the gate for the other arms' timing reports.

Each run writes data/results/leakcheck/<prefix>_<arm>_<view>[_<part>][_timing]/ (report.json, .md, .html), or
the same under --reports (scripts/reproduce_paper2.sh writes into its sandbox);
--out writes the summary (.json, .md): verdicts, macro-F1 and CI, p, carried by (matches all, the
non-inferiority rule), the baseline comparisons, and paper, collection ids, data folders, commit and
seed. Nothing is written over; uncommitted code is refused. --title names the summary (default "B1 audits").

    python scripts/b1_audits.py --arm lan_padmax=data/raw_c2b1_padmax --arm lan_shaped=data/raw_c2b1_shaped \\
        --baseline-arm lan_padmax --prefix c2b1 --out data/results/b1_audits
    # after C2B1X: sensor vs fault on the shaped traces of both collections, against B1's lan_padmax
    python scripts/b1_audits.py --arm lan_shaped=data/raw_c2b1_shaped,data/raw_c2b1x_shaped --parts pair \\
        --baseline-arm lan_padmax --baseline-prefix c2b1 --prefix c2b1_c2b1x --out data/results/b1_pair_pooled
    # B3: the second day of lan, audited as C2's lan arm
    python scripts/b1_audits.py --arm lan=data/raw_c2b3_lan --prefix c2b3 --title "B3 audits" --out data/results/b3_audits
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from a2a_leakcheck.cli import _git  # noqa: E402
from a2a_leakcheck.extract import FEATURES_JSON, FEATURES_NPZ  # noqa: E402
from features.families import family_columns  # noqa: E402

PAIR = ("fault_diagnosis", "sensor_analysis")
ESCALATED = ("fault_diagnosis", "procedure_lookup", "sensor_analysis")
PARTS = {"all": (None, "task_type,escalated,cloud_role,audit_null"), "pair": (PAIR, "task_type"),
         "escalated_only": (ESCALATED, "task_type")}
REPORTS = Path("data/results/leakcheck")
SEED = 42                                        # a2a-leakcheck's default --seed
FEATURE_SETS = ("all", "timing")


def name(prefix: str, arm: str, view: str, part: str, fs: str = "all") -> str:
    return f"{prefix}_{arm}_{view}" + ("" if part == "all" else f"_{part}") + ("" if fs == "all" else f"_{fs}")


def only_family(src: Path, dst: Path, family: str) -> dict:
    """A copy of the features folder src with every column outside the family set to 0 (trace and role
    vectors) and the first-request size set to 0; features.json says so (feature_set)."""
    meta = json.loads((src / FEATURES_JSON).read_text())
    with np.load(src / FEATURES_NPZ, allow_pickle=False) as z:
        arr = {k: z[k] for k in z.files}
    keep_t, keep_r = family_columns(family, False), family_columns(family, True)
    tx = np.zeros_like(arr["trace_X"])
    tx[:, keep_t] = arr["trace_X"][:, keep_t]
    rx = np.zeros_like(arr["role_X"])
    if rx.size:
        rx[:, keep_r] = arr["role_X"][:, keep_r]
    arr.update(trace_X=tx, role_X=rx, first_request=np.zeros_like(arr["first_request"]))
    fs = {"family": family, "trace_columns": int(len(keep_t)), "role_columns": int(len(keep_r)),
          "source": str(src), "rule": f"every column outside features/families.py's {family} family, and the "
                                      "first-request size, set to 0"}
    dst.mkdir(parents=True)
    np.savez_compressed(dst / FEATURES_NPZ, **arr)
    (dst / FEATURES_JSON).write_text(json.dumps({**meta, "feature_set": fs}, indent=1))
    return fs


def extract_family(folder: Path, feats: Path, view: str, attrs: str, family: str) -> tuple[Path, dict]:
    """Extract folder at the view into feats (reused if it holds the same input, view and attributes), then
    the family-only copy beside it (feats + _family, made again from feats)."""
    want = {"folder": str(folder), "vantage": view, "attributes": attrs.split(",")}
    if feats.exists():
        m = json.loads((feats / FEATURES_JSON).read_text()) if (feats / FEATURES_JSON).exists() else {}
        have = {"folder": (m.get("input") or {}).get("folder"), "vantage": (m.get("input") or {}).get("vantage"),
                "attributes": m.get("attributes")}
        if have != want:
            raise SystemExit(f"{feats} holds other features ({have}); remove it or pick --features-dir")
    else:
        cmd = [sys.executable, "-m", "a2a_leakcheck", "extract", str(folder), "--out", str(feats), "--strip",
               "--vantage", view, "--attributes", attrs]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not (feats / FEATURES_JSON).exists():
            raise SystemExit(f"extract {folder} ({view}) exited {r.returncode}\n{r.stderr[-2000:]}")
    dst = feats.with_name(f"{feats.name}_{family}")
    if dst.exists():
        for f in (FEATURES_JSON, FEATURES_NPZ):
            (dst / f).unlink(missing_ok=True)
        dst.rmdir()
    return dst, only_family(feats, dst, family)


def traces(folder: Path) -> list[tuple[Path, dict]]:
    """(sidecar, its labels) of every complete trace: a pcap with a sidecar beside it."""
    out = []
    for pcap in sorted(folder.glob("*.pcap")):
        sc = pcap.with_suffix(".json")
        if sc.exists():
            out.append((sc, json.loads(sc.read_text())))
    return out


def sources(dirs: list[Path]) -> list[dict]:
    """Per capture folder: its collection id (session_meta.json, else the sidecars') and traces per task type."""
    out = []
    for d in dirs:
        tr = traces(d)
        meta = d / "session_meta.json"
        cid = json.loads(meta.read_text()).get("collection_id") if meta.exists() else None
        ids = sorted({s.get("collection_id") for _, s in tr if s.get("collection_id")})
        out.append({"dir": str(d), "collection_id": cid or (ids[0] if len(ids) == 1 else ids or None),
                    "traces": len(tr), "per_task_type": _count(s.get("task_type") for _, s in tr)})
    return out


def _count(xs) -> dict:
    out: dict = {}
    for x in xs:
        out[x] = out.get(x, 0) + 1
    return dict(sorted(out.items()))


def subset(dirs: list[Path], task_types: tuple | None, folder: Path) -> dict:
    """A folder of relative symlinks (pcap and sidecar) to the traces of these task types, with a
    manifest; an existing folder is used only if its manifest is the same."""
    chosen = [(sc, s) for d in dirs for sc, s in traces(d) if task_types is None or s.get("task_type") in task_types]
    names = [sc.stem for sc, _ in chosen]
    if len(set(names)) != len(names):
        raise SystemExit(f"{folder}: two folders hold a trace of the same name")
    manifest = {"sources": sources(dirs), "task_types": list(task_types) if task_types else "all",
                "traces": len(chosen), "per_task_type": _count(s.get("task_type") for _, s in chosen),
                "per_collection": _count(s.get("collection_id") for _, s in chosen)}
    mf = folder / "manifest.json"
    if folder.exists():
        if not mf.exists() or json.loads(mf.read_text()) != manifest:
            raise SystemExit(f"{folder} exists with other traces: remove it (it holds only symlinks) or pick --subset-dir")
        return manifest
    folder.mkdir(parents=True)
    for sc, _ in chosen:
        for f in (sc.with_suffix(".pcap"), sc):
            os.symlink(os.path.relpath(f.resolve(), folder.resolve()), folder / f.name)
    mf.write_text(json.dumps(manifest, indent=1))
    return manifest


def command(folder: Path, out: Path, view: str, attrs: str, label: str, baseline: Path | None, jobs: int,
            features: bool = False) -> list[str]:
    """`run` on captures (--strip, --vantage), or on a features folder (extracted with them already)."""
    cmd = [sys.executable, "-m", "a2a_leakcheck", "run", str(folder), "--out", str(out)]
    cmd += [] if features else ["--strip", "--vantage", view]
    cmd += ["--attributes", attrs, "--label", label, "--html", "--jobs", str(jobs)]
    return cmd + (["--baseline", str(baseline)] if baseline else [])


def carried(at: dict | None) -> str:
    """The report's "carried by" under the non-inferiority rule (paper2_round2.carried, matches_all)."""
    if not at:
        return "-"
    single = at.get("single_request_size") or {}
    if single and single.get("matches_all"):
        return f"{single['feature']} alone"
    top = at.get("top_family")
    if not top:
        return "-"
    return top + (" (alone matches all)" if at["families"][top].get("matches_all") else "")


def summarize(report: dict) -> dict:
    out = {"attributes": {}}
    for attr, r in report["attributes"].items():
        an = r.get("analysis") or {}
        perm = (r.get("validation") or {}).get("permutation") or {}
        out["attributes"][attr] = {"verdict": r["verdict"], "n": r.get("n"), "groups": r.get("n_groups"),
                                   "classes": r.get("classes"), "macro_f1": an.get("macro_f1"),
                                   "ci": [an.get("ci_lo"), an.get("ci_hi")], "threshold": r.get("threshold"),
                                   "p": perm.get("p_value"),
                                   "carried_by": carried(r.get("attribution")) if r["verdict"] == "LEAK" else "-"}
    if report.get("diff") is not None:
        d = report["diff"]
        out["baseline"] = {"against": d.get("baseline"), "compatible": d.get("compatible"),
                           "changes": d.get("changes"), "new_leaks": d.get("new_leaks"),
                           "needs_review": d.get("needs_review"), "resolved": d.get("resolved")}
    status = (report.get("status") or {}).get("release_policy") or {}
    out["exit_code"] = status.get("exit_code")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--arm", action="append", required=True, metavar="NAME=DIR[,DIR...]")
    p.add_argument("--views", default="v1,v2")
    p.add_argument("--parts", default="all,pair,escalated_only")
    p.add_argument("--prefix", required=True, help="report folders: <reports>/<prefix>_<arm>_<view>[_<part>]")
    p.add_argument("--reports", default=str(REPORTS), help=f"where the reports go (default {REPORTS}); the "
                   "baseline arm's earlier reports (--baseline-prefix) are read from here too")
    p.add_argument("--baseline-arm", default=None, dest="baseline_arm",
                   help="run every other arm with --baseline against this arm's report of the same view and part")
    p.add_argument("--baseline-prefix", default=None, dest="baseline_prefix",
                   help="the baseline arm's reports come from an earlier run with this prefix (default: --prefix)")
    p.add_argument("--subset-dir", default="data/subsets", dest="subset_dir")
    p.add_argument("--feature-sets", default="all", dest="feature_sets",
                   help="all (every feature, as before) and/or timing (the timing family alone), comma-separated")
    p.add_argument("--features-dir", default="data/features_audits", dest="features_dir",
                   help="where --feature-sets timing extracts (not committed)")
    p.add_argument("--out", required=True, help="summary path without extension (.json, .md)")
    p.add_argument("--jobs", type=int, default=-1)
    p.add_argument("--title", default="B1 audits", help="the summary's purpose and heading")
    p.add_argument("--allow-dirty", action="store_true", dest="allow_dirty")
    a = p.parse_args(argv)

    arms = {}
    for spec in a.arm:
        arm, _, dirs = spec.partition("=")
        arms[arm] = [Path(d) for d in dirs.split(",") if d]
        if not arms[arm] or any(not d.is_dir() for d in arms[arm]):
            raise SystemExit(f"--arm {spec}: give NAME=DIR[,DIR...] of existing capture folders")
    views = [v for v in a.views.split(",") if v]
    parts = [x for x in a.parts.split(",") if x]
    if bad := set(parts) - set(PARTS):
        raise SystemExit(f"unknown parts {sorted(bad)}; choose from {list(PARTS)}")
    fsets = [x for x in a.feature_sets.split(",") if x]
    if not fsets or (bad := set(fsets) - set(FEATURE_SETS)):
        raise SystemExit(f"--feature-sets: choose from {list(FEATURE_SETS)}")
    base_prefix = a.baseline_prefix or a.prefix
    if a.baseline_arm and a.baseline_arm not in arms and not a.baseline_prefix:
        raise SystemExit("--baseline-arm is not one of the arms: give --baseline-prefix of its earlier reports")
    order = sorted(arms, key=lambda x: x != a.baseline_arm)          # the baseline arm's reports first
    runs = [(arm, v, part, fs) for arm in order for v in views for part in parts for fs in fsets]
    out, reports = Path(a.out), Path(a.reports)
    exist = [str(x) for x in (out.with_suffix(".json"), out.with_suffix(".md")) if x.exists()]
    exist += [str(reports / name(a.prefix, *r)) for r in runs if (reports / name(a.prefix, *r)).exists()]
    if exist:
        raise SystemExit("results are not written over: " + ", ".join(exist))
    for arm, v, part, fs in runs:
        if a.baseline_arm and arm != a.baseline_arm:
            b = reports / name(base_prefix, a.baseline_arm, v, part, fs) / "report.json"
            if a.baseline_arm not in arms and not b.exists():
                raise SystemExit(f"no baseline report {b}")
    git = _git()
    if git["git_dirty"] is not False and not a.allow_dirty:
        raise SystemExit("uncommitted code: commit first (or --allow-dirty for a test run)")

    t0 = time.perf_counter()
    res = {"paper": "P2", "round": 2, "purpose": f"{a.title}: per arm, view and part, with the baseline gate",
           "title": a.title,
           "seed": SEED, **git, "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "parameters": {"views": views, "parts": parts, **({"feature_sets": fsets} if fsets != ["all"] else {}),
                          "prefix": a.prefix, "baseline_arm": a.baseline_arm,
                          "baseline_prefix": base_prefix if a.baseline_arm else None,
                          "tool_defaults": "perm-unit group, match-margin 0.05, margin 0.05, 99 permutations, "
                                           "1000 bootstraps, gbt, --strip"},
           "arms": {}, "runs": {}}
    for arm in order:
        src = sources(arms[arm])
        res["arms"][arm] = {"data_dir": [str(d) for d in arms[arm]], "collection_id": [s["collection_id"] for s in src],
                            "sources": src}
    res["collection_id"] = sorted({str(c) for x in res["arms"].values() for c in x["collection_id"]})
    res["data_dir"] = {arm: x["data_dir"] for arm, x in res["arms"].items()}
    for arm, v, part, fs in runs:
        task_types, attrs = PARTS[part]
        dirs = arms[arm]
        if task_types is None and len(dirs) == 1:
            folder, manifest = dirs[0], None
        else:
            folder = Path(a.subset_dir) / f"{a.prefix}_{arm}_{part}"
            manifest = subset(dirs, task_types, folder)
        baseline = reports / name(base_prefix, a.baseline_arm, v, part, fs) / "report.json" \
            if a.baseline_arm and arm != a.baseline_arm else None
        rep = reports / name(a.prefix, arm, v, part, fs)
        ids = "+".join(str(c) for c in res["arms"][arm]["collection_id"])
        label = f"{ids} {arm}, view {v}" + ("" if part == "all" else f", {part}") + ("" if fs == "all" else f", {fs} alone")
        family = None
        if fs != "all":
            src, family = extract_family(folder, Path(a.features_dir) / f"{a.prefix}_{arm}_{v}_{part}", v, attrs, fs)
            cmd = command(src, rep, v, attrs, label, baseline, a.jobs, features=True)
        else:
            cmd = command(folder, rep, v, attrs, label, baseline, a.jobs)
        print(f"[{time.strftime('%H:%M:%S')}] {name(a.prefix, arm, v, part, fs)}: {folder}"
              + (f" ({fs} alone)" if fs != "all" else "") + (f" (baseline {baseline})" if baseline else ""), flush=True)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode not in (0, 3, 4) or not (rep / "report.json").exists():
            raise SystemExit(f"{name(a.prefix, arm, v, part, fs)}: a2a_leakcheck exited {r.returncode}\n{r.stderr[-2000:]}")
        print("  " + r.stdout.strip().replace("\n", "\n  "), flush=True)
        row = {"report": str(rep / "report.json"), "input": str(folder), "subset": manifest,
               **({"feature_set": fs, "family_only": family} if fsets != ["all"] else {}),   # as before without them
               "returncode": r.returncode, **summarize(json.loads((rep / "report.json").read_text()))}
        res["runs"][name(a.prefix, arm, v, part, fs)] = row
    res["runtime_s"] = time.perf_counter() - t0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(res, indent=1, default=str))
    out.with_suffix(".md").write_text(markdown(res))
    print(f"→ {out}.json, {out}.md ({res['runtime_s']:.0f} s)")
    return 0


def _f(x) -> str:
    return "-" if x is None else f"{x:.3f}"


def markdown(r: dict) -> str:
    L = [f"# {r.get('title', 'B1 audits')} ({', '.join(r['collection_id'])})", "",
         f"Commit {r['git_commit']} (dirty: {r['git_dirty']}), seed {r['seed']}; a2a-leakcheck defaults "
         f"({r['parameters']['tool_defaults']}).", "",
         "| Run | Attribute | Verdict | Macro-F1 [95% CI] | Threshold | p | Carried by |", "|---|---|---|---|---|---|---|"]
    for run, x in r["runs"].items():
        for attr, v in x["attributes"].items():
            feats = f" ({x['feature_set']} alone)" if x.get("feature_set", "all") != "all" else ""
            L.append(f"| {run} | {attr}{feats} | {v['verdict']} | {_f(v['macro_f1'])} [{_f(v['ci'][0])}, {_f(v['ci'][1])}] | "
                     f"{_f(v['threshold'])} | {_f(v['p'])} | {v['carried_by']} |")
    gates = [(run, x) for run, x in r["runs"].items() if x.get("baseline")]
    if gates:
        L += ["", "Baseline gate (`run --baseline`):", "", "| Run | Against | Exit | Changes | New LEAK | Needs review | Resolved |",
              "|---|---|---|---|---|---|---|"]
        for run, x in gates:
            b = x["baseline"]
            ch = "; ".join(f"{c['attribute']} {c['before']} → {c['after']}" for c in b.get("changes") or []) or "-"
            nr = "; ".join(f"{c['attribute']} ({c['after']})" for c in b.get("needs_review") or []) or "-"
            L.append(f"| {run} | {b['against']} | {x['exit_code']} | {ch} | {', '.join(b.get('new_leaks') or []) or '-'} | "
                     f"{nr} | {', '.join(b.get('resolved') or []) or '-'} |")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
