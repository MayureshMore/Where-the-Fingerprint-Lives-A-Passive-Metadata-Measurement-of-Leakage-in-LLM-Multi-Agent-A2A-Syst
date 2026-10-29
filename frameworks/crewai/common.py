"""Shared brains + A2A server bootstrap for the CrewAI cross-framework traffic experiment.

Exp 1 separated A2A from AutoGen at AUROC 1.0, but the driver was a TRANSPORT-framing packet
size (A2A = SSE-over-HTTP; AutoGen = gRPC/HTTP2). That does not answer the referee's real
question: can an observer distinguish A2A from another agentic framework on the SAME transport?

CrewAI is that test. CrewAI's OWN native remote-agent transport IS the A2A protocol
(crewai.a2a, JSON-RPC 2.0 + SSE over HTTP). CrewAI has NO turnkey serve helper, so we serve the
specialists on the a2a-sdk server stack -- the identical server library and version (a2a-sdk
0.3.26) the positive class (Google's a2a_mcp) uses -- with a real CrewAI Agent/Task/Crew brain
(local ollama, no spend) inside each. Transport + server lib are IDENTICAL to the positive class;
the ONLY variable is the agent framework's orchestration/reasoning behaviour. Any separability is
therefore behavioural/structural, not transport framing -- exactly the same-transport case Exp 1
could not reach. Domain is matched to the A2A positives (travel) so FRAMEWORK is the variable.

The A2A server path (executor + A2AStarletteApplication + DefaultRequestHandler + uvicorn) is a
verbatim inline copy of a2a_mcp's GenericAgentExecutor/__main__.py, so the wire protocol emitted
is byte-for-byte the a2a-sdk 0.3.26 JSON-RPC+SSE the positive class emits. Role is a ground-truth
LABEL by server port, never a feature.
"""
from __future__ import annotations

import asyncio
import logging
import os

os.environ.setdefault("CREWAI_TELEMETRY_OPT_OUT", "1")
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "1")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

logger = logging.getLogger(__name__)

OLLAMA_MODEL = "ollama/llama3.2:3b"
OLLAMA_BASE = "http://localhost:11434"

ROLE_PORT = {
    "planner":       (10201, True),
    "air_ticketing": (10203, False),
    "hotel":         (10204, False),
    "car_rental":    (10205, False),
}

ROLE_SPEC = {
    "planner": dict(
        role="Travel Planner",
        goal="Produce a concise ordered plan for a complete trip (flights, hotel, car).",
        backstory="You are a meticulous travel coordinator who breaks a trip into clear booking steps.",
        expected="A short numbered plan (4-6 steps) covering flights, hotel and car rental.",
    ),
    "air_ticketing": dict(
        role="Air Ticketing Agent",
        goal="Recommend specific round-trip flight options for the requested route and dates.",
        backstory="You are an airline booking specialist who quotes concrete flights, times and fares.",
        expected="2-3 concrete round-trip flight options with airline, times and price.",
    ),
    "hotel": dict(
        role="Hotel Booking Agent",
        goal="Recommend specific hotels for the destination and stay length.",
        backstory="You are a hotel booking specialist who quotes concrete properties and nightly rates.",
        expected="2-3 concrete hotel options with name, area and nightly rate.",
    ),
    "car_rental": dict(
        role="Car Rental Agent",
        goal="Recommend specific rental cars for the destination and dates.",
        backstory="You are a car rental specialist who quotes concrete vehicles and daily rates.",
        expected="2-3 concrete rental-car options with class, vendor and daily rate.",
    ),
}


class CrewAiAgent:
    """A leaf brain backed by a real CrewAI single-agent Crew on local ollama.

    Exposes the exact async .stream(query, context_id, task_id) interface the inline
    GenericAgentExecutor consumes, so the a2a-sdk server path is unchanged from a2a_mcp."""

    def __init__(self, role: str) -> None:
        self._role = role
        self.agent_name = f"CrewAI-{role}"
        spec = ROLE_SPEC[role]
        from crewai import Agent, LLM

        self._llm = LLM(model=OLLAMA_MODEL, base_url=OLLAMA_BASE)
        self._agent = Agent(
            role=spec["role"], goal=spec["goal"], backstory=spec["backstory"],
            llm=self._llm, verbose=False, allow_delegation=False, max_iter=2,
        )
        self._expected = spec["expected"]

    def _run(self, query: str) -> str:
        from crewai import Task, Crew, Process

        task = Task(description=query, expected_output=self._expected, agent=self._agent)
        crew = Crew(agents=[self._agent], tasks=[task], process=Process.sequential, verbose=False)
        return str(crew.kickoff())

    async def stream(self, query: str, context_id: str, task_id: str):
        text = await asyncio.to_thread(self._run, query)
        yield {"is_task_complete": True, "require_user_input": False,
               "response_type": "text", "content": text}


