#!/usr/bin/env bash
#
# reproduce_paper2.sh — rebuild the numbers of paper 2 (a2a-leakcheck; draft 1.1) from the released data
# and compare each with the committed one. Like scripts/reproduce.sh it writes to a sandbox and never to
# data/results/. docs/PAPER2_NUMBERS.md maps every number in the paper to its file and field.
#
# Four sections (--section NAME[,NAME...]; all four by default):
#
#   v1.0    The v1.0 path: the numbers draft 1.1 still quotes from the first evaluation, made with
#           a2a-leakcheck 0.1.x and its permutation test by sample (these audits pin --perm-unit sample):
#           Table 1's severities, D1, the C2 setup and input sizes, the sample-size subsampling and
#           App. B's excerpt.
#             1. examples        leakcheck on the examples in the repo: the TLS control's leaky and
#                                permuted sets; C2's c2_lan, c2_lan_padmax and c2_ci_baseline at the
#                                upstream view (--vantage v2, task_type), with the tool's defaults   ~3 min
#             2. TLS control     leakcheck on both arms, own connections → leakcheck/tls_control_*_own;
#                                scripts/evaluate_tls_control.py → tls_control_own                   ~10 min
#             3. C2 setup        scripts/c2_setup_numbers.py → c2_setup; the TLS scanners' committed
#                                output → tls_scanners_summary                                       seconds
#             4. C2 audits       the three arms at both views → leakcheck/c2_<arm>_<view>, then the
#                                review checks (scripts/paper2_review.py → paper2_review)            ~30 min
#             5. tool evaluation scripts/evaluate_leakcheck.py → paper2_tool_eval, paper2_tool_eval_c2;
#                                the false-LEAK draws and summary                          full only, a day
#             6. CSV             scripts/export_paper2_csv.py → paper2_csv/, file by file       full only
#   round2  Round 2 with a2a-leakcheck's defaults (the permutation test by prompt group, the
#           non-inferiority match rule): Tables 2 and 3, the accounting, k-FP, the robustness checks.
#           scripts/paper2_round2.py in its four parts, then merged → paper2_round2:
#             a3, a8, a9   ~1 h (also in --quick: compared section by section)
#             a4           ~9.6 h      a5, a7   ~5.8 h      a10, a11   ~6.2 h          full only
#           and A6 on this machine: features of C2 lan at V1, scripts/pvalue_diagnostics.py dump
#           → paper2_pvalue_mac (the seed spread)                                                  ~3 min
#   d3      Reply shaping, C2B1 + C2B1X (Table 4): b1_shape_calibration; the shaping checks and their
#           overhead (b1_shaping_overhead, c2b1x_shaping_overhead); b1_power; b1_audits and its 12
#           reports (leakcheck/c2b1_*); b1_pair_pooled and its 2 reports (leakcheck/c2b1_c2b1x_*,
#           the timing family alone included); b1_size_check                                        ~1 h
#   b3      A second day of lan, C2B3: b3_audits and its 6 reports (leakcheck/c2b3_*); the features of
#           both sessions per view; the four cross-session runs (b3_cross_session_*)                ~1 h
#
# --quick: v1.0's stages 1 to 4, round 2's a3, a8, a9 and A6, then d3 and b3: about 5 h. The final line
# names what --quick does not rebuild.
#
# Every input a section needs is checked first; if one is missing the script stops with the list and
# where each comes from (exit 2), before running anything. A stage that fails, or a number that differs,
# makes the run FAIL (exit 1); PASS means every stage selected ran and every number compared matched.
# Compared (scripts/compare_paper2_results.py): verdicts, macro-F1 with its interval, p-values and
# every other number; not compared: dates, commits, run times, memory, the machine and file paths.
# The committed numbers were made on macOS arm64. On another platform the permutation test's null model
# (rf-light) can fit differently (A6): null_mean is allowed 0.01, but a p-value that moves is reported
# as DIFFERENT; the GBT's numbers (macro-F1, intervals) do not change.
#
# Not rebuilt here, because they measure live systems or another machine: the TLS scanners
# (baselines/run_tls_scanners.sh), the WAN emulation's round trip (c2_wan_emulation.json, the guard),
# the collection records (docs/ROUND2_SESSIONS.md), the Raspberry Pi's timing (leakcheck_pi) and its
# side of A6 (paper2_pvalue_pi.json, paper2_pvalue_compare.json), and the laptop's run time
# (leakcheck/c2_lan_v1_v030_cost).
#
# Inputs: the paper 2 data release (DATA.md), unzipped into the repository root: Zenodo version 1.0 for
# C2 and the TLS control, version 1.1 for C2B1, C2B1X and C2B3.
#
# Usage:
#   bash scripts/reproduce_paper2.sh                       # every section, in full (about two days)
#   bash scripts/reproduce_paper2.sh --quick               # about 5 h
#   bash scripts/reproduce_paper2.sh --section d3,b3       # some sections (about 2 h)
#   A2A_RESULTS_DIR=data/results_p2 PYTHON=venv/bin/python bash scripts/reproduce_paper2.sh --section v1.0
#
set -u

