# Leak check: C2 lan_pad, view v1

1000 traces from 1000 captures in `data/raw_c2_pad` (0 skipped, 1000 analysed as stripped copies). a2a-leakcheck 0.1.0, 2026-11-14T12:19:27-0800.

Vantage `v1`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 0 of 1000 traces show no flow there; they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge | ticket |
|---|---|---|---|---|
| edge_cloud | 1000 | 500 | 250 | 1000 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **LEAK** | high | 0.951 [0.937, 0.963] | 0.300 | 0.010 | 0.00 | sizes (alone matches all) |
| escalated | **LEAK** | high | 0.999 [0.996, 1.000] | 0.550 | 0.010 | 0.00 | first_request_bytes alone |
| cloud_role | **LEAK** | high | 0.998 [0.995, 1.000] | 0.550 | 0.010 | 0.00 | timing (alone matches all) |
| audit_null | **INCONCLUSIVE** | none | 0.249 [0.221, 0.277] | 0.300 | 0.030 | 0.00 | — |

## task_type

**LEAK**: CI lower bound 0.937 > chance + margin 0.300.

1000 samples in 982 groups; classes alert_triage 250, fault_diagnosis 250, procedure_lookup 250, sensor_analysis 250.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.951 [0.937, 0.963] | — |
| sizes only | 139 | 0.953 [0.940, 0.965] | -0.002 [-0.011, +0.006] |
| timing only | 30 | 0.904 [0.886, 0.921] | +0.047 [+0.029, +0.064] |
| counts and direction only | 26 | 0.728 [0.704, 0.751] | +0.223 [+0.197, +0.249] |
| first_request_bytes only | 1 | 0.751 [0.730, 0.773] | +0.200 [+0.175, +0.224] |

Effect size 0.93 (share of the way from chance to perfect); severity high.

Permutation test (rf-light: macro-F1 0.956 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.251, max 0.306; verdicts on permuted labels: 0 LEAK, 90 NO LEAK, 9 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

- **pad-local-posts**: This view also sees requests that are not padded, such as posts to a local service (in C2, the ticket service on the building network). Pad posts to local services too, then re-run the audit; the audit of a view without them shows what they add.

## escalated

**LEAK**: CI lower bound 0.996 > chance + margin 0.550.

1000 samples in 982 groups; classes no 250, yes 750.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.999 [0.996, 1.000] | — |
| sizes only | 139 | 1.000 [1.000, 1.000] | -0.001 [-0.004, +0.000] |
| timing only | 30 | 0.999 [0.996, 1.000] | +0.000 [+0.000, +0.000] |
| counts and direction only | 26 | 0.999 [0.996, 1.000] | +0.000 [+0.000, +0.000] |
| first_request_bytes only | 1 | 1.000 [1.000, 1.000] | -0.001 [-0.004, +0.000] |

Effect size 1.00 (share of the way from chance to perfect); severity high.

Permutation test (rf-light: macro-F1 1.000 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.498, max 0.567; verdicts on permuted labels: 0 LEAK, 84 NO LEAK, 15 INCONCLUSIVE.

- **hide-escalation**: Whether the edge called the cloud is visible from the connections themselves, and padding cannot hide a call that did or did not happen. Make every task look alike upstream: dummy cloud calls at a fixed rate (cover traffic), or send every task to the cloud. Then re-run the audit.

## cloud_role

**LEAK**: CI lower bound 0.995 > chance + margin 0.550.

750 samples in 736 groups; classes diagnostics 500, knowledge 250.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.998 [0.995, 1.000] | — |
| sizes only | 139 | 0.991 [0.983, 0.997] | +0.007 [+0.002, +0.015] |
| timing only | 30 | 0.998 [0.995, 1.000] | +0.000 [+0.000, +0.000] |
| counts and direction only | 26 | 0.892 [0.866, 0.916] | +0.107 [+0.082, +0.133] |
| first_request_bytes only | 1 | 0.982 [0.972, 0.991] | +0.016 [+0.007, +0.027] |

Effect size 1.00 (share of the way from chance to perfect); severity high.

Permutation test (rf-light: macro-F1 1.000 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.499, max 0.553; verdicts on permuted labels: 0 LEAK, 72 NO LEAK, 27 INCONCLUSIVE.

- **one-cloud-front-end**: Each cloud agent has its own address and TLS server name, which tell an observer which agent served the task whatever the traffic's shape (this audit scores the shape alone). Put the cloud agents behind one front end, one address and server name, then re-run the audit to see whether the shape still gives the agent away.

## audit_null

**INCONCLUSIVE**: CI upper bound 0.277 <= chance + margin 0.300, but the permutation test finds a signal (p = 0.030 <= 0.05): the two models disagree.

1000 samples in 982 groups; classes a 251, b 252, c 244, d 253.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.249 [0.221, 0.277] | — |
| sizes only | 139 | 0.272 [0.245, 0.300] | -0.023 [-0.051, +0.003] |
| timing only | 30 | 0.227 [0.200, 0.252] | +0.022 [-0.010, +0.059] |
| counts and direction only | 26 | 0.260 [0.231, 0.288] | -0.011 [-0.047, +0.024] |
| first_request_bytes only | 1 | 0.282 [0.253, 0.309] | -0.033 [-0.068, +0.002] |

Effect size -0.00 (share of the way from chance to perfect); severity none.

Permutation test (rf-light: macro-F1 0.284 on the real labels): p = 0.030; permuted-label macro-F1 mean 0.249, max 0.296; verdicts on permuted labels: 0 LEAK, 88 NO LEAK, 11 INCONCLUSIVE.

- **inconclusive**: The interval straddles chance + margin: more traces will narrow it. Re-run before treating this attribute as safe.

## Runtime

214.6 s in all (collection 0.9 s, extraction 24.5 s, analysis 189.1 s); peak memory 308 MB in the main process, up to 329 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.9 | 170 | — |
| extraction | 24.5 | 247 | — |
| analysis:task_type | 50.5 | 295 | 300 |
| analysis:escalated | 40.3 | 300 | 300 |
| analysis:cloud_role | 35.7 | 307 | 300 |
| analysis:audit_null | 61.5 | 308 | 329 |
