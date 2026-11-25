# Leak check: C2 lan_padmax, view v2

1000 traces from 1000 captures in `1_analysis_object/a2a-leakcheck/downloads/data/raw_c2_padmax` (0 skipped, 0 analysed as stripped copies). a2a-leakcheck 0.3.1, 2026-11-25T07:50:24-0800.

**Audit completed**: 4 attributes, 3 LEAK, 1 NO LEAK, 0 INCONCLUSIVE.

**Release policy**: none configured, so the run exits 0 whatever the verdicts (gate a release with --baseline, --fail-on-leak, --strict or --require).

Vantage `v2`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 250 of 1000 traces show no flow there (250 expected: not escalated, per the sidecar, and this view sees only cloud agents; 0 unexpectedly empty); they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

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
| audit_null | **NO LEAK** | none | 0.259 [0.231, 0.286] | 0.300 | 0.220 | 0.00 | — |

## task_type

**LEAK**: CI lower bound 0.870 > chance + margin 0.300.

1000 samples in 982 groups; classes alert_triage 250, fault_diagnosis 250, procedure_lookup 250, sensor_analysis 250.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.889 [0.870, 0.907] | — | — |
| sizes only | 139 | 0.875 [0.855, 0.892] | +0.014 [+0.000, +0.028] | yes |
| timing only | 30 | 0.892 [0.874, 0.910] | -0.003 [-0.020, +0.014] | yes |
| counts and direction only | 26 | 0.711 [0.685, 0.737] | +0.178 [+0.149, +0.205] | no |
| first_request_bytes only | 1 | 0.375 [0.365, 0.385] | +0.514 [+0.493, +0.534] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.85 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (982 groups): macro-F1 0.894 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.244, max 0.288; verdicts on permuted labels: 0 LEAK, 94 NO LEAK, 5 INCONCLUSIVE.

- **padding-not-enough-timing**: The requests are padded, yet the attribute still leaks and timing carries it: padding is not enough. Shape the response timing as well (replies at a fixed rate or in batches, delays that do not follow the work done), then re-run the audit.

## escalated

**LEAK**: CI lower bound 1.000 > chance + margin 0.550.

1000 samples in 982 groups; classes no 250, yes 750.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 1.000 [1.000, 1.000] | — | — |
| sizes only | 139 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |
| timing only | 30 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |
| counts and direction only | 26 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |
| first_request_bytes only | 1 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 1.00 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (982 groups): macro-F1 1.000 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.493, max 0.547; verdicts on permuted labels: 0 LEAK, 96 NO LEAK, 3 INCONCLUSIVE.

- **hide-escalation**: Whether the edge called the cloud is visible from the connections themselves, and padding cannot hide a call that did or did not happen. Make every task look alike upstream: dummy cloud calls at a fixed rate (cover traffic), or send every task to the cloud. Then re-run the audit.

## cloud_role

**LEAK**: CI lower bound 0.990 > chance + margin 0.550.

750 samples in 736 groups; classes diagnostics 500, knowledge 250.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.996 [0.990, 1.000] | — | — |
| sizes only | 139 | 0.995 [0.989, 1.000] | +0.000 [-0.006, +0.006] | yes |
| timing only | 30 | 0.994 [0.988, 0.999] | +0.002 [+0.000, +0.005] | yes |
| counts and direction only | 26 | 0.810 [0.779, 0.839] | +0.186 [+0.157, +0.215] | no |
| first_request_bytes only | 1 | 0.400 [0.387, 0.413] | +0.596 [+0.581, +0.610] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.99 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (736 groups): macro-F1 0.995 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.501, max 0.563; verdicts on permuted labels: 0 LEAK, 72 NO LEAK, 27 INCONCLUSIVE.

- **one-cloud-front-end**: Each cloud agent has its own address and TLS server name, which tell an observer which agent served the task whatever the traffic's shape (this audit scores the shape alone). Put the cloud agents behind one front end, one address and server name, then re-run the audit to see whether the shape still gives the agent away.

## audit_null

**NO LEAK**: CI upper bound 0.286 <= chance + margin 0.300.

1000 samples in 982 groups; classes a 251, b 252, c 244, d 253.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.259 [0.231, 0.286] | — | — |
| sizes only | 139 | 0.254 [0.226, 0.280] | +0.005 [-0.016, +0.027] | yes |
| timing only | 30 | 0.251 [0.224, 0.276] | +0.008 [-0.021, +0.036] | yes |
| counts and direction only | 26 | 0.250 [0.222, 0.274] | +0.009 [-0.024, +0.041] | yes |
| first_request_bytes only | 1 | 0.213 [0.188, 0.239] | +0.046 [+0.015, +0.076] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.01 (share of the way from chance to perfect); severity none.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (982 groups): macro-F1 0.255 on the real labels): p = 0.220; permuted-label macro-F1 mean 0.244, max 0.292; verdicts on permuted labels: 0 LEAK, 93 NO LEAK, 6 INCONCLUSIVE.

## Runtime

187.2 s in all (features 0.0 s, analysis 187.2 s); peak memory 197 MB in the main process, up to 278 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| analysis:task_type | 63.8 | 186 | 277 |
| analysis:escalated | 45.7 | 191 | 277 |
| analysis:cloud_role | 32.6 | 195 | 277 |
| analysis:audit_null | 44.3 | 197 | 278 |
