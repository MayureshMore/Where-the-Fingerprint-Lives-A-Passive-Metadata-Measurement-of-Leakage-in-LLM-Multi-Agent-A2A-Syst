#!/usr/bin/env bash
#
# PARKED — do not run. Superseded by one same-session TLS collection of all five
# deployments as arms of scripts/collect_session.py (see RECREATE §7e). Kept for reference.
#
# recollect_core_deployments.sh — re-collect the core deployments after the SSE
# stream fix (agents/base.py; sse-starlette >= 3.6.0).
#
# Before the fix, every collector that ran more than one agent set in one process cut
# each later specialist stream after its first event, so chain and mesh traces of these
# sets carry no streamed replies (scripts/check_stream_integrity.py shows it from the
# captures). This script collects each named set again with --n 50 --num-predict 256,
# extracts features, and checks the new captures for cut streams.
#
#   set        deployment   model         raw dir               processed dir
#   a          a            llama3.2:3b   data/raw              data/processed
#   amodel     a            qwen2.5:7b    data/raw_amodel_sdk   data/processed_amodel_sdk
#   b          b            qwen2.5:7b    data/raw_b_sdk        data/processed_b_sdk
#   blogic     b            llama3.2:3b   data/raw_blogic_sdk   data/processed_blogic_sdk
#   langgraph  langgraph    llama3.2:3b   data/raw_langgraph    data/processed_langgraph
#
# Sets named together run in parallel (each deployment has its own ports); run them one
# call at a time to collect sequentially. The pre-fix raw and processed dirs are moved to
# data/pre_fix/ (never deleted), and data/results is snapshotted to data/results/pre_fix/
# once, before anything is re-evaluated.
#
# Capture needs read access to /dev/bpf*:  sudo chmod o+r /dev/bpf*  (revert with o-r).
#
# Usage:
#     bash scripts/recollect_core_deployments.sh a blogic     # A and B-logic in parallel
#     bash scripts/recollect_core_deployments.sh amodel
#     RESUME=1 bash scripts/recollect_core_deployments.sh a   # keep what is already in data/raw
#
set -euo pipefail

N="${N:-50}"
NUM_PREDICT="${NUM_PREDICT:-256}"
RESUME="${RESUME:-0}"
PY="${PYTHON:-venv/bin/python}"
[ -x "$PY" ] || PY=python3
mkdir -p data/logs data/pre_fix
STAMP="$(date +%Y%m%d_%H%M%S)"

# set → "deployment model raw-dir processed-dir"   (bash 3.2: no associative arrays)
spec() {
  case "$1" in
    a)         echo "a llama3.2:3b data/raw data/processed" ;;
    amodel)    echo "a qwen2.5:7b data/raw_amodel_sdk data/processed_amodel_sdk" ;;
    b)         echo "b qwen2.5:7b data/raw_b_sdk data/processed_b_sdk" ;;
    blogic)    echo "b llama3.2:3b data/raw_blogic_sdk data/processed_blogic_sdk" ;;
    langgraph) echo "langgraph llama3.2:3b data/raw_langgraph data/processed_langgraph" ;;
    *)         return 1 ;;
  esac
}
field() { spec "$1" | cut -d' ' -f"$2"; }     # 1 deployment, 2 model, 3 raw, 4 processed
ports() {
  case "$1" in a) echo "8000 8001 8002 8003" ;; b) echo "8010 8011 8012 8013" ;;
               langgraph) echo "8030 8031 8032 8033" ;; esac
}

fail() { echo "STOPPED: $*" >&2; exit 1; }
[ $# -gt 0 ] || fail "name one or more sets: a amodel b blogic langgraph"
for s in "$@"; do spec "$s" >/dev/null || fail "unknown set '$s'"; done

# ── preflight ────────────────────────────────────────────────────────────────
"$PY" -c "import sse_starlette, importlib.metadata as m, sys
v = tuple(int(x) for x in m.version('sse-starlette').split('.')[:2])
sys.exit(0 if v >= (3, 6) else 1)" || fail "sse-starlette < 3.6.0 (pip install -r requirements.txt)"
grep -q "^AppStatus.disable_automatic_graceful_drain()" agents/base.py || fail "stream fix missing from agents/base.py"
if [ "$(id -u)" != 0 ] && [ ! -r /dev/bpf0 ]; then
  fail "no capture access: run  sudo chmod o+r /dev/bpf*  first (revert afterwards with o-r)"
fi
for s in "$@"; do
  m=$(field "$s" 2)
  curl -sf localhost:11434/api/tags | grep -q "\"$m\"" || fail "Ollama not running or $m not pulled"
  for p in $(ports "$(field "$s" 1)"); do
    lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && fail "port $p is in use"
  done
done

# ── keep the pre-fix results and data ────────────────────────────────────────
if [ ! -d data/results/pre_fix ]; then
  mkdir -p data/results/pre_fix
  (cd data/results && find . -path ./pre_fix -prune -o -type f -print | cpio -pdm --quiet pre_fix)
  echo "snapshot of data/results → data/results/pre_fix/"
fi
for s in "$@"; do
  for d in "$(field "$s" 3)" "$(field "$s" 4)"; do
    dest="data/pre_fix/$(basename "$d")"
    if [ -d "$d" ] && [ ! -e "$dest" ] && [ "$RESUME" != 1 ]; then
      mv "$d" "$dest" && echo "moved $d → $dest"
    fi
  done
  if [ "$RESUME" != 1 ] && [ -n "$(ls "$(field "$s" 3)"/*.pcap 2>/dev/null | head -1)" ]; then
    fail "$(field "$s" 3) already holds traces; move it aside or RESUME=1"
  fi
done

# ── collect → extract → integrity check, one background job per set ─────────
run_set() {
  local s=$1 log="data/logs/recollect_${1}_$STAMP.log"
  local dep model raw pro
  read -r dep model raw pro <<<"$(spec "$s")"
  {
    echo "== [$(date +%H:%M:%S)] collect $s: deployment $dep, $model, n=$N, num_predict=$NUM_PREDICT"
    caffeinate -dims "$PY" scripts/collect_deployment.py --deployment "$dep" --model "$model" \
      --n "$N" --num-predict "$NUM_PREDICT" --out "$raw"
    echo "== [$(date +%H:%M:%S)] extract $s"
    "$PY" scripts/extract_features.py --raw "$raw" --out "$pro" --scapy
    echo "== [$(date +%H:%M:%S)] stream integrity $s"
    "$PY" scripts/check_stream_integrity.py "$raw" --json "$raw/stream_integrity.json"
    echo "== [$(date +%H:%M:%S)] done $s"
  } >"$log" 2>&1
}

pids=()
for s in "$@"; do
  echo "[$(date +%H:%M:%S)] starting $s → data/logs/recollect_${s}_$STAMP.log"
  run_set "$s" &
  pids+=($!)
done
status=0
for i in "${!pids[@]}"; do
  wait "${pids[$i]}" || { echo "set ${*:$((i+1)):1} FAILED — see its log"; status=1; }
done
for s in "$@"; do grep -E "^data/" "data/logs/recollect_${s}_$STAMP.log" | tail -1 || true; done
echo "Revert capture access when all sets are done:  sudo chmod o-r /dev/bpf*"
exit $status
