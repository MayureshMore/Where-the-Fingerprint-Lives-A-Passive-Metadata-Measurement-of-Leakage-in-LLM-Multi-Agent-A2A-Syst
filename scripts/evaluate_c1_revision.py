#!/usr/bin/env python3
"""
Paper 1 revision checks on collection C1 (analysis only; no new collection).

  A10 capture     largest on-wire packet per direction, header sizes, loopback MTU, and how many
                  TCP segments each first request spans
  A2  input size  per-trace table (prompt characters, prompt bytes as JSON-encoded in the request,
                  first-request bytes); fit first-request bytes = prompt bytes + c_w per workflow;
                  the orchestrator's own text in the first request (its LLM-written sub-task plan,
                  agents/orchestrator.py), estimated per trace; scatter figure
  A3  pairs       response-side-only GBT on code_review vs data_analysis and research_retrieval vs
                  support_triage (same folds restricted to the pair)
  A6  topology    a fixed rule from the number of calls and their nesting in time (no ports or
                  addresses; 5-tuples only group packets into connections)
  A5  k-FP + GBT  k-FP's 138 direction and timing features with the GBT classifier, paired
                  against GBT on all features
  A7  role        role with leave-one-workflow-out and leave-one-topology-out folds
  A8  replies     response bytes per role (token counts were not logged)
  A4  padding     every request message padded to (a) 1 KB linear buckets and (b) power-of-two
                  buckets from 1 KB, re-segmented at the capture's largest TCP payload; all
                  features recomputed; GBT on the same folds; bandwidth overhead
  A9  templates   each prompt traced back to its generator template; workflow GBT with folds
                  grouped by template instead of by prompt

Measurement: a trace uses only the TCP connections it opens itself (features/connections.py);
features from data/processed_c1_own. --legacy-all-connections uses every connection on the agent
ports (data/processed_c1).

GBT, 5-fold StratifiedGroupKFold by prompt group (seed 42), the same folds as
scripts/evaluate_c1.py; macro-F1 with 95% cluster-bootstrap CIs over prompt groups (template
groups for A9); paired differences on the same group resamples.

Writes data/results/c1_revision.{json,md}, data/results/c1_first_request_traces.csv and
data/results/figures/c1_first_request_scatter.png.

Usage:
    python scripts/evaluate_c1_revision.py
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import struct
import sys
import uuid
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.model_selection import StratifiedGroupKFold

sys.path.insert(0, str(Path(__file__).parent.parent))

from a2a.types import Message, MessageSendParams, Part, Role, SendStreamingMessageRequest, TextPart  # noqa: E402
from agents.base import request_body_len  # noqa: E402
import scripts.evaluate_c1 as ev  # noqa: E402
from features.connections import own_packets  # noqa: E402
from features.extractor import FeatureExtractor  # noqa: E402
from features.first_request import REQUEST_GAP_S, first_request  # noqa: E402
from features.kfp import tcp_packets  # noqa: E402
from features.per_flow import PerFlowFeatures  # noqa: E402
from features.roles import role_vectors  # noqa: E402
from scripts.evaluate_c1 import (  # noqa: E402
    LENGTH_PAIRS, SEED, TASKS, _git, _sub_splits, folds, kfp_matrix, load, oof_predict, paired_diff,
    response_side_columns, score,
)
from scripts.strip_payload import _MAGICS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROC, RAW = Path("data/processed_c1_own"), Path("data/raw_c1")
LEGACY = False
TLS_RECORD_OVERHEAD = 22          # TLS 1.3 AES-GCM record: 5-byte header + 16-byte tag + 1 type byte
MIN_REQUEST, MIN_RESPONSE = 300, 50
FANOUT = {"star": 3, "chain": 1, "mesh": 2}      # orchestrator calls per topology (orchestrator.py)


def servers_of(eps: dict) -> set[int]:
    return {int(a.rsplit(":", 1)[1]) for a in eps.values()}


def side(base: str) -> dict:
    return json.loads((RAW / f"{base}.json").read_text())


# ── A10 ─────────────────────────────────────────────────────────────────────

def capture_facts(d: dict) -> dict:
    mx, mxp, hdr = {"request": 0, "response": 0}, {"request": 0, "response": 0}, Counter()
    spans, linktypes = defaultdict(Counter), Counter()
    for base, eps, wf in zip(d["base"], d["endpoints"], d["y"]):
        servers = servers_of(eps)
        raw = (RAW / f"{base}.pcap").read_bytes()[:24]
        linktypes[struct.unpack(_MAGICS[raw[:4]] + "I", raw[20:24])[0]] += 1
        pk = tcp_packets(RAW / f"{base}.pcap")
        for _, sp, dp, wire, pl, _ in pk:
            k = "request" if dp in servers else "response" if sp in servers else None
            if k:
                mx[k], mxp[k] = max(mx[k], wire), max(mxp[k], pl)
                hdr[wire - pl] += 1
        spans[str(wf)][first_request(pk, servers, LEGACY)["packets"]] += 1
    return {"max_wire_bytes": mx, "max_tcp_payload_bytes": mxp,
            "header_bytes": {str(k): v for k, v in hdr.most_common()},
            "link_types": {str(k): v for k, v in linktypes.items()},
            "loopback_mtu_inferred": mxp["response"] + 52,      # IP 20 + TCP with timestamps 32
            "first_request_segments": {w: {str(k): v for k, v in sorted(c.items())} for w, c in spans.items()}}


# ── A2 ──────────────────────────────────────────────────────────────────────

def body_without_plan(prompt: str, topology: str) -> int:
    """Bytes of the first request's JSON-RPC body with an empty sub-task plan (orchestrator.py)."""
    text = f"Sub-task 1 of {FANOUT[topology]}:\n\n\nFULL TASK CONTEXT (use as needed):\n{prompt}"
    msg = Message(role=Role.user, message_id=uuid.uuid4().hex, parts=[Part(root=TextPart(text=text))])
    return request_body_len(SendStreamingMessageRequest(id=str(uuid.uuid4()), params=MessageSendParams(message=msg)))


