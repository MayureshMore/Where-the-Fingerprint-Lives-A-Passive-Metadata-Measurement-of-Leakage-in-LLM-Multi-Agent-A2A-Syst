#!/usr/bin/env python3
"""
Build examples/c2_lan and examples/c2_lan_padmax: small leakcheck inputs from C2 (paper 2's edge-cloud
use case, docs/LAN_SETUP.md), the same tasks in the unpadded and the fully padded arm.

    examples/c2_lan          20 sensor_analysis and 20 fault_diagnosis tasks from data/raw_c2 (no padding)
    examples/c2_lan_padmax   the same 40 tasks (same prompts) from data/raw_c2_padmax: every request to a
                             cloud agent padded to 8 KB
    examples/c2_ci_baseline  the first 10 tasks of each type in examples/c2_lan (by name): the input of the
                             demo's CI baseline, an earlier audit with too few traces to decide

Both task types go to the same cloud agent (diagnostics), so at the upstream view (--vantage v2) the
observer sees one agent and must tell the tasks apart by the shape of the traffic alone: what padding
is meant to stop. On all of C2 the pair reads LEAK in every arm, with timing alone too
(data/results/paper2_tool_eval_c2.json, pair).

Tasks are drawn at random (seed 42) from prompt groups with one task each, so no two examples share
a prompt. Captures are cut to their headers and their Ethernet addresses replaced by placeholders, as
in the data release (scripts/strip_payload.py --placeholder-macs; scripts/package_paper2_data.py).
Sidecars keep what leakcheck reads and the C2 labels; the prompt text is left out (prompt_group
stands for it).

Usage:
    python scripts/make_c2_examples.py                      # from data/raw_c2, data/raw_c2_padmax
    for x in c2_lan c2_lan_padmax c2_ci_baseline; do
        python -m a2a_leakcheck run examples/$x --vantage v2 --attributes task_type --html \\
            --label "example: $x, view v2" --out examples/expected/${x}_v2
    done
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.strip_payload import MacPlaceholders, strip_file  # noqa: E402

SEED = 42
TASKS = ("sensor_analysis", "fault_diagnosis")
PER_TASK = 20
ARMS = {"c2_lan": "raw_c2", "c2_lan_padmax": "raw_c2_padmax"}
KEEP = ("run_id", "agent_endpoints", "vantages", "topology", "prompt_group", "task_type", "escalated",
        "cloud_role", "audit_null", "arm", "edge_host", "defense", "pad_buckets", "pad_expect",
        "padded_endpoints")
CI_BASELINE = ("c2_lan", "c2_ci_baseline", 10)


def sidecars(raw: Path) -> dict[str, dict]:
    """prompt_group → sidecar, for groups with exactly one successful task."""
    by: dict[str, list] = {}
    for side in sorted(raw.glob("*_edge_cloud_*.json")):
        sc = json.loads(side.read_text())
        if sc.get("success") is not False and side.with_suffix(".pcap").exists():
            by.setdefault(sc["prompt_group"], []).append(sc)
    return {g: v[0] for g, v in by.items() if len(v) == 1}


def pick(data: Path, tasks=TASKS, per_task=PER_TASK) -> list[str]:
    arms = {name: sidecars(data / raw) for name, raw in ARMS.items()}
    shared = set.intersection(*(set(a) for a in arms.values()))
    rng = np.random.default_rng(SEED)
    groups = []
    for t in tasks:
        pool = sorted(g for g in shared if all(a[g]["task_type"] == t for a in arms.values()))
        if len(pool) < per_task:
            raise SystemExit(f"{t}: only {len(pool)} prompt groups in both arms")
        groups += [pool[i] for i in sorted(rng.choice(len(pool), per_task, replace=False))]
    return groups


def main(a: argparse.Namespace) -> None:
    data, out = Path(a.data), Path(a.out)
    groups = pick(data, a.tasks.split(","), a.per_task)
    macs = MacPlaceholders()
    for name, raw in ARMS.items():
        dst = out / name
        if dst.exists() and any(dst.iterdir()):
            raise SystemExit(f"{dst} is not empty: remove it first")
        dst.mkdir(parents=True, exist_ok=True)
        sides = sidecars(data / raw)
        for g in groups:
            sc = sides[g]
            strip_file(data / raw / f"{sc['run_id']}.pcap", dst / f"{sc['run_id']}.pcap", macs)
            keep = {k: sc[k] for k in KEEP if k in sc}
            (dst / f"{sc['run_id']}.json").write_text(json.dumps({**keep, "success": True}, indent=2) + "\n")
        print(f"{len(groups)} traces → {dst}")
    src, name, n = CI_BASELINE
    dst = out / name
    if dst.exists() and any(dst.iterdir()):
        raise SystemExit(f"{dst} is not empty: remove it first")
    dst.mkdir(parents=True, exist_ok=True)
    sides = [json.loads(f.read_text()) for f in sorted((out / src).glob("*.json"))]
    for t in a.tasks.split(","):
        for sc in [x for x in sides if x["task_type"] == t][:n]:
            for ext in (".pcap", ".json"):
                (dst / f"{sc['run_id']}{ext}").write_bytes((out / src / f"{sc['run_id']}{ext}").read_bytes())
    print(f"{n} per task type of {out / src} → {dst}")
    for row in macs.table():
        print(f"  MAC {row['placeholder']}: frames of {', '.join(row['ipv4'])}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--data", default="data")
    p.add_argument("--out", default="examples")
    p.add_argument("--tasks", default=",".join(TASKS))
    p.add_argument("--per-task", type=int, default=PER_TASK, dest="per_task")
    main(p.parse_args())
