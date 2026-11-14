# a2a-leakcheck on known answers (C2)

Commit `e485f117` (dirty: False), seed 42. Cells: lan_v1 (`data/raw_c2` at view v1, 1000 traces, 0 with nothing in view), lan_v2 (`data/raw_c2` at view v2, 1000 traces, 250 with nothing in view), lan_pad_v1 (`data/raw_c2_pad` at view v1, 1000 traces, 0 with nothing in view), lan_pad_v2 (`data/raw_c2_pad` at view v2, 1000 traces, 250 with nothing in view), lan_padmax_v1 (`data/raw_c2_padmax` at view v1, 1000 traces, 0 with nothing in view), lan_padmax_v2 (`data/raw_c2_padmax` at view v2, 1000 traces, 250 with nothing in view).

Full-data verdicts on the real labels, and runtime and memory, from `python -m a2a_leakcheck run --strip` in a fresh process per arm and view. Permuted labels, baselines and subsamples go through the same verdict rule (a2a_leakcheck.analyze: 5-fold StratifiedGroupKFold by prompt group, macro-F1 with a 1000-resample cluster-bootstrap 95% CI, LEAK above chance + 0.05, 99-permutation test with the rf-light null at alpha 0.05, at least 20 samples per class in 5 groups), without feature attribution, which the verdict does not use. Own connections only. Ports are never features.

Known leaks: escalated and cloud_role by construction, in every cell, and the cells (arm, view, attribute) in which k-FP or the first-request rule reads LEAK on the full data; a2a-leakcheck is not part of the reference, and recall is measured against these cells. Known non-leaks: audit_null and the permuted labels. A cell in neither set is not scored. Agreement with a2a-leakcheck's own full-data verdicts is reported apart, as coverage, and the cells only a2a-leakcheck flags are listed as beyond the baselines.

## Full data

| Method | Recall [95% CI] | False-negative rate | of which NO LEAK | False-positive rate [95% CI] | Precision [95% CI] | Known leaks | Known non-leaks |
|---|---|---|---|---|---|---|---|
| leakcheck | 1.00 [0.82, 1.00] | 0.00 | 0 | 0.00 [0.00, 0.01] | 1.00 [0.82, 1.00] | 18 | 486 |
| kfp_rf | 1.00 [0.82, 1.00] | 0.00 | 0 | 0.00 [0.00, 0.01] | 1.00 [0.82, 1.00] | 18 | 486 |
| first_request | 0.89 [0.67, 0.97] | 0.11 | 2 | 0.00 [0.00, 0.01] | 1.00 [0.81, 1.00] | 18 | 486 |

