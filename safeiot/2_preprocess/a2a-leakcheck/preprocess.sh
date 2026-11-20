#!/usr/bin/env bash
#
# a2a-leakcheck, stage 2: the header-only check and the features, per arm and observer view.
#
# Usage: ./2_preprocess/a2a-leakcheck/preprocess.sh lan_padmax:v2 [lan:v1 ...]
# Reads 1_analysis_object/a2a-leakcheck/downloads/data/raw_c2*; writes
# 2_preprocess/a2a-leakcheck/features/<arm>_<view>/{features.npz,features.json}.
# Run from the repository root (the harness does); A2A_PY selects the Python (default: the
# harness's venv in 3_security_analysis/a2a-leakcheck/.venv).

set -euo pipefail

TOOL=a2a-leakcheck
PY="${A2A_PY:-3_security_analysis/$TOOL/.venv/bin/python}"
export PYTHONPATH="3_security_analysis/$TOOL/src"
ATTRIBUTES=task_type,escalated,cloud_role,audit_null

for cell in "$@"; do
    arm=${cell%%:*}
    view=${cell##*:}
    case $arm in
        lan) raw=raw_c2 ;;
        lan_pad) raw=raw_c2_pad ;;
        lan_padmax) raw=raw_c2_padmax ;;
        *) echo "unknown arm $arm (lan, lan_pad, lan_padmax)" >&2; exit 1 ;;
    esac
    "$PY" -m a2a_leakcheck extract "1_analysis_object/$TOOL/downloads/data/$raw" --vantage "$view" \
        --attributes "$ATTRIBUTES" --out "2_preprocess/$TOOL/features/${arm}_${view}" 2>/dev/null
done
