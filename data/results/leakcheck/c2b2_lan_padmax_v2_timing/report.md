# Leak check: C2B2 lan_padmax, view v2, timing alone

1000 traces from 1000 captures in `data/raw_c2b2_padmax` (0 skipped, 1000 analysed as stripped copies). a2a-leakcheck 0.3.1, 2026-11-26T19:57:36-0800.

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
| task_type | **LEAK** | high | 0.814 [0.794, 0.835] | 0.300 | 0.010 | 0.00 | timing (alone matches all) |
| escalated | **LEAK** | high | 1.000 [1.000, 1.000] | 0.550 | 0.010 | 0.00 | timing (alone matches all) |
| cloud_role | **LEAK** | high | 0.991 [0.983, 0.997] | 0.550 | 0.010 | 0.00 | timing (alone matches all) |
| audit_null | **NO LEAK** | none | 0.248 [0.222, 0.273] | 0.300 | 0.180 | 0.00 | — |

## task_type

**LEAK**: CI lower bound 0.794 > chance + margin 0.300.

1000 samples in 1000 groups; classes alert_triage 250, fault_diagnosis 250, procedure_lookup 250, sensor_analysis 250.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.814 [0.794, 0.835] | — | — |
| sizes only | 139 | 0.100 [0.091, 0.108] | +0.714 [+0.691, +0.736] | no |
| timing only | 30 | 0.814 [0.794, 0.835] | +0.000 [+0.000, +0.000] | yes |
| counts and direction only | 26 | 0.100 [0.091, 0.108] | +0.714 [+0.691, +0.736] | no |
| first_request_bytes only | 1 | 0.100 [0.091, 0.108] | +0.714 [+0.691, +0.736] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.75 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (1000 groups): macro-F1 0.825 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.244, max 0.287; verdicts on permuted labels: 0 LEAK, 93 NO LEAK, 6 INCONCLUSIVE.

- **padding-not-enough-timing**: The requests are padded, yet the attribute still leaks and timing carries it: padding is not enough. Shape the response timing as well (replies at a fixed rate or in batches, delays that do not follow the work done), then re-run the audit.

## escalated

**LEAK**: CI lower bound 1.000 > chance + margin 0.550.

1000 samples in 1000 groups; classes no 250, yes 750.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 1.000 [1.000, 1.000] | — | — |
| sizes only | 139 | 0.200 [0.182, 0.217] | +0.800 [+0.783, +0.818] | no |
| timing only | 30 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |
| counts and direction only | 26 | 0.200 [0.182, 0.217] | +0.800 [+0.783, +0.818] | no |
| first_request_bytes only | 1 | 0.200 [0.182, 0.217] | +0.800 [+0.783, +0.818] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 1.00 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (1000 groups): macro-F1 1.000 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.491, max 0.559; verdicts on permuted labels: 0 LEAK, 93 NO LEAK, 6 INCONCLUSIVE.

- **hide-escalation**: Whether the edge called the cloud is visible from the connections themselves, and padding cannot hide a call that did or did not happen. Make every task look alike upstream: dummy cloud calls at a fixed rate (cover traffic), or send every task to the cloud. Then re-run the audit.

## cloud_role

**LEAK**: CI lower bound 0.983 > chance + margin 0.550.

750 samples in 750 groups; classes diagnostics 500, knowledge 250.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.991 [0.983, 0.997] | — | — |
| sizes only | 139 | 0.400 [0.388, 0.411] | +0.591 [+0.578, +0.605] | no |
| timing only | 30 | 0.991 [0.983, 0.997] | +0.000 [+0.000, +0.000] | yes |
| counts and direction only | 26 | 0.400 [0.388, 0.411] | +0.591 [+0.578, +0.605] | no |
| first_request_bytes only | 1 | 0.400 [0.388, 0.411] | +0.591 [+0.578, +0.605] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.98 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (750 groups): macro-F1 0.989 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.497, max 0.549; verdicts on permuted labels: 0 LEAK, 74 NO LEAK, 25 INCONCLUSIVE.

- **one-cloud-front-end**: Each cloud agent has its own address and TLS server name, which tell an observer which agent served the task whatever the traffic's shape (this audit scores the shape alone). Put the cloud agents behind one front end, one address and server name, then re-run the audit to see whether the shape still gives the agent away.

## audit_null

**NO LEAK**: CI upper bound 0.273 <= chance + margin 0.300.

1000 samples in 1000 groups; classes a 249, b 244, c 248, d 259.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.248 [0.222, 0.273] | — | — |
| sizes only | 139 | 0.100 [0.091, 0.108] | +0.148 [+0.122, +0.174] | no |
| timing only | 30 | 0.248 [0.222, 0.273] | +0.000 [+0.000, +0.000] | yes |
| counts and direction only | 26 | 0.100 [0.091, 0.108] | +0.148 [+0.122, +0.174] | no |
| first_request_bytes only | 1 | 0.100 [0.091, 0.108] | +0.148 [+0.122, +0.174] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size -0.00 (share of the way from chance to perfect); severity none.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (1000 groups): macro-F1 0.262 on the real labels): p = 0.180; permuted-label macro-F1 mean 0.245, max 0.292; verdicts on permuted labels: 0 LEAK, 95 NO LEAK, 4 INCONCLUSIVE.

## Runtime

150.3 s in all (features 0.0 s, analysis 150.3 s); peak memory 231 MB in the main process, up to 291 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| analysis:task_type | 41.2 | 222 | 291 |
| analysis:escalated | 34.6 | 227 | 291 |
| analysis:cloud_role | 32.5 | 230 | 291 |
| analysis:audit_null | 40.9 | 231 | 291 |
