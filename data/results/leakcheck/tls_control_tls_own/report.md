# Leak check: data/raw_tlspair_tls

432 traces from 432 captures in `data/raw_tlspair_tls` (0 skipped, 432 analysed as stripped copies). a2a-leakcheck 0.1.0, 2026-11-02T21:06:05-0800.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| role | **LEAK** | high | 0.991 [0.984, 0.997] | 0.383 | 0.010 | 0.00 | timing |
| workflow | **LEAK** | medium | 0.613 [0.558, 0.660] | 0.300 | 0.010 | 0.00 | first_request_bytes alone |
| topology | **LEAK** | high | 1.000 [1.000, 1.000] | 0.383 | 0.010 | 0.00 | sizes (alone matches all) |

## role

**LEAK**: CI lower bound 0.984 > chance + margin 0.383.

1296 samples in 231 groups; classes executor 432, retriever 432, validator 432.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 35 | 0.991 [0.984, 0.997] | — |
| sizes only | 26 | 0.926 [0.912, 0.942] | +0.065 [+0.051, +0.078] |
| timing only | 5 | 0.974 [0.963, 0.983] | +0.017 [+0.009, +0.027] |
| counts and direction only | 4 | 0.693 [0.662, 0.721] | +0.298 [+0.269, +0.328] |
| bytes_in only | 1 | 0.526 [0.491, 0.559] | +0.464 [+0.431, +0.501] |

Effect size 0.99 (share of the way from chance to perfect); severity high.

Permutation test (rf-light: macro-F1 0.992 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.333, max 0.369; verdicts on permuted labels: 0 LEAK, 95 NO LEAK, 4 INCONCLUSIVE.

- **shape-timing**: Timing carries the leak. Add jitter and reordering to delegations (defense=rate), or batch responses so their timing no longer follows the work done.

- **role-endpoints**: Each agent's traffic profile identifies its role. Put agents behind one endpoint, or pad their requests and responses to common sizes.

## workflow

**LEAK**: CI lower bound 0.558 > chance + margin 0.300.

432 samples in 231 groups; classes code_review 108, data_analysis 108, research_retrieval 108, support_triage 108.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.613 [0.558, 0.660] | — |
| sizes only | 139 | 0.580 [0.525, 0.636] | +0.033 [-0.006, +0.071] |
| timing only | 30 | 0.466 [0.413, 0.515] | +0.147 [+0.094, +0.200] |
| counts and direction only | 26 | 0.265 [0.222, 0.306] | +0.348 [+0.285, +0.405] |
| first_request_bytes only | 1 | 0.582 [0.515, 0.642] | +0.030 [-0.032, +0.088] |

Effect size 0.48 (share of the way from chance to perfect); severity medium.

Permutation test (rf-light: macro-F1 0.622 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.246, max 0.317; verdicts on permuted labels: 0 LEAK, 71 NO LEAK, 28 INCONCLUSIVE.

- **pad-task-inputs**: One request-size feature alone matches all features: the size of the task input gives the attribute away. Pad request bodies to fixed size buckets (AgentConfig.pad_buckets; in this testbed the session collector's arm option pad=B1/B2/...), with buckets wide enough that the inputs of different classes share one.

## topology

**LEAK**: CI lower bound 1.000 > chance + margin 0.383.

432 samples in 231 groups; classes chain 144, mesh 144, star 144.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 1.000 [1.000, 1.000] | — |
| sizes only | 139 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] |
| timing only | 30 | 0.995 [0.988, 1.000] | +0.005 [+0.000, +0.012] |
| counts and direction only | 26 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] |
| first_request_bytes only | 1 | 0.356 [0.313, 0.398] | +0.644 [+0.602, +0.687] |

Effect size 1.00 (share of the way from chance to perfect); severity high.

Permutation test (rf-light: macro-F1 0.998 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.331, max 0.391; verdicts on permuted labels: 0 LEAK, 61 NO LEAK, 38 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

- **topology-structure**: Which agents talk to each other is visible from the connections themselves, whatever their content. Hiding topology needs a constant call pattern (every agent called in every task) or relaying all calls through one endpoint.

## Against the baseline

Baseline: `data/results/leakcheck/tls_control_tls/report.json`.

- no verdict changed

## Runtime

123.5 s in all (collection 0.5 s, extraction 21.6 s, analysis 100.8 s); peak memory 425 MB in the main process, up to 432 MB in each of 14 worker processes.
