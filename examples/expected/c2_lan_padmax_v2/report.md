# Leak check: example: c2_lan_padmax, view v2

40 traces from 40 captures in `examples/c2_lan_padmax` (0 skipped, 0 analysed as stripped copies). a2a-leakcheck 0.3.0, 2026-11-20T07:53:57-0800.

**Audit completed**: 1 attributes, 1 LEAK, 0 NO LEAK, 0 INCONCLUSIVE.

**Release policy**: none configured, so the run exits 0 whatever the verdicts (gate a release with --baseline, --fail-on-leak, --strict or --require).

Vantage `v2`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 0 of 40 traces show no flow there; they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge |
|---|---|---|---|
| edge_cloud | 40 | 40 | 0 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **LEAK** | medium | 0.749 [0.599, 0.874] | 0.550 | 0.020 | 0.03 | counts and direction |

## task_type

**LEAK**: CI lower bound 0.599 > chance + margin 0.550.

40 samples in 40 groups; classes fault_diagnosis 20, sensor_analysis 20.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.749 [0.599, 0.874] | — | — |
| sizes only | 139 | 0.670 [0.505, 0.804] | +0.080 [-0.051, +0.207] | no |
| timing only | 30 | 0.670 [0.500, 0.800] | +0.080 [-0.092, +0.245] | no |
| counts and direction only | 26 | 0.697 [0.545, 0.825] | +0.052 [-0.102, +0.207] | no |
| first_request_bytes only | 1 | 0.333 [0.245, 0.394] | +0.416 [+0.252, +0.550] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.50 (share of the way from chance to perfect); severity medium.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (40 groups): macro-F1 0.774 on the real labels): p = 0.020; permuted-label macro-F1 mean 0.493, max 0.825; verdicts on permuted labels: 3 LEAK, 20 NO LEAK, 76 INCONCLUSIVE.

- **fix-message-counts**: Message counts and direction carry the leak. Keep the number of calls per agent constant and add dummy calls (defense=rate).

## Runtime

18.5 s in all (collection 0.0 s, extraction 1.5 s, analysis 16.9 s); peak memory 243 MB in the main process, up to 197 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.0 | 170 | — |
| extraction | 1.5 | 241 | — |
| analysis:task_type | 16.6 | 243 | 197 |
