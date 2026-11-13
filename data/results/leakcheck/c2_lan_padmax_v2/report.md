# Leak check: C2 lan_padmax, view v2

1000 traces from 1000 captures in `data/raw_c2_padmax` (0 skipped, 1000 analysed as stripped copies). a2a-leakcheck 0.1.0, 2026-11-13T11:30:25-0800.

Vantage `v2`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 250 of 1000 traces show no flow there; they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge |
|---|---|---|---|
| edge_cloud | 1000 | 500 | 250 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **LEAK** | high | 0.889 [0.870, 0.907] | 0.300 | 0.010 | 0.00 | timing (alone matches all) |
| escalated | **LEAK** | high | 1.000 [1.000, 1.000] | 0.550 | 0.010 | 0.00 | first_request_bytes alone |
| cloud_role | **LEAK** | high | 0.996 [0.990, 1.000] | 0.550 | 0.010 | 0.00 | sizes (alone matches all) |
| audit_null | **NO LEAK** | none | 0.259 [0.231, 0.286] | 0.300 | 0.340 | 0.00 | — |

## task_type

**LEAK**: CI lower bound 0.870 > chance + margin 0.300.

1000 samples in 982 groups; classes alert_triage 250, fault_diagnosis 250, procedure_lookup 250, sensor_analysis 250.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.889 [0.870, 0.907] | — |
| sizes only | 139 | 0.875 [0.855, 0.892] | +0.014 [+0.000, +0.028] |
| timing only | 30 | 0.892 [0.874, 0.910] | -0.003 [-0.020, +0.014] |
| counts and direction only | 26 | 0.711 [0.685, 0.737] | +0.178 [+0.149, +0.205] |
| first_request_bytes only | 1 | 0.375 [0.365, 0.385] | +0.514 [+0.493, +0.534] |

Effect size 0.85 (share of the way from chance to perfect); severity high.

Permutation test (rf-light: macro-F1 0.894 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.244, max 0.283; verdicts on permuted labels: 0 LEAK, 94 NO LEAK, 5 INCONCLUSIVE.

- **shape-timing**: Timing carries the leak. Add jitter and reordering to delegations (defense=rate), or batch responses so their timing no longer follows the work done.

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

Permutation test (rf-light: macro-F1 1.000 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.494, max 0.534; verdicts on permuted labels: 0 LEAK, 91 NO LEAK, 8 INCONCLUSIVE.

- **pad-task-inputs**: One request-size feature alone matches all features: the size of the task input gives the attribute away. Pad request bodies to fixed size buckets (AgentConfig.pad_buckets; in this testbed the session collector's arm option pad=B1/B2/...), with buckets wide enough that the inputs of different classes share one. Padding task inputs may not remove the leak: other size and timing features can still carry it. Re-run the audit on the padded deployment.

## cloud_role

**LEAK**: CI lower bound 0.990 > chance + margin 0.550.

750 samples in 736 groups; classes diagnostics 500, knowledge 250.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.996 [0.990, 1.000] | — |
| sizes only | 139 | 0.995 [0.989, 1.000] | +0.000 [-0.006, +0.006] |
| timing only | 30 | 0.994 [0.988, 0.999] | +0.002 [+0.000, +0.005] |
| counts and direction only | 26 | 0.810 [0.779, 0.839] | +0.186 [+0.157, +0.215] |
| first_request_bytes only | 1 | 0.400 [0.387, 0.413] | +0.596 [+0.581, +0.610] |

Effect size 0.99 (share of the way from chance to perfect); severity high.

Permutation test (rf-light: macro-F1 0.995 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.501, max 0.550; verdicts on permuted labels: 0 LEAK, 69 NO LEAK, 30 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

## audit_null

**NO LEAK**: CI upper bound 0.286 <= chance + margin 0.300.

1000 samples in 982 groups; classes a 251, b 252, c 244, d 253.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.259 [0.231, 0.286] | — |
| sizes only | 139 | 0.254 [0.226, 0.280] | +0.005 [-0.016, +0.027] |
| timing only | 30 | 0.251 [0.224, 0.276] | +0.008 [-0.021, +0.036] |
| counts and direction only | 26 | 0.250 [0.222, 0.274] | +0.009 [-0.024, +0.041] |
| first_request_bytes only | 1 | 0.213 [0.188, 0.239] | +0.046 [+0.015, +0.076] |

Effect size 0.01 (share of the way from chance to perfect); severity none.

Permutation test (rf-light: macro-F1 0.255 on the real labels): p = 0.340; permuted-label macro-F1 mean 0.248, max 0.281; verdicts on permuted labels: 0 LEAK, 94 NO LEAK, 5 INCONCLUSIVE.

## Runtime

178.7 s in all (collection 0.6 s, extraction 22.6 s, analysis 155.4 s); peak memory 306 MB in the main process, up to 319 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.6 | 168 | — |
| extraction | 22.6 | 244 | — |
| analysis:task_type | 43.4 | 287 | 316 |
| analysis:escalated | 34.3 | 294 | 316 |
| analysis:cloud_role | 32.1 | 302 | 316 |
| analysis:audit_null | 44.6 | 306 | 319 |