| Arm | Attribute | Classes | leakcheck: real | kfp_rf: real | first_request: real | leakcheck: permuted L/I/N | kfp_rf: permuted L/I/N | first_request: permuted L/I/N |
|---|---|---|---|---|---|---|---|---|
| lan_v1 | task_type (known leak: kfp_rf, first_request) | 4 | LEAK 0.97 [0.95, 0.98] | LEAK 0.92 [0.90, 0.94] | LEAK 0.74 [0.71, 0.76] | 0/4/16 | 0/3/17 | 0/3/17 |
| lan_v1 | escalated (known leak: by construction, kfp_rf, first_request) | 2 | LEAK 1.00 [1.00, 1.00] | LEAK 1.00 [1.00, 1.00] | LEAK 0.89 [0.86, 0.91] | 0/0/20 | 0/2/18 | 0/1/19 |
| lan_v1 | cloud_role (known leak: by construction, kfp_rf, first_request) | 2 | LEAK 1.00 [1.00, 1.00] | LEAK 1.00 [1.00, 1.00] | LEAK 1.00 [1.00, 1.00] | 0/4/16 | 0/5/15 | 0/5/15 |
| lan_v1 | audit_null (known non-leak) | 4 | NO LEAK 0.25 [0.22, 0.28] | NO LEAK 0.26 [0.23, 0.28] | NO LEAK 0.22 [0.20, 0.25] | 0/0/20 | 0/1/19 | 0/2/18 |
| lan_v2 | task_type (known leak: kfp_rf, first_request) | 4 | LEAK 0.98 [0.97, 0.98] | LEAK 0.93 [0.91, 0.94] | LEAK 0.80 [0.78, 0.82] | 0/2/18 | 0/1/19 | 0/2/18 |
| lan_v2 | escalated (known leak: by construction, kfp_rf, first_request) | 2 | LEAK 1.00 [1.00, 1.00] | LEAK 1.00 [1.00, 1.00] | LEAK 1.00 [1.00, 1.00] | 0/1/19 | 0/3/17 | 0/2/18 |
| lan_v2 | cloud_role (known leak: by construction, kfp_rf, first_request) | 2 | LEAK 1.00 [1.00, 1.00] | LEAK 1.00 [1.00, 1.00] | LEAK 1.00 [1.00, 1.00] | 0/6/14 | 0/3/17 | 0/5/15 |
| lan_v2 | audit_null (known non-leak) | 4 | NO LEAK 0.24 [0.21, 0.26] | NO LEAK 0.25 [0.22, 0.28] | NO LEAK 0.23 [0.20, 0.25] | 0/0/20 | 0/0/20 | 0/1/19 |
| lan_pad_v1 | task_type (known leak: kfp_rf, first_request) | 4 | LEAK 0.95 [0.94, 0.96] | LEAK 0.92 [0.91, 0.94] | LEAK 0.75 [0.73, 0.77] | 0/3/17 | 0/0/20 | 0/4/16 |
| lan_pad_v1 | escalated (known leak: by construction, kfp_rf, first_request) | 2 | LEAK 1.00 [1.00, 1.00] | LEAK 1.00 [1.00, 1.00] | LEAK 1.00 [1.00, 1.00] | 0/0/20 | 0/0/20 | 0/1/19 |
| lan_pad_v1 | cloud_role (known leak: by construction, kfp_rf, first_request) | 2 | LEAK 1.00 [1.00, 1.00] | LEAK 1.00 [0.99, 1.00] | LEAK 0.98 [0.97, 0.99] | 0/5/15 | 0/4/16 | 0/3/17 |
| lan_pad_v1 | audit_null (known non-leak) | 4 | INCONCLUSIVE 0.25 [0.22, 0.28] | NO LEAK 0.26 [0.24, 0.29] | INCONCLUSIVE 0.28 [0.25, 0.31] | 0/3/17 | 0/0/20 | 0/2/18 |
| lan_pad_v2 | task_type (known leak: kfp_rf, first_request) | 4 | LEAK 0.95 [0.94, 0.96] | LEAK 0.93 [0.91, 0.94] | LEAK 0.75 [0.73, 0.77] | 0/3/17 | 0/1/19 | 0/1/19 |
| lan_pad_v2 | escalated (known leak: by construction, kfp_rf, first_request) | 2 | LEAK 1.00 [1.00, 1.00] | LEAK 1.00 [1.00, 1.00] | LEAK 1.00 [1.00, 1.00] | 0/2/18 | 0/1/19 | 0/0/20 |
| lan_pad_v2 | cloud_role (known leak: by construction, kfp_rf, first_request) | 2 | LEAK 1.00 [1.00, 1.00] | LEAK 1.00 [0.99, 1.00] | LEAK 0.98 [0.97, 0.99] | 0/5/15 | 0/5/15 | 0/3/17 |
| lan_pad_v2 | audit_null (known non-leak) | 4 | NO LEAK 0.25 [0.23, 0.28] | NO LEAK 0.26 [0.23, 0.28] | INCONCLUSIVE 0.28 [0.25, 0.31] | 0/3/17 | 0/1/19 | 0/1/19 |
| lan_padmax_v1 | task_type (known leak: kfp_rf, first_request) | 4 | LEAK 0.90 [0.88, 0.92] | LEAK 0.90 [0.88, 0.92] | LEAK 0.38 [0.36, 0.38] | 0/1/19 | 0/3/17 | 0/3/17 |
| lan_padmax_v1 | escalated (known leak: by construction, kfp_rf, first_request) | 2 | LEAK 1.00 [1.00, 1.00] | LEAK 1.00 [1.00, 1.00] | LEAK 1.00 [1.00, 1.00] | 0/2/18 | 0/3/17 | 0/2/18 |
| lan_padmax_v1 | cloud_role (known leak: by construction, kfp_rf) | 2 | LEAK 1.00 [0.99, 1.00] | LEAK 1.00 [0.99, 1.00] | NO LEAK 0.40 [0.39, 0.41] | 0/7/13 | 0/4/16 | 0/0/20 |
| lan_padmax_v1 | audit_null (known non-leak) | 4 | INCONCLUSIVE 0.28 [0.25, 0.30] | INCONCLUSIVE 0.29 [0.26, 0.31] | NO LEAK 0.22 [0.19, 0.24] | 0/4/16 | 0/1/19 | 0/1/19 |
| lan_padmax_v2 | task_type (known leak: kfp_rf, first_request) | 4 | LEAK 0.89 [0.87, 0.91] | LEAK 0.90 [0.88, 0.92] | LEAK 0.38 [0.36, 0.38] | 0/1/19 | 0/0/20 | 0/1/19 |
| lan_padmax_v2 | escalated (known leak: by construction, kfp_rf, first_request) | 2 | LEAK 1.00 [1.00, 1.00] | LEAK 1.00 [1.00, 1.00] | LEAK 1.00 [1.00, 1.00] | 0/5/15 | 0/3/17 | 0/4/16 |
| lan_padmax_v2 | cloud_role (known leak: by construction, kfp_rf) | 2 | LEAK 1.00 [0.99, 1.00] | LEAK 1.00 [0.99, 1.00] | NO LEAK 0.40 [0.39, 0.41] | 0/4/16 | 0/6/14 | 0/0/20 |
| lan_padmax_v2 | audit_null (known non-leak) | 4 | NO LEAK 0.26 [0.23, 0.29] | NO LEAK 0.25 [0.23, 0.28] | NO LEAK 0.21 [0.19, 0.24] | 0/0/20 | 0/2/18 | 0/0/20 |

