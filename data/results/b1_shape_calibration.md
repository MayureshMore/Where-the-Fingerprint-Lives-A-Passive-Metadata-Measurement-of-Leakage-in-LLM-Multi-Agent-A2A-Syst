# B1: reply shaping 2048/14/128/0.05/truncate against C2

Commit `b0ca13c8` (clean: True). 2250 escalated cloud replies from data/raw_c2, data/raw_c2_pad, data/raw_c2_padmax (1720 measured exactly).

| | |
|---|---|
| Reply bytes (JSON-encoded): max / p99 / median | 1515 / 1433 / 1207 |
| Cap | 2048 B: 0 cut, margin 533 B |
| Cloud call (edge's answer time): max / p99 | 9.9 / 9.4 s |
| Release | first event at 14 s, last at 14.75 s: 0 late, margin 4.1 s |
| Shaped reply on the wire | 16 events × 707 B + artifact 2423 B = 13735 B |
| Filler per reply: median / p95 / max | 2121 / 2813 / 4477 B (15% of the shaped reply) |
| C2's unshaped reply part: median / p95 / max | 144330 / 144658 / 144950 B |

| Task type | Replies | Bytes max | Cut | Answer max (s) | Late |
|---|---|---|---|---|---|
| fault_diagnosis | 750 | 1448 | 0 | 8.3 | 0 |
| procedure_lookup | 750 | 1510 | 0 | 5.5 | 0 |
| sensor_analysis | 750 | 1515 | 0 | 9.9 | 0 |
