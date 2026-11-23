# Leak check: C2B1 lan_padmax, view v2, pair

250 traces from 250 captures in `data/subsets/c2b1_lan_padmax_pair` (0 skipped, 250 analysed as stripped copies). a2a-leakcheck 0.3.0, 2026-11-22T17:45:23-0800.

**Audit completed**: 1 attributes, 1 LEAK, 0 NO LEAK, 0 INCONCLUSIVE.

**Release policy**: none configured, so the run exits 0 whatever the verdicts (gate a release with --baseline, --fail-on-leak, --strict or --require).

Vantage `v2`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 0 of 250 traces show no flow there; they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge |
|---|---|---|---|
| edge_cloud | 250 | 250 | 0 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **LEAK** | low | 0.628 [0.570, 0.685] | 0.550 | 0.010 | 0.00 | sizes |

## task_type

**LEAK**: CI lower bound 0.570 > chance + margin 0.550.

250 samples in 250 groups; classes fault_diagnosis 125, sensor_analysis 125.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.628 [0.570, 0.685] | — | — |
| sizes only | 139 | 0.608 [0.544, 0.664] | +0.020 [-0.033, +0.073] | no |
| timing only | 30 | 0.588 [0.530, 0.644] | +0.040 [-0.025, +0.103] | no |
| counts and direction only | 26 | 0.456 [0.394, 0.512] | +0.172 [+0.097, +0.252] | no |
| first_request_bytes only | 1 | 0.333 [0.306, 0.361] | +0.294 [+0.230, +0.355] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.26 (share of the way from chance to perfect); severity low.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (250 groups): macro-F1 0.636 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.496, max 0.603; verdicts on permuted labels: 0 LEAK, 49 NO LEAK, 50 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

## Runtime

31.8 s in all (collection 0.2 s, extraction 7.6 s, analysis 24.0 s); peak memory 253 MB in the main process, up to 233 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.2 | 172 | — |
| extraction | 7.6 | 243 | — |
| analysis:task_type | 23.7 | 253 | 233 |
