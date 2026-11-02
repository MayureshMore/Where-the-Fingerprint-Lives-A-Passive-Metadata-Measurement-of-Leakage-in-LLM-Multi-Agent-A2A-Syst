"""
Role samples: one per-flow feature vector per agent per trace.

All TCP connections to the same agent port within one trace are pooled into a single sample
(retries, keep-alive reconnects and pipelined requests must be aggregated, not overwritten by
iteration order). Shared by scripts/extract_features.py and a2a_leakcheck.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from features.per_flow import compute_per_flow


def role_vectors(extractor, packets: list[tuple[float, int, str, int]],
                 port_role: dict[str, str]) -> dict[str, tuple[str, np.ndarray, np.ndarray, np.ndarray]]:
    """agent port → (role, 35-dim per-flow vector, burst sequence, gap sequence).

    packets: (ts, size, flow_key, direction) from FeatureExtractor._read_pcap;
    port_role: "8101" → "executor" (from the sidecar's agent_endpoints).
    """
    # Step 1: group individual TCP connections by flow key
    by_flow: dict[str, list[tuple[float, int, int]]] = defaultdict(list)
    for ts, size, fk, direction in packets:
        by_flow[fk].append((ts, size, direction))

    # Step 2: pool all flows that share the same destination agent port
    by_agent_port: dict[str, list[tuple[str, list[tuple[float, int, int]]]]] = defaultdict(list)
    for fk, pkts in by_flow.items():
        parts = fk.split("→")
        if len(parts) != 2:
            continue
        dst_port = parts[1].rsplit(":", 1)[-1]
        if port_role.get(dst_port) is not None:
            by_agent_port[dst_port].append((fk, pkts))

    # Step 3: per-flow features on the pooled view
    out = {}
    for dst_port, flow_list in by_agent_port.items():
        pooled_pkts: list[tuple[float, int, int]] = []
        for _, pkts in flow_list:
            pooled_pkts.extend(pkts)
        pooled_bursts = []
        for fk, pkts in flow_list:
            pooled_bursts.extend(extractor.segmenter.segment([(ts, size, fk, d) for ts, size, d in pkts]))
        pooled_bursts.sort(key=lambda b: b.start_ts)

        pf_vec = compute_per_flow(f"pooled→{dst_port}", pooled_bursts, pooled_pkts).to_vector()
        if pooled_bursts:
            burst_seq = np.stack([b.to_feature_vector() for b in pooled_bursts], axis=0)
            gap_seq = extractor.segmenter.gap_sequence(pooled_bursts)
        else:
            burst_seq = np.zeros((0, 10), dtype=np.float32)
            gap_seq = np.zeros(0, dtype=np.float32)
        out[dst_port] = (port_role[dst_port], pf_vec, burst_seq, gap_seq)
    return out
