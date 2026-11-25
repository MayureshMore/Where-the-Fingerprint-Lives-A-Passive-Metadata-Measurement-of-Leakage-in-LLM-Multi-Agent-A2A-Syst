# Paper 2 pitch video: shot list

At most 5 minutes, on the SafeIoT slide template. The terminal shots come from one run of
`bash scripts/demo_paper2.sh`, which is deterministic and takes under a minute on a laptop, and from
three `a2a_leakcheck diff` commands on committed reports (shot 8), which take a second each. Record the
demo once with `OUT=/tmp/demo OPEN=1` and cut it into the shots below. Every number on screen comes
from a committed file; the last column says which.

The SafeIoT pipeline stages are collection, evidence extraction, analysis, detection, validation and
prioritization, report, and repeated evaluation.

| # | Time | Shot | Screen | Pipeline stage | Source of what is shown |
|---|---|---|---|---|---|
| 1 | 0:00–0:25 | **The problem** | Slide: Fig. 1 of the paper (edge agent on the gateway, cloud agents, V1 and V2). Every link is TLS 1.3. | — | paper Fig. 1 |
| 2 | 0:25–0:45 | **What today's checks say** | Slide: the TLS scanners on the same endpoints: grade B for configuration (private CA, TLS 1.2 CBC suites offered), and no check on traffic sizes or timing | — (the baseline) | `data/results/tls_scanners_summary.md` |
| 3 | 0:45–1:00 | **The input** | Terminal: `ls examples/c2_lan`, one sidecar (`agent_endpoints`, `vantages`, `task_type`), `python scripts/strip_payload.py --check --placeholder-macs examples/c2_lan` → 0 payload bytes, 0 real MAC addresses | Collection | `examples/c2_lan/` |
| 4 | 1:00–1:20 | **One command** | Terminal: the demo's step 1, `python -m a2a_leakcheck run examples/c2_lan_padmax --vantage v2 --attributes task_type --html`, and its log (40 traces, extraction, analysis). Voice: header-only features, the upstream view keeps only the cloud flows, grouped cross-validation | Evidence extraction, analysis | demo output |
| 5 | 1:20–1:55 | **The verdicts** | Terminal: the demo's table, the same 40 tasks without padding and padded to 8 KB. Both read LEAK; the interval clears chance + margin, and p = 0.01 (unpadded) and 0.02 (padded) against 99 permutations of the labels by prompt group. Unpadded, message sizes score best alone; padded, message counts and direction do. With 40 tasks no family alone is shown to match all features, so the table names the best one without "(alone matches all)" | Detection, validation and prioritization | `examples/expected/c2_lan_v2`, `c2_lan_padmax_v2` |
| 6 | 1:55–2:25 | **The report** | Browser: `report.html` of the padded arm: verdict, interval, permutation test, severity, which feature family carries it, and its hint. Then the full C2 report of the same arm at V2 (`data/results/leakcheck/c2_lan_padmax_v2/report.html`): with 1,000 tasks timing carries it, and the hint says padding is not enough and response timing needs shaping | Report | demo output; `data/results/leakcheck/c2_lan_padmax_v2/` |
| 7 | 2:25–2:45 | **In CI** | Terminal: the demo's step 3. The unpadded audit runs with `--baseline` against an earlier report that had too few traces to decide; task_type is now LEAK, so the run exits with code 3 | Repeated evaluation | `examples/expected/c2_ci_baseline_v2` |
| 8 | 2:45–3:50 | **Following the hint: shaping, and what the gate says** | Slide, three steps for sensor analysis vs fault diagnosis upstream (V2), the pair one cloud agent serves: **padded only** LEAK 0.628 [0.570, 0.685]; **padded + reply shaping**, 125 per class, INCONCLUSIVE 0.532 [0.470, 0.591]; **pooled** over both shaped sessions, 625 per class, NO LEAK 0.514 [0.485, 0.540], p = 0.26. Terminal, the CI gate on the committed reports, each against the padded-only one: `python -m a2a_leakcheck diff data/results/leakcheck/c2b1_lan_shaped_v2_pair/report.json data/results/leakcheck/c2b1_lan_padmax_v2_pair/report.json` → `task_type: LEAK → INCONCLUSIVE`, `needs review`, exit 0; the same with `c2b1_c2b1x_lan_shaped_v2_pair` → `task_type: LEAK → NO LEAK`, `resolved: task_type`, exit 0; the first again with `--require task_type` → exit 5 (the policy decides what fails a build; say which one runs). Slide, what remains and what it costs: timing alone 0.539 [0.510, 0.569] crosses the 0.55 bound; on the building network (V1) INCONCLUSIVE 0.544 [0.517, 0.571], p = 0.01, where the ticket post is not padded; whether the gateway called the cloud stays LEAK, 1.00. An escalated task's trace shrinks from 163.2 to 32.4 KB and takes 7.4 to 10.8 s longer. Voice: a reference defence (every cloud reply capped at 2,048 B and held until 14 s after the request, then sent as 16 events 0.05 s apart) built to test the tool's path to "resolved", not a production design; for the primary detector it meets the bound upstream, which is a large reduction, not proof the leak is closed | Repeated evaluation | `data/results/b1_audits.md`, `b1_pair_pooled.md`, `leakcheck/c2b1_c2b1x_lan_shaped_v2_pair/report.md` (timing), `b1_shaping_overhead.md`, `c2b1x_shaping_overhead.md` |
| 9 | 3:50–4:25 | **At scale and on the edge** | Slide: the full C2 numbers (3,000 traces, three padding levels, both views): all 18 learned leaks and 12 structural checks LEAK; on 480 permuted-label tests no LEAK (61 INCONCLUSIVE, 419 NO LEAK), the test rejecting 24 of 480 (5.0%); a second day (B3) gives the same verdict in all 12 cells. A four-attribute audit takes 230 s on a laptop and 26 min 38 s on the Raspberry Pi 5 (version 0.1, 4 workers) | All | `data/results/paper2_round2.md` (a11, a12), `b3_audits.md`, `leakcheck/c2_lan_v1_v030_cost/`, `leakcheck_pi/` |
| 10 | 4:25–4:55 | **Use it** | Slide: repository, `pip install -r requirements-leakcheck.txt`, the Zenodo DOI (10.5281/zenodo.24238558), the MIT licence, the SafeIoT pipeline folders; what is automated, what needs review (INCONCLUSIVE, the choice of tasks and views), what stays unverifiable | — | README, DATA.md, `safeiot/` |

Notes for recording:
- Run the demo once before recording. The first run after a reboot is slower (Python imports).
- Narrate the cause of the padded arm's leak only as the report states it. On the examples (40 tasks),
  no family alone is shown to match all features; on all of C2, the report for `lan_padmax` at V2 names timing.
- The examples are 40 of C2's 3,000 traces. Every claim about C2 as a whole comes from shot 9's files.
- Shot 8's `resolved:` line is printed from a2a-leakcheck 0.3.1 on; with 0.3.0 the run shows only the
  verdict change, and the report's "Against the baseline" section lists it as resolved.
- Shot 8 is the paper's central example: say what padding fixed (the input size), what persisted
  (timing), what shaping reduced (the pair to the bound upstream), and what remains (timing alone, V1,
  escalation). Never show a verdict without the policy that turns it into an exit code: with
  `--baseline` alone, LEAK → INCONCLUSIVE exits 0 and is listed for review; `--strict` or `--require`
  make it fail.
