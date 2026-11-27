# Leak check: C2B2 lan_padmax, view v2

1000 traces from 1000 captures in `data/raw_c2b2_padmax` (0 skipped, 1000 analysed as stripped copies). a2a-leakcheck 0.3.1, 2026-11-26T19:54:39-0800.

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
| task_type | **LEAK** | high | 0.847 [0.827, 0.866] | 0.300 | 0.010 | 0.00 | sizes (alone matches all) |
| escalated | **LEAK** | high | 1.000 [1.000, 1.000] | 0.550 | 0.010 | 0.00 | first_request_bytes alone |
| cloud_role | **LEAK** | high | 0.995 [0.989, 1.000] | 0.550 | 0.010 | 0.00 | timing (alone matches all) |
| audit_null | **NO LEAK** | none | 0.245 [0.219, 0.270] | 0.300 | 0.430 | 0.00 | — |

## task_type

**LEAK**: CI lower bound 0.827 > chance + margin 0.300.

1000 samples in 1000 groups; classes alert_triage 250, fault_diagnosis 250, procedure_lookup 250, sensor_analysis 250.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.847 [0.827, 0.866] | — | — |
| sizes only | 139 | 0.827 [0.806, 0.848] | +0.020 [+0.002, +0.038] | yes |
| timing only | 30 | 0.814 [0.794, 0.835] | +0.033 [+0.010, +0.056] | no |
| counts and direction only | 26 | 0.613 [0.587, 0.640] | +0.234 [+0.205, +0.265] | no |
| first_request_bytes only | 1 | 0.375 [0.366, 0.385] | +0.472 [+0.450, +0.494] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.80 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (1000 groups): macro-F1 0.835 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.243, max 0.276; verdicts on permuted labels: 0 LEAK, 97 NO LEAK, 2 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

## escalated

**LEAK**: CI lower bound 1.000 > chance + margin 0.550.

1000 samples in 1000 groups; classes no 250, yes 750.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 1.000 [1.000, 1.000] | — | — |
| sizes only | 139 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |
| timing only | 30 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |
| counts and direction only | 26 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |
| first_request_bytes only | 1 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 1.00 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (1000 groups): macro-F1 1.000 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.493, max 0.542; verdicts on permuted labels: 0 LEAK, 90 NO LEAK, 9 INCONCLUSIVE.

- **hide-escalation**: Whether the edge called the cloud is visible from the connections themselves, and padding cannot hide a call that did or did not happen. Make every task look alike upstream: dummy cloud calls at a fixed rate (cover traffic), or send every task to the cloud. Then re-run the audit.

## cloud_role

**LEAK**: CI lower bound 0.989 > chance + margin 0.550.

750 samples in 750 groups; classes diagnostics 500, knowledge 250.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.995 [0.989, 1.000] | — | — |
| sizes only | 139 | 0.988 [0.979, 0.996] | +0.007 [-0.000, +0.016] | yes |
| timing only | 30 | 0.991 [0.983, 0.997] | +0.005 [+0.000, +0.010] | yes |
| counts and direction only | 26 | 0.709 [0.675, 0.742] | +0.287 [+0.254, +0.321] | no |
| first_request_bytes only | 1 | 0.400 [0.388, 0.411] | +0.595 [+0.583, +0.609] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.99 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (750 groups): macro-F1 0.996 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.497, max 0.543; verdicts on permuted labels: 0 LEAK, 77 NO LEAK, 22 INCONCLUSIVE.

- **one-cloud-front-end**: Each cloud agent has its own address and TLS server name, which tell an observer which agent served the task whatever the traffic's shape (this audit scores the shape alone). Put the cloud agents behind one front end, one address and server name, then re-run the audit to see whether the shape still gives the agent away.

## audit_null

**NO LEAK**: CI upper bound 0.270 <= chance + margin 0.300.

1000 samples in 1000 groups; classes a 249, b 244, c 248, d 259.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.245 [0.219, 0.270] | — | — |
| sizes only | 139 | 0.243 [0.216, 0.268] | +0.002 [-0.021, +0.025] | yes |
| timing only | 30 | 0.248 [0.222, 0.273] | -0.004 [-0.032, +0.026] | yes |
| counts and direction only | 26 | 0.255 [0.227, 0.281] | -0.010 [-0.043, +0.022] | yes |
| first_request_bytes only | 1 | 0.207 [0.184, 0.229] | +0.038 [+0.010, +0.069] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size -0.01 (share of the way from chance to perfect); severity none.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (1000 groups): macro-F1 0.249 on the real labels): p = 0.430; permuted-label macro-F1 mean 0.244, max 0.280; verdicts on permuted labels: 0 LEAK, 97 NO LEAK, 2 INCONCLUSIVE.

## Runtime

195.6 s in all (collection 1.3 s, extraction 23.5 s, analysis 170.7 s); peak memory 305 MB in the main process, up to 314 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 1.3 | 172 | — |
| extraction | 23.5 | 249 | — |
| analysis:task_type | 48.6 | 299 | 314 |
| analysis:escalated | 37.6 | 302 | 314 |
| analysis:cloud_role | 34.9 | 303 | 314 |
| analysis:audit_null | 48.7 | 305 | 314 |
