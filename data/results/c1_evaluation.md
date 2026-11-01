# C1 evaluation (P1)

Collection C1: deployment A, llama3.2:3b, TLS on every agent link, one session (2026-10-31T19:28:51-0700 → 2026-10-31T22:32:05-0700), 600 traces in 5 balanced rounds, 0 failed attempts. Data `data/processed_c1`, commit `4adc0ea2` (uncommitted changes), seed 42.

Capture checks: TLS record check passed (1.0 handshakes per connection); median largest specialist reply chain 44 pkts (0% cut), mesh 78 pkts (0% cut), star 272 pkts (0% cut).

macro-F1 with 95% cluster-bootstrap CIs over prompt groups. Same 5 group folds for every row except the temporal holdout.

## Closed world, temporal holdout, k-FP

| Task | Chance | n (groups) | GBT | RF | k-FP | Temporal GBT | Temporal RF |
|---|---|---|---|---|---|---|---|
| role | 0.333 | 1800 (282) | 0.994 [0.989, 0.998] | 0.993 [0.989, 0.997] | 0.984 [0.977, 0.991] | 0.985 [0.974, 0.993] | 0.985 [0.975, 0.994] |
| workflow | 0.250 | 600 (282) | 0.626 [0.572, 0.672] | 0.606 [0.557, 0.650] | 0.516 [0.465, 0.565] | 0.441 [0.365, 0.522] | 0.463 [0.380, 0.548] |
| topology | 0.333 | 600 (282) | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 0.998 [0.995, 1.000] | 0.979 [0.959, 0.996] | 0.987 [0.971, 1.000] |

Temporal holdout: train rounds 1–3, test rounds 4–5; training traces whose prompt occurs in the test rounds are removed.

Removing those prompts shrinks training, so the size-matched CV trains each fold on random whole prompt groups up to the same number of traces, with no time gap. Temporal below size-matched = drift; equal = training size.

| Task | Train (after / before prompt removal) | Test | Temporal GBT | Size-matched CV GBT | Temporal RF | Size-matched CV RF |
|---|---|---|---|---|---|---|
| role | 507 / 1080 | 720 | 0.985 [0.974, 0.993] | 0.986 [0.979, 0.991] | 0.985 [0.975, 0.994] | 0.989 [0.983, 0.995] |
| workflow | 169 / 360 | 240 | 0.441 [0.365, 0.522] | 0.525 [0.468, 0.576] | 0.463 [0.380, 0.548] | 0.535 [0.482, 0.582] |
| topology | 169 / 360 | 240 | 0.979 [0.959, 0.996] | 0.998 [0.995, 1.000] | 0.987 [0.971, 1.000] | 0.997 [0.990, 1.000] |

## Paired differences (GBT minus …)

| Task | GBT − RF | GBT − k-FP |
|---|---|---|
| role | +0.001 [-0.002, +0.003] (n.s.) | +0.010 [+0.005, +0.015] |
| workflow | +0.020 [-0.010, +0.049] (n.s.) | +0.110 [+0.062, +0.164] |
| topology | +0.000 [+0.000, +0.000] (n.s.) | +0.002 [+0.000, +0.005] (n.s.) |

## Feature ablation (GBT, same folds)

| Task | All | sizes only | timing only | counts and direction only |
|---|---|---|---|---|
| role | 0.994 [0.989, 0.998] | 0.978 [0.971, 0.985] (26 dims) | 0.920 [0.907, 0.932] (5 dims) | 0.744 [0.723, 0.764] (4 dims) |
| workflow | 0.626 [0.572, 0.672] | 0.617 [0.570, 0.663] (139 dims) | 0.477 [0.428, 0.521] (30 dims) | 0.291 [0.253, 0.329] (26 dims) |
| topology | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] (139 dims) | 0.998 [0.995, 1.000] (30 dims) | 1.000 [1.000, 1.000] (26 dims) |

Drop from all features to one family (paired, all − family):

| Task | sizes | timing | counts_direction |
|---|---|---|---|
| role | +0.016 [+0.010, +0.022] | +0.074 [+0.062, +0.086] | +0.250 [+0.230, +0.271] |
| workflow | +0.009 [-0.016, +0.038] (n.s.) | +0.149 [+0.103, +0.197] | +0.334 [+0.281, +0.386] |
| topology | +0.000 [+0.000, +0.000] (n.s.) | +0.002 [+0.000, +0.005] (n.s.) | +0.000 [+0.000, +0.000] (n.s.) |

Per-flow vs system aggregates (GBT, same folds; trace tasks only — a role sample is one flow). Per-flow = mean, heaviest and second-heaviest flow (105 dims); system = system-wide aggregates (90 dims).

| Task | Per-flow only | System only | All − per-flow | All − system |
|---|---|---|---|---|
| workflow | 0.592 [0.539, 0.642] | 0.617 [0.559, 0.668] | +0.034 [+0.001, +0.068] | +0.009 [-0.022, +0.037] (n.s.) |
| topology | 0.990 [0.982, 0.997] | 0.998 [0.995, 1.000] | +0.010 [+0.003, +0.018] | +0.002 [+0.000, +0.005] (n.s.) |

## Learning curve (GBT, same folds, training cut to whole prompt groups)

Share of each fold's training set; each cell gives the training traces per class.

| Task | 10% | 25% | 50% | 75% | 100% |
|---|---|---|---|---|---|
| role | 0.964 [0.955, 0.973] (48/class) | 0.977 [0.969, 0.985] (120/class) | 0.989 [0.983, 0.995] (240/class) | 0.992 [0.986, 0.997] (360/class) | 0.994 [0.989, 0.998] (480/class) |
| workflow | 0.391 [0.344, 0.438] (12/class) | 0.541 [0.482, 0.592] (30/class) | 0.564 [0.514, 0.609] (60/class) | 0.605 [0.556, 0.649] (90/class) | 0.626 [0.572, 0.672] (120/class) |
| topology | 0.963 [0.944, 0.980] (16/class) | 0.992 [0.982, 0.999] (40/class) | 0.998 [0.994, 1.000] (80/class) | 0.998 [0.994, 1.000] (120/class) | 1.000 [1.000, 1.000] (160/class) |

k-FP: 138 features from packet direction and timing only (Hayes & Danezis 2016), RandomForest, 1000 trees (k-FP closed world).
