"""The ORCHESTRATOR (coordinator) in its OWN process. Sends a SubTask to each specialist in
turn (routing many small request/reply messages ⇒ a distinct coordinator traffic shape),
collects Results, then exits. One trip = one orchestrator run."""
import argparse
import asyncio
import os

from autogen_core import AgentId
from autogen_ext.runtimes.grpc import GrpcWorkerAgentRuntime
from common import HOST_ADDR, SPECIALISTS, SubTask, Result, register_msgs


async def main(topic: str) -> None:
    rt = GrpcWorkerAgentRuntime(host_address=HOST_ADDR)
    register_msgs(rt)
    await rt.start()
    print(f"[orch] up pid={os.getpid()} topic={topic!r}", flush=True)
    for role in SPECIALISTS:
        resp = await rt.send_message(SubTask(topic=topic, role=role),
                                     recipient=AgentId(role, "default"))
        assert isinstance(resp, Result)
        print(f"[orch] {role} -> {len(resp.text)} chars", flush=True)
    await rt.stop()
    print("[orch] done", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", required=True)
    asyncio.run(main(ap.parse_args().topic))
