#!/usr/bin/env bash
#
# reproduce_paper2.sh — rebuild every paper 2 (a2a-leakcheck) number from the released data and
# compare it with the committed one. Like scripts/reproduce.sh it writes to a sandbox and never to
# data/results/.
#
#   1. examples        leakcheck on examples/leaky and examples/permuted (in the repo)       ~2 min
#   2. TLS control     leakcheck on both arms, own connections
#                      (data/raw_tlspair_{tls,clear}) → leakcheck/tls_control_{tls,clear}_own  ~5 min
#   3. tool evaluation scripts/evaluate_leakcheck.py on both TLS-control arms
#                      → paper2_tool_eval.{json,md}, figures/paper2_tool_eval.png             hours
#   4. C2              once released: leakcheck on both LAN arms (data/raw_c2, data/raw_c2_pad)
#                      → leakcheck/c2_{lan,lan_pad}, and the tool evaluation with audit_null
#                      → paper2_tool_eval_c2.{json,md}                                         hours
#
# A stage whose inputs are absent is skipped. Each result is compared with the committed one:
# verdicts, macro-F1 with its interval, and p-values must match; runtime, memory, dates and
# commits are not compared. The TLS scanner baselines (baselines/run_tls_scanners.sh) and the
# Raspberry Pi timing (docs/LEAKCHECK.md) are measurements of live systems, not rebuilt here.
#
# Inputs: the TLS control's raw captures (data/raw_tlspair_tls, data/raw_tlspair_clear) from the
# data archive (DATA.md); the C2 captures once published.
#
# Usage:
#   bash scripts/reproduce_paper2.sh                  # all stages whose data is present
#   bash scripts/reproduce_paper2.sh --quick          # stages 1 and 2 only (minutes)
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

pick = pick_eval if "arms" in old else pick_report
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

echo "== 1. examples"
run_report example_leaky examples/leaky examples/expected/leaky --label "example: leaky"
run_report example_permuted examples/permuted examples/expected/permuted --label "example: permuted"

echo "== 2. TLS control"
run_report tls_control_tls_own data/raw_tlspair_tls "$CANON/leakcheck/tls_control_tls_own" --strip
run_report tls_control_clear_own data/raw_tlspair_clear "$CANON/leakcheck/tls_control_clear_own" --strip

if [ "$QUICK" -eq 0 ]; then
    echo "== 3. tool evaluation, TLS control"
    if [ -d data/raw_tlspair_tls ] && [ -d data/raw_tlspair_clear ]; then
        run_eval paper2_tool_eval "$CANON/paper2_tool_eval.json"
    else
        echo "[skip] TLS-control captures absent"
    fi

    echo "== 4. C2"
    run_report c2_lan data/raw_c2 "$CANON/leakcheck/c2_lan" --strip --attributes role,workflow,topology,audit_null
    run_report c2_lan_pad data/raw_c2_pad "$CANON/leakcheck/c2_lan_pad" --strip --attributes role,workflow,topology,audit_null
    if [ -d data/raw_c2 ] && [ -d data/raw_c2_pad ]; then
        run_eval paper2_tool_eval_c2 "$CANON/paper2_tool_eval_c2.json" --collection-id C2 \
            --arm lan=data/raw_c2 --arm lan_pad=data/raw_c2_pad --not-known lan_pad:workflow
    else
        echo "[skip] C2 captures absent"
    fi
fi

if [ "$FAIL" -eq 0 ]; then echo "PASS: every rebuilt number matches the committed one"; else echo "FAIL: see above and $LOG"; fi
exit "$FAIL"
