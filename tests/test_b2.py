"""B2 as the WAN portability check (docs/PREREG_C2B2.md): the manipulation checks
(scripts/check_b2_manipulation.py), the timing-alone audits (scripts/b1_audits.py --feature-sets), the
cloud agents' record of their jitter draws and the GPU check (scripts/ollama_load.py gpu_state)."""

import asyncio
import json
import threading
import time
from pathlib import Path

import numpy as np
import pytest
from scapy.all import IP, TCP, Ether, wrpcap

from scripts import b1_audits
from scripts.check_b2_manipulation import (check_gpu, check_jitter_log, check_load_slowdown, check_load_windows,
                                           check_netem_capture, main, parse_tc, sidecars)

ROOT = Path(__file__).resolve().parent.parent
PI, CLOUD, MAC = "10.0.0.171", "172.30.0.100", "10.0.0.228"

TC_TEMPLATE = """qdisc prio 1: root refcnt 2 bands 4 priomap 1 2 2 2 1 2 0 0 1 1 1 1 1 1 1 1
 Sent 9912345 bytes 61234 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
qdisc netem 40: parent 1:4 limit 1000 delay 4ms  1.8ms rate 1Gbit
 Sent {bytes} bytes {pkts} pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
"""


def _handshakes(path: Path, base: int, synack_ms: float, ack_ms: list[float], t0: float = 1000.0) -> None:
    """One cloud connection per entry of ack_ms: SYN, SYN-ACK synack_ms later, the Pi's ACK ack_ms after
    that, then one data packet each way (the Pi's to the cloud port counts as Pi -> cloud)."""
    pkts, t = [], t0
    for k, a in enumerate(ack_ms):
        sport = 40000 + k
        for ts, src, dst, sp, dp, fl, load in (
                (t, PI, CLOUD, sport, base + 1, "S", b""),
                (t + synack_ms / 1000, CLOUD, PI, base + 1, sport, "SA", b""),
                (t + (synack_ms + a) / 1000, PI, CLOUD, sport, base + 1, "A", b""),
                (t + 0.05, PI, CLOUD, sport, base + 1, "PA", b"x" * 100),
                (t + 0.06, CLOUD, PI, base + 1, sport, "PA", b"y" * 100)):
            p = Ether() / IP(src=src, dst=dst) / TCP(sport=sp, dport=dp, flags=fl, seq=1000) / load
            p.time = ts
            pkts.append(p)
        t += 1.0
    wrpcap(str(path), pkts)


