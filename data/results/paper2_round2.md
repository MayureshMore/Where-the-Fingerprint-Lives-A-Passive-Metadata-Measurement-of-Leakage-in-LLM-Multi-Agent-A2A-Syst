# Paper 2, round 2: the reviewers' checks

Parts from commit `b53e9859` (clean: True), merged at commit `a9b9dd76` (clean: True); seed 42; a2a-leakcheck 0.3.0 defaults (permutation test by prompt group; a feature set matches all features when the upper bound of the paired 95% CI of F1(all) − F1(set) is at most 0.05). Verdict counts are LEAK / INCONCLUSIVE / NO LEAK.

## A12 / A4. Accounting (group-level permutation)

| Set | n | a2a-leakcheck | k-FP | first request |
|---|---|---|---|---|
| Learned: task_type | 6 | 6 / 0 / 0 | 6 / 0 / 0 | 6 / 0 / 0 |
| Learned: pair | 6 | 6 / 0 / 0 | 6 / 0 / 0 | 0 / 4 / 2 |
| Learned: escalated_only | 6 | 6 / 0 / 0 | 6 / 0 / 0 | 4 / 0 / 2 |
| **Learned, all** | 18 | 18 / 0 / 0 | 18 / 0 / 0 | 10 / 4 / 4 |
| Structural check: escalated | 6 | 6 / 0 / 0 | 6 / 0 / 0 | 6 / 0 / 0 |
| Structural check: cloud_role | 6 | 6 / 0 / 0 | 6 / 0 / 0 | 4 / 0 / 2 |
| Known non-leaks: permuted | 480 | 0 / 61 / 419 | 0 / 47 / 433 | 0 / 42 / 438 |
| Known non-leaks: audit_null | 6 | 0 / 2 / 4 | 0 / 1 / 5 | 0 / 2 / 4 |

The same with the per-sample permutation of v1.0 (`paper2_review.json`):

| Set | a2a-leakcheck | k-FP | first request |
|---|---|---|---|
| Known non-leaks: permuted | 0 / 65 / 415 | 0 / 52 / 428 | 0 / 47 / 433 |
| Known non-leaks: audit_null | 0 / 2 / 4 | 0 / 1 / 5 | 0 / 2 / 4 |
| Known leaks: by construction | 12 / 0 / 0 | 12 / 0 / 0 | 10 / 0 / 2 |
| Known leaks: baseline only | 6 / 0 / 0 | 6 / 0 / 0 | 6 / 0 / 0 |

Release blocking over the permuted audits (one cell, one draw index, four attributes):

| Method | Audits | Any LEAK | No LEAK but an INCONCLUSIVE |
|---|---|---|---|
| leakcheck | 120 | 0 [0.000, 0.031] | 54 (0.450) [0.364, 0.539] |
| kfp_rf | 120 | 0 [0.000, 0.031] | 43 (0.358) [0.278, 0.447] |
| first_request | 120 | 0 [0.000, 0.031] | 37 (0.308) [0.233, 0.396] |

All-zero windows (nothing in view) per cell and task type: lan_v1: ; lan_v2: alert_triage 250; lan_pad_v1: ; lan_pad_v2: alert_triage 250; lan_padmax_v1: ; lan_padmax_v2: alert_triage 250.

## A4. Groups per class and draw reuse

| Cell | Attribute | Samples | Groups | Group sizes (size: groups) |
|---|---|---|---|---|
| lan_v1 | task_type | 1000 | 982 | 1: 964, 2: 18 |
| lan_v1 | escalated | 1000 | 982 | 1: 964, 2: 18 |
| lan_v1 | cloud_role | 750 | 736 | 1: 722, 2: 14 |
| lan_v1 | audit_null | 1000 | 982 | 1: 964, 2: 18 |
| lan_v2 | task_type | 1000 | 982 | 1: 964, 2: 18 |
| lan_v2 | escalated | 1000 | 982 | 1: 964, 2: 18 |
| lan_v2 | cloud_role | 750 | 736 | 1: 722, 2: 14 |
| lan_v2 | audit_null | 1000 | 982 | 1: 964, 2: 18 |
| lan_pad_v1 | task_type | 1000 | 982 | 1: 964, 2: 18 |
| lan_pad_v1 | escalated | 1000 | 982 | 1: 964, 2: 18 |
| lan_pad_v1 | cloud_role | 750 | 736 | 1: 722, 2: 14 |
| lan_pad_v1 | audit_null | 1000 | 982 | 1: 964, 2: 18 |
| lan_pad_v2 | task_type | 1000 | 982 | 1: 964, 2: 18 |
| lan_pad_v2 | escalated | 1000 | 982 | 1: 964, 2: 18 |
| lan_pad_v2 | cloud_role | 750 | 736 | 1: 722, 2: 14 |
| lan_pad_v2 | audit_null | 1000 | 982 | 1: 964, 2: 18 |
| lan_padmax_v1 | task_type | 1000 | 982 | 1: 964, 2: 18 |
| lan_padmax_v1 | escalated | 1000 | 982 | 1: 964, 2: 18 |
| lan_padmax_v1 | cloud_role | 750 | 736 | 1: 722, 2: 14 |
| lan_padmax_v1 | audit_null | 1000 | 982 | 1: 964, 2: 18 |
| lan_padmax_v2 | task_type | 1000 | 982 | 1: 964, 2: 18 |
| lan_padmax_v2 | escalated | 1000 | 982 | 1: 964, 2: 18 |
| lan_padmax_v2 | cloud_role | 750 | 736 | 1: 722, 2: 14 |
| lan_padmax_v2 | audit_null | 1000 | 982 | 1: 964, 2: 18 |

