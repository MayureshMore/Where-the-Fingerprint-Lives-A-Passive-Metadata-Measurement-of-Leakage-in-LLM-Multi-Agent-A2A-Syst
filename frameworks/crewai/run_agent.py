"""One CrewAI-backed A2A specialist server in its OWN process (⇒ its own listen port, distinct
per-role server flows). Role is a ground-truth LABEL by server port, never a feature."""
import argparse

from common import ROLE_PORT, serve

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True, choices=list(ROLE_PORT))
    serve(ap.parse_args().role)
