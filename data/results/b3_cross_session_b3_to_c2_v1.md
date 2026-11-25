# Cross-session transfer, view v1: C2B3 (all) → C2 (all)

Commit `8c227411` (clean: True); seed 42; train C2B3 (`data/raw_c2b3_lan`, features `data/features_b3_cross/c2b3_lan_v1`), test C2 (`data/raw_c2`, features `data/features_b3_cross/c2_lan_v1`). Test traces whose prompt also occurs in the training side are dropped.

| Attribute | train n | test n (shared dropped) | transfer macro-F1 [95% CI] | p | verdict | within the test session | C2 within (a7) |
|---|---|---|---|---|---|---|---|
| task_type | 1000 | 970 (30) | 0.843 [0.820, 0.863] | 0.01 | LEAK | LEAK 0.967 [0.955, 0.977] | LEAK 0.967 [0.955, 0.977] |
| escalated | 1000 | 970 (30) | 1.000 [1.000, 1.000] | 0.01 | LEAK | LEAK 1.000 [1.000, 1.000] | LEAK 1.000 [1.000, 1.000] |
| cloud_role | 750 | 724 (26) | 0.995 [0.990, 1.000] | 0.01 | LEAK | LEAK 0.998 [0.994, 1.000] | LEAK 0.998 [0.995, 1.000] |
| audit_null | 1000 | 970 (30) | 0.255 [0.230, 0.283] | 0.23 | NO LEAK | NO LEAK 0.226 [0.201, 0.252] | NO LEAK 0.250 [0.222, 0.275] |
| pair | 500 | 500 (0) | 0.661 [0.617, 0.701] | 0.01 | LEAK | LEAK 0.934 [0.912, 0.954] | LEAK 0.934 [0.912, 0.954] |
| escalated_only | 750 | 724 (26) | 0.770 [0.741, 0.800] | 0.01 | LEAK | LEAK 0.956 [0.940, 0.969] | LEAK 0.959 [0.945, 0.972] |

C2 within: `data/results/paper2_round2.json` section a7, lan_v1, seed 42 (commit a9b9dd76, clean: True).
