"""
Optional TLS for the A2A testbed (the TLS control experiment).

Off by default: the main experiments run over cleartext HTTP. Setting
A2A_TLS_CERT, A2A_TLS_KEY and A2A_TLS_CA (or passing --tls-dir to
scripts/run_pilot.py) makes every agent serve HTTPS and every client verify
against the local CA. Certificates come from scripts/make_tls_certs.sh.
"""

from __future__ import annotations

import os
import ssl

_CERT, _KEY, _CA = "A2A_TLS_CERT", "A2A_TLS_KEY", "A2A_TLS_CA"


def enabled() -> bool:
    return bool(os.environ.get(_CERT))


def scheme() -> str:
    return "https" if enabled() else "http"


def server_kwargs() -> dict:
    """Extra uvicorn.Config arguments (empty when TLS is off)."""
    if not enabled():
        return {}
    return {"ssl_certfile": os.environ[_CERT], "ssl_keyfile": os.environ[_KEY]}


def client_verify() -> ssl.SSLContext | bool:
    """httpx `verify=` value: a context trusting the local CA when TLS is on."""
    if not enabled():
        return True
    return ssl.create_default_context(cafile=os.environ[_CA])


def configure(tls_dir: str) -> None:
    """Enable TLS for this process from a directory made by scripts/make_tls_certs.sh."""
    os.environ[_CERT] = os.path.join(tls_dir, "agent.pem")
    os.environ[_KEY] = os.path.join(tls_dir, "agent-key.pem")
    os.environ[_CA] = os.path.join(tls_dir, "ca.pem")
