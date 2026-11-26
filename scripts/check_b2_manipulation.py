#!/usr/bin/env python3
"""
B2's manipulation checks (docs/PREREG_C2B2.md): did the treatment arm get the WAN jitter and the server
load, and only it? Each check passes or fails; the session is valid only if every one passes, and an
invalid session is still analysed and reported, as invalid.

  netem_pi        the Pi's `tc -s qdisc show dev wlan0`, saved before and after the session: the netem
                  qdisc is there both times with the plan's delay (4 ms, 1.8 ms), and its packet count
                  grew by at least 0.9 x the treatment's Pi -> cloud packets in the captures
  netem_capture   at the capture, the cloud's SYN-ACK -> the Pi's ACK: the treatment's median exceeds
                  the control's by the netem mean (the plan's clipped mean, 4.01 ms) +- 1.5 ms. The Pi's
                  ACK leaves through netem on the treatment's cloud ports only; without netem the two
                  medians would match (the same Wi-Fi)
  reorder         scripts/check_reorder.py's result (the treatment's Pi -> cloud reordering within the
                  control's + 0.5 percentage points; no hole on the cloud -> Pi side): ok
  jitter_log      the cloud agents' record of every reply (sidecar cloud_replies, jitter.draws): pooled
                  over the treatment, the draws' mean and sd within 0.2 ms of the plan's clipped normal
                  (4.01, 1.78 ms); every escalated treatment trace has the record, with the plan's spec;
                  no control trace has one
  load_windows    every treatment trace ran under the load: its window (sidecar load, t_start to
                  t_stop) covers the trace (start_ts to end_ts), with the plan's concurrency, every
                  stream generating at the start and tokens received; no control trace has a load, and
                  no control trace overlaps any load window
  load_slowdown   the cloud answered more slowly under load: per escalated task type, the median of the
                  edge's cloud call time (sidecar edge_report.seconds.answer) in the treatment is at least
                  1.10 x the control's
  gpu             the model wholly in GPU memory at the session's context: every parallel check (each
                  start and resume) ok, and the last GPU check of every round and the one at the end
                  with a share >= 0.999 and context --context (32768) (session_meta.json)
  keeper          scripts/pi_wifi_keeper.py check over the session: pass

    python scripts/check_b2_manipulation.py --control data/raw_c2b2_padmax --treatment data/raw_c2b2_padmax_jl \\
        --target data/results/b2_wan_jitter.json --tc-start data/raw_c2b2_padmax/pi_tc_start.txt \\
        --tc-end data/raw_c2b2_padmax/pi_tc_end.txt --reorder data/raw_c2b2_padmax_jl/reorder_check.json \\
        --keeper data/raw_c2b2_padmax/wifi_keeper_check.json --json data/raw_c2b2_padmax_jl/manipulation_check.json

Exit 0 if valid, 1 if not.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from features.kfp import tcp_records  # noqa: E402
from scripts.c2_guard import handshakes  # noqa: E402

ESCALATED = ("fault_diagnosis", "procedure_lookup", "sensor_analysis")
CLOUD_ROLES = ("diagnostics", "knowledge")
NETEM_TOL_MS, JITTER_TOL_MS, SLOWDOWN, TC_SHARE, GPU_SHARE = 1.5, 0.2, 1.10, 0.9, 0.999


def sidecars(folder: Path) -> list[dict]:
    out = []
    for side in sorted(folder.glob("*_edge_cloud_*.json")):
        sc = json.loads(side.read_text())
        if sc.get("success") and side.with_suffix(".pcap").exists():
            sc["_pcap"] = side.with_suffix(".pcap")
            out.append(sc)
    return out


def cloud_ports(sc: dict) -> set[int]:
    eps = sc.get("agent_endpoints") or {}
    return {int(eps[r].rsplit(":", 1)[1]) for r in CLOUD_ROLES if r in eps}


def ticket_ports(sc: dict) -> set[int]:
    eps = sc.get("agent_endpoints") or {}
    return {int(eps["ticket"].rsplit(":", 1)[1])} if "ticket" in eps else set()


# ── netem on the Pi ──────────────────────────────────────────────────────────

def parse_tc(text: str) -> dict | None:
    """The netem qdisc in `tc -s qdisc show`: handle, delay and jitter (ms), packets sent; None if absent."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.search(r"qdisc netem (\S+).*?delay ([\d.]+)(us|ms|s)\s+([\d.]+)(us|ms|s)", line)
        if not m:
            continue
        scale = {"us": 1e-3, "ms": 1.0, "s": 1e3}
        sent = None
        for nxt in lines[i + 1:i + 4]:
            s = re.search(r"Sent (\d+) bytes (\d+) pkt", nxt)
            if s:
                sent = int(s.group(2))
                break
        return {"handle": m.group(1), "delay_ms": float(m.group(2)) * scale[m.group(3)],
                "jitter_ms": float(m.group(4)) * scale[m.group(5)], "packets": sent}
    return None


