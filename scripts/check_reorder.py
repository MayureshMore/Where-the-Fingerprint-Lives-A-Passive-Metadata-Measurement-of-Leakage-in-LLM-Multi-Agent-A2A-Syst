#!/usr/bin/env python3
"""
Do the jitter arm's packets keep their order? (paper 2 round 2, B2: netem with jitter reorders packets
unless it has a rate; the cloud agents' event jitter is in order by construction.) Per arm folder of
edge-cloud captures (header-only is enough: sequence numbers and lengths come from the headers), per
direction of every connection to the cloud agents (Pi → cloud: requests and the Pi's ACKs, netem's
side; cloud → Pi: replies, the agents' side):

    out_of_order   a data segment that starts below the highest sequence already seen and carries bytes
                   not seen before: it filled a hole, so it arrived after a later segment. Reordering
                   fills a hole within the jitter (a few ms); a lost segment's retransmission fills it
                   after a round trip or more, so the fill delay (first byte past the hole → the fill)
                   is reported too
    duplicates     a data segment all of whose bytes were seen before (a retransmission)
    handshakes     SYN → SYN-ACK and SYN → the Pi's ACK at the capture: their spread shows the jitter

The home Wi-Fi reorders on its own: in C2 (no netem) the Pi's packets reached the Mac's capture out
of order for 0.4% (lan) to 6.6% (lan_padmax, 8 KB requests) of the Pi → cloud data segments, mostly
within 0.1 ms (frames of one aggregate), some by tens of ms (link-layer retries); the cloud → Pi side,
captured where it is sent, showed none. So the test is against the control arm collected in the same
session: holes filled after more than --wifi-ms (0.1 ms) and within --retx-ms (20 ms) are what netem's
jitter would add, and the jitter arm's share of them may exceed the control's by at most --margin
(0.5 percentage points; netem without a rate would reorder a large part of every multi-packet
request). The cloud → Pi side must show no hole at all. Exit 1 otherwise. Compare arms whose requests
are alike (B2: lan_jl against lan, both unpadded): larger requests give the Wi-Fi more to reorder (C2's
lan_padmax shows 0.82% against lan's 0.06%).

    python scripts/check_reorder.py data/raw_c2b2_jl --control data/raw_c2b2_lan --json data/raw_c2b2_jl/reorder_check.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from features.kfp import tcp_records  # noqa: E402
from scripts.c2_guard import handshakes  # noqa: E402

SYN = 0x02


def directions(pcap: Path, cloud: set[int]) -> dict:
    """Per direction: data segments, holes filled (with the delay since the first byte past the hole), duplicates."""
    st: dict[tuple[int, int], dict] = {}
    out = {d: {"segments": 0, "out_of_order": 0, "fill_ms": [], "duplicates": 0} for d in ("pi_to_cloud", "cloud_to_pi")}
    for ts, sp, dp, _, pl, fl, seq in tcp_records(pcap):
        if dp in cloud:
            d = "pi_to_cloud"
        elif sp in cloud:
            d = "cloud_to_pi"
        else:
            continue
        key = (sp, dp)
        if fl & SYN:
            st.pop(key, None)
        if pl == 0:
            continue
        s = st.setdefault(key, {"base": seq, "seen": [], "top": 0, "top_ts": {}})
        lo = ((seq - s["base"] + 2 ** 31) % 2 ** 32) - 2 ** 31
        hi = lo + pl
        new = pl - sum(max(0, min(hi, y) - max(lo, x)) for x, y in s["seen"])
        o = out[d]
        o["segments"] += 1
        if new == 0:
            o["duplicates"] += 1
        elif lo < s["top"]:
            o["out_of_order"] += 1
            past = [t for start, t in s["top_ts"].items() if start >= hi]
            o["fill_ms"].append((ts - min(past)) * 1000 if past else None)
        if hi > s["top"]:
            s["top_ts"][lo] = ts
            s["top"] = hi
        merged: list[list[int]] = []
        for x, y in sorted(s["seen"] + [(lo, hi)]):
            if merged and x <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], y)
            else:
                merged.append([x, y])
        s["seen"] = [tuple(m) for m in merged]
    return out


def check_dir(folder: Path, wifi_ms: float, retx_ms: float) -> dict:
    tot = {d: {"segments": 0, "out_of_order": 0, "fill_ms": [], "duplicates": 0} for d in ("pi_to_cloud", "cloud_to_pi")}
    syn_synack, syn_ack, traces = [], [], 0
    for side in sorted(folder.glob("*_edge_cloud_*.json")):
        pcap = side.with_suffix(".pcap")
        if not pcap.exists():
            continue
        sc = json.loads(side.read_text())
        cloud = {int(sc["agent_endpoints"][r].rsplit(":", 1)[1]) for r in ("diagnostics", "knowledge")
                 if r in sc.get("agent_endpoints", {})}
        ticket = {int(sc["agent_endpoints"]["ticket"].rsplit(":", 1)[1])} if "ticket" in sc.get("agent_endpoints", {}) else set()
        traces += 1
        for d, v in directions(pcap, cloud).items():
            for k in ("segments", "out_of_order", "duplicates"):
                tot[d][k] += v[k]
            tot[d]["fill_ms"] += v["fill_ms"]
        for a, b in handshakes(pcap, cloud, ticket)["cloud"]:
            syn_synack.append(a)
            syn_ack.append(b)

    def spread(xs):
        if len(xs) < 2:
            return None
        q = statistics.quantiles(xs, n=4)
        return {"n": len(xs), "median_ms": statistics.median(xs), "iqr_ms": q[2] - q[0], "sd_ms": statistics.stdev(xs)}

    res = {"folder": str(folder), "traces": traces, "handshake_syn_synack": spread(syn_synack),
           "handshake_syn_ack": spread(syn_ack)}
    for d, v in tot.items():
        fills = [x for x in v["fill_ms"] if x is not None]
        jit = [x for x in fills if wifi_ms < x <= retx_ms]
        res[d] = {"segments": v["segments"], "duplicates": v["duplicates"], "out_of_order": v["out_of_order"],
                  "within_wifi_ms": sum(x <= wifi_ms for x in fills), "reordered": len(jit),
                  "after_retx_ms": sum(x > retx_ms for x in fills),
                  "reordered_share": len(jit) / v["segments"] if v["segments"] else 0.0,
                  "fill_ms_max": max(fills, default=None), "fill_ms_median": statistics.median(fills) if fills else None}
    return res


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("dirs", nargs="+", help="the arm(s) to check (B2: the jitter arm)")
    p.add_argument("--control", required=True, help="the arm collected beside them without jitter")
    p.add_argument("--wifi-ms", type=float, default=0.1, dest="wifi_ms")
    p.add_argument("--retx-ms", type=float, default=20.0, dest="retx_ms")
    p.add_argument("--margin", type=float, default=0.005)
    p.add_argument("--json", default=None)
    a = p.parse_args(argv)
    ctl = check_dir(Path(a.control), a.wifi_ms, a.retx_ms)
    ctl["ok"] = ctl["cloud_to_pi"]["out_of_order"] == 0
    rows = [check_dir(Path(d), a.wifi_ms, a.retx_ms) for d in a.dirs]
    for r in rows:
        r["ok"] = (r["cloud_to_pi"]["out_of_order"] == 0 and
                   r["pi_to_cloud"]["reordered_share"] <= ctl["pi_to_cloud"]["reordered_share"] + a.margin)
    for r in [ctl] + rows:
        h = r["handshake_syn_ack"] or {}
        pc = r["pi_to_cloud"]
        print(f"{r['folder']}{' (control)' if r is ctl else ''}: {r['traces']} traces; Pi → cloud {pc['segments']} "
              f"segments, {pc['out_of_order']} holes filled ({pc['within_wifi_ms']} within {a.wifi_ms:g} ms, "
              f"{pc['reordered']} = {pc['reordered_share']:.2%} within {a.retx_ms:g} ms, {pc['after_retx_ms']} later); "
              f"cloud → Pi {r['cloud_to_pi']['segments']} segments, {r['cloud_to_pi']['out_of_order']} holes; "
              f"SYN → ACK median {h.get('median_ms', float('nan')):.1f} ms, sd {h.get('sd_ms', float('nan')):.2f} ms "
              f"→ {'ok' if r['ok'] else 'REORDERED'}")
    out = {"wifi_ms": a.wifi_ms, "retx_ms": a.retx_ms, "margin": a.margin, "control": ctl, "dirs": rows,
           "ok": ctl["ok"] and all(r["ok"] for r in rows)}
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=1))
    print("PASS" if out["ok"] else "FAIL")
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
