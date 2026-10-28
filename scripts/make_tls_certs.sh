#!/usr/bin/env bash
#
# make_tls_certs.sh — create a throwaway local CA and one agent certificate for the
# TLS control experiment (scripts/run_pilot.py --tls-dir DIR).
#
# The certificate is valid for 127.0.0.1 and localhost only. Keys stay local:
# the default output dir (data/tls) is gitignored.
#
# Usage:  bash scripts/make_tls_certs.sh [OUT_DIR]
set -euo pipefail

OUT="${1:-data/tls}"
mkdir -p "$OUT"
cd "$OUT"

openssl req -x509 -newkey rsa:2048 -nodes -days 365 -subj "/CN=A2A testbed CA" \
    -keyout ca-key.pem -out ca.pem 2>/dev/null

openssl req -newkey rsa:2048 -nodes -subj "/CN=localhost" \
    -keyout agent-key.pem -out agent.csr 2>/dev/null
printf 'subjectAltName=IP:127.0.0.1,DNS:localhost\nextendedKeyUsage=serverAuth\n' > agent.ext
openssl x509 -req -in agent.csr -CA ca.pem -CAkey ca-key.pem -CAcreateserial -days 365 \
    -extfile agent.ext -out agent.pem 2>/dev/null

echo "wrote $OUT/{ca.pem, agent.pem, agent-key.pem}"