def pi_to_cloud_packets(rows: list[dict]) -> int:
    return sum(1 for sc in rows for r in tcp_records(sc["_pcap"]) if r[2] in cloud_ports(sc))


def check_netem_pi(start: str, end: str, treatment: list[dict], mean_ms: float, sd_ms: float) -> dict:
    a, b = parse_tc(start), parse_tc(end)
    sent = pi_to_cloud_packets(treatment)
    grew = (b["packets"] - a["packets"]) if a and b and a["packets"] is not None and b["packets"] is not None else None
    ok = (a is not None and b is not None and all(abs(x["delay_ms"] - mean_ms) < 1e-6 and abs(x["jitter_ms"] - sd_ms) < 1e-6
                                                   for x in (a, b))
          and grew is not None and grew >= TC_SHARE * sent)
    return {"start": a, "end": b, "netem_packets": grew, "captured_pi_to_cloud_packets": sent,
            "rule": f"netem with delay {mean_ms:g} ms, jitter {sd_ms:g} ms before and after; its packets grew by at "
                    f"least {TC_SHARE:g} x the treatment's Pi -> cloud packets in the captures", "ok": ok}


def synack_to_ack(rows: list[dict]) -> list[float]:
    out = []
    for sc in rows:
        for a, b in handshakes(sc["_pcap"], cloud_ports(sc), ticket_ports(sc))["cloud"]:
            out.append(b - a)
    return out


def check_netem_capture(control: list[dict], treatment: list[dict], mean_ms: float) -> dict:
    c, t = synack_to_ack(control), synack_to_ack(treatment)
    if not c or not t:
        return {"ok": False, "detail": "no cloud handshake in an arm"}
    mc, mt = statistics.median(c), statistics.median(t)
    diff = mt - mc
    return {"control_median_ms": mc, "treatment_median_ms": mt, "n": [len(c), len(t)], "difference_ms": diff,
            "expected_ms": mean_ms, "tolerance_ms": NETEM_TOL_MS,
            "rule": "the cloud's SYN-ACK -> the Pi's ACK at the capture: treatment median - control median within "
                    f"the netem mean +- {NETEM_TOL_MS:g} ms", "ok": abs(diff - mean_ms) <= NETEM_TOL_MS}


# ── the cloud agents' reply jitter ───────────────────────────────────────────

def check_jitter_log(control: list[dict], treatment: list[dict], spec: str, mean_ms: float, sd_ms: float) -> dict:
    n = s = ss = 0.0
    missing, wrong_spec, with_record = [], [], 0
    for sc in treatment:
        recs = [r.get("jitter") for r in sc.get("cloud_replies") or [] if r.get("jitter")]
        if not (sc.get("edge_report") or {}).get("escalated"):
            continue
        if not recs:
            missing.append(sc["run_id"])
            continue
        with_record += 1
        for j in recs:
            if not str(j.get("spec", "")).startswith(spec + "/") and j.get("spec") != spec:
                wrong_spec.append(sc["run_id"])
            d = j.get("draws") or {}
            n, s, ss = n + d.get("n", 0), s + d.get("sum_ms", 0.0), ss + d.get("sumsq_ms2", 0.0)
    in_control = [sc["run_id"] for sc in control if any(r.get("jitter") for r in sc.get("cloud_replies") or [])]
    m = s / n if n else None
    sd = math.sqrt(max(0.0, ss / n - m * m) * n / (n - 1)) if n > 1 else None
    ok = (m is not None and sd is not None and abs(m - mean_ms) <= JITTER_TOL_MS and abs(sd - sd_ms) <= JITTER_TOL_MS
          and not missing and not wrong_spec and not in_control)
    return {"draws": int(n), "mean_ms": m, "sd_ms": sd, "expected": {"mean_ms": mean_ms, "sd_ms": sd_ms},
            "tolerance_ms": JITTER_TOL_MS, "escalated_traces_with_record": with_record,
            "escalated_traces_without_record": missing[:20], "n_without_record": len(missing),
            "wrong_spec": sorted(set(wrong_spec))[:20], "control_traces_with_jitter": in_control[:20],
            "n_control_with_jitter": len(in_control), "ok": ok}


