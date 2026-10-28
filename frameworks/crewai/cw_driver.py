"""Coordinator/driver for ONE trip: an a2a-sdk streaming client (identical to a2a_mcp's
drive_orch.py client path) that fans a trip request out to the CrewAI planner (:10201) and the
three CrewAI specialists (:10203 air, :10204 hotel, :10205 car) over A2A JSON-RPC + SSE.

One trip => one pcap capturing lo0 ports 10201-10205. Server (dest) port is the ground-truth
role LABEL; the sidecar written by collect_trips.sh maps port->role for extract_role_samples."""
import argparse
import asyncio
from uuid import uuid4

import httpx
from a2a.client import A2AClient, A2ACardResolver
from a2a.types import MessageSendParams, SendStreamingMessageRequest

from cw_common import ROLE_PORT


async def call_agent(hc: httpx.AsyncClient, port: int, text: str) -> tuple[int, int]:
    """Send one streaming message to the A2A agent on `port`; return (chunks, chars)."""
    base = f"http://localhost:{port}"
    card = await A2ACardResolver(hc, base).get_agent_card()
    client = A2AClient(hc, card)
    payload = {"message": {"role": "user", "parts": [{"kind": "text", "text": text}],
                           "messageId": uuid4().hex, "contextId": uuid4().hex}}
    req = SendStreamingMessageRequest(id=str(uuid4()), params=MessageSendParams(**payload))
    chunks, chars = 0, 0
    async for chunk in client.send_message_streaming(req):
        chunks += 1
        res = getattr(chunk.root, "result", chunk.root)
        st = getattr(res, "status", None)
        msg = getattr(st, "message", None) if st is not None else None
        if msg is not None:
            for p in msg.parts:
                r = getattr(p, "root", p)
                chars += len(getattr(r, "text", "") or "")
    return chunks, chars


async def drive(origin: str, dest: str, d1: str, d2: str) -> None:
    subq = {
        "planner": f"Plan a complete trip from {origin} to {dest}, depart {d1}, return {d2}, "
                   f"2 adults, economy. Cover flights, a 5-night hotel and a rental car.",
        "air_ticketing": f"Recommend round-trip flights from {origin} to {dest}, depart {d1}, "
                         f"return {d2}, 2 adults, economy class.",
        "hotel": f"Recommend a reputable 4-star hotel in {dest} for 5 nights from {d1}.",
        "car_rental": f"Recommend a mid-size rental car in {dest} from {d1} to {d2}.",
    }
    async with httpx.AsyncClient(timeout=240.0) as hc:
        for role in ("planner", "air_ticketing", "hotel", "car_rental"):
            port, _ = ROLE_PORT[role]
            try:
                ch, cc = await call_agent(hc, port, subq[role])
                print(f"  {role:14s} :{port} -> {ch} chunks, {cc} chars", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"  {role:14s} :{port} STREAM ERROR {type(e).__name__}: {str(e)[:140]}", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--origin", required=True)
    ap.add_argument("--dest", required=True)
    ap.add_argument("--d1", default="2026-05-04")
    ap.add_argument("--d2", default="2026-05-13")
    a = ap.parse_args()
    asyncio.run(drive(a.origin, a.dest, a.d1, a.d2))
