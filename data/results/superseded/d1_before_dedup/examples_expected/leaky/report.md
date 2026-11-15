# Leak check: example: leaky

40 traces from 40 captures in `examples/leaky` (0 skipped, 0 analysed as stripped copies). a2a-leakcheck 0.1.0, 2026-11-05T07:35:52-0800.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | executor | orchestrator | retriever | validator |
|---|---|---|---|---|---|
| chain | 20 | 20 | 0 | 20 | 20 |
| star | 20 | 20 | 0 | 20 | 20 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| role | **LEAK** | high | 0.992 [0.975, 1.000] | 0.383 | 0.010 | 0.00 | timing |
| workflow | **INCONCLUSIVE** | none | 0.623 [0.466, 0.757] | 0.550 | 0.010 | 0.00 | — |
| topology | **LEAK** | high | 1.000 [1.000, 1.000] | 0.550 | 0.010 | 0.01 | sizes (alone matches all) |

## role

**LEAK**: CI lower bound 0.975 > chance + margin 0.383.

120 samples in 40 groups; classes executor 40, retriever 40, validator 40.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 35 | 0.992 [0.975, 1.000] | — |
| sizes only | 26 | 0.933 [0.892, 0.967] | +0.058 [+0.025, +0.100] |
| timing only | 5 | 0.942 [0.899, 0.983] | +0.050 [+0.017, +0.090] |
| counts and direction only | 4 | 0.617 [0.503, 0.716] | +0.374 [+0.276, +0.492] |
| bytes_in only | 1 | 0.505 [0.431, 0.572] | +0.487 [+0.416, +0.564] |

Effect size 0.99 (share of the way from chance to perfect); severity high.

Permutation test (rf-light: macro-F1 0.983 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.329, max 0.458; verdicts on permuted labels: 0 LEAK, 34 NO LEAK, 65 INCONCLUSIVE.

- **shape-timing**: Timing carries the leak. Add jitter and reordering to delegations (defense=rate), or batch responses so their timing no longer follows the work done.

- **role-endpoints**: Each agent's traffic profile identifies its role. Put agents behind one endpoint, or pad their requests and responses to common sizes.

A role verdict holds for the topologies in the captures; a role profile need not transfer to another topology.

## workflow

**INCONCLUSIVE**: CI [0.466, 0.757] straddles chance + margin 0.550.

40 samples in 40 groups; classes code_review 20, support_triage 20.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.623 [0.466, 0.757] | — |
| sizes only | 139 | 0.747 [0.596, 0.873] | -0.125 [-0.250, +0.002] |
| timing only | 30 | 0.599 [0.444, 0.748] | +0.024 [-0.107, +0.163] |
| counts and direction only | 26 | 0.444 [0.293, 0.596] | +0.178 [-0.008, +0.371] |
| first_request_bytes only | 1 | 0.850 [0.740, 0.949] | -0.227 [-0.375, -0.092] |

Effect size 0.25 (share of the way from chance to perfect); severity none.

Permutation test (rf-light: macro-F1 0.725 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.490, max 0.650; verdicts on permuted labels: 0 LEAK, 21 NO LEAK, 78 INCONCLUSIVE.

- **inconclusive**: The interval straddles chance + margin: more traces will narrow it. Re-run before treating this attribute as safe.

## topology

**LEAK**: CI lower bound 1.000 > chance + margin 0.550.

40 samples in 40 groups; classes chain 20, star 20.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 1.000 [1.000, 1.000] | — |
| sizes only | 139 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] |
| timing only | 30 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] |
| counts and direction only | 26 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] |
| first_request_bytes only | 1 | 0.350 [0.200, 0.499] | +0.650 [+0.501, +0.800] |

Effect size 1.00 (share of the way from chance to perfect); severity high.

Permutation test (rf-light: macro-F1 1.000 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.496, max 0.700; verdicts on permuted labels: 1 LEAK, 20 NO LEAK, 78 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

- **topology-structure**: Which agents talk to each other is visible from the connections themselves, whatever their content. Hiding topology needs a constant call pattern (every agent called in every task) or relaying all calls through one endpoint.

## Runtime

51.8 s in all (collection 0.0 s, extraction 2.5 s, analysis 49.2 s); peak memory 245 MB in the main process, up to 198 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.0 | 169 | — |
| extraction | 2.5 | 244 | — |
| analysis:role | 16.8 | 245 | 182 |
| analysis:workflow | 16.0 | 245 | 197 |
| analysis:topology | 15.7 | 245 | 198 |
