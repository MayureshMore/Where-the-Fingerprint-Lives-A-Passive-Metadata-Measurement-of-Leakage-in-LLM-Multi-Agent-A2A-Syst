# Home Wi-Fi setup: edge agent on a Raspberry Pi, emulated cloud on the Mac (collection C2)

**Use case:** an edge AI assistant for building and factory operations. The assistant's agent runs
**on the building's IoT gateway** (the Raspberry Pi). It answers alarm triage itself with a small
local model, sends sensor analysis and fault diagnosis to a cloud agent `diagnostics` and procedure
questions to a cloud agent `knowledge`, and files every result with the building's maintenance-ticket
service. The Mac stands in for both the cloud (on a separate address, the cloud alias) and the
building server (its own address). The Pi and the Mac are on the home Wi-Fi; the Mac captures the
Pi's flows to its two addresses, the same packets a router or access point between them forwards.

**Addresses and interfaces** live in one file, `configs/c2_network.conf`, which every C2 script
reads (an environment variable of the same name overrides a value; a command-line flag overrides
both). In a shell, `. configs/c2_network.conf` sets them for the commands below.

| Name | What | Value |
|---|---|---|
| `C2_IFACE` | the Mac's Wi-Fi interface: capture and WAN emulation | `en0` |
| `C2_MAC` | the Mac's own address: the ticket service (the building server) | `10.0.0.228` |
| `C2_PI` | the Pi's reserved address on the Wi-Fi | set it (section 1) |
| `C2_CLOUD` | the cloud alias on the Mac: an unused address outside the router's DHCP range | set it (section 1) |
| `C2_PI_IFACE` | the Pi's Wi-Fi interface (only for the WAN fallback on the Pi) | `wlan0` |

The C2 scripts stop with a message while `C2_PI` or `C2_CLOUD` is empty; they never guess an
address on the home network.

| Role | Host | Address | Model |
|---|---|---|---|
| Edge agent (A2A client) + local triage (`scripts/serve_edge.py`) | Raspberry Pi 5, on the Wi-Fi | `C2_PI` | Ollama on the Pi (localhost), `llama3.2:1b`, `num_predict 128` |
| Cloud agents `diagnostics`, `knowledge` (`scripts/serve_cloud.py`) | Mac, cloud alias | `C2_CLOUD` (alias on `C2_IFACE`) | Ollama on the Mac (localhost), `llama3.2:3b`, `num_predict 256` |
| Ticket service, HTTPS `POST /tickets` (`scripts/serve_cloud.py`) | Mac, building server | `C2_MAC` | none |
| Collector, capture (`tcpdump -p`, the Pi's address only) and WAN emulation | Mac | `C2_IFACE` | |

**Routing on the edge agent is a fixed rule on the task type** (`agents/edge.py`), as a building
management system tags its requests: `alert_triage` is answered on the gateway and never leaves the
building; `sensor_analysis` and `fault_diagnosis` go to `diagnostics`; `procedure_lookup` goes to
`knowledge`. After every task the edge agent POSTs its result to the ticket service. Every link is
TLS 1.3. No LLM router (it would cost Pi time and make routing a random variable).

**Ports, per arm base B** (`lan` 8100, `lan_pad` 8200, `lan_padmax` 8300): `diagnostics` B+1 and
`knowledge` B+2 on the cloud alias; tickets B+5 on the Mac's address; the edge agent's task trigger
B+9 on the Pi. Each arm has its own ports, so one arm's closing connections never land in another
arm's captures.

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
port (B+9, plain HTTP; the Pi's firewall accepts it only from the Mac). The trigger port is not in
the capture filter, so no capture, and hence neither observer view, contains it; in the paper the
trigger stands for the sensors and building systems wired to the gateway. Why not an injector on
the Pi reading a pushed schedule: every capture would then have to be cut out of one continuous
capture by the Pi's clock, and the session machinery (balanced rounds, arms alternating on the same
prompt, a retry per failed trace, `--resume`, sidecars) would have to be rebuilt on the Pi. With
the trigger, each capture starts before the task and stops after its last connection closes.

**Observer views** (one capture, two vantage points; `a2a_leakcheck --vantage`):

| View | Who | Sees |
|---|---|---|
| `v1` building network | a compromised router or access point, a mirrored switch port | every flow of the Pi to the cloud alias and to the ticket service |
| `v2` upstream | the ISP, a cellular backhaul, the cloud's edge | only the flows between the Pi and the cloud alias |

At `v2` every `alert_triage` task shows no flow at all. That is an observation, not a missing
trace: leakcheck keeps such traces with all-zero features. Attributes: `task_type` (4 classes),
`escalated` (cloud call or not; at `v2` padding cannot hide whether a call happened),
`cloud_role` (`diagnostics` or `knowledge`, escalated tasks only), and the input size (the
first-request estimator). The architecture is fixed, so C2 has no topology attribute.

**Emulated WAN.** Traffic between the Pi and the cloud alias is delayed on the Mac with pf
dummynet on `C2_IFACE`, half of a round trip measured to the nearest public cloud region each way
(section 8), and nothing else is: the ticket service and the Pi's internet traffic are not delayed.
The capture on `C2_IFACE` sits where a building router would: the Pi's packets to the cloud are
captured before the delay and the cloud's replies after it, so the round trip shows up between a
request and its response. dummynet has no jitter: the delay is constant, and the measured spread
is not reproduced (`data/results/c2_wan_emulation.json` records this). On top of the delay the Pi
sees the Wi-Fi round trip to the Mac (the base round trip, measured and recorded in section 8). The
fallback, netem on the Pi (`scripts/wan_emulation_pi.sh`), is used only if the Mac emulation
cannot run.

**Ethics and the home network:** other people's devices share this Wi-Fi. The capture never runs in
promiscuous mode (`tcpdump -p`) and its filter names the Pi's address and the arm's ports, so no
other device's traffic is ever written. The Mac's Ollama stays on localhost; the Pi's trigger ports
accept only the Mac (section 6). While `serve_cloud.py` runs, its TLS services listen on the Mac's
two Wi-Fi addresses, where other devices on the network could reach them: stop it after each
session.

## 0. You need

- The Mac with this repo, its `venv`, and Ollama with `llama3.2:3b`.
- A Raspberry Pi 5 (4 GB or more) running Raspberry Pi OS 64-bit (Bookworm), with SSH on.
- The home Wi-Fi, and access to the router's admin page (an address reservation for the Pi, and
  the DHCP range).

