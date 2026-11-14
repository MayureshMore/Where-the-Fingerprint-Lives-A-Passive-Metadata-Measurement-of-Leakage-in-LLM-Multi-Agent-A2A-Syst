# Leak check: C2 lan, view v2

1000 traces from 1000 captures in `data/raw_c2` (0 skipped, 1000 analysed as stripped copies). a2a-leakcheck 0.1.0, 2026-11-13T11:17:26-0800.

Vantage `v2`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 250 of 1000 traces show no flow there; they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge |
|---|---|---|---|
| edge_cloud | 1000 | 500 | 250 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **LEAK** | high | 0.975 [0.965, 0.984] | 0.300 | 0.010 | 0.00 | sizes (alone matches all) |
| escalated | **LEAK** | high | 1.000 [1.000, 1.000] | 0.550 | 0.010 | 0.00 | first_request_bytes alone |
| cloud_role | **LEAK** | high | 0.998 [0.995, 1.000] | 0.550 | 0.010 | 0.00 | first_request_bytes alone |
| audit_null | **NO LEAK** | none | 0.238 [0.211, 0.265] | 0.300 | 0.370 | 0.00 | — |

## task_type

**LEAK**: CI lower bound 0.965 > chance + margin 0.300.

1000 samples in 982 groups; classes alert_triage 250, fault_diagnosis 250, procedure_lookup 250, sensor_analysis 250.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.975 [0.965, 0.984] | — |
| sizes only | 139 | 0.968 [0.957, 0.978] | +0.007 [-0.002, +0.016] |
| timing only | 30 | 0.882 [0.861, 0.901] | +0.093 [+0.076, +0.113] |
| counts and direction only | 26 | 0.752 [0.727, 0.773] | +0.223 [+0.202, +0.251] |
| first_request_bytes only | 1 | 0.797 [0.775, 0.817] | +0.178 [+0.156, +0.201] |

Effect size 0.97 (share of the way from chance to perfect); severity high.

Permutation test (rf-light: macro-F1 0.971 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.246, max 0.281; verdicts on permuted labels: 0 LEAK, 96 NO LEAK, 3 INCONCLUSIVE.

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

Permutation test (rf-light: macro-F1 1.000 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.495, max 0.537; verdicts on permuted labels: 0 LEAK, 93 NO LEAK, 6 INCONCLUSIVE.

- **pad-task-inputs**: One request-size feature alone matches all features: the size of the task input gives the attribute away. Pad request bodies to fixed size buckets (AgentConfig.pad_buckets; in this testbed the session collector's arm option pad=B1/B2/...), with buckets wide enough that the inputs of different classes share one. Padding task inputs may not remove the leak: other size and timing features can still carry it. Re-run the audit on the padded deployment.

## cloud_role

**LEAK**: CI lower bound 0.995 > chance + margin 0.550.

750 samples in 736 groups; classes diagnostics 500, knowledge 250.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.998 [0.995, 1.000] | — |
| sizes only | 139 | 0.999 [0.995, 1.000] | -0.000 [-0.005, +0.004] |
| timing only | 30 | 0.998 [0.995, 1.000] | +0.000 [+0.000, +0.000] |
| counts and direction only | 26 | 0.882 [0.857, 0.906] | +0.117 [+0.093, +0.142] |
| first_request_bytes only | 1 | 1.000 [1.000, 1.000] | -0.002 [-0.005, +0.000] |

Effect size 1.00 (share of the way from chance to perfect); severity high.

Permutation test (rf-light: macro-F1 0.997 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.496, max 0.540; verdicts on permuted labels: 0 LEAK, 77 NO LEAK, 22 INCONCLUSIVE.

- **pad-task-inputs**: One request-size feature alone matches all features: the size of the task input gives the attribute away. Pad request bodies to fixed size buckets (AgentConfig.pad_buckets; in this testbed the session collector's arm option pad=B1/B2/...), with buckets wide enough that the inputs of different classes share one. Padding task inputs may not remove the leak: other size and timing features can still carry it. Re-run the audit on the padded deployment.

## audit_null

**NO LEAK**: CI upper bound 0.265 <= chance + margin 0.300.

1000 samples in 982 groups; classes a 251, b 252, c 244, d 253.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.238 [0.211, 0.265] | — |
| sizes only | 139 | 0.237 [0.211, 0.263] | +0.001 [-0.018, +0.021] |
| timing only | 30 | 0.252 [0.224, 0.277] | -0.014 [-0.045, +0.017] |
| counts and direction only | 26 | 0.266 [0.238, 0.292] | -0.027 [-0.062, +0.004] |
| first_request_bytes only | 1 | 0.230 [0.204, 0.254] | +0.009 [-0.024, +0.040] |

Effect size -0.02 (share of the way from chance to perfect); severity none.

Permutation test (rf-light: macro-F1 0.249 on the real labels): p = 0.370; permuted-label macro-F1 mean 0.244, max 0.276; verdicts on permuted labels: 0 LEAK, 95 NO LEAK, 4 INCONCLUSIVE.

## Runtime

186.5 s in all (collection 0.6 s, extraction 22.6 s, analysis 163.3 s); peak memory 307 MB in the main process, up to 314 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.6 | 169 | — |
| extraction | 22.6 | 244 | — |
| analysis:task_type | 44.7 | 291 | 289 |
| analysis:escalated | 35.6 | 297 | 289 |
| analysis:cloud_role | 33.4 | 306 | 289 |
| analysis:audit_null | 48.6 | 307 | 314 |
