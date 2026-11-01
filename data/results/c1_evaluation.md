# C1 evaluation (P1)

Collection C1: deployment A, llama3.2:3b, TLS on every agent link, one session (2026-10-31T19:28:51-0700 → 2026-10-31T22:32:05-0700), 600 traces in 5 balanced rounds, 0 failed attempts. Data `data/processed_c1`, commit `fd46e23e`, seed 42.

Capture checks: TLS record check passed (1.0 handshakes per connection); median largest specialist reply chain 44 pkts (0% cut), mesh 78 pkts (0% cut), star 272 pkts (0% cut).

macro-F1 with 95% cluster-bootstrap CIs over prompt groups. Same 5 group folds for every row except the temporal holdout.

## Closed world, temporal holdout, k-FP

| Task | Chance | n (groups) | GBT | RF | k-FP | Temporal GBT | Temporal RF |
|---|---|---|---|---|---|---|---|
| role | 0.333 | 1800 (282) | 0.994 [0.989, 0.998] | 0.993 [0.989, 0.997] | 0.984 [0.977, 0.991] | 0.985 [0.974, 0.993] | 0.985 [0.975, 0.994] |
| workflow | 0.250 | 600 (282) | 0.626 [0.572, 0.672] | 0.606 [0.557, 0.650] | 0.516 [0.465, 0.565] | 0.441 [0.365, 0.522] | 0.463 [0.380, 0.548] |
| topology | 0.333 | 600 (282) | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 0.998 [0.995, 1.000] | 0.979 [0.959, 0.996] | 0.987 [0.971, 1.000] |

Temporal holdout: train rounds 1–3, test rounds 4–5; training traces whose prompt occurs in the test rounds are removed.

Removing those prompts shrinks training, so the size-matched CV trains each fold on random whole prompt groups up to the same number of traces, with no time gap: the gap between the two is what drift could add beyond training size. Conditions are interleaved within rounds, so drift cannot correlate with labels.

| Task | Train (after / before prompt removal) | Test | Temporal GBT | Size-matched CV GBT | Temporal RF | Size-matched CV RF |
|---|---|---|---|---|---|---|
| role | 507 / 1080 | 720 | 0.985 [0.974, 0.993] | 0.986 [0.979, 0.991] | 0.985 [0.975, 0.994] | 0.989 [0.983, 0.995] |
| workflow | 169 / 360 | 240 | 0.441 [0.365, 0.522] | 0.525 [0.468, 0.576] | 0.463 [0.380, 0.548] | 0.535 [0.482, 0.582] |
| topology | 169 / 360 | 240 | 0.979 [0.959, 0.996] | 0.998 [0.995, 1.000] | 0.987 [0.971, 1.000] | 0.997 [0.990, 1.000] |

## Paired differences (GBT minus …)

| Task | GBT − RF | GBT − k-FP |
|---|---|---|
| role | +0.001 [-0.002, +0.003] (n.s.) | +0.010 [+0.005, +0.015] |
| workflow | +0.020 [-0.010, +0.049] (n.s.) | +0.110 [+0.062, +0.164] |
| topology | +0.000 [+0.000, +0.000] (n.s.) | +0.002 [+0.000, +0.005] (n.s.) |

## Feature ablation (GBT, same folds)

| Task | All | sizes only | timing only | counts and direction only |
|---|---|---|---|---|
| role | 0.994 [0.989, 0.998] | 0.978 [0.971, 0.985] (26 dims) | 0.920 [0.907, 0.932] (5 dims) | 0.744 [0.723, 0.764] (4 dims) |
| workflow | 0.626 [0.572, 0.672] | 0.617 [0.570, 0.663] (139 dims) | 0.477 [0.428, 0.521] (30 dims) | 0.291 [0.253, 0.329] (26 dims) |
| topology | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] (139 dims) | 0.998 [0.995, 1.000] (30 dims) | 1.000 [1.000, 1.000] (26 dims) |

Drop from all features to one family (paired, all − family):

| Task | sizes | timing | counts_direction |
|---|---|---|---|
| role | +0.016 [+0.010, +0.022] | +0.074 [+0.062, +0.086] | +0.250 [+0.230, +0.271] |
| workflow | +0.009 [-0.016, +0.038] (n.s.) | +0.149 [+0.103, +0.197] | +0.334 [+0.281, +0.386] |
| topology | +0.000 [+0.000, +0.000] (n.s.) | +0.002 [+0.000, +0.005] (n.s.) | +0.000 [+0.000, +0.000] (n.s.) |

Per-flow vs system aggregates (GBT, same folds; trace tasks only — a role sample is one flow). Per-flow = mean, heaviest and second-heaviest flow (105 dims); system = system-wide aggregates (90 dims).

