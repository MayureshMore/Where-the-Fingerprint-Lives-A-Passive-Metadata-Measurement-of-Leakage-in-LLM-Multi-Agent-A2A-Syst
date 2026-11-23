# Leak check: C2B1 lan_shaped, view v1, pair

250 traces from 250 captures in `data/subsets/c2b1_lan_shaped_pair` (0 skipped, 250 analysed as stripped copies). a2a-leakcheck 0.3.0, 2026-11-22T17:48:49-0800.

**Audit completed**: 1 attributes, 0 LEAK, 0 NO LEAK, 1 INCONCLUSIVE.

**Release policy satisfied** (baseline); exit 0.

**For review**: task_type (INCONCLUSIVE; LEAK in the baseline).

Vantage `v1`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 0 of 250 traces show no flow there; they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge | ticket |
|---|---|---|---|---|
| edge_cloud | 250 | 250 | 0 | 250 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **INCONCLUSIVE** | none | 0.552 [0.491, 0.608] | 0.550 | 0.010 | 0.00 | — |

## task_type

**INCONCLUSIVE**: CI [0.491, 0.608] straddles chance + margin 0.550.

250 samples in 250 groups; classes fault_diagnosis 125, sensor_analysis 125.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.552 [0.491, 0.608] | — | — |
| sizes only | 139 | 0.543 [0.476, 0.600] | +0.009 [-0.047, +0.066] | no |
| timing only | 30 | 0.548 [0.483, 0.604] | +0.004 [-0.072, +0.076] | no |
| counts and direction only | 26 | 0.520 [0.459, 0.580] | +0.032 [-0.040, +0.110] | no |
| first_request_bytes only | 1 | 0.333 [0.306, 0.361] | +0.219 [+0.153, +0.285] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.10 (share of the way from chance to perfect); severity none.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (250 groups): macro-F1 0.576 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.505, max 0.572; verdicts on permuted labels: 0 LEAK, 28 NO LEAK, 71 INCONCLUSIVE.

- **inconclusive**: The interval straddles chance + margin: more traces will narrow it. Re-run before treating this attribute as safe.

## Against the baseline

Baseline: `data/results/leakcheck/c2b1_lan_padmax_v1_pair/report.json`.

- task_type: LEAK → INCONCLUSIVE

**Needs review**: task_type (LEAK in the baseline, INCONCLUSIVE now: the leak is not shown to be gone).

## Runtime

25.1 s in all (collection 0.1 s, extraction 2.2 s, analysis 22.7 s); peak memory 247 MB in the main process, up to 235 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.1 | 171 | — |
| extraction | 2.2 | 237 | — |
| analysis:task_type | 22.5 | 247 | 235 |
