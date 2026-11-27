# Paper 2: where each number comes from

Every number in paper 2 (a2a-leakcheck, SafeIoT Track 1) and the file that holds it. All files are
under `data/results/` unless the path says otherwise. `scripts/reproduce_paper2.sh` rebuilds them
from the released data and compares each with the committed one, in six sections: `v1.0` (the
tables from "Data and setup" to "Review checks"), `round2`, `d3`, `b3`, `c2b1m` and `c2b2`. `scripts/export_paper2_csv.py`
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

Draft 1.1 (Nov 24) quotes a2a-leakcheck 0.3.0's numbers: the permutation test by prompt group,
"matches all features" as non-inferiority, and the accounting as 18 learned leaks and 12 structural
checks (`paper2_round2.json`, section a12). [Draft 1.1, number by number](#draft-11-nov-24-number-by-number)
maps each of its numbers to a file and field. The tables from "Data and setup" to "Review checks"
are v1.0's map (the permutation test by sample), kept for `reproduce_paper2.sh`; [D3](#d3-reply-shaping-c2b1--c2b1x)
and [B3](#b3-a-second-day-of-lan-c2b3) are round 2's collections.

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

## D3: reply shaping (C2B1 + C2B1X)

Two collections on C2's testbed (docs/ROUND2_SESSIONS.md): C2B1, 500 traces with 8 KB requests
(`lan_padmax`) alternating with 500 that also shape replies (`lan_shaped`), 125 per task type each;
C2B1X, 2,000 more shaped traces with new prompts.

| Number | File | Field |
|---|---|---|
| The shape: reply cap 2,048 encoded bytes, release 14 s after the request, 16 events 0.05 s apart, one artifact | `b1_shape_calibration.json` | `shape`, `cut.cap`, `late.deadline_s`, `overhead.events`, `release_s` |
| No C2 reply would have been cut or late: largest 1,515 B, longest cloud call 9.9 s | `b1_shape_calibration.json` | `by_task_type.<type>.bytes_max` (`cut.cap` − `cut.margin_bytes`), `late.answer_s_max`, `cut.n`, `late.n` |
| Shaped replies identical on the wire (16,902 B; requests 10,116 B), none cut or overrun | `b1_shaping_overhead.json` (C2B1, 375), `c2b1x_shaping_overhead.json` (C2B1X, 1,500) | `checks.identical.replies`, `.reply_bytes`, `.request_bytes`; `checks.cut_overrun.cut`, `.overrun` |
| Release time: median 14.770 s against 14.762 expected; the latest 46.6 ms (C2B1) and 94.6 ms (C2B1X) after the median | same | `checks.release.median_s`, `.expected_s`, `.max_s` − `.median_s`, `.spread_ms`, `.ok` (C2B1X fails on that one trace) |
| Cost per task type: trace bytes (163.2 → 32.4 KB, ratio 0.199 per escalated type) and seconds (7.4 to 10.8 s longer) | same | `overhead.<type>.trace_bytes`, `.trace_bytes_ratio`, `.total_s`, `.cloud_s`, `.release_s`; the medians from `control_runs[].trace_bytes` and `runs[].trace_bytes` |
| C2B1's audits: per arm, view and part (all, pair, escalated_only), verdict, macro-F1 [CI], p, carried by; the CI gate of each shaped audit against `lan_padmax` | `b1_audits.json`; reports in `leakcheck/c2b1_*` | `runs.c2b1_<arm>_<view>[_<part>].attributes.<attr>`, `.exit_code`, `.baseline` (`changes`, `new_leaks`, `needs_review`, `resolved`) |
| Sensor vs fault pooled over C2B1's and C2B1X's shaped traces (625 per class), against C2B1's `lan_padmax` | `b1_pair_pooled.json`; reports in `leakcheck/c2b1_c2b1x_*` | `runs.c2b1_c2b1x_lan_shaped_<view>_pair.attributes.task_type`, `.baseline`, `.exit_code`; the traces per collection: `arms.lan_shaped.sources` |
| What carries the pooled pair at V1 (sizes and counts each match all features; timing does not) | `leakcheck/c2b1_c2b1x_lan_shaped_v1_pair/report.json` | `attributes.task_type.attribution.families.<family>.matches_all` |
| Power: permuted sensor vs fault on C2 `lan_padmax_v2` at 125 and 250 per class (20 draws each), predicted 375 and 500, and measured at 375 (`lan_padmax` and `lan_pad` pooled) | `b1_power.json` | `measured.<n>.verdicts`, `.ci_hi_median`; `predicted.<n>.ci_no_leak`; `pooled_check.verdicts` |
| Size check: C2 `lan_padmax` at C2B1's 125 per task type (10 draws by prompt group), against C2B1's `lan_padmax` | `b1_size_check.json` | `summary.<task>_<view>.macro_f1_median`, `.macro_f1_min`, `.macro_f1_max`, `.b1_minus_median`, `.b1_draws_below`; the full C2 cell `full.<task>_<view>` |

## B3: a second day of `lan` (C2B3)

C2's unpadded arm (8100) again, 1,000 traces on Nov 24, new prompts (seed offset 33000); 23
`procedure_lookup` and 4 `alert_triage` prompts also occur in C2 (docs/PROMPT_REGISTRY.md).

| Number | File | Field |
|---|---|---|
| B3's own audits at V1 and V2: task_type, escalated, cloud_role, audit_null; sensor vs fault; the escalated task types | `b3_audits.json`; reports in `leakcheck/c2b3_lan_*` | `runs.c2b3_lan_<view>[_pair\|_escalated_only].attributes.<attr>` (`verdict`, `macro_f1`, `ci`, `p`, `carried_by`) |
| C2's within-session figures beside them | `paper2_round2.json` | `sections.a7["lan_<view> / <task>"].seed_42` |
| Cross-session transfer, C2 → B3 and B3 → C2 per view: macro-F1 [CI over the test side's prompt groups], p of the transfer's permutation test, verdict | `b3_cross_session_c2_to_b3_<view>.json`, `b3_cross_session_b3_to_c2_<view>.json` | `attributes.<attr>.transfer` (`macro_f1`, `ci`, `p`, `verdict`, `null_mean`) |
| Test traces dropped because their prompt is in the training session (29 or 30; 25 or 26 among escalated tasks) | same | `attributes.<attr>.test.dropped_shared` |
| The test session's own figure without those traces; C2's a7 figure | same | `attributes.<attr>.within_test`; `reference.tasks.<task>` |

## C2B1M: a matched, held-out test of reply shaping (pre-registered)

One collection on Nov 25, pre-registered in docs/PREREG_C2B1M.md (def5d6a0). sensor_analysis and
fault_diagnosis only: 625 shaped traces per class (`lan_shaped`) and 250 padded per class (`lan_padmax`),
interleaved on the same new prompts (seed offset 34000). Not in draft 1.1.

| Number | File | Field |
|---|---|---|
| Primary: the shaped pair at V2, INCONCLUSIVE 0.520 [0.494, 0.547], p 0.050 | `c2b1m_audits.json`; `leakcheck/c2b1m_lan_shaped_v2_pair/report.json` | `runs.c2b1m_lan_shaped_v2_pair.attributes.task_type` (`verdict`, `macro_f1`, `ci`, `p`) |
| Control: the padded pair at V2, LEAK 0.672 [0.630, 0.712], p 0.01 | `c2b1m_audits.json` | `runs.c2b1m_lan_padmax_v2_pair.attributes.task_type` |
| Secondary: timing alone on the shaped pair at V2, 0.512 [0.486, 0.538]; sizes 0.509, counts 0.509 | `leakcheck/c2b1m_lan_shaped_v2_pair/report.json` | `attributes.task_type.attribution.families.<family>` (`macro_f1`, `ci_lo`, `ci_hi`) |
| Secondary: the shaped pair at V1, INCONCLUSIVE 0.571 [0.542, 0.598], p 0.01 | `c2b1m_audits.json` | `runs.c2b1m_lan_shaped_v1_pair.attributes.task_type` |
| Descriptive: the padded pair at V1, LEAK 0.694 [0.652, 0.733]; the CI gate LEAK to INCONCLUSIVE at both views, exit 0 | `c2b1m_audits.json` | `runs.c2b1m_lan_padmax_v1_pair.attributes.task_type`; `runs.c2b1m_lan_shaped_<view>_pair.baseline`, `.exit_code` |
| Shaping: replies 16,902 B on the wire, 0 cut or late; release median 14.768 s, the latest 1.15 s after it (one trace, kept); trace bytes 32.3 against 163.1 KB, 7.6 to 7.9 s longer | `c2b1m_shaping_overhead.json` | `checks.identical`, `checks.cut_overrun`, `checks.release` (`median_s`, `max_s`, `spread_ms`, `ok`); `overhead.<type>.trace_bytes`, `.total_s` |

## C2B2: the WAN portability check (pre-registered)

One collection on Nov 26, pre-registered in docs/PREREG_C2B2.md (2171e4ba). The IoT set, 250 per task
type in each arm, interleaved on the same new prompts (seed offset 32000):
- `lan_padmax`: 8 KB requests on C2's WAN (6 ms each way);
- `lan_padmax_jl`: the same padding, with 2 ms of dummynet plus N(4, 1.8) ms clipped at 0 each way
  (requests through netem on the Pi, reply events delayed by the cloud agents), and 2 concurrent
  Ollama generations during its tasks only.

Two deviations from the pre-registration are listed in `c2b2_results.md`. Not in draft 1.1.

| Number | File | Field |
|---|---|---|
| Primary: sensor vs fault at V2 on timing alone; control LEAK 0.656 [0.612, 0.699], treatment LEAK 0.682 [0.638, 0.718], p 0.01 each; the control requirement met; the registered reading | `c2b2_results.json` (from `c2b2_audits.json`) | `primary.control`, `primary.treatment` (`verdict`, `macro_f1`, `ci`, `p`), `primary.control_requirement.met`, `primary.reading` |
| Manipulation checks VALID: reply jitter mean 4.01 ms, sd 1.78 (193,014 draws); the cloud × 1.66, × 1.49, × 1.67 under load; reordering 0.62% against 0.38%; the Pi's ACK 4.48 ms later; keeper PASS | `c2b2_results.json`; every check in `c2b2_manipulation.json` | `manipulation.verdict`, `.jitter`, `.slowdown`, `.reorder`, `.netem`, `.keeper`; `checks.<check>` |
| All features at V2, control / treatment: the pair LEAK 0.688 / 0.724, task_type over four types LEAK 0.847 / 0.867 | `c2b2_results.json` | `secondary.pair_all_v2.<arm>`, `secondary.all_all_v2.<arm>` |
| Every audit: both arms at V1 and V2, parts all, pair and escalated_only, all features and timing alone, with the CI gate | `c2b2_audits.json`; reports in `leakcheck/c2b2_*` | `runs.c2b2_<arm>_<view>[_<part>][_timing].attributes.<attr>`, `.baseline`, `.exit_code` |
| The deviations: the pf rules (6d228a42, fc103506) and the guard's tolerance 0.30 (01230d36) | `c2b2_results.json` | `deviations[]` (`when`, `commits`, `what`, `why`, `scope`) |
| The WAN as applied | `c2b2_wan.json` | `emulation.pipes`, `emulation.rules`, `arms`, `jitter`, `load` |

## Draft 1.1 (Nov 24), number by number

Every number in `Paper2-SafeIoT-draft1.1`, in the order it appears, with the file and field it
comes from. "a7", "a12" and the other sections are `paper2_round2.json`'s `sections.<name>`;
`<cell>` is `lan_v1` … `lan_padmax_v2`. A few numbers come from a document or the code, not a
results file; they are marked *doc*.

Draft 1.1 settles the eight places where draft 1.0 differed from the files (cloud role 0.98 and
0.59 in Table 4; the Pi's p and the seed spread, both by group; the sample-size sentences; 1,795 B;
"at equal sample size"; one event per token). Notes on the rest:
- "A CI regression gate can thus run on 100 to 200 traces per class": a reading of two files, not a
  number in one. LEAK from 20 per class in the v1.0 evaluation (`paper2_tool_eval_c2.json`,
  `summary.sample_size.20.recall`), and the review burden at 100 to 200 per task type (a10
  `<n>.audit_rate`, `<n>.inconclusive_rate`).
- "14 of 20 are predicted at 500" counts CI verdicts only (`b1_power.json`, `predicted.500.ci_no_leak`);
  the permutation test, not modelled there, turns about 1 in 20 null draws INCONCLUSIVE on its own
  (`predicted.500.note`).
- "Earning NO LEAK on a two-class attribute takes hundreds of traces per class" (abstract) rests on
  the same three counts: 8 of 20 at 125, 15 of 20 at 375, 14 of 20 predicted at 500.

| Where | Number | Value in the file | File | Field |
|---|---|---|---|---|
| Abstract | all 18 learned and 12 structural leaks | 18 / 0 / 0; 12 / 0 / 0 | `paper2_round2.json` | a12 `learned.leakcheck`, `structural.leakcheck` |
| Abstract | 480 permuted-label tests: no LEAK, 61 INCONCLUSIVE, 419 NO LEAK | 0 / 61 / 419 | `paper2_round2.json` | a12 `negatives.permuted.leakcheck` |
| Abstract | its test rejects at 5.0% | 24 of 480 | `paper2_round2.json` | a11 `methods.leakcheck.p_le_0_05`, `.permuted_draws` |
| Abstract | 8 KB padding: task type 0.89 upstream | 0.889 | `paper2_round2.json` | a7 `["lan_padmax_v2 / task_type"].seed_42.macro_f1` |
| Abstract | a reference shaping defence: sensor vs fault NO LEAK upstream for the primary detector, 625 per class; listed as resolved; a residual signal on the building network | NO LEAK, n 1,250; `resolved: ["task_type"]` | `b1_pair_pooled.json` | `runs.c2b1_c2b1x_lan_shaped_v2_pair.attributes.task_type.verdict`, `.n`; `.baseline.resolved`; V1: `runs.c2b1_c2b1x_lan_shaped_v1_pair.attributes.task_type` (INCONCLUSIVE, p 0.01) |
| Abstract | cuts an escalated task's bytes by 80%; adds 7 to 11 s | ratio 0.199; 7.42 to 10.84 s | `b1_shaping_overhead.json`, `c2b1x_shaping_overhead.json` | `overhead.<type>.trace_bytes_ratio`, `.total_s` |
| Abstract | NO LEAK on a two-class attribute takes hundreds of traces per class | 8, 15 and 14 (predicted) of 20 at 125, 375, 500 | `b1_power.json` | `measured.125.verdicts`, `pooled_check.verdicts`, `predicted.500.ci_no_leak` |
| Abstract | minutes on a laptop, under half an hour on the Pi | 230.4 s; 26:38 | `leakcheck/c2_lan_v1_v030_cost/report.json`; `leakcheck_pi/time_c2_lan_v1.txt` | `runtime.total_s`; "Elapsed (wall clock)" |
| Introduction | the pipeline stage reproduces an audit in about 4 minutes | 4 min 16 s (quick) | *doc* `safeiot/pipeline_harness/a2a-leakcheck/README.md` | "Time from a fresh clone" |
| Related work | Dangol; Pouryousef et al. | | `refs.bib` (the paper) | `dangol2026graph`, `pouryousef2026bench` |
| Introduction, App. A | data DOI 10.5281/zenodo.24238558, all versions; D3 and B3 from version 1.1 | concept DOI; version 1.0 is 24238559 | DATA.md | "Paper 2 archive"; version 1.1: `scripts/package_paper2_data.py --release round2` |
| Table 1 (classes) | task type high (0.85–0.97) | 0.852 to 0.967 | `leakcheck/c2_<arm>_<view>/report.json` (six) | `attributes.task_type.prioritization.effect_size`, `.severity` |
| Table 1 (classes) | escalated high (1.00); cloud role high (0.99–1.00) | 0.997 to 1.000; 0.991 to 0.997 | same | `attributes.escalated.prioritization`, `attributes.cloud_role.prioritization` |
| Table 1, §4 | severity high ≥ 0.6, medium ≥ 0.3 | 0.6, 0.3 | `a2a_leakcheck/rules.yaml` | `severity.high`, `severity.medium` |
| §4 | 195 features per trace, 35 per agent | 195, 35 | any report | `extraction.trace_dims`, `.role_dims` |
| §4 | 5 folds, 1,000 resamples, margin 0.05, 20 per class, 99 permutations by group, δ = 0.05 | | any 0.3.0 report, e.g. `leakcheck/c2b3_lan_v1/report.json` | `parameters.folds`, `.n_boot`, `.margin`, `.min_per_class`, `.permutations`, `.perm_unit`, `.match_margin` |
| §4 | exit codes 3, 4, 5 | | *doc* `docs/LEAKCHECK.md` | "Exit codes and the release policy" |
| §5 | a2a-sdk 0.3.26; Ollama 0.40 | 0.3.26; 0.40.15 (Mac), 0.40.16 (Pi) | `requirements-lock.txt`; *doc* DATA.md | "Versions" |
| §5 | D1: 432 traces per arm | 432 | `leakcheck/tls_control_<arm>_own/report.json` | `extraction.traces` |
| §5 | edge Llama 3.2 1B, 128 tokens; cloud 3B, 256 | | `c2_setup.json` | `models.edge`, `models.cloud` |
| §5 | 6 ms each way; target 22.6 ms | 6.0; 22.59 | `c2_setup.json` | `wan.one_way_ms`, `wan.target_rtt_ms` |
| §5 | 19.7 to 21.1 ms during the collection | 19.66 to 20.63; to 21.10 | `c2_setup.json` | `wan.guard.pi_connect_window_medians_ms`; `wan.wan_checks.*.cloud_end_to_end_ms` |
| §5 | power of two: all first requests between 1 and 8 KB | 262 / 45 / 277 / 166 in 1, 2, 4, 8 KB | `c2_setup.json` | `padding_check.per_arm.lan_pad.by_bucket` |
| §5 | 8 KB: none needed 16 KB | 750 in 8 KB | `c2_setup.json` | `padding_check.per_arm.lan_padmax.by_bucket` |
| §5 | 1,000 per arm, 250 per type, 3,000 traces, 5 h 45 min, no failed task | | `c2_setup.json` | `session.traces`, `.per_task_type`, `.length`, `.failed` |
| §5 | Pi never throttled; 61 WAN checks, all passed | 0; 61, true | `c2_setup.json` | `pi.throttled_traces`; `wan.guard.checks`, `.all_ok` |
| §5 | input medians 2,799, 3,590, 81, 154 B | 2,798.5, 3,589.5, 81, 154 (halves up) | `c2_setup.json` | `inputs.per_task_type.<type>.median` |
| §5 | 982 distinct prompts | 982 | `paper2_review.json` | `data.C2.arms.lan.prompt_groups` |
| §5 | 750 escalated (500 diagnostics, 250 knowledge), 250 local | | `paper2_tool_eval_c2.json` | `summary.input_size.lan_v1.n`, `.first_request_link` |
| §5 D3 | 500 + 500, 125 per type; 2,000 more shaped | | `b1_audits.json`; `b1_pair_pooled.json` | `arms.<arm>.sources[].per_task_type`; `arms.lan_shaped.sources[1]` |
| §5 D3 | new prompts, none shared with D2 or the first session | | *doc* `docs/PROMPT_REGISTRY.md` | the C2B1X row |
| §5 D3 | cap 2,048 B (D2's largest 1,515); 14 s (D2's longest 9.9 s); 16 events 0.05 s apart | | `b1_shape_calibration.json` | `cut.cap`, `by_task_type.sensor_analysis.bytes_max`; `late.deadline_s`, `late.answer_s_max`; `shape`, `overhead.events` |
| §5 D3 | Nagle on: the stream's end varied by up to 99 ms | 14.787 to 14.886 s | *doc* `docs/ROUND2_SESSIONS.md` | "B1 pilot", the first pilot (`data/pilot_c2b1`) |
| §5 D3 | 1,875 shaped replies, 16,902 B, none cut | 375 + 1,500 | `b1_shaping_overhead.json`, `c2b1x_shaping_overhead.json` | `checks.identical.replies`, `.reply_bytes`; `checks.cut_overrun.cut` |
| §5 D3 | all but two within 27 ms of the median release | C2B1: 374 of 375 within 18 ms; C2B1X: 1,499 of 1,500 within 27 ms | *doc* `docs/ROUND2_SESSIONS.md` | "B1 record", "C2B1X record" (the JSON files hold `median_s`, `min_s`, `max_s`, `spread_ms`) |
| §5 D3 | the two 47 and 95 ms late | 46.6, 94.6 ms | `b1_shaping_overhead.json`, `c2b1x_shaping_overhead.json` | `checks.release.max_s` − `.median_s` |
| §5 | 12 structural cells, 18 learned | | `paper2_round2.json` | a12 `rows` (`kind`) |
| §5, Table 2 | 20 permuted audits per cell and attribute | 20 | `paper2_tool_eval_c2.json` | `parameters.label_perms` |
| Table 2 (accounting) | every row and method | | `paper2_round2.json` | a12 `learned_by_task.<task>.<method>`, `structural.<method>`, `negatives.permuted.<method>`, `negatives.audit_null.<method>` |
| Table 3 (D2) | task type, escalated types, sensor vs fault, escalated, cloud role, audit null per cell; the INCONCLUSIVE marks | | `paper2_round2.json` | a7 `["<cell> / <task>"].seed_42.macro_f1`, `.verdict` (`<task>`: `task_type`, `escalated_only`, `pair`, `escalated`, `cloud_role`, `audit_null`) |
| Table 3 (D2) | sensor vs fault, timing: 0.78 / 0.75, 0.80 / 0.78 | 0.782, 0.748, 0.798, 0.784 | `paper2_round2.json` | a3 `learned["<cell> / pair"].families.timing.macro_f1` |
| Table 4 (D3) | padded only and padded + shaped, per attribute and view | | `b1_audits.json` | `runs.c2b1_<arm>_<view>[_pair\|_escalated_only].attributes.<attr>.verdict`, `.macro_f1` |
| Table 4 (D3) | pooled sensor vs fault, I 0.54 and N 0.51 | 0.544, 0.514 | `b1_pair_pooled.json` | `runs.c2b1_c2b1x_lan_shaped_<view>_pair.attributes.task_type` |
| Table 4 (D3) | D2 cut to 125 per type loses at most 0.05 | 0.001 to 0.046 | `b1_size_check.json` | `full.<task>_<view>.macro_f1` − `summary.<task>_<view>.macro_f1_median` |
| §6 | 18 learned, 12 structural, none of the 486 non-leaks | | `paper2_round2.json` | a12 `learned`, `structural`, `negatives` |
| §6 | rejects in 24 of the 480 permuted runs (5.0%) | 24 | `paper2_round2.json` | a11 `methods.leakcheck.p_le_0_05` |
| §6 | 120 audits, none would block, 95% CI [0, 0.031]; 54 (45%) to review | | `paper2_round2.json` | a12 `release_blocking.leakcheck` (`audits`, `any_leak`, `any_leak_ci`, `inconclusive_no_leak`, `inconclusive_no_leak_rate`) |
| §6 | 13% of attributes; cloud role 28 of 120 | 0.127; 28 | `paper2_round2.json` | a10 `all.inconclusive_rate`; a11 `by_attribute.leakcheck.cloud_role.inconclusive` |
| §6 | k-FP: interval 0.057 against 0.056, 47 INCONCLUSIVE, 1.5 times faster | 0.0571, 0.0565; 47; 19.1 s against 28.4 s | `paper2_round2.json` | a11 `methods.<method>.ci_width_median`, `.inconclusive`, `.seconds_median` |
| §6 | 14 of the tool's 61 INCONCLUSIVEs are NO LEAKs vetoed by the permutation test | 14 of 61 (47 straddle) | `paper2_round2.json` | a11 `methods.leakcheck.inconclusive_why` ("permutation test disagrees with a NO LEAK") |
| §6 | the first-request rule misses 8 of the 18 | 10 LEAK | `paper2_round2.json` | a12 `learned.first_request` |
| §6 | testssl.sh grades B; SSLyze finds nothing | B; every check false | `tls_scanners_summary.json` | `groups[0].testssl.grade`; `groups[0].sslyze.vulnerable` |
| §6 | D1: LEAK for role, workflow and topology in both arms, 0.58 to 1.00 | 0.577 to 1.000 | `leakcheck/tls_control_<arm>_own/report.json` | `attributes.<attr>.verdict`, `.analysis.macro_f1` |
| §6 | sizes alone match all, no padding and power of two | | `paper2_round2.json` | a3 `learned["<cell> / <task>"].carried_0_3` |
| §6 | input size: median error 0 B; power of two four sizes, 329 B | 0.0; 4, 329.0 | `paper2_tool_eval_c2.json` | `summary.input_size.<cell>.constant.median_abs_error`, `.first_request_distinct` |
| §6 | padding costs 1.8% and 4.2% more bytes at V1 | 1.0176, 1.0420 | `c2_setup.json` | `on_wire.per_arm.<arm>.v1.bytes_ratio_to_lan` |
| §6 | 749 of 750 first requests at 8,488 B | 749 (one at 8,568) | `paper2_review.json` | `input_size.lan_padmax_v1.first_request_sizes.counts` |
| §6 | the 8 KB estimator's error equals the no-traffic guess's, 1,795 B | 1,794.5 B both (halves up) | `paper2_tool_eval_c2.json` | `summary.input_size.lan_padmax_v1.constant.median_abs_error`, `.no_traffic.median_abs_error` |
| §6 | task type 0.90 and 0.89; 0.85 and 0.84 among escalated tasks | 0.898, 0.889; 0.852, 0.842 | `paper2_round2.json` | a7 `["lan_padmax_<view> / task_type"]`, `["lan_padmax_<view> / escalated_only"]` |
| §6 | timing alone matches all: task type at both views; sensor vs fault upstream, 0.78 against 0.79 | 0.784 against 0.788 | `paper2_round2.json` | a3 `learned["lan_padmax_<view> / <task>"].families.timing.matches_all`, `.macro_f1` |
| §6 | 40 timestamp features within 0.022 of the timing family | 40; at most 0.0221 | `paper2_round2.json` | a8 `timestamps_features`; a8 `cells.<cell / task>.timestamps_only.macro_f1` against `.timing.macro_f1` |
| §6 D3 | shaping moves cloud role, the escalated types and sensor vs fault from LEAK to INCONCLUSIVE | | `b1_audits.json` | `runs.c2b1_lan_shaped_*.baseline.changes` |
| §6 D3 | pooled over both shaped sessions, 625 per class, the second without a padded control | 125 + 500 per class | `b1_pair_pooled.json` | `arms.lan_shaped.sources` |
| §6 D3 | pooled upstream 0.514 [0.485, 0.540], p 0.26; V1 0.544 [0.517, 0.571], p 0.01 | | `b1_pair_pooled.json` | `runs.c2b1_c2b1x_lan_shaped_<view>_pair.attributes.task_type.macro_f1`, `.ci`, `.p` |
| §6 D3 | timing alone upstream 0.539 [0.510, 0.569], across the 0.55 bound | 0.5389 [0.5104, 0.5685] | `leakcheck/c2b1_c2b1x_lan_shaped_v2_pair/report.json` | `attributes.task_type.attribution.families.timing.macro_f1`, `.ci_lo`, `.ci_hi` |
| §6 D3 | V1 carried by sizes or counts alone | sizes 0.533, counts 0.531 match; timing 0.509 does not | `leakcheck/c2b1_c2b1x_lan_shaped_v1_pair/report.json` | `attributes.task_type.attribution.families.<family>.matches_all` |
| §6 D3 | escalation 1.00; task type 0.51 upstream | 1.000; 0.512 | `b1_audits.json` | `runs.c2b1_lan_shaped_<view>.attributes.escalated`, `.task_type` |
| §6 D3 | every shaped audit exits 0; the pooled upstream audit lists the pair as resolved | | `b1_audits.json`, `b1_pair_pooled.json` | `runs.*.exit_code`; `runs.*.baseline.resolved`, `.needs_review` |
| §6 D3 | 163.2 → 32.4 KB; 7.4 to 10.8 s longer | | `b1_shaping_overhead.json`, `c2b1x_shaping_overhead.json` | the medians of `control_runs[].trace_bytes` and `runs[].trace_bytes` per escalated type; `overhead.<type>.total_s` |
| §6 D3 | 16 events replace one streamed event per token (up to 256) | 16; 256 | `b1_shape_calibration.json`, `c2_setup.json`; *doc* `agents/base.py` | `overhead.events`; `models.cloud.num_predict`; `_SSE_COALESCE = 1` (one SSE event per token) |
| §6 | 6 to 20 templates per type; every held-out verdict LEAK | 6 (fault_diagnosis) to 20 (procedure_lookup); 12 of 12 | `paper2_round2.json` | a9 `levels`; a9 `cells.<cell / task>.template.verdict` |
| §6 | five more fold seeds: 34 of 36 verdicts repeat | | `paper2_round2.json` | a7 `["<cell> / <task>"].agree_with_42`, `.verdicts` |
| §6 | the Pi's null model moves one p from 0.08 to 0.20; seeds 0.08 to 0.91 | by group (0.3.0) | `paper2_pvalue_compare.json`, `paper2_pvalue_mac.json` | `stages` (the group rows, "…/rf-light: p"); `seed_spread_group` |
| §6 B3 | 1,000 tasks; D2's verdicts in all 12 cells, within 0.025 | 12 of 12; at most 0.024 | `b3_audits.json` against `paper2_round2.json` | `runs.c2b3_lan_<view>[_<part>].attributes.<attr>`; a7 `["lan_<view> / <task>"].seed_42` |
| §6 B3 | across sessions every verdict holds, the learned tasks lose 0.08 to 0.27; sensor vs fault 0.66 to 0.73 | 0.078 to 0.273; 0.661, 0.668, 0.726, 0.732 | `b3_cross_session_*.json` | `attributes.<task>.transfer.macro_f1`, `.verdict`, against the test session's figure (`b3_audits.json` for C2 → B3, a7 for B3 → C2) |
| §6 | in version 0.1's evaluation every subsample of 20 or more per class of the task type, escalation and cloud role read LEAK | 1.00 (360 of 360 at 20) | `paper2_tool_eval_c2.json` | `summary.sample_size.<n>.recall` (the permutation test by sample) |
| §6 | audits with an INCONCLUSIVE 0.97 at 50 per type to 0.48 at 200; per attribute 0.61 to 0.17 | 0.967, 0.483; 0.608, 0.167 | `paper2_round2.json` | a10 `<n>.audit_rate`, `<n>.inconclusive_rate` |
| §6 | no signal: 8 of 20 NO LEAK at 125 per class, 15 of 20 at 375; 14 of 20 predicted at 500 (margin 0.05) | | `b1_power.json` | `measured.125.verdicts`; `pooled_check.verdicts`; `predicted.500.ci_no_leak` |
| §6 | a CI gate on 100 to 200 per class; certifying NO LEAK needs several hundred | see the notes above | `paper2_tool_eval_c2.json`, `paper2_round2.json`, `b1_power.json` | `summary.sample_size`; a10; `measured`, `pooled_check`, `predicted` |
| §6 Cost | 230 s on a laptop, 14 workers, 323 MB each | 230.4 s, 14, 322.75 MB | `leakcheck/c2_lan_v1_v030_cost/report.json` | `runtime.total_s`, `.workers`, `.peak_rss_children_mb` |
| §6 Cost | 26 min 38 s on the Pi, version 0.1, 4 workers, 212 MB | 26:38.45; 217,088 kB | `leakcheck_pi/time_c2_lan_v1.txt`, `leakcheck_pi/c2_lan_v1/report.json` | "Elapsed (wall clock)", "Maximum resident set size"; `version`, `runtime.workers` |
| §7 | the padded arm 0.08 to 0.14 below D2's at equal sample size | −0.076 to −0.138 | `b1_size_check.json` | `summary.<task>_<view>.b1_minus_median` |
| App. B | all 0.889 [0.870, 0.907]; sizes 0.875 [0.855, 0.892]; timing 0.892 [0.874, 0.910]; first request 0.375 [0.365, 0.385]; carried by timing | | `leakcheck/c2_lan_padmax_v2/report.md` (0.1.0); the same carried by under 0.3.0's rule | the task_type table; a3 `learned["lan_padmax_v2 / task_type"].carried_0_3` |

## Appendix

| Item | File |
|---|---|
| Example rule | `a2a_leakcheck/rules.yaml` |
| Excerpt of a D2 report | `leakcheck/c2_lan_padmax_v2/report.md` |
| Example captures and their expected reports | `examples/`, `examples/expected/` |
| Data release: archives and checksums | DATA.md, "Paper 2 archive" |
