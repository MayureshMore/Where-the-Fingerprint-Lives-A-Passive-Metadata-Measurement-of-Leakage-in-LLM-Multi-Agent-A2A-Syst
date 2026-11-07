# LAN setup: Mac + Raspberry Pi over a direct Ethernet link (collection C2)

The specialist agents run on a Raspberry Pi; the orchestrator, Ollama, the collector and the
capture run on the Mac. The Pi reaches the network only through the Mac, so the Mac is the Pi's
gateway, and the capture sees what a compromised gateway would see (paper 2's threat model).

**Use case:** an edge AI assistant for building and factory operations. The coordinator
(orchestrator) runs on the site's IoT gateway, the specialists on an edge device. C2 uses the IoT
workflow set (`--workflows iot`, `docs/PROMPT_REGISTRY.md`), four synthetic task types with the same
design as paper 1's: sensor_analysis (a telemetry window as CSV) and fault_diagnosis (a device log
and config excerpt) have long task inputs; procedure_lookup (a maintenance question) and
alert_triage (an alarm or occupant request) short ones.

| | Mac (gateway) | Raspberry Pi |
|---|---|---|
| Runs | orchestrator (in the collector), Ollama, `collect_session.py`, tcpdump | executor, retriever, validator (`serve_agents.py`, one instance per arm) |
| Address | `192.168.2.1` on `bridge100` | `192.168.2.2` on `eth0` |
| Ports | Ollama `11434` | arm `lan`: topology *t* at `8100 + 10t` (8101–8123); arm `lan_pad`: `8200 + 10t` (8201–8223); arm `lan_padmax`: `8300 + 10t` (8301–8323); executor `+1`, retriever `+2`, validator `+3` |

C2 has three arms, collected in one session and alternating trace by trace on the same prompt:

