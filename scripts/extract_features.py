#!/usr/bin/env python3
"""
Feature extraction script.

Reads all .pcap files from data/raw/ (with matching .json label sidecars),
extracts TraceFeatures for each, and writes:
  - data/processed/<run_id>.npz          per-trace flat+burst features
  - data/processed/<run_id>__role__<port>.npz  per-agent features for C2
  - data/processed/labels.json           run_id → {workflow, topology, prompt_group}
                                         + <run_id>__role__<port> → {role, workflow, topology}

C2 (role classification) design:
  All TCP connections to the same agent port within one trace are pooled
  into a single feature vector (one sample per agent per trace).  This
  prevents the bug where multiple connections to the same port would
  overwrite each other, leaving the last connection's features in the NPZ
  while n_role overcounted the writes.  Pooling also better captures the
  total traffic exchanged with each agent, not just one arbitrary connection.

A trace uses only the TCP connections it opens itself (features/connections.py): packets of
connections opened before the capture (the previous trace's closes) are dropped, and
<out>/extraction_meta.json records how many traces had any. --legacy-all-connections keeps every
connection on the agent ports, the measurement behind results committed before this rule.

Usage:
    python scripts/extract_features.py --raw data/raw --out data/processed
    python scripts/extract_features.py --raw data/raw --out data/processed --scapy
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _port_to_role(agent_endpoints: dict[str, str]) -> dict[str, str]:
    """Build reverse map: "8001" → "executor" from sidecar agent_endpoints."""
    mapping: dict[str, str] = {}
    for role, addr in agent_endpoints.items():
        port = addr.rsplit(":", 1)[-1]
        mapping[port] = role
    return mapping


def _prompt_group(prompt: str) -> str:
    """Stable 8-char hash of input_prompt used as GroupKFold group key."""
    return hashlib.sha1(prompt.encode()).hexdigest()[:8]


def main(raw_dir: Path, out_dir: Path, use_scapy: bool = False, legacy: bool = False) -> None:
    from capture.labeler import TraceLabeler
    from features.extractor import FeatureExtractor
    from features.roles import role_vectors

    out_dir.mkdir(parents=True, exist_ok=True)

    pcap_files = sorted(raw_dir.glob("*.pcap"))
    logger.info("Found %d pcap files in %s", len(pcap_files), raw_dir)

    # Auto-detect agent ports from sidecar files so deployment-B pcaps (ports
    # 8010-8013) are filtered correctly without any CLI flag change.
    agent_ports: set[int] = set()
    for pcap_path in pcap_files:
        label_path = pcap_path.with_suffix(".json")
        if label_path.exists():
            try:
                sc = json.loads(label_path.read_text())
                for addr in sc.get("agent_endpoints", {}).values():
                    port_str = addr.rsplit(":", 1)[-1]
                    if port_str.isdigit():
                        agent_ports.add(int(port_str))
            except Exception:
                pass
    if not agent_ports:
        agent_ports = {8000, 8001, 8002, 8003}
    logger.info("Agent ports detected from sidecars: %s", sorted(agent_ports))

    extractor = FeatureExtractor(agent_ports=agent_ports, use_scapy=use_scapy, own_connections=not legacy)
    from features.connections import own_packets
    from features.kfp import tcp_packets
    leftover: dict[str, int] = {}

    labels_map: dict[str, dict] = {}
    n_ok = n_fail = n_role = 0

    for pcap_path in pcap_files:
        label_path = pcap_path.with_suffix(".json")
        if not label_path.exists():
            logger.warning("No label sidecar for %s — skipping", pcap_path.name)
            continue

        sidecar = json.loads(label_path.read_text())
        run = TraceLabeler.read(pcap_path)
        if not run.success:
            logger.debug("Skipping failed run %s", run.run_id)
            continue

        try:
            features = extractor.extract(pcap_path, run_id=run.run_id)
        except ValueError as exc:  # zero valid A2A flows — fail loud (per-pcap)
            logger.error("ZERO-FLOW extraction failure: %s", exc)
            features = None
        if features is None:
            logger.warning("No features extracted from %s", pcap_path.name)
            n_fail += 1
            continue

        pk = [p for p in tcp_packets(pcap_path) if p[1] in agent_ports or p[2] in agent_ports]
        leftover[run.run_id] = len(pk) - len(own_packets(pk, agent_ports))

        # ── Per-trace NPZ (workflow + topology labels) ────────────────────────
        npz_path = out_dir / f"{run.run_id}.npz"
        features.save(npz_path)
        prompt = sidecar.get("input_prompt", "")
        # parallelism: binary label replacing topology-type.
        # chain → "sequential" (each agent waits for previous output)
        # star/mesh → "parallel" (orchestrator fans out concurrently)
        parallelism = "sequential" if run.topology.value == "chain" else "parallel"
        labels_map[run.run_id] = {
            "workflow": run.workflow_class.value,
            "topology": run.topology.value,
            "parallelism": parallelism,
            "prompt_group": _prompt_group(prompt),
            "deployment": run.deployment,
        }
        n_ok += 1

        # ── Per-flow NPZ (role labels — C2) ───────────────────────────────────
        agent_endpoints: dict[str, str] = sidecar.get("agent_endpoints", {})
        if not agent_endpoints:
            continue

        port_role = _port_to_role(agent_endpoints)

        # Re-read packets to group by flow and extract per-flow features
        packets = extractor._read_pcap(pcap_path)
        if not packets:
            continue

        # One NPZ per (run_id, agent_port): every connection to the agent pooled
        for dst_port, (role, pf_vec, burst_seq, gap_seq) in role_vectors(extractor, packets, port_role).items():
            role_run_id = f"{run.run_id}__role__{dst_port}"
            role_npz = out_dir / f"{role_run_id}.npz"
            np.savez_compressed(
                role_npz,
                flat=pf_vec,
                burst_sequence=burst_seq,
                gap_sequence=gap_seq,
            )
            labels_map[role_run_id] = {
                "role": role,
                "workflow": run.workflow_class.value,
                "topology": run.topology.value,
                "parallelism": parallelism,
                "prompt_group": _prompt_group(prompt),
                "deployment": run.deployment,
            }
            n_role += 1

    # FAIL HARD on a systematic zero-extraction (the IPv6-bug class): refuse to
    # write an empty dataset that exits 0 and looks like success.
    if pcap_files and n_ok == 0:
        raise SystemExit(
            f"FATAL: extracted 0/{len(pcap_files)} traces from {raw_dir} — systematic "
            f"failure (wrong agent_ports, IPv4-vs-IPv6 mismatch, or all runs marked "
            f"failed). Refusing to write an empty dataset."
        )

    (out_dir / "labels.json").write_text(json.dumps(labels_map, indent=2))
    with_left = sum(1 for v in leftover.values() if v)
    (out_dir / "extraction_meta.json").write_text(json.dumps({
        "raw_dir": str(raw_dir), "measurement": "all connections (legacy)" if legacy else "own connections",
        "traces": n_ok, "role_samples": n_role, "traces_with_leftover_packets": with_left,
        "leftover_packets": sum(leftover.values()),
        "note": "leftover = packets of connections opened before the capture; dropped unless legacy",
    }, indent=2))
    logger.info("%d of %d traces had packets of earlier connections (%s)", with_left, n_ok,
                "kept: legacy" if legacy else "dropped")
    logger.info(
        "Extraction complete: %d traces ok, %d failed, %d role samples. Labels → %s",
        n_ok, n_fail, n_role, out_dir / "labels.json",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract features from pcap files")
    parser.add_argument("--raw", default="data/raw")
    parser.add_argument("--out", default="data/processed")
    parser.add_argument("--scapy", action="store_true",
                        help="Use scapy instead of pyshark for pcap parsing")
    parser.add_argument("--legacy-all-connections", action="store_true", dest="legacy",
                        help="keep every connection on the agent ports (the earlier measurement)")
    args = parser.parse_args()
    main(Path(args.raw), Path(args.out), use_scapy=args.scapy, legacy=args.legacy)
