"""
Edge agent of the edge-cloud placement (collection C2, docs/LAN_SETUP.md): an A2A agent on the
building's IoT gateway (the Raspberry Pi) that answers some tasks with a small local model and
escalates the rest to cloud agents, then files every result with the building's ticket service.

Routing is a fixed rule on the task type, as a building management system tags its requests:

    alert_triage                       answered on the gateway (local model); never leaves the building
    sensor_analysis, fault_diagnosis   → cloud agent "diagnostics"
    procedure_lookup                   → cloud agent "knowledge"

Every task then POSTs its result to the ticket service. Every link is TLS. Input padding
(pad_buckets, sent with each task by the collector) applies to the request to the cloud agent;
ticket posts are not padded. Each task opens its own connections and closes them before it
returns, so a per-task capture holds whole connections; the cloud agents' cards are fetched by
prepare(), outside any capture.

Port layout per arm (base B, docs/LAN_SETUP.md): diagnostics B+1 and knowledge B+2 on the cloud
address, tickets B+5 on the building server, the task trigger B+9 on the gateway. The trigger is
the collector's channel to the gateway (it models sensors wired to the gateway, not a network
flow); captures leave its port out, so no observer view contains it.

scripts/serve_edge.py serves the trigger endpoints:
    POST /task     {"task_id", "task_type", "content", "pad_buckets"} → run one task
    POST /prepare  fetch the cloud agents' cards and load the local model (between captures)
    POST /probe    {"n", "target": cloud|ticket|internet} → TCP connect times from the gateway
    GET  /health   configuration
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import statistics
import subprocess
import time
import uuid
from pathlib import Path

from a2a.client import A2AClient
from a2a.types import Message, MessageSendParams, Part, Role, SendStreamingMessageRequest, TextPart

from .base import AgentConfig, AgentRole, BaseA2AAgent, _extract_event_text, pad_request

logger = logging.getLogger(__name__)

# port offsets from an arm's base
CLOUD_PORTS = {"diagnostics": 1, "knowledge": 2}
TICKET_PORT = 5
TRIGGER_PORT = 9
ROUTES = {"sensor_analysis": "diagnostics", "fault_diagnosis": "diagnostics",
          "procedure_lookup": "knowledge", "alert_triage": None}
# what each observer sees (docs/LAN_SETUP.md): v1 the building network, v2 upstream of the building
VANTAGES = {"v1": ["diagnostics", "knowledge", "ticket"], "v2": ["diagnostics", "knowledge"]}
PADDED_ENDPOINTS = ["diagnostics", "knowledge"]

TRIAGE_PROMPT = ("You are the edge assistant on a building's IoT gateway. Triage this alert: give a "
                 "priority (P1-P4), the responsible team and the first action, in three short lines.\n\n")


NETWORK_CONF = Path(__file__).resolve().parent.parent / "configs" / "c2_network.conf"
NETWORK_KEYS = ("C2_IFACE", "C2_MAC", "C2_PI", "C2_CLOUD", "C2_PI_IFACE", "C2_PI_USER")


def c2_network(path: Path | None = None) -> dict[str, str]:
    """The C2 addresses and interfaces: configs/c2_network.conf (KEY=VALUE, # comments), each
    overridden by an environment variable of the same name. Unset values are empty strings."""
    net = dict.fromkeys(NETWORK_KEYS, "")
    conf = Path(path or NETWORK_CONF)
    if conf.exists():
        for line in conf.read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if "=" in line:
                k, v = (x.strip() for x in line.split("=", 1))
                net[k] = v.strip("'\"")
    for k in NETWORK_KEYS:
        if os.environ.get(k):
            net[k] = os.environ[k]
    return net


def require(value: str | None, what: str) -> str:
    """value, or stop with a pointer to the network config."""
    if not value:
        raise SystemExit(f"{what} is not set: fill it in configs/c2_network.conf (docs/LAN_SETUP.md), "
                         "or set it in the environment or on the command line")
    return value


def endpoints(base: int, cloud_host: str, ticket_host: str) -> dict[str, str]:
    """The servers an arm's tasks talk to, as host:port (the sidecar's agent_endpoints)."""
    eps = {role: f"{cloud_host}:{base + off}" for role, off in CLOUD_PORTS.items()}
    eps["ticket"] = f"{ticket_host}:{base + TICKET_PORT}"
    return eps


def pi_telemetry() -> dict:
    """CPU temperature and throttling state from vcgencmd (Raspberry Pi); None elsewhere.
    throttled_now: any of the current-state bits (under-voltage, frequency capped, throttled,
    soft temperature limit) is set."""
    def run(*cmd: str) -> str | None:
        try:
            return subprocess.run(["vcgencmd", *cmd], capture_output=True, text=True, timeout=5).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None
    temp, thr = run("measure_temp"), run("get_throttled")
    try:
        temp_c = float(temp.split("=")[1].split("'")[0]) if temp else None
    except (IndexError, ValueError):
        temp_c = None
    try:
        bits = int(thr.split("=")[1], 16) if thr else None
    except (IndexError, ValueError):
        bits = None
    return {"temp_c": temp_c, "throttled": None if bits is None else hex(bits),
            "throttled_now": None if bits is None else bool(bits & 0xF)}


class EdgeAgent(BaseA2AAgent):
    def __init__(self, base: int, cloud_host: str, ticket_host: str, ollama_url: str = "http://127.0.0.1:11434",
                 model: str = "llama3.2:1b", num_predict: int | None = 128, tls_on: bool = True) -> None:
        super().__init__(AgentConfig(role=AgentRole.EDGE, port=base + TRIGGER_PORT, ollama_base_url=ollama_url,
                                     ollama_model=model, ollama_num_predict=num_predict, tls=tls_on))
        from agents import tls
        scheme = tls.scheme(tls_on)
        self.base, self.cloud_host, self.ticket_host = base, cloud_host, ticket_host
        eps = endpoints(base, cloud_host, ticket_host)
        self.cloud = {role: f"{scheme}://{eps[role]}" for role in CLOUD_PORTS}
        self.ticket_url = f"{scheme}://{eps['ticket']}/tickets"
        self._lock = asyncio.Lock()

    def info(self) -> dict:
        return {"base": self.base, "cloud": self.cloud, "ticket": self.ticket_url, "model": self.config.ollama_model,
                "num_predict": self.config.ollama_num_predict, "ollama": self.config.ollama_base_url,
                "routes": ROUTES, "host": platform.node(), "python": platform.python_version(),
                "pi": pi_telemetry(), "cards": sorted(self._card_cache)}

    async def prepare(self) -> dict:
        """Fetch the cloud agents' cards and load the local model, outside any capture."""
        async with self:
            client = await self._get_http_client()
            for url in self.cloud.values():
                if url not in self._card_cache:
                    await self._resolve_card(client, url)
            r = await client.post(f"{self.config.ollama_base_url}/api/generate", timeout=300, json={
                "model": self.config.ollama_model, "prompt": "ok", "stream": False, "keep_alive": "60m",
                "options": {"num_predict": 1}})
            r.raise_for_status()
        return self.info()

    def probe_targets(self) -> dict[str, tuple[str, int]]:
        return {"cloud": (self.cloud_host, self.base + CLOUD_PORTS["diagnostics"]),
                "ticket": (self.ticket_host, self.base + TICKET_PORT),
                "internet": ("1.1.1.1", 443)}               # through the building router's NAT

    async def probe(self, n: int = 30, target: str = "cloud") -> dict:
        """TCP connect time from the gateway to the cloud alias (the emulated WAN), the ticket
        service (must not be delayed) or the internet (the router still routes), n times: one
        round trip each."""
        host, port = self.probe_targets()[target]
        ms = []
        for _ in range(n):
            t = time.perf_counter()
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), 10)
            ms.append((time.perf_counter() - t) * 1000)
            writer.close()
            await writer.wait_closed()
            await asyncio.sleep(0.1)
        return {"target": target, "host": host, "port": port, "n": n, "connect_ms": ms,
                "median_ms": statistics.median(ms)}

    async def _call_cloud(self, url: str, task_id: str, content: str, pad: list[int]) -> str:
        client = await self._get_http_client()
        card = self._card_cache.get(url) or await self._resolve_card(client, url)
        card = card.model_copy(update={"url": url})          # the card advertises its bind address
        msg = Message(role=Role.user, message_id=uuid.uuid4().hex, parts=[Part(root=TextPart(text=content))])
        request = SendStreamingMessageRequest(id=str(uuid.uuid4()), params=MessageSendParams(message=msg))
        if pad:
            pad_request(request, pad)
        artifact, status = [], []
        async for response in A2AClient(client, agent_card=card).send_message_streaming(
                request, http_kwargs={"timeout": 180.0}):
            result = getattr(getattr(response, "root", None), "result", None)
            if result is None:
                raise RuntimeError(f"cloud agent error: {getattr(response.root, 'error', response)}")
            state = getattr(getattr(result, "status", None), "state", None)
            if getattr(state, "value", state) == "failed":
                raise RuntimeError(f"cloud agent task failed: {_extract_event_text(response)[1][:200]}")
            kind, chunk = _extract_event_text(response)
            (artifact if kind == "artifact" else status).append(chunk)
        return "".join(artifact) or "".join(status)

    async def run_task(self, task_id: str, task_type: str, content: str, pad_buckets: list[int] | None = None) -> dict:
        if task_type not in ROUTES:
            raise ValueError(f"unknown task type {task_type!r}")
        route = ROUTES[task_type]
        async with self._lock:
            pi_before = pi_telemetry()
            t0 = time.perf_counter()
            async with self:                       # this task's connections, closed before returning
                if route:
                    answer = await self._call_cloud(self.cloud[route], task_id, content, list(pad_buckets or []))
                else:
                    answer = await self.llm_generate(TRIAGE_PROMPT + content)
                t1 = time.perf_counter()
                client = await self._get_http_client()
                r = await client.post(self.ticket_url, json={"task_id": task_id, "category": task_type,
                                                             "source": "edge-gateway", "summary": answer})
                r.raise_for_status()
                ticket = r.json().get("ticket_id")
            t2 = time.perf_counter()
            pi_after = pi_telemetry()
        throttled = [x["throttled_now"] for x in (pi_before, pi_after) if x["throttled_now"] is not None]
        return {"ok": True, "task_id": task_id, "task_type": task_type, "escalated": route is not None,
                "cloud_role": route, "answer_chars": len(answer), "ticket_id": ticket,
                "seconds": {"answer": t1 - t0, "ticket": t2 - t1, "total": t2 - t0},
                "pi": {"before": pi_before, "after": pi_after, "throttled": any(throttled) if throttled else None},
                "padded": bool(route and pad_buckets), "model": None if route else self.config.ollama_model}


