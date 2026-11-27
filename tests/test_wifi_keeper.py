"""The Pi's Wi-Fi keeper (scripts/pi_wifi_keeper.py): the chip's power save through brcmfmac's vendor
command, iw's outputs, when it acts, and the check of its log against a session's window."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.pi_wifi_keeper import (Wifi, check_log, dcmd_bytes, decide, install, parse_connected_s,
                                    parse_link, parse_power_save, parse_vendor_value, reconnected,
                                    vendor_args)

ROOT = Path(__file__).resolve().parent.parent

# The Pi's answer to GET_PM on Nov 25 (Debian 13, iw 6.9): BRCMF_NLATTR_DATA = 0, BRCMF_NLATTR_LEN = 4.
PI_REPLY = "vendor response: 08 00 02 00 00 00 00 00 06 00 01 00 04 00 00 00 \n\n"

LINK = """Connected to 12:34:56:78:9a:bc (on wlan0)
\tSSID: somewhere
\tfreq: 5180
\tRX: 123456 bytes (789 packets)
\tTX: 23456 bytes (321 packets)
\tsignal: -52 dBm
\trx bitrate: 433.3 MBit/s VHT-MCS 9 80MHz short GI VHT-NSS 1
\ttx bitrate: 390.0 MBit/s VHT-MCS 8 80MHz short GI VHT-NSS 1
"""
STATION = """Station 12:34:56:78:9a:bc (on wlan0)
\tinactive time:\t20 ms
\tsignal:  \t-52 dBm
\tconnected time:\t86123 seconds
"""


def test_the_get_pm_request_is_the_one_the_pi_answered():
    b = dcmd_bytes(85, False)
    assert len(b) == 24
    assert vendor_args("wlan0", b)[7:] == ("0x55 0x00 0x00 0x00 0x04 0x00 0x00 0x00 0x14 0x00 0x00 0x00 "
                                           "0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00").split()
    assert vendor_args("wlan0", b)[:7] == ["iw", "dev", "wlan0", "vendor", "recv", "0x001018", "0x1"]
    s = dcmd_bytes(86, True, 0)
    assert s[:4] == bytes([86, 0, 0, 0]) and s[12:16] == bytes([1, 0, 0, 0])


def test_the_chip_s_setting_is_read_from_the_data_attribute():
    assert parse_vendor_value(PI_REPLY) == 0
    assert parse_vendor_value(PI_REPLY.replace("02 00 00 00 00 00", "02 00 02 00 00 00")) == 2
    # the LEN attribute first, then DATA: still the DATA value
    assert parse_vendor_value("vendor response: 06 00 01 00 04 00 00 00 08 00 02 00 01 00 00 00 \n") == 1
    # 16 bytes per line, continued on the next line with the same prefix
    two = "vendor response: 06 00 01 00 04 00 00 00 08 00 02 00 01 00 00 00 \nvendor response: 00 \n"
    assert parse_vendor_value(two) == 1
    for bad in ("command failed: Operation not supported (-95)\n", "", "vendor response: 08 00 \n",
                "vendor response: zz\n"):
        assert parse_vendor_value(bad) is None


def test_iw_outputs():
    assert parse_power_save("Power save: off\n") == "off"
    assert parse_power_save("Power save: on\n") == "on"
    assert parse_power_save("command failed: No such device (-19)") is None
    link = parse_link(LINK)
    assert link == {"connected": True, "bssid": "12:34:56:78:9a:bc", "signal_dbm": -52, "tx_mbit": 390.0}
    assert parse_link("Not connected.\n") == {"connected": False, "bssid": None, "signal_dbm": None, "tx_mbit": None}
    assert parse_connected_s(STATION) == 86123
    assert parse_connected_s("") is None


def _s(**kw):
    s = {"connected": True, "bssid": "a", "connected_s": 100, "iw_ps": "off", "fw_pm": 0}
    s.update(kw)
    return s


def test_a_reconnect_is_a_new_bssid_a_connected_time_that_went_back_or_the_link_coming_back():
    assert not reconnected(_s(), None)
    assert not reconnected(_s(connected_s=130), _s())
    assert reconnected(_s(connected_s=5), _s())
    assert reconnected(_s(bssid="b"), _s())
    assert reconnected(_s(), _s(connected=False, bssid=None))
    assert not reconnected(_s(connected=False, bssid=None), _s())


def test_it_acts_only_when_the_chip_or_cfg80211_says_on_when_it_can_read_the_chip():
    assert decide(_s(), _s(connected_s=50), True) == ([], [])
    assert decide(_s(fw_pm=2), None, True) == (["fw_pm=2"], ["fw_set_pm0"])
    assert decide(_s(iw_ps="on", fw_pm=2), None, True) == (["iw_on", "fw_pm=2"], ["iw_off", "fw_set_pm0"])
    # a reconnect is logged by the caller, but with the chip readable it is not a reason to act
    assert decide(_s(connected_s=5), _s(), True) == ([], [])


def test_without_the_chip_a_reconnect_calls_for_on_then_off():
    assert decide(_s(fw_pm=None, connected_s=5), _s(fw_pm=None), False) == (["reconnected"], ["toggle"])
    assert decide(_s(fw_pm=None), _s(fw_pm=None), False) == ([], [])
    assert decide(_s(fw_pm=None, iw_ps="on", bssid="b"), _s(fw_pm=None), False) == (["iw_on"], ["iw_off"])


def test_the_state_never_carries_the_bssid_into_the_log(monkeypatch):
    from scripts import pi_wifi_keeper as k
    outs = {"link": LINK, "dump": STATION, "get": "Power save: off\n", "recv": PI_REPLY}

    def fake(self, args):
        key = "recv" if "vendor" in args else "dump" if "dump" in args else "get" if "get" in args else "link"
        return 0, outs[key]
    monkeypatch.setattr(Wifi, "_run", fake)
    state = Wifi("wlan0").state(True)
    assert state["fw_pm"] == 0 and state["iw_ps"] == "off" and state["connected_s"] == 86123
    line = json.dumps(k._public(state))
    assert "12:34:56" not in line and "somewhere" not in line


def _log(t0, n, every=30, start_at=None, **extra):
    recs = [{"t": (start_at if start_at is not None else t0) - 1, "event": "start", "every_s": every, "fw_read": True}]
    for i in range(n):
        recs.append({"t": t0 + i * every, "at": "x", "connected": True, "iw_ps": "off", "fw_pm": 0,
                     "reconnected": False, "reasons": [], "action": None})
    return recs


def test_a_clean_log_covering_the_window_passes():
    recs = _log(1000, 40)
    res = check_log(recs, 1010, 1900, 75)
    assert res["pass"] and res["coverage"]["ok"] and res["checks_in_window"] == 30 and res["fw_read"] is True


def test_a_re_disable_a_reconnect_or_a_lost_link_inside_the_window_fails_and_outside_does_not():
    for change, key in (({"action": ["fw_set_pm0"], "reasons": ["fw_pm=2"]}, "re_disables"),
                        ({"reconnected": True}, "reconnects"),
                        ({"connected": False}, "link_down")):
        recs = _log(1000, 40)
        recs[10].update(change)                       # t = 1270, inside
        res = check_log(recs, 1010, 1900, 75)
        assert not res["pass"] and len(res[key]) == 1, key
        recs = _log(1000, 40)
        recs[1].update(change)                        # t = 1000, before the window
        assert check_log(recs, 1010, 1900, 75)["pass"], key


def test_the_keeper_must_run_throughout_the_window():
    recs = _log(1000, 40)
    del recs[15:20]                                   # 1390 to 1510 missing: a 180 s gap
    res = check_log(recs, 1010, 1900, 75)
    assert not res["pass"] and res["coverage"]["gaps"][0]["s"] == 180.0
    late = _log(1100, 40)                             # first check 90 s after the window opens
    res = check_log(late, 1010, 1900, 75)
    assert not res["pass"] and not res["coverage"]["running_at_start"]
    short = _log(1000, 20)                            # last check at 1570
    res = check_log(short, 1010, 1900, 75)
    assert not res["pass"] and not res["coverage"]["running_at_end"]
    assert not check_log([], 1010, 1900, 75)["pass"]


def test_an_error_or_a_restart_inside_the_window_fails():
    recs = _log(1000, 40)
    recs.insert(12, {"t": 1300, "error": "OSError()"})
    assert len(check_log(recs, 1010, 1900, 75)["errors"]) == 1
    recs = _log(1000, 40)
    recs[12]["error"], recs[12]["fw_pm"] = "the chip's setting could not be read", None
    res = check_log(recs, 1010, 1900, 75)
    assert not res["pass"] and len(res["errors"]) == 1 and res["coverage"]["ok"]
    recs = _log(1000, 40)
    recs.insert(12, {"t": 1300, "event": "start", "every_s": 30, "fw_read": True})
    res = check_log(recs, 1010, 1900, 75)
    assert not res["pass"] and len(res["restarts"]) == 1


def _session(tmp_path, name, started, finished, cid="C2B2-pilot"):
    d = tmp_path / name
    d.mkdir()
    (d / "session_meta.json").write_text(json.dumps({"collection_id": cid, "started": started, "finished": finished}))
    return d


def test_the_check_reads_the_window_from_the_sessions_and_cuts_the_log(tmp_path):
    from datetime import datetime
    t0 = datetime.strptime("2026-11-27T20:00:00-0800", "%Y-%m-%dT%H:%M:%S%z").timestamp()
    a = _session(tmp_path, "lan", "2026-11-27T20:00:00-0800", "2026-11-27T20:10:00-0800")
    b = _session(tmp_path, "jl", "2026-11-27T20:00:00-0800", "2026-11-27T20:10:00-0800")
    log = tmp_path / "keeper.jsonl"
    recs = _log(t0 - 600, 60)                         # 19:50 to 20:19:30
    log.write_text("".join(json.dumps(r) + "\n" for r in recs))
    cmd = [sys.executable, str(ROOT / "scripts/pi_wifi_keeper.py"), "check", str(log), "--session", str(a), str(b),
           "--json", str(a / "wifi_keeper_check.json"), "--cut", str(a / "wifi_keeper.jsonl")]
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    assert p.returncode == 0, p.stdout + p.stderr
    assert p.stdout.strip().endswith("PASS")
    out = json.loads((a / "wifi_keeper_check.json").read_text())
    assert out["pass"] and out["collection_ids"] == ["C2B2-pilot"] and out["checks_in_window"] == 21
    cut = [json.loads(l) for l in (a / "wifi_keeper.jsonl").read_text().splitlines()]
    assert min(r["t"] for r in cut) >= t0 - 300 and max(r["t"] for r in cut) <= t0 + 900
    recs[30]["action"], recs[30]["reasons"] = ["fw_set_pm0"], ["fw_pm=2"]   # 20:05
    log.write_text("".join(json.dumps(r) + "\n" for r in recs))
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    assert p.returncode == 1 and p.stdout.strip().endswith("FAIL") and "re-disables" in p.stdout


def test_the_check_refuses_a_session_that_has_not_finished(tmp_path):
    a = _session(tmp_path, "lan", "2026-11-27T20:00:00-0800", None)
    log = tmp_path / "keeper.jsonl"
    log.write_text("")
    p = subprocess.run([sys.executable, str(ROOT / "scripts/pi_wifi_keeper.py"), "check", str(log),
                        "--session", str(a)], capture_output=True, text=True, cwd=ROOT)
    assert p.returncode != 0 and "finished" in p.stderr


def test_the_unit_names_this_file_and_the_log_and_restarts(capsys):
    import argparse
    install(argparse.Namespace(iface="wlan0", every=30.0, log="/var/log/a2a-wifi-keeper.jsonl", print_only=True))
    unit = capsys.readouterr().out
    assert "pi_wifi_keeper.py run --iface wlan0 --every 30.0 --log /var/log/a2a-wifi-keeper.jsonl" in unit
    assert "Restart=always" in unit and "WantedBy=multi-user.target" in unit


def test_a_log_cut_to_the_session_still_says_whether_the_chip_was_read():
    recs = _log(1000, 40)[1:]                         # the cut: no start line
    assert check_log(recs, 1010, 1900, 75)["fw_read"] is True
    for r in recs:
        r["fw_pm"] = None
    assert check_log(recs, 1010, 1900, 75)["fw_read"] is None
    assert check_log(_log(1000, 40), 1010, 1900, 75)["fw_read"] is True      # from the start line, as before
