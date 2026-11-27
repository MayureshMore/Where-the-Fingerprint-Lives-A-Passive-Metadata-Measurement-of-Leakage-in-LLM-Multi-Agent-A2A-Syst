# Leak check: C2B2 lan_padmax_jl, view v1, pair, timing alone

500 traces from 500 captures in `data/subsets/c2b2_lan_padmax_jl_pair` (0 skipped, 500 analysed as stripped copies). a2a-leakcheck 0.3.1, 2026-11-26T20:10:27-0800.

**Audit completed**: 1 attributes, 1 LEAK, 0 NO LEAK, 0 INCONCLUSIVE.

**Release policy satisfied** (baseline); exit 0.

Vantage `v1`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 0 of 500 traces show no flow there (0 expected: not escalated, per the sidecar, and this view sees only cloud agents; 0 unexpectedly empty); they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge | ticket |
|---|---|---|---|---|
| edge_cloud | 500 | 500 | 0 | 500 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **LEAK** | medium | 0.688 [0.645, 0.727] | 0.550 | 0.010 | 0.00 | timing (alone matches all) |

## task_type

**LEAK**: CI lower bound 0.645 > chance + margin 0.550.

500 samples in 500 groups; classes fault_diagnosis 250, sensor_analysis 250.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.688 [0.645, 0.727] | — | — |
| sizes only | 139 | 0.333 [0.313, 0.352] | +0.354 [+0.308, +0.399] | no |
| timing only | 30 | 0.688 [0.645, 0.727] | +0.000 [+0.000, +0.000] | yes |
| counts and direction only | 26 | 0.333 [0.313, 0.352] | +0.354 [+0.308, +0.399] | no |
| first_request_bytes only | 1 | 0.333 [0.313, 0.352] | +0.354 [+0.308, +0.399] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.38 (share of the way from chance to perfect); severity medium.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (500 groups): macro-F1 0.724 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.499, max 0.558; verdicts on permuted labels: 0 LEAK, 57 NO LEAK, 42 INCONCLUSIVE.

- **padding-not-enough-timing**: The requests are padded, yet the attribute still leaks and timing carries it: padding is not enough. Shape the response timing as well (replies at a fixed rate or in batches, delays that do not follow the work done), then re-run the audit.

- **pad-local-posts**: This view also sees requests that are not padded, such as posts to a local service (in C2, the ticket service on the building network). Pad posts to local services too, then re-run the audit; the audit of a view without them shows what they add.

## Against the baseline

Baseline: `data/results/leakcheck/c2b2_lan_padmax_v1_pair_timing/report.json`.

- no verdict changed

## Runtime

28.1 s in all (features 0.0 s, analysis 28.0 s); peak memory 192 MB in the main process, up to 269 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| analysis:task_type | 27.8 | 192 | 269 |