## 1. The network

1. **The Mac.** Its Wi-Fi interface and address (they go in `C2_IFACE` and `C2_MAC`):
   ```bash
   route -n get default | grep interface        # interface: en0
   ipconfig getifaddr en0                       # 10.0.0.228
   ```
   The Mac's address must stay the same for the whole collection: reserve it on the router too.
   If Internet Sharing is still on from the earlier cable setup, turn it off.
2. **The Pi on the Wi-Fi.** Join the Wi-Fi (Raspberry Pi Imager's Wi-Fi settings, or
   `sudo nmcli dev wifi connect "<SSID>" password "<password>"`), unplug any Ethernet cable so all
   its traffic uses Wi-Fi, and reserve its address on the router (DHCP reservation for the Pi's
   Wi-Fi MAC address, `ip link show wlan0`). The Wi-Fi connection's name is in `nmcli con show`
   (the SSID, or `preconfigured` when Raspberry Pi Imager set it up). Renew the lease
   (`sudo nmcli con up "<connection>"`) and check: `ip -4 addr show wlan0`. That address is `C2_PI`.
3. **The cloud alias.** An address in the same subnet that the router never hands out: outside
   its DHCP range and not reserved for anything. Check that nothing answers on it:
   ```bash
   ping -c 2 10.0.0.240; arp -an | grep '10.0.0.240'       # for example: no reply, no entry
   ```
   That address is `C2_CLOUD`.
4. Fill in `configs/c2_network.conf` (`C2_PI`, `C2_CLOUD`; check `C2_IFACE` and `C2_MAC`).
5. **Wi-Fi power saving off on the Pi** (it adds tens to hundreds of milliseconds to some packets):
   ```bash
   sudo iw dev wlan0 set power_save off                                # now
   sudo nmcli con mod "<connection>" 802-11-wireless.powersave 2       # 2 = disable, after reboots too
   iw dev wlan0 get power_save                                          # Power save: off
   ```

## 2. The cloud alias on the Mac

The cloud agents get their own address, so the Pi's flows to "the cloud" and to the building server
are told apart by address, as on a real network:
```bash
. configs/c2_network.conf
sudo ifconfig "$C2_IFACE" alias "$C2_CLOUD" netmask 255.255.255.255
ifconfig "$C2_IFACE" | grep 'inet '               # C2_MAC and C2_CLOUD
```
From the Pi: `ping -c 3 <C2_CLOUD>`. The alias goes away when the Mac rejoins the Wi-Fi or
restarts; add it again before starting the cloud services. Remove it with
`sudo ifconfig "$C2_IFACE" -alias "$C2_CLOUD"`.

