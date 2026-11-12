"""C2's edge-cloud placement: routing and sidecar labels, the observer views in a2a-leakcheck (an
upstream view that sees nothing of a task answered on the gateway keeps that task, with all-zero
features), and the capture check's rules, on synthetic header-only captures."""

import json
from types import SimpleNamespace

import numpy as np
import pytest

from agents.edge import PADDED_ENDPOINTS, ROUTES, VANTAGES, endpoints, pi_telemetry
from a2a_leakcheck.analyze import LEAK
from a2a_leakcheck.cli import main as leakcheck
from scripts.check_lan_capture import check_trace
from scripts.check_session_design import _padded_ports
from scripts.collect_session import edge_sidecar

scapy_all = pytest.importorskip("scapy.all")
Ether, IP, TCP, Raw, wrpcap = (scapy_all.Ether, scapy_all.IP, scapy_all.TCP, scapy_all.Raw, scapy_all.wrpcap)

EDGE, CLOUD, TICKET, BASE = "10.0.0.2", "10.0.0.100", "10.0.0.1", 9100
EPS = endpoints(BASE, CLOUD, TICKET)
PORT = {r: int(a.rsplit(":", 1)[1]) for r, a in EPS.items()}
REQUEST = {"sensor_analysis": 3000, "fault_diagnosis": 4200, "procedure_lookup": 700}
FAST = ["--model", "rf", "--permutations", "9", "--alpha", "0.1", "--n-boot", "200", "--min-per-class", "10"]


def _conn(t, cport, server, port, request, n_resp, resp, rng):
    """One TLS connection from the edge: handshake, a request, n_resp response records, close."""
    out = []
    seq = [("c", "S", 0), ("s", "SA", 0), ("c", "A", 0), ("c", "PA", 517), ("s", "PA", 1374), ("c", "PA", 80),
           ("c", "PA", request + int(rng.integers(-120, 120)))]
    seq += [("s", "PA", resp + int(rng.integers(-60, 60))) for _ in range(n_resp)]
    seq += [("c", "FA", 0), ("s", "FA", 0), ("c", "A", 0)]
    for j, (who, flags, n) in enumerate(seq):
        src, dst, sp, dp = (EDGE, server, cport, port) if who == "c" else (server, EDGE, port, cport)
        p = Ether() / IP(src=src, dst=dst) / TCP(sport=sp, dport=dp, flags=flags)
        if n:
            p = p / Raw(b"\x17" * n)
        p.time = t + 0.01 * j
        out.append(p)
    return out, t + 0.01 * len(seq)


def _trace(i, task, rng, cloud_for_alert=False):
    t, pkts = 1000.0 + 20 * i, []
    route = ROUTES[task] or ("diagnostics" if cloud_for_alert else None)
    if route:
        c, t = _conn(t, 40000 + 3 * i, CLOUD, PORT[route], REQUEST.get(task, 700), 30 if route == "diagnostics" else 12,
                     300, rng)
        pkts += c
    c, _ = _conn(t + 0.05, 40001 + 3 * i, TICKET, PORT["ticket"], 1500 if route else 600, 1, 120, rng)
    return pkts + c


def make_edge_dataset(folder, per_type=20, seed=0, bad_alert=False):
    rng = np.random.default_rng(seed)
    folder.mkdir(parents=True, exist_ok=True)
    tasks = [w for w in ROUTES for _ in range(per_type)]
    for i, w in enumerate(tasks):
        run_id = f"{w}_edge_cloud_{i:04d}"
        wrpcap(str(folder / f"{run_id}.pcap"), _trace(i, w, rng, cloud_for_alert=bad_alert and w == "alert_triage" and i % per_type == 0))
        a = SimpleNamespace(edge_host=EDGE)
        sc = {"run_id": run_id, "workflow_class": w, "topology": "edge_cloud", "agent_endpoints": EPS,
              "input_prompt": f"prompt {i}", "prompt_group": f"g{i:04d}", "success": True,
              **edge_sidecar(w, f"prompt {i}", a, {"ok": True, "escalated": ROUTES[w] is not None,
                                                   "cloud_role": ROUTES[w], "pi": {"throttled": False}})}
        (folder / f"{run_id}.json").write_text(json.dumps(sc))
    return folder


