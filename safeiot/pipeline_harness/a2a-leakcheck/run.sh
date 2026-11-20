#!/usr/bin/env bash
#
# a2a-leakcheck — end-to-end run, from a clean checkout to reports in 4_analysis_output/.
#
#   1  fetch the header-only captures from Zenodo and check their sha256      1_analysis_object
#   2  header-only check and features, per arm and observer view              2_preprocess
#   3  the audit: a verdict per attribute                                     3_security_analysis
#   4  report.md / report.json / report.html per arm and view                 4_analysis_output
#
# Usage: ./pipeline_harness/a2a-leakcheck/run.sh [quick|full] [AUDIT OPTIONS]
#   quick   one arm and view: requests padded to 8 KB, seen upstream (lan_padmax, V2)  (default)
#   full    all three arms at both views (six audits)
#   AUDIT OPTIONS go to every audit, e.g. --strict, --require task_type, --jobs 4
# PYTHON selects the interpreter that creates the venv (3.11 to 3.13; default: the first found).
# Exits with the audits' exit code (4_analysis_output/a2a-leakcheck/README.md).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"                     # relative paths from here on, so the reports name no home folder
TOOL=a2a-leakcheck
ANA="3_security_analysis/$TOOL"
OUT="4_analysis_output/$TOOL"

MODE="${1:-quick}"
[ $# -gt 0 ] && shift
case "$MODE" in
    quick) CELLS=(lan_padmax:v2) ;;
    full) CELLS=(lan:v1 lan:v2 lan_pad:v1 lan_pad:v2 lan_padmax:v1 lan_padmax:v2) ;;
    *) echo "usage: $0 [quick|full] [audit options]" >&2; exit 1 ;;
esac

T0=$(date +%s)
stamp() { echo "    ($(( $(date +%s) - T0 )) s)"; }

echo "==> Python environment ($ANA/.venv)"
if [ ! -x "$ANA/.venv/bin/python" ]; then
    PY=""
    for c in ${PYTHON:-} python3.12 python3.13 python3.11 python3; do
        if command -v "$c" >/dev/null 2>&1 && \
           "$c" -c 'import sys; sys.exit(not (3, 11) <= sys.version_info[:2] <= (3, 13))' 2>/dev/null; then
            PY="$c"; break
        fi
    done
    [ -n "$PY" ] || { echo "needs Python 3.11 to 3.13 (set PYTHON=...)" >&2; exit 1; }
    "$PY" -m venv "$ANA/.venv"
fi
"$ANA/.venv/bin/python" -m pip install --quiet --disable-pip-version-check -r "$ANA/requirements.txt"
echo "    $("$ANA/.venv/bin/python" --version)"; stamp

echo "==> Stage 1: analysis object (Zenodo record 24238559)"
"1_analysis_object/$TOOL/fetch.sh"; stamp

echo "==> Stage 2: header-only check and features (${CELLS[*]})"
"2_preprocess/$TOOL/preprocess.sh" "${CELLS[@]}"; stamp

echo "==> Stage 3: audit"
code=0
"$ANA/analyze.sh" "${CELLS[@]}" -- "$@" || code=$?
stamp

echo "==> Stage 4: reports"
for cell in "${CELLS[@]}"; do
    echo "    $OUT/last_run/${cell/:/_}/report.md"
done
echo "    exit code $code"
exit "$code"
