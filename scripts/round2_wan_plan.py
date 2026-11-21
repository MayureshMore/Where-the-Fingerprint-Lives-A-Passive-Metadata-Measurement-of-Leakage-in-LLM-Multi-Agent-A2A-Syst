#!/usr/bin/env python3
"""
The emulated WAN of paper 2's round-2 sessions, from C2's measurement (data/results/c2_wan_emulation.json):
one JSON per session, in the form scripts/wan_emulation.sh, scripts/wan_emulation_pi.sh,
scripts/check_wan_emulation.py, scripts/c2_guard.py and scripts/collect_session.py --wan-target read.

    b1_wan.json         B1 (reply shaping): arms lan_padmax (8300) and lan_shaped (8400), both on C2's
                        WAN: 6 ms each way on the Mac (dummynet pipes 1 and 2), no jitter
    b2_wan_jitter.json  B2 (jitter and server load): arms lan (8100, C2's WAN) and lan_jl (8500): the
                        same 6 ms mean one way, of which 2 ms is dummynet (pipes 3 and 4) and 4 ms is a
                        normal delay with sd 1.8 ms, on the request side by netem on the Pi's egress
                        (with a rate, so packets keep their order) and on the reply side by the cloud
                        agents (every SSE event, in order; serve_cloud.py --jitter); draws below 0 are
                        clipped to 0 on both sides
B3 (a second day of C2's lan arm) uses c2_wan_emulation.json itself.

The jitter's sd per direction comes from the two IQRs C2 measured: a normal's sd is IQR / 1.349; the
cloud round trip (Mac → EC2 us-west-1) spreads by sd_cloud, the Pi ↔ Mac Wi-Fi alone by sd_base, so the
internet part adds sqrt(sd_cloud² − sd_base²) per round trip, split evenly: / √2 per direction (1.83 ms,
used as 1.8 ms).

What the jitter arm cannot match: the reply side's jitter is in the cloud agent, so only the SSE
events get it; the cloud's other packets (TCP and TLS handshakes, ACKs, HTTP headers) see 2 ms one way
instead of 6. Its handshakes are therefore 4 ms shorter than the control's, for every task alike; the
per-arm targets below say what the checks expect.

    python scripts/round2_wan_plan.py            # → data/results/b1_wan.json, b2_wan_jitter.json
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from defense.shaping import clipped_normal  # noqa: E402
from scripts.measure_cloud_rtt import ANCHOR, lock_ports  # noqa: E402

IQR_PER_SD = 2 * 0.6744897501960817            # a normal's IQR in sds
JITTER_MEAN_MS, JITTER_SD_MS, DUMMYNET_JITTER_ARM_MS = 4.0, 1.8, 2
NETEM_RATE = "1gbit"                            # 12 µs per 1,500-byte packet; with a rate netem keeps order
SHAPE_B1 = "2048/14/128/0.05/truncate"
LOAD_CONCURRENCY = 2


def jitter_sd(cloud_iqr: float, base_iqr: float) -> dict:
    sd_c, sd_b = cloud_iqr / IQR_PER_SD, base_iqr / IQR_PER_SD
    rtt = math.sqrt(max(0.0, sd_c ** 2 - sd_b ** 2))
    return {"cloud_iqr_ms": cloud_iqr, "base_iqr_ms": base_iqr, "sd_cloud_ms": sd_c, "sd_base_ms": sd_b,
            "internet_sd_rtt_ms": rtt, "per_direction_sd_ms": rtt / math.sqrt(2), "used_sd_ms": JITTER_SD_MS,
            "rule": "sd = IQR / 1.349 (normal); internet sd per round trip = sqrt(sd_cloud² − sd_base²); "
                    "per direction = that / √2"}


def rules(e: dict, bases: list[int], jitter_ports: list[int]) -> list[str]:
    """pf anchor rules, first match wins (quick): the jitter arm's ports into pipes 3 and 4, then
    everything else between the Pi and the alias into pipes 1 and 2, then the port lock."""
    iface, pi, cloud, mac = e["iface"], e["pi"], e["cloud"], e["mac"]
    out = []
    if jitter_ports:
        jp = " ".join(map(str, jitter_ports))
        out += [f"dummynet in quick on {iface} proto tcp from {pi} to {cloud} port {{ {jp} }} pipe 3",
                f"dummynet out quick on {iface} proto tcp from {cloud} port {{ {jp} }} to {pi} pipe 4"]
    ports = " ".join(str(p) for p in lock_ports(bases))
    return out + [f"dummynet in quick on {iface} proto tcp from {pi} to {cloud} pipe 1",
                  f"dummynet out quick on {iface} proto tcp from {cloud} to {pi} pipe 2",
                  f"pass in quick on {iface} proto tcp from {pi} to {{ {mac} {cloud} }} port {{ {ports} }}",
                  f"block in quick on {iface} proto tcp from any to {{ {mac} {cloud} }} port {{ {ports} }}"]


def mac_commands(pipes: list[list[int]], rule_list: list[str]) -> list[str]:
    r = "\\n".join(rule_list)
    return [f"dnctl pipe {n} config delay {ms}" for n, ms in pipes] + [f"printf '{r}\\n' | pfctl -a {ANCHOR} -f -",
                                                                        "pfctl -E"]


def pi_commands(dev: str, cloud: str, ports: list[int]) -> list[str]:
    """netem on a fourth prio band that the default priomap never uses; u32 filters send only the
    Pi's packets to the jitter arm's cloud ports there. With a rate, netem sends each packet at
    max(the previous one's departure, its arrival + its delay) + its transmission time: no reordering."""
    out = [f"tc qdisc del dev {dev} root 2>/dev/null || true",
           f"tc qdisc add dev {dev} root handle 1: prio bands 4 priomap 1 2 2 2 1 2 0 0 1 1 1 1 1 1 1 1",
           f"tc qdisc add dev {dev} parent 1:4 handle 40: netem delay {JITTER_MEAN_MS:g}ms {JITTER_SD_MS:g}ms "
           f"distribution normal rate {NETEM_RATE}"]
    out += [f"tc filter add dev {dev} parent 1: protocol ip prio 1 u32 match ip dst {cloud}/32 match ip protocol 6 0xff "
            f"match ip dport {p} 0xffff flowid 1:4" for p in ports]
    return out


def _git() -> dict:
    def run(*args):
        return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()
    return {"git_commit": run("rev-parse", "HEAD") or None,
            "git_dirty": bool(run("status", "--porcelain", "--", ".", ":(exclude)data"))}


def plans(c2: dict) -> dict[str, dict]:
    e = c2["emulation"]
    one_way, rtt, delay = int(e["one_way_ms"]), float(c2["target_rtt_ms"]), float(c2["delay_ms"])
    common = {k: c2[k] for k in ("endpoint", "cloud_rtt", "base_rtt", "total_delay_ms", "target_rtt_ms", "delay_ms")}
    src = {"measurement": "data/results/c2_wan_emulation.json", "measured_at": c2["measured_at"],
           "measurement_commit": c2.get("git_commit")}
    dev = c2["fallback_pi_netem"]["dev"]

    b1_bases = [8300, 8400]
    b1_rules = rules(e, b1_bases, [])
    b1 = {"paper": "P2", "round": 2, "session": "B1", "purpose": "reply shaping: lan_shaped against lan_padmax on C2's WAN",
          **src, **common, "jitter_ms": 0,
          "arms": {"8300": {"name": "lan_padmax", "target_rtt_ms": rtt, "delay_ms": delay, "pipes": [1, 2]},
                   "8400": {"name": "lan_shaped", "target_rtt_ms": rtt, "delay_ms": delay, "pipes": [1, 2],
                            "shape": SHAPE_B1}},
          "emulation": {**{k: e[k] for k in ("iface", "pi", "cloud", "mac")}, "bases": b1_bases, "one_way_ms": one_way,
                        "round_trip_ms": 2 * one_way, "jitter_ms": 0, "pipes": [[1, one_way], [2, one_way]],
                        "where": e["where"], "port_lock": f"the Mac's ports {lock_ports(b1_bases)} on {e['mac']} and "
                                                          f"{e['cloud']} accept only {e['pi']}",
                        "rules": b1_rules, "commands": mac_commands([[1, one_way], [2, one_way]], b1_rules)}}

    b2_bases, jl = [8100, 8500], 8500
    jports = [jl + 1, jl + 2]
    pipes = [[1, one_way], [2, one_way], [3, DUMMYNET_JITTER_ARM_MS], [4, DUMMYNET_JITTER_ARM_MS]]
    b2_rules = rules(e, b2_bases, jports)
    c = clipped_normal(JITTER_MEAN_MS, JITTER_SD_MS)
    jl_delay = 2.0 * DUMMYNET_JITTER_ARM_MS                         # SYN → SYN-ACK at the capture: pipes 3 + 4
    jl_rtt = rtt - delay + jl_delay + c["mean"]                      # the Pi's connect: + netem on its SYN
    jitter = {
        "distribution": f"normal, mean {JITTER_MEAN_MS:g} ms, sd {JITTER_SD_MS:g} ms per direction",
        "negative_draws": "clipped to 0, on both sides: netem sends a packet whose drawn delay is negative at once "
                          "(and with a rate never before the packet ahead of it); the cloud agents take max(0, draw) "
                          "(defense/shaping.py Jitter)",
        "clipped": {"p_clipped": c["p_clipped"], "mean_ms": c["mean"], "sd_ms": c["sd"]},
        "derivation": jitter_sd(c2["cloud_rtt"]["iqr_ms"], c2["base_rtt"]["iqr_ms"]),
        "request_side": {"where": f"Pi egress ({dev}), only packets to {e['cloud']} ports {jports}: every packet "
                                  "the Pi sends on the jitter arm's cloud connections (requests and ACKs), before the "
                                  "capture",
                         "netem": f"delay {JITTER_MEAN_MS:g}ms {JITTER_SD_MS:g}ms distribution normal rate {NETEM_RATE}",
                         "order": "kept: with a rate, netem never sends a packet before the one ahead of it; check in a "
                                  "capture with scripts/check_reorder.py",
                         "burst_note": "packets that arrive together leave at the latest of their draws so far, so the "
                                       "later packets of a multi-packet request wait a little longer than the mean"},
        "reply_side": {"where": "the cloud agents (serve_cloud.py --jitter 8500=4/1.8/SEED): every SSE event, in "
                                "order, before the capture; the agent's other packets are not delayed",
                       "spec": f"{JITTER_MEAN_MS:g}/{JITTER_SD_MS:g}"},
        "one_way_ms": {"requests": DUMMYNET_JITTER_ARM_MS + c["mean"], "reply_events": DUMMYNET_JITTER_ARM_MS + c["mean"],
                       "reply_other_packets": DUMMYNET_JITTER_ARM_MS, "control": one_way},
        "pi_netem": {"dev": dev, "tc_commands": pi_commands(dev, e["cloud"], jports)},
    }
    b2 = {"paper": "P2", "round": 2, "session": "B2",
          "purpose": "jitter and server load: lan_jl (both) against lan (neither), interleaved", **src, **common,
          "jitter_ms": JITTER_SD_MS, "jitter": jitter,
          "load": {"where": "the Mac's Ollama, localhost (never on the observed path), during every lan_jl task only",
                   "concurrency": LOAD_CONCURRENCY, "ollama": "OLLAMA_NUM_PARALLEL=4 (two load streams + the agents)",
                   "tool": "scripts/ollama_load.py; collect_session.py --arm ...,load=2"},
          "arms": {"8100": {"name": "lan", "target_rtt_ms": rtt, "delay_ms": delay, "pipes": [1, 2]},
                   "8500": {"name": "lan_jl", "target_rtt_ms": jl_rtt, "delay_ms": jl_delay, "pipes": [3, 4],
                            "jitter": f"{JITTER_MEAN_MS:g}/{JITTER_SD_MS:g}", "load": LOAD_CONCURRENCY,
                            "targets_note": f"SYN → SYN-ACK at the capture is pipes 3 + 4 ({jl_delay:g} ms); the Pi's "
                                            f"connect time is C2's target − {delay:g} + {jl_delay:g} + the netem delay on "
                                            f"its SYN ({c['mean']:.2f} ms mean)"}},
          "emulation": {**{k: e[k] for k in ("iface", "pi", "cloud", "mac")}, "bases": b2_bases, "one_way_ms": one_way,
                        "round_trip_ms": 2 * one_way, "jitter_ms": 0, "pipes": pipes, "where": e["where"],
                        "port_lock": f"the Mac's ports {lock_ports(b2_bases)} on {e['mac']} and {e['cloud']} accept only "
                                     f"{e['pi']}",
                        "rules": b2_rules, "commands": mac_commands(pipes, b2_rules)}}
    return {"b1_wan.json": b1, "b2_wan_jitter.json": b2}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--c2", default="data/results/c2_wan_emulation.json")
    p.add_argument("--out-dir", default="data/results", dest="out_dir")
    p.add_argument("--allow-dirty", action="store_true", dest="allow_dirty")
    a = p.parse_args(argv)
    git = _git()
    if git["git_dirty"] and not a.allow_dirty:
        raise SystemExit("uncommitted code: commit first (or --allow-dirty for a dry run)")
    for name, plan in plans(json.loads(Path(a.c2).read_text())).items():
        out = Path(a.out_dir) / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({**plan, **git}, indent=2))
        print(f"→ {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
