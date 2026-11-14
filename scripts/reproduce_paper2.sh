#!/usr/bin/env bash
#
# reproduce_paper2.sh — rebuild every paper 2 (a2a-leakcheck) number from the released data and
# compare it with the committed one. Like scripts/reproduce.sh it writes to a sandbox and never to
# data/results/.
#
#   1. examples        leakcheck on the examples in the repo: the TLS control's leaky and permuted
#                      sets; C2's c2_lan, c2_lan_padmax and c2_ci_baseline at the upstream view
#                      (--vantage v2, task_type)                                             ~3 min
#   2. TLS control     leakcheck on both arms, own connections (data/raw_tlspair_{tls,clear})
#                      → leakcheck/tls_control_{tls,clear}_own; scripts/evaluate_tls_control.py:
#                      the paired TLS − cleartext difference, cleartext → TLS transfer and on-wire
#                      cost (data/processed_tlspair_{clear,tls}_own) → tls_control_own         ~10 min
#   3. C2 setup        scripts/c2_setup_numbers.py on the released C2 folders → c2_setup (session,
#                      Pi temperature, input sizes per task type, emulated WAN);
#                      baselines/summarize_tls_scanners.py on the committed scanner output
#                      → tls_scanners_summary                                                seconds
#   4. C2 audits       leakcheck on the three edge-cloud arms (data/raw_c2, data/raw_c2_pad,
#                      data/raw_c2_padmax) at both observer views → leakcheck/c2_<arm>_<view> ~20 min
#   5. tool evaluation scripts/evaluate_leakcheck.py on both TLS-control arms
#                      → paper2_tool_eval.{json,md}                                            hours
#                      and on all six C2 cells, in one process (the committed one ran split by
#                      arm and merged; the verdicts do not depend on the split)
#                      → paper2_tool_eval_c2.{json,md}                                       a day
#   6. CSV             scripts/export_paper2_csv.py on the rebuilt results → paper2_csv/ (the
#                      numbers behind the paper's pgfplots figures), compared file by file
#
# A stage whose inputs are absent is skipped. Each result is compared with the committed one:
# verdicts, macro-F1 with its interval, p-values and every other number must match; runtime,
# memory, dates, commits and paths are not compared. Not rebuilt here, because they measure live
# systems: the TLS scanners themselves (baselines/run_tls_scanners.sh), the cloud round trip the
# WAN emulation targets (data/results/c2_wan_emulation.json) and the Raspberry Pi timing
# (data/results/leakcheck_pi). docs/PAPER2_NUMBERS.md maps every number in the paper to its file.
#
# Inputs: the paper 2 data release (DATA.md): the TLS control's captures and features
# (data/raw_tlspair_{tls,clear}, data/processed_tlspair_{tls,clear}_own) and C2's captures
# (data/raw_c2, data/raw_c2_pad, data/raw_c2_padmax).
#
# Usage:
#   bash scripts/reproduce_paper2.sh                  # all stages whose data is present
#   bash scripts/reproduce_paper2.sh --quick          # stages 1 to 4 (about half an hour)
#   A2A_RESULTS_DIR=data/results_p2 bash scripts/reproduce_paper2.sh
#   PYTHON=venv/bin/python bash scripts/reproduce_paper2.sh
#
set -u

PY="${PYTHON:-python3}"
QUICK=0
for arg in "$@"; do
    case "$arg" in
        --quick) QUICK=1 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

CANON="data/results"
SANDBOX="${A2A_RESULTS_DIR:-data/results_paper2_demo}"
if [ "${SANDBOX%/}" = "$CANON" ]; then
    echo "REFUSING: A2A_RESULTS_DIR would overwrite the canonical $CANON." >&2
    exit 2
fi
export A2A_RESULTS_DIR="$SANDBOX"
mkdir -p "$SANDBOX/leakcheck" logs
LOG="logs/reproduce_paper2_$(date +%Y%m%d_%H%M%S).log"
echo "sandbox: $SANDBOX   log: $LOG   python: $("$PY" --version 2>&1)   commit: $(git rev-parse --short HEAD 2>/dev/null)"