def _make_executor():
    """Inline copy of a2a_mcp's GenericAgentExecutor (a2a-sdk 0.3.26), so we depend only on
    a2a-sdk, not the a2a_mcp package (which imports google.generativeai)."""
    from a2a.server.agent_execution import AgentExecutor, RequestContext
    from a2a.server.events import EventQueue
    from a2a.server.tasks import TaskUpdater
    from a2a.types import (
        DataPart, TaskState, TextPart, UnsupportedOperationError,
    )
    from a2a.utils import new_agent_text_message, new_task
    from a2a.utils.errors import ServerError

    class GenericAgentExecutor(AgentExecutor):
        def __init__(self, agent):
            self.agent = agent

        async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
            query = context.get_user_input()
            task = context.current_task
            if not task:
                task = new_task(context.message)
                await event_queue.enqueue_event(task)
            updater = TaskUpdater(event_queue, task.id, task.context_id)
            async for item in self.agent.stream(query, task.context_id, task.id):
                is_complete = item["is_task_complete"]
                needs_input = item["require_user_input"]
                if is_complete:
                    part = (DataPart(data=item["content"]) if item["response_type"] == "data"
                            else TextPart(text=item["content"]))
                    await updater.add_artifact([part], name=f"{self.agent.agent_name}-result")
                    await updater.complete()
                    break
                if needs_input:
                    await updater.update_status(
                        TaskState.input_required,
                        new_agent_text_message(item["content"], task.context_id, task.id),
                        final=True)
                    break
                await updater.update_status(
                    TaskState.working,
                    new_agent_text_message(item["content"], task.context_id, task.id))

        async def cancel(self, request: RequestContext, event_queue: EventQueue):
            raise ServerError(error=UnsupportedOperationError())

    return GenericAgentExecutor


def build_agent_card(role: str, host: str, port: int):
    from a2a.types import AgentCapabilities, AgentCard, AgentSkill

    spec = ROLE_SPEC[role]
    skill = AgentSkill(
        id=f"{role}_skill", name=spec["role"], description=spec["goal"],
        tags=[role], examples=[f"Handle the {role} portion of a trip request."],
    )
    return AgentCard(
        name=f"CrewAI {spec['role']}", description=spec["goal"],
        url=f"http://{host}:{port}/", version="1.0.0",
        capabilities=AgentCapabilities(streaming=True, pushNotifications=False,
                                       stateTransitionHistory=False),
        defaultInputModes=["text", "text/plain"],
        defaultOutputModes=["text", "text/plain"],
        skills=[skill],
    )


def serve(role: str, host: str = "localhost") -> None:
    """Start a CrewAI-backed A2A server for role -- mirrors a2a_mcp/agents/__main__.py exactly."""
    import httpx
    import uvicorn
    from a2a.server.apps import A2AStarletteApplication
    from a2a.server.request_handlers import DefaultRequestHandler
    from a2a.server.tasks import (
        BasePushNotificationSender, InMemoryPushNotificationConfigStore, InMemoryTaskStore,
    )
    GenericAgentExecutor = _make_executor()

    port, _ = ROLE_PORT[role]
    card = build_agent_card(role, host, port)
    client = httpx.AsyncClient()
    cfg_store = InMemoryPushNotificationConfigStore()
    sender = BasePushNotificationSender(client, config_store=cfg_store)
    handler = DefaultRequestHandler(
        agent_executor=GenericAgentExecutor(CrewAiAgent(role)),
        task_store=InMemoryTaskStore(), push_config_store=cfg_store, push_sender=sender,
    )
    app = A2AStarletteApplication(agent_card=card, http_handler=handler)
    logging.basicConfig(level=logging.INFO)
    logger.info("CrewAI %s server on %s:%d", role, host, port)
    uvicorn.run(app.build(), host=host, port=port, log_level="warning")