def test_routing_and_sidecar_labels():
    a = SimpleNamespace(edge_host=EDGE)
    sc = edge_sidecar("alert_triage", "x", a, {"ok": True, "escalated": False, "cloud_role": None})
    assert sc["escalated"] == "no" and "cloud_role" not in sc and sc["task_type"] == "alert_triage"
    sc = edge_sidecar("procedure_lookup", "x", a, {"ok": True, "escalated": True, "cloud_role": "knowledge"})
    assert sc["escalated"] == "yes" and sc["cloud_role"] == "knowledge" and "mismatch" not in sc["edge_report"]
    sc = edge_sidecar("sensor_analysis", "x", a, {"ok": True, "escalated": True, "cloud_role": "knowledge"})
    assert sc["edge_report"]["mismatch"]                                  # the edge did not follow the rule
    assert sc["vantages"] == VANTAGES and sc["padded_endpoints"] == PADDED_ENDPOINTS == ["diagnostics", "knowledge"]
    assert EPS == {"diagnostics": f"{CLOUD}:9101", "knowledge": f"{CLOUD}:9102", "ticket": f"{TICKET}:9105"}
    assert _padded_ports({"agent_endpoints": EPS, "padded_endpoints": PADDED_ENDPOINTS}) == {9101, 9102}
    assert _padded_ports({"agent_endpoints": EPS}) is None
    assert set(pi_telemetry()) == {"temp_c", "throttled", "throttled_now"}  # None values off a Pi


def test_capture_check_rules(tmp_path):
    d = make_edge_dataset(tmp_path / "ok", per_type=3)
    rows = [check_trace(p, json.loads(p.with_suffix(".json").read_text())) for p in sorted(d.glob("*.pcap"))]
    assert all(r["ok"] for r in rows), [r for r in rows if not r["ok"]]
    d = make_edge_dataset(tmp_path / "bad", per_type=3, bad_alert=True)
    bad = [r for p in sorted(d.glob("*.pcap")) if not (r := check_trace(p, json.loads(p.with_suffix(".json").read_text())))["ok"]]
    assert len(bad) == 1 and bad[0]["task_type"] == "alert_triage"
    assert any("alert_triage reaches the cloud" in x for x in bad[0]["problems"])


@pytest.fixture(scope="module")
def edge_data(tmp_path_factory):
    return make_edge_dataset(tmp_path_factory.mktemp("edge"), per_type=20)


def _run(folder, out, vantage, attrs):
    assert leakcheck(["run", str(folder), "--out", str(out), "--strip", "--vantage", vantage,
                      "--attributes", attrs, *FAST]) == 0
    return json.loads((out / "report.json").read_text())


def test_upstream_view_keeps_tasks_it_cannot_see(edge_data, tmp_path):
    rep = _run(edge_data, tmp_path / "v2", "v2", "escalated,task_type,cloud_role")
    assert rep["input"]["vantage"] == "v2"
    assert rep["extraction"]["traces"] == 80 and rep["extraction"]["empty_traces"] == 20     # every alert_triage
    esc = rep["attributes"]["escalated"]
    assert esc["validation"]["min_samples"]["per_class"] == {"no": 20, "yes": 60} and esc["verdict"] == LEAK
    assert rep["attributes"]["cloud_role"]["n"] == 60                     # escalated tasks only
    assert "show no flow there" in (tmp_path / "v2" / "report.md").read_text()