## Sample size (a2a-leakcheck)

20 draws per size, attribute and arm, by whole prompt groups; each draw also scored with its labels permuted. Recall against the same known leaks as above; agreement with a2a-leakcheck's own full-data verdicts is under Coverage.

| Samples per class | Recall [95% CI] | INCONCLUSIVE on leaks | NO LEAK on leaks | False-positive rate [95% CI] |
|---|---|---|---|---|
| 5 | 0.00 [0.00, 0.01] | 360 of 360 | 0 | 0.00 [0.00, 0.01] |
| 10 | 0.00 [0.00, 0.01] | 360 of 360 | 0 | 0.00 [0.00, 0.01] |
| 20 | 1.00 [0.99, 1.00] | 0 of 360 | 0 | 0.01 [0.00, 0.02] |
| 30 | 1.00 [0.99, 1.00] | 0 of 360 | 0 | 0.00 [0.00, 0.01] |
| 50 | 1.00 [0.99, 1.00] | 0 of 360 | 0 | 0.01 [0.00, 0.01] |

| Arm | Attribute | n=5 L/I/N (agree) | n=10 L/I/N (agree) | n=20 L/I/N (agree) | n=30 L/I/N (agree) | n=50 L/I/N (agree) |
|---|---|---|---|---|---|---|
| lan_v1 | task_type | 0/20/0 (0.00) | 0/20/0 (0.00) | 20/0/0 (1.00) | 20/0/0 (1.00) | 20/0/0 (1.00) |
| lan_v1 | escalated | 0/20/0 (0.00) | 0/20/0 (0.00) | 20/0/0 (1.00) | 20/0/0 (1.00) | 20/0/0 (1.00) |
| lan_v1 | cloud_role | 0/20/0 (0.00) | 0/20/0 (0.00) | 20/0/0 (1.00) | 20/0/0 (1.00) | 20/0/0 (1.00) |
| lan_v1 | audit_null | 0/20/0 (0.00) | 0/20/0 (0.00) | 0/14/6 (0.30) | 0/10/10 (0.50) | 0/12/8 (0.40) |
| lan_v2 | task_type | 0/20/0 (0.00) | 0/20/0 (0.00) | 20/0/0 (1.00) | 20/0/0 (1.00) | 20/0/0 (1.00) |
| lan_v2 | escalated | 0/20/0 (0.00) | 0/20/0 (0.00) | 20/0/0 (1.00) | 20/0/0 (1.00) | 20/0/0 (1.00) |
| lan_v2 | cloud_role | 0/20/0 (0.00) | 0/20/0 (0.00) | 20/0/0 (1.00) | 20/0/0 (1.00) | 20/0/0 (1.00) |
| lan_v2 | audit_null | 0/20/0 (0.00) | 0/20/0 (0.00) | 0/15/5 (0.25) | 0/9/11 (0.55) | 0/9/11 (0.55) |
| lan_pad_v1 | task_type | 0/20/0 (0.00) | 0/20/0 (0.00) | 20/0/0 (1.00) | 20/0/0 (1.00) | 20/0/0 (1.00) |
| lan_pad_v1 | escalated | 0/20/0 (0.00) | 0/20/0 (0.00) | 20/0/0 (1.00) | 20/0/0 (1.00) | 20/0/0 (1.00) |
| lan_pad_v1 | cloud_role | 0/20/0 (0.00) | 0/20/0 (0.00) | 20/0/0 (1.00) | 20/0/0 (1.00) | 20/0/0 (1.00) |
| lan_pad_v1 | audit_null | 0/20/0 (1.00) | 0/20/0 (1.00) | 0/16/4 (0.80) | 0/16/4 (0.80) | 0/12/8 (0.60) |
| lan_pad_v2 | task_type | 0/20/0 (0.00) | 0/20/0 (0.00) | 20/0/0 (1.00) | 20/0/0 (1.00) | 20/0/0 (1.00) |
| lan_pad_v2 | escalated | 0/20/0 (0.00) | 0/20/0 (0.00) | 20/0/0 (1.00) | 20/0/0 (1.00) | 20/0/0 (1.00) |
| lan_pad_v2 | cloud_role | 0/20/0 (0.00) | 0/20/0 (0.00) | 20/0/0 (1.00) | 20/0/0 (1.00) | 20/0/0 (1.00) |
| lan_pad_v2 | audit_null | 0/20/0 (0.00) | 0/20/0 (0.00) | 0/13/7 (0.35) | 0/12/8 (0.40) | 0/11/9 (0.45) |
| lan_padmax_v1 | task_type | 0/20/0 (0.00) | 0/20/0 (0.00) | 20/0/0 (1.00) | 20/0/0 (1.00) | 20/0/0 (1.00) |
| lan_padmax_v1 | escalated | 0/20/0 (0.00) | 0/20/0 (0.00) | 20/0/0 (1.00) | 20/0/0 (1.00) | 20/0/0 (1.00) |
| lan_padmax_v1 | cloud_role | 0/20/0 (0.00) | 0/20/0 (0.00) | 20/0/0 (1.00) | 20/0/0 (1.00) | 20/0/0 (1.00) |
| lan_padmax_v1 | audit_null | 0/20/0 (1.00) | 0/20/0 (1.00) | 0/16/4 (0.80) | 0/12/8 (0.60) | 0/15/5 (0.75) |
| lan_padmax_v2 | task_type | 0/20/0 (0.00) | 0/20/0 (0.00) | 20/0/0 (1.00) | 20/0/0 (1.00) | 20/0/0 (1.00) |
| lan_padmax_v2 | escalated | 0/20/0 (0.00) | 0/20/0 (0.00) | 20/0/0 (1.00) | 20/0/0 (1.00) | 20/0/0 (1.00) |
| lan_padmax_v2 | cloud_role | 0/20/0 (0.00) | 0/20/0 (0.00) | 20/0/0 (1.00) | 20/0/0 (1.00) | 20/0/0 (1.00) |
| lan_padmax_v2 | audit_null | 0/20/0 (0.00) | 0/20/0 (0.00) | 0/16/4 (0.20) | 0/11/9 (0.45) | 0/8/12 (0.60) |

