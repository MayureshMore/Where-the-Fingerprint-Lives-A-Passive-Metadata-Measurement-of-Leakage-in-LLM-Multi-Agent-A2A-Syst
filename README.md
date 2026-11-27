# Passive inference of topology, roles and workflows in LLM multi-agent systems from encrypted traffic

> **SafeIoT Track 1 reviewers start here.** Paper 2 is **a2a-leakcheck**; the rest of this README before
> [Paper 2](#paper-2-safeiot-track-1-a2a-leakcheck) is about paper 1 and can be skipped.
>
> | To | Run or read | Time |
> |---|---|---|
> | Install the tool alone (Python 3.11 to 3.13, no GPU) | `python3 -m venv venv-leakcheck && venv-leakcheck/bin/pip install -r requirements-leakcheck.txt` | 1 min |
> | See it work: the C2 examples audited, the HTML report, the CI gate failing a build on a new leak | `PYTHON=venv-leakcheck/bin/python bash scripts/demo_paper2.sh` | under 1 min |
> | Run the pipeline contribution: the five folders laid out as [safeiot-vuln-pipeline](https://github.com/systemsecurity-uiuc/safeiot-vuln-pipeline) expects, from the Zenodo download to a report | [`safeiot/`](safeiot/README.md): `bash safeiot/pipeline_harness/a2a-leakcheck/run.sh` | about 4 min |
> | Find any number in the paper: its file and field | [docs/PAPER2_NUMBERS.md](docs/PAPER2_NUMBERS.md) | |
> | Rebuild the paper's numbers from the released data and compare each with the committed one; it stops and names any missing archive | `bash scripts/reproduce_paper2.sh --section c2b1m,c2b2` (the two pre-registered sessions), `--section d3,b3` (shaping and the second day), `--quick` (every section's fast part), or no option (everything) | 1 h, 2 h, 6 h, about two days |
>
> Data: Zenodo [doi:10.5281/zenodo.24238558](https://doi.org/10.5281/zenodo.24238558) (all versions;
> D3 and B3 from version 1.1, C2B1M and C2B2 from version 1.2), header-only captures; checksums in
> [DATA.md](DATA.md). The tool's
> manual: [docs/LEAKCHECK.md](docs/LEAKCHECK.md).

Code, testbed, data pipeline and frozen results for three papers on what a passive observer learns
from the **metadata** of encrypted agent-to-agent traffic (packet sizes, timing and direction,
never payloads) in LLM multi-agent systems built on the official
[Agent2Agent (A2A)](https://a2a-protocol.org/latest/specification/) SDK, and for **a2a-leakcheck**,
a tool that audits a deployment's captures for that leakage.

| | Paper | Data | Here |
|---|---|---|---|
| 1 | EDI 2027 (*Procedia Computer Science*) | C1 | [Paper 1](#paper-1-edi-2027-task-input-sizes-leak-through-tls) |
| 2 | SafeIoT Hackathon, Track 1 (IoT vulnerability detection) | C2 and the TLS control (D1) | [Paper 2](#paper-2-safeiot-track-1-a2a-leakcheck) |
| 3 | in progress | new collections | [Paper 3](#paper-3-in-progress) |

Scores below are macro-F1 with 95% cluster-bootstrap CIs over prompt groups unless a row says
otherwise (recall and false-positive rates carry their own 95% CIs), read from the committed files
in [`data/results/`](data/results/), the single source of truth.

- **New here?** [START_HERE.md](START_HERE.md): one command per step, install to reproduce.
- **Every result, with its scope and whether it is still valid:** [RESULTS.md](RESULTS.md).
- **Rebuild everything from scratch** (datasets to results): [RECREATE.md](RECREATE.md).
- **Data archives and checksums:** [DATA.md](DATA.md).

---

## Paper 1 (EDI 2027): task input sizes leak through TLS

*What TLS leaves on the wire: task input sizes leak from encrypted agent-to-agent traffic in
industrial LLM multi-agent systems.* Collection C1: deployment A (four agents, llama3.2:3b), TLS 1.3
on every agent link, 600 traces in one session (50 per topology × workflow, five balanced rounds),
each trace measured on the TCP connections it opens itself. GBT on five prompt-group folds:

| Result | Macro-F1 [95% CI] | Chance | Source |
|---|---|---|---|
| Role (1,800 agent samples) | **0.994** [0.990, 0.997] | 0.333 | `c1_evaluation_own.md` |
| Workflow (600 traces) | **0.660** [0.613, 0.703] | 0.250 | `c1_evaluation_own.md` |
| Topology: a structural baseline, readable from the connection graph | 1.000 [1.000, 1.000] | 0.333 | `c1_evaluation_own.md` |
| Workflow from the size of the first request alone, not distinguishable from all 195 features | 0.641 [0.589, 0.687] | 0.250 | `c1_revision.md` |
| Workflow with requests padded to power-of-two buckets from 1 KB (simulated, 2.7% more bytes); the first request alone falls to 0.324 | 0.554 [0.506, 0.600] | 0.250 | `c1_revision.md` |

**Data:** Zenodo [doi:10.5281/zenodo.23938311](https://doi.org/10.5281/zenodo.23938311) (version
1.1; files and checksums in [DATA.md](DATA.md#paper-1-archive-collection-c1)). Unzip
`c1-raw-pcaps-headers-only.zip` and `c1-features-own.zip` into the repository root, then:

```bash
A2A_RESULTS_DIR=data/results_p1 python scripts/evaluate_c1.py
python scripts/evaluate_c1_revision.py
```

`evaluate_c1.py` writes to `$A2A_RESULTS_DIR` (by default `data/results/`, so set it);
`evaluate_c1_revision.py` always writes to `data/results/`, so run it in a separate clone and
compare with `git diff`. The full analysis is in [RESULTS.md](RESULTS.md#p1-collection-c1--deployment-a-over-tls-13-one-session-paper-1).

---

## Paper 2 (SafeIoT Track 1): a2a-leakcheck

*a2a-leakcheck: Auditing Encrypted Agent-to-Agent Traffic for Metadata Leakage in Edge-AI
Deployments.* Given one header-only capture per task and a label sidecar, a2a-leakcheck answers
LEAK, NO LEAK or INCONCLUSIVE for each attribute, with a confidence interval, a label-permutation
test, the feature family that carries the leak and a mitigation hint ([full usage](#leak-audit-a2a-leakcheck),
[docs/LEAKCHECK.md](docs/LEAKCHECK.md)).

**Quick start** (Python 3.11 or newer, no PyTorch):

```bash
python3 -m venv venv-leakcheck && venv-leakcheck/bin/pip install -r requirements-leakcheck.txt
venv-leakcheck/bin/python -m a2a_leakcheck run examples/c2_lan --vantage v2 --attributes task_type --html --out /tmp/c2_lan
PYTHON=venv-leakcheck/bin/python bash scripts/demo_paper2.sh
```

`demo_paper2.sh` audits the C2 examples without and with padding, writes the HTML reports and
shows the CI gate (exit code 3 on a new LEAK; exit codes and `--strict` in
[docs/LEAKCHECK.md](docs/LEAKCHECK.md#exit-codes-and-the-release-policy)).

**SafeIoT pipeline:** [safeiot/](safeiot/README.md) holds the tool laid out as the
[safeiot-vuln-pipeline](https://github.com/systemsecurity-uiuc/safeiot-vuln-pipeline) expects (stages
1 to 4 and a harness); `pipeline_harness/a2a-leakcheck/run.sh` goes from a fresh clone of that
repository to a report in about 4 minutes. Submitted upstream as
[safeiot-vuln-pipeline#1](https://github.com/systemsecurity-uiuc/safeiot-vuln-pipeline/pull/1)
(Nov 25, the five folders as of commit `c38e7728`).

**Headline numbers** (a2a-leakcheck 0.3.0: the permutation test by prompt group, "matches all
features" as non-inferiority; every number in the paper and its file:
[docs/PAPER2_NUMBERS.md](docs/PAPER2_NUMBERS.md)):

| Data | Result | File |
|---|---|---|
| C2 (D2): an edge-cloud deployment, 3,000 traces (1,000 per padding level: none, power of two, 8 KB); the edge agent on a Raspberry Pi 5 gateway; observed on the building network (v1) and upstream (v2) | all 18 learned leaks (task type, sensor vs fault, the escalated task types; 6 cells each) and all 12 structural checks (escalated, cloud role) read LEAK; no LEAK on 486 known non-leaks (480 audits with labels permuted by prompt group, 6 injected `audit_null` labels); its permutation test rejects in 24 of the 480 (5.0%); 0 of 120 permuted four-attribute audits would block a release [0, 0.031], 54 (0.45) hold an INCONCLUSIVE to review | `paper2_round2.json`: `sections.a12`, `sections.a11.methods` |
| Baselines in the same verdict rule | k-FP finds the same 18 and 12; the first-request size alone misses 8 of the 18 learned leaks | `paper2_round2.json`: `sections.a12.learned_by_task` |
| C2 with every cloud request padded to 8 KB | the task type still leaks, through timing: 0.90 [0.88, 0.92] at v1, 0.89 [0.87, 0.91] at v2 (the first request alone 0.38); sensor vs fault, served by the same cloud agent, 0.77 and 0.79; `escalated` stays 1.00 upstream | `paper2_round2.json`: `sections.a7`, `sections.a3.learned`; `leakcheck/c2_lan_padmax_v2/report.json` |
| D3 (C2B1 + C2B1X): 8 KB requests plus a reference reply-shaping defence (one reply size, one release time), 625 traces per class pooled over both shaped sessions | sensor vs fault reads NO LEAK upstream for the primary detector, 0.514 [0.485, 0.540], p 0.26, and the CI gate (`--baseline` against the padded arm) lists it as resolved; timing alone scores 0.539 [0.510, 0.569], across the 0.55 bound, so this is a large reduction, not proof the leak is closed; on the building network INCONCLUSIVE, 0.544 [0.517, 0.571], p 0.01, since v1 also sees the unpadded ticket post; `escalated` stays LEAK, 1.00. An escalated task's trace shrinks from 163.2 to 32.4 KB and takes 7.4 to 10.8 s longer | `b1_pair_pooled.json` (timing: `leakcheck/c2b1_c2b1x_lan_shaped_v2_pair/report.json`), `b1_audits.json`, `b1_shaping_overhead.json`, `c2b1x_shaping_overhead.json` |
| B3 (C2B3): C2's unpadded arm again on another day, 1,000 traces, new prompts | the same verdicts as C2 in 12 of 12 cells, macro-F1 within 0.024; trained on one session and tested on the other, every verdict holds but the learned tasks lose 0.08 to 0.27 (sensor vs fault 0.66 to 0.73) | `b3_audits.json`, `b3_cross_session_*.json` |
| D1: the TLS control (paired cleartext and TLS arms, 864 traces) | LEAK for role, workflow and topology in both arms (0.58 to 1.00); TLS changes no verdict | `leakcheck/tls_control_*_own/report.json` |
| Traces an auditor needs | LEAK from 20 per class (v1.0 evaluation: recall 1.00 on C2's task type, escalated and cloud role); NO LEAK is harder: with no signal, a two-class attribute stays INCONCLUSIVE in 12 of 20 draws at 125 per class and 5 of 20 at 375 | `paper2_tool_eval_c2.json`: `summary.sample_size`; `b1_power.json`: `measured`, `pooled_check` |
| Cost of a four-attribute audit (one C2 arm and view, 1,000 traces) | 230 s on a laptop with 14 workers (0.3.0); 26 min 38 s on the Raspberry Pi 5 with 4 workers (0.1.0) | `leakcheck/c2_lan_v1_v030_cost/report.json`; `leakcheck_pi/time_c2_lan_v1.txt` |

D1 is measured as a2a-leakcheck measures, every payload byte counted once. Its TLS − cleartext
workflow difference is −0.083 [−0.137, −0.025] that way and −0.046 [−0.105, +0.015] with TCP
retransmissions counted ([`d1_dedup_comparison.md`](data/results/d1_dedup_comparison.md)); paper 2
reports both and does not claim that TLS lowers workflow leakage.

**Data:** Zenodo [doi:10.5281/zenodo.24238558](https://doi.org/10.5281/zenodo.24238558) (all
versions): version 1.0, [doi:10.5281/zenodo.24238559](https://doi.org/10.5281/zenodo.24238559), holds
C2 and D1 (files and checksums in [DATA.md](DATA.md#paper-2-archive-collections-c2-and-the-tls-control));
version 1.1, [doi:10.5281/zenodo.24542790](https://doi.org/10.5281/zenodo.24542790), adds D3 (C2B1,
C2B1X) and B3 (C2B3) ([DATA.md](DATA.md#paper-2-archive-version-11-d3-and-b3-collections-c2b1-c2b1x-and-c2b3));
version 1.2, [doi:10.5281/zenodo.24582646](https://doi.org/10.5281/zenodo.24582646), adds the two
pre-registered sessions, C2B1M and C2B2 ([DATA.md](DATA.md#paper-2-archive-version-12-collections-c2b1m-and-c2b2)). Unzip the archives into the repository root, then
`bash scripts/reproduce_paper2.sh` rebuilds the paper's numbers and compares each with the committed
one, in six sections:
- the v1.0 path (the numbers made with 0.1.x's permutation test by sample);
- round 2, D3 and B3 (`--section d3,b3`: about 2 h);
- the two pre-registered sessions, C2B1M and C2B2, from version 1.2 (`--section c2b1m,c2b2`: about 1 h).

`--quick` runs every section's fast part, about 6 h; everything takes about two days. A missing
archive stops it, with the list, before anything runs.

---

## Paper 3: in progress

Paper 3 asks where the fingerprint comes from (the model or the agents' call logic), how far it
carries across deployments, networks and frameworks, and which defenses stop it. Its results will
come from new same-session TLS collections that have not been made yet; no result in this
repository is a paper 3 result.

---

## Earlier results: superseded, not to be cited

An earlier draft (*Where the Fingerprint Lives*) reported role 0.864 and workflow 0.708 on
deployment A and concluded that the leak is carried by the agents' call structure rather than the
model. Most of its numbers came from captures in which every chain and mesh specialist stream was
cut after its first event: an sse-starlette bug, fixed in commit `28a1b23`
([RECREATE.md §7e](RECREATE.md#7e-streaming-bug-in-the-pre-fix-captures-and-what-was-re-collected)).
Its headline table has been removed from this README. The results stay in `data/results/`, with a
snapshot in `data/results/pre_fix/`, and [RESULTS.md](RESULTS.md) marks each section as superseded
or clean. Cite none of them; paper 3 measures the model-versus-logic question again on clean data.

---

## Threat model

A **passive, on-path** observer records per-packet sizes, timestamps, and direction of the
encrypted traffic exchanged *among the agents*. It cannot decrypt, inject, alter, or compromise
any agent. It is granted one capability, stated with its limit: it observes the **distinct
inter-agent flows** — an in-network tap on the agent subnet, a co-located host, or a
service-mesh/sidecar vantage. It does **not** fit an observer who must first carve agent flows
out of heavy multiplexing (many TLS connections coalesced behind a shared reverse proxy or
load balancer on port 443); separating target flows from such background is not solved here.
The role task additionally assumes flows can be attributed to individual agents. Packet
direction is assigned from the known agent ports; ports never enter the feature vector. In
paper 2 the observer is the IoT gateway's network or the link upstream of it (views v1 and v2,
[docs/LEAKCHECK.md](docs/LEAKCHECK.md)), and the auditor knows the agent endpoints.

**Transport.** C1 (paper 1), the TLS arm of the TLS control and C2 (paper 2) run TLS 1.3 on every
agent link, so their captures hold only TLS records. The earlier collections (deployments A, B and
C, the live defenses, the WAN run), `a2a_mcp` and CrewAI speak cleartext HTTP, and AutoGen uses an
insecure gRPC channel; for those the observer is *restricted* to the metadata that TLS would leave
visible (on-wire packet sizes, timing and direction) and never reads content. The WAN capture
(RESULTS §4) was taken post-decapsulation on the VPN tunnel interface, i.e. at the tunnel endpoint:
an on-path observer outside the tunnel would see one encrypted, multiplexed flow, the case
excluded above.

Captures use a **96-byte snaplen**. On loopback that still keeps a 20-40 byte slice of payload
per packet, so the released captures are stripped to their link, IP and TCP headers
(`scripts/strip_payload.py`); every feature reads only timestamps and on-wire lengths.

---

## What is in this repository

```
agents/             Deployment A — official a2a-sdk agents (orchestrator, executor, retriever, validator)
agents_b/           Deployment B — same roles, different logic (sequential) and model (qwen2.5:7b)
agents_langgraph/   Deployment C — A's orchestrator re-implemented in LangGraph (runtime-only control)
workflows/          The four workflow classes and their prompt generators
capture/            tcpdump capture session, labeler, collection automation
features/           Burst segmentation, 35-dim per-flow and 90-dim per-system features → 195-dim vector
models/             Random forest, gradient-boosted trees (headline), 1-D CNN and Transformer (appendix)
defense/            Live defenses: randomized delegation scheduling and dummy sub-calls
evaluation/         Closed-world / open-world drivers, metrics, cluster-bootstrap CIs
scripts/            Every runnable entry point: collect, extract, train, evaluate, reproduce
a2a_leakcheck/      Leak audit tool: header-only captures in, LEAK / NO LEAK / INCONCLUSIVE per
                    attribute out (docs/LEAKCHECK.md)
safeiot/            a2a-leakcheck as a SafeIoT pipeline contribution: stages 1-4 and a harness, with
                    a copy of the tool's code (scripts/sync_safeiot.py)
examples/           Five small leakcheck inputs with their expected reports: the TLS control's
                    leaky and permuted sets, and C2's c2_lan, c2_lan_padmax and c2_ci_baseline
baselines/          Standard TLS scanners (sslyze, testssl.sh) against the C2 endpoints; k-FP and
                    the first-request rule as detectors
frameworks/         The independently authored comparison deployments (RESULTS §10–§13):
  autogen/            AutoGen distributed gRPC runtime (orchestrator + 3 workers) and its collector
  crewai/             CrewAI served over a2a-sdk, plus the fully matched A-vs-CrewAI pair
third_party/a2a_mcp/ Compatibility patch and drivers for Google's a2a_mcp sample (RESULTS §7, §9)
configs/            Testbed configurations (local loopback, LangGraph, US⇄India WAN, the C2 network)
docs/               WAN and LAN runbooks, leakcheck, deep-model appendix, cross-framework plan,
                    a2a_mcp patch notes
tests/              Unit and regression tests (pytest)
data/results/       Committed, canonical results: JSON + figures (everything else under data/ is gitignored)
```

### Deployments

Deployment A, over TLS, is paper 1's C1. C2 (paper 2) has its own edge and cloud agents
(`agents/edge.py`, `agents/cloud.py`): the edge agent on a Raspberry Pi gateway, the cloud agents
on the Mac behind emulated WAN delay ([docs/LAN_SETUP.md](docs/LAN_SETUP.md)). The other rows were
collected for the superseded draft and are measured again for paper 3.

| Deployment | Code | What differs from A | Isolates |
|---|---|---|---|
| **A** | `agents/` | — (llama3.2:3b, parallel `asyncio.gather` orchestrator) | baseline |
| **B** | `agents_b/` | different model **and** call logic (qwen2.5:7b, sequential) | model + logic |
| **A-model** | `agents/` + B's model | A's logic with B's model | model only |
| **B-logic** | `agents_b/` + A's model | B's logic with A's model | logic only |
| **C** | `agents_langgraph/` | only the orchestration runtime (LangGraph `StateGraph`) | runtime only |
| `a2a_mcp` | `third_party/a2a_mcp/` | Google's travel sample, six agents — not written by us | independent replication |
| AutoGen | `frameworks/autogen/` | different framework and transport (gRPC/HTTP2) | cross-framework |
| CrewAI | `frameworks/crewai/` | different framework on the same a2a-sdk transport | agentic detection |

Topologies: **star** (orchestrator to all specialists in parallel), **chain** (sequential
pipeline), **mesh** (with peer cross-links). Workflows: `code_review`, `data_analysis`,
`research_retrieval`, `support_triage`, with deliberately overlapping payload-size
distributions so workflow cannot be read off message size.

### Features and models

The 195-dim trace vector is `[0:35]` per-flow mean, `[35:70]` heaviest flow, `[70:105]` second
heaviest, `[105:195]` per-system aggregates. Per-flow features cover size distribution,
inter-arrival timing, burst structure, and SSE streaming-chunk structure.

| Model | File | Role |
|---|---|---|
| Gradient-boosted trees | `models/gradient_boosted.py` | headline attacker (paper 1) |
| Random forest | `models/random_forest.py` | equivalent baseline (overlapping CIs); used by the transfer evaluations |
| 1-D CNN, gap-aware Transformer | `models/cnn1d.py`, `models/transformer.py` | collapsed to near-single-class at ≈600 traces in the earlier suite; excluded from claims — see [docs/DEEP_MODEL_APPENDIX.md](docs/DEEP_MODEL_APPENDIX.md) |

### Defenses (run live, re-captured on the wire)

- **Size padding** — each SSE event padded to a fixed cell (`agents/base.py`, `_cell_pad_len`).
- **Rate/count** — dummy sub-calls with jittered, reordered delegation (`defense/scheduling.py`, `defense/dummy.py`).
- **Input padding** — every request body padded to a fixed size bucket (`AgentConfig.pad_buckets`;
  `scripts/collect_session.py --arm ...,pad=1024/2048/4096`).

---

## Installation

Requirements: Python 3.11+, `tcpdump`, and [Ollama](https://ollama.com) for real-LLM capture.

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements-lock.txt     # exact versions that produced data/results/
# (requirements.txt holds the looser ranges)
```

`a2a-sdk[http-server]` is pinned to **0.3.26**: the 1.x line moved to a gRPC-only transport,
unsuited to an HTTP/SSE study. The AutoGen and CrewAI deployments each have their own
`requirements.txt` under `frameworks/`.

---

## Reproducing the results

- **Paper 1:** [above](#paper-1-edi-2027-task-input-sizes-leak-through-tls), from the C1 archive.
- **Paper 2:** `bash scripts/reproduce_paper2.sh` ([above](#paper-2-safeiot-track-1-a2a-leakcheck)),
  from the paper 2 archive.
- **The earlier suite (superseded):** `bash scripts/reproduce.sh` re-analyses deployment A's
  closed world and the WAN run, and `--full-suite` every earlier result (with the C1 and
  TLS-control stages); the earlier captures and features are not in a published archive
  ([DATA.md](DATA.md#earlier-archives-not-published)).

Both reproduction scripts write to a **sandbox** (`data/results_demo/`,
`data/results_paper2_demo/` or `$A2A_RESULTS_DIR`), compare with the committed results and refuse
to write into `data/results/`. Results regenerate deterministically from the released features and captures, with
no GPU, network or Ollama. Raw *collection* is stochastic: a fresh collection gives a new dataset
whose estimates fall within the published CIs, not identical numbers.

---

## Running the pipeline

The session collector gathers one or more arms (deployment, model, TLS on or off, defense) in one
session with every condition interleaved: C1 is `bash scripts/run_c1_collection.sh`
([RECREATE.md §7f](RECREATE.md#7f-session-collections-c1-and-later)), and C2 on the Mac and the
Raspberry Pi is [docs/LAN_SETUP.md](docs/LAN_SETUP.md). The commands below are the earlier,
per-deployment pipeline (cleartext). Since the fix it records complete streams, but the results it
produced in `data/results/` are the superseded ones, so write a re-run elsewhere:

```bash
# 0. Verify A2A traffic is on the wire (must print OVERALL : PASS)
python scripts/smoke_test_a2a.py --mode local --use-llm --model llama3.2:3b

# 1. Collect all 12 topology × workflow pairs, 50 runs each (sudo only for tcpdump's BPF access;
#    on macOS `chmod o+r /dev/bpf*` once removes the need for sudo)
sudo venv/bin/python scripts/collect_deployment.py --n 50 --out data/raw

# 2. Extract the 195-dim features (evaluate.py reads data/processed)
python scripts/extract_features.py --raw data/raw --out data/processed --scapy

# 3. Evaluate: closed-world + open-world, RF + GBT, into a fresh results folder
A2A_RESULTS_DIR=data/results_rerun python scripts/evaluate.py --mode all
```

The model-vs-logic, cross-deployment, runtime-control and live-defense evaluations, the US⇄India
WAN run ([docs/WAN_COLLECTION.md](docs/WAN_COLLECTION.md); captured post-decapsulation on the VPN
tunnel interface) and the `a2a_mcp`, AutoGen and CrewAI collections are in
[RECREATE.md](RECREATE.md).

---

## Leak audit: a2a-leakcheck

`a2a_leakcheck` asks of a folder of encrypted captures whether an observer of packet headers
alone can tell which agent does what (role), which task runs (workflow) or how the agents are
wired (topology), and answers LEAK, NO LEAK or INCONCLUSIVE per attribute, with a confidence
interval, a label-permutation test and mitigation hints. Input: one header-only pcap per task with
a JSON sidecar naming the agent ports and the labels. Full description:
[docs/LEAKCHECK.md](docs/LEAKCHECK.md); other frameworks, protocols and capture sources:
[docs/EXTENDING.md](docs/EXTENDING.md).

### Setup and usage on a laptop

Python 3.11 or newer; the audit needs only `requirements-leakcheck.txt` (numpy, SciPy,
scikit-learn, joblib, threadpoolctl, PyYAML and scapy at the locked versions; no PyTorch).

```bash
python3 -m venv venv-leakcheck && venv-leakcheck/bin/pip install -r requirements-leakcheck.txt
venv-leakcheck/bin/python -m a2a_leakcheck run examples/c2_lan --vantage v2 --attributes task_type --html --out /tmp/c2_lan
PYTHON=venv-leakcheck/bin/python bash scripts/demo_paper2.sh   # C2 examples: both arms, HTML, CI gate
```

On your own deployment: one header-only pcap per task with a JSON sidecar naming the agent
endpoints and the labels ([docs/LEAKCHECK.md](docs/LEAKCHECK.md#input)), then

```bash
python -m a2a_leakcheck run CAPTURES --out REPORT --html                       # role, workflow, topology
python -m a2a_leakcheck run CAPTURES --strip --attributes task_type,escalated  # payload cut on the fly
python -m a2a_leakcheck run CAPTURES --vantage v2 --out REPORT                 # one observer's view
python -m a2a_leakcheck run CAPTURES --out NEW --baseline OLD/report.json      # CI: exit 3 on a new LEAK
```

Each report (`report.json`, `report.md`, `report.html`) gives per attribute the verdict, macro-F1
with its 95% interval, the permutation test, severity, which feature family carries the leak and a
mitigation hint from [`a2a_leakcheck/rules.yaml`](a2a_leakcheck/rules.yaml). A full audit of C2's
1,000 traces per arm and view takes three to four minutes with 14 workers; the report's runtime section gives
time and peak memory per stage.

### Setup and usage on a Raspberry Pi 5

64-bit Raspberry Pi OS with Python 3.11 or newer; the same requirements file.

```bash
python3 -m venv venv-leakcheck && venv-leakcheck/bin/pip install -r requirements-leakcheck.txt
venv-leakcheck/bin/python -m a2a_leakcheck run data/raw_c2 --strip --vantage v1 \
    --attributes task_type,escalated,cloud_role,audit_null --jobs 4 --out REPORT
python scripts/compare_reports.py REPORT/report.json data/results/leakcheck/c2_lan_v1/report.json
```

`--jobs 4` runs one cross-validation per core. Stop other heavy work first (in C2 the Pi also serves
the edge agent and its model; the audit runs after collection, not alongside it), and keep it
cool: `vcgencmd get_throttled` should read `0x0`. `scripts/compare_reports.py` checks that the
Pi's verdicts and scores equal the laptop's and lists both runtimes and peak memory.

### What else is here

- [examples/](examples/README.md): five small header-only inputs with expected reports. The TLS
  control's `leaky` and `permuted` sets (the same 40 captures with real and permuted labels), and
  C2's `c2_lan` and `c2_lan_padmax` (the same 40 tasks without and with padding) and
  `c2_ci_baseline` (the first 10 tasks per type of `c2_lan`, the earlier report the CI gate
  compares against).
- [baselines/](baselines/README.md): the TLS scanners (sslyze, testssl.sh) on the same endpoints, and
  k-FP and the first-request rule in the tool's verdict rule (`baselines/run_detectors.py`).
- `scripts/evaluate_leakcheck.py` measures the tool on known answers: recall on known leaks, false
  positives on permuted labels and on `audit_null`, the effect of sample size, and the baselines.
- **Paper 2.** `bash scripts/reproduce_paper2.sh` rebuilds every paper 2 number from the released
  data into a sandbox and compares it with the committed one, in six sections (`--section v1.0,round2,d3,b3,c2b1m,c2b2`;
  `--quick` about 6 h, everything about two days); a missing input stops it with the list, and it never
  reports success after skipping. [docs/PAPER2_NUMBERS.md](docs/PAPER2_NUMBERS.md)
  maps each number in the paper to its JSON; `scripts/export_paper2_csv.py` writes the plotted
  ones as CSV for pgfplots.
- [docs/EXTENDING.md](docs/EXTENDING.md): adding a framework, a protocol, a capture source or vantage
  point, a rule or an attribute.

---

## Data

Everything under `data/` except `data/results/` is gitignored. Raw captures live in
`data/raw*/` (pcaps at 96-byte snaplen plus label sidecars), extracted features in
`data/processed*/` (`.npz` + `labels.json`). The published archive and its layout are
described in [DATA.md](DATA.md).

---

## Ethics

All experiments ran on researcher-owned, isolated infrastructure with synthetic tasks and
locally hosted models; no real users, third-party services, or production systems were
observed. Captures are constrained to the agents under test by an explicit BPF filter and a
96-byte snaplen, and the released captures are stripped to packet headers, so no payload is
published. The work characterizes and bounds a
privacy risk and pairs the attack with a defense analysis. Do not use this code to observe
multi-agent systems without the explicit authorization of their owner.

---

## Citation

Until the papers appear, cite the data records:

```bibtex
@dataset{more2026c1,
  author    = {More, Mayuresh Sanjay and Pujari, Shradha Devendra and Berhe, Solomon},
  title     = {Encrypted agent-to-agent traffic of an LLM multi-agent system: TLS 1.3 A2A
               captures and features (collection C1)},
  year      = {2026},
  version   = {1.1},
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.23938311}
}

@dataset{more2026c2,
  author    = {More, Mayuresh Sanjay and Pujari, Shradha Devendra and Berhe, Solomon},
  title     = {Encrypted agent-to-agent traffic of an edge-AI gateway and its emulated cloud
               agents (collection C2), with a paired cleartext/TLS control: header-only
               captures and features},
  year      = {2026},
  version   = {1.0},
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.24238559}
}
```

## License

- **Code:** MIT License, see [`LICENSE`](LICENSE).
- **Data** (the published archives and `data/results/`): CC BY 4.0, see [`LICENSE-DATA.md`](LICENSE-DATA.md).