## 3. Ollama, on localhost on both machines

- **Mac:** the Ollama app, as usual. It must listen on localhost only (the cloud agents call it
  locally); never set `OLLAMA_HOST` to a network address on the home Wi-Fi:
  ```bash
  lsof -nP -iTCP:11434 -sTCP:LISTEN               # ollama 127.0.0.1:11434
  ollama list                                     # llama3.2:3b
  ```
- **Pi:** install Ollama and the edge model; the installer's service listens on localhost:
  ```bash
  curl -fsSL https://ollama.com/install.sh | sh
  ollama pull llama3.2:1b
  ss -ltn | grep 11434                            # 127.0.0.1:11434
  time ollama run llama3.2:1b "Triage: ALARM A512 HIGH: chiller CH-1 high temperature. Priority, team, first action."
  ```
  If `qwen2.5:1.5b` answers faster on your Pi (`ollama pull qwen2.5:1.5b`, same `time` line), use
  it and pass `--model qwen2.5:1.5b` in section 7. Record the choice.

## 4. Code on the Pi

On the Pi:
```bash
sudo apt install -y python3-venv rsync tmux iw ufw
mkdir -p ~/a2a
```
From the Mac, in the repo (this copies `configs/c2_network.conf` too; copy it again whenever it
changes):
```bash
. configs/c2_network.conf
rsync -a --exclude data --exclude venv --exclude .git --exclude dist ./ "pi@$C2_PI:a2a/"
```
On the Pi, install what the edge agent needs, at the Mac's versions (requirements-lock.txt):
```bash
cd ~/a2a && python3 -m venv venv
venv/bin/pip install "a2a-sdk[http-server]==0.3.26" "sse-starlette==3.6.0" "uvicorn[standard]==0.49.0" \
    "httpx==0.28.1" "httpx-sse==0.4.3" "pydantic==2.13.4" "starlette==1.2.1"
venv/bin/python --version; venv/bin/pip freeze > ~/pi-freeze.txt    # keep both with the collection
```

## 5. TLS certificates

One certificate for the Mac's two TLS services, valid for the cloud alias and the Mac's own
address; the Pi is only a TLS client and needs only the CA:
```bash
. configs/c2_network.conf
bash scripts/make_tls_certs.sh data/tls_lan "$C2_CLOUD" "$C2_MAC"
ssh "pi@$C2_PI" mkdir -p a2a/data/tls_lan
scp data/tls_lan/ca.pem "pi@$C2_PI:a2a/data/tls_lan/"
```
This replaces the earlier `data/tls_lan`, CA included: copy `ca.pem` to the Pi again. Make the
certificate again whenever `C2_CLOUD` or `C2_MAC` changes. `data/` is gitignored.

## 6. Firewall on the Pi

The edge agents' trigger ports accept tasks; on a shared Wi-Fi only the Mac may reach them. On the
Pi (allow SSH from the Mac **before** enabling, or the SSH session is cut):
```bash
cd ~/a2a && . configs/c2_network.conf
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from "$C2_MAC" to any port 22 proto tcp
sudo ufw allow from "$C2_MAC" to any port 8109,8209,8309 proto tcp
sudo ufw enable
sudo ufw status numbered
```
Replies to the Pi's own connections (to the cloud agents, the ticket service, the internet) are
allowed by ufw's connection tracking. From the Mac, `curl -s http://$C2_PI:8109/health` answers once
the edge agents run (section 7); from any other device it times out.

## 7. Start the services

On the Mac, in a `tmux` window (the cloud agents for all three arms and the ticket services, on
`C2_CLOUD` and `C2_MAC`):
```bash
venv/bin/python scripts/serve_cloud.py --bases 8100,8200,8300 --tls-dir data/tls_lan
```
On the Pi, in a `tmux` window (one edge agent per arm, triggers bound to `C2_PI`; padding comes with
each task):
```bash
cd ~/a2a
venv/bin/python scripts/serve_edge.py --bases 8100,8200,8300 --tls-dir data/tls_lan \
    --model llama3.2:1b --num-predict 128
```
Allow incoming connections for Python if the macOS firewall asks. Check from the Mac: the nine TLS
endpoints answer, and each edge agent fetches the cloud agents' cards and loads its model:
```bash
. configs/c2_network.conf
for b in 8100 8200 8300; do
  for e in "$C2_CLOUD:$((b+1))" "$C2_CLOUD:$((b+2))"; do
    curl -s --cacert data/tls_lan/ca.pem -o /dev/null -w "$e %{http_code}\n" "https://$e/.well-known/agent-card.json"; done
  curl -s --cacert data/tls_lan/ca.pem -w " $C2_MAC:$((b+5))\n" "https://$C2_MAC:$((b+5))/health"
  curl -s -X POST "http://$C2_PI:$((b+9))/prepare" | head -c 160; echo
done                                         # 200s, {"ok":true,...}, and three edge configurations
```