## Coverage (a2a-leakcheck's subsamples against its own full-data verdicts)

Share of n-sample draws (real labels) whose verdict is the one a2a-leakcheck reaches on all of that cell's data, over every cell and attribute, and split by that full-data verdict. This is agreement with the tool itself, not recall.

| Samples per class | All cells [95% CI] | Its LEAK cells [95% CI] | Its other cells [95% CI] | Draws |
|---|---|---|---|---|
| 5 | 0.08 [0.06, 0.11] | 0.00 [0.00, 0.01] | 0.33 [0.26, 0.42] | 480 |
| 10 | 0.08 [0.06, 0.11] | 0.00 [0.00, 0.01] | 0.33 [0.26, 0.42] | 480 |
| 20 | 0.86 [0.83, 0.89] | 1.00 [0.99, 1.00] | 0.45 [0.36, 0.54] | 480 |
| 30 | 0.89 [0.86, 0.91] | 1.00 [0.99, 1.00] | 0.55 [0.46, 0.64] | 480 |
| 50 | 0.89 [0.86, 0.91] | 1.00 [0.99, 1.00] | 0.56 [0.47, 0.64] | 480 |

## Beyond the baselines

Cells in which a2a-leakcheck reads LEAK on the full data and neither k-FP nor the first-request rule does:

