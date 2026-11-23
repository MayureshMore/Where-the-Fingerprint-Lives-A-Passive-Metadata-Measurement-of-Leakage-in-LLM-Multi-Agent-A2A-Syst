# Leak check: C2B1 lan_shaped, view v1

500 traces from 500 captures in `data/raw_c2b1_shaped` (0 skipped, 500 analysed as stripped copies). a2a-leakcheck 0.3.0, 2026-11-22T17:48:22-0800.

**Audit completed**: 4 attributes, 2 LEAK, 1 NO LEAK, 1 INCONCLUSIVE.

**Release policy satisfied** (baseline); exit 0.

**For review**: cloud_role (INCONCLUSIVE; LEAK in the baseline).

Vantage `v1`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). 0 of 500 traces show no flow there; they stay in the analysis with all-zero features, since seeing nothing is what this observer sees for them.

Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + 0.05; NO LEAK if the upper bound is at most chance + 0.05; INCONCLUSIVE otherwise, or when the minimum-sample check fails, or when a LEAK fails the label-permutation test (p > 0.05, 99 permutations scored with RF-LIGHT). 5-fold grouped CV, GBT, 1000 cluster-bootstrap resamples, seed 42.

Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries traffic. An agent never seen gives no role samples.

| Topology | Traces | diagnostics | knowledge | ticket |
|---|---|---|---|---|
| edge_cloud | 500 | 250 | 125 | 500 |

| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | False positives on permuted labels | Leak carried by |
|---|---|---|---|---|---|---|---|
| task_type | **LEAK** | medium | 0.574 [0.533, 0.612] | 0.300 | 0.010 | 0.00 | sizes (alone matches all) |
| escalated | **LEAK** | high | 1.000 [1.000, 1.000] | 0.550 | 0.010 | 0.00 | first_request_bytes alone |
| cloud_role | **INCONCLUSIVE** | none | 0.595 [0.545, 0.644] | 0.550 | 0.010 | 0.00 | — |
| audit_null | **NO LEAK** | none | 0.225 [0.187, 0.262] | 0.300 | 0.470 | 0.00 | — |

## task_type

**LEAK**: CI lower bound 0.533 > chance + margin 0.300.

500 samples in 498 groups; classes alert_triage 125, fault_diagnosis 125, procedure_lookup 125, sensor_analysis 125.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.574 [0.533, 0.612] | — | — |
| sizes only | 139 | 0.563 [0.522, 0.601] | +0.010 [-0.022, +0.043] | yes |
| timing only | 30 | 0.510 [0.475, 0.546] | +0.064 [+0.015, +0.111] | no |
| counts and direction only | 26 | 0.497 [0.461, 0.533] | +0.076 [+0.028, +0.123] | no |
| first_request_bytes only | 1 | 0.375 [0.361, 0.388] | +0.199 [+0.155, +0.239] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.43 (share of the way from chance to perfect); severity medium.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (498 groups): macro-F1 0.577 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.249, max 0.300; verdicts on permuted labels: 0 LEAK, 67 NO LEAK, 32 INCONCLUSIVE.

- **pad-messages**: Message sizes carry the leak, beyond any single request. Pad streamed response events to fixed cells (defense=pad) as well as request bodies to buckets.

- **pad-local-posts**: This view also sees requests that are not padded, such as posts to a local service (in C2, the ticket service on the building network). Pad posts to local services too, then re-run the audit; the audit of a view without them shows what they add.

## escalated

**LEAK**: CI lower bound 1.000 > chance + margin 0.550.

500 samples in 498 groups; classes no 125, yes 375.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 1.000 [1.000, 1.000] | — | — |
| sizes only | 139 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |
| timing only | 30 | 0.997 [0.992, 1.000] | +0.003 [+0.000, +0.008] | yes |
| counts and direction only | 26 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |
| first_request_bytes only | 1 | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] | yes |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 1.00 (share of the way from chance to perfect); severity high.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (498 groups): macro-F1 1.000 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.499, max 0.554; verdicts on permuted labels: 0 LEAK, 57 NO LEAK, 42 INCONCLUSIVE.

- **hide-escalation**: Whether the edge called the cloud is visible from the connections themselves, and padding cannot hide a call that did or did not happen. Make every task look alike upstream: dummy cloud calls at a fixed rate (cover traffic), or send every task to the cloud. Then re-run the audit.

## cloud_role

**INCONCLUSIVE**: CI [0.545, 0.644] straddles chance + margin 0.550.

375 samples in 373 groups; classes diagnostics 250, knowledge 125.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.595 [0.545, 0.644] | — | — |
| sizes only | 139 | 0.576 [0.523, 0.625] | +0.019 [-0.026, +0.068] | no |
| timing only | 30 | 0.511 [0.463, 0.562] | +0.084 [+0.020, +0.145] | no |
| counts and direction only | 26 | 0.504 [0.455, 0.552] | +0.091 [+0.029, +0.152] | no |
| first_request_bytes only | 1 | 0.400 [0.383, 0.416] | +0.195 [+0.146, +0.245] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size 0.19 (share of the way from chance to perfect); severity none.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (373 groups): macro-F1 0.603 on the real labels): p = 0.010; permuted-label macro-F1 mean 0.501, max 0.571; verdicts on permuted labels: 0 LEAK, 46 NO LEAK, 53 INCONCLUSIVE.

- **inconclusive**: The interval straddles chance + margin: more traces will narrow it. Re-run before treating this attribute as safe.

## audit_null

**NO LEAK**: CI upper bound 0.262 <= chance + margin 0.300.

500 samples in 498 groups; classes a 123, b 134, c 123, d 120.

| Features | Dims | macro-F1 [95% CI] | All − this | Matches all |
|---|---|---|---|---|
| all | 195 | 0.225 [0.187, 0.262] | — | — |
| sizes only | 139 | 0.236 [0.198, 0.272] | -0.010 [-0.041, +0.020] | yes |
| timing only | 30 | 0.234 [0.198, 0.273] | -0.009 [-0.059, +0.039] | yes |
| counts and direction only | 26 | 0.252 [0.214, 0.291] | -0.027 [-0.078, +0.022] | yes |
| first_request_bytes only | 1 | 0.216 [0.181, 0.251] | +0.009 [-0.044, +0.059] | no |

A feature set matches all features when the upper bound of all − this is at most 0.05 (it is shown to be no more than that below all features).

Effect size -0.03 (share of the way from chance to perfect); severity none.

Permutation test (rf-light, 99 permutations, labels permuted by prompt group (498 groups): macro-F1 0.253 on the real labels): p = 0.470; permuted-label macro-F1 mean 0.251, max 0.318; verdicts on permuted labels: 0 LEAK, 69 NO LEAK, 30 INCONCLUSIVE.

## Against the baseline

Baseline: `data/results/leakcheck/c2b1_lan_padmax_v1/report.json`.

- cloud_role: LEAK → INCONCLUSIVE

**Needs review**: cloud_role (LEAK in the baseline, INCONCLUSIVE now: the leak is not shown to be gone).

## Runtime

132.7 s in all (collection 0.2 s, extraction 3.8 s, analysis 128.7 s); peak memory 270 MB in the main process, up to 263 MB in each of 14 worker processes.

| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|
| collection | 0.2 | 171 | — |
| extraction | 3.8 | 245 | — |
| analysis:task_type | 37.3 | 266 | 261 |
| analysis:escalated | 28.2 | 269 | 261 |
| analysis:cloud_role | 25.7 | 270 | 261 |
| analysis:audit_null | 36.3 | 270 | 263 |