D1: tls: role 1296 samples in 231 groups, workflow 432 samples in 231 groups, topology 432 samples in 231 groups (trace group sizes {'1': 129, '2': 59, '3': 27, '4': 7, '5': 2, '6': 3, '8': 1, '9': 1, '14': 1, '17': 1}); cleartext: role 1296 samples in 231 groups, workflow 432 samples in 231 groups, topology 432 samples in 231 groups (trace group sizes {'1': 129, '2': 59, '3': 27, '4': 7, '5': 2, '6': 3, '8': 1, '9': 1, '14': 1, '17': 1})

Reuse: lan_v1 task_type: 20/20 distinct, 0 equal to an inner permutation, lan_v1 escalated: 20/20 distinct, 0 equal to an inner permutation, lan_v1 cloud_role: 20/20 distinct, 0 equal to an inner permutation, lan_v1 audit_null: 20/20 distinct, 0 equal to an inner permutation, lan_v2 task_type: 20/20 distinct, 0 equal to an inner permutation, lan_v2 escalated: 20/20 distinct, 0 equal to an inner permutation, lan_v2 cloud_role: 20/20 distinct, 0 equal to an inner permutation, lan_v2 audit_null: 20/20 distinct, 0 equal to an inner permutation, lan_pad_v1 task_type: 20/20 distinct, 0 equal to an inner permutation, lan_pad_v1 escalated: 20/20 distinct, 0 equal to an inner permutation, lan_pad_v1 cloud_role: 20/20 distinct, 0 equal to an inner permutation, lan_pad_v1 audit_null: 20/20 distinct, 0 equal to an inner permutation, lan_pad_v2 task_type: 20/20 distinct, 0 equal to an inner permutation, lan_pad_v2 escalated: 20/20 distinct, 0 equal to an inner permutation, lan_pad_v2 cloud_role: 20/20 distinct, 0 equal to an inner permutation, lan_pad_v2 audit_null: 20/20 distinct, 0 equal to an inner permutation, lan_padmax_v1 task_type: 20/20 distinct, 0 equal to an inner permutation, lan_padmax_v1 escalated: 20/20 distinct, 0 equal to an inner permutation, lan_padmax_v1 cloud_role: 20/20 distinct, 0 equal to an inner permutation, lan_padmax_v1 audit_null: 20/20 distinct, 0 equal to an inner permutation, lan_padmax_v2 task_type: 20/20 distinct, 0 equal to an inner permutation, lan_padmax_v2 escalated: 20/20 distinct, 0 equal to an inner permutation, lan_padmax_v2 cloud_role: 20/20 distinct, 0 equal to an inner permutation, lan_padmax_v2 audit_null: 20/20 distinct, 0 equal to an inner permutation.

## A3. "Matches all features": non-inferiority (δ = 0.05) against 0.1.x's rule

Committed reports, every LEAK whose "carried by" changes:

| Report / attribute | 0.1.x | 0.3.0 |
|---|---|---|
| D1 tls / role | timing | timing (alone matches all) |
| D1 cleartext / workflow | sizes (alone matches all) | sizes |

Recomputed (permutations 0; the gap of each family against all features):

