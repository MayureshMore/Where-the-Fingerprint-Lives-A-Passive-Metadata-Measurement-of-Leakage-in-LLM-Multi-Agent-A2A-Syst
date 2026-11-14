# Paper 2 pitch video: shot list

At most 5 minutes, on the SafeIoT slide template. The terminal shots come from one run of
`bash scripts/demo_paper2.sh`, which is deterministic and takes under a minute on a laptop. Record it
once with `OUT=/tmp/demo OPEN=1` and cut it into the shots below. Every number on screen comes from a
committed file; the last column says which.

The SafeIoT pipeline stages are collection, evidence extraction, analysis, detection, validation and
prioritization, report, and repeated evaluation.

| # | Time | Shot | Screen | Pipeline stage | Source of what is shown |
|---|---|---|---|---|---|
| 1 | 0:00–0:30 | **The problem** | Slide: Fig. 1 of the paper (edge agent on the gateway, cloud agents, V1 and V2). Every link is TLS 1.3. | — | paper Fig. 1 |
| 2 | 0:30–0:55 | **What today's checks say** | Slide: the TLS scanners on the same endpoints: grade B for configuration (private CA, TLS 1.2 CBC suites offered), and no check on traffic sizes or timing | — (the baseline) | `data/results/tls_scanners_summary.md` |
| 3 | 0:55–1:20 | **The input** | Terminal: `ls examples/c2_lan`, one sidecar (`agent_endpoints`, `vantages`, `task_type`), `python scripts/strip_payload.py --check --placeholder-macs examples/c2_lan` → 0 payload bytes, 0 real MAC addresses | Collection | `examples/c2_lan/` |
| 4 | 1:20–1:50 | **One command** | Terminal: the demo's step 1, `python -m a2a_leakcheck run examples/c2_lan_padmax --vantage v2 --attributes task_type --html`, and its log (40 traces, extraction, analysis). Voice: header-only features, the upstream view keeps only the cloud flows, grouped cross-validation | Evidence extraction, analysis | demo output |
| 5 | 1:50–2:40 | **The verdicts** | Terminal: the demo's table, the same 40 tasks without padding and padded to 8 KB. Both read LEAK; the interval clears chance + margin and p = 0.01 against 99 label permutations. What carries the leak moves away from message sizes once padded | Detection, validation and prioritization | `examples/expected/c2_lan_v2`, `c2_lan_padmax_v2` |
| 6 | 2:40–3:20 | **The report** | Browser: `report.html` of the padded arm: verdict, interval, permutation test, severity, which feature family carries it, the hint ("padding is not enough…") | Report | demo output |
| 7 | 3:20–3:50 | **In CI** | Terminal: the demo's step 3. The unpadded audit runs with `--baseline` against an earlier report that had too few traces to decide; task_type is now LEAK, so the run exits with code 3 | Repeated evaluation | `examples/expected/c2_ci_baseline_v2` |
| 8 | 3:50–4:20 | **At scale and on the edge** | Slide: the full C2 numbers (3,000 traces, both views, three arms), recall and false positives, and the audit's runtime and memory on the Raspberry Pi 5 | All | `data/results/paper2_tool_eval_c2.md`, `data/results/leakcheck_pi/` |
| 9 | 4:20–4:50 | **Use it** | Slide: repository, `pip install -r requirements-leakcheck.txt`, the Zenodo DOI, the MIT licence; what is automated, what needs review (INCONCLUSIVE, the choice of tasks and views), what stays unverifiable | — | README, DATA.md |

Notes for recording:
- Run the demo once before recording. The first run after a reboot is slower (Python imports).
- Narrate the cause of the padded arm's leak only as the report states it. On the examples, several
  families each match all features; on all of C2, the report for `lan_padmax` at V2 names timing.
- The examples are 40 of C2's 3,000 traces. Every claim about C2 as a whole comes from shot 8's files.
