#!/usr/bin/env bash
#
# a2a-leakcheck, stage 3: audit each arm and view's features; reports go to stage 4.
#
# Usage: ./3_security_analysis/a2a-leakcheck/analyze.sh lan_padmax:v2 [lan:v1 ...] [-- AUDIT OPTIONS]
# AUDIT OPTIONS go to `a2a_leakcheck run`, e.g. --strict, --baseline OLD/report.json, --jobs 4.
# Writes 4_analysis_output/a2a-leakcheck/last_run/<arm>_<view>/report.{md,json,html}. Exits with
# the first non-zero exit code of the audits (see 4_analysis_output/a2a-leakcheck/README.md).

set -euo pipefail

TOOL=a2a-leakcheck
PY="${A2A_PY:-3_security_analysis/$TOOL/.venv/bin/python}"
export PYTHONPATH="3_security_analysis/$TOOL/src"

cells=()
while [ $# -gt 0 ] && [ "$1" != "--" ]; do cells+=("$1"); shift; done
[ $# -gt 0 ] && shift

status=0
for cell in "${cells[@]}"; do
    arm=${cell%%:*}
    view=${cell##*:}
    code=0
    "$PY" -m a2a_leakcheck run "2_preprocess/$TOOL/features/${arm}_${view}" --html \
        --label "C2 $arm, view $view" --out "4_analysis_output/$TOOL/last_run/${arm}_${view}" "$@" 2>/dev/null \
        || code=$?
    [ "$code" = 1 ] && exit 1
    [ "$status" = 0 ] && status=$code
done
exit "$status"
