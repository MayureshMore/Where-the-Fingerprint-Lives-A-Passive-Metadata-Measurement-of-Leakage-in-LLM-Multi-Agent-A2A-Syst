# B1 audits (C2B1, C2B1X)

Commit 615db784719c7cd0ed55b9fbe8b281fc2596b87e (dirty: False), seed 42; a2a-leakcheck defaults (perm-unit group, match-margin 0.05, margin 0.05, 99 permutations, 1000 bootstraps, gbt, --strip).

| Run | Attribute | Verdict | Macro-F1 [95% CI] | Threshold | p | Carried by |
|---|---|---|---|---|---|---|
| c2b1_c2b1x_lan_shaped_v1_pair | task_type | INCONCLUSIVE | 0.544 [0.517, 0.571] | 0.550 | 0.010 | - |
| c2b1_c2b1x_lan_shaped_v2_pair | task_type | NO LEAK | 0.514 [0.485, 0.540] | 0.550 | 0.260 | - |

Baseline gate (`run --baseline`):

| Run | Against | Exit | Changes | New LEAK | Needs review | Resolved |
|---|---|---|---|---|---|---|
| c2b1_c2b1x_lan_shaped_v1_pair | data/results/leakcheck/c2b1_lan_padmax_v1_pair/report.json | 0 | task_type LEAK → INCONCLUSIVE | - | task_type (INCONCLUSIVE) | - |
| c2b1_c2b1x_lan_shaped_v2_pair | data/results/leakcheck/c2b1_lan_padmax_v2_pair/report.json | 0 | task_type LEAK → NO LEAK | - | - | task_type |
