# Leak check: C2B1+C2B1X lan_shaped, view v2, pair

1250 traces from 1250 captures in `data/subsets/c2b1_c2b1x_lan_shaped_pair` (0 skipped, 1250 analysed as stripped copies). a2a-leakcheck 0.3.0, 2026-11-22T17:54:27-0800.

**Audit completed**: 1 attributes, 0 LEAK, 1 NO LEAK, 0 INCONCLUSIVE.

**Release policy satisfied** (baseline); exit 0.

Vantage `v2`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 0 of 1250 traces show no flow there; they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge |
|---|---|---|---|
| edge_cloud | 1250 | 1250 | 0 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **NO LEAK** | none | 0.514 [0.485, 0.540] | 0.550 | 0.260 | 0.00 | — |

## task_type

**NO LEAK**: CI upper bound 0.540 <= chance + margin 0.550.

1250 samples in 1250 groups; classes fault_diagnosis 625, sensor_analysis 625.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.514 [0.485, 0.540] | — | — |
| sizes only | 139 | 0.481 [0.453, 0.509] | +0.034 [+0.002, +0.065] | no |
| timing only | 30 | 0.539 [0.510, 0.569] | -0.024 [-0.054, +0.002] | yes |
| counts and direction only | 26 | 0.519 [0.490, 0.547] | -0.005 [-0.040, +0.029] | yes |
| first_request_bytes only | 1 | 0.333 [0.321, 0.346] | +0.181 [+0.148, +0.212] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.03 (share of the way from chance to perfect); severity none.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (1250 groups): macro-F1 0.512 on the real labels): p = 0.260; permuted-label macro-F1 mean 0.499, max 0.546; verdicts on permuted labels: 0 LEAK, 91 NO LEAK, 8 INCONCLUSIVE.

## Against the baseline

Baseline: `data/results/leakcheck/c2b1_lan_padmax_v2_pair/report.json`.

- task_type: LEAK → NO LEAK

Resolved (LEAK in the baseline, NO LEAK now): task_type

## Runtime

59.1 s in all (collection 0.4 s, extraction 9.3 s, analysis 49.3 s); peak memory 297 MB in the main process, up to 330 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.4 | 169 | — |
| extraction | 9.3 | 245 | — |
| analysis:task_type | 49.0 | 297 | 330 |
