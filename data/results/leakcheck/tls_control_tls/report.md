# Leak check: TLS control, tls arm

432 traces from 432 captures in `data/raw_tlspair_tls` (0 skipped, 432 analysed as stripped copies). a2a-leakcheck 0.1.0, 2026-11-01T15:41:48-0800.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 19 permutations). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| role | **LEAK** | high | 0.988 [0.980, 0.994] | 0.383 | 0.050 | 0.00 | sizes (alone matches all) |
| workflow | **LEAK** | high | 0.741 [0.689, 0.788] | 0.300 | 0.050 | 0.00 | sizes (alone matches all) |
| topology | **LEAK** | high | 1.000 [1.000, 1.000] | 0.383 | 0.050 | 0.00 | sizes (alone matches all) |

## role

**LEAK**: CI lower bound 0.980 > chance + margin 0.383.

1296 samples in 231 groups; classes executor 432, retriever 432, validator 432.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 35 | 0.988 [0.980, 0.994] | — |
| sizes only | 26 | 0.985 [0.977, 0.992] | +0.002 [-0.002, +0.006] |
| timing only | 5 | 0.941 [0.927, 0.956] | +0.046 [+0.033, +0.060] |
| counts and direction only | 4 | 0.808 [0.788, 0.828] | +0.179 [+0.160, +0.200] |
| bytes_in only | 1 | 0.524 [0.488, 0.553] | +0.464 [+0.433, +0.499] |

Effect size 0.98 (share of the way from chance to perfect); severity high.

Permutation test: p = 0.050; permuted-label macro-F1 mean 0.339, max 0.362; verdicts on permuted labels: 0 LEAK, 18 NO LEAK, 1 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

- **role-endpoints**: Each agent's traffic profile identifies its role. Put agents behind one endpoint, or pad their requests and responses to common sizes.

## workflow

**LEAK**: CI lower bound 0.689 > chance + margin 0.300.

432 samples in 231 groups; classes code_review 108, data_analysis 108, research_retrieval 108, support_triage 108.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.741 [0.689, 0.788] | — |
| sizes only | 139 | 0.715 [0.666, 0.758] | +0.026 [-0.012, +0.063] |
| timing only | 30 | 0.551 [0.495, 0.604] | +0.190 [+0.134, +0.244] |
| counts and direction only | 26 | 0.334 [0.290, 0.376] | +0.407 [+0.348, +0.466] |
| first_request_bytes only | 1 | 0.582 [0.515, 0.642] | +0.158 [+0.093, +0.223] |

Effect size 0.65 (share of the way from chance to perfect); severity high.

Permutation test: p = 0.050; permuted-label macro-F1 mean 0.247, max 0.298; verdicts on permuted labels: 0 LEAK, 14 NO LEAK, 5 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

## topology

**LEAK**: CI lower bound 1.000 > chance + margin 0.383.

432 samples in 231 groups; classes chain 144, mesh 144, star 144.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 1.000 [1.000, 1.000] | — |
| sizes only | 139 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] |
| timing only | 30 | 0.998 [0.992, 1.000] | +0.002 [+0.000, +0.008] |
| counts and direction only | 26 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] |
| first_request_bytes only | 1 | 0.356 [0.313, 0.398] | +0.644 [+0.602, +0.687] |

Effect size 1.00 (share of the way from chance to perfect); severity high.

Permutation test: p = 0.050; permuted-label macro-F1 mean 0.333, max 0.404; verdicts on permuted labels: 0 LEAK, 11 NO LEAK, 8 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

- **topology-structure**: Which agents talk to each other is visible from the connections themselves, whatever their content. Hiding topology needs a constant call pattern (every agent called in every task) or relaying all calls through one endpoint.

## Runtime

2975.1 s in all (collection 0.6 s, extraction 21.6 s, analysis 2952.8 s); peak memory 521 MB (worker processes 6 MB).
