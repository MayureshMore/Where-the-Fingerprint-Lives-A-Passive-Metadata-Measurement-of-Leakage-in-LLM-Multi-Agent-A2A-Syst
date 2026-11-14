# Leak check: example: c2_lan, view v2

40 traces from 40 captures in `examples/c2_lan` (0 skipped, 0 analysed as stripped copies). a2a-leakcheck 0.1.0, 2026-11-14T12:29:46-0800.

Vantage `v2`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 0 of 40 traces show no flow there; they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge |
|---|---|---|---|
| edge_cloud | 40 | 40 | 0 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **LEAK** | medium | 0.774 [0.642, 0.900] | 0.550 | 0.010 | 0.01 | sizes (alone matches all) |

## task_type

**LEAK**: CI lower bound 0.642 > chance + margin 0.550.

40 samples in 40 groups; classes fault_diagnosis 20, sensor_analysis 20.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.774 [0.642, 0.900] | — |
| sizes only | 139 | 0.799 [0.670, 0.909] | -0.026 [-0.122, +0.064] |
| timing only | 30 | 0.522 [0.365, 0.680] | +0.251 [+0.101, +0.412] |
| counts and direction only | 26 | 0.723 [0.573, 0.849] | +0.050 [-0.106, +0.222] |
| first_request_bytes only | 1 | 0.472 [0.314, 0.613] | +0.302 [+0.081, +0.505] |

Effect size 0.55 (share of the way from chance to perfect); severity medium.

Permutation test (rf-light: macro-F1 0.875 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.506, max 0.750; verdicts on permuted labels: 1 LEAK, 19 NO LEAK, 79 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

## Runtime

17.2 s in all (collection 0.0 s, extraction 1.6 s, analysis 15.6 s); peak memory 241 MB in the main process, up to 191 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.0 | 168 | — |
| extraction | 1.6 | 239 | — |
| analysis:task_type | 15.3 | 241 | 191 |
