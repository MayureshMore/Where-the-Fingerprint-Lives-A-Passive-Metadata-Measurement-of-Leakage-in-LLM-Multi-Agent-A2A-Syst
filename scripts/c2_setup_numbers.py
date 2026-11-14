#!/usr/bin/env python3
"""
C2's setup numbers (paper 2, D2 in the evaluation setup) from the released capture folders, so each
has a JSON behind it: the session, the Raspberry Pi, the task-input sizes per task type, and the
emulated WAN as the guard and the WAN checks measured it.

Reads only files in the data release (DATA.md, paper 2 archive): data/raw_c2*/ sidecars and
session_meta.json; data/raw_c2/wan_guard.json, wan_check_start.json, wan_check_after.json.

    session    start, end and length; traces per arm and task type; failed and retried tasks; median
               time per trace
    pi         temperature range over all traces (sidecar pi_temp_c), throttled traces
    inputs     the task input in UTF-8 bytes (sidecar prompt_bytes) per task type: median, quartiles
               (statistics.quantiles, n=4), range; checked equal across the arms
    wan        target round trip and dummynet delay; the guard's 50-trace windows (Pi → cloud connect
               median, SYN → SYN-ACK at the capture, ticket service connect); the WAN checks before and
               after (cloud end to end; the Mac's own address, never delayed); the collector's probes
               before each round

Usage (never overwrites):
    python scripts/c2_setup_numbers.py --out data/results/c2_setup     # → .json and .md
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from a2a_leakcheck.cli import _git  # noqa: E402

ARMS = {"lan": "raw_c2", "lan_pad": "raw_c2_pad", "lan_padmax": "raw_c2_padmax"}


def rng(xs) -> list[float]:
    xs = list(xs)
    return [min(xs), max(xs)] if xs else [None, None]


def wire_bytes(pcap: Path, endpoints: set[tuple[str, int]]) -> tuple[int, int]:
    """On-wire IP bytes (the pcap's original length minus the link header) and packets of the TCP segments
    to or from any of endpoints (address, port), as an observer view keeps them."""
    raw = pcap.read_bytes()
    e = "<" if raw[:4] in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1") else ">"
    off = {0: 4, 1: 14}[struct.unpack(e + "I", raw[20:24])[0]]
    pos, total, n = 24, 0, 0
    while pos + 16 <= len(raw):
        incl, orig = struct.unpack(e + "II", raw[pos + 8:pos + 16])
        d = raw[pos + 16:pos + 16 + incl]
        pos += 16 + incl
        if len(d) < off + 24 or d[off] >> 4 != 4 or d[off + 9] != 6:
            continue
        l4 = off + (d[off] & 0x0F) * 4
        src = (".".join(map(str, d[off + 12:off + 16])), int.from_bytes(d[l4:l4 + 2], "big"))
        dst = (".".join(map(str, d[off + 16:off + 20])), int.from_bytes(d[l4 + 2:l4 + 4], "big"))
        if src in endpoints or dst in endpoints:
            total += orig - off
            n += 1
    return total, n


def sidecars(d: Path) -> list[dict]:
    return [json.loads(f.read_text()) for f in sorted(d.glob("*_edge_cloud_*.json"))]


def numbers(data: Path) -> dict:
    meta = json.loads((data / "raw_c2" / "session_meta.json").read_text())
    side = {arm: sidecars(data / d) for arm, d in ARMS.items()}
    sched = meta["schedule"]
    a = dt.datetime.strptime(meta["started"], "%Y-%m-%dT%H:%M:%S%z")
    b = dt.datetime.strptime(meta["finished"], "%Y-%m-%dT%H:%M:%S%z")
    mins = round((b - a).total_seconds() / 60)
    out = {"paper": "P2", "collection_id": meta["collection_id"], "data_dir": str(data), **_git(),
           "source": "data/raw_c2*/ sidecars, session_meta.json, wan_guard.json, wan_check_{start,after}.json"}
    out["session"] = {
        "started": meta["started"], "finished": meta["finished"],
        "length": f"{mins // 60} h {mins % 60} min",
        "traces": {arm: len(s) for arm, s in side.items()},
        "per_task_type": {arm: dict(sorted({t: sum(x["task_type"] == t for x in s)
                                            for t in {x["task_type"] for x in s}}.items()))
                          for arm, s in side.items()},
        "failed": meta["failures"], "scheduled": len(sched),
        "succeeded_first_try": sum(1 for x in sched if x["success"] and x["attempt"] == 1),
        "retried": sum(1 for x in sched if x["attempt"] > 1),
        "median_s_per_trace": meta["pace"]["median_s_per_trace"]}
    temps = [x["pi_temp_c"] for s in side.values() for x in s if x.get("pi_temp_c") is not None]
    out["pi"] = {"temperature_c": rng(temps), "traces_with_temperature": len(temps),
                 "throttled_traces": sum(1 for x in sched if x.get("pi_throttled"))}
    inputs, same = {}, True
    for t in sorted({x["task_type"] for x in side["lan"]}):
        by_arm = {arm: sorted(x["prompt_bytes"] for x in s if x["task_type"] == t) for arm, s in side.items()}
        same &= all(v == by_arm["lan"] for v in by_arm.values())
        v = by_arm["lan"]
        q = statistics.quantiles(v, n=4)
        inputs[t] = {"n": len(v), "median": statistics.median(v), "q1": q[0], "q3": q[2], "min": v[0], "max": v[-1]}
    answers = {}
    for arm, sc in side.items():
        for t in sorted({x["task_type"] for x in sc}):
            v = sorted(x["edge_report"]["answer_chars"] for x in sc if x["task_type"] == t)
            q = statistics.quantiles(v, n=4)
            answers.setdefault(arm, {})[t] = {"n": len(v), "median": statistics.median(v), "q1": q[0], "q3": q[2],
                                              "min": v[0], "max": v[-1]}
    out["answers"] = {"unit": "characters of the answer the edge agent filed (sidecar edge_report.answer_chars); "
                              "no file records token counts", "per_arm": answers}
    wire = {}
    for arm, d in ARMS.items():
        rows = []
        for x in side[arm]:
            eps = x["agent_endpoints"]
            views = {v: {(eps[r].rsplit(":", 1)[0], int(eps[r].rsplit(":", 1)[1])) for r in seen}
                     for v, seen in x["vantages"].items()}
            rows.append({v: wire_bytes(data / d / f"{x['run_id']}.pcap", h) for v, h in views.items()})
        wire[arm] = {v: {"bytes_mean": statistics.mean(r[v][0] for r in rows),
                         "packets_mean": statistics.mean(r[v][1] for r in rows)} for v in rows[0]}
    for arm in wire:
        for v in wire[arm]:
            wire[arm][v]["bytes_ratio_to_lan"] = wire[arm][v]["bytes_mean"] / wire["lan"][v]["bytes_mean"]
            wire[arm][v]["packets_ratio_to_lan"] = wire[arm][v]["packets_mean"] / wire["lan"][v]["packets_mean"]
    out["on_wire"] = {"unit": "IP bytes and packets per trace, to or from the agent endpoints each view sees (all "
                              "1,000 tasks of the arm; a task the view does not see counts as 0)", "per_arm": wire}
    pad = {}
    for x in json.loads((data / "raw_c2" / "design_check_seq.json").read_text())["arms"]:
        if "padding" in x:
            q = x["padding"]
            pad[x["arm"]] = {"buckets": q["buckets"], "first_requests": q["traces"],
                             "by_bucket": q["message_bytes_by_bucket"], "median_overhead_bytes": q["median_overhead"]}
    out["padding_check"] = {"source": "data/raw_c2/design_check_seq.json", "per_arm": pad}
    edge = meta["edge"]["lan"]
    out["models"] = {"edge": {"model": edge["model"], "num_predict": edge["num_predict"]},
                     "cloud": {"model": sorted({a["model"] for a in meta["arms"]}), "num_predict": meta["num_predict"]},
                     "pad_buckets": {a["name"]: a["pad_buckets"] for a in meta["arms"]},
                     "pad_expect": {a["name"]: a["pad_expect"] for a in meta["arms"]}}
    allv = [x["prompt_bytes"] for x in side["lan"]]
    out["inputs"] = {"unit": "UTF-8 bytes of the prompt (sidecar prompt_bytes)", "per_task_type": inputs,
                     "median_all": statistics.median(allv), "max_all": max(allv), "same_in_all_arms": same}
    g = json.loads((data / "raw_c2" / "wan_guard.json").read_text())
    conn = [r for c in g["checks"] for r in c["rows"] if r["check"].startswith("4.")]
    probes = meta["wan_probes"]
    wc = {}
    for name in ("wan_check_start", "wan_check_after"):
        w = json.loads((data / "raw_c2" / f"{name}.json").read_text())
        edge = [c for c in w["checks"] if c["edge"] != "all"]          # per edge agent, timed on the Pi
        cap = {c["check"][:2]: c["value"] for c in w["checks"] if c["edge"] == "all" and c["value"] is not None}
        wc[name] = {"pass": w["pass"],
                    "cloud_end_to_end_ms": rng(c["value"] for c in edge if c["check"].startswith("b.")),
                    "mac_address_base_ms": rng(c["value"] for c in edge if c["check"].startswith("c.")),
                    "cloud_syn_synack_at_capture_ms": cap.get("b."), "mac_syn_synack_at_capture_ms": cap.get("c."),
                    "base_rtt_median_ms": (w.get("base_rtt_probes") or {}).get("median_ms")}
    out["wan"] = {
        "target_rtt_ms": g["target"]["target_rtt_ms"], "dummynet_ms": g["target"]["dummynet_ms"],
        "one_way_ms": g["target"]["one_way_ms"],
        "guard": {"checks": len(g["checks"]), "all_ok": all(c["ok"] for c in g["checks"]),
                  "suspect": len(g["suspect"]), "stopped": g["stopped"], "traces_checked": g["traces_checked"],
                  "windows": len(conn), "handshakes": sum(r["handshakes"] for r in conn),
                  "pi_connect_median_ms": statistics.median(r["pi_connect_median_ms"] for r in conn),
                  "pi_connect_window_medians_ms": rng(r["pi_connect_median_ms"] for r in conn),
                  "syn_synack_window_medians_ms": rng(r["dummynet_median_ms"] for r in conn),
                  "min_syn_synack_ms": min(r["min_dummynet_ms"] for r in conn),
                  "ticket_connect_window_medians_ms": rng(r["ticket_median_ms"] for r in conn)},
        "wan_checks": wc,
        "collector_probes": {"n": len(probes), "medians_ms": rng(p["median_ms"] for p in probes),
                             "median_of_medians_ms": statistics.median(p["median_ms"] for p in probes),
                             "base_medians_ms": rng(p["base_median_ms"] for p in probes),
                             "all_ok": all(p["ok"] for p in probes)}}
    return out


def markdown(n: dict) -> str:
    s, p, i, w = n["session"], n["pi"], n["inputs"], n["wan"]
    g = w["guard"]
    f = lambda r, d=1: f"{r[0]:.{d}f}–{r[1]:.{d}f}"  # noqa: E731
    b = lambda v: f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}".rstrip("0")  # noqa: E731
    lines = ["# C2 setup numbers\n", f"From {n['data_dir']} at commit {str(n['git_commit'])[:8]}"
             f"{' (uncommitted changes)' if n['git_dirty'] else ''}.\n",
             f"Session {s['started']} to {s['finished']} ({s['length']}); traces per arm "
             f"{', '.join(f'{k} {v}' for k, v in s['traces'].items())}; {s['failed']} failed, "
             f"{s['succeeded_first_try']} of {s['scheduled']} succeeded on the first try; median "
             f"{s['median_s_per_trace']:.2f} s per trace.\n",
             f"Raspberry Pi: {f(p['temperature_c'])} °C over {p['traces_with_temperature']} traces; "
             f"{p['throttled_traces']} throttled.\n",
             f"## Task inputs ({i['unit']}; same in all arms: {i['same_in_all_arms']})\n",
             "| Task type | n | Median | IQR | Range |", "|---|---|---|---|---|"]
    for t, x in i["per_task_type"].items():
        lines.append(f"| {t} | {x['n']} | {b(x['median'])} | {b(x['q1'])}–{b(x['q3'])} | {x['min']:,}–{x['max']:,} |")
    lines += [f"\nMedian over all tasks {b(i['median_all'])} B; largest {i['max_all']:,} B.\n",
              f"## Answers ({n['answers']['unit']})\n", "| Arm | Task type | n | Median | IQR | Range |",
              "|---|---|---|---|---|---|"]
    for arm, ts in n["answers"]["per_arm"].items():
        for t, x in ts.items():
            lines.append(f"| {arm} | {t} | {x['n']} | {b(x['median'])} | {b(x['q1'])}–{b(x['q3'])} | {x['min']:,}–{x['max']:,} |")
    lines += ["\n## On the wire (" + n["on_wire"]["unit"] + ")\n", "| Arm | View | Bytes per trace | Packets | Bytes vs lan | Packets vs lan |",
              "|---|---|---|---|---|---|"]
    for arm, vs in n["on_wire"]["per_arm"].items():
        for v, x in vs.items():
            lines.append(f"| {arm} | {v} | {x['bytes_mean']:,.0f} | {x['packets_mean']:,.1f} | ×{x['bytes_ratio_to_lan']:.3f} | "
                         f"×{x['packets_ratio_to_lan']:.3f} |")
    for arm, x in n["padding_check"]["per_arm"].items():
        lines.append(f"\nPadding check, {arm}: {x['first_requests']} first requests by bucket {x['by_bucket']}; median "
                     f"overhead {x['median_overhead_bytes']:.0f} B.")
    m = n["models"]
    lines += [f"\nModels: edge {m['edge']['model']} (num_predict {m['edge']['num_predict']}); cloud "
              f"{', '.join(m['cloud']['model'])} (num_predict {m['cloud']['num_predict']}). Padding buckets: "
              + "; ".join(f"{k} {v or 'none'}" for k, v in m["pad_buckets"].items()) + ".\n",
              "## Emulated WAN\n",
              f"- Target round trip {w['target_rtt_ms']:.1f} ms; dummynet {w['dummynet_ms']:.0f} ms "
              f"({w['one_way_ms']:.0f} ms each way).",
              f"- Guard: {g['checks']} checks, all passed: {g['all_ok']}; {g['suspect']} suspect traces; "
              f"stopped: {g['stopped']}. Over {g['handshakes']:,} handshakes in {g['windows']} windows of 50 "
              f"traces, Pi → cloud connect median {g['pi_connect_median_ms']:.1f} ms (window medians "
              f"{f(g['pi_connect_window_medians_ms'])} ms); SYN → SYN-ACK at the capture "
              f"{f(g['syn_synack_window_medians_ms'])} ms, never under {g['min_syn_synack_ms']:.1f} ms; "
              f"ticket service connect {f(g['ticket_connect_window_medians_ms'])} ms."]
    for k, x in w["wan_checks"].items():
        lines.append(f"- {k}: passed {x['pass']}; per edge agent, cloud end to end {f(x['cloud_end_to_end_ms'])} ms "
                     f"and the Mac's own address {f(x['mac_address_base_ms'])} ms; at the capture, SYN → SYN-ACK "
                     f"{x['cloud_syn_synack_at_capture_ms']:.1f} ms to the cloud, {x['mac_syn_synack_at_capture_ms']:.1f} ms "
                     f"to the Mac" +
                     (f"; base round trip median {x['base_rtt_median_ms']:.1f} ms" if x["base_rtt_median_ms"] else ""))
    c = w["collector_probes"]
    lines.append(f"- Collector's probes before each round ({c['n']}): medians {f(c['medians_ms'])} ms, median "
                 f"{c['median_of_medians_ms']:.1f} ms; the Mac's own address {f(c['base_medians_ms'])} ms.\n")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--data", default="data")
    p.add_argument("--out", default=None, help="path stem for .json and .md (not overwritten)")
    a = p.parse_args(argv)
    n = numbers(Path(a.data))
    md = markdown(n)
    print(md)
    if a.out:
        for ext, text in ((".json", json.dumps(n, indent=2) + "\n"), (".md", md)):
            f = Path(a.out + ext)
            if f.exists():
                raise SystemExit(f"{f} exists: not overwritten")
            f.write_text(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
