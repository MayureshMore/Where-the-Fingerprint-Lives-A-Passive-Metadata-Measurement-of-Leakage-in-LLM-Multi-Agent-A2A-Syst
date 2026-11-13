# Leak check: C2 lan_pad, view v2

1000 traces from 1000 captures in `data/raw_c2_pad` (0 skipped, 1000 analysed as stripped copies). a2a-leakcheck 0.1.0, 2026-11-13T11:23:58-0800.

Vantage `v2`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 250 of 1000 traces show no flow there; they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge |
|---|---|---|---|
| edge_cloud | 1000 | 500 | 250 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **LEAK** | high | 0.950 [0.936, 0.962] | 0.300 | 0.010 | 0.00 | sizes (alone matches all) |
| escalated | **LEAK** | high | 1.000 [1.000, 1.000] | 0.550 | 0.010 | 0.00 | first_request_bytes alone |
| cloud_role | **LEAK** | high | 0.998 [0.995, 1.000] | 0.550 | 0.010 | 0.00 | timing (alone matches all) |
| audit_null | **NO LEAK** | none | 0.255 [0.229, 0.280] | 0.300 | 0.520 | 0.00 | — |

## task_type

**LEAK**: CI lower bound 0.936 > chance + margin 0.300.

1000 samples in 982 groups; classes alert_triage 250, fault_diagnosis 250, procedure_lookup 250, sensor_analysis 250.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.950 [0.936, 0.962] | — |
| sizes only | 139 | 0.946 [0.931, 0.958] | +0.004 [-0.004, +0.013] |
| timing only | 30 | 0.898 [0.881, 0.916] | +0.052 [+0.034, +0.069] |
| counts and direction only | 26 | 0.702 [0.677, 0.727] | +0.248 [+0.221, +0.274] |
| first_request_bytes only | 1 | 0.751 [0.730, 0.773] | +0.199 [+0.175, +0.222] |

Effect size 0.93 (share of the way from chance to perfect); severity high.

Permutation test (rf-light: macro-F1 0.956 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.245, max 0.291; verdicts on permuted labels: 0 LEAK, 92 NO LEAK, 7 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

## escalated

**LEAK**: CI lower bound 1.000 > chance + margin 0.550.

1000 samples in 982 groups; classes no 250, yes 750.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 1.000 [1.000, 1.000] | — |
| sizes only | 139 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] |
| timing only | 30 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] |
| counts and direction only | 26 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] |
| first_request_bytes only | 1 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] |

Effect size 1.00 (share of the way from chance to perfect); severity high.

Permutation test (rf-light: macro-F1 1.000 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.492, max 0.540; verdicts on permuted labels: 0 LEAK, 89 NO LEAK, 10 INCONCLUSIVE.

- **pad-task-inputs**: One request-size feature alone matches all features: the size of the task input gives the attribute away. Pad request bodies to fixed size buckets (AgentConfig.pad_buckets; in this testbed the session collector's arm option pad=B1/B2/...), with buckets wide enough that the inputs of different classes share one. Padding task inputs may not remove the leak: other size and timing features can still carry it. Re-run the audit on the padded deployment.

## cloud_role

**LEAK**: CI lower bound 0.995 > chance + margin 0.550.

750 samples in 736 groups; classes diagnostics 500, knowledge 250.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.998 [0.995, 1.000] | — |
| sizes only | 139 | 0.993 [0.985, 0.998] | +0.006 [+0.001, +0.012] |
| timing only | 30 | 0.998 [0.995, 1.000] | +0.000 [+0.000, +0.000] |
| counts and direction only | 26 | 0.881 [0.855, 0.907] | +0.117 [+0.092, +0.143] |
| first_request_bytes only | 1 | 0.982 [0.972, 0.991] | +0.016 [+0.007, +0.027] |

Effect size 1.00 (share of the way from chance to perfect); severity high.

Permutation test (rf-light: macro-F1 0.998 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.500, max 0.550; verdicts on permuted labels: 0 LEAK, 78 NO LEAK, 21 INCONCLUSIVE.

- **shape-timing**: Timing carries the leak. Add jitter and reordering to delegations (defense=rate), or batch responses so their timing no longer follows the work done.

## audit_null

**NO LEAK**: CI upper bound 0.280 <= chance + margin 0.300.

1000 samples in 982 groups; classes a 251, b 252, c 244, d 253.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.255 [0.229, 0.280] | — |
| sizes only | 139 | 0.270 [0.243, 0.297] | -0.015 [-0.034, +0.003] |
| timing only | 30 | 0.245 [0.217, 0.272] | +0.010 [-0.019, +0.038] |
| counts and direction only | 26 | 0.268 [0.239, 0.296] | -0.013 [-0.046, +0.018] |
| first_request_bytes only | 1 | 0.278 [0.249, 0.305] | -0.023 [-0.053, +0.011] |

Effect size 0.01 (share of the way from chance to perfect); severity none.

Permutation test (rf-light: macro-F1 0.242 on the real labels): p = 0.520; permuted-label macro-F1 mean 0.244, max 0.281; verdicts on permuted labels: 0 LEAK, 96 NO LEAK, 3 INCONCLUSIVE.

## Runtime

178.7 s in all (collection 0.6 s, extraction 22.4 s, analysis 155.6 s); peak memory 310 MB in the main process, up to 317 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.6 | 169 | — |
| extraction | 22.4 | 246 | — |
| analysis:task_type | 43.0 | 290 | 306 |
| analysis:escalated | 34.2 | 297 | 306 |
| analysis:cloud_role | 32.3 | 305 | 306 |
| analysis:audit_null | 45.1 | 310 | 317 |
