# B3 audits (C2B3)

Commit 8c2274118cca95ef94fd8d65cfe585012faa1c69 (dirty: False), seed 42; a2a-leakcheck defaults (perm-unit group, match-margin 0.05, margin 0.05, 99 permutations, 1000 bootstraps, gbt, --strip).

| Run | Attribute | Verdict | Macro-F1 [95% CI] | Threshold | p | Carried by |
|---|---|---|---|---|---|---|
| c2b3_lan_v1 | task_type | LEAK | 0.960 [0.948, 0.971] | 0.300 | 0.010 | sizes (alone matches all) |
| c2b3_lan_v1 | escalated | LEAK | 1.000 [1.000, 1.000] | 0.550 | 0.010 | counts_direction (alone matches all) |
| c2b3_lan_v1 | cloud_role | LEAK | 0.997 [0.992, 1.000] | 0.550 | 0.010 | first_request_bytes alone |
| c2b3_lan_v1 | audit_null | NO LEAK | 0.238 [0.212, 0.263] | 0.300 | 0.810 | - |
| c2b3_lan_v1_pair | task_type | LEAK | 0.916 [0.890, 0.938] | 0.550 | 0.010 | sizes (alone matches all) |
| c2b3_lan_v1_escalated_only | task_type | LEAK | 0.953 [0.937, 0.968] | 0.383 | 0.010 | sizes (alone matches all) |
| c2b3_lan_v2 | task_type | LEAK | 0.956 [0.943, 0.968] | 0.300 | 0.010 | sizes (alone matches all) |
| c2b3_lan_v2 | escalated | LEAK | 1.000 [1.000, 1.000] | 0.550 | 0.010 | first_request_bytes alone |
| c2b3_lan_v2 | cloud_role | LEAK | 0.997 [0.992, 1.000] | 0.550 | 0.010 | first_request_bytes alone |
| c2b3_lan_v2 | audit_null | NO LEAK | 0.239 [0.214, 0.266] | 0.300 | 0.960 | - |
| c2b3_lan_v2_pair | task_type | LEAK | 0.916 [0.891, 0.938] | 0.550 | 0.010 | sizes (alone matches all) |
| c2b3_lan_v2_escalated_only | task_type | LEAK | 0.948 [0.931, 0.963] | 0.383 | 0.010 | sizes (alone matches all) |
