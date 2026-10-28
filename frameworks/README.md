# frameworks/

Independently authored multi-agent deployments used as comparison systems in the paper.
Each runs on local Ollama models (no API keys) and has its own virtualenv and
`requirements.txt`; captures are written to the repo's gitignored `data/` directory.

| Folder | System | Collector | Writes | Paper |
|---|---|---|---|---|
| `autogen/` | AutoGen distributed gRPC runtime: a host plus an orchestrator and three workers (researcher, writer, reviewer) | `N=30 bash collect_trips.sh` | `data/raw_autogen/` | §5.10, §5.11 |
| `crewai/` | CrewAI agents served over a2a-sdk 0.3.26 (the same transport as deployment A) | `N=30 bash collect_trips.sh` | `data/raw_crewai/` | §5.11 |
| `crewai/` | CrewAI matched to deployment A (same LLM, roles, topology, prompts in `a_prompts.jsonl`) | `N=40 bash collect_matched.sh` | `data/raw_crewai_matched/` | §5.11 |

Setup (per folder): `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`.
Captures use tcpdump at a 96-byte snaplen on loopback; on macOS run `sudo chmod o+r /dev/bpf*`
once to capture without sudo. Evaluation scripts live in `scripts/` — see
[RECREATE.md §7c](../RECREATE.md).
