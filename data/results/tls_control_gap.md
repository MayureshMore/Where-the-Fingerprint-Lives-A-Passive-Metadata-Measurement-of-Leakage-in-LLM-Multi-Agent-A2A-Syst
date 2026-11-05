# Why all features beat the first request on the TLS control but not on C1

Commit `d2302703`; GBT, 5-fold StratifiedGroupKFold by prompt group, seed 42; 95% cluster-bootstrap CIs.

## 1. Workflow that ran last on the same agent ports

A capture starts while the previous trace's connections on the same ports are still closing.

| Workflow | C1 | TLS control, TLS arm | TLS control, cleartext arm |
|---|---|---|---|
| code_review | research_retrieval 30%, support_triage 27%, code_review 21%, data_analysis 21% | research_retrieval 100% | research_retrieval 100% |
| data_analysis | support_triage 31%, code_review 26%, data_analysis 24%, research_retrieval 19% | code_review 100% | code_review 100% |
| research_retrieval | data_analysis 28%, research_retrieval 27%, support_triage 22%, code_review 21% | support_triage 97%, none 3% | support_triage 97%, none 3% |
| support_triage | code_review 31%, data_analysis 27%, research_retrieval 24%, support_triage 19% | data_analysis 100% | data_analysis 100% |

## 2. Per specialist, research retrieval vs support triage (median; AUC)

| Specialist feature | C1 | TLS control, TLS arm | TLS control, cleartext arm |
|---|---|---|---|
| executor.bytes_out | 25817 vs 24621.5; 0.56 | 26722.5 vs 24897.5; 0.56 | 22901 vs 22822; 0.53 |
| executor.duration_s | 9.91134 vs 10.0299; 0.48 | 8.92462 vs 9.00697; 0.51 | 8.96659 vs 9.00065; 0.53 |
| executor.n_response_bursts | 45 vs 43.5; 0.56 | 46.5 vs 43.5; 0.55 | 44 vs 43; 0.53 |
| retriever.bytes_out | 47455 vs 46574; 0.51 | 48467.5 vs 47517.5; 0.51 | 43270 vs 41583; 0.51 |
| retriever.duration_s | 9.88895 vs 10.0277; 0.48 | 8.90907 vs 9.00061; 0.47 | 8.96543 vs 8.99785; 0.48 |
| retriever.n_response_bursts | 85 vs 83.5; 0.51 | 87 vs 85; 0.54 | 83 vs 81; 0.52 |
| validator.bytes_out | 25895 vs 24179; 0.54 | 26542 vs 24643; 0.56 | 22840 vs 22275; 0.57 |
| validator.duration_s | 9.66924 vs 9.87753; 0.48 | 8.87703 vs 8.82708; 0.51 | 8.80853 vs 8.83429; 0.51 |
| validator.n_response_bursts | 46 vs 44; 0.54 | 48 vs 44; 0.57 | 44 vs 43; 0.58 |

## 3. Trace features that best separate research retrieval from support triage on the TLS arm (AUC; 0.5 = none)

| Feature | C1 | TLS control, TLS arm | TLS control, cleartext arm |
|---|---|---|---|
| sys.pf_mean_p75_sz_in | 0.49 | 0.78 | 0.50 |
| pf_mean.p75_sz_in | 0.49 | 0.78 | 0.50 |
| sys.pf_mean_cumul_bytes_q0 | 0.49 | 0.73 | 0.48 |
| pf_mean.cumul_bytes_q0 | 0.49 | 0.73 | 0.48 |
| sys.pf_std_p25_sz_in | 0.50 | 0.31 | 0.50 |
| sys.pf_mean_p25_sz_in | 0.50 | 0.68 | 0.50 |
| pf_mean.p25_sz_in | 0.50 | 0.68 | 0.50 |
| sys.pf_std_bytes_out_ratio | 0.48 | 0.32 | 0.50 |
| sys.min_flow_bytes_out_ratio | 0.51 | 0.67 | 0.52 |
| sys.pf_std_p75_sz_in | 0.52 | 0.34 | 0.50 |
| sys.pf_mean_mean_iat | 0.48 | 0.66 | 0.62 |
| pf_mean.mean_iat | 0.48 | 0.66 | 0.62 |

Largest separation of any single feature (|AUC − 0.5|): C1 0.064, TLS control, TLS arm 0.284, TLS control, cleartext arm 0.116.

## 4. Only the connections a trace opens itself

