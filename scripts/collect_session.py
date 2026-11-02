#!/usr/bin/env python3
"""
Session collector: one or more arms collected in ONE session, one trace at a time.

An arm is a deployment configuration — deployment (a, b, langgraph), model, TLS on/off
and live defense — with its own output directory. Every condition (topology × workflow)
of every arm is collected in the same session, so session drift is shared by all labels
and all arms instead of masquerading as one of them:

  * balanced rounds: each round gives every condition of every arm n/rounds traces;
    within a round all conditions are interleaved in a seeded random order, so no
    condition owns a stretch of time (the round index is the temporal-holdout unit)
  * arms alternate trace by trace on the same prompt, never in parallel; the arm order
    is rotated item by item (counterbalanced)
  * every arm starts one agent set per topology on its own ports at the start of each
    round, so conditions can interleave without restarting agents between traces
  * a trace in which any agent-to-agent call failed counts as failed and is retried once
  * --resume continues an interrupted session; --deadline-hours stops starting new items
  * when the model changes between consecutive traces, a discarded one-token Ollama call
    loads it first, so model-load latency never lands inside a captured trace

Each trace's label sidecar gets the session fields (collection_id, arm, round, position,
seed_offset); <out>/session_meta.json holds the design, the schedule and, for TLS arms,
the negotiated TLS parameters.

Arms are given as --arm name=...,deployment=...,model=...,tls=on|off,defense=...,out=...
(ports=BASE optional; arm k defaults to 8100 + 100k, topology t adds 10t). Optional:

  * pad=1024/2048/4096  input padding: every request body padded to the smallest bucket that
                        fits (above the largest, to a multiple of it)
  * host=ADDR           the specialists run on another machine (docs/LAN_SETUP.md): this
                        collector neither starts nor restarts them, it waits until they answer
                        at ADDR on the arm's ports (scripts/serve_agents.py --ports-base there),
                        and the capture is limited to ADDR; use --interface for the link

Usage:
    bash scripts/make_tls_certs.sh
    python scripts/collect_session.py --collection-id C1 --n 50 --rounds 5 --seed-offset 2000 \\
        --arm name=a_tls,deployment=a,model=llama3.2:3b,tls=on,out=data/raw_c1
    python scripts/collect_session.py ... --pilot        # one trace per topology into <out>_pilot/
    # LAN: specialists on a Raspberry Pi at 192.168.2.2, captured on the Mac's Ethernet port
    python scripts/collect_session.py --collection-id C2 --n 50 --rounds 5 --seed-offset 20000 \
        --interface en7 --arm name=lan,deployment=a,tls=on,host=192.168.2.2,ports=8100,out=data/raw_c2
Capture needs read access to /dev/bpf* (or sudo).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents import tls  # noqa: E402
from capture.automation import TraceCollector  # noqa: E402
from capture.recorder import PacketRecorder  # noqa: E402
from scripts.collect_deployment import (  # noqa: E402
    DEFAULT_NUM_PREDICT, DEPLOYMENTS, TOPO_EDGES, _agent_configs, _kill_port, _orchestrator,
    _wait_ready,
)
from scripts.collect_tls_session import probe_tls  # noqa: E402
from workflows import WORKFLOW_REGISTRY, WorkflowClass  # noqa: E402
from workflows.base import TopologyType  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TOPOLOGIES = ["star", "chain", "mesh"]
ROLES = ("orchestrator", "executor", "retriever", "validator")
SEED = 42
OLLAMA = "http://localhost:11434"


@dataclass
class Arm:
    name: str
    deployment: str
    model: str
    tls: bool
    defense: str
    out: Path
    ports_base: int
    host: str | None = None                         # remote specialists (LAN); None = local
    pad: list[int] = field(default_factory=list)    # input-padding buckets; empty = off
    sets: dict = field(default_factory=dict)        # topology → (agents, tasks)

    @property
    def agent_host(self) -> str:
        return self.host or "127.0.0.1"

    def ports(self, topology: str) -> dict[str, int]:
        base = self.ports_base + 10 * TOPOLOGIES.index(topology)
        return {r: base + i for i, r in enumerate(ROLES)}

    def dep(self, topology: str) -> dict:
        return {**DEPLOYMENTS[self.deployment], "ports": self.ports(topology)}


def parse_arm(spec: str, k: int) -> Arm:
    kv = dict(part.split("=", 1) for part in spec.split(","))
    unknown = set(kv) - {"name", "deployment", "model", "tls", "defense", "out", "ports", "pad", "host"}
    if unknown or not {"name", "deployment", "out"} <= set(kv):
        raise SystemExit(f"bad --arm {spec!r}: needs name, deployment, out; unknown keys {sorted(unknown)}")
    if kv["deployment"] not in DEPLOYMENTS:
        raise SystemExit(f"unknown deployment {kv['deployment']!r} (choose from {sorted(DEPLOYMENTS)})")
    return Arm(name=kv["name"], deployment=kv["deployment"],
               model=kv.get("model") or DEPLOYMENTS[kv["deployment"]]["default_model"],
               tls=kv.get("tls", "off").lower() in ("on", "1", "true", "yes"),
               defense=kv.get("defense", "none"), out=Path(kv["out"]),
               ports_base=int(kv.get("ports", 8100 + 100 * k)), host=kv.get("host") or None,
               pad=[int(b) for b in kv["pad"].split("/")] if kv.get("pad") else [])


class _DownstreamFailures(logging.Handler):
    """Counts ERROR records from the agents during one trace (e.g. a failed delegation,
    which the orchestrator logs but does not raise)."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith(("agents", "agents_b", "agents_langgraph")):
            self.messages.append(record.getMessage())


