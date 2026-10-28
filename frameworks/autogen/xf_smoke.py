"""SMOKE TEST — does networked inter-agent traffic actually flow (with ollama)?

Starts the gRPC host, one specialist worker runtime, and an orchestrator runtime; the
orchestrator sends a SubTask to the specialist over the host and awaits the Result. Two
runtimes ⇒ two real gRPC channels to the host ⇒ real TCP flows on lo0. Prints whether the
LLM answered. Run under tcpdump (see xf_smoke.sh) to confirm on-wire packets.
"""
import asyncio

from autogen_core import AgentId, try_get_known_serializers_for_type
from autogen_ext.runtimes.grpc import GrpcWorkerAgentRuntime, GrpcWorkerAgentRuntimeHost

from xf_common import SpecialistAgent, SubTask, Result

HOST = "localhost:50051"


def register_msgs(rt) -> None:
    """Both request (SubTask) and reply (Result) types must be serializable on EVERY
    runtime that sends or returns them — agent registration only covers handled inputs."""
    for t in (SubTask, Result):
        for s in try_get_known_serializers_for_type(t):
            rt.add_message_serializer(s)


async def main() -> None:
    host = GrpcWorkerAgentRuntimeHost(address=HOST)
    host.start()
    print("host started on", HOST)

    worker = GrpcWorkerAgentRuntime(host_address=HOST)
    register_msgs(worker)
    await worker.start()
    await SpecialistAgent.register(worker, "researcher", lambda: SpecialistAgent("researcher"))
    print("specialist worker up (researcher)")

    orch = GrpcWorkerAgentRuntime(host_address=HOST)
    register_msgs(orch)
    await orch.start()
    print("orchestrator runtime up; sending SubTask...")

    resp = await orch.send_message(SubTask(topic="undersea cables", role="researcher"),
                                   recipient=AgentId("researcher", "default"))
    assert isinstance(resp, Result), f"unexpected response type: {type(resp)}"
    print("GOT RESULT from", resp.role, "| chars:", len(resp.text))
    print("  preview:", resp.text[:120].replace("\n", " "))

    await orch.stop()
    await worker.stop()
    await host.stop()
    print("SMOKE OK — networked round-trip through gRPC host succeeded")


if __name__ == "__main__":
    asyncio.run(main())
