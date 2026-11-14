# False LEAKs on permuted labels

From `data/results/paper2_tool_eval_c2.json` (evaluation commit e485f117); no model run here.

## 1. Pooled over every permuted subsample draw (all cells, attributes and views)

| Traces per class | False LEAK | Rate | Wilson 95% CI |
|---|---|---|---|
| 5 | 0/480 | 0.0000 | [0.0000, 0.0079] |
| 10 | 0/480 | 0.0000 | [0.0000, 0.0079] |
| 20 | 6/480 | 0.0125 | [0.0057, 0.0270] |
| 30 | 2/480 | 0.0042 | [0.0011, 0.0151] |
| 50 | 3/480 | 0.0063 | [0.0021, 0.0182] |

4-class attributes (audit_null, task_type):

| Traces per class | False LEAK | Rate | Wilson 95% CI |
|---|---|---|---|
| 5 | 0/240 | 0.0000 | [0.0000, 0.0158] |
| 10 | 0/240 | 0.0000 | [0.0000, 0.0158] |
| 20 | 0/240 | 0.0000 | [0.0000, 0.0158] |
| 30 | 0/240 | 0.0000 | [0.0000, 0.0158] |
| 50 | 0/240 | 0.0000 | [0.0000, 0.0158] |

Binary attributes (cloud_role, escalated):

| Traces per class | False LEAK | Rate | Wilson 95% CI |
|---|---|---|---|
| 5 | 0/240 | 0.0000 | [0.0000, 0.0158] |
| 10 | 0/240 | 0.0000 | [0.0000, 0.0158] |
| 20 | 6/240 | 0.0250 | [0.0115, 0.0535] |
| 30 | 2/240 | 0.0083 | [0.0023, 0.0299] |
| 50 | 3/240 | 0.0125 | [0.0043, 0.0361] |

Full data, the label permutations of each cell and attribute:

| Method | False LEAK | Rate | Wilson 95% CI |
|---|---|---|---|
| leakcheck | 0/480 | 0.0000 | [0.0000, 0.0079] |
| kfp_rf | 0/480 | 0.0000 | [0.0000, 0.0079] |
| first_request | 0/480 | 0.0000 | [0.0000, 0.0079] |

**Independence.** The Wilson intervals assume independent draws. The draws are not fully independent: for one attribute, size and draw index, every arm and view takes the same prompt groups, and the two views of an arm also get the same permuted labels (only the features differ). The intervals are therefore somewhat too narrow.

## 2. The test behind each draw

- 20 draws per cell, attribute and size, each with 1 label permutation of its subsample;
- each permuted draw goes through the full verdict rule: a permutation test with 99 permutations (rf-light), so the smallest p-value is 0.01; a LEAK needs p ≤ 0.05 and the cluster-bootstrap (1000 resamples) interval's lower bound above chance + 0.05 (two classes: 0.55);
- stored per draw: the verdict only (p-value and macro-F1 are not stored; scripts/rerun_false_leak_draws.py recomputes them).

## 3. The false LEAKs

| Arm | View | Attribute | Per class | False LEAK | LEAK needs CI lower bound above |
|---|---|---|---|---|---|
| lan | v2 | escalated | 20 | 1/20 | 0.55 |
| lan_pad | v2 | escalated | 20 | 1/20 | 0.55 |
| lan_padmax | v1 | escalated | 20 | 1/20 | 0.55 |
| lan_padmax | v2 | escalated | 20 | 3/20 | 0.55 |
| lan | v1 | cloud_role | 30 | 1/20 | 0.55 |
| lan_padmax | v2 | cloud_role | 30 | 1/20 | 0.55 |
| lan | v1 | escalated | 50 | 1/20 | 0.55 |
| lan_padmax | v2 | cloud_role | 50 | 2/20 | 0.55 |

