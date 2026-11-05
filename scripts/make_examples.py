#!/usr/bin/env python3
"""
Build examples/: two small leakcheck inputs from the TLS control's TLS arm.

  examples/leaky      40 header-only traces: workflows code_review and support_triage ×
                      topologies chain and star, 10 each, every trace from its own prompt group.
                      The real labels: role, workflow and topology are known to leak.
  examples/permuted   the same 40 captures with permuted labels: in each real workflow ×
                      topology cell of 10, five traces get each workflow and five each topology,
                      at random, so the permuted labels are independent of the real ones in this
                      sample (a plain shuffle of 40 can agree with the real topology by chance, and
                      topology is visible in the traffic); in each trace the four roles are
                      shuffled across the four agent ports. The labels say nothing about the
                      traffic.

Sidecars keep only what leakcheck reads (agent_endpoints, workflow_class, topology,
prompt_group, success) and run_id; prompt_group is sha1(prompt)[:8], as collect.py derives it,
so the prompt text is not included. Captures are cut to their headers (scripts/strip_payload.py).

Usage:
    python scripts/make_examples.py                       # from data/raw_tlspair_tls
    python -m a2a_leakcheck run examples/leaky --out examples/expected/leaky
    python -m a2a_leakcheck run examples/permuted --out examples/expected/permuted
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.strip_payload import strip_file  # noqa: E402

SEED = 42
WORKFLOWS = ("code_review", "support_triage")
TOPOLOGIES = ("chain", "star")
PER_CELL = 10


def pick(raw: Path) -> list[dict]:
    """PER_CELL traces per workflow × topology, each from a prompt group not used before."""
    rng = np.random.default_rng(SEED)
    cells: dict[tuple, list] = {}
    for side in sorted(raw.glob("*.json")):
        sc = json.loads(side.read_text())
        if "run_id" not in sc or sc.get("success") is False or not side.with_suffix(".pcap").exists():
            continue
        if sc["workflow_class"] in WORKFLOWS and sc["topology"] in TOPOLOGIES:
            sc["prompt_group"] = sc.get("prompt_group") or hashlib.sha1(sc["input_prompt"].encode()).hexdigest()[:8]
            cells.setdefault((sc["workflow_class"], sc["topology"]), []).append((side, sc))
    used, out = set(), []
    for key in [(w, t) for w in WORKFLOWS for t in TOPOLOGIES]:
        got = 0
        for i in rng.permutation(len(cells[key])):
            side, sc = cells[key][i]
            if sc["prompt_group"] in used:
                continue
            used.add(sc["prompt_group"])
            out.append({"pcap": side.with_suffix(".pcap"), "sidecar": sc})
            got += 1
            if got == PER_CELL:
                break
        if got < PER_CELL:
            raise SystemExit(f"{key}: only {got} traces from unused prompt groups")
    return out


def _sidecar(sc: dict, **override) -> dict:
    keep = {k: sc[k] for k in ("run_id", "agent_endpoints", "workflow_class", "topology", "prompt_group")}
    return {**keep, "success": True, **override}


def main(a: argparse.Namespace) -> None:
    raw, out = Path(a.raw), Path(a.out)
    traces = pick(raw)
    rng = np.random.default_rng(SEED)
    wf, top = [None] * len(traces), [None] * len(traces)
    for i in range(0, len(traces), PER_CELL):                 # pick() returns the cells in order
        for labels, values in ((wf, WORKFLOWS), (top, TOPOLOGIES)):
            half = [values[0]] * (PER_CELL // 2) + [values[1]] * (PER_CELL - PER_CELL // 2)
            labels[i:i + PER_CELL] = rng.permutation(half).tolist()
    for name in ("leaky", "permuted"):
        (out / name).mkdir(parents=True, exist_ok=True)
    for i, t in enumerate(traces):
        sc, stem = t["sidecar"], t["sidecar"]["run_id"]
        for name in ("leaky", "permuted"):
            strip_file(t["pcap"], out / name / f"{stem}.pcap")
        (out / "leaky" / f"{stem}.json").write_text(json.dumps(_sidecar(sc), indent=2) + "\n")
        roles = list(sc["agent_endpoints"])
        eps = dict(zip(rng.permutation(roles).tolist(), sc["agent_endpoints"].values()))
        perm = _sidecar(sc, workflow_class=str(wf[i]), topology=str(top[i]), agent_endpoints=eps,
                        labels="permuted (examples/README.md)")
        (out / "permuted" / f"{stem}.json").write_text(json.dumps(perm, indent=2) + "\n")
    print(f"{len(traces)} traces → {out}/leaky, {out}/permuted")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--raw", default="data/raw_tlspair_tls")
    p.add_argument("--out", default="examples")
    main(p.parse_args())
