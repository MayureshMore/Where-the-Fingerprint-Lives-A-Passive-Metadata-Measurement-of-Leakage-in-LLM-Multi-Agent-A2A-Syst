#!/usr/bin/env python3
"""Keep the Pi's Wi-Fi power save off, log every check, and check the log against a session.

`iw dev wlan0 get power_save` reports cfg80211's setting, not the chip's. In C2B1X (Nov 22) and
C2B1M (Nov 25) it said off while the chip dozed, and setting it off again does nothing, because
cfg80211 skips a setting equal to the one it holds; only on, then off, reached the chip, and that
wore off after 4 to 6.5 hours. NetworkManager's `wifi.powersave = 2` goes through the same path, so
it keeps NetworkManager from turning power save on at a reconnect but does not undo the chip's drift.

So the keeper reads the chip's own setting: brcmfmac passes dongle commands through its vendor
command (Broadcom OUI 0x001018, subcommand 1), and GET_PM (85) returns 0 (off), 1 (PM_MAX) or 2
(PM_FAST). When it is not 0, the keeper writes 0 with SET_PM (86), straight to the chip, without
turning power save on first. When the driver refuses the vendor command, it falls back to cfg80211:
`set power_save off` when iw says on, and on, then off, after a reconnect (the chip may rejoin with
power save on); such a log cannot show a silent doze, and the check says so.

Every check is one JSON line: iw's setting, the chip's, whether the link is up, the signal, the
link's connected time and whether it reconnected since the last check (BSSID or connected time),
and what the keeper had to do. The log holds no SSID, connection name or MAC address.

  run      on the Pi, as root (systemd, `install`): check every --every seconds
  install  on the Pi, as root: write the systemd unit for `run`, with this file's own path
  check    on the Mac: the log within a session's window (session_meta.json `started` to
           `finished`): the keeper ran throughout (no gap over --max-gap-s), and it never had to
           re-disable power save, saw no reconnect or lost link, and logged no error. PASS or FAIL;
           --cut writes the window's records (with --margin-s on each side) into the session.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import struct
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BROADCOM_OUI = "0x001018"
DCMD = "0x1"                 # BRCMF_VNDR_CMDS_DCMD
GET_PM, SET_PM = 85, 86      # BRCMF_C_GET_PM, BRCMF_C_SET_PM
NLATTR_DATA = 2              # BRCMF_NLATTR_DATA in the reply
UNIT = "a2a-wifi-keeper"
LOG = "/var/log/a2a-wifi-keeper.jsonl"
VERSION = 1


# ── the chip's setting through brcmfmac's vendor command ─────────────────────

def dcmd_bytes(cmd: int, set_: bool, value: int = 0) -> bytes:
    """struct brcmf_vndr_dcmd_hdr {cmd, len, offset, set, magic}, then one 32-bit value."""
    return struct.pack("<IiIII", cmd, 4, 20, int(set_), 0) + struct.pack("<I", value)


def vendor_args(iface: str, payload: bytes) -> list[str]:
    return ["iw", "dev", iface, "vendor", "recv", BROADCOM_OUI, DCMD, *(f"0x{b:02x}" for b in payload)]


def parse_vendor_value(text: str) -> int | None:
    """The 32-bit value in BRCMF_NLATTR_DATA of iw's `vendor response:` hex dump, or None."""
    data: list[int] = []
    for line in text.splitlines():
        if line.startswith("vendor response:"):
            try:
                data += [int(t, 16) for t in line.split(":", 1)[1].split()]
            except ValueError:
                return None
    i = 0
    while i + 4 <= len(data):
        length, kind = data[i] | data[i + 1] << 8, data[i + 2] | data[i + 3] << 8
        if length < 4:
            return None
        if kind == NLATTR_DATA and length >= 8 and i + 8 <= len(data):
            v = data[i + 4:i + 8]
            return v[0] | v[1] << 8 | v[2] << 16 | v[3] << 24
        i += (length + 3) & ~3
    return None


# ── iw's view ────────────────────────────────────────────────────────────────

def parse_power_save(text: str) -> str | None:
    m = re.search(r"Power save:\s*(on|off)", text)
    return m.group(1) if m else None


