# C1 evaluation (P1)

Collection C1: deployment A, llama3.2:3b, TLS on every agent link, one session (2026-10-31T19:28:51-0700 → 2026-10-31T22:32:05-0700), 600 traces in 5 balanced rounds, 0 failed attempts. Data `data/processed_c1_own`, commit `da31192a`, seed 42. Measurement: own connections: only TCP connections whose SYN is in the trace (features/connections.py).

Capture checks: TLS record check passed (1.0 handshakes per connection); median largest specialist reply chain 44 pkts (0% cut), mesh 78 pkts (0% cut), star 272 pkts (0% cut).

macro-F1 with 95% cluster-bootstrap CIs over prompt groups. Same 5 group folds for every row except the temporal holdout.

## Closed world, temporal holdout, k-FP

| Task | Chance | n (groups) | GBT | RF | k-FP | Temporal GBT | Temporal RF |
|---|---|---|---|---|---|---|---|
| role | 0.333 | 1800 (282) | 0.994 [0.990, 0.997] | 0.997 [0.993, 0.999] | 0.991 [0.985, 0.995] | 0.993 [0.986, 0.998] | 0.990 [0.982, 0.996] |
| workflow | 0.250 | 600 (282) | 0.660 [0.613, 0.703] | 0.624 [0.572, 0.669] | 0.515 [0.462, 0.563] | 0.473 [0.399, 0.553] | 0.505 [0.425, 0.587] |
| topology | 0.333 | 600 (282) | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 0.998 [0.995, 1.000] | 0.979 [0.960, 0.996] | 0.987 [0.971, 1.000] |

Temporal holdout: train rounds 1–3, test rounds 4–5; training traces whose prompt occurs in the test rounds are removed.

Removing those prompts shrinks training, so the size-matched CV trains each fold on random whole prompt groups up to the same number of traces, with no time gap: the gap between the two is what drift could add beyond training size. Conditions are interleaved within rounds, so drift cannot correlate with labels.

| Task | Train (after / before prompt removal) | Test | Temporal GBT | Size-matched CV GBT | Temporal RF | Size-matched CV RF |
|---|---|---|---|---|---|---|
| role | 507 / 1080 | 720 | 0.993 [0.986, 0.998] | 0.987 [0.981, 0.993] | 0.990 [0.982, 0.996] | 0.991 [0.986, 0.996] |
| workflow | 169 / 360 | 240 | 0.473 [0.399, 0.553] | 0.550 [0.497, 0.599] | 0.505 [0.425, 0.587] | 0.571 [0.519, 0.616] |
| topology | 169 / 360 | 240 | 0.979 [0.960, 0.996] | 0.998 [0.995, 1.000] | 0.987 [0.971, 1.000] | 0.998 [0.995, 1.000] |

## Paired differences (GBT minus …)

| Task | GBT − RF | GBT − k-FP |
|---|---|---|
| role | -0.003 [-0.005, -0.001] | +0.003 [-0.001, +0.007] (n.s.) |
| workflow | +0.036 [+0.002, +0.070] | +0.145 [+0.099, +0.196] |
| topology | +0.000 [+0.000, +0.000] (n.s.) | +0.002 [+0.000, +0.005] (n.s.) |

## Feature ablation (GBT, same folds)

| Task | All | sizes only | timing only | counts and direction only |
|---|---|---|---|---|
| role | 0.994 [0.990, 0.997] | 0.933 [0.920, 0.945] (26 dims) | 0.981 [0.973, 0.988] (5 dims) | 0.696 [0.670, 0.723] (4 dims) |
| workflow | 0.660 [0.613, 0.703] | 0.664 [0.614, 0.708] (139 dims) | 0.464 [0.415, 0.508] (30 dims) | 0.303 [0.264, 0.339] (26 dims) |
| topology | 1.000 [1.000, 1.000] | 0.998 [0.994, 1.000] (139 dims) | 1.000 [1.000, 1.000] (30 dims) | 1.000 [1.000, 1.000] (26 dims) |

Drop from all features to one family (paired, all − family):

