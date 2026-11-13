# Leak check: C2 lan, view v1

1000 traces from 1000 captures in `data/raw_c2` (0 skipped, 1000 analysed as stripped copies). a2a-leakcheck 0.1.0, 2026-11-13T11:14:18-0800.

Vantage `v1`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 0 of 1000 traces show no flow there; they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge | ticket |
|---|---|---|---|---|
| edge_cloud | 1000 | 500 | 250 | 1000 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **LEAK** | high | 0.967 [0.955, 0.977] | 0.300 | 0.010 | 0.00 | sizes (alone matches all) |
| escalated | **LEAK** | high | 1.000 [1.000, 1.000] | 0.550 | 0.010 | 0.00 | sizes (alone matches all) |
| cloud_role | **LEAK** | high | 0.998 [0.995, 1.000] | 0.550 | 0.010 | 0.00 | first_request_bytes alone |
| audit_null | **NO LEAK** | none | 0.250 [0.222, 0.275] | 0.300 | 0.070 | 0.00 | — |

## task_type

**LEAK**: CI lower bound 0.955 > chance + margin 0.300.

1000 samples in 982 groups; classes alert_triage 250, fault_diagnosis 250, procedure_lookup 250, sensor_analysis 250.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.967 [0.955, 0.977] | — |
| sizes only | 139 | 0.962 [0.950, 0.974] | +0.005 [-0.002, +0.013] |
| timing only | 30 | 0.901 [0.883, 0.918] | +0.066 [+0.049, +0.083] |
| counts and direction only | 26 | 0.732 [0.708, 0.757] | +0.235 [+0.208, +0.262] |
| first_request_bytes only | 1 | 0.739 [0.713, 0.765] | +0.228 [+0.201, +0.257] |

Effect size 0.96 (share of the way from chance to perfect); severity high.

Permutation test (rf-light: macro-F1 0.970 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.251, max 0.283; verdicts on permuted labels: 0 LEAK, 89 NO LEAK, 10 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

## escalated

**LEAK**: CI lower bound 1.000 > chance + margin 0.550.

1000 samples in 982 groups; classes no 250, yes 750.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 1.000 [1.000, 1.000] | — |
| sizes only | 139 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] |
| timing only | 30 | 0.999 [0.996, 1.000] | +0.001 [+0.000, +0.004] |
| counts and direction only | 26 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] |
| first_request_bytes only | 1 | 0.888 [0.863, 0.910] | +0.112 [+0.090, +0.137] |

Effect size 1.00 (share of the way from chance to perfect); severity high.

Permutation test (rf-light: macro-F1 1.000 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.501, max 0.554; verdicts on permuted labels: 0 LEAK, 84 NO LEAK, 15 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

## cloud_role

**LEAK**: CI lower bound 0.995 > chance + margin 0.550.

750 samples in 736 groups; classes diagnostics 500, knowledge 250.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.998 [0.995, 1.000] | — |
| sizes only | 139 | 0.997 [0.993, 1.000] | +0.001 [-0.003, +0.006] |
| timing only | 30 | 0.998 [0.995, 1.000] | +0.000 [+0.000, +0.000] |
| counts and direction only | 26 | 0.897 [0.875, 0.919] | +0.102 [+0.079, +0.124] |
| first_request_bytes only | 1 | 1.000 [1.000, 1.000] | -0.002 [-0.005, +0.000] |

Effect size 1.00 (share of the way from chance to perfect); severity high.

Permutation test (rf-light: macro-F1 0.997 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.494, max 0.546; verdicts on permuted labels: 0 LEAK, 82 NO LEAK, 17 INCONCLUSIVE.

- **pad-task-inputs**: One request-size feature alone matches all features: the size of the task input gives the attribute away. Pad request bodies to fixed size buckets (AgentConfig.pad_buckets; in this testbed the session collector's arm option pad=B1/B2/...), with buckets wide enough that the inputs of different classes share one. Padding task inputs may not remove the leak: other size and timing features can still carry it. Re-run the audit on the padded deployment.

- **shape-timing**: Timing carries the leak. Add jitter and reordering to delegations (defense=rate), or batch responses so their timing no longer follows the work done.

## audit_null

**NO LEAK**: CI upper bound 0.275 <= chance + margin 0.300.

1000 samples in 982 groups; classes a 251, b 252, c 244, d 253.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.250 [0.222, 0.275] | — |
| sizes only | 139 | 0.266 [0.238, 0.292] | -0.016 [-0.041, +0.011] |
| timing only | 30 | 0.251 [0.224, 0.277] | -0.001 [-0.036, +0.032] |
| counts and direction only | 26 | 0.259 [0.230, 0.286] | -0.009 [-0.043, +0.027] |
| first_request_bytes only | 1 | 0.222 [0.197, 0.247] | +0.028 [-0.008, +0.063] |

Effect size 0.00 (share of the way from chance to perfect); severity none.

Permutation test (rf-light: macro-F1 0.270 on the real labels): p = 0.070; permuted-label macro-F1 mean 0.250, max 0.280; verdicts on permuted labels: 0 LEAK, 94 NO LEAK, 5 INCONCLUSIVE.

## Runtime

209.7 s in all (collection 0.5 s, extraction 22.3 s, analysis 186.9 s); peak memory 310 MB in the main process, up to 326 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.5 | 171 | — |
| extraction | 22.3 | 248 | — |
| analysis:task_type | 49.9 | 297 | 292 |
| analysis:escalated | 38.7 | 301 | 292 |
| analysis:cloud_role | 35.7 | 309 | 292 |
| analysis:audit_null | 61.6 | 310 | 326 |