- none

## Carried by (a2a-leakcheck's attribution, every cell with a LEAK)

Each feature family's features alone (macro-F1 [95% CI]); the top family scores highest alone, and "matches all" means its gap to all features has a CI that reaches 0. Single request size: the first request's size alone.

| Cell | Attribute | a2a-leakcheck | k-FP | first request | Carried by | sizes | timing | counts_direction | single request size |
|---|---|---|---|---|---|---|---|---|---|
| lan_v1 | task_type | LEAK | LEAK | LEAK | sizes (matches all) | 0.96 [0.95, 0.97] | 0.90 [0.88, 0.92] | 0.73 [0.71, 0.76] | 0.74 [0.71, 0.76] |
| lan_v1 | escalated | LEAK | LEAK | LEAK | sizes (matches all) | 1.00 [1.00, 1.00] | 1.00 [1.00, 1.00] | 1.00 [1.00, 1.00] | 0.89 [0.86, 0.91] |
| lan_v1 | cloud_role | LEAK | LEAK | LEAK | timing (matches all) | 1.00 [0.99, 1.00] | 1.00 [1.00, 1.00] | 0.90 [0.87, 0.92] | 1.00 [1.00, 1.00] |
| lan_v2 | task_type | LEAK | LEAK | LEAK | sizes (matches all) | 0.97 [0.96, 0.98] | 0.88 [0.86, 0.90] | 0.75 [0.73, 0.77] | 0.80 [0.78, 0.82] |
| lan_v2 | escalated | LEAK | LEAK | LEAK | sizes (matches all) | 1.00 [1.00, 1.00] | 1.00 [1.00, 1.00] | 1.00 [1.00, 1.00] | 1.00 [1.00, 1.00] |
| lan_v2 | cloud_role | LEAK | LEAK | LEAK | sizes (matches all) | 1.00 [1.00, 1.00] | 1.00 [1.00, 1.00] | 0.88 [0.86, 0.91] | 1.00 [1.00, 1.00] |
| lan_pad_v1 | task_type | LEAK | LEAK | LEAK | sizes (matches all) | 0.95 [0.94, 0.96] | 0.90 [0.89, 0.92] | 0.73 [0.70, 0.75] | 0.75 [0.73, 0.77] |
| lan_pad_v1 | escalated | LEAK | LEAK | LEAK | sizes (matches all) | 1.00 [1.00, 1.00] | 1.00 [1.00, 1.00] | 1.00 [1.00, 1.00] | 1.00 [1.00, 1.00] |
| lan_pad_v1 | cloud_role | LEAK | LEAK | LEAK | timing (matches all) | 0.99 [0.98, 1.00] | 1.00 [1.00, 1.00] | 0.89 [0.87, 0.92] | 0.98 [0.97, 0.99] |
| lan_pad_v2 | task_type | LEAK | LEAK | LEAK | sizes (matches all) | 0.95 [0.93, 0.96] | 0.90 [0.88, 0.92] | 0.70 [0.68, 0.73] | 0.75 [0.73, 0.77] |
| lan_pad_v2 | escalated | LEAK | LEAK | LEAK | sizes (matches all) | 1.00 [1.00, 1.00] | 1.00 [1.00, 1.00] | 1.00 [1.00, 1.00] | 1.00 [1.00, 1.00] |
| lan_pad_v2 | cloud_role | LEAK | LEAK | LEAK | timing (matches all) | 0.99 [0.99, 1.00] | 1.00 [1.00, 1.00] | 0.88 [0.85, 0.91] | 0.98 [0.97, 0.99] |
| lan_padmax_v1 | task_type | LEAK | LEAK | LEAK | timing (matches all) | 0.88 [0.86, 0.90] | 0.88 [0.87, 0.90] | 0.70 [0.67, 0.72] | 0.38 [0.36, 0.38] |
| lan_padmax_v1 | escalated | LEAK | LEAK | LEAK | sizes (matches all) | 1.00 [1.00, 1.00] | 1.00 [0.99, 1.00] | 1.00 [1.00, 1.00] | 1.00 [1.00, 1.00] |
| lan_padmax_v1 | cloud_role | LEAK | LEAK | NO LEAK | sizes (matches all) | 1.00 [0.99, 1.00] | 1.00 [0.99, 1.00] | 0.82 [0.79, 0.85] | 0.40 [0.39, 0.41] |
| lan_padmax_v2 | task_type | LEAK | LEAK | LEAK | timing (matches all) | 0.87 [0.86, 0.89] | 0.89 [0.87, 0.91] | 0.71 [0.69, 0.74] | 0.38 [0.36, 0.38] |
| lan_padmax_v2 | escalated | LEAK | LEAK | LEAK | sizes (matches all) | 1.00 [1.00, 1.00] | 1.00 [1.00, 1.00] | 1.00 [1.00, 1.00] | 1.00 [1.00, 1.00] |
| lan_padmax_v2 | cloud_role | LEAK | LEAK | NO LEAK | sizes (matches all) | 1.00 [0.99, 1.00] | 0.99 [0.99, 1.00] | 0.81 [0.78, 0.84] | 0.40 [0.39, 0.41] |

