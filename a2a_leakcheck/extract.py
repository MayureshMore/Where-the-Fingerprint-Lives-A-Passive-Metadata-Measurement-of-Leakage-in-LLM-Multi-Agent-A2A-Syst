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
observer sees nothing is the observation. Such a trace is counted as expected silent when its
sidecar says the task was not escalated and the view sees only cloud agents (the agents the
collection's sidecars name as cloud_role), and as unexpectedly empty otherwise: a call its sidecar
says was made, or nothing to say either way, so the capture or its filter may have missed traffic.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

from features.extractor import FeatureExtractor
from features.first_request import FIRST_REQUEST_SEQ_DEF, first_request_seq_bytes
from features.roles import role_vectors

logger = logging.getLogger(__name__)

# Bump when a feature's definition or the vector layout changes: reports with different schema versions
# are not compared (report.compatibility). 1: the 195-dim trace vector, 35-dim role vector and the
# first-request size in TCP sequence space (first_request_seq), as of a2a-leakcheck 0.1.0.
FEATURE_SCHEMA_VERSION = 1
FEATURES_NPZ, FEATURES_JSON = "features.npz", "features.json"
ARRAYS = ("trace_X", "first_request", "role_X", "role_y", "role_trace")


def _by_port(item: tuple) -> tuple:
    """Role samples in the order of their agent port (as text, as before keys carried the host), then host."""
    key = item[0]
    return key.rsplit(":", 1)[-1], key


def expected_silent(tr, cloud: set) -> bool:
    """A trace with nothing in view whose sidecar says so: not escalated, and every endpoint in view is a
    cloud agent (cloud: the cloud_role values of the collection's escalated traces)."""
    in_view = set(getattr(tr, "endpoints", {}).values()) or set(tr.port_role.values())
    return getattr(tr, "escalated", None) is False and bool(cloud) and in_view <= cloud


def extract(traces: list, legacy: bool = False, keep_empty: bool = False, dedup: bool = True) -> dict:
    """legacy: every connection on the agent ports instead of only those each trace opens itself
    (features/connections.py). keep_empty: a capture with no packets on the agent ports becomes
    an all-zero trace (see above) rather than a failure. dedup: each payload byte once (default);
    False keeps retransmitted segments (not in the first-request size, which is in sequence space)."""
    extractors: dict[frozenset, FeatureExtractor] = {}
    rows, first, keep, role_rows, role_y, role_trace, failed = [], [], [], [], [], [], []
    visible: list[list[str]] = []                    # per extracted trace: roles with traffic
    cloud = {t.cloud_role for t in traces if getattr(t, "cloud_role", None)}
    silent, unexpected = 0, []
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
                if expected_silent(tr, cloud):
                    silent += 1
                else:
                    unexpected.append(tr.run_id)
                continue
            failed.append({"pcap": tr.pcap.name, "reason": "no packets on the agent ports"})
            continue
        rows.append(ex._compute_features(tr.run_id, packets).flat_vector())
        first.append(first_request_seq_bytes(tr.pcap, set(ports), legacy, tls=getattr(tr, "tls", True)))
        keep.append(i)
        seen = []
        keys = getattr(tr, "role_keys", None) or {str(p): r for p, r in tr.port_role.items()}
        for _, (role, vec, _, _) in sorted(role_vectors(ex, packets, keys).items(), key=_by_port):
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
        "summary": {"schema_version": FEATURE_SCHEMA_VERSION, "traces": len(rows), "failed": failed,
                    "role_samples": len(role_rows),
                    "empty_traces": empty, "empty_expected_silent": silent, "empty_unexpected": len(unexpected),
                    "empty_unexpected_runs": unexpected[:20],
                    "trace_dims": int(dims), "role_dims": 35,
                    "measurement": "all connections on the agent ports (legacy)" if legacy else
                                   "own connections: only TCP connections whose SYN is in the capture",
                    "retransmissions": "dropped: every payload byte counted once (TCP sequence numbers)"
                                       if dedup else "kept",
                    "first_request": FIRST_REQUEST_SEQ_DEF,
                    **({"first_request_cleartext": f"{n} traces without TLS: no handshake skipped, the request starts "
                                                   "at the first client byte"}
                       if (n := sum(not getattr(t, "tls", True) for t in traces)) else {})},
    }


def save_features(folder: Path, col: dict, ext: dict, traces: list, meta: dict) -> None:
    """Stage 2's output (`leakcheck extract`): the feature arrays (features.npz) and what the analysis
    needs besides them (features.json): per trace its run id, group, topology, labels and the padding
    facts the rules read, which agents carry traffic, and the collection and extraction summaries."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(folder / FEATURES_NPZ, **{k: ext[k] for k in ARRAYS})
    rows = [{"run_id": t.run_id, "group": t.group, "group_source": t.group_source, "topology": t.topology,
             "labels": t.labels, "padded": t.padded, "unpadded_in_view": list(t.unpadded_in_view), "tls": t.tls}
            for t in traces]
    (folder / FEATURES_JSON).write_text(json.dumps({
        **meta, "schema_version": FEATURE_SCHEMA_VERSION, "collection": col["summary"],
        "extraction": ext["summary"], "visible_roles": ext["visible_roles"], "traces": rows}, indent=1))


def is_features(folder: Path) -> bool:
    return (Path(folder) / FEATURES_JSON).exists() and (Path(folder) / FEATURES_NPZ).exists()


def load_features(folder: Path) -> tuple[dict, dict, list, dict]:
    """(collection summary, extraction dict as extract() returns it, traces, metadata) from save_features()."""
    from a2a_leakcheck.collect import Trace
    folder = Path(folder)
    meta = json.loads((folder / FEATURES_JSON).read_text())
    if meta.get("schema_version") != FEATURE_SCHEMA_VERSION:
        raise SystemExit(f"{folder}: feature schema {meta.get('schema_version')}, this a2a-leakcheck reads "
                         f"{FEATURE_SCHEMA_VERSION}: extract the captures again")
    with np.load(folder / FEATURES_NPZ, allow_pickle=False) as z:
        ext = {k: z[k] for k in ARRAYS}
    traces = [Trace(run_id=r["run_id"], pcap=Path(r["run_id"]), port_role={}, labels=r["labels"],
                    group=r["group"], group_source=r["group_source"], topology=r["topology"],
                    padded=r["padded"], unpadded_in_view=tuple(r["unpadded_in_view"]), tls=r["tls"])
              for r in meta["traces"]]
    ext.update(trace_index=list(range(len(traces))), visible_roles=meta["visible_roles"], summary=meta["extraction"])
    return meta["collection"], ext, traces, meta
