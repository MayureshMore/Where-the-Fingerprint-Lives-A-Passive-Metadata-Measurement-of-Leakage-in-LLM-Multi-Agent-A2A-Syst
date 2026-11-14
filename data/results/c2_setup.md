# C2 setup numbers

From data at commit 8dd4b74e.

Session 2026-11-12T21:43:54-0800 to 2026-11-13T03:28:37-0800 (5 h 45 min); traces per arm lan 1000, lan_pad 1000, lan_padmax 1000; 0 failed, 3000 of 3000 succeeded on the first try; median 7.03 s per trace.

Raspberry Pi: 51.6–69.7 °C over 3000 traces; 0 throttled.

## Task inputs (UTF-8 bytes of the prompt (sidecar prompt_bytes); same in all arms: True)

| Task type | n | Median | IQR | Range |
|---|---|---|---|---|
| alert_triage | 250 | 154 | 145–162 | 124–187 |
| fault_diagnosis | 250 | 3,589.5 | 2,996.25–4,183.25 | 1,987–5,490 |
| procedure_lookup | 250 | 81 | 69.75–95 | 48–124 |
| sensor_analysis | 250 | 2,798.5 | 1,818.25–3,755.5 | 573–5,238 |

Median over all tasks 380 B; largest 5,490 B.

## Answers (characters of the answer the edge agent filed (sidecar edge_report.answer_chars); no file records token counts)

| Arm | Task type | n | Median | IQR | Range |
|---|---|---|---|---|---|
| lan | alert_triage | 250 | 216.5 | 155.75–309.75 | 33–616 |
| lan | fault_diagnosis | 250 | 1,178.5 | 1,088.5–1,228.25 | 634–1,435 |
| lan | procedure_lookup | 250 | 1,204 | 1,125–1,267.25 | 84–1,462 |
| lan | sensor_analysis | 250 | 1,140.5 | 1,004–1,259.25 | 605–1,493 |
| lan_pad | alert_triage | 250 | 205 | 143.75–283 | 33–666 |
| lan_pad | fault_diagnosis | 250 | 1,167 | 1,078.75–1,238 | 704–1,403 |
| lan_pad | procedure_lookup | 250 | 1,206.5 | 1,148–1,278.5 | 29–1,467 |
| lan_pad | sensor_analysis | 250 | 1,165.5 | 1,044.25–1,251 | 603–1,436 |
| lan_padmax | alert_triage | 250 | 209.5 | 142–292 | 42–676 |
| lan_padmax | fault_diagnosis | 250 | 1,170 | 1,088–1,247.25 | 686–1,353 |
| lan_padmax | procedure_lookup | 250 | 1,224.5 | 1,151.5–1,277.75 | 141–1,497 |
| lan_padmax | sensor_analysis | 250 | 1,175.5 | 1,015.5–1,274.25 | 675–1,468 |

## On the wire (IP bytes and packets per trace, to or from the agent endpoints each view sees (all 1,000 tasks of the arm; a task the view does not see counts as 0))

| Arm | View | Bytes per trace | Packets | Bytes vs lan | Packets vs lan |
|---|---|---|---|---|---|
| lan | v1 | 131,417 | 268.8 | ×1.000 | ×1.000 |
| lan | v2 | 125,155 | 245.8 | ×1.000 | ×1.000 |
| lan_pad | v1 | 133,734 | 271.8 | ×1.018 | ×1.011 |
| lan_pad | v2 | 127,464 | 248.9 | ×1.018 | ×1.013 |
| lan_padmax | v1 | 136,940 | 275.0 | ×1.042 | ×1.023 |
| lan_padmax | v2 | 130,670 | 252.1 | ×1.044 | ×1.026 |

Padding check, lan_pad: 750 first requests by bucket {'1024': 262, '2048': 45, '4096': 277, '8192': 166}; median overhead 296 B.

Padding check, lan_padmax: 750 first requests by bucket {'8192': 750}; median overhead 296 B.

Models: edge llama3.2:1b (num_predict 128); cloud llama3.2:3b (num_predict 256). Padding buckets: lan none; lan_pad [1024, 2048, 4096, 8192, 16384, 32768]; lan_padmax [8192, 16384].

## Emulated WAN

- Target round trip 22.6 ms; dummynet 12 ms (6 ms each way).
- Guard: 61 checks, all passed: True; 0 suspect traces; stopped: False. Over 2,250 handshakes in 60 windows of 50 traces, Pi → cloud connect median 20.2 ms (window medians 19.7–20.6 ms); SYN → SYN-ACK at the capture 12.0–13.3 ms, never under 11.2 ms; ticket service connect 0.4–0.6 ms.
- wan_check_start: passed True; per edge agent, cloud end to end 20.5–20.7 ms and the Mac's own address 8.0–8.5 ms; at the capture, SYN → SYN-ACK 12.5 ms to the cloud, 0.7 ms to the Mac; base round trip median 8.4 ms
- wan_check_after: passed True; per edge agent, cloud end to end 20.7–21.1 ms and the Mac's own address 7.7–9.1 ms; at the capture, SYN → SYN-ACK 13.2 ms to the cloud, 0.6 ms to the Mac; base round trip median 8.3 ms
- Collector's probes before each round (15): medians 19.5–21.6 ms, median 20.8 ms; the Mac's own address 7.6–9.1 ms.
