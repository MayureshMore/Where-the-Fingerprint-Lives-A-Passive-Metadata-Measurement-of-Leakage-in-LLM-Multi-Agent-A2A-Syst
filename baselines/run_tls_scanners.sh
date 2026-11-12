#!/usr/bin/env bash
#
# Standard TLS scanners against C2's TLS endpoints (docs/LAN_SETUP.md): the cloud agents on the
# cloud alias (diagnostics base+1, knowledge base+2) and the ticket service on the Mac's own
# address (base+5), for the three arm bases; addresses from configs/c2_network.conf (C2_CLOUD,
# C2_MAC) unless CLOUD / TICKET are set: what an operator's usual TLS check reports for the
# same deployment that a2a-leakcheck audits. Both scanners look at the TLS configuration
# (versions, cipher suites, certificate, known vulnerabilities); neither looks at what the sizes
# and timing of the encrypted traffic reveal.
#
# Run from the Mac during the pilot, with scripts/serve_cloud.py running:
#   bash baselines/run_tls_scanners.sh
#   CLOUD=10.0.0.240 TICKET=10.0.0.228 OUT=data/results/tls_scanners bash baselines/run_tls_scanners.sh
#
# Needs sslyze (python3 -m venv venv-scanners && venv-scanners/bin/pip install sslyze==6.3.1) and
# testssl.sh (brew install testssl)
# on PATH; set SSLYZE / TESTSSL to override. Writes, per endpoint, sslyze_<host>_<port>.json and
# testssl_<host>_<port>.json, plus scanners.json (endpoints, scanner versions, start and end).
set -u

CONF="$(cd "$(dirname "$0")/.." && pwd)/configs/c2_network.conf"
[ -f "$CONF" ] && . "$CONF"
CLOUD="${CLOUD:-${C2_CLOUD:-}}"
TICKET="${TICKET:-${C2_MAC:-}}"
[ -n "$CLOUD" ] && [ -n "$TICKET" ] || { echo "set C2_CLOUD and C2_MAC in $CONF" >&2; exit 1; }
OUT="${OUT:-data/results/tls_scanners}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
# sslyze lives in its own venv (it pins an older cryptography than requirements-lock.txt)
SSLYZE="${SSLYZE:-$([ -x "$REPO/venv-scanners/bin/sslyze" ] && echo "$REPO/venv-scanners/bin/sslyze" || echo sslyze)}"
TESTSSL="${TESTSSL:-testssl.sh}"
command -v "$TESTSSL" >/dev/null 2>&1 || TESTSSL=testssl
for tool in "$SSLYZE" "$TESTSSL"; do
    command -v "$tool" >/dev/null 2>&1 || { echo "not found: $tool" >&2; exit 1; }
done
mkdir -p "$OUT"

TARGETS=()
for b in 8100 8200 8300; do TARGETS+=("$CLOUD:$((b + 1))" "$CLOUD:$((b + 2))" "$TICKET:$((b + 5))"); done

START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
FAILED=()
for t in "${TARGETS[@]}"; do
    echo "== $t"
    f="${t/:/_}"
    rm -f "$OUT/sslyze_$f.json" "$OUT/testssl_$f.json"     # testssl.sh refuses to overwrite its JSON
    "$SSLYZE" --json_out "$OUT/sslyze_$f.json" "$t" > "$OUT/sslyze_$f.log" 2>&1
    "$TESTSSL" --quiet --color 0 --warnings batch --jsonfile "$OUT/testssl_$f.json" "$t" \
        > "$OUT/testssl_$f.log" 2>&1
    # testssl.sh's exit status is not a failure signal; a missing or empty report is
    [ -s "$OUT/sslyze_$f.json" ] || FAILED+=("sslyze:$t")
    [ -s "$OUT/testssl_$f.json" ] || FAILED+=("testssl:$t")
done
END="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

SSLYZE_V="$("$SSLYZE" --help 2>/dev/null | head -1)"
SPY="$(dirname "$SSLYZE")/python"; [ -x "$SPY" ] || SPY=python3
PY_SSLYZE_V="$("$SPY" -c 'import importlib.metadata as m; print(m.version("sslyze"))' 2>/dev/null)"
TESTSSL_V="$("$TESTSSL" --version 2>/dev/null | grep -m1 -i 'testssl.sh' | tr -s ' ')"
python3 - "$OUT/scanners.json" "$START" "$END" "${PY_SSLYZE_V:-$SSLYZE_V}" "$TESTSSL_V" \
    "$(git rev-parse HEAD 2>/dev/null)" "${TARGETS[*]}" "${FAILED[*]:-}" <<'PY'
import json, sys
path, start, end, sv, tv, commit, targets, failed = sys.argv[1:]
json.dump({"endpoints": targets.split(), "started": start, "finished": end,
           "sslyze": sv, "testssl": tv, "git_commit": commit,
           "failed": failed.split() if failed else []}, open(path, "w"), indent=2)
PY
echo "${#TARGETS[@]} endpoints → $OUT (failed: ${FAILED[*]:-none})"
[ "${#FAILED[@]}" -eq 0 ]
