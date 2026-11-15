# Leak check: data/raw_tlspair_tls

432 traces from 432 captures in `data/raw_tlspair_tls` (0 skipped, 432 analysed as stripped copies). a2a-leakcheck 0.1.0, 2026-11-14T14:13:29-0800.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | executor | orchestrator | retriever | validator |
|---|---|---|---|---|---|
| chain | 144 | 144 | 0 | 144 | 144 |
| mesh | 144 | 144 | 0 | 144 | 144 |
| star | 144 | 144 | 0 | 144 | 144 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| role | **LEAK** | high | 0.991 [0.984, 0.996] | 0.383 | 0.010 | 0.00 | timing |
| workflow | **LEAK** | medium | 0.577 [0.518, 0.627] | 0.300 | 0.010 | 0.00 | first_request_bytes alone |
| topology | **LEAK** | high | 1.000 [1.000, 1.000] | 0.383 | 0.010 | 0.00 | sizes (alone matches all) |

## role

**LEAK**: CI lower bound 0.984 > chance + margin 0.383.

1296 samples in 231 groups; classes executor 432, retriever 432, validator 432.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 35 | 0.991 [0.984, 0.996] | — |
| sizes only | 26 | 0.925 [0.910, 0.941] | +0.066 [+0.051, +0.080] |
| timing only | 5 | 0.972 [0.961, 0.982] | +0.019 [+0.010, +0.027] |
| counts and direction only | 4 | 0.688 [0.660, 0.716] | +0.302 [+0.274, +0.331] |
| bytes_in only | 1 | 0.526 [0.491, 0.559] | +0.464 [+0.431, +0.500] |

Effect size 0.99 (share of the way from chance to perfect); severity high.

Permutation test (rf-light: macro-F1 0.992 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.333, max 0.368; verdicts on permuted labels: 0 LEAK, 93 NO LEAK, 6 INCONCLUSIVE.

- **shape-timing**: Timing carries the leak. Add jitter and reordering to delegations (defense=rate), or batch responses so their timing no longer follows the work done.

- **role-endpoints**: Each agent's traffic profile identifies its role. Put agents behind one endpoint, or pad their requests and responses to common sizes.

A role verdict holds for the topologies in the captures; a role profile need not transfer to another topology.

## workflow

**LEAK**: CI lower bound 0.518 > chance + margin 0.300.

432 samples in 231 groups; classes code_review 108, data_analysis 108, research_retrieval 108, support_triage 108.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 0.577 [0.518, 0.627] | — |
| sizes only | 139 | 0.569 [0.509, 0.620] | +0.008 [-0.025, +0.045] |
| timing only | 30 | 0.459 [0.402, 0.510] | +0.118 [+0.072, +0.165] |
| counts and direction only | 26 | 0.278 [0.234, 0.319] | +0.298 [+0.237, +0.360] |
| first_request_bytes only | 1 | 0.572 [0.514, 0.628] | +0.005 [-0.051, +0.058] |

Effect size 0.44 (share of the way from chance to perfect); severity medium.

Permutation test (rf-light: macro-F1 0.636 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.245, max 0.304; verdicts on permuted labels: 0 LEAK, 70 NO LEAK, 29 INCONCLUSIVE.

- **pad-task-inputs**: One request-size feature alone matches all features: the size of the task input gives the attribute away. Pad request bodies to fixed size buckets (AgentConfig.pad_buckets; in this testbed the session collector's arm option pad=B1/B2/...), with buckets wide enough that the inputs of different classes share one. Padding task inputs may not remove the leak: other size and timing features can still carry it. Re-run the audit on the padded deployment.

## topology

**LEAK**: CI lower bound 1.000 > chance + margin 0.383.

432 samples in 231 groups; classes chain 144, mesh 144, star 144.

| Features | Dims | macro-F1 [95% CI] | All − this |
|---|---|---|---|
| all | 195 | 1.000 [1.000, 1.000] | — |
| sizes only | 139 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] |
| timing only | 30 | 0.995 [0.988, 1.000] | +0.005 [+0.000, +0.012] |
| counts and direction only | 26 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] |
| first_request_bytes only | 1 | 0.341 [0.298, 0.386] | +0.659 [+0.614, +0.702] |

Effect size 1.00 (share of the way from chance to perfect); severity high.

Permutation test (rf-light: macro-F1 0.998 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.331, max 0.393; verdicts on permuted labels: 0 LEAK, 59 NO LEAK, 40 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

- **topology-structure**: Which agents talk to each other is visible from the connections themselves, whatever their content. Hiding topology needs a constant call pattern (every agent called in every task) or relaying all calls through one endpoint.

## Runtime

135.3 s in all (collection 0.5 s, extraction 23.3 s, analysis 111.4 s); peak memory 280 MB in the main process, up to 268 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.5 | 171 | — |
| extraction | 23.3 | 252 | — |
| analysis:role | 41.6 | 271 | 211 |
| analysis:workflow | 40.5 | 278 | 268 |
| analysis:topology | 28.6 | 280 | 268 |
