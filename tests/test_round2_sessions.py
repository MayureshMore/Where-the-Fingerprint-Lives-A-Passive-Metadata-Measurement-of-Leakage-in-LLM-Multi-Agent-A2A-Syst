"""Round-2 sessions (paper 2, B1-B3): the WAN plans, per-arm targets in the guard, the reorder check,
the Ollama load generator, the collector's arm options and the shaping calibration's sizes."""

import argparse
import asyncio
import json
import socket
import threading
import time
from pathlib import Path

import pytest
from scapy.all import IP, TCP, Ether, wrpcap

from agents.edge import wan_target
from scripts.b1_shape_calibration import overhead, record
from scripts.check_reorder import check_dir
from scripts.collect_session import ReplyLog, advertised, parse_arm, same_jitter
from scripts.round2_wan_plan import plans
from defense.shaping import ShapeConfig, clipped_normal

ROOT = Path(__file__).resolve().parent.parent
C2 = json.loads((ROOT / "data/results/c2_wan_emulation.json").read_text())
PI, CLOUD = C2["emulation"]["pi"], C2["emulation"]["cloud"]


def test_the_plans_split_the_delay_and_keep_c2_s_wan():
    p = plans(C2)
    b1, b2 = p["b1_wan.json"], p["b2_wan_jitter.json"]
    assert b1["emulation"]["bases"] == [8300, 8400] and b1["arms"]["8400"]["shape"] == "2048/14/128/0.05/truncate"
    assert b1["emulation"]["pipes"] == [[1, 6], [2, 6]]
    e = b2["emulation"]
    assert e["pipes"] == [[1, 6], [2, 6], [3, 2], [4, 2]] and e["bases"] == [8100, 8500]
    assert "port { 8501 8502 } pipe 3" in e["rules"][0] and "port { 8501 8502 } to" in e["rules"][1]
    assert e["rules"][2].endswith("pipe 1") and "8505" in e["rules"][-1]          # quick: the jitter arm's rules first
    tc = b2["jitter"]["pi_netem"]["tc_commands"]
    assert "netem delay 4ms 1.8ms distribution normal rate 1gbit" in tc[2]
    assert [c for c in tc if "dport 8501" in c] and [c for c in tc if "dport 8502" in c]
    assert "clipped to 0" in b2["jitter"]["negative_draws"]
    c = clipped_normal(4, 1.8)
    assert abs(b2["jitter"]["one_way_ms"]["requests"] - (2 + c["mean"])) < 1e-9
    assert b2["jitter"]["one_way_ms"]["reply_other_packets"] == 2
    d = b2["jitter"]["derivation"]
    assert 1.75 < d["per_direction_sd_ms"] < 1.9 and d["used_sd_ms"] == 1.8
    jl = b2["arms"]["8500"]
    assert jl["delay_ms"] == 4 and abs(jl["target_rtt_ms"] - (C2["target_rtt_ms"] - 12 + 4 + c["mean"])) < 1e-9


def test_wan_targets_per_arm_with_a_floor():
    t = wan_target(C2, 8100)
    assert t["delay_band"] == pytest.approx((9.6, 14.4)) and t["pipes"] == [1, 2]
    b2 = plans(C2)["b2_wan_jitter.json"]
    jl = wan_target(b2, 8500)
    assert jl["delay_band"] == pytest.approx((2.0, 6.0)) and jl["pipes"] == [3, 4]
    assert wan_target(b2, 8100)["target_rtt_ms"] == C2["target_rtt_ms"]


def _status(path: Path, pipes: dict[int, int], b2: dict) -> None:
    rules = []
    for r in b2["emulation"]["rules"]:                       # as pfctl prints the anchor: one rule per port
        if "port {" in r and r.startswith("dummynet"):
            head, rest = r.split("port {", 1)
            ports, tail = rest.split("}", 1)
            rules += [f"{head}port = {p}{tail}".replace("proto tcp", "inet proto tcp") for p in ports.split()]
        elif r.startswith("dummynet"):
            rules.append(r.replace("proto tcp", "inet proto tcp"))
    path.write_text(json.dumps({"time": time.time(), "at": "now", "pf_status": "Status: Enabled",
                                "dummynet": {"ok": True, "pipes": [{"pipe": n, "delay_ms": ms, "bandwidth": 0, "plr": 0}
                                                                   for n, ms in pipes.items()]},
                                "anchor_dummynet": rules, "anchor_rules": [r for r in b2["emulation"]["rules"]
                                                                           if not r.startswith("dummynet")],
                                "dnctl_list": []}))


def _guard_args(tmp: Path, target: Path, status: Path, dirs: list[Path]) -> argparse.Namespace:
    return argparse.Namespace(target=str(target), status=str(status), tolerance=0.2, every=50, max_age=120,
                              pi_overhead_ms=3.3, calibration=None, dirs=[str(d) for d in dirs], json=None,
                              collector_pid=None, poll=1, grace=1)


