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
seed_offset), its prompt_group (sha1 of the prompt, 8 hex digits, as scripts/extract_features.py
computes it) and audit_null: a label a–d drawn per prompt group from a generator seeded with
AUDIT_NULL_SEED and the group, so every trace of a prompt, in every arm, gets the same label and
the label carries nothing about the traffic (the audit's known-null attribute).
<out>/session_meta.json holds the design, the schedule and, for TLS arms, the negotiated TLS
parameters.

Workflows: --workflows classic (default: research_retrieval, code_review, data_analysis,
support_triage; every collection up to C1) or iot (sensor_analysis, fault_diagnosis,
procedure_lookup, alert_triage; C2), or a comma-separated list from one set. Prompt seeds are
workflows.prompt_seed: topology_index × 4 + the workflow's index in its set + 100 + seed_offset, so
classic prompts are what they were. session_meta.json records the template pools and how many
distinct prompts were drawn per workflow.

Edge-cloud placement (--placement edge-cloud; C2, docs/LAN_SETUP.md): the agent that runs the task
is the edge agent on the IoT gateway (scripts/serve_edge.py on the Raspberry Pi); it answers
alert_triage itself and escalates the other task types to the cloud agents (scripts/serve_cloud.py
on the Mac's cloud alias), then files a ticket with the building's ticket service. This collector
sends each task to the edge agent's trigger port (arm base + 9) and captures the gateway's flows
to the cloud agents (base + 1, + 2) and the ticket service (base + 5); the trigger port is not in
the capture filter, so no observer view contains it. There is one condition per task type (no
topology; items are edge_cloud/<task type>/<i>). Sidecars add task_type, escalated (yes/no),
cloud_role (escalated tasks only), the observer views (vantages: v1 building network, v2 upstream),
the padded endpoints, the edge agent's timings and the Pi's temperature and throttling
(pi_throttled). With --wan-target, every round starts with the edge agent measuring its TCP
connect time to the cloud address; outside the target ± --wan-tolerance the session stops.

Arms are given as --arm name=...,deployment=...,model=...,tls=on|off,defense=...,out=...
(ports=BASE optional; arm k defaults to 8100 + 100k, topology t adds 10t). Optional:

  * pad=1024/2048/4096  input padding: every request body padded to the smallest bucket that
                        fits (above the largest, to a multiple of it)
  * pad_expect=8192     with pad=: every first request of the arm is meant to land in this one
                        bucket (C2's lan_padmax); scripts/check_session_design.py [c] then fails
                        unless all of them do
  * host=ADDR           the specialists run on another machine (docs/LAN_SETUP.md): this
                        collector neither starts nor restarts them, it waits until they answer
                        at ADDR on the arm's ports (scripts/serve_agents.py --ports-base there),
                        and the capture is limited to ADDR; use --interface for the link

Usage:
    bash scripts/make_tls_certs.sh
    python scripts/collect_session.py --collection-id C1 --n 50 --rounds 5 --seed-offset 2000 \\
        --arm name=a_tls,deployment=a,model=llama3.2:3b,tls=on,out=data/raw_c1
    python scripts/collect_session.py ... --pilot        # one trace per topology into <out>_pilot/
    # C2, edge-cloud on the home Wi-Fi (docs/LAN_SETUP.md); addresses and the capture interface from
    # configs/c2_network.conf
    python scripts/collect_session.py --placement edge-cloud --collection-id C2 --n 150 --rounds 5 \\
        --seed-offset 30000 --workflows iot --tls-dir data/tls_lan --wan-target data/results/c2_wan_emulation.json \\
        --arm name=lan,ports=8100,out=data/raw_c2 \\
        --arm name=lan_pad,ports=8200,pad=1024/2048/4096/8192/16384/32768,out=data/raw_c2_pad \\
        --arm name=lan_padmax,ports=8300,pad=8192/16384,pad_expect=8192,out=data/raw_c2_padmax
Capture needs read access to /dev/bpf* (or sudo).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
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
from workflows import WORKFLOW_REGISTRY, WORKFLOW_SETS, WorkflowClass, prompt_seed, workflow_set  # noqa: E402
from workflows.base import TopologyType  # noqa: E402
from agents.edge import (  # noqa: E402
    CLOUD_PORTS, PADDED_ENDPOINTS, ROUTES, TRIGGER_PORT, VANTAGES, c2_network, endpoints as edge_endpoints,
    require,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TOPOLOGIES = ["star", "chain", "mesh"]
ROLES = ("orchestrator", "executor", "retriever", "validator")
SEED = 42
AUDIT_NULL_SEED = 42
AUDIT_NULL_LABELS = "abcd"
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
    pad_expect: int | None = None                   # the one bucket every first request should land in
    sets: dict = field(default_factory=dict)        # topology → (agents, tasks)

    @property
    def agent_host(self) -> str:
        return self.host or "127.0.0.1"

    def ports(self, topology: str) -> dict[str, int]:
        base = self.ports_base + 10 * TOPOLOGIES.index(topology)
        return {r: base + i for i, r in enumerate(ROLES)}

    def dep(self, topology: str) -> dict:
        return {**DEPLOYMENTS[self.deployment], "ports": self.ports(topology)}


def prompt_group(prompt: str) -> str:
    return hashlib.sha1(prompt.encode()).hexdigest()[:8]


def audit_null(group: str) -> str:
    """A label with no relation to the traffic: random per prompt group, fixed seed."""
    return random.Random(f"{AUDIT_NULL_SEED}:{group}").choice(AUDIT_NULL_LABELS)


def resolve_workflows(spec: str, only: str | None) -> list[str]:
    """--workflows: a set name (classic, iot) or comma-separated workflows of one set, in set order
    as given; --workflow narrows it to one."""
    names = [w.value for w in WORKFLOW_SETS[spec]] if spec in WORKFLOW_SETS else \
        [x.strip() for x in spec.split(",") if x.strip()]
    valid = {w.value for w in WorkflowClass}
    if not names or set(names) - valid:
        raise SystemExit(f"--workflows {spec!r}: give one of {sorted(WORKFLOW_SETS)} or workflows from "
                         f"{sorted(valid)}")
    if len({workflow_set(w) for w in names}) > 1:
        raise SystemExit(f"--workflows {spec!r} mixes workflow sets; a collection uses one set")
    if only is not None:
        if only not in names:
            raise SystemExit(f"--workflow {only} is not in --workflows {spec}")
        return [only]
    return names


def prompt_pool(prompts: dict, topologies: list[str], workflows: list[str]) -> dict:
    """Per workflow: the generator's template pools, prompts drawn, distinct prompts among them."""
    out = {}
    for w in workflows:
        drawn = [p for t in topologies for p in prompts[(t, w)]]
        out[w] = {"template_pools": WORKFLOW_REGISTRY[WorkflowClass(w)].template_pools,
                  "drawn": len(drawn), "distinct": len(set(drawn))}
    return out


EDGE_CLOUD = "edge_cloud"


def parse_arm(spec: str, k: int, placement: str = "local") -> Arm:
    kv = dict(part.split("=", 1) for part in spec.split(","))
    if placement == "edge-cloud":            # the edge and cloud agents are configured where they run
        kv.setdefault("deployment", EDGE_CLOUD)
        kv.setdefault("model", "llama3.2:3b")
        kv.setdefault("tls", "on")
        if kv["tls"].lower() not in ("on", "1", "true", "yes") or "host" in kv or kv.get("defense", "none") != "none":
            raise SystemExit(f"bad --arm {spec!r}: edge-cloud arms are TLS on, without host= or defense=")
    unknown = set(kv) - {"name", "deployment", "model", "tls", "defense", "out", "ports", "pad", "host",
                         "pad_expect"}
    if unknown or not {"name", "deployment", "out"} <= set(kv):
        raise SystemExit(f"bad --arm {spec!r}: needs name, deployment, out; unknown keys {sorted(unknown)}")
    if kv["deployment"] not in DEPLOYMENTS and not (placement == "edge-cloud" and kv["deployment"] == EDGE_CLOUD):
        raise SystemExit(f"unknown deployment {kv['deployment']!r} (choose from {sorted(DEPLOYMENTS)})")
    pad = [int(b) for b in kv["pad"].split("/")] if kv.get("pad") else []
    expect = int(kv["pad_expect"]) if kv.get("pad_expect") else None
    if expect is not None and expect not in pad:
        raise SystemExit(f"bad --arm {spec!r}: pad_expect must be one of the pad buckets")
    return Arm(name=kv["name"], deployment=kv["deployment"],
               model=kv.get("model") or DEPLOYMENTS[kv["deployment"]]["default_model"],
               tls=kv.get("tls", "off").lower() in ("on", "1", "true", "yes"),
               defense=kv.get("defense", "none"), out=Path(kv["out"]),
               ports_base=int(kv.get("ports", 8100 + 100 * k)), host=kv.get("host") or None,
               pad=pad, pad_expect=expect)


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


async def _ready(c: httpx.AsyncClient, method: str, url: str, wait_s: float = 60, **kw) -> dict:
    """Retry until url answers 2xx (or wait_s passes); the JSON body."""
    end = time.time() + wait_s
    while True:
        try:
            r = await c.request(method, url, **kw)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as exc:
            if time.time() > end:
                raise RuntimeError(f"{method} {url} not answering: {exc}") from exc
            await asyncio.sleep(2.0)


async def start_edge(arm: Arm, a: argparse.Namespace) -> dict:
    """Edge-cloud arm, between captures: the cloud agents' cards and the ticket service answer,
    and the edge agent has fetched the cards and loaded its local model (POST /prepare)."""
    eps = edge_endpoints(arm.ports_base, a.cloud_host, a.ticket_host)
    async with httpx.AsyncClient(timeout=30, verify=tls.client_verify()) as c:
        for role in CLOUD_PORTS:
            await _ready(c, "GET", f"https://{eps[role]}/.well-known/agent-card.json")
        await _ready(c, "GET", f"https://{eps['ticket']}/health")
        return await _ready(c, "POST", f"{edge_url(arm, a)}/prepare", timeout=300)


def edge_url(arm: Arm, a: argparse.Namespace) -> str:
    return f"http://{a.edge_host}:{arm.ports_base + TRIGGER_PORT}"


async def wan_probe(arm: Arm, a: argparse.Namespace, target_ms: float) -> dict:
    """The edge agent's TCP connect times to the cloud alias, end to end, against the cloud round
    trip the emulation reproduces (target_rtt_ms); its connect time to the Mac's own address (never
    delayed: the base Wi-Fi round trip) is recorded alongside."""
    async with httpx.AsyncClient(timeout=120) as c:
        r = await _ready(c, "POST", f"{edge_url(arm, a)}/probe", json={"n": a.wan_probes})
        base = await _ready(c, "POST", f"{edge_url(arm, a)}/probe", json={"n": a.wan_probes, "target": "ticket"})
    dev = (r["median_ms"] - target_ms) / target_ms
    return {"arm": arm.name, "median_ms": r["median_ms"], "connect_ms": r["connect_ms"],
            "base_median_ms": base["median_ms"], "target_ms": target_ms,
            "deviation": dev, "ok": abs(dev) <= a.wan_tolerance}


def make_edge_collector(arm: Arm, workflow: str, a: argparse.Namespace, last: dict) -> TraceCollector:
    """One task = one trigger to the edge agent; the capture holds the gateway's flows to the cloud
    agents and the ticket service. `last` receives the edge agent's report of the task."""
    eps = edge_endpoints(arm.ports_base, a.cloud_host, a.ticket_host)

    # Same task-id format in every arm: the id travels in the ticket post.
    async def exec_fn(prompt: str) -> None:
        last.clear()
        async with httpx.AsyncClient(timeout=600) as c:
            r = await c.post(f"{edge_url(arm, a)}/task", json={
                "task_id": f"edge_{uuid.uuid4().hex[:8]}", "task_type": workflow, "content": prompt,
                "pad_buckets": arm.pad})
        r.raise_for_status()
        last.update(r.json())
        if not last.get("ok"):
            raise RuntimeError(f"edge agent: {last.get('error')}")

    return TraceCollector(
        orchestrator_fn=exec_fn,
        recorder=PacketRecorder(output_dir=arm.out, interface=a.interface,
                                agent_ports=[int(e.rsplit(":", 1)[1]) for e in eps.values()],
                                hosts=[a.edge_host]),
        workflow_class=WorkflowClass(workflow), topology=TopologyType.EDGE_CLOUD, agent_endpoints=eps,
        topology_edges=[["edge", role] for role in eps], output_dir=arm.out, deployment=EDGE_CLOUD,
    )


def edge_sidecar(workflow: str, prompt: str, a: argparse.Namespace, last: dict) -> dict:
    """Edge-cloud sidecar fields. escalated and cloud_role follow the routing rule; the edge
    agent's own report of what it did must agree (check_lan_capture.py checks the packets)."""
    route = ROUTES[workflow]
    pi = (last.get("pi") or {})
    out = {"placement": EDGE_CLOUD, "task_type": workflow, "escalated": "yes" if route else "no",
           "vantages": VANTAGES, "padded_endpoints": PADDED_ENDPOINTS, "edge_host": a.edge_host,
           "prompt_bytes": len(prompt.encode()),
           "edge_report": {k: last.get(k) for k in ("escalated", "cloud_role", "answer_chars", "ticket_id",
                                                     "seconds", "padded", "model", "error")},
           "pi_temp_c": (pi.get("after") or {}).get("temp_c"), "pi_throttled": pi.get("throttled")}
    if route:
        out["cloud_role"] = route
    if last.get("ok") and (last.get("escalated") != bool(route) or last.get("cloud_role") != route):
        out["edge_report"]["mismatch"] = True
    return out


def pace(meta: dict) -> dict:
    """Seconds per trace over the session (median gap between consecutive trace starts, gaps over
    10 minutes dropped: a stop between nights) and what 1,800 and 1,200 traces would take."""
    ts = sorted(e["start_ts"] for e in meta["schedule"])
    gaps = [b - x for x, b in zip(ts, ts[1:]) if b - x < 600]
    if not gaps:
        return {}
    import statistics
    s = statistics.median(gaps)
    return {"median_s_per_trace": s, "traces": len(ts), "projected_hours": {"1800": 1800 * s / 3600,
                                                                             "1200": 1200 * s / 3600}}


async def main(a: argparse.Namespace) -> None:
    edge = a.placement == "edge-cloud"
    if edge:                          # addresses and interface from configs/c2_network.conf unless given
        net = c2_network()
        a.edge_host = require(a.edge_host or net["C2_PI"], "the Pi's address (C2_PI)")
        a.cloud_host = require(a.cloud_host or net["C2_CLOUD"], "the cloud alias (C2_CLOUD)")
        a.ticket_host = require(a.ticket_host or net["C2_MAC"], "the Mac's address (C2_MAC)")
        a.interface = a.interface or require(net["C2_IFACE"], "the capture interface (C2_IFACE)")
    a.interface = a.interface or "lo0"
    arms = [parse_arm(s, k, a.placement) for k, s in enumerate(a.arm)]
    if edge and a.topology:
        raise SystemExit("--topology does not apply to --placement edge-cloud")
    wan_target = json.loads(Path(a.wan_target).read_text())["target_rtt_ms"] if a.wan_target else None
    network = None
    if edge and not a.edge_host.startswith("127."):          # before each session: the Mac and the Pi's route
        from scripts.check_c2_network import check_network
        network = check_network(c2_network(), [arm.ports_base for arm in arms], a.edge_host)
        for c in network["checks"]:
            logger.info("  network %-5s %s  %s", c["check"], "ok" if c["ok"] else "FAIL", c["detail"])
        if not network["ok"]:
            raise SystemExit("network check failed (scripts/check_c2_network.py): "
                             + "; ".join(c["detail"] for c in network["checks"] if not c["ok"]))
    if len({arm.name for arm in arms}) != len(arms) or len({arm.out for arm in arms}) != len(arms):
        raise SystemExit("arm names and output dirs must be unique")
    if any(arm.tls for arm in arms):
        tls.configure(a.tls_dir, default_on=False)
    num_predict = a.num_predict if a.num_predict > 0 else None
    for arm in arms:
        arm.out.mkdir(parents=True, exist_ok=True)
        if any(arm.out.glob("*.pcap")) and not (a.allow_existing or a.resume):
            sys.exit(f"{arm.out} already holds pcaps; move it aside, or pass --resume")

    topologies = [EDGE_CLOUD] if edge else [a.topology] if a.topology else TOPOLOGIES
    workflows = resolve_workflows(a.workflows, a.workflow)
    if edge and set(workflows) - set(ROUTES):
        raise SystemExit(f"--placement edge-cloud routes only {sorted(ROUTES)} (--workflows iot)")
    meta_paths = [arm.out / "session_meta.json" for arm in arms]
    meta = json.loads(meta_paths[0].read_text()) if a.resume and meta_paths[0].exists() else None
    if meta is not None and meta["workflows"] != workflows:
        raise SystemExit(f"--resume: the session collected {meta['workflows']}, not {workflows}")
    prompts = {(t, w): WORKFLOW_REGISTRY[WorkflowClass(w)]().sample_prompts(
                   n=a.n, seed=prompt_seed(0 if t == EDGE_CLOUD else TOPOLOGIES.index(t), w, a.seed_offset))
               for t in (topologies if edge else TOPOLOGIES) for w in workflows}
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
                      "host": x.host, "pad_buckets": x.pad, "pad_expect": x.pad_expect} for x in arms],
            "interface": a.interface, "ollama_url": a.ollama_url,
            "num_predict": num_predict, "n_per_condition": a.n, "rounds": a.rounds,
            "seed_offset": a.seed_offset, "order_seed": SEED, "topologies": topologies,
            "workflows": workflows, "workflow_set": sorted({workflow_set(w) for w in workflows}),
            "prompt_seed": "topology_index × 4 + index of the workflow in its set + 100 + seed_offset "
                           "(workflows.prompt_seed)",
            "prompt_pool": prompt_pool(prompts, topologies, workflows),
            "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "schedule": [], "failures": 0, "tls_params": {},
            "placement": a.placement,
            "audit_null": {"labels": list(AUDIT_NULL_LABELS), "seed": AUDIT_NULL_SEED,
                           "rule": "random.Random(f'{seed}:{prompt_group}').choice(labels)"},
        }

    if network is not None:                                   # one per session (a --resume adds one)
        meta.setdefault("network_checks", []).append({"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **network})

    def save() -> None:
        for p in meta_paths:
            p.write_text(json.dumps(meta, indent=2))

    done = {(e["item"], e["arm"]) for e in meta["schedule"] if e["success"]}
    deadline = time.time() + a.deadline_hours * 3600 if a.deadline_hours else None
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
                if edge:
                    meta.setdefault("edge", {})[arm.name] = await start_edge(arm, a)
                    if wan_target is not None:
                        probe = {"round": rnd, **await wan_probe(arm, a, wan_target)}
                        meta.setdefault("wan_probes", []).append(probe)
                        save()
                        logger.info("  WAN probe (%s): cloud alias %.1f ms (base %.1f ms), target %.1f ms",
                                    arm.name, probe["median_ms"], probe["base_median_ms"], wan_target)
                        if not probe["ok"]:
                            raise SystemExit(f"{arm.name}: the Pi's round trip to the cloud alias "
                                             f"({probe['median_ms']:.1f} ms) is outside {wan_target:.1f} ms ± "
                                             f"{a.wan_tolerance:.0%}: is the WAN emulation on "
                                             "(sudo bash scripts/wan_emulation.sh show)?")
                    if arm.name not in meta["tls_params"]:
                        eps = edge_endpoints(arm.ports_base, a.cloud_host, a.ticket_host)
                        meta["tls_params"][arm.name] = {
                            role: await probe_tls(int(eps[role].rsplit(":", 1)[1]), host=eps[role].rsplit(":", 1)[0])
                            for role in ("diagnostics", "ticket")}
                        logger.info("  TLS parameters (%s): %s", arm.name, meta["tls_params"][arm.name])
                    continue
                await start_sets(arm, topologies, num_predict, a.ollama_url)
                if arm.tls and arm.name not in meta["tls_params"]:
                    meta["tls_params"][arm.name] = await probe_tls(arm.ports(topologies[0])["executor"],
                                                                   host=arm.agent_host)
                    logger.info("  TLS parameters (%s): %s", arm.name, meta["tls_params"][arm.name])
            last: dict = {}                                 # the edge agent's report of the current task
            collectors = {(arm.name, t, w): make_edge_collector(arm, w, a, last) if edge else
                          make_collector(arm, t, w, num_predict, a.interface, a.ollama_url)
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
                            group = prompt_group(sc.get("input_prompt") or prompts[(t, w)][i])
                            sc.update({"prompt_group": group, "audit_null": audit_null(group),
                                       "collection_id": a.collection_id, "arm": arm.name, "round": rnd,
                                       "position": position, "seed_offset": a.seed_offset,
                                       "model": arm.model, "tls": arm.tls, "defense": arm.defense,
                                       "agent_host": arm.host, "pad_buckets": arm.pad,
                                       "pad_expect": arm.pad_expect})
                            if edge:
                                sc.update(edge_sidecar(w, prompts[(t, w)][i], a, last))
                                entry["pi_throttled"] = sc["pi_throttled"]
                            sidecar.write_text(json.dumps(sc, indent=2))
                        if run.success:
                            done.add((item, arm.name))
                            break
                        meta["failures"] += 1
                        if edge:                            # remote agents: wait until they answer again
                            await start_edge(arm, a)
                        else:
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
    meta["pace"] = pace(meta)
    if edge:
        meta["throttled_traces"] = sum(1 for e in meta["schedule"] if e.get("pi_throttled"))
    planned = a.n * len(topologies) * len(workflows)
    meta["complete_items"] = sum(1 for t in topologies for w in workflows for i in range(a.n)
                                 if all((f"{t}/{w}/{i}", arm.name) in done for arm in arms))
    save()
    print(f"\n{a.collection_id}: {meta['complete_items']} of {planned} items complete in every arm, "
          f"{meta['failures']} failed attempts → " + ", ".join(f"{x.out}/" for x in arms))
    if meta["pace"]:
        print(f"pace: {meta['pace']['median_s_per_trace']:.1f} s per trace; 1,800 traces ≈ "
              f"{meta['pace']['projected_hours']['1800']:.1f} h, 1,200 ≈ {meta['pace']['projected_hours']['1200']:.1f} h"
              + (f"; {meta['throttled_traces']} traces taken while the Pi was throttled" if edge else ""))


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Collect one or more arms in one session, one trace at a time")
    p.add_argument("--arm", action="append", required=True,
                   help="name=...,deployment=a|b|langgraph,model=...,tls=on|off,defense=none|pad|rate|both,"
                        "out=DIR[,ports=BASE][,pad=B1/B2/...[,pad_expect=B]][,host=ADDR]  (repeat for more arms)")
    p.add_argument("--ollama-url", default=OLLAMA, dest="ollama_url",
                   help="Ollama for the model warm-up and the agents this process runs")
    p.add_argument("--interface", default=None,
                   help="capture interface (default lo0; the Ethernet port for host=; for --placement "
                        "edge-cloud, C2_IFACE from configs/c2_network.conf)")
    p.add_argument("--collection-id", required=True, dest="collection_id")
    p.add_argument("--n", type=int, default=50, help="traces per topology × workflow condition, per arm")
    p.add_argument("--rounds", type=int, default=5)
    p.add_argument("--seed-offset", type=int, required=True, dest="seed_offset",
                   help="prompt seed offset; register it in docs/PROMPT_REGISTRY.md")
    p.add_argument("--num-predict", type=int, default=DEFAULT_NUM_PREDICT, dest="num_predict")
    p.add_argument("--topology", choices=TOPOLOGIES, default=None)
    p.add_argument("--placement", choices=["local", "edge-cloud"], default="local",
                   help="local: this process runs the orchestrator (and the agents, unless host=); "
                        "edge-cloud: the edge agent on the gateway runs each task (C2)")
    p.add_argument("--edge-host", default=None, dest="edge_host", help="edge-cloud: the Pi (default C2_PI)")
    p.add_argument("--cloud-host", default=None, dest="cloud_host",
                   help="edge-cloud: the cloud alias (default C2_CLOUD)")
    p.add_argument("--ticket-host", default=None, dest="ticket_host",
                   help="edge-cloud: the Mac, running the ticket service (default C2_MAC)")
    p.add_argument("--wan-target", default=None, dest="wan_target",
                   help="edge-cloud: data/c2_wan_emulation.json; each round checks the emulated round trip")
    p.add_argument("--wan-tolerance", type=float, default=0.20, dest="wan_tolerance")
    p.add_argument("--wan-probes", type=int, default=10, dest="wan_probes")
    p.add_argument("--workflows", default="classic",
                   help=f"workflow set ({', '.join(WORKFLOW_SETS)}; classic = every collection up to C1, iot = C2) "
                        "or comma-separated workflows of one set")
    p.add_argument("--workflow", choices=[wf.value for wf in WorkflowClass], default=None,
                   help="only this workflow (must be in --workflows)")
    p.add_argument("--tls-dir", default="data/tls", dest="tls_dir")
    p.add_argument("--deadline-hours", type=float, default=None, dest="deadline_hours")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--allow-existing", action="store_true", dest="allow_existing")
    p.add_argument("--pilot", action="store_true",
                   help="one trace per topology (first workflow) per arm, into <out>_pilot/")
    args = p.parse_args()
    if args.pilot:
        args.n, args.rounds = 1, 1
        args.workflow = args.workflow or resolve_workflows(args.workflows, None)[0]
        args.arm = [",".join(f"out={v}_pilot" if kv.startswith("out=") else kv
                             for kv, v in ((kv, kv.split("=", 1)[1]) for kv in s.split(",")))
                    for s in args.arm]
        args.allow_existing = True
        args.collection_id = f"{args.collection_id}-pilot"
    return args


if __name__ == "__main__":
    asyncio.run(main(_parse()))
