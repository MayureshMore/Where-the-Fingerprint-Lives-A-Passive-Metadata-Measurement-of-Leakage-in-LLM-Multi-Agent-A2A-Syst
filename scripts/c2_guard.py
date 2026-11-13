#!/usr/bin/env python3
"""
Guard C2's emulated WAN during the collection. Runs beside scripts/collect_session.py; once at the
start and then every --every traces (all arms together) it checks:

  1. pipes      both dummynet pipes exist with the measured one-way delay (6 ms), no bandwidth
                limit and no loss rate, as scripts/wan_watch.py (root) last read them from the
                kernel; that reading must be at most --max-age seconds old
  2. rules      pf is enabled, and anchor com.apple/c2-wan sends the Pi's packets to the cloud
                alias into pipe 1 and the alias's packets to the Pi into pipe 2
  3. port lock  every C2 port on the Mac's two addresses has a pass rule for the Pi before a block
                rule for any other host
  4. connect    in the traces since the last check, the Pi's TCP connect time to the cloud alias
                has a median within ±--tolerance of the target round trip (22.6 ms), as the Pi's
                own timer would read it: SYN to the Pi's ACK of the SYN-ACK at the capture, plus
                --pi-overhead-ms, what the Pi's timer adds (the WAN check's probes, timed on the
                Pi and captured on the Mac: median Pi time minus median capture time); the
                capture's SYN to SYN-ACK, the two dummynet delays, has a median within
                ±--tolerance of 12 ms and no handshake under its lower bound (a missing pipe halves
                it); the ticket service on the Mac's own address stays undelayed

If any check fails, it stops the collection (SIGINT to collect_session.py, which --resume
continues), marks every trace since the last good check as suspect, and exits 2. The record is
--json: every check, the dummynet drop counters, and the suspect traces. A trace is complete when
its sidecar JSON is written; traces are ordered by that time.

    python scripts/c2_guard.py --collector-pid PID --status data/raw_c2/wan_status.json \
        --json data/raw_c2/wan_guard.json data/raw_c2 data/raw_c2_pad data/raw_c2_padmax
    python scripts/c2_guard.py --replay data/raw_c2_pilot ...       # check 4 only, on finished traces
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from features.kfp import tcp_records  # noqa: E402

TRACE = re.compile(r"_edge_cloud_[0-9a-f]{6}$")
CLOUD_OFFSETS, TICKET_OFFSET = (1, 2), 5          # agents/edge.py: CLOUD_PORTS, TICKET_PORT
SYN, ACK = 0x02, 0x10


def traces(dirs: list[Path]) -> list[Path]:
    """Complete traces (pcap and sidecar), oldest sidecar first."""
    out = [j for d in dirs for j in d.glob("*.json") if TRACE.search(j.stem) and j.with_suffix(".pcap").exists()]
    return sorted(out, key=lambda j: (j.stat().st_mtime, str(j)))


def handshakes(pcap: Path, cloud: set[int], ticket: set[int]) -> dict[str, list[tuple[float, float]]]:
    """Per server kind: (SYN → SYN-ACK, SYN → the Pi's ACK) in ms, at the capture."""
    syn, synack, out = {}, {}, {"cloud": [], "ticket": []}
    for ts, sp, dp, _, _, fl, _ in tcp_records(pcap):
        if fl & (SYN | ACK) == SYN and (dp in cloud or dp in ticket):
            syn[(sp, dp)] = ts
            synack.pop((sp, dp), None)
        elif fl & (SYN | ACK) == SYN | ACK and (dp, sp) in syn:
            synack[(dp, sp)] = ts
        elif fl & (SYN | ACK) == ACK and (sp, dp) in synack:
            t0 = syn.pop((sp, dp))
            kind = "cloud" if dp in cloud else "ticket"
            out[kind].append(((synack.pop((sp, dp)) - t0) * 1000, (ts - t0) * 1000))
    return out


class Guard:
    def __init__(self, a: argparse.Namespace):
        self.a = a
        t = json.loads(Path(a.target).read_text())
        e = t["emulation"]
        self.pi, self.cloud_ip, self.mac, self.iface = e["pi"], e["cloud"], e["mac"], e["iface"]
        self.one_way, self.rtt, self.delay = float(e["one_way_ms"]), float(t["target_rtt_ms"]), float(t["delay_ms"])
        self.cloud = {b + o for b in e["bases"] for o in CLOUD_OFFSETS}
        self.ticket = {b + TICKET_OFFSET for b in e["bases"]}
        self.lock_ports = sorted(self.cloud | self.ticket)
        self.dirs = [Path(d) for d in a.dirs]
        self.record = {"paper": "P2", "collection_id": "C2", "every": a.every, "tolerance": a.tolerance,
                       "target": {"target_rtt_ms": self.rtt, "dummynet_ms": self.delay, "one_way_ms": self.one_way},
                       "pi_overhead_ms": a.pi_overhead_ms,
                       "calibration": json.loads(a.calibration) if a.calibration else None,
                       "guard_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "checks": [], "suspect": [],
                       "stopped": False, "git_commit": _git("rev-parse", "HEAD")}
        self.covered: set[str] = set()           # traces a passing check covered
        self.drops: dict[int, int] = {}

    # ---- checks 1-3: what wan_watch.py read as root
    def status(self) -> list[dict]:
        a, out = self.a, []
        try:
            s = json.loads(Path(a.status).read_text())
        except (OSError, ValueError) as e:
            return [{"check": "1. pipes", "ok": False, "detail": f"no reading from wan_watch.py ({e})"}]
        age = time.time() - s.get("time", 0)
        d = s.get("dummynet", {})
        pipes = {p["pipe"]: p for p in d.get("pipes", [])}
        want = int(round(self.one_way))
        bad = [f"pipe {n}: " + ("missing" if n not in pipes else
                                f"{pipes[n]['delay_ms']} ms, bandwidth {pipes[n]['bandwidth']}, plr {pipes[n]['plr']}")
               for n in (1, 2) if n not in pipes or (pipes[n]["delay_ms"], pipes[n]["bandwidth"], pipes[n]["plr"]) != (want, 0, 0)]
        drops = {n: pipes[n].get("drops", 0) for n in pipes}
        new_drops = {n: v - self.drops.get(n, 0) for n, v in drops.items() if v != self.drops.get(n, 0)}
        self.drops = drops
        out.append({"check": "1. pipes", "ok": d.get("ok", False) and not bad and age <= a.max_age,
                    "detail": (f"reading {age:.0f} s old; " if age > a.max_age else "") +
                              ("; ".join(bad) or f"pipes 1 and 2 at {want} ms") +
                              ("" if d.get("ok") else f"; reader: {d.get('error', 'records do not walk to the end')}"),
                    "packets": {n: p.get("pkts") for n, p in pipes.items()}, "drops": drops, "new_drops": new_drops,
                    "dnctl_list_pipes": [x.split(":")[0] for x in s.get("dnctl_list", []) if re.match(r"^\d{5}:", x)],
                    "reading_at": s.get("at")})
        ins = any(re.search(rf"dummynet in\b.*\bon {self.iface}\b.*from {re.escape(self.pi)} to {re.escape(self.cloud_ip)}\b.*\bpipe 1\b", x)
                  for x in s.get("anchor_dummynet", []))
        outs = any(re.search(rf"dummynet out\b.*\bon {self.iface}\b.*from {re.escape(self.cloud_ip)} to {re.escape(self.pi)}\b.*\bpipe 2\b", x)
                   for x in s.get("anchor_dummynet", []))
        enabled = "Enabled" in s.get("pf_status", "")
        out.append({"check": "2. rules", "ok": ins and outs and enabled,
                    "detail": f"pf {'enabled' if enabled else 'NOT enabled'}; Pi → alias into pipe 1: {ins}; "
                              f"alias → Pi into pipe 2: {outs}"})
        missing = self.port_lock(s.get("anchor_rules", []))
        out.append({"check": "3. port lock", "ok": not missing,
                    "detail": f"pass from {self.pi}, then block, for {len(self.lock_ports)} ports on {self.mac} and "
                              f"{self.cloud_ip}" + (f"; missing: {', '.join(missing[:6])}" if missing else "")})
        return out

    def port_lock(self, rules: list[str]) -> list[str]:
        first = {}                                   # (action, dst, port) → first rule index
        for i, line in enumerate(rules):
            m = re.match(r"^(pass|block)\b.*\bin\b.*\bproto tcp\b.*\bfrom (\S+|\{[^}]*\}) to (\{[^}]*\}|\S+)"
                         r"(?: port (?:= )?(\{[^}]*\}|\d+))?", line)
            if not m:
                continue
            action, src, dst, ports = m.groups()
            if (action == "pass") != (src.strip("{} ") == self.pi):
                continue                             # a pass must name the Pi; a block, any host
            if action == "block" and src != "any":
                continue
            for d in re.findall(r"\d+\.\d+\.\d+\.\d+", dst):
                for p in re.findall(r"\d+", ports or ""):
                    first.setdefault((action, d, int(p)), i)
        missing = []
        for d in (self.mac, self.cloud_ip):
            for p in self.lock_ports:
                ip, ib = first.get(("pass", d, p)), first.get(("block", d, p))
                if ip is None or ib is None or ip > ib:
                    missing.append(f"{d}:{p}")
        return missing

    # ---- check 4: the traces themselves
    def connect(self, window: list[Path]) -> dict:
        tol = self.a.tolerance
        lo_c, hi_c = self.rtt * (1 - tol), self.rtt * (1 + tol)
        lo_d, hi_d = self.delay * (1 - tol), self.delay * (1 + tol)
        small = max(2.0, 0.2 * self.rtt)
        cloud, ticket, low = [], [], []
        for j in window:
            hs = handshakes(j.with_suffix(".pcap"), self.cloud, self.ticket)
            cloud += hs["cloud"]
            ticket += hs["ticket"]
            if any(d < lo_d for d, _ in hs["cloud"]):
                low.append(j.stem)
        med = lambda xs: statistics.median(xs) if xs else None          # noqa: E731
        c_cap, c_dn, t_dn = med([c for _, c in cloud]), med([d for d, _ in cloud]), med([d for d, _ in ticket])
        c_conn = None if c_cap is None else c_cap + self.a.pi_overhead_ms
        ok = (c_conn is not None and lo_c <= c_conn <= hi_c and lo_d <= c_dn <= hi_d and not low
              and (t_dn is None or t_dn < small))
        fmt = lambda v: "—" if v is None else f"{v:.1f} ms"              # noqa: E731
        return {"check": "4. connect", "ok": ok, "traces": len(window), "handshakes": len(cloud),
                "pi_connect_median_ms": c_conn, "capture_connect_median_ms": c_cap,
                "dummynet_median_ms": c_dn, "ticket_median_ms": t_dn,
                "min_dummynet_ms": min((d for d, _ in cloud), default=None), "under_bound": low,
                "detail": f"Pi → alias connect {fmt(c_conn)} ({fmt(c_cap)} at the capture + "
                          f"{self.a.pi_overhead_ms:.1f}; target {self.rtt:.1f} ±{tol:.0%}); SYN → SYN-ACK "
                          f"{fmt(c_dn)} ({self.delay:g} ±{tol:.0%}), {len(low)} trace(s) under {lo_d:.1f} ms; "
                          f"ticket {fmt(t_dn)} (under {small:.1f}); {len(cloud)} handshakes in {len(window)} traces"}

    def check(self, window: list[Path], with_status: bool = True) -> bool:
        rows = (self.status() if with_status else []) + ([self.connect(window)] if window else [])
        ok = all(r["ok"] for r in rows)
        self.record["checks"].append({"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "ok": ok,
                                      "traces_done": len(self.covered) + len(window),
                                      "window": [window[0].stem, window[-1].stem] if window else None, "rows": rows})
        for r in rows:
            print(f"[{time.strftime('%H:%M:%S')}] {r['check']:13s} {'ok  ' if r['ok'] else 'FAIL'} {r['detail']}", flush=True)
        if ok:
            self.covered |= {str(j) for j in window}
        return ok

    def save(self) -> None:
        if self.a.json:
            p = Path(self.a.json)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.record, indent=1))
            os.replace(tmp, p)

    def stop_collector(self, why: str) -> None:
        """SIGINT to the collector and its children, so collect_session.py cleans up; a job a script
        started with & ignores SIGINT, so after --grace seconds SIGTERM to every process it started
        (tcpdump included), then SIGKILL to what is left."""
        self.record.update(stopped=True, stop_reason=why, stopped_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        pid, signals = self.a.collector_pid, []
        if pid:
            tree = _tree(pid)
            for sig, wait in ((signal.SIGINT, self.a.grace), (signal.SIGTERM, 15), (signal.SIGKILL, 5)):
                left = [p for p in [pid, *tree] if _alive(p)]
                if not left:
                    break
                for p in reversed(left) if sig != signal.SIGINT else left:   # children first, then the collector
                    try:
                        os.kill(p, sig)
                    except ProcessLookupError:
                        pass
                signals.append(sig.name)
                for _ in range(int(wait)):
                    if not any(_alive(p) for p in [pid, *tree]):
                        break
                    time.sleep(1)
            self.record["stop_signals"] = signals
            self.record["still_running"] = [p for p in [pid, *tree] if _alive(p)]
        self.record["incomplete_pcaps"] = sorted(p.name for d in self.dirs for p in d.glob("*.pcap")
                                                 if TRACE.search(p.stem) and not p.with_suffix(".json").exists())
        print(f"[{time.strftime('%H:%M:%S')}] GUARD FAIL: {why}; collection stopped ({', '.join(signals) or 'no pid'}"
              f"{'; still running: ' + str(self.record.get('still_running')) if self.record.get('still_running') else ''})",
              flush=True)

    def run(self) -> int:
        stopping = []
        signal.signal(signal.SIGTERM, lambda *_: stopping.append(1))
        alive = lambda: self.a.collector_pid is None or _alive(self.a.collector_pid)   # noqa: E731
        if not self.check([]):                        # before the first trace
            self.stop_collector("WAN emulation not as measured at the start")
            self.save()
            return 2
        self.save()
        while True:
            done = traces(self.dirs)
            new = [j for j in done if str(j) not in self.covered]
            final = bool(stopping) or not alive()
            if len(new) >= self.a.every or (final and new):
                window = new if final else new[: self.a.every]
                if not self.check(window):
                    self.record["suspect"] = [j.stem for j in traces(self.dirs) if str(j) not in self.covered]
                    self.stop_collector(f"check failed after {len(self.covered)} good traces")
                    self.save()
                    print(f"suspect traces: {len(self.record['suspect'])}", flush=True)
                    return 2
                self.save()
                continue
            if final:
                self.record["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                self.record["traces_checked"] = len(self.covered)
                self.save()
                print(f"[{time.strftime('%H:%M:%S')}] guard done: {len(self.covered)} traces, "
                      f"{len(self.record['checks'])} checks, all ok", flush=True)
                return 0
            for _ in range(int(self.a.poll)):
                if stopping or not alive():
                    break
                time.sleep(1)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    out = _git_free_run("ps", "-o", "stat=", "-p", str(pid)).strip()
    return bool(out) and not out.startswith("Z")


def _tree(pid: int) -> list[int]:
    """Every process below pid."""
    out, todo = [], [pid]
    while todo:
        kids = [int(k) for k in _git_free_run("pgrep", "-P", str(todo.pop())).split()]
        out += kids
        todo += kids
    return out


def _git_free_run(*cmd: str) -> str:
    return subprocess.run(list(cmd), capture_output=True, text=True).stdout


def _git(*args: str) -> str | None:
    return _git_free_run("git", *args).strip() or None


def replay(a: argparse.Namespace) -> int:
    """Check 4 on finished traces, in windows of --every (a pilot, or C2 afterwards)."""
    g = Guard(a)
    done = traces(g.dirs)
    ok = True
    for i in range(0, len(done), a.every):
        ok &= g.check(done[i: i + a.every], with_status=False)
    g.save()
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("dirs", nargs="+", help="the arms' output directories")
    p.add_argument("--collector-pid", type=int, default=None, dest="collector_pid")
    p.add_argument("--status", default="data/raw_c2/wan_status.json", help="scripts/wan_watch.py --out")
    p.add_argument("--target", default="data/results/c2_wan_emulation.json")
    p.add_argument("--every", type=int, default=50)
    p.add_argument("--tolerance", type=float, default=0.20)
    p.add_argument("--max-age", type=float, default=120.0, dest="max_age")
    p.add_argument("--poll", type=float, default=10.0)
    p.add_argument("--grace", type=float, default=60.0, help="seconds between SIGINT and SIGTERM")
    p.add_argument("--pi-overhead-ms", type=float, default=0.0, dest="pi_overhead_ms",
                   help="what the Pi's connect timer adds to the capture's SYN → ACK")
    p.add_argument("--calibration", default=None, help="JSON: where --pi-overhead-ms came from")
    p.add_argument("--json", default=None)
    p.add_argument("--replay", action="store_true", help="check 4 only, on finished traces; no collector")
    a = p.parse_args()
    sys.exit(replay(a) if a.replay else Guard(a).run())
