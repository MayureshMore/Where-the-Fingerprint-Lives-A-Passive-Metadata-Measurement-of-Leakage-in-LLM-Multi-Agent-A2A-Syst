# First-request size vs all features for workflow: C1 and the TLS control

GBT, 5-fold StratifiedGroupKFold by prompt group (shuffle, seed 42), the same folds for every model of a set; macro-F1 and per-class F1 with 95% cluster-bootstrap CIs over prompt groups; paired differences on the same group resamples. Commit `757cf6db`.

## Overall

| Set | n (groups) | All features | First request only | All − first |
|---|---|---|---|---|
| C1 | 600 (282) | 0.626 [0.572, 0.672] | 0.641 [0.589, 0.687] | -0.016 [-0.067, +0.040] (n.s.) |
| TLS control, TLS arm | 432 (231) | 0.741 [0.689, 0.786] | 0.582 [0.516, 0.643] | +0.158 [+0.088, +0.223] |
| TLS control, cleartext arm | 432 (231) | 0.677 [0.625, 0.720] | 0.590 [0.529, 0.644] | +0.086 [+0.025, +0.146] |

## First-request size per workflow (bytes; prompt in characters)

| Workflow | C1: median [Q1, Q3] | TLS control, TLS arm: median [Q1, Q3] | TLS control, cleartext arm: median [Q1, Q3] | C1: overhead | TLS control, TLS arm: overhead | TLS control, cleartext arm: overhead |
|---|---|---|---|---|---|---|
| code_review | 6175.5 [2355.5, 6721.5] | 6093.5 [2256.5, 6773.25] | 5829 [1981, 6491.25] | 1178 | 1210 | 874 |
| data_analysis | 4976 [1705.5, 5479.75] | 5143.5 [1835.75, 5628.25] | 4911 [1617.75, 5335.5] | 1012 | 1007 | 714 |
| research_retrieval | 1371 [1236, 2229.75] | 1436 [1266, 2332] | 1144 [957, 2022.25] | 1178 | 1187 | 913.5 |
| support_triage | 1271.5 [1175.25, 2614.75] | 1288.5 [1162, 2524.5] | 985 [870, 2240.25] | 1020.5 | 1004 | 709.5 |

Overhead = median of (first-request bytes − prompt characters).

## Per-class F1

| Workflow | C1: all | C1: first | C1: all − first | TLS control, TLS arm: all | TLS control, TLS arm: first | TLS control, TLS arm: all − first | TLS control, cleartext arm: all | TLS control, cleartext arm: first | TLS control, cleartext arm: all − first |
|---|---|---|---|---|---|---|---|---|---|
| code_review | 0.682 [0.546, 0.785] | 0.739 [0.627, 0.825] | -0.057 [-0.122, +0.004] (n.s.) | 0.710 [0.595, 0.800] | 0.629 [0.485, 0.742] | +0.081 [-0.005, +0.176] (n.s.) | 0.710 [0.593, 0.800] | 0.622 [0.495, 0.726] | +0.088 [-0.003, +0.177] (n.s.) |
| data_analysis | 0.838 [0.781, 0.888] | 0.877 [0.820, 0.924] | -0.039 [-0.093, +0.018] (n.s.) | 0.815 [0.746, 0.873] | 0.785 [0.708, 0.852] | +0.030 [-0.042, +0.101] (n.s.) | 0.864 [0.802, 0.911] | 0.769 [0.688, 0.838] | +0.094 [+0.016, +0.175] |
| research_retrieval | 0.432 [0.351, 0.506] | 0.395 [0.259, 0.497] | +0.037 [-0.080, +0.165] (n.s.) | 0.750 [0.656, 0.816] | 0.377 [0.279, 0.481] | +0.373 [+0.241, +0.489] | 0.547 [0.447, 0.620] | 0.435 [0.343, 0.516] | +0.112 [-0.008, +0.221] (n.s.) |
| support_triage | 0.551 [0.466, 0.626] | 0.554 [0.469, 0.636] | -0.003 [-0.084, +0.081] (n.s.) | 0.688 [0.603, 0.767] | 0.539 [0.431, 0.638] | +0.149 [+0.044, +0.262] | 0.585 [0.493, 0.669] | 0.536 [0.440, 0.624] | +0.049 [-0.041, +0.136] (n.s.) |

## What adds to the first request (paired against the first request alone)

**C1** (first request alone 0.641 [0.589, 0.687])

