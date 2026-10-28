#!/usr/bin/env bash
#
# AutoGen cross-framework collector. Each TRIP: start host + 3 specialist workers (each in its
# OWN process ⇒ its own gRPC channel ⇒ one TCP flow with a distinct ephemeral port), capture
# lo0:50051 at 96-byte snaplen while the orchestrator drives one task, then map source-port→role
# via lsof (workers) + elimination (orchestrator). Port is a ground-truth LABEL only, never a
# feature. Full teardown per trip ⇒ clean per-trip per-role samples. Local ollama ⇒ no spend.
# (Written for macOS bash 3.2 — no associative arrays.)
#
# Usage: N=3 bash collect_trips.sh
set -u
cd "$(dirname "$0")"
PY="./.venv/bin/python"
HOSTPORT=50051
OUT="${OUT:-../../data/raw_autogen}"; mkdir -p "$OUT" logs   # repo-level data dir (gitignored)
N="${N:-3}"
TOPICS=("undersea cables" "coral reefs" "mars colonization" "quantum computing" "ancient rome"
        "jazz history" "wind turbines" "deep sea fish" "volcanoes" "the water cycle"
        "honeybee behavior" "glacier retreat" "the printing press" "black holes" "silk road trade"
        "photosynthesis" "the human immune system" "renewable batteries" "migratory birds" "tea ceremonies"
        "desert ecosystems" "the french revolution" "gut microbiome" "lighthouse engineering" "auroras")

clearports(){ lsof -ti tcp:$HOSTPORT 2>/dev/null | xargs kill -9 2>/dev/null; }
portof(){ lsof -nP -a -p "$1" -iTCP 2>/dev/null | grep -oE "127.0.0.1:[0-9]+->127.0.0.1:$HOSTPORT" | head -1 | sed -E 's/127.0.0.1:([0-9]+).*/\1/'; }

last=$(ls "$OUT"/trip_*.pcap 2>/dev/null | sed -E 's#.*/trip_0*([0-9]+)\.pcap#\1#' | sort -n | tail -1)
start_i=$(( ${last:-0} + 1 ))
echo "collecting $N trips (roles: researcher writer reviewer) starting at trip_$(printf %03d $start_i)"

for k in $(seq 0 $((N-1))); do
    i=$(( start_i + k )); id=$(printf "trip_%03d" "$i")
    topic="${TOPICS[$(( i % ${#TOPICS[@]} ))]}"
    clearports; sleep 0.5

    $PY run_host.py > "logs/${id}_host.log" 2>&1 & hpid=$!
    sleep 2
    $PY run_worker.py --role researcher > "logs/${id}_researcher.log" 2>&1 & pid_r=$!
    $PY run_worker.py --role writer     > "logs/${id}_writer.log"     2>&1 & pid_w=$!
    $PY run_worker.py --role reviewer   > "logs/${id}_reviewer.log"   2>&1 & pid_v=$!
    sleep 6                                    # let workers register + connect

    port_r=$(portof "$pid_r"); port_w=$(portof "$pid_w"); port_v=$(portof "$pid_v")
    if [ -z "$port_r" ] || [ -z "$port_w" ] || [ -z "$port_v" ]; then
        echo "  ! $id: missing worker port (r=$port_r w=$port_w v=$port_v) — see logs/${id}_*.log"
        kill $pid_r $pid_w $pid_v $hpid 2>/dev/null; clearports; sleep 1; continue
    fi

    tcpdump -i lo0 -s 96 -w "$OUT/$id.pcap" "tcp port $HOSTPORT" 2>/dev/null & tpid=$!
    sleep 0.6
    $PY run_orchestrator.py --topic "$topic" > "logs/${id}_orch.log" 2>&1
    sleep 0.6
    kill $tpid 2>/dev/null; wait $tpid 2>/dev/null
    kill $pid_r $pid_w $pid_v $hpid 2>/dev/null; clearports

    # orchestrator port = client port touching :50051 that is NOT a worker port
    worker_ports=" $port_r $port_w $port_v "
    orch_port=$(tcpdump -r "$OUT/$id.pcap" -nn 2>/dev/null \
        | grep -oE "127.0.0.1\.[0-9]+ > 127.0.0.1\.$HOSTPORT" | awk -F'[. ]' '{print $5}' \
        | sort -u | while read -r pp; do echo "$worker_ports" | grep -q " $pp " || echo "$pp"; done | head -1)

    sz=$(stat -f%z "$OUT/$id.pcap" 2>/dev/null || echo 0)
    $PY - "$OUT/$id.labels.json" "$topic" "$port_r" "$port_w" "$port_v" "${orch_port:-}" <<'PYW'
import json, sys
out, topic, rp, wp, vp, op = sys.argv[1:7]
labels = {"system":"autogen_grpc","framework":"autogen-core-0.7.5","llm":"ollama/llama3.2:3b",
          "trace_id": out.split("/")[-1].replace(".labels.json",""), "topic": topic,
          "host_port": 50051,
          "port_role": {rp:"researcher", wp:"writer", vp:"reviewer"}}
if op: labels["port_role"][op] = "orchestrator"
json.dump(labels, open(out,"w"), indent=2)
PYW
    nports=$(tcpdump -r "$OUT/$id.pcap" -nn 2>/dev/null | grep -oE "127.0.0.1\.[0-9]+ > 127.0.0.1\.$HOSTPORT" | awk -F'[. ]' '{print $5}' | sort -u | wc -l | tr -d ' ')
    printf "  [%s] topic=%-18s pcap=%6sB client-ports=%s  roles{r:%s w:%s v:%s orch:%s}\n" \
        "$id" "$topic" "$sz" "$nports" "$port_r" "$port_w" "$port_v" "${orch_port:-?}"
    sleep 1
done
echo "done. pcaps + labels in $OUT/"