| Cell / task | all | sizes: gap | timing: gap | counts: gap | 0.1.x | 0.3.0 |
|---|---|---|---|---|---|---|
| lan_v1 / task_type | 0.967 [0.955, 0.977] | +0.005 [-0.002, +0.013] ✓ | +0.066 [+0.049, +0.083]  | +0.235 [+0.208, +0.262]  | sizes (alone matches all) | sizes (alone matches all) |
| lan_v1 / pair | 0.934 [0.912, 0.954] | -0.002 [-0.018, +0.014] ✓ | +0.152 [+0.114, +0.189]  | +0.332 [+0.290, +0.376]  | sizes (alone matches all) | sizes (alone matches all) |
| lan_v1 / escalated_only | 0.959 [0.945, 0.972] | +0.000 [-0.012, +0.013] ✓ | +0.093 [+0.071, +0.116]  | +0.297 [+0.261, +0.329]  | sizes (alone matches all) | sizes (alone matches all) |
| lan_v2 / task_type | 0.975 [0.965, 0.984] | +0.007 [-0.002, +0.016] ✓ | +0.093 [+0.076, +0.113]  | +0.223 [+0.202, +0.251]  | sizes (alone matches all) | sizes (alone matches all) |
| lan_v2 / pair | 0.940 [0.920, 0.960] | +0.002 [-0.014, +0.018] ✓ | +0.142 [+0.108, +0.178]  | +0.338 [+0.294, +0.382]  | sizes (alone matches all) | sizes (alone matches all) |
| lan_v2 / escalated_only | 0.963 [0.948, 0.975] | -0.007 [-0.016, +0.003] ✓ | +0.097 [+0.074, +0.121]  | +0.300 [+0.266, +0.334]  | sizes (alone matches all) | sizes (alone matches all) |
| lan_pad_v1 / task_type | 0.951 [0.937, 0.963] | -0.002 [-0.011, +0.006] ✓ | +0.047 [+0.029, +0.064]  | +0.223 [+0.197, +0.249]  | sizes (alone matches all) | sizes (alone matches all) |
| lan_pad_v1 / pair | 0.914 [0.890, 0.940] | +0.016 [-0.000, +0.034] ✓ | +0.130 [+0.093, +0.166]  | +0.350 [+0.302, +0.394]  | sizes (alone matches all) | sizes (alone matches all) |
| lan_pad_v1 / escalated_only | 0.933 [0.916, 0.952] | +0.004 [-0.009, +0.017] ✓ | +0.083 [+0.059, +0.106]  | +0.304 [+0.268, +0.339]  | sizes (alone matches all) | sizes (alone matches all) |
| lan_pad_v2 / task_type | 0.950 [0.936, 0.962] | +0.004 [-0.004, +0.013] ✓ | +0.052 [+0.034, +0.069]  | +0.248 [+0.221, +0.274]  | sizes (alone matches all) | sizes (alone matches all) |
| lan_pad_v2 / pair | 0.916 [0.890, 0.942] | +0.004 [-0.010, +0.018] ✓ | +0.124 [+0.090, +0.160]  | +0.362 [+0.310, +0.408]  | sizes (alone matches all) | sizes (alone matches all) |
| lan_pad_v2 / escalated_only | 0.947 [0.930, 0.962] | +0.007 [-0.002, +0.016] ✓ | +0.095 [+0.070, +0.119]  | +0.355 [+0.318, +0.387]  | sizes (alone matches all) | sizes (alone matches all) |
| lan_padmax_v1 / task_type | 0.898 [0.879, 0.915] | +0.017 [+0.003, +0.031] ✓ | +0.015 [-0.001, +0.031] ✓ | +0.201 [+0.170, +0.230]  | timing (alone matches all) | timing (alone matches all) |
| lan_padmax_v1 / pair | 0.774 [0.737, 0.810] | +0.028 [-0.003, +0.058]  | +0.026 [-0.010, +0.062]  | +0.158 [+0.108, +0.208]  | timing (alone matches all) | timing |
| lan_padmax_v1 / escalated_only | 0.852 [0.827, 0.876] | +0.004 [-0.016, +0.025] ✓ | +0.018 [-0.005, +0.040] ✓ | +0.250 [+0.213, +0.291]  | sizes (alone matches all) | sizes (alone matches all) |
| lan_padmax_v2 / task_type | 0.889 [0.870, 0.907] | +0.014 [+0.000, +0.028] ✓ | -0.003 [-0.020, +0.014] ✓ | +0.178 [+0.149, +0.205]  | timing (alone matches all) | timing (alone matches all) |
| lan_padmax_v2 / pair | 0.788 [0.750, 0.822] | +0.010 [-0.018, +0.038] ✓ | +0.004 [-0.030, +0.034] ✓ | +0.144 [+0.096, +0.192]  | timing (alone matches all) | timing (alone matches all) |
| lan_padmax_v2 / escalated_only | 0.842 [0.814, 0.868] | +0.010 [-0.007, +0.027] ✓ | -0.010 [-0.035, +0.014] ✓ | +0.242 [+0.203, +0.280]  | timing (alone matches all) | timing (alone matches all) |

