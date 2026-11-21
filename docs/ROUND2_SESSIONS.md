# Paper 2, round 2: sessions B1–B3 (Nov 21–22)

Three collections on C2's testbed ([LAN_SETUP.md](LAN_SETUP.md): the Pi's edge agents, the Mac's
cloud agents and ticket services, dummynet on the Mac, capture on `C2_IFACE`). Each one runs
after the round-2 analysis chain has finished, from a clean commit, with nothing else running on
the Mac. Every collection is started by hand. Ethics as in C2: `tcpdump -p`, filtered on the Pi and
the arm's ports; Ollama on localhost on both machines.

The Mac's commands are written for zsh. The Pi's address is written `${C2_PI}`, in braces, before
a colon: zsh reads `$C2_PI:a2a/` as `$C2_PI` with its `:a` modifier (absolute path), so an rsync to
it copies into a local directory instead of the Pi.

| Session | Date | Arms (port base) | Traces | Seed offset | Ollama on the Mac | Hours |
|---|---|---|---|---|---|---|
| B1 reply shaping | Nov 21 | `lan_padmax` (8300), `lan_shaped` (8400) | 500 + 500 | 31000 | `OLLAMA_NUM_PARALLEL` 1, context 128k, as in C2 | about 2.9 |
| B3 second day | Nov 22, morning | `lan` (8100) | 1,000 | 33000 | 1, context 128k, as in C2 | about 1.9 |
| B2 jitter and load | Nov 22, after B3 | `lan` (8100), `lan_jl` (8500) | 500 + 500 | 32000 | `OLLAMA_NUM_PARALLEL` 4, context 32k | about 2.5 |

The hours come from C2's pace (6.9 s per trace): a shaped escalated task takes C2's time with
its cloud call replaced by the 14.75 s release. For `lan_jl`, the cloud's answers are assumed
1.6 times slower under load, plus about 1.3 s per task to start and stop the load. The first
round's pace line settles it. Add about 20 minutes of setup per session.

Before each full session, a pilot on the real testbed: one short round per arm (`--n 5 --rounds 1`,
20 traces per arm), into `data/pilot2_c2b1/` (B1, second pilot) or `data/pilot_c2b2/`, never into the raw data folders,
with the session's checks run on it. The full session starts only if they pass. B2 runs after B3, so
B3 keeps C2's Ollama settings; B2's full session runs only if its pilot passes, and goes to paper 3
otherwise.

