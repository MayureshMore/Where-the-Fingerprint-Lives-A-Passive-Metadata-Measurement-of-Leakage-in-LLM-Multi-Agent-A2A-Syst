# Paper 2, round 2: sessions B1, B3 and C2B1X (Nov 21–22); B2 for paper 3

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
| B1 reply shaping | Nov 21 (done) | `lan_padmax` (8300), `lan_shaped` (8400) | 500 + 500 | 31000 | `OLLAMA_NUM_PARALLEL` 1, context 128k, as in C2 | 2.9 measured, plus a 4.3 h pause |
| B3 second day | Nov 22, from 22:00 | `lan` (8100) | 1,000 | 33000 | 1, context 128k, as in C2 | about 1.9 |
| C2B1X more shaped traces | Nov 22 (done) | `lan_shaped` (8400) | 2,000 | 31000, from position 125 | 1, context 128k, as in B1 | 7.7 measured, plus a 4.0 h pause |
| B2 jitter and load (paper 3) | later | `lan` (8100), `lan_jl` (8500) | 500 + 500 | 32000 | `OLLAMA_NUM_PARALLEL` 4, context 32k | about 2.5 |

The hours come from C2's pace (6.9 s per trace): a shaped escalated task takes C2's time with
its cloud call replaced by the 14.75 s release. For `lan_jl`, the cloud's answers are assumed
1.6 times slower under load, plus about 1.3 s per task to start and stop the load. The first
round's pace line settles it. Add about 20 minutes of setup per session.