## A5. The permutation test's model

42 cases (('lan_v1', 'lan_padmax_v2'): audit_null and 5 permuted draws per attribute). Pi estimate: Mac time × 7.26 (data/results/leakcheck_pi/c2_lan_v1/report.json / data/results/leakcheck/c2_lan_v1/report.json: total_s 1597 / 220).

| Option | Verdicts changed | Extended to 999 | Mac time (s) | Baseline (s) | Pi estimate (s) |
|---|---|---|---|---|---|
| gbt_99 | 2 | 0 | 11225 | 1281 | 81468 |
| rf_light_adaptive_999 | 0 | 10 | 3131 | 1281 | 22724 |
- gbt_99: lan_v1 cloud_role permuted 3: INCONCLUSIVE (p 0.02) → NO LEAK (p 0.250)
- gbt_99: lan_v1 audit_null permuted 2: INCONCLUSIVE (p 0.02) → NO LEAK (p 0.260)

## A7. Repeated grouped splits (fold seeds 43–47 against 42)

| Cell / task | seed 42 | agree of 5 | macro-F1 range | CI lower | CI upper | p range |
|---|---|---|---|---|---|---|
| lan_v1 / task_type | LEAK 0.967 | 5 | 0.965–0.970 | 0.953–0.958 | 0.976–0.980 | 0.01–0.01 |
| lan_v1 / escalated | LEAK 1.000 | 5 | 0.997–1.000 | 0.993–1.000 | 1.000–1.000 | 0.01–0.01 |
| lan_v1 / cloud_role | LEAK 0.998 | 5 | 0.997–0.998 | 0.992–0.995 | 1.000–1.000 | 0.01–0.01 |
| lan_v1 / audit_null | NO LEAK 0.250 | 5 | 0.236–0.262 | 0.212–0.234 | 0.260–0.289 | 0.19–0.87 |
| lan_v1 / pair | LEAK 0.934 | 5 | 0.920–0.936 | 0.894–0.914 | 0.944–0.958 | 0.01–0.01 |
| lan_v1 / escalated_only | LEAK 0.959 | 5 | 0.944–0.965 | 0.927–0.952 | 0.960–0.977 | 0.01–0.01 |
| lan_v2 / task_type | LEAK 0.975 | 5 | 0.971–0.978 | 0.959–0.968 | 0.981–0.986 | 0.01–0.01 |
| lan_v2 / escalated | LEAK 1.000 | 5 | 1.000–1.000 | 1.000–1.000 | 1.000–1.000 | 0.01–0.01 |
| lan_v2 / cloud_role | LEAK 0.998 | 5 | 0.996–0.998 | 0.990–0.995 | 1.000–1.000 | 0.01–0.01 |
| lan_v2 / audit_null | NO LEAK 0.238 | 5 | 0.228–0.261 | 0.201–0.231 | 0.254–0.288 | 0.46–0.98 |
| lan_v2 / pair | LEAK 0.940 | 5 | 0.930–0.948 | 0.908–0.926 | 0.952–0.966 | 0.01–0.01 |
| lan_v2 / escalated_only | LEAK 0.963 | 5 | 0.960–0.967 | 0.945–0.954 | 0.973–0.980 | 0.01–0.01 |
| lan_pad_v1 / task_type | LEAK 0.951 | 5 | 0.945–0.955 | 0.930–0.942 | 0.958–0.967 | 0.01–0.01 |
| lan_pad_v1 / escalated | LEAK 0.999 | 5 | 0.999–0.999 | 0.996–0.996 | 1.000–1.000 | 0.01–0.01 |
| lan_pad_v1 / cloud_role | LEAK 0.998 | 5 | 0.995–0.998 | 0.990–0.995 | 1.000–1.000 | 0.01–0.01 |
| lan_pad_v1 / audit_null | INCONCLUSIVE 0.249 | 2 | 0.259–0.268 | 0.233–0.239 | 0.287–0.294 | 0.02–0.19 |
| lan_pad_v1 / pair | LEAK 0.914 | 5 | 0.900–0.912 | 0.872–0.888 | 0.924–0.938 | 0.01–0.01 |
| lan_pad_v1 / escalated_only | LEAK 0.933 | 5 | 0.925–0.940 | 0.906–0.922 | 0.943–0.956 | 0.01–0.01 |
| lan_pad_v2 / task_type | LEAK 0.950 | 5 | 0.946–0.953 | 0.932–0.939 | 0.959–0.965 | 0.01–0.01 |
| lan_pad_v2 / escalated | LEAK 1.000 | 5 | 1.000–1.000 | 1.000–1.000 | 1.000–1.000 | 0.01–0.01 |
| lan_pad_v2 / cloud_role | LEAK 0.998 | 5 | 0.995–0.998 | 0.990–0.995 | 1.000–1.000 | 0.01–0.01 |
| lan_pad_v2 / audit_null | NO LEAK 0.255 | 5 | 0.235–0.253 | 0.208–0.226 | 0.261–0.281 | 0.07–0.61 |
| lan_pad_v2 / pair | LEAK 0.916 | 5 | 0.902–0.914 | 0.874–0.888 | 0.928–0.938 | 0.01–0.01 |
| lan_pad_v2 / escalated_only | LEAK 0.947 | 5 | 0.935–0.939 | 0.917–0.922 | 0.951–0.954 | 0.01–0.01 |
| lan_padmax_v1 / task_type | LEAK 0.898 | 5 | 0.886–0.897 | 0.867–0.879 | 0.904–0.914 | 0.01–0.01 |
| lan_padmax_v1 / escalated | LEAK 1.000 | 5 | 1.000–1.000 | 1.000–1.000 | 1.000–1.000 | 0.01–0.01 |
| lan_padmax_v1 / cloud_role | LEAK 0.995 | 5 | 0.995–0.998 | 0.990–0.995 | 1.000–1.000 | 0.01–0.01 |
| lan_padmax_v1 / audit_null | INCONCLUSIVE 0.277 | 4 | 0.266–0.297 | 0.238–0.267 | 0.292–0.323 | 0.03–0.32 |
| lan_padmax_v1 / pair | LEAK 0.774 | 5 | 0.776–0.800 | 0.739–0.765 | 0.814–0.834 | 0.01–0.01 |
| lan_padmax_v1 / escalated_only | LEAK 0.852 | 5 | 0.852–0.867 | 0.826–0.842 | 0.876–0.890 | 0.01–0.01 |
| lan_padmax_v2 / task_type | LEAK 0.889 | 5 | 0.886–0.902 | 0.868–0.884 | 0.904–0.919 | 0.01–0.01 |
| lan_padmax_v2 / escalated | LEAK 1.000 | 5 | 1.000–1.000 | 1.000–1.000 | 1.000–1.000 | 0.01–0.01 |
| lan_padmax_v2 / cloud_role | LEAK 0.996 | 5 | 0.994–0.997 | 0.988–0.992 | 0.999–1.000 | 0.01–0.01 |
| lan_padmax_v2 / audit_null | NO LEAK 0.259 | 5 | 0.225–0.249 | 0.198–0.222 | 0.252–0.275 | 0.10–0.93 |
| lan_padmax_v2 / pair | LEAK 0.788 | 5 | 0.778–0.796 | 0.742–0.760 | 0.816–0.832 | 0.01–0.01 |
| lan_padmax_v2 / escalated_only | LEAK 0.842 | 5 | 0.847–0.863 | 0.822–0.839 | 0.872–0.888 | 0.01–0.01 |

