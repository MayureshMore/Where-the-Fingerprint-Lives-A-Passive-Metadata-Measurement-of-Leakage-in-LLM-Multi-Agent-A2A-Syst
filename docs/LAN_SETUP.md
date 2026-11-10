# LAN setup: edge agent on a Raspberry Pi, emulated cloud on the Mac (collection C2)

**Use case:** an edge AI assistant for building and factory operations. The assistant's agent runs
**on the building's IoT gateway** (the Raspberry Pi). It answers alarm triage itself with a small
local model, sends sensor analysis and fault diagnosis to a cloud agent `diagnostics` and procedure
questions to a cloud agent `knowledge`, and files every result with the building's maintenance-ticket
service. The Mac stands in for both the cloud (on a separate address) and the building server, and
it is the gateway's router, so its capture is what a passive observer on the building network sees.

| Role | Host | Address | Model |
|---|---|---|---|
| Edge agent (A2A client) + local triage (`scripts/serve_edge.py`) | Raspberry Pi 5 | `192.168.2.2` | Ollama on the Pi, `llama3.2:1b`, `num_predict 128` |
| Cloud agents `diagnostics`, `knowledge` (`scripts/serve_cloud.py`) | Mac, cloud alias | `192.168.2.100` (alias on `bridge100`) | Ollama on the Mac (localhost), `llama3.2:3b`, `num_predict 256` |
| Ticket service, HTTPS `POST /tickets` (`scripts/serve_cloud.py`) | Mac, building server | `192.168.2.1` | none |
| Collector and capture (= the building router) | Mac, `bridge100` | | |

**Routing on the edge agent is a fixed rule on the task type** (`agents/edge.py`), as a building
management system tags its requests: `alert_triage` is answered on the gateway and never leaves the
building; `sensor_analysis` and `fault_diagnosis` go to `diagnostics`; `procedure_lookup` goes to
`knowledge`. After every task the edge agent POSTs its result to the ticket service. Every link is
TLS 1.3. No LLM router (it would cost Pi time and make routing a random variable).

**Ports, per arm base B** (`lan` 8100, `lan_pad` 8200, `lan_padmax` 8300): `diagnostics` B+1 and
`knowledge` B+2 on `192.168.2.100`; tickets B+5 on `192.168.2.1`; the edge agent's task trigger
B+9 on `192.168.2.2`. Each arm has its own ports, so one arm's closing connections never land in
another arm's captures.

