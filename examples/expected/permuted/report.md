# Leak check: example: permuted

40 traces from 40 captures in `examples/permuted` (0 skipped, 0 analysed as stripped copies). a2a-leakcheck 0.1.0, 2026-11-14T14:17:34-0800.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | executor | orchestrator | retriever | validator |
|---|---|---|---|---|---|
| chain | 20 | 16 | 14 | 16 | 14 |
| star | 20 | 12 | 14 | 17 | 17 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| role | **NO LEAK** | none | 0.180 [0.107, 0.253] | 0.300 | 0.930 | 0.00 | — |
| workflow | **NO LEAK** | none | 0.355 [0.213, 0.489] | 0.550 | 0.680 | 0.01 | — |
| topology | **INCONCLUSIVE** | none | 0.437 [0.289, 0.594] | 0.550 | 0.880 | 0.01 | — |

## role

**NO LEAK**: CI upper bound 0.253 <= chance + margin 0.300.

120 samples in 40 groups; classes executor 28, orchestrator 28, retriever 33, validator 31.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 35 | 0.180 [0.107, 0.253] | — |
| sizes only | 26 | 0.104 [0.049, 0.166] | +0.076 [+0.004, +0.151] |
| timing only | 5 | 0.218 [0.152, 0.289] | -0.039 [-0.142, +0.068] |
| counts and direction only | 4 | 0.173 [0.115, 0.229] | +0.006 [-0.069, +0.093] |
| bytes_in only | 1 | 0.216 [0.154, 0.268] | -0.036 [-0.122, +0.053] |

Effect size -0.09 (share of the way from chance to perfect); severity none.

Permutation test (rf-light: macro-F1 0.172 on the real labels): p = 0.930; permuted-label macro-F1 mean 0.248, max 0.374; verdicts on permuted labels: 0 LEAK, 37 NO LEAK, 62 INCONCLUSIVE.

A role verdict holds for the topologies in the captures; a role profile need not transfer to another topology.

## workflow

**NO LEAK**: CI upper bound 0.489 <= chance + margin 0.550.

40 samples in 40 groups; classes code_review 20, support_triage 20.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.355 [0.213, 0.489] | — |
| sizes only | 139 | 0.416 [0.263, 0.573] | -0.061 [-0.218, +0.085] |
| timing only | 30 | 0.499 [0.325, 0.636] | -0.143 [-0.330, +0.044] |
| counts and direction only | 26 | 0.625 [0.472, 0.768] | -0.270 [-0.450, -0.101] |
| first_request_bytes only | 1 | 0.348 [0.213, 0.495] | +0.007 [-0.181, +0.197] |

Effect size -0.29 (share of the way from chance to perfect); severity none.

Permutation test (rf-light: macro-F1 0.472 on the real labels): p = 0.680; permuted-label macro-F1 mean 0.507, max 0.700; verdicts on permuted labels: 1 LEAK, 16 NO LEAK, 82 INCONCLUSIVE.

## topology

**INCONCLUSIVE**: CI [0.289, 0.594] straddles chance + margin 0.550.

40 samples in 40 groups; classes chain 20, star 20.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.437 [0.289, 0.594] | — |
| sizes only | 139 | 0.522 [0.365, 0.670] | -0.085 [-0.213, +0.034] |
| timing only | 30 | 0.323 [0.200, 0.467] | +0.114 [-0.066, +0.292] |
| counts and direction only | 26 | 0.323 [0.192, 0.459] | +0.114 [-0.072, +0.298] |
| first_request_bytes only | 1 | 0.394 [0.236, 0.545] | +0.043 [-0.172, +0.254] |

Effect size -0.13 (share of the way from chance to perfect); severity none.

Permutation test (rf-light: macro-F1 0.355 on the real labels): p = 0.880; permuted-label macro-F1 mean 0.481, max 0.749; verdicts on permuted labels: 1 LEAK, 22 NO LEAK, 76 INCONCLUSIVE.

- **inconclusive**: The interval straddles chance + margin: more traces will narrow it. Re-run before treating this attribute as safe.

## Runtime

53.7 s in all (collection 0.0 s, extraction 2.7 s, analysis 50.9 s); peak memory 247 MB in the main process, up to 199 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.0 | 170 | — |
| extraction | 2.7 | 244 | — |
| analysis:role | 18.0 | 246 | 186 |
| analysis:workflow | 16.2 | 246 | 198 |
| analysis:topology | 15.9 | 247 | 199 |