PY="${PYTHON:-python3}"
QUICK=0
SECTIONS="v1.0,round2,d3,b3"
while [ $# -gt 0 ]; do
    case "$1" in
        --quick) QUICK=1 ;;
        --section) [ $# -ge 2 ] || { echo "--section needs a name" >&2; exit 2; }; SECTIONS="$2"; shift ;;
        --section=*) SECTIONS="${1#--section=}" ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done
for s in $(echo "$SECTIONS" | tr ',' ' '); do
    case "$s" in v1.0|round2|d3|b3) ;; *) echo "unknown section: $s (v1.0, round2, d3, b3)" >&2; exit 2 ;; esac
done
want() { case ",$SECTIONS," in *",$1,"*) return 0 ;; *) return 1 ;; esac; }

CANON="data/results"
SANDBOX="${A2A_RESULTS_DIR:-data/results_paper2_demo}"
case "${SANDBOX%/}/" in
    "$CANON/"*) echo "REFUSING: A2A_RESULTS_DIR ($SANDBOX) is in the canonical $CANON." >&2; exit 2 ;;
esac

# ── the inputs every selected section needs ──────────────────────────────────────────────────────────
V10="Zenodo version 1.0"; V11="Zenodo version 1.1"
from_where() {   # from_where PATH: where a missing input comes from
    case "$1" in
        data/raw_c2|data/raw_c2_pad|data/raw_c2_padmax) echo "$V10, c2-raw-pcaps-headers-only.zip" ;;
        data/raw_tlspair_*) echo "$V10, tlscontrol-raw-pcaps-headers-only.zip" ;;
        data/processed_tlspair_*) echo "$V10, tlscontrol-features-own-dedup.zip" ;;
        data/raw_c2b1_padmax|data/raw_c2b1_shaped) echo "$V11, c2b1-raw-pcaps-headers-only.zip" ;;
        data/raw_c2b1x_shaped) echo "$V11, c2b1x-raw-pcaps-headers-only.zip" ;;
        data/raw_c2b3_lan) echo "$V11, c2b3-raw-pcaps-headers-only.zip" ;;
        *) echo "the repository (git checkout)" ;;
    esac
}
C2="data/raw_c2 data/raw_c2_pad data/raw_c2_padmax"
D1="data/raw_tlspair_tls data/raw_tlspair_clear"
NEED=""
want v1.0 && NEED="$NEED $C2 $D1 data/processed_tlspair_clear_own_dedup data/processed_tlspair_tls_own_dedup
    examples/leaky examples/permuted examples/c2_lan examples/c2_lan_padmax examples/c2_ci_baseline
    $CANON/tls_scanners $CANON/paper2_tool_eval_c2.json"
want v1.0 && [ "$QUICK" -eq 0 ] && NEED="$NEED $CANON/paper2_csv"
want round2 && NEED="$NEED $C2 $D1 $CANON/leakcheck/c2_lan_v1/report.json $CANON/leakcheck/tls_control_tls_own/report.json
    $CANON/leakcheck/tls_control_clear_own/report.json $CANON/leakcheck_pi/c2_lan_v1/report.json
    $CANON/paper2_review.json $CANON/paper2_round2.json $CANON/paper2_pvalue_mac.json"