def parse_link(text: str) -> dict:
    """`iw dev IFACE link`: connected, the BSSID (kept in memory, never logged), signal, bitrate."""
    m = re.search(r"Connected to ([0-9a-f:]{17})", text)
    sig = re.search(r"signal:\s*(-?\d+)\s*dBm", text)
    rate = re.search(r"tx bitrate:\s*([\d.]+)\s*MBit/s", text)
    return {"connected": bool(m), "bssid": m.group(1) if m else None,
            "signal_dbm": int(sig.group(1)) if sig else None,
            "tx_mbit": float(rate.group(1)) if rate else None}


def parse_connected_s(text: str) -> int | None:
    """`iw dev IFACE station dump`: the access point's `connected time`."""
    m = re.search(r"connected time:\s*(\d+)\s*seconds", text)
    return int(m.group(1)) if m else None


def reconnected(state: dict, prev: dict | None) -> bool:
    """A new association since the last check: a new BSSID, or a connected time that went back."""
    if prev is None or not state["connected"]:
        return False
    if not prev["connected"] or state["bssid"] != prev["bssid"]:
        return True
    a, b = state.get("connected_s"), prev.get("connected_s")
    return a is not None and b is not None and a < b


def decide(state: dict, prev: dict | None, fw_read: bool) -> tuple[list[str], list[str]]:
    """Reasons to act and the actions, in order. With the chip's setting readable, only a chip or
    cfg80211 setting that is on calls for action; without it, a reconnect does too (on, then off)."""
    reasons, actions = [], []
    if state.get("iw_ps") == "on":
        reasons.append("iw_on")
        actions.append("iw_off")
    if state.get("fw_pm") not in (None, 0):
        reasons.append(f"fw_pm={state['fw_pm']}")
        actions.append("fw_set_pm0")
    if not fw_read and reconnected(state, prev) and state.get("iw_ps") != "on":
        reasons.append("reconnected")
        actions.append("toggle")
    return reasons, actions


class Wifi:
    """The commands, run as root on the Pi."""

    def __init__(self, iface: str):
        self.iface = iface

    def _run(self, args: list[str]) -> tuple[int, str]:
        try:
            p = subprocess.run(args, capture_output=True, text=True, timeout=10)
            return p.returncode, p.stdout + p.stderr
        except (OSError, subprocess.TimeoutExpired) as e:
            return -1, str(e)

    def fw_pm(self) -> int | None:
        rc, out = self._run(vendor_args(self.iface, dcmd_bytes(GET_PM, False)))
        return parse_vendor_value(out) if rc == 0 else None

    def fw_set_pm0(self) -> bool:
        rc, _ = self._run(vendor_args(self.iface, dcmd_bytes(SET_PM, True, 0)))
        return rc == 0

    def iw_ps(self) -> str | None:
        return parse_power_save(self._run(["iw", "dev", self.iface, "get", "power_save"])[1])

    def set_ps(self, on: bool) -> bool:
        return self._run(["iw", "dev", self.iface, "set", "power_save", "on" if on else "off"])[0] == 0

    def state(self, fw_read: bool) -> dict:
        s = parse_link(self._run(["iw", "dev", self.iface, "link"])[1])
        s["connected_s"] = parse_connected_s(self._run(["iw", "dev", self.iface, "station", "dump"])[1])
        s["iw_ps"] = self.iw_ps()
        s["fw_pm"] = self.fw_pm() if fw_read else None
        return s