## A8. Timing family against timestamps only

The timing family has 30 columns: 10 come from flows chosen by bytes (heaviest, second heaviest), 11 from bursts split at changes of direction; the inter-arrival times run over every packet, whose number follows the bytes sent. Timestamps only: 40 features (features/timestamps.py).

| Cell / task | all | timing | all − timing | timestamps only | all − timestamps |
|---|---|---|---|---|---|
| lan_v1 / task_type | 0.967 [0.955, 0.977] | 0.901 [0.883, 0.918] LEAK | +0.066 [+0.049, +0.083] | 0.897 [0.879, 0.915] LEAK | +0.070 [+0.053, +0.088] |
| lan_v1 / pair | 0.934 [0.912, 0.954] | 0.782 [0.746, 0.817] LEAK | +0.152 [+0.114, +0.189] | 0.792 [0.757, 0.828] LEAK | +0.142 [+0.102, +0.180] |
| lan_v1 / escalated_only | 0.959 [0.945, 0.972] | 0.865 [0.842, 0.888] LEAK | +0.093 [+0.071, +0.116] | 0.856 [0.832, 0.880] LEAK | +0.103 [+0.078, +0.126] |
| lan_v2 / task_type | 0.975 [0.965, 0.984] | 0.882 [0.861, 0.901] LEAK | +0.093 [+0.076, +0.113] | 0.898 [0.880, 0.915] LEAK | +0.077 [+0.059, +0.095] |
| lan_v2 / pair | 0.940 [0.920, 0.960] | 0.798 [0.762, 0.831] LEAK | +0.142 [+0.108, +0.178] | 0.814 [0.780, 0.848] LEAK | +0.126 [+0.089, +0.162] |
| lan_v2 / escalated_only | 0.963 [0.948, 0.975] | 0.865 [0.842, 0.888] LEAK | +0.097 [+0.074, +0.121] | 0.861 [0.836, 0.884] LEAK | +0.101 [+0.077, +0.128] |
| lan_pad_v1 / task_type | 0.951 [0.937, 0.963] | 0.904 [0.886, 0.921] LEAK | +0.047 [+0.029, +0.064] | 0.903 [0.885, 0.920] LEAK | +0.048 [+0.031, +0.065] |
| lan_pad_v1 / pair | 0.914 [0.890, 0.940] | 0.784 [0.746, 0.818] LEAK | +0.130 [+0.093, +0.166] | 0.800 [0.763, 0.836] LEAK | +0.114 [+0.078, +0.149] |
| lan_pad_v1 / escalated_only | 0.933 [0.916, 0.952] | 0.851 [0.825, 0.875] LEAK | +0.083 [+0.059, +0.106] | 0.860 [0.834, 0.885] LEAK | +0.073 [+0.050, +0.100] |
| lan_pad_v2 / task_type | 0.950 [0.936, 0.962] | 0.898 [0.881, 0.916] LEAK | +0.052 [+0.034, +0.069] | 0.887 [0.868, 0.904] LEAK | +0.063 [+0.046, +0.080] |
| lan_pad_v2 / pair | 0.916 [0.890, 0.942] | 0.792 [0.756, 0.828] LEAK | +0.124 [+0.090, +0.160] | 0.804 [0.768, 0.840] LEAK | +0.112 [+0.076, +0.147] |
| lan_pad_v2 / escalated_only | 0.947 [0.930, 0.962] | 0.852 [0.827, 0.876] LEAK | +0.095 [+0.070, +0.119] | 0.849 [0.824, 0.872] LEAK | +0.097 [+0.074, +0.123] |
| lan_padmax_v1 / task_type | 0.898 [0.879, 0.915] | 0.883 [0.865, 0.900] LEAK | +0.015 [-0.001, +0.031] | 0.882 [0.863, 0.901] LEAK | +0.016 [-0.002, +0.034] |
| lan_padmax_v1 / pair | 0.774 [0.737, 0.810] | 0.748 [0.709, 0.786] LEAK | +0.026 [-0.010, +0.062] | 0.770 [0.735, 0.805] LEAK | +0.004 [-0.030, +0.037] |
| lan_padmax_v1 / escalated_only | 0.852 [0.827, 0.876] | 0.834 [0.808, 0.858] LEAK | +0.018 [-0.005, +0.040] | 0.835 [0.808, 0.859] LEAK | +0.017 [-0.007, +0.041] |
| lan_padmax_v2 / task_type | 0.889 [0.870, 0.907] | 0.892 [0.874, 0.910] LEAK | -0.003 [-0.020, +0.014] | 0.890 [0.872, 0.907] LEAK | -0.001 [-0.020, +0.016] |
| lan_padmax_v2 / pair | 0.788 [0.750, 0.822] | 0.784 [0.750, 0.819] LEAK | +0.004 [-0.030, +0.034] | 0.784 [0.747, 0.820] LEAK | +0.004 [-0.032, +0.035] |
| lan_padmax_v2 / escalated_only | 0.842 [0.814, 0.868] | 0.852 [0.830, 0.875] LEAK | -0.010 [-0.035, +0.014] | 0.846 [0.818, 0.871] LEAK | -0.003 [-0.029, +0.023] |

