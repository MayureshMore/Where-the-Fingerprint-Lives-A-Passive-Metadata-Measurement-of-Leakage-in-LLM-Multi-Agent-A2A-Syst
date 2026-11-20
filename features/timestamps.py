"""
Timestamps-only features: what an observer learns from when packets pass, with no packet size and no
direction.

The trace vector's timing family (features/families.py) is broader. Its per-flow blocks come from the
mean flow and from the heaviest and second-heaviest flow, chosen by bytes; its burst features split
packets at changes of direction; and its inter-arrival times run over a packet sequence whose length
follows the bytes sent (TCP segments of at most one MSS). This family keeps only timestamps:

    flows           the TCP connections in view, ordered by their first packet (first, second, third),
                    not by bytes; a flow that is not there is all zeros
    per flow        start (s after the trace's first packet), duration, and the gaps between
                    consecutive packets of either direction: mean, std, median, 90th percentile and
                    maximum, and how many exceed 0.05 s, 0.5 s and 2 s (counts of idle time)
    whole trace     duration, the gaps over all packets as above, and the time from the first flow's
                    start to the last flow's start

Packets still count implicitly: a gap statistic over more packets differs from one over fewer, and a
larger message takes more packets. A timestamp is all this family reads per packet.
"""

from __future__ import annotations

import numpy as np

N_FLOWS = 3
GAP_THRESHOLDS = (0.05, 0.5, 2.0)
_GAP_NAMES = ["gap_mean", "gap_std", "gap_median", "gap_p90", "gap_max"] + [f"gaps_over_{t}s" for t in GAP_THRESHOLDS]
FLOW_NAMES = ["start", "duration", *_GAP_NAMES]
TRACE_NAMES = ["duration", *_GAP_NAMES, "flow_start_span"]


def _gaps(ts: np.ndarray) -> list[float]:
    if len(ts) < 2:
        return [0.0] * len(_GAP_NAMES)
    d = np.diff(np.sort(ts))
    return [float(d.mean()), float(d.std()), float(np.median(d)), float(np.percentile(d, 90)), float(d.max()),
            *(float((d > t).sum()) for t in GAP_THRESHOLDS)]


def names() -> list[str]:
    return [f"flow{k + 1}_{n}" for k in range(N_FLOWS) for n in FLOW_NAMES] + [f"trace_{n}" for n in TRACE_NAMES]


def timestamp_vector(packets: list) -> np.ndarray:
    """packets: (timestamp, size, flow_key, direction) as features.extractor reads them; only the
    timestamp and the flow key are used."""
    out = np.zeros(len(names()), np.float32)
    if not packets:
        return out
    flows: dict[str, list[float]] = {}
    for ts, _size, key, _direction in packets:
        flows.setdefault(key, []).append(float(ts))
    ordered = sorted((np.sort(np.array(v)) for v in flows.values()), key=lambda t: t[0])
    t0 = ordered[0][0]
    w = len(FLOW_NAMES)
    for k, ts in enumerate(ordered[:N_FLOWS]):
        out[k * w:(k + 1) * w] = [ts[0] - t0, ts[-1] - ts[0], *_gaps(ts)]
    every = np.sort(np.concatenate(ordered))
    out[N_FLOWS * w:] = [every[-1] - every[0], *_gaps(every), ordered[-1][0] - t0]
    return out