Before each full session, a pilot on the real testbed: one short round per arm (`--n 5 --rounds 1`,
20 traces per arm), into `data/pilot2_c2b1/` (B1, second pilot), `data/pilot_c2b3/` or `data/pilot_c2b2/`, never into the raw data folders,
with the session's checks run on it. The full session starts only if they pass. B2 moved to paper 3
(Nov 21); its section below stays for that collection. C2B1X ([below](#c2b1x-more-shaped-traces-for-sensor-vs-fault-nov-22-overnight))
adds shaped traces so that sensor vs fault can come out NO LEAK if the shaping removes the signal.

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

**Pi, before** (in a second `tmux` window, Ctrl-b c, never the one that runs `serve_edge.py`):
Wi-Fi power save on, then off, so that the off reaches the driver:
```bash
sudo iw dev wlan0 set power_save on
sudo iw dev wlan0 set power_save off
sudo dmesg | tail -n 3
```
The last line must say `brcmfmac: brcmf_cfg80211_set_power_mgmt: power save disabled`. A plain
`set power_save off` is not enough: cfg80211 skips a setting equal to the one it holds, and
`iw dev wlan0 get power_save` can say off while the chip dozes (C2B1X, Nov 22). A dozing chip shows
in the WAN probes to the cloud as connects near 100 ms (the beacon interval, 102.4 ms) between
normal ones: the cloud's SYN-ACK comes 12 ms after the SYN, by when the chip may sleep until the
next beacon, while the Mac's own address answers at once. Do the same before a resume. Then the
session's `serve_edge.py` line, below, in its own window.

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

The second pilot passed its checks (Nov 21, 13:56). Its closing WAN check
(`data/pilot2_c2b1/padmax/wan_check_after.json`, 15:42) has no values: every cloud and ticket port
refused, as `serve_cloud.py` had been stopped for the full run. The full run's opening check
passed a minute later.

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
If the collection stops, rerun the same command with `--resume`, after a new WAN check
(`--json …/wan_check_resume1.json`), and start the guard again with a new `--json`
(`wan_guard_resume1.json`): neither writes over an existing file.

### B1 record (Nov 21)

- Started 15:43 from f801a63a (clean). The collector did not record the commit then; it does now.
- At 17:28, at the start of round 3, the WAN probe for `lan_shaped` read 27.25 ms against the
  27.11 ms bound (22.6 ms + 20%), and the collector stopped before the round's first trace, with
  600 traces done and 0 failed. The evening Wi-Fi had slowed: the Pi's connect time to the Mac's
  own address (never delayed) rose from 9.4 ms in round 0 to 15.3 ms. The emulated part stayed at
  the dummynet's 12 ms, the pipes at 6 ms with 0 drops (`wan_watch.jsonl`), and the guard passed
  all 600 traces.
- A power check ran during the pause (`scripts/b1_power.py`, data/results/b1_power.json).
- At 21:45 the WAN check passed (`wan_check_resume1.json`: 24.2 and 24.8 ms end to end, 12.8 and
  13.2 ms at the capture). The collector resumed with round 3's probes at 21.5 ms; the guard wrote
  `wan_guard_resume1.json`. Rounds 3 and 4 ran with `scripts/b1_power.py` and its test untracked;
  the collection code was f801a63a's.
- 22:54: 500 + 500 traces, 0 failed; 375 shaped replies, 0 cut, 0 overrun, released 14.000 to
  14.006 s after the request by the cloud's clock. The guard has 13 checks (to 600 traces) and 21
  (to 1,000), all OK, none suspect.
- The closing WAN check (`wan_check_after.json`) passed for 8300 (23.3 ms end to end, 12.6 ms at
  the capture). The 8400 probes were refused because `serve_cloud.py` was stopped while the check
  was running; the capture still saw three 8400 handshakes at 12.8 ms. Run the closing check
  before stopping anything.
- The checks pass: capture, TLS, stream integrity (0% cut) and design (8192 bucket 375 of 375 per
  arm, 0 leftover connections). The shaping check also passes: every shaped reply is 16,902 B on the
  wire and the median release is 14.770 s (expected 14.762). 374 of the 375 releases lie within
  18 ms of the median (5th to 95th percentile 14.7666 to 14.7740 s). One round-3 trace left
  46.7 ms late; the spread of 52.3 ms is that trace.

**Mac, after** (checks as in C2's pilot). The closing WAN check (last line) runs first, while
`serve_cloud.py` and the Pi's `serve_edge.py` still run:
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

## C2B1X: more shaped traces for sensor vs fault (Nov 22, overnight)

At B1's 125 + 125, an audit of sensor_analysis vs fault_diagnosis with permuted labels comes out
NO LEAK in 8 of 20 draws and INCONCLUSIVE in 12 (`data/results/b1_power.json`). Permuted labels
carry no signal, so a perfect defence would look like this. At about 625 per class, 16 to 18 of
20 are predicted to come out NO LEAK. C2B1X adds 500 shaped traces per task type:

- `lan_shaped` alone, with B1's shaping, WAN plan (`b1_wan.json`, base 8400) and checks.
- All four task types in every round, interleaved as in B1.
- The pair verdict is within the shaped arm, so no control arm runs beside it. B1's `lan_padmax`
  (125 per type) and C2's arms show the unshaped leak.

The prompts continue B1's sequence (seed offset 31000) from position 125, and skip every prompt in
C2's and B1's sidecars and every repeat (`--prompt-start 125 --exclude-prompts …`):

| Task type | Positions | Skipped as used | Skipped as repeats |
|---|---|---|---|
| sensor_analysis, fault_diagnosis | 125–624 | 0 | 0 |
| procedure_lookup | 125–810 | 122 | 64 |
| alert_triage | 125–661 | 27 | 10 |

The collector logs these positions at the start. The audit pools B1's and C2B1X's shaped traces
(`scripts/b1_audits.py`, below), recording both collection ids.

About 7.8 h: 2,000 traces at B1's shaped pace (5.6 s for alert_triage, 15.35 s for an escalated
task, about 0.8 s between traces), in 20 rounds of 25 per task type, each opened by a WAN probe.
Ollama as in B1: `OLLAMA_NUM_PARALLEL` 1, context 128k. Start by 22:00 to finish by morning.

**Pi** (`tmux`; stop B3's `serve_edge.py` first):
```bash
cd ~/a2a
venv/bin/python scripts/serve_edge.py --bases 8400 --tls-dir data/tls_lan --model llama3.2:1b --num-predict 128
```
**Mac**, window 2: B1's WAN, whole (after B3, `sudo bash scripts/wan_emulation.sh off` first).
`wan_emulation.sh` sets up a plan only with `C2_BASES` equal to the plan's bases, 8300 and 8400 for
`b1_wan.json`; its rules and pipes do not depend on them, so the WAN is B1's, and nothing listens on
8300's ports. The WAN checks probe 8400 only (`C2_BASES=8400` on them), and the guard reads
connect times on 8400 only (`--bases 8400`) while checking the whole plan's pipes, rules and port
lock.
```bash
mkdir -p data/pilot2_c2b1x/shaped data/raw_c2b1x_shaped
sudo C2_BASES=8300,8400 bash scripts/wan_emulation.sh on data/results/b1_wan.json
```

### C2B1X pilot (about 6 minutes)

The first pilot (`data/pilot_c2b1x`, Nov 22 00:59) ran with the WAN off: the command above had
`C2_BASES=8400`, which `wan_emulation.sh` refuses for this plan, so it set up nothing. The opening
WAN check failed (12.4 ms end to end against 22.6), and the guard stopped the collector at the start
(no pipes, no rules), before any trace. Its files stay as they are; the pilot runs again into
`data/pilot2_c2b1x`.

**Mac**, window 1 (`tmux`):
```bash
venv/bin/python scripts/serve_cloud.py --bases 8400 --shape 8400=2048/14/128/0.05/truncate \
    --reply-log data/pilot2_c2b1x/replies --tls-dir data/tls_lan
```
**Mac**, window 2, then window 3 (root):
```bash
C2_BASES=8400 venv/bin/python scripts/check_wan_emulation.py --target data/results/b1_wan.json \
    --json data/pilot2_c2b1x/shaped/wan_check_start.json
sudo venv/bin/python scripts/wan_watch.py --out data/pilot2_c2b1x/shaped/wan_status.json --log data/pilot2_c2b1x/shaped/wan_watch.jsonl
```
**Mac**, window 2: the pilot:
```bash
caffeinate -dimsu venv/bin/python scripts/collect_session.py --placement edge-cloud --collection-id C2B1X-pilot \
    --n 5 --rounds 1 --seed-offset 31000 --prompt-start 125 \
    --exclude-prompts data/raw_c2,data/raw_c2_pad,data/raw_c2_padmax,data/raw_c2b1_padmax,data/raw_c2b1_shaped \
    --workflows iot --tls-dir data/tls_lan --wan-target data/results/b1_wan.json --reply-log data/pilot2_c2b1x/replies \
    --arm name=lan_shaped,ports=8400,pad=8192/16384,pad_expect=8192,shape=2048/14/128/0.05/truncate,out=data/pilot2_c2b1x/shaped
```
**Mac**, window 4, as soon as it has started:
```bash
venv/bin/python scripts/c2_guard.py --collector-pid "$(pgrep -f 'Python scripts/collect_session.py')" \
    --target data/results/b1_wan.json --bases 8400 --status data/pilot2_c2b1x/shaped/wan_status.json --pi-overhead-ms 3.31 \
    --calibration "$(python3 -c 'import json; print(json.dumps(json.load(open("data/raw_c2/wan_guard.json"))["calibration"]))')" \
    --json data/pilot2_c2b1x/shaped/wan_guard.json data/pilot2_c2b1x/shaped
```
The pilot passes with all of these:

- 20 of 20 traces, ending with `lan_shaped: 15 cloud replies logged, 0 cut, 0 past the deadline,
  0 failed`.
- Prompt lines from position 125.
- The guard OK.
- The closing WAN check (`--json data/pilot2_c2b1x/shaped/wan_check_after.json`, run while
  `serve_cloud.py` still runs).
- The checks below on `P=(data/pilot2_c2b1x/shaped)`.

### C2B1X pilot record (Nov 22)

- 01:07: the opening WAN check failed at 92.1 ms end to end, while the capture saw the dummynet's
  12.9 ms and the Pi reached the Mac's own address in 10.3 ms. The guard, started before the
  collector, checked once and ended (`wan_guard.json`, 0 traces). The collector was started anyway
  (01:08, 0b7acd27, clean); its round-0 probe read 58.3 ms (connects 18, 22, 19, 95, 21, 108, 95,
  21, 105, 98 ms) and it stopped before the first trace.
- 01:14: `wan_check_resume1.json` failed the same way (96.8 ms end to end, 13.1 ms at the capture).
  `iw dev wlan0 get power_save` said off. Setting power save on, then off, reached the driver (the
  kernel logged `power save enabled`, then `disabled`). Commands typed into `serve_edge.py`'s tmux
  window stopped it twice in this hour: the collector refused at its network check, and one WAN
  check could not connect and left no file.
- 01:19: `wan_check_resume2.json` passed (22.0 ms end to end, 12.5 ms at the capture). The collector
  resumed at 01:22 (0b7acd27, clean); its probe read 22.7 ms. The guard (`wan_guard_resume1.json`)
  checked at 0 and 20 traces, OK, none suspect.
- 20 of 20 traces, 0 failed, prompts from position 125 (procedure_lookup skipped 2 used before), 20
  distinct and none among C2's and B1's 1,460. 15 shaped replies, each 16,902 B on the wire, median
  release 14.768 s (expected 14.762), spread 10.7 ms, 0 cut. The closing WAN check passed (23.6 ms
  end to end, 12.6 ms at the capture), and the five checks pass.

### C2B1X full run

**Mac**, window 1: Ctrl-C, then:
```bash
venv/bin/python scripts/serve_cloud.py --bases 8400 --shape 8400=2048/14/128/0.05/truncate \
    --reply-log data/raw_c2b1x_replies --tls-dir data/tls_lan
```
**Mac**, window 3: Ctrl-C, then:
```bash
sudo venv/bin/python scripts/wan_watch.py --out data/raw_c2b1x_shaped/wan_status.json --log data/raw_c2b1x_shaped/wan_watch.jsonl
```
**Mac**, window 2: the WAN check, then the collection:
```bash
C2_BASES=8400 venv/bin/python scripts/check_wan_emulation.py --target data/results/b1_wan.json \
    --json data/raw_c2b1x_shaped/wan_check_start.json
caffeinate -dimsu venv/bin/python scripts/collect_session.py --placement edge-cloud --collection-id C2B1X \
    --n 500 --rounds 20 --seed-offset 31000 --prompt-start 125 \
    --exclude-prompts data/raw_c2,data/raw_c2_pad,data/raw_c2_padmax,data/raw_c2b1_padmax,data/raw_c2b1_shaped \
    --workflows iot --tls-dir data/tls_lan --wan-target data/results/b1_wan.json --reply-log data/raw_c2b1x_replies \
    --arm name=lan_shaped,ports=8400,pad=8192/16384,pad_expect=8192,shape=2048/14/128/0.05/truncate,out=data/raw_c2b1x_shaped
```
**Mac**, window 4, as soon as it has started:
```bash
venv/bin/python scripts/c2_guard.py --collector-pid "$(pgrep -f 'Python scripts/collect_session.py')" \
    --target data/results/b1_wan.json --bases 8400 --status data/raw_c2b1x_shaped/wan_status.json --pi-overhead-ms 3.31 \
    --calibration "$(python3 -c 'import json; print(json.dumps(json.load(open("data/raw_c2/wan_guard.json"))["calibration"]))')" \
    --json data/raw_c2b1x_shaped/wan_guard.json data/raw_c2b1x_shaped
```
The collector must end with `lan_shaped: 1500 cloud replies logged, 0 cut, 0 past the deadline, 0
failed`. If it stops (a WAN probe out of bounds on a busy Wi-Fi), rerun the same command with
`--resume` after a new WAN check (`wan_check_resume1.json`), and the guard with a new `--json`
(`wan_guard_resume1.json`).

**Mac, after:** the closing WAN check first, while `serve_cloud.py` and the Pi's `serve_edge.py`
still run, then the checks; then stop everything and the WAN (as in "Every session"):
```bash
C2_BASES=8400 venv/bin/python scripts/check_wan_emulation.py --target data/results/b1_wan.json \
    --json data/raw_c2b1x_shaped/wan_check_after.json
P=(data/raw_c2b1x_shaped)
venv/bin/python scripts/check_lan_capture.py "${P[@]}" --json data/raw_c2b1x_shaped/lan_check.json
venv/bin/python scripts/check_tls_capture.py data/raw_c2b1x_shaped --expect tls --json data/raw_c2b1x_shaped/tls_check.json
venv/bin/python scripts/check_stream_integrity.py data/raw_c2b1x_shaped --json data/raw_c2b1x_shaped/stream_integrity.json
venv/bin/python scripts/check_session_design.py "${P[@]}" --json data/raw_c2b1x_shaped/design_check.json
venv/bin/python scripts/check_shaping.py data/raw_c2b1x_shaped --json data/raw_c2b1x_shaped/shaping_check.json
```

### C2B1X record (Nov 22)

Rounds are counted from 0, as in `session_meta.json`; the collector prints round 17 as `ROUND 18/20`.

- 01:29: started from 0b7acd27 (clean). The opening WAN check passed (23.0 ms end to end, 12.6 ms at
  the capture, 9.8 ms to the Mac's own address).
- Rounds 0 to 16 ran to 07:59: 1,700 traces, 0 failed, round-start probes 21.3 to 24.2 ms. At the
  start of round 17 the probe read 57.5 ms (connects 17, 21, 89, 21, 105, 98, 26, 102, 95, 24 ms;
  11.0 ms to the Mac's own address), the Pi's chip dozing again, and the collector stopped before
  the round's first trace. The guard: 35 checks to 1,700 traces, all OK, none suspect. The pipes
  stayed at 6 ms with 0 drops throughout (`wan_watch.jsonl`).
- The collection stood until 11:59. Power save was set on, then off, on the Pi (the kernel logged
  both). `wan_check_resume1.json` then failed on its base check alone: the Pi's connects to the
  Mac's own address had a median of 66.8 ms (most of the first 20 of 30 near 67 to 70 ms, the
  last 10 mostly 8 to 10 ms), while the Mac answered them in 0.7 ms at the capture; the cloud was
  22.2 ms end to end and 13.0 ms at the capture. The collector had been pasted with the check and
  started without waiting for its result. Its own probe passed (22.6 ms; 8.6 ms to the Mac's own
  address), and it resumed at 11:59:45 from 0b7acd27 (clean), recorded as a resume.
- The guard (`wan_guard_resume1.json`) checked from 0 to 2,000 traces: 41 checks, all OK, none
  suspect. Rounds 18 and 19 opened at 21.6 and 20.9 ms.
- 13:08: 2,000 of 2,000 items, 0 failed attempts, 0 traces while the Pi was throttled; 1,500 shaped
  replies, 0 cut, 0 overrun, 0 failed, released 14.000 to 14.033 s after the request by the
  cloud's clock (2 after 14.010 s). The 2,000 prompts are distinct, and none is among C2's and
  B1's 1,460.
- The closing WAN check passed (23.2 ms end to end, 12.6 ms at the capture, 10.2 ms to the Mac's
  own address).
- The checks pass: capture (500 of 500 per task type), TLS (1.75 connections per trace, one
  handshake each), stream integrity (0% cut; the largest reply 29 to 42 packets) and design (8192
  bucket 1,500 of 1,500, largest first message 8,568 B, 0 leftover connections, `audit_null` in
  2,000 of 2,000 sidecars).
- The shaping check passes on size (every shaped reply 16,902 B on the wire, every request
  10,116 B) and on cut and overrun, and fails on release time. The median release is 14.770 s
  (expected 14.762). The 5th to 95th percentile is 14.7672 to 14.7753 s. 1,492 of 1,500 releases
  lie within 18 ms of the median and 1,499 within 27 ms, against the check's 50 ms. One trace,
  `sensor_analysis_edge_cloud_f60a76` (round 4, 03:23), ended 94.6 ms late. The cloud released it
  on time (14.002 s by its clock), and its events left 50 ms apart until the Pi's ACK of one came
  back 100 ms after it (the others within 7 ms); the reply's last 3,481 B left together 145 ms
  after the event before them. The trace stays in the collection: its bytes match every other
  reply's, and no trace is dropped after collection.
- 7.7 h of collection, plus the 4.0 h pause.

## B2: jitter and server load (paper 3)

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

## B3: a second day of `lan` (Nov 22, from 22:00)

C2's `lan` arm (8100) again, with new prompts (seed offset 33000), on C2's WAN plan
(`data/results/c2_wan_emulation.json`, bases 8100, 8200 and 8300). `OLLAMA_NUM_PARALLEL` 1 and
context 128k, as in C2 and B1. Start with "Every session", the Pi's power save on, then off,
included. `wan_emulation.sh on` sets up the whole plan: pipes 1 and 2, and the port lock on the
three bases' ports. Only 8100 runs, so the WAN checks probe 8100 (`--bases 8100`) and the guard
reads connect times on 8100 only (`--bases 8100`) while checking the plan's pipes, rules and port
lock, as for C2B1X. A pilot first, into `data/pilot_c2b3/lan`.

**Pi** (`tmux`, a window of its own; other Pi commands in a second window):
```bash
cd ~/a2a
venv/bin/python scripts/serve_edge.py --bases 8100 --tls-dir data/tls_lan --model llama3.2:1b --num-predict 128
```
**Mac**, window 1: the cloud agents (no shaping; Nagle on, as in C2), for the pilot and the full run:
```bash
venv/bin/python scripts/serve_cloud.py --bases 8100 --tls-dir data/tls_lan
```
**Mac**, window 2: C2's WAN, for the pilot and the full run:
```bash
mkdir -p data/pilot_c2b3/lan data/raw_c2b3_lan
sudo bash scripts/wan_emulation.sh on
```

### B3 pilot (about 3 minutes)

**Mac**, window 2: the WAN check, alone. Go on only if it ends with `PASS`:
```bash
venv/bin/python scripts/check_wan_emulation.py --bases 8100 --json data/pilot_c2b3/lan/wan_check_start.json
```
**Mac**, window 3 (root):
```bash
sudo venv/bin/python scripts/wan_watch.py --out data/pilot_c2b3/lan/wan_status.json --log data/pilot_c2b3/lan/wan_watch.jsonl
```
**Mac**, window 2: the pilot:
```bash
caffeinate -dimsu venv/bin/python scripts/collect_session.py --placement edge-cloud --collection-id C2B3-pilot \
    --n 5 --rounds 1 --seed-offset 33000 --workflows iot --tls-dir data/tls_lan \
    --wan-target data/results/c2_wan_emulation.json --arm name=lan,ports=8100,out=data/pilot_c2b3/lan
```
**Mac**, window 4, once the collector has printed its `network ... ok` lines:
```bash
venv/bin/python scripts/c2_guard.py --collector-pid "$(pgrep -f 'Python scripts/collect_session.py')" \
    --bases 8100 --status data/pilot_c2b3/lan/wan_status.json --pi-overhead-ms 3.31 \
    --calibration "$(python3 -c 'import json; print(json.dumps(json.load(open("data/raw_c2/wan_guard.json"))["calibration"]))')" \
    --json data/pilot_c2b3/lan/wan_guard.json data/pilot_c2b3/lan
```
The pilot passes with 20 of 20 traces and 0 failed, the guard OK, the closing WAN check and the
checks below with `D=data/pilot_c2b3/lan`. Then stop `wan_watch.py` (Ctrl-C) and start it again for
the full run's folder; the WAN, `serve_cloud.py` and `serve_edge.py` stay.

### B3 full run (about 1.9 h)

**Mac**, window 2: the WAN check, alone. Go on only if it ends with `PASS`:
```bash
venv/bin/python scripts/check_wan_emulation.py --bases 8100 --json data/raw_c2b3_lan/wan_check_start.json
```
**Mac**, window 3 (root):
```bash
sudo venv/bin/python scripts/wan_watch.py --out data/raw_c2b3_lan/wan_status.json --log data/raw_c2b3_lan/wan_watch.jsonl
```
**Mac**, window 2: the collection:
```bash
caffeinate -dimsu venv/bin/python scripts/collect_session.py --placement edge-cloud --collection-id C2B3 \
    --n 250 --rounds 5 --seed-offset 33000 --workflows iot --tls-dir data/tls_lan \
    --wan-target data/results/c2_wan_emulation.json --arm name=lan,ports=8100,out=data/raw_c2b3_lan
```
**Mac**, window 4, once the collector has printed its `network ... ok` lines:
```bash
venv/bin/python scripts/c2_guard.py --collector-pid "$(pgrep -f 'Python scripts/collect_session.py')" \
    --bases 8100 --status data/raw_c2b3_lan/wan_status.json --pi-overhead-ms 3.31 \
    --calibration "$(python3 -c 'import json; print(json.dumps(json.load(open("data/raw_c2/wan_guard.json"))["calibration"]))')" \
    --json data/raw_c2b3_lan/wan_guard.json data/raw_c2b3_lan
```
If it stops (a WAN probe out of bounds): the Pi's power save on, then off; a new WAN check, alone
(`wan_check_resume1.json`); the same collection command with `--resume`; the guard with
`wan_guard_resume1.json`.

**Mac, after** (pilot and full run): the closing WAN check first, while `serve_cloud.py` and the
Pi's `serve_edge.py` still run, then the checks; after the full run, stop everything and the WAN
(as in "Every session"):
```bash
D=data/raw_c2b3_lan
venv/bin/python scripts/check_wan_emulation.py --bases 8100 --json $D/wan_check_after.json
venv/bin/python scripts/check_lan_capture.py $D --json $D/lan_check.json
venv/bin/python scripts/check_tls_capture.py $D --expect tls --json $D/tls_check.json
venv/bin/python scripts/check_stream_integrity.py $D --json $D/stream_integrity.json
venv/bin/python scripts/check_session_design.py $D --json $D/design_check.json
```

## Afterwards (me, from a clean commit)

The audits and the cross-session transfer. Each session writes its own results JSON with commit,
seed and data folders; nothing heavy runs beside them.
- **B1:** `scripts/b1_power.py --out data/results/b1_power`; `check_shaping.py --out
  data/results/b1_shaping_overhead` (per task type, bytes and seconds against `lan_padmax`); the
  audits, per arm and view (task_type, escalated, cloud_role, audit_null; sensor vs fault; the
  escalated task types), `lan_shaped` run with `--baseline` against `lan_padmax` (the CI gate):
  ```bash
  venv/bin/python scripts/b1_audits.py --arm lan_padmax=data/raw_c2b1_padmax --arm lan_shaped=data/raw_c2b1_shaped \
      --baseline-arm lan_padmax --prefix c2b1 --out data/results/b1_audits
  ```
- **C2B1X:** sensor vs fault on B1's and C2B1X's shaped traces together, against B1's `lan_padmax`:
  ```bash
  venv/bin/python scripts/b1_audits.py --arm lan_shaped=data/raw_c2b1_shaped,data/raw_c2b1x_shaped --parts pair \
      --baseline-arm lan_padmax --baseline-prefix c2b1 --prefix c2b1_c2b1x --out data/results/b1_pair_pooled
  ```
- **B2 (paper 3):** the same audits, per arm and view.
- **B3:** `evaluate_cross_session.py --train` on C2's `lan` features, `--test` on B3's, at V1
  and V2.
