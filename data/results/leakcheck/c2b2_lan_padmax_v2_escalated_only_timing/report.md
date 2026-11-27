# Leak check: C2B2 lan_padmax, view v2, escalated_only, timing alone

750 traces from 750 captures in `data/subsets/c2b2_lan_padmax_escalated_only` (0 skipped, 750 analysed as stripped copies). a2a-leakcheck 0.3.1, 2026-11-26T20:01:21-0800.

**Audit completed**: 1 attributes, 1 LEAK, 0 NO LEAK, 0 INCONCLUSIVE.

**Release policy**: none configured, so the run exits 0 whatever the verdicts (gate a release with --baseline, --fail-on-leak, --strict or --require).

Vantage `v2`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 0 of 750 traces show no flow there (0 expected: not escalated, per the sidecar, and this view sees only cloud agents; 0 unexpectedly empty); they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge |
|---|---|---|---|
| edge_cloud | 750 | 500 | 250 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **LEAK** | high | 0.745 [0.718, 0.774] | 0.383 | 0.010 | 0.00 | timing (alone matches all) |

## task_type

**LEAK**: CI lower bound 0.718 > chance + margin 0.383.

750 samples in 750 groups; classes fault_diagnosis 250, procedure_lookup 250, sensor_analysis 250.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.745 [0.718, 0.774] | — | — |
| sizes only | 139 | 0.167 [0.154, 0.179] | +0.578 [+0.549, +0.609] | no |
| timing only | 30 | 0.745 [0.718, 0.774] | +0.000 [+0.000, +0.000] | yes |
| counts and direction only | 26 | 0.167 [0.154, 0.179] | +0.578 [+0.549, +0.609] | no |
| first_request_bytes only | 1 | 0.167 [0.154, 0.179] | +0.578 [+0.549, +0.609] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.62 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (750 groups): macro-F1 0.777 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.329, max 0.372; verdicts on permuted labels: 0 LEAK, 85 NO LEAK, 14 INCONCLUSIVE.

- **padding-not-enough-timing**: The requests are padded, yet the attribute still leaks and timing carries it: padding is not enough. Shape the response timing as well (replies at a fixed rate or in batches, delays that do not follow the work done), then re-run the audit.

## Runtime

38.0 s in all (features 0.0 s, analysis 37.9 s); peak memory 211 MB in the main process, up to 277 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| analysis:task_type | 37.7 | 211 | 277 |