## A9. Template-held-out

Factors: alert_triage: event template (alarm or request) (8 levels); sensor_analysis: equipment kind (8 levels); fault_diagnosis: device kind (6 levels); procedure_lookup: question template (20 levels).

| Cell / task | held out by prompt | by template | timing alone, by template |
|---|---|---|---|
| lan_v1 / task_type | LEAK 0.967 [0.955, 0.977] | LEAK 0.968 [0.948, 0.977] (42 groups) | 0.890, gap +0.078 [+0.064, +0.105] |
| lan_v1 / pair | LEAK 0.934 [0.912, 0.954] | LEAK 0.920 [0.864, 0.952] (14 groups) | 0.786, gap +0.134 [+0.098, +0.183] |
| lan_v2 / task_type | LEAK 0.975 [0.965, 0.984] | LEAK 0.978 [0.958, 0.989] (42 groups) | 0.903, gap +0.075 [+0.060, +0.108] |
| lan_v2 / pair | LEAK 0.940 [0.920, 0.960] | LEAK 0.950 [0.906, 0.976] (14 groups) | 0.776, gap +0.174 [+0.143, +0.228] |
| lan_pad_v1 / task_type | LEAK 0.951 [0.937, 0.963] | LEAK 0.939 [0.908, 0.952] (42 groups) | 0.876, gap +0.063 [+0.039, +0.092] |
| lan_pad_v1 / pair | LEAK 0.914 [0.890, 0.940] | LEAK 0.892 [0.834, 0.915] (14 groups) | 0.788, gap +0.104 [+0.060, +0.162] |
| lan_pad_v2 / task_type | LEAK 0.950 [0.936, 0.962] | LEAK 0.943 [0.916, 0.955] (42 groups) | 0.896, gap +0.047 [+0.027, +0.072] |
| lan_pad_v2 / pair | LEAK 0.916 [0.890, 0.942] | LEAK 0.906 [0.852, 0.930] (14 groups) | 0.792, gap +0.114 [+0.081, +0.162] |
| lan_padmax_v1 / task_type | LEAK 0.898 [0.879, 0.915] | LEAK 0.882 [0.840, 0.897] (42 groups) | 0.874, gap +0.008 [-0.007, +0.020] |
| lan_padmax_v1 / pair | LEAK 0.774 [0.737, 0.810] | LEAK 0.776 [0.694, 0.805] (14 groups) | 0.742, gap +0.034 [-0.002, +0.065] |
| lan_padmax_v2 / task_type | LEAK 0.889 [0.870, 0.907] | LEAK 0.893 [0.853, 0.908] (42 groups) | 0.872, gap +0.021 [+0.001, +0.043] |
| lan_padmax_v2 / pair | LEAK 0.788 [0.750, 0.822] | LEAK 0.792 [0.717, 0.819] (14 groups) | 0.754, gap +0.038 [-0.004, +0.080] |

