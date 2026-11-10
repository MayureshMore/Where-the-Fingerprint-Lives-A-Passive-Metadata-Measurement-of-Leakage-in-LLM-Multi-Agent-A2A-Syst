"""
Cloud side of the edge-cloud placement (collection C2, docs/LAN_SETUP.md): two A2A agents that
stand in for a building-operations cloud service, and the building's maintenance-ticket service.

    diagnostics   sensor analysis and fault diagnosis: an internal pass that lists the
                  observations in the data, then a streamed diagnosis report
    knowledge     procedure lookup: an internal pass that names the procedure sections that
                  apply, then a streamed answer with the steps and safety notes
    tickets       HTTPS POST /tickets: the edge agent files every task's result here (a local
                  network application, not an agent)

Both agents use Ollama on the machine that hosts them (in C2 the Mac, on localhost), so their
model calls never cross the link. scripts/serve_cloud.py serves them.
"""

from __future__ import annotations

import logging
import time

from .base import AgentConfig, AgentRole, BaseA2AAgent, EmitFn

logger = logging.getLogger(__name__)


class DiagnosticsAgent(BaseA2AAgent):
    def __init__(self, config: AgentConfig) -> None:
        config.role = AgentRole.DIAGNOSTICS
        config.description = config.description or "Remote diagnostics for building and plant equipment"
        super().__init__(config)

    async def handle_task(self, task_id: str, content: str, emit: EmitFn | None = None) -> str:
        logger.info("[diagnostics] task %s", task_id)
        observations = await self.llm_generate(
            "You are a remote diagnostics service for building and factory equipment. List the key "
            "observations in the data below (anomalies, out-of-range values, error patterns) as short "
            f"bullet points.\n\nDATA:\n{content}")
        return await self.llm_stream(
            "You are a remote diagnostics service. Using the observations and the request, write a "
            "diagnosis report with the sections Findings, Likely cause and Recommended actions.\n\n"
            f"OBSERVATIONS:\n{observations}\n\nREQUEST:\n{content[:2000]}", emit)


class KnowledgeAgent(BaseA2AAgent):
    def __init__(self, config: AgentConfig) -> None:
        config.role = AgentRole.KNOWLEDGE
        config.description = config.description or "Maintenance procedures and operating knowledge"
        super().__init__(config)

    async def handle_task(self, task_id: str, content: str, emit: EmitFn | None = None) -> str:
        logger.info("[knowledge] task %s", task_id)
        sections = await self.llm_generate(
            "You are a maintenance knowledge service. Name the procedure documents and sections that "
            f"answer this question, as a short numbered list.\n\nQUESTION: {content}")
        return await self.llm_stream(
            "You are a maintenance knowledge service. Answer the question with numbered steps and the "
            "safety notes that apply, using these procedure sections.\n\n"
            f"SECTIONS:\n{sections}\n\nQUESTION: {content}", emit)


CLOUD_AGENTS = {"diagnostics": DiagnosticsAgent, "knowledge": KnowledgeAgent}


def ticket_app():
    """The maintenance-ticket service: POST /tickets files one ticket (201 with its id),
    GET /health reports how many it has received."""
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    tickets: list[dict] = []

    async def create(request: Request) -> JSONResponse:
        body = await request.json()
        tid = f"T-{len(tickets) + 1:06d}"
        tickets.append({"ticket_id": tid, "task_id": body.get("task_id"), "category": body.get("category"),
                        "summary_chars": len(str(body.get("summary", ""))), "received": time.time()})
        return JSONResponse({"ticket_id": tid, "status": "open"}, status_code=201)

    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"ok": True, "tickets": len(tickets)})

    return Starlette(routes=[Route("/tickets", create, methods=["POST"]), Route("/health", health)])
