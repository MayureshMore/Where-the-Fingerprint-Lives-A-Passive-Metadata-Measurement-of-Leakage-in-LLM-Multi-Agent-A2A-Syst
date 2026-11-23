# Leak check: C2B1 lan_shaped, view v1, escalated_only

375 traces from 375 captures in `data/subsets/c2b1_lan_shaped_escalated_only` (0 skipped, 375 analysed as stripped copies). a2a-leakcheck 0.3.0, 2026-11-22T17:49:23-0800.

**Audit completed**: 1 attributes, 0 LEAK, 0 NO LEAK, 1 INCONCLUSIVE.

**Release policy satisfied** (baseline); exit 0.

**For review**: task_type (INCONCLUSIVE; LEAK in the baseline).

Vantage `v1`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 0 of 375 traces show no flow there; they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge | ticket |
|---|---|---|---|---|
| edge_cloud | 375 | 250 | 125 | 375 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **INCONCLUSIVE** | none | 0.432 [0.380, 0.478] | 0.383 | 0.010 | 0.00 | — |

## task_type

**INCONCLUSIVE**: CI [0.380, 0.478] straddles chance + margin 0.383.

375 samples in 373 groups; classes fault_diagnosis 125, procedure_lookup 125, sensor_analysis 125.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.432 [0.380, 0.478] | — | — |
| sizes only | 139 | 0.453 [0.404, 0.501] | -0.021 [-0.069, +0.026] | yes |
| timing only | 30 | 0.375 [0.329, 0.425] | +0.057 [-0.005, +0.116] | no |
| counts and direction only | 26 | 0.352 [0.303, 0.398] | +0.080 [+0.014, +0.144] | no |
| first_request_bytes only | 1 | 0.167 [0.148, 0.184] | +0.265 [+0.211, +0.313] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.15 (share of the way from chance to perfect); severity none.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (373 groups): macro-F1 0.427 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.336, max 0.389; verdicts on permuted labels: 0 LEAK, 45 NO LEAK, 54 INCONCLUSIVE.

- **inconclusive**: The interval straddles chance + margin: more traces will narrow it. Re-run before treating this attribute as safe.

## Against the baseline

Baseline: `data/results/leakcheck/c2b1_lan_padmax_v1_escalated_only/report.json`.

- task_type: LEAK → INCONCLUSIVE

**Needs review**: task_type (LEAK in the baseline, INCONCLUSIVE now: the leak is not shown to be gone).

## Runtime

32.5 s in all (collection 0.1 s, extraction 3.3 s, analysis 28.9 s); peak memory 258 MB in the main process, up to 256 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.1 | 171 | — |
| extraction | 3.3 | 243 | — |
| analysis:task_type | 28.7 | 258 | 256 |
