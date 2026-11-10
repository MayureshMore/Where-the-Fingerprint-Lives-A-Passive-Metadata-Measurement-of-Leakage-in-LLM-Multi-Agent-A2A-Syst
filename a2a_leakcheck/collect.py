"""
Collection: a folder of header-only pcaps, each with a JSON label sidecar of the same name.

Sidecar fields read (anything else is ignored):

    agent_endpoints   {"executor": "10.0.0.2:8101", ...}   role of every agent port (required)
    workflow_class    or "workflow": the workflow label
    topology          the topology label (also used to count the visible agents per topology)
    <any other key>   a trace-level attribute, if asked for with --attributes
    prompt_group      grouping key; else sha1(input_prompt)[:8]; else the run id
    success           false → the trace is skipped
    vantages          {"v1": ["diagnostics", "knowledge", "ticket"], "v2": [...]}: the agent endpoints
                      each observer view sees (scripts/collect_session.py --placement edge-cloud).
                      With --vantage NAME only those endpoints' flows are kept, before feature
                      extraction; a trace in which the view sees nothing stays in, with all-zero
                      features (the observer sees no traffic, which is itself an observation).

Traces that share a prompt are correlated, so they form one group: cross-validation never
splits a group, and confidence intervals resample whole groups.

A capture's features come only from the TCP connections it opens itself (the SYN is in the
capture; features/connections.py): the tail of an earlier trace's connections is dropped.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from scripts.strip_payload import payload_bytes, strip_file

ALIASES = {"workflow": ("workflow_class", "workflow")}


@dataclass
class Trace:
    run_id: str
    pcap: Path
    port_role: dict[int, str]                     # agent port → role
    labels: dict[str, str] = field(default_factory=dict)
    group: str = ""
    group_source: str = ""                        # prompt_group | input_prompt | run_id
    topology: str | None = None                   # sidecar topology, for the visibility summary


def _label(sidecar: dict, attribute: str) -> str | None:
    for key in ALIASES.get(attribute, (attribute,)):
        if sidecar.get(key) not in (None, ""):
            return str(sidecar[key])
    return None


def read_trace(pcap: Path, trace_attributes: list[str], vantage: str | None = None) -> tuple[Trace | None, str]:
    """(trace, "") or (None, reason it was skipped). vantage: keep only the endpoints that view sees."""
    side = pcap.with_suffix(".json")
    if not side.exists():
        return None, "no sidecar"
    try:
        sc = json.loads(side.read_text())
    except ValueError as exc:
        return None, f"bad sidecar: {exc}"
    if sc.get("success") is False:
        return None, "run marked failed"
    eps = sc.get("agent_endpoints") or {}
    if isinstance(eps, str):
        return None, "agent_endpoints is not an object"
    port_role = {}
    for role, addr in eps.items():
        port = str(addr).rsplit(":", 1)[-1]
        if port.isdigit():
            port_role[int(port)] = role
    if not port_role:
        return None, "no agent_endpoints"
    if vantage is not None:
        seen = (sc.get("vantages") or {}).get(vantage)
        if seen is None:
            return None, f"no vantage {vantage!r} in the sidecar"
        port_role = {p: r for p, r in port_role.items() if r in seen}
        if not port_role:
            return None, f"vantage {vantage!r} lists no endpoint of agent_endpoints"
    if sc.get("prompt_group"):
        group, source = str(sc["prompt_group"]), "prompt_group"
    elif sc.get("input_prompt"):
        group, source = hashlib.sha1(sc["input_prompt"].encode()).hexdigest()[:8], "input_prompt"
    else:
        group, source = pcap.stem, "run_id"
    labels = {a: v for a in trace_attributes if (v := _label(sc, a)) is not None}
    return Trace(run_id=sc.get("run_id", pcap.stem), pcap=pcap, port_role=port_role,
                 labels=labels, group=group, group_source=source, topology=_label(sc, "topology")), ""


def collect(folder: Path, trace_attributes: list[str], strip_dir: Path | None = None,
            vantage: str | None = None) -> dict:
    """Read every pcap + sidecar in folder. Captures must be header-only; with strip_dir, a
    header-only copy of each capture that still holds payload bytes is written there and used.
    vantage: an observer view from the sidecars' vantages (only its endpoints' flows are kept).
    """
    folder = Path(folder)
    pcaps = sorted(folder.glob("*.pcap"))
    traces, skipped, with_payload, stripped = [], [], [], 0
    for pcap in pcaps:
        tr, why = read_trace(pcap, trace_attributes, vantage)
        if tr is None:
            skipped.append({"pcap": pcap.name, "reason": why})
            continue
        if payload_bytes(pcap):
            if strip_dir is None:
                with_payload.append(pcap.name)
                continue
            dst = Path(strip_dir) / pcap.name
            strip_file(pcap, dst)
            tr.pcap = dst
            stripped += 1
        traces.append(tr)
    if with_payload:
        raise SystemExit(
            f"{len(with_payload)} of {len(pcaps)} captures in {folder} hold payload bytes beyond the "
            f"headers (first: {with_payload[0]}). leakcheck takes header-only captures: strip them "
            f"with scripts/strip_payload.py, or pass --strip to analyse header-only copies.")
    groups = [t.group_source for t in traces]
    return {"traces": traces, "skipped": skipped,
            "summary": {"folder": str(folder), "vantage": vantage, "pcaps": len(pcaps), "traces": len(traces),
                        "skipped": skipped, "stripped_copies": stripped,
                        "group_source": {s: groups.count(s) for s in sorted(set(groups))}}}
