# Leak check: example: c2_ci_baseline, view v2

20 traces from 20 captures in `examples/c2_ci_baseline` (0 skipped, 0 analysed as stripped copies). a2a-leakcheck 0.1.0, 2026-11-14T12:30:06-0800.

Vantage `v2`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 0 of 20 traces show no flow there; they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge |
|---|---|---|---|
| edge_cloud | 20 | 20 | 0 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **INCONCLUSIVE** | none | — | 0.550 | — | — | — |

## task_type

**INCONCLUSIVE**: too few samples: fault_diagnosis: 10 samples < 20; sensor_analysis: 10 samples < 20.

20 samples in 20 groups; classes fault_diagnosis 10, sensor_analysis 10.

- **collect-more**: Too few samples per class for a verdict: collect more traces (at least min_per_class per class, from at least as many prompt groups as folds).

## Runtime

1.0 s in all (collection 0.0 s, extraction 0.9 s, analysis 0.0 s); peak memory 234 MB in the main process, up to 6 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.0 | 166 | — |
| extraction | 0.9 | 234 | — |
| analysis:task_type | 0.0 | 234 | 0 |