| Arm | Input padding (the edge agent's request to the cloud agent) |
|---|---|
| `lan` | none |
| `lan_pad` | request bodies padded to 1024/2048/4096/8192/16384/32768 B (paper 1's pow2 buckets from 1 KB) |
| `lan_padmax` | request bodies padded to 8192 B (16384 above it): every cloud request in one bucket (`pad_expect=8192`) |

The edge agent sends the task text to the cloud agent as it is (no sub-task plan), so the padded
body is the task input plus about 0.4 KB; C2's longest input is 5.3 KB, so every request fits in
8192. Ticket posts are not padded: the building-network leg stays exposed, and the paper says so.
Padding is set once, on the collector's `--arm pad=`; each task carries it to the edge agent.

**The task trigger.** The collector stays on the Mac and sends each task to the edge agent's trigger
port (B+9, plain HTTP). The trigger port is not in the capture filter, so no capture, and hence
neither observer view, contains it; in the paper the trigger stands for the sensors and building
systems wired to the gateway. Why not an injector on the Pi reading a pushed schedule: every
capture would then have to be cut out of one continuous capture by the Pi's clock, and the
session machinery (balanced rounds, arms alternating on the same prompt, a retry per failed
trace, `--resume`, sidecars) would have to be rebuilt on the Pi. With the trigger, each capture
starts before the task and stops after its last connection closes, exactly as in C1.

**Observer views** (one capture, two vantage points; `a2a_leakcheck --vantage`):

| View | Who | Sees |
|---|---|---|
| `v1` building network | a compromised gateway or router, a mirrored switch port | every flow of the Pi to the cloud alias and to the ticket service |
| `v2` upstream | the ISP, a cellular backhaul, the cloud's edge | only the flows between the Pi and the cloud alias |

At `v2` every `alert_triage` task shows no flow at all. That is an observation, not a missing
trace: leakcheck keeps such traces with all-zero features. Attributes: `task_type` (4 classes),
`escalated` (cloud call or not; at `v2` padding cannot hide whether a call happened),
`cloud_role` (`diagnostics` or `knowledge`, escalated tasks only), and the input size (the
first-request estimator). The architecture is fixed, so C2 has no topology attribute.

**Emulated WAN.** Traffic from the Pi to the cloud alias is delayed on the Pi's egress with
`tc netem`, by a round trip measured from the Mac to the nearest public cloud region (section 7).
The whole delay sits on the Pi's side of the capture point, so the Mac captures each of the Pi's
packets to the cloud after the delay, like an observer next to the cloud: sizes, counts and
whether a call happened are as any observer sees them, but the round trip shows up after a
response (before the Pi's next packet) rather than between a request and its response.

**Ethics:** the cable connects only your own two devices, and the capture filter is limited to the
Pi's address and the agent and ticket ports. Keep the Pi off Wi-Fi: it reaches the network only
through the Mac. Never capture on a shared interface.

## 0. You need

- The Mac with this repo, its `venv`, Ollama with `llama3.2:3b`, and an Ethernet port or adapter.
- A Raspberry Pi 5 (4 GB or more) running Raspberry Pi OS 64-bit (Bookworm), with SSH on.
- One Ethernet cable from the Pi to the Mac. Nothing else on that link.

## 1. The link, with the Mac as gateway

1. Plug the cable into both machines and power the Pi.
2. On the Mac: System Settings → General → Sharing → Internet Sharing → (i). Share your
   connection from **Wi-Fi** to computers using **your Ethernet adapter**. Turn Internet Sharing
   on. macOS creates `bridge100`, gives it `192.168.2.1`, and serves DHCP and NAT on it.
3. On the Mac, check the address and find the Pi:
   ```bash
   ifconfig bridge100 | grep 'inet '          # inet 192.168.2.1 ...
   arp -a -i bridge100                         # the Pi's DHCP address
   ```
4. SSH to the Pi at that address, fix its address, and turn its Wi-Fi off:
   ```bash
   nmcli con show                              # the wired connection's name, e.g. "Wired connection 1"
   sudo nmcli con mod "Wired connection 1" ipv4.method manual \
       ipv4.addresses 192.168.2.2/24 ipv4.gateway 192.168.2.1 ipv4.dns 192.168.2.1
   sudo nmcli con up "Wired connection 1"
   sudo nmcli radio wifi off
   ```
5. Check from the Pi: the Mac is its gateway and it reaches the internet through it.
   ```bash
   ip route | grep default                     # default via 192.168.2.1 dev eth0
   ping -c 3 192.168.2.1 && ping -c 3 1.1.1.1
   ```

## 2. The cloud alias on the Mac

The cloud agents get their own address on the link, so the Pi's flows to "the cloud" and to the
building server are told apart by address, as on a real network:
```bash
sudo ifconfig bridge100 alias 192.168.2.100 netmask 255.255.255.255
ifconfig bridge100 | grep 'inet '               # 192.168.2.1 and 192.168.2.100
```
From the Pi: `ping -c 3 192.168.2.100`. The alias goes away when Internet Sharing restarts or the
Mac reboots; add it again before starting the cloud services.

## 3. Ollama

- **Mac:** Ollama as usual, on localhost (the cloud agents call it locally; it never crosses the
  link). If an earlier setup ran `OLLAMA_HOST=192.168.2.1 ollama serve`, quit it and start the
  Ollama app. `ollama list` shows `llama3.2:3b`.
- **Pi:** install Ollama and the edge model (the Pi reaches the internet through the Mac):
  ```bash
  curl -fsSL https://ollama.com/install.sh | sh
  ollama pull llama3.2:1b
  time ollama run llama3.2:1b "Triage: ALARM A512 HIGH: chiller CH-1 high temperature. Priority, team, first action."
  ```
  If `qwen2.5:1.5b` answers faster on your Pi (`ollama pull qwen2.5:1.5b`, same `time` line), use
  it and pass `--model qwen2.5:1.5b` in section 6. Record the choice.

## 4. Code on the Pi

On the Pi:
```bash
sudo apt install -y python3-venv rsync tmux
mkdir -p ~/a2a
```
From the Mac, in the repo:
```bash
rsync -a --exclude data --exclude venv --exclude .git --exclude dist ./ pi@192.168.2.2:a2a/
```
On the Pi, install what the edge agent needs, at the Mac's versions (requirements-lock.txt):
```bash
cd ~/a2a && python3 -m venv venv
venv/bin/pip install "a2a-sdk[http-server]==0.3.26" "sse-starlette==3.6.0" "uvicorn[standard]==0.49.0" \
    "httpx==0.28.1" "httpx-sse==0.4.3" "pydantic==2.13.4" "starlette==1.2.1"
venv/bin/python --version; venv/bin/pip freeze > ~/pi-freeze.txt    # keep both with the collection
```

## 5. TLS certificates

One certificate for the Mac's two TLS services (the cloud alias and the building server); the Pi is
only a TLS client and needs only the CA:
```bash
bash scripts/make_tls_certs.sh data/tls_lan 192.168.2.100 192.168.2.1
ssh pi@192.168.2.2 mkdir -p a2a/data/tls_lan
scp data/tls_lan/ca.pem pi@192.168.2.2:a2a/data/tls_lan/
```
This replaces the earlier `data/tls_lan` (made for the Pi's address). `data/` is gitignored.

## 6. Start the services

On the Mac, in a `tmux` window (the cloud agents for all three arms and the ticket services):
```bash
venv/bin/python scripts/serve_cloud.py --bases 8100,8200,8300 --tls-dir data/tls_lan \
    --cloud-host 192.168.2.100 --ticket-host 192.168.2.1
```
On the Pi, in a `tmux` window (one edge agent per arm; padding comes with each task):
```bash
cd ~/a2a
venv/bin/python scripts/serve_edge.py --bases 8100,8200,8300 --tls-dir data/tls_lan \
    --cloud-host 192.168.2.100 --ticket-host 192.168.2.1 --model llama3.2:1b --num-predict 128
```
Allow incoming connections for Python if the macOS firewall asks. Check from the Mac: the nine TLS
endpoints answer, and each edge agent fetches the cloud agents' cards and loads its model:
```bash
for b in 8100 8200 8300; do
  for e in 192.168.2.100:$((b+1)) 192.168.2.100:$((b+2)); do
    curl -s --cacert data/tls_lan/ca.pem -o /dev/null -w "$e %{http_code}\n" https://$e/.well-known/agent-card.json; done
  curl -s --cacert data/tls_lan/ca.pem -w " 192.168.2.1:$((b+5))\n" https://192.168.2.1:$((b+5))/health
  curl -s -X POST http://192.168.2.2:$((b+9))/prepare | head -c 160; echo
done                                         # 200s, {"ok":true,...}, and three edge configurations
```

## 7. Emulated WAN

On the Mac, measure the round trip to the nearest public cloud region (TCP connect time, 30 tries)
and write the netem settings and the exact `tc` commands:
```bash
venv/bin/python scripts/measure_cloud_rtt.py            # https://ec2.us-west-1.amazonaws.com
ssh pi@192.168.2.2 mkdir -p a2a/data/results
scp data/results/c2_wan_emulation.json pi@192.168.2.2:a2a/data/results/
```
It writes `data/results/c2_wan_emulation.json` (raw times, median, IQR, delay = median,
jitter = half the IQR, the `tc` commands; the paper cites it). On the Pi:
```bash
sudo bash scripts/wan_emulation.sh on data/results/c2_wan_emulation.json
bash scripts/wan_emulation.sh show                   # prio bands 4, netem on 1:4, u32 filter dst 192.168.2.100
```
The commands put a 4-band `prio` qdisc on `eth0` (the default priomap never uses band 4, so no
other traffic is delayed), `netem delay <median>ms <jitter>ms distribution normal` on band 4 with
a `pfifo` child (netem with jitter would otherwise reorder packets, adding retransmissions to the
captures), and a `u32` filter that sends only traffic to `192.168.2.100` there. Turn it off with
`sudo bash scripts/wan_emulation.sh off`. Then, from the Mac:
```bash
venv/bin/python scripts/check_wan_emulation.py --json data/raw_c2_pilot/wan_check.json
```
Each edge agent measures its TCP connect time to the cloud alias 30 times; the median must be
within ±20% of the delay, or the check fails. The collector repeats this (10 tries) at the start of
every round with `--wan-target` and stops if the emulation is off.

## 8. Capture on the Mac

The collector runs tcpdump on `--interface bridge100`, limited to the Pi's address and the arm's
cloud and ticket ports, for example
`tcp and (port 8101 or port 8102 or port 8105) and (host 192.168.2.2)`. The trigger port (B+9) is
not in the filter. Before a run: charger in, `caffeinate`, and capture access for your user:
```bash
sudo chmod o+r /dev/bpf*        # revoke afterwards: sudo chmod o-r /dev/bpf*
```

## 9. Smoke test (Mac only) and the 1-hour pilot

C2 uses seed offset 30000 and the IoT workflows (`docs/PROMPT_REGISTRY.md`): one condition per
task type, 150 tasks each per arm. First a smoke test on the Mac alone, everything on loopback
(the loopback certificates in `data/tls`; the edge agent uses the Mac's `llama3.2:3b`; no WAN
emulation), 3 tasks per task type and arm:
```bash
venv/bin/python scripts/serve_cloud.py --bases 8100,8200,8300 --tls-dir data/tls --cloud-host 127.0.0.1 --ticket-host 127.0.0.1 &
venv/bin/python scripts/serve_edge.py --bases 8100,8200,8300 --tls-dir data/tls --cloud-host 127.0.0.1 \
    --ticket-host 127.0.0.1 --bind 127.0.0.1 --model llama3.2:3b &
venv/bin/python scripts/collect_session.py --placement edge-cloud --collection-id C2-smoke --n 3 --rounds 1 \
    --seed-offset 30000 --workflows iot --tls-dir data/tls --edge-host 127.0.0.1 --cloud-host 127.0.0.1 \
    --ticket-host 127.0.0.1 \
    --arm name=lan,ports=8100,out=/tmp/c2s/lan --arm name=lan_pad,ports=8200,pad=1024/2048/4096/8192/16384/32768,out=/tmp/c2s/lan_pad \
    --arm name=lan_padmax,ports=8300,pad=8192/16384,pad_expect=8192,out=/tmp/c2s/lan_padmax
venv/bin/python scripts/check_lan_capture.py /tmp/c2s/lan /tmp/c2s/lan_pad /tmp/c2s/lan_padmax
venv/bin/python scripts/check_session_design.py /tmp/c2s/lan /tmp/c2s/lan_pad /tmp/c2s/lan_padmax
kill %1 %2
```
Then the pilot on the LAN, one hour, all three arms:
```bash
caffeinate -dimsu venv/bin/python scripts/collect_session.py --placement edge-cloud --collection-id C2-pilot \
    --n 150 --rounds 5 --seed-offset 30000 --workflows iot --deadline-hours 1 \
    --interface bridge100 --tls-dir data/tls_lan --wan-target data/results/c2_wan_emulation.json \
    --arm name=lan,ports=8100,out=data/raw_c2_pilot \
    --arm name=lan_pad,ports=8200,pad=1024/2048/4096/8192/16384/32768,out=data/raw_c2_pad_pilot \
    --arm name=lan_padmax,ports=8300,pad=8192/16384,pad_expect=8192,out=data/raw_c2_padmax_pilot
```
The last line it prints is the pace: seconds per trace, and the hours 1,800 traces (three arms)
and 1,200 traces (two arms) would take. **If 1,800 traces do not fit in about 30 hours, C2 runs
`lan` and `lan_padmax` only; record why** (`session_meta.json` keeps the pace).

Checks on the raw (not yet stripped) pilot captures:
```bash
P="data/raw_c2_pilot data/raw_c2_pad_pilot data/raw_c2_padmax_pilot"
venv/bin/python scripts/check_lan_capture.py $P --json data/raw_c2_pilot/lan_check.json
for d in $P; do
  venv/bin/python scripts/check_tls_capture.py $d --expect tls --json $d/tls_check.json
  venv/bin/python scripts/check_stream_integrity.py $d --json $d/stream_integrity.json
done
venv/bin/python scripts/check_session_design.py $P --json data/raw_c2_pilot/design_check.json
venv/bin/python scripts/check_wan_emulation.py --json data/raw_c2_pilot/wan_check.json
bash baselines/run_tls_scanners.sh                   # sslyze and testssl.sh on the nine TLS endpoints
```

### Pass criteria

| Check | Pass when |
|---|---|
| Every call captured, nothing extra | `check_lan_capture.py` PASS: every escalated task shows a request after the TLS handshake and response data on the cloud agent the routing rule names and no request to the other; every task shows exactly one ticket POST; no `alert_triage` task opens a connection to the cloud alias; the edge agent's report agrees with the rule |
| TLS on | `check_tls_capture.py --expect tls`: every trace carries ClientHellos and application-data records, no cleartext HTTP; the scanners report TLS 1.3 on all nine endpoints |
| Streams complete | `check_stream_integrity.py`: per escalated task type, share of cut cloud replies ≤ 5% and median largest reply far above the truncation signature of 7–10 packets |
| WAN emulation | `check_wan_emulation.py`: the edge-to-cloud connect time within ±20% of the measured delay, for all three edge agents; no round stopped by `--wan-target` |
| Collection healthy | `session_meta.json`: `workflows` are the four IoT ones; every task type has traces in every arm; failed attempts ≤ 1% of traces; `throttled_traces` (traces taken while the Pi was throttled) reported; the pace line decides `lan_pad` |
| No fixed predecessor | `check_session_design.py` [a], as before |
| Leftover connections | [b]: none may carry data beyond the close |
| Padding on the wire | [c], `lan_pad` and `lan_padmax`, on the edge-to-cloud requests only (the sidecar's `padded_endpoints`): message − bucket constant in at least 95% of traces; `lan_padmax` needs every cloud request in the 8192 bucket (100%) |
| Null label | [d], as before |

Keep `pi-freeze.txt`, the Pi's Python version and model, `data/results/c2_wan_emulation.json` and
the pilot's JSON files.

## 10. C2

If the pilot passes (arms as the pace decided; nights of a few hours each):
```bash
caffeinate -dimsu venv/bin/python scripts/collect_session.py --placement edge-cloud --collection-id C2 \
    --n 150 --rounds 5 --seed-offset 30000 --workflows iot --deadline-hours 8 \
    --interface bridge100 --tls-dir data/tls_lan --wan-target data/results/c2_wan_emulation.json \
    --arm name=lan,ports=8100,out=data/raw_c2 \
    --arm name=lan_pad,ports=8200,pad=1024/2048/4096/8192/16384/32768,out=data/raw_c2_pad \
    --arm name=lan_padmax,ports=8300,pad=8192/16384,pad_expect=8192,out=data/raw_c2_padmax
# following nights: the same command with --resume added
```
600 tasks per arm. Between nights leave the services and the WAN emulation running, or restart them
(sections 2, 6 and 7) and rerun section 6's check. Run the section 9 checks on the C2 folders
afterwards. The audit, per arm and view:
```bash
for arm in c2 c2_pad c2_padmax; do for v in v1 v2; do
  venv/bin/python -m a2a_leakcheck run data/raw_$arm --strip --vantage $v \
      --attributes task_type,escalated,cloud_role,audit_null --out data/results/leakcheck/${arm}_$v --html
done; done
```

### If a check fails

| Symptom | Likely cause |
|---|---|
| Every trace fails at once | capture access (`/dev/bpf*`), wrong `--interface`, or the edge agents are not running (`curl http://192.168.2.2:8109/health`) |
| `check_lan_capture.py`: no complete call to the cloud agent | `serve_cloud.py` is down, the alias is gone (section 2), or the certificate lacks `192.168.2.100` (section 5) |
| An `alert_triage` task reaches the cloud | the Pi runs an older `agents/edge.py`: rsync the code again (section 4) |
| Two ticket connections in one trace | a retry inside the edge agent, or a previous task still running: check the Pi's log |
| `--wan-target` stops the session, or `check_wan_emulation.py` fails | the emulation is off or on the wrong interface: `bash scripts/wan_emulation.sh show` on the Pi |
| [c] fails: overhead not constant | `pad=` missing from a padded arm |
| [c] fails: `lan_padmax` messages outside 8192 | a cloud request above 8192 B (the largest is printed): raise the bucket (`pad=16384/32768,pad_expect=16384`) |
| Traces taken while throttled | the Pi is too hot or under-powered: a fan or heatsink, the official 27 W supply; the traces are flagged in the sidecars (`pi_throttled`) |
| Cut streams | Ollama on the Mac overloaded or restarted mid-trace |
