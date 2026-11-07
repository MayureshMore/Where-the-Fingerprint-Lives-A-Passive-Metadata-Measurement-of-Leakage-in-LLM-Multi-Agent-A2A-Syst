#!/usr/bin/env bash
#
# Standard TLS scanners against the Pi's 27 agent ports (docs/LAN_SETUP.md, section 5): what an
# operator's usual TLS check reports for the same deployment that a2a-leakcheck audits. Both
# scanners look at the TLS configuration (versions, cipher suites, certificate, known
# vulnerabilities); neither looks at what the sizes and timing of the encrypted traffic reveal.
#
# Run from the Mac during the pilot, with all three serve_agents.py instances up on the Pi:
#   bash baselines/run_tls_scanners.sh                     # Pi at 192.168.2.2
#   HOST=192.168.2.2 OUT=data/results/tls_scanners bash baselines/run_tls_scanners.sh
#
# Needs sslyze (pip install sslyze) and testssl.sh (https://testssl.sh, or brew install testssl)
# on PATH; set SSLYZE / TESTSSL to override. Writes, per port, sslyze_<port>.json and
# testssl_<port>.json, plus scanners.json (host, ports, scanner versions, start and end).
set -u

HOST="${HOST:-192.168.2.2}"
OUT="${OUT:-data/results/tls_scanners}"
SSLYZE="${SSLYZE:-sslyze}"
TESTSSL="${TESTSSL:-testssl.sh}"
command -v "$TESTSSL" >/dev/null 2>&1 || TESTSSL=testssl
for tool in "$SSLYZE" "$TESTSSL"; do
    command -v "$tool" >/dev/null 2>&1 || { echo "not found: $tool" >&2; exit 1; }
done
mkdir -p "$OUT"

PORTS=()
for b in 8100 8200 8300; do for t in 0 10 20; do for r in 1 2 3; do PORTS+=($((b + t + r))); done; done; done

START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
FAILED=()
for p in "${PORTS[@]}"; do
    echo "== $HOST:$p"
    rm -f "$OUT/sslyze_$p.json" "$OUT/testssl_$p.json"     # testssl.sh refuses to overwrite its JSON
    "$SSLYZE" --json_out "$OUT/sslyze_$p.json" "$HOST:$p" > "$OUT/sslyze_$p.log" 2>&1
    "$TESTSSL" --quiet --color 0 --warnings batch --jsonfile "$OUT/testssl_$p.json" "$HOST:$p" \
        > "$OUT/testssl_$p.log" 2>&1
    # testssl.sh's exit status is not a failure signal; a missing or empty report is
    [ -s "$OUT/sslyze_$p.json" ] || FAILED+=("sslyze:$p")
    [ -s "$OUT/testssl_$p.json" ] || FAILED+=("testssl:$p")
done
END="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

SSLYZE_V="$("$SSLYZE" --help 2>/dev/null | head -1)"
PY_SSLYZE_V="$(python3 -c 'import importlib.metadata as m; print(m.version("sslyze"))' 2>/dev/null)"
TESTSSL_V="$("$TESTSSL" --version 2>/dev/null | grep -m1 -i 'testssl.sh' | tr -s ' ')"
python3 - "$OUT/scanners.json" "$HOST" "$START" "$END" "${PY_SSLYZE_V:-$SSLYZE_V}" "$TESTSSL_V" \
    "$(git rev-parse HEAD 2>/dev/null)" "${PORTS[*]}" "${FAILED[*]:-}" <<'PY'
import json, sys
path, host, start, end, sv, tv, commit, ports, failed = sys.argv[1:]
json.dump({"host": host, "ports": [int(p) for p in ports.split()], "started": start, "finished": end,
           "sslyze": sv, "testssl": tv, "git_commit": commit,
           "failed": failed.split() if failed else []}, open(path, "w"), indent=2)
PY
echo "${#PORTS[@]} ports → $OUT (failed: ${FAILED[*]:-none})"
[ "${#FAILED[@]}" -eq 0 ]