# ── the server load ──────────────────────────────────────────────────────────

def check_load_windows(control: list[dict], treatment: list[dict], concurrency: int) -> dict:
    bad, windows = [], []
    for sc in treatment:
        ld = sc.get("load")
        why = None
        if not ld:
            why = "no load"
        elif ld.get("concurrency") != concurrency:
            why = f"concurrency {ld.get('concurrency')}"
        elif ld.get("generating_at_start") != concurrency:
            why = f"{ld.get('generating_at_start')} of {concurrency} streams generating at the start"
        elif not ld.get("tokens"):
            why = "no tokens"
        elif not (ld["t_start"] <= sc["start_ts"] and ld.get("t_stop", 0) >= sc["end_ts"]):
            why = "the window does not cover the trace"
        if why:
            bad.append({"run": sc["run_id"], "why": why})
        if ld and ld.get("t_stop"):
            windows.append((ld["t_start"], ld["t_stop"]))
    loaded_control = [sc["run_id"] for sc in control if sc.get("load")]
    windows.sort()
    overlap = []
    for sc in control:
        a, b = sc["start_ts"], sc["end_ts"]
        if any(s < b and a < e for s, e in windows):
            overlap.append(sc["run_id"])
    tokens = [sc["load"]["tokens_per_s"] for sc in treatment if sc.get("load") and sc["load"].get("tokens_per_s")]
    return {"treatment_traces": len(treatment), "not_under_load": bad[:20], "n_not_under_load": len(bad),
            "control_with_load": loaded_control[:20], "control_overlapping_a_load": overlap[:20],
            "n_control_overlapping": len(overlap), "load_tokens_per_s_median": statistics.median(tokens) if tokens else None,
            "ok": not bad and not loaded_control and not overlap}


def cloud_seconds(rows: list[dict], task_type: str) -> list[float]:
    out = []
    for sc in rows:
        er = sc.get("edge_report") or {}
        sec = (er.get("seconds") or {}).get("answer")
        if sc.get("task_type") == task_type and er.get("escalated") and sec is not None:
            out.append(sec)
    return out


def check_load_slowdown(control: list[dict], treatment: list[dict]) -> dict:
    per, ok = {}, True
    for t in ESCALATED:
        c, x = cloud_seconds(control, t), cloud_seconds(treatment, t)
        if not c or not x:
            per[t] = {"ok": False, "detail": "no cloud call in an arm"}
            ok = False
            continue
        mc, mx = statistics.median(c), statistics.median(x)
        r = mx / mc if mc else None
        per[t] = {"control_median_s": mc, "treatment_median_s": mx, "ratio": r, "n": [len(c), len(x)],
                  "ok": r is not None and r >= SLOWDOWN}
        ok = ok and per[t]["ok"]
    return {"per_task_type": per, "rule": f"treatment median / control median >= {SLOWDOWN:g} per escalated task type",
            "ok": ok}


def check_gpu(meta: dict, context: int) -> dict:
    load = meta.get("load") or {}
    pchecks = load.get("parallel_checks") or ([load["parallel_check"]] if load.get("parallel_check") else [])

    def good(g):
        gpu = (g or {}).get("gpu") or {}
        return (gpu.get("share") or 0) >= GPU_SHARE and gpu.get("context_length") == context

    par_ok = bool(pchecks) and all(p.get("ok") and good(p) for p in pchecks)
    last = {}
    for g in meta.get("gpu_checks") or []:
        last[str(g["round"])] = g
    rounds = {str(e["round"]) for e in meta.get("schedule") or []}
    missing = sorted(rounds - set(last), key=lambda x: int(x))
    failed = sorted(r for r, g in last.items() if not good(g))
    end_ok = "end" in last and good(last["end"])
    return {"parallel_checks": len(pchecks), "parallel_ok": par_ok, "rounds_checked": len(set(last) - {"end"}),
            "rounds_without_check": missing, "rounds_failed": failed, "end_ok": end_ok, "context": context,
            "rule": f"every parallel check ok; the last GPU check of every round and the end check: share >= "
                    f"{GPU_SHARE:g}, context {context}", "ok": par_ok and not missing and not failed and end_ok}


