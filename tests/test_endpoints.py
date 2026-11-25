"""a2a-leakcheck keys agent endpoints by host and port (a2a_leakcheck/endpoints.py), and counts the traces a view
sees nothing of as expected silent or unexpectedly empty (a2a_leakcheck/extract.py). Synthetic captures: DLT_NULL,
one TCP connection per call with its handshake, headers only."""

import ipaddress
import json
import struct

import numpy as np
import pytest

from a2a_leakcheck.cli import main
from a2a_leakcheck.collect import collect, read_trace
from a2a_leakcheck.endpoints import LOOPBACK, foreign_packets, parse_endpoints, role_keys
from a2a_leakcheck.extract import expected_silent, extract
from a2a_leakcheck.report import _vantage_md
from scripts.compare_reports import compare


def _packet(src, dst, sp, dp, seq, ack, flags, n):
    s, d = ipaddress.ip_address(src), ipaddress.ip_address(dst)
    tcp = struct.pack(">HHIIBBHHH", sp, dp, seq, ack, 5 << 4, flags, 65535, 0, 0)
    if s.version == 4:
        ip = struct.pack(">BBHHHBBH4s4s", 0x45, 0, 40 + n, 0, 0, 64, 6, 0, s.packed, d.packed)
        return struct.pack("<I", 2) + ip + tcp
    ip = struct.pack(">IHBB16s16s", 0x60000000, 20 + n, 6, 64, s.packed, d.packed)
    return struct.pack("<I", 30) + ip + tcp


