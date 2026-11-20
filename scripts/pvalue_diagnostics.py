#!/usr/bin/env python3
"""
Where do two machines' permutation p-values part? (paper 2 round 2, A6: audit_null on C2 lan V1 read
p = 0.22 on the Raspberry Pi and 0.07 on the Mac, same seed and data.)

    dump      on one machine, from a features folder (python -m a2a_leakcheck extract): the library
              versions, BLAS/OpenMP libraries and thread settings, then a hash of every stage of one
              attribute's permutation test in order: the features, labels and groups; the folds; each
              permuted label vector; the GBT's out-of-fold predictions; the null model's predictions and
              macro-F1 on the real labels; every permuted run's macro-F1; p. For both permutation units
              (sample: 0.1.x's test, which gave 0.22 and 0.07; group: 0.3.0's) and both null models
              (rf-light, the default; gbt). With --seeds, the p-value at each seed (the spread a seed
              alone causes) and the Monte-Carlo standard error sqrt(p(1-p)/R).
    compare   two dumps: the first stage at which they differ, and by how much.

Usage:
    python -m a2a_leakcheck extract data/raw_c2 --vantage v1 --strip \\
        --attributes task_type,escalated,cloud_role,audit_null --out data/round2_parts/features_c2_lan_v1
    python scripts/pvalue_diagnostics.py dump data/round2_parts/features_c2_lan_v1 --seeds 42-51 \\
        --out data/results/paper2_pvalue_mac.json
    # the same on the Pi (docs/LEAKCHECK.md, "On a Raspberry Pi"), then:
    python scripts/pvalue_diagnostics.py compare data/results/paper2_pvalue_pi.json data/results/paper2_pvalue_mac.json \\
        --out data/results/paper2_pvalue_compare
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as md
import json
import os
import platform
import sys
import time
from pathlib import Path

import numpy as np
from sklearn.metrics import f1_score

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from a2a_leakcheck.analyze import Config, _null_run, _oof, _parallel, _splits, group_plan, permutations  # noqa: E402
from a2a_leakcheck.cli import _git  # noqa: E402
from a2a_leakcheck.extract import load_features  # noqa: E402

PACKAGES = ("numpy", "scipy", "scikit-learn", "joblib", "threadpoolctl", "narwhals", "PyYAML", "scapy")
ENV = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "LOKY_MAX_CPU_COUNT")


def h(x) -> str:
    a = np.asarray(x)
    data = a.tobytes() if a.dtype != object and a.dtype.kind != "U" else "\x1f".join(map(str, a.tolist())).encode()
    return hashlib.sha256(data).hexdigest()[:16]


def environment() -> dict:
    from threadpoolctl import threadpool_info
    git = _git()
    commit_file = Path(__file__).resolve().parent.parent / "COMMIT"
    if git["git_commit"] is None and commit_file.exists():
        git = {"git_commit": commit_file.read_text().strip(), "git_dirty": None, "source": "COMMIT file (rsync copy)"}
    vers = {}
    for p in PACKAGES:
        try:
            vers[p] = md.version(p)
        except md.PackageNotFoundError:
            vers[p] = None
    return {**git, "python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine(),
            "cpu_count": os.cpu_count(), "packages": vers, "env": {k: os.environ.get(k) for k in ENV},
            "threadpools": [{k: v for k, v in x.items() if k in ("user_api", "internal_api", "prefix", "version",
                                                                  "num_threads", "threading_layer", "architecture")}
                            for x in threadpool_info()]}


def stages(X, y, g, cfg: Config) -> dict:
    """Every stage of one attribute's test, hashed, and the numbers that come out of it."""
    classes = sorted(set(y.tolist()))
    f1 = lambda p: float(f1_score(y, p, labels=classes, average="macro", zero_division=0))  # noqa: E731
    null_model = cfg.model if cfg.null_model == "same" else cfg.null_model
    splits = _splits(y, g, cfg)
    perms = permutations(y, g, cfg, 0, cfg.permutations, group_plan(y, g) if cfg.perm_unit == "group" else None)
    t = time.perf_counter()
    main = _oof(X, y, splits, cfg)
    null_real = _oof(X, y, splits, cfg, null_model)
    runs = _parallel([(_null_run, X, yp, g, classes, cfg, null_model) for yp in perms], cfg.jobs)
    null_f1 = [f for f, _ in runs]
    observed = f1(null_real)
    return {"unit": cfg.perm_unit, "null_model": null_model, "seed": cfg.seed,
            "hash": {"folds": h(np.concatenate([np.sort(te) for _, te in splits])),
                     "permutations": [h(p) for p in perms], "main_oof": h(main), "null_oof_real": h(null_real)},
            "main_macro_f1": f1(main), "observed_null_macro_f1": observed, "null_f1": null_f1,
            "p_value": (1 + sum(x >= observed for x in null_f1)) / (len(null_f1) + 1),
            "seconds": time.perf_counter() - t}