## 8. Emulated WAN

On the Mac, measure the round trip to the nearest public cloud region (TCP connect time, 30 tries):
```bash
venv/bin/python scripts/measure_cloud_rtt.py            # https://ec2.us-west-1.amazonaws.com
```
It writes `data/results/c2_wan_emulation.json` (the paper cites it): the raw times, the median and
IQR, the round trip the checks expect (`delay_ms`, twice the one-way delay), the Mac emulation
(`emulation`: half the median each way, no jitter, the interface and addresses, the exact commands)
and the Pi fallback (`fallback_pi_netem`). Rerun it whenever the network config changes. Check that
`/etc/pf.conf` evaluates Apple's dummynet anchors, then turn the emulation on:
```bash
grep dummynet-anchor /etc/pf.conf                     # dummynet-anchor "com.apple/*"
sudo bash scripts/wan_emulation.sh on                 # prints "main ruleset and NAT unchanged"
sudo bash scripts/wan_emulation.sh show
```
`on` refuses to run if the config's interface or addresses differ from those the JSON recorded. For
a 24 ms round trip it runs:
```bash
dnctl pipe 1 config delay 12 ; dnctl pipe 2 config delay 12
printf 'dummynet in quick on en0 proto tcp from <C2_PI> to <C2_CLOUD> pipe 1\ndummynet out quick on en0 proto tcp from <C2_CLOUD> to <C2_PI> pipe 2\n' \
    | pfctl -a com.apple/c2-wan -f -
pfctl -E                                              # the token is kept in /var/tmp/c2-wan; off releases it
```
The rules live in their own anchor under `com.apple/`, so the main ruleset and NAT rules are
untouched; `on` diffs both before and after. `sudo bash scripts/wan_emulation.sh off` flushes the
anchor, deletes the two pipes and releases the token. Then, with the services of section 7 running:
```bash
venv/bin/python scripts/check_wan_emulation.py --record --json data/raw_c2_pilot/wan_check.json
```
Each edge agent measures TCP connect times to the internet, to the Mac's own address and to the
cloud alias, and the probes are captured on `C2_IFACE`:
- (a) the Pi reaches `1.1.1.1:443`;
- (b) the delay added to the cloud alias, its connect time minus the base Wi-Fi round trip, is
  within ±20% of the round trip, and so is the SYN → SYN-ACK time seen at the capture;
- (c) the Mac's own address is not delayed: at the capture its SYN → SYN-ACK is under a fifth of
  the round trip, and from the Pi its connect time, the **base Wi-Fi round trip Pi ↔ Mac**, is under
  the round trip (delayed it would be the base plus the round trip; a base that high usually means
  power saving is still on, section 1). With power saving off, the Pi and the Mac both on the Wi-Fi
  measured a median of 12.3 ms (IQR 9.4–13.5, 40 pings, Nov 11); with it on, 65–863 ms.

`--record` writes the base Wi-Fi round trip (median, IQR and all connect times, pooled over the
three edge agents) into `data/results/c2_wan_emulation.json` as `base_wifi_rtt`. The collector
repeats (b) at the start of every round with `--wan-target` (the cloud alias minus the Mac's own
address, 10 tries each) and stops if the emulation is off.

**Fallback, only if the Mac emulation cannot run** (for example if (a) fails: turn it off first):
netem on the Pi's Wi-Fi egress to the cloud alias, delay = median, jitter = half the IQR, with a
4-band `prio` qdisc, a `pfifo` child under netem so that jitter does not reorder packets, and a
`u32` filter on the cloud alias:
```bash
ssh "pi@$C2_PI" mkdir -p a2a/data/results
scp data/results/c2_wan_emulation.json "pi@$C2_PI:a2a/data/results/"
# on the Pi:
sudo bash scripts/wan_emulation_pi.sh on data/results/c2_wan_emulation.json
# on the Mac:
venv/bin/python scripts/check_wan_emulation.py --fallback-pi --json data/raw_c2_pilot/wan_check.json
```
With the fallback the capture sits on the cloud side of the delay: the Pi's packets reach the
capture already delayed, so the round trip shows up after a response rather than between a
request and its response; record that the fallback was used.

