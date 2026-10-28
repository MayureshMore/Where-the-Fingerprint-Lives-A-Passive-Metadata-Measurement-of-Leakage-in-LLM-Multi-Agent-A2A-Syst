#!/usr/bin/env python3
"""
TLS control collection: cleartext and TLS round-robin in ONE session.

Comparing a new TLS capture against the earlier cleartext capture would mix the
TLS effect with session drift (the artifact the temporal-interleaving control
exposed). This driver instead runs two copies of deployment A side by side —
a cleartext set on ports 8000-8003 and a TLS set on 8040-8043 — and alternates
them trace by trace, with the SAME prompt for both arms of each pair and the
arm order counterbalanced (cleartext first on even pairs, TLS first on odd).
Prompts come from a disjoint pool (--seed-offset, default 1000).

Writes:
  <out-clear>/   cleartext traces (pcap + label sidecar)
  <out-tls>/     TLS traces
  <out-tls>/session_meta.json   design, schedule and the negotiated TLS
                                parameters (version, cipher, HTTP version)

Usage:
    bash scripts/make_tls_certs.sh
    python scripts/run_tls_session.py --n 36                     # 12 conditions × 36 × 2 arms
    python scripts/run_tls_session.py --pilot                    # one pair, into data/tls_pilot/
Capture needs read access to /dev/bpf* (or sudo); see scripts/run_tls_overnight.sh.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import socket
import ssl
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents import tls  # noqa: E402
from capture.automation import TraceCollector  # noqa: E402
from capture.recorder import PacketRecorder  # noqa: E402
from scripts.run_pilot import (  # noqa: E402
    DEFAULT_NUM_PREDICT, DEPLOYMENTS, TOPO_EDGES, _agent_configs, _kill_port, _orchestrator,
    _wait_ready,
)
from workflows import WORKFLOW_REGISTRY, WorkflowClass  # noqa: E402
from workflows.base import TopologyType  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEP = DEPLOYMENTS["a"]
ARMS = {
    "clear": {"tls": False, "ports": DEP["ports"], "deployment": "a"},
    "tls":   {"tls": True,  "ports": {r: p + 40 for r, p in DEP["ports"].items()}, "deployment": "a_tls"},
}
TOPOLOGIES = ["star", "chain", "mesh"]


async def start_set(arm: str, topology: str, model: str, num_predict: int | None) -> tuple[list, list]:
    """Start one arm's executor/retriever/validator; returns (agents, tasks)."""
    a = ARMS[arm]
    dep = {**DEP, "ports": a["ports"]}
    for role in ("executor", "retriever", "validator"):
        await _kill_port(a["ports"][role])
    await asyncio.sleep(0.6)
    configs = _agent_configs(dep, topology, model, num_predict=num_predict, tls_on=a["tls"])
    agents, tasks = [], []
    for role in ("executor", "retriever", "validator"):
        agent = DEP[role](configs[role])
        agents.append(agent)
        tasks.append(asyncio.create_task(agent.run(), name=f"{arm}-{topology}-{role}"))
    await asyncio.sleep(1.2)
    for role in ("executor", "retriever", "validator"):
        if not await _wait_ready(role, a["ports"], tls_on=a["tls"]):
            raise RuntimeError(f"{arm} {role} agent never came up ({topology})")
    return agents, tasks


async def stop_set(arm: str, agents: list, tasks: list) -> None:
    for agent in agents:
        await agent.shutdown()
    _, pending = await asyncio.wait(tasks, timeout=4.0)
    for t in pending:
        t.cancel()
        try:
            await t
        except BaseException:
            pass
    for role in ("executor", "retriever", "validator"):
        await _kill_port(ARMS[arm]["ports"][role])


async def probe_tls(port: int) -> dict:
    """Negotiated TLS version/cipher (raw handshake) and HTTP version (httpx) of a TLS agent."""
    ctx = tls.client_verify()
    loop = asyncio.get_running_loop()

    def _handshake() -> tuple[str, list]:
        with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
            with ctx.wrap_socket(raw, server_hostname="127.0.0.1") as s:
                return s.version(), list(s.cipher())

    version, cipher = await loop.run_in_executor(None, _handshake)
    async with httpx.AsyncClient(verify=ctx, timeout=5) as c:
        r = await c.get(f"https://127.0.0.1:{port}/.well-known/agent.json")
    return {"tls_version": version, "cipher": cipher[0], "cipher_bits": cipher[2],
            "http_version": r.http_version, "openssl": ssl.OPENSSL_VERSION,
            "httpx": httpx.__version__}


