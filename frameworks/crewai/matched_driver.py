"""Drive ONE matched chain trip: call the orchestrator (:8100) with an A prompt; the chain
propagates orchestrator->executor->retriever->validator agent-to-agent over A2A (mirrors A)."""
import argparse, asyncio
from uuid import uuid4
import httpx
from a2a.client import A2AClient, A2ACardResolver
from a2a.types import MessageSendParams, SendStreamingMessageRequest

async def drive(prompt: str) -> None:
    async with httpx.AsyncClient(timeout=300.0) as hc:
        card = await A2ACardResolver(hc, "http://localhost:8100").get_agent_card()
        client = A2AClient(hc, card)
        payload = {"message": {"role": "user", "parts": [{"kind": "text", "text": prompt}],
                               "messageId": uuid4().hex, "contextId": uuid4().hex}}
        req = SendStreamingMessageRequest(id=str(uuid4()), params=MessageSendParams(**payload))
        n = 0
        async for _ in client.send_message_streaming(req):
            n += 1
        print(f"  orchestrator :8100 -> {n} chunks (chain propagated)", flush=True)
    print("DONE", flush=True)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--prompt", required=True)
    asyncio.run(drive(ap.parse_args().prompt))
