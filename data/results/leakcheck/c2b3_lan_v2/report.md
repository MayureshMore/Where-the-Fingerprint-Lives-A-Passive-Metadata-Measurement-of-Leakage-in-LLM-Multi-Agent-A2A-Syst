# Leak check: C2B3 lan, view v2

1000 traces from 1000 captures in `data/raw_c2b3_lan` (0 skipped, 1000 analysed as stripped copies). a2a-leakcheck 0.3.0, 2026-11-24T18:00:43-0800.

**Audit completed**: 4 attributes, 3 LEAK, 1 NO LEAK, 0 INCONCLUSIVE.

**Release policy**: none configured, so the run exits 0 whatever the verdicts (gate a release with --baseline, --fail-on-leak, --strict or --require).

Vantage `v2`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 250 of 1000 traces show no flow there; they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge |
|---|---|---|---|
| edge_cloud | 1000 | 500 | 250 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **LEAK** | high | 0.956 [0.943, 0.968] | 0.300 | 0.010 | 0.00 | sizes (alone matches all) |
| escalated | **LEAK** | high | 1.000 [1.000, 1.000] | 0.550 | 0.010 | 0.00 | first_request_bytes alone |
| cloud_role | **LEAK** | high | 0.997 [0.992, 1.000] | 0.550 | 0.010 | 0.00 | first_request_bytes alone |
| audit_null | **NO LEAK** | none | 0.239 [0.214, 0.266] | 0.300 | 0.960 | 0.00 | — |

## task_type

**LEAK**: CI lower bound 0.943 > chance + margin 0.300.

1000 samples in 978 groups; classes alert_triage 250, fault_diagnosis 250, procedure_lookup 250, sensor_analysis 250.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.956 [0.943, 0.968] | — | — |
| sizes only | 139 | 0.958 [0.945, 0.970] | -0.002 [-0.010, +0.006] | yes |
| timing only | 30 | 0.840 [0.818, 0.862] | +0.116 [+0.093, +0.140] | no |
| counts and direction only | 26 | 0.735 [0.709, 0.760] | +0.221 [+0.191, +0.249] | no |
| first_request_bytes only | 1 | 0.796 [0.773, 0.818] | +0.160 [+0.137, +0.184] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.94 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (978 groups): macro-F1 0.956 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.245, max 0.275; verdicts on permuted labels: 0 LEAK, 98 NO LEAK, 1 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

## escalated

**LEAK**: CI lower bound 1.000 > chance + margin 0.550.

1000 samples in 978 groups; classes no 250, yes 750.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 1.000 [1.000, 1.000] | — | — |
| sizes only | 139 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |
| timing only | 30 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |
| counts and direction only | 26 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |
| first_request_bytes only | 1 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 1.00 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (978 groups): macro-F1 1.000 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.494, max 0.547; verdicts on permuted labels: 0 LEAK, 89 NO LEAK, 10 INCONCLUSIVE.

- **hide-escalation**: Whether the edge called the cloud is visible from the connections themselves, and padding cannot hide a call that did or did not happen. Make every task look alike upstream: dummy cloud calls at a fixed rate (cover traffic), or send every task to the cloud. Then re-run the audit.

## cloud_role

**LEAK**: CI lower bound 0.992 > chance + margin 0.550.

750 samples in 734 groups; classes diagnostics 500, knowledge 250.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.997 [0.992, 1.000] | — | — |
| sizes only | 139 | 0.997 [0.992, 1.000] | +0.000 [-0.006, +0.006] | yes |
| timing only | 30 | 0.997 [0.992, 1.000] | +0.000 [+0.000, +0.000] | yes |
| counts and direction only | 26 | 0.893 [0.870, 0.915] | +0.104 [+0.081, +0.128] | no |
| first_request_bytes only | 1 | 0.998 [0.995, 1.000] | -0.002 [-0.006, +0.003] | yes |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.99 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (734 groups): macro-F1 0.999 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.500, max 0.543; verdicts on permuted labels: 0 LEAK, 72 NO LEAK, 27 INCONCLUSIVE.

- **one-cloud-front-end**: Each cloud agent has its own address and TLS server name, which tell an observer which agent served the task whatever the traffic's shape (this audit scores the shape alone). Put the cloud agents behind one front end, one address and server name, then re-run the audit to see whether the shape still gives the agent away.

## audit_null

**NO LEAK**: CI upper bound 0.266 <= chance + margin 0.300.

1000 samples in 978 groups; classes a 247, b 242, c 271, d 240.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.239 [0.214, 0.266] | — | — |
| sizes only | 139 | 0.239 [0.213, 0.267] | +0.000 [-0.022, +0.022] | yes |
| timing only | 30 | 0.253 [0.226, 0.281] | -0.014 [-0.047, +0.019] | yes |
| counts and direction only | 26 | 0.239 [0.214, 0.266] | -0.000 [-0.032, +0.031] | yes |
| first_request_bytes only | 1 | 0.223 [0.198, 0.249] | +0.016 [-0.013, +0.049] | yes |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size -0.01 (share of the way from chance to perfect); severity none.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (978 groups): macro-F1 0.223 on the real labels): p = 0.960; permuted-label macro-F1 mean 0.245, max 0.286; verdicts on permuted labels: 0 LEAK, 97 NO LEAK, 2 INCONCLUSIVE.

## Runtime

185.8 s in all (collection 0.9 s, extraction 23.0 s, analysis 161.8 s); peak memory 308 MB in the main process, up to 309 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.9 | 167 | — |
| extraction | 23.0 | 244 | — |
| analysis:task_type | 44.3 | 293 | 303 |
| analysis:escalated | 35.2 | 297 | 303 |
| analysis:cloud_role | 33.0 | 306 | 303 |
| analysis:audit_null | 48.4 | 308 | 309 |