## A10. Review burden against traces per task type (a2a-leakcheck, permuted draws)

Cells: lan_v1, lan_v2, lan_pad_v1, lan_pad_v2, lan_padmax_v1, lan_padmax_v2; the all row is A4's six cells.

| Traces per task type | Audits | INCONCLUSIVE per attribute | Audits with one | audit_null (real) |
|---|---|---|---|---|
| 50 | 60 | 0.608 | 58 (0.967) [0.886, 0.991] | 0 / 29 / 31 |
| 100 | 60 | 0.438 | 55 (0.917) [0.819, 0.964] | 0 / 22 / 38 |
| 150 | 60 | 0.271 | 46 (0.767) [0.646, 0.856] | 0 / 17 / 43 |
| 200 | 60 | 0.167 | 29 (0.483) [0.362, 0.607] | 0 / 15 / 45 |
| all | 120 | 0.127 | 54 (0.450) [0.364, 0.539] | 0 / 2 / 4 |

## A11. a2a-leakcheck against k-FP

| Method | INCONCLUSIVE on permuted | why | CI width (median, P90) | p ≤ 0.05 | time per test (s) |
|---|---|---|---|---|---|
| leakcheck | 61/480 | CI straddles the threshold 47, permutation test disagrees with a NO LEAK 14 | 0.056, 0.071 | 24 | 28.4 |
| kfp_rf | 47/480 | CI straddles the threshold 43, permutation test disagrees with a NO LEAK 4 | 0.057, 0.071 | 16 | 19.1 |
| first_request | 42/480 | CI straddles the threshold 31, permutation test disagrees with a NO LEAK 11 | 0.056, 0.073 | 18 | 16.1 |

Agreement with kfp_rf: real labels 35/36; permuted 402/480 (both INCONCLUSIVE 15, only a2a-leakcheck 46, only kfp_rf 32).

Agreement with first_request: real labels 24/36; permuted 387/480 (both INCONCLUSIVE 5, only a2a-leakcheck 56, only first_request 37).

