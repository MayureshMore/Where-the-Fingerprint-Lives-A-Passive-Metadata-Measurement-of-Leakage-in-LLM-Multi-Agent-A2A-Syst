#!/usr/bin/env bash
#
# wan_emulation.sh — C2's emulated WAN on the Raspberry Pi (docs/LAN_SETUP.md): delay only the
# Pi's traffic to the cloud alias, with the tc commands that scripts/measure_cloud_rtt.py wrote
# from a measured round trip (so what runs here is exactly what the JSON records).
#
#   sudo bash scripts/wan_emulation.sh on   [data/results/c2_wan_emulation.json]
#   sudo bash scripts/wan_emulation.sh off  [DEV]
#        bash scripts/wan_emulation.sh show [DEV]
#
# Then, from the Mac, scripts/check_wan_emulation.py checks the edge agent's connect time to the
# cloud alias against the target (±20%).
set -euo pipefail

CMD="${1:-show}"
case "$CMD" in
    on)
        JSON="${2:-data/results/c2_wan_emulation.json}"
        [ -f "$JSON" ] || { echo "no $JSON: run scripts/measure_cloud_rtt.py on the Mac and copy it here" >&2; exit 1; }
        python3 - "$JSON" <<'PY' | while IFS= read -r line; do echo "+ $line"; sh -c "$line"; done
import json, sys
for c in json.load(open(sys.argv[1]))["tc_commands"]:
    print(c)
PY
        ;;
    off)
        DEV="${2:-eth0}"
        tc qdisc del dev "$DEV" root 2>/dev/null || true
        echo "WAN emulation off on $DEV"
        ;;
    show)
        DEV="${2:-eth0}"
        tc qdisc show dev "$DEV"
        tc filter show dev "$DEV"
        ;;
    *)
        echo "usage: $0 on [JSON] | off [DEV] | show [DEV]" >&2; exit 2 ;;
esac
