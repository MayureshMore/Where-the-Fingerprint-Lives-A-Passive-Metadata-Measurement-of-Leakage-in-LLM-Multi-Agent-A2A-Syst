# Leak check: C2B1 lan_padmax, view v2, escalated_only

375 traces from 375 captures in `data/subsets/c2b1_lan_padmax_escalated_only` (0 skipped, 375 analysed as stripped copies). a2a-leakcheck 0.3.0, 2026-11-22T17:46:08-0800.

**Audit completed**: 1 attributes, 1 LEAK, 0 NO LEAK, 0 INCONCLUSIVE.

**Release policy**: none configured, so the run exits 0 whatever the verdicts (gate a release with --baseline, --fail-on-leak, --strict or --require).

Vantage `v2`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 0 of 375 traces show no flow there; they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge |
|---|---|---|---|
| edge_cloud | 375 | 250 | 125 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **LEAK** | medium | 0.726 [0.683, 0.763] | 0.383 | 0.010 | 0.00 | sizes (alone matches all) |

## task_type

**LEAK**: CI lower bound 0.683 > chance + margin 0.383.

375 samples in 373 groups; classes fault_diagnosis 125, procedure_lookup 125, sensor_analysis 125.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.726 [0.683, 0.763] | — | — |
| sizes only | 139 | 0.723 [0.679, 0.761] | +0.003 [-0.029, +0.037] | yes |
| timing only | 30 | 0.721 [0.679, 0.762] | +0.005 [-0.040, +0.050] | yes |
| counts and direction only | 26 | 0.410 [0.360, 0.457] | +0.316 [+0.259, +0.375] | no |
| first_request_bytes only | 1 | 0.167 [0.148, 0.184] | +0.559 [+0.513, +0.600] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.59 (share of the way from chance to perfect); severity medium.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (373 groups): macro-F1 0.748 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.331, max 0.408; verdicts on permuted labels: 0 LEAK, 53 NO LEAK, 46 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

## Runtime

43.6 s in all (collection 0.3 s, extraction 11.4 s, analysis 31.9 s); peak memory 259 MB in the main process, up to 252 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.3 | 171 | — |
| extraction | 11.4 | 246 | — |
| analysis:task_type | 31.7 | 259 | 252 |