| Task | sizes | timing | counts_direction |
|---|---|---|---|
| role | +0.061 [+0.049, +0.074] | +0.013 [+0.007, +0.020] | +0.298 [+0.272, +0.324] |
| workflow | -0.004 [-0.032, +0.025] (n.s.) | +0.196 [+0.154, +0.241] | +0.356 [+0.303, +0.406] |
| topology | +0.002 [+0.000, +0.006] (n.s.) | +0.000 [+0.000, +0.000] (n.s.) | +0.000 [+0.000, +0.000] (n.s.) |

Per-flow vs system aggregates (GBT, same folds; trace tasks only — a role sample is one flow). Per-flow = mean, heaviest and second-heaviest flow (105 dims); system = system-wide aggregates (90 dims).

| Task | Per-flow only | System only | All − per-flow | All − system |
|---|---|---|---|---|
| workflow | 0.597 [0.545, 0.644] | 0.660 [0.611, 0.707] | +0.063 [+0.034, +0.093] | -0.001 [-0.023, +0.024] (n.s.) |
| topology | 0.997 [0.991, 1.000] | 0.998 [0.995, 1.000] | +0.003 [+0.000, +0.009] (n.s.) | +0.002 [+0.000, +0.005] (n.s.) |

## Learning curve (GBT, same folds, training cut to whole prompt groups)

Share of each fold's training set; each cell gives the training traces per class.

| Task | 10% | 25% | 50% | 75% | 100% |
|---|---|---|---|---|---|
| role | 0.970 [0.961, 0.978] (48/class) | 0.983 [0.976, 0.989] (120/class) | 0.990 [0.984, 0.995] (240/class) | 0.992 [0.987, 0.996] (360/class) | 0.994 [0.990, 0.997] (480/class) |
| workflow | 0.426 [0.378, 0.471] (12/class) | 0.532 [0.470, 0.589] (30/class) | 0.592 [0.543, 0.636] (60/class) | 0.650 [0.602, 0.694] (90/class) | 0.660 [0.613, 0.703] (120/class) |
| topology | 0.983 [0.972, 0.994] (16/class) | 0.990 [0.980, 0.998] (40/class) | 0.998 [0.994, 1.000] (80/class) | 0.998 [0.994, 1.000] (120/class) | 1.000 [1.000, 1.000] (160/class) |

## Sensitivity: own connections vs all connections

Own connections: `data/processed_c1_own`; all connections (earlier measurement): `data/processed_c1`. Same samples and folds; paired differences own − all. 351 of 600 traces contained packets of connections opened before the capture (2882 packets; median 6 when present). The first request moved to another link in 0 traces and changed size in 0.

| Task | Measure | All connections | Own connections | Own − all |
|---|---|---|---|---|
| role | GBT | 0.994 [0.989, 0.998] | 0.994 [0.990, 0.997] | +0.000 [-0.003, +0.003] (n.s.) |
| role | RF | 0.993 [0.989, 0.997] | 0.997 [0.993, 0.999] | +0.003 [+0.001, +0.006] |
| workflow | GBT | 0.626 [0.572, 0.672] | 0.660 [0.613, 0.703] | +0.034 [-0.000, +0.066] (n.s.) |
| workflow | RF | 0.606 [0.557, 0.650] | 0.624 [0.572, 0.669] | +0.018 [-0.015, +0.051] (n.s.) |
| workflow | first request only (GBT) | 0.641 [0.589, 0.687] | 0.641 [0.589, 0.687] | +0.000 [+0.000, +0.000] (n.s.) |
| workflow | response side only (GBT) | 0.481 [0.435, 0.522] | 0.469 [0.422, 0.514] | -0.012 [-0.046, +0.023] (n.s.) |
| topology | GBT | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] (n.s.) |
| topology | RF | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] (n.s.) |
| topology | first request only (GBT) | 0.308 [0.273, 0.344] | 0.308 [0.273, 0.344] | +0.000 [+0.000, +0.000] (n.s.) |

## Workflow detail (GBT closed-world predictions)

