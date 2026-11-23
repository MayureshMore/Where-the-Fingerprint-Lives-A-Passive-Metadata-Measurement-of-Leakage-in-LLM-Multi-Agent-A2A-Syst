# Leak check: C2B1 lan_padmax, view v1

500 traces from 500 captures in `data/raw_c2b1_padmax` (0 skipped, 500 analysed as stripped copies). a2a-leakcheck 0.3.0, 2026-11-22T17:41:30-0800.

**Audit completed**: 4 attributes, 3 LEAK, 1 NO LEAK, 0 INCONCLUSIVE.

**Release policy**: none configured, so the run exits 0 whatever the verdicts (gate a release with --baseline, --fail-on-leak, --strict or --require).

Vantage `v1`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 0 of 500 traces show no flow there; they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge | ticket |
|---|---|---|---|---|
| edge_cloud | 500 | 250 | 125 | 500 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **LEAK** | high | 0.796 [0.762, 0.825] | 0.300 | 0.010 | 0.00 | sizes (alone matches all) |
| escalated | **LEAK** | high | 0.992 [0.979, 1.000] | 0.550 | 0.010 | 0.00 | first_request_bytes alone |
| cloud_role | **LEAK** | high | 0.985 [0.972, 0.997] | 0.550 | 0.010 | 0.00 | timing (alone matches all) |
| audit_null | **NO LEAK** | none | 0.236 [0.201, 0.273] | 0.300 | 0.630 | 0.00 | — |

## task_type

**LEAK**: CI lower bound 0.762 > chance + margin 0.300.

500 samples in 498 groups; classes alert_triage 125, fault_diagnosis 125, procedure_lookup 125, sensor_analysis 125.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.796 [0.762, 0.825] | — | — |
| sizes only | 139 | 0.792 [0.759, 0.821] | +0.004 [-0.022, +0.030] | yes |
| timing only | 30 | 0.772 [0.741, 0.805] | +0.024 [-0.009, +0.057] | no |
| counts and direction only | 26 | 0.557 [0.519, 0.594] | +0.239 [+0.194, +0.285] | no |
| first_request_bytes only | 1 | 0.375 [0.361, 0.388] | +0.421 [+0.385, +0.452] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.73 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (498 groups): macro-F1 0.800 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.250, max 0.320; verdicts on permuted labels: 0 LEAK, 72 NO LEAK, 27 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

- **pad-local-posts**: This view also sees requests that are not padded, such as posts to a local service (in C2, the ticket service on the building network). Pad posts to local services too, then re-run the audit; the audit of a view without them shows what they add.

## escalated

**LEAK**: CI lower bound 0.979 > chance + margin 0.550.

500 samples in 498 groups; classes no 125, yes 375.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.992 [0.979, 1.000] | — | — |
| sizes only | 139 | 0.997 [0.991, 1.000] | -0.005 [-0.018, +0.005] | yes |
| timing only | 30 | 0.997 [0.992, 1.000] | -0.005 [-0.020, +0.005] | yes |
| counts and direction only | 26 | 0.992 [0.979, 1.000] | +0.000 [+0.000, +0.000] | yes |
| first_request_bytes only | 1 | 1.000 [1.000, 1.000] | -0.008 [-0.021, +0.000] | yes |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.98 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (498 groups): macro-F1 1.000 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.498, max 0.575; verdicts on permuted labels: 0 LEAK, 63 NO LEAK, 36 INCONCLUSIVE.

- **hide-escalation**: Whether the edge called the cloud is visible from the connections themselves, and padding cannot hide a call that did or did not happen. Make every task look alike upstream: dummy cloud calls at a fixed rate (cover traffic), or send every task to the cloud. Then re-run the audit.

## cloud_role

**LEAK**: CI lower bound 0.972 > chance + margin 0.550.

375 samples in 373 groups; classes diagnostics 250, knowledge 125.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.985 [0.972, 0.997] | — | — |
| sizes only | 139 | 0.979 [0.963, 0.994] | +0.006 [-0.009, +0.023] | yes |
| timing only | 30 | 0.985 [0.972, 0.997] | +0.000 [+0.000, +0.000] | yes |
| counts and direction only | 26 | 0.701 [0.655, 0.747] | +0.284 [+0.235, +0.334] | no |
| first_request_bytes only | 1 | 0.400 [0.383, 0.416] | +0.585 [+0.564, +0.606] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.97 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (373 groups): macro-F1 0.991 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.493, max 0.563; verdicts on permuted labels: 0 LEAK, 59 NO LEAK, 40 INCONCLUSIVE.

- **one-cloud-front-end**: Each cloud agent has its own address and TLS server name, which tell an observer which agent served the task whatever the traffic's shape (this audit scores the shape alone). Put the cloud agents behind one front end, one address and server name, then re-run the audit to see whether the shape still gives the agent away.

## audit_null

**NO LEAK**: CI upper bound 0.273 <= chance + margin 0.300.

500 samples in 498 groups; classes a 123, b 134, c 123, d 120.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.236 [0.201, 0.273] | — | — |
| sizes only | 139 | 0.254 [0.214, 0.292] | -0.018 [-0.053, +0.015] | yes |
| timing only | 30 | 0.229 [0.195, 0.265] | +0.007 [-0.038, +0.055] | no |
| counts and direction only | 26 | 0.274 [0.236, 0.313] | -0.039 [-0.081, +0.005] | yes |
| first_request_bytes only | 1 | 0.200 [0.168, 0.233] | +0.036 [-0.017, +0.083] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size -0.02 (share of the way from chance to perfect); severity none.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (498 groups): macro-F1 0.240 on the real labels): p = 0.630; permuted-label macro-F1 mean 0.249, max 0.302; verdicts on permuted labels: 0 LEAK, 63 NO LEAK, 36 INCONCLUSIVE.

## Runtime

149.2 s in all (collection 0.3 s, extraction 11.6 s, analysis 137.3 s); peak memory 274 MB in the main process, up to 265 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.3 | 168 | — |
| extraction | 11.6 | 243 | — |
| analysis:task_type | 35.0 | 264 | 263 |
| analysis:escalated | 28.0 | 269 | 263 |
| analysis:cloud_role | 27.4 | 272 | 263 |
| analysis:audit_null | 45.8 | 274 | 265 |