| Arm | Ports | Input padding (Mac orchestrator) |
|---|---|---|
| `lan` | 8100 | none |
| `lan_pad` | 8200 | request bodies padded to 1024/2048/4096/8192/16384/32768 B (paper 1's pow2 buckets from 1 KB) |
| `lan_padmax` | 8300 | request bodies padded to 8192 B (16384 above it): every first request in one bucket (`pad_expect=8192`) |

The top bucket must exceed the largest first request, so that every padded first request lands in
a bucket rather than in a multiple of the top one. The first A2A message is the orchestrator's
sub-task plan plus the whole task input; C2's longest task input is 5.8 KB (fault_diagnosis), and
in the smoke test the first request was the task input plus 1.1–1.5 KB, so about 7.3 KB at most,
well under 32768 (C1's largest was 7821 B). The short task inputs put the first message near the
1024 bucket's edge: procedure_lookup about 0.8–0.9 KB (bucket 1024), alert_triage about 1.0–1.1 KB
(1024 or 2048, depending on the plan's length), as with the classic short workflows, so
`lan_pad` leaves the task input's size class visible. `lan_padmax` removes it: the largest first
message C2 can produce is about 7.8 KB (the longest fault_diagnosis input with a 1,600-character
sub-task plan, more than 256 tokens give), under 8192, so every first request lands in the 8192
bucket and check [c] fails if one does not. Each arm has its own ports so that one arm's closing
connections never land in another arm's captures.

The addresses are macOS Internet Sharing's defaults; check yours in step 1 and use them
everywhere below.

**What crosses the link:** the orchestrator's calls to the specialists (star: all three;
chain: executor; mesh: executor and retriever), and the specialists' calls to Ollama. Chain and
mesh forwarding *between* specialists stays inside the Pi and never reaches the link, so a
gateway observer does not see it. Write that down in the paper's setup. The capture keeps only
agent ports to and from the Pi; the Ollama calls (port 11434) cross the link but are filtered
out.

**Ethics:** the cable connects only your own two devices, and the capture filter is limited to
the Pi's address and the agent ports. Never point the capture at a shared network.

## 0. You need

- The Mac with this repo, its `venv`, Ollama with `llama3.2:3b`, and an Ethernet port or adapter.
- A Raspberry Pi 4 or 5 (4 GB or more) running Raspberry Pi OS 64-bit (Bookworm), with SSH on.
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
4. SSH to the Pi at that address and fix its address, so every run uses the same one:
   ```bash
   nmcli con show                              # the wired connection's name, e.g. "Wired connection 1"
   sudo nmcli con mod "Wired connection 1" ipv4.method manual \
       ipv4.addresses 192.168.2.2/24 ipv4.gateway 192.168.2.1 ipv4.dns 192.168.2.1
   sudo nmcli con up "Wired connection 1"
   ```
5. Check from the Pi: the Mac is its gateway and it reaches the internet through it.
   ```bash
   ip route | grep default                     # default via 192.168.2.1 dev eth0
   ping -c 3 192.168.2.1 && ping -c 3 1.1.1.1
   ```

## 2. Ollama on the Mac, reachable from the Pi only

Bind Ollama to the link address instead of all interfaces, so it is not exposed on Wi-Fi:

```bash
# quit the Ollama app first, then:
OLLAMA_HOST=192.168.2.1:11434 ollama serve      # leave running (or in tmux)
```

Allow incoming connections for Ollama if the macOS firewall asks. From then on every Mac-side
command passes `--ollama-url http://192.168.2.1:11434`. Check from the Pi:

```bash
curl -s http://192.168.2.1:11434/api/tags | head -c 200      # lists llama3.2:3b
```

## 3. Code on the Pi

On the Pi:
```bash
sudo apt install -y python3-venv rsync tmux
mkdir -p ~/a2a
```
From the Mac, in the repo:
```bash
rsync -a --exclude data --exclude venv --exclude .git --exclude dist ./ pi@192.168.2.2:a2a/
```
On the Pi, install only what the agents need, at the Mac's versions (requirements-lock.txt):
```bash
cd ~/a2a && python3 -m venv venv
venv/bin/pip install "a2a-sdk[http-server]==0.3.26" "sse-starlette==3.6.0" "uvicorn[standard]==0.49.0" \
    "httpx==0.28.1" "httpx-sse==0.4.3" "pydantic==2.13.4" "starlette==1.2.1"
venv/bin/python --version; venv/bin/pip freeze > ~/pi-freeze.txt    # keep both with the collection
```

## 4. TLS certificates valid for the Pi's address

On the Mac (a separate directory, so the loopback certificates stay as they were):
```bash
bash scripts/make_tls_certs.sh data/tls_lan 192.168.2.2
ssh pi@192.168.2.2 mkdir -p a2a/data/tls_lan
scp data/tls_lan/ca.pem data/tls_lan/agent.pem data/tls_lan/agent-key.pem pi@192.168.2.2:a2a/data/tls_lan/
```
The key goes only to the Pi, over the direct link; `data/` is gitignored on both machines.

## 5. Start the Pi's agents

One instance per arm. On the Pi, in three `tmux` windows so they survive the SSH session:
```bash
# window 1: arm lan
cd ~/a2a
venv/bin/python scripts/serve_agents.py --ports-base 8100 --tls-dir data/tls_lan \
    --ollama-url http://192.168.2.1:11434 --num-predict 256
```
```bash
# window 2: arm lan_pad (no --pad-buckets; see below)
cd ~/a2a
venv/bin/python scripts/serve_agents.py --ports-base 8200 --tls-dir data/tls_lan \
    --ollama-url http://192.168.2.1:11434 --num-predict 256
```
```bash
# window 3: arm lan_padmax (no --pad-buckets either)
cd ~/a2a
venv/bin/python scripts/serve_agents.py --ports-base 8300 --tls-dir data/tls_lan \
    --ollama-url http://192.168.2.1:11434 --num-predict 256
```
Each instance serves all three topologies at once (nine servers: `B+1`–`B+3`, `B+11`–`B+13`,
`B+21`–`B+23` for base `B`), over TLS, with Ollama on the Mac. Ctrl-C stops one instance's nine.
Check all 27 from the Mac:
```bash
for b in 8100 8200 8300; do for t in 0 10 20; do for r in 1 2 3; do p=$((b + t + r))
  curl -s --cacert data/tls_lan/ca.pem -o /dev/null -w "$p %{http_code}\n" https://192.168.2.2:$p/.well-known/agent-card.json
done; done; done                            # 27 lines ending in 200
```
Input padding is applied by whoever sends a request. The calls that cross the link come from the
Mac's orchestrator, so the padded arms set `pad=` on the Mac's `--arm`, and the Pi's 8200 and
8300 instances run **without** `--pad-buckets`. Padding on the Pi would only pad the forwarding
inside the Pi, which no observer at the gateway sees, and the arms would then differ in more than
the padding the paper evaluates.

## 6. Capture on the Mac

The collector runs tcpdump on `--interface bridge100` and limits each capture to the trace's
agent ports and the Pi's address, for example
`tcp and (port 8100 or port 8101 or port 8102 or port 8103) and (host 192.168.2.2)`.

Before a run: charger in, `caffeinate`, and capture access for your user:
```bash
sudo chmod o+r /dev/bpf*        # revoke afterwards: sudo chmod o-r /dev/bpf*
```
Quick look that the agent traffic is on `bridge100` (Ctrl-C after a few lines while a test
trace runs):
```bash
tcpdump -i bridge100 -nn 'tcp and portrange 8101-8323 and host 192.168.2.2'
```

## 7. Two-hour pilot

C2 uses seed offset 20000 and the IoT workflows (both registered in `docs/PROMPT_REGISTRY.md`).
Local smoke tests first, without the Pi (agents on loopback, TLS on, 3 traces per workflow, about
4 minutes each; the folders are discarded afterwards): the unpadded arm, and `lan_padmax`'s
padding, whose first requests must all land in the 8192 bucket:
```bash
venv/bin/python scripts/collect_session.py --collection-id C2-smoke --n 1 --rounds 1 --seed-offset 20000 \
    --workflows iot --arm name=smoke,deployment=a,tls=on,out=/tmp/c2_smoke
venv/bin/python scripts/collect_session.py --collection-id C2-smoke-padmax --n 1 --rounds 1 --seed-offset 20000 \
    --workflows iot --arm name=smoke_padmax,deployment=a,tls=on,pad=8192/16384,pad_expect=8192,out=/tmp/c2_smoke_padmax
for d in /tmp/c2_smoke /tmp/c2_smoke_padmax; do
  venv/bin/python scripts/check_tls_capture.py $d --expect tls
  venv/bin/python scripts/check_stream_integrity.py $d
done
venv/bin/python scripts/check_session_design.py /tmp/c2_smoke_padmax      # [c]: 100% in the 8192 bucket
```
Then the pilot, on the Mac, in the repo:
```bash
caffeinate -dimsu venv/bin/python scripts/collect_session.py --collection-id C2-pilot \
    --n 50 --rounds 5 --seed-offset 20000 --workflows iot --deadline-hours 2.5 \
    --interface bridge100 --ollama-url http://192.168.2.1:11434 --tls-dir data/tls_lan \
    --arm name=lan,deployment=a,tls=on,host=192.168.2.2,ports=8100,out=data/raw_c2_pilot \
    --arm name=lan_pad,deployment=a,tls=on,host=192.168.2.2,ports=8200,pad=1024/2048/4096/8192/16384/32768,out=data/raw_c2_pad_pilot \
    --arm name=lan_padmax,deployment=a,tls=on,host=192.168.2.2,ports=8300,pad=8192/16384,pad_expect=8192,out=data/raw_c2_padmax_pilot
```
The C2 design, stopped after two and a half hours: round 1 (all 12 conditions, 10 traces each,
interleaved, three arms: 360 traces) takes about 110 minutes at C1's pace of 18 s per trace,
longer if the Pi is slower; the pass criteria need round 1 complete, hence 2.5 hours rather than
2. The collector does not start or restart the Pi's agents; if one stops answering, the
trace fails and the retry waits for it. Every sidecar gets `prompt_group` and `audit_null` (a
label a–d drawn at random per prompt group with a fixed seed, for the audit's known-null test).

Then run the checks on the raw (not yet stripped) captures, the first three once per arm:
```bash
for d in data/raw_c2_pilot data/raw_c2_pad_pilot data/raw_c2_padmax_pilot; do
  venv/bin/python scripts/check_lan_capture.py $d --json $d/lan_check.json
  venv/bin/python scripts/check_tls_capture.py $d --expect tls --json $d/tls_check.json
  venv/bin/python scripts/check_stream_integrity.py $d --json $d/stream_integrity.json
done
venv/bin/python scripts/check_session_design.py data/raw_c2_pilot data/raw_c2_pad_pilot data/raw_c2_padmax_pilot \
    --json data/raw_c2_pilot/design_check.json
```

### Pass criteria

The pilot passes only if all of these hold:

| Check | Pass when |
|---|---|
| Every cross-host call captured | `check_lan_capture.py` prints PASS: in every successful trace, each call the topology makes from the Mac (star 3, chain 1, mesh 2) shows a request after the TLS handshake and response data, and no other specialist port gets a request |
| TLS on | `check_tls_capture.py --expect tls` passes: every trace carries ClientHellos and TLS application-data records, and no cleartext HTTP |
| Streams complete | `check_stream_integrity.py`: share of cut replies ≤ 5% for every topology (the bar C1 passed), with median largest replies far above the truncation signature of 7–10 packets. C1 (classic prompts): star 272, chain 44, mesh 78; the IoT smoke test on loopback: star 274, chain 45, mesh 48.5 (4 traces each), so IoT replies can differ from C1's |
| Collection healthy | `session_meta.json`: `workflows` are the four IoT ones; round 1 complete for all 12 conditions in all three arms; failed attempts ≤ 1% of traces |
| No fixed predecessor | `check_session_design.py` [a]: per arm and workflow, the workflow that ran last on the same ports. A share above 40% is flagged; it fails only if it is also unlikely under a random order (binomial test, Bonferroni), since one round gives about 30 traces per cell. The TLS control failed this (100%) |
| Leftover connections | [b]: connections opened before the capture, per trace; none may carry data beyond the close |
| Padding on the wire | [c], `lan_pad` and `lan_padmax`: first-request bytes − bucket (the HTTP header record and TLS overhead) is the same in at least 95% of traces (±32 B of the median, median 100–1000 B); `lan_padmax` also needs every first A2A message in the 8192 bucket (the share is printed; 100% to pass) |
| Null label | [d]: every sidecar has `prompt_group` and `audit_null`, and `audit_null` is constant within a prompt group |

Keep `pi-freeze.txt`, the Pi's Python version and the JSON files of all three arms with the pilot.
If it passes, collect C2 over three nights:
```bash
# night 1
caffeinate -dimsu venv/bin/python scripts/collect_session.py --collection-id C2 \
    --n 50 --rounds 5 --seed-offset 20000 --workflows iot --deadline-hours 3.5 \
    --interface bridge100 --ollama-url http://192.168.2.1:11434 --tls-dir data/tls_lan \
    --arm name=lan,deployment=a,tls=on,host=192.168.2.2,ports=8100,out=data/raw_c2 \
    --arm name=lan_pad,deployment=a,tls=on,host=192.168.2.2,ports=8200,pad=1024/2048/4096/8192/16384/32768,out=data/raw_c2_pad \
    --arm name=lan_padmax,deployment=a,tls=on,host=192.168.2.2,ports=8300,pad=8192/16384,pad_expect=8192,out=data/raw_c2_padmax
# nights 2 and 3: the same command with --resume added (it continues the round where night 1 stopped)
```
1800 traces (600 per arm), about 9 hours at 18 s per trace, so three nights of about 3 hours;
`--deadline-hours` stops starting new items, and `--resume` continues with the same order and
prompts. Leave the Pi's three instances running between nights, or restart them as in step 5 and
rerun the 27-port check. Run the same checks on `data/raw_c2`, `data/raw_c2_pad` and
`data/raw_c2_padmax` afterwards.

### If a check fails

| Symptom | Likely cause |
|---|---|
| Missing calls in every trace | wrong `--interface`, or the Pi's address differs from `host=` |
| Missing calls in one arm only | that arm's `serve_agents.py` instance is down or on another `--ports-base`: rerun the 27-port check |
| [a] fails | the item order is not shuffled per round (a fixed workflow order, as in the TLS control) |
| [c] fails: overhead not constant | `pad=` missing from a padded arm, or the top bucket is below a first request |
| [c] fails: `lan_padmax` messages outside 8192 | a first message above 8192 B (the largest is printed): a longer task input or sub-task plan than estimated; raise the bucket (e.g. `pad=16384/32768,pad_expect=16384`) and rerun the pilot |
| [d] fails | the collector predates `audit_null`: update the repo on the Mac |
| A specialist port gets unexpected requests | an agent from another topology answering on the wrong port: restart `serve_agents.py` with the same `--ports-base` as the arm |
| TLS check finds cleartext HTTP | the Pi was started without `--tls-dir`, or the arm has `tls=off` |
| Certificate errors when agents start | certificate made without the Pi's address: redo step 4 |
| Cut streams | the Pi or Ollama overloaded or restarted mid-trace: check the Pi's log and `top` |
| Agents time out on Ollama | Ollama not bound to `192.168.2.1`, or the firewall blocks it: redo step 2 |