Confusion matrix, rows = true, columns = predicted (count, row share):

| True (row) / predicted (column) | code_review | data_analysis | research_retrieval | support_triage |
|---|---|---|---|---|
| code_review | 109 (73%) | 9 (6%) | 18 (12%) | 14 (9%) |
| data_analysis | 13 (9%) | 132 (88%) | 3 (2%) | 2 (1%) |
| research_retrieval | 24 (16%) | 3 (2%) | 72 (48%) | 51 (34%) |
| support_triage | 15 (10%) | 1 (1%) | 51 (34%) | 83 (55%) |

Workflow macro-F1 on each topology's traces (same predictions, sliced):

| Topology | n (groups) | macro-F1 |
|---|---|---|
| chain | 200 (145) | 0.651 [0.580, 0.714] |
| mesh | 200 (140) | 0.692 [0.627, 0.756] |
| star | 200 (144) | 0.635 [0.573, 0.698] |

Per-workflow F1, C1 vs the TLS control's TLS arm (its within-TLS CV recomputed with the same folds; pooled macro-F1 0.599 [0.543, 0.648], where tls_control.json gives the mean of the five fold scores). Difference CIs come from independent group bootstraps.

| Workflow | C1 F1 | C1 P / R | TLS arm F1 | TLS arm P / R | C1 − TLS arm |
|---|---|---|---|---|---|
| code_review | 0.701 [0.569, 0.800] | 0.68 / 0.73 | 0.624 [0.476, 0.738] | 0.67 / 0.58 | +0.077 [-0.093, +0.261] (n.s.) |
| data_analysis | 0.895 [0.849, 0.934] | 0.91 / 0.88 | 0.839 [0.776, 0.891] | 0.83 / 0.84 | +0.056 [-0.015, +0.129] (n.s.) |
| research_retrieval | 0.490 [0.410, 0.559] | 0.50 / 0.48 | 0.404 [0.314, 0.479] | 0.43 / 0.38 | +0.086 [-0.021, +0.198] (n.s.) |
| support_triage | 0.553 [0.471, 0.631] | 0.55 / 0.55 | 0.529 [0.438, 0.617] | 0.48 / 0.59 | +0.024 [-0.094, +0.147] (n.s.) |

Prompt mix (prompt_group = sha1 of the prompt). TV = total-variation distance between the two sets' prompt frequencies (0 = same mix, 1 = disjoint).

| Workflow | Traces C1 / TLS | Distinct prompts C1 / TLS | Shared distinct | C1 traces with a shared prompt | TLS traces with a shared prompt | TV | Median prompt chars C1 / TLS |
|---|---|---|---|---|---|---|---|
| code_review | 150 / 108 | 51 / 49 | 37 | 82% | 83% | 0.38 | 5059 / 5059 |
| data_analysis | 150 / 108 | 74 / 69 | 52 | 69% | 75% | 0.46 | 3902 / 4083 |
| research_retrieval | 150 / 108 | 62 / 42 | 34 | 72% | 89% | 0.38 | 127.5 / 133 |
| support_triage | 150 / 108 | 95 / 71 | 45 | 50% | 70% | 0.60 | 222 / 224 |

C1 workflow macro-F1 on traces whose prompt also occurs in the TLS arm: 0.656 [0.599, 0.707] (n = 409); on C1-only prompts: 0.619 [0.541, 0.689] (n = 191).

## Workflow: input length and response side (GBT, same folds)

First request into the system: TCP payload bytes of the first request message that reaches an agent (the caller → orchestrator link is not captured): on the agent link, opened by the trace, whose first post-handshake request starts earliest, the request-direction writes ≤ 50 ms apart, TLS ClientHello and client Finished excluded; from headers only. Pearson r with the true prompt length 0.996; 0 traces without one.

