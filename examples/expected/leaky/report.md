# Leak check: example: leaky

40 traces from 40 captures in `examples/leaky` (0 skipped, 0 analysed as stripped copies). a2a-leakcheck 0.3.0, 2026-11-20T07:52:13-0800.

**Audit completed**: 3 attributes, 2 LEAK, 0 NO LEAK, 1 INCONCLUSIVE.

**Release policy**: none configured, so the run exits 0 whatever the verdicts (gate a release with --baseline, --fail-on-leak, --strict or --require).

**For review**: workflow (INCONCLUSIVE).

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | executor | orchestrator | retriever | validator |
|---|---|---|---|---|---|
| chain | 20 | 20 | 0 | 20 | 20 |
| star | 20 | 20 | 0 | 20 | 20 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| role | **LEAK** | high | 0.992 [0.975, 1.000] | 0.383 | 0.010 | 0.02 | timing |
| workflow | **INCONCLUSIVE** | none | 0.599 [0.437, 0.725] | 0.550 | 0.010 | 0.01 | — |
| topology | **LEAK** | high | 1.000 [1.000, 1.000] | 0.550 | 0.010 | 0.02 | sizes (alone matches all) |

## role

**LEAK**: CI lower bound 0.975 > chance + margin 0.383.

120 samples in 40 groups; classes executor 40, retriever 40, validator 40.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 35 | 0.992 [0.975, 1.000] | — | — |
| sizes only | 26 | 0.933 [0.892, 0.967] | +0.058 [+0.025, +0.100] | no |
| timing only | 5 | 0.950 [0.892, 0.992] | +0.042 [+0.008, +0.091] | no |
| counts and direction only | 4 | 0.616 [0.508, 0.714] | +0.376 [+0.278, +0.488] | no |
| bytes_in only | 1 | 0.505 [0.431, 0.572] | +0.487 [+0.416, +0.564] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.99 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (40 groups, 40 permuted within): macro-F1 0.983 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.328, max 0.485; verdicts on permuted labels: 2 LEAK, 37 NO LEAK, 60 INCONCLUSIVE.

- **shape-timing**: Timing carries the leak. Add jitter and reordering to delegations (defense=rate), or batch responses so their timing no longer follows the work done.

- **role-endpoints**: Each agent's traffic profile identifies its role. Put agents behind one endpoint, or pad their requests and responses to common sizes.

A role verdict holds for the topologies in the captures; a role profile need not transfer to another topology.

## workflow

**INCONCLUSIVE**: CI [0.437, 0.725] straddles chance + margin 0.550.

40 samples in 40 groups; classes code_review 20, support_triage 20.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.599 [0.437, 0.725] | — | — |
| sizes only | 139 | 0.744 [0.583, 0.874] | -0.145 [-0.259, -0.050] | yes |
| timing only | 30 | 0.675 [0.525, 0.822] | -0.076 [-0.225, +0.065] | no |
| counts and direction only | 26 | 0.437 [0.289, 0.591] | +0.162 [-0.049, +0.366] | no |
| first_request_bytes only | 1 | 0.900 [0.798, 0.975] | -0.301 [-0.446, -0.175] | yes |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.20 (share of the way from chance to perfect); severity none.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (40 groups): macro-F1 0.725 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.505, max 0.721; verdicts on permuted labels: 1 LEAK, 13 NO LEAK, 85 INCONCLUSIVE.

- **inconclusive**: The interval straddles chance + margin: more traces will narrow it. Re-run before treating this attribute as safe.

## topology

**LEAK**: CI lower bound 1.000 > chance + margin 0.550.

40 samples in 40 groups; classes chain 20, star 20.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 1.000 [1.000, 1.000] | — | — |
| sizes only | 139 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |
| timing only | 30 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |
| counts and direction only | 26 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |
| first_request_bytes only | 1 | 0.348 [0.200, 0.488] | +0.652 [+0.512, +0.800] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 1.00 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (40 groups): macro-F1 1.000 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.523, max 0.750; verdicts on permuted labels: 2 LEAK, 12 NO LEAK, 85 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

- **topology-structure**: Which agents talk to each other is visible from the connections themselves, whatever their content. Hiding topology needs a constant call pattern (every agent called in every task) or relaying all calls through one endpoint.

## Runtime

61.4 s in all (collection 0.0 s, extraction 2.9 s, analysis 58.4 s); peak memory 247 MB in the main process, up to 199 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.0 | 170 | — |
| extraction | 2.9 | 245 | — |
| analysis:role | 20.1 | 247 | 180 |
| analysis:workflow | 20.0 | 247 | 196 |
| analysis:topology | 17.4 | 247 | 199 |