FAIL=0
compare() {   # compare NEW OLD: report.json or a paper2_tool_eval json
    "$PY" - "$1" "$2" <<'PY'
import json, sys
new, old = (json.load(open(p)) for p in sys.argv[1:3])

def pick_report(r):
    out = {}
    for k, a in r["attributes"].items():
        an, perm = a.get("analysis") or {}, a["validation"].get("permutation") or {}
        out[k] = {"verdict": a["verdict"], "macro_f1": an.get("macro_f1"), "ci": [an.get("ci_lo"), an.get("ci_hi")],
                  "p": perm.get("p_value")}
    return out

def pick_eval(r):
    out = {"summary": r["summary"]}
    for an, arm in r["arms"].items():
        for k, a in arm["attributes"].items():
            out[f"{an}/{k}"] = {"full": {m: v["verdict"] for m, v in a["full"].items()}, "permuted": a["permuted"],
                                "sample_size": a["sample_size"]}
    return out

SKIP = {"created", "git_commit", "git_dirty", "runtime", "runtime_s", "data_dir", "source", "clear_dir", "tls_dir"}

def pick_generic(r):
    return {k: v for k, v in r.items() if k not in SKIP}

pick = pick_eval if "arms" in old else pick_report if "attributes" in old and "tool" in old else pick_generic
a, b = pick(new), pick(old)
def close(x, y):
    if isinstance(x, float) and isinstance(y, float):
        return abs(x - y) < 1e-9
    if isinstance(x, dict) and isinstance(y, dict):
        return x.keys() == y.keys() and all(close(x[k], y[k]) for k in x)
    if isinstance(x, list) and isinstance(y, list):
        return len(x) == len(y) and all(close(i, j) for i, j in zip(x, y))
    return x == y
bad = [k for k in b if k not in a or not close(a[k], b[k])]
for k in b:
    print(f"  {k:28s} {'same' if k not in bad else 'DIFFERENT'}"
          + (f"  ({b[k]['verdict']})" if isinstance(b[k], dict) and "verdict" in b[k] else ""))
if pick is pick_eval:
    for part in ("pair", "input_size"):        # C2's extras, per cell
        for an in old.get("arms", {}):
            x, y = new["arms"].get(an, {}).get(part), old["arms"][an].get(part)
            if y is not None and not close(x, y):
                bad.append(f"{an}/{part}"); print(f"  {an + '/' + part:28s} DIFFERENT")
sys.exit(1 if bad else 0)
PY
}

run_report() {   # run_report NAME CAPTURE_DIR COMMITTED_DIR [extra args]
    local name="$1" dir="$2" committed="$3"; shift 3
    if [ ! -d "$dir" ]; then echo "[skip] $name: $dir absent"; return; fi
    echo "[run ] $name: $dir"
    "$PY" -m a2a_leakcheck run "$dir" --out "$SANDBOX/leakcheck/$name" --html "$@" >> "$LOG" 2>&1 \
        || { echo "  FAILED (see $LOG)"; FAIL=1; return; }
    if [ -f "$committed/report.json" ]; then
        compare "$SANDBOX/leakcheck/$name/report.json" "$committed/report.json" || FAIL=1
    else
        echo "  (no committed report at $committed to compare)"
    fi
}

run_eval() {     # run_eval NAME COMMITTED_JSON [evaluate_leakcheck.py args]
    local name="$1" committed="$2"; shift 2
    echo "[run ] $name (hours)"
    "$PY" scripts/evaluate_leakcheck.py --name "$name" "$@" >> "$LOG" 2>&1 \
        || { echo "  FAILED (see $LOG)"; FAIL=1; return; }
    if [ -f "$committed" ]; then
        compare "$SANDBOX/$name.json" "$committed" || FAIL=1
    else
        echo "  (no committed $committed to compare)"
    fi
}

run_json() {     # run_json NAME COMMITTED_JSON COMMAND...: a script writing $SANDBOX/NAME.json
    local name="$1" committed="$2"; shift 2
    echo "[run ] $name"
    "$@" >> "$LOG" 2>&1 || { echo "  FAILED (see $LOG)"; FAIL=1; return; }
    if [ -f "$committed" ]; then
        compare "$SANDBOX/$name.json" "$committed" || FAIL=1
    else
        echo "  (no committed $committed to compare)"
    fi
}

