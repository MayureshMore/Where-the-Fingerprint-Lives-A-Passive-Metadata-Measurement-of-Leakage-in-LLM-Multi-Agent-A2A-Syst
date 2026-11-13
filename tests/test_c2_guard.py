"""scripts/wan_watch.py reads every dummynet pipe where dnctl stops; scripts/c2_guard.py's checks.

The buffer is laid out as xnu's dummynet_get writes it for a 64-bit process: a 352-byte
dn_pipe_64 per pipe followed by its 176-byte dn_flow_queue_64 records, sized with the kernel's own
184-byte queue struct, so zeros trail.
"""

import argparse
import json
import socket
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import c2_guard  # noqa: E402
from wan_watch import DN_IS_PIPE, PIPE, QUEUE, parse_pipes  # noqa: E402

DNCTL_QUEUE = 184           # dnctl's sizeof(struct dn_flow_queue)


def _pipe(nr: int, delay: int, queues: list[tuple[str, int, str, int, int, int]]) -> bytes:
    b = bytearray(PIPE)
    struct.pack_into("<Qiii", b, 0, DN_IS_PIPE, nr, 0, delay)
    struct.pack_into("<ii", b, 168 + 32, 50, 0)                      # fs.qsize, fs.plr
    struct.pack_into("<ii", b, 168 + 96, 1, len(queues))             # fs.rq_size, fs.rq_elements
    for src, sport, dst, dport, pkts, drops in queues:
        q = bytearray(QUEUE)
        h = lambda ip: struct.unpack(">I", socket.inet_aton(ip))[0]  # noqa: E731
        struct.pack_into("<IIHHB", q, 8, h(dst), h(src), dport, sport, 6)
        struct.pack_into("<QQI", q, 96, pkts, pkts * 100, drops)
        b += q
    return bytes(b)


def _buffer() -> bytes:
    p1 = _pipe(1, 6, [("10.0.0.171", 42212, "172.30.0.100", 8101, 66044, 0)])
    p2 = _pipe(2, 6, [])
    return p1 + p2 + bytes(DNCTL_QUEUE - QUEUE)


def _dnctl_walk(buf: bytes) -> list[int]:
    out, off = [], 0
    while off + PIPE <= len(buf) and struct.unpack_from("<Q", buf, off)[0] == DN_IS_PIPE:
        out.append(struct.unpack_from("<i", buf, off + 8)[0])
        off += PIPE + struct.unpack_from("<i", buf, off + 168 + 100)[0] * DNCTL_QUEUE
    return out


def test_reader_finds_pipe_2_where_dnctl_stops():
    buf = _buffer()
    assert _dnctl_walk(buf) == [1]
    d = parse_pipes(buf)
    assert d["ok"]
    assert [(p["pipe"], p["delay_ms"], p["pkts"], p["drops"]) for p in d["pipes"]] == [(1, 6, 66044, 0), (2, 6, 0, 0)]
    assert d["pipes"][0]["flows"][0]["src"] == "10.0.0.171/42212"
    assert parse_pipes(_pipe(1, 6, []) + _pipe(2, 6, []))["pipes"][1]["pipe"] == 2
    assert not parse_pipes(buf[:-8] + b"\x01" * 8)["ok"]           # something after the last record


def _guard(tmp_path: Path, status: dict) -> c2_guard.Guard:
    p = tmp_path / "status.json"
    p.write_text(json.dumps(status))
    target = tmp_path / "target.json"
    target.write_text(json.dumps({"target_rtt_ms": 22.6, "delay_ms": 12, "emulation": {
        "pi": "10.0.0.171", "cloud": "172.30.0.100", "mac": "10.0.0.228", "iface": "en0",
        "bases": [8100, 8200, 8300], "one_way_ms": 6}}))
    a = argparse.Namespace(dirs=[str(tmp_path)], collector_pid=None, status=str(p), target=str(target), every=50,
                           tolerance=0.2, max_age=120, poll=1, grace=1, json=None, replay=False,
                           pi_overhead_ms=3.31, calibration=None)
    return c2_guard.Guard(a)


def _status(**over) -> dict:
    ports = [8101, 8102, 8105, 8201, 8202, 8205, 8301, 8302, 8305]
    rules = [f"pass in quick on en0 inet proto tcp from 10.0.0.171 to {a} port = {p} flags S/SA keep state"
             for a in ("10.0.0.228", "172.30.0.100") for p in ports]
    rules += [f"block drop in quick on en0 inet proto tcp from any to {a} port = {p}"
              for a in ("10.0.0.228", "172.30.0.100") for p in ports]
    s = {"time": time.time(), "dummynet": parse_pipes(_buffer()), "pf_status": "Status: Enabled for 0 days",
         "anchor_rules": rules,
         "anchor_dummynet": ["dummynet in quick on en0 inet proto tcp from 10.0.0.171 to 172.30.0.100 pipe 1",
                             "dummynet out quick on en0 inet proto tcp from 172.30.0.100 to 10.0.0.171 pipe 2"]}
    return {**s, **over}


def test_status_checks(tmp_path):
    ok = lambda s: all(r["ok"] for r in _guard(tmp_path, s).status())                       # noqa: E731
    assert ok(_status())
    one = _status()
    one["dummynet"] = {**one["dummynet"], "pipes": one["dummynet"]["pipes"][:1]}
    assert not ok(one)                                                                     # pipe 2 missing
    assert not ok(_status(time=time.time() - 600))                                         # old reading
    assert not ok(_status(anchor_rules=[r for r in _status()["anchor_rules"] if "8205" not in r or "block" in r]))
    assert not ok(_status(anchor_rules=list(reversed(_status()["anchor_rules"]))))         # block before pass
    assert not ok(_status(anchor_dummynet=_status()["anchor_dummynet"][:1]))               # no rule into pipe 2
    assert not ok(_status(pf_status="Status: Disabled"))