def dump(a) -> dict:
    summary, ext, traces, meta = load_features(Path(a.features))
    have = np.array([a.attribute in t.labels for t in traces])
    X = ext["trace_X"][have]
    y = np.array([t.labels[a.attribute] for t, k in zip(traces, have) if k])
    g = np.array([t.group for t, k in zip(traces, have) if k])
    out = {"tool": "pvalue_diagnostics", "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "environment": environment(),
           "features": str(a.features), "attribute": a.attribute,
           "hash": {"X": h(X.astype(np.float32)), "y": h(y), "g": h(g)}, "n": int(len(y)), "runs": []}
    for unit in ("sample", "group"):
        for null in ("rf-light", "gbt"):
            cfg = Config(perm_unit=unit, null_model=null, jobs=a.jobs)
            out["runs"].append(stages(X, y, g, cfg))
            r = out["runs"][-1]
            print(f"{unit:6s} {null:8s} p = {r['p_value']:.2f}, observed {r['observed_null_macro_f1']:.4f} "
                  f"({r['seconds']:.0f} s)", flush=True)
    if a.seeds:
        lo, hi = (int(x) for x in a.seeds.split("-"))
        spread = []
        for s in range(lo, hi + 1):
            for unit in ("sample", "group"):
                r = stages(X, y, g, Config(seed=s, perm_unit=unit, jobs=a.jobs))
                spread.append({"seed": s, "unit": unit, "p_value": r["p_value"], "observed": r["observed_null_macro_f1"]})
                print(f"seed {s} {unit:6s} p = {r['p_value']:.2f}", flush=True)
        out["seed_spread"] = spread
        for unit in ("sample", "group"):
            ps = [x["p_value"] for x in spread if x["unit"] == unit]
            out[f"seed_spread_{unit}"] = {"min": min(ps), "max": max(ps), "mean": float(np.mean(ps)), "sd": float(np.std(ps)),
                                          "mc_se_at_mean": float(np.sqrt(np.mean(ps) * (1 - np.mean(ps)) / 99))}
    return out


def compare(a_: dict, b_: dict) -> dict:
    out = {"a": a_["environment"], "b": b_["environment"], "first_difference": None, "stages": []}
    pkgs = {p: [a_["environment"]["packages"].get(p), b_["environment"]["packages"].get(p)]
            for p in PACKAGES if a_["environment"]["packages"].get(p) != b_["environment"]["packages"].get(p)}
    out["packages_differ"] = pkgs
    def stage(name, x, y, detail=None):
        same = x == y
        out["stages"].append({"stage": name, "same": same, **({"detail": detail} if detail and not same else {})})
        if not same and out["first_difference"] is None:
            out["first_difference"] = name
    for k in ("X", "y", "g"):
        stage(f"input {k}", a_["hash"][k], b_["hash"][k])
    for ra, rb in zip(a_["runs"], b_["runs"]):
        tag = f"{ra['unit']}/{ra['null_model']}"
        stage(f"{tag}: folds", ra["hash"]["folds"], rb["hash"]["folds"])
        diff = [i for i, (x, y) in enumerate(zip(ra["hash"]["permutations"], rb["hash"]["permutations"])) if x != y]
        stage(f"{tag}: permuted labels", not diff, True, {"first": diff[:1], "count": len(diff)})
        stage(f"{tag}: GBT out-of-fold predictions", ra["hash"]["main_oof"], rb["hash"]["main_oof"])
        stage(f"{tag}: null model on the real labels", ra["hash"]["null_oof_real"], rb["hash"]["null_oof_real"],
              {"observed": [ra["observed_null_macro_f1"], rb["observed_null_macro_f1"]]})
        d = [abs(x - y) for x, y in zip(ra["null_f1"], rb["null_f1"])]
        stage(f"{tag}: permuted runs' macro-F1", max(d) == 0, True,
              {"differ": sum(x > 0 for x in d), "max_abs": max(d)})
        stage(f"{tag}: p", ra["p_value"], rb["p_value"], {"p": [ra["p_value"], rb["p_value"]]})
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump")
    d.add_argument("features")
    d.add_argument("--attribute", default="audit_null")
    d.add_argument("--seeds", default="", help="e.g. 42-51: the p-value at each seed")
    d.add_argument("--jobs", type=int, default=-1)
    d.add_argument("--out", required=True)
    c = sub.add_parser("compare")
    c.add_argument("a")
    c.add_argument("b")
    c.add_argument("--out", required=True, help="path without extension (.json, .md)")
    a = p.parse_args(argv)
    if a.cmd == "dump":
        if Path(a.out).exists():
            raise SystemExit(f"{a.out} exists")
        Path(a.out).write_text(json.dumps(dump(a), indent=1))
        print(f"→ {a.out}")
        return 0
    res = compare(*(json.loads(Path(x).read_text()) for x in (a.a, a.b)))
    out = Path(a.out)
    out.with_suffix(".json").write_text(json.dumps(res, indent=1))
    L = [f"# p-value diagnostics: {a.a} against {a.b}", "",
         f"First difference: **{res['first_difference'] or 'none'}**. Packages that differ: {res['packages_differ'] or 'none'}.", "",
         "| Stage | Same | Detail |", "|---|---|---|"]
    L += [f"| {s['stage']} | {'yes' if s['same'] else 'no'} | {s.get('detail', '')} |" for s in res["stages"]]
    out.with_suffix(".md").write_text("\n".join(L) + "\n")
    print(f"→ {out}.json, {out}.md; first difference: {res['first_difference']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
