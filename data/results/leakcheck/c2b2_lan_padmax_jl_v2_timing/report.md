# Leak check: C2B2 lan_padmax_jl, view v2, timing alone

1000 traces from 1000 captures in `data/raw_c2b2_padmax_jl` (0 skipped, 1000 analysed as stripped copies). a2a-leakcheck 0.3.1, 2026-11-26T20:19:33-0800.

**Audit completed**: 4 attributes, 3 LEAK, 1 NO LEAK, 0 INCONCLUSIVE.

**Release policy satisfied** (baseline); exit 0.

Vantage `v2`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 250 of 1000 traces show no flow there (250 expected: not escalated, per the sidecar, and this view sees only cloud agents; 0 unexpectedly empty); they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge |
|---|---|---|---|
| edge_cloud | 1000 | 500 | 250 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **LEAK** | high | 0.850 [0.830, 0.870] | 0.300 | 0.010 | 0.00 | timing (alone matches all) |
| escalated | **LEAK** | high | 1.000 [1.000, 1.000] | 0.550 | 0.010 | 0.00 | timing (alone matches all) |
| cloud_role | **LEAK** | high | 0.998 [0.995, 1.000] | 0.550 | 0.010 | 0.00 | timing (alone matches all) |
| audit_null | **NO LEAK** | none | 0.233 [0.206, 0.259] | 0.300 | 0.760 | 0.00 | — |

## task_type

**LEAK**: CI lower bound 0.830 > chance + margin 0.300.

1000 samples in 1000 groups; classes alert_triage 250, fault_diagnosis 250, procedure_lookup 250, sensor_analysis 250.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.850 [0.830, 0.870] | — | — |
| sizes only | 139 | 0.100 [0.091, 0.108] | +0.750 [+0.727, +0.774] | no |
| timing only | 30 | 0.850 [0.830, 0.870] | +0.000 [+0.000, +0.000] | yes |
| counts and direction only | 26 | 0.100 [0.091, 0.108] | +0.750 [+0.727, +0.774] | no |
| first_request_bytes only | 1 | 0.100 [0.091, 0.108] | +0.750 [+0.727, +0.774] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.80 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (1000 groups): macro-F1 0.855 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.245, max 0.288; verdicts on permuted labels: 0 LEAK, 91 NO LEAK, 8 INCONCLUSIVE.

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

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (1000 groups): macro-F1 1.000 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.493, max 0.536; verdicts on permuted labels: 0 LEAK, 92 NO LEAK, 7 INCONCLUSIVE.

- **hide-escalation**: Whether the edge called the cloud is visible from the connections themselves, and padding cannot hide a call that did or did not happen. Make every task look alike upstream: dummy cloud calls at a fixed rate (cover traffic), or send every task to the cloud. Then re-run the audit.

## cloud_role

**LEAK**: CI lower bound 0.995 > chance + margin 0.550.

750 samples in 750 groups; classes diagnostics 500, knowledge 250.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.998 [0.995, 1.000] | — | — |
| sizes only | 139 | 0.400 [0.388, 0.411] | +0.598 [+0.586, +0.611] | no |
| timing only | 30 | 0.998 [0.995, 1.000] | +0.000 [+0.000, +0.000] | yes |
| counts and direction only | 26 | 0.400 [0.388, 0.411] | +0.598 [+0.586, +0.611] | no |
| first_request_bytes only | 1 | 0.400 [0.388, 0.411] | +0.598 [+0.586, +0.611] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 1.00 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (750 groups): macro-F1 0.997 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.499, max 0.549; verdicts on permuted labels: 0 LEAK, 74 NO LEAK, 25 INCONCLUSIVE.

- **one-cloud-front-end**: Each cloud agent has its own address and TLS server name, which tell an observer which agent served the task whatever the traffic's shape (this audit scores the shape alone). Put the cloud agents behind one front end, one address and server name, then re-run the audit to see whether the shape still gives the agent away.

## audit_null

**NO LEAK**: CI upper bound 0.259 <= chance + margin 0.300.

1000 samples in 1000 groups; classes a 249, b 244, c 248, d 259.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.233 [0.206, 0.259] | — | — |
| sizes only | 139 | 0.100 [0.091, 0.108] | +0.133 [+0.106, +0.159] | no |
| timing only | 30 | 0.233 [0.206, 0.259] | +0.000 [+0.000, +0.000] | yes |
| counts and direction only | 26 | 0.100 [0.091, 0.108] | +0.133 [+0.106, +0.159] | no |
| first_request_bytes only | 1 | 0.100 [0.091, 0.108] | +0.133 [+0.106, +0.159] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size -0.02 (share of the way from chance to perfect); severity none.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (1000 groups): macro-F1 0.231 on the real labels): p = 0.760; permuted-label macro-F1 mean 0.243, max 0.285; verdicts on permuted labels: 0 LEAK, 95 NO LEAK, 4 INCONCLUSIVE.

## Against the baseline

Baseline: `data/results/leakcheck/c2b2_lan_padmax_v2_timing/report.json`.

- no verdict changed

## Runtime

149.5 s in all (features 0.0 s, analysis 149.4 s); peak memory 237 MB in the main process, up to 296 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| analysis:task_type | 40.9 | 224 | 290 |
| analysis:escalated | 34.4 | 231 | 290 |
| analysis:cloud_role | 31.9 | 237 | 290 |
| analysis:audit_null | 41.2 | 237 | 296 |
