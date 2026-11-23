# Leak check: C2B1 lan_padmax, view v2

500 traces from 500 captures in `data/raw_c2b1_padmax` (0 skipped, 500 analysed as stripped copies). a2a-leakcheck 0.3.0, 2026-11-22T17:44:50-0800.

**Audit completed**: 4 attributes, 3 LEAK, 1 NO LEAK, 0 INCONCLUSIVE.

**Release policy**: none configured, so the run exits 0 whatever the verdicts (gate a release with --baseline, --fail-on-leak, --strict or --require).

Vantage `v2`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 125 of 500 traces show no flow there; they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge |
|---|---|---|---|
| edge_cloud | 500 | 250 | 125 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **LEAK** | high | 0.784 [0.751, 0.814] | 0.300 | 0.010 | 0.00 | timing (alone matches all) |
| escalated | **LEAK** | high | 0.992 [0.979, 1.000] | 0.550 | 0.010 | 0.00 | first_request_bytes alone |
| cloud_role | **LEAK** | high | 0.982 [0.963, 0.994] | 0.550 | 0.010 | 0.00 | sizes (alone matches all) |
| audit_null | **NO LEAK** | none | 0.212 [0.176, 0.248] | 0.300 | 0.870 | 0.00 | — |

## task_type

**LEAK**: CI lower bound 0.751 > chance + margin 0.300.

500 samples in 498 groups; classes alert_triage 125, fault_diagnosis 125, procedure_lookup 125, sensor_analysis 125.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.784 [0.751, 0.814] | — | — |
| sizes only | 139 | 0.779 [0.748, 0.810] | +0.004 [-0.021, +0.029] | yes |
| timing only | 30 | 0.790 [0.757, 0.818] | -0.007 [-0.038, +0.029] | yes |
| counts and direction only | 26 | 0.557 [0.519, 0.592] | +0.226 [+0.181, +0.269] | no |
| first_request_bytes only | 1 | 0.375 [0.361, 0.388] | +0.409 [+0.372, +0.441] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.71 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (498 groups): macro-F1 0.810 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.249, max 0.306; verdicts on permuted labels: 0 LEAK, 75 NO LEAK, 24 INCONCLUSIVE.

- **padding-not-enough-timing**: The requests are padded, yet the attribute still leaks and timing carries it: padding is not enough. Shape the response timing as well (replies at a fixed rate or in batches, delays that do not follow the work done), then re-run the audit.

## escalated

**LEAK**: CI lower bound 0.979 > chance + margin 0.550.

500 samples in 498 groups; classes no 125, yes 375.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.992 [0.979, 1.000] | — | — |
| sizes only | 139 | 1.000 [1.000, 1.000] | -0.008 [-0.021, +0.000] | yes |
| timing only | 30 | 1.000 [1.000, 1.000] | -0.008 [-0.021, +0.000] | yes |
| counts and direction only | 26 | 0.992 [0.979, 1.000] | +0.000 [+0.000, +0.000] | yes |
| first_request_bytes only | 1 | 1.000 [1.000, 1.000] | -0.008 [-0.021, +0.000] | yes |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.98 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (498 groups): macro-F1 1.000 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.496, max 0.577; verdicts on permuted labels: 0 LEAK, 65 NO LEAK, 34 INCONCLUSIVE.

- **hide-escalation**: Whether the edge called the cloud is visible from the connections themselves, and padding cannot hide a call that did or did not happen. Make every task look alike upstream: dummy cloud calls at a fixed rate (cover traffic), or send every task to the cloud. Then re-run the audit.

## cloud_role

**LEAK**: CI lower bound 0.963 > chance + margin 0.550.

375 samples in 373 groups; classes diagnostics 250, knowledge 125.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.982 [0.963, 0.994] | — | — |
| sizes only | 139 | 0.985 [0.970, 0.997] | -0.003 [-0.021, +0.014] | yes |
| timing only | 30 | 0.982 [0.963, 0.994] | +0.000 [+0.000, +0.000] | yes |
| counts and direction only | 26 | 0.674 [0.626, 0.723] | +0.308 [+0.252, +0.362] | no |
| first_request_bytes only | 1 | 0.400 [0.383, 0.416] | +0.582 [+0.559, +0.605] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.96 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (373 groups): macro-F1 0.988 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.498, max 0.574; verdicts on permuted labels: 0 LEAK, 50 NO LEAK, 49 INCONCLUSIVE.

- **one-cloud-front-end**: Each cloud agent has its own address and TLS server name, which tell an observer which agent served the task whatever the traffic's shape (this audit scores the shape alone). Put the cloud agents behind one front end, one address and server name, then re-run the audit to see whether the shape still gives the agent away.

## audit_null

**NO LEAK**: CI upper bound 0.248 <= chance + margin 0.300.

500 samples in 498 groups; classes a 123, b 134, c 123, d 120.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.212 [0.176, 0.248] | — | — |
| sizes only | 139 | 0.215 [0.179, 0.252] | -0.004 [-0.035, +0.030] | yes |
| timing only | 30 | 0.229 [0.195, 0.269] | -0.017 [-0.063, +0.024] | yes |
| counts and direction only | 26 | 0.251 [0.211, 0.288] | -0.039 [-0.080, +0.007] | yes |
| first_request_bytes only | 1 | 0.175 [0.146, 0.205] | +0.037 [-0.002, +0.076] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size -0.05 (share of the way from chance to perfect); severity none.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (498 groups): macro-F1 0.222 on the real labels): p = 0.870; permuted-label macro-F1 mean 0.247, max 0.318; verdicts on permuted labels: 0 LEAK, 74 NO LEAK, 25 INCONCLUSIVE.

## Runtime

125.4 s in all (collection 0.3 s, extraction 10.8 s, analysis 114.2 s); peak memory 271 MB in the main process, up to 270 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.3 | 168 | — |
| extraction | 10.8 | 244 | — |
| analysis:task_type | 30.6 | 265 | 270 |
| analysis:escalated | 26.0 | 267 | 270 |
| analysis:cloud_role | 24.8 | 270 | 270 |
| analysis:audit_null | 31.8 | 271 | 270 |