def _handshake(sport: int, dport: int, t0: float, synack_ms: float, ack_ms: float) -> list:
    pkts = [Ether() / IP(src=PI, dst=CLOUD) / TCP(sport=sport, dport=dport, flags="S", seq=1000),
            Ether() / IP(src=CLOUD, dst=PI) / TCP(sport=dport, dport=sport, flags="SA", seq=5000, ack=1001),
            Ether() / IP(src=PI, dst=CLOUD) / TCP(sport=sport, dport=dport, flags="A", seq=1001, ack=5001)]
    for p, t in zip(pkts, (t0, t0 + synack_ms / 1000, t0 + ack_ms / 1000)):
        p.time = t
    return pkts


def test_the_guard_checks_each_arm_against_its_own_targets(tmp_path):
    from scripts.c2_guard import Guard
    b2 = plans(C2)["b2_wan_jitter.json"]
    target = tmp_path / "b2.json"
    target.write_text(json.dumps(b2))
    status = tmp_path / "status.json"
    dirs = {8100: tmp_path / "lan", 8500: tmp_path / "jl"}
    window = []
    for base, d in dirs.items():
        d.mkdir()
        syn_synack = 13.0 if base == 8100 else 5.0                        # dummynet's ~1 ms on top of 12 / 4
        for k in range(6):
            stem = f"sensor_analysis_edge_cloud_{base:04x}{k:02x}"
            wrpcap(str(d / f"{stem}.pcap"), _handshake(40000 + k, base + 1, 100.0 + k, syn_synack, syn_synack + 4.0 +
                                                       (4.0 if base == 8500 else 0.0)))
            (d / f"{stem}.json").write_text("{}")
            window.append(d / f"{stem}.json")
    _status(status, {1: 6, 2: 6, 3: 2, 4: 2}, b2)
    g = Guard(_guard_args(tmp_path, target, status, list(dirs.values())))
    rows = g.status()
    assert all(r["ok"] for r in rows), [r["detail"] for r in rows]
    c = g.connect(window)
    assert c["ok"], c["detail"]
    assert [r["handshakes"] for r in c["arms"]] == [6, 6]
    _status(status, {1: 6, 2: 6, 3: 6, 4: 2}, b2)                         # pipe 3 at the control's delay
    assert not g.status()[0]["ok"]
    pooled = json.loads(target.read_text())
    pooled.pop("arms")                                                      # without per-arm targets: C2's pooled check
    target.write_text(json.dumps(pooled))
    assert not Guard(_guard_args(tmp_path, target, status, list(dirs.values()))).connect(window)["ok"]


def _flow(path: Path, order: list[int], gap_ms: float) -> None:
    """A request of len(order) 1,000-byte segments from the Pi to cloud port 8501, sent in this order,
    gap_ms apart, and the sidecar naming the endpoints."""
    pkts = []
    for k, i in enumerate(order):
        p = Ether() / IP(src=PI, dst=CLOUD) / TCP(sport=40001, dport=8501, flags="PA", seq=1000 + 1000 * i) / (b"x" * 1000)
        p.time = 50.0 + k * gap_ms / 1000
        pkts.append(p)
    stem = path / "fault_diagnosis_edge_cloud_00aa01"
    wrpcap(str(stem) + ".pcap", pkts)
    Path(str(stem) + ".json").write_text(json.dumps({"agent_endpoints": {"diagnostics": f"{CLOUD}:8501",
                                                                           "knowledge": f"{CLOUD}:8502"}}))


def test_reordering_is_told_from_wifi_and_from_retransmission(tmp_path):
    cases = {"inorder": ([0, 1, 2, 3], 1.0), "jitter": ([0, 2, 1, 3], 2.0), "wifi": ([0, 2, 1, 3], 0.01),
             "retx": ([0, 2, 3, 1], 30.0)}
    res = {}
    for name, (order, gap) in cases.items():
        (tmp_path / name).mkdir()
        _flow(tmp_path / name, order, gap)
        res[name] = check_dir(tmp_path / name, 0.1, 20.0)["pi_to_cloud"]
    assert res["inorder"]["out_of_order"] == 0
    assert (res["jitter"]["reordered"], res["wifi"]["within_wifi_ms"], res["retx"]["after_retx_ms"]) == (1, 1, 1)
    assert res["wifi"]["reordered"] == res["retx"]["reordered"] == 0
    from scripts.check_reorder import main
    assert main([str(tmp_path / "wifi"), "--control", str(tmp_path / "inorder")]) == 0
    assert main([str(tmp_path / "jitter"), "--control", str(tmp_path / "inorder")]) == 1


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(params=[False, True], ids=["parallel", "serial"])
def fake_ollama(request):
    import uvicorn
    from scripts.fake_ollama import app
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app(5.0, 64, request.param), host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", request.param
    server.should_exit = True
    th.join(timeout=5)