### INCONCLUSIVE on permuted draws, by attribute

NO LEAK needs the CI's upper bound at most chance + margin (chance = 1/k, margin 0.05). Headroom is that threshold minus the permuted draws' mean macro-F1 and the CI's median half-width; the predicted count is draws · (1 − Φ(headroom / sd)).

| Attribute | Method | n | Classes | Groups (fewest per class) | INCONCLUSIVE | from the CI | predicted | CI half-width | half-width · √n | sd of macro-F1 | headroom (sd) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| task_type | leakcheck | 1000 | 250 / 250 / 250 / 250 | 982 (alert_triage 246, fault_diagnosis 250, procedure_lookup 236, sensor_analysis 250) | 11/120 | 8 | 7.1 | 0.027 | 0.84 | 0.016 | 0.025 (1.56) |
| task_type | kfp_rf | 1000 | 250 / 250 / 250 / 250 | 982 (alert_triage 246, fault_diagnosis 250, procedure_lookup 236, sensor_analysis 250) | 5/120 | 3 | 2.8 | 0.026 | 0.83 | 0.015 | 0.030 (2.00) |
| task_type | first_request | 1000 | 250 / 250 / 250 / 250 | 982 (alert_triage 246, fault_diagnosis 250, procedure_lookup 236, sensor_analysis 250) | 10/120 | 3 | 3.9 | 0.026 | 0.83 | 0.025 | 0.046 (1.84) |
| escalated | leakcheck | 1000 | 250 / 750 | 982 (no 246, yes 736) | 13/120 | 9 | 8.0 | 0.031 | 0.97 | 0.019 | 0.028 (1.50) |
| escalated | kfp_rf | 1000 | 250 / 750 | 982 (no 246, yes 736) | 12/120 | 12 | 11.5 | 0.031 | 0.97 | 0.018 | 0.023 (1.30) |
| escalated | first_request | 1000 | 250 / 750 | 982 (no 246, yes 736) | 5/120 | 5 | 10.7 | 0.031 | 0.98 | 0.043 | 0.058 (1.35) |
| cloud_role | leakcheck | 750 | 500 / 250 | 736 (diagnostics 500, knowledge 236) | 28/120 | 24 | 22.5 | 0.035 | 0.96 | 0.024 | 0.021 (0.89) |
| cloud_role | kfp_rf | 750 | 500 / 250 | 736 (diagnostics 500, knowledge 236) | 24/120 | 24 | 19.5 | 0.035 | 0.97 | 0.023 | 0.023 (0.98) |
| cloud_role | first_request | 750 | 500 / 250 | 736 (diagnostics 500, knowledge 236) | 18/120 | 16 | 14.7 | 0.036 | 0.99 | 0.038 | 0.044 (1.16) |
| audit_null | leakcheck | 1000 | 251 / 252 / 244 / 253 | 982 (a 247, b 249, c 238, d 248) | 9/120 | 6 | 6.0 | 0.027 | 0.84 | 0.016 | 0.026 (1.65) |
| audit_null | kfp_rf | 1000 | 251 / 252 / 244 / 253 | 982 (a 247, b 249, c 238, d 248) | 6/120 | 4 | 6.4 | 0.027 | 0.84 | 0.017 | 0.027 (1.61) |
| audit_null | first_request | 1000 | 251 / 252 / 244 / 253 | 982 (a 247, b 249, c 238, d 248) | 9/120 | 7 | 7.6 | 0.026 | 0.83 | 0.031 | 0.047 (1.53) |

cloud_role is labelled on escalated traces only (n = 750, minority share 0.33); escalated has two classes too (n = 1000, minority share 0.25). Median CI half-width 0.035 against 0.031; escalated's scaled by √(1000/750) is 0.035. On its 120 permuted draws, a2a-leakcheck and k-FP are both INCONCLUSIVE on 9, a2a-leakcheck alone on 19 (CI straddles the threshold 18, permutation test disagrees with a NO LEAK 1), k-FP alone on 15.

| Cell | plain k-FP task_type macro-F1 | its time (s) | a2a-leakcheck task_type test (s) |
|---|---|---|---|
| lan_v1 | 0.920 | 3 | 31 |
| lan_v2 | 0.925 | 3 | 25 |
| lan_pad_v1 | 0.925 | 3 | 31 |
| lan_pad_v2 | 0.928 | 3 | 25 |
| lan_padmax_v1 | 0.902 | 3 | 31 |
| lan_padmax_v2 | 0.898 | 3 | 25 |

