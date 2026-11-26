#!/usr/bin/env python3
"""
Server load for paper 2 round 2, B2: concurrent generations on the Mac's Ollama (localhost; never on
the observed path), so that the cloud agents answer while other requests share the model, as a busy
cloud would. The collector (scripts/collect_session.py, arm option load=N) starts the load before each
task of the loaded arm and stops it after, so the interleaved control arm never runs under it.

    OllamaLoad  N workers, each streaming one generation after another (prompts drawn from a fixed
                pool, num_predict drawn from a range; seeded) until stop(); start() returns once every
                worker is generating (its first token arrived) or after warmup_s; stop() closes the
                streams (Ollama stops a generation whose client went away) and waits cooldown_s.
                Each start/stop window reports requests started and finished, tokens received and
                tokens per second.
    check_parallel  Ollama serves requests concurrently only with OLLAMA_NUM_PARALLEL > 1 (or its
                automatic choice): two generations started together must overlap (the second's first
                token before the first one's end). Without that the load would only queue the
                agents' requests. The model must also sit wholly in GPU memory (/api/ps): Ollama keeps
                a cache of context length x parallel slots, and with the app's 131072 and 4 slots
                (56 GB of cache for llama3.2:3b) 17 of its 29 layers ran on the CPU of the 36 GB Mac;
                at 32768 and 4 slots it holds 16.7 GB, all of it on the GPU, as C2's 131072 x 1 did.

Ollama on the Mac must run with parallel requests on and a context that fits 4 slots, for example
(the app: Settings, Context length 32k; then quit it and reopen it):
    launchctl setenv OLLAMA_NUM_PARALLEL 4
Check, then a one-minute trial:
    venv/bin/python scripts/ollama_load.py --check
    venv/bin/python scripts/ollama_load.py --concurrency 2 --seconds 60
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time

import httpx

TOPICS = ("how a heat pump moves heat", "how TCP congestion control reacts to loss", "the history of the printing press",
          "how vaccines train the immune system", "how a compiler optimizes loops", "the water cycle",
          "how photosynthesis stores energy", "how elevators balance their load", "the causes of ocean tides",
          "how a bicycle stays upright", "how batteries age", "how bridges carry load")
STYLES = ("Explain in detail", "Write a long technical overview of", "Write a step-by-step tutorial on",
          "Describe for a new engineer")


class OllamaLoad:
    def __init__(self, url: str = "http://127.0.0.1:11434", model: str = "llama3.2:3b", concurrency: int = 2,
                 num_predict: tuple[int, int] = (128, 384), seed: int = 0, warmup_s: float = 3.0,
                 cooldown_s: float = 1.0):
        if concurrency < 1:
            raise ValueError("concurrency must be >= 1")
        self.url, self.model, self.n = url.rstrip("/"), model, concurrency
        self.num_predict, self.warmup_s, self.cooldown_s = num_predict, warmup_s, cooldown_s
        self.rng = random.Random(seed)
        self.workers: list[asyncio.Task] = []
        self.generating: list[asyncio.Event] = []
        self.client: httpx.AsyncClient | None = None
        self.window: dict = {}

    def _request(self) -> dict:
        prompt = f"{self.rng.choice(STYLES)} {self.rng.choice(TOPICS)}."
        return {"model": self.model, "prompt": prompt, "stream": True,
                "options": {"num_predict": self.rng.randint(*self.num_predict), "seed": self.rng.randrange(1 << 30)}}

    async def _worker(self, k: int) -> None:
        while True:
            body = self._request()
            self.window["started"] += 1
            async with self.client.stream("POST", f"{self.url}/api/generate", json=body) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    msg = json.loads(line)
                    if msg.get("response"):
                        self.window["tokens"] += 1
                        self.generating[k].set()
                    if msg.get("done"):
                        self.window["finished"] += 1
                        break

    async def start(self) -> dict:
        if self.workers:
            raise RuntimeError("load already running")
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(600, connect=10))
        self.window = {"concurrency": self.n, "model": self.model, "started": 0, "finished": 0, "tokens": 0,
                       "t_start": time.time()}
        self.generating = [asyncio.Event() for _ in range(self.n)]
        self.workers = [asyncio.create_task(self._worker(k)) for k in range(self.n)]
        t = time.monotonic()
        while (time.monotonic() - t < self.warmup_s and not all(e.is_set() for e in self.generating)
               and not any(w.done() for w in self.workers)):
            await asyncio.sleep(0.02)
        self.window["warm_s"] = time.monotonic() - t
        self.window["generating_at_start"] = sum(e.is_set() for e in self.generating)
        failed = [w for w in self.workers if w.done() and w.exception()]
        if failed:
            await self.stop()
            raise RuntimeError(f"load generator failed: {failed[0].exception()!r}")
        return dict(self.window)

    async def stop(self) -> dict:
        for w in self.workers:
            w.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers = []
        if self.client is not None:
            await self.client.aclose()
            self.client = None
        self.window["t_stop"] = time.time()
        span = self.window["t_stop"] - self.window["t_start"]
        self.window["tokens_per_s"] = self.window["tokens"] / span if span > 0 else None
        await asyncio.sleep(self.cooldown_s)
        return dict(self.window)


async def check_parallel(url: str = "http://127.0.0.1:11434", model: str = "llama3.2:3b", num_predict: int = 64) -> dict:
    """Two generations started together: do they overlap? (first token of the second before the end of the first)"""
    async def one(c: httpx.AsyncClient, t0: float) -> dict:
        first = end = None
        body = {"model": model, "prompt": "Count slowly from one to fifty in words.", "stream": True,
                "options": {"num_predict": num_predict, "seed": 1}}
        async with c.stream("POST", f"{url.rstrip('/')}/api/generate", json=body) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line:
                    continue
                msg = json.loads(line)
                if msg.get("response") and first is None:
                    first = time.monotonic() - t0
                if msg.get("done"):
                    end = time.monotonic() - t0
                    break
        return {"first_token_s": first, "end_s": end}

    async with httpx.AsyncClient(timeout=300) as c:
        await one(c, time.monotonic())                                   # the model loaded, outside the test
        t0 = time.monotonic()
        a, b = await asyncio.gather(one(c, t0), one(c, t0))
    early, late = sorted((a, b), key=lambda x: x["end_s"])
    parallel = late["first_token_s"] is not None and late["first_token_s"] < early["end_s"]
    state = await gpu_state(url, model)
    gpu = state["gpu"]
    fits = state["fits"]
    detail = ("the two generations overlapped" if parallel else
              "the second generation waited for the first: set OLLAMA_NUM_PARALLEL (> 1) and restart Ollama")
    if gpu is None:
        detail += f"; {model} is not in /api/ps, so its memory is unknown"
    elif not fits:
        detail += (f"; only {gpu['vram_gb']} of {gpu['size_gb']} GB of {model} is in GPU memory (context "
                   f"{gpu['context_length']}): lower the context length (the app's Settings) and restart Ollama")
    else:
        detail += f"; {model} wholly in GPU memory ({gpu['size_gb']} GB, context {gpu['context_length']})"
    return {"parallel": parallel, "fits": fits, "ok": parallel and fits, "gpu": gpu, "runs": [a, b], "detail": detail}


async def gpu_state(url: str = "http://127.0.0.1:11434", model: str = "llama3.2:3b") -> dict:
    """The model's place in memory now (/api/ps): size, the part in GPU memory, its share and the context
    length; fits when the share is at least 0.999. gpu is None when the model is not loaded."""
    async with httpx.AsyncClient(timeout=30) as c:
        ps = (await c.get(f"{url.rstrip('/')}/api/ps")).json().get("models", [])
    m = next((x for x in ps if model in (x.get("name"), x.get("model"))), None)
    gpu = None if m is None else {"size_gb": round(m["size"] / 2**30, 2), "vram_gb": round(m.get("size_vram", 0) / 2**30, 2),
                                  "share": round(m.get("size_vram", 0) / m["size"], 4) if m.get("size") else None,
                                  "context_length": m.get("context_length")}
    return {"model": model, "gpu": gpu, "fits": gpu is not None and gpu["share"] is not None and gpu["share"] >= 0.999}


async def _main(a: argparse.Namespace) -> int:
    if a.check:
        r = await check_parallel(a.url, a.model)
        print(json.dumps(r, indent=1))
        return 0 if r["ok"] else 1
    load = OllamaLoad(a.url, a.model, a.concurrency, seed=a.seed)
    print("start:", await load.start())
    await asyncio.sleep(a.seconds)
    print("stop:", await load.stop())
    return 0


if __name__ == "__main__":
    import sys
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--url", default="http://127.0.0.1:11434")
    p.add_argument("--model", default="llama3.2:3b")
    p.add_argument("--concurrency", type=int, default=2)
    p.add_argument("--seconds", type=float, default=60)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--check", action="store_true", help="check that Ollama runs two generations at once")
    sys.exit(asyncio.run(_main(p.parse_args())))
