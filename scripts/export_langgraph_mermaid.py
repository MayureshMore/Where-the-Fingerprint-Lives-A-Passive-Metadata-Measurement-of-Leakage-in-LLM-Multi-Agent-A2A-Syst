#!/usr/bin/env python3
"""
Export deployment C's orchestrator graph (agents_langgraph/) as Mermaid, one file
per topology, using LangGraph's own renderer (CompiledGraph.get_graph().draw_mermaid()).
Nothing is called: the graph is only compiled, so no Ollama or agents are needed.

Usage:
    python scripts/export_langgraph_mermaid.py            # → docs/diagrams/langgraph_{star,chain,mesh}.mmd
    python scripts/export_langgraph_mermaid.py --out DIR
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.base import AgentConfig, AgentRole  # noqa: E402
from agents_langgraph.orchestrator_langgraph import OrchestratorLangGraph  # noqa: E402

# Downstream agents the orchestrator calls directly, per topology (as in scripts/collect_deployment.py)
DOWNSTREAM = {
    "star": ["executor", "retriever", "validator"],
    "chain": ["executor"],
    "mesh": ["executor", "retriever"],
}
PORTS = {"executor": 8001, "retriever": 8002, "validator": 8003}


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    orch = OrchestratorLangGraph(AgentConfig(role=AgentRole.ORCHESTRATOR, port=8000))
    for topology, roles in DOWNSTREAM.items():
        urls = [f"http://127.0.0.1:{PORTS[r]}" for r in roles]
        text = orch._build_graph(urls).get_graph().draw_mermaid()
        path = out / f"langgraph_{topology}.mmd"
        path.write_text(text)
        print(f"{path}  (call_i → {', '.join(roles)})")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Export the LangGraph orchestrator graph as Mermaid")
    p.add_argument("--out", type=Path, default=Path("docs/diagrams"))
    main(p.parse_args().out)
