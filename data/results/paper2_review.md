# Paper 2 review checks (C2)

Commit `0700d4bc` (clean: True); seed 42. Inputs: `data/results/paper2_tool_eval_c2.json` (commit `e485f117`) and the six tool reports `data/results/leakcheck/c2_<cell>` (commit `2c1f3ef1`); captures `data/raw_c2`, `data/raw_c2_pad`, `data/raw_c2_padmax`. Features as in the evaluation (own connections, each payload byte once). Verdict rule throughout: 5-fold StratifiedGroupKFold by prompt group, macro-F1 with a 1000-resample cluster-bootstrap 95% CI, LEAK when the lower bound exceeds 1/k + 0.05, and a 99-permutation test (rf-light) at 0.05.

## 2. Accounting: every known leak and known non-leak

Verdict counts are LEAK / INCONCLUSIVE / NO LEAK.

| Set | Cells or draws | a2a-leakcheck | k-FP | first request |
|---|---|---|---|---|
| Known leaks by construction (escalated, cloud_role) | 12 | 12 / 0 / 0 | 12 / 0 / 0 | 10 / 0 / 2 |
| Known leaks only because a baseline reads LEAK (task_type) | 6 | 6 / 0 / 0 | 6 / 0 / 0 | 6 / 0 / 0 |
| **All known leaks** | 18 | 18 / 0 / 0 | 18 / 0 / 0 | 16 / 0 / 2 |
| Full-size permuted draws (6 cells × 4 attributes × 20) | 480 | 0 / 65 / 415 | 0 / 52 / 428 | 0 / 47 / 433 |
| audit_null, real labels (6 cells) | 6 | 0 / 2 / 4 | 0 / 1 / 5 | 0 / 2 / 4 |
| **All known non-leaks** | 486 | 0 / 67 / 419 | 0 / 53 / 433 | 0 / 49 / 437 |

The task_type cells are known leaks because k-FP and the first-request rule read LEAK on them, so those two methods' recall there is true by definition; only the 12 cells by construction score all three methods without that circularity.

Permuted draws per attribute (6 cells × 20):

| Attribute | a2a-leakcheck | k-FP | first request |
|---|---|---|---|
| task_type | 0 / 14 / 106 | 0 / 8 / 112 | 0 / 14 / 106 |
| escalated | 0 / 10 / 110 | 0 / 12 / 108 | 0 / 10 / 110 |
| cloud_role | 0 / 31 / 89 | 0 / 27 / 93 | 0 / 16 / 104 |
| audit_null | 0 / 10 / 110 | 0 / 5 / 115 | 0 / 7 / 113 |

Each known leak:

| Cell | Attribute | Why it is a known leak | a2a-leakcheck | k-FP | first request |
|---|---|---|---|---|---|
| lan_v1 | task_type | kfp_rf, first_request | LEAK | LEAK | LEAK |
| lan_v1 | escalated | by construction, kfp_rf, first_request | LEAK | LEAK | LEAK |
| lan_v1 | cloud_role | by construction, kfp_rf, first_request | LEAK | LEAK | LEAK |
| lan_v2 | task_type | kfp_rf, first_request | LEAK | LEAK | LEAK |
| lan_v2 | escalated | by construction, kfp_rf, first_request | LEAK | LEAK | LEAK |
| lan_v2 | cloud_role | by construction, kfp_rf, first_request | LEAK | LEAK | LEAK |
| lan_pad_v1 | task_type | kfp_rf, first_request | LEAK | LEAK | LEAK |
| lan_pad_v1 | escalated | by construction, kfp_rf, first_request | LEAK | LEAK | LEAK |
| lan_pad_v1 | cloud_role | by construction, kfp_rf, first_request | LEAK | LEAK | LEAK |
| lan_pad_v2 | task_type | kfp_rf, first_request | LEAK | LEAK | LEAK |
| lan_pad_v2 | escalated | by construction, kfp_rf, first_request | LEAK | LEAK | LEAK |
| lan_pad_v2 | cloud_role | by construction, kfp_rf, first_request | LEAK | LEAK | LEAK |
| lan_padmax_v1 | task_type | kfp_rf, first_request | LEAK | LEAK | LEAK |
| lan_padmax_v1 | escalated | by construction, kfp_rf, first_request | LEAK | LEAK | LEAK |
| lan_padmax_v1 | cloud_role | by construction, kfp_rf | LEAK | LEAK | NO LEAK |
| lan_padmax_v2 | task_type | kfp_rf, first_request | LEAK | LEAK | LEAK |
| lan_padmax_v2 | escalated | by construction, kfp_rf, first_request | LEAK | LEAK | LEAK |
| lan_padmax_v2 | cloud_role | by construction, kfp_rf | LEAK | LEAK | NO LEAK |

