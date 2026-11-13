#!/usr/bin/env python3
"""
Watch C2's emulated WAN on the Mac (run as root): every --every seconds, read the dummynet pipes
straight from the kernel, the pf anchor com.apple/c2-wan (dummynet rules and port lock) and pf's
status, and write them to --out (JSON, replaced atomically, owned by the sudo user) for
scripts/c2_guard.py, which cannot read them without root. --log appends one line per sample.

Why not dnctl: in a 64-bit process the kernel copies each flow queue out as a 176-byte
struct dn_flow_queue_64 (xnu bsd/netinet/ip_dummynet.c, dn_copy_set_64), but dnctl steps over it
as its own 184-byte struct dn_flow_queue (network_cmds dnctl.c, list_pipes). Once a pipe has a
queue, which its first packet creates, dnctl lands 8 bytes into the next pipe's record, finds no
pipe marker there and stops: `dnctl list` shows only the first pipe and `dnctl pipe show 2` prints
nothing although pipe 2 exists and delays packets. This reader steps by the kernel's own sizes and
checks that the records it walks end where the kernel's data does. dnctl's listing is kept in the
JSON, for the record.

    sudo venv/bin/python scripts/wan_watch.py --out data/raw_c2/wan_status.json --log data/raw_c2/wan_watch.jsonl
    sudo venv/bin/python scripts/wan_watch.py --once          # print what it reads, then exit
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

IP_DUMMYNET_GET = 64                       # <netinet/in.h>
DN_IS_PIPE, DN_IS_QUEUE = 0x4000, 0x8000   # the kernel marks each record's first field
PIPE, FLOW_SET, QUEUE = 352, 184, 176      # sizeof dn_pipe_64, dn_flow_set_64, dn_flow_queue_64
FS_IN_PIPE = 168                           # offsetof(struct dn_pipe_64, fs)
ANCHOR = "com.apple/c2-wan"


def _queue(buf: bytes, off: int) -> dict:
    dst, src, dport, sport, proto = struct.unpack_from("<IIHHB", buf, off + 8)     # struct ip_flow_id
    pkts, nbytes = struct.unpack_from("<QQ", buf, off + 96)
    drops, = struct.unpack_from("<I", buf, off + 112)
    ip = lambda v: socket.inet_ntoa(struct.pack(">I", v))                           # noqa: E731 (host order)
    return {"src": f"{ip(src)}/{sport}", "dst": f"{ip(dst)}/{dport}", "proto": proto,
            "pkts": pkts, "bytes": nbytes, "drops": drops}


def _flow_set(buf: bytes, off: int) -> dict:
    qsize, plr = struct.unpack_from("<ii", buf, off + 32)
    rq_size, rq_elements = struct.unpack_from("<ii", buf, off + 96)
    return {"qsize": qsize, "plr": plr, "rq_size": rq_size, "queues": rq_elements}


def parse_pipes(buf: bytes) -> dict:
    """The pipes and flow sets in an IP_DUMMYNET_GET buffer. ok: every record carried its marker
    and only zeros follow the last one (the kernel sizes the buffer with its own, larger, queue
    struct, so a few zero bytes can trail)."""
    pipes, sets, off = [], [], 0
    while off + PIPE <= len(buf) and struct.unpack_from("<Q", buf, off)[0] == DN_IS_PIPE:
        nr, bandwidth, delay = struct.unpack_from("<iii", buf, off + 8)
        fs = _flow_set(buf, off + FS_IN_PIPE)
        q0 = off + PIPE
        queues = [_queue(buf, q0 + i * QUEUE) for i in range(fs["queues"]) if q0 + (i + 1) * QUEUE <= len(buf)]
        pipes.append({"pipe": nr, "bandwidth": bandwidth, "delay_ms": delay, **fs, "flows": queues,
                      "pkts": sum(q["pkts"] for q in queues), "drops": sum(q["drops"] for q in queues)})
        off = q0 + fs["queues"] * QUEUE
    while off + FLOW_SET <= len(buf) and struct.unpack_from("<Q", buf, off)[0] == DN_IS_QUEUE:
        fs = _flow_set(buf, off)
        sets.append(fs)
        off += FLOW_SET + fs["queues"] * QUEUE
    ok = off <= len(buf) and not any(buf[off:])
    return {"ok": ok, "pipes": pipes, "flow_sets": sets, "bytes": len(buf), "parsed": off}


def read_pipes() -> dict:
    s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)
    try:
        return parse_pipes(s.getsockopt(socket.IPPROTO_IP, IP_DUMMYNET_GET, 1 << 20))
    finally:
        s.close()


def _run(*cmd: str) -> list[str]:
    r = subprocess.run(list(cmd), capture_output=True, text=True)
    return [x for x in (r.stdout + r.stderr).splitlines() if x.strip()]


def sample() -> dict:
    out = {"time": time.time(), "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    try:
        out["dummynet"] = read_pipes()
    except OSError as e:
        out["dummynet"] = {"ok": False, "error": str(e), "pipes": []}
    out["pf_status"] = next(iter(_run("pfctl", "-s", "info")), "")
    out["anchor_rules"] = _run("pfctl", "-a", ANCHOR, "-s", "rules")
    out["anchor_dummynet"] = _run("pfctl", "-a", ANCHOR, "-s", "dummynet")
    out["dnctl_list"] = _run("dnctl", "list")
    return out


def _own(path: Path) -> None:
    if "SUDO_UID" in os.environ:
        os.chown(path, int(os.environ["SUDO_UID"]), int(os.environ["SUDO_GID"]))


def main(a: argparse.Namespace) -> int:
    if os.geteuid() != 0:
        sys.exit("run with sudo: reading dummynet and pf needs root")
    if a.once:
        s = sample()
        d = s["dummynet"]
        print(f"reader ok: {d.get('ok')}  ({d.get('parsed')} of {d.get('bytes')} bytes)")
        for p in d.get("pipes", []):
            print(f"  pipe {p['pipe']}: {p['delay_ms']} ms, bandwidth {p['bandwidth']}, plr {p['plr']}, "
                  f"{p['queues']} queue(s), {p['pkts']} packets, {p['drops']} drops")
        print("pf:", s["pf_status"])
        print("anchor dummynet:", *s["anchor_dummynet"], sep="\n  ")
        print(f"anchor rules: {len(s['anchor_rules'])} lines")
        print("dnctl list:", *s["dnctl_list"], sep="\n  ")
        return 0
    out, log = Path(a.out), Path(a.log) if a.log else None
    out.parent.mkdir(parents=True, exist_ok=True)
    last_text = None
    print(f"watching every {a.every:g} s → {out}", flush=True)
    while True:
        s = sample()
        tmp = out.with_suffix(".tmp")
        tmp.write_text(json.dumps(s, indent=1))
        _own(tmp)
        os.replace(tmp, out)
        if log:
            text = (s["pf_status"], s["anchor_rules"], s["anchor_dummynet"], s["dnctl_list"])
            row = {"at": s["at"], "time": s["time"], "dummynet": s["dummynet"],
                   **({"pf_status": text[0], "anchor_rules": text[1], "anchor_dummynet": text[2],
                       "dnctl_list": text[3]} if text != last_text else {"text": "unchanged"})}
            new = not log.exists()
            with log.open("a") as f:
                f.write(json.dumps(row) + "\n")
            if new:
                _own(log)
            last_text = text
        time.sleep(a.every)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--out", default="data/raw_c2/wan_status.json")
    p.add_argument("--log", default=None, help="append every sample here (JSON lines)")
    p.add_argument("--every", type=float, default=30.0)
    p.add_argument("--once", action="store_true", help="print one sample and exit")
    sys.exit(main(p.parse_args()))
