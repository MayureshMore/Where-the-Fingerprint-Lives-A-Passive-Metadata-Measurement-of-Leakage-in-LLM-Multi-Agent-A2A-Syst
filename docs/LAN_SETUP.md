# LAN setup: Mac + Raspberry Pi over a direct Ethernet link (collection C2)

The specialist agents run on a Raspberry Pi; the orchestrator, Ollama, the collector and the
capture run on the Mac. The Pi reaches the network only through the Mac, so the Mac is the Pi's
gateway, and the capture sees what a compromised gateway would see (paper 2's threat model).

| | Mac (gateway) | Raspberry Pi |
|---|---|---|
| Runs | orchestrator (in the collector), Ollama, `collect_session.py`, tcpdump | executor, retriever, validator (`serve_agents.py`) |
| Address | `192.168.2.1` on `bridge100` | `192.168.2.2` on `eth0` |
| Ports | Ollama `11434` | topology *t* at `8100 + 10t`: executor `+1`, retriever `+2`, validator `+3` (8101–8123) |

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

On the Pi, in `tmux` so it survives the SSH session:
```bash
cd ~/a2a
venv/bin/python scripts/serve_agents.py --ports-base 8100 --tls-dir data/tls_lan \
    --ollama-url http://192.168.2.1:11434 --num-predict 256
```
This serves all three topologies at once (nine servers, 8101–8103, 8111–8113, 8121–8123), over
TLS, with Ollama on the Mac. Ctrl-C stops all nine. Check from the Mac:
```bash
for p in 8101 8102 8103 8111 8112 8113 8121 8122 8123; do
  curl -s --cacert data/tls_lan/ca.pem -o /dev/null -w "$p %{http_code}\n" https://192.168.2.2:$p/.well-known/agent-card.json
done                                        # nine lines ending in 200
```
Input padding is applied by whoever sends a request. The calls that cross the link come from the
Mac's orchestrator, so a padded arm sets `pad=` on the Mac's `--arm`. Giving the Pi
`--pad-buckets` as well also pads the forwarding inside the Pi, which no observer at the gateway
sees.

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
tcpdump -i bridge100 -nn 'tcp and portrange 8101-8123 and host 192.168.2.2'
```

## 7. One-hour pilot

C2 uses seed offset 20000 (registered in `docs/PROMPT_REGISTRY.md`). On the
Mac, in the repo:
```bash
caffeinate -dimsu venv/bin/python scripts/collect_session.py --collection-id C2-pilot \
    --n 50 --rounds 5 --seed-offset 20000 --deadline-hours 1 \
    --interface bridge100 --ollama-url http://192.168.2.1:11434 --tls-dir data/tls_lan \
    --arm name=lan,deployment=a,tls=on,host=192.168.2.2,ports=8100,out=data/raw_c2_pilot
```
The C2 design, stopped after an hour: round 1 (all 12 conditions, 10 traces each, interleaved)
completes in about 40 minutes. The collector does not start or restart the Pi's agents; if one
stops answering, the trace fails and the retry waits for it.

Then run the three checks on the raw (not yet stripped) captures:
```bash
venv/bin/python scripts/check_lan_capture.py data/raw_c2_pilot --json data/raw_c2_pilot/lan_check.json
venv/bin/python scripts/check_tls_capture.py data/raw_c2_pilot --expect tls --json data/raw_c2_pilot/tls_check.json
venv/bin/python scripts/check_stream_integrity.py data/raw_c2_pilot --json data/raw_c2_pilot/stream_integrity.json
```

### Pass criteria

The pilot passes only if all of these hold:

| Check | Pass when |
|---|---|
| Every cross-host call captured | `check_lan_capture.py` prints PASS: in every successful trace, each call the topology makes from the Mac (star 3, chain 1, mesh 2) shows a request after the TLS handshake and response data, and no other specialist port gets a request |
| TLS on | `check_tls_capture.py --expect tls` passes: every trace carries ClientHellos and TLS application-data records, and no cleartext HTTP |
| Streams complete | `check_stream_integrity.py`: share of cut replies ≤ 5% for every topology (the bar C1 passed), with median largest replies in C1's range (star 272, chain 44, mesh 78 packets) |
| Collection healthy | `session_meta.json`: round 1 complete for all 12 conditions; failed attempts ≤ 1% of traces |

Keep `pi-freeze.txt`, the Pi's Python version and the four JSON files with the pilot. If it
passes, collect C2 with the same command, a new collection id and output directory, and without
`--deadline-hours`.

### If a check fails

| Symptom | Likely cause |
|---|---|
| Missing calls in every trace | wrong `--interface`, or the Pi's address differs from `host=` |
| A specialist port gets unexpected requests | an agent from another topology answering on the wrong port: restart `serve_agents.py` with the same `--ports-base` as the arm |
| TLS check finds cleartext HTTP | the Pi was started without `--tls-dir`, or the arm has `tls=off` |
| Certificate errors when agents start | certificate made without the Pi's address: redo step 4 |
| Cut streams | the Pi or Ollama overloaded or restarted mid-trace: check the Pi's log and `top` |
| Agents time out on Ollama | Ollama not bound to `192.168.2.1`, or the firewall blocks it: redo step 2 |
