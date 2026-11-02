"""Input padding: every request body an agent sends is padded to a fixed size bucket."""

import asyncio
import json

import httpx
import pytest

from agents.base import AgentConfig, AgentRole, pad_bucket
from agents.executor import ExecutorAgent

BUCKETS = [1024, 2048, 4096]
URL = "http://10.0.0.2:8101"


def test_pad_bucket():
    assert pad_bucket(10, BUCKETS) == 1024
    assert pad_bucket(1024, BUCKETS) == 1024
    assert pad_bucket(1025, BUCKETS) == 2048
    assert pad_bucket(4097, BUCKETS) == 8192       # past the largest: multiples of it
    assert pad_bucket(9000, BUCKETS) == 12288


def _sent_body(content: str, buckets: list[int]) -> bytes:
    """Run send_task against a mock transport and return the request body httpx sent."""
    bodies: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        return httpx.Response(500)

    agent = ExecutorAgent(AgentConfig(role=AgentRole.EXECUTOR, port=8101, pad_buckets=buckets))
    agent._card_cache[URL] = agent.agent_card()
    agent._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(Exception):
        asyncio.run(agent.send_task(URL, "t1", content))
    assert len(bodies) == 1
    return bodies[0]


@pytest.mark.parametrize("n", [5, 300, 600])
def test_request_body_is_padded_to_a_bucket_and_text_is_unchanged(n):
    text = "q" * n
    body = _sent_body(text, BUCKETS)
    assert len(body) == 1024
    msg = json.loads(body)["params"]["message"]
    assert msg["parts"][0]["text"] == text
    assert set(msg["metadata"]["pad"]) <= {"x"}


def test_different_inputs_in_one_bucket_are_the_same_size_and_larger_ones_move_up():
    assert len(_sent_body("a" * 10, BUCKETS)) == len(_sent_body("b" * 600, BUCKETS)) == 1024
    assert len(_sent_body("c" * 1500, BUCKETS)) == 2048
    assert len(_sent_body("d" * 5000, BUCKETS)) == 8192


def test_no_padding_by_default():
    body = _sent_body("a" * 10, [])
    assert len(body) < 1024 and "metadata" not in json.loads(body)["params"]["message"]
