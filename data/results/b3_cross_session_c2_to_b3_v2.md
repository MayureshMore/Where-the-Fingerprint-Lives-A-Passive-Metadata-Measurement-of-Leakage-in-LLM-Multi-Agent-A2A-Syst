# Cross-session transfer, view v2: C2 (all) → C2B3 (all)

Commit `8c227411` (clean: True); seed 42; train C2 (`data/raw_c2`, features `data/features_b3_cross/c2_lan_v2`), test C2B3 (`data/raw_c2b3_lan`, features `data/features_b3_cross/c2b3_lan_v2`). Test traces whose prompt also occurs in the training side are dropped.

| Attribute | train n | test n (shared dropped) | transfer macro-F1 [95% CI] | p | verdict | within the test session | C2 within (a7) |
|---|---|---|---|---|---|---|---|
| task_type | 1000 | 971 (29) | 0.878 [0.858, 0.897] | 0.01 | LEAK | LEAK 0.958 [0.944, 0.969] | LEAK 0.975 [0.965, 0.984] |
| escalated | 1000 | 971 (29) | 1.000 [1.000, 1.000] | 0.01 | LEAK | LEAK 1.000 [1.000, 1.000] | LEAK 1.000 [1.000, 1.000] |
| cloud_role | 750 | 725 (25) | 0.987 [0.978, 0.995] | 0.01 | LEAK | LEAK 0.997 [0.992, 1.000] | LEAK 0.998 [0.995, 1.000] |
| audit_null | 1000 | 971 (29) | 0.215 [0.192, 0.243] | 0.87 | NO LEAK | NO LEAK 0.231 [0.206, 0.255] | NO LEAK 0.238 [0.211, 0.265] |
| pair | 500 | 500 (0) | 0.732 [0.693, 0.768] | 0.01 | LEAK | LEAK 0.916 [0.891, 0.938] | LEAK 0.940 [0.920, 0.960] |
| escalated_only | 750 | 725 (25) | 0.828 [0.801, 0.854] | 0.01 | LEAK | LEAK 0.944 [0.927, 0.960] | LEAK 0.963 [0.948, 0.975] |

C2 within: `data/results/paper2_round2.json` section a7, lan_v2, seed 42 (commit a9b9dd76, clean: True).
