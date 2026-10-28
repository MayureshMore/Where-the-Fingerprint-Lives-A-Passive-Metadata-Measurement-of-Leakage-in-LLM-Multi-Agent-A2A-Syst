"""MATCHED-PAIR CrewAI deployment for §13.1 — mirrors deployment A exactly, so the ONLY variable
is the agent framework.

Deployment A: 4 roles (orchestrator/executor/retriever/validator) chained
orchestrator->executor->retriever->validator, each an a2a-sdk 0.3.26 A2AStarletteApplication
server calling local ollama llama3.2:3b, agents call downstream via A2A send_message_streaming.

This module builds the SAME: 4 CrewAI Agent brains with the SAME role semantics as A's agents
(same instructions), served over the SAME a2a-sdk 0.3.26 stack, chained agent->agent the SAME way,
on the SAME local ollama llama3.2:3b, same host/lo0, driven with A's OWN prompts. Controlled:
transport, server lib+version, LLM, agent count, host, task domain, role semantics, call topology.
Uncontrolled: ONLY the framework's internal machinery (CrewAI Agent/Task/Crew reasoning loop vs A's
direct llm_generate). Ports 8100-8103 (disjoint from A's 8000-8003 so both can coexist).

Role is a ground-truth LABEL by server port, never a feature.
"""
from __future__ import annotations

import asyncio
import logging
import os
from uuid import uuid4

os.environ.setdefault("CREWAI_TELEMETRY_OPT_OUT", "1")
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "1")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

logger = logging.getLogger(__name__)
OLLAMA_MODEL = "ollama/llama3.2:3b"
OLLAMA_BASE = "http://localhost:11434"

# chain order + ports + downstream map (mirrors A's topology_edges chain)
CHAIN = ["orchestrator", "executor", "retriever", "validator"]
ROLE_PORT = {"orchestrator": 8100, "executor": 8101, "retriever": 8102, "validator": 8103}
DOWNSTREAM = {"orchestrator": "executor", "executor": "retriever", "retriever": "validator",
              "validator": None}

# Role specs mirror agents/{orchestrator,executor,retriever,validator}.py instructions verbatim in spirit.
ROLE_SPEC = {
    "orchestrator": dict(
        role="Task Orchestrator",
        goal="Break a task into 2-3 concise sub-tasks for executor/retriever/validator agents.",
        backstory="You decompose work into a numbered plan and delegate.",
        expected="A numbered list of 2-3 concise sub-tasks only."),
    "executor": dict(
        role="Task Executor",
        goal="Carry out the instruction and produce a concrete result.",
        backstory="You are a task executor: thorough but concise.",
        expected="A concrete, concise result for the instruction."),
    "retriever": dict(
        role="Knowledge Retriever",
        goal="Extract 3-5 precise search terms and the key facts they retrieve.",
        backstory="You are a knowledge retriever.",
        expected="3-5 precise search terms plus the key facts."),
    "validator": dict(
        role="Quality Validator",
        goal="Strictly validate the work in a fixed format.",
        backstory="You are a strict quality validator.",
        expected="EXACTLY:\nVERDICT: PASS or FAIL\nSCORE: X/10\nREASON: one sentence (<=20 words)"),
}


