# Leak check: C2B3 lan, view v1, escalated_only

750 traces from 750 captures in `data/subsets/c2b3_lan_escalated_only` (0 skipped, 750 analysed as stripped copies). a2a-leakcheck 0.3.0, 2026-11-24T17:57:36-0800.

**Audit completed**: 1 attributes, 1 LEAK, 0 NO LEAK, 0 INCONCLUSIVE.

**Release policy**: none configured, so the run exits 0 whatever the verdicts (gate a release with --baseline, --fail-on-leak, --strict or --require).

Vantage `v1`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 0 of 750 traces show no flow there; they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge | ticket |
|---|---|---|---|---|
| edge_cloud | 750 | 500 | 250 | 750 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **LEAK** | high | 0.953 [0.937, 0.968] | 0.383 | 0.010 | 0.00 | sizes (alone matches all) |

## task_type

**LEAK**: CI lower bound 0.937 > chance + margin 0.383.

750 samples in 734 groups; classes fault_diagnosis 250, procedure_lookup 250, sensor_analysis 250.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.953 [0.937, 0.968] | — | — |
| sizes only | 139 | 0.953 [0.938, 0.968] | +0.000 [-0.010, +0.011] | yes |
| timing only | 30 | 0.827 [0.799, 0.852] | +0.126 [+0.100, +0.154] | no |
| counts and direction only | 26 | 0.639 [0.608, 0.672] | +0.314 [+0.280, +0.349] | no |
| first_request_bytes only | 1 | 0.730 [0.700, 0.757] | +0.224 [+0.194, +0.256] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.93 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (734 groups): macro-F1 0.940 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.334, max 0.391; verdicts on permuted labels: 0 LEAK, 77 NO LEAK, 22 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

## Runtime

64.7 s in all (collection 0.7 s, extraction 23.1 s, analysis 40.9 s); peak memory 280 MB in the main process, up to 282 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.7 | 169 | — |
| extraction | 23.1 | 243 | — |
| analysis:task_type | 40.6 | 280 | 282 |
