"""
Optional TLS for the A2A testbed (the TLS control experiment).

Off by default: the main experiments run over cleartext HTTP. Setting
A2A_TLS_CERT, A2A_TLS_KEY and A2A_TLS_CA (or passing --tls-dir to
scripts/collect_deployment.py) makes every agent serve HTTPS and every client verify
against the local CA. Certificates come from scripts/make_tls_certs.sh.

TLS can also be chosen per agent (AgentConfig.tls), which is how
scripts/collect_tls_session.py runs a cleartext and a TLS agent set side by side
in one session: configure(tls_dir, default_on=False) loads the certificates
without turning TLS on for agents that do not ask for it.
"""

from __future__ import annotations

import os
import ssl

_CERT, _KEY, _CA = "A2A_TLS_CERT", "A2A_TLS_KEY", "A2A_TLS_CA"
_DEFAULT = "A2A_TLS_DEFAULT"   # "0" → certificates loaded, TLS off unless asked for


def enabled(on: bool | None = None) -> bool:
    """TLS for one agent/URL: `on` if given, else the process-wide default."""
    if on is not None:
        return on
    return bool(os.environ.get(_CERT)) and os.environ.get(_DEFAULT, "1") != "0"


def scheme(on: bool | None = None) -> str:
    return "https" if enabled(on) else "http"


def server_kwargs(on: bool | None = None) -> dict:
    """Extra uvicorn.Config arguments (empty when TLS is off)."""
    if not enabled(on):
        return {}
    if not os.environ.get(_CERT):
        raise RuntimeError("TLS requested but no certificate configured (tls.configure / A2A_TLS_CERT)")
    return {"ssl_certfile": os.environ[_CERT], "ssl_keyfile": os.environ[_KEY]}


def client_verify() -> ssl.SSLContext | bool:
    """httpx `verify=` value: a context trusting the local CA whenever one is configured.

    httpx ignores it for http:// URLs, so one client serves both agent sets."""
    if not os.environ.get(_CA):
        return True
    return ssl.create_default_context(cafile=os.environ[_CA])


def configure(tls_dir: str, default_on: bool = True) -> None:
    """Load the certificates made by scripts/make_tls_certs.sh into this process."""
    os.environ[_CERT] = os.path.join(tls_dir, "agent.pem")
    os.environ[_KEY] = os.path.join(tls_dir, "agent-key.pem")
    os.environ[_CA] = os.path.join(tls_dir, "ca.pem")
    os.environ[_DEFAULT] = "1" if default_on else "0"
