# Paper 1: robustness to the connection closes the old recorder lost

Commit `dce7e8d7` (dirty: False), seed 42. New features `data/processed_c1_dataend` (every connection ends at its last data packet); old features `data/processed_c1_own`; captures `data/raw_c1`. Old numbers recomputed with this code (identical to the committed c1_evaluation_own and c1_revision, commit `da31192a`).

Cut: every own connection ends at its last packet with TCP payload > 0, a 24-byte TLS close_notify alert not counted (features/connections.py, end_at_data); every later packet is dropped.

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

Packets the cut removes per trace: median 6, max 21.

## The cut removes the loss

Tail check, recorded vs complete capture: as recorded, 12 of 12 traces change in a trace feature and 12 in a per-connection feature; with the cut, 0 and 0 (identical).

Re-extraction without the cut vs `data/processed_c1_own`: 2400 files, max |difference| 0 (identical).

## Paper 1's numbers: old vs with the cut

macro-F1 with 95% cluster-bootstrap CIs over prompt groups; new − old paired on the same resamples. Flag: the new point estimate is outside the old 95% CI.

| Task | Result | Old | With the cut | New − old | Flag |
|---|---|---|---|---|---|
| role | closed world GBT | 0.994 [0.990, 0.997] | 0.992 [0.987, 0.996] | -0.002 [-0.006, +0.001] (n.s.) |  |
| role | closed world RF | 0.997 [0.993, 0.999] | 0.992 [0.987, 0.996] | -0.004 [-0.008, -0.002] | **outside** |
| role | closed world k-FP | 0.991 [0.985, 0.995] | 0.988 [0.982, 0.994] | -0.002 [-0.005, +0.000] (n.s.) |  |
| role | GBT, sizes only | 0.933 [0.920, 0.945] | 0.876 [0.862, 0.891] | -0.056 [-0.069, -0.045] | **outside** |
| role | GBT, timing only | 0.981 [0.973, 0.988] | 0.986 [0.979, 0.992] | +0.006 [+0.000, +0.011] |  |
| role | GBT, counts and direction only | 0.696 [0.670, 0.723] | 0.514 [0.495, 0.533] | -0.181 [-0.204, -0.159] | **outside** |
| role | GBT, role leave-one-topology-out | 0.468 [0.437, 0.498] | 0.474 [0.445, 0.503] | +0.006 [-0.019, +0.030] (n.s.) |  |
| role | GBT, role leave-one-workflow-out | 0.992 [0.988, 0.996] | 0.990 [0.984, 0.995] | -0.002 [-0.007, +0.002] (n.s.) |  |
| workflow | closed world GBT | 0.660 [0.613, 0.703] | 0.642 [0.596, 0.685] | -0.018 [-0.044, +0.006] (n.s.) |  |
| workflow | closed world RF | 0.624 [0.572, 0.669] | 0.632 [0.582, 0.678] | +0.008 [-0.014, +0.031] (n.s.) |  |
| workflow | closed world k-FP | 0.515 [0.462, 0.563] | 0.513 [0.463, 0.560] | -0.001 [-0.022, +0.017] (n.s.) |  |
| workflow | GBT, sizes only | 0.664 [0.614, 0.708] | 0.637 [0.592, 0.682] | -0.027 [-0.052, +0.000] (n.s.) |  |
| workflow | GBT, timing only | 0.464 [0.415, 0.508] | 0.482 [0.435, 0.526] | +0.018 [-0.014, +0.053] (n.s.) |  |
| workflow | GBT, counts and direction only | 0.303 [0.264, 0.339] | 0.275 [0.237, 0.312] | -0.028 [-0.060, +0.004] (n.s.) |  |
| workflow | GBT, first-request size alone | 0.641 [0.589, 0.687] | 0.641 [0.589, 0.687] | +0.000 [+0.000, +0.000] (n.s.) |  |
| topology | closed world GBT | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] (n.s.) |  |
| topology | closed world RF | 1.000 [1.000, 1.000] | 0.998 [0.995, 1.000] | -0.002 [-0.005, +0.000] (n.s.) | **outside** |
| topology | closed world k-FP | 0.998 [0.995, 1.000] | 1.000 [1.000, 1.000] | +0.002 [+0.000, +0.005] (n.s.) |  |
| topology | GBT, sizes only | 0.998 [0.994, 1.000] | 1.000 [1.000, 1.000] | +0.002 [+0.000, +0.006] (n.s.) |  |
| topology | GBT, timing only | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] (n.s.) |  |
| topology | GBT, counts and direction only | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] (n.s.) |  |
| topology | fixed rule (A6) | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] (n.s.) |  |

GBT, role leave-one-topology-out, per held-out value (old → new): chain 0.907 → 0.607, mesh 0.386 → 0.626, star 0.033 → 0.097

GBT, role leave-one-workflow-out, per held-out value (old → new): code_review 1.000 → 1.000, data_analysis 0.984 → 0.993, research_retrieval 0.996 → 0.993, support_triage 0.989 → 0.973

First-request size identical with and without the cut in every trace: True.

Flagged: role: closed world RF, role: GBT, sizes only, role: GBT, counts and direction only, topology: closed world RF.
