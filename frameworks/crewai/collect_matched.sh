#!/usr/bin/env bash
# Matched-pair collector (§13.1): CrewAI agents mirroring deployment A (orchestrator/executor/
# retriever/validator, chained a2a-sdk 0.3.26 SSE, local ollama), driven on A's OWN prompts.
# Capture lo0 ports 8100-8103. Server (dest) port is the role LABEL only. Prereq: sudo chmod o+r /dev/bpf*
set -u
cd "$(dirname "$0")"
PY="./.venv/bin/python"; OUT="${OUT:-../../data/raw_crewai_matched}"; mkdir -p "$OUT" logs_matched
N="${N:-40}"; PORTS="8100-8103"; PORTLIST="8100 8101 8102 8103"
clearports(){ for p in $PORTLIST; do lsof -ti tcp:$p 2>/dev/null | xargs kill -9 2>/dev/null; done; }
trap 'clearports' EXIT
bpf_ok=0; for b in /dev/bpf*; do [ -r "$b" ] && { bpf_ok=1; break; }; done
[ "$bpf_ok" -ne 1 ] && { echo "BLOCKED: no readable /dev/bpf* — run: sudo chmod o+r /dev/bpf*"; exit 3; }

PROMPTS=(); while IFS= read -r line; do PROMPTS+=("$line"); done < <(head -n "$N" a_prompts.jsonl)
last=$(ls "$OUT"/trip_*.pcap 2>/dev/null | sed -E 's#.*/trip_0*([0-9]+)\.pcap#\1#' | sort -n | tail -1)
start_i=$(( ${last:-0} + 1 ))
echo "collecting ${#PROMPTS[@]} matched CrewAI trips (chain) starting at trip_$(printf %03d $start_i)"

ok=0
for k in "${!PROMPTS[@]}"; do
    i=$(( start_i + k )); id=$(printf "trip_%03d" "$i")
    wf=$($PY -c "import json,sys;print(json.loads(sys.argv[1])['workflow'])" "${PROMPTS[$k]}")
    pr=$($PY -c "import json,sys;print(json.loads(sys.argv[1])['prompt'])" "${PROMPTS[$k]}")
    clearports; sleep 0.5
    $PY run_matched.py --role orchestrator > "logs_matched/${id}_orch.log" 2>&1 &
    $PY run_matched.py --role executor     > "logs_matched/${id}_exec.log" 2>&1 &
    $PY run_matched.py --role retriever    > "logs_matched/${id}_retr.log" 2>&1 &
    $PY run_matched.py --role validator    > "logs_matched/${id}_vald.log" 2>&1 &
    sleep 14
    tcpdump -i lo0 -s 96 -w "$OUT/$id.pcap" "tcp portrange $PORTS" 2>/dev/null & tpid=$!
    sleep 0.8
    $PY matched_driver.py --prompt "$pr" > "logs_matched/${id}_drive.log" 2>&1
    sleep 0.8
    kill $tpid 2>/dev/null; wait $tpid 2>/dev/null; clearports
    sz=$(stat -f%z "$OUT/$id.pcap" 2>/dev/null || echo 0)
    if [ "${sz:-0}" -le 400 ]; then echo "  ~ $id empty (${sz}B) — see logs_matched/${id}_*"; rm -f "$OUT/$id.pcap"; continue; fi
    $PY - "$OUT/$id.labels.json" "$wf" <<PYW
import json, sys
out, wf = sys.argv[1:3]
json.dump({"system":"crewai_matched","framework":"crewai-1.15.2","transport":"a2a-sdk-0.3.26 JSON-RPC+SSE",
           "llm":"ollama/llama3.2:3b","trace_id":out.split("/")[-1].replace(".labels.json",""),"workflow_class":wf,
           "agent_endpoints":{"orchestrator":"localhost:8100","executor":"localhost:8101",
                              "retriever":"localhost:8102","validator":"localhost:8103"}}, open(out,"w"), indent=2)
PYW
    ok=$((ok+1)); printf "  [%s] wf=%-18s pcap=%6sB\n" "$id" "$wf" "$sz"; sleep 0.5
done
echo "done. $ok good matched pcaps + labels in $OUT/"
