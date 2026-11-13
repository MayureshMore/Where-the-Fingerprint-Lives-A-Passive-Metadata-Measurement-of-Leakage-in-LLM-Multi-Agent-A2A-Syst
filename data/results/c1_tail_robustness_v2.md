# Paper 1: robustness to the connection closes the old recorder lost

Commit `1878eda2` (dirty: False), seed 42. New features `data/processed_c1_dataend_v2`; old (published) features `data/processed_c1_own`; captures `data/raw_c1`. Old numbers recomputed with this code (identical to the committed c1_evaluation_own and c1_revision, commit `da31192a`).

New view: every own connection ends at its last packet with TCP payload > 0, a 24-byte TLS close_notify alert not counted (features/connections.py, end_at_data); every later packet is dropped.

## TCP retransmissions in C1

398 retransmitted data segments in 275 of 600 traces (payload sizes {24: 398}); 285 on the traces' own connections (by role {'retriever': 72, 'validator': 111, 'executor': 102}); 113 before their connection's last data packet. The published extraction counts them; the cut drops every one after the last data packet.

## Which connections lose their close

Tail check (12 C1-style traces with a complete ground-truth capture): traces in which a role's connection lost packets, by topology:

| Topology | executor | retriever | validator |
|---|---|---|---|
| chain | 4 of 4 | 0 of 4 | 0 of 4 |
| mesh | 4 of 4 | 4 of 4 | 0 of 4 |
| star | 0 of 4 | 4 of 4 | 0 of 4 |

Lost data packets (payload > 0, not a close alert): 0.

C1 (600 traces, 2085 own connections): how each connection ends inside its capture. 600 of 600 traces have at least one connection with neither a FIN nor an RST.

| Topology / role | FIN | RST | neither | packets after the last data packet (median, max) | trailing close alert |
|---|---|---|---|---|---|
| chain/executor | 0 | 0 | 200 | 1, 3 | 5 of 200 |
| chain/retriever | 0 | 0 | 200 | 1, 3 | 5 of 200 |
| chain/validator | 0 | 0 | 200 | 1, 5 | 5 of 200 |
| mesh/executor | 0 | 0 | 200 | 1, 3 | 4 of 200 |
| mesh/retriever | 0 | 0 | 400 | 1, 5 | 117 of 400 |
| mesh/validator | 0 | 0 | 285 | 1, 5 | 5 of 285 |
| star/executor | 0 | 198 | 2 | 8, 8 | 199 of 200 |
| star/retriever | 0 | 0 | 200 | 1, 5 | 14 of 200 |
| star/validator | 0 | 198 | 2 | 8, 8 | 200 of 200 |

By workflow and role (FIN / RST / neither): code_review/executor 0/50/100; code_review/retriever 0/0/200; code_review/validator 0/50/109; data_analysis/executor 0/50/100; data_analysis/retriever 0/0/200; data_analysis/validator 0/50/108; research_retrieval/executor 0/49/101; research_retrieval/retriever 0/0/200; research_retrieval/validator 0/49/134; support_triage/executor 0/49/101; support_triage/retriever 0/0/200; support_triage/validator 0/49/136.

Packets the cut removes per trace: median 6, max 21.

## The cut removes the loss

Tail check, recorded vs complete capture: as recorded, 12 of 12 traces change in a trace feature and 12 in a per-connection feature; with the cut, 0 and 0 (identical).

Re-extraction of the published view vs `data/processed_c1_own`: 2400 files, max |difference| 0 (identical).

## Paper 1's numbers: published vs with the cut

macro-F1 with 95% cluster-bootstrap CIs over prompt groups; new − old paired on the same resamples (the temporal rows on the test rounds). Flag: the new point estimate is outside the old 95% CI.

