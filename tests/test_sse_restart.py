"""An agent set started after another one shut down still streams its whole SSE response."""

import asyncio
import socket

from agents.base import AgentConfig, AgentRole, BaseA2AAgent


class _Streamer(BaseA2AAgent):
    async def handle_task(self, task_id, content, emit=None):
        for i in range(5):
            await asyncio.sleep(0.6)          # longer than sse-starlette's 0.5 s exit poll
            if emit is not None:
                await emit(f"chunk{i} ")
        return "done"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _serve_and_call() -> tuple[int, str]:
    agent = _Streamer(AgentConfig(role=AgentRole.EXECUTOR, host="127.0.0.1", port=_free_port()))
    task = asyncio.create_task(agent.run())
    await asyncio.sleep(1.0)
    chunks = []

    async def emit(c):
        chunks.append(c)

    async with _Streamer(AgentConfig(role=AgentRole.ORCHESTRATOR, port=1)) as caller:
        result = await caller.send_task(agent.config.base_url(), "t", "go", emit=emit)
    await agent.shutdown()
    await asyncio.wait([task], timeout=4)
    return len(chunks), result.output


def test_second_agent_set_streams_after_first_shut_down():
    async def main():
        return [await _serve_and_call() for _ in range(2)]

    for n_chunks, output in asyncio.run(main()):
        assert n_chunks == 5
        assert output == "done"
