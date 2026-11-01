# Prompt registry

Every collection draws its prompts from the workflow generators (`workflows/`) with
`seed = topology_index × 4 + workflow_index + 100 + seed_offset`. Register each collection's
offsets here before collecting, and report its overlap with every collection it will be
compared with. `prompt_group = sha1(prompt)[:8]` is the grouping key in every evaluation.

## The pool is small

Over 4,000 seeds the generators produce only this many distinct prompts per workflow, so a new
seed offset does **not** give prompts disjoint from earlier collections:

| Workflow | Distinct prompts (whole pool) |
|---|---|
| research_retrieval | 79 |
| code_review | 72 |
| data_analysis | 100 |
| support_triage | 175 |

Within one collection this is handled by grouping (cross-validation holds out whole prompt
groups). Across collections, transfers are cross-fitted (`evaluation/crossfit.py`). Collections
that must be prompt-disjoint from earlier ones need new templates first.

## Collections

| Collection | Seed offsets | Per condition | Script |
|---|---|---|---|
| Summer sets (`raw`, `raw_amodel_sdk`, `raw_b_sdk`, `raw_blogic_sdk`, `raw_langgraph`, defenses) | 0 | 50 | `collect_deployment.py` |
| `raw_wf_interleaved_full` | 1000, 2000, …, 6000 (one per cycle) | 6 per cycle | `collect_wf_interleaved.sh` |
| TLS control (`raw_tlspair_*`) | 1000 | 36 pairs | `collect_tls_session.py` |
| **C1** (`raw_c1`) | **10000** | 50 | `collect_session.py` |
| C1 pilot (`raw_c1_pilot`) | 10000 | 1 per topology | `collect_session.py --pilot` |

## C1 overlap (measured before collection)

Distinct prompts C1 draws per workflow (150 traces each), and how many of those also occur in
the TLS control and in `raw_wf_interleaved_full`:

| Workflow | C1 distinct | Also in TLS control | Also in `raw_wf_interleaved_full` |
|---|---|---|---|
| research_retrieval | 62 | 34 (55%) | 37 (60%) |
| code_review | 51 | 37 (73%) | 41 (80%) |
| data_analysis | 74 | 52 (70%) | 50 (68%) |
| support_triage | 95 | 45 (47%) | 48 (51%) |

C1 results are within-collection (grouped CV, temporal holdout with test-round prompts removed
from training), so the overlap does not leak into them. Any transfer between C1 and another
collection must be cross-fitted.
