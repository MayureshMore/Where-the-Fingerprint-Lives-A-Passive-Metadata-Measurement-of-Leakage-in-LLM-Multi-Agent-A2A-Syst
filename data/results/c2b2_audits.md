# C2B2 audits (C2B2)

Commit 37e568015125df383cb2c7ff5080f40aa4f73e11 (dirty: False), seed 42; a2a-leakcheck defaults (perm-unit group, match-margin 0.05, margin 0.05, 99 permutations, 1000 bootstraps, gbt, --strip).

| Run | Attribute | Verdict | Macro-F1 [95% CI] | Threshold | p | Carried by |
|---|---|---|---|---|---|---|
| c2b2_lan_padmax_v1 | task_type | LEAK | 0.837 [0.816, 0.857] | 0.300 | 0.010 | sizes (alone matches all) |
| c2b2_lan_padmax_v1 | escalated | LEAK | 1.000 [1.000, 1.000] | 0.550 | 0.010 | first_request_bytes alone |
| c2b2_lan_padmax_v1 | cloud_role | LEAK | 0.994 [0.987, 0.999] | 0.550 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_v1 | audit_null | NO LEAK | 0.229 [0.202, 0.255] | 0.300 | 0.780 | - |
| c2b2_lan_padmax_v1_timing | task_type (timing alone) | LEAK | 0.801 [0.780, 0.822] | 0.300 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_v1_timing | escalated (timing alone) | LEAK | 1.000 [1.000, 1.000] | 0.550 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_v1_timing | cloud_role (timing alone) | LEAK | 0.988 [0.979, 0.995] | 0.550 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_v1_timing | audit_null (timing alone) | NO LEAK | 0.244 [0.218, 0.269] | 0.300 | 0.750 | - |
| c2b2_lan_padmax_v1_pair | task_type | LEAK | 0.678 [0.637, 0.720] | 0.550 | 0.010 | sizes (alone matches all) |
| c2b2_lan_padmax_v1_pair_timing | task_type (timing alone) | LEAK | 0.632 [0.588, 0.672] | 0.550 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_v1_escalated_only | task_type | LEAK | 0.780 [0.753, 0.808] | 0.383 | 0.010 | sizes (alone matches all) |
| c2b2_lan_padmax_v1_escalated_only_timing | task_type (timing alone) | LEAK | 0.724 [0.695, 0.756] | 0.383 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_v2 | task_type | LEAK | 0.847 [0.827, 0.866] | 0.300 | 0.010 | sizes (alone matches all) |
| c2b2_lan_padmax_v2 | escalated | LEAK | 1.000 [1.000, 1.000] | 0.550 | 0.010 | first_request_bytes alone |
| c2b2_lan_padmax_v2 | cloud_role | LEAK | 0.995 [0.989, 1.000] | 0.550 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_v2 | audit_null | NO LEAK | 0.245 [0.219, 0.270] | 0.300 | 0.430 | - |
| c2b2_lan_padmax_v2_timing | task_type (timing alone) | LEAK | 0.814 [0.794, 0.835] | 0.300 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_v2_timing | escalated (timing alone) | LEAK | 1.000 [1.000, 1.000] | 0.550 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_v2_timing | cloud_role (timing alone) | LEAK | 0.991 [0.983, 0.997] | 0.550 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_v2_timing | audit_null (timing alone) | NO LEAK | 0.248 [0.222, 0.273] | 0.300 | 0.180 | - |
| c2b2_lan_padmax_v2_pair | task_type | LEAK | 0.688 [0.648, 0.728] | 0.550 | 0.010 | sizes (alone matches all) |
| c2b2_lan_padmax_v2_pair_timing | task_type (timing alone) | LEAK | 0.656 [0.612, 0.699] | 0.550 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_v2_escalated_only | task_type | LEAK | 0.788 [0.761, 0.816] | 0.383 | 0.010 | sizes (alone matches all) |
| c2b2_lan_padmax_v2_escalated_only_timing | task_type (timing alone) | LEAK | 0.745 [0.718, 0.774] | 0.383 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_jl_v1 | task_type | LEAK | 0.863 [0.843, 0.882] | 0.300 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_jl_v1 | escalated | LEAK | 1.000 [1.000, 1.000] | 0.550 | 0.010 | first_request_bytes alone |
| c2b2_lan_padmax_jl_v1 | cloud_role | LEAK | 0.998 [0.995, 1.000] | 0.550 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_jl_v1 | audit_null | INCONCLUSIVE | 0.282 [0.254, 0.309] | 0.300 | 0.080 | - |
| c2b2_lan_padmax_jl_v1_timing | task_type (timing alone) | LEAK | 0.846 [0.826, 0.866] | 0.300 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_jl_v1_timing | escalated (timing alone) | LEAK | 1.000 [1.000, 1.000] | 0.550 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_jl_v1_timing | cloud_role (timing alone) | LEAK | 0.998 [0.995, 1.000] | 0.550 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_jl_v1_timing | audit_null (timing alone) | NO LEAK | 0.273 [0.245, 0.300] | 0.300 | 0.780 | - |
| c2b2_lan_padmax_jl_v1_pair | task_type | LEAK | 0.688 [0.648, 0.726] | 0.550 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_jl_v1_pair_timing | task_type (timing alone) | LEAK | 0.688 [0.645, 0.727] | 0.550 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_jl_v1_escalated_only | task_type | LEAK | 0.821 [0.795, 0.847] | 0.383 | 0.010 | timing |
| c2b2_lan_padmax_jl_v1_escalated_only_timing | task_type (timing alone) | LEAK | 0.787 [0.759, 0.813] | 0.383 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_jl_v2 | task_type | LEAK | 0.867 [0.848, 0.886] | 0.300 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_jl_v2 | escalated | LEAK | 1.000 [1.000, 1.000] | 0.550 | 0.010 | first_request_bytes alone |
| c2b2_lan_padmax_jl_v2 | cloud_role | LEAK | 0.998 [0.995, 1.000] | 0.550 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_jl_v2 | audit_null | INCONCLUSIVE | 0.260 [0.233, 0.287] | 0.300 | 0.050 | - |
| c2b2_lan_padmax_jl_v2_timing | task_type (timing alone) | LEAK | 0.850 [0.830, 0.870] | 0.300 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_jl_v2_timing | escalated (timing alone) | LEAK | 1.000 [1.000, 1.000] | 0.550 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_jl_v2_timing | cloud_role (timing alone) | LEAK | 0.998 [0.995, 1.000] | 0.550 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_jl_v2_timing | audit_null (timing alone) | NO LEAK | 0.233 [0.206, 0.259] | 0.300 | 0.760 | - |
| c2b2_lan_padmax_jl_v2_pair | task_type | LEAK | 0.724 [0.684, 0.761] | 0.550 | 0.010 | timing |
| c2b2_lan_padmax_jl_v2_pair_timing | task_type (timing alone) | LEAK | 0.682 [0.638, 0.718] | 0.550 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_jl_v2_escalated_only | task_type | LEAK | 0.816 [0.789, 0.842] | 0.383 | 0.010 | timing (alone matches all) |
| c2b2_lan_padmax_jl_v2_escalated_only_timing | task_type (timing alone) | LEAK | 0.816 [0.790, 0.843] | 0.383 | 0.010 | timing (alone matches all) |