| Features | Dims | macro-F1 | All − this |
|---|---|---|---|
| all | 195 | 0.660 [0.613, 0.703] | — |
| first-request size only | 1 | 0.641 [0.589, 0.687] | +0.018 [-0.033, +0.070] (n.s.) |
| true prompt length only (not observable) | 1 | 0.928 [0.869, 0.975] | -0.268 [-0.326, -0.214] |
| response side only (no request-byte sizes) | 81 | 0.469 [0.422, 0.514] | +0.191 [+0.149, +0.237] |

| Workflow | Median first request (B) | Median prompt (chars) | Median first request − prompt |
|---|---|---|---|
| code_review | 6175.5 | 5059 | 1178 |
| data_analysis | 4976 | 3902 | 1012 |
| research_retrieval | 1371 | 127.5 | 1178 |
| support_triage | 1271.5 | 222 | 1020.5 |

Within-length pairs (binary, the same folds restricted to the pair, chance 0.5):

| Pair | n | All features | First-request size only | Prompt length only | All − first request | All − prompt length |
|---|---|---|---|---|---|---|
| code_review vs data_analysis | 300 | 0.893 [0.847, 0.931] | 0.903 [0.859, 0.943] | 0.957 [0.914, 0.993] | -0.010 [-0.058, +0.035] (n.s.) | -0.063 [-0.117, -0.011] |
| research_retrieval vs support_triage | 300 | 0.550 [0.475, 0.619] | 0.571 [0.472, 0.660] | 1.000 [1.000, 1.000] | -0.021 [-0.108, +0.065] (n.s.) | -0.450 [-0.525, -0.381] |

## Role: single features and one direction's sizes (GBT, same folds)

Each of the 35 per-flow features alone; the top 5 are shown with CIs (top 5 chosen on these folds out of 35 features, so their scores are optimistic). Response = agent → caller, request = caller → agent.

| Features | macro-F1 | All − this |
|---|---|---|
| all 35 | 0.994 [0.990, 0.997] | — |
| cumul_bytes_q8 only | 0.848 [0.830, 0.866] | +0.146 [+0.127, +0.165] |
| cumul_bytes_q7 only | 0.828 [0.803, 0.850] | +0.166 [+0.143, +0.191] |
| std_iat only | 0.771 [0.752, 0.790] | +0.223 [+0.203, +0.242] |
| cumul_bytes_q6 only | 0.720 [0.702, 0.737] | +0.274 [+0.257, +0.292] |
| cumul_bytes_q5 only | 0.696 [0.676, 0.714] | +0.298 [+0.280, +0.319] |
| response-side sizes only (bytes_out, mean_sz_out, std_sz_out, p25_sz_out, p75_sz_out) | 0.746 [0.722, 0.769] | +0.248 [+0.225, +0.272] |
| request-side sizes only (bytes_in, mean_sz_in, std_sz_in, p25_sz_in, p75_sz_in, n_small_inbound, iqr_size_in) | 0.701 [0.676, 0.725] | +0.293 [+0.268, +0.317] |

All single features: cumul_bytes_q8 0.848, cumul_bytes_q7 0.828, std_iat 0.771, cumul_bytes_q6 0.720, cumul_bytes_q5 0.696, mean_ibg 0.676, mean_iat 0.670, n_bursts 0.638, mean_burst_bytes 0.636, n_small_inbound 0.598, duration_s 0.597, cumul_bytes_q4 0.596, mean_sz_out 0.592, n_pkts_in 0.582, n_pkts_out 0.574, bytes_out 0.573, mean_burst_dur 0.570, n_response_bursts 0.570, cumul_bytes_q3 0.552, std_sz_out 0.552, p25_sz_out 0.536, cumul_bytes_q2 0.535, bytes_in 0.533, std_burst_bytes 0.531, std_sz_in 0.528, pkt_size_asymmetry 0.516, bytes_out_ratio 0.515, mean_sz_in 0.514, cumul_bytes_q1 0.480, cumul_bytes_q9 0.454, p75_sz_out 0.452, p25_sz_in 0.167, p75_sz_in 0.167, cumul_bytes_q0 0.167, iqr_size_in 0.167.

k-FP: 138 features from packet direction and timing only (Hayes & Danezis 2016), RandomForest, 1000 trees (k-FP closed world).
