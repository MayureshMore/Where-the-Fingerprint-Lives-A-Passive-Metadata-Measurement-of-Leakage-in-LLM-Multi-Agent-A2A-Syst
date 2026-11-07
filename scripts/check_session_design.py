#!/usr/bin/env python3
"""
Design checks for a session collection (scripts/collect_session.py), run on the pilot before
the full collection:

  a. predecessors   per arm and workflow, the share of each workflow that ran last on the same
                    agent ports (session_meta.json). A capture starts while the previous trace's
                    connections on those ports are still closing; in the TLS control the
                    predecessor was fixed (100%) and its leftover packets leaked the workflow
                    (data/results/tls_control_gap.md). FLAG when a workflow's most common
                    predecessor exceeds 40%; FAIL when a flagged share is also unlikely under a
                    random order (one-sided binomial test against 1/number of workflows,
                    Bonferroni over every arm × workflow × predecessor cell): one round of the
                    pilot gives about 30 traces per cell, and a 40% share then arises by chance
                    in roughly half of all pilots.
  b. leftovers      connections opened before each capture (scripts/audit_dropped_connections.py):
                    per trace, and whether any carries data beyond the close. FAIL on data.
  c. padding        for an arm with pad buckets: the first A2A message's on-wire size minus its
                    bucket is the TLS and HTTP overhead, which is nearly constant if the body
                    really is padded. FAIL if under 95% of traces sit within ±32 B of the median
                    overhead, or the median is outside 100–1000 B. The message is the request
                    writes on the first request's link (features/first_request.py) up to the
                    first response data, after the TLS handshake, of at least 300 B. The first
                    request as features/first_request.py measures it also takes in a GET of the
                    agent card when the orchestrator has just started (the first trace of each
                    condition in each round: 197 B more on loopback, 60 of C1's 600 traces); those
                    traces are counted, not failed. An arm with pad_expect (C2's lan_padmax: buckets
                    8192/16384, every first request meant for 8192) also FAILS unless every first
                    message lands in that one bucket; the share in it is reported.
  d. audit_null     every sidecar carries prompt_group and audit_null (scripts/collect_session.py),
                    audit_null constant within a prompt group.

Usage:
    python scripts/check_session_design.py data/raw_c2_pilot data/raw_c2_pad_pilot data/raw_c2_padmax_pilot \\
        --json data/raw_c2_pilot/design_check.json
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from features.connections import own_packets  # noqa: E402
from features.first_request import first_request  # noqa: E402
from features.kfp import tcp_packets  # noqa: E402
from scripts.audit_dropped_connections import audit_trace  # noqa: E402

MAX_PREDECESSOR = 0.40
ALPHA = 0.05
PAD_TOLERANCE = 32
PAD_OVERHEAD = (100, 1000)
MIN_MESSAGE = 300             # bytes; the agent-card GET is under it, an A2A request well over


def _sidecars(raw: Path) -> list[tuple[Path, dict]]:
    out = []
    for side in sorted(raw.glob("*.json")):
        sc = json.loads(side.read_text())
        if "run_id" in sc and side.with_suffix(".pcap").exists():
            out.append((side, sc))
    return out


def _ports(sc: dict) -> set[int]:
    eps = sc["agent_endpoints"]
    eps = ast.literal_eval(eps) if isinstance(eps, str) else eps
    return {int(str(v).rsplit(":", 1)[1]) for v in eps.values()}


def predecessors(meta: dict) -> dict:
    """({arm: {workflow: {predecessor: share}}}, {arm: {workflow: traces with a predecessor}});
    the same ports = the same arm and topology."""
    sched = sorted((e for e in meta["schedule"] if e["success"]), key=lambda e: e["start_ts"])
    last, out = {}, defaultdict(lambda: defaultdict(Counter))
    for e in sched:
        top, wf, _ = e["item"].split("/")
        key = (e["arm"], top)
        out[e["arm"]][wf][last.get(key, "none")] += 1
        last[key] = wf
    return ({arm: {wf: {p: n / sum(c.values()) for p, n in c.most_common()} for wf, c in sorted(w.items())}
             for arm, w in sorted(out.items())},
            {arm: {wf: sum(c.values()) - c.get("none", 0) for wf, c in w.items()} for arm, w in out.items()})


def _binom_sf(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p)."""
    return float(sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1)))


