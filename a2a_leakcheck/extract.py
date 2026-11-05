"""
Extraction: the repository's header-only features (packet sizes, timestamps, direction).

    trace samples   195-dim trace vector (features/extractor.py) + the first-request size
                    (features/first_request.py), one per capture: workflow, topology, ...
    role samples    35-dim per-flow vector, one per agent port per capture (features/roles.py),
                    only for the agents that carry traffic in that capture: an agent the vantage
                    point never sees (at a gateway, the calls between specialists on the far
                    side) gives no sample, so role classes can be unbalanced or missing

Direction: a packet to an agent port is a request (caller → agent), from one a response.
"""

from __future__ import annotations

import logging

import numpy as np

from features.extractor import FeatureExtractor
from features.first_request import FIRST_REQUEST_DEF, first_request_bytes
from features.roles import role_vectors

logger = logging.getLogger(__name__)


def extract(traces: list, legacy: bool = False) -> dict:
    """legacy: every connection on the agent ports instead of only those each trace opens itself
    (features/connections.py)."""
    extractors: dict[frozenset, FeatureExtractor] = {}
    rows, first, keep, role_rows, role_y, role_trace, failed = [], [], [], [], [], [], []
    visible: list[list[str]] = []                    # per extracted trace: roles with traffic
    for i, tr in enumerate(traces):
        ports = frozenset(tr.port_role)
        ex = extractors.setdefault(ports, FeatureExtractor(agent_ports=set(ports), use_scapy=True,
                                                           own_connections=not legacy))
        try:
            packets = ex._read_pcap(tr.pcap)
        except Exception as exc:  # noqa: BLE001 — one unreadable capture must not stop the run
            failed.append({"pcap": tr.pcap.name, "reason": f"unreadable: {exc}"})
            continue
        if not packets:
            failed.append({"pcap": tr.pcap.name, "reason": "no packets on the agent ports"})
            continue
        rows.append(ex._compute_features(tr.run_id, packets).flat_vector())
        first.append(first_request_bytes(tr.pcap, set(ports), legacy))
        keep.append(i)
        seen = []
        for _, (role, vec, _, _) in sorted(role_vectors(ex, packets, {str(p): r for p, r in tr.port_role.items()}).items()):
            role_rows.append(vec)
            role_y.append(role)
            role_trace.append(len(keep) - 1)
            seen.append(role)
        visible.append(sorted(seen))
    if not rows:
        raise SystemExit("no capture yielded any agent traffic: check agent_endpoints and the capture filter")
    return {
        "trace_X": np.stack(rows).astype(np.float32),
        "first_request": np.array(first, dtype=np.float32),
        "trace_index": keep,                         # into the collected traces
        "role_X": np.stack(role_rows).astype(np.float32) if role_rows else np.zeros((0, 35), np.float32),
        "role_y": np.array(role_y),
        "role_trace": np.array(role_trace, dtype=int),   # into the extracted traces
        "visible_roles": visible,                    # per extracted trace
        "summary": {"traces": len(rows), "failed": failed, "role_samples": len(role_rows),
                    "trace_dims": int(rows[0].shape[0]), "role_dims": 35,
                    "measurement": "all connections on the agent ports (legacy)" if legacy else
                                   "own connections: only TCP connections whose SYN is in the capture",
                    "first_request": FIRST_REQUEST_DEF},
    }
