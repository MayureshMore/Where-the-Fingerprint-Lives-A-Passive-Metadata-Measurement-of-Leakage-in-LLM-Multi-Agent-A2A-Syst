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

D1 (the TLS control) is measured as a2a-leakcheck measures, every payload byte counted once (TCP
retransmissions dropped), since Nov 14. The earlier D1 results, with retransmitted segments counted
again, are in `superseded/d1_before_dedup/`; `d1_dedup_comparison.{json,md}` sets every D1 number
below old against new, and counts the TCP retransmissions that counting each byte once drops in each arm
(`retransmissions.<tls|clear>`: sizes, direction, after the last data packet, per workflow and topology with
chi-square and Kruskal-Wallis tests), and sets the old and new features against each other on the same folds and
bootstrap resamples (`same_folds_old_vs_new.<arm>.<task>.new_minus_old`). Paper 2 reports the TLS − cleartext
paired difference under both measures (`rows`, "TLS − cleartext") and does not claim that TLS lowers workflow
leakage.

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
| FP 0/99 per row; 0 of 594, 152 INCONCLUSIVE | same | `attributes.<attr>.validation.permutation.null_verdicts` (summed over 3 attributes × 2 arms) |
| TLS − cleartext: workflow −0.083 [−0.137, −0.025], role +0.001 | `tls_control_own.json` | `results.<attr>.tls_minus_clear.diff`, `.ci_lo`, `.ci_hi` |
| TLS − cleartext with retransmissions counted: workflow −0.046 [−0.105, +0.015] | `d1_dedup_comparison.json` | `rows` ("workflow: TLS − cleartext [CI]", old) |
| Cleartext → TLS transfer 0.474 | `tls_control_own.json` | `results.workflow.clear_to_tls.macro_f1` |
| +8.6% bytes, +4.8% packets | `tls_control_own.json` | `overhead.bytes_ratio`, `overhead.packets_ratio` |
| D2 table: verdict, macro-F1 [CI], p per cell and attribute | `leakcheck/c2_<arm>_<view>/report.json`; `paper2_tool_eval_c2.json` | report: as for D1; evaluation: `arms.<cell>.attributes.<attr>.full.leakcheck` |
| Recall, false-negative rate, false-positive rate, precision (with CIs) | `paper2_tool_eval.json`, `paper2_tool_eval_c2.json` | `summary.full_data.<method>` |
| Known leaks and non-leaks per cell, and why (D2: by construction, k-FP, first-request rule) | `paper2_tool_eval_c2.json` | `reference.cells` |
| Permuted-label verdicts per cell | both evaluations | `arms.<cell>.attributes.<attr>.permuted.<method>` |
| False LEAKs on permuted labels per sample size, pooled over all cells, attributes and views (Wilson 95% CI; the draws are not fully independent) | `paper2_permuted_false_leaks.json` | `pooled.per_size`, `pooled.per_size_by_classes`, `independence` |
| The permutation test behind each draw (99 permutations, smallest p 0.01) | `paper2_permuted_false_leaks.json` | `test` |
| Each false LEAK: arm, view, attribute, size, draw, p, macro-F1 [CI], prompt groups | `paper2_false_leak_draws.json` | `false_leaks`; `all_counts_reproduced` |
| `audit_null` (the injected random attribute) | `paper2_tool_eval_c2.json`; the C2 reports | `arms.<cell>.attributes.audit_null.full`; `attributes.audit_null` |
| Cells only leakcheck flags ("beyond the baselines") | `paper2_tool_eval_c2.json` | `summary.beyond_baselines` |

### Does it explain the leak?

