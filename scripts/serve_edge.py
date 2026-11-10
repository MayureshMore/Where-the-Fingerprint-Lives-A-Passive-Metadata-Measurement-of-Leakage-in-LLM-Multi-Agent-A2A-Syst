#!/usr/bin/env python3
"""
Edge side of C2's edge-cloud placement (docs/LAN_SETUP.md), on the Raspberry Pi (the building's
IoT gateway): one edge agent per arm base B, each with its trigger endpoint on B+9 (plain HTTP;
captures leave it out). The edge agents call the cloud agents and the ticket service over TLS,
verifying them against the CA in --tls-dir (only ca.pem is needed there), and answer
alert_triage with the Pi's own Ollama. Input padding comes with each task from the collector's
--arm pad=, so every instance is the same apart from its ports. Runs until Ctrl-C.

Usage (Pi):
    venv/bin/python scripts/serve_edge.py --bases 8100,8200,8300 --tls-dir data/tls_lan \\
        --cloud-host 192.168.2.100 --ticket-host 192.168.2.1 --model llama3.2:1b --num-predict 128
    # loopback smoke test on the Mac
    venv/bin/python scripts/serve_edge.py --bases 8100 --tls-dir data/tls --cloud-host 127.0.0.1 \\
        --ticket-host 127.0.0.1 --bind 127.0.0.1 --model llama3.2:3b
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.edge import TRIGGER_PORT, EdgeAgent, trigger_app  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main(a: argparse.Namespace) -> None:
    import uvicorn
    os.environ["A2A_TLS_CA"] = str(Path(a.tls_dir) / "ca.pem")        # the edge is a TLS client only
    servers = []
    for base in (int(b) for b in a.bases.split(",")):
        edge = EdgeAgent(base, a.cloud_host, a.ticket_host, ollama_url=a.ollama_url, model=a.model,
                         num_predict=a.num_predict or None, tls_on=True)
        servers.append(uvicorn.Server(uvicorn.Config(trigger_app(edge), host=a.bind, port=base + TRIGGER_PORT,
                                                     log_level="warning")))
        logger.info("edge agent %d: trigger http://%s:%d, cloud %s, tickets %s, local model %s",
                    base, a.bind, base + TRIGGER_PORT, edge.cloud, edge.ticket_url, a.model)
    await asyncio.gather(*(s.serve() for s in servers))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--bases", default="8100,8200,8300", help="arm port bases, comma-separated")
    p.add_argument("--cloud-host", default="192.168.2.100", dest="cloud_host")
    p.add_argument("--ticket-host", default="192.168.2.1", dest="ticket_host")
    p.add_argument("--tls-dir", required=True, dest="tls_dir", help="folder with ca.pem")
    p.add_argument("--bind", default="0.0.0.0", help="address of the trigger endpoints")
    p.add_argument("--ollama-url", default="http://127.0.0.1:11434", dest="ollama_url")
    p.add_argument("--model", default="llama3.2:1b")
    p.add_argument("--num-predict", type=int, default=128, dest="num_predict")
    try:
        asyncio.run(main(p.parse_args()))
    except KeyboardInterrupt:
        pass
