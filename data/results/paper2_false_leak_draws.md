# The permuted-label draws behind the false LEAKs, re-run

From `data/results/paper2_tool_eval_c2.json` (evaluation commit e485f117); re-run at commit 2c1f3ef1. Stored verdict counts reproduced in every combination: True.

| Arm | View | Attribute | Per class | Draw | p | macro-F1 [95% CI] | Prompt groups |
|---|---|---|---|---|---|---|---|
| lan | v1 | escalated | 50 | 4 | 0.03 | 0.678 [0.585, 0.769] | 100 |
| lan | v1 | cloud_role | 30 | 17 | 0.02 | 0.683 [0.568, 0.782] | 59 |
| lan | v2 | escalated | 20 | 3 | 0.02 | 0.699 [0.559, 0.840] | 38 |
| lan_pad | v2 | escalated | 20 | 13 | 0.05 | 0.716 [0.568, 0.844] | 40 |
| lan_padmax | v1 | escalated | 20 | 1 | 0.04 | 0.721 [0.572, 0.848] | 40 |
| lan_padmax | v2 | escalated | 20 | 1 | 0.04 | 0.723 [0.575, 0.871] | 40 |
| lan_padmax | v2 | escalated | 20 | 3 | 0.02 | 0.699 [0.552, 0.819] | 38 |
| lan_padmax | v2 | escalated | 20 | 13 | 0.01 | 0.716 [0.561, 0.855] | 40 |
| lan_padmax | v2 | cloud_role | 30 | 1 | 0.04 | 0.750 [0.619, 0.850] | 59 |
| lan_padmax | v2 | cloud_role | 50 | 3 | 0.03 | 0.660 [0.557, 0.750] | 98 |
| lan_padmax | v2 | cloud_role | 50 | 14 | 0.03 | 0.690 [0.596, 0.780] | 99 |

Shared prompt groups between false LEAKs:

