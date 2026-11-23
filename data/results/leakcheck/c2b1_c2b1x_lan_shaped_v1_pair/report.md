# Leak check: C2B1+C2B1X lan_shaped, view v1, pair

1250 traces from 1250 captures in `data/subsets/c2b1_c2b1x_lan_shaped_pair` (0 skipped, 1250 analysed as stripped copies). a2a-leakcheck 0.3.0, 2026-11-22T17:53:26-0800.

**Audit completed**: 1 attributes, 0 LEAK, 0 NO LEAK, 1 INCONCLUSIVE.

**Release policy satisfied** (baseline); exit 0.

**For review**: task_type (INCONCLUSIVE; LEAK in the baseline).

Vantage `v1`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 0 of 1250 traces show no flow there; they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge | ticket |
|---|---|---|---|---|
| edge_cloud | 1250 | 1250 | 0 | 1250 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **INCONCLUSIVE** | none | 0.544 [0.517, 0.571] | 0.550 | 0.010 | 0.00 | — |

## task_type

**INCONCLUSIVE**: CI [0.517, 0.571] straddles chance + margin 0.550.

1250 samples in 1250 groups; classes fault_diagnosis 625, sensor_analysis 625.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.544 [0.517, 0.571] | — | — |
| sizes only | 139 | 0.533 [0.505, 0.560] | +0.011 [-0.013, +0.036] | yes |
| timing only | 30 | 0.509 [0.481, 0.537] | +0.035 [+0.004, +0.069] | no |
| counts and direction only | 26 | 0.531 [0.503, 0.557] | +0.013 [-0.022, +0.047] | yes |
| first_request_bytes only | 1 | 0.333 [0.321, 0.346] | +0.210 [+0.181, +0.240] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.09 (share of the way from chance to perfect); severity none.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (1250 groups): macro-F1 0.560 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.498, max 0.533; verdicts on permuted labels: 0 LEAK, 93 NO LEAK, 6 INCONCLUSIVE.

- **inconclusive**: The interval straddles chance + margin: more traces will narrow it. Re-run before treating this attribute as safe.

## Against the baseline

Baseline: `data/results/leakcheck/c2b1_lan_padmax_v1_pair/report.json`.

- task_type: LEAK → INCONCLUSIVE

**Needs review**: task_type (LEAK in the baseline, INCONCLUSIVE now: the leak is not shown to be gone).

## Runtime

68.0 s in all (collection 0.4 s, extraction 10.2 s, analysis 57.2 s); peak memory 300 MB in the main process, up to 348 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.4 | 171 | — |
| extraction | 10.2 | 248 | — |
| analysis:task_type | 57.0 | 300 | 348 |