## 9. Capture on the Mac

The collector runs tcpdump on `C2_IFACE` (`--interface` overrides) with `-p` (never promiscuous)
and `--immediate-mode`, filtered on the Pi's address and the arm's cloud and ticket ports, for
example `tcp and (port 8101 or port 8102 or port 8105) and (host <C2_PI>)`. No other device's
traffic is written, and the trigger port (B+9) is not in the filter. Without immediate mode macOS
hands packets over in batches, and a capture stopped right after a task loses the last ones (the
ticket post, a whole `alert_triage` task; in C1-style traces only the final 2–5 connection-close
packets). Before a run: charger in, `caffeinate`, and capture access for the admin group (your
user is in it; other local users are not given access):
```bash
sudo chgrp admin /dev/bpf* && sudo chmod g+r /dev/bpf*
# afterwards: sudo chmod g-r /dev/bpf* && sudo chgrp wheel /dev/bpf*
```
The permissions reset when the Mac restarts; set them again before each run.

## 10. Smoke test (Mac only) and the 1-hour pilot

C2 uses seed offset 30000 and the IoT workflows (`docs/PROMPT_REGISTRY.md`): one condition per
task type, 150 tasks each per arm. First a smoke test on the Mac alone, everything on loopback
(the loopback certificates in `data/tls`; the edge agent uses the Mac's `llama3.2:3b`; no WAN
emulation; the addresses and `--interface lo0` given explicitly, so the network config is not
used), 3 tasks per task type and arm:
```bash
venv/bin/python scripts/serve_cloud.py --bases 8100,8200,8300 --tls-dir data/tls --cloud-host 127.0.0.1 --ticket-host 127.0.0.1 &
venv/bin/python scripts/serve_edge.py --bases 8100,8200,8300 --tls-dir data/tls --cloud-host 127.0.0.1 \
    --ticket-host 127.0.0.1 --bind 127.0.0.1 --model llama3.2:3b &
venv/bin/python scripts/collect_session.py --placement edge-cloud --collection-id C2-smoke --n 3 --rounds 1 \
    --seed-offset 30000 --workflows iot --tls-dir data/tls --interface lo0 --edge-host 127.0.0.1 \
    --cloud-host 127.0.0.1 --ticket-host 127.0.0.1 \
    --arm name=lan,ports=8100,out=/tmp/c2s/lan --arm name=lan_pad,ports=8200,pad=1024/2048/4096/8192/16384/32768,out=/tmp/c2s/lan_pad \
    --arm name=lan_padmax,ports=8300,pad=8192/16384,pad_expect=8192,out=/tmp/c2s/lan_padmax
venv/bin/python scripts/check_lan_capture.py /tmp/c2s/lan /tmp/c2s/lan_pad /tmp/c2s/lan_padmax
venv/bin/python scripts/check_session_design.py /tmp/c2s/lan /tmp/c2s/lan_pad /tmp/c2s/lan_padmax
kill %1 %2
```
Then the pilot on the Wi-Fi, one hour, all three arms (addresses and interface from the config):
```bash
caffeinate -dimsu venv/bin/python scripts/collect_session.py --placement edge-cloud --collection-id C2-pilot \
    --n 150 --rounds 5 --seed-offset 30000 --workflows iot --deadline-hours 1 \
    --tls-dir data/tls_lan --wan-target data/results/c2_wan_emulation.json \
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
| WAN emulation | `wan_emulation.sh on`: main ruleset and NAT unchanged. `check_wan_emulation.py`, for all three edge agents: (a) `1.1.1.1:443` reachable; (b) the added delay (cloud minus base) and the SYN → SYN-ACK at the capture within ±20% of the round trip; (c) the Mac's own address undelayed at the capture, base Wi-Fi round trip under the round trip. Base round trip recorded. No round stopped by `--wan-target` |
| Collection healthy | `session_meta.json`: `workflows` are the four IoT ones; every task type has traces in every arm; failed attempts ≤ 1% of traces; `throttled_traces` (traces taken while the Pi was throttled) reported; the pace line decides `lan_pad` |
| No fixed predecessor | `check_session_design.py` [a], as before |
| Leftover connections | [b]: none may carry data beyond the close |
| Padding on the wire | [c], `lan_pad` and `lan_padmax`, on the edge-to-cloud requests only (the sidecar's `padded_endpoints`): message − bucket constant in at least 95% of traces; `lan_padmax` needs every cloud request in the 8192 bucket (100%) |
| Null label | [d], as before |

Keep `pi-freeze.txt`, the Pi's Python version and model, `configs/c2_network.conf`,
`data/results/c2_wan_emulation.json`, `sudo bash scripts/wan_emulation.sh show`, `sudo ufw status`,
`iw dev wlan0 get power_save`, and the pilot's JSON files.

## 11. C2

If the pilot passes (arms as the pace decided; nights of a few hours each):
```bash
caffeinate -dimsu venv/bin/python scripts/collect_session.py --placement edge-cloud --collection-id C2 \
    --n 150 --rounds 5 --seed-offset 30000 --workflows iot --deadline-hours 8 \
    --tls-dir data/tls_lan --wan-target data/results/c2_wan_emulation.json \
    --arm name=lan,ports=8100,out=data/raw_c2 \
    --arm name=lan_pad,ports=8200,pad=1024/2048/4096/8192/16384/32768,out=data/raw_c2_pad \
    --arm name=lan_padmax,ports=8300,pad=8192/16384,pad_expect=8192,out=data/raw_c2_padmax