## task_type: sensor_analysis vs fault_diagnosis

Binary macro-F1 [95% CI] through the same verdict rule, with the tool's GBT on all 195 trace features and on the 30 timing features alone (features/families.py); p from the permutation test.

| Cell | sensor_analysis / fault_diagnosis | All features | p | Timing alone | p |
|---|---|---|---|---|---|
| lan_v1 | 250 / 250 | LEAK 0.93 [0.91, 0.95] | 0.01 | LEAK 0.78 [0.75, 0.82] | 0.01 |
| lan_v2 | 250 / 250 | LEAK 0.94 [0.92, 0.96] | 0.01 | LEAK 0.80 [0.76, 0.83] | 0.01 |
| lan_pad_v1 | 250 / 250 | LEAK 0.91 [0.89, 0.94] | 0.01 | LEAK 0.78 [0.75, 0.82] | 0.01 |
| lan_pad_v2 | 250 / 250 | LEAK 0.92 [0.89, 0.94] | 0.01 | LEAK 0.79 [0.76, 0.83] | 0.01 |
| lan_padmax_v1 | 250 / 250 | LEAK 0.77 [0.74, 0.81] | 0.01 | LEAK 0.75 [0.71, 0.79] | 0.01 |
| lan_padmax_v2 | 250 / 250 | LEAK 0.79 [0.75, 0.82] | 0.01 | LEAK 0.78 [0.75, 0.82] | 0.01 |

## Input size from the first request