class ChainingCrewAiAgent:
    """CrewAI brain for `role`; after its own step it calls the downstream agent over A2A
    (mirroring A's orchestrator->executor->retriever->validator chain)."""

    def __init__(self, role: str) -> None:
        self._role = role
        self.agent_name = f"CrewAI-{role}"
        self._down = DOWNSTREAM[role]
        spec = ROLE_SPEC[role]
        from crewai import Agent, LLM
        self._llm = LLM(model=OLLAMA_MODEL, base_url=OLLAMA_BASE)
        self._agent = Agent(role=spec["role"], goal=spec["goal"], backstory=spec["backstory"],
                            llm=self._llm, verbose=False, allow_delegation=False, max_iter=2)
        self._expected = spec["expected"]

    def _run(self, query: str) -> str:
        from crewai import Task, Crew, Process
        task = Task(description=query, expected_output=self._expected, agent=self._agent)
        crew = Crew(agents=[self._agent], tasks=[task], process=Process.sequential, verbose=False)
        return str(crew.kickoff())

    async def _call_downstream(self, text: str) -> str:
        import httpx
        from a2a.client import A2AClient, A2ACardResolver
        from a2a.types import MessageSendParams, SendStreamingMessageRequest
        port = ROLE_PORT[self._down]
        async with httpx.AsyncClient(timeout=240.0) as hc:
            card = await A2ACardResolver(hc, f"http://localhost:{port}").get_agent_card()
            client = A2AClient(hc, card)
            payload = {"message": {"role": "user", "parts": [{"kind": "text", "text": text}],
                                   "messageId": uuid4().hex, "contextId": uuid4().hex}}
            req = SendStreamingMessageRequest(id=str(uuid4()), params=MessageSendParams(**payload))
            chunks = 0
            async for _ in client.send_message_streaming(req):
                chunks += 1
            return f"[downstream {self._down}: {chunks} chunks]"

    async def stream(self, query: str, context_id: str, task_id: str):
        text = await asyncio.to_thread(self._run, query)
        if self._down is not None:
            try:
                await self._call_downstream(text)
            except Exception as e:  # noqa: BLE001
                logger.warning("%s downstream call failed: %s", self._role, e)
        yield {"is_task_complete": True, "require_user_input": False,
               "response_type": "text", "content": text}


def build_agent_card(role: str, host: str, port: int):
    from a2a.types import AgentCapabilities, AgentCard, AgentSkill
    spec = ROLE_SPEC[role]
    skill = AgentSkill(id=f"{role}_skill", name=spec["role"], description=spec["goal"],
                       tags=[role], examples=[f"{role} step of a chained task."])
    return AgentCard(name=f"CrewAI {spec['role']}", description=spec["goal"],
                     url=f"http://{host}:{port}/", version="1.0.0",
                     capabilities=AgentCapabilities(streaming=True, pushNotifications=False,
                                                    stateTransitionHistory=False),
                     defaultInputModes=["text", "text/plain"],
                     defaultOutputModes=["text", "text/plain"], skills=[skill])


def _make_executor():
    from a2a.server.agent_execution import AgentExecutor, RequestContext
    from a2a.server.events import EventQueue
    from a2a.server.tasks import TaskUpdater
    from a2a.types import DataPart, TaskState, TextPart, UnsupportedOperationError
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
                if item["is_task_complete"]:
                    part = (DataPart(data=item["content"]) if item["response_type"] == "data"
                            else TextPart(text=item["content"]))
                    await updater.add_artifact([part], name=f"{self.agent.agent_name}-result")
                    await updater.complete()
                    break
                await updater.update_status(TaskState.working,
                    new_agent_text_message(item["content"], task.context_id, task.id))

        async def cancel(self, request: RequestContext, event_queue: EventQueue):
            raise ServerError(error=UnsupportedOperationError())
    return GenericAgentExecutor


def serve(role: str, host: str = "localhost") -> None:
    import httpx
    import uvicorn
    from a2a.server.apps import A2AStarletteApplication
    from a2a.server.request_handlers import DefaultRequestHandler
    from a2a.server.tasks import (BasePushNotificationSender, InMemoryPushNotificationConfigStore,
                                  InMemoryTaskStore)
    GenericAgentExecutor = _make_executor()
    port = ROLE_PORT[role]
    card = build_agent_card(role, host, port)
    client = httpx.AsyncClient()
    cfg = InMemoryPushNotificationConfigStore()
    handler = DefaultRequestHandler(
        agent_executor=GenericAgentExecutor(ChainingCrewAiAgent(role)),
        task_store=InMemoryTaskStore(), push_config_store=cfg,
        push_sender=BasePushNotificationSender(client, config_store=cfg))
    app = A2AStarletteApplication(agent_card=card, http_handler=handler)
    logging.basicConfig(level=logging.INFO)
    logger.info("CrewAI-matched %s server on %s:%d", role, host, port)
    uvicorn.run(app.build(), host=host, port=port, log_level="warning")