async def main(a: argparse.Namespace) -> None:
    tls.configure(a.tls_dir, default_on=False)
    model = a.model or DEP["default_model"]
    num_predict = a.num_predict if a.num_predict > 0 else None
    outs = {"clear": Path(a.out_clear), "tls": Path(a.out_tls)}
    for d in outs.values():
        d.mkdir(parents=True, exist_ok=True)
        if any(d.glob("*.pcap")) and not a.allow_existing:
            sys.exit(f"{d} already holds pcaps; move it aside or pass --allow-existing")

    topologies = [a.topology] if a.topology else TOPOLOGIES
    workflows = [a.workflow] if a.workflow else [wf.value for wf in WorkflowClass]
    wfs_all = [wf.value for wf in WorkflowClass]
    meta = {
        "design": "deployment A; cleartext (ports 8000-8003) and TLS (ports 8040-8043) agent sets "
                  "run side by side and alternate trace by trace in one session; the two traces "
                  "of a pair share one prompt; arm order counterbalanced (cleartext first on even "
                  "pairs, TLS first on odd)",
        "model": model, "num_predict": num_predict, "n_per_condition": a.n,
        "seed_offset": a.seed_offset, "topologies": topologies, "workflows": workflows,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "schedule": [], "failures": 0,
    }

    for topology in topologies:
        logger.info("=" * 60)
        logger.info("  TOPOLOGY %s — cleartext and TLS sets", topology.upper())
        logger.info("=" * 60)
        sets = {arm: await start_set(arm, topology, model, num_predict) for arm in ARMS}
        if "tls_params" not in meta:
            meta["tls_params"] = await probe_tls(ARMS["tls"]["ports"]["executor"])
            logger.info("  TLS parameters: %s", meta["tls_params"])
        try:
            for wf_name in workflows:
                wf_class = WorkflowClass(wf_name)
                seed = TOPOLOGIES.index(topology) * len(wfs_all) + wfs_all.index(wf_name) + 100 + a.seed_offset
                prompts = WORKFLOW_REGISTRY[wf_class]().sample_prompts(n=a.n, seed=seed)
                collectors = {}
                for arm, cfg in ARMS.items():
                    dep = {**DEP, "ports": cfg["ports"]}
                    orch = _orchestrator(dep, topology, model, num_predict=num_predict, tls_on=cfg["tls"])

                    async def exec_fn(prompt: str, _orch=orch, _d=cfg["deployment"]) -> None:
                        async with _orch:
                            await _orch.handle_task(task_id=f"pilot_{_d}_{uuid.uuid4().hex[:8]}", content=prompt)

                    collectors[arm] = TraceCollector(
                        orchestrator_fn=exec_fn,
                        recorder=PacketRecorder(output_dir=outs[arm], interface="lo0",
                                                agent_ports=list(cfg["ports"].values())),
                        workflow_class=wf_class, topology=TopologyType(topology),
                        agent_endpoints={r: f"127.0.0.1:{p}" for r, p in cfg["ports"].items()},
                        topology_edges=TOPO_EDGES[topology], output_dir=outs[arm],
                        deployment=cfg["deployment"],
                    )
                logger.info("  %s / %s: %d pairs", topology, wf_name, len(prompts))
                for i, prompt in enumerate(prompts):
                    order = ("clear", "tls") if i % 2 == 0 else ("tls", "clear")
                    for arm in order:
                        run = (await collectors[arm].collect([prompt], inter_run_delay=0.5))[0]
                        meta["schedule"].append({"pair": f"{topology}/{wf_name}/{i}", "arm": arm,
                                                 "run_id": run.run_id, "success": run.success,
                                                 "start_ts": run.start_ts})
                        meta["failures"] += 0 if run.success else 1
                (outs["tls"] / "session_meta.json").write_text(json.dumps(meta, indent=2))
        finally:
            for arm, (agents, tasks) in sets.items():
                await stop_set(arm, agents, tasks)
            await asyncio.sleep(3.0)

    meta["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    (outs["tls"] / "session_meta.json").write_text(json.dumps(meta, indent=2))
    ok = sum(s["success"] for s in meta["schedule"])
    print(f"\nTLS session: {ok}/{len(meta['schedule'])} traces successful "
          f"→ {outs['clear']}/ and {outs['tls']}/")


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Paired cleartext/TLS collection in one session (deployment A)")
    p.add_argument("--n", type=int, default=36, help="pairs per topology × workflow condition")
    p.add_argument("--pilot", action="store_true",
                   help="one pair (star, first workflow) into data/tls_pilot/{clear,tls}")
    p.add_argument("--topology", choices=TOPOLOGIES, default=None)
    p.add_argument("--workflow", choices=[wf.value for wf in WorkflowClass], default=None)
    p.add_argument("--seed-offset", type=int, default=1000, dest="seed_offset",
                   help="prompt pool offset; 1000 keeps it disjoint from the main collections")
    p.add_argument("--model", default=None)
    p.add_argument("--num-predict", type=int, default=DEFAULT_NUM_PREDICT, dest="num_predict")
    p.add_argument("--tls-dir", default="data/tls", dest="tls_dir")
    p.add_argument("--out-clear", default="data/raw_tlspair_clear", dest="out_clear")
    p.add_argument("--out-tls", default="data/raw_tlspair_tls", dest="out_tls")
    p.add_argument("--allow-existing", action="store_true", dest="allow_existing",
                   help="add to output dirs that already hold traces")
    args = p.parse_args()
    if args.pilot:
        args.n, args.topology = 1, args.topology or "star"
        args.workflow = args.workflow or list(WorkflowClass)[0].value
        args.out_clear, args.out_tls = "data/tls_pilot/clear", "data/tls_pilot/tls"
        args.allow_existing = True
    return args


if __name__ == "__main__":
    asyncio.run(main(_parse()))