def test_load_runs_between_start_and_stop_and_the_parallel_check(fake_ollama):
    from scripts.ollama_load import OllamaLoad, check_parallel
    url, serial = fake_ollama
    r = asyncio.run(check_parallel(url, "fake", num_predict=20))
    assert r["parallel"] is (not serial) and r["fits"] and r["ok"] is (not serial) and r["gpu"]["share"] == 1.0

    async def run():
        load = OllamaLoad(url, "fake", concurrency=2, num_predict=(10, 20), warmup_s=2, cooldown_s=0)
        a = await load.start()
        await asyncio.sleep(0.4)
        b = await load.stop()
        return a, b
    a, b = asyncio.run(run())
    if not serial:
        assert a["generating_at_start"] == 2 and a["warm_s"] < 1.0
    assert b["tokens"] > 20 and b["started"] >= 2 and b["tokens_per_s"] > 0


def test_the_parallel_check_refuses_a_model_partly_off_the_gpu():
    import uvicorn
    from scripts.fake_ollama import app
    from scripts.ollama_load import check_parallel
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app(5.0, 64, False, gpu_share=0.41), host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    try:
        r = asyncio.run(check_parallel(f"http://127.0.0.1:{port}", "fake", num_predict=20))
    finally:
        server.should_exit = True
        th.join(timeout=5)
    assert r["parallel"] and not r["fits"] and not r["ok"] and "GPU memory" in r["detail"]


def test_arm_options_and_card_checks(tmp_path):
    arm = parse_arm("name=jl,ports=8500,jitter=4/1.8,load=2,out=x", 0, "edge-cloud")
    assert (arm.jitter, arm.load) == ("4/1.8", 2)
    arm = parse_arm("name=s,ports=8400,shape=2048:14:128:0.05:truncate,out=y", 0, "edge-cloud")
    assert arm.shape == "2048/14/128/0.05/truncate"
    for bad in ("name=a,deployment=a,jitter=4/1.8,out=z", "name=j,jitter=4,out=z", "name=l,load=-1,out=z"):
        with pytest.raises(SystemExit):
            parse_arm(bad, 0, "edge-cloud" if "deployment" not in bad else "local")
    desc = "A2A diagnostics agent [shaped reply 2048/14/128/0.05/truncate] [reply jitter 4/1.8/1]"
    assert advertised(desc, "shaped reply") == "2048/14/128/0.05/truncate"
    assert same_jitter(advertised(desc, "reply jitter")) == same_jitter("4/1.8") == (4.0, 1.8)
    assert advertised("A2A agent", "reply jitter") == "" and same_jitter("") is None
    log = ReplyLog(str(tmp_path))
    (tmp_path / "replies_8501.jsonl").write_text('{"old": 1}\n')
    log.mark([8501, 8502])
    with open(tmp_path / "replies_8501.jsonl", "a") as f:
        f.write('{"task_id": "t1"}\n')
    assert log.new([8501, 8502]) == [{"task_id": "t1"}] and log.new([8501, 8502]) == []


def test_the_calibration_s_sizes_are_the_wire_s():
    assert record(514) == 553 and record(285) == 324                       # C2's token event and completed event
    oh = overhead(ShapeConfig.parse("2048/14/128/0.05/truncate"))
    assert oh["events"] == 16 and oh["event_record"] == record(oh["event_json"])
    assert oh["reply_record_bytes"] == 16 * oh["event_record"] + oh["artifact_record"]
    assert oh["filler_const"] - 2 * 2048 >= 0                               # a full reply still has non-negative filler


