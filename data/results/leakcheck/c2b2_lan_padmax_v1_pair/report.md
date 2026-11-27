# Leak check: C2B2 lan_padmax, view v1, pair

500 traces from 500 captures in `data/subsets/c2b2_lan_padmax_pair` (0 skipped, 500 analysed as stripped copies). a2a-leakcheck 0.3.1, 2026-11-26T19:48:15-0800.

**Audit completed**: 1 attributes, 1 LEAK, 0 NO LEAK, 0 INCONCLUSIVE.

**Release policy**: none configured, so the run exits 0 whatever the verdicts (gate a release with --baseline, --fail-on-leak, --strict or --require).

Vantage `v1`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 0 of 500 traces show no flow there (0 expected: not escalated, per the sidecar, and this view sees only cloud agents; 0 unexpectedly empty); they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge | ticket |
|---|---|---|---|---|
| edge_cloud | 500 | 500 | 0 | 500 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **LEAK** | medium | 0.678 [0.637, 0.720] | 0.550 | 0.010 | 0.00 | sizes (alone matches all) |

## task_type

**LEAK**: CI lower bound 0.637 > chance + margin 0.550.

500 samples in 500 groups; classes fault_diagnosis 250, sensor_analysis 250.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.678 [0.637, 0.720] | — | — |
| sizes only | 139 | 0.664 [0.622, 0.704] | +0.014 [-0.016, +0.047] | yes |
| timing only | 30 | 0.632 [0.588, 0.672] | +0.046 [+0.002, +0.094] | no |
| counts and direction only | 26 | 0.510 [0.466, 0.550] | +0.168 [+0.118, +0.218] | no |
| first_request_bytes only | 1 | 0.333 [0.313, 0.352] | +0.345 [+0.299, +0.388] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.36 (share of the way from chance to perfect); severity medium.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (500 groups): macro-F1 0.708 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.497, max 0.550; verdicts on permuted labels: 0 LEAK, 58 NO LEAK, 41 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

- **pad-local-posts**: This view also sees requests that are not padded, such as posts to a local service (in C2, the ticket service on the building network). Pad posts to local services too, then re-run the audit; the audit of a view without them shows what they add.

## Runtime

50.8 s in all (collection 0.8 s, extraction 15.8 s, analysis 34.0 s); peak memory 267 MB in the main process, up to 264 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.8 | 171 | — |
| extraction | 15.8 | 245 | — |
| analysis:task_type | 33.8 | 267 | 264 |
