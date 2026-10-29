#!/usr/bin/env bash
#
# CrewAI cross-framework collector (same-transport A2A). Each TRIP: start the CrewAI planner +
# 3 CrewAI specialists, each an a2a-sdk 0.3.26 A2AStarletteApplication server (IDENTICAL server
# lib+version to the a2a_mcp positive class) with a real CrewAI Agent brain (local ollama, no
# spend). Capture lo0 ports 10201-10205 at 96-byte snaplen while the driver fans one trip out
# over A2A JSON-RPC+SSE, then write a sidecar mapping server-port -> role. Server (dest) port is
# a ground-truth LABEL only, never a feature. Full teardown per trip => clean per-role samples.
#
# Prereq (one-time, for non-root tcpdump, same as the A2A/AutoGen collections):
#   sudo chmod o+r /dev/bpf*
# Run (NO sudo):  N=30 bash collect_trips.sh
set -u
cd "$(dirname "$0")"
PY="./.venv/bin/python"
OUT="${OUT:-../../data/raw_crewai}"; mkdir -p "$OUT" logs   # repo-level data dir (gitignored)
N="${N:-30}"
PORTS="10201-10205"
PORTLIST="10201 10203 10204 10205"

DESTS=("Tokyo Japan|NRT" "Paris France|CDG" "Rome Italy|FCO" "Sydney Australia|SYD"
       "Cairo Egypt|CAI" "Reykjavik Iceland|KEF" "Bangkok Thailand|BKK" "Lisbon Portugal|LIS"
       "Athens Greece|ATH" "Dubai UAE|DXB" "Singapore|SIN" "Toronto Canada|YYZ"
       "Mexico City Mexico|MEX" "Cape Town South Africa|CPT" "Oslo Norway|OSL" "Seoul Korea|ICN"
       "Buenos Aires Argentina|EZE" "Vienna Austria|VIE" "Istanbul Turkey|IST" "Nairobi Kenya|NBO")
ORIG=("New York JFK" "San Francisco SFO" "Chicago ORD" "Los Angeles LAX" "Boston BOS" "Seattle SEA")

clearports(){ for p in $PORTLIST; do lsof -ti tcp:$p 2>/dev/null | xargs kill -9 2>/dev/null; done; }
trap 'clearports' EXIT

# preflight: BPF must be readable or every trip is a silent 0-byte pcap (ghost-trace gotcha).
# Use a readability test, NOT a live `tcpdump -c 1` (that blocks forever waiting for a packet).
bpf_ok=0
for b in /dev/bpf*; do [ -r "$b" ] && { bpf_ok=1; break; }; done
if [ "$bpf_ok" -ne 1 ]; then
    echo "BLOCKED: cannot capture on lo0 (no readable /dev/bpf*). Run once:  sudo chmod o+r /dev/bpf*"; exit 3
fi

last=$(ls "$OUT"/trip_*.pcap 2>/dev/null | sed -E 's#.*/trip_0*([0-9]+)\.pcap#\1#' | sort -n | tail -1)
start_i=$(( ${last:-0} + 1 ))
echo "collecting $N CrewAI trips (planner+air+hotel+car) starting at trip_$(printf %03d $start_i)"

ok=0
for k in $(seq 0 $((N-1))); do
    i=$(( start_i + k )); id=$(printf "trip_%03d" "$i")
    d=${DESTS[$(( (i-1) % ${#DESTS[@]} ))]}; dest=${d%%|*}; apt=${d##*|}
    o=${ORIG[$(( (i-1) % ${#ORIG[@]} ))]}
    d1=$(printf "2026-05-0%d" $(( i % 9 + 1 ))); d2=$(printf "2026-05-1%d" $(( i % 9 )))
    clearports; sleep 0.5

    $PY run_agent.py --role planner       > "logs/${id}_planner.log"  2>&1 &
    $PY run_agent.py --role air_ticketing > "logs/${id}_air.log"      2>&1 &
    $PY run_agent.py --role hotel         > "logs/${id}_hotel.log"    2>&1 &
    $PY run_agent.py --role car_rental    > "logs/${id}_car.log"      2>&1 &
    sleep 14                                   # let all 4 servers bind + load crewai

    tcpdump -i lo0 -s 96 -w "$OUT/$id.pcap" "tcp portrange $PORTS" 2>/dev/null & tpid=$!
    sleep 0.8
    $PY trip_driver.py --origin "$o" --dest "$dest" --d1 "$d1" --d2 "$d2" > "logs/${id}_drive.log" 2>&1
    sleep 0.8
    kill $tpid 2>/dev/null; wait $tpid 2>/dev/null
    clearports

    sz=$(stat -f%z "$OUT/$id.pcap" 2>/dev/null || echo 0)
    if [ "${sz:-0}" -le 400 ]; then echo "  ~ $id empty/failed (pcap ${sz}B) — see logs/${id}_*.log"; rm -f "$OUT/$id.pcap"; continue; fi

    $PY - "$OUT/$id.labels.json" "$dest" "$o" <<'PYW'
import json, sys
out, dest, orig = sys.argv[1:4]
labels = {"system":"crewai_a2a","framework":"crewai-1.15.2","transport":"a2a-sdk-0.3.26 JSON-RPC+SSE over HTTP",
          "llm":"ollama/llama3.2:3b","trace_id": out.split("/")[-1].replace(".labels.json",""),
          "origin": orig, "dest": dest,
          "agent_endpoints": {"planner":"localhost:10201","air_ticketing":"localhost:10203",
                              "hotel":"localhost:10204","car_rental":"localhost:10205"}}
json.dump(labels, open(out,"w"), indent=2)
PYW
    nports=$(tcpdump -r "$OUT/$id.pcap" -nn 2>/dev/null | grep -oE "> 127.0.0.1\.(10201|10203|10204|10205)" | sort -u | wc -l | tr -d ' ')
    ok=$((ok+1))
    printf "  [%s] %-22s pcap=%6sB server-ports-hit=%s\n" "$id" "$o -> $dest" "$sz" "$nports"
    sleep 1
done
echo "done. $ok good pcaps + labels in $OUT/"
