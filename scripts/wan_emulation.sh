#!/usr/bin/env bash
#
# wan_emulation.sh — C2's emulated WAN on the Mac (docs/LAN_SETUP.md, section 7): pf dummynet
# delays only the traffic between the Pi and the cloud alias, half the measured round trip each
# way, so the capture on bridge100 sits where a building router would: the Pi's packets to the
# cloud are captured before the delay, the cloud's replies after it. The rules live in their own
# anchor, com.apple/c2-wan, which /etc/pf.conf's dummynet-anchor "com.apple/*" evaluates; the
# main ruleset and Internet Sharing's NAT are not touched (on checks this by diffing them).
# dummynet has no jitter: the delay is constant (data/results/c2_wan_emulation.json records that).
#
#   sudo bash scripts/wan_emulation.sh on   [data/results/c2_wan_emulation.json]
#   sudo bash scripts/wan_emulation.sh off
#   sudo bash scripts/wan_emulation.sh show
#
# Then scripts/check_wan_emulation.py --interface bridge100 checks the result. Fallback if this
# cannot run: scripts/wan_emulation_pi.sh (netem on the Pi).
set -euo pipefail

IFACE="${IFACE:-bridge100}"
PI="${PI:-192.168.2.2}"
CLOUD="${CLOUD:-192.168.2.100}"
ANCHOR="com.apple/c2-wan"
PIPE_IN=1          # Pi → cloud alias, as it enters the Mac
PIPE_OUT=2         # cloud alias → Pi, as it leaves the Mac
STATE="${STATE:-/var/tmp/c2-wan}"     # pf enable token and the ruleset snapshots

[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }
mkdir -p "$STATE"

snapshot() {       # the main ruleset and NAT rules, which must not change
    { echo "## rules"; pfctl -s rules 2>/dev/null; echo "## nat"; pfctl -s nat 2>/dev/null; } > "$1"
}

case "${1:-show}" in
    on)
        JSON="${2:-data/results/c2_wan_emulation.json}"
        [ -f "$JSON" ] || { echo "no $JSON: run scripts/measure_cloud_rtt.py first" >&2; exit 1; }
        ONE_WAY="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["emulation"]["one_way_ms"])' "$JSON")"
        grep -q '^dummynet-anchor "com.apple/\*"' /etc/pf.conf \
            || { echo "/etc/pf.conf has no dummynet-anchor \"com.apple/*\": use the Pi fallback" >&2; exit 1; }
        snapshot "$STATE/before.txt"
        dnctl pipe "$PIPE_IN" config delay "$ONE_WAY"
        dnctl pipe "$PIPE_OUT" config delay "$ONE_WAY"
        printf 'dummynet in quick on %s proto tcp from %s to %s pipe %s\ndummynet out quick on %s proto tcp from %s to %s pipe %s\n' \
            "$IFACE" "$PI" "$CLOUD" "$PIPE_IN" "$IFACE" "$CLOUD" "$PI" "$PIPE_OUT" | pfctl -a "$ANCHOR" -f -
        TOKEN="$(pfctl -E 2>&1 | sed -n 's/.*Token : \([0-9][0-9]*\).*/\1/p')"
        [ -n "$TOKEN" ] && echo "$TOKEN" > "$STATE/token"
        snapshot "$STATE/after.txt"
        if diff -q "$STATE/before.txt" "$STATE/after.txt" >/dev/null; then
            echo "main ruleset and NAT unchanged"
        else
            echo "WARNING: the main ruleset or NAT changed:" >&2; diff "$STATE/before.txt" "$STATE/after.txt" >&2 || true
        fi
        echo "WAN emulation on: $ONE_WAY ms each way between $PI and $CLOUD on $IFACE (pf token ${TOKEN:-?})"
        ;;
    off)
        pfctl -a "$ANCHOR" -F all 2>/dev/null || true
        dnctl pipe delete "$PIPE_IN" 2>/dev/null || true
        dnctl pipe delete "$PIPE_OUT" 2>/dev/null || true
        if [ -f "$STATE/token" ]; then pfctl -X "$(cat "$STATE/token")" 2>/dev/null || true; rm -f "$STATE/token"; fi
        echo "WAN emulation off"
        ;;
    show)
        echo "## anchor $ANCHOR"; pfctl -a "$ANCHOR" -s rules 2>/dev/null || true
        echo "## pipes"; dnctl list 2>/dev/null || true
        echo "## pf"; pfctl -s info 2>/dev/null | head -1
        ;;
    *)
        echo "usage: sudo $0 on [JSON] | off | show" >&2; exit 2 ;;
esac
