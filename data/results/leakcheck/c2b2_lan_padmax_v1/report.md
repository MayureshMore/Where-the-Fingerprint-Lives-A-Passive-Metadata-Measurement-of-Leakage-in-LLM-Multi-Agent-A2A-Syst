# Leak check: C2B2 lan_padmax, view v1

1000 traces from 1000 captures in `data/raw_c2b2_padmax` (0 skipped, 1000 analysed as stripped copies). a2a-leakcheck 0.3.1, 2026-11-26T19:44:06-0800.

**Audit completed**: 4 attributes, 3 LEAK, 1 NO LEAK, 0 INCONCLUSIVE.

**Release policy**: none configured, so the run exits 0 whatever the verdicts (gate a release with --baseline, --fail-on-leak, --strict or --require).

Vantage `v1`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 0 of 1000 traces show no flow there (0 expected: not escalated, per the sidecar, and this view sees only cloud agents; 0 unexpectedly empty); they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge | ticket |
|---|---|---|---|---|
| edge_cloud | 1000 | 500 | 250 | 1000 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **LEAK** | high | 0.837 [0.816, 0.857] | 0.300 | 0.010 | 0.00 | sizes (alone matches all) |
| escalated | **LEAK** | high | 1.000 [1.000, 1.000] | 0.550 | 0.010 | 0.00 | first_request_bytes alone |
| cloud_role | **LEAK** | high | 0.994 [0.987, 0.999] | 0.550 | 0.010 | 0.00 | timing (alone matches all) |
| audit_null | **NO LEAK** | none | 0.229 [0.202, 0.255] | 0.300 | 0.780 | 0.00 | — |

## task_type

**LEAK**: CI lower bound 0.816 > chance + margin 0.300.

1000 samples in 1000 groups; classes alert_triage 250, fault_diagnosis 250, procedure_lookup 250, sensor_analysis 250.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.837 [0.816, 0.857] | — | — |
| sizes only | 139 | 0.816 [0.795, 0.838] | +0.021 [+0.002, +0.039] | yes |
| timing only | 30 | 0.801 [0.780, 0.822] | +0.036 [+0.016, +0.059] | no |
| counts and direction only | 26 | 0.624 [0.594, 0.653] | +0.213 [+0.182, +0.245] | no |
| first_request_bytes only | 1 | 0.375 [0.366, 0.385] | +0.462 [+0.439, +0.483] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.78 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (1000 groups): macro-F1 0.844 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.249, max 0.284; verdicts on permuted labels: 0 LEAK, 91 NO LEAK, 8 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

- **pad-local-posts**: This view also sees requests that are not padded, such as posts to a local service (in C2, the ticket service on the building network). Pad posts to local services too, then re-run the audit; the audit of a view without them shows what they add.

## escalated

**LEAK**: CI lower bound 1.000 > chance + margin 0.550.

1000 samples in 1000 groups; classes no 250, yes 750.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 1.000 [1.000, 1.000] | — | — |
| sizes only | 139 | 0.999 [0.996, 1.000] | +0.001 [+0.000, +0.004] | yes |
| timing only | 30 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |
| counts and direction only | 26 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |
| first_request_bytes only | 1 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 1.00 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (1000 groups): macro-F1 1.000 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.497, max 0.550; verdicts on permuted labels: 0 LEAK, 81 NO LEAK, 18 INCONCLUSIVE.

- **hide-escalation**: Whether the edge called the cloud is visible from the connections themselves, and padding cannot hide a call that did or did not happen. Make every task look alike upstream: dummy cloud calls at a fixed rate (cover traffic), or send every task to the cloud. Then re-run the audit.

## cloud_role

**LEAK**: CI lower bound 0.987 > chance + margin 0.550.

750 samples in 750 groups; classes diagnostics 500, knowledge 250.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.994 [0.987, 0.999] | — | — |
| sizes only | 139 | 0.985 [0.975, 0.994] | +0.009 [-0.000, +0.019] | yes |
| timing only | 30 | 0.988 [0.979, 0.995] | +0.006 [+0.000, +0.014] | yes |
| counts and direction only | 26 | 0.720 [0.687, 0.753] | +0.274 [+0.243, +0.308] | no |
| first_request_bytes only | 1 | 0.400 [0.388, 0.411] | +0.594 [+0.581, +0.607] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.99 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (750 groups): macro-F1 0.993 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.497, max 0.555; verdicts on permuted labels: 0 LEAK, 79 NO LEAK, 20 INCONCLUSIVE.

- **one-cloud-front-end**: Each cloud agent has its own address and TLS server name, which tell an observer which agent served the task whatever the traffic's shape (this audit scores the shape alone). Put the cloud agents behind one front end, one address and server name, then re-run the audit to see whether the shape still gives the agent away.

## audit_null

**NO LEAK**: CI upper bound 0.255 <= chance + margin 0.300.

1000 samples in 1000 groups; classes a 249, b 244, c 248, d 259.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.229 [0.202, 0.255] | — | — |
| sizes only | 139 | 0.254 [0.225, 0.279] | -0.025 [-0.051, +0.001] | yes |
| timing only | 30 | 0.244 [0.218, 0.269] | -0.014 [-0.048, +0.018] | yes |
| counts and direction only | 26 | 0.250 [0.222, 0.276] | -0.021 [-0.057, +0.016] | yes |
| first_request_bytes only | 1 | 0.196 [0.172, 0.220] | +0.033 [-0.003, +0.067] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size -0.03 (share of the way from chance to perfect); severity none.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (1000 groups): macro-F1 0.238 on the real labels): p = 0.780; permuted-label macro-F1 mean 0.252, max 0.287; verdicts on permuted labels: 0 LEAK, 88 NO LEAK, 11 INCONCLUSIVE.

## Runtime

230.3 s in all (collection 1.5 s, extraction 24.0 s, analysis 204.7 s); peak memory 305 MB in the main process, up to 314 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 1.5 | 172 | — |
| extraction | 24.0 | 248 | — |
| analysis:task_type | 54.7 | 299 | 307 |
| analysis:escalated | 41.8 | 302 | 307 |
| analysis:cloud_role | 39.1 | 303 | 307 |
| analysis:audit_null | 68.1 | 305 | 314 |
