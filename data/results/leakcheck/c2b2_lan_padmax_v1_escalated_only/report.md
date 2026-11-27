# Leak check: C2B2 lan_padmax, view v1, escalated_only

750 traces from 750 captures in `data/subsets/c2b2_lan_padmax_escalated_only` (0 skipped, 750 analysed as stripped copies). a2a-leakcheck 0.3.1, 2026-11-26T19:50:18-0800.

**Audit completed**: 1 attributes, 1 LEAK, 0 NO LEAK, 0 INCONCLUSIVE.

**Release policy**: none configured, so the run exits 0 whatever the verdicts (gate a release with --baseline, --fail-on-leak, --strict or --require).

Vantage `v1`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 0 of 750 traces show no flow there (0 expected: not escalated, per the sidecar, and this view sees only cloud agents; 0 unexpectedly empty); they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge | ticket |
|---|---|---|---|---|
| edge_cloud | 750 | 500 | 250 | 750 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **LEAK** | high | 0.780 [0.753, 0.808] | 0.383 | 0.010 | 0.00 | sizes (alone matches all) |

## task_type

**LEAK**: CI lower bound 0.753 > chance + margin 0.383.

750 samples in 750 groups; classes fault_diagnosis 250, procedure_lookup 250, sensor_analysis 250.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.780 [0.753, 0.808] | — | — |
| sizes only | 139 | 0.758 [0.728, 0.785] | +0.022 [-0.001, +0.045] | yes |
| timing only | 30 | 0.724 [0.695, 0.756] | +0.057 [+0.028, +0.084] | no |
| counts and direction only | 26 | 0.514 [0.476, 0.547] | +0.267 [+0.219, +0.307] | no |
| first_request_bytes only | 1 | 0.167 [0.154, 0.179] | +0.614 [+0.582, +0.645] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.67 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (750 groups): macro-F1 0.793 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.333, max 0.384; verdicts on permuted labels: 0 LEAK, 75 NO LEAK, 24 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

- **pad-local-posts**: This view also sees requests that are not padded, such as posts to a local service (in C2, the ticket service on the building network). Pad posts to local services too, then re-run the audit; the audit of a view without them shows what they add.

## Runtime

71.6 s in all (collection 1.3 s, extraction 23.6 s, analysis 46.6 s); peak memory 286 MB in the main process, up to 298 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 1.3 | 172 | — |
| extraction | 23.6 | 248 | — |
| analysis:task_type | 46.4 | 286 | 298 |
