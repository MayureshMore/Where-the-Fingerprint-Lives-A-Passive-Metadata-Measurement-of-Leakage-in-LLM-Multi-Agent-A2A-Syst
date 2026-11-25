# Prompt registry

Every collection draws its prompts from the workflow generators (`workflows/`) with
`seed = topology_index × 4 + workflow_index + 100 + seed_offset` (`workflows.prompt_seed`), where
`workflow_index` is the workflow's position in its set. Register each collection's offsets here
before collecting, and report its overlap with every collection it will be compared with.
`prompt_group = sha1(prompt)[:8]` is the grouping key in every evaluation.

## Workflow sets

A collection draws all its workflows from one set (`collect_session.py --workflows`). Both sets
have the same design: two workflows with long task inputs and two with short ones.

| Set | Workflows (in index order) | Used by |
|---|---|---|
| `classic` | research_retrieval, code_review, data_analysis, support_triage | every collection up to C1; unchanged (its seeds and prompts are those of the original four-member registry, checked against C1's sidecars) |
| `iot` | sensor_analysis, fault_diagnosis, procedure_lookup, alert_triage | C2: an edge AI assistant for building and factory operations |

The IoT generators are synthetic: invented sites, assets, telemetry, logs and configurations, no
real or third-party data. Their template pools:

| Workflow | Input | Template pools |
|---|---|---|
| sensor_analysis | a telemetry window as CSV (8–110 rows), with one injected anomaly in most windows | 8 equipment kinds, 6 asks, 10 sites, 5 sample intervals, 6 anomaly patterns (none, spike, drift, step, stuck, dropout) |
| fault_diagnosis | a device log (30–80 lines) and a config excerpt | 6 device kinds, 18 fault scenarios, 5 asks, 10 sites, 30 routine log lines |
| procedure_lookup | a short maintenance or procedure question | 20 question templates, 4 prefixes; slots: 14 assets, 9 parts, 7 sensors, 8 locations, 7 tasks, 5 faults |
| alert_triage | a short alarm or occupant request | 5 alarm and 3 request templates, 5 asks; slots: 11 assets, 7 conditions, 5 faults, 9 locations, 10 complaints |

## The classic pool is small

Over 4,000 seeds the classic generators produce only this many distinct prompts per workflow, so a
new seed offset does **not** give prompts disjoint from earlier collections:

| Workflow | Distinct prompts (whole pool) |
|---|---|
| research_retrieval | 79 |
| code_review | 72 |
| data_analysis | 100 |
| support_triage | 175 |

Within one collection this is handled by grouping (cross-validation holds out whole prompt
groups). Across collections, transfers are cross-fitted (`evaluation/crossfit.py`). Collections
that must be prompt-disjoint from earlier ones need new templates first.

The IoT generators draw their content at random (telemetry values, log timelines, slot values), so
their pool is large: 4,000 seeds give 4,000 distinct sensor_analysis and fault_diagnosis prompts,
2,163 procedure_lookup and 3,531 alert_triage.

## Collections

| Collection | Seed offsets | Per condition | Script |
|---|---|---|---|
| Summer sets (`raw`, `raw_amodel_sdk`, `raw_b_sdk`, `raw_blogic_sdk`, `raw_langgraph`, defenses) | 0 | 50 | `collect_deployment.py` |
| `raw_wf_interleaved_full` | 1000, 2000, …, 6000 (one per cycle) | 6 per cycle | `collect_wf_interleaved.sh` |
| TLS control (`raw_tlspair_*`) | 1000 | 36 pairs | `collect_tls_session.py` |
| **C1** (`raw_c1`) | **10000** | 50 | `collect_session.py` |
| C1 pilot (`raw_c1_pilot`) | 10000 | 1 per topology | `collect_session.py --pilot` |
| **C2** edge-cloud: edge agent on the Raspberry Pi, cloud agents and ticket service on the Mac (`raw_c2`, `raw_c2_pad`, `raw_c2_padmax`; arms: no mitigation, pow2 input padding, input padding to one 8 KB bucket), **IoT set**, one condition per task type | **30000** | 250 (planned 150; `session_meta.json`: `--n 250`) | `collect_session.py --placement edge-cloud --workflows iot` (docs/LAN_SETUP.md) |
| C2 pilot (`raw_c2_pilot`, `raw_c2_pad_pilot`, `raw_c2_padmax_pilot`) | 30000 | 1 hour (`--deadline-hours 1`) | as C2 |
| C2 smoke test (Mac only, loopback, discarded) | 30000 | 3 per task type (items 0–2) | as C2, `--n 3 --rounds 1` |
| **C2B1** round 2, reply shaping (`raw_c2b1_padmax`, `raw_c2b1_shaped`), IoT set | **31000** | 125 | as C2 (docs/ROUND2_SESSIONS.md) |
| C2B1 pilots (`pilot_c2b1`, before TCP_NODELAY on the shaped arm, and `pilot2_c2b1`; each `padmax`, `shaped`; checks only, not analysed) | 31000 | 5 per task type (items 0–4), `--n 5 --rounds 1` | as C2B1 |
| **C2B1X** round 2, more shaped traces for sensor vs fault (`raw_c2b1x_shaped`), IoT set | **31000**, from position 125 | 500 | as C2B1, `--prompt-start 125 --exclude-prompts` C2's and B1's folders (docs/ROUND2_SESSIONS.md) |
| C2B1X pilot (`pilot_c2b1x/shaped`, stopped by the guard at the start because the WAN was off, and `pilot2_c2b1x/shaped`; checks only, not analysed) | 31000, from position 125 | 5 per task type (C2B1X's first 5) | as C2B1X, `--n 5 --rounds 1` |
| **C2B2** round 2, jitter and server load (`raw_c2b2_lan`, `raw_c2b2_jl`), IoT set | **32000** | 125 | as C2 (docs/ROUND2_SESSIONS.md) |
| **C2B3** round 2, a second day of `lan` (`raw_c2b3_lan`), IoT set | **33000** | 250 | as C2 (docs/ROUND2_SESSIONS.md) |
| **C2B1M** round 2, matched held-out shaping (`raw_c2b1m_padmax`, `raw_c2b1m_shaped`), sensor_analysis and fault_diagnosis only | **34000** | 625 (the control arm 250 of them, spread evenly, on the same prompts) | as C2B1, `--workflows sensor_analysis,fault_diagnosis --exclude-prompts` C2's, C2B1's, C2B1X's and C2B3's folders (docs/PREREG_C2B1M.md) |
| C2B1M pilot (`pilot_c2b1m/padmax`, `pilot_c2b1m/shaped`; checks only, not analysed) | 34000 | 10 per task type (C2B1M's first 10; the control 4 of them) | as C2B1M, `--n 10 --rounds 1`, control `n=4` |
| Round-2 loopback dry run (stand-in Ollama, discarded) | 99000 | 2 per task type | as C2, `--n 2 --rounds 1` |
| *Superseded C2 design* (orchestrator on the Mac, specialists on the Pi; never collected) | 20000 | — | only two discarded loopback smoke tests (Nov 6) used it |

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

## C2 prompts (IoT set, measured before collection)

C2 draws 150 prompts per task type (seed offset 30000; one condition per task type, so
`workflows.prompt_seed` with topology index 0). Prompt length in bytes:

| Task type | Distinct of 150 | Median | Min | Max |
|---|---|---|---|---|
| sensor_analysis | 150 | 2988 | 573 | 5238 |
| fault_diagnosis | 150 | 3681 | 2040 | 5310 |
| procedure_lookup | 145 | 81 | 48 | 124 |
| alert_triage | 150 | 153 | 124 | 185 |

None of these prompts occurs in any earlier collection (checked against the sidecars of all
`data/raw*` folders).

Round 2 (measured before collection, against C2's draw and the sidecars of all `data/raw*`
folders): sensor_analysis and fault_diagnosis prompts occur nowhere else. The small
procedure_lookup and alert_triage pools repeat a few:

| Session (offset, per type) | procedure_lookup: distinct, also in C2 | alert_triage: distinct, also in C2 |
|---|---|---|
| C2B1 (31000, 125) | 123, 18 | 125, 2 |
| C2B2 (32000, 125) | 118, 14 | 125, 3 |
| C2B3 (33000, 250) | 234, 23 | 244, 4 |

C2B1M (34000, 625 per type, sensor_analysis and fault_diagnosis only), measured on Nov 25 before
the session with `collect_session.select_prompts` against the 4,350 prompts in the sidecars of C2,
C2B1, C2B1X and C2B3: positions 0 to 624 for both types, 0 skipped as used, 0 as repeats, 625
distinct each.

`scripts/evaluate_cross_session.py` drops the B3 test traces whose prompt also occurs in C2.

C2B1X shares no prompt with C2 or B1: it continues B1's offset-31000 sequence from position 125 and
skips every prompt in their sidecars and every repeat (session_meta.json `prompt_selection`).
sensor_analysis and fault_diagnosis take positions 125–624 with nothing skipped; procedure_lookup
takes 125–810, skipping 122 used and 64 repeats; alert_triage takes 125–661, skipping 27 and 10.
In the collected sidecars (Nov 22), the 2,000 prompts are distinct and none is among the 1,460
distinct prompts of C2's and B1's folders. Eleven procedure_lookup questions also occur in the offset-20000 draw of the
superseded design, which was never collected (only its discarded smoke tests used items 0 of each
condition).