How the draws relate (rebuilt from the sidecars with the evaluation's seeds):

- cloud_role/30: same prompt groups in every cell for a draw index: True; same permuted labels in both views of an arm: True; 57 groups per draw; different draw indices share 9% of their groups (median; max 19%)
- cloud_role/50: same prompt groups in every cell for a draw index: True; same permuted labels in both views of an arm: True; 95 groups per draw; different draw indices share 16% of their groups (median; max 24%)
- escalated/20: same prompt groups in every cell for a draw index: True; same permuted labels in both views of an arm: True; 40 groups per draw; different draw indices share 5% of their groups (median; max 15%)
- escalated/50: same prompt groups in every cell for a draw index: True; same permuted labels in both views of an arm: True; 98 groups per draw; different draw indices share 13% of their groups (median; max 23%)

Each false LEAK, re-run by `scripts/rerun_false_leak_draws.py` (commit 2c1f3ef1; stored verdict counts reproduced: True):

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

False LEAKs that share prompt groups:

- lan_v1 escalated n=50 draw 4 and lan_v1 cloud_role n=30 draw 17: 5 groups in common
- lan_v1 escalated n=50 draw 4 and lan_v2 escalated n=20 draw 3: 6 groups in common
- lan_v1 escalated n=50 draw 4 and lan_pad_v2 escalated n=20 draw 13: 2 groups in common
- lan_v1 escalated n=50 draw 4 and lan_padmax_v1 escalated n=20 draw 1: 2 groups in common
- lan_v1 escalated n=50 draw 4 and lan_padmax_v2 escalated n=20 draw 1: 2 groups in common
- lan_v1 escalated n=50 draw 4 and lan_padmax_v2 escalated n=20 draw 3: 6 groups in common
- lan_v1 escalated n=50 draw 4 and lan_padmax_v2 escalated n=20 draw 13: 2 groups in common
- lan_v1 escalated n=50 draw 4 and lan_padmax_v2 cloud_role n=30 draw 1: 4 groups in common
- lan_v1 escalated n=50 draw 4 and lan_padmax_v2 cloud_role n=50 draw 3: 6 groups in common
- lan_v1 escalated n=50 draw 4 and lan_padmax_v2 cloud_role n=50 draw 14: 13 groups in common
- lan_v1 cloud_role n=30 draw 17 and lan_v2 escalated n=20 draw 3: 2 groups in common
- lan_v1 cloud_role n=30 draw 17 and lan_pad_v2 escalated n=20 draw 13: 3 groups in common
- lan_v1 cloud_role n=30 draw 17 and lan_padmax_v1 escalated n=20 draw 1: 2 groups in common
- lan_v1 cloud_role n=30 draw 17 and lan_padmax_v2 escalated n=20 draw 1: 2 groups in common
- lan_v1 cloud_role n=30 draw 17 and lan_padmax_v2 escalated n=20 draw 3: 2 groups in common
- lan_v1 cloud_role n=30 draw 17 and lan_padmax_v2 escalated n=20 draw 13: 3 groups in common
- lan_v1 cloud_role n=30 draw 17 and lan_padmax_v2 cloud_role n=30 draw 1: 5 groups in common
- lan_v1 cloud_role n=30 draw 17 and lan_padmax_v2 cloud_role n=50 draw 3: 9 groups in common
- lan_v1 cloud_role n=30 draw 17 and lan_padmax_v2 cloud_role n=50 draw 14: 9 groups in common
- lan_v2 escalated n=20 draw 3 and lan_pad_v2 escalated n=20 draw 13: 3 groups in common
- lan_v2 escalated n=20 draw 3 and lan_padmax_v1 escalated n=20 draw 1: 1 groups in common
- lan_v2 escalated n=20 draw 3 and lan_padmax_v2 escalated n=20 draw 1: 1 groups in common
- lan_v2 escalated n=20 draw 3 and lan_padmax_v2 escalated n=20 draw 3: 38 groups in common (same draw index: the same subsample)
- lan_v2 escalated n=20 draw 3 and lan_padmax_v2 escalated n=20 draw 13: 3 groups in common
- lan_v2 escalated n=20 draw 3 and lan_padmax_v2 cloud_role n=50 draw 3: 4 groups in common
- lan_v2 escalated n=20 draw 3 and lan_padmax_v2 cloud_role n=50 draw 14: 2 groups in common
- lan_pad_v2 escalated n=20 draw 13 and lan_padmax_v1 escalated n=20 draw 1: 3 groups in common
- lan_pad_v2 escalated n=20 draw 13 and lan_padmax_v2 escalated n=20 draw 1: 3 groups in common
- lan_pad_v2 escalated n=20 draw 13 and lan_padmax_v2 escalated n=20 draw 3: 3 groups in common
- lan_pad_v2 escalated n=20 draw 13 and lan_padmax_v2 escalated n=20 draw 13: 40 groups in common (same draw index: the same subsample)
- lan_pad_v2 escalated n=20 draw 13 and lan_padmax_v2 cloud_role n=30 draw 1: 3 groups in common
- lan_pad_v2 escalated n=20 draw 13 and lan_padmax_v2 cloud_role n=50 draw 3: 3 groups in common
- lan_padmax_v1 escalated n=20 draw 1 and lan_padmax_v2 escalated n=20 draw 1: 40 groups in common (same draw index: the same subsample)
- lan_padmax_v1 escalated n=20 draw 1 and lan_padmax_v2 escalated n=20 draw 3: 1 groups in common
- lan_padmax_v1 escalated n=20 draw 1 and lan_padmax_v2 escalated n=20 draw 13: 3 groups in common
- lan_padmax_v1 escalated n=20 draw 1 and lan_padmax_v2 cloud_role n=30 draw 1: 2 groups in common
- lan_padmax_v1 escalated n=20 draw 1 and lan_padmax_v2 cloud_role n=50 draw 3: 2 groups in common
- lan_padmax_v1 escalated n=20 draw 1 and lan_padmax_v2 cloud_role n=50 draw 14: 3 groups in common
- lan_padmax_v2 escalated n=20 draw 1 and lan_padmax_v2 escalated n=20 draw 3: 1 groups in common
- lan_padmax_v2 escalated n=20 draw 1 and lan_padmax_v2 escalated n=20 draw 13: 3 groups in common
- lan_padmax_v2 escalated n=20 draw 1 and lan_padmax_v2 cloud_role n=30 draw 1: 2 groups in common
- lan_padmax_v2 escalated n=20 draw 1 and lan_padmax_v2 cloud_role n=50 draw 3: 2 groups in common
- lan_padmax_v2 escalated n=20 draw 1 and lan_padmax_v2 cloud_role n=50 draw 14: 3 groups in common
- lan_padmax_v2 escalated n=20 draw 3 and lan_padmax_v2 escalated n=20 draw 13: 3 groups in common
- lan_padmax_v2 escalated n=20 draw 3 and lan_padmax_v2 cloud_role n=50 draw 3: 4 groups in common
- lan_padmax_v2 escalated n=20 draw 3 and lan_padmax_v2 cloud_role n=50 draw 14: 2 groups in common
- lan_padmax_v2 escalated n=20 draw 13 and lan_padmax_v2 cloud_role n=30 draw 1: 3 groups in common
- lan_padmax_v2 escalated n=20 draw 13 and lan_padmax_v2 cloud_role n=50 draw 3: 3 groups in common
- lan_padmax_v2 cloud_role n=30 draw 1 and lan_padmax_v2 cloud_role n=50 draw 3: 10 groups in common
- lan_padmax_v2 cloud_role n=30 draw 1 and lan_padmax_v2 cloud_role n=50 draw 14: 11 groups in common
- lan_padmax_v2 cloud_role n=50 draw 3 and lan_padmax_v2 cloud_role n=50 draw 14: 16 groups in common
