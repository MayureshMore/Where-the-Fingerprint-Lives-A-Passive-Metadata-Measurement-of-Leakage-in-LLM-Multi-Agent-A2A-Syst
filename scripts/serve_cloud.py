#!/usr/bin/env python3
"""
Cloud side of C2's edge-cloud placement (docs/LAN_SETUP.md), on the Mac: for every arm base B,
the cloud agents diagnostics (B+1) and knowledge (B+2) on the cloud alias (C2_CLOUD), and the
ticket service (B+5) on the Mac's own address (C2_MAC), both from configs/c2_network.conf unless
given. All over TLS, one certificate valid for both addresses (docs/LAN_SETUP.md, section 5).
The agents use Ollama on this machine (localhost), so their model calls never cross the link.
Runs until Ctrl-C.

Usage (Mac):
    venv/bin/python scripts/serve_cloud.py --bases 8100,8200,8300 --tls-dir data/tls_lan
    # loopback smoke test: every address 127.0.0.1
    venv/bin/python scripts/serve_cloud.py --bases 8100 --tls-dir data/tls --cloud-host 127.0.0.1 --ticket-host 127.0.0.1
    # round 2, B1: the lan_shaped arm's cloud agents shape every reply (defense/shaping.py); one JSON
    # line per reply in data/raw_c2b1_replies/replies_PORT.jsonl (what was cut: expect none)
    venv/bin/python scripts/serve_cloud.py --bases 8300,8400 --shape 8400=2048/14/128/0.05/truncate \
        --reply-log data/raw_c2b1_replies --tls-dir data/tls_lan
    # round 2, B2: the jitter arm's cloud agents delay every SSE event (mean 4 ms, sd 1.8 ms, in order);
    # the rest of its WAN is in data/results/b2_wan_jitter.json (scripts/round2_wan_plan.py)
    venv/bin/python scripts/serve_cloud.py --bases 8100,8500 --jitter 8500=4/1.8/1 \
        --reply-log data/raw_c2b2_replies --tls-dir data/tls_lan
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents import tls  # noqa: E402
from agents.base import AgentConfig, AgentRole  # noqa: E402
from agents.cloud import CLOUD_AGENTS, ticket_app  # noqa: E402
from agents.edge import CLOUD_PORTS, TICKET_PORT, c2_network, require  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def serve_ticket(host: str, port: int) -> None:
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(ticket_app(), host=host, port=port, log_level="warning",
                                           **tls.server_kwargs(True)))
    logger.info("ticket service on https://%s:%d", host, port)
    await server.serve()


def per_base(specs: list[str], flag: str, parse) -> dict[int, str]:
    """BASE=SPEC options → {base: normalized spec}."""
    out = {}
    for spec in specs:
        b, _, x = spec.partition("=")
        try:
            out[int(b)] = parse(x)
        except ValueError as exc:
            raise SystemExit(f"{flag} {spec!r}: {exc}") from exc
    return out


async def main(a: argparse.Namespace) -> None:
    net = c2_network()
    a.cloud_host = require(a.cloud_host or net["C2_CLOUD"], "the cloud alias (C2_CLOUD)")
    a.ticket_host = require(a.ticket_host or net["C2_MAC"], "the Mac's address (C2_MAC)")
    tls.configure(a.tls_dir, default_on=True)
    runs = []
    from defense.shaping import JitterConfig, ShapeConfig
    shapes = per_base(a.shape, "--shape", lambda x: ShapeConfig.parse(x).spec())
    jitters = per_base(a.jitter, "--jitter", lambda x: JitterConfig.parse(x).spec())
    bases = [int(b) for b in a.bases.split(",")]
    if missing := (set(shapes) | set(jitters)) - set(bases):
        raise SystemExit(f"--shape or --jitter for bases not served: {sorted(missing)}")
    if (shapes or jitters) and not a.reply_log:
        raise SystemExit("--shape and --jitter need --reply-log DIR (one JSON line per reply: what was cut, the delays)")
    if a.reply_log:
        Path(a.reply_log).mkdir(parents=True, exist_ok=True)
    for base in bases:
        for role, off in CLOUD_PORTS.items():
            port = base + off
            logged = base in shapes or base in jitters
            agent = CLOUD_AGENTS[role](AgentConfig(
                role=AgentRole(role), host=a.cloud_host, port=port, ollama_base_url=a.ollama_url,
                ollama_model=a.model, ollama_num_predict=a.num_predict or None, tls=True, shape=shapes.get(base, ""),
                jitter=jitters.get(base, ""), reply_log=str(Path(a.reply_log) / f"replies_{port}.jsonl") if logged else ""))
            if base in shapes:
                logger.info("%s on %d shapes its replies: %s", role, port, shapes[base])
            if base in jitters:
                logger.info("%s on %d delays every SSE event: %s (mean ms/sd ms/seed)", role, port, jitters[base])
            runs.append(agent.run())
        runs.append(serve_ticket(a.ticket_host, base + TICKET_PORT))
    await asyncio.gather(*runs)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--bases", default="8100,8200,8300", help="arm port bases, comma-separated")
    p.add_argument("--cloud-host", default=None, dest="cloud_host", help="default: C2_CLOUD")
    p.add_argument("--ticket-host", default=None, dest="ticket_host", help="default: C2_MAC")
    p.add_argument("--tls-dir", required=True, dest="tls_dir")
    p.add_argument("--ollama-url", default="http://127.0.0.1:11434", dest="ollama_url")
    p.add_argument("--model", default="llama3.2:3b")
    p.add_argument("--num-predict", type=int, default=256, dest="num_predict")
    p.add_argument("--shape", action="append", default=[], metavar="BASE=SPEC",
                   help="reply shaping for one arm base: REPLY_BYTES/DEADLINE_S[/CHUNK_BYTES[/INTERVAL_S[/OVERRUN]]]")
    p.add_argument("--jitter", action="append", default=[], metavar="BASE=SPEC",
                   help="reply jitter for one arm base: MEAN_MS/SD_MS[/SEED], every SSE event delayed, in order")
    p.add_argument("--reply-log", default="", dest="reply_log", metavar="DIR",
                   help="with --shape or --jitter: DIR/replies_PORT.jsonl, one JSON line per reply")
    try:
        asyncio.run(main(p.parse_args()))
    except KeyboardInterrupt:
        pass
