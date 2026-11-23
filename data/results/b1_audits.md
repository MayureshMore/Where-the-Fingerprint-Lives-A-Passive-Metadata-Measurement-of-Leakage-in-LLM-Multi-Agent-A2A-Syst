# B1 audits (C2B1)

Commit 615db784719c7cd0ed55b9fbe8b281fc2596b87e (dirty: False), seed 42; a2a-leakcheck defaults (perm-unit group, match-margin 0.05, margin 0.05, 99 permutations, 1000 bootstraps, gbt, --strip).

| Run | Attribute | Verdict | Macro-F1 [95% CI] | Threshold | p | Carried by |
|---|---|---|---|---|---|---|
| c2b1_lan_padmax_v1 | task_type | LEAK | 0.796 [0.762, 0.825] | 0.300 | 0.010 | sizes (alone matches all) |
| c2b1_lan_padmax_v1 | escalated | LEAK | 0.992 [0.979, 1.000] | 0.550 | 0.010 | first_request_bytes alone |
| c2b1_lan_padmax_v1 | cloud_role | LEAK | 0.985 [0.972, 0.997] | 0.550 | 0.010 | timing (alone matches all) |
| c2b1_lan_padmax_v1 | audit_null | NO LEAK | 0.236 [0.201, 0.273] | 0.300 | 0.630 | - |
| c2b1_lan_padmax_v1_pair | task_type | LEAK | 0.612 [0.550, 0.671] | 0.550 | 0.010 | sizes |
| c2b1_lan_padmax_v1_escalated_only | task_type | LEAK | 0.726 [0.682, 0.764] | 0.383 | 0.010 | sizes (alone matches all) |
| c2b1_lan_padmax_v2 | task_type | LEAK | 0.784 [0.751, 0.814] | 0.300 | 0.010 | timing (alone matches all) |
| c2b1_lan_padmax_v2 | escalated | LEAK | 0.992 [0.979, 1.000] | 0.550 | 0.010 | first_request_bytes alone |
| c2b1_lan_padmax_v2 | cloud_role | LEAK | 0.982 [0.963, 0.994] | 0.550 | 0.010 | sizes (alone matches all) |
| c2b1_lan_padmax_v2 | audit_null | NO LEAK | 0.212 [0.176, 0.248] | 0.300 | 0.870 | - |
| c2b1_lan_padmax_v2_pair | task_type | LEAK | 0.628 [0.570, 0.685] | 0.550 | 0.010 | sizes |
| c2b1_lan_padmax_v2_escalated_only | task_type | LEAK | 0.726 [0.683, 0.763] | 0.383 | 0.010 | sizes (alone matches all) |
| c2b1_lan_shaped_v1 | task_type | LEAK | 0.574 [0.533, 0.612] | 0.300 | 0.010 | sizes (alone matches all) |
| c2b1_lan_shaped_v1 | escalated | LEAK | 1.000 [1.000, 1.000] | 0.550 | 0.010 | first_request_bytes alone |
| c2b1_lan_shaped_v1 | cloud_role | INCONCLUSIVE | 0.595 [0.545, 0.644] | 0.550 | 0.010 | - |
| c2b1_lan_shaped_v1 | audit_null | NO LEAK | 0.225 [0.187, 0.262] | 0.300 | 0.470 | - |
| c2b1_lan_shaped_v1_pair | task_type | INCONCLUSIVE | 0.552 [0.491, 0.608] | 0.550 | 0.010 | - |
| c2b1_lan_shaped_v1_escalated_only | task_type | INCONCLUSIVE | 0.432 [0.380, 0.478] | 0.383 | 0.010 | - |
| c2b1_lan_shaped_v2 | task_type | LEAK | 0.512 [0.474, 0.549] | 0.300 | 0.010 | counts_direction (alone matches all) |
| c2b1_lan_shaped_v2 | escalated | LEAK | 1.000 [1.000, 1.000] | 0.550 | 0.010 | first_request_bytes alone |
| c2b1_lan_shaped_v2 | cloud_role | INCONCLUSIVE | 0.500 [0.453, 0.554] | 0.550 | 0.230 | - |
| c2b1_lan_shaped_v2 | audit_null | NO LEAK | 0.198 [0.163, 0.232] | 0.300 | 0.890 | - |
| c2b1_lan_shaped_v2_pair | task_type | INCONCLUSIVE | 0.532 [0.470, 0.591] | 0.550 | 0.420 | - |
| c2b1_lan_shaped_v2_escalated_only | task_type | INCONCLUSIVE | 0.342 [0.292, 0.386] | 0.383 | 0.110 | - |

Baseline gate (`run --baseline`):

| Run | Against | Exit | Changes | New LEAK | Needs review | Resolved |
|---|---|---|---|---|---|---|
| c2b1_lan_shaped_v1 | data/results/leakcheck/c2b1_lan_padmax_v1/report.json | 0 | cloud_role LEAK → INCONCLUSIVE | - | cloud_role (INCONCLUSIVE) | - |
| c2b1_lan_shaped_v1_pair | data/results/leakcheck/c2b1_lan_padmax_v1_pair/report.json | 0 | task_type LEAK → INCONCLUSIVE | - | task_type (INCONCLUSIVE) | - |
| c2b1_lan_shaped_v1_escalated_only | data/results/leakcheck/c2b1_lan_padmax_v1_escalated_only/report.json | 0 | task_type LEAK → INCONCLUSIVE | - | task_type (INCONCLUSIVE) | - |
| c2b1_lan_shaped_v2 | data/results/leakcheck/c2b1_lan_padmax_v2/report.json | 0 | cloud_role LEAK → INCONCLUSIVE | - | cloud_role (INCONCLUSIVE) | - |
| c2b1_lan_shaped_v2_pair | data/results/leakcheck/c2b1_lan_padmax_v2_pair/report.json | 0 | task_type LEAK → INCONCLUSIVE | - | task_type (INCONCLUSIVE) | - |
| c2b1_lan_shaped_v2_escalated_only | data/results/leakcheck/c2b1_lan_padmax_v2_escalated_only/report.json | 0 | task_type LEAK → INCONCLUSIVE | - | task_type (INCONCLUSIVE) | - |