def predecessor_flags(pred: dict, counts: dict, n_wf: int) -> dict:
    """Most common predecessor per arm and workflow: share, n, flag (> 40%) and the Bonferroni-
    adjusted binomial p against a uniform predecessor."""
    cells = sum(len(w) for w in pred.values()) * n_wf
    out = {}
    for arm, w in pred.items():
        for wf, shares in w.items():
            top, share = max(((k, v) for k, v in shares.items() if k != "none"), key=lambda kv: kv[1],
                             default=("none", 0.0))
            n = counts[arm][wf]
            k = round(share * n)
            p_adj = min(1.0, cells * _binom_sf(k, n, 1 / n_wf))
            out.setdefault(arm, {})[wf] = {"predecessor": top, "share": share, "n": n,
                                           "flag": share > MAX_PREDECESSOR, "p_bonferroni": p_adj,
                                           "fail": share > MAX_PREDECESSOR and p_adj < ALPHA}
    return out


def _bucket_below(n: int, buckets: list[int]) -> int:
    top = max(buckets)
    cands = sorted(set(buckets) | {top * k for k in range(1, n // top + 2)})
    below = [b for b in cands if b <= n]
    return below[-1] if below else 0


def first_message(pcap: Path, servers: set[int], tls: bool) -> tuple[int, int]:
    """(first_request bytes, bytes of the first A2A message on that link): request writes up to
    the first response data, after the ClientHello and client Finished, of at least MIN_MESSAGE."""
    pk = own_packets(tcp_packets(pcap), servers)
    fr = first_request(pk, servers)
    if not fr["link"]:
        return 0, 0
    link, msgs, cur, seen = fr["link"], [], 0, 0
    for _, sp, dp, _, pl, _ in pk:
        if pl == 0:
            continue
        if (sp, dp) == link:
            seen += 1
            if tls and (seen == 1 or (seen == 2 and pl <= 100)):       # ClientHello, client Finished
                continue
            cur += pl
        elif (dp, sp) == link and cur:
            msgs.append(cur)
            cur = 0
    if cur:
        msgs.append(cur)
    return fr["bytes"], next((m for m in msgs if m >= MIN_MESSAGE), 0)


def padding(rows: list[tuple[dict, tuple[int, int]]], buckets: list[int], expect: int | None = None) -> dict:
    """expect: the one bucket every first message should land in (pad_expect), or None."""
    msg = [m for _, (_, m) in rows]
    over = np.array([m - _bucket_below(m, buckets) for m in msg], dtype=float)
    med = float(np.median(over))
    within = float((np.abs(over - med) <= PAD_TOLERANCE).mean())
    by = Counter(_bucket_below(m, buckets) for m in msg)
    extra = [fr - m for _, (fr, m) in rows if fr - m > 0]
    one = None
    if expect is not None:
        n_in = by.get(expect, 0)
        one = {"bucket": expect, "share": n_in / len(msg) if msg else 0.0, "traces_in": n_in,
               "traces_outside": len(msg) - n_in, "largest_message": max(msg) if msg else 0,
               "ok": bool(msg) and n_in == len(msg)}
    return {"buckets": buckets, "traces": len(rows), "median_overhead": med,
            "overhead_range": [float(over.min()), float(over.max())], "share_within_tolerance": within,
            "message_bytes_by_bucket": {str(k): v for k, v in sorted(by.items())},
            "distinct_message_sizes": len(set(msg)),
            "first_request_includes_card_fetch": {"traces": len(extra),
                                                  "extra_bytes": dict(Counter(extra).most_common(5))},
            "expected_bucket": one,
            "ok": within >= 0.95 and PAD_OVERHEAD[0] <= med <= PAD_OVERHEAD[1] and (one is None or one["ok"])}


def check_arm(raw: Path) -> dict:
    meta = json.loads((raw / "session_meta.json").read_text())
    arm = next((a for a in meta["arms"] if Path(a["out"]).resolve() == raw.resolve()), None)
    name = arm["name"] if arm else raw.name
    rows, left, groups = [], [], defaultdict(set)
    for side, sc in _sidecars(raw):
        if sc.get("success") is False:
            continue
        ports, pcap = _ports(sc), side.with_suffix(".pcap")
        a = audit_trace(pcap, ports, bool(sc.get("tls", True)))
        left.append(a)
        rows.append((sc, first_message(pcap, ports, bool(sc.get("tls", True)))))
        groups[sc.get("prompt_group")].add(sc.get("audit_null"))
    n_left = np.array([len(a["connections"]) for a in left])
    res = {"arm": name, "raw_dir": str(raw), "traces": len(rows),
           "leftovers": {"connections_per_trace_mean": float(n_left.mean()) if len(n_left) else 0.0,
                         "connections_per_trace_max": int(n_left.max()) if len(n_left) else 0,
                         "traces_with_leftovers": int((n_left > 0).sum()),
                         "traces_with_application_data": sorted(sc["run_id"] for (sc, _), a in zip(rows, left)
                                                                if a["application_data"])},
           "audit_null": {"present": sum(1 for sc, _ in rows if sc.get("audit_null") in tuple("abcd")),
                          "groups_with_two_values": sum(1 for v in groups.values() if len(v) > 1),
                          "counts": dict(Counter(sc.get("audit_null") for sc, _ in rows))}}
    pad = (arm or {}).get("pad_buckets") or []
    if pad:
        res["padding"] = padding([r for r in rows if r[1][1]], pad, (arm or {}).get("pad_expect"))
    res["audit_null"]["missing_prompt_group"] = sum(1 for sc, _ in rows if not sc.get("prompt_group"))
    res["ok"] = (not res["leftovers"]["traces_with_application_data"]
                 and res["audit_null"]["present"] == len(rows)
                 and not res["audit_null"]["missing_prompt_group"]
                 and not res["audit_null"]["groups_with_two_values"]
                 and res.get("padding", {"ok": True})["ok"])
    return res, meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("raw", nargs="+", help="one output directory per arm of the session")
    ap.add_argument("--json")
    a = ap.parse_args()
    arms, meta = [], None
    for raw in a.raw:
        r, meta = check_arm(Path(raw))
        arms.append(r)
    pred, counts = predecessors(meta)
    top = predecessor_flags(pred, counts, len(meta["workflows"]))
    fails = [(arm, wf) for arm, w in top.items() for wf, v in w.items() if v["fail"]]
    out = {"predecessors": pred, "most_common_predecessor": top, "max_predecessor_share": MAX_PREDECESSOR,
           "alpha": ALPHA, "predecessor_failures": fails, "arms": arms,
           "ok": not fails and all(r["ok"] for r in arms)}
    for arm, w in top.items():
        for wf, v in w.items():
            if not v["n"]:
                print(f"[a] {arm:10s} {wf:20s} no trace with a predecessor on its ports")
                continue
            print(f"[a] {arm:10s} {wf:20s} most common predecessor {v['predecessor']} {v['share']:.0%} "
                  f"of {v['n']}" + (f"  FLAG (p_bonferroni {v['p_bonferroni']:.3f}"
                                    f"{', FAIL' if v['fail'] else ''})" if v["flag"] else ""))
    for r in arms:
        lo = r["leftovers"]
        print(f"[b] {r['arm']:10s} leftover connections per trace {lo['connections_per_trace_mean']:.2f} "
              f"(max {lo['connections_per_trace_max']}, {lo['traces_with_leftovers']} of {r['traces']} traces); "
              f"with data: {len(lo['traces_with_application_data'])}")
        if "padding" in r:
            p = r["padding"]
            print(f"[c] {r['arm']:10s} first A2A message − bucket: median {p['median_overhead']:.0f} B, "
                  f"{p['share_within_tolerance']:.0%} within ±{PAD_TOLERANCE} B; by bucket "
                  f"{p['message_bytes_by_bucket']}; agent-card GET in the first request: "
                  f"{p['first_request_includes_card_fetch']['traces']} traces  {'ok' if p['ok'] else 'FAIL'}")
            if p.get("expected_bucket"):
                e = p["expected_bucket"]
                print(f"[c] {r['arm']:10s} first A2A messages in the {e['bucket']} bucket: {e['share']:.1%} "
                      f"({e['traces_in']} of {e['traces_in'] + e['traces_outside']}); largest message "
                      f"{e['largest_message']} B on the wire  {'ok' if e['ok'] else 'FAIL'}")
        an = r["audit_null"]
        print(f"[d] {r['arm']:10s} audit_null in {an['present']} of {r['traces']} sidecars, "
              f"{an['groups_with_two_values']} groups with two values, {an['missing_prompt_group']} without "
              f"prompt_group, counts {an['counts']}")
    print("PASS" if out["ok"] else "FAIL")
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=2))
    sys.exit(0 if out["ok"] else 1)


if __name__ == "__main__":
    main()
