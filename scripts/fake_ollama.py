#!/usr/bin/env python3
"""
A stand-in for Ollama's /api/generate in dry runs and tests (no model, almost no CPU): it answers
with num_predict tokens (default 64, at most --max-tokens), one every --token-ms, streamed as NDJSON
or in one reply, and serves requests concurrently (as OLLAMA_NUM_PARALLEL > 1 does; --serial queues
them, as a single-slot Ollama would). /api/ps lists the model with the share of it in GPU memory
(--gpu-share, default 1.0; below 1 as when Ollama's cache does not fit). The tokens include quotes,
newlines and non-ASCII characters, so replies exercise the JSON escapes; their number varies with
the prompt (seeded by it).

    venv/bin/python scripts/fake_ollama.py --port 11555
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random

WORDS = ("the", "chiller", "pressure", "°C", "valve", "\"setpoint\"", "check", "–", "compressor", "→", "sensor", "\n- ",
         "alarm", "flow", "is", "within", "range", "fault", "ticket", "étage")


def tokens(prompt: str, n: int) -> list[str]:
    rng = random.Random(hashlib.sha256(prompt.encode()).hexdigest())
    n = max(1, n - rng.randrange(0, max(1, n // 3)))
    return [rng.choice(WORDS) + " " for _ in range(n)]


def app(token_ms: float, max_tokens: int, serial: bool, gpu_share: float = 1.0):
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse, StreamingResponse
    from starlette.routing import Route
    lock = asyncio.Lock()

    async def generate(request: Request):
        body = await request.json()
        n = min(int((body.get("options") or {}).get("num_predict") or 64), max_tokens)
        toks = tokens(body.get("prompt", ""), n)

        async def stream():
            async with (lock if serial else _null()):
                for t in toks:
                    await asyncio.sleep(token_ms / 1000)
                    yield json.dumps({"model": body.get("model"), "response": t, "done": False}) + "\n"
                yield json.dumps({"model": body.get("model"), "response": "", "done": True, "eval_count": len(toks)}) + "\n"
        if body.get("stream", True):
            return StreamingResponse(stream(), media_type="application/x-ndjson")
        async with (lock if serial else _null()):
            await asyncio.sleep(token_ms * len(toks) / 1000)
        return JSONResponse({"model": body.get("model"), "response": "".join(toks), "done": True, "eval_count": len(toks)})

    async def tags(_: Request):
        return JSONResponse({"models": [{"name": "fake"}]})

    async def ps(_: Request):
        size = 4 * 2**30
        return JSONResponse({"models": [{"name": "fake", "model": "fake", "size": size, "size_vram": int(size * gpu_share),
                                         "context_length": 4096}]})

    return Starlette(routes=[Route("/api/generate", generate, methods=["POST"]), Route("/api/tags", tags), Route("/api/ps", ps)])


class _null:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


if __name__ == "__main__":
    import uvicorn
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--port", type=int, default=11555)
    p.add_argument("--token-ms", type=float, default=20.0, dest="token_ms")
    p.add_argument("--max-tokens", type=int, default=256, dest="max_tokens")
    p.add_argument("--serial", action="store_true")
    p.add_argument("--gpu-share", type=float, default=1.0, dest="gpu_share")
    a = p.parse_args()
    uvicorn.run(app(a.token_ms, a.max_tokens, a.serial, a.gpu_share), host="127.0.0.1", port=a.port, log_level="warning")
