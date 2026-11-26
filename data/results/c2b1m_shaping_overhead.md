# Reply shaping 2048/14/128/0.05/truncate on the wire: lan_shaped against lan_padmax

Commit `d20beec0` (clean: True); C2B1M, `data/raw_c2b1m_shaped` against `data/raw_c2b1m_padmax`.

| Check | Result | |
|---|---|---|
| Identical replies | PASS | 1250 replies, bytes [16902] |
| Release time | FAIL | median 14.768 s (expected 14.762), spread 1154.1 ms |
| Cut, overrun | PASS | 0 cut, 0 overrun, 0 without the record |

| Task type | Arm | n | Trace bytes | Reply bytes | Task s | Cloud call s |
|---|---|---|---|---|---|---|
| fault_diagnosis | shaped | 625 | 32,344 | 16,902 | 15.29 | 14.83 |
| fault_diagnosis | control | 250 | 163,102 | 147,472 | 7.44 | 6.98 |
| fault_diagnosis | shaped − control | | -130,758 | -130,570 | 7.85 | 7.84 |
| sensor_analysis | shaped | 625 | 32,373 | 16,902 | 15.29 | 14.83 |
| sensor_analysis | control | 250 | 163,116 | 147,419 | 7.71 | 7.24 |
| sensor_analysis | shaped − control | | -130,743 | -130,517 | 7.57 | 7.59 |

Medians per task type; bytes from TCP sequence numbers in header-only captures.
