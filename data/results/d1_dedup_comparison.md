# D1 before and after counting every payload byte once

Old: `data/results/superseded/d1_before_dedup` (retransmitted segments counted again). New: `data/results` (each payload byte once). Pending: not rebuilt yet.

TLS − cleartext paired difference under both measures (macro-F1, 95% CI over shared prompt groups):

| Task | Old: retransmissions counted | New: each byte once |
|---|---|---|
| role | 0.0008 [-0.0072, 0.0083] (not significant) | 0.0008 [-0.0070, 0.0081] (not significant) |
| workflow | -0.0463 [-0.1049, 0.0147] (not significant) | -0.0825 [-0.1375, -0.0255] (significant) |
| topology | 0.0000 [0.0000, 0.0000] (not significant) | 0.0000 [0.0000, 0.0000] (not significant) |

| Number | Old | New | Same |
|---|---|---|---|
| D1 TLS: traces | 432 | 432 | yes |
| D1 TLS: runtime total (s) | 123.4808 | 135.2724 | no |
| D1 TLS: runtime analysis (s) | 100.7861 | 111.4277 | no |
| D1 TLS: peak memory per worker (MB) | 431.7031 | 267.7656 | no |
| D1 TLS role: verdict | LEAK | LEAK | yes |
| D1 TLS role: macro-F1 [CI] | 0.9907 [0.9842, 0.9968] | 0.9907 [0.9843, 0.9963] | no |
| D1 TLS role: p | 0.0100 | 0.0100 | yes |
| D1 TLS role: permuted LEAK / INCONCLUSIVE of 99 | 0 / 4 | 0 / 6 | no |
| D1 TLS role: timing alone, macro-F1 [CI] | 0.9738 [0.9630, 0.9833] | 0.9722 [0.9610, 0.9819] | no |
| D1 TLS workflow: verdict | LEAK | LEAK | yes |
| D1 TLS workflow: macro-F1 [CI] | 0.6128 [0.5577, 0.6600] | 0.5766 [0.5182, 0.6267] | no |
| D1 TLS workflow: p | 0.0100 | 0.0100 | yes |
| D1 TLS workflow: permuted LEAK / INCONCLUSIVE of 99 | 0 / 28 | 0 / 29 | no |
| D1 TLS workflow: first request alone, macro-F1 [CI] | 0.5825 [0.5149, 0.6419] | 0.5716 [0.5141, 0.6281] | no |
| D1 TLS workflow: first request alone matches all | yes | yes | yes |
| D1 TLS workflow: all − first request alone | 0.0303 | 0.0051 | no |
| D1 TLS topology: verdict | LEAK | LEAK | yes |
| D1 TLS topology: macro-F1 [CI] | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | yes |
| D1 TLS topology: p | 0.0100 | 0.0100 | yes |
| D1 TLS topology: permuted LEAK / INCONCLUSIVE of 99 | 0 / 38 | 0 / 40 | no |
| D1 cleartext: traces | 432 | 432 | yes |
| D1 cleartext: runtime total (s) | 121.4680 | 148.6290 | no |
| D1 cleartext: runtime analysis (s) | 100.0067 | 124.2092 | no |
| D1 cleartext: peak memory per worker (MB) | 440.6562 | 259.7812 | no |
| D1 cleartext role: verdict | LEAK | LEAK | yes |
| D1 cleartext role: macro-F1 [CI] | 0.9900 [0.9834, 0.9952] | 0.9900 [0.9834, 0.9952] | yes |
| D1 cleartext role: p | 0.0100 | 0.0100 | yes |
| D1 cleartext role: permuted LEAK / INCONCLUSIVE of 99 | 0 / 6 | 0 / 6 | yes |
| D1 cleartext role: timing alone, macro-F1 [CI] | 0.9830 [0.9735, 0.9916] | 0.9830 [0.9735, 0.9916] | yes |
| D1 cleartext workflow: verdict | LEAK | LEAK | yes |
| D1 cleartext workflow: macro-F1 [CI] | 0.6591 [0.6021, 0.7114] | 0.6591 [0.6021, 0.7114] | yes |
| D1 cleartext workflow: p | 0.0100 | 0.0100 | yes |
| D1 cleartext workflow: permuted LEAK / INCONCLUSIVE of 99 | 0 / 31 | 0 / 31 | yes |
| D1 cleartext workflow: first request alone, macro-F1 [CI] | 0.5905 [0.5274, 0.6449] | 0.5874 [0.5319, 0.6381] | no |
| D1 cleartext workflow: first request alone matches all | no | no | yes |
| D1 cleartext workflow: all − first request alone | 0.0686 | 0.0717 | no |
| D1 cleartext topology: verdict | LEAK | LEAK | yes |
| D1 cleartext topology: macro-F1 [CI] | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | yes |
| D1 cleartext topology: p | 0.0100 | 0.0100 | yes |
| D1 cleartext topology: permuted LEAK / INCONCLUSIVE of 99 | 0 / 40 | 0 / 40 | yes |
| D1 both arms: permuted-label LEAK / INCONCLUSIVE / runs | 0 / 147 / 594 | 0 / 152 / 594 | no |
| tls_control_own: retransmissions | kept (before Nov 14) | dropped: every payload byte counted once (TCP sequence numbers) | no |
| role: within cleartext, macro-F1 [CI] | 0.9900 [0.9835, 0.9957] | 0.9900 [0.9835, 0.9957] | yes |
| role: within TLS, macro-F1 [CI] | 0.9907 [0.9842, 0.9964] | 0.9907 [0.9843, 0.9962] | no |
| role: TLS − cleartext [CI] | 0.0008 [-0.0072, 0.0083] | 0.0008 [-0.0070, 0.0081] | no |
| role: TLS − cleartext interval contains 0 (not significant) | yes | yes | yes |
| role: shared prompt groups | 231 | 231 | yes |
| role: cleartext → TLS, macro-F1 [CI] | 0.9606 [0.9483, 0.9725] | 0.9606 [0.9483, 0.9725] | yes |
| workflow: within cleartext, macro-F1 [CI] | 0.6591 [0.6030, 0.7084] | 0.6591 [0.6030, 0.7084] | yes |
| workflow: within TLS, macro-F1 [CI] | 0.6128 [0.5584, 0.6616] | 0.5766 [0.5205, 0.6268] | no |
| workflow: TLS − cleartext [CI] | -0.0463 [-0.1049, 0.0147] | -0.0825 [-0.1375, -0.0255] | no |
| workflow: TLS − cleartext interval contains 0 (not significant) | yes | no | no |
| workflow: shared prompt groups | 231 | 231 | yes |
| workflow: cleartext → TLS, macro-F1 [CI] | 0.4782 [0.4227, 0.5296] | 0.4740 [0.4183, 0.5265] | no |
| topology: within cleartext, macro-F1 [CI] | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | yes |
| topology: within TLS, macro-F1 [CI] | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | yes |
| topology: TLS − cleartext [CI] | 0.0000 [0.0000, 0.0000] | 0.0000 [0.0000, 0.0000] | yes |
| topology: TLS − cleartext interval contains 0 (not significant) | yes | yes | yes |
| topology: shared prompt groups | 231 | 231 | yes |
| topology: cleartext → TLS, macro-F1 [CI] | 0.9954 [0.9881, 1.0000] | 0.9954 [0.9881, 1.0000] | yes |
| on-wire bytes per trace, TLS / cleartext | 1.0857 | 1.0855 | no |
| on-wire packets per trace, TLS / cleartext | 1.0490 | 1.0483 | no |
| tool eval leakcheck: recall (TP of known leaks) | 1.0000 / 6 / 6 | 1.0000 / 6 / 6 | yes |
| tool eval leakcheck: false-positive rate (FP of known non-leaks) | 0.0000 / 0 / 120 | 0.0000 / 0 / 120 | yes |
| tool eval leakcheck: precision | 1.0000 | 1.0000 | yes |
| tool eval kfp_rf: recall (TP of known leaks) | 1.0000 / 6 / 6 | 1.0000 / 6 / 6 | yes |
| tool eval kfp_rf: false-positive rate (FP of known non-leaks) | 0.0000 / 0 / 120 | 0.0000 / 0 / 120 | yes |
| tool eval kfp_rf: precision | 1.0000 | 1.0000 | yes |
| tool eval first_request: recall (TP of known leaks) | 0.6667 / 4 / 6 | 0.6667 / 4 / 6 | yes |
| tool eval first_request: false-positive rate (FP of known non-leaks) | 0.0000 / 0 / 120 | 0.0000 / 0 / 120 | yes |
| tool eval first_request: precision | 1.0000 | 1.0000 | yes |
| tool eval sample size 20: recall [CI] | 0.8750 [0.8040, 0.9228] | 0.9000 [0.8333, 0.9419] | no |
| tool eval sample size 20: false-positive rate | 0.0083 | 0.0000 | no |
| tool eval sample size 30: recall [CI] | 0.9833 [0.9413, 0.9954] | 0.9917 [0.9543, 0.9985] | no |
| tool eval sample size 30: false-positive rate | 0.0083 | 0.0083 | yes |
| tool eval sample size 50: recall [CI] | 1.0000 [0.9690, 1.0000] | 1.0000 [0.9690, 1.0000] | yes |
| tool eval sample size 50: false-positive rate | 0.0000 | 0.0000 | yes |

