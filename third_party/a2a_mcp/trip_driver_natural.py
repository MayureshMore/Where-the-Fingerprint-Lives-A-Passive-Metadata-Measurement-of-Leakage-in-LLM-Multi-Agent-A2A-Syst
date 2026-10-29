"""Drive the a2a_mcp orchestrator (:10101) over A2A, MULTI-TURN — the BUG-FIXED-BUT-NOT-FORCED
natural driver for the clean cross-instance de-confound (Task 2).

Identical to trip_driver.py EXCEPT the canned multi-turn ANSWER is DESTINATION-AGNOSTIC (so it
does not sabotage fan-out on non-Tokyo destinations — the original hardcodes "Narita (NRT) …
Shinjuku", giving ~6% fan-out) YET NOT completion-forcing (unlike trip_driver_boosted.py, which
commands "complete ALL THREE now … do not ask any further questions", shifting the specialist
feature distributions — the very confound Task 2 exists to remove).

The answer just supplies sensible destination-agnostic defaults a cooperative user would give
and lets the planner proceed on its own — so fan-out happens naturally, at its natural rate,
with natural specialist traffic. Paired with instance-2's OWN reworded natural query (NOT the
boost's forced full-service prompt and NOT instance-1's prompt) this keeps instance-2 internally
consistent; the specialist_distribution_check then honestly measures whether natural collection
removed the driver confound.
"""
import asyncio
import sys
from uuid import uuid4

import httpx
from a2a.client import A2AClient, A2ACardResolver
from a2a.types import MessageSendParams, SendStreamingMessageRequest

ORCH = "http://localhost:10101"

# Destination-agnostic (bug-fixed) and NON-forcing: gives the planner the defaults it needs to
# proceed, phrased as a cooperative reply — no "ALL THREE now", no "do not ask further questions".
ANSWER = (
    "Use the nearest major international airport for the destination I gave. Economy class is "
    "fine. A reputable 4-star hotel near the city centre is fine. A standard mid-size rental car "
    "is fine. Please go ahead with your recommended options."
)


def status_of(res):
    st = getattr(res, "status", None)
    if st is None:
        return None, None
    txt = ""
    msg = getattr(st, "message", None)
    if msg is not None:
        for p in msg.parts:
            r = getattr(p, "root", p)
            txt += getattr(r, "text", "") or ""
    return getattr(st, "state", None), txt


async def drive(query: str) -> None:
    context_id = uuid4().hex
    msg = query
    async with httpx.AsyncClient(timeout=240.0) as hc:
        card = await A2ACardResolver(hc, ORCH).get_agent_card()
        client = A2AClient(hc, card)
        for turn in range(1, 7):
            payload = {"message": {"role": "user", "parts": [{"kind": "text", "text": msg}],
                                   "messageId": uuid4().hex, "contextId": context_id}}
            req = SendStreamingMessageRequest(id=str(uuid4()), params=MessageSendParams(**payload))
            final_state, question, chunks = None, None, 0
            try:
                async for chunk in client.send_message_streaming(req):
                    chunks += 1
                    res = getattr(chunk.root, "result", chunk.root)
                    state, txt = status_of(res)
                    if state is not None:
                        s = str(state)
                        if "input_required" in s:
                            final_state, question = "input_required", txt
                        elif "completed" in s:
                            final_state = "completed"
                        elif "working" in s and final_state is None:
                            final_state = "working"
            except Exception as e:  # noqa: BLE001
                print(f"  turn {turn}: STREAM ERROR {type(e).__name__}: {str(e)[:160]}")
                return
            print(f"  turn {turn}: {chunks} chunks, final={final_state}"
                  + (f", Q={question[:80]!r}" if question else ""))
            if final_state == "input_required":
                msg = ANSWER
                continue
            break
        print("DONE")


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "Plan a trip."
    asyncio.run(drive(q))
