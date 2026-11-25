# Cross-session transfer, view v2: C2B3 (all) → C2 (all)

Commit `8c227411` (clean: True); seed 42; train C2B3 (`data/raw_c2b3_lan`, features `data/features_b3_cross/c2b3_lan_v2`), test C2 (`data/raw_c2`, features `data/features_b3_cross/c2_lan_v2`). Test traces whose prompt also occurs in the training side are dropped.

| Attribute | train n | test n (shared dropped) | transfer macro-F1 [95% CI] | p | verdict | within the test session | C2 within (a7) |
|---|---|---|---|---|---|---|---|
| task_type | 1000 | 970 (30) | 0.809 [0.787, 0.831] | 0.01 | LEAK | LEAK 0.977 [0.967, 0.985] | LEAK 0.975 [0.965, 0.984] |
| escalated | 1000 | 970 (30) | 1.000 [1.000, 1.000] | 0.01 | LEAK | LEAK 1.000 [1.000, 1.000] | LEAK 1.000 [1.000, 1.000] |
| cloud_role | 750 | 724 (26) | 0.995 [0.990, 1.000] | 0.01 | LEAK | LEAK 0.998 [0.994, 1.000] | LEAK 0.998 [0.995, 1.000] |
| audit_null | 1000 | 970 (30) | 0.220 [0.195, 0.247] | 0.89 | NO LEAK | NO LEAK 0.228 [0.201, 0.255] | NO LEAK 0.238 [0.211, 0.265] |
| pair | 500 | 500 (0) | 0.668 [0.625, 0.707] | 0.01 | LEAK | LEAK 0.940 [0.920, 0.960] | LEAK 0.940 [0.920, 0.960] |
| escalated_only | 750 | 724 (26) | 0.691 [0.657, 0.720] | 0.01 | LEAK | LEAK 0.965 [0.952, 0.977] | LEAK 0.963 [0.948, 0.975] |

C2 within: `data/results/paper2_round2.json` section a7, lan_v2, seed 42 (commit a9b9dd76, clean: True).
