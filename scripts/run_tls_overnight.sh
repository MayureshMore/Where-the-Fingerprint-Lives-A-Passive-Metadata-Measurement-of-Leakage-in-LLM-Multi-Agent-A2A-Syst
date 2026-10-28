#!/usr/bin/env bash
#
# run_tls_overnight.sh — the whole TLS control, unattended:
#
#   0. preflight   python deps, Ollama + llama3.2:3b, certificates, capture access, free ports
#   1. pilot       one cleartext/TLS pair; the raw pcaps must show TLS records on the TLS
#                  trace (0x16 0x03 handshake, 0x17 0x03 0x03 data) and cleartext HTTP on
#                  the other, or the run stops here
#   2. collect     same-session round-robin, 12 conditions x N pairs (default 36 → 864
#                  traces, ~8 h at ~31 s per trace); the Mac is kept awake
#   3. check       record check on the full raw captures (before any stripping)
#                  → data/raw_tlspair_tls/tls_check.json
#   4. extract     features for both arms
#   5. evaluate    → data/results/tls_control.json + figures/tls_control.png
#
# Capture access: tcpdump needs read access to /dev/bpf*. Before starting:
#     sudo chmod o+r /dev/bpf*
# That lets every process on the Mac capture all traffic until reboot, so undo it
# when the run ends (the script tries `sudo -n` and otherwise prints the command):
#     sudo chmod o-r /dev/bpf*
#
# Usage:
#     bash scripts/run_tls_overnight.sh            # N=36
#     N=3 bash scripts/run_tls_overnight.sh        # quick dry run (72 traces, ~45 min) into
#                                                  # *_n3 dirs and data/results_demo
#
set -euo pipefail

N="${N:-36}"
PY="${PYTHON:-venv/bin/python}"
[ -x "$PY" ] || PY=python3
STAMP="$(date +%Y%m%d_%H%M%S)"
mkdir -p data/logs
LOG="data/logs/tls_session_$STAMP.log"
exec > >(tee -a "$LOG") 2>&1

if [ "$N" = 36 ]; then SFX=""; else SFX="_n$N"; fi
RAW_C="data/raw_tlspair_clear$SFX";  RAW_T="data/raw_tlspair_tls$SFX"
PRO_C="data/processed_tlspair_clear$SFX"; PRO_T="data/processed_tlspair_tls$SFX"
RESULTS="${A2A_RESULTS_DIR:-data/results}"
[ -n "$SFX" ] && RESULTS="${A2A_RESULTS_DIR:-data/results_demo}"

step() { echo; echo "== [$(date +%H:%M:%S)] $* =="; }
fail() { echo "STOPPED: $*" >&2; exit 1; }
restore_bpf() {
  if ls -l /dev/bpf0 2>/dev/null | grep -q '^crw----r'; then
    sudo -n chmod o-r /dev/bpf* 2>/dev/null && echo "capture access reverted (chmod o-r /dev/bpf*)" \
      || echo "REMINDER: run  sudo chmod o-r /dev/bpf*  to revert capture access"
  fi
}

trap restore_bpf EXIT

step "0. preflight (N=$N, log $LOG)"
"$PY" -c "import a2a, httpx, uvicorn, sklearn" || fail "python deps missing (pip install -r requirements.txt)"
curl -sf localhost:11434/api/tags | grep -q '"llama3.2:3b"' \
  || fail "Ollama not running or llama3.2:3b not pulled (ollama serve; ollama pull llama3.2:3b)"
[ -f data/tls/agent.pem ] || bash scripts/make_tls_certs.sh
openssl x509 -checkend 86400 -noout -in data/tls/agent.pem >/dev/null || bash scripts/make_tls_certs.sh
if [ "$(id -u)" != 0 ] && [ ! -r /dev/bpf0 ]; then
  fail "no capture access: run  sudo chmod o+r /dev/bpf*  first (revert afterwards with o-r)"
fi
for p in 8001 8002 8003 8041 8042 8043; do
  lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && fail "port $p is in use"
done
for d in "$RAW_C" "$RAW_T"; do
  [ -n "$(ls "$d"/*.pcap 2>/dev/null | head -1)" ] && fail "$d already holds traces; move it aside first"
done
echo "ok"

step "1. pilot: one pair, then check the raw pcaps for TLS records"
rm -rf data/tls_pilot
"$PY" scripts/run_tls_session.py --pilot
"$PY" scripts/check_tls_capture.py data/tls_pilot/tls --expect tls || fail "pilot TLS trace check failed"
"$PY" scripts/check_tls_capture.py data/tls_pilot/clear --expect clear || fail "pilot cleartext trace check failed"

step "2. collect: same-session round-robin, $N pairs per condition (caffeinate keeps the Mac awake)"
caffeinate -dims "$PY" scripts/run_tls_session.py --n "$N" --out-clear "$RAW_C" --out-tls "$RAW_T"

step "3. record check on the full raw captures"
"$PY" scripts/check_tls_capture.py "$RAW_T" --expect tls --json "$RAW_T/tls_check.json" \
  || fail "TLS record check failed on $RAW_T"
"$PY" scripts/check_tls_capture.py "$RAW_C" --expect clear --json "$RAW_C/clear_check.json" \
  || fail "cleartext record check failed on $RAW_C"
restore_bpf

step "4. extract features"
"$PY" scripts/extract_features.py --raw "$RAW_C" --out "$PRO_C" --scapy
"$PY" scripts/extract_features.py --raw "$RAW_T" --out "$PRO_T" --scapy

step "5. evaluate"
A2A_RESULTS_DIR="$RESULTS" "$PY" scripts/evaluate_tls_control.py \
  --clear "$PRO_C" --tls "$PRO_T" --clear-raw "$RAW_C" --tls-raw "$RAW_T"

echo
echo "Done → $RESULTS/tls_control.json  (log: $LOG)"