def input_size(d: dict) -> tuple[list[dict], dict]:
    rows = []
    for base, eps, wf, top in zip(d["base"], d["endpoints"], d["y"], d["topology"]):
        prompt = side(base)["input_prompt"]
        fr = first_request(tcp_packets(RAW / f"{base}.pcap"), servers_of(eps), LEGACY)
        pjb = len(json.dumps(prompt, ensure_ascii=False).encode()) - 2
        body = fr["bytes"] - fr["first_payload"] - TLS_RECORD_OVERHEAD      # the body record, decrypted size
        rows.append({"run_id": base, "workflow": str(wf), "topology": str(top),
                     "prompt_chars": len(prompt), "prompt_json_bytes": pjb,
                     "first_request_bytes": fr["bytes"], "first_request_segments": fr["packets"],
                     "header_record_bytes": fr["first_payload"],
                     "plan_json_bytes_est": body - body_without_plan(prompt, str(top))})
    fit = {}
    for w in sorted({r["workflow"] for r in rows}):
        x = np.array([r["prompt_json_bytes"] for r in rows if r["workflow"] == w], float)
        yv = np.array([r["first_request_bytes"] for r in rows if r["workflow"] == w], float)
        plan = np.array([r["plan_json_bytes_est"] for r in rows if r["workflow"] == w], float)
        c = float(np.mean(yv - x))
        res = yv - x - c
        slope, icpt = np.polyfit(x, yv, 1)
        fit[w] = {"c_w": c, "residual_sd": float(res.std(ddof=1)), "max_abs_residual": float(np.abs(res).max()),
                  "free_fit_slope": float(slope), "free_fit_intercept": float(icpt),
                  "plan_json_bytes_median": float(np.median(plan)),
                  "plan_json_bytes_iqr": [float(np.percentile(plan, 25)), float(np.percentile(plan, 75))]}
    hdr = [r["header_record_bytes"] for r in rows]
    return rows, {"per_workflow": fit, "header_record_bytes": dict(Counter(hdr).most_common(5)),
                  "note": "first-request bytes = HTTP header record + body record; body = JSON-RPC "
                          "envelope + 'Sub-task i of n' + the orchestrator's LLM-written sub-task plan "
                          "+ the prompt (agents/orchestrator.py:45-53); plan bytes estimated as body "
                          "record − 22 B TLS overhead − the body built with an empty plan"}


