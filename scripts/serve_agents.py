#!/usr/bin/env python3
"""
C5 WAN harness — REMOTE side (run this on the India Dell host).

Serves the three specialist agents (executor, retriever, validator) bound to
0.0.0.0 so the US orchestrator can reach them across the wide-area network.
Each agent uses THIS host's local Ollama (keeping inference traffic local, so
only A2A flows cross the WAN — see the inference-latency confound note in the
proposal §8.1).

The agents keep running until interrupted (Ctrl-C).  Start them here, then run
scripts/collect_wan.py on the US host pointing --remote-host at this machine.

Usage (on the India host):
    # Deployment A specialists on the default ports (8001-8003):
    venv/bin/python scripts/serve_agents.py --topology star --deployment a
    # Deployment B specialists:
    venv/bin/python scripts/serve_agents.py --topology chain --deployment b

Topology note: chain/mesh forwarding between specialists stays LOCAL on this
host (127.0.0.1); only the orchestrator->specialist hops cross the WAN.

LAN setup (docs/LAN_SETUP.md; a Raspberry Pi serving the specialists for
scripts/collect_session.py --arm ...,host=PI_ADDR,ports=BASE on the Mac): --ports-base serves
all three topologies at once on the collector's layout (topology t at BASE + 10t, executor +1,
retriever +2, validator +3), --tls-dir serves HTTPS, --ollama-url points the agents at the
Mac's Ollama, and --pad-buckets turns on input padding:

    venv/bin/python scripts/serve_agents.py --ports-base 8100 --tls-dir data/tls \
        --ollama-url http://192.168.2.1:11434
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents import tls
from agents.base import AgentConfig, AgentRole
from agents.executor import ExecutorAgent
from agents.retriever import RetrieverAgent
from agents.validator import ValidatorAgent
from agents_b.executor_b import ExecutorB
from agents_b.retriever_b import RetrieverB
from agents_b.validator_b import ValidatorB

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Deployment A uses 8001-8003; B uses 8011-8013; C (LangGraph) uses 8031-8033.
# Deployment C reuses A's specialist classes unchanged (only its orchestrator,
# driven by the collector, is LangGraph); these are the specialist servers.
PORTS = {
    "a": {"executor": 8001, "retriever": 8002, "validator": 8003},
    "b": {"executor": 8011, "retriever": 8012, "validator": 8013},
    "langgraph": {"executor": 8031, "retriever": 8032, "validator": 8033},
}
CLASSES = {
    "a": {"executor": ExecutorAgent, "retriever": RetrieverAgent, "validator": ValidatorAgent},
    "b": {"executor": ExecutorB, "retriever": RetrieverB, "validator": ValidatorB},
    "langgraph": {"executor": ExecutorAgent, "retriever": RetrieverAgent, "validator": ValidatorAgent},
}
DEFAULT_MODEL = {"a": "llama3.2:3b", "b": "qwen2.5:7b", "langgraph": "llama3.2:3b"}
TOPOLOGIES = ["star", "chain", "mesh"]          # order matches scripts/collect_session.py


def session_ports(base: int, topology: str) -> dict[str, int]:
    """collect_session.py's layout: topology t at base + 10t; executor, retriever, validator +1..3."""
    b = base + 10 * TOPOLOGIES.index(topology)
    return {"executor": b + 1, "retriever": b + 2, "validator": b + 3}


def _downstream(role: str, topology: str, ports: dict[str, int], tls_on: bool = False) -> list[str]:
    """Host-local forwarding URLs for chain/mesh (specialists are co-located)."""
    local = lambda r: f"{tls.scheme(tls_on)}://127.0.0.1:{ports[r]}"
    if topology in ("chain", "mesh"):
        if role == "executor":
            return [local("retriever")]
        if role == "retriever":
            return [local("validator")]
    return []  # star: all specialists are leaves


async def main(args: argparse.Namespace) -> None:
    dep = args.deployment
    classes = CLASSES[dep]
    model = args.model or DEFAULT_MODEL[dep]
    num_predict = args.num_predict if args.num_predict > 0 else None
    tls_on = bool(args.tls_dir)
    if tls_on:
        tls.configure(args.tls_dir, default_on=True)
    pad = [int(b) for b in args.pad_buckets.split(",")] if args.pad_buckets else []
    if args.ports_base is not None:
        sets = [(t, session_ports(args.ports_base, t))
                for t in (TOPOLOGIES if args.topology == "all" else [args.topology])]
    else:
        if args.topology == "all":
            raise SystemExit("--topology all needs --ports-base")
        sets = [(args.topology, PORTS[dep])]

    agents = []
    tasks = []
    for topology, ports in sets:
        for role, AgentClass in classes.items():
            cfg = AgentConfig(
                role=AgentRole(role),
                host=args.bind,
                port=ports[role],
                downstream_agents=_downstream(role, topology, ports, tls_on),
                ollama_model=model,
                ollama_num_predict=num_predict,
                ollama_base_url=args.ollama_url,
                defense=args.defense,
                pad_buckets=pad,
                tls=tls_on,
            )
            agent = AgentClass(cfg)
            agents.append(agent)
            tasks.append(asyncio.create_task(agent.run(), name=f"{dep}-{topology}-{role}"))

    for topology, ports in sets:
        logger.info("Serving deployment-%s %s specialists on %s ports %s (model=%s, TLS %s, "
                    "Ollama %s, defense=%s, pad=%s).", dep.upper(), topology, args.bind,
                    list(ports.values()), model, "on" if tls_on else "off", args.ollama_url,
                    args.defense, pad or "off")
    logger.info("Ctrl-C to stop.")
    try:
        # A signal reaches only one of the uvicorn servers in this process; when any server
        # stops, stop them all.
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        for agent in agents:
            await agent.shutdown()
        await asyncio.wait(tasks, timeout=5)


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="C5 WAN harness — serve specialist agents (remote/India host)")
    p.add_argument("--topology", default="all", choices=["star", "chain", "mesh", "all"],
                   help="Wire specialists for this topology (all: every topology, needs --ports-base). "
                        "For collect_wan it MUST match its --topology")
    p.add_argument("--ports-base", type=int, default=None, dest="ports_base",
                   help="collect_session.py port layout (the arm's ports=BASE); default: the WAN ports")
    p.add_argument("--bind", default="0.0.0.0", help="listen address")
    p.add_argument("--tls-dir", default=None, dest="tls_dir",
                   help="serve HTTPS with the certificates in this dir (scripts/make_tls_certs.sh)")
    p.add_argument("--ollama-url", default="http://localhost:11434", dest="ollama_url",
                   help="Ollama the agents call (the Mac's in the LAN setup)")
    p.add_argument("--pad-buckets", default="", dest="pad_buckets",
                   help="input padding buckets in bytes, e.g. 1024,2048,4096 (default off)")
    p.add_argument("--deployment", choices=["a", "b", "langgraph"], default="a")
    p.add_argument("--model", default=None, help="Override Ollama model (default per deployment)")
    p.add_argument("--num-predict", type=int, default=256, dest="num_predict",
                   help="Cap Ollama output tokens (match the local collection: 256; 0 = unlimited)")
    p.add_argument("--defense", default="none", choices=["none", "pad", "rate", "both"])
    return p.parse_args()


if __name__ == "__main__":
    try:
        asyncio.run(main(_parse()))
    except KeyboardInterrupt:
        pass
