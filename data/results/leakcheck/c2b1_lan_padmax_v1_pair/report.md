# Leak check: C2B1 lan_padmax, view v1, pair

250 traces from 250 captures in `data/subsets/c2b1_lan_padmax_pair` (0 skipped, 250 analysed as stripped copies). a2a-leakcheck 0.3.0, 2026-11-22T17:42:01-0800.

**Audit completed**: 1 attributes, 1 LEAK, 0 NO LEAK, 0 INCONCLUSIVE.

**Release policy**: none configured, so the run exits 0 whatever the verdicts (gate a release with --baseline, --fail-on-leak, --strict or --require).

Vantage `v1`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 0 of 250 traces show no flow there; they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge | ticket |
|---|---|---|---|---|
| edge_cloud | 250 | 250 | 0 | 250 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **LEAK** | low | 0.612 [0.550, 0.671] | 0.550 | 0.010 | 0.00 | sizes |

## task_type

**LEAK**: CI lower bound 0.550 > chance + margin 0.550.

250 samples in 250 groups; classes fault_diagnosis 125, sensor_analysis 125.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.612 [0.550, 0.671] | — | — |
| sizes only | 139 | 0.596 [0.536, 0.654] | +0.016 [-0.040, +0.066] | no |
| timing only | 30 | 0.540 [0.472, 0.603] | +0.072 [+0.007, +0.135] | no |
| counts and direction only | 26 | 0.396 [0.331, 0.455] | +0.216 [+0.141, +0.289] | no |
| first_request_bytes only | 1 | 0.333 [0.306, 0.361] | +0.279 [+0.211, +0.348] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.22 (share of the way from chance to perfect); severity low.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (250 groups): macro-F1 0.628 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.496, max 0.592; verdicts on permuted labels: 0 LEAK, 42 NO LEAK, 57 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

- **pad-local-posts**: This view also sees requests that are not padded, such as posts to a local service (in C2, the ticket service on the building network). Pad posts to local services too, then re-run the audit; the audit of a view without them shows what they add.

## Runtime

29.8 s in all (collection 0.2 s, extraction 7.6 s, analysis 22.0 s); peak memory 255 MB in the main process, up to 235 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.2 | 172 | — |
| extraction | 7.6 | 246 | — |
| analysis:task_type | 21.8 | 255 | 235 |