| Task | Result | Published | With the cut | New − old | Flag |
|---|---|---|---|---|---|
| role | closed world GBT | 0.994 [0.990, 0.997] | 0.992 [0.987, 0.996] | -0.002 [-0.006, +0.001] (n.s.) |  |
| role | closed world RF | 0.997 [0.993, 0.999] | 0.992 [0.987, 0.996] | -0.004 [-0.008, -0.002] | **outside** |
| role | closed world k-FP | 0.991 [0.985, 0.995] | 0.988 [0.982, 0.994] | -0.002 [-0.005, +0.000] (n.s.) |  |
| role | GBT on the k-FP features (A5) | 0.988 [0.982, 0.993] | 0.988 [0.982, 0.993] | +0.000 [-0.003, +0.003] (n.s.) |  |
| role | GBT, sizes only | 0.933 [0.920, 0.945] | 0.876 [0.862, 0.891] | -0.056 [-0.069, -0.045] | **outside** |
| role | GBT, timing only | 0.981 [0.973, 0.988] | 0.986 [0.979, 0.992] | +0.006 [+0.000, +0.011] |  |
| role | GBT, counts and direction only | 0.696 [0.670, 0.723] | 0.514 [0.495, 0.533] | -0.181 [-0.204, -0.159] | **outside** |
| role | temporal holdout GBT (train rounds 1–3, test 4–5) | 0.993 [0.986, 0.998] | 0.990 [0.982, 0.996] | -0.003 [-0.011, +0.004] (n.s.) |  |
| role | GBT, cumul_bytes_q8 alone (best of the cumulative byte profile) | 0.848 [0.830, 0.866] | 0.794 [0.775, 0.813] | -0.054 [-0.073, -0.036] | **outside** |
| role | GBT, role leave-one-topology-out | 0.468 [0.437, 0.498] | 0.474 [0.445, 0.503] | +0.006 [-0.019, +0.030] (n.s.) |  |
| role | GBT, role leave-one-workflow-out | 0.992 [0.988, 0.996] | 0.990 [0.984, 0.995] | -0.002 [-0.007, +0.002] (n.s.) |  |
| workflow | closed world GBT | 0.660 [0.613, 0.703] | 0.642 [0.596, 0.685] | -0.018 [-0.044, +0.006] (n.s.) |  |
| workflow | closed world RF | 0.624 [0.572, 0.669] | 0.632 [0.582, 0.678] | +0.008 [-0.014, +0.031] (n.s.) |  |
| workflow | closed world k-FP | 0.515 [0.462, 0.563] | 0.513 [0.463, 0.560] | -0.001 [-0.022, +0.017] (n.s.) |  |
| workflow | GBT on the k-FP features (A5) | 0.511 [0.461, 0.556] | 0.532 [0.487, 0.573] | +0.021 [-0.008, +0.052] (n.s.) |  |
| workflow | GBT, sizes only | 0.664 [0.614, 0.708] | 0.637 [0.592, 0.682] | -0.027 [-0.052, +0.000] (n.s.) |  |
| workflow | GBT, timing only | 0.464 [0.415, 0.508] | 0.482 [0.435, 0.526] | +0.018 [-0.014, +0.053] (n.s.) |  |
| workflow | GBT, counts and direction only | 0.303 [0.264, 0.339] | 0.275 [0.237, 0.312] | -0.028 [-0.060, +0.004] (n.s.) |  |
| workflow | temporal holdout GBT (train rounds 1–3, test 4–5) | 0.473 [0.399, 0.553] | 0.473 [0.399, 0.559] | +0.000 [-0.038, +0.041] (n.s.) |  |
| workflow | size-matched CV GBT (no time gap) | 0.550 [0.497, 0.599] | 0.559 [0.499, 0.613] | +0.009 [-0.025, +0.040] (n.s.) |  |
| workflow | GBT, first-request size alone | 0.641 [0.589, 0.687] | 0.641 [0.589, 0.687] | +0.000 [+0.000, +0.000] (n.s.) |  |
| topology | closed world GBT | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] (n.s.) |  |
| topology | closed world RF | 1.000 [1.000, 1.000] | 0.998 [0.995, 1.000] | -0.002 [-0.005, +0.000] (n.s.) | **outside** |
| topology | closed world k-FP | 0.998 [0.995, 1.000] | 1.000 [1.000, 1.000] | +0.002 [+0.000, +0.005] (n.s.) |  |
| topology | GBT on the k-FP features (A5) | 0.998 [0.995, 1.000] | 0.998 [0.995, 1.000] | +0.000 [+0.000, +0.000] (n.s.) |  |
| topology | GBT, sizes only | 0.998 [0.994, 1.000] | 1.000 [1.000, 1.000] | +0.002 [+0.000, +0.006] (n.s.) |  |
| topology | GBT, timing only | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] (n.s.) |  |
| topology | GBT, counts and direction only | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] (n.s.) |  |
| topology | temporal holdout GBT (train rounds 1–3, test 4–5) | 0.979 [0.960, 0.996] | 0.992 [0.978, 1.000] | +0.013 [-0.008, +0.035] (n.s.) |  |
| topology | fixed rule (A6) | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] (n.s.) |  |
| role | all connections, GBT | 0.994 [0.989, 0.998] | 0.992 [0.986, 0.996] | -0.002 [-0.006, +0.001] (n.s.) |  |
| role | all connections, RF | 0.993 [0.989, 0.997] | 0.993 [0.989, 0.997] | -0.000 [-0.004, +0.003] (n.s.) |  |
| workflow | all connections, GBT | 0.626 [0.572, 0.672] | 0.606 [0.555, 0.652] | -0.020 [-0.053, +0.014] (n.s.) |  |
| workflow | all connections, RF | 0.606 [0.557, 0.650] | 0.593 [0.537, 0.642] | -0.013 [-0.046, +0.022] (n.s.) |  |
| workflow | all connections, first request only (GBT) | 0.641 [0.589, 0.687] | 0.641 [0.589, 0.687] | +0.000 [+0.000, +0.000] (n.s.) |  |
| topology | all connections, GBT | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] (n.s.) |  |
| topology | all connections, RF | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] (n.s.) |  |
| topology | all connections, first request only (GBT) | 0.308 [0.273, 0.344] | 0.308 [0.273, 0.344] | +0.000 [+0.000, +0.000] (n.s.) |  |

