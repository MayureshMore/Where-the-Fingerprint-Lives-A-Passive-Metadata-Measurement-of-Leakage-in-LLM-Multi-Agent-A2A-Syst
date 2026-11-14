# Leak check: C2 lan_padmax, view v1

1000 traces from 1000 captures in `data/raw_c2_padmax` (0 skipped, 1000 analysed as stripped copies). a2a-leakcheck 0.1.0, 2026-11-13T11:27:25-0800.

Vantage `v1`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 0 of 1000 traces show no flow there; they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge | ticket |
|---|---|---|---|---|
| edge_cloud | 1000 | 500 | 250 | 1000 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **LEAK** | high | 0.898 [0.879, 0.915] | 0.300 | 0.010 | 0.00 | timing (alone matches all) |
| escalated | **LEAK** | high | 1.000 [1.000, 1.000] | 0.550 | 0.010 | 0.00 | first_request_bytes alone |
| cloud_role | **LEAK** | high | 0.995 [0.990, 1.000] | 0.550 | 0.010 | 0.00 | sizes (alone matches all) |
| audit_null | **INCONCLUSIVE** | none | 0.277 [0.248, 0.303] | 0.300 | 0.120 | 0.00 | — |

## task_type

**LEAK**: CI lower bound 0.879 > chance + margin 0.300.

1000 samples in 982 groups; classes alert_triage 250, fault_diagnosis 250, procedure_lookup 250, sensor_analysis 250.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.898 [0.879, 0.915] | — |
| sizes only | 139 | 0.881 [0.862, 0.899] | +0.017 [+0.003, +0.031] |
| timing only | 30 | 0.883 [0.865, 0.900] | +0.015 [-0.001, +0.031] |
| counts and direction only | 26 | 0.697 [0.672, 0.722] | +0.201 [+0.170, +0.230] |
| first_request_bytes only | 1 | 0.375 [0.365, 0.385] | +0.523 [+0.502, +0.543] |

Effect size 0.86 (share of the way from chance to perfect); severity high.

Permutation test (rf-light: macro-F1 0.905 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.246, max 0.289; verdicts on permuted labels: 0 LEAK, 93 NO LEAK, 6 INCONCLUSIVE.

- **shape-timing**: Timing carries the leak. Add jitter and reordering to delegations (defense=rate), or batch responses so their timing no longer follows the work done.

## escalated

**LEAK**: CI lower bound 1.000 > chance + margin 0.550.

1000 samples in 982 groups; classes no 250, yes 750.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 1.000 [1.000, 1.000] | — |
| sizes only | 139 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] |
| timing only | 30 | 0.997 [0.993, 1.000] | +0.003 [+0.000, +0.007] |
| counts and direction only | 26 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] |
| first_request_bytes only | 1 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] |

Effect size 1.00 (share of the way from chance to perfect); severity high.

Permutation test (rf-light: macro-F1 1.000 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.496, max 0.562; verdicts on permuted labels: 0 LEAK, 87 NO LEAK, 12 INCONCLUSIVE.

- **pad-task-inputs**: One request-size feature alone matches all features: the size of the task input gives the attribute away. Pad request bodies to fixed size buckets (AgentConfig.pad_buckets; in this testbed the session collector's arm option pad=B1/B2/...), with buckets wide enough that the inputs of different classes share one. Padding task inputs may not remove the leak: other size and timing features can still carry it. Re-run the audit on the padded deployment.

## cloud_role

**LEAK**: CI lower bound 0.990 > chance + margin 0.550.

750 samples in 736 groups; classes diagnostics 500, knowledge 250.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.995 [0.990, 1.000] | — |
| sizes only | 139 | 0.997 [0.992, 1.000] | -0.001 [-0.005, +0.000] |
| timing only | 30 | 0.995 [0.990, 1.000] | +0.000 [+0.000, +0.000] |
| counts and direction only | 26 | 0.820 [0.792, 0.849] | +0.175 [+0.147, +0.204] |
| first_request_bytes only | 1 | 0.400 [0.387, 0.413] | +0.595 [+0.581, +0.610] |

Effect size 0.99 (share of the way from chance to perfect); severity high.

Permutation test (rf-light: macro-F1 0.997 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.501, max 0.558; verdicts on permuted labels: 0 LEAK, 72 NO LEAK, 27 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

## audit_null

**INCONCLUSIVE**: CI [0.248, 0.303] straddles chance + margin 0.300.

1000 samples in 982 groups; classes a 251, b 252, c 244, d 253.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.277 [0.248, 0.303] | — |
| sizes only | 139 | 0.294 [0.265, 0.321] | -0.017 [-0.045, +0.010] |
| timing only | 30 | 0.265 [0.237, 0.292] | +0.012 [-0.022, +0.045] |
| counts and direction only | 26 | 0.254 [0.227, 0.280] | +0.023 [-0.016, +0.058] |
| first_request_bytes only | 1 | 0.218 [0.192, 0.243] | +0.058 [+0.021, +0.095] |

Effect size 0.04 (share of the way from chance to perfect); severity none.

Permutation test (rf-light: macro-F1 0.271 on the real labels): p = 0.120; permuted-label macro-F1 mean 0.249, max 0.282; verdicts on permuted labels: 0 LEAK, 89 NO LEAK, 10 INCONCLUSIVE.

- **inconclusive**: The interval straddles chance + margin: more traces will narrow it. Re-run before treating this attribute as safe.

## Runtime

205.2 s in all (collection 0.6 s, extraction 23.2 s, analysis 181.3 s); peak memory 310 MB in the main process, up to 334 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.6 | 169 | — |
| extraction | 23.2 | 244 | — |
| analysis:task_type | 48.3 | 292 | 317 |
| analysis:escalated | 37.9 | 300 | 317 |
| analysis:cloud_role | 35.0 | 309 | 317 |
| analysis:audit_null | 59.1 | 310 | 334 |
