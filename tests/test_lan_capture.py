"""LAN pilot check: every orchestrator → specialist call the topology implies is in the capture."""

import json

import pytest

from scripts.check_lan_capture import check_trace

scapy_all = pytest.importorskip("scapy.all")
from test_leakcheck import ROLES, _trace  # noqa: E402

import numpy as np  # noqa: E402


def _write(tmp_path, topology, drop=None):
    pkts = [p for p in _trace(0, "alpha", np.random.default_rng(0))
            if drop is None or ROLES[drop] not in (p["TCP"].sport, p["TCP"].dport)]
    pcap = tmp_path / f"t_{topology}.pcap"
    scapy_all.wrpcap(str(pcap), pkts)
    side = {"run_id": pcap.stem, "topology": topology,
            "agent_endpoints": {"orchestrator": "10.0.0.1:9000", **{r: f"10.0.0.2:{p}" for r, p in ROLES.items()}}}
    return pcap, side


def test_star_with_every_call_passes(tmp_path):
    assert check_trace(*_write(tmp_path, "star"))["ok"]


def test_a_missing_call_fails(tmp_path):
    r = check_trace(*_write(tmp_path, "star", drop="validator"))
    assert not r["ok"] and r["missing"] == ["validator"]


def test_calls_the_topology_does_not_make_from_the_mac_are_flagged(tmp_path):
    r = check_trace(*_write(tmp_path, "chain"))
    assert not r["ok"] and r["unexpected"] == ["retriever", "validator"]
    assert json.dumps(r)
