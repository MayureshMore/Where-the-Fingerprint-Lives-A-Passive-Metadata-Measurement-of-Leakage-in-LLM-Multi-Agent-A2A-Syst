# Leak check: C2B3 lan, view v1

1000 traces from 1000 captures in `data/raw_c2b3_lan` (0 skipped, 1000 analysed as stripped copies). a2a-leakcheck 0.3.0, 2026-11-24T17:55:40-0800.

**Audit completed**: 4 attributes, 3 LEAK, 1 NO LEAK, 0 INCONCLUSIVE.

**Release policy**: none configured, so the run exits 0 whatever the verdicts (gate a release with --baseline, --fail-on-leak, --strict or --require).

Vantage `v1`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 0 of 1000 traces show no flow there; they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge | ticket |
|---|---|---|---|---|
| edge_cloud | 1000 | 500 | 250 | 1000 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **LEAK** | high | 0.960 [0.948, 0.971] | 0.300 | 0.010 | 0.00 | sizes (alone matches all) |
| escalated | **LEAK** | high | 1.000 [1.000, 1.000] | 0.550 | 0.010 | 0.00 | counts and direction (alone matches all) |
| cloud_role | **LEAK** | high | 0.997 [0.992, 1.000] | 0.550 | 0.010 | 0.00 | first_request_bytes alone |
| audit_null | **NO LEAK** | none | 0.238 [0.212, 0.263] | 0.300 | 0.810 | 0.00 | — |

## task_type

**LEAK**: CI lower bound 0.948 > chance + margin 0.300.

1000 samples in 978 groups; classes alert_triage 250, fault_diagnosis 250, procedure_lookup 250, sensor_analysis 250.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.960 [0.948, 0.971] | — | — |
| sizes only | 139 | 0.955 [0.942, 0.967] | +0.005 [-0.003, +0.014] | yes |
| timing only | 30 | 0.861 [0.841, 0.879] | +0.099 [+0.078, +0.122] | no |
| counts and direction only | 26 | 0.726 [0.702, 0.751] | +0.234 [+0.208, +0.260] | no |
| first_request_bytes only | 1 | 0.711 [0.684, 0.738] | +0.249 [+0.219, +0.278] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.95 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (978 groups): macro-F1 0.956 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.250, max 0.294; verdicts on permuted labels: 0 LEAK, 90 NO LEAK, 9 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

## escalated

**LEAK**: CI lower bound 1.000 > chance + margin 0.550.

1000 samples in 978 groups; classes no 250, yes 750.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 1.000 [1.000, 1.000] | — | — |
| sizes only | 139 | 0.999 [0.996, 1.000] | +0.001 [+0.000, +0.004] | yes |
| timing only | 30 | 0.999 [0.996, 1.000] | +0.001 [+0.000, +0.004] | yes |
| counts and direction only | 26 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |
| first_request_bytes only | 1 | 0.875 [0.850, 0.898] | +0.125 [+0.102, +0.150] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 1.00 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (978 groups): macro-F1 1.000 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.498, max 0.557; verdicts on permuted labels: 0 LEAK, 82 NO LEAK, 17 INCONCLUSIVE.

- **hide-escalation**: Whether the edge called the cloud is visible from the connections themselves, and padding cannot hide a call that did or did not happen. Make every task look alike upstream: dummy cloud calls at a fixed rate (cover traffic), or send every task to the cloud. Then re-run the audit.

## cloud_role

**LEAK**: CI lower bound 0.992 > chance + margin 0.550.

750 samples in 734 groups; classes diagnostics 500, knowledge 250.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.997 [0.992, 1.000] | — | — |
| sizes only | 139 | 0.997 [0.992, 1.000] | +0.000 [-0.006, +0.006] | yes |
| timing only | 30 | 0.997 [0.992, 1.000] | +0.000 [+0.000, +0.000] | yes |
| counts and direction only | 26 | 0.869 [0.845, 0.895] | +0.128 [+0.102, +0.154] | no |
| first_request_bytes only | 1 | 0.998 [0.995, 1.000] | -0.002 [-0.006, +0.003] | yes |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.99 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (734 groups): macro-F1 0.997 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.495, max 0.559; verdicts on permuted labels: 0 LEAK, 79 NO LEAK, 20 INCONCLUSIVE.

- **one-cloud-front-end**: Each cloud agent has its own address and TLS server name, which tell an observer which agent served the task whatever the traffic's shape (this audit scores the shape alone). Put the cloud agents behind one front end, one address and server name, then re-run the audit to see whether the shape still gives the agent away.

## audit_null

**NO LEAK**: CI upper bound 0.263 <= chance + margin 0.300.

1000 samples in 978 groups; classes a 247, b 242, c 271, d 240.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.238 [0.212, 0.263] | — | — |
| sizes only | 139 | 0.247 [0.222, 0.276] | -0.009 [-0.036, +0.019] | yes |
| timing only | 30 | 0.247 [0.221, 0.273] | -0.009 [-0.042, +0.022] | yes |
| counts and direction only | 26 | 0.272 [0.245, 0.300] | -0.034 [-0.070, -0.001] | yes |
| first_request_bytes only | 1 | 0.218 [0.192, 0.246] | +0.020 [-0.018, +0.055] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size -0.02 (share of the way from chance to perfect); severity none.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (978 groups): macro-F1 0.235 on the real labels): p = 0.810; permuted-label macro-F1 mean 0.249, max 0.281; verdicts on permuted labels: 0 LEAK, 93 NO LEAK, 6 INCONCLUSIVE.

## Runtime

216.8 s in all (collection 0.8 s, extraction 24.2 s, analysis 191.8 s); peak memory 304 MB in the main process, up to 330 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.8 | 170 | — |
| extraction | 24.2 | 247 | — |
| analysis:task_type | 50.3 | 294 | 287 |
| analysis:escalated | 41.5 | 298 | 287 |
| analysis:cloud_role | 37.3 | 303 | 287 |
| analysis:audit_null | 61.6 | 304 | 330 |
