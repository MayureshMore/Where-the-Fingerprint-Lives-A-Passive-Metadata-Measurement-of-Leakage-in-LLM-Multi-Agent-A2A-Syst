# Cross-session transfer, view v1: C2 (all) → C2B3 (all)

Commit `8c227411` (clean: True); seed 42; train C2 (`data/raw_c2`, features `data/features_b3_cross/c2_lan_v1`), test C2B3 (`data/raw_c2b3_lan`, features `data/features_b3_cross/c2b3_lan_v1`). Test traces whose prompt also occurs in the training side are dropped.

| Attribute | train n | test n (shared dropped) | transfer macro-F1 [95% CI] | p | verdict | within the test session | C2 within (a7) |
|---|---|---|---|---|---|---|---|
| task_type | 1000 | 971 (29) | 0.852 [0.831, 0.871] | 0.01 | LEAK | LEAK 0.958 [0.945, 0.970] | LEAK 0.967 [0.955, 0.977] |
| escalated | 1000 | 971 (29) | 1.000 [1.000, 1.000] | 0.01 | LEAK | LEAK 1.000 [1.000, 1.000] | LEAK 1.000 [1.000, 1.000] |
| cloud_role | 750 | 725 (25) | 0.987 [0.978, 0.995] | 0.01 | LEAK | LEAK 0.997 [0.992, 1.000] | LEAK 0.998 [0.995, 1.000] |
| audit_null | 1000 | 971 (29) | 0.261 [0.231, 0.288] | 0.16 | NO LEAK | NO LEAK 0.235 [0.210, 0.261] | NO LEAK 0.250 [0.222, 0.275] |
| pair | 500 | 500 (0) | 0.726 [0.688, 0.764] | 0.01 | LEAK | LEAK 0.916 [0.890, 0.938] | LEAK 0.934 [0.912, 0.954] |
| escalated_only | 750 | 725 (25) | 0.804 [0.777, 0.830] | 0.01 | LEAK | LEAK 0.940 [0.922, 0.955] | LEAK 0.959 [0.945, 0.972] |

C2 within: `data/results/paper2_round2.json` section a7, lan_v1, seed 42 (commit a9b9dd76, clean: True).
