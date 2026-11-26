# Pre-registration: C2B2, the WAN portability check

This file is committed before any C2B2 trace is collected, pilot included. The commit that adds it is
the registration. Any change after it is listed, with its reason, in the C2B2 record in
docs/ROUND2_SESSIONS.md and in the paper.

## Question

With every request padded to 8 KB, the task type still leaks upstream through timing. In C2B1M's padded
control, the pair sensor_analysis vs fault_diagnosis at V2 scored 0.646 [0.604, 0.688] on the timing
family alone (`data/results/leakcheck/c2b1m_lan_padmax_v2_pair/report.json`,
`attributes.task_type.attribution.families.timing`).

**Does that timing leak survive a less ideal WAN, one with jitter in both directions and a loaded cloud
server?** Or is it an artefact of the testbed's fixed delay and idle server?

## Design

| | |
|---|---|
| Collection | C2B2, one session on C2's testbed (docs/LAN_SETUP.md), from Nov 26, 2026 |
| Task types | the IoT set (`--workflows iot`): alert_triage, procedure_lookup, sensor_analysis, fault_diagnosis |
| Control arm | `lan_padmax`, ports 8100: requests padded to 8 KB (`pad=8192/16384`, `pad_expect=8192`), on C2's WAN (6 ms each way, dummynet pipes 1 and 2); **250 per task type** |
| Treatment arm | `lan_padmax_jl`, ports 8500: the same padding, the WAN jitter and the server load below; **250 per task type** |
| Jitter | as planned on Nov 21 (`data/results/b2_wan_jitter.json`). The same 6 ms mean one way: 2 ms of dummynet (pipes 3 and 4) plus a normal delay, mean 4 ms and sd 1.8 ms, with draws below 0 clipped to 0 (mean 4.01, sd 1.78). Request side: netem on the Pi's egress, only for packets to the treatment's cloud ports 8501 and 8502 (requests and the Pi's ACKs), with a rate so that order is kept. Reply side: the cloud agents delay every SSE event by a draw, in order (`serve_cloud.py --jitter 8500=4/1.8/1`) |
| Load | during every treatment task, and only then: 2 concurrent generations on the Mac's Ollama (`load=2`, `scripts/ollama_load.py`; localhost, never on the observed path), started before the capture and stopped after it |
| Ollama | for the whole session, both arms: `OLLAMA_NUM_PARALLEL` 4, context 32k, the model wholly in GPU memory |
| Interleaving | 25 rounds. Each round runs 10 items per task type in one seeded random order, and the two arms alternate on the same prompt |
| Prompts | seed offset 32000, new to this collection. Every prompt in the sidecars of C2 (`raw_c2`, `raw_c2_pad`, `raw_c2_padmax`), C2B1 (`raw_c2b1_padmax`, `raw_c2b1_shaped`), C2B1X (`raw_c2b1x_shaped`), B3 (`raw_c2b3_lan`) and C2B1M (`raw_c2b1m_padmax`, `raw_c2b1m_shaped`) is skipped (`--exclude-prompts`), and so is every repeat. Measured on Nov 26 against those 5,600 prompts: 250 distinct prompts per type, none used before (docs/PROMPT_REGISTRY.md) |
| Testbed | as C2: the edge agent on the Pi (`llama3.2:1b`, 128 tokens) and the cloud agents on the Mac (`llama3.2:3b`), over TLS 1.3. Also: the guard with `--bases 8100,8500` and per-arm targets, `wan_watch.py`, AWDL down, and the Pi's Wi-Fi keeper (`scripts/pi_wifi_keeper.py`) |
| Pilot | first, into `data/pilot_c2b2/`: 5 items per task type in each arm. The full run starts only if the pilot passes every check below, manipulation checks included. The pilot is not analysed |

What the design cannot separate or match:
- **Jitter and load act together.** The treatment tests the two combined, not either one alone.
- **The reply side's jitter only reaches the SSE events.** The cloud's other packets (TCP and TLS
  handshakes, ACKs, HTTP headers) see 2 ms of dummynet one way instead of 6. So the treatment's
  handshakes are 4 ms shorter than the control's, for every task alike.
- **Both arms run at 4 Ollama slots and a 32k context.** That differs from C2's 1 slot and 128k, so
  the control matches C2's WAN, not C2's server.

## Checks

**Data checks:**
- the opening and closing WAN checks, and the guard;
- every expected call captured (`check_lan_capture.py`);
- TLS on every connection (`check_tls_capture.py`);
- no cut stream (`check_stream_integrity.py`);
- the design: every first request of both arms in the 8,192 B bucket (`check_session_design.py`);
- a header-only copy with 0 payload bytes and 0 real MAC addresses.

**Manipulation checks.** They are run by `scripts/check_b2_manipulation.py`. Every one must pass, or the
session is reported **invalid**: its results are still reported, labelled invalid, and the primary is not
read either way.

1. **netem active on the Pi.**
   - The Pi's `tc -s qdisc show dev wlan0` is saved before and after the session. Both times it shows
     the netem qdisc with a 4 ms delay and 1.8 ms jitter.
   - Its packet count grew by at least 0.9 × the treatment's Pi → cloud packets in the captures.
   - At the capture, the time from the cloud's SYN-ACK to the Pi's ACK has a treatment median that
     exceeds the control's by the netem mean (4.01 ms), within ±1.5 ms.
2. **Reordering.** The treatment's Pi → cloud reordering is within the control's plus 0.5 percentage
   points, and the cloud → Pi side has no hole (`check_reorder.py`).
3. **Logged jitter.** The cloud agents record their draws for every reply (count, sum, sum of squares,
   in `cloud_replies`).
   - Pooled over the treatment arm, the draws' mean and sd lie within 0.2 ms of 4.01 and 1.78 ms.
   - Every escalated treatment trace has the record.
   - No control trace has one.
4. **Load only during treatment tasks.**
   - Every treatment trace's load window covers the trace (`start_ts` to `end_ts`).
   - That window has 2 streams, both generating at the start, with tokens received.
   - No control trace has a load, and none overlaps a load window.
5. **Cloud replies slower under load.** For each escalated task type, the median of the edge's cloud
   call time (`edge_report.seconds.answer`) in the treatment is at least 1.10 × the control's.
6. **Model fully on the GPU.** These come from the collector, in `session_meta.json`:
   - every parallel check, at each start and resume, is ok;
   - the last GPU check of every round, and the check at the end, show at least 0.999 of the model in
     GPU memory, at context 32,768.
7. **The Pi's Wi-Fi keeper.** `scripts/pi_wifi_keeper.py check` passes over the session: no
   re-disable, reconnect, lost link, error or restart, with the keeper running throughout.

## Analysis, fixed now

The analysis runs from a clean commit, after the collection and its checks. It uses a2a-leakcheck's
defaults at that commit (0.3.1):
- gradient-boosted trees, with 5 folds grouped by prompt;
- 1,000 cluster-bootstrap resamples;
- 99 label permutations by prompt group, scored with the rf-light null model;
- margin 0.05, alpha 0.05, match margin 0.05, seed 42, `--strip`.

```bash
python scripts/b1_audits.py --arm lan_padmax=data/raw_c2b2_padmax --arm lan_padmax_jl=data/raw_c2b2_padmax_jl \
    --parts all,pair,escalated_only --feature-sets all,timing --baseline-arm lan_padmax \
    --prefix c2b2 --title "C2B2 audits" --out data/results/c2b2_audits
python scripts/check_b2_manipulation.py --control data/raw_c2b2_padmax --treatment data/raw_c2b2_padmax_jl \
    --target data/results/b2_wan_jitter.json --tc-start data/raw_c2b2_padmax/pi_tc_start.txt \
    --tc-end data/raw_c2b2_padmax/pi_tc_end.txt --reorder data/raw_c2b2_padmax_jl/reorder_check.json \
    --keeper data/raw_c2b2_padmax/wifi_keeper_check.json --json data/results/c2b2_manipulation.json
```

The first command audits both arms at both views (V1, V2) in three parts:
- all traces: task_type, escalated, cloud_role and audit_null;
- the pair, sensor_analysis vs fault_diagnosis;
- the three escalated task types.

Each part is audited twice: on all features, and on the **timing family alone**. For timing alone, the
traces are extracted at the same view. Every column of the trace and role vectors outside
`features/families.py`'s timing family (30 of the 195 trace columns) is set to 0, and so is the
first-request size. `run` then audits that features folder. This gives the full verdict on timing alone:
- **LEAK** if the interval's lower bound is above 0.55 and p ≤ 0.05;
- **NO LEAK** if its upper bound is at most 0.55 and p > 0.05;
- **INCONCLUSIVE** otherwise.

A column that is 0 everywhere is never split on, so the timing-only macro-F1 equals the timing
family's score in the full audit's attribution. Checked on C2B1M's pair at V2: 0.646 [0.604, 0.688]
and 0.512 [0.486, 0.538], each the same as its attribution. The treatment arm's audits run with
`--baseline` against the control's audit of the same view, part and feature set (the CI gate).

**Primary.** Sensor vs fault at V2, on the timing family alone, in each arm:
- the control: `c2b2_lan_padmax_v2_pair_timing`;
- the treatment: `c2b2_lan_padmax_jl_v2_pair_timing`.

Each is reported as its verdict, macro-F1 [95% CI] and p. **Does the treatment arm still read LEAK?**
- **LEAK:** the timing leak survives the WAN's jitter and the server load at this sample size.
- **NO LEAK:** jitter and load together bring it to the NO LEAK bound.
- **INCONCLUSIVE:** not shown either way.

**Control requirement, the condition for reading the primary.** The control's pair at V2 on timing alone
(`c2b2_lan_padmax_v2_pair_timing`) must read LEAK. Otherwise the session did not show the timing leak
whose portability is in question, and the primary is reported but not read. The control's
all-features pair at V2 is reported beside it.

**Secondary,** each arm, at V1 and V2, with all features and on timing alone, as verdict, macro-F1
[95% CI] and p:
1. task_type over all four types (`c2b2_<arm>_<view>` and `..._timing`);
2. task_type over the three escalated types (`c2b2_<arm>_<view>_escalated_only` and `..._timing`);
3. the all-features pair (`c2b2_<arm>_<view>_pair`).

**Reported beside them, descriptive:**
- escalated, cloud_role and audit_null (part all), and the timing-alone pair at V1;
- each CI gate (exit code, changes, needs review, resolved);
- every manipulation check with its numbers;
- the data checks and the pace.

## What we report whatever the outcome

- The primary, worded as above.
- The control's verdict.
- The manipulation checks and the validity they give.
- The secondaries and the descriptive numbers.

Each comes with its file and field:
- `data/results/c2b2_audits.{json,md}`;
- the reports under `data/results/leakcheck/c2b2_*`;
- `data/results/c2b2_manipulation.json`.

These are committed from a clean commit, with the commit, seed and data folders they record. The paper
states the primary as registered here, including an INCONCLUSIVE, a NO LEAK or an invalid session.

## What we will not do

- Pool C2B2 with C2, C2B1M or any other session. Or change the parameters, the seed, the views, the
  attribute or the feature set, for the primary.
- Audit any label before the collection ends. Only the data and manipulation checks run during it.
- Drop traces other than those the collector marks failed (`success: false`), which the tool skips.
- Change the jitter or the load after the pilot. A pilot that fails a manipulation check because of a
  setup fault (netem not on, Ollama not parallel, the model off the GPU) is fixed and run again. One
  that fails because the manipulation itself is too weak (the load slows the cloud by less than 10%)
  ends C2B2 there, and that is reported. Changing the manipulation needs an amendment committed before
  any further trace.
- Extend or repeat the collection because of a result. If the session ends early (the guard or a GPU
  check stops it, and it cannot be resumed), the traces collected are analysed as registered and the
  shortfall is reported.

## Power

At 250 per class the interval's half-width is about 0.04: C2B1M's padded control gave 0.646
[0.604, 0.688] on timing alone.
- **LEAK** in the treatment needs a macro-F1 of about 0.595 or more.
- **NO LEAK** needs about 0.508 or less.
- **INCONCLUSIVE** covers anything between, so a treatment that weakens the timing signal without
  removing it can read INCONCLUSIVE. That is what this sample size leaves undecided, not evidence either
  way.
- **The control** is expected to read LEAK with room to spare, if its timing signal is as in C2B1M
  (lower bound 0.604).