echo "== 1. examples"
run_report example_leaky examples/leaky examples/expected/leaky --label "example: leaky"
run_report example_permuted examples/permuted examples/expected/permuted --label "example: permuted"
for x in c2_lan c2_lan_padmax c2_ci_baseline; do
    run_report "example_${x}_v2" "examples/$x" "examples/expected/${x}_v2" --vantage v2 --attributes task_type \
        --label "example: $x, view v2"
done

echo "== 2. TLS control"
run_report tls_control_tls_own data/raw_tlspair_tls "$CANON/leakcheck/tls_control_tls_own" --strip
run_report tls_control_clear_own data/raw_tlspair_clear "$CANON/leakcheck/tls_control_clear_own" --strip
if [ -d data/processed_tlspair_clear_own ] && [ -d data/processed_tlspair_tls_own ]; then
    run_json tls_control_own "$CANON/tls_control_own.json" "$PY" scripts/evaluate_tls_control.py
else
    echo "[skip] tls_control_own: data/processed_tlspair_{clear,tls}_own absent"
fi

echo "== 3. C2 setup and the TLS scanners"
if [ -d data/raw_c2 ] && [ -d data/raw_c2_pad ] && [ -d data/raw_c2_padmax ]; then
    run_json c2_setup "$CANON/c2_setup.json" "$PY" scripts/c2_setup_numbers.py --out "$SANDBOX/c2_setup"
else
    echo "[skip] c2_setup: C2 captures absent"
fi
run_json tls_scanners_summary "$CANON/tls_scanners_summary.json" \
    "$PY" baselines/summarize_tls_scanners.py "$CANON/tls_scanners" --out "$SANDBOX/tls_scanners_summary"

echo "== 4. C2 audits"
for pair in lan:data/raw_c2 lan_pad:data/raw_c2_pad lan_padmax:data/raw_c2_padmax; do
    for v in v1 v2; do
        run_report "c2_${pair%%:*}_$v" "${pair#*:}" "$CANON/leakcheck/c2_${pair%%:*}_$v" --strip --vantage "$v" \
            --attributes task_type,escalated,cloud_role,audit_null --label "C2 ${pair%%:*}, view $v"
    done
done

if [ "$QUICK" -eq 0 ]; then
    echo "== 5. tool evaluation"
    if [ -d data/raw_tlspair_tls ] && [ -d data/raw_tlspair_clear ]; then
        run_eval paper2_tool_eval "$CANON/paper2_tool_eval.json"
    else
        echo "[skip] TLS-control captures absent"
    fi
    if [ -d data/raw_c2 ] && [ -d data/raw_c2_pad ] && [ -d data/raw_c2_padmax ]; then
        run_eval paper2_tool_eval_c2 "$CANON/paper2_tool_eval_c2.json" --collection-id C2 \
            --attributes task_type,escalated,cloud_role,audit_null --vantage v1,v2 \
            --reference baselines --by-construction escalated,cloud_role \
            --pair task_type:sensor_analysis,fault_diagnosis --input-size escalated=yes \
            --arm lan=data/raw_c2 --arm lan_pad=data/raw_c2_pad --arm lan_padmax=data/raw_c2_padmax
    else
        echo "[skip] C2 tool evaluation: captures absent"
    fi

    echo "== 6. CSV for the figures"
    if [ -d "$CANON/paper2_csv" ]; then
        rm -rf "$SANDBOX/paper2_csv"
        if "$PY" scripts/export_paper2_csv.py --results "$SANDBOX" --out "$SANDBOX/paper2_csv" >> "$LOG" 2>&1; then
            for f in "$CANON"/paper2_csv/*.csv; do
                [ "$(basename "$f")" = runtime.csv ] && continue        # wall-clock times; Pi rows are not rebuilt
                if cmp -s "$f" "$SANDBOX/paper2_csv/$(basename "$f")"; then echo "  $(basename "$f")  same"
                else echo "  $(basename "$f")  DIFFERENT"; FAIL=1; fi
            done
        else
            echo "  FAILED (see $LOG)"; FAIL=1
        fi
    else
        echo "[skip] no committed $CANON/paper2_csv"
    fi
fi

if [ "$FAIL" -eq 0 ]; then echo "PASS: every rebuilt number matches the committed one"; else echo "FAIL: see above and $LOG"; fi
exit "$FAIL"
