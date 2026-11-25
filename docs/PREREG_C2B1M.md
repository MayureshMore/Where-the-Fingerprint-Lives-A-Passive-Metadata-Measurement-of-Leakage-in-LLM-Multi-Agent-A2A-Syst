# Pre-registration: C2B1M, a matched held-out test of reply shaping

Committed before any C2B1M trace is collected, pilot included; the commit that adds this file is the
registration. Changes after it are listed, with their reasons, in the C2B1M record in
docs/ROUND2_SESSIONS.md and in the paper.

## Question

Does D3's reference reply-shaping defence bring sensor_analysis vs fault_diagnosis (the pair one cloud
agent serves) to NO LEAK upstream in a session it has not been seen in, against a padded control
collected beside it?

D3 answered this only in part: in C2B1 (125 per class) the shaped pair read INCONCLUSIVE at V2, and its
NO LEAK (0.514 [0.485, 0.540], p 0.26) came from pooling C2B1's shaped traces with C2B1X's, a later
session without a padded control, after C2B1's results were known. C2B1M is collected once, with its
analysis fixed here.

## Design

| | |
|---|---|
| Collection | C2B1M, one session on C2's testbed (docs/LAN_SETUP.md), the night of Nov 25, 2026 |
| Task types | sensor_analysis and fault_diagnosis only (`--workflows sensor_analysis,fault_diagnosis`); both escalate to the diagnostics cloud agent |
| Shaped arm | `lan_shaped`, ports 8400: requests padded to 8 KB (`pad=8192/16384`, `pad_expect=8192`) and cloud replies shaped as in D3 (`shape=2048/14/128/0.05/truncate`: at most 2,048 encoded bytes, released 14 s after the request as 16 events 0.05 s apart); **625 per class** |
| Control arm | `lan_padmax`, ports 8300: the same padding, no shaping; **250 per class** |
| Interleaving | 25 rounds; each round 25 shaped and 10 control traces per class in one seeded random order, the arms alternating on the same prompt (the control runs on 250 of the 625 items per class, spread evenly: 10 per round) |
| Prompts | seed offset 34000, new to this collection; every prompt in the sidecars of C2 (`raw_c2`, `raw_c2_pad`, `raw_c2_padmax`), C2B1 (`raw_c2b1_padmax`, `raw_c2b1_shaped`), C2B1X (`raw_c2b1x_shaped`) and B3 (`raw_c2b3_lan`) skipped (`--exclude-prompts`), and every repeat; checked after the run against those folders |
| Testbed | as C2B1 and C2B1X: the edge agent on the Pi (`llama3.2:1b`, 128 tokens), the cloud agents on the Mac (`llama3.2:3b`, 256 tokens, `OLLAMA_NUM_PARALLEL` 1), TLS 1.3, WAN plan `data/results/b1_wan.json` (bases 8300 and 8400), the guard with `--bases 8300,8400`, `wan_watch.py`, AWDL down, the Pi's power-save toggle |
| Pilot | first, into `data/pilot_c2b1m/`: 10 shaped and 4 control per class; the full run starts only if it passes every check below. Not analysed |
| Checks | the opening and closing WAN checks; the guard; every expected call captured (`check_lan_capture.py`); TLS on every connection (`check_tls_capture.py`); no cut stream (`check_stream_integrity.py`); the design (`check_session_design.py`); the shaping, against the control (`check_shaping.py --control`); a header-only copy with 0 payload bytes and 0 real MAC addresses; the collector's tally `0 cut, 0 past the deadline, 0 failed` |

## Analysis, fixed now

From a clean commit, after the collection and its checks, with a2a-leakcheck's defaults at that
commit (0.3.1: gradient-boosted trees, 5 folds grouped by prompt, 1,000 cluster-bootstrap resamples,
99 label permutations by prompt group scored with the rf-light null model, margin 0.05, alpha 0.05,
match margin 0.05, seed 42, `--strip`):

```bash
python scripts/b1_audits.py --arm lan_padmax=data/raw_c2b1m_padmax --arm lan_shaped=data/raw_c2b1m_shaped \
    --parts pair --baseline-arm lan_padmax --prefix c2b1m --title "C2B1M audits" --out data/results/c2b1m_audits
```

It audits the pair in both arms at both views, and runs each shaped audit with `--baseline` against
the control's audit of the same view (the CI gate).

**Primary.** The shaped arm's pair at V2 (`c2b1m_lan_shaped_v2_pair`). NO LEAK if and only if the
upper bound of the 95% interval of macro-F1 is at most 0.55 (chance 0.5 + margin 0.05) **and** the
permutation test's p > 0.05: the tool's NO LEAK verdict. Read as:
- NO LEAK: the defence meets the NO LEAK bound upstream for the primary detector in a held-out session;
- INCONCLUSIVE: not shown either way;
- LEAK: the defence leaves the pair separable upstream.

**Control, the condition for reading the primary.** The control's pair at V2
(`c2b1m_lan_padmax_v2_pair`) must read LEAK (lower bound above 0.55 and p ≤ 0.05). If it does not, the
session did not show the leak the defence is meant to remove: the primary is reported, but not read
as evidence for or against the defence.

**Secondary.**
1. The timing family alone on the shaped pair at V2: its macro-F1 and 95% interval from the report's
   attribution (`attribution.families.timing`). Below the bound if and only if the upper bound is at
   most 0.55. The sizes and counts families are reported beside it.
2. The shaped pair at V1, the building network, which also sees the unpadded ticket post: verdict,
   macro-F1, interval and p.

**Reported beside them, descriptive.** The control's pair at V1; the CI gate of each shaped audit
(exit code, changes, needs review, resolved); the shaping check and the overhead in bytes and seconds
against the control (`check_shaping.py --control`); the collection's checks and pace.

## What we report whatever the outcome

The primary verdict worded as above, the control's verdict, both secondaries and the descriptive
numbers, each with its file and field, in `data/results/c2b1m_audits.{json,md}` and the reports under
`data/results/leakcheck/c2b1m_*`, committed from a clean commit with the commit, seed and data folders
they record. The paper states the primary as registered here, including an INCONCLUSIVE or a LEAK, and
keeps D3's pooled result as what it is: a result from pooled sessions.

## What we will not do

- Pool C2B1M with C2B1 or C2B1X, or change the parameters, the seed, the views or the attribute,
  for the primary.
- Audit the pair (or any label) before the collection ends; only the data checks above run during it.
- Drop traces other than those the collector marks failed (`success: false`), which the tool skips.
- Extend or repeat the collection because of a result. If the night ends early (the guard stops it,
  or a check fails and cannot be resumed as in C2B1X), the traces collected are analysed as registered
  and the shortfall is reported.

## Power

With no signal at all, a two-class audit reads NO LEAK in 8 of 20 permuted draws at 125 per class and
15 of 20 at 375, and 14 of 20 are predicted at 500 from the intervals alone
(`data/results/b1_power.json`: `measured.125.verdicts`, `pooled_check.verdicts`,
`predicted.500.ci_no_leak`). At 625 per class the interval is narrower still (its half-width scales as
1/√n), but even a perfect defence can read INCONCLUSIVE here. An INCONCLUSIVE primary is therefore not
evidence of a leak; it is what this sample size leaves undecided.