GBT, role leave-one-topology-out, per held-out value (published → with the cut, paired difference):

- chain: 0.907 [0.882, 0.932] → 0.607 [0.561, 0.652], -0.300 [-0.339, -0.260]
- mesh: 0.386 [0.357, 0.417] → 0.626 [0.601, 0.650], +0.241 [+0.200, +0.276]
- star: 0.033 [0.022, 0.045] → 0.097 [0.083, 0.113], +0.064 [+0.052, +0.077]

GBT, role leave-one-workflow-out, per held-out value (published → with the cut, paired difference):

- code_review: 1.000 [1.000, 1.000] → 1.000 [1.000, 1.000], +0.000 [+0.000, +0.000] (n.s.)
- data_analysis: 0.984 [0.971, 0.995] → 0.993 [0.982, 1.000], +0.009 [-0.002, +0.022] (n.s.)
- research_retrieval: 0.996 [0.988, 1.000] → 0.993 [0.980, 1.000], -0.002 [-0.008, +0.000] (n.s.)
- support_triage: 0.989 [0.979, 0.998] → 0.973 [0.955, 0.988], -0.016 [-0.029, -0.004]

First-request size identical in both views in every trace: True.

role, all connections, GBT: own − all connections, published +0.000 [-0.003, +0.003] (n.s.); with the cut -0.000 [-0.005, +0.004] (n.s.).

role, all connections, RF: own − all connections, published +0.003 [+0.001, +0.006]; with the cut -0.001 [-0.004, +0.001] (n.s.).

workflow, all connections, GBT: own − all connections, published +0.034 [-0.000, +0.066] (n.s.); with the cut +0.037 [+0.006, +0.066].

workflow, all connections, RF: own − all connections, published +0.018 [-0.015, +0.051] (n.s.); with the cut +0.039 [+0.012, +0.064].

workflow, all connections, first request only (GBT): own − all connections, published +0.000 [+0.000, +0.000] (n.s.); with the cut +0.000 [+0.000, +0.000] (n.s.).

topology, all connections, GBT: own − all connections, published +0.000 [+0.000, +0.000] (n.s.); with the cut +0.000 [+0.000, +0.000] (n.s.).

topology, all connections, RF: own − all connections, published +0.000 [+0.000, +0.000] (n.s.); with the cut -0.002 [-0.005, +0.000] (n.s.).

topology, all connections, first request only (GBT): own − all connections, published +0.000 [+0.000, +0.000] (n.s.); with the cut +0.000 [+0.000, +0.000] (n.s.).

## Leave one topology out: the star traces (GBT trained on chain and mesh)

Star executors and retrievers labeled validator: published 399 of 400; with the cut 399 of 400.

| True / predicted | executor | retriever | validator |
|---|---|---|---|
| executor (published) | 0 | 0 | 200 |
| retriever (published) | 0 | 1 | 199 |
| validator (published) | 76 | 95 | 29 |
| executor (with the cut) | 0 | 0 | 200 |
| retriever (with the cut) | 0 | 1 | 199 |
| validator (with the cut) | 64 | 37 | 99 |

Role from one cumulative-byte feature alone (GBT macro-F1, published → with the cut): cumul_bytes_q0 0.167 → 0.167, cumul_bytes_q1 0.480 → 0.430, cumul_bytes_q2 0.535 → 0.455, cumul_bytes_q3 0.552 → 0.509, cumul_bytes_q4 0.596 → 0.527, cumul_bytes_q5 0.696 → 0.582, cumul_bytes_q6 0.720 → 0.623, cumul_bytes_q7 0.828 → 0.703, cumul_bytes_q8 0.848 → 0.794, cumul_bytes_q9 0.454 → 0.474.

Flagged: role: closed world RF, role: GBT, sizes only, role: GBT, counts and direction only, role: GBT, cumul_bytes_q8 alone (best of the cumulative byte profile), topology: closed world RF.
