# Leak check: example: permuted

40 traces from 40 captures in `examples/permuted` (0 skipped, 0 analysed as stripped copies). a2a-leakcheck 0.1.0, 2026-11-05T07:36:45-0800.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | executor | orchestrator | retriever | validator |
|---|---|---|---|---|---|
| chain | 20 | 16 | 14 | 16 | 14 |
| star | 20 | 12 | 14 | 17 | 17 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| role | **NO LEAK** | none | 0.165 [0.094, 0.241] | 0.300 | 0.990 | 0.00 | — |
| workflow | **NO LEAK** | none | 0.386 [0.231, 0.540] | 0.550 | 0.820 | 0.00 | — |
| topology | **INCONCLUSIVE** | none | 0.479 [0.314, 0.623] | 0.550 | 0.580 | 0.01 | — |

## role

**NO LEAK**: CI upper bound 0.241 <= chance + margin 0.300.

120 samples in 40 groups; classes executor 28, orchestrator 28, retriever 33, validator 31.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 35 | 0.165 [0.094, 0.241] | — |
| sizes only | 26 | 0.140 [0.080, 0.202] | +0.025 [-0.048, +0.102] |
| timing only | 5 | 0.203 [0.135, 0.272] | -0.038 [-0.114, +0.040] |
| counts and direction only | 4 | 0.166 [0.110, 0.216] | -0.001 [-0.073, +0.080] |
| bytes_in only | 1 | 0.216 [0.154, 0.268] | -0.051 [-0.133, +0.037] |

Effect size -0.11 (share of the way from chance to perfect); severity none.

Permutation test (rf-light: macro-F1 0.143 on the real labels): p = 0.990; permuted-label macro-F1 mean 0.249, max 0.374; verdicts on permuted labels: 0 LEAK, 32 NO LEAK, 67 INCONCLUSIVE.

A role verdict holds for the topologies in the captures; a role profile need not transfer to another topology.

## workflow

**NO LEAK**: CI upper bound 0.540 <= chance + margin 0.550.

40 samples in 40 groups; classes code_review 20, support_triage 20.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.386 [0.231, 0.540] | — |
| sizes only | 139 | 0.437 [0.284, 0.584] | -0.051 [-0.204, +0.102] |
| timing only | 30 | 0.416 [0.270, 0.562] | -0.030 [-0.203, +0.139] |
| counts and direction only | 26 | 0.650 [0.488, 0.795] | -0.264 [-0.460, -0.054] |
| first_request_bytes only | 1 | 0.263 [0.141, 0.398] | +0.123 [-0.068, +0.309] |

Effect size -0.23 (share of the way from chance to perfect); severity none.

Permutation test (rf-light: macro-F1 0.422 on the real labels): p = 0.820; permuted-label macro-F1 mean 0.503, max 0.699; verdicts on permuted labels: 0 LEAK, 18 NO LEAK, 81 INCONCLUSIVE.

## topology

**INCONCLUSIVE**: CI [0.314, 0.623] straddles chance + margin 0.550.

40 samples in 40 groups; classes chain 20, star 20.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.479 [0.314, 0.623] | — |
| sizes only | 139 | 0.499 [0.343, 0.648] | -0.020 [-0.168, +0.125] |
| timing only | 30 | 0.407 [0.263, 0.552] | +0.072 [-0.111, +0.226] |
| counts and direction only | 26 | 0.323 [0.192, 0.459] | +0.156 [+0.006, +0.308] |
| first_request_bytes only | 1 | 0.449 [0.293, 0.596] | +0.031 [-0.169, +0.236] |

Effect size -0.04 (share of the way from chance to perfect); severity none.

Permutation test (rf-light: macro-F1 0.458 on the real labels): p = 0.580; permuted-label macro-F1 mean 0.478, max 0.725; verdicts on permuted labels: 1 LEAK, 28 NO LEAK, 70 INCONCLUSIVE.

- **inconclusive**: The interval straddles chance + margin: more traces will narrow it. Re-run before treating this attribute as safe.

## Runtime

51.3 s in all (collection 0.0 s, extraction 2.6 s, analysis 48.7 s); peak memory 246 MB in the main process, up to 197 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.0 | 169 | — |
| extraction | 2.6 | 246 | — |
| analysis:role | 17.2 | 246 | 187 |
| analysis:workflow | 15.4 | 246 | 196 |
| analysis:topology | 15.3 | 246 | 197 |