def _pcap(path, calls):
    """calls: (client ip, server ip, client port, server port, request bytes, response bytes), one after another."""
    out, t = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 96, 0), 0
    for c, s, cp, sp, req, resp in calls:
        for src, dst, a, b, seq, ack, fl, n in [
                (c, s, cp, sp, 100, 0, 0x02, 0), (s, c, sp, cp, 500, 101, 0x12, 0), (c, s, cp, sp, 101, 501, 0x10, 0),
                (c, s, cp, sp, 101, 501, 0x18, req), (s, c, sp, cp, 501, 101 + req, 0x10, 0),
                (s, c, sp, cp, 501, 101 + req, 0x18, resp), (c, s, cp, sp, 101 + req, 501 + resp, 0x10, 0)]:
            pkt = _packet(src, dst, a, b, seq, ack, fl, n)
            t += 1
            out += struct.pack("<IIII", t // 10, (t % 10) * 100000, len(pkt), len(pkt) + n) + pkt
    path.write_bytes(out)


def _trace(folder, name, calls, **side):
    folder.mkdir(parents=True, exist_ok=True)
    _pcap(folder / f"{name}.pcap", calls)
    (folder / f"{name}.json").write_text(json.dumps({"run_id": name, "tls": False, "workflow_class": "w",
                                                     "prompt_group": name, **side}))


def test_an_endpoint_is_a_host_and_a_port():
    e, why = parse_endpoints({"a": "10.0.0.2:8101", "b": "[::1]:8102", "c": "localhost:8103", "d": "agents.lan:8104"})
    assert why == "" and e == {("10.0.0.2", 8101): "a", (LOOPBACK, 8102): "b", (LOOPBACK, 8103): "c", (None, 8104): "d"}
    assert role_keys(e) == {"10.0.0.2:8101": "a", "8102": "b", "8103": "c", "8104": "d"}
    e, why = parse_endpoints({"diagnostics": "10.0.0.2:443", "knowledge": "10.0.0.3:443"})
    assert why == "" and len(e) == 2                                   # one port, two hosts: two agents
    for eps, msg in (({"a": "10.0.0.2:8101", "b": "10.0.0.2:8101"}, "share the address"),
                     ({"a": "127.0.0.1:8101", "b": "localhost:8101"}, "share the address"),     # loopback is one host
                     ({"a": "10.0.0.2:8101", "b": "agents.lan:8101"}, "with and without a host")):
        assert parse_endpoints(eps)[0] == {} and msg in parse_endpoints(eps)[1]


def test_another_hosts_traffic_on_an_agent_port_is_dropped(tmp_path):
    own = ("10.0.0.9", "10.0.0.2", 50000, 8101, 600, 400)
    other = ("10.0.0.9", "10.0.0.7", 50001, 8101, 900, 2000)               # the same port on a host not listed
    side = {"agent_endpoints": {"executor": "10.0.0.2:8101"}}
    _trace(tmp_path / "mixed", "t", [own, other], **side)
    _trace(tmp_path / "clean", "t", [own], **side)
    with pytest.raises(SystemExit, match="10.0.0.7:8101"):
        collect(tmp_path / "mixed", ["workflow"])
    col = collect(tmp_path / "mixed", ["workflow"], filter_dir=tmp_path / "work")
    assert col["summary"]["other_host_packets"] == {"captures": 1, "packets": 7, "endpoints": {"10.0.0.7:8101": 7}}
    clean = collect(tmp_path / "clean", ["workflow"], filter_dir=tmp_path / "work2")
    assert clean["summary"]["other_host_packets"]["packets"] == 0
    a, b = extract(col["traces"]), extract(clean["traces"])
    assert np.array_equal(a["trace_X"], b["trace_X"]) and np.array_equal(a["role_X"], b["role_X"])
    assert a["first_request"][0] == b["first_request"][0] == 600


def test_two_agents_on_one_port_keep_their_own_role_samples(tmp_path):
    _trace(tmp_path, "t", [("10.0.0.9", "10.0.0.2", 50000, 443, 600, 400), ("10.0.0.9", "10.0.0.3", 50001, 443, 900, 3000)],
           agent_endpoints={"diagnostics": "10.0.0.2:443", "knowledge": "10.0.0.3:443"})
    tr, why = read_trace(tmp_path / "t.pcap", [])
    assert why == "" and tr.port_role == {443: "diagnostics+knowledge"}
    ext = extract(collect(tmp_path, [], filter_dir=tmp_path / "work")["traces"])
    assert list(ext["role_y"]) == ["diagnostics", "knowledge"]           # before 0.3.1: one sample, one role
    assert not np.array_equal(ext["role_X"][0], ext["role_X"][1])


def test_a_sidecar_on_127_0_0_1_matches_traffic_on_ipv6_loopback(tmp_path):
    _pcap(tmp_path / "t.pcap", [("::1", "::1", 50000, 8101, 600, 400)])
    e, _ = parse_endpoints({"executor": "127.0.0.1:8101"})
    assert foreign_packets(tmp_path / "t.pcap", e) == ([], {})
    e, _ = parse_endpoints({"executor": "10.0.0.2:8101"})
    drop, seen = foreign_packets(tmp_path / "t.pcap", e)
    assert len(drop) == 7 and seen == {f"{LOOPBACK}:8101": 7}


EPS = {"diagnostics": "172.30.0.100:8101", "ticket": "10.0.0.228:8105"}
VIEWS = {"v1": ["diagnostics", "ticket"], "v2": ["diagnostics"]}
CLOUD = ("10.0.0.171", "172.30.0.100", 50000, 8101, 900, 1500)
TICKET = ("10.0.0.171", "10.0.0.228", 50001, 8105, 300, 100)


@pytest.fixture
def edge_cloud(tmp_path):
    side = {"agent_endpoints": EPS, "vantages": VIEWS}
    _trace(tmp_path, "a_escalated", [CLOUD, TICKET], escalated="yes", cloud_role="diagnostics", **side)
    _trace(tmp_path, "b_local", [TICKET], escalated="no", **side)                      # silent upstream, as expected
    _trace(tmp_path, "c_missed", [TICKET], escalated="yes", cloud_role="diagnostics", **side)   # the cloud call missing
    _trace(tmp_path, "d_unknown", [TICKET], **side)                                    # the sidecar says nothing
    return tmp_path


def test_empty_traces_are_expected_silent_or_unexpectedly_empty(edge_cloud):
    s = extract(collect(edge_cloud, ["escalated"], vantage="v2", filter_dir=edge_cloud / "w")["traces"],
                keep_empty=True)["summary"]
    assert (s["empty_traces"], s["empty_expected_silent"], s["empty_unexpected"]) == (3, 1, 2)
    assert s["empty_unexpected_runs"] == ["c_missed", "d_unknown"]
    s = extract(collect(edge_cloud, ["escalated"], vantage="v1", filter_dir=edge_cloud / "w1")["traces"],
                keep_empty=True)["summary"]
    assert (s["empty_traces"], s["empty_expected_silent"], s["empty_unexpected"]) == (0, 0, 0)


def test_a_local_task_is_silent_only_where_the_view_sees_cloud_agents_alone(edge_cloud):
    v1, _ = read_trace(edge_cloud / "b_local.pcap", [], "v1")
    v2, _ = read_trace(edge_cloud / "b_local.pcap", [], "v2")
    assert expected_silent(v2, {"diagnostics"}) and not expected_silent(v1, {"diagnostics"})   # v1 sees the ticket post
    assert not expected_silent(v2, set())                     # no escalated trace names a cloud agent: no evidence


def test_the_counts_reach_the_extract_command_and_the_report(edge_cloud, capsys):
    assert main(["extract", str(edge_cloud), "--vantage", "v2", "--attributes", "escalated",
                 "--out", str(edge_cloud / "f")]) == 0
    assert "3 with nothing in view: 1 expected silent, 2 unexpectedly empty" in capsys.readouterr().out
    e = json.loads((edge_cloud / "f" / "features.json").read_text())["extraction"]
    md = "\n".join(_vantage_md({"input": {"vantage": "v2"}, "extraction": e}))
    assert "1 expected: not escalated" in md and "2 unexpectedly empty" in md
    assert "**Check the capture**: 2 traces" in md and "`c_missed`, `d_unknown`" in md
    older = {k: v for k, v in e.items() if not k.startswith("empty_") or k == "empty_traces"}
    assert "Check the capture" not in "\n".join(_vantage_md({"input": {"vantage": "v2"}, "extraction": older}))


def test_reports_from_before_the_counts_still_compare():
    base = {"attributes": {}, "summary": {}, "parameters": {}, "input": {},
            "collection": {"traces": 4}, "extraction": {"traces": 4, "empty_traces": 3}}
    new = json.loads(json.dumps(base))
    new["collection"]["other_host_packets"] = {"captures": 0, "packets": 0, "endpoints": {}}
    new["extraction"].update(empty_expected_silent=1, empty_unexpected=2, empty_unexpected_runs=["c", "d"])
    assert compare(new, base)["same"]
    later = json.loads(json.dumps(new))
    later["extraction"]["empty_unexpected"] = 1
    assert [d["field"] for d in compare(later, new)["differences"]] == ["extraction.empty_unexpected"]
