# C1 reviewer follow-up (review 2)

Collection C1, data/processed_c1_own, own connections: only TCP connections whose SYN is in the trace (features/connections.py). Commit 5d92b8dd, seed 42. Analysis only; no new collection.

## B1. Prompt size from the first request, without the workflow

600 traces, the 5 prompt-group folds of evaluate_c1.py. The target is the prompt's bytes as JSON-encoded in the request (median 1237 B, range 101–6424 B). Errors are absolute, in bytes, on the test folds.

**constant**: one overhead c = median(first_request_bytes − prompt_json_bytes) on the training folds; prompt bytes = first_request_bytes − c (does not know the workflow).

| | n | Median AE | MAE | 90th pct | ≤100 B | ≤200 B | ≤300 B | Median relative error |
|---|---|---|---|---|---|---|---|---|
| all | 600 | 106 | 132 | 259 | 49% | 82% | 93% | 9.0% |
| code_review | 150 | 96 | 141 | 285 | 53% | 79% | 91% | 3.3% |
| data_analysis | 150 | 115 | 119 | 196 | 43% | 91% | 98% | 3.8% |
| research_retrieval | 150 | 136 | 175 | 342 | 37% | 65% | 87% | 44.3% |
| support_triage | 150 | 74 | 95 | 195 | 61% | 92% | 95% | 14.9% |

**linear**: least-squares prompt_json_bytes ~ a + b·first_request_bytes on the training folds (does not know the workflow).

| | n | Median AE | MAE | 90th pct | ≤100 B | ≤200 B | ≤300 B | Median relative error |
|---|---|---|---|---|---|---|---|---|
| all | 600 | 110 | 135 | 252 | 44% | 80% | 94% | 9.6% |
| code_review | 150 | 104 | 141 | 298 | 47% | 78% | 91% | 3.3% |
| data_analysis | 150 | 137 | 138 | 224 | 34% | 79% | 98% | 4.2% |
| research_retrieval | 150 | 117 | 156 | 315 | 42% | 73% | 89% | 41.6% |
| support_triage | 150 | 92 | 105 | 213 | 55% | 89% | 97% | 19.1% |

**per_workflow_constant**: reference only: c learned per workflow on the training folds and applied with the test trace's true workflow (knows the workflow).

| | n | Median AE | MAE | 90th pct | ≤100 B | ≤200 B | ≤300 B | Median relative error |
|---|---|---|---|---|---|---|---|---|
| all | 600 | 79 | 111 | 235 | 60% | 85% | 95% | 7.3% |
| code_review | 150 | 106 | 141 | 279 | 49% | 80% | 91% | 3.3% |
| data_analysis | 150 | 72 | 94 | 211 | 70% | 89% | 97% | 2.3% |
| research_retrieval | 150 | 89 | 119 | 229 | 55% | 82% | 95% | 33.2% |
| support_triage | 150 | 69 | 92 | 201 | 65% | 90% | 96% | 14.3% |

Learned overhead c per fold: 1038, 1032, 1040, 1040, 1040 B. Linear fit per fold: slope 1.000, intercept -1064; slope 1.000, intercept -1062; slope 0.997, intercept -1057; slope 0.995, intercept -1057; slope 0.998, intercept -1071.

## B2. Role, leave one topology out: confusion per held-out topology

train on two topologies, test on the third (evaluate_c1_revision.py A7); GBT on the role features. Rows are the true role, columns the predicted role (counts). Overall macro-F1 0.468 [0.437, 0.498].

**Held out: chain** (n = 600, macro-F1 0.907)

| true \ predicted | executor | retriever | validator | recall |
|---|---|---|---|---|
| executor | 157 | 42 | 1 | 78% |
| retriever | 0 | 188 | 12 | 94% |
| validator | 0 | 0 | 200 | 100% |

**Held out: mesh** (n = 600, macro-F1 0.386)

| true \ predicted | executor | retriever | validator | recall |
|---|---|---|---|---|
| executor | 200 | 0 | 0 | 100% |
| retriever | 73 | 13 | 114 | 6% |
| validator | 0 | 157 | 43 | 22% |

**Held out: star** (n = 600, macro-F1 0.033)

| true \ predicted | executor | retriever | validator | recall |
|---|---|---|---|---|
| executor | 0 | 0 | 200 | 0% |
| retriever | 0 | 1 | 199 | 0% |
| validator | 76 | 95 | 29 | 14% |

## B3. Padding simulation (c1_revision A4), confirmed from the code

- Padded trace vectors are recomputed: for each scheme, the padded packet list goes through FeatureExtractor._compute_features and role_vectors (evaluate_c1_revision.py padding()), and the unpadded rebuild matches the stored features for 600 of 600 traces.
- The GBT is retrained and tested on padded traffic: oof_predict fits each fold on the padded vectors of the training traces and predicts the padded vectors of the test traces; the folds are the same prompt-group folds as the unpadded run. Nothing is trained on unpadded traffic.
- Overhead = (padded wire bytes − unpadded wire bytes) / unpadded wire bytes, summed over every packet of each trace's own connections in both directions (handshakes, requests, responses, ACKs). Wire bytes are the captured frame length, so IP and TCP headers (and the loopback link header) are included, and each extra segment created by padding adds its own header.