**Release-blocking rate.** A permuted audit is one cell and one draw index k: the k-th full-size permuted draw of each of the four attributes, on the same captures (each attribute's labels permuted independently, with its own random stream). It blocks a release if any attribute reads LEAK.

| Method | Audits | Any LEAK [Wilson 95% CI] | No LEAK, some INCONCLUSIVE [95% CI] | All NO LEAK |
|---|---|---|---|---|
| a2a-leakcheck | 120 | 0 (0.000 [0.000, 0.031]) | 56 (0.467 [0.380, 0.556]) | 64 |
| k-FP | 120 | 0 (0.000 [0.000, 0.031]) | 48 (0.400 [0.317, 0.489]) | 72 |
| first request | 120 | 0 (0.000 [0.000, 0.031]) | 42 (0.350 [0.271, 0.439]) | 78 |

**Reuse between draws and the permutation tests inside them.** For each of the 24 (cell, attribute) pairs, the 20 permuted draws, the real labels, and the 99 shuffles inside each of those 21 tests: 50400 distinct labellings of 50400; a draw equal to a shuffle in any test: 0; a draw equal to the real labels: 0. Every test in a cell uses the same 99 index permutations (generator seeded 42) applied to its own labels, and the same 1,000 bootstrap resamples, so the draws are not fully independent of each other, but no labelling is reused.

## 3. task_type on the escalated tasks only

sensor_analysis, fault_diagnosis and procedure_lookup (alert_triage, which never leaves the building and is answered on the edge, left out): three classes, chance 1/3, so a LEAK needs the CI's lower bound above 0.383. Verdict, macro-F1 [95% CI] and permutation p.

| Cell | Traces | All 195 features | Timing alone (30) | Timing gap: all − timing [95% CI] | Sizes alone | Sizes gap | Top family |
|---|---|---|---|---|---|---|---|
| lan_v1 | 750 | LEAK 0.959 [0.945, 0.972], p 0.01 | LEAK 0.865 [0.842, 0.888], p 0.01 | +0.093 [+0.071, +0.116] | 0.959 [0.945, 0.973] | +0.000 [-0.012, +0.013] | sizes |
| lan_v2 | 750 | LEAK 0.963 [0.948, 0.975], p 0.01 | LEAK 0.865 [0.842, 0.888], p 0.01 | +0.097 [+0.074, +0.121] | 0.969 [0.957, 0.981] | -0.007 [-0.016, +0.003] | sizes |
| lan_pad_v1 | 750 | LEAK 0.933 [0.916, 0.952], p 0.01 | LEAK 0.851 [0.825, 0.875], p 0.01 | +0.083 [+0.059, +0.106] | 0.929 [0.910, 0.947] | +0.004 [-0.009, +0.017] | sizes |
| lan_pad_v2 | 750 | LEAK 0.947 [0.930, 0.962], p 0.01 | LEAK 0.852 [0.827, 0.876], p 0.01 | +0.095 [+0.070, +0.119] | 0.940 [0.923, 0.955] | +0.007 [-0.002, +0.016] | sizes |
| lan_padmax_v1 | 750 | LEAK 0.852 [0.827, 0.876], p 0.01 | LEAK 0.834 [0.808, 0.858], p 0.01 | +0.018 [-0.005, +0.040] | 0.848 [0.822, 0.874] | +0.004 [-0.016, +0.025] | sizes |
| lan_padmax_v2 | 750 | LEAK 0.842 [0.814, 0.868], p 0.01 | LEAK 0.852 [0.830, 0.875], p 0.01 | -0.010 [-0.035, +0.014] | 0.832 [0.806, 0.859] | +0.010 [-0.007, +0.027] | timing |

## 4. Input-size estimator

**Population.** The escalated traces of each arm (sidecar `escalated=yes`, 750: 250 per task type), the only tasks whose prompt crosses a captured link, to a cloud agent. **Truth:** the prompt as JSON-encoded in the request, without its quotes (`prompt_json_bytes`). **Observation:** the first request's size as the leakcheck measures it (`first_request_seq`, TCP sequence space, after the TLS handshake). **Error:** |estimate − truth| in bytes, out of fold: 5-fold StratifiedGroupKFold by prompt group over task_type, seed 42. **Constant overhead:** on the training folds c = median(first request − input); estimate = first request − c. **No traffic:** on the training folds the median input; every test trace gets that number. Linear (least squares of input on first request) and per-class constant (c per task type, applied with the true type, reference only) as stored. The cloud agents are in both views, so v1 and v2 see the same first request; results identical at v1 and v2: lan True, lan_pad True, lan_padmax True. Each arm is shown once.

**lan** (750 traces, 736 prompt groups; first request to diagnostics 500, knowledge 250; 539 distinct first-request sizes; stored errors reproduced: True; c per fold 520.0, 520.0, 520.0, 520.0, 520.0 B; no-traffic estimate per fold 2420.0, 2366.5, 2435.0, 2427.5, 2383.0 B)

| | Constant: median / P90 | No traffic: median / P90 | Constant − no traffic, median abs error [95% CI] | Mean abs error [95% CI] |
|---|---|---|---|---|
| all | 0 / 1 | 1794 / 2361 | -1794.5 [-1943.0, -1628.5] | -1582.2 [-1643.1, -1525.3] |
| fault_diagnosis | 0 / 0 | 1264 / 2413 | -1263.5 [-1396.0, -1111.5] | -1280.6 [-1374.5, -1187.6] |
| procedure_lookup | 1 / 1 | 2325 / 2362 | -2324.0 [-2335.2, -2320.0] | -2323.5 [-2327.5, -2319.7] |
| sensor_analysis | 0 / 0 | 1080 / 2238 | -1080.0 [-1257.0, -937.0] | -1142.6 [-1243.7, -1049.9] |

**lan_pad** (750 traces, 736 prompt groups; first request to diagnostics 500, knowledge 250; 4 distinct first-request sizes; stored errors reproduced: True; c per fold 1256.0, 1255.0, 1254.5, 1256.0, 1254.0 B; no-traffic estimate per fold 2420.0, 2366.5, 2435.0, 2427.5, 2383.0 B)

| | Constant: median / P90 | No traffic: median / P90 | Constant − no traffic, median abs error [95% CI] | Mean abs error [95% CI] |
|---|---|---|---|---|
| all | 329 / 2832 | 1794 / 2361 | -1465.5 [-1664.0, -1273.0] | -754.3 [-851.9, -653.2] |
| fault_diagnosis | 729 / 3165 | 1264 / 2413 | -534.5 [-618.0, -349.0] | +122.6 [+11.9, +235.7] |
| procedure_lookup | 16 / 40 | 2325 / 2362 | -2309.2 [-2321.0, -2304.0] | -2305.4 [-2310.6, -2300.5] |
| sensor_analysis | 635 / 2831 | 1080 / 2238 | -445.2 [-608.0, -267.2] | -80.2 [-179.0, +23.7] |

**lan_padmax** (750 traces, 736 prompt groups; first request to diagnostics 500, knowledge 250; 2 distinct first-request sizes; stored errors reproduced: True; c per fold 6068.0, 6121.5, 6053.0, 6060.5, 6105.0 B; no-traffic estimate per fold 2420.0, 2366.5, 2435.0, 2427.5, 2383.0 B)

| | Constant: median / P90 | No traffic: median / P90 | Constant − no traffic, median abs error [95% CI] | Mean abs error [95% CI] |
|---|---|---|---|---|
| all | 1794 / 2361 | 1794 / 2361 | +0.0 [+0.0, +0.0] | -0.1 [-0.3, +0.0] |
| fault_diagnosis | 1264 / 2413 | 1264 / 2413 | +0.0 [+0.0, +0.0] | +0.0 [+0.0, +0.0] |
| procedure_lookup | 2325 / 2362 | 2325 / 2362 | +0.0 [+0.0, +0.0] | +0.0 [+0.0, +0.0] |
| sensor_analysis | 1080 / 2238 | 1080 / 2238 | +0.0 [+0.0, +0.0] | -0.3 [-1.0, +0.0] |

First-request sizes: 8488 B × 749, 8568 B × 1. `sensor_analysis_edge_cloud_274df9` (sensor_analysis, diagnostics): 8568 B, +80 B. DATA.md (C2: the first request measured in TCP sequence space) explains it: that trace's client Finished (80 B) and HTTP header were lost and resent as one segment, and from headers alone the Finished's end inside it is unknown, so it is counted in the request.

## 5. "Matches all features"

A feature family matches all features when the 95% cluster-bootstrap CI of the paired difference macro-F1(all features) - macro-F1(family alone) has a lower bound <= 0: both are out-of-fold predictions from the same 5 folds, scored on the same 1,000 resamples of whole prompt groups (seed 42), percentile interval (evaluation/stats.py paired_bootstrap_diff; a2a_leakcheck/analyze.py attribution). It says the family is not shown to fall short of all features; it is not an equivalence test, and a family whose CI lies wholly below 0 (better than all features) also matches.

**task_type at lan_padmax (four classes; the tool reports):**

| View | All features | Family | Alone | All − family [95% CI] | Matches all |
|---|---|---|---|---|---|
| v1 | 0.898 [0.879, 0.915] | sizes | 0.881 [0.862, 0.899] | +0.017 [+0.003, +0.031] | no |
| v1 | 0.898 [0.879, 0.915] | timing (top) | 0.883 [0.865, 0.900] | +0.015 [-0.001, +0.031] | yes |
| v1 | 0.898 [0.879, 0.915] | counts_direction | 0.697 [0.672, 0.722] | +0.201 [+0.170, +0.230] | no |
| v2 | 0.889 [0.870, 0.907] | sizes | 0.875 [0.855, 0.892] | +0.014 [+0.000, +0.028] | no |
| v2 | 0.889 [0.870, 0.907] | timing (top) | 0.892 [0.874, 0.910] | -0.003 [-0.020, +0.014] | yes |
| v2 | 0.889 [0.870, 0.907] | counts_direction | 0.711 [0.685, 0.737] | +0.178 [+0.149, +0.205] | no |

**sensor_analysis vs fault_diagnosis (the evaluation's --pair), every cell:**

| Cell | All features (stored) | Timing alone (stored) | All − timing [95% CI] | Sizes alone | All − sizes [95% CI] | Reproduces stored |
|---|---|---|---|---|---|---|
| lan_v1 | LEAK 0.934 [0.912, 0.954] | LEAK 0.782 [0.746, 0.817] | +0.152 [+0.114, +0.189] (short of all) | 0.936 [0.916, 0.958] | -0.002 [-0.018, +0.014] | True |
| lan_v2 | LEAK 0.940 [0.920, 0.960] | LEAK 0.798 [0.762, 0.831] | +0.142 [+0.108, +0.178] (short of all) | 0.938 [0.918, 0.960] | +0.002 [-0.014, +0.018] | True |
| lan_pad_v1 | LEAK 0.914 [0.890, 0.940] | LEAK 0.784 [0.746, 0.818] | +0.130 [+0.093, +0.166] (short of all) | 0.898 [0.873, 0.924] | +0.016 [-0.000, +0.034] | True |
| lan_pad_v2 | LEAK 0.916 [0.890, 0.942] | LEAK 0.792 [0.756, 0.828] | +0.124 [+0.090, +0.160] (short of all) | 0.912 [0.887, 0.938] | +0.004 [-0.010, +0.018] | True |
| lan_padmax_v1 | LEAK 0.774 [0.737, 0.810] | LEAK 0.748 [0.709, 0.786] | +0.026 [-0.010, +0.062] (matches) | 0.746 [0.708, 0.784] | +0.028 [-0.003, +0.058] | True |
| lan_padmax_v2 | LEAK 0.788 [0.750, 0.822] | LEAK 0.784 [0.750, 0.819] | +0.004 [-0.030, +0.034] (matches) | 0.778 [0.741, 0.812] | +0.010 [-0.018, +0.038] | True |

## A. Prompts and template pools

C2 (the three arms share each item's prompt: alert_triage True, fault_diagnosis True, procedure_lookup True, sensor_analysis True):

| Task type | Traces per arm | Distinct prompts | Prompt groups | Template pools |
|---|---|---|---|---|
| alert_triage | 250 | 246 | 246 | alarm templates 5, request templates 3, asks 5, assets 11, conditions 7, faults 5, locations 9, complaints 10 |
| fault_diagnosis | 250 | 250 | 250 | device kinds 6, fault scenarios 18, asks 5, sites 10, routine log lines 30 |
| procedure_lookup | 250 | 236 | 236 | question templates 20, prefixes 4, assets 14, parts 9, sensors 7, locations 8, tasks 7, faults 5 |
| sensor_analysis | 250 | 250 | 250 | equipment kinds 8, asks 6, sites 10, sample intervals 5, anomaly patterns 6 |

D1 (TLS control; each arm 432 traces, 231 prompt groups, grouped by sha1(input_prompt)[:8] (no prompt_group in the sidecars); the two arms hold the same prompts, with the same counts: code_review True, data_analysis True, research_retrieval True, support_triage True):

| Workflow | Traces per arm | Distinct prompts | Possible prompts | Pools |
|---|---|---|---|---|
| code_review | 108 | 49 | 72 | code_snippets 7, large_code_snippets 2, review_asks 8 |
| data_analysis | 108 | 69 | 100 | small_datasets 4, datasets 6, analysis_asks 10 |
| research_retrieval | 108 | 42 | 79 | topics 15, question_templates 5, long_questions 4 |
| support_triage | 108 | 71 | 175 | tickets 30, long_tickets 5, triage_asks 5 |
