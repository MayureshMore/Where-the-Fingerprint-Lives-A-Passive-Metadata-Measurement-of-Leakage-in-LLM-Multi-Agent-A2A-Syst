# Leak check: C2B1 lan_shaped, view v2

500 traces from 500 captures in `data/raw_c2b1_shaped` (0 skipped, 500 analysed as stripped copies). a2a-leakcheck 0.3.0, 2026-11-22T17:51:18-0800.

**Audit completed**: 4 attributes, 2 LEAK, 1 NO LEAK, 1 INCONCLUSIVE.

**Release policy satisfied** (baseline); exit 0.

**For review**: cloud_role (INCONCLUSIVE; LEAK in the baseline).

Vantage `v2`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 125 of 500 traces show no flow there; they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge |
|---|---|---|---|
| edge_cloud | 500 | 250 | 125 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **LEAK** | medium | 0.512 [0.474, 0.549] | 0.300 | 0.010 | 0.00 | counts and direction (alone matches all) |
| escalated | **LEAK** | high | 1.000 [1.000, 1.000] | 0.550 | 0.010 | 0.00 | first_request_bytes alone |
| cloud_role | **INCONCLUSIVE** | none | 0.500 [0.453, 0.554] | 0.550 | 0.230 | 0.00 | — |
| audit_null | **NO LEAK** | none | 0.198 [0.163, 0.232] | 0.300 | 0.890 | 0.00 | — |

## task_type

**LEAK**: CI lower bound 0.474 > chance + margin 0.300.

500 samples in 498 groups; classes alert_triage 125, fault_diagnosis 125, procedure_lookup 125, sensor_analysis 125.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.512 [0.474, 0.549] | — | — |
| sizes only | 139 | 0.513 [0.476, 0.547] | -0.002 [-0.043, +0.038] | yes |
| timing only | 30 | 0.493 [0.460, 0.530] | +0.018 [-0.025, +0.059] | no |
| counts and direction only | 26 | 0.542 [0.505, 0.580] | -0.031 [-0.077, +0.014] | yes |
| first_request_bytes only | 1 | 0.375 [0.361, 0.388] | +0.137 [+0.097, +0.175] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.35 (share of the way from chance to perfect); severity medium.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (498 groups): macro-F1 0.532 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.242, max 0.303; verdicts on permuted labels: 0 LEAK, 84 NO LEAK, 15 INCONCLUSIVE.

- **fix-message-counts**: Message counts and direction carry the leak. Keep the number of calls per agent constant and add dummy calls (defense=rate).

## escalated

**LEAK**: CI lower bound 1.000 > chance + margin 0.550.

500 samples in 498 groups; classes no 125, yes 375.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 1.000 [1.000, 1.000] | — | — |
| sizes only | 139 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |
| timing only | 30 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |
| counts and direction only | 26 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |
| first_request_bytes only | 1 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 1.00 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (498 groups): macro-F1 1.000 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.493, max 0.559; verdicts on permuted labels: 0 LEAK, 63 NO LEAK, 36 INCONCLUSIVE.

- **hide-escalation**: Whether the edge called the cloud is visible from the connections themselves, and padding cannot hide a call that did or did not happen. Make every task look alike upstream: dummy cloud calls at a fixed rate (cover traffic), or send every task to the cloud. Then re-run the audit.

## cloud_role

**INCONCLUSIVE**: CI [0.453, 0.554] straddles chance + margin 0.550.

375 samples in 373 groups; classes diagnostics 250, knowledge 125.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.500 [0.453, 0.554] | — | — |
| sizes only | 139 | 0.508 [0.456, 0.554] | -0.008 [-0.061, +0.049] | yes |
| timing only | 30 | 0.488 [0.437, 0.538] | +0.012 [-0.036, +0.065] | no |
| counts and direction only | 26 | 0.532 [0.481, 0.582] | -0.032 [-0.090, +0.028] | yes |
| first_request_bytes only | 1 | 0.400 [0.383, 0.416] | +0.100 [+0.051, +0.156] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size -0.00 (share of the way from chance to perfect); severity none.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (373 groups): macro-F1 0.532 on the real labels): p = 0.230; permuted-label macro-F1 mean 0.501, max 0.576; verdicts on permuted labels: 0 LEAK, 50 NO LEAK, 49 INCONCLUSIVE.

- **inconclusive**: The interval straddles chance + margin: more traces will narrow it. Re-run before treating this attribute as safe.

## audit_null

**NO LEAK**: CI upper bound 0.232 <= chance + margin 0.300.

500 samples in 498 groups; classes a 123, b 134, c 123, d 120.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.198 [0.163, 0.232] | — | — |
| sizes only | 139 | 0.199 [0.163, 0.237] | -0.001 [-0.035, +0.033] | yes |
| timing only | 30 | 0.199 [0.165, 0.236] | -0.001 [-0.043, +0.037] | yes |
| counts and direction only | 26 | 0.231 [0.195, 0.266] | -0.033 [-0.070, +0.006] | yes |
| first_request_bytes only | 1 | 0.175 [0.146, 0.205] | +0.023 [-0.016, +0.063] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size -0.07 (share of the way from chance to perfect); severity none.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (498 groups): macro-F1 0.220 on the real labels): p = 0.890; permuted-label macro-F1 mean 0.246, max 0.301; verdicts on permuted labels: 0 LEAK, 76 NO LEAK, 23 INCONCLUSIVE.

## Against the baseline

Baseline: `data/results/leakcheck/c2b1_lan_padmax_v2/report.json`.

- cloud_role: LEAK → INCONCLUSIVE

**Needs review**: cloud_role (LEAK in the baseline, INCONCLUSIVE now: the leak is not shown to be gone).

## Runtime

114.3 s in all (collection 0.1 s, extraction 3.2 s, analysis 110.8 s); peak memory 269 MB in the main process, up to 262 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.1 | 168 | — |
| extraction | 3.2 | 239 | — |
| analysis:task_type | 31.2 | 261 | 262 |
| analysis:escalated | 26.4 | 266 | 262 |
| analysis:cloud_role | 25.1 | 268 | 262 |
| analysis:audit_null | 27.1 | 269 | 262 |