def _shaped_trace(d: Path, stem: str, *, reply_segments, t0=100.0, release=14.762, edge_port=41000, retransmit=False,
                  arm="lan_shaped", shaping=True, cut=False):
    """One escalated trace: the edge's connection to the cloud agent on 8401, its 2 KB request in two
    segments, the reply as reply_segments (sizes), its last byte release seconds after the request's."""
    mac = dict(src="02:00:00:00:00:01", dst="02:00:00:00:00:02")
    e, c = Ether(**mac) / IP(src=PI, dst=CLOUD), Ether(**mac) / IP(src=CLOUD, dst=PI)
    a = dict(sport=edge_port, dport=8401)
    b = dict(sport=8401, dport=edge_port)
    pkts = [e / TCP(flags="S", seq=1000, **a), c / TCP(flags="SA", seq=5000, **b), e / TCP(flags="A", seq=1001, **a)]
    times = [t0, t0 + 0.012, t0 + 0.013]
    pkts += [e / TCP(flags="PA", seq=1001, **a) / (b"x" * 1448), e / TCP(flags="PA", seq=2449, **a) / (b"x" * 600)]
    times += [t0 + 0.02, t0 + 0.021]
    seq, n = 5001, len(reply_segments)
    for i, size in enumerate(reply_segments):
        pkts.append(c / TCP(flags="PA", seq=seq, **b) / (b"y" * size))
        times.append(t0 + 0.021 + (release * (i + 1) / n))
        if retransmit and i == 0:
            pkts.append(c / TCP(flags="PA", seq=seq, **b) / (b"y" * size))
            times.append(times[-1] + 0.2)
        seq += size
    for p, t in zip(pkts, times):
        p.time = t
    wrpcap(str(d / f"{stem}.pcap"), pkts)
    rec = {"port": 8401, "role": "diagnostics", "shaping": {"spec": "2048/14/128/0.05/truncate", "truncated": cut,
                                                            "overrun": False, "generated_s": 5.0, "released_s": 14.0}}
    (d / f"{stem}.json").write_text(json.dumps({
        "success": True, "arm": arm, "round": 0, "task_type": "fault_diagnosis", "start_ts": t0, "end_ts": t0 + 15.0,
        "agent_endpoints": {"diagnostics": f"{CLOUD}:8401"},
        "edge_report": {"escalated": True, "cloud_role": "diagnostics", "seconds": {"answer": 14.8}},
        "cloud_replies": [rec] if shaping else []}))


def test_check_shaping_counts_bytes_by_sequence_and_times_the_release(tmp_path):
    from scripts.check_shaping import checks, measure, overhead, summary
    d = tmp_path / "shaped"
    d.mkdir()
    _shaped_trace(d, "fault_diagnosis_edge_cloud_000001", reply_segments=[1000, 2000, 3000])
    _shaped_trace(d, "fault_diagnosis_edge_cloud_000002", reply_segments=[3000, 3000], t0=200.0, release=14.770)
    _shaped_trace(d, "fault_diagnosis_edge_cloud_000003", reply_segments=[6000], t0=300.0, retransmit=True)
    rows = measure(d)
    assert [r["reply_bytes"] for r in rows] == [6000, 6000, 6000] and {r["request_bytes"] for r in rows} == {2048}
    assert all(abs(r["release_s"] - 14.762) < 0.02 for r in rows)            # the retransmission is not the end
    res = checks(rows, "2048/14/128/0.05/truncate", wan_ms=12, tol_ms=50)
    assert res["ok"] and res["identical"]["reply_bytes"] == [6000] and res["release"]["spread_ms"] < 10
    _shaped_trace(d, "fault_diagnosis_edge_cloud_000004", reply_segments=[6001], t0=400.0, cut=True)
    res = checks(measure(d), "2048/14/128/0.05/truncate", wan_ms=12, tol_ms=50)
    assert not res["identical"]["ok"] and res["cut_overrun"]["cut"] == 1 and not res["ok"]
    late = tmp_path / "late"
    late.mkdir()
    _shaped_trace(late, "fault_diagnosis_edge_cloud_000005", reply_segments=[6000], release=15.5, shaping=False)
    res = checks(measure(late), "2048/14/128/0.05/truncate", wan_ms=12, tol_ms=50)
    assert not res["release"]["ok"] and res["cut_overrun"]["missing_or_other_spec"] == ["fault_diagnosis_edge_cloud_000005"]
    ctl = tmp_path / "control"
    ctl.mkdir()
    _shaped_trace(ctl, "fault_diagnosis_edge_cloud_000006", reply_segments=[30000] * 3, release=6.0, arm="lan_padmax")
    o = overhead(summary(rows), summary(measure(ctl)))["fault_diagnosis"]
    assert o["reply_bytes"] == 6000 - 90000 and abs(o["release_s"] - 8.762) < 0.02


def test_results_are_never_written_over(tmp_path):
    from scripts import b1_shape_calibration, round2_wan_plan
    from scripts.check_shaping import main as shaping_main
    assert round2_wan_plan.main(["--out-dir", str(tmp_path), "--allow-dirty"]) == 0
    plan = json.loads((tmp_path / "b1_wan.json").read_text())
    assert plan["collection_id"] == "C2B1" and plan["measurement_collection_id"] == "C2" and plan["created"]
    with pytest.raises(SystemExit, match="never written over"):
        round2_wan_plan.main(["--out-dir", str(tmp_path), "--allow-dirty"])
    (tmp_path / "cal.md").write_text("")
    with pytest.raises(SystemExit, match="never written over"):
        b1_shape_calibration.main(["--out", str(tmp_path / "cal"), "--allow-dirty"])
    (tmp_path / "ovh.json").write_text("")
    with pytest.raises(SystemExit, match="never written over"):
        shaping_main([str(tmp_path), "--out", str(tmp_path / "ovh"), "--allow-dirty"])
