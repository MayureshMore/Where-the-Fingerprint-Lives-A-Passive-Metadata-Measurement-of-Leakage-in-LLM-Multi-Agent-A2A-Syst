"""Session collector: arm parsing and port layout."""

import logging

import pytest

from scripts.collect_session import TOPOLOGIES, _DownstreamFailures, parse_arm


def test_arm_defaults_and_ports_do_not_collide():
    a = parse_arm("name=x,deployment=a,out=d/x,tls=on", 0)
    b = parse_arm("name=y,deployment=b,out=d/y", 1)
    assert a.tls and not b.tls and a.defense == "none" and b.model == "qwen2.5:7b"
    ports = [p for arm in (a, b) for t in TOPOLOGIES for p in arm.ports(t).values()]
    assert len(ports) == len(set(ports)) == 24
    assert a.ports("chain") == {"orchestrator": 8110, "executor": 8111, "retriever": 8112, "validator": 8113}


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