def _session(tmp_path: Path, *, netem_ms=4.0, draw_sd=1.78, overlap=False, slow=1.6, gpu_round_fail=False,
             n=6) -> tuple[Path, Path]:
    c, x = tmp_path / "padmax", tmp_path / "padmax_jl"
    c.mkdir(exist_ok=True)
    x.mkdir(exist_ok=True)
    rng = np.random.default_rng(1)
    t = 10_000.0
    types = ["sensor_analysis", "fault_diagnosis", "procedure_lookup", "alert_triage"]
    for i in range(n):
        for arm, folder, base in (("lan_padmax", c, 8100), ("lan_padmax_jl", x, 8500)):
            for tt in types:
                run = f"{tt}_edge_cloud_{arm}{i}"
                esc = tt != "alert_triage"
                wifi = list(rng.normal(9.0, 1.5, 3))
                acks = [w + (netem_ms if arm.endswith("jl") else 0.0) for w in wifi]
                _handshakes(folder / f"{run}.pcap", base, 4.0 if arm.endswith("jl") else 12.0, acks)
                start, end = t, t + 5.0
                sc = {"run_id": run, "success": True, "task_type": tt, "arm": arm, "round": i // 3,
                      "start_ts": start, "end_ts": end,
                      "agent_endpoints": {"diagnostics": f"{CLOUD}:{base + 1}", "knowledge": f"{CLOUD}:{base + 2}",
                                          "ticket": f"{MAC}:{base + 5}"},
                      "edge_report": {"escalated": esc, "seconds": {"answer": (5.0 * (slow if arm.endswith("jl") else 1.0)
                                                                               if esc else None)}},
                      "load": None}
                if arm.endswith("jl"):
                    draws = np.clip(rng.normal(4.0, draw_sd, 400), 0, None)
                    if esc:
                        sc["cloud_replies"] = [{"port": base + 1, "jitter": {
                            "spec": "4/1.8/1", "events": 400, "mean_ms": 4.1, "max_ms": 9.0,
                            "draws": {"n": 400, "sum_ms": float(draws.sum()), "sumsq_ms2": float((draws ** 2).sum())}}}]
                    sc["load"] = {"concurrency": 2, "generating_at_start": 2, "tokens": 300, "tokens_per_s": 60.0,
                                  "t_start": start - 1.0, "t_stop": end + 0.2}
                (folder / f"{run}.json").write_text(json.dumps(sc))
                t += 6.0 if not (overlap and arm == "lan_padmax" and i == 0) else 0.5
    rounds = sorted({i // 3 for i in range(n)})
    gpu = {"share": 1.0, "context_length": 32768, "size_gb": 16.7, "vram_gb": 16.7}
    bad = {**gpu, "share": 0.6}
    checks = [{"round": r, "fits": True, "gpu": bad if (gpu_round_fail and r == rounds[-1]) else gpu} for r in rounds]
    checks.append({"round": "end", "fits": True, "gpu": gpu})
    meta = {"collection_id": "C2B2-test", "schedule": [{"round": r} for r in rounds],
            "load": {"parallel_checks": [{"ok": True, "gpu": gpu}]}, "gpu_checks": checks}
    for folder in (c, x):
        (folder / "session_meta.json").write_text(json.dumps(meta))
    return c, x


def test_parse_tc_finds_netem_and_its_packets():
    r = parse_tc(TC_TEMPLATE.format(bytes=123, pkts=456))
    assert r == {"handle": "40:", "delay_ms": 4.0, "jitter_ms": 1.8, "packets": 456}
    assert parse_tc("qdisc fq_codel 0: root refcnt 2 limit 10240p\n Sent 1 bytes 1 pkt\n") is None
    assert parse_tc("qdisc netem 40: parent 1:4 limit 1000 delay 4000us  1800us\n Sent 5 bytes 2 pkt (dropped 0)\n") == \
        {"handle": "40:", "delay_ms": 4.0, "jitter_ms": 1.8, "packets": 2}


def test_a_session_with_every_manipulation_in_place_is_valid(tmp_path):
    c, x = _session(tmp_path)
    ctl, trt = sidecars(c), sidecars(x)
    assert check_netem_capture(ctl, trt, 4.01)["ok"]
    j = check_jitter_log(ctl, trt, "4/1.8", 4.008, 1.779)
    assert j["ok"] and j["draws"] == 6 * 3 * 400 and abs(j["mean_ms"] - 4.0) < 0.15
    assert check_load_windows(ctl, trt, 2)["ok"]
    s = check_load_slowdown(ctl, trt)
    assert s["ok"] and abs(s["per_task_type"]["sensor_analysis"]["ratio"] - 1.6) < 1e-9
    assert check_gpu(json.loads((x / "session_meta.json").read_text()), 32768)["ok"]
    (tmp_path / "tc_start.txt").write_text(TC_TEMPLATE.format(bytes=1, pkts=100))
    sent = 6 * 4 * 3 * 3            # 24 treatment traces, 3 connections, 3 Pi -> cloud packets each
    (tmp_path / "tc_end.txt").write_text(TC_TEMPLATE.format(bytes=9, pkts=100 + sent))
    (tmp_path / "reorder.json").write_text(json.dumps({"ok": True}))
    (tmp_path / "keeper.json").write_text(json.dumps({"pass": True}))
    args = ["--control", str(c), "--treatment", str(x), "--target", str(ROOT / "data/results/b2_wan_jitter.json"),
            "--tc-start", str(tmp_path / "tc_start.txt"), "--tc-end", str(tmp_path / "tc_end.txt"),
            "--reorder", str(tmp_path / "reorder.json"), "--keeper", str(tmp_path / "keeper.json"),
            "--json", str(tmp_path / "out.json")]
    assert main(args) == 0
    out = json.loads((tmp_path / "out.json").read_text())
    assert out["valid"] and out["checks"]["netem_pi"]["captured_pi_to_cloud_packets"] == sent
    assert out["checks"]["netem_pi"]["netem_packets"] == sent
    # netem's count grew by less than the Pi's packets to the cloud ports: netem was not on all session
    (tmp_path / "tc_end.txt").write_text(TC_TEMPLATE.format(bytes=9, pkts=110))
    assert main(args) == 1
    # no netem at the end
    (tmp_path / "tc_end.txt").write_text("qdisc fq_codel 0: root\n Sent 1 bytes 1 pkt\n")
    assert main(args) == 1


def test_without_netem_the_acks_are_no_later_than_the_control_s(tmp_path):
    c, x = _session(tmp_path, netem_ms=0.0)
    r = check_netem_capture(sidecars(c), sidecars(x), 4.01)
    assert not r["ok"] and abs(r["difference_ms"]) < 1.5


def test_a_jitter_of_the_wrong_spread_or_a_missing_record_fails(tmp_path):
    c, x = _session(tmp_path, draw_sd=0.5)
    assert not check_jitter_log(sidecars(c), sidecars(x), "4/1.8", 4.008, 1.779)["ok"]
    (tmp_path / "b").mkdir()
    c, x = _session(tmp_path / "b", n=3)
    trt = sidecars(x)
    esc = next(sc for sc in trt if sc["edge_report"]["escalated"])
    esc.pop("cloud_replies")
    r = check_jitter_log(sidecars(c), trt, "4/1.8", 4.008, 1.779)
    assert not r["ok"] and r["n_without_record"] == 1


def test_a_control_trace_during_a_load_or_a_trace_outside_its_window_fails(tmp_path):
    c, x = _session(tmp_path, overlap=True)
    r = check_load_windows(sidecars(c), sidecars(x), 2)
    assert not r["ok"] and r["n_control_overlapping"] >= 1
    (tmp_path / "b").mkdir()
    c, x = _session(tmp_path / "b")
    trt = sidecars(x)
    trt[0]["load"]["t_stop"] = trt[0]["end_ts"] - 1
    r = check_load_windows(sidecars(c), trt, 2)
    assert not r["ok"] and r["not_under_load"][0]["why"] == "the window does not cover the trace"


def test_no_slowdown_under_load_fails(tmp_path):
    c, x = _session(tmp_path, slow=1.05)
    assert not check_load_slowdown(sidecars(c), sidecars(x))["ok"]


def test_the_gpu_check_takes_each_round_s_last_check_and_the_end(tmp_path):
    c, x = _session(tmp_path, gpu_round_fail=True)
    meta = json.loads((x / "session_meta.json").read_text())
    r = check_gpu(meta, 32768)
    assert not r["ok"] and r["rounds_failed"] == ["1"]
    meta["gpu_checks"].insert(-1, {"round": 1, "fits": True, "gpu": {"share": 1.0, "context_length": 32768}})
    assert check_gpu(meta, 32768)["ok"]                       # failed, then passed on resume: the last one counts
    assert not check_gpu(meta, 131072)["ok"]                  # another context than the session's
    meta["gpu_checks"] = [g for g in meta["gpu_checks"] if g["round"] != "end"]
    assert not check_gpu(meta, 32768)["ok"]


def _features(folder: Path, n: int = 40) -> None:
    from a2a_leakcheck.extract import FEATURE_SCHEMA_VERSION
    folder.mkdir(parents=True)
    rng = np.random.default_rng(0)
    np.savez_compressed(folder / "features.npz", trace_X=rng.random((n, 195)).astype(np.float32) + 1,
                        first_request=np.full(n, 8192, np.float32), role_X=rng.random((2 * n, 35)).astype(np.float32) + 1,
                        role_y=np.array(["a", "b"] * n), role_trace=np.repeat(np.arange(n), 2))
    (folder / "features.json").write_text(json.dumps({"schema_version": FEATURE_SCHEMA_VERSION,
                                                      "input": {"folder": "x", "vantage": "v2"},
                                                      "attributes": ["task_type"], "traces": []}))


def test_the_timing_only_copy_keeps_the_timing_columns_and_zeroes_the_rest(tmp_path):
    from features.families import family_columns
    src = tmp_path / "f"
    _features(src)
    fs = b1_audits.only_family(src, tmp_path / "f_timing", "timing")
    with np.load(src / "features.npz") as a, np.load(tmp_path / "f_timing" / "features.npz") as b:
        t, r = family_columns("timing", False), family_columns("timing", True)
        assert fs["trace_columns"] == len(t) == 30 and fs["role_columns"] == len(r) == 5
        assert np.array_equal(b["trace_X"][:, t], a["trace_X"][:, t])
        mask = np.ones(195, bool)
        mask[t] = False
        assert not b["trace_X"][:, mask].any() and not b["first_request"].any()
        assert np.array_equal(b["role_X"][:, r], a["role_X"][:, r]) and b["role_X"].sum() == b["role_X"][:, r].sum()
        assert np.array_equal(b["role_y"], a["role_y"])
    meta = json.loads((tmp_path / "f_timing" / "features.json").read_text())
    assert meta["feature_set"]["family"] == "timing" and meta["schema_version"] == 1


def test_a_features_folder_of_other_input_is_not_reused(tmp_path):
    feats = tmp_path / "f"
    _features(feats)
    with pytest.raises(SystemExit, match="other features"):
        b1_audits.extract_family(tmp_path / "captures", feats, "v2", "task_type", "timing")
    src, fs = b1_audits.extract_family(Path("x"), feats, "v2", "task_type", "timing")   # the same input: reused
    assert src == tmp_path / "f_timing" and fs["family"] == "timing"


def test_report_names_and_the_command_on_a_features_folder():
    assert b1_audits.name("c2b2", "lan_padmax", "v2", "pair", "timing") == "c2b2_lan_padmax_v2_pair_timing"
    assert b1_audits.name("c2b2", "lan_padmax", "v2", "all") == "c2b2_lan_padmax_v2"
    cmd = b1_audits.command(Path("f"), Path("o"), "v2", "task_type", "l", None, 4, features=True)
    assert "--strip" not in cmd and "--vantage" not in cmd and cmd[3] == "run"
    cmd = b1_audits.command(Path("f"), Path("o"), "v2", "task_type", "l", Path("b.json"), 4)
    assert cmd[cmd.index("--vantage") + 1] == "v2" and cmd[-2:] == ["--baseline", "b.json"]


def test_without_feature_sets_the_summary_has_no_new_fields(tmp_path, monkeypatch):
    """Summaries written before --feature-sets (B1, D3, B3, C2B1M) compare equal to new runs of the same."""
    import subprocess as sp
    rep = {"attributes": {"task_type": {"verdict": "LEAK", "analysis": {"macro_f1": 0.7, "ci_lo": 0.6, "ci_hi": 0.8},
                                        "validation": {"permutation": {"p_value": 0.01}}, "n": 10, "n_groups": 10,
                                        "classes": ["a", "b"], "threshold": 0.55}}}
    arm = tmp_path / "arm"
    arm.mkdir()

    def fake_run(cmd, capture_output, text):
        out = Path(cmd[cmd.index("--out") + 1])
        out.mkdir(parents=True)
        (out / "report.json").write_text(json.dumps(rep))
        return sp.CompletedProcess(cmd, 0, "ok", "")
    monkeypatch.setattr(b1_audits.subprocess, "run", fake_run)
    monkeypatch.setattr(b1_audits, "_git", lambda: {"git_commit": "x", "git_dirty": False})
    b1_audits.main(["--arm", f"a={arm}", "--views", "v2", "--parts", "all", "--prefix", "p", "--reports",
                    str(tmp_path / "r"), "--out", str(tmp_path / "s")])
    s = json.loads((tmp_path / "s.json").read_text())
    assert "feature_sets" not in s["parameters"] and "feature_set" not in s["runs"]["p_a_v2"]


def test_the_cloud_agent_logs_its_draws_as_sums(tmp_path):
    from tests.test_shaping import _free_port, _serve
    from agents.base import AgentConfig, AgentRole
    log = tmp_path / "replies.jsonl"
    cfg = AgentConfig(role=AgentRole.DIAGNOSTICS, host="127.0.0.1", port=_free_port(), tls=False, jitter="30/10/1",
                      reply_log=str(log))
    (ev,) = asyncio.run(_serve(cfg, ["300"]))
    j = json.loads(log.read_text())["jitter"]
    d = j["draws"]
    assert d["n"] == j["events"] == len(ev)
    mean = d["sum_ms"] / d["n"]
    assert 15 < mean < 45 and d["sumsq_ms2"] >= d["sum_ms"] ** 2 / d["n"]
    assert j["mean_ms"] >= mean - 1e-9                     # a wait is never shorter than its draw


def test_jitter_keeps_its_last_draw():
    from defense.shaping import Jitter, JitterConfig
    j = Jitter(JitterConfig.parse("4/1.8/7"), stream="s")
    assert j.last_draw_ms is None
    d = j.departure(1.0) - 1.0
    assert abs(j.last_draw_ms - d * 1000) < 1e-9
    j2 = Jitter(JitterConfig.parse("4/1.8/7"), stream="s")      # the same draws as before the change
    assert abs(j2.draw_s() - d) < 1e-12


@pytest.mark.parametrize("share,fits", [(1.0, True), (0.41, False)])
def test_gpu_state_reads_the_share_and_the_context(share, fits):
    import uvicorn
    from tests.test_round2_sessions import _free_port as port_
    from scripts.fake_ollama import app
    from scripts.ollama_load import gpu_state
    port = port_()
    server = uvicorn.Server(uvicorn.Config(app(5.0, 64, False, gpu_share=share), host="127.0.0.1", port=port,
                                           log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    try:
        r = asyncio.run(gpu_state(f"http://127.0.0.1:{port}", "fake"))
        gone = asyncio.run(gpu_state(f"http://127.0.0.1:{port}", "other"))
    finally:
        server.should_exit = True
        th.join(timeout=5)
    assert r["fits"] is fits and r["gpu"]["share"] == share and r["gpu"]["context_length"] == 4096
    assert gone == {"model": "other", "gpu": None, "fits": False}
