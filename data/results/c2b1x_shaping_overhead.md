# Reply shaping 2048/14/128/0.05/truncate on the wire: lan_shaped against lan_padmax

Commit `615db784` (clean: True); C2B1X, `data/raw_c2b1x_shaped` against `data/raw_c2b1_padmax`.

| Check | Result | |
|---|---|---|
| Identical replies | PASS | 1500 replies, bytes [16902] |
| Release time | FAIL | median 14.770 s (expected 14.762), spread 100.4 ms |
| Cut, overrun | PASS | 0 cut, 0 overrun, 0 without the record |

| Task type | Arm | n | Trace bytes | Reply bytes | Task s | Cloud call s |
|---|---|---|---|---|---|---|
| alert_triage | shaped | 500 | 4,345 | - | 6.34 | - |
| alert_triage | control | 125 | 4,327 | - | 6.00 | - |
| alert_triage | shaped − control | | 18 | - | 0.34 | - |
| fault_diagnosis | shaped | 500 | 32,388 | 16,902 | 15.35 | 14.83 |
| fault_diagnosis | control | 125 | 163,198 | 147,495 | 7.39 | 6.87 |
| fault_diagnosis | shaped − control | | -130,810 | -130,593 | 7.96 | 7.96 |
| procedure_lookup | shaped | 500 | 32,417 | 16,902 | 15.34 | 14.83 |
| procedure_lookup | control | 125 | 163,189 | 147,531 | 4.51 | 4.04 |
| procedure_lookup | shaped − control | | -130,772 | -130,629 | 10.82 | 10.79 |
| sensor_analysis | shaped | 500 | 32,422 | 16,902 | 15.34 | 14.83 |
| sensor_analysis | control | 125 | 163,206 | 147,363 | 7.92 | 7.45 |
| sensor_analysis | shaped − control | | -130,784 | -130,461 | 7.42 | 7.38 |

Medians per task type; bytes from TCP sequence numbers in header-only captures.