## Old against new on the same folds and bootstrap resamples

GBT out-of-fold predictions on the old features (retransmissions counted) and the new ones (each byte once), the same 5 folds, scored on the same 2,000 group resamples (paired, as paper 1's robustness check).

| Arm | Task | Old macro-F1 [CI] | New macro-F1 [CI] | New − old [CI] | Significant | Predictions that differ |
|---|---|---|---|---|---|---|
| TLS | role | 0.9907 [0.9842, 0.9964] | 0.9907 [0.9843, 0.9962] | +0.0000 [-0.0023, +0.0022] | no | 2 of 1296 |
| TLS | workflow | 0.6128 [0.5584, 0.6616] | 0.5766 [0.5205, 0.6268] | -0.0362 [-0.0649, -0.0074] | yes | 47 of 432 |
| TLS | topology | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | +0.0000 [+0.0000, +0.0000] | no | 0 of 432 |
| cleartext | role | 0.9900 [0.9835, 0.9957] | 0.9900 [0.9835, 0.9957] | +0.0000 [+0.0000, +0.0000] | no | 0 of 1296 |
| cleartext | workflow | 0.6591 [0.6030, 0.7084] | 0.6591 [0.6030, 0.7084] | +0.0000 [+0.0000, +0.0000] | no | 0 of 432 |
| cleartext | topology | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | +0.0000 [+0.0000, +0.0000] | no | 0 of 432 |

## TCP retransmissions in each arm (what counting each byte once drops)

Each trace's own agent connections; a retransmission carries no new payload byte (features/kfp.py).

| | TLS | cleartext |
|---|---|---|
| traces | 432 | 432 |
| traces with at least one | 147 | 0 |
| retransmitted segments | 196 | 0 |
| of which requests / responses | 0 / 196 | 0 / 0 |
| after their connection's last data packet | 196 | 0 |
| partial retransmissions (only the new bytes kept) | 0 | 0 |
| payload bytes dropped (share of all payload) | 4,704 (0.01%) | 0 (0.00%) |
| payload size min / median / max (B) | 24 / 24 / 24 | — / — / — |
| payload 0-100 B | 196 | 0 |
| payload 101-1000 B | 0 | 0 |
| payload >1000 B | 0 | 0 |

TLS arm, per workflow:

| Class | Traces | With at least one | Segments | Per trace |
|---|---|---|---|---|
| code_review | 108 | 35 | 47 | 0.44 |
| data_analysis | 108 | 41 | 51 | 0.47 |
| research_retrieval | 108 | 35 | 52 | 0.48 |
| support_triage | 108 | 36 | 46 | 0.43 |

Chi-square (traces with at least one, by class): χ² = 1.02, dof 3, p = 0.796; Kruskal-Wallis (retransmissions per trace): H = 0.54, p = 0.909.

cleartext arm, per workflow:

| Class | Traces | With at least one | Segments | Per trace |
|---|---|---|---|---|
| code_review | 108 | 0 | 0 | 0.00 |
| data_analysis | 108 | 0 | 0 | 0.00 |
| research_retrieval | 108 | 0 | 0 | 0.00 |
| support_triage | 108 | 0 | 0 | 0.00 |

Chi-square (traces with at least one, by class): not defined; Kruskal-Wallis (retransmissions per trace): not defined.

TLS arm, per topology:

| Class | Traces | With at least one | Segments | Per trace |
|---|---|---|---|---|
| chain | 144 | 0 | 0 | 0.00 |
| mesh | 144 | 40 | 40 | 0.28 |
| star | 144 | 107 | 156 | 1.08 |

Chi-square (traces with at least one, by class): χ² = 180.84, dof 2, p = 5.38e-40; Kruskal-Wallis (retransmissions per trace): H = 192.93, p = 1.27e-42.

cleartext arm, per topology:

| Class | Traces | With at least one | Segments | Per trace |
|---|---|---|---|---|
| chain | 144 | 0 | 0 | 0.00 |
| mesh | 144 | 0 | 0 | 0.00 |
| star | 144 | 0 | 0 | 0.00 |

Chi-square (traces with at least one, by class): not defined; Kruskal-Wallis (retransmissions per trace): not defined.
