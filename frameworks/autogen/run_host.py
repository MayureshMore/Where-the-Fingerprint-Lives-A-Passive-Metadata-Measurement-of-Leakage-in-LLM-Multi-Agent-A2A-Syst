"""The gRPC message-routing host. Long-lived; every worker/orchestrator connects to it."""
import asyncio

from autogen_ext.runtimes.grpc import GrpcWorkerAgentRuntimeHost
from common import HOST_ADDR


async def main() -> None:
    host = GrpcWorkerAgentRuntimeHost(address=HOST_ADDR)
    host.start()
    print(f"[host] up on {HOST_ADDR}", flush=True)
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