# following nights: the same command with --resume added
```
600 tasks per arm. Between nights leave the services and the WAN emulation running, or restart them
(sections 2, 7 and 8) and rerun the checks of sections 7 and 8. The WAN rules and pipes do not
survive a restart of the Mac, and the alias goes when the Mac rejoins the Wi-Fi. Run the section 10
checks on the C2 folders afterwards. The audit, per arm and view:
```bash
for arm in c2 c2_pad c2_padmax; do for v in v1 v2; do
  venv/bin/python -m a2a_leakcheck run data/raw_$arm --strip --vantage $v \
      --attributes task_type,escalated,cloud_role,audit_null --out data/results/leakcheck/${arm}_$v --html
done; done
```

### If a check fails

| Symptom | Likely cause |
|---|---|
| A C2 script stops: `C2_PI` (or `C2_CLOUD`) is not set | fill in `configs/c2_network.conf` (section 1) |
| Every trace fails at once | capture access (`/dev/bpf*`, section 9), the wrong interface in `C2_IFACE`, or the edge agents are not running or blocked (`curl http://$C2_PI:8109/health`; `sudo ufw status` on the Pi) |
| `check_lan_capture.py`: no complete call to the cloud agent | `serve_cloud.py` is down, the alias is gone (section 2), or the certificate lacks `C2_CLOUD` (section 5) |
| An `alert_triage` task reaches the cloud | the Pi runs an older `agents/edge.py`: rsync the code again (section 4) |
| Two ticket connections in one trace | a retry inside the edge agent, or a previous task still running: check the Pi's log |
| `--wan-target` stops the session, or `check_wan_emulation.py` (b) fails | the emulation is off (a Mac restart clears it): `sudo bash scripts/wan_emulation.sh show`, then `on` |
| `wan_emulation.sh on` refuses: config differs from the measurement | `C2_IFACE`, `C2_PI` or `C2_CLOUD` changed since `measure_cloud_rtt.py`: rerun it |
| (c) fails from the Pi: the base Wi-Fi round trip is high | Wi-Fi power saving is on (`iw dev wlan0 get power_save`, section 1), or the Pi is far from the access point |
| `check_wan_emulation.py` (a) fails, or the Pi loses the internet | `sudo bash scripts/wan_emulation.sh off`, check `ping 1.1.1.1` on the Pi, and use the Pi fallback (section 8) |
| (b) passes in the probes but the capture's SYN → SYN-ACK is near zero | the delay is applied on the Pi (fallback) or before the capture point: check which emulation is on |
| (c) fails at the capture: the Mac's address is delayed | the anchor's rules match more than the cloud alias: `sudo bash scripts/wan_emulation.sh show` |
| [c] fails: overhead not constant | `pad=` missing from a padded arm |
| [c] fails: `lan_padmax` messages outside 8192 | a cloud request above 8192 B (the largest is printed): raise the bucket (`pad=16384/32768,pad_expect=16384`) |
| Traces taken while throttled | the Pi is too hot or under-powered: a fan or heatsink, the official 27 W supply; the traces are flagged in the sidecars (`pi_throttled`) |
| Cut streams | Ollama on the Mac overloaded or restarted mid-trace |