async def start_sets(arm: Arm, topologies: list[str], num_predict: int | None,
                     ollama: str = OLLAMA) -> None:
    if arm.host:                                   # remote specialists: only check they answer
        for topology in topologies:
            arm.sets[topology] = ([], [])
            for role in ("executor", "retriever", "validator"):
                if not await _wait_ready(role, arm.ports(topology), tls_on=arm.tls, host=arm.host):
                    raise RuntimeError(f"{arm.name} {topology} {role} agent not answering at {arm.host}")
        return
    for topology in topologies:
        ports, dep = arm.ports(topology), arm.dep(topology)
        for role in ("executor", "retriever", "validator"):
            await _kill_port(ports[role])
        configs = _agent_configs(dep, topology, arm.model, num_predict=num_predict,
                                 defense=arm.defense, tls_on=arm.tls, pad_buckets=arm.pad,
                                 ollama_url=ollama)
        agents, tasks = [], []
        for role in ("executor", "retriever", "validator"):
            agent = dep[role](configs[role])
            agents.append(agent)
            tasks.append(asyncio.create_task(agent.run(), name=f"{arm.name}-{topology}-{role}"))
        arm.sets[topology] = (agents, tasks)
    await asyncio.sleep(1.5)
    for topology in topologies:
        for role in ("executor", "retriever", "validator"):
            if not await _wait_ready(role, arm.ports(topology), tls_on=arm.tls):
                raise RuntimeError(f"{arm.name} {topology} {role} agent never came up")


async def _stop_set(arm: Arm, topology: str) -> None:
    agents, tasks = arm.sets.pop(topology)
    if arm.host:                                   # remote specialists are not ours to stop
        return
    for t in tasks:
        if t.done() and not t.cancelled() and t.exception() is not None:
            logger.error("agent server %s had exited: %r", t.get_name(), t.exception())
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
        await _kill_port(arm.ports(topology)[role])


async def stop_sets(arm: Arm) -> None:
    for topology in list(arm.sets):
        await _stop_set(arm, topology)


async def restart_set(arm: Arm, topology: str, num_predict: int | None, ollama: str = OLLAMA) -> None:
    """Fresh specialist servers for one topology, so a retry never reuses a dead one.
    Remote specialists cannot be restarted from here: the retry only waits until they answer."""
    logger.warning("%s %s %s agents before the retry", "checking" if arm.host else "restarting",
                   arm.name, topology)
    await _stop_set(arm, topology)
    await asyncio.sleep(1.0)
    await start_sets(arm, [topology], num_predict, ollama)


async def warm_up(model: str, ollama: str = OLLAMA) -> None:
    """Load the model into Ollama (outside any capture) and keep it resident."""
    async with httpx.AsyncClient(timeout=300) as c:
        r = await c.post(f"{ollama}/api/generate", json={
            "model": model, "prompt": "ok", "stream": False, "keep_alive": "60m",
            "options": {"num_predict": 1}})
        r.raise_for_status()


def make_collector(arm: Arm, topology: str, workflow: str, num_predict: int | None,
                   interface: str = "lo0", ollama: str = OLLAMA) -> TraceCollector:
    dep = arm.dep(topology)
    orch = _orchestrator(dep, topology, arm.model, num_predict=num_predict,
                         defense=arm.defense, tls_on=arm.tls, pad_buckets=arm.pad,
                         host=arm.agent_host, ollama_url=ollama)

    # Same task-id format in every arm: the id travels in the request body, so an
    # arm-specific id would change request sizes.
    async def exec_fn(prompt: str, _orch=orch) -> None:
        watch = _DownstreamFailures()
        logging.getLogger().addHandler(watch)
        try:
            async with _orch:
                await _orch.handle_task(task_id=f"pilot_a_{uuid.uuid4().hex[:8]}", content=prompt)
        finally:
            logging.getLogger().removeHandler(watch)
        if watch.messages:
            raise RuntimeError(f"{len(watch.messages)} agent error(s): {watch.messages[0][:200]}")

    ports = arm.ports(topology)
    return TraceCollector(
        orchestrator_fn=exec_fn,
        recorder=PacketRecorder(output_dir=arm.out, interface=interface, agent_ports=list(ports.values()),
                                hosts=[arm.host] if arm.host else None),
        workflow_class=WorkflowClass(workflow), topology=TopologyType(topology),
        # the orchestrator runs in this process; the specialists at agent_host
        agent_endpoints={r: f"{'127.0.0.1' if r == 'orchestrator' else arm.agent_host}:{p}"
                         for r, p in ports.items()},
        topology_edges=TOPO_EDGES[topology], output_dir=arm.out,
        deployment=f"{arm.deployment}{'_tls' if arm.tls else ''}",
    )


