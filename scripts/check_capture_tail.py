#!/usr/bin/env python3
"""
Paper 1 sensitivity check: how much the capture tail the old recorder lost changes the features.

Until commit f38a2828 the collectors ran tcpdump without --immediate-mode, and macOS handed the
last packets before each stop to tcpdump too late: they were never written (capture/recorder.py).
Every collection up to then (C1, the TLS control, the summer sets) has that loss. To measure it,
12 C1-style traces were re-collected on Nov 9 with the old recorder (collect_session.py,
deployment A, TLS, llama3.2:3b, classic workflows, C1's first prompt of each topology × workflow,
seed offset 10000) while a second tcpdump in immediate mode captured the same traffic throughout
(ground_truth.pcap), and the moment each trace's capture was stopped was logged (stops.json).

For every trace, the complete capture is the recorded one plus the tail it lost: the ground
truth's packets of the trace's own connections (SYN in the trace's capture, as every evaluation
uses) after the last recorded packet and up to the stop. The recorded packets keep their own
timestamps (the two captures timestamp the same packet microseconds apart), so a feature changes
only through the lost packets; that the tail has exactly as many packets as the ground truth has
more than the recording up to the stop is checked per trace. Both are run through the
same extraction as the evaluations (features/extractor.py, own connections; features/roles.py):

  per connection   paper 1's 35 per-flow features, one vector per agent port (role samples)
  per trace        the 195 trace features (summary only)

Per feature: in how many samples it changes, and the largest relative change
|complete − recorded| / |complete|. Writes data/results/c1_capture_tail.{json,md}.

Usage:
    python scripts/check_capture_tail.py                    # data/raw_c1_tailcheck
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from features.connections import opened_connections  # noqa: E402
from features.extractor import FeatureExtractor  # noqa: E402
from features.kfp import tcp_packets  # noqa: E402
from features.names import FLAT_FEATURE_NAMES  # noqa: E402
from features.per_flow import PerFlowFeatures  # noqa: E402
from features.roles import role_vectors  # noqa: E402
from scripts.make_gateway_view import _records  # noqa: E402

RESULTS = Path(os.environ.get("A2A_RESULTS_DIR", "data/results"))
EPS = 1e-12


def _git() -> dict:
    def run(*a):
        return subprocess.run(["git", *a], capture_output=True, text=True).stdout.strip()
    return {"git_commit": run("rev-parse", "HEAD"),
            "git_dirty": bool(run("status", "--porcelain", "--", ".", ":(exclude)data"))}


def complete_capture(rec_raw: bytes, gt_raw: bytes, conns: set[tuple[int, int]], stop: float,
                     out: Path) -> tuple[int, int]:
    """Write the recorded capture plus the ground truth's packets of these connections after the
    last recorded packet and up to stop. Returns (tail packets, ground-truth packets up to stop
    minus recorded ones), which must agree."""
    own = lambda sp, dp: (sp, dp) in conns or (dp, sp) in conns          # noqa: E731
    recorded = [(ts, rec) for rec, ts, sp, dp, _ in _records(rec_raw)]
    last = max(ts for ts, _ in recorded)
    gt_own = [(ts, rec) for rec, ts, sp, dp, _ in _records(gt_raw) if ts <= stop and own(sp, dp)]
    tail = [(ts, rec) for ts, rec in gt_own if ts > last + 1e-3]
    n_rec_own = sum(1 for rec, ts, sp, dp, _ in _records(rec_raw) if own(sp, dp))
    out.write_bytes(rec_raw[:24] + b"".join(rec for _, rec in sorted(recorded + tail, key=lambda x: x[0])))
    return len(tail), len(gt_own) - n_rec_own


def features(pcap: Path, port_role: dict[int, str]) -> tuple[np.ndarray, dict[str, np.ndarray], int]:
    ex = FeatureExtractor(agent_ports=set(port_role), use_scapy=True, own_connections=True)
    packets = ex._read_pcap(pcap)
    trace = ex._compute_features(pcap.stem, packets).flat_vector()
    roles = {role: vec for _, (role, vec, _, _) in
             role_vectors(ex, packets, {str(p): r for p, r in port_role.items()}).items()}
    return np.asarray(trace, float), {r: np.asarray(v, float) for r, v in roles.items()}, len(packets)


def rel(complete: np.ndarray, recorded: np.ndarray) -> np.ndarray:
    d = np.abs(complete - recorded)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(np.abs(complete) > EPS, d / np.abs(complete), np.where(d > EPS, np.inf, 0.0))
    return r


def summarize(changes: np.ndarray, names: list[str]) -> list[dict]:
    """changes: samples × features of relative change."""
    out = []
    for j, name in enumerate(names):
        c = changes[:, j]
        changed = c[c > 1e-9]
        out.append({"feature": name, "samples": int(len(c)), "samples_changed": int(len(changed)),
                    "max_relative_change": float(changed.max()) if len(changed) else 0.0,
                    "median_relative_change_when_changed": float(np.median(changed)) if len(changed) else 0.0})
    return out


def main(a: argparse.Namespace) -> None:
    d = Path(a.dir)
    stops = json.loads((d / "stops.json").read_text())
    gt_raw = (d / "ground_truth.pcap").read_bytes()
    names = PerFlowFeatures.FEATURE_NAMES()
    role_rows, trace_rows, traces = [], [], []
    with tempfile.TemporaryDirectory(prefix="tailcheck_") as tmp:
        for side in sorted((d / "c1like").glob("*.json")):
            sc = json.loads(side.read_text())
            if "run_id" not in sc or not sc.get("success"):
                continue
            pcap = side.with_suffix(".pcap")
            port_role = {int(str(v).rsplit(":", 1)[1]): r for r, v in sc["agent_endpoints"].items()}
            conns = opened_connections(tcp_packets(pcap), set(port_role))
            full = Path(tmp) / pcap.name
            n_tail, n_missing = complete_capture(pcap.read_bytes(), gt_raw, conns, stops[pcap.name], full)
            t_rec, r_rec, n_rec = features(pcap, port_role)
            t_full, r_full, n_full_own = features(full, port_role)
            lost = n_full_own - n_rec
            trace_rows.append(rel(t_full, t_rec))
            for role in sorted(r_full):
                if role in r_rec:
                    role_rows.append(rel(r_full[role], r_rec[role]))
            traces.append({"run_id": sc["run_id"], "topology": sc["topology"], "workflow": sc["workflow_class"],
                           "packets_recorded": n_rec, "packets_complete": n_full_own, "packets_lost": lost,
                           "tail_matches_ground_truth": n_tail == n_missing == lost,
                           "share_lost": lost / n_full_own if n_full_own else 0.0,
                           "roles": sorted(r_full), "roles_missing_in_recorded": sorted(set(r_full) - set(r_rec))})
    per_conn = summarize(np.array(role_rows), names)
    trace_rel = np.array(trace_rows)
    changed_trace = int((trace_rel > 1e-9).any(axis=0).sum())
    per_trace = summarize(trace_rel, FLAT_FEATURE_NAMES())
    assert all(t["tail_matches_ground_truth"] for t in traces), [t for t in traces if not t["tail_matches_ground_truth"]]
    out = {"paper": "P1", "collection_id": "C1-style tail check (12 traces re-collected Nov 9)",
           "data_dir": str(d), "seed": None, **_git(),
           "task": "sensitivity of the features to the capture tail lost by the recorder without --immediate-mode",
           "method": "complete capture = the recorded capture plus the ground truth's packets of the trace's own "
                     "connections after its last recorded packet and up to the stop (recorded packets keep their "
                     "timestamps); features from features/extractor.py (own connections) and features/roles.py",
           "traces": traces,
           "packets_lost": {"per_trace": [t["packets_lost"] for t in traces],
                            "median_share": float(np.median([t["share_lost"] for t in traces]))},
           "per_connection": {"features": 35, "role_samples": len(role_rows),
                              "features_changed": [f["feature"] for f in per_conn if f["samples_changed"]],
                              "per_feature": per_conn},
           "per_trace": {"features": int(trace_rel.shape[1]), "features_changed": changed_trace,
                         "max_relative_change": float(np.nanmax(np.where(np.isfinite(trace_rel), trace_rel, np.nan)))
                         if trace_rel.size else 0.0, "per_feature": per_trace}}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{a.name}.json").write_text(json.dumps(out, indent=2))
    L = ["# Capture tail lost by the old recorder: feature sensitivity (paper 1)", "",
         f"Commit `{out['git_commit'][:8]}` (dirty: {out['git_dirty']}). Data: `{d}` ({len(traces)} C1-style traces, "
         "re-collected Nov 9 with the old recorder and a ground-truth capture in immediate mode).", "",
         f"Packets lost per trace: {', '.join(str(x) for x in out['packets_lost']['per_trace'])} "
         f"(median share {out['packets_lost']['median_share']:.1%}).", "",
         f"## Paper 1's 35 per-connection features ({len(role_rows)} role samples)", "",
         f"Features that change at all: {len(out['per_connection']['features_changed'])} of 35.", "",
         "| Feature | Samples changed | Largest relative change | Median when changed |", "|---|---|---|---|"]
    for f in sorted(per_conn, key=lambda f: -f["max_relative_change"]):
        if f["samples_changed"]:
            L.append(f"| {f['feature']} | {f['samples_changed']} of {f['samples']} | {f['max_relative_change']:.2%} | "
                     f"{f['median_relative_change_when_changed']:.2%} |")
    unchanged = [f["feature"] for f in per_conn if not f["samples_changed"]]
    L += ["", f"Unchanged in every sample: {', '.join(unchanged) or 'none'}.", "",
          f"## The 195 trace features", "",
          f"{changed_trace} of {out['per_trace']['features']} change in at least one of the {len(traces)} traces; "
          f"largest relative change {out['per_trace']['max_relative_change']:.2%}. The ten largest:", "",
          "| Feature | Traces changed | Largest relative change | Median when changed |", "|---|---|---|---|"]
    for f in sorted(per_trace, key=lambda f: -f["max_relative_change"])[:10]:
        L.append(f"| {f['feature']} | {f['samples_changed']} of {f['samples']} | {f['max_relative_change']:.2%} | "
                 f"{f['median_relative_change_when_changed']:.2%} |")
    L += ["", "Features with at most 5% change in every trace: "
          f"{sum(1 for f in per_trace if f['max_relative_change'] <= 0.05)} of {len(per_trace)}."]
    (RESULTS / f"{a.name}.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--dir", default="data/raw_c1_tailcheck")
    p.add_argument("--name", default="c1_capture_tail")
    main(p.parse_args())