Traces with escalated=yes; input = the prompt as JSON-encoded in the request. Out-of-fold estimates (5-fold StratifiedGroupKFold by prompt group over task_type): constant overhead, linear fit, no traffic (the training folds' median input), and per-class overhead (reference only: it knows the class). Median absolute error in bytes (share within 200 B).

| Cell | Traces | First request to | Distinct first-request sizes | constant | linear | no_traffic | per_class_constant |
|---|---|---|---|---|---|---|---|
| lan_v1 | 750 | diagnostics 500, knowledge 250 | 539 | 0 (1.00) | 0 (1.00) | 1794 (0.06) | 0 (1.00) |
| lan_v2 | 750 | diagnostics 500, knowledge 250 | 539 | 0 (1.00) | 0 (1.00) | 1794 (0.06) | 0 (1.00) |
| lan_pad_v1 | 750 | diagnostics 500, knowledge 250 | 4 | 329 (0.44) | 413 (0.15) | 1794 (0.06) | 496 (0.38) |
| lan_pad_v2 | 750 | diagnostics 500, knowledge 250 | 4 | 329 (0.44) | 413 (0.15) | 1794 (0.06) | 496 (0.38) |
| lan_padmax_v1 | 750 | diagnostics 500, knowledge 250 | 2 | 1794 (0.06) | 1983 (0.07) | 1794 (0.06) | 410 (0.42) |
| lan_padmax_v2 | 750 | diagnostics 500, knowledge 250 | 2 | 1794 (0.06) | 1983 (0.07) | 1794 (0.06) | 410 (0.42) |

The views give identical estimates on lan, lan_pad, lan_padmax: the first request of every such trace is the same at each view.

Per class, median absolute error in bytes:

| Cell | Class | Input median | First request median | constant | linear | no_traffic | per_class_constant |
|---|---|---|---|---|---|---|---|
| lan_v1 | fault_diagnosis | 3675 | 4195 | 0 | 0 | 1264 | 0 |
| lan_v1 | procedure_lookup | 81 | 600 | 1 | 0 | 2325 | 0 |
| lan_v1 | sensor_analysis | 2866 | 3386 | 0 | 0 | 1080 | 0 |
| lan_v2 | fault_diagnosis | 3675 | 4195 | 0 | 0 | 1264 | 0 |
| lan_v2 | procedure_lookup | 81 | 600 | 1 | 0 | 2325 | 0 |
| lan_v2 | sensor_analysis | 2866 | 3386 | 0 | 0 | 1080 | 0 |
| lan_pad_v1 | fault_diagnosis | 3675 | 4392 | 729 | 648 | 1264 | 1246 |
| lan_pad_v1 | procedure_lookup | 81 | 1320 | 16 | 404 | 2325 | 12 |
| lan_pad_v1 | sensor_analysis | 2866 | 4392 | 635 | 415 | 1080 | 786 |
| lan_pad_v2 | fault_diagnosis | 3675 | 4392 | 729 | 648 | 1264 | 1246 |
| lan_pad_v2 | procedure_lookup | 81 | 1320 | 16 | 404 | 2325 | 12 |
| lan_pad_v2 | sensor_analysis | 2866 | 4392 | 635 | 415 | 1080 | 786 |
| lan_padmax_v1 | fault_diagnosis | 3675 | 8488 | 1264 | 1479 | 1264 | 626 |
| lan_padmax_v1 | procedure_lookup | 81 | 8488 | 2325 | 2124 | 2325 | 12 |
| lan_padmax_v1 | sensor_analysis | 2866 | 8488 | 1080 | 1081 | 1080 | 1060 |
| lan_padmax_v2 | fault_diagnosis | 3675 | 8488 | 1264 | 1479 | 1264 | 626 |
| lan_padmax_v2 | procedure_lookup | 81 | 8488 | 2325 | 2124 | 2325 | 12 |
| lan_padmax_v2 | sensor_analysis | 2866 | 8488 | 1080 | 1081 | 1080 | 1060 |

## Runtime and memory (a2a-leakcheck run, full data)

| Arm | Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|---|
| lan_v1 | collection | 0.5 | 171 | — |
| lan_v1 | extraction | 22.3 | 248 | — |
| lan_v1 | analysis:task_type | 49.9 | 297 | 292 |
| lan_v1 | analysis:escalated | 38.7 | 301 | 292 |
| lan_v1 | analysis:cloud_role | 35.7 | 309 | 292 |
| lan_v1 | analysis:audit_null | 61.6 | 310 | 326 |
| lan_v1 | total | 209.7 | 310 | 326 |
| lan_v2 | collection | 0.6 | 169 | — |
| lan_v2 | extraction | 22.6 | 244 | — |
| lan_v2 | analysis:task_type | 44.7 | 291 | 289 |
| lan_v2 | analysis:escalated | 35.6 | 297 | 289 |
| lan_v2 | analysis:cloud_role | 33.4 | 306 | 289 |
| lan_v2 | analysis:audit_null | 48.6 | 307 | 314 |
| lan_v2 | total | 186.5 | 307 | 314 |
| lan_pad_v1 | collection | 0.6 | 171 | — |
| lan_pad_v1 | extraction | 23.3 | 246 | — |
| lan_pad_v1 | analysis:task_type | 50.2 | 291 | 293 |
| lan_pad_v1 | analysis:escalated | 38.9 | 299 | 293 |
| lan_pad_v1 | analysis:cloud_role | 36.0 | 301 | 293 |
| lan_pad_v1 | analysis:audit_null | 60.9 | 302 | 329 |
| lan_pad_v1 | total | 211.0 | 302 | 329 |
| lan_pad_v2 | collection | 0.6 | 169 | — |
| lan_pad_v2 | extraction | 22.4 | 246 | — |
| lan_pad_v2 | analysis:task_type | 43.0 | 290 | 306 |
| lan_pad_v2 | analysis:escalated | 34.2 | 297 | 306 |
| lan_pad_v2 | analysis:cloud_role | 32.3 | 305 | 306 |
| lan_pad_v2 | analysis:audit_null | 45.1 | 310 | 317 |
| lan_pad_v2 | total | 178.7 | 310 | 317 |
| lan_padmax_v1 | collection | 0.6 | 169 | — |
| lan_padmax_v1 | extraction | 23.2 | 244 | — |
| lan_padmax_v1 | analysis:task_type | 48.3 | 292 | 317 |
| lan_padmax_v1 | analysis:escalated | 37.9 | 300 | 317 |
| lan_padmax_v1 | analysis:cloud_role | 35.0 | 309 | 317 |
| lan_padmax_v1 | analysis:audit_null | 59.1 | 310 | 334 |
| lan_padmax_v1 | total | 205.2 | 310 | 334 |
| lan_padmax_v2 | collection | 0.6 | 168 | — |
| lan_padmax_v2 | extraction | 22.6 | 244 | — |
| lan_padmax_v2 | analysis:task_type | 43.4 | 287 | 316 |
| lan_padmax_v2 | analysis:escalated | 34.3 | 294 | 316 |
| lan_padmax_v2 | analysis:cloud_role | 32.1 | 302 | 316 |
| lan_padmax_v2 | analysis:audit_null | 44.6 | 306 | 319 |
| lan_padmax_v2 | total | 178.7 | 306 | 319 |

14 worker processes; macOS-27.0.1-arm64-arm-64bit. This evaluation ran in 3 parallel parts; the longest took 945 min.

The tool's verdicts, runtime and memory come from its reports, each run alone beforehand (--tool-reports): `data/results/leakcheck/c2_lan_v1/report.json` (commit `eb8fbbfb`), `data/results/leakcheck/c2_lan_v2/report.json` (commit `eb8fbbfb`), `data/results/leakcheck/c2_lan_pad_v1/report.json` (commit `eb8fbbfb`), `data/results/leakcheck/c2_lan_pad_v2/report.json` (commit `eb8fbbfb`), `data/results/leakcheck/c2_lan_padmax_v1/report.json` (commit `eb8fbbfb`), `data/results/leakcheck/c2_lan_padmax_v2/report.json` (commit `eb8fbbfb`).