Baseline gate (`run --baseline`):

| Run | Against | Exit | Changes | New LEAK | Needs review | Resolved |
|---|---|---|---|---|---|---|
| c2b2_lan_padmax_jl_v1 | data/results/leakcheck/c2b2_lan_padmax_v1/report.json | 0 | audit_null NO LEAK → INCONCLUSIVE | - | - | - |
| c2b2_lan_padmax_jl_v1_timing | data/results/leakcheck/c2b2_lan_padmax_v1_timing/report.json | 0 | - | - | - | - |
| c2b2_lan_padmax_jl_v1_pair | data/results/leakcheck/c2b2_lan_padmax_v1_pair/report.json | 0 | - | - | - | - |
| c2b2_lan_padmax_jl_v1_pair_timing | data/results/leakcheck/c2b2_lan_padmax_v1_pair_timing/report.json | 0 | - | - | - | - |
| c2b2_lan_padmax_jl_v1_escalated_only | data/results/leakcheck/c2b2_lan_padmax_v1_escalated_only/report.json | 0 | - | - | - | - |
| c2b2_lan_padmax_jl_v1_escalated_only_timing | data/results/leakcheck/c2b2_lan_padmax_v1_escalated_only_timing/report.json | 0 | - | - | - | - |
| c2b2_lan_padmax_jl_v2 | data/results/leakcheck/c2b2_lan_padmax_v2/report.json | 0 | audit_null NO LEAK → INCONCLUSIVE | - | - | - |
| c2b2_lan_padmax_jl_v2_timing | data/results/leakcheck/c2b2_lan_padmax_v2_timing/report.json | 0 | - | - | - | - |
| c2b2_lan_padmax_jl_v2_pair | data/results/leakcheck/c2b2_lan_padmax_v2_pair/report.json | 0 | - | - | - | - |
| c2b2_lan_padmax_jl_v2_pair_timing | data/results/leakcheck/c2b2_lan_padmax_v2_pair_timing/report.json | 0 | - | - | - | - |
| c2b2_lan_padmax_jl_v2_escalated_only | data/results/leakcheck/c2b2_lan_padmax_v2_escalated_only/report.json | 0 | - | - | - | - |
| c2b2_lan_padmax_jl_v2_escalated_only_timing | data/results/leakcheck/c2b2_lan_padmax_v2_escalated_only_timing/report.json | 0 | - | - | - | - |
