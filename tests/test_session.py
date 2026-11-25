"""Session collector: arm parsing and port layout."""

import logging

import pytest

from scripts.collect_session import TOPOLOGIES, _DownstreamFailures, arm_items, parse_arm


def test_arm_defaults_and_ports_do_not_collide():
    a = parse_arm("name=x,deployment=a,out=d/x,tls=on", 0)
    b = parse_arm("name=y,deployment=b,out=d/y", 1)
    assert a.tls and not b.tls and a.defense == "none" and b.model == "qwen2.5:7b"
    ports = [p for arm in (a, b) for t in TOPOLOGIES for p in arm.ports(t).values()]
    assert len(ports) == len(set(ports)) == 24
    assert a.ports("chain") == {"orchestrator": 8110, "executor": 8111, "retriever": 8112, "validator": 8113}


def test_an_arm_can_run_an_even_subset_of_the_items():
    arm = parse_arm("name=lan_padmax,ports=8300,pad=8192/16384,pad_expect=8192,n=250,out=/tmp/x", 0, "edge-cloud")
    assert arm.n == 250 and parse_arm("name=s,ports=8400,out=/tmp/y", 1, "edge-cloud").n is None
    items = arm_items(625, 250)                                  # C2B1M's control beside 625 shaped, 25 rounds
    assert len(items) == 250
    assert [sum(1 for i in items if r * 25 <= i < (r + 1) * 25) for r in range(25)] == [10] * 25
    assert sorted(arm_items(10, 4)) == [2, 4, 7, 9] and arm_items(10, None) == arm_items(10, 10) == frozenset(range(10))
    for bad in ("n=0", "n=-3", "n=x"):
        with pytest.raises(SystemExit, match="n must be"):
            parse_arm(f"name=c,ports=8300,{bad},out=/tmp/z", 0, "edge-cloud")


def test_the_predecessor_flag_scales_with_the_task_types():
    from scripts.check_session_design import flag_share, predecessor_flags
    assert flag_share(4) == 0.40 and flag_share(2) == 0.75
    two = predecessor_flags({"a": {"x": {"x": 0.55, "y": 0.45}}}, {"a": {"x": 100}}, 2)["a"]["x"]
    four = predecessor_flags({"a": {"x": {"x": 0.45, "y": 0.55}}}, {"a": {"x": 100}}, 4)["a"]["x"]
    assert not two["flag"] and four["flag"]                      # C2's four task types: unchanged


def test_bad_arm_is_rejected():
    with pytest.raises(SystemExit):
        parse_arm("name=x,deployment=zz,out=d", 0)
    with pytest.raises(SystemExit):
        parse_arm("name=x,deployment=a,out=d,colour=red", 0)


def test_agent_errors_are_caught_but_others_ignored():
    watch = _DownstreamFailures()
    root = logging.getLogger()
    root.addHandler(watch)
    try:
        logging.getLogger("agents.orchestrator").error("[orchestrator] downstream 0 failed: 503")
        logging.getLogger("httpx").error("unrelated")
        logging.getLogger("agents.base").warning("not an error")
    finally:
        root.removeHandler(watch)
    assert watch.messages == ["[orchestrator] downstream 0 failed: 503"]


def test_remote_host_and_padding_arm(tmp_path):
    from scripts.collect_session import make_collector
    arm = parse_arm(f"name=lan,deployment=a,tls=off,host=192.168.2.2,ports=8100,pad=1024/4096,out={tmp_path}", 0)
    assert arm.host == "192.168.2.2" and arm.pad == [1024, 4096]
    assert parse_arm("name=x,deployment=a,out=d", 0).pad == [] and parse_arm("name=x,deployment=a,out=d", 0).host is None
    col = make_collector(arm, "star", "code_review", 256, interface="en7")
    assert col.agent_endpoints["executor"] == "192.168.2.2:8101"
    assert col.agent_endpoints["orchestrator"] == "127.0.0.1:8100"
    assert col.recorder.interface == "en7"
    assert col.recorder._bpf_filter() == "tcp and (port 8100 or port 8101 or port 8102 or port 8103) and (host 192.168.2.2)"


def test_padmax_arm_expects_one_bucket():
    from scripts.check_session_design import padding
    arm = parse_arm("name=lan_padmax,deployment=a,tls=on,host=192.168.2.2,ports=8300,pad=8192/16384,"
                    "pad_expect=8192,out=d", 2)
    assert arm.pad == [8192, 16384] and arm.pad_expect == 8192 and arm.ports("star")["executor"] == 8301
    with pytest.raises(SystemExit):
        parse_arm("name=x,deployment=a,out=d,pad=8192/16384,pad_expect=4096", 0)
    # first A2A messages on the wire: the 8192-byte body plus a constant ~300 B of HTTP and TLS
    def row(run_id, n, earlier=None, skipped=()):
        return {"run_id": run_id}, {"bytes": n, "earlier": n if earlier is None else earlier,
                                    "skipped": list(skipped), "acked": True}
    rows = [row("a", 8491, 1802), row("b", 8491, skipped=[197]), row("c", 8492)]
    r = padding(rows, arm.pad, arm.pad_expect)
    assert r["ok"] and r["expected_bucket"]["share"] == 1.0
    assert r["earlier_measure_differs"]["traces"] == 1 and r["earlier_measure_differs"]["largest_change"] == ("a", 1802, 8491)
    assert r["short_requests_before"] == {"traces": 1, "bytes": {197: 1}}
    big = row("d", 16683)                                                   # one body above 8192
    r = padding(rows + [big], arm.pad, arm.pad_expect)
    assert not r["ok"] and r["expected_bucket"]["traces_outside"] == 1
    assert padding(rows + [big], arm.pad)["expected_bucket"] is None        # lan_pad: no such rule