want d3 && NEED="$NEED $C2 data/raw_c2b1_padmax data/raw_c2b1_shaped data/raw_c2b1x_shaped $CANON/b1_audits.json"
want b3 && NEED="$NEED data/raw_c2 data/raw_c2b3_lan $CANON/paper2_round2.json $CANON/b3_audits.json"
MISSING=""
for p in $NEED; do
    case " $MISSING " in *" $p "*) continue ;; esac
    [ -e "$p" ] || MISSING="$MISSING $p"
done
if [ -n "$MISSING" ]; then
    echo "FAIL: required inputs missing for --section $SECTIONS; nothing was run:" >&2
    for p in $MISSING; do echo "  $p   (from $(from_where "$p"))" >&2; done
    echo "Unzip the archives into the repository root (DATA.md), then run again." >&2
    exit 2
fi

RUN="$SANDBOX/$(date +%Y%m%d_%H%M%S)"     # outputs of round2, d3 and b3: the scripts never write over a file
export A2A_RESULTS_DIR="$SANDBOX"
mkdir -p "$SANDBOX/leakcheck" "$RUN/leakcheck" logs
LOG="logs/reproduce_paper2_$(date +%Y%m%d_%H%M%S).log"
echo "sections: $SECTIONS$([ "$QUICK" -eq 1 ] && echo ' (quick)')   sandbox: $SANDBOX   run: $RUN   log: $LOG"
echo "python: $("$PY" --version 2>&1)   commit: $(git rev-parse --short HEAD 2>/dev/null)"

FAIL=0
NOT_RUN=""
compare() {   # compare NEW COMMITTED [--sections a,b]
    if [ ! -f "$2" ]; then echo "  FAILED: no committed $2 to compare"; FAIL=1; return; fi
    if [ ! -f "$1" ]; then echo "  FAILED: $1 was not written (see $LOG)"; FAIL=1; return; fi
    "$PY" scripts/compare_paper2_results.py "$@" || FAIL=1
}

run() {   # run NAME COMMAND...: a stage; its output and errors go to the log
    local name="$1"; shift
    echo "[run ] $name"
    echo "### $name: $*" >> "$LOG"
    "$@" >> "$LOG" 2>&1 || { echo "  FAILED: $name (see $LOG)"; FAIL=1; return 1; }
}

run_report() {   # run_report NAME CAPTURE_DIR COMMITTED_DIR [leakcheck args]: a v1.0 audit into $SANDBOX/leakcheck
    local name="$1" dir="$2" committed="$3"; shift 3
    run "$name" "$PY" -m a2a_leakcheck run "$dir" --out "$SANDBOX/leakcheck/$name" --html "$@" \
        && compare "$SANDBOX/leakcheck/$name/report.json" "$committed/report.json"
}

run_check() {   # run_check NAME OUTPUT_JSON COMMAND...: a check script that exits 1 when one of its checks fails; its
                #   output is then compared like any other (C2B1X's release-time check fails on one trace, as committed)
    local name="$1" outj="$2" rc; shift 2
    echo "[run ] $name"
    echo "### $name: $*" >> "$LOG"
    "$@" >> "$LOG" 2>&1; rc=$?
    if [ "$rc" -eq 0 ]; then return 0; fi
    if [ "$rc" -eq 1 ] && [ -f "$outj" ]; then echo "  (exit 1: one of its checks fails; compared with the committed result)"; return 0; fi
    echo "  FAILED: $name (exit $rc, see $LOG)"; FAIL=1; return 1
}

compare_reports() {   # compare_reports PREFIX: every committed leakcheck/PREFIX* report against the rebuilt one
    local n=0 d
    for d in "$CANON"/leakcheck/"$1"*/; do
        d="${d%/}"; n=$((n + 1))
        compare "$RUN/leakcheck/$(basename "$d")/report.json" "$d/report.json"
    done
    [ "$n" -gt 0 ] || { echo "  FAILED: no committed $CANON/leakcheck/$1* reports"; FAIL=1; }
}

