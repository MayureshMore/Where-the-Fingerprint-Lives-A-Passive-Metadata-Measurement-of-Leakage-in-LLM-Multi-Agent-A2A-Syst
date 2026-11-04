# C1: paper 1 revision checks

Collection C1, `data/processed_c1_own`; commit `da31192a`; seed 42. Measurement: own connections: only TCP connections whose SYN is in the trace (features/connections.py). GBT, the five prompt-group folds of scripts/evaluate_c1.py unless stated; macro-F1 with 95% cluster-bootstrap CIs.

## A10. Capture

Link type 0 (BSD loopback). Largest packet on the wire: request 9928 B, response 16388 B; largest TCP payload 16332 B, so the loopback MTU is 16384 B. Header bytes per packet: 56 B × 377779, 68 B × 4572, 44 B × 912.

TCP segments per first request: code_review 2: 135, 3: 15; data_analysis 2: 135, 3: 15; research_retrieval 2: 135, 3: 15; support_triage 2: 135, 3: 15.

## A2. First-request size against prompt size

first-request bytes = HTTP header record + body record; body = JSON-RPC envelope + 'Sub-task i of n' + the orchestrator's LLM-written sub-task plan + the prompt (agents/orchestrator.py:45-53); plan bytes estimated as body record − 22 B TLS overhead − the body built with an empty plan.

| Workflow | c_w (B) | Residual SD | Max residual | Free fit slope | Plan bytes, median [IQR] |
|---|---|---|---|---|---|
| code_review | 1085 | 199 | 784 | 1.002 | 476 [373, 599] |
| data_analysis | 977 | 144 | 1093 | 1.006 | 367 [304, 454] |
| research_retrieval | 1200 | 159 | 693 | 1.153 | 598 [516, 703] |
| support_triage | 1011 | 121 | 332 | 1.059 | 430 [359, 498] |

Per-trace table: `data/results/c1_first_request_traces.csv`; figure: `data/results/figures/c1_first_request_scatter.png`.

## A3. Response side only, on the length pairs (chance 0.5)

| Pair | n | Response side only | All features | All − response side |
|---|---|---|---|---|
| code_review vs data_analysis | 300 | 0.697 [0.638, 0.752] (81 dims) | 0.893 [0.847, 0.931] | +0.197 [+0.128, +0.263] |
| research_retrieval vs support_triage | 300 | 0.502 [0.445, 0.555] (81 dims) | 0.550 [0.475, 0.619] | +0.048 [-0.026, +0.124] (n.s.) |

## A6. Topology from call count and nesting (fixed rule, no ports or addresses)

Rule: no call nested in another → star; nested calls and at most 3 calls → chain; more than 3 → mesh. Accuracy 1.000 on 600 traces (macro-F1 1.000 [1.000, 1.000]).

| Topology | Observed shapes |
|---|---|
| chain | 3 calls, nesting 3: 200 |
| mesh | 5 calls, nesting 4: 200 |
| star | 3 calls, nesting 1: 200 |

## A5. k-FP's features with GBT

| Task | GBT, all 195 features | GBT, k-FP's 138 features | All − k-FP |
|---|---|---|---|
| role | 0.994 [0.990, 0.997] | 0.988 [0.982, 0.993] | +0.006 [+0.002, +0.011] |
| workflow | 0.660 [0.613, 0.703] | 0.511 [0.461, 0.556] | +0.148 [+0.106, +0.195] |
| topology | 1.000 [1.000, 1.000] | 0.998 [0.995, 1.000] | +0.002 [+0.000, +0.005] (n.s.) |

## A7. Role on held-out workflows and topologies

Grouped CV 0.994 [0.990, 0.997]; leave one workflow out 0.992 [0.988, 0.996] (per held-out workflow: code_review 1.000, data_analysis 0.984, research_retrieval 0.996, support_triage 0.989); leave one topology out 0.468 [0.437, 0.498] (chain 0.907, mesh 0.386, star 0.033).

## A8. Reply sizes per role

not logged: the agents never record Ollama's eval_count or done_reason, so the share of replies that hit the 256-token cap cannot be measured from C1.

| Role | n | Response bytes, median [IQR] | CV |
|---|---|---|---|
| executor | 600 | 25201 [23337, 162424] | 0.93 |
| retriever | 600 | 47422 [25198, 162802] | 0.78 |
| validator | 600 | 25200 [22854, 44812] | 0.41 |

## A4. Input padding, simulated

every request message (request writes on one connection ≤ 50 ms apart; TLS handshake records and alerts excluded) padded to its bucket and re-segmented at the capture's largest TCP payload (16332 B); timestamps and header sizes kept; responses and ACKs unchanged (a real sender would also trigger a few more ACKs). 600 of 600 unpadded trace vectors rebuilt from packet headers equal the stored features.

| Padding | Overhead | Workflow | Unpadded − padded (workflow) | Workflow, first request only | Role | Topology |
|---|---|---|---|---|---|---|
| none | 0.0% | 0.660 [0.613, 0.703] | — | 0.641 [0.589, 0.687] | 0.994 [0.990, 0.997] | 1.000 [1.000, 1.000] |
| linear_1KB | 0.8% | 0.552 [0.497, 0.600] | +0.108 [+0.070, +0.145] | 0.465 [0.399, 0.527] | 0.994 [0.990, 0.998] | 1.000 [1.000, 1.000] |
| pow2_from_1KB | 2.7% | 0.554 [0.506, 0.600] | +0.106 [+0.070, +0.144] | 0.324 [0.263, 0.387] | 0.993 [0.989, 0.997] | 1.000 [1.000, 1.000] |

## A9. Folds grouped by generator template

template = the generator's base element (code snippet, dataset, research question template, support ticket); prompts sharing one differ only in the ask or topic.

Templates per workflow: code_review 9, data_analysis 10, research_retrieval 9, support_triage 35; prompts: code_review 51, data_analysis 74, research_retrieval 62, support_triage 95; unmatched prompts 0.

Workflow GBT: grouped by template 0.604 [0.498, 0.658]; grouped by prompt 0.660 [0.613, 0.703]; prompt − template grouping +0.055 [+0.010, +0.105] (bootstrap over templates).
