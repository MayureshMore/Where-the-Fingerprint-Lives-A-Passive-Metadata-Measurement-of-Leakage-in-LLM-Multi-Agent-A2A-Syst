# Where the Fingerprint Lives: A Passive Metadata Measurement of Leakage in LLM Multi-Agent (A2A) Systems

Code, data pipeline, and frozen results for the paper above. A passive observer who sees only
the **metadata** of encrypted agent-to-agent traffic — packet sizes, timing, direction, never
payloads — recovers the **roles** of the agents and the **workflow** they are running in an LLM
multi-agent system built on the official [Agent2Agent (A2A)](https://a2a-protocol.org/latest/specification/)
SDK. The paper's central result is *where* that leakage lives: it is carried by the agent
implementation's inter-agent call structure, not by the language model or the orchestration
runtime — which is also why the attack is real within a profiled deployment and stops at its edges.

- **New here?** [START_HERE.md](START_HERE.md) — one command per step, install → reproduce.
- **Results, scope, and caveats:** [RESULTS.md](RESULTS.md).
- **Rebuild everything from scratch** (datasets → results): [RECREATE.md](RECREATE.md).
- **Data archive layout:** [DATA.md](DATA.md).

---

## Headline results

All numbers are macro-F1 with 95% cluster-bootstrap CIs, from the committed JSONs in
[`data/results/`](data/results/) (the single source of truth). Section numbers refer to the paper.

| Finding | Result | Chance | Source |
|---|---|---|---|
| Role recovery, single deployment (§5.1) | **0.864** [0.847, 0.881] | 0.333 | `closed_world/closed_world_gbt_role.json` |
| Workflow recovery, single deployment (§5.1) | **0.708** [0.665, 0.745] | 0.250 | `closed_world/closed_world_gbt_workflow.json` |
| Topology / parallelism — *structural baselines*, read off the connection graph (§5.1) | 0.995 / 0.989 | 0.333 / 0.500 | `closed_world/` |
| Swap the **model**, keep the logic (§5.2) | role 0.829, workflow 0.588 — signal survives | | `model_vs_logic.json` |
| Swap the **logic**, keep the model (§5.2) | role 0.517, workflow 0.321 — signal collapses | | `model_vs_logic.json` |
| Swap only the **runtime** (LangGraph, §5.2) | role 0.83, workflow 0.64 — near ceiling | | `cross_framework.json` |
| Transfer across implementations, A→B workflow (§5.3) | 0.289 | 0.250 | `cross_deployment.json` |
| Open world, novelty detector at a 1% base rate (§5.4) | precision ≈ **1.6%** | | `open_world_background.json` |
| Live defenses: rate/count, size padding (§5.5) | 0.531 at +34.9% bytes; 0.544 at +30.8% | 0.250 | `defense/defense_live.json` |
| US⇄India WAN, train and test at the WAN vantage (§5.6) | role 0.871, workflow 0.616 | | `c5_cross_network.json` |
| LAN-trained model tested on WAN, workflow (§5.6) | 0.196 — does not transfer | 0.250 | `c5_cross_network.json` |
| Google `a2a_mcp` (not ours), six-way role (§5.7) | **0.906** [0.852, 0.956] | 0.167 | `offtheshelf_fingerprint.json` |
| Same-session control: framework-ID collapses, core tasks hold (§5.8) | 0.997 → 0.46 | 0.500 | `confound_control.json` |
| Cross-instance `a2a_mcp`, coordinator layer (§5.9) | 0.87 (82 trips); 0.94 (102 trips) | 0.333 | `cross_instance_transfer*.json` |
| AutoGen over gRPC (not ours), four-way role (§5.10) | **0.966** | 0.250 | `cross_framework_autogen.json` |
| Cross-framework transfer, two-way coordinator/specialist (§5.10) | 0.43 — below chance | 0.500 | `cross_framework_autogen.json` |

Every value above regenerates exactly from the frozen features — see [Reproducing the paper](#reproducing-the-paper).

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
direction is assigned from the known agent ports; ports never enter the feature vector.

Captures use a **96-byte snaplen**: payload bytes are never written to disk.

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
frameworks/         The independently authored comparison deployments (§5.10–5.11):
  autogen/            AutoGen distributed gRPC runtime (orchestrator + 3 workers) and its collector
  crewai/             CrewAI served over a2a-sdk, plus the fully matched A-vs-CrewAI pair
third_party/a2a_mcp/ Compatibility patch and drivers for Google's a2a_mcp sample (§5.7, §5.9)
configs/            Testbed configurations (local loopback, LangGraph, US⇄India WAN)
docs/               WAN runbook, deep-model appendix, cross-framework plan, a2a_mcp patch notes
tests/              Unit and regression tests (pytest)
data/results/       Committed, canonical results: JSON + figures (everything else under data/ is gitignored)
```

### Deployments

| Deployment | Code | What differs from A | Isolates |
|---|---|---|---|
| **A** (headline) | `agents/` | — (llama3.2:3b, parallel `asyncio.gather` orchestrator) | baseline |
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

| Model | File | Role in the paper |
|---|---|---|
| Gradient-boosted trees | `models/gradient_boosted.py` | headline attacker |
| Random forest | `models/random_forest.py` | equivalent baseline (overlapping CIs); used by the transfer evaluations |
| 1-D CNN, gap-aware Transformer | `models/cnn1d.py`, `models/transformer.py` | collapse to near-single-class at ≈600 traces; excluded from claims — see [docs/DEEP_MODEL_APPENDIX.md](docs/DEEP_MODEL_APPENDIX.md) |

### Defenses (run live, re-captured on the wire)

- **Size padding** — each SSE event padded to a fixed cell (`agents/base.py`, `_cell_pad_len`).
- **Rate/count** — dummy sub-calls with jittered, reordered delegation (`defense/scheduling.py`, `defense/dummy.py`).

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

## Reproducing the paper

All tables and figures regenerate deterministically from the published feature matrices and
captures — no GPU, no network, no Ollama. Download and unpack the archive into `data/`
(layout in [DATA.md](DATA.md)), then:

```bash
bash scripts/reproduce.sh                          # short demo (~5 min): closed-world + WAN, side-by-side check
bash scripts/reproduce.sh --full-suite             # every result in the paper (RF + GBT)
bash scripts/reproduce.sh --full-suite --with-deep # also train the CNN/Transformer (stochastic, slow)
```

Output goes to a **sandbox** (`data/results_demo/`); the committed `data/results/` is never
overwritten (the script refuses to run if pointed at it). To write a fresh copy instead:
`A2A_RESULTS_DIR=data/results_$(date +%F) bash scripts/reproduce.sh --full-suite`.

Raw *collection* is stochastic: a fresh collection gives a new dataset whose estimates fall
within the published CIs, not identical numbers.

---

## Running the pipeline

```bash
# 0. Verify A2A traffic is on the wire (must print OVERALL : PASS)
python scripts/run_poc.py --mode local --use-llm --model llama3.2:3b

# 1. Collect all 12 topology × workflow pairs, 50 runs each (sudo only for tcpdump's BPF access;
#    on macOS `chmod o+r /dev/bpf*` once removes the need for sudo)
sudo venv/bin/python scripts/run_pilot.py --n 50 --out data/raw

# 2. Extract the 195-dim features
python scripts/extract_features.py --raw data/raw --out data/processed --scapy

# 3. Evaluate: closed-world + open-world, RF + GBT (add --full-suite for the deep models)
python scripts/evaluate.py --mode all

# Model vs. logic, cross-deployment, runtime control
python scripts/evaluate_model_vs_logic.py
python scripts/evaluate_cross_deployment.py --dir-a data/processed --dir-b data/processed_b_sdk
python scripts/evaluate_cross_deployment.py --dir-a data/processed --dir-b data/processed_langgraph \
    --label-b C --control --out data/results/cross_framework.json

# Live defenses
python scripts/evaluate_defense_live.py \
  --baseline data/processed --baseline-raw data/raw \
  --rate data/processed_defense_rate --rate-raw data/raw_defense_rate \
  --pad  data/processed_defense_pad  --pad-raw  data/raw_defense_pad
```

The US⇄India WAN experiment (§5.6) is documented step by step in
[docs/C5_WAN_RUNBOOK.md](docs/C5_WAN_RUNBOOK.md); capture is taken post-decapsulation on the VPN
tunnel interface, not the physical NIC. The `a2a_mcp`, AutoGen, and CrewAI collections are in
[RECREATE.md](RECREATE.md). Every evaluation step is also wired into `scripts/reproduce.sh`.

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
96-byte snaplen, so payload bytes are never recorded. The work characterizes and bounds a
privacy risk and pairs the attack with a defense analysis. Do not use this code to observe
multi-agent systems without the explicit authorization of their owner.

---

## Citation

```bibtex
@misc{more2026wherefingerprintlives,
  title  = {Where the Fingerprint Lives: A Passive Metadata Measurement of Leakage
            in LLM Multi-Agent (A2A) Systems},
  author = {More, Mayuresh Sanjay},
  year   = {2026},
  note   = {Code and data: https://github.com/MayureshMore/Passive-Inference-of-Topology-Roles-and-Workflows-in-LLM-Multi-Agent-via-Encrypted-Traffic-Analysis}
}
```

## License

A formal `LICENSE` (code) and data license are to be added before public release.