| Set | Leftover flows per trace | All features | All, own connections | First request | All − own | Own − first |
|---|---|---|---|---|---|---|
| C1 | 1.30 (58% of traces) | 0.626 [0.572, 0.672] | 0.660 [0.613, 0.703] | 0.641 [0.589, 0.687] | -0.034 [-0.066, +0.000] (n.s.) | +0.018 [-0.033, +0.070] (n.s.) |
| TLS control, TLS arm | 1.42 (65% of traces) | 0.741 [0.689, 0.786] | 0.613 [0.558, 0.662] | 0.582 [0.516, 0.643] | +0.128 [+0.084, +0.171] | +0.030 [-0.030, +0.089] (n.s.) |
| TLS control, cleartext arm | 1.44 (65% of traces) | 0.677 [0.625, 0.720] | 0.659 [0.603, 0.708] | 0.590 [0.529, 0.644] | +0.017 [-0.024, +0.058] (n.s.) | +0.069 [+0.003, +0.127] |

Per-class F1, all features → own connections only:

- C1: code_review 0.682 → 0.701, data_analysis 0.838 → 0.895, research_retrieval 0.432 → 0.490, support_triage 0.551 → 0.553
- TLS control, TLS arm: code_review 0.710 → 0.676, data_analysis 0.815 → 0.811, research_retrieval 0.750 → 0.453, support_triage 0.688 → 0.511
- TLS control, cleartext arm: code_review 0.710 → 0.725, data_analysis 0.864 → 0.891, research_retrieval 0.547 → 0.495, support_triage 0.585 → 0.525

## 5. Which leftover packets move the features

Wire sizes are on the loopback capture (4 B link header): a header-only ACK or FIN with TCP timestamps is 56 B, a caller RST without options 44 B, an ACK with SACK blocks 68 B, and a TLS 1.3 close_notify alert record 24 B of payload (80 B on the wire).

Leftover packets per workflow (packets in all traces of that workflow; direction, TCP flags, wire size):

| Workflow | C1 | TLS control, TLS arm | TLS control, cleartext arm |
|---|---|---|---|
| code_review | request FA 56 B ×207, response A 56 B ×207, request RA 44 B ×133, response PA 80 B (payload 24 B) ×94, request A 56 B ×65, request A 68 B ×29, response FA 56 B ×1 | request FA 56 B ×162, response A 56 B ×162, request RA 44 B ×162 | request FA 56 B ×163, response A 56 B ×163 |
| data_analysis | request FA 56 B ×181, response A 56 B ×181, request RA 44 B ×119, response PA 80 B (payload 24 B) ×104, request A 56 B ×83, request A 68 B ×30, response FA 56 B ×7, response RA 44 B ×2 | request FA 56 B ×152, response A 56 B ×152, request RA 44 B ×152 | request FA 56 B ×154, response A 56 B ×154 |
| research_retrieval | request FA 56 B ×190, response A 56 B ×190, request RA 44 B ×132, response PA 80 B (payload 24 B) ×96, request A 56 B ×67, request A 68 B ×31, response FA 56 B ×6 | request FA 56 B ×152, response A 56 B ×152, response PA 80 B (payload 24 B) ×120, request RA 44 B ×112, request A 56 B ×77, request A 68 B ×37, response FA 56 B ×1 | request FA 56 B ×154, response A 56 B ×154, response FA 56 B ×70, request A 56 B ×70 |
| support_triage | request FA 56 B ×198, response A 56 B ×198, request RA 44 B ×129, response PA 80 B (payload 24 B) ×98, request A 56 B ×73, request A 68 B ×27, response FA 56 B ×3, response RA 44 B ×1 | request FA 56 B ×149, response A 56 B ×149, request RA 44 B ×149 | request FA 56 B ×152, response A 56 B ×152 |

Traces whose leftover connections include a caller RST / an agent close_notify (of traces with leftover packets):

| Workflow | C1 | TLS control, TLS arm | TLS control, cleartext arm |
|---|---|---|---|
| code_review | 58 / 27 of 92 | 72 / 0 of 72 | 0 / 0 of 72 |
| data_analysis | 57 / 36 of 84 | 72 / 0 of 72 | 0 / 0 of 72 |
| research_retrieval | 59 / 28 of 84 | 51 / 36 of 66 | 0 / 0 of 66 |
| support_triage | 61 / 32 of 91 | 72 / 0 of 72 | 0 / 0 of 72 |

Request-size 75th percentile of each leftover flow (wire bytes: number of leftover flows); own flows almost always sit at 56 B, the header-only ACK that dominates a flow's request direction:

| Workflow | C1 | TLS control, TLS arm | TLS control, cleartext arm |
|---|---|---|---|
| code_review | 53 B: 69, 56 B: 109, 59 B: 29 | 53 B: 162 | 56 B: 163 |
| data_analysis | 53 B: 43, 56 B: 108, 59 B: 30 | 53 B: 152 | 56 B: 154 |
| research_retrieval | 53 B: 71, 56 B: 88, 59 B: 31 | 53 B: 35, 56 B: 80, 59 B: 36, 62 B: 1 | 56 B: 154 |
| support_triage | 53 B: 59, 56 B: 112, 59 B: 27 | 53 B: 149 | 56 B: 152 |