# ── v1.0 ─────────────────────────────────────────────────────────────────────────────────────────────
if want v1.0; then
    echo "== v1.0 path: a2a-leakcheck 0.1.x's numbers (the permutation test by sample)"
    echo "== v1.0 / 1. examples"
    run_report example_leaky examples/leaky examples/expected/leaky --label "example: leaky"
    run_report example_permuted examples/permuted examples/expected/permuted --label "example: permuted"
    for x in c2_lan c2_lan_padmax c2_ci_baseline; do
        run_report "example_${x}_v2" "examples/$x" "examples/expected/${x}_v2" --vantage v2 --attributes task_type \
            --label "example: $x, view v2"
    done

    echo "== v1.0 / 2. TLS control"
    run_report tls_control_tls_own data/raw_tlspair_tls "$CANON/leakcheck/tls_control_tls_own" --strip --perm-unit sample
    run_report tls_control_clear_own data/raw_tlspair_clear "$CANON/leakcheck/tls_control_clear_own" --strip --cleartext \
        --perm-unit sample
    run tls_control_own "$PY" scripts/evaluate_tls_control.py \
        && compare "$SANDBOX/tls_control_own.json" "$CANON/tls_control_own.json"

    echo "== v1.0 / 3. C2 setup and the TLS scanners"
    run c2_setup "$PY" scripts/c2_setup_numbers.py --out "$SANDBOX/c2_setup" \
        && compare "$SANDBOX/c2_setup.json" "$CANON/c2_setup.json"
    run tls_scanners_summary "$PY" baselines/summarize_tls_scanners.py "$CANON/tls_scanners" --out "$SANDBOX/tls_scanners_summary" \
        && compare "$SANDBOX/tls_scanners_summary.json" "$CANON/tls_scanners_summary.json"

    echo "== v1.0 / 4. C2 audits"
    for pair in lan:data/raw_c2 lan_pad:data/raw_c2_pad lan_padmax:data/raw_c2_padmax; do
        for v in v1 v2; do
            run_report "c2_${pair%%:*}_$v" "${pair#*:}" "$CANON/leakcheck/c2_${pair%%:*}_$v" --strip --perm-unit sample \
                --vantage "$v" --attributes task_type,escalated,cloud_role,audit_null --label "C2 ${pair%%:*}, view $v"
        done
    done
    rm -f "$SANDBOX/paper2_review.json" "$SANDBOX/paper2_review.md"
    run paper2_review "$PY" scripts/paper2_review.py --eval "$CANON/paper2_tool_eval_c2.json" \
        --reports "$SANDBOX/leakcheck/c2_{cell}" --out "$SANDBOX/paper2_review" --allow-dirty \
        && compare "$SANDBOX/paper2_review.json" "$CANON/paper2_review.json"

    if [ "$QUICK" -eq 0 ]; then
        echo "== v1.0 / 5. tool evaluation"
        run paper2_tool_eval "$PY" scripts/evaluate_leakcheck.py --name paper2_tool_eval \
            && compare "$SANDBOX/paper2_tool_eval.json" "$CANON/paper2_tool_eval.json"
        run paper2_tool_eval_c2 "$PY" scripts/evaluate_leakcheck.py --name paper2_tool_eval_c2 --collection-id C2 \
            --attributes task_type,escalated,cloud_role,audit_null --vantage v1,v2 \
            --reference baselines --by-construction escalated,cloud_role \
            --pair task_type:sensor_analysis,fault_diagnosis --input-size escalated=yes \
            --arm lan=data/raw_c2 --arm lan_pad=data/raw_c2_pad --arm lan_padmax=data/raw_c2_padmax \
            && compare "$SANDBOX/paper2_tool_eval_c2.json" "$CANON/paper2_tool_eval_c2.json" \
            && run paper2_false_leak_draws "$PY" scripts/rerun_false_leak_draws.py --eval "$SANDBOX/paper2_tool_eval_c2.json" \
                --out "$SANDBOX/paper2_false_leak_draws" --allow-dirty \
            && compare "$SANDBOX/paper2_false_leak_draws.json" "$CANON/paper2_false_leak_draws.json" \
            && run paper2_permuted_false_leaks "$PY" scripts/permuted_false_leaks.py \
                --eval "$SANDBOX/paper2_tool_eval_c2.json" --draws "$SANDBOX/paper2_false_leak_draws.json" \
                --out "$SANDBOX/paper2_permuted_false_leaks" \
            && compare "$SANDBOX/paper2_permuted_false_leaks.json" "$CANON/paper2_permuted_false_leaks.json"

        echo "== v1.0 / 6. CSV for the figures"
        rm -rf "$SANDBOX/paper2_csv"
        if run paper2_csv "$PY" scripts/export_paper2_csv.py --results "$SANDBOX" --out "$SANDBOX/paper2_csv"; then
            for f in "$CANON"/paper2_csv/*.csv; do
                [ "$(basename "$f")" = runtime.csv ] && continue        # wall-clock times; Pi rows are not rebuilt
                if cmp -s "$f" "$SANDBOX/paper2_csv/$(basename "$f")"; then echo "  $(basename "$f")  same"
                else echo "  $(basename "$f")  DIFFERENT"; FAIL=1; fi
            done
        fi
    else
        NOT_RUN="$NOT_RUN v1.0 stages 5-6 (tool evaluation, CSV);"
    fi
fi

# ── round 2 ──────────────────────────────────────────────────────────────────────────────────────────
if want round2; then
    echo "== round 2: a2a-leakcheck's defaults (the permutation test by prompt group)"
    P="$RUN/round2_parts"
    mkdir -p "$P"
    run "round 2 a3, a8, a9" "$PY" scripts/paper2_round2.py --sections a3,a8,a9 --out "$P/fast" --allow-dirty
    if [ "$QUICK" -eq 1 ]; then
        compare "$P/fast.json" "$CANON/paper2_round2.json" --sections a3,a8,a9
        NOT_RUN="$NOT_RUN round 2 a4, a5, a7, a10, a11;"
    else
        run "round 2 a4 (about 9.6 h)" "$PY" scripts/paper2_round2.py --sections a4 --out "$P/a4" --allow-dirty
        run "round 2 a5, a7 (about 5.8 h)" "$PY" scripts/paper2_round2.py --sections a5,a7 --out "$P/a5a7" --allow-dirty
        run "round 2 a10, a11 (about 6.2 h)" "$PY" scripts/paper2_round2.py --sections a10,a11 --out "$P/a10a11" --allow-dirty
        run "round 2 merge" "$PY" scripts/paper2_round2.py --merge "$P/fast.json" "$P/a4.json" "$P/a5a7.json" "$P/a10a11.json" \
            --out "$RUN/paper2_round2" --allow-dirty \
            && compare "$RUN/paper2_round2.json" "$CANON/paper2_round2.json"
    fi
    echo "== round 2: A6 on this machine"
    run "A6 features (C2 lan, V1)" "$PY" -m a2a_leakcheck extract data/raw_c2 --vantage v1 --strip \
        --attributes task_type,escalated,cloud_role,audit_null --out "$RUN/features_c2_lan_v1" \
        && run "A6 p-value dump" "$PY" scripts/pvalue_diagnostics.py dump "$RUN/features_c2_lan_v1" --seeds 42-51 \
            --out "$RUN/paper2_pvalue_mac.json" \
        && compare "$RUN/paper2_pvalue_mac.json" "$CANON/paper2_pvalue_mac.json"
fi

# ── D3 ───────────────────────────────────────────────────────────────────────────────────────────────
if want d3; then
    echo "== D3: reply shaping (C2B1 + C2B1X)"
    run b1_shape_calibration "$PY" scripts/b1_shape_calibration.py --out "$RUN/b1_shape_calibration" --allow-dirty \
        && compare "$RUN/b1_shape_calibration.json" "$CANON/b1_shape_calibration.json"
    run_check b1_shaping_overhead "$RUN/b1_shaping_overhead.json" "$PY" scripts/check_shaping.py data/raw_c2b1_shaped --control data/raw_c2b1_padmax --wan-ms 12 \
        --out "$RUN/b1_shaping_overhead" --allow-dirty \
        && compare "$RUN/b1_shaping_overhead.json" "$CANON/b1_shaping_overhead.json"
    run_check c2b1x_shaping_overhead "$RUN/c2b1x_shaping_overhead.json" "$PY" scripts/check_shaping.py data/raw_c2b1x_shaped --control data/raw_c2b1_padmax --wan-ms 12 \
        --out "$RUN/c2b1x_shaping_overhead" --allow-dirty \
        && compare "$RUN/c2b1x_shaping_overhead.json" "$CANON/c2b1x_shaping_overhead.json"
    run "b1_power (about 18 min)" "$PY" scripts/b1_power.py --out "$RUN/b1_power" --allow-dirty \
        && compare "$RUN/b1_power.json" "$CANON/b1_power.json"
    run "b1_audits (about 13 min)" "$PY" scripts/b1_audits.py --arm lan_padmax=data/raw_c2b1_padmax \
        --arm lan_shaped=data/raw_c2b1_shaped --baseline-arm lan_padmax --prefix c2b1 --reports "$RUN/leakcheck" \
        --out "$RUN/b1_audits" --allow-dirty \
        && compare "$RUN/b1_audits.json" "$CANON/b1_audits.json" \
        && compare_reports "c2b1_lan_"
    run b1_pair_pooled "$PY" scripts/b1_audits.py --arm lan_shaped=data/raw_c2b1_shaped,data/raw_c2b1x_shaped --parts pair \
        --baseline-arm lan_padmax --baseline-prefix c2b1 --prefix c2b1_c2b1x --reports "$RUN/leakcheck" \
        --out "$RUN/b1_pair_pooled" --allow-dirty \
        && compare "$RUN/b1_pair_pooled.json" "$CANON/b1_pair_pooled.json" \
        && compare_reports "c2b1_c2b1x_"
    run "b1_size_check (about 21 min)" "$PY" scripts/b1_size_check.py --out "$RUN/b1_size_check" --allow-dirty \
        && compare "$RUN/b1_size_check.json" "$CANON/b1_size_check.json"
fi

# ── B3 ───────────────────────────────────────────────────────────────────────────────────────────────
if want b3; then
    echo "== B3: a second day of lan (C2B3)"
    run "b3_audits (about 11 min)" "$PY" scripts/b1_audits.py --arm lan=data/raw_c2b3_lan --prefix c2b3 --title "B3 audits" \
        --reports "$RUN/leakcheck" --out "$RUN/b3_audits" --allow-dirty \
        && compare "$RUN/b3_audits.json" "$CANON/b3_audits.json" \
        && compare_reports "c2b3_"
    S=(--subset pair=task_type:sensor_analysis,fault_diagnosis
       --subset escalated_only=task_type:fault_diagnosis,procedure_lookup,sensor_analysis
       --reference "$CANON/paper2_round2.json" --allow-dirty)
    for v in v1 v2; do
        run "features C2 lan $v" "$PY" -m a2a_leakcheck extract data/raw_c2 --vantage "$v" --strip \
            --attributes task_type,escalated,cloud_role,audit_null --out "$RUN/features_b3_cross/c2_lan_$v"
        run "features C2B3 lan $v" "$PY" -m a2a_leakcheck extract data/raw_c2b3_lan --vantage "$v" --strip \
            --attributes task_type,escalated,cloud_role,audit_null --out "$RUN/features_b3_cross/c2b3_lan_$v"
        run "cross-session C2 → B3, $v (about 10 min)" "$PY" scripts/evaluate_cross_session.py \
            --train "$RUN/features_b3_cross/c2_lan_$v" --test "$RUN/features_b3_cross/c2b3_lan_$v" "${S[@]}" \
            --out "$RUN/b3_cross_session_c2_to_b3_$v" \
            && compare "$RUN/b3_cross_session_c2_to_b3_$v.json" "$CANON/b3_cross_session_c2_to_b3_$v.json"
        run "cross-session B3 → C2, $v (about 10 min)" "$PY" scripts/evaluate_cross_session.py \
            --train "$RUN/features_b3_cross/c2b3_lan_$v" --test "$RUN/features_b3_cross/c2_lan_$v" "${S[@]}" \
            --out "$RUN/b3_cross_session_b3_to_c2_$v" \
            && compare "$RUN/b3_cross_session_b3_to_c2_$v.json" "$CANON/b3_cross_session_b3_to_c2_$v.json"
    done
fi

if [ "$FAIL" -ne 0 ]; then
    echo "FAIL: see above and $LOG"
elif [ -n "$NOT_RUN" ]; then
    echo "PASS (quick): every number rebuilt matches the committed one; not rebuilt in --quick:$NOT_RUN run without --quick for those"
else
    echo "PASS: every number of sections $SECTIONS rebuilt and matches the committed one"
fi
exit "$FAIL"
