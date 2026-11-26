# Leak check: C2B1M lan_shaped, view v1, pair

1250 traces from 1250 captures in `data/subsets/c2b1m_lan_shaped_pair` (0 skipped, 1250 analysed as stripped copies). a2a-leakcheck 0.3.1, 2026-11-25T23:31:53-0800.

**Audit completed**: 1 attributes, 0 LEAK, 0 NO LEAK, 1 INCONCLUSIVE.

**Release policy satisfied** (baseline); exit 0.

**For review**: task_type (INCONCLUSIVE; LEAK in the baseline).

Vantage `v1`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 0 of 1250 traces show no flow there (0 expected: not escalated, per the sidecar, and this view sees only cloud agents; 0 unexpectedly empty); they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge | ticket |
|---|---|---|---|---|
| edge_cloud | 1250 | 1250 | 0 | 1250 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **INCONCLUSIVE** | none | 0.571 [0.542, 0.598] | 0.550 | 0.010 | 0.00 | — |

## task_type

**INCONCLUSIVE**: CI [0.542, 0.598] straddles chance + margin 0.550.

1250 samples in 1250 groups; classes fault_diagnosis 625, sensor_analysis 625.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.571 [0.542, 0.598] | — | — |
| sizes only | 139 | 0.570 [0.542, 0.597] | +0.002 [-0.021, +0.026] | yes |
| timing only | 30 | 0.487 [0.456, 0.516] | +0.084 [+0.050, +0.118] | no |
| counts and direction only | 26 | 0.526 [0.498, 0.553] | +0.046 [+0.011, +0.082] | no |
| first_request_bytes only | 1 | 0.333 [0.321, 0.345] | +0.238 [+0.207, +0.268] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.14 (share of the way from chance to perfect); severity none.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (1250 groups): macro-F1 0.596 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.501, max 0.550; verdicts on permuted labels: 0 LEAK, 90 NO LEAK, 9 INCONCLUSIVE.

- **inconclusive-unpadded-in-view**: INCONCLUSIVE, yet the permutation test finds a signal (p at most alpha), and this view also sees requests that are not padded, such as posts to a local service (in C2 at V1, the ticket post on the building network). They may carry what is left: pad posts to local services too, or compare with the audit of a view without them, then re-run. Do not treat this attribute as safe.

- **inconclusive**: The interval straddles chance + margin: more traces will narrow it. Re-run before treating this attribute as safe.

## Against the baseline

Baseline: `data/results/leakcheck/c2b1m_lan_padmax_v1_pair/report.json`.

- task_type: LEAK → INCONCLUSIVE

**Needs review**: task_type (LEAK in the baseline, INCONCLUSIVE now: the leak is not shown to be gone).

## Runtime

66.2 s in all (collection 1.0 s, extraction 10.6 s, analysis 54.5 s); peak memory 299 MB in the main process, up to 358 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 1.0 | 171 | — |
| extraction | 10.6 | 247 | — |
| analysis:task_type | 54.2 | 299 | 358 |