def trigger_app(edge: EdgeAgent):
    """The edge agent's trigger endpoints (plain HTTP; captures leave this port out)."""
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def task(request: Request) -> JSONResponse:
        b = await request.json()
        try:
            return JSONResponse(await edge.run_task(b["task_id"], b["task_type"], b["content"], b.get("pad_buckets")))
        except Exception as exc:  # noqa: BLE001 — the collector records the error and retries
            logger.exception("task %s failed", b.get("task_id"))
            return JSONResponse({"ok": False, "task_id": b.get("task_id"), "error": f"{type(exc).__name__}: {exc}",
                                 "pi": {"after": pi_telemetry()}})

    async def prepare(_: Request) -> JSONResponse:
        return JSONResponse(await edge.prepare())

    async def probe(request: Request) -> JSONResponse:
        b = await request.json() if (await request.body()) else {}
        target = b.get("target", "cloud")
        if target not in edge.probe_targets():
            return JSONResponse({"error": f"unknown target {target!r}"}, status_code=400)
        try:
            return JSONResponse(await edge.probe(int(b.get("n", 30)), target))
        except (OSError, asyncio.TimeoutError) as exc:
            return JSONResponse({"target": target, "error": f"{type(exc).__name__}: {exc}"}, status_code=502)

    async def health(_: Request) -> JSONResponse:
        return JSONResponse(edge.info())

    return Starlette(routes=[Route("/task", task, methods=["POST"]), Route("/prepare", prepare, methods=["POST"]),
                             Route("/probe", probe, methods=["POST"]), Route("/health", health)])