def _now() -> dict:
    t = time.time()
    return {"t": round(t, 3), "at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(t))}


def _public(state: dict) -> dict:
    return {k: v for k, v in state.items() if k != "bssid"}


def act(wifi: Wifi, actions: list[str]) -> dict:
    done = {}
    for a in actions:
        if a == "iw_off":
            done[a] = wifi.set_ps(False)
        elif a == "fw_set_pm0":
            done[a] = wifi.fw_set_pm0()
        elif a == "toggle":
            done[a] = wifi.set_ps(True) and wifi.set_ps(False)
    return done


def run(a: argparse.Namespace) -> None:
    if os.geteuid() != 0:
        sys.exit("run needs root (iw set, iw vendor)")
    wifi, log = Wifi(a.iface), Path(a.log)
    log.parent.mkdir(parents=True, exist_ok=True)

    def write(rec: dict) -> None:
        with log.open("a") as f:
            f.write(json.dumps(rec) + "\n")

    fw_read = wifi.fw_pm() is not None
    start = {**_now(), "event": "start", "version": VERSION, "iface": a.iface, "every_s": a.every,
             "fw_read": fw_read, "pid": os.getpid()}
    # At start, with no reading of the chip, reset it once (on, then off), as by hand before a session.
    if not fw_read:
        start["start_toggle"] = wifi.set_ps(True) and wifi.set_ps(False)
    write(start)
    prev = None
    while True:
        try:
            state = wifi.state(fw_read)
            reasons, actions = decide(state, prev, fw_read)
            rec = {**_now(), **_public(state), "reconnected": reconnected(state, prev),
                   "reasons": reasons, "action": actions or None}
            if fw_read and state["fw_pm"] is None:
                rec["error"] = "the chip's setting could not be read"
            if actions:
                rec["done"] = act(wifi, actions)
                after = wifi.state(fw_read)
                rec["after"] = {"iw_ps": after["iw_ps"], "fw_pm": after["fw_pm"]}
            write(rec)
            prev = state
        except Exception as e:                              # keep running; the check counts errors
            write({**_now(), "error": repr(e)})
        time.sleep(a.every)


def install(a: argparse.Namespace) -> None:
    script = Path(__file__).resolve()
    unit = f"""[Unit]
Description=a2a testbed: keep {a.iface} power save off and log each check ({script.name})
After=network.target

[Service]
ExecStart={sys.executable} {script} run --iface {a.iface} --every {a.every} --log {a.log}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
    path = Path(f"/etc/systemd/system/{UNIT}.service")
    if a.print_only:
        print(unit, end="")
        return
    path.write_text(unit)
    print(f"wrote {path}:\n{unit}", end="")


# ── the check against a session (Mac) ────────────────────────────────────────

def _ts(s: str) -> float:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z").timestamp()


def window(sessions: list[Path]) -> tuple[float, float, list[str]]:
    starts, ends, ids = [], [], []
    for d in sessions:
        m = json.loads((d / "session_meta.json").read_text())
        if not m.get("finished"):
            raise SystemExit(f"{d}/session_meta.json has no `finished`: check after the collection ends")
        starts.append(_ts(m["started"]))
        ends.append(_ts(m["finished"]))
        ids.append(m.get("collection_id"))
    return min(starts), max(ends), sorted(set(i for i in ids if i))


def check_log(records: list[dict], t0: float, t1: float, max_gap_s: float) -> dict:
    """Coverage of [t0, t1] by the keeper's checks, and every event inside it."""
    inside = [r for r in records if t0 <= r["t"] <= t1]
    checks = sorted(r["t"] for r in records if "event" not in r and "error" not in r)
    before = [t for t in checks if t <= t0]
    after = [t for t in checks if t >= t1]
    span = ([before[-1]] if before else []) + [t for t in checks if t0 < t < t1] + ([after[0]] if after else [])
    gaps = [{"from": a, "to": b, "s": round(b - a, 1)} for a, b in zip(span, span[1:]) if b - a > max_gap_s]
    starts_ok = bool(before) and t0 - before[-1] <= max_gap_s
    ends_ok = bool(after) and after[0] - t1 <= max_gap_s
    if not span:
        gaps = [{"from": t0, "to": t1, "s": round(t1 - t0, 1)}]

    def pick(pred):
        return [{"at": r.get("at"), **{k: r[k] for k in ("reasons", "action", "done", "after", "error",
                                                         "fw_pm", "iw_ps", "signal_dbm", "connected_s")
                                       if k in r}} for r in inside if pred(r)]

    keepers = [r for r in records if r.get("event") == "start" and r["t"] <= t1]
    fw_read = keepers[-1].get("fw_read") if keepers else None
    out = {
        "checks_in_window": sum(1 for r in inside if "event" not in r and "error" not in r),
        "coverage": {"ok": starts_ok and ends_ok and not gaps, "running_at_start": starts_ok,
                     "running_at_end": ends_ok, "gaps": gaps, "max_gap_s": max_gap_s},
        "re_disables": pick(lambda r: bool(r.get("action"))),
        "reconnects": pick(lambda r: r.get("reconnected") is True),
        "link_down": pick(lambda r: r.get("connected") is False),
        "errors": pick(lambda r: "error" in r),
        "restarts": pick(lambda r: r.get("event") == "start"),
        "fw_read": fw_read,
    }
    out["pass"] = (out["coverage"]["ok"] and not out["re_disables"] and not out["reconnects"]
                   and not out["link_down"] and not out["errors"] and not out["restarts"])
    return out


def _git() -> dict:
    def g(*args):
        return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()
    return {"git_commit": g("rev-parse", "HEAD") or None,
            "git_dirty": bool(g("status", "--porcelain", "--", ".", ":(exclude)data"))}


def check(a: argparse.Namespace) -> None:
    sessions = [Path(d) for d in a.session]
    t0, t1, ids = window(sessions)
    records = [json.loads(l) for l in Path(a.log).read_text().splitlines() if l.strip()]
    every = next((r["every_s"] for r in reversed(records) if r.get("event") == "start" and r["t"] <= t1), 30)
    max_gap = a.max_gap_s if a.max_gap_s is not None else 2.5 * every
    res = check_log(records, t0, t1, max_gap)
    fmt = lambda t: time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(t))
    out = {"collection_ids": ids, "sessions": [str(d) for d in sessions],
           "window": {"from": fmt(t0), "to": fmt(t1)}, "every_s": every, **res,
           "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **_git()}
    c = res["coverage"]
    print(f"window {out['window']['from']} to {out['window']['to']} ({', '.join(ids)}): "
          f"{res['checks_in_window']} checks every {every} s")
    print(f"  keeper ran throughout   {'ok' if c['ok'] else 'FAIL'}"
          + ("" if c["ok"] else f" (at start {c['running_at_start']}, at end {c['running_at_end']}, "
                                f"{len(c['gaps'])} gaps over {max_gap:g} s)"))
    for k, label in (("re_disables", "re-disables"), ("reconnects", "reconnects"), ("link_down", "link down"),
                     ("errors", "errors"), ("restarts", "keeper restarts")):
        print(f"  {label:<22}  {len(res[k])}  {'ok' if not res[k] else 'FAIL'}")
        for e in res[k][:5]:
            print(f"      {e}")
    if res["fw_read"] is False:
        print("  note: the keeper could not read the chip's setting (vendor command refused): "
              "a doze with iw saying off would not show")
    print("PASS" if res["pass"] else "FAIL")
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=2))
    if a.cut:
        lo, hi = t0 - a.margin_s, t1 + a.margin_s
        Path(a.cut).write_text("".join(json.dumps(r) + "\n" for r in records if lo <= r["t"] <= hi))
    sys.exit(0 if res["pass"] else 1)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="on the Pi, as root: check every --every seconds")
    i = sub.add_parser("install", help="on the Pi, as root: write the systemd unit")
    for q in (r, i):
        q.add_argument("--iface", default="wlan0")
        q.add_argument("--every", type=float, default=30.0)
        q.add_argument("--log", default=LOG)
    i.add_argument("--print-only", action="store_true", dest="print_only")
    c = sub.add_parser("check", help="on the Mac: the log within a session's window")
    c.add_argument("log", help="the keeper's log, copied from the Pi")
    c.add_argument("--session", nargs="+", required=True, help="session folders with session_meta.json")
    c.add_argument("--max-gap-s", type=float, default=None, dest="max_gap_s", help="default 2.5 x every")
    c.add_argument("--json")
    c.add_argument("--cut", help="write the window's records here (the session's copy)")
    c.add_argument("--margin-s", type=float, default=300.0, dest="margin_s")
    a = p.parse_args()
    {"run": run, "install": install, "check": check}[a.cmd](a)


if __name__ == "__main__":
    main()