- lan_v1 escalated n=50 draw 4 and lan_v1 cloud_role n=30 draw 17: 5 in common
- lan_v1 escalated n=50 draw 4 and lan_v2 escalated n=20 draw 3: 6 in common
- lan_v1 escalated n=50 draw 4 and lan_pad_v2 escalated n=20 draw 13: 2 in common
- lan_v1 escalated n=50 draw 4 and lan_padmax_v1 escalated n=20 draw 1: 2 in common
- lan_v1 escalated n=50 draw 4 and lan_padmax_v2 escalated n=20 draw 1: 2 in common
- lan_v1 escalated n=50 draw 4 and lan_padmax_v2 escalated n=20 draw 3: 6 in common
- lan_v1 escalated n=50 draw 4 and lan_padmax_v2 escalated n=20 draw 13: 2 in common
- lan_v1 escalated n=50 draw 4 and lan_padmax_v2 cloud_role n=30 draw 1: 4 in common
- lan_v1 escalated n=50 draw 4 and lan_padmax_v2 cloud_role n=50 draw 3: 6 in common
- lan_v1 escalated n=50 draw 4 and lan_padmax_v2 cloud_role n=50 draw 14: 13 in common
- lan_v1 cloud_role n=30 draw 17 and lan_v2 escalated n=20 draw 3: 2 in common
- lan_v1 cloud_role n=30 draw 17 and lan_pad_v2 escalated n=20 draw 13: 3 in common
- lan_v1 cloud_role n=30 draw 17 and lan_padmax_v1 escalated n=20 draw 1: 2 in common
- lan_v1 cloud_role n=30 draw 17 and lan_padmax_v2 escalated n=20 draw 1: 2 in common
- lan_v1 cloud_role n=30 draw 17 and lan_padmax_v2 escalated n=20 draw 3: 2 in common
- lan_v1 cloud_role n=30 draw 17 and lan_padmax_v2 escalated n=20 draw 13: 3 in common
- lan_v1 cloud_role n=30 draw 17 and lan_padmax_v2 cloud_role n=30 draw 1: 5 in common
- lan_v1 cloud_role n=30 draw 17 and lan_padmax_v2 cloud_role n=50 draw 3: 9 in common
- lan_v1 cloud_role n=30 draw 17 and lan_padmax_v2 cloud_role n=50 draw 14: 9 in common
- lan_v2 escalated n=20 draw 3 and lan_pad_v2 escalated n=20 draw 13: 3 in common
- lan_v2 escalated n=20 draw 3 and lan_padmax_v1 escalated n=20 draw 1: 1 in common
- lan_v2 escalated n=20 draw 3 and lan_padmax_v2 escalated n=20 draw 1: 1 in common
- lan_v2 escalated n=20 draw 3 and lan_padmax_v2 escalated n=20 draw 3: 38 in common (same draw index: the same subsample)
- lan_v2 escalated n=20 draw 3 and lan_padmax_v2 escalated n=20 draw 13: 3 in common
- lan_v2 escalated n=20 draw 3 and lan_padmax_v2 cloud_role n=50 draw 3: 4 in common
- lan_v2 escalated n=20 draw 3 and lan_padmax_v2 cloud_role n=50 draw 14: 2 in common
- lan_pad_v2 escalated n=20 draw 13 and lan_padmax_v1 escalated n=20 draw 1: 3 in common
- lan_pad_v2 escalated n=20 draw 13 and lan_padmax_v2 escalated n=20 draw 1: 3 in common
- lan_pad_v2 escalated n=20 draw 13 and lan_padmax_v2 escalated n=20 draw 3: 3 in common
- lan_pad_v2 escalated n=20 draw 13 and lan_padmax_v2 escalated n=20 draw 13: 40 in common (same draw index: the same subsample)
- lan_pad_v2 escalated n=20 draw 13 and lan_padmax_v2 cloud_role n=30 draw 1: 3 in common
- lan_pad_v2 escalated n=20 draw 13 and lan_padmax_v2 cloud_role n=50 draw 3: 3 in common
- lan_padmax_v1 escalated n=20 draw 1 and lan_padmax_v2 escalated n=20 draw 1: 40 in common (same draw index: the same subsample)
- lan_padmax_v1 escalated n=20 draw 1 and lan_padmax_v2 escalated n=20 draw 3: 1 in common
- lan_padmax_v1 escalated n=20 draw 1 and lan_padmax_v2 escalated n=20 draw 13: 3 in common
- lan_padmax_v1 escalated n=20 draw 1 and lan_padmax_v2 cloud_role n=30 draw 1: 2 in common
- lan_padmax_v1 escalated n=20 draw 1 and lan_padmax_v2 cloud_role n=50 draw 3: 2 in common
- lan_padmax_v1 escalated n=20 draw 1 and lan_padmax_v2 cloud_role n=50 draw 14: 3 in common
- lan_padmax_v2 escalated n=20 draw 1 and lan_padmax_v2 escalated n=20 draw 3: 1 in common
- lan_padmax_v2 escalated n=20 draw 1 and lan_padmax_v2 escalated n=20 draw 13: 3 in common
- lan_padmax_v2 escalated n=20 draw 1 and lan_padmax_v2 cloud_role n=30 draw 1: 2 in common
- lan_padmax_v2 escalated n=20 draw 1 and lan_padmax_v2 cloud_role n=50 draw 3: 2 in common
- lan_padmax_v2 escalated n=20 draw 1 and lan_padmax_v2 cloud_role n=50 draw 14: 3 in common
- lan_padmax_v2 escalated n=20 draw 3 and lan_padmax_v2 escalated n=20 draw 13: 3 in common
- lan_padmax_v2 escalated n=20 draw 3 and lan_padmax_v2 cloud_role n=50 draw 3: 4 in common
- lan_padmax_v2 escalated n=20 draw 3 and lan_padmax_v2 cloud_role n=50 draw 14: 2 in common
- lan_padmax_v2 escalated n=20 draw 13 and lan_padmax_v2 cloud_role n=30 draw 1: 3 in common
- lan_padmax_v2 escalated n=20 draw 13 and lan_padmax_v2 cloud_role n=50 draw 3: 3 in common
- lan_padmax_v2 cloud_role n=30 draw 1 and lan_padmax_v2 cloud_role n=50 draw 3: 10 in common
- lan_padmax_v2 cloud_role n=30 draw 1 and lan_padmax_v2 cloud_role n=50 draw 14: 11 in common
- lan_padmax_v2 cloud_role n=50 draw 3 and lan_padmax_v2 cloud_role n=50 draw 14: 16 in common

Each false LEAK's prompt groups and permuted labels are in the JSON (`false_leaks`).