async def main(a: argparse.Namespace) -> None:
    arms = [parse_arm(s, k) for k, s in enumerate(a.arm)]
    if len({arm.name for arm in arms}) != len(arms) or len({arm.out for arm in arms}) != len(arms):
        raise SystemExit("arm names and output dirs must be unique")
    if any(arm.tls for arm in arms):
        tls.configure(a.tls_dir, default_on=False)
    num_predict = a.num_predict if a.num_predict > 0 else None
    for arm in arms:
        arm.out.mkdir(parents=True, exist_ok=True)
        if any(arm.out.glob("*.pcap")) and not (a.allow_existing or a.resume):
            sys.exit(f"{arm.out} already holds pcaps; move it aside, or pass --resume")

    topologies = [a.topology] if a.topology else TOPOLOGIES
    workflows = [a.workflow] if a.workflow else [wf.value for wf in WorkflowClass]
    wfs_all = [wf.value for wf in WorkflowClass]
    meta_paths = [arm.out / "session_meta.json" for arm in arms]
    meta = json.loads(meta_paths[0].read_text()) if a.resume and meta_paths[0].exists() else None
    if meta is None:
        meta = {
            "collection_id": a.collection_id,
            "design": "arms collected in one session, one trace at a time; balanced rounds (every "
                      "condition of every arm gets n/rounds traces per round); all conditions "
                      "interleaved in a seeded random order within each round; arms share the "
                      "prompt of an item and alternate with the order rotated per item; one agent "
                      "set per arm and topology, restarted each round; a trace with any agent error "
                      "is failed and retried once; models warmed up outside capture",
            "arms": [{"name": x.name, "deployment": x.deployment, "model": x.model, "tls": x.tls,
                      "defense": x.defense, "out": str(x.out), "ports_base": x.ports_base,
                      "host": x.host, "pad_buckets": x.pad} for x in arms],
            "interface": a.interface, "ollama_url": a.ollama_url,
            "num_predict": num_predict, "n_per_condition": a.n, "rounds": a.rounds,
            "seed_offset": a.seed_offset, "order_seed": SEED, "topologies": topologies,
            "workflows": workflows, "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "schedule": [], "failures": 0, "tls_params": {},
        }

    def save() -> None:
        for p in meta_paths:
            p.write_text(json.dumps(meta, indent=2))

    done = {(e["item"], e["arm"]) for e in meta["schedule"] if e["success"]}
    deadline = time.time() + a.deadline_hours * 3600 if a.deadline_hours else None
    prompts = {(t, w): WORKFLOW_REGISTRY[WorkflowClass(w)]().sample_prompts(
                   n=a.n, seed=TOPOLOGIES.index(t) * len(wfs_all) + wfs_all.index(w) + 100 + a.seed_offset)
               for t in TOPOLOGIES for w in wfs_all}
    bounds = [round(a.n * r / a.rounds) for r in range(a.rounds + 1)]
    position = len(meta["schedule"])
    last_model = None
    stopped = False

    for rnd in range(a.rounds):
        items = [(t, w, i) for t in topologies for w in workflows
                 for i in range(bounds[rnd], bounds[rnd + 1])]
        random.Random(SEED + rnd).shuffle(items)
        todo = [it for it in items if any((f"{it[0]}/{it[1]}/{it[2]}", arm.name) not in done for arm in arms)]
        if not todo:
            continue
        if deadline and time.time() > deadline:
            stopped = True
            break
        logger.info("=" * 60)
        logger.info("  %s ROUND %d/%d — %d items × %d arm(s)", a.collection_id, rnd + 1, a.rounds,
                    len(todo), len(arms))
        logger.info("=" * 60)
        try:
            for arm in arms:
                await start_sets(arm, topologies, num_predict, a.ollama_url)
                if arm.tls and arm.name not in meta["tls_params"]:
                    meta["tls_params"][arm.name] = await probe_tls(arm.ports(topologies[0])["executor"],
                                                                   host=arm.agent_host)
                    logger.info("  TLS parameters (%s): %s", arm.name, meta["tls_params"][arm.name])
            collectors = {(arm.name, t, w): make_collector(arm, t, w, num_predict, a.interface, a.ollama_url)
                          for arm in arms for t in topologies for w in workflows}
            for k, (t, w, i) in enumerate(todo):
                if deadline and time.time() > deadline:
                    stopped = True
                    break
                item = f"{t}/{w}/{i}"
                shift = (position + k) % len(arms)
                for arm in arms[shift:] + arms[:shift]:
                    if (item, arm.name) in done:
                        continue
                    if arm.model != last_model:
                        await warm_up(arm.model, a.ollama_url)
                        last_model = arm.model
                    for attempt in (1, 2):
                        run = (await collectors[(arm.name, t, w)].collect([prompts[(t, w)][i]],
                                                                          inter_run_delay=0.5))[0]
                        position += 1
                        entry = {"item": item, "arm": arm.name, "round": rnd, "position": position,
                                 "run_id": run.run_id, "success": run.success, "attempt": attempt,
                                 "start_ts": run.start_ts, "error": run.error or ""}
                        meta["schedule"].append(entry)
                        sidecar = arm.out / f"{run.run_id}.json"
                        if sidecar.exists():
                            sc = json.loads(sidecar.read_text())
                            sc.update({"collection_id": a.collection_id, "arm": arm.name, "round": rnd,
                                       "position": position, "seed_offset": a.seed_offset,
                                       "model": arm.model, "tls": arm.tls, "defense": arm.defense,
                                       "agent_host": arm.host, "pad_buckets": arm.pad})
                            sidecar.write_text(json.dumps(sc, indent=2))
                        if run.success:
                            done.add((item, arm.name))
                            break
                        meta["failures"] += 1
                        await restart_set(arm, t, num_predict, a.ollama_url)
                save()
        finally:
            for arm in arms:
                await stop_sets(arm)
            await asyncio.sleep(3.0)
        if stopped:
            logger.warning("deadline reached in round %d — stopping collection", rnd + 1)
            break

    meta["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    meta["stopped_at_deadline"] = stopped
    planned = a.n * len(topologies) * len(workflows)
    meta["complete_items"] = sum(1 for t in topologies for w in workflows for i in range(a.n)
                                 if all((f"{t}/{w}/{i}", arm.name) in done for arm in arms))
    save()
    print(f"\n{a.collection_id}: {meta['complete_items']} of {planned} items complete in every arm, "
          f"{meta['failures']} failed attempts → " + ", ".join(f"{x.out}/" for x in arms))


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Collect one or more arms in one session, one trace at a time")
    p.add_argument("--arm", action="append", required=True,
                   help="name=...,deployment=a|b|langgraph,model=...,tls=on|off,defense=none|pad|rate|both,"
                        "out=DIR[,ports=BASE][,pad=B1/B2/...][,host=ADDR]  (repeat for more arms)")
    p.add_argument("--ollama-url", default=OLLAMA, dest="ollama_url",
                   help="Ollama for the model warm-up and the agents this process runs")
    p.add_argument("--interface", default="lo0",
                   help="capture interface (lo0 for local agents; the Ethernet port for host=)")
    p.add_argument("--collection-id", required=True, dest="collection_id")
    p.add_argument("--n", type=int, default=50, help="traces per topology × workflow condition, per arm")
    p.add_argument("--rounds", type=int, default=5)
    p.add_argument("--seed-offset", type=int, required=True, dest="seed_offset",
                   help="prompt seed offset; register it in docs/PROMPT_REGISTRY.md")
    p.add_argument("--num-predict", type=int, default=DEFAULT_NUM_PREDICT, dest="num_predict")
    p.add_argument("--topology", choices=TOPOLOGIES, default=None)
    p.add_argument("--workflow", choices=[wf.value for wf in WorkflowClass], default=None)
    p.add_argument("--tls-dir", default="data/tls", dest="tls_dir")
    p.add_argument("--deadline-hours", type=float, default=None, dest="deadline_hours")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--allow-existing", action="store_true", dest="allow_existing")
    p.add_argument("--pilot", action="store_true",
                   help="one trace per topology (first workflow) per arm, into <out>_pilot/")
    args = p.parse_args()
    if args.pilot:
        args.n, args.rounds = 1, 1
        args.workflow = args.workflow or list(WorkflowClass)[0].value
        args.arm = [",".join(f"out={v}_pilot" if kv.startswith("out=") else kv
                             for kv, v in ((kv, kv.split("=", 1)[1]) for kv in s.split(",")))
                    for s in args.arm]
        args.allow_existing = True
        args.collection_id = f"{args.collection_id}-pilot"
    return args


if __name__ == "__main__":
    asyncio.run(main(_parse()))
