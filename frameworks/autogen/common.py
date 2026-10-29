"""Shared message types + agents for the AutoGen cross-framework traffic experiment.

Mirrors the a2a_mcp taxonomy: an ORCHESTRATOR (coordinator) that routes sub-tasks to
three SPECIALIST worker agents (researcher / writer / reviewer), each of which calls a
LOCAL ollama LLM (no API spend) and returns a result. Runs on AutoGen's *distributed*
gRPC runtime (GrpcWorkerAgentRuntimeHost + GrpcWorkerAgentRuntime) so every agent has a
real TCP channel to the host — genuinely networked, non-A2A, sniffable on lo0.
"""
from __future__ import annotations

from dataclasses import dataclass

from autogen_core import MessageContext, RoutedAgent, message_handler, try_get_known_serializers_for_type
from autogen_ext.models.ollama import OllamaChatCompletionClient
from autogen_core.models import UserMessage

# 127.0.0.1 (not "localhost") forces IPv4 loopback → same 127.0.0.1 flows the a2a pipeline
# already extracts, avoiding the ::1 IPv6 path.
HOST_ADDR = "127.0.0.1:50051"
SPECIALISTS = ("researcher", "writer", "reviewer")
OLLAMA_MODEL = "llama3.2:3b"   # local, no spend; matches deployment A's model

# Distinct per-role prompts → distinct per-agent traffic shapes (the fingerprint).
ROLE_PROMPT = {
    "researcher": "You are a research agent. In 3-4 sentences, list key facts about: {topic}",
    "writer":     "You are a writer. Write a short vivid paragraph (5-6 sentences) about: {topic}",
    "reviewer":   "You are a terse reviewer. In ONE sentence, give a verdict on coverage of: {topic}",
}


@dataclass
class SubTask:
    topic: str
    role: str


@dataclass
class Result:
    role: str
    text: str


def register_msgs(rt) -> None:
    """Both request (SubTask) and reply (Result) types must be serializable on EVERY runtime
    that sends or returns them — agent registration only covers handled inputs."""
    for t in (SubTask, Result):
        for s in try_get_known_serializers_for_type(t):
            rt.add_message_serializer(s)


class SpecialistAgent(RoutedAgent):
    """A leaf worker: receives a SubTask, calls the local LLM, returns a Result."""

    def __init__(self, role: str) -> None:
        super().__init__(f"specialist-{role}")
        self._role = role
        self._client = OllamaChatCompletionClient(model=OLLAMA_MODEL, host="http://localhost:11434")

    @message_handler
    async def handle(self, message: SubTask, ctx: MessageContext) -> Result:
        prompt = ROLE_PROMPT[self._role].format(topic=message.topic)
        res = await self._client.create([UserMessage(content=prompt, source="user")])
        text = res.content if isinstance(res.content, str) else str(res.content)
        return Result(role=self._role, text=text)