def test_building_view_sees_every_task(edge_data, tmp_path):
    rep = _run(edge_data, tmp_path / "v1", "v1", "escalated")
    assert rep["extraction"]["empty_traces"] == 0 and rep["extraction"]["traces"] == 80
    assert rep["attributes"]["escalated"]["verdict"] == LEAK


def test_unknown_vantage_skips_traces(edge_data, tmp_path):
    with pytest.raises(SystemExit):                                       # no trace left to analyse
        leakcheck(["run", str(edge_data), "--out", str(tmp_path / "v9"), "--strip", "--vantage", "v9",
                   "--attributes", "escalated", *FAST])


def test_handshake_times_at_the_capture(tmp_path):
    """check_wan_emulation: SYN → SYN-ACK per server, as a capture on the building side sees it."""
    from scripts.check_wan_emulation import handshakes
    pkts = []
    for k, (port, rtt) in enumerate([(9101, 0.030), (9101, 0.031), (9105, 0.0004)]):
        c, t = 50000 + k, 10.0 + k
        for when, (src, dst, sp, dp, flags) in ((t, (EDGE, CLOUD, c, port, "S")), (t + rtt, (CLOUD, EDGE, port, c, "SA"))):
            p = Ether() / IP(src=src, dst=dst) / TCP(sport=sp, dport=dp, flags=flags)
            p.time = when
            pkts.append(p)
    wrpcap(str(tmp_path / "p.pcap"), pkts)
    hs = handshakes(tmp_path / "p.pcap", {9101: "cloud", 9105: "ticket"})
    assert [round(x) for x in hs["cloud"]] == [30, 31] and hs["ticket"][0] < 1


def test_recorder_uses_immediate_mode(tmp_path):
    """Without it macOS hands packets over in batches, and a capture stopped right after a task
    loses its last ones (C2's ticket post, a whole alert_triage task)."""
    from capture.recorder import PacketRecorder
    s = PacketRecorder(output_dir=tmp_path, interface="lo0", agent_ports=[9101]).new_session("x")
    assert s.immediate
    assert not PacketRecorder(output_dir=tmp_path, agent_ports=[9101], immediate=False).new_session("y").immediate


def test_network_config_file_and_overrides(tmp_path, monkeypatch):
    from agents.edge import NETWORK_KEYS, c2_network, require
    conf = tmp_path / "net.conf"
    conf.write_text("# comment\nC2_IFACE=en0   # Wi-Fi\nC2_MAC=10.0.0.228\nC2_PI=\nC2_CLOUD='10.0.0.240'\n")
    for k in NETWORK_KEYS:
        monkeypatch.delenv(k, raising=False)
    net = c2_network(conf)
    assert net == {"C2_IFACE": "en0", "C2_MAC": "10.0.0.228", "C2_PI": "", "C2_CLOUD": "10.0.0.240", "C2_PI_IFACE": "", "C2_PI_USER": ""}
    monkeypatch.setenv("C2_PI", "10.0.0.50")
    assert c2_network(conf)["C2_PI"] == "10.0.0.50"                    # the environment overrides the file
    with pytest.raises(SystemExit, match="configs/c2_network.conf"):
        require("", "the Pi's address (C2_PI)")


def test_capture_command_never_promiscuous_and_pi_only(tmp_path, monkeypatch):
    import capture.recorder as rec
    seen = {}

    class FakePopen:
        def __init__(self, cmd, **kw):
            seen["cmd"] = cmd

        def poll(self):
            return None

    monkeypatch.setattr(rec.subprocess, "Popen", FakePopen)
    rec.PacketRecorder(output_dir=tmp_path, interface="en0", agent_ports=[8101, 8102, 8105],
                       hosts=["10.0.0.50"]).new_session("t").start()
    cmd = seen["cmd"]
    assert "-p" in cmd and "--immediate-mode" in cmd and cmd[cmd.index("-i") + 1] == "en0"
    assert cmd[-1] == "tcp and (port 8101 or port 8102 or port 8105) and (host 10.0.0.50)"
