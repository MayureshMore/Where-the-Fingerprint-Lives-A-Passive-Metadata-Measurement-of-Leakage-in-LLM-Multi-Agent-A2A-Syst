#!/usr/bin/env bash
#
# run_c1_collection.sh — collection C1, unattended: deployment A, llama3.2:3b, TLS on,
# one arm, num_predict 256, 50 traces per condition, all 12 conditions in every round.
#
#   0. preflight  python deps, sse-starlette >= 3.6 and the stream fix, Ollama + model,
#                 certificates, capture access, free ports, empty output dir
#   1. pilot      one trace per topology; the run stops here unless the raw pcaps show TLS
#                 on every connection and no topology has a cut specialist stream
#   2. collect    scripts/collect_session.py, 5 balanced rounds; a crashed collector is
#                 restarted with --resume (up to 3 times); no new item after COLLECT_HOURS
#   3. checks     check_tls_capture.py and check_stream_integrity.py on the full raw captures
#   4. extract    features → data/processed_c1
#
# The whole run is kept awake with caffeinate (keep the charger in). Capture access:
#     sudo chmod o+r /dev/bpf*     before
#     sudo chmod o-r /dev/bpf*     after (the script tries sudo -n and otherwise reminds you)
#
# Usage:
#     bash scripts/run_c1_collection.sh
#     RESUME=1 bash scripts/run_c1_collection.sh     # continue an interrupted run (skips the pilot)
#
set -euo pipefail

if [ -z "${C1_AWAKE:-}" ]; then                     # re-run the whole script under caffeinate
  export C1_AWAKE=1
  exec caffeinate -dimsu bash "$0" "$@"
fi

N="${N:-50}"
ROUNDS="${ROUNDS:-5}"
SEED_OFFSET="${SEED_OFFSET:-10000}"
COLLECT_HOURS="${COLLECT_HOURS:-6}"
RESUME="${RESUME:-0}"
PY="${PYTHON:-venv/bin/python}"
[ -x "$PY" ] || PY=python3
RAW=data/raw_c1
PRO=data/processed_c1
ARM="name=a_tls,deployment=a,model=llama3.2:3b,tls=on,defense=none,out=$RAW"
STAMP="$(date +%Y%m%d_%H%M%S)"
mkdir -p data/logs
LOG="data/logs/c1_$STAMP.log"
exec > >(tee -a "$LOG") 2>&1

step() { echo; echo "== [$(date +%H:%M:%S)] $* =="; }
fail() { echo "STOPPED: $*" >&2; exit 1; }
restore_bpf() {
  if ls -l /dev/bpf0 2>/dev/null | grep -q '^crw----r'; then
    sudo -n chmod o-r /dev/bpf* 2>/dev/null && echo "capture access reverted (chmod o-r /dev/bpf*)" \
      || echo "REMINDER: run  sudo chmod o-r /dev/bpf*  to revert capture access"
  fi
}
trap restore_bpf EXIT
session() { "$PY" scripts/collect_session.py --collection-id C1 --n "$N" --rounds "$ROUNDS" \
              --seed-offset "$SEED_OFFSET" --num-predict 256 --arm "$ARM" "$@"; }
# a topology whose specialist streams are cut fails the gate
streams_ok() { "$PY" - "$1" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))["sets"]
bad = [f"{d} {t}: median {s['median_largest_reply_pkts']:g} pkts, {s['share_cut']:.0%} cut"
       for d, tops in r.items() for t, s in tops.items() if s["share_cut"] > 0.05]
print("\n".join(bad) or "all topologies stream in full")
sys.exit(1 if bad else 0)
PY
}

step "0. preflight (C1, n=$N, rounds=$ROUNDS, seed offset $SEED_OFFSET, log $LOG)"
"$PY" -c "import a2a, httpx, uvicorn, sklearn, sse_starlette, importlib.metadata as m, sys
v = tuple(int(x) for x in m.version('sse-starlette').split('.')[:2]); sys.exit(0 if v >= (3, 6) else 1)" \
  || fail "python deps missing or sse-starlette < 3.6.0 (pip install -r requirements.txt)"
grep -q "^AppStatus.disable_automatic_graceful_drain()" agents/base.py || fail "stream fix missing from agents/base.py"
curl -sf localhost:11434/api/tags | grep -q '"llama3.2:3b"' \
  || fail "Ollama not running or llama3.2:3b not pulled (ollama serve; ollama pull llama3.2:3b)"
[ -f data/tls/agent.pem ] || bash scripts/make_tls_certs.sh
openssl x509 -checkend 86400 -noout -in data/tls/agent.pem >/dev/null || bash scripts/make_tls_certs.sh
if [ "$(id -u)" != 0 ] && [ ! -r /dev/bpf0 ]; then
  fail "no capture access: run  sudo chmod o+r /dev/bpf*  first (revert afterwards with o-r)"
fi
for p in 8101 8102 8103 8111 8112 8113 8121 8122 8123; do
  lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && fail "port $p is in use"
done
if [ "$RESUME" != 1 ] && [ -n "$(ls "$RAW"/*.pcap 2>/dev/null | head -1)" ]; then
  fail "$RAW already holds traces; move it aside or RESUME=1"
fi
pmset -g batt | grep -q "AC Power" || echo "WARNING: on battery — plug in the charger"
echo "ok"

if [ "$RESUME" != 1 ]; then
  step "1. pilot: one trace per topology, then check TLS records and stream completeness"
  rm -rf "${RAW}_pilot"
  session --pilot
  "$PY" scripts/check_tls_capture.py "${RAW}_pilot" --expect tls --json "${RAW}_pilot/tls_check.json" \
    || fail "pilot TLS check failed"
  "$PY" scripts/check_stream_integrity.py "${RAW}_pilot" --json "${RAW}_pilot/stream_integrity.json"
  streams_ok "${RAW}_pilot/stream_integrity.json" || fail "pilot streams are cut"
fi

step "2. collect: $N per condition in $ROUNDS rounds, no new item after ${COLLECT_HOURS} h"
END=$(( $(date +%s) + $(printf '%.0f' "$(echo "$COLLECT_HOURS * 3600" | bc)") ))
for attempt in 1 2 3; do
  left=$(echo "scale=3; ($END - $(date +%s)) / 3600" | bc)
  if [ "$(echo "$left <= 0" | bc)" = 1 ]; then break; fi
  if session --resume --deadline-hours "$left"; then break; fi
  echo "collector exited with an error (attempt $attempt); restarting with --resume in 30 s"
  sleep 30
done
[ -n "$(ls "$RAW"/*.pcap 2>/dev/null | head -1)" ] || fail "no traces were collected"

step "3. checks on the full raw captures"
# Not fatal after a night of collection: verdicts are kept in the JSON files.
"$PY" scripts/check_tls_capture.py "$RAW" --expect tls --json "$RAW/tls_check.json" \
  || echo "WARNING: TLS record check reported problems — see $RAW/tls_check.json"
"$PY" scripts/check_stream_integrity.py "$RAW" --json "$RAW/stream_integrity.json"
streams_ok "$RAW/stream_integrity.json" || echo "WARNING: cut streams — see $RAW/stream_integrity.json"
restore_bpf

step "4. extract features"
"$PY" scripts/extract_features.py --raw "$RAW" --out "$PRO" --scapy

echo
echo "Done → $RAW (pcaps, session_meta.json, tls_check.json, stream_integrity.json), $PRO"
echo "(log: $LOG)"
