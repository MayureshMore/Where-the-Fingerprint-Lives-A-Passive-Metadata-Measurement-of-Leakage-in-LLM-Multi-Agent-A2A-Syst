# Leak check: TLS control, clear arm

432 traces from 432 captures in `data/raw_tlspair_clear` (0 skipped, 432 analysed as stripped copies). a2a-leakcheck 0.1.0, 2026-11-02T16:47:51-0800.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| role | **LEAK** | high | 0.991 [0.985, 0.996] | 0.383 | 0.010 | 0.00 | sizes |
| workflow | **LEAK** | medium | 0.677 [0.622, 0.721] | 0.300 | 0.010 | 0.00 | sizes (alone matches all) |
| topology | **LEAK** | high | 1.000 [1.000, 1.000] | 0.383 | 0.010 | 0.00 | timing (alone matches all) |

## role

**LEAK**: CI lower bound 0.985 > chance + margin 0.383.

1296 samples in 231 groups; classes executor 432, retriever 432, validator 432.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 35 | 0.991 [0.985, 0.996] | — |
| sizes only | 26 | 0.985 [0.977, 0.992] | +0.006 [+0.000, +0.012] |
| timing only | 5 | 0.955 [0.942, 0.968] | +0.036 [+0.024, +0.048] |
| counts and direction only | 4 | 0.559 [0.531, 0.585] | +0.432 [+0.405, +0.461] |
| bytes_in only | 1 | 0.545 [0.509, 0.577] | +0.446 [+0.412, +0.482] |

Effect size 0.99 (share of the way from chance to perfect); severity high.

Permutation test (rf-light: macro-F1 0.992 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.331, max 0.389; verdicts on permuted labels: 0 LEAK, 95 NO LEAK, 4 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

- **role-endpoints**: Each agent's traffic profile identifies its role. Put agents behind one endpoint, or pad their requests and responses to common sizes.

## workflow

**LEAK**: CI lower bound 0.622 > chance + margin 0.300.

432 samples in 231 groups; classes code_review 108, data_analysis 108, research_retrieval 108, support_triage 108.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.677 [0.622, 0.721] | — |
| sizes only | 139 | 0.647 [0.587, 0.700] | +0.029 [-0.016, +0.069] |
| timing only | 30 | 0.548 [0.494, 0.596] | +0.128 [+0.077, +0.176] |
| counts and direction only | 26 | 0.289 [0.242, 0.331] | +0.387 [+0.327, +0.453] |
| first_request_bytes only | 1 | 0.590 [0.527, 0.645] | +0.086 [+0.027, +0.146] |

Effect size 0.57 (share of the way from chance to perfect); severity medium.

Permutation test (rf-light: macro-F1 0.641 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.253, max 0.319; verdicts on permuted labels: 0 LEAK, 63 NO LEAK, 36 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

## topology

**LEAK**: CI lower bound 1.000 > chance + margin 0.383.

432 samples in 231 groups; classes chain 144, mesh 144, star 144.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 1.000 [1.000, 1.000] | — |
| sizes only | 139 | 0.998 [0.993, 1.000] | +0.002 [+0.000, +0.007] |
| timing only | 30 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] |
| counts and direction only | 26 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] |
| first_request_bytes only | 1 | 0.349 [0.304, 0.394] | +0.651 [+0.606, +0.696] |

Effect size 1.00 (share of the way from chance to perfect); severity high.

Permutation test (rf-light: macro-F1 0.998 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.335, max 0.405; verdicts on permuted labels: 0 LEAK, 53 NO LEAK, 46 INCONCLUSIVE.

- **shape-timing**: Timing carries the leak. Add jitter and reordering to delegations (defense=rate), or batch responses so their timing no longer follows the work done.

- **topology-structure**: Which agents talk to each other is visible from the connections themselves, whatever their content. Hiding topology needs a constant call pattern (every agent called in every task) or relaying all calls through one endpoint.

## Runtime

131.8 s in all (collection 0.4 s, extraction 21.0 s, analysis 109.6 s); peak memory 433 MB in the main process, up to 436 MB in each of 14 worker processes.
