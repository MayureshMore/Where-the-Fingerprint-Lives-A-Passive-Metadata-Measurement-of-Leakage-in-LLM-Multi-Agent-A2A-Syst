"""
Collection: a folder of header-only pcaps, each with a JSON label sidecar of the same name.

Sidecar fields read (anything else is ignored):

    agent_endpoints   {"executor": "10.0.0.2:8101", ...}   every agent's host and port (required): a packet
                      counts for an agent only if its server side is that host and port; agents on
                      different hosts may share a port (a2a_leakcheck/endpoints.py)
    workflow_class    or "workflow": the workflow label
    topology          the topology label (also used to count the visible agents per topology)
    <any other key>   a trace-level attribute, if asked for with --attributes
    prompt_group      grouping key; else sha1(input_prompt)[:8]; else the run id
    success           false → the trace is skipped
    tls               false → a cleartext capture: the first request is measured from the first client byte
                      (there is no TLS handshake to skip); also for every trace with --cleartext
    pad_buckets, padded_endpoints   requests padded to these sizes, on these agents (session collector):
                      only for the mitigation rules (facts padded, unpadded_in_view); not in the report
    escalated, cloud_role   edge-cloud sidecars: whether the edge called a cloud agent ("yes"/"no") and
                      which one. With --vantage, a trace with nothing in view is counted as expected
                      silent when it was not escalated and the view sees only cloud agents (those the
                      sidecars' cloud_role names), else as unexpectedly empty (extract.py)
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

from a2a_leakcheck.endpoints import foreign_packets, parse_endpoints, role_keys, write_without
from scripts.strip_payload import payload_bytes, strip_file

ALIASES = {"workflow": ("workflow_class", "workflow")}


@dataclass
class Trace:
    run_id: str
    pcap: Path
    port_role: dict[int, str]                     # agent port → role ("a+b" where agents on two hosts share it)
    labels: dict[str, str] = field(default_factory=dict)
    group: str = ""
    group_source: str = ""                        # prompt_group | input_prompt | run_id
    topology: str | None = None                   # sidecar topology, for the visibility summary
    padded: bool = False                          # sidecar pad_buckets non-empty (rules only)
    unpadded_in_view: tuple = ()                  # padded deployment: endpoints in view not in padded_endpoints
    tls: bool = True                              # False: cleartext, no handshake for the first request to skip
    endpoints: dict = field(default_factory=dict)  # (host, port) → role (endpoints.py)
    role_keys: dict = field(default_factory=dict)  # "ip:port" or "port" → role, for features/roles.py
    escalated: bool | None = None                 # sidecar escalated (edge-cloud): did the edge call the cloud
    cloud_role: str | None = None                 # sidecar cloud_role: the cloud agent it called


def _label(sidecar: dict, attribute: str) -> str | None:
    for key in ALIASES.get(attribute, (attribute,)):
        if sidecar.get(key) not in (None, ""):
            return str(sidecar[key])
    return None


def read_trace(pcap: Path, trace_attributes: list[str], vantage: str | None = None,
               cleartext: bool = False) -> tuple[Trace | None, str]:
    """(trace, "") or (None, reason it was skipped). vantage: keep only the endpoints that view sees.
    cleartext: the capture has no TLS (as a sidecar "tls": false says for itself)."""
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
    endpoints, why = parse_endpoints(eps)
    if why:
        return None, why
    if not endpoints:
        return None, "no agent_endpoints"
    if vantage is not None:
        seen = (sc.get("vantages") or {}).get(vantage)
        if seen is None:
            return None, f"no vantage {vantage!r} in the sidecar"
        endpoints = {e: r for e, r in endpoints.items() if r in seen}
        if not endpoints:
            return None, f"vantage {vantage!r} lists no endpoint of agent_endpoints"
    port_role: dict[int, str] = {}
    for (_, port), role in sorted(endpoints.items(), key=lambda x: (x[0][1], str(x[0][0]))):
        port_role[port] = f"{port_role[port]}+{role}" if port in port_role else role
    if sc.get("prompt_group"):
        group, source = str(sc["prompt_group"]), "prompt_group"
    elif sc.get("input_prompt"):
        group, source = hashlib.sha1(sc["input_prompt"].encode()).hexdigest()[:8], "input_prompt"
    else:
        group, source = pcap.stem, "run_id"
    labels = {a: v for a in trace_attributes if (v := _label(sc, a)) is not None}
    padded = bool(sc.get("pad_buckets"))
    unpadded = tuple(sorted(set(endpoints.values()) - set(sc.get("padded_endpoints") or []))) if padded else ()
    return Trace(run_id=sc.get("run_id", pcap.stem), pcap=pcap, port_role=port_role,
                 labels=labels, group=group, group_source=source, topology=_label(sc, "topology"),
                 padded=padded, unpadded_in_view=unpadded,
                 tls=not cleartext and sc.get("tls", True) is not False, endpoints=endpoints,
                 role_keys=role_keys(endpoints),
                 escalated={"yes": True, "true": True, "no": False, "false": False}.get(str(sc.get("escalated")).lower()),
                 cloud_role=sc.get("cloud_role") or None), ""


def collect(folder: Path, trace_attributes: list[str], strip_dir: Path | None = None,
            vantage: str | None = None, cleartext: bool = False, filter_dir: Path | None = None) -> dict:
    """Read every pcap + sidecar in folder. Captures must be header-only; with strip_dir, a
    header-only copy of each capture that still holds payload bytes is written there and used.
    vantage: an observer view from the sidecars' vantages (only its endpoints' flows are kept).
    filter_dir: where a copy without other hosts' packets on an agent port is written (endpoints.py);
    without it, a capture that has such packets stops the run.
    """
    folder = Path(folder)
    pcaps = sorted(folder.glob("*.pcap"))
    traces, skipped, with_payload, stripped = [], [], [], 0
    other = {"captures": 0, "packets": 0, "endpoints": {}}
    for pcap in pcaps:
        tr, why = read_trace(pcap, trace_attributes, vantage, cleartext)
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
        drop, seen = foreign_packets(tr.pcap, tr.endpoints)
        if drop:
            if filter_dir is None:
                raise SystemExit(f"{pcap.name}: {len(drop)} packets on an agent port of a host its sidecar's "
                                 f"agent_endpoints do not list ({', '.join(sorted(seen))}); the leakcheck "
                                 "command drops them into a filtered copy")
            dst = Path(filter_dir) / "endpoints" / pcap.name
            write_without(tr.pcap, dst, drop)
            tr.pcap = dst
            other["captures"] += 1
            other["packets"] += len(drop)
            for k, n in seen.items():
                other["endpoints"][k] = other["endpoints"].get(k, 0) + n
        traces.append(tr)
    if with_payload:
        raise SystemExit(
            f"{len(with_payload)} of {len(pcaps)} captures in {folder} hold payload bytes beyond the "
            f"headers (first: {with_payload[0]}). leakcheck takes header-only captures: strip them "
            f"with scripts/strip_payload.py, or pass --strip to analyse header-only copies.")
    groups = [t.group_source for t in traces]
    return {"traces": traces, "skipped": skipped,
            "summary": {"folder": str(folder), "vantage": vantage, "pcaps": len(pcaps), "traces": len(traces),
                        **({"cleartext_traces": n} if (n := sum(not t.tls for t in traces)) else {}),
                        "skipped": skipped, "stripped_copies": stripped, "other_host_packets": other,
                        "group_source": {s: groups.count(s) for s in sorted(set(groups))}}}
