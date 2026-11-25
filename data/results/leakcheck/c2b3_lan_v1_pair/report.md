# Leak check: C2B3 lan, view v1, pair

500 traces from 500 captures in `data/subsets/c2b3_lan_pair` (0 skipped, 500 analysed as stripped copies). a2a-leakcheck 0.3.0, 2026-11-24T17:56:29-0800.

**Audit completed**: 1 attributes, 1 LEAK, 0 NO LEAK, 0 INCONCLUSIVE.

**Release policy**: none configured, so the run exits 0 whatever the verdicts (gate a release with --baseline, --fail-on-leak, --strict or --require).

Vantage `v1`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 0 of 500 traces show no flow there; they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge | ticket |
|---|---|---|---|---|
| edge_cloud | 500 | 500 | 0 | 500 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **LEAK** | high | 0.916 [0.890, 0.938] | 0.550 | 0.010 | 0.00 | sizes (alone matches all) |

## task_type

**LEAK**: CI lower bound 0.890 > chance + margin 0.550.

500 samples in 500 groups; classes fault_diagnosis 250, sensor_analysis 250.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.916 [0.890, 0.938] | — | — |
| sizes only | 139 | 0.914 [0.890, 0.938] | +0.002 [-0.016, +0.020] | yes |
| timing only | 30 | 0.727 [0.687, 0.765] | +0.189 [+0.147, +0.233] | no |
| counts and direction only | 26 | 0.558 [0.514, 0.604] | +0.358 [+0.309, +0.405] | no |
| first_request_bytes only | 1 | 0.602 [0.557, 0.646] | +0.314 [+0.266, +0.361] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.83 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (500 groups): macro-F1 0.916 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.499, max 0.581; verdicts on permuted labels: 0 LEAK, 64 NO LEAK, 35 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

## Runtime

47.2 s in all (collection 0.4 s, extraction 15.9 s, analysis 30.8 s); peak memory 262 MB in the main process, up to 265 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.4 | 168 | — |
| extraction | 15.9 | 240 | — |
| analysis:task_type | 30.6 | 262 | 265 |