| Task | Per-flow only | System only | All − per-flow | All − system |
|---|---|---|---|---|
| workflow | 0.592 [0.539, 0.642] | 0.617 [0.559, 0.668] | +0.034 [+0.001, +0.068] | +0.009 [-0.022, +0.037] (n.s.) |
| topology | 0.990 [0.982, 0.997] | 0.998 [0.995, 1.000] | +0.010 [+0.003, +0.018] | +0.002 [+0.000, +0.005] (n.s.) |

## Learning curve (GBT, same folds, training cut to whole prompt groups)

Share of each fold's training set; each cell gives the training traces per class.

| Task | 10% | 25% | 50% | 75% | 100% |
|---|---|---|---|---|---|
| role | 0.964 [0.955, 0.973] (48/class) | 0.977 [0.969, 0.985] (120/class) | 0.989 [0.983, 0.995] (240/class) | 0.992 [0.986, 0.997] (360/class) | 0.994 [0.989, 0.998] (480/class) |
| workflow | 0.391 [0.344, 0.438] (12/class) | 0.541 [0.482, 0.592] (30/class) | 0.564 [0.514, 0.609] (60/class) | 0.605 [0.556, 0.649] (90/class) | 0.626 [0.572, 0.672] (120/class) |
| topology | 0.963 [0.944, 0.980] (16/class) | 0.992 [0.982, 0.999] (40/class) | 0.998 [0.994, 1.000] (80/class) | 0.998 [0.994, 1.000] (120/class) | 1.000 [1.000, 1.000] (160/class) |

## Workflow detail (GBT closed-world predictions)

Confusion matrix, rows = true, columns = predicted (count, row share):

| True (row) / predicted (column) | code_review | data_analysis | research_retrieval | support_triage |
|---|---|---|---|---|
| code_review | 105 (70%) | 12 (8%) | 22 (15%) | 11 (7%) |
| data_analysis | 13 (9%) | 122 (81%) | 10 (7%) | 5 (3%) |
| research_retrieval | 26 (17%) | 5 (3%) | 64 (43%) | 55 (37%) |
| support_triage | 14 (9%) | 2 (1%) | 50 (33%) | 84 (56%) |

Workflow macro-F1 on each topology's traces (same predictions, sliced):

| Topology | n (groups) | macro-F1 |
|---|---|---|
| chain | 200 (145) | 0.607 [0.528, 0.676] |
| mesh | 200 (140) | 0.639 [0.564, 0.704] |
| star | 200 (144) | 0.628 [0.563, 0.691] |

Per-workflow F1, C1 vs the TLS control's TLS arm (its within-TLS CV recomputed with the same folds; pooled macro-F1 0.730 [0.675, 0.779], where tls_control.json gives the mean of the five fold scores). Difference CIs come from independent group bootstraps.

| Workflow | C1 F1 | C1 P / R | TLS arm F1 | TLS arm P / R | C1 − TLS arm |
|---|---|---|---|---|---|
| code_review | 0.682 [0.546, 0.785] | 0.66 / 0.70 | 0.689 [0.562, 0.785] | 0.71 / 0.67 | -0.007 [-0.163, +0.159] (n.s.) |
| data_analysis | 0.838 [0.781, 0.888] | 0.87 / 0.81 | 0.804 [0.733, 0.861] | 0.79 / 0.81 | +0.035 [-0.047, +0.123] (n.s.) |
| research_retrieval | 0.432 [0.351, 0.506] | 0.44 / 0.43 | 0.768 [0.670, 0.841] | 0.79 / 0.75 | -0.335 [-0.444, -0.212] |
| support_triage | 0.551 [0.466, 0.626] | 0.54 / 0.56 | 0.658 [0.571, 0.739] | 0.63 / 0.69 | -0.107 [-0.227, +0.008] (n.s.) |

Prompt mix (prompt_group = sha1 of the prompt). TV = total-variation distance between the two sets' prompt frequencies (0 = same mix, 1 = disjoint).

| Workflow | Traces C1 / TLS | Distinct prompts C1 / TLS | Shared distinct | C1 traces with a shared prompt | TLS traces with a shared prompt | TV | Median prompt chars C1 / TLS |
|---|---|---|---|---|---|---|---|
| code_review | 150 / 108 | 51 / 49 | 37 | 82% | 83% | 0.38 | 5059 / 5059 |
| data_analysis | 150 / 108 | 74 / 69 | 52 | 69% | 75% | 0.46 | 3902 / 4083 |
| research_retrieval | 150 / 108 | 62 / 42 | 34 | 72% | 89% | 0.38 | 127.5 / 133 |
| support_triage | 150 / 108 | 95 / 71 | 45 | 50% | 70% | 0.60 | 222 / 224 |

