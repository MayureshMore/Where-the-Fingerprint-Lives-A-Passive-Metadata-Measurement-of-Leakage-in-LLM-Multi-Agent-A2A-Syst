# Capture tail lost by the old recorder: feature sensitivity (paper 1)

Commit `d6f059c2` (dirty: False). Data: `data/raw_c1_tailcheck` (12 C1-style traces, re-collected Nov 9 with the old recorder and a ground-truth capture in immediate mode).

Packets lost per trace: 2, 5, 2, 2, 5, 5, 2, 4, 2, 2, 4, 2 (median share 0.7%).

## Paper 1's 35 per-connection features (36 role samples)

Features that change at all: 27 of 35.

| Feature | Samples changed | Largest relative change | Median when changed |
|---|---|---|---|
| cumul_bytes_q6 | 6 of 36 | 94.02% | 92.78% |
| cumul_bytes_q7 | 10 of 36 | 94.02% | 74.14% |
| cumul_bytes_q8 | 14 of 36 | 78.86% | 68.56% |
| cumul_bytes_q5 | 3 of 36 | 77.62% | 70.62% |
| duration_s | 16 of 36 | 33.37% | 21.34% |
| mean_ibg | 16 of 36 | 32.76% | 19.47% |
| mean_iat | 16 of 36 | 32.74% | 19.61% |
| p25_sz_out | 10 of 36 | 17.91% | 5.03% |
| std_iat | 16 of 36 | 12.17% | 2.50% |
| std_sz_out | 16 of 36 | 3.09% | 2.41% |
| n_small_inbound | 16 of 36 | 2.47% | 2.13% |
| mean_burst_dur | 16 of 36 | 2.41% | 1.97% |
| n_response_bursts | 16 of 36 | 2.38% | 1.65% |
| n_bursts | 16 of 36 | 2.35% | 1.93% |
| n_pkts_in | 16 of 36 | 2.27% | 1.96% |
| n_pkts_out | 16 of 36 | 2.17% | 1.52% |
| mean_burst_bytes | 16 of 36 | 2.02% | 1.67% |
| mean_sz_out | 16 of 36 | 1.97% | 1.37% |
| mean_sz_in | 16 of 36 | 1.70% | 0.91% |
| bytes_in | 16 of 36 | 1.19% | 0.68% |
| std_sz_in | 16 of 36 | 1.11% | 0.95% |
| std_burst_bytes | 16 of 36 | 0.82% | 0.20% |
| cumul_bytes_q9 | 16 of 36 | 0.41% | 0.28% |
| bytes_out | 16 of 36 | 0.25% | 0.17% |
| pkt_size_asymmetry | 16 of 36 | 0.20% | 0.11% |
| bytes_out_ratio | 16 of 36 | 0.16% | 0.11% |
| p75_sz_out | 3 of 36 | 0.04% | 0.04% |

Unchanged in every sample: p25_sz_in, p75_sz_in, cumul_bytes_q0, cumul_bytes_q1, cumul_bytes_q2, cumul_bytes_q3, cumul_bytes_q4, iqr_size_in.

## The 195 trace features

148 of 195 change in at least one of the 12 traces; largest relative change 100.00%. The ten largest:

| Feature | Traces changed | Largest relative change | Median when changed |
|---|---|---|---|
| sys.pf_std_n_pkts_out | 12 of 12 | 100.00% | 1.89% |
| sys.pf_std_n_pkts_in | 12 of 12 | 100.00% | 2.64% |
| sys.pf_std_p25_sz_out | 8 of 12 | 100.00% | 15.77% |
| sys.pf_std_p75_sz_out | 4 of 12 | 100.00% | 22.88% |
| sys.pf_std_n_bursts | 12 of 12 | 100.00% | 2.31% |
| sys.pf_std_n_small_inbound | 12 of 12 | 100.00% | 2.89% |
| sys.pf_std_n_response_bursts | 12 of 12 | 100.00% | 1.98% |
| sys.flow_end_spread | 12 of 12 | 99.98% | 99.90% |
| sys.pf_std_duration_s | 12 of 12 | 99.98% | 25.33% |
| sys.pf_std_std_sz_out | 12 of 12 | 99.45% | 10.34% |

Features with at most 5% change in every trace: 127 of 195.
