# Leak check: data/raw_tlspair_clear

432 traces from 432 captures in `data/raw_tlspair_clear` (0 skipped, 432 analysed as stripped copies). a2a-leakcheck 0.1.0, 2026-11-02T21:08:09-0800.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| role | **LEAK** | high | 0.990 [0.983, 0.995] | 0.383 | 0.010 | 0.00 | timing (alone matches all) |
| workflow | **LEAK** | medium | 0.659 [0.602, 0.711] | 0.300 | 0.010 | 0.00 | sizes (alone matches all) |
| topology | **LEAK** | high | 1.000 [1.000, 1.000] | 0.383 | 0.010 | 0.00 | timing (alone matches all) |

## role

**LEAK**: CI lower bound 0.983 > chance + margin 0.383.

1296 samples in 231 groups; classes executor 432, retriever 432, validator 432.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 35 | 0.990 [0.983, 0.995] | — |
| sizes only | 26 | 0.927 [0.911, 0.941] | +0.063 [+0.049, +0.078] |
| timing only | 5 | 0.983 [0.974, 0.992] | +0.007 [-0.000, +0.014] |
| counts and direction only | 4 | 0.542 [0.512, 0.570] | +0.448 [+0.421, +0.478] |
| bytes_in only | 1 | 0.520 [0.483, 0.551] | +0.470 [+0.440, +0.505] |

Effect size 0.98 (share of the way from chance to perfect); severity high.

Permutation test (rf-light: macro-F1 0.990 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.331, max 0.371; verdicts on permuted labels: 0 LEAK, 93 NO LEAK, 6 INCONCLUSIVE.

- **shape-timing**: Timing carries the leak. Add jitter and reordering to delegations (defense=rate), or batch responses so their timing no longer follows the work done.

- **role-endpoints**: Each agent's traffic profile identifies its role. Put agents behind one endpoint, or pad their requests and responses to common sizes.

## workflow

**LEAK**: CI lower bound 0.602 > chance + margin 0.300.

432 samples in 231 groups; classes code_review 108, data_analysis 108, research_retrieval 108, support_triage 108.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.659 [0.602, 0.711] | — |
| sizes only | 139 | 0.641 [0.581, 0.695] | +0.018 [-0.015, +0.051] |
| timing only | 30 | 0.538 [0.486, 0.587] | +0.122 [+0.062, +0.183] |
| counts and direction only | 26 | 0.270 [0.225, 0.304] | +0.390 [+0.319, +0.464] |
| first_request_bytes only | 1 | 0.590 [0.527, 0.645] | +0.069 [+0.004, +0.128] |

Effect size 0.55 (share of the way from chance to perfect); severity medium.

Permutation test (rf-light: macro-F1 0.621 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.251, max 0.329; verdicts on permuted labels: 0 LEAK, 68 NO LEAK, 31 INCONCLUSIVE.

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

Permutation test (rf-light: macro-F1 0.998 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.336, max 0.429; verdicts on permuted labels: 0 LEAK, 59 NO LEAK, 40 INCONCLUSIVE.

- **shape-timing**: Timing carries the leak. Add jitter and reordering to delegations (defense=rate), or batch responses so their timing no longer follows the work done.

- **topology-structure**: Which agents talk to each other is visible from the connections themselves, whatever their content. Hiding topology needs a constant call pattern (every agent called in every task) or relaying all calls through one endpoint.

## Against the baseline

Baseline: `data/results/leakcheck/tls_control_clear/report.json`.

- no verdict changed

## Runtime

121.5 s in all (collection 0.6 s, extraction 20.3 s, analysis 100.0 s); peak memory 432 MB in the main process, up to 441 MB in each of 14 worker processes.
