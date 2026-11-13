"""
Extraction: the repository's header-only features (packet sizes, timestamps, direction).

    trace samples   195-dim trace vector (features/extractor.py) + the first-request size
                    (features/first_request.py, first_request_seq: in TCP sequence space, ended
                    by the server's acknowledgment), one per capture: workflow, topology, ...
    role samples    35-dim per-flow vector, one per agent port per capture (features/roles.py),
                    only for the agents that carry traffic in that capture: an agent the vantage
                    point never sees (at a gateway, the calls between specialists on the far
                    side) gives no sample, so role classes can be unbalanced or missing

Direction: a packet to an agent port is a request (caller → agent), from one a response.

Every payload byte is counted once (dedup, features/kfp.py): a TCP retransmission is dropped and a
partial one keeps only its new bytes, as an observer that reassembles the TCP stream would see it.
Sizes, byte totals, packet counts and timing all use that view. The first-request size is measured
in TCP sequence space whatever dedup is: from the end of the TLS handshake to the acknowledgment
number of the first server data that acknowledges every client byte seen so far and that the client
received before sending more, so a TLS session ticket arriving mid-request, or part of a request held
back by a loss, does not end it early (features/first_request.py, first_request_seq).

keep_empty (leakcheck --vantage): a capture with no packets on the endpoints left in view is kept
as an all-zero trace vector with a first-request size of 0 and no role samples, instead of failing:
at an upstream vantage point every task answered on the gateway looks like that, and that the
observer sees nothing is the observation.
"""

from __future__ import annotations

import logging

import numpy as np

from features.extractor import FeatureExtractor
from features.first_request import FIRST_REQUEST_SEQ_DEF, first_request_seq_bytes
from features.roles import role_vectors

logger = logging.getLogger(__name__)


def extract(traces: list, legacy: bool = False, keep_empty: bool = False, dedup: bool = True) -> dict:
    """legacy: every connection on the agent ports instead of only those each trace opens itself
    (features/connections.py). keep_empty: a capture with no packets on the agent ports becomes
    an all-zero trace (see above) rather than a failure. dedup: each payload byte once (default);
    False keeps retransmitted segments (not in the first-request size, which is in sequence space)."""
    extractors: dict[frozenset, FeatureExtractor] = {}
    rows, first, keep, role_rows, role_y, role_trace, failed = [], [], [], [], [], [], []
    visible: list[list[str]] = []                    # per extracted trace: roles with traffic
    for i, tr in enumerate(traces):
        ports = frozenset(tr.port_role)
        ex = extractors.setdefault(ports, FeatureExtractor(agent_ports=set(ports), use_scapy=True,
                                                           own_connections=not legacy, dedup=dedup))
        try:
            packets = ex._read_pcap(tr.pcap)
        except Exception as exc:  # noqa: BLE001 — one unreadable capture must not stop the run
            failed.append({"pcap": tr.pcap.name, "reason": f"unreadable: {exc}"})
            continue
        if not packets:
            if keep_empty:
                rows.append(None)                  # all-zero vector, filled in below
                first.append(0.0)
                keep.append(i)
                visible.append([])
                continue
            failed.append({"pcap": tr.pcap.name, "reason": "no packets on the agent ports"})
            continue
        rows.append(ex._compute_features(tr.run_id, packets).flat_vector())
        first.append(first_request_seq_bytes(tr.pcap, set(ports), legacy))
        keep.append(i)
        seen = []
        for _, (role, vec, _, _) in sorted(role_vectors(ex, packets, {str(p): r for p, r in tr.port_role.items()}).items()):
            role_rows.append(vec)
            role_y.append(role)
            role_trace.append(len(keep) - 1)
            seen.append(role)
        visible.append(sorted(seen))
    dims = next((r.shape[0] for r in rows if r is not None), None)
    if dims is None:
        raise SystemExit("no capture yielded any agent traffic: check agent_endpoints and the capture filter")
    empty = sum(r is None for r in rows)
    rows = [np.zeros(dims, np.float32) if r is None else r for r in rows]
    return {
        "trace_X": np.stack(rows).astype(np.float32),
        "first_request": np.array(first, dtype=np.float32),
        "trace_index": keep,                         # into the collected traces
        "role_X": np.stack(role_rows).astype(np.float32) if role_rows else np.zeros((0, 35), np.float32),
        "role_y": np.array(role_y),
        "role_trace": np.array(role_trace, dtype=int),   # into the extracted traces
        "visible_roles": visible,                    # per extracted trace
        "summary": {"traces": len(rows), "failed": failed, "role_samples": len(role_rows),
                    "empty_traces": empty, "trace_dims": int(dims), "role_dims": 35,
                    "measurement": "all connections on the agent ports (legacy)" if legacy else
                                   "own connections: only TCP connections whose SYN is in the capture",
                    "retransmissions": "dropped: every payload byte counted once (TCP sequence numbers)"
                                       if dedup else "kept",
                    "first_request": FIRST_REQUEST_SEQ_DEF},
    }