- **B1** `lan_shaped`: requests padded to 8 KB, as in `lan_padmax`. Every reply is released
  14 s after its request as 16 events of one size, 0.05 s apart, then an artifact of one size, on
  connections with TCP_NODELAY (the other arms keep uvicorn's default, Nagle on, as in C2). A
  reply over 2,048 JSON-encoded bytes is cut. In C2 none would have been: the largest reply is
  1,515 B and the longest cloud call 9.9 s (`data/results/b1_shape_calibration.json`).
- **B2** `lan_jl`: both directions jittered, normal with mean 4 ms and sd 1.8 ms, plus 2 ms of
  dummynet, so the mean one way stays 6 ms.
  - The request side is netem with a rate on the Pi.
  - The reply side is the cloud agents, per SSE event and in order.
  - Draws below 0 are clipped to 0.
  - During each `lan_jl` task, 2 concurrent generations load the Mac's Ollama.
  - The interleaved `lan` arm is the control.

  Details are in `data/results/b2_wan_jitter.json`.
- **B3**: C2's `lan` arm again, on another day, with new prompts from the same templates.
  `scripts/evaluate_cross_session.py` trains on C2's `lan` and tests on this session.

## 0. Before Nov 21 (once)

1. **Code and plans.** Commit Phase B. Then, from that clean commit, write the WAN plans and the
   shaping calibration, which are committed results (neither script writes over an existing file):
   ```bash
   venv/bin/python scripts/round2_wan_plan.py
   venv/bin/python scripts/b1_shape_calibration.py --out data/results/b1_shape_calibration
   ```
2. **Code to the Pi** (Mac, in the repo):
   ```bash
   . configs/c2_network.conf
   rsync -a --exclude data --exclude venv --exclude 'venv-*' --exclude .git --exclude dist ./ "$C2_PI_USER@${C2_PI}:a2a/"
   ssh "$C2_PI_USER@$C2_PI" mkdir -p a2a/data/results
   scp data/results/b2_wan_jitter.json "$C2_PI_USER@${C2_PI}:a2a/data/results/"
   ```
3. **Pi firewall:** the new arms' trigger ports, from the Mac only (on the Pi):
   ```bash
   sudo ufw allow from 10.0.0.228 to any port 8409,8509 proto tcp
   sudo ufw status numbered
   ```

## Every session: start and finish

**Mac, before:**
```bash
cd "<repo>"
git status --short
. configs/c2_network.conf
sudo ifconfig "$C2_IFACE" alias "$C2_CLOUD" netmask 255.255.255.255
sudo chgrp admin /dev/bpf* && sudo chmod g+r /dev/bpf*
grep -o "OLLAMA_NUM_PARALLEL:[^ ]*" ~/.ollama/logs/server.log | tail -1
grep -o "OLLAMA_CONTEXT_LENGTH:[^ ]*" ~/.ollama/logs/server.log | tail -1
```
`git status --short` must print nothing. The last two lines must print the session's values:
`OLLAMA_NUM_PARALLEL:1` and `OLLAMA_CONTEXT_LENGTH:131072` for B1 and B3, as in C2; `4` and `32768`
for B2. To change them, quit the Ollama app, run `launchctl setenv OLLAMA_NUM_PARALLEL 4` (B2) or
`launchctl unsetenv OLLAMA_NUM_PARALLEL` (B1, B3), reopen the app, set Settings, Context length
(32k for B2, 128k for B1 and B3), and check again. The context length is the app's own setting.

**Pi, before** (in `tmux`): `iw dev wlan0 get power_save` must say off; then the session's
`serve_edge.py` line, below.

**Mac, after:**
```bash
sudo bash scripts/wan_emulation.sh off
sudo chmod g-r /dev/bpf* && sudo chgrp wheel /dev/bpf*
```
Stop `serve_cloud.py`, `wan_watch.py` and the guard (Ctrl-C). On the Pi, stop `serve_edge.py`.
After B2, also run `sudo bash scripts/wan_emulation_pi.sh off` on the Pi.

## B1: reply shaping (Nov 21)

The pilot and the full run share the Pi's edge agents and the WAN; the cloud agents, `wan_watch.py`
and the guard are restarted between them with the full run's folders.

**Pi** (`tmux`):
```bash
cd ~/a2a
venv/bin/python scripts/serve_edge.py --bases 8300,8400 --tls-dir data/tls_lan --model llama3.2:1b --num-predict 128
```
**Mac**, window 2: the WAN (C2's, for these two bases), for the pilot and the full run:
```bash
mkdir -p data/pilot2_c2b1/padmax data/raw_c2b1_padmax
sudo C2_BASES=8300,8400 bash scripts/wan_emulation.sh on data/results/b1_wan.json
```

### B1 pilot

The first pilot (`data/pilot_c2b1`, Nov 21) passed every check but the release time. Every shaped
reply was 16,902 B on the wire and its events and artifact left on time (14.766 to 14.770 s after the
request), but its last 351 B (the completed event and the end of the chunked stream) left 12 ms after
the Pi's ACK of the artifact. uvicorn leaves Nagle's algorithm on, so the stream ended 14.787 to
14.886 s after the request, as the Wi-Fi's ACKs came. The shaping agents now set TCP_NODELAY and
their cards say `[tcp nodelay on]`; the collector refuses a shaped arm whose agents do not, and an
unshaped arm whose agents do (`lan_padmax` stays as in C2). The second pilot runs into
`data/pilot2_c2b1`; start the guard as soon as the collector has started.

**Mac**, window 1 (`tmux`): the cloud agents, logging into the pilot's folder:
```bash
venv/bin/python scripts/serve_cloud.py --bases 8300,8400 --shape 8400=2048/14/128/0.05/truncate \
    --reply-log data/pilot2_c2b1/replies --tls-dir data/tls_lan
```
**Mac**, window 2: the WAN check, then (window 3, root) the kernel's pipes:
```bash
C2_BASES=8300,8400 venv/bin/python scripts/check_wan_emulation.py --target data/results/b1_wan.json \
    --json data/pilot2_c2b1/padmax/wan_check_start.json
sudo venv/bin/python scripts/wan_watch.py --out data/pilot2_c2b1/padmax/wan_status.json --log data/pilot2_c2b1/padmax/wan_watch.jsonl
```
**Mac**, window 2: the pilot, about 8 minutes:
```bash
caffeinate -dimsu venv/bin/python scripts/collect_session.py --placement edge-cloud --collection-id C2B1-pilot2 \
    --n 5 --rounds 1 --seed-offset 31000 --workflows iot --tls-dir data/tls_lan \
    --wan-target data/results/b1_wan.json --reply-log data/pilot2_c2b1/replies \
    --arm name=lan_padmax,ports=8300,pad=8192/16384,pad_expect=8192,out=data/pilot2_c2b1/padmax \
    --arm name=lan_shaped,ports=8400,pad=8192/16384,pad_expect=8192,shape=2048/14/128/0.05/truncate,out=data/pilot2_c2b1/shaped
```
**Mac**, window 4, once it has started: the guard on the pilot's folders:
```bash
venv/bin/python scripts/c2_guard.py --collector-pid "$(pgrep -f 'Python scripts/collect_session.py')" \
    --target data/results/b1_wan.json --status data/pilot2_c2b1/padmax/wan_status.json --pi-overhead-ms 3.31 \
    --calibration "$(python3 -c 'import json; print(json.dumps(json.load(open("data/raw_c2/wan_guard.json"))["calibration"]))')" \
    --json data/pilot2_c2b1/padmax/wan_guard.json data/pilot2_c2b1/padmax data/pilot2_c2b1/shaped
```
The collector must end with `lan_shaped: 15 cloud replies logged, 0 cut, 0 past the deadline, 0
failed`. Then the WAN check again, and the checks below on `P=(data/pilot2_c2b1/padmax
data/pilot2_c2b1/shaped)`, the shaping check with `data/pilot2_c2b1/shaped --control
data/pilot2_c2b1/padmax`. `check_shaping.py` passes when every shaped reply has one size on the wire,
every release time is within 50 ms of 14.75 s plus the 12 ms round trip, and nothing was cut or
overran. Stop `serve_cloud.py`, `wan_watch.py` and the guard; the WAN stays on.

### B1 full run

**Mac**, window 1 (`tmux`): the cloud agents, which shape the 8400 arm and log every reply:
```bash
venv/bin/python scripts/serve_cloud.py --bases 8300,8400 --shape 8400=2048/14/128/0.05/truncate \
    --reply-log data/raw_c2b1_replies --tls-dir data/tls_lan
```
**Mac**, window 2: the WAN check:
```bash
C2_BASES=8300,8400 venv/bin/python scripts/check_wan_emulation.py --target data/results/b1_wan.json \
    --json data/raw_c2b1_padmax/wan_check_start.json
```
**Mac**, window 3 (`tmux`, root): the kernel's pipes, for the guard:
```bash
sudo venv/bin/python scripts/wan_watch.py --out data/raw_c2b1_padmax/wan_status.json --log data/raw_c2b1_padmax/wan_watch.jsonl
```
**Mac**, window 2: the collection:
```bash
caffeinate -dimsu venv/bin/python scripts/collect_session.py --placement edge-cloud --collection-id C2B1 \
    --n 125 --rounds 5 --seed-offset 31000 --workflows iot --tls-dir data/tls_lan \
    --wan-target data/results/b1_wan.json --reply-log data/raw_c2b1_replies \
    --arm name=lan_padmax,ports=8300,pad=8192/16384,pad_expect=8192,out=data/raw_c2b1_padmax \
    --arm name=lan_shaped,ports=8400,pad=8192/16384,pad_expect=8192,shape=2048/14/128/0.05/truncate,out=data/raw_c2b1_shaped
```
**Mac**, window 4 (`tmux`), once the collection has started: the guard, with C2's Pi-timer
calibration. The venv's Python runs as `…/Python.app/Contents/MacOS/Python`, so the pattern finds
the collector and not `caffeinate`:
```bash
venv/bin/python scripts/c2_guard.py --collector-pid "$(pgrep -f 'Python scripts/collect_session.py')" \
    --target data/results/b1_wan.json --status data/raw_c2b1_padmax/wan_status.json --pi-overhead-ms 3.31 \
    --calibration "$(python3 -c 'import json; print(json.dumps(json.load(open("data/raw_c2/wan_guard.json"))["calibration"]))')" \
    --json data/raw_c2b1_padmax/wan_guard.json data/raw_c2b1_padmax data/raw_c2b1_shaped
```
The collector's last lines must say `lan_shaped: 375 cloud replies logged, 0 cut, 0 past the
deadline, 0 failed`. Each sidecar of the shaped arm holds the cloud's record (`cloud_replies`).
If the collection stops, rerun the same command with `--resume`.

**Mac, after** (checks as in C2's pilot):
```bash
P=(data/raw_c2b1_padmax data/raw_c2b1_shaped)
venv/bin/python scripts/check_lan_capture.py "${P[@]}" --json data/raw_c2b1_padmax/lan_check.json
for d in "${P[@]}"; do
  venv/bin/python scripts/check_tls_capture.py $d --expect tls --json $d/tls_check.json
  venv/bin/python scripts/check_stream_integrity.py $d --json $d/stream_integrity.json
done
venv/bin/python scripts/check_session_design.py "${P[@]}" --json data/raw_c2b1_padmax/design_check.json
venv/bin/python scripts/check_shaping.py data/raw_c2b1_shaped --control data/raw_c2b1_padmax \
    --json data/raw_c2b1_shaped/shaping_check.json
C2_BASES=8300,8400 venv/bin/python scripts/check_wan_emulation.py --target data/results/b1_wan.json \
    --json data/raw_c2b1_padmax/wan_check_after.json
```

## B2: jitter and server load (Nov 22, after B3)

**Mac, first:** Ollama with parallel requests and a context that fits them, then the load check:
```bash
launchctl setenv OLLAMA_NUM_PARALLEL 4
```
Quit and reopen the Ollama app, set Settings, Context length to 32k, then:
```bash
grep -o "OLLAMA_NUM_PARALLEL:[^ ]*" ~/.ollama/logs/server.log | tail -1
grep -o "OLLAMA_CONTEXT_LENGTH:[^ ]*" ~/.ollama/logs/server.log | tail -1
venv/bin/python scripts/ollama_load.py --check
```
The `grep` lines must print `OLLAMA_NUM_PARALLEL:4` and `OLLAMA_CONTEXT_LENGTH:32768`. The check
must report `"ok": true`: the two generations overlap and the model is wholly in GPU memory. Ollama
keeps a cache of context length × parallel slots. At the app's 128k, 4 slots need 56 GB of cache for
llama3.2:3b: 60.6 GB in all, 17 of 29 layers on the CPU of the 36 GB Mac, which would slow both
arms. At 32k, 4 slots hold 16.7 GB, all on the GPU, as C2's 128k × 1 does. The prompts are far
shorter than 32k tokens. The collector refuses `load=` unless the check passes.

**Pi** (`tmux`): the request side's jitter, then the edge agents:
```bash
cd ~/a2a
sudo bash scripts/wan_emulation_pi.sh jitter data/results/b2_wan_jitter.json
venv/bin/python scripts/serve_edge.py --bases 8100,8500 --tls-dir data/tls_lan --model llama3.2:1b --num-predict 128
```
`jitter` prints the `prio` qdisc, `netem delay 4ms 1.8ms ... rate 1Gbit` on `1:4`, and two `u32`
filters (ports 8501 and 8502).

**Mac**, window 1 (`tmux`): the cloud agents, which jitter the 8500 arm's replies:
```bash
venv/bin/python scripts/serve_cloud.py --bases 8100,8500 --jitter 8500=4/1.8/1 \
    --reply-log data/raw_c2b2_replies --tls-dir data/tls_lan
```
**Mac**, window 2: the WAN (pipes 1 and 2 at 6 ms, 3 and 4 at 2 ms) and its check, per arm:
```bash
mkdir -p data/raw_c2b2_lan
sudo C2_BASES=8100,8500 bash scripts/wan_emulation.sh on data/results/b2_wan_jitter.json
C2_BASES=8100,8500 venv/bin/python scripts/check_wan_emulation.py --target data/results/b2_wan_jitter.json \
    --json data/raw_c2b2_lan/wan_check_start.json
```
For the 8500 edge, check (b) expects an 18.6 ms round trip and a 4 ms SYN → SYN-ACK at the capture.
The 8100 edge keeps C2's 22.6 ms and 12 ms.

**Mac**, window 3 (`tmux`, root):
```bash
sudo venv/bin/python scripts/wan_watch.py --out data/raw_c2b2_lan/wan_status.json --log data/raw_c2b2_lan/wan_watch.jsonl
```
**Mac**, window 2: the collection (the load runs only during `lan_jl` tasks):
```bash
caffeinate -dimsu venv/bin/python scripts/collect_session.py --placement edge-cloud --collection-id C2B2 \
    --n 125 --rounds 5 --seed-offset 32000 --workflows iot --tls-dir data/tls_lan \
    --wan-target data/results/b2_wan_jitter.json --reply-log data/raw_c2b2_replies \
    --arm name=lan,ports=8100,out=data/raw_c2b2_lan \
    --arm name=lan_jl,ports=8500,jitter=4/1.8,load=2,out=data/raw_c2b2_jl
```
**Mac**, window 4 (`tmux`): the guard, per arm:
```bash
venv/bin/python scripts/c2_guard.py --collector-pid "$(pgrep -f 'Python scripts/collect_session.py')" \
    --target data/results/b2_wan_jitter.json --status data/raw_c2b2_lan/wan_status.json --pi-overhead-ms 3.31 \
    --calibration "$(python3 -c 'import json; print(json.dumps(json.load(open("data/raw_c2/wan_guard.json"))["calibration"]))')" \
    --json data/raw_c2b2_lan/wan_guard.json data/raw_c2b2_lan data/raw_c2b2_jl
```

**After:**
1. **Mac:** the C2 checks, then reordering against the control:
   ```bash
   P=(data/raw_c2b2_lan data/raw_c2b2_jl)
   venv/bin/python scripts/check_lan_capture.py "${P[@]}" --json data/raw_c2b2_lan/lan_check.json
   for d in "${P[@]}"; do
     venv/bin/python scripts/check_tls_capture.py $d --expect tls --json $d/tls_check.json
     venv/bin/python scripts/check_stream_integrity.py $d --json $d/stream_integrity.json
   done
   venv/bin/python scripts/check_session_design.py "${P[@]}" --json data/raw_c2b2_lan/design_check.json
   venv/bin/python scripts/check_reorder.py data/raw_c2b2_jl --control data/raw_c2b2_lan --json data/raw_c2b2_jl/reorder_check.json
   C2_BASES=8100,8500 venv/bin/python scripts/check_wan_emulation.py --target data/results/b2_wan_jitter.json \
       --json data/raw_c2b2_lan/wan_check_after.json
   ```
2. **Pi:** `sudo bash scripts/wan_emulation_pi.sh off`.
3. **Mac:** quit Ollama, run `launchctl unsetenv OLLAMA_NUM_PARALLEL`, reopen Ollama and set
   Settings, Context length back to 128k.

`check_reorder.py` passes when the jitter arm's request side has no more reordering than the
control's plus 0.5 percentage points. The Wi-Fi reorders some packets on its own: in C2, 0.06% of
`lan`'s request segments.

## B3: a second day of `lan` (Nov 22, morning)

`OLLAMA_NUM_PARALLEL` must be 1 and the context length 128k, as in C2 and B1 (B3 runs before B2).

**Pi:**
```bash
cd ~/a2a
venv/bin/python scripts/serve_edge.py --bases 8100 --tls-dir data/tls_lan --model llama3.2:1b --num-predict 128
```
**Mac:** C2's WAN and services, unchanged:
```bash
venv/bin/python scripts/serve_cloud.py --bases 8100 --tls-dir data/tls_lan
mkdir -p data/raw_c2b3_lan
sudo bash scripts/wan_emulation.sh on
venv/bin/python scripts/check_wan_emulation.py --bases 8100 --json data/raw_c2b3_lan/wan_check_start.json
sudo venv/bin/python scripts/wan_watch.py --out data/raw_c2b3_lan/wan_status.json --log data/raw_c2b3_lan/wan_watch.jsonl
caffeinate -dimsu venv/bin/python scripts/collect_session.py --placement edge-cloud --collection-id C2B3 \
    --n 250 --rounds 5 --seed-offset 33000 --workflows iot --tls-dir data/tls_lan \
    --wan-target data/results/c2_wan_emulation.json --arm name=lan,ports=8100,out=data/raw_c2b3_lan
venv/bin/python scripts/c2_guard.py --collector-pid "$(pgrep -f 'Python scripts/collect_session.py')" \
    --status data/raw_c2b3_lan/wan_status.json --pi-overhead-ms 3.31 \
    --calibration "$(python3 -c 'import json; print(json.dumps(json.load(open("data/raw_c2/wan_guard.json"))["calibration"]))')" \
    --json data/raw_c2b3_lan/wan_guard.json data/raw_c2b3_lan
```
Run each line in its own window, as in B1: `serve_cloud.py` in window 1, `wan_watch.py` in
window 3 (root), the guard in window 4 once the collection has started.

**After:** the same checks as B1, on `data/raw_c2b3_lan`.

## Afterwards (me, from a clean commit)

The audits and the cross-session transfer. Each session writes its own results JSON with commit,
seed and data folders; nothing heavy runs beside them.
- **B1:** `a2a_leakcheck` per arm and view; `check_shaping.py --out data/results/b1_shaping_overhead`
  (per task type, bytes and seconds against `lan_padmax`).
- **B2:** the same, per arm and view.
- **B3:** `evaluate_cross_session.py --train` on C2's `lan` features, `--test` on B3's, at V1
  and V2.