def scatter(rows: list[dict], path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = {"code_review": "#1b6ca8", "data_analysis": "#e07b00", "research_retrieval": "#2e8b57",
              "support_triage": "#c0392b"}
    markers = {"star": "o", "chain": "s", "mesh": "^"}
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    for ax, zoom in ((axes[0], False), (axes[1], True)):
        for r in rows:
            if zoom and r["workflow"] not in ("research_retrieval", "support_triage"):
                continue
            ax.scatter(r["prompt_json_bytes"], r["first_request_bytes"], s=14, alpha=0.6,
                       c=colors[r["workflow"]], marker=markers[r["topology"]], linewidths=0)
        ax.set_xlabel("prompt bytes (JSON-encoded, as sent)")
        ax.set_ylabel("first-request bytes on the wire")
        if zoom:
            xs = [r["prompt_json_bytes"] for r in rows if r["workflow"] in ("research_retrieval", "support_triage")]
            ax.set_xlim(0, np.percentile(xs, 95) * 1.1)
            ax.set_title("research_retrieval and support_triage", fontsize=9)
        else:
            ax.set_title("all workflows", fontsize=9)
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], color=c, marker="o", ls="", label=w) for w, c in colors.items()]
    handles += [Line2D([], [], color="#555", marker=m, ls="", label=t) for t, m in markers.items()]
    axes[0].legend(handles=handles, fontsize=7, frameon=False)
    fig.suptitle("C1: prompt size vs first-request size (colour = workflow, marker = topology)", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(path, dpi=150)
    plt.close(fig)


# ── A3 ──────────────────────────────────────────────────────────────────────

def pairs_response_side(d: dict, splits) -> dict:
    out = {}
    cols = response_side_columns()
    for a, b in LENGTH_PAIRS:
        m = np.isin(d["y"], [a, b])
        sub, y, g = _sub_splits(splits, m), d["y"][m], d["g"][m]
        p_resp = oof_predict("gbt", "workflow", d["X"][m][:, cols], y, sub)
        p_all = oof_predict("gbt", "workflow", d["X"][m], y, sub)
        out[f"{a}_vs_{b}"] = {"chance": 0.5, "n": int(m.sum()), "dims": int(len(cols)),
                              "response_side": score(y, p_resp, g, [a, b]), "all": score(y, p_all, g, [a, b]),
                              "all_minus_response_side": paired_diff(y, p_all, p_resp, g, [a, b])}
    return out


# ── A6 ──────────────────────────────────────────────────────────────────────

def calls(pk, servers: set[int]) -> list[dict]:
    """Request messages (request-direction writes ≥ 300 B, ≤ 50 ms apart) with their active span:
    from the request to the last response packet of > 50 B on that connection before the next."""
    conns = defaultdict(list)
    for ts, sp, dp, _, pl, _ in pk:
        if dp in servers:
            conns[(sp, dp)].append((ts, -1, pl))
        elif sp in servers:
            conns[(dp, sp)].append((ts, 1, pl))
    out = []
    for pkts in conns.values():
        cur, last_req = None, None
        for ts, d, pl in pkts:
            if d == -1 and pl > 0:
                if cur is not None and last_req is not None and ts - last_req <= REQUEST_GAP_S:
                    cur["bytes"] += pl
                else:
                    if cur and cur["bytes"] >= MIN_REQUEST:
                        out.append(cur)
                    cur = {"start": ts, "end": ts, "bytes": pl}
                last_req = ts
            elif d == 1 and pl > MIN_RESPONSE and cur is not None:
                cur["end"] = ts
        if cur and cur["bytes"] >= MIN_REQUEST:
            out.append(cur)
    return out


def nesting(cs: list[dict]) -> int:
    """Calls a call is nested in, plus one, maximised: B is nested in A if B starts more than the
    50 ms request gap after A and ends before A ends (parallel fan-out calls are siblings)."""
    return max((1 + sum(1 for b in cs if b is not a and a["start"] - b["start"] > REQUEST_GAP_S
                        and a["end"] <= b["end"]) for a in cs), default=0)


def topology_rule(n_calls: int, depth: int) -> str:
    """From the call graph in the code: star = 3 parallel orchestrator calls, none nested; chain =
    3 calls each nested in the previous; mesh = 5 calls (orchestrator → executor and retriever,
    executor → retriever, retriever → validator twice)."""
    if depth <= 1:
        return "star"
    return "chain" if n_calls <= 3 else "mesh"


def topology_by_rule(d: dict) -> dict:
    pred, shape = [], defaultdict(Counter)
    for base, eps, top in zip(d["base"], d["endpoints"], d["y"]):
        servers = servers_of(eps)
        cs = calls(own_packets(tcp_packets(RAW / f"{base}.pcap"), servers, LEGACY), servers)
        n, dep = len(cs), nesting(cs)
        pred.append(topology_rule(n, dep))
        shape[str(top)][f"{n} calls, nesting {dep}"] += 1
    pred = np.array(pred)
    classes = sorted(set(d["y"].tolist()))
    conf = {t: {p: int(((d["y"] == t) & (pred == p)).sum()) for p in classes} for t in classes}
    return {"accuracy": float((pred == d["y"]).mean()), "n": int(len(pred)),
            "macro_f1": score(d["y"], pred, d["g"], classes), "confusion": conf,
            "shapes": {t: dict(c) for t, c in shape.items()}}


# ── A5 ──────────────────────────────────────────────────────────────────────

def kfp_with_gbt(task: str) -> dict:
    d = load(PROC, RAW, task)
    y, g = d["y"], d["g"]
    classes, sp = sorted(set(y.tolist())), folds(y, g)
    p_all = oof_predict("gbt", task, d["X"], y, sp)
    p_kfp = oof_predict("gbt", task, kfp_matrix(d, RAW), y, sp)
    return {"gbt_all_features": score(y, p_all, g, classes), "gbt_kfp_features": score(y, p_kfp, g, classes),
            "all_minus_kfp": paired_diff(y, p_all, p_kfp, g, classes)}


# ── A7 ──────────────────────────────────────────────────────────────────────

def role_held_out(d_role: dict, workflow_of: dict) -> dict:
    y, g, X = d_role["y"], d_role["g"], d_role["X"]
    classes = sorted(set(y.tolist()))
    wf = np.array([workflow_of[b] for b in d_role["base"]])
    top = np.array(d_role["topology"])
    out = {"grouped_cv": score(y, oof_predict("gbt", "role", X, y, folds(y, g)), g, classes)}
    for name, key in (("leave_one_workflow_out", wf), ("leave_one_topology_out", top)):
        sp = [(np.where(key != v)[0], np.where(key == v)[0]) for v in sorted(set(key.tolist()))]
        p = oof_predict("gbt", "role", X, y, sp)
        out[name] = {**score(y, p, g, classes), "folds": len(sp),
                     "per_held_out": {v: score(y[key == v], p[key == v], g[key == v], classes)["macro_f1"]
                                      for v in sorted(set(key.tolist()))}}
    return out


# ── A8 ──────────────────────────────────────────────────────────────────────

def reply_sizes(d_role: dict) -> dict:
    col = PerFlowFeatures.FEATURE_NAMES().index("bytes_out")
    out = {}
    for r in sorted(set(d_role["y"].tolist())):
        v = d_role["X"][d_role["y"] == r, col].astype(float)
        out[r] = {"n": int(len(v)), "median": float(np.median(v)),
                  "iqr": [float(np.percentile(v, 25)), float(np.percentile(v, 75))],
                  "cv": float(v.std(ddof=1) / v.mean())}
    return {"response_bytes_per_role": out,
            "tokens": "not logged: the agents never record Ollama's eval_count or done_reason, so the "
                      "share of replies that hit the 256-token cap cannot be measured from C1"}


# ── A4 ──────────────────────────────────────────────────────────────────────

def bucket_linear(n: int, step: int = 1024) -> int:
    return max(step, -(-n // step) * step)


def bucket_pow2(n: int, start: int = 1024) -> int:
    return max(start, 1 << math.ceil(math.log2(max(n, 1))))


def pad_packets(pk, servers: set[int], bucket, mss: int) -> tuple[list, int, int]:
    """Pad every request message to its bucket and re-segment it at mss bytes of payload. A
    message is the request writes on one connection ≤ 50 ms apart, not interrupted by response
    data. Input padding pads what the application sends, so TLS handshake records and alerts are
    left as they are: messages under 300 B (client Finished, close_notify) and the first message
    of a connection opened in the trace (the ClientHello). New segments carry the header size
    and timestamps of the message's segments (extra ones the last timestamp). Returns the new
    packet list and (original, padded) total wire bytes."""
    by_conn = defaultdict(list)
    opened = {(sp, dp) for _, sp, dp, _, _, fl in pk if dp in servers and fl & 0x02}
    for i, (ts, sp, dp, wire, pl, fl) in enumerate(pk):
        if dp in servers and pl > 0:
            by_conn[(sp, dp)].append(i)
        elif sp in servers and pl > 0:
            by_conn[(dp, sp)].append(-1)                       # response data closes a message
    groups, drop = [], set()
    for conn, idx in by_conn.items():
        if conn in opened:                                     # the ClientHello is its own message
            first_data = next((i for i in idx if i != -1), None)
            idx = [i for i in idx if i != first_data]
        cur = []
        for i in idx:
            if i == -1:
                if cur:
                    groups.append(cur)
                cur = []
                continue
            if cur and pk[i][0] - pk[cur[-1]][0] > REQUEST_GAP_S:
                groups.append(cur)
                cur = []
            cur.append(i)
        if cur:
            groups.append(cur)
    new = []
    for grp in groups:
        payload = sum(pk[i][4] for i in grp)
        if payload < MIN_REQUEST:                              # TLS alerts and the client Finished
            continue
        target = bucket(payload)
        n_seg = -(-target // mss)
        ts_list = [pk[i][0] for i in grp]
        hdr = pk[grp[0]][3] - pk[grp[0]][4]
        _, sp, dp, _, _, fl = pk[grp[0]]
        for k in range(n_seg):
            seg = min(mss, target - k * mss)
            new.append((ts_list[min(k, len(ts_list) - 1)], sp, dp, hdr + seg, seg, fl))
        drop.update(grp)
    out = sorted([p for i, p in enumerate(pk) if i not in drop] + new, key=lambda p: p[0])
    return out, sum(p[3] for p in pk), sum(p[3] for p in out)


def to_extractor(pk, servers: set[int]) -> list[tuple[float, int, str, int]]:
    """features/extractor.py's packet tuples (all C1 agents are on 127.0.0.1)."""
    out = []
    for ts, sp, dp, wire, _, _ in pk:
        if dp in servers:
            out.append((ts, wire, f"127.0.0.1:{sp}→127.0.0.1:{dp}", -1))
        elif sp in servers:
            out.append((ts, wire, f"127.0.0.1:{dp}→127.0.0.1:{sp}", 1))
    return out


def padding(d_wf: dict, d_role: dict, d_top: dict, mss: int) -> dict:
    schemes = {"none": None, "linear_1KB": bucket_linear, "pow2_from_1KB": bucket_pow2}
    trace_X = {s: [] for s in schemes}
    role_X = {s: {} for s in schemes}
    first = {s: [] for s in schemes}
    wire = {s: [0, 0] for s in schemes}
    check = 0
    for base, eps in zip(d_wf["base"], d_wf["endpoints"]):
        servers = servers_of(eps)
        pk = own_packets(tcp_packets(RAW / f"{base}.pcap"), servers, LEGACY)
        fx = FeatureExtractor(agent_ports=servers, use_scapy=True, own_connections=not LEGACY)
        port_role = {str(int(a.rsplit(":", 1)[1])): r for r, a in eps.items()}
        for s, bucket in schemes.items():
            pp, w0, w1 = (pk, sum(p[3] for p in pk), sum(p[3] for p in pk)) if bucket is None else \
                pad_packets(pk, servers, bucket, mss)
            wire[s][0] += w0
            wire[s][1] += w1
            ex = to_extractor(pp, servers)
            trace_X[s].append(fx._compute_features(base, ex).flat_vector())
            for port, (_, vec, _, _) in role_vectors(fx, ex, port_role).items():
                role_X[s][f"{base}__role__{port}"] = vec
            first[s].append(first_request(pp, servers, LEGACY)["bytes"])
        if np.array_equal(trace_X["none"][-1], d_wf["X"][len(trace_X["none"]) - 1]):
            check += 1
    out = {"method": "every request message (request writes on one connection ≤ 50 ms apart; TLS "
                     "handshake records and alerts excluded) padded to its bucket and re-segmented at "
                     f"the capture's largest TCP payload ({mss} B); timestamps and header sizes kept; "
                     "responses and ACKs unchanged (a real sender would also trigger a few more ACKs)",
           "reconstruction_check": f"{check} of {len(d_wf['base'])} unpadded trace vectors rebuilt "
                                   "from packet headers equal the stored features",
           "schemes": {}}
    preds = {}
    for s in schemes:
        X = np.stack(trace_X[s]).astype(np.float32)
        res = {"overhead": (wire[s][1] - wire[s][0]) / wire[s][0] if wire[s][0] else 0.0,
               "wire_bytes": wire[s]}
        for task, d in (("workflow", d_wf), ("topology", d_top)):
            y, g = d["y"], d["g"]
            idx = [d_wf["base"].index(b) for b in d["base"]]
            p = oof_predict("gbt", task, X[idx], y, folds(y, g))
            res[task] = score(y, p, g, sorted(set(y.tolist())))
            if task == "workflow":
                preds[s] = p
                if s != "none":
                    res["workflow_unpadded_minus_this"] = paired_diff(y, preds["none"], p, g, sorted(set(y.tolist())))
        y, g = d_wf["y"], d_wf["g"]
        fr = np.array(first[s], dtype=np.float32)[:, None]
        res["workflow_first_request_only"] = score(y, oof_predict("gbt", "workflow", fr, y, folds(y, g)), g,
                                                   sorted(set(y.tolist())))
        Xr = np.stack([role_X[s][rid] for rid in d_role["run_id"]]).astype(np.float32)
        yr, gr = d_role["y"], d_role["g"]
        res["role"] = score(yr, oof_predict("gbt", "role", Xr, yr, folds(yr, gr)), gr, sorted(set(yr.tolist())))
        out["schemes"][s] = res
        logger.info("padding %s: overhead %.1f%%, workflow %.3f", s, 100 * res["overhead"], res["workflow"]["macro_f1"])
    return out


# ── A9 ──────────────────────────────────────────────────────────────────────

def template_id(workflow: str, prompt: str) -> str | None:
    import workflows.code_review as cr
    import workflows.data_analysis as da
    import workflows.research_retrieval as rr
    import workflows.support_triage as st
    if workflow == "code_review":
        snippet = prompt.split("```python\n", 1)[1].rsplit("\n```", 1)[0]
        for name, pool in (("large", cr._LARGE_CODE_SNIPPETS), ("small", cr._CODE_SNIPPETS)):
            if snippet in pool:
                return f"cr:{name}{pool.index(snippet)}"
    elif workflow == "data_analysis":
        name = prompt.split("Dataset: ", 1)[1].split("\n", 1)[0]
        for kind, pool in (("small", da._SMALL_DATASETS), ("full", da._DATASETS)):
            for i, (n, _) in enumerate(pool):
                if n == name:
                    return f"da:{kind}{i}"
    elif workflow == "research_retrieval":
        if prompt in rr._LONG_QUESTIONS:
            return f"rr:long{rr._LONG_QUESTIONS.index(prompt)}"
        for i, t in enumerate(rr._QUESTION_TEMPLATES):
            if any(t.format(topic=topic) == prompt for topic in rr._TOPICS):
                return f"rr:q{i}"
    elif workflow == "support_triage":
        ticket = prompt.split("TICKET:\n", 1)[1]
        for kind, pool in (("long", st._LONG_TICKETS), ("short", st._TICKETS)):
            if ticket in pool:
                return f"st:{kind}{pool.index(ticket)}"
    return None


def template_grouped(d: dict) -> dict:
    tid = np.array([template_id(str(w), side(b)["input_prompt"]) or "unmatched" for b, w in zip(d["base"], d["y"])])
    y = d["y"]
    classes = sorted(set(y.tolist()))
    sp = list(StratifiedGroupKFold(5, shuffle=True, random_state=SEED).split(np.zeros(len(y)), y, tid))
    p = oof_predict("gbt", "workflow", d["X"], y, sp)
    p_prompt = oof_predict("gbt", "workflow", d["X"], y, folds(y, d["g"]))
    return {"prompt_minus_template_grouped": paired_diff(y, p_prompt, p, tid, classes),
            "unmatched": int((tid == "unmatched").sum()),
            "templates_per_workflow": {c: int(len(set(tid[y == c]))) for c in classes},
            "prompts_per_workflow": {c: int(len(set(d["g"][y == c]))) for c in classes},
            "template_grouped": score(y, p, tid, classes),
            "prompt_grouped": score(y, p_prompt, d["g"], classes),
            "note": "template = the generator's base element (code snippet, dataset, research question "
                    "template, support ticket); prompts sharing one differ only in the ask or topic"}


# ── main ────────────────────────────────────────────────────────────────────

def main(a: argparse.Namespace) -> None:
    global PROC, LEGACY
    LEGACY = ev.LEGACY = a.legacy_all_connections
    PROC = Path(a.processed or ("data/processed_c1" if LEGACY else "data/processed_c1_own"))
    suffix = "_legacy" if LEGACY else ""
    d = {t: load(PROC, RAW, t) for t in TASKS}
    d_wf, d_role, d_top = d["workflow"], d["role"], d["topology"]
    workflow_of = {b: str(w) for b, w in zip(d_wf["base"], d_wf["y"])}
    splits = folds(d_wf["y"], d_wf["g"])
    out = {"paper": "P1", "collection_id": "C1", "data_dir": str(PROC), "raw_dir": str(RAW), "seed": SEED,
           **_git(), "measurement": "all connections on the agent ports (legacy)" if LEGACY else
           "own connections: only TCP connections whose SYN is in the trace (features/connections.py)",
           "results": {}}
    R = out["results"]
    logger.info("A10 capture facts")
    R["A10_capture"] = capture_facts(d_wf)
    logger.info("A2 input size")
    rows, R["A2_input_size"] = input_size(d_wf)
    with open(f"data/results/c1_first_request_traces{suffix}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    Path("data/results/figures").mkdir(parents=True, exist_ok=True)
    scatter(rows, Path(f"data/results/figures/c1_first_request_scatter{suffix}.png"))
    logger.info("A3 response side on the length pairs")
    R["A3_pairs_response_side"] = pairs_response_side(d_wf, splits)
    logger.info("A6 topology rule")
    R["A6_topology_rule"] = topology_by_rule(d_top)
    logger.info("A5 k-FP features with GBT")
    R["A5_kfp_features_gbt"] = {t: kfp_with_gbt(t) for t in TASKS}
    logger.info("A7 role, held-out workflow and topology")
    R["A7_role_held_out"] = role_held_out(d_role, workflow_of)
    R["A8_replies"] = reply_sizes(d_role)
    logger.info("A4 padding simulation")
    R["A4_padding"] = padding(d_wf, d_role, d_top, R["A10_capture"]["max_tcp_payload_bytes"]["response"])
    logger.info("A9 template-grouped folds")
    R["A9_templates"] = template_grouped(d_wf)
    path = Path(f"data/results/c1_revision{suffix}.json")
    path.write_text(json.dumps(out, indent=2))
    write_report(out, path.with_suffix(".md"))
    logger.info("wrote %s", path)


def _c(r):
    return f"{r['macro_f1']:.3f} [{r['ci_lo']:.3f}, {r['ci_hi']:.3f}]"


def _d(r):
    return f"{r['diff']:+.3f} [{r['ci_lo']:+.3f}, {r['ci_hi']:+.3f}]{'' if r['significant'] else ' (n.s.)'}"


def write_report(out: dict, path: Path) -> None:
    R = out["results"]
    L = ["# C1: paper 1 revision checks", "",
         f"Collection C1, `{out['data_dir']}`; commit `{out['git_commit'][:8]}`"
         f"{' (uncommitted changes)' if out['git_dirty'] else ''}; seed {out['seed']}. Measurement: "
         f"{out['measurement']}. GBT, the five "
         "prompt-group folds of scripts/evaluate_c1.py unless stated; macro-F1 with 95% cluster-bootstrap CIs.", ""]
    c = R["A10_capture"]
    L += ["## A10. Capture", "",
          f"Link type {', '.join(c['link_types'])} (BSD loopback). Largest packet on the wire: request "
          f"{c['max_wire_bytes']['request']} B, response {c['max_wire_bytes']['response']} B; largest TCP payload "
          f"{c['max_tcp_payload_bytes']['response']} B, so the loopback MTU is {c['loopback_mtu_inferred']} B. "
          f"Header bytes per packet: " + ", ".join(f"{k} B × {v}" for k, v in c["header_bytes"].items()) + ".",
          "", "TCP segments per first request: " + "; ".join(
              f"{w} " + ", ".join(f"{k}: {v}" for k, v in s.items()) for w, s in sorted(c["first_request_segments"].items())) + "."]
    a = R["A2_input_size"]
    L += ["", "## A2. First-request size against prompt size", "", a["note"] + ".", "",
          "| Workflow | c_w (B) | Residual SD | Max residual | Free fit slope | Plan bytes, median [IQR] |",
          "|---|---|---|---|---|---|"]
    for w, f in a["per_workflow"].items():
        L.append(f"| {w} | {f['c_w']:.0f} | {f['residual_sd']:.0f} | {f['max_abs_residual']:.0f} | "
                 f"{f['free_fit_slope']:.3f} | {f['plan_json_bytes_median']:.0f} "
                 f"[{f['plan_json_bytes_iqr'][0]:.0f}, {f['plan_json_bytes_iqr'][1]:.0f}] |")
    L += ["", "Per-trace table: `data/results/c1_first_request_traces.csv`; figure: "
          "`data/results/figures/c1_first_request_scatter.png`.", "",
          "## A3. Response side only, on the length pairs (chance 0.5)", "",
          "| Pair | n | Response side only | All features | All − response side |", "|---|---|---|---|---|"]
    for k, r in R["A3_pairs_response_side"].items():
        L.append(f"| {k.replace('_vs_', ' vs ')} | {r['n']} | {_c(r['response_side'])} ({r['dims']} dims) | "
                 f"{_c(r['all'])} | {_d(r['all_minus_response_side'])} |")
    t = R["A6_topology_rule"]
    L += ["", "## A6. Topology from call count and nesting (fixed rule, no ports or addresses)", "",
          "Rule: no call nested in another → star; nested calls and at most 3 calls → chain; more than 3 → mesh. "
          f"Accuracy {t['accuracy']:.3f} on {t['n']} traces (macro-F1 {_c(t['macro_f1'])}).", "",
          "| Topology | Observed shapes |", "|---|---|"]
    for k, v in t["shapes"].items():
        L.append(f"| {k} | " + ", ".join(f"{s}: {n}" for s, n in v.items()) + " |")
    L += ["", "## A5. k-FP's features with GBT", "",
          "| Task | GBT, all 195 features | GBT, k-FP's 138 features | All − k-FP |", "|---|---|---|---|"]
    for task, r in R["A5_kfp_features_gbt"].items():
        L.append(f"| {task} | {_c(r['gbt_all_features'])} | {_c(r['gbt_kfp_features'])} | {_d(r['all_minus_kfp'])} |")
    r = R["A7_role_held_out"]
    L += ["", "## A7. Role on held-out workflows and topologies", "",
          f"Grouped CV {_c(r['grouped_cv'])}; leave one workflow out {_c(r['leave_one_workflow_out'])} "
          f"(per held-out workflow: " + ", ".join(f"{k} {v:.3f}" for k, v in r["leave_one_workflow_out"]["per_held_out"].items())
          + f"); leave one topology out {_c(r['leave_one_topology_out'])} (" +
          ", ".join(f"{k} {v:.3f}" for k, v in r["leave_one_topology_out"]["per_held_out"].items()) + ")."]
    r = R["A8_replies"]
    L += ["", "## A8. Reply sizes per role", "", r["tokens"] + ".", "",
          "| Role | n | Response bytes, median [IQR] | CV |", "|---|---|---|---|"]
    for k, v in r["response_bytes_per_role"].items():
        L.append(f"| {k} | {v['n']} | {v['median']:.0f} [{v['iqr'][0]:.0f}, {v['iqr'][1]:.0f}] | {v['cv']:.2f} |")
    p = R["A4_padding"]
    L += ["", "## A4. Input padding, simulated", "", p["method"] + ". " + p["reconstruction_check"] + ".", "",
          "| Padding | Overhead | Workflow | Unpadded − padded (workflow) | Workflow, first request only | Role | Topology |",
          "|---|---|---|---|---|---|---|"]
    for s, v in p["schemes"].items():
        dd = _d(v["workflow_unpadded_minus_this"]) if "workflow_unpadded_minus_this" in v else "—"
        L.append(f"| {s} | {100 * v['overhead']:.1f}% | {_c(v['workflow'])} | {dd} | "
                 f"{_c(v['workflow_first_request_only'])} | {_c(v['role'])} | {_c(v['topology'])} |")
    r = R["A9_templates"]
    L += ["", "## A9. Folds grouped by generator template", "", r["note"] + ".", "",
          "Templates per workflow: " + ", ".join(f"{k} {v}" for k, v in r["templates_per_workflow"].items()) +
          "; prompts: " + ", ".join(f"{k} {v}" for k, v in r["prompts_per_workflow"].items()) +
          f"; unmatched prompts {r['unmatched']}.", "",
          f"Workflow GBT: grouped by template {_c(r['template_grouped'])}; grouped by prompt {_c(r['prompt_grouped'])}; "
          f"prompt − template grouping {_d(r['prompt_minus_template_grouped'])} (bootstrap over templates)."]
    path.write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Paper 1 revision checks on C1")
    p.add_argument("--processed", default=None,
                   help="default data/processed_c1_own (data/processed_c1 with --legacy-all-connections)")
    p.add_argument("--legacy-all-connections", action="store_true", dest="legacy_all_connections")
    main(p.parse_args())