def _git() -> dict:
    def run(*args):
        return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()
    return {"git_commit": run("rev-parse", "HEAD") or None,
            "git_dirty": bool(run("status", "--porcelain", "--", ".", ":(exclude)data"))}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--control", required=True)
    p.add_argument("--treatment", required=True)
    p.add_argument("--target", required=True, help="the WAN plan (data/results/b2_wan_jitter.json)")
    p.add_argument("--tc-start", required=True, dest="tc_start")
    p.add_argument("--tc-end", required=True, dest="tc_end")
    p.add_argument("--reorder", required=True, help="scripts/check_reorder.py --json")
    p.add_argument("--keeper", required=True, help="scripts/pi_wifi_keeper.py check --json")
    p.add_argument("--context", type=int, default=32768)
    p.add_argument("--json", default=None)
    a = p.parse_args(argv)

    plan = json.loads(Path(a.target).read_text())
    jit = plan["jitter"]
    spec = jit["reply_side"]["spec"]
    mean_c, sd_c = jit["clipped"]["mean_ms"], jit["clipped"]["sd_ms"]
    raw_mean, raw_sd = (float(x) for x in spec.split("/")[:2])
    concurrency = plan["load"]["concurrency"]
    control, treatment = sidecars(Path(a.control)), sidecars(Path(a.treatment))
    meta = json.loads((Path(a.treatment) / "session_meta.json").read_text())

    checks = {
        "netem_pi": check_netem_pi(Path(a.tc_start).read_text(), Path(a.tc_end).read_text(), treatment, raw_mean, raw_sd),
        "netem_capture": check_netem_capture(control, treatment, mean_c),
        "reorder": {"file": a.reorder, "ok": bool(json.loads(Path(a.reorder).read_text()).get("ok"))},
        "jitter_log": check_jitter_log(control, treatment, f"{raw_mean:g}/{raw_sd:g}", mean_c, sd_c),
        "load_windows": check_load_windows(control, treatment, concurrency),
        "load_slowdown": check_load_slowdown(control, treatment),
        "gpu": check_gpu(meta, a.context),
        "keeper": {"file": a.keeper, "ok": bool(json.loads(Path(a.keeper).read_text()).get("pass"))},
    }
    valid = all(c["ok"] for c in checks.values())
    out = {"collection_id": meta.get("collection_id"), "control": a.control, "treatment": a.treatment,
           "traces": {"control": len(control), "treatment": len(treatment)}, "checks": checks, "valid": valid,
           "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **_git()}
    for k, c in checks.items():
        print(f"  {k:<15} {'ok' if c['ok'] else 'FAIL'}")
    n = checks["netem_capture"]
    if "difference_ms" in n:
        print(f"    SYN-ACK -> ACK: treatment {n['treatment_median_ms']:.2f} ms, control {n['control_median_ms']:.2f} ms, "
              f"difference {n['difference_ms']:.2f} (expected {n['expected_ms']:.2f} +- {NETEM_TOL_MS:g})")
    j = checks["jitter_log"]
    if j["mean_ms"] is not None:
        print(f"    reply jitter: {j['draws']} draws, mean {j['mean_ms']:.3f} ms, sd {j['sd_ms']:.3f} ms "
              f"(expected {mean_c:.3f}, {sd_c:.3f})")
    for t, r in checks["load_slowdown"]["per_task_type"].items():
        if "ratio" in r and r["ratio"] is not None:
            print(f"    {t}: cloud call {r['control_median_s']:.2f} s -> {r['treatment_median_s']:.2f} s under load "
                  f"(x{r['ratio']:.2f})")
    print("VALID" if valid else "INVALID")
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=1, default=str))
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())