| Number | File | Field |
|---|---|---|
| D1 TLS workflow: first request alone 0.572 vs 0.577 | `leakcheck/tls_control_tls_own/report.json` | `attributes.workflow.attribution.single_request_size.macro_f1`, `.matches_all` |
| D1 cleartext: first request 0.072 below all features | `leakcheck/tls_control_clear_own/report.json` | `attributes.workflow.attribution.single_request_size` (against `analysis.macro_f1`) |
| Role carried by timing (0.972 vs 0.991) | `leakcheck/tls_control_tls_own/report.json` | `attributes.role.attribution.families.timing` |
| D2: the family carrying each LEAK | `paper2_tool_eval_c2.json` | `summary.carried_by` (each family's F1 alone and whether it matches all) |
| The hint per finding | the reports | `attributes.<attr>.mitigations` (rules: `a2a_leakcheck/rules.yaml`) |
| The C2 audits with the C2 rules: every verdict and score unchanged, only the hints | `leakcheck/c2_rerun_compare.json` | `<audit>.same_apart_from_hints`, `.hints_changed`; the reports the evaluation read: `superseded/c2_audits_eb8fbbfb/` |

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

### Review checks (C2)

`scripts/paper2_review.py` → `paper2_review.{json,md}`: no new collection; the committed C2 evaluation
and reports, and new runs of the same verdict rule on the C2 captures.

| Number | File | Field |
|---|---|---|
| Every known leak (18) and known non-leak (480 permuted draws + 6 audit_null): LEAK / INCONCLUSIVE / NO LEAK per method | `paper2_review.json` | `accounting.positive_totals`, `.negative_totals`, `.positives`, `.negatives_by_attribute` |
| Release-blocking rate: permuted audits (cell × draw index) with any LEAK | `paper2_review.json` | `accounting.release_blocking.methods.<method>` |
| No permuted labelling reused by the permutation tests | `paper2_review.json` | `reuse.<cell>/<attr>` |
| task_type on the escalated tasks only, all features and timing alone | `paper2_review.json` | `escalated_task_type.<cell>.all`, `.timing`, `.attribution` |
| Input size: constant overhead − no traffic, paired CI; median and P90 per task type | `paper2_review.json` | `input_size.<cell>.constant_minus_no_traffic`, `.errors` |
| lan_padmax's two first-request sizes, by trace | `paper2_review.json` | `input_size.<cell>.first_request_sizes` |
| "Matches all features": the rule; padmax task_type; sensor vs fault, all − family per cell | `paper2_review.json` | `matches_all.rule`, `.padmax_task_type`, `.pair.<cell>.attribution` |
| Distinct prompts, prompt groups and template pools, C2 and D1 | `paper2_review.json` | `data.C2`, `data.D1` |

### Round 2 (reviewers' checks, a2a-leakcheck 0.3.0)

`scripts/paper2_round2.py` → `paper2_round2.{json,md}`, merged from parts run at one clean commit
(`parts`); no new collection. 0.3.0's defaults throughout: the permutation test by prompt group, and
"matches all features" as non-inferiority (upper bound of the paired 95% CI of all − family ≤ 0.05).
`scripts/pvalue_diagnostics.py` → `paper2_pvalue_{mac,pi}.json`, `paper2_pvalue_compare.{json,md}` (A6).

| Number | File | Field |
|---|---|---|
| Main accounting: learned rows (task_type, sensor vs fault, escalated-only) per method | `paper2_round2.json` | `sections.a12.learned`, `.learned_by_task.<task>`, `.rows` |
| Structural checks (escalated, cloud_role) per method | `paper2_round2.json` | `sections.a12.structural`, `.structural_by_task.<task>` |
| Known non-leaks with group-level permutation (480 draws, 6 audit_null), next to v1.0's | `paper2_round2.json` | `sections.a12.negatives.<set>.<method>`; v1.0: `sections.a12.current.negative_totals` |
| Release blocking over the permuted audits | `paper2_round2.json` | `sections.a12.release_blocking.<method>` |
| All-zero V2 windows per arm and task type | `paper2_round2.json` | `sections.a12.all_zero_windows.<cell>` |
| Groups per class and group sizes, C2 and D1; draw reuse | `paper2_round2.json` | `sections.a4.cells.<cell>.attributes.<attr>.groups_per_class`, `.group_sizes`; `sections.a4.d1`; `sections.a4.cells.<cell>.reuse` |
| "Carried by" under the 0.1.x rule and under non-inferiority; every change | `paper2_round2.json` | `sections.a3.reports.<report / attr>`, `sections.a3.learned.<cell / task>` (`carried_0_1`, `carried_0_3`, `changed`) |
| GBT as null model, and the adaptive 99→999 rule: verdict changes, runtime, Pi estimate | `paper2_round2.json` | `sections.a5.gbt_99`, `.rf_light_adaptive_999`, `.rows`, `.pi_over_mac` |
| Pi against Mac p-value: the first stage that differs; versions, BLAS, threads; spread over 10 seeds | `paper2_pvalue_compare.json`, `paper2_pvalue_{mac,pi}.json` | `first_difference`, `stages`; `environment`; `seed_spread_<unit>` |
| Repeated grouped splits: verdict agreement and ranges | `paper2_round2.json` | `sections.a7.<cell / task>` |
| Timing family columns that depend on bytes or direction; timestamps-only against timing | `paper2_round2.json` | `sections.a8.timing_columns`; `sections.a8.cells.<cell / task>` |
| Template-held-out against prompt-held-out | `paper2_round2.json` | `sections.a9.cells.<cell / task>.prompt`, `.template`; factors `sections.a9.factor`, `.levels` |
| INCONCLUSIVE rate per attribute and per audit against traces per task type | `paper2_round2.json` | `sections.a10.<n>` (n = 50, 100, 150, 200, all) |
| k-FP against a2a-leakcheck: INCONCLUSIVE sources, CI widths, agreement, runtime, plain k-FP | `paper2_round2.json` | `sections.a11.methods`, `.agreement`, `.plain_kfp`, `.runtime_task_type` |

## Appendix

| Item | File |
|---|---|
| Example rule | `a2a_leakcheck/rules.yaml` |
| Excerpt of a D2 report | `leakcheck/c2_lan_padmax_v2/report.md` |
| Example captures and their expected reports | `examples/`, `examples/expected/` |
| Data release: archives and checksums | DATA.md, "Paper 2 archive" |
