# Reply shaping 2048/14/128/0.05/truncate on the wire: lan_shaped against lan_padmax

Commit `dd9320b5` (clean: True); C2B1, `data/raw_c2b1_shaped` against `data/raw_c2b1_padmax`.

| Check | Result | |
|---|---|---|
| Identical replies | PASS | 375 replies, bytes [16902] |
| Release time | PASS | median 14.770 s (expected 14.762), spread 52.3 ms |
| Cut, overrun | PASS | 0 cut, 0 overrun, 0 without the record |

| Task type | Arm | n | Trace bytes | Reply bytes | Task s | Cloud call s |
|---|---|---|---|---|---|---|
| alert_triage | shaped | 125 | 4,326 | - | 5.62 | - |
| alert_triage | control | 125 | 4,327 | - | 6.00 | - |
| alert_triage | shaped − control | | -1 | - | -0.38 | - |
| fault_diagnosis | shaped | 125 | 32,439 | 16,902 | 15.36 | 14.83 |
| fault_diagnosis | control | 125 | 163,198 | 147,495 | 7.39 | 6.87 |
| fault_diagnosis | shaped − control | | -130,759 | -130,593 | 7.97 | 7.97 |
| procedure_lookup | shaped | 125 | 32,438 | 16,902 | 15.35 | 14.84 |
| procedure_lookup | control | 125 | 163,189 | 147,531 | 4.51 | 4.04 |
| procedure_lookup | shaped − control | | -130,751 | -130,629 | 10.84 | 10.80 |
| sensor_analysis | shaped | 125 | 32,422 | 16,902 | 15.35 | 14.83 |
| sensor_analysis | control | 125 | 163,206 | 147,363 | 7.92 | 7.45 |
| sensor_analysis | shaped − control | | -130,784 | -130,461 | 7.43 | 7.39 |

Medians per task type; bytes from TCP sequence numbers in header-only captures.
