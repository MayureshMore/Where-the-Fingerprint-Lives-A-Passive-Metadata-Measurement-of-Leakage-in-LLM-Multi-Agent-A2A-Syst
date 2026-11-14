# Paper 2: where each number comes from

Every number in paper 2 (a2a-leakcheck, SafeIoT Track 1) and the file that holds it. All files are
under `data/results/` unless the path says otherwise. `scripts/reproduce_paper2.sh` rebuilds them
from the released data and compares each with the committed one. `scripts/export_paper2_csv.py`
writes the plotted ones to `data/results/paper2_csv/` for the paper's pgfplots figures.

The paths use these placeholders:
- `<arm>`: `tls` or `cleartext` in D1; `lan`, `lan_pad` or `lan_padmax` in D2.
- `<cell>`: an arm at a view: `tls`, `cleartext`, or `lan_v1` … `lan_padmax_v2`.
- `<attr>`: an attribute.
- `<audit>`: a leakcheck report folder (`leakcheck/<audit>/report.json`): `tls_control_clear_own`,
  `tls_control_tls_own`, or `c2_<arm>_<view>`.

## Data and setup

| Number | File | Field |
|---|---|---|
| D1: 432 traces per arm (864) | `leakcheck/tls_control_<arm>_own/report.json` | `extraction.traces` |
| D1: the 231 prompts both arms share | `tls_control_own.json` | `results.workflow.tls_minus_clear.shared_groups` |
| D2: 3,000 traces, 1,000 per arm, 250 per task type, 0 failed, first try | `c2_setup.json` | `session.traces`, `session.per_task_type`, `session.failed`, `session.succeeded_first_try` |
| D2: one session of 5 h 45 min; 7.03 s per trace | `c2_setup.json` | `session.length`, `session.median_s_per_trace` |
| D2: the models and token limits (edge 1B, 128; cloud 3B, 256) | `c2_setup.json` | `models` |
| D2: padding buckets (power of two from 1 KB; one bucket of 8 KB) | `c2_setup.json` | `models.pad_buckets`, `models.pad_expect` |
| D2: Pi 52 to 70 °C, never throttled | `c2_setup.json` | `pi.temperature_c` (51.6–69.7), `pi.throttled_traces` |
| D2: task inputs per task type (medians, IQR, range) | `c2_setup.json` | `inputs.per_task_type` (exact; DATA.md rounds the halves up) |
| D2: answer lengths per task type | `c2_setup.json` | `answers.per_arm` (characters; no file records token counts) |
| Target round trip 22.6 ms (the Mac to EC2 us-west-1) | `c2_wan_emulation.json`; `c2_setup.json` | `wan.target_rtt_ms` |
| 6 ms each way (12 ms dummynet) | `c2_setup.json` | `wan.one_way_ms`, `wan.dummynet_ms` |
| The cloud connect time over the collection (19.7–21.1 ms) | `c2_setup.json` | `wan.guard.pi_connect_window_medians_ms` (19.7–20.6) and `wan.wan_checks.*.cloud_end_to_end_ms` (to 21.1) |
| The Wi-Fi round trip (8.3 ms) | `c2_setup.json` | `wan.wan_checks.wan_check_after.base_rtt_median_ms` |
| Ticket service not delayed (0.4–0.6 ms) | `c2_setup.json` | `wan.guard.ticket_connect_window_medians_ms` |
| The guard's 61 checks, all passed | `c2_setup.json` | `wan.guard.checks`, `wan.guard.all_ok` |
| Header-only release: snaplen, hosts, placeholder MACs | the release's `manifest.json` (DATA.md) | `checks`, `mac_placeholders`, `cut` |

## Results

### Does it find real leaks, and only those?

| Number | File | Field |
|---|---|---|
| D1 table: verdict, macro-F1 [CI] per attribute and arm | `leakcheck/tls_control_<arm>_own/report.json` | `attributes.<attr>.verdict`, `.analysis.macro_f1`, `.analysis.ci_lo`, `.analysis.ci_hi` |
| Chance + margin (role 0.38, workflow 0.30, topology 0.38) | same | `attributes.<attr>.threshold` |
| p = 0.01 | same | `attributes.<attr>.validation.permutation.p_value` |
| FP 0/99 per row; 0 of 594, 147 INCONCLUSIVE | same | `attributes.<attr>.validation.permutation.null_verdicts` (summed over 3 attributes × 2 arms) |
| TLS − cleartext: workflow −0.046 [−0.105, +0.015], role +0.001 | `tls_control_own.json` | `results.<attr>.tls_minus_clear.diff`, `.ci_lo`, `.ci_hi` |
| Cleartext → TLS transfer 0.478 | `tls_control_own.json` | `results.workflow.clear_to_tls.macro_f1` |
| +8.6% bytes, +4.9% packets | `tls_control_own.json` | `overhead.bytes_ratio`, `overhead.packets_ratio` |
| D2 table: verdict, macro-F1 [CI], p per cell and attribute | `leakcheck/c2_<arm>_<view>/report.json`; `paper2_tool_eval_c2.json` | report: as for D1; evaluation: `arms.<cell>.attributes.<attr>.full.leakcheck` |
| Recall, false-negative rate, false-positive rate, precision (with CIs) | `paper2_tool_eval.json`, `paper2_tool_eval_c2.json` | `summary.full_data.<method>` |
| Known leaks and non-leaks per cell, and why (D2: by construction, k-FP, first-request rule) | `paper2_tool_eval_c2.json` | `reference.cells` |
| Permuted-label verdicts per cell | both evaluations | `arms.<cell>.attributes.<attr>.permuted.<method>` |
| `audit_null` (the injected random attribute) | `paper2_tool_eval_c2.json`; the C2 reports | `arms.<cell>.attributes.audit_null.full`; `attributes.audit_null` |
| Cells only leakcheck flags ("beyond the baselines") | `paper2_tool_eval_c2.json` | `summary.beyond_baselines` |

