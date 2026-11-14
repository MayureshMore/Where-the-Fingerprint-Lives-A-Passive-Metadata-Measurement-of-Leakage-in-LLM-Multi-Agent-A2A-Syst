#!/usr/bin/env bash
#
# demo_paper2.sh — paper 2's video demo: a2a-leakcheck on the C2 examples, under a minute on a laptop.
#
# The building's edge agent sends sensor analyses and fault diagnoses to the same cloud agent over TLS
# 1.3. An upstream observer (V2: the ISP) sees only those encrypted calls. The examples hold the same
# 40 tasks twice: without padding (lan) and with every cloud request padded to 8 KB (lan_padmax).
#
#   1. verdict table   both arms audited at V2 for the task type; what carries the leak; the hint
#   2. HTML report     the report a manufacturer or auditor reads
#   3. CI gate         the unpadded audit against an earlier report (--baseline): task_type is LEAK now
#                      and was not then, so the run exits with code 3 and would fail the build
#
# Deterministic: fixed seeds, no network; the verdicts and scores match examples/expected/.
#
# Usage:
#   bash scripts/demo_paper2.sh                 # reports in a temporary folder
#   OUT=/tmp/demo OPEN=1 bash scripts/demo_paper2.sh   # keep the reports, open the HTML (macOS)
#   PYTHON=venv/bin/python bash scripts/demo_paper2.sh
#
set -u
PY="${PYTHON:-python3}"
OUT="${OUT:-$(mktemp -d -t leakcheck_demo)}"
BASE="examples/expected/c2_ci_baseline_v2/report.json"
ATTR="--vantage v2 --attributes task_type"
cd "$(dirname "$0")/.." || exit 1
for x in examples/c2_lan examples/c2_lan_padmax "$BASE"; do
    [ -e "$x" ] || { echo "missing $x (scripts/make_c2_examples.py)" >&2; exit 1; }
done
mkdir -p "$OUT"
T0=$(date +%s)
say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
run() { echo "\$ $*"; "$@"; }

say "1. Audit both arms, as the upstream observer (V2) sees them"
run "$PY" -m a2a_leakcheck run examples/c2_lan_padmax $ATTR --html --label "C2 example, padded to 8 KB, V2" \
    --out "$OUT/lan_padmax" 2>/dev/null || { echo "audit failed" >&2; exit 1; }
run "$PY" -m a2a_leakcheck run examples/c2_lan $ATTR --html --label "C2 example, no padding, V2" \
    --out "$OUT/lan" --baseline "$BASE" 2>/dev/null
GATE=$?

"$PY" - "$OUT/lan/report.json" "$OUT/lan_padmax/report.json" <<'PY'
import json, sys
rows = []
for name, path in zip(("no padding", "padded to 8 KB"), sys.argv[1:3]):
    r = json.load(open(path))
    for attr, a in r["attributes"].items():
        an, at = a["analysis"] or {}, a.get("attribution") or {}
        fams = at.get("families") or {}
        carried = [f for f, v in fams.items() if v["all_minus_this"]["ci_lo"] <= 0]
        single = (at.get("single_request_size") or {}).get("matches_all")
        rows.append((name, attr, a["verdict"], f"{an.get('macro_f1', 0):.2f} [{an.get('ci_lo', 0):.2f}, {an.get('ci_hi', 0):.2f}]",
                     f"{a['validation']['permutation']['p_value']:.2f}",
                     "first request alone" if single else ", ".join(carried) or "—",
                     ", ".join(m["id"] for m in a["mitigations"]) or "—"))
head = ("arm", "attribute", "verdict", "macro-F1 [95% CI]", "p", "carried by", "hint")
w = [max(len(str(x[i])) for x in rows + [head]) for i in range(len(head))]
for x in [head, tuple("-" * n for n in w)] + rows:
    print("  ".join(str(v).ljust(n) for v, n in zip(x, w)))
print("\nchance for two task types: 0.50; LEAK needs the interval above 0.55 and p ≤ 0.05")
for name, path in zip(("no padding", "padded"), sys.argv[1:3]):
    for attr, a in json.load(open(path))["attributes"].items():
        for m in a["mitigations"]:
            print(f"\n[{name}] {m['id']}: {m['hint']}")
PY

say "2. The HTML report"
echo "$OUT/lan_padmax/report.html"
echo "$OUT/lan/report.html"
[ "${OPEN:-0}" = 1 ] && command -v open >/dev/null && open "$OUT/lan_padmax/report.html"

say "3. CI gate: the unpadded audit against the earlier report ($BASE)"
"$PY" -m a2a_leakcheck diff "$OUT/lan/report.json" "$BASE"
echo "exit code of the audit with --baseline: $GATE"
[ "$GATE" = 3 ] && echo "→ a new LEAK: the release check fails" || echo "→ unexpected: the gate should have exited with 3" >&2

say "Done in $(( $(date +%s) - T0 )) s; reports in $OUT"
[ "$GATE" = 3 ]
