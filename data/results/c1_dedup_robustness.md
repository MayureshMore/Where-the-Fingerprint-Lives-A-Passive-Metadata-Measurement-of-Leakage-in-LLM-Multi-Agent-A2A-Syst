# Paper 1: robustness to TCP retransmissions

Commit `1878eda2` (dirty: False), seed 42. New features `data/processed_c1_dedup`; old (published) features `data/processed_c1_own`; captures `data/raw_c1`. Old numbers recomputed with this code (identical to the committed c1_evaluation_own and c1_revision, commit `da31192a`).

New view: every payload byte counted once: a TCP retransmission is dropped (features/kfp.py, dedup); nothing else changes.

## TCP retransmissions in C1

398 retransmitted data segments in 275 of 600 traces (payload sizes {24: 398}); 285 on the traces' own connections (by role {'retriever': 72, 'validator': 111, 'executor': 102}); 113 before their connection's last data packet. The published extraction counts them; the cut drops every one after the last data packet.

Re-extraction of the published view vs `data/processed_c1_own`: 2400 files, max |difference| 0 (identical).

## Paper 1's numbers: published vs deduplicated

macro-F1 with 95% cluster-bootstrap CIs over prompt groups; new − old paired on the same resamples (the temporal rows on the test rounds). Flag: the new point estimate is outside the old 95% CI.

| Task | Result | Published | Deduplicated | New − old | Flag |
|---|---|---|---|---|---|
| role | closed world GBT | 0.994 [0.990, 0.997] | 0.994 [0.990, 0.998] | +0.001 [+0.000, +0.002] (n.s.) |  |
| role | closed world RF | 0.997 [0.993, 0.999] | 0.997 [0.993, 0.999] | +0.000 [+0.000, +0.000] (n.s.) |  |
| role | closed world k-FP | 0.991 [0.985, 0.995] | 0.991 [0.985, 0.995] | +0.000 [+0.000, +0.000] (n.s.) |  |
| role | GBT on the k-FP features (A5) | 0.988 [0.982, 0.993] | 0.987 [0.981, 0.992] | -0.001 [-0.003, +0.001] (n.s.) |  |
| role | GBT, sizes only | 0.933 [0.920, 0.945] | 0.933 [0.920, 0.946] | -0.000 [-0.004, +0.004] (n.s.) |  |
| role | GBT, timing only | 0.981 [0.973, 0.988] | 0.981 [0.973, 0.988] | +0.001 [-0.003, +0.004] (n.s.) |  |
| role | GBT, counts and direction only | 0.696 [0.670, 0.723] | 0.698 [0.673, 0.725] | +0.003 [-0.002, +0.008] (n.s.) |  |
| role | temporal holdout GBT (train rounds 1–3, test 4–5) | 0.993 [0.986, 0.998] | 0.994 [0.988, 0.999] | +0.001 [+0.000, +0.004] (n.s.) |  |
| role | GBT, cumul_bytes_q8 alone (best of the cumulative byte profile) | 0.848 [0.830, 0.866] | 0.848 [0.829, 0.866] | -0.000 [-0.003, +0.002] (n.s.) |  |
| role | GBT, role leave-one-topology-out | 0.468 [0.437, 0.498] | 0.472 [0.442, 0.501] | +0.004 [+0.000, +0.008] |  |
| role | GBT, role leave-one-workflow-out | 0.992 [0.988, 0.996] | 0.993 [0.989, 0.996] | +0.001 [-0.001, +0.002] (n.s.) |  |
| workflow | closed world GBT | 0.660 [0.613, 0.703] | 0.659 [0.609, 0.707] | -0.001 [-0.020, +0.019] (n.s.) |  |
| workflow | closed world RF | 0.624 [0.572, 0.669] | 0.632 [0.582, 0.677] | +0.009 [-0.007, +0.025] (n.s.) |  |
| workflow | closed world k-FP | 0.515 [0.462, 0.563] | 0.510 [0.459, 0.560] | -0.005 [-0.020, +0.010] (n.s.) |  |
| workflow | GBT on the k-FP features (A5) | 0.511 [0.461, 0.556] | 0.514 [0.464, 0.556] | +0.003 [-0.016, +0.021] (n.s.) |  |
| workflow | GBT, sizes only | 0.664 [0.614, 0.708] | 0.660 [0.608, 0.707] | -0.004 [-0.024, +0.017] (n.s.) |  |
| workflow | GBT, timing only | 0.464 [0.415, 0.508] | 0.465 [0.416, 0.508] | +0.002 [-0.027, +0.028] (n.s.) |  |
| workflow | GBT, counts and direction only | 0.303 [0.264, 0.339] | 0.285 [0.247, 0.323] | -0.019 [-0.037, +0.000] (n.s.) |  |
| workflow | temporal holdout GBT (train rounds 1–3, test 4–5) | 0.473 [0.399, 0.553] | 0.476 [0.402, 0.557] | +0.003 [-0.032, +0.039] (n.s.) |  |
| workflow | size-matched CV GBT (no time gap) | 0.550 [0.497, 0.599] | 0.545 [0.494, 0.591] | -0.004 [-0.026, +0.019] (n.s.) |  |
| workflow | GBT, first-request size alone | 0.641 [0.589, 0.687] | 0.641 [0.589, 0.687] | +0.000 [+0.000, +0.000] (n.s.) |  |
| topology | closed world GBT | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] (n.s.) |  |
| topology | closed world RF | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] (n.s.) |  |
| topology | closed world k-FP | 0.998 [0.995, 1.000] | 0.998 [0.995, 1.000] | +0.000 [+0.000, +0.000] (n.s.) |  |
| topology | GBT on the k-FP features (A5) | 0.998 [0.995, 1.000] | 0.998 [0.995, 1.000] | +0.000 [+0.000, +0.000] (n.s.) |  |
| topology | GBT, sizes only | 0.998 [0.994, 1.000] | 0.998 [0.994, 1.000] | +0.000 [+0.000, +0.000] (n.s.) |  |
| topology | GBT, timing only | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] (n.s.) |  |
| topology | GBT, counts and direction only | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] (n.s.) |  |
| topology | temporal holdout GBT (train rounds 1–3, test 4–5) | 0.979 [0.960, 0.996] | 0.979 [0.960, 0.996] | +0.000 [+0.000, +0.000] (n.s.) |  |
| topology | fixed rule (A6) | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] (n.s.) |  |
| role | all connections, GBT | 0.994 [0.989, 0.998] | 0.994 [0.990, 0.998] | +0.001 [-0.001, +0.002] (n.s.) |  |
| role | all connections, RF | 0.993 [0.989, 0.997] | 0.994 [0.990, 0.998] | +0.001 [+0.000, +0.002] (n.s.) |  |
| workflow | all connections, GBT | 0.626 [0.572, 0.672] | 0.617 [0.564, 0.664] | -0.009 [-0.031, +0.013] (n.s.) |  |
| workflow | all connections, RF | 0.606 [0.557, 0.650] | 0.610 [0.559, 0.652] | +0.004 [-0.014, +0.022] (n.s.) |  |
| workflow | all connections, first request only (GBT) | 0.641 [0.589, 0.687] | 0.641 [0.589, 0.687] | +0.000 [+0.000, +0.000] (n.s.) |  |
| topology | all connections, GBT | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] (n.s.) |  |
| topology | all connections, RF | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] (n.s.) |  |
| topology | all connections, first request only (GBT) | 0.308 [0.273, 0.344] | 0.308 [0.273, 0.344] | +0.000 [+0.000, +0.000] (n.s.) |  |

