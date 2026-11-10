#!/usr/bin/env python3
"""
Cloud side of C2's edge-cloud placement (docs/LAN_SETUP.md), on the Mac: for every arm base B,
the cloud agents diagnostics (B+1) and knowledge (B+2) on the cloud address, and the ticket
service (B+5) on the building server's address. All over TLS (one certificate valid for both
addresses: bash scripts/make_tls_certs.sh data/tls_lan 192.168.2.2 192.168.2.100 192.168.2.1).
The agents use Ollama on this machine (localhost), so their model calls never cross the link.
Runs until Ctrl-C.

Usage (Mac):
    venv/bin/python scripts/serve_cloud.py --bases 8100,8200,8300 --tls-dir data/tls_lan \\
        --cloud-host 192.168.2.100 --ticket-host 192.168.2.1
    # loopback smoke test: every address 127.0.0.1
    venv/bin/python scripts/serve_cloud.py --bases 8100 --tls-dir data/tls --cloud-host 127.0.0.1 --ticket-host 127.0.0.1
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
from agents.edge import CLOUD_PORTS, TICKET_PORT  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def serve_ticket(host: str, port: int) -> None:
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(ticket_app(), host=host, port=port, log_level="warning",
                                           **tls.server_kwargs(True)))
    logger.info("ticket service on https://%s:%d", host, port)
    await server.serve()


async def main(a: argparse.Namespace) -> None:
    tls.configure(a.tls_dir, default_on=True)
    runs = []
    for base in (int(b) for b in a.bases.split(",")):
        for role, off in CLOUD_PORTS.items():
            agent = CLOUD_AGENTS[role](AgentConfig(
                role=AgentRole(role), host=a.cloud_host, port=base + off, ollama_base_url=a.ollama_url,
                ollama_model=a.model, ollama_num_predict=a.num_predict or None, tls=True))
            runs.append(agent.run())
        runs.append(serve_ticket(a.ticket_host, base + TICKET_PORT))
    await asyncio.gather(*runs)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--bases", default="8100,8200,8300", help="arm port bases, comma-separated")
    p.add_argument("--cloud-host", default="192.168.2.100", dest="cloud_host")
    p.add_argument("--ticket-host", default="192.168.2.1", dest="ticket_host")
    p.add_argument("--tls-dir", required=True, dest="tls_dir")
    p.add_argument("--ollama-url", default="http://127.0.0.1:11434", dest="ollama_url")
    p.add_argument("--model", default="llama3.2:3b")
    p.add_argument("--num-predict", type=int, default=256, dest="num_predict")
    try:
        asyncio.run(main(p.parse_args()))
    except KeyboardInterrupt:
        pass