`pf_mean.p75_sz_in` (mean per workflow; research retrieval vs support triage AUC) and GBT workflow macro-F1, with only the leftover packets of one direction put back on top of own connections; paired difference to own connections only:

| Set | Measurement | code_review | data_analysis | research_retrieval | support_triage | AUC RR/ST | Workflow macro-F1 | − own |
|---|---|---|---|---|---|---|---|---|
| C1 | own connections only | 56.00 | 56.00 | 56.00 | 56.00 | 0.50 | 0.660 [0.613, 0.703] |  |
| C1 | all connections | 55.86 | 55.80 | 55.86 | 55.82 | 0.49 | 0.626 [0.572, 0.672] | -0.034 [-0.066, +0.000] (n.s.) |
| C1 | own + leftover request-direction packets (caller -> agent) | 55.86 | 55.95 | 55.86 | 55.89 | 0.49 | 0.634 [0.581, 0.680] | -0.026 [-0.059, +0.009] (n.s.) |
| C1 | own + leftover response-direction packets (agent -> caller) | 42.78 | 44.14 | 44.32 | 43.58 | 0.51 | 0.595 [0.543, 0.639] | -0.065 [-0.102, -0.029] |
| TLS control, TLS arm | own connections only | 56.00 | 56.00 | 57.55 | 56.00 | 0.50 | 0.613 [0.558, 0.662] |  |
| TLS control, TLS arm | all connections | 55.23 | 55.25 | 57.55 | 55.28 | 0.78 | 0.741 [0.689, 0.786] | +0.128 [+0.084, +0.171] |
| TLS control, TLS arm | own + leftover request-direction packets (caller -> agent) | 55.23 | 55.25 | 57.55 | 55.28 | 0.78 | 0.746 [0.694, 0.794] | +0.133 [+0.084, +0.180] |
| TLS control, TLS arm | own + leftover response-direction packets (agent -> caller) | 41.64 | 42.04 | 44.44 | 42.60 | 0.47 | 0.702 [0.649, 0.748] | +0.090 [+0.046, +0.130] |
| TLS control, cleartext arm | own connections only | 56.00 | 56.00 | 56.00 | 56.00 | 0.50 | 0.659 [0.603, 0.708] |  |
| TLS control, cleartext arm | all connections | 56.00 | 56.00 | 56.00 | 56.00 | 0.50 | 0.677 [0.625, 0.720] | +0.017 [-0.024, +0.058] (n.s.) |
| TLS control, cleartext arm | own + leftover request-direction packets (caller -> agent) | 56.00 | 56.00 | 56.00 | 56.00 | 0.50 | 0.666 [0.614, 0.710] | +0.006 [-0.036, +0.050] (n.s.) |
| TLS control, cleartext arm | own + leftover response-direction packets (agent -> caller) | 41.63 | 42.02 | 42.83 | 42.53 | 0.48 | 0.652 [0.601, 0.698] | -0.007 [-0.049, +0.037] (n.s.) |

Mechanism. The 24 B close_notify alerts travel agent → caller (response direction), so they cannot move request-size features. With only the leftover response-direction packets put back (close_notify alerts, the agent's ACKs and FINs), every leftover flow adds a request size of 0 to the mean over flows: `pf_mean.p75_sz_in` falls for all workflows alike (41.6–44.4 B) and separates research retrieval from support triage at AUC 0.47. With only the caller's leftover packets put back (header-only ACKs, FINs and RSTs), AUC is 0.78, as with every leftover packet (0.78). Every own flow's request direction is dominated by 56 B header-only ACKs, so its 75th percentile is almost always 56 B. A leftover connection the caller ends with a FIN (56 B) and an RST (44 B) has a lower percentile and pulls the trace mean down: for code_review 56.00 → 55.23 B, data_analysis 56.00 → 55.25 B, support_triage 56.00 → 55.28 B. The connections left by support triage, the fixed predecessor of research retrieval, end differently: in 36 of 66 research retrieval traces with leftovers the agent closes with close_notify and the caller answers with ACKs (56 B, 68 B with SACK blocks), keeping that flow's percentile at or above 56 B, so research retrieval stays at 57.55 B (57.55 B on own connections). No other workflow's leftovers on the TLS arm contain a close_notify (0, 0, 0 traces).

Both directions carry the predecessor. On the TLS arm, workflow macro-F1 rises over own connections by +0.133 [+0.084, +0.180] with the caller's leftover packets, +0.090 [+0.046, +0.130] with the agent's (the close_notify itself marks research retrieval) and +0.128 [+0.084, +0.171] with both. On the cleartext arm the leftover connections end with FINs and ACKs only (caller RSTs in 0 traces, close_notify in none); `pf_mean.p75_sz_in` separates at AUC 0.50 and all − own is +0.017 [-0.024, +0.058] (n.s.).

Conclusion: removing leftover connections removes the effect (section 4).