GBT, role leave-one-topology-out, per held-out value (published → deduplicated, paired difference):

- chain: 0.907 [0.882, 0.932] → 0.904 [0.879, 0.927], -0.003 [-0.009, +0.000] (n.s.)
- mesh: 0.386 [0.357, 0.417] → 0.404 [0.375, 0.433], +0.018 [+0.005, +0.031]
- star: 0.033 [0.022, 0.045] → 0.032 [0.021, 0.044], -0.001 [-0.003, +0.000] (n.s.)

GBT, role leave-one-workflow-out, per held-out value (published → deduplicated, paired difference):

- code_review: 1.000 [1.000, 1.000] → 1.000 [1.000, 1.000], +0.000 [+0.000, +0.000] (n.s.)
- data_analysis: 0.984 [0.971, 0.995] → 0.984 [0.972, 0.994], -0.000 [-0.006, +0.006] (n.s.)
- research_retrieval: 0.996 [0.988, 1.000] → 0.996 [0.988, 1.000], +0.000 [+0.000, +0.000] (n.s.)
- support_triage: 0.989 [0.979, 0.998] → 0.991 [0.982, 0.998], +0.002 [+0.000, +0.007] (n.s.)

First-request size identical in both views in every trace: True.

role, all connections, GBT: own − all connections, published +0.000 [-0.003, +0.003] (n.s.); deduplicated +0.000 [-0.003, +0.003] (n.s.).

role, all connections, RF: own − all connections, published +0.003 [+0.001, +0.006]; deduplicated +0.003 [+0.001, +0.005].

workflow, all connections, GBT: own − all connections, published +0.034 [-0.000, +0.066] (n.s.); deduplicated +0.042 [+0.010, +0.072].

workflow, all connections, RF: own − all connections, published +0.018 [-0.015, +0.051] (n.s.); deduplicated +0.023 [-0.010, +0.056] (n.s.).

workflow, all connections, first request only (GBT): own − all connections, published +0.000 [+0.000, +0.000] (n.s.); deduplicated +0.000 [+0.000, +0.000] (n.s.).

topology, all connections, GBT: own − all connections, published +0.000 [+0.000, +0.000] (n.s.); deduplicated +0.000 [+0.000, +0.000] (n.s.).

topology, all connections, RF: own − all connections, published +0.000 [+0.000, +0.000] (n.s.); deduplicated +0.000 [+0.000, +0.000] (n.s.).

topology, all connections, first request only (GBT): own − all connections, published +0.000 [+0.000, +0.000] (n.s.); deduplicated +0.000 [+0.000, +0.000] (n.s.).

## Leave one topology out: the star traces (GBT trained on chain and mesh)

Star executors and retrievers labeled validator: published 399 of 400; deduplicated 399 of 400.

| True / predicted | executor | retriever | validator |
|---|---|---|---|
| executor (published) | 0 | 0 | 200 |
| retriever (published) | 0 | 1 | 199 |
| validator (published) | 76 | 95 | 29 |
| executor (deduplicated) | 0 | 0 | 200 |
| retriever (deduplicated) | 0 | 1 | 199 |
| validator (deduplicated) | 75 | 97 | 28 |

Role from one cumulative-byte feature alone (GBT macro-F1, published → deduplicated): cumul_bytes_q0 0.167 → 0.167, cumul_bytes_q1 0.480 → 0.480, cumul_bytes_q2 0.535 → 0.535, cumul_bytes_q3 0.552 → 0.552, cumul_bytes_q4 0.596 → 0.596, cumul_bytes_q5 0.696 → 0.695, cumul_bytes_q6 0.720 → 0.722, cumul_bytes_q7 0.828 → 0.827, cumul_bytes_q8 0.848 → 0.848, cumul_bytes_q9 0.454 → 0.453.

Flagged: none.
