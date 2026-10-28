"""One SPECIALIST worker in its OWN process (⇒ its own gRPC connection ⇒ one TCP flow to the
host, distinct ephemeral port). Registers the agent, then stays alive serving requests. Its
PID is printed so the collector can map source-port→role via lsof (port is a ground-truth
LABEL only, never a feature)."""
import argparse
import asyncio
import os

from autogen_ext.runtimes.grpc import GrpcWorkerAgentRuntime
from xf_common import HOST_ADDR, SpecialistAgent, register_msgs


async def main(role: str) -> None:
    rt = GrpcWorkerAgentRuntime(host_address=HOST_ADDR)
    register_msgs(rt)
    await rt.start()
    await SpecialistAgent.register(rt, role, lambda: SpecialistAgent(role))
    print(f"[worker:{role}] up pid={os.getpid()}", flush=True)
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await rt.stop()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True)
    asyncio.run(main(ap.parse_args().role))
