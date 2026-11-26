# C2B1M audits (C2B1M)

Commit b02990e87d8dd999e59d030221f73f055908323b (dirty: False), seed 42; a2a-leakcheck defaults (perm-unit group, match-margin 0.05, margin 0.05, 99 permutations, 1000 bootstraps, gbt, --strip).

| Run | Attribute | Verdict | Macro-F1 [95% CI] | Threshold | p | Carried by |
|---|---|---|---|---|---|---|
| c2b1m_lan_padmax_v1_pair | task_type | LEAK | 0.694 [0.652, 0.733] | 0.550 | 0.010 | sizes (alone matches all) |
| c2b1m_lan_padmax_v2_pair | task_type | LEAK | 0.672 [0.630, 0.712] | 0.550 | 0.010 | sizes (alone matches all) |
| c2b1m_lan_shaped_v1_pair | task_type | INCONCLUSIVE | 0.571 [0.542, 0.598] | 0.550 | 0.010 | - |
| c2b1m_lan_shaped_v2_pair | task_type | INCONCLUSIVE | 0.520 [0.494, 0.547] | 0.550 | 0.050 | - |

Baseline gate (`run --baseline`):

| Run | Against | Exit | Changes | New LEAK | Needs review | Resolved |
|---|---|---|---|---|---|---|
| c2b1m_lan_shaped_v1_pair | data/results/leakcheck/c2b1m_lan_padmax_v1_pair/report.json | 0 | task_type LEAK → INCONCLUSIVE | - | task_type (INCONCLUSIVE) | - |
| c2b1m_lan_shaped_v2_pair | data/results/leakcheck/c2b1m_lan_padmax_v2_pair/report.json | 0 | task_type LEAK → INCONCLUSIVE | - | task_type (INCONCLUSIVE) | - |
