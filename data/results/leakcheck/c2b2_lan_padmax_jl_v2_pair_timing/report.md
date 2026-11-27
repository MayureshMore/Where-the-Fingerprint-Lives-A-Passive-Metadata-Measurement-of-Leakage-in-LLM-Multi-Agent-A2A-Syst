# Leak check: C2B2 lan_padmax_jl, view v2, pair, timing alone

500 traces from 500 captures in `data/subsets/c2b2_lan_padmax_jl_pair` (0 skipped, 500 analysed as stripped copies). a2a-leakcheck 0.3.1, 2026-11-26T20:21:19-0800.

**Audit completed**: 1 attributes, 1 LEAK, 0 NO LEAK, 0 INCONCLUSIVE.

**Release policy satisfied** (baseline); exit 0.

Vantage `v2`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 0 of 500 traces show no flow there (0 expected: not escalated, per the sidecar, and this view sees only cloud agents; 0 unexpectedly empty); they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge |
|---|---|---|---|
| edge_cloud | 500 | 500 | 0 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **LEAK** | medium | 0.682 [0.638, 0.718] | 0.550 | 0.010 | 0.00 | timing (alone matches all) |

## task_type

**LEAK**: CI lower bound 0.638 > chance + margin 0.550.

500 samples in 500 groups; classes fault_diagnosis 250, sensor_analysis 250.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.682 [0.638, 0.718] | — | — |
| sizes only | 139 | 0.333 [0.313, 0.352] | +0.348 [+0.299, +0.391] | no |
| timing only | 30 | 0.682 [0.638, 0.718] | +0.000 [+0.000, +0.000] | yes |
| counts and direction only | 26 | 0.333 [0.313, 0.352] | +0.348 [+0.299, +0.391] | no |
| first_request_bytes only | 1 | 0.333 [0.313, 0.352] | +0.348 [+0.299, +0.391] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.36 (share of the way from chance to perfect); severity medium.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (500 groups): macro-F1 0.694 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.499, max 0.576; verdicts on permuted labels: 0 LEAK, 57 NO LEAK, 42 INCONCLUSIVE.

- **padding-not-enough-timing**: The requests are padded, yet the attribute still leaks and timing carries it: padding is not enough. Shape the response timing as well (replies at a fixed rate or in batches, delays that do not follow the work done), then re-run the audit.

## Against the baseline

Baseline: `data/results/leakcheck/c2b2_lan_padmax_v2_pair_timing/report.json`.

- no verdict changed

## Runtime

27.5 s in all (features 0.0 s, analysis 27.5 s); peak memory 193 MB in the main process, up to 264 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| analysis:task_type | 27.2 | 193 | 264 |