| Features | macro-F1 | − first | code_review − first | data_analysis − first | research_retrieval − first | support_triage − first |
|---|---|---|---|---|---|---|
| first + sizes | 0.663 [0.613, 0.711] | +0.021 [-0.021, +0.068] (n.s.) | -0.007 [-0.064, +0.046] (n.s.) | -0.007 [-0.044, +0.028] (n.s.) | +0.074 [-0.021, +0.182] (n.s.) | +0.025 [-0.048, +0.096] (n.s.) |
| first + timing | 0.650 [0.593, 0.704] | +0.008 [-0.041, +0.063] (n.s.) | -0.051 [-0.119, +0.012] (n.s.) | +0.002 [-0.045, +0.049] (n.s.) | +0.056 [-0.056, +0.190] (n.s.) | +0.027 [-0.046, +0.101] (n.s.) |
| first + counts_direction | 0.640 [0.588, 0.685] | -0.001 [-0.040, +0.037] (n.s.) | -0.039 [-0.090, +0.008] (n.s.) | -0.046 [-0.082, -0.013] | +0.082 [+0.004, +0.170] | -0.002 [-0.077, +0.066] (n.s.) |
| first + response-side features | 0.671 [0.614, 0.722] | +0.030 [-0.019, +0.080] (n.s.) | -0.016 [-0.086, +0.049] (n.s.) | +0.005 [-0.040, +0.051] (n.s.) | +0.094 [-0.017, +0.210] (n.s.) | +0.037 [-0.031, +0.107] (n.s.) |

**TLS control, TLS arm** (first request alone 0.582 [0.516, 0.643])

| Features | macro-F1 | − first | code_review − first | data_analysis − first | research_retrieval − first | support_triage − first |
|---|---|---|---|---|---|---|
| first + sizes | 0.759 [0.711, 0.803] | +0.177 [+0.109, +0.240] | +0.091 [-0.006, +0.204] (n.s.) | +0.031 [-0.027, +0.089] (n.s.) | +0.396 [+0.256, +0.515] | +0.190 [+0.099, +0.285] |
| first + timing | 0.717 [0.665, 0.765] | +0.135 [+0.075, +0.192] | +0.084 [+0.007, +0.173] | +0.071 [+0.014, +0.134] | +0.249 [+0.114, +0.363] | +0.136 [+0.049, +0.222] |
| first + counts_direction | 0.652 [0.600, 0.700] | +0.069 [+0.013, +0.126] | +0.059 [-0.021, +0.156] (n.s.) | +0.044 [-0.011, +0.100] (n.s.) | +0.118 [+0.013, +0.212] | +0.055 [-0.035, +0.152] (n.s.) |
| first + response-side features | 0.740 [0.689, 0.783] | +0.158 [+0.092, +0.217] | +0.119 [+0.039, +0.209] | +0.083 [+0.024, +0.147] | +0.290 [+0.143, +0.414] | +0.139 [+0.053, +0.226] |

**TLS control, cleartext arm** (first request alone 0.590 [0.529, 0.644])

| Features | macro-F1 | − first | code_review − first | data_analysis − first | research_retrieval − first | support_triage − first |
|---|---|---|---|---|---|---|
| first + sizes | 0.666 [0.603, 0.725] | +0.076 [+0.022, +0.133] | +0.038 [-0.046, +0.125] (n.s.) | +0.096 [+0.033, +0.163] | +0.083 [-0.015, +0.195] (n.s.) | +0.087 [+0.004, +0.164] |
| first + timing | 0.696 [0.647, 0.739] | +0.105 [+0.045, +0.160] | +0.084 [+0.009, +0.161] | +0.128 [+0.061, +0.205] | +0.131 [+0.013, +0.233] | +0.078 [-0.011, +0.162] (n.s.) |
| first + counts_direction | 0.578 [0.513, 0.641] | -0.012 [-0.063, +0.042] (n.s.) | -0.031 [-0.098, +0.040] (n.s.) | +0.042 [-0.016, +0.105] (n.s.) | -0.029 [-0.140, +0.084] (n.s.) | -0.031 [-0.115, +0.052] (n.s.) |
| first + response-side features | 0.709 [0.662, 0.751] | +0.118 [+0.064, +0.171] | +0.098 [+0.022, +0.180] | +0.152 [+0.087, +0.232] | +0.145 [+0.039, +0.249] | +0.078 [-0.003, +0.161] (n.s.) |

## Restricted to the 168 prompts shared by C1 and the TLS control

| Set | n (groups) | All features | First request only | All − first |
|---|---|---|---|---|
| C1 | 409 (168) | 0.596 [0.533, 0.647] | 0.686 [0.601, 0.754] | -0.090 [-0.158, -0.014] |
| TLS control, TLS arm | 343 (168) | 0.708 [0.644, 0.761] | 0.598 [0.534, 0.654] | +0.109 [+0.035, +0.180] |
| TLS control, cleartext arm | 343 (168) | 0.653 [0.589, 0.711] | 0.566 [0.499, 0.625] | +0.088 [+0.022, +0.151] |

## C1 with training cut to the TLS control's size (345 traces per fold)

All features 0.605 [0.556, 0.650]; first request only 0.680 [0.625, 0.725]; all − first -0.075 [-0.132, -0.013].