### Does it explain the leak?

| Number | File | Field |
|---|---|---|
| D1 TLS workflow: first request alone 0.582 vs 0.613 | `leakcheck/tls_control_tls_own/report.json` | `attributes.workflow.attribution.single_request_size.macro_f1`, `.matches_all` |
| D1 cleartext: first request 0.069 below all features | `leakcheck/tls_control_clear_own/report.json` | `attributes.workflow.attribution.single_request_size` (against `analysis.macro_f1`) |
| Role carried by timing (0.974 vs 0.991) | `leakcheck/tls_control_tls_own/report.json` | `attributes.role.attribution.families.timing` |
| D2: the family carrying each LEAK | `paper2_tool_eval_c2.json` | `summary.carried_by` (each family's F1 alone and whether it matches all) |
| The hint per finding | the reports | `attributes.<attr>.mitigations` |

### Does it see what a mitigation fixes and misses?

| Number | File | Field |
|---|---|---|
| Verdict per attribute, unpadded vs padded, per view | the C2 reports; `paper2_tool_eval_c2.json` | as above, per `<arm>` |
| sensor_analysis vs fault_diagnosis, all features and timing alone | `paper2_tool_eval_c2.json` | `summary.pair.<cell>.all`, `.timing` (`arms.<cell>.pair` in full) |
| Input size from the first request: error per arm and estimator | `paper2_tool_eval_c2.json` | `summary.input_size.<cell>`; per task type `arms.<cell>.input_size.estimators.<estimator>.per_class` |
| Padding: buckets the first requests reached, overhead | `c2_setup.json` (from `data/raw_c2/design_check_seq.json`) | `padding_check.per_arm` |
| Padding's cost on the wire: bytes and packets per trace, per arm and view | `c2_setup.json` | `on_wire.per_arm.<arm>.<view>` |

### How many traces does an auditor need?

| Number | File | Field |
|---|---|---|
| Verdict shares at 5, 10, 20, 30 and 50 per class (figure) | both evaluations; `paper2_csv/sample_size.csv` | `arms.<cell>.attributes.<attr>.sample_size.<n>` |
| Recall and false-positive rate at each n | both evaluations; `paper2_csv/sample_size_summary.csv` | `summary.sample_size.<n>` |
| D2 coverage (agreement with leakcheck's own full-data verdict) | `paper2_tool_eval_c2.json`; same CSV | `summary.coverage.<n>` |

### What do the baselines report?

| Number | File | Field |
|---|---|---|
| sslyze and testssl.sh on the nine C2 endpoints | `tls_scanners_summary.json` (from `tls_scanners/`) | `groups` |
| k-FP and the first-request rule, per cell | both evaluations | `arms.<cell>.attributes.<attr>.full.kfp_rf`, `.full.first_request` |

### Cost

| Number | File | Field |
|---|---|---|
| Laptop: total, analysis, peak memory per worker | the reports; `paper2_csv/runtime.csv` | `runtime.total_s`, `runtime.stages_s`, `runtime.peak_rss_mb`, `runtime.peak_rss_children_mb`, `runtime.workers` |
| Raspberry Pi 5: the same audit | `leakcheck_pi/<audit>/report.json`, `leakcheck_pi/machine_c2.txt`, `leakcheck_pi/time_*.txt` | as above; `/usr/bin/time -v` gives the maximum resident set |
| Pi and laptop give the same verdicts and scores | `scripts/compare_reports.py PI MAC` | exit 0, "every compared field matches" |

## Appendix

| Item | File |
|---|---|
| Example rule | `a2a_leakcheck/rules.yaml` |
| Excerpt of a D2 report | `leakcheck/c2_lan_padmax_v2/report.md` |
| Example captures and their expected reports | `examples/`, `examples/expected/` |
| Data release: archives and checksums | DATA.md, "Paper 2 archive" |