C1 workflow macro-F1 on traces whose prompt also occurs in the TLS arm: 0.628 [0.564, 0.688] (n = 409); on C1-only prompts: 0.585 [0.505, 0.655] (n = 191).

## Workflow: input length and response side (GBT, same folds)

First request into the system: TCP payload bytes of the first request message that reaches an agent (the caller → orchestrator link is not captured): on the agent link whose first post-handshake request starts earliest, the request-direction writes ≤ 50 ms apart, TLS ClientHello and client Finished excluded; from headers only. Pearson r with the true prompt length 0.996; 0 traces without one.

| Features | Dims | macro-F1 | All − this |
|---|---|---|---|
| all | 195 | 0.626 [0.572, 0.672] | — |
| first-request size only | 1 | 0.641 [0.589, 0.687] | -0.016 [-0.067, +0.040] (n.s.) |
| true prompt length only (not observable) | 1 | 0.928 [0.869, 0.975] | -0.302 [-0.363, -0.244] |
| response side only (no request-byte sizes) | 81 | 0.481 [0.435, 0.522] | +0.145 [+0.101, +0.191] |

| Workflow | Median first request (B) | Median prompt (chars) | Median first request − prompt |
|---|---|---|---|
| code_review | 6175.5 | 5059 | 1178 |
| data_analysis | 4976 | 3902 | 1012 |
| research_retrieval | 1371 | 127.5 | 1178 |
| support_triage | 1271.5 | 222 | 1020.5 |

Within-length pairs (binary, the same folds restricted to the pair, chance 0.5):

| Pair | n | All features | First-request size only | Prompt length only | All − first request | All − prompt length |
|---|---|---|---|---|---|---|
| code_review vs data_analysis | 300 | 0.893 [0.850, 0.929] | 0.903 [0.859, 0.943] | 0.957 [0.914, 0.993] | -0.010 [-0.054, +0.033] (n.s.) | -0.063 [-0.118, -0.010] |
| research_retrieval vs support_triage | 300 | 0.577 [0.501, 0.640] | 0.571 [0.472, 0.660] | 1.000 [1.000, 1.000] | +0.005 [-0.076, +0.093] (n.s.) | -0.423 [-0.499, -0.360] |

## Role: single features and one direction's sizes (GBT, same folds)

Each of the 35 per-flow features alone; the top 5 are shown with CIs (top 5 chosen on these folds out of 35 features, so their scores are optimistic). Response = agent → caller, request = caller → agent.

| Features | macro-F1 | All − this |
|---|---|---|
| all 35 | 0.994 [0.989, 0.998] | — |
| cumul_bytes_q8 only | 0.842 [0.821, 0.861] | +0.152 [+0.133, +0.173] |
| cumul_bytes_q5 only | 0.793 [0.777, 0.809] | +0.201 [+0.185, +0.217] |
| cumul_bytes_q4 only | 0.782 [0.764, 0.800] | +0.211 [+0.193, +0.230] |
| cumul_bytes_q7 only | 0.777 [0.752, 0.801] | +0.217 [+0.192, +0.242] |
| std_iat only | 0.744 [0.726, 0.765] | +0.250 [+0.230, +0.268] |
| response-side sizes only (bytes_out, mean_sz_out, std_sz_out, p25_sz_out, p75_sz_out) | 0.796 [0.778, 0.814] | +0.198 [+0.180, +0.215] |
| request-side sizes only (bytes_in, mean_sz_in, std_sz_in, p25_sz_in, p75_sz_in, n_small_inbound, iqr_size_in) | 0.685 [0.659, 0.711] | +0.309 [+0.283, +0.334] |

All single features: cumul_bytes_q8 0.842, cumul_bytes_q5 0.793, cumul_bytes_q4 0.782, cumul_bytes_q7 0.777, std_iat 0.744, cumul_bytes_q6 0.729, n_bursts 0.712, cumul_bytes_q3 0.694, n_small_inbound 0.624, cumul_bytes_q2 0.624, n_pkts_in 0.608, std_sz_out 0.602, bytes_out 0.584, mean_sz_out 0.577, n_pkts_out 0.571, mean_burst_dur 0.564, mean_burst_bytes 0.561, n_response_bursts 0.561, cumul_bytes_q1 0.544, std_sz_in 0.542, p25_sz_out 0.538, bytes_out_ratio 0.538, mean_ibg 0.537, mean_iat 0.527, std_burst_bytes 0.524, mean_sz_in 0.519, bytes_in 0.514, pkt_size_asymmetry 0.511, p75_sz_out 0.461, duration_s 0.445, cumul_bytes_q9 0.431, cumul_bytes_q0 0.419, p25_sz_in 0.167, p75_sz_in 0.167, iqr_size_in 0.167.

k-FP: 138 features from packet direction and timing only (Hayes & Danezis 2016), RandomForest, 1000 trees (k-FP closed world).
