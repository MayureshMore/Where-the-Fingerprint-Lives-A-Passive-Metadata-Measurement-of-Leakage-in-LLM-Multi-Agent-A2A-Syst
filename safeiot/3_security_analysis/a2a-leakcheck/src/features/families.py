"""
Feature families of the flat feature vectors, for ablations and leak attribution.

Indices refer to the 35-dim per-flow vector (role samples: one flow per sample) and the 195-dim
trace vector: per-flow blocks for the mean, heaviest and second-heaviest flow at 0/35/70, the
20 system scalars at 105, and the system-wide mean/std of the per-flow vector at 125/160.

Direction (features/extractor.py): "out" = agent → caller (response), "in" = caller → agent
(request).
"""

from __future__ import annotations

import numpy as np

from features.per_flow import PerFlowFeatures
from features.per_system import PerSystemFeatures

_PF_SIZES = {"bytes_out", "bytes_in", "mean_sz_out", "std_sz_out", "p25_sz_out", "p75_sz_out",
             "mean_sz_in", "std_sz_in", "p25_sz_in", "p75_sz_in", "mean_burst_bytes",
             "std_burst_bytes", "bytes_out_ratio", "pkt_size_asymmetry", "n_small_inbound",
             "iqr_size_in"} | {f"cumul_bytes_q{i}" for i in range(10)}
_PF_TIMING = {"duration_s", "mean_iat", "std_iat", "mean_burst_dur", "mean_ibg"}
_PF_COUNTS = {"n_pkts_out", "n_pkts_in", "n_bursts", "n_response_bursts"}
_SYS_SIZES = {"total_bytes", "bytes_out_ratio", "heaviest_flow_bytes_frac", "flow_bytes_cv",
              "n_response_heavy_flows", "mean_flow_response_ratio", "max_flow_bytes_out_ratio",
              "min_flow_bytes_out_ratio", "max_flow_bytes_in"}
_SYS_TIMING = {"total_duration_s", "flow_start_spread", "flow_end_spread", "max_concurrent_flows",
               "mean_burst_rate"}
_SYS_COUNTS = {"n_flows", "n_src_hosts", "n_dst_hosts", "n_host_pairs", "total_packets",
               "total_bursts"}
FAMILIES = {"sizes": (_PF_SIZES, _SYS_SIZES), "timing": (_PF_TIMING, _SYS_TIMING),
            "counts_direction": (_PF_COUNTS, _SYS_COUNTS)}
# Response-side check: drop every size feature that uses request bytes, including the
# mixed ones (ratios, totals, cumulative bytes, burst bytes); keep response sizes, timing, counts.
_PF_RESPONSE_SIZES = {"bytes_out", "mean_sz_out", "std_sz_out", "p25_sz_out", "p75_sz_out"}
_PF_REQUEST_SIZES = {"bytes_in", "mean_sz_in", "std_sz_in", "p25_sz_in", "p75_sz_in", "iqr_size_in",
                     "n_small_inbound"}


def family_columns(family: str, role: bool) -> np.ndarray:
    """Column indices of one feature family in the role (35) or trace (195) flat vector."""
    return _columns(*FAMILIES[family], role)


def response_side_columns() -> np.ndarray:
    """Trace columns left after removing every size feature that uses request-direction bytes."""
    keep_pf = _PF_TIMING | _PF_COUNTS | _PF_RESPONSE_SIZES
    return _columns(keep_pf, _SYS_TIMING | _SYS_COUNTS, False)


def _columns(pf_set: set, sys_set: set, role: bool) -> np.ndarray:
    pf_names = PerFlowFeatures.FEATURE_NAMES()
    sys_names = PerSystemFeatures.FEATURE_NAMES()[:20]
    pf_idx = [i for i, n in enumerate(pf_names) if n in pf_set]
    if role:
        return np.array(pf_idx)
    cols = [b + i for b in (0, 35, 70, 125, 160) for i in pf_idx]   # pf blocks + sys pf mean/std
    cols += [105 + i for i, n in enumerate(sys_names) if n in sys_set]
    return np.array(sorted(cols))


def _check_partition() -> None:
    pf = set(PerFlowFeatures.FEATURE_NAMES())
    sysn = set(PerSystemFeatures.FEATURE_NAMES()[:20])
    fams = list(FAMILIES.values())
    assert set().union(*(f[0] for f in fams)) == pf and sum(len(f[0]) for f in fams) == len(pf)
    assert set().union(*(f[1] for f in fams)) == sysn and sum(len(f[1]) for f in fams) == len(sysn)
