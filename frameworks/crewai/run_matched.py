"""One matched CrewAI chain-agent server in its own process. Role = LABEL by server port."""
import argparse
from matched_agents import ROLE_PORT, serve
if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--role", required=True, choices=list(ROLE_PORT))
    serve(ap.parse_args().role)
