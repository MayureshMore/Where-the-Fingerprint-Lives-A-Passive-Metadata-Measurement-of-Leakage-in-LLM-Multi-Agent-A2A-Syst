#!/usr/bin/env python3
"""
Build the paper 2 data release (Zenodo 10.5281/zenodo.24238559, DATA.md) from a populated data/.

    c2-raw-pcaps-headers-only.zip         data/raw_c2, raw_c2_pad, raw_c2_padmax: 1,000 captures per
                                          arm, every packet cut to its headers, Ethernet addresses
                                          replaced by placeholders; the label sidecars and the run's
                                          check files
    c2-features.zip                       data/features_c2/<arm>_<view>.npz: the 195 trace features
                                          and the first-request size a2a-leakcheck computes at each
                                          observer view (v1 building network, v2 upstream), with the
                                          labels; extracted from the released captures
    tlscontrol-raw-pcaps-headers-only.zip data/raw_tlspair_tls, raw_tlspair_clear (loopback, headers
                                          only): the TLS control behind paper 2's D1 numbers
    tlscontrol-features-own-dedup.zip     data/processed_tlspair_{tls,clear}_own_dedup (own connections, each
                                          payload byte once: scripts/extract_features.py --dedup)
    SHA256SUMS.txt, manifest.json         checksums; what was checked, cut and left out

With --release round2, the new version's files instead (round 2's collections, docs/ROUND2_SESSIONS.md):
    c2b1-raw-pcaps-headers-only.zip       data/raw_c2b1_padmax, raw_c2b1_shaped (500 each) and the shaping
                                          agents' reply log data/raw_c2b1_replies (sizes and times, no text)
    c2b1x-raw-pcaps-headers-only.zip      data/raw_c2b1x_shaped (2,000) and data/raw_c2b1x_replies
    c2b3-raw-pcaps-headers-only.zip       data/raw_c2b3_lan (1,000)
    round2-features.zip                   data/features_round2/<collection>_<arm>_<view>.npz
    round2-SHA256SUMS.txt, round2-manifest.json
The same changes and checks as below; every reply-log record must lie in its collection's window.

Changes from data/ (recorded in manifest.json and DATA.md):
  - every pcap is stripped to its headers (scripts/strip_payload.py); timestamps and on-wire
    lengths are kept, so the features do not change (checked below);
  - Ethernet addresses: the C2 captures were taken on the Mac's Wi-Fi interface and hold the real
    hardware addresses of the Mac and of the Pi; each is replaced by a placeholder (02:00:00:00:00:NN);
  - data/raw_c2/wan_watch.jsonl (the WAN watcher's log) kept running after the collection: only the
    records from the collection window (session_meta started/finished, one second either side)
    are released; the full log stays out;
  - data/raw_c2/wan_status.json (the watcher's last state, written after the collection) is left out.

Checks on the staged copy, before anything is zipped (any failure stops the build):
  - every pcap: snaplen ≤ 96 in the file header and every stored packet ≤ 96 bytes; no payload byte
    left; every packet IPv4 between hosts its sidecar names (C2: the edge host and the agent
    endpoints, i.e. 10.0.0.171, 10.0.0.228 and 172.30.0.100; TLS control: 127.0.0.1); no unicast
    Ethernet address other than a placeholder; no original address anywhere in any released file,
    as bytes or as text;
  - no released file (nor manifest.json) contains the packager's home directory path;
  - every pcap has its sidecar; 1,000 captures per C2 arm;
  - the C2 features from the released captures equal those from the captures in data/.

Usage (never overwrites: OUT must not exist):
    python scripts/package_paper2_data.py --out dist/paper2
    python scripts/package_paper2_data.py --out dist/paper2 --no-tls-control
    python scripts/package_paper2_data.py --release round2 --out dist/paper2_round2
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from a2a_leakcheck.collect import read_trace  # noqa: E402
from a2a_leakcheck.extract import extract  # noqa: E402
from features.names import FLAT_FEATURE_NAMES  # noqa: E402
from scripts.strip_payload import _MAGICS, MacPlaceholders, payload_bytes, real_macs, strip_file  # noqa: E402

C2_SETS = ("raw_c2", "raw_c2_pad", "raw_c2_padmax")
C2_ARMS = {"raw_c2": "lan", "raw_c2_pad": "lan_pad", "raw_c2_padmax": "lan_padmax"}
C2_VIEWS = ("v1", "v2")
C2_PER_ARM = 1000
C2_LABELS = ("task_type", "escalated", "cloud_role", "audit_null", "prompt_group")
TLS_RAW = ("raw_tlspair_tls", "raw_tlspair_clear")
TLS_FEATURES = ("processed_tlspair_tls_own_dedup", "processed_tlspair_clear_own_dedup")
ZIP_TIME = (1980, 1, 1, 0, 0, 0)          # fixed, so a rebuild of the same files gives the same checksum
LEFT_OUT = {"raw_c2": {"wan_status.json": "the WAN watcher's last state, written after the collection"}}
CUT = {"raw_c2": "wan_watch.jsonl"}
SNAPLEN = 96
TRACE_SIDECAR = re.compile(r"_[0-9a-f]{6}\.json$")
WAN_STATUS = "the WAN watcher's last state, written after the collection"
ROUND2_WAN = ("raw_c2b1_padmax", "raw_c2b1x_shaped", "raw_c2b3_lan")   # the folders the watcher wrote into


def releases() -> dict:
    """Per release: capture folders (name in the features, captures expected), log folders without captures
    (each with the capture folder whose session window its records must lie in), what is left out or cut,
    the features folder, the archives and the manifest's and checksums' names."""
    return {
        "v1": {"sets": {s: (C2_ARMS[s], C2_PER_ARM) for s in C2_SETS}, "logs": {},
               "left_out": LEFT_OUT, "cut": CUT, "features_dir": "features_c2", "readme": FEATURES_README,
               "zips": {"c2-raw-pcaps-headers-only.zip": list(C2_SETS), "c2-features.zip": ["features_c2"]},
               "tls_control": True, "manifest": "manifest.json", "sums": "SHA256SUMS.txt"},
        "round2": {"sets": {"raw_c2b1_padmax": ("c2b1_lan_padmax", 500), "raw_c2b1_shaped": ("c2b1_lan_shaped", 500),
                            "raw_c2b1x_shaped": ("c2b1x_lan_shaped", 2000), "raw_c2b3_lan": ("c2b3_lan", 1000)},
                   "logs": {"raw_c2b1_replies": "raw_c2b1_shaped", "raw_c2b1x_replies": "raw_c2b1x_shaped"},
                   "left_out": {s: {"wan_status.json": WAN_STATUS} for s in ROUND2_WAN},
                   "cut": {s: "wan_watch.jsonl" for s in ROUND2_WAN},
                   "features_dir": "features_round2", "readme": ROUND2_FEATURES_README,
                   "zips": {"c2b1-raw-pcaps-headers-only.zip": ["raw_c2b1_padmax", "raw_c2b1_shaped", "raw_c2b1_replies"],
                            "c2b1x-raw-pcaps-headers-only.zip": ["raw_c2b1x_shaped", "raw_c2b1x_replies"],
                            "c2b3-raw-pcaps-headers-only.zip": ["raw_c2b3_lan"],
                            "round2-features.zip": ["features_round2"]},
                   "tls_control": False, "manifest": "round2-manifest.json", "sums": "round2-SHA256SUMS.txt"},
    }


def check_log_window(src: Path, lo: float, hi: float) -> dict:
    """A log folder's JSON-lines files: every record's time inside [lo, hi], else the build stops."""
    out = {}
    for f in sorted(src.glob("*.jsonl")):
        times = [json.loads(x)["time"] for x in f.read_text().splitlines() if x.strip()]
        outside = sum(not lo <= t <= hi for t in times)
        if outside:
            raise SystemExit(f"{f}: {outside} of {len(times)} records outside the collection window")
        out[f.name] = {"records": len(times)}
    return out


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def git_state() -> dict:
    def run(*cmd: str) -> str:
        return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return {"git_commit": run("git", "rev-parse", "HEAD"),
            "git_dirty": bool(run("git", "status", "--porcelain", "--", ".", ":(exclude)data", ":(exclude)examples/expected"))}


def window(meta: Path) -> tuple[float, float, str, str]:
    m = json.loads(meta.read_text())
    a = dt.datetime.strptime(m["started"], "%Y-%m-%dT%H:%M:%S%z") - dt.timedelta(seconds=1)
    b = dt.datetime.strptime(m["finished"], "%Y-%m-%dT%H:%M:%S%z") + dt.timedelta(seconds=1)
    return a.timestamp(), b.timestamp(), a.isoformat(), b.isoformat()


def cut_jsonl(src: Path, dst: Path, lo: float, hi: float) -> dict:
    kept = dropped = 0
    with src.open() as f, dst.open("w") as g:
        for line in f:
            if not line.strip():
                continue
            t = json.loads(line)["time"]
            if lo <= t <= hi:
                g.write(line if line.endswith("\n") else line + "\n")
                kept += 1
            else:
                dropped += 1
    return {"kept": kept, "dropped": dropped}


def sidecar_hosts(side: Path) -> set[str]:
    sc = json.loads(side.read_text())
    hosts = {str(a).rsplit(":", 1)[0] for a in (sc.get("agent_endpoints") or {}).values()}
    if sc.get("edge_host"):
        hosts.add(sc["edge_host"])
    return hosts


def packets(path: Path):
    raw = path.read_bytes()
    e = _MAGICS[raw[:4]]
    snap, link = struct.unpack(e + "II", raw[16:24])
    pos = 24
    out = []
    while pos + 16 <= len(raw):
        incl = struct.unpack(e + "I", raw[pos + 8:pos + 12])[0]
        out.append(raw[pos + 16:pos + 16 + incl])
        pos += 16 + incl
    return snap, link, out


def check_pcap(path: Path, allowed: set[str]) -> list[str]:
    bad = []
    snap, link, pkts = packets(path)
    if snap > SNAPLEN:
        bad.append(f"snaplen {snap}")
    if any(len(p) > SNAPLEN for p in pkts):
        bad.append(f"{sum(len(p) > SNAPLEN for p in pkts)} packets over {SNAPLEN} bytes")
    if (n := payload_bytes(path)):
        bad.append(f"{n} payload bytes")
    if (n := real_macs(path)):
        bad.append(f"{n} real MAC addresses")
    off = {0: 4, 1: 14}.get(link)
    if off is None:
        return bad + [f"link type {link}"]
    other = set()
    for p in pkts:
        if len(p) < off + 20 or p[off] >> 4 != 4:
            other.add("non-IPv4 packet")
            continue
        for ip in (p[off + 12:off + 16], p[off + 16:off + 20]):
            s = ".".join(map(str, ip))
            if s not in allowed:
                other.add(s)
    if other:
        bad.append(f"addresses outside {sorted(allowed)}: {sorted(other)}")
    return bad


def text_forms(mac: bytes) -> list[str]:
    h = mac.hex()
    return [h, ":".join(h[i:i + 2] for i in range(0, 12, 2)), "-".join(h[i:i + 2] for i in range(0, 12, 2))]


def leaked_originals(stage: Path, originals: list[bytes]) -> list[str]:
    hits = []
    for f in sorted(stage.rglob("*")):
        if not f.is_file():
            continue
        raw = f.read_bytes()
        low = raw.lower()
        for m in originals:
            if m in raw or any(t.encode() in low for t in text_forms(m)):
                hits.append(str(f.relative_to(stage)))
                break
    return hits


def with_home(stage: Path) -> list[str]:
    """Released files that contain the packager's home directory path (a user name)."""
    home = str(Path.home()).encode()
    return [str(f.relative_to(stage)) for f in sorted(stage.rglob("*")) if f.is_file() and home in f.read_bytes()]


def features(folder: Path, view: str) -> dict:
    """What `a2a_leakcheck run FOLDER --vantage VIEW` extracts. The traces are read directly (not
    through collect(), which refuses captures holding payload) so the originals in data/ can be
    compared as they are."""
    found = []
    for pcap in sorted(folder.glob("*.pcap")):
        tr, why = read_trace(pcap, list(C2_LABELS[:-1]), view)
        if tr is None:
            raise SystemExit(f"{pcap} at {view}: {why}")
        found.append(tr)
    ext = extract(found, keep_empty=True)
    if ext["summary"]["failed"]:
        raise SystemExit(f"{folder} at {view}: {ext['summary']['failed'][:3]}")
    traces = [found[i] for i in ext["trace_index"]]
    sides = [json.loads(t.pcap.with_suffix(".json").read_text()) for t in traces]
    return {"X": ext["trace_X"], "first_request": ext["first_request"],
            "run_id": np.array([t.run_id for t in traces]),
            **{k: np.array(["" if s.get(k) is None else str(s[k]) for s in sides]) for k in C2_LABELS},
            "empty": ext["summary"]["empty_traces"], "summary": ext["summary"]}


def zip_dirs(zpath: Path, root: Path, rels: list[str]) -> None:
    """Deterministic: entries in sorted order, a fixed timestamp and permissions, so the same files give
    the same archive (and checksum) on every build."""
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in rels:
            base = root / rel
            if not base.is_dir():
                raise SystemExit(f"missing {base}")
            for f in sorted(base.rglob("*")):
                if f.is_file() and f.name != ".DS_Store":
                    info = zipfile.ZipInfo(f.relative_to(root).as_posix(), date_time=ZIP_TIME)
                    info.external_attr = 0o644 << 16
                    info.compress_type = zipfile.ZIP_DEFLATED
                    z.writestr(info, f.read_bytes())


def main(a: argparse.Namespace) -> int:
    data, out = Path(a.data).resolve(), Path(a.out).resolve()
    if out.exists():
        raise SystemExit(f"{out} exists: the packager never overwrites; pick a new --out")
    stage = out / "stage"
    if Path(a.data).is_absolute():
        raise SystemExit("--data must be a relative path (it is recorded in the released manifest)")
    rel = releases()[a.release]
    sets, tls = rel["sets"], rel["tls_control"] and not a.no_tls_control
    man: dict = {"created": dt.datetime.now().astimezone().isoformat(timespec="seconds"), **git_state(),
                 "release": a.release, "data": a.data, "sets": {}, "left_out": {}, "cut": {}}
    if man["git_dirty"]:
        print(f"warning: uncommitted code; {rel['manifest']} records git_dirty: true")
    macs = MacPlaceholders()
    raw_sets = list(sets) + (list(TLS_RAW) if tls else [])

    # 1. stage: strip, rewrite addresses, cut the watcher log, leave out what is listed
    for s in raw_sets:
        src = data / s
        pcaps = sorted(src.glob("*.pcap"))
        if s in sets and len(pcaps) != sets[s][1]:
            raise SystemExit(f"{src}: {len(pcaps)} captures, expected {sets[s][1]}")
        removed = 0
        for p in pcaps:
            removed += strip_file(p, stage / "data" / s / p.name, macs if s in sets else None)[1]
        for f in sorted(src.iterdir()):
            if f.suffix == ".pcap" or not f.is_file() or f.name == ".DS_Store":
                continue
            if f.name in rel["left_out"].get(s, {}):
                man["left_out"][f"{s}/{f.name}"] = rel["left_out"][s][f.name]
                continue
            dst = stage / "data" / s / f.name
            if rel["cut"].get(s) == f.name:
                lo, hi, lo_s, hi_s = window(src / "session_meta.json")
                man["cut"][f"{s}/{f.name}"] = {"window": [lo_s, hi_s], **cut_jsonl(f, dst, lo, hi),
                                               "rule": "records whose time is in the collection window "
                                                       "(session_meta started/finished, ±1 s)"}
                continue
            shutil.copy2(f, dst)
        man["sets"][s] = {"pcaps": len(pcaps), "payload_bytes_removed": removed}
        print(f"staged data/{s}: {len(pcaps)} captures, {removed} payload bytes removed")
    man["logs"] = {}
    for s, owner in rel["logs"].items():
        lo, hi, lo_s, hi_s = window(data / owner / "session_meta.json")
        man["logs"][s] = {"window_of": owner, "window": [lo_s, hi_s], "files": check_log_window(data / s, lo, hi)}
        shutil.copytree(data / s, stage / "data" / s, ignore=shutil.ignore_patterns(".DS_Store"))
        print(f"staged data/{s}: {man['logs'][s]['files']}, every record inside {owner}'s window")
    man["mac_placeholders"] = macs.table()
    for row in macs.table():
        print(f"  MAC {row['placeholder']}: frames of {', '.join(row['ipv4'])}")

    # 2. check the staged captures
    problems = {}
    for s in raw_sets:
        for p in sorted((stage / "data" / s).glob("*.pcap")):
            side = p.with_suffix(".json")
            if not side.exists():
                problems[f"{s}/{p.name}"] = ["no sidecar"]
                continue
            bad = check_pcap(p, sidecar_hosts(side))
            if bad:
                problems[f"{s}/{p.name}"] = bad
    leaks = leaked_originals(stage, macs.originals())
    home = with_home(stage)
    hosts = sorted({h for s in sets for side in (stage / "data" / s).glob("*.json")
                    if TRACE_SIDECAR.search(side.name) for h in sidecar_hosts(side)})
    man["checks"] = {"pcaps_checked": sum(man["sets"][s]["pcaps"] for s in raw_sets),
                     "problems": problems, "files_with_an_original_mac": leaks, "files_with_the_home_path": home,
                     "c2_hosts_in_sidecars": hosts, "snaplen_max": SNAPLEN}
    if problems or leaks or home:
        (out / rel["manifest"]).write_text(json.dumps(man, indent=2))
        raise SystemExit(f"checks failed: {len(problems)} captures, {len(leaks)} files with an original "
                         f"address, {len(home)} with the home path; see {out / rel['manifest']}")
    print(f"checked {man['checks']['pcaps_checked']} captures: snaplen ≤ {SNAPLEN}, headers only, "
          f"placeholder MACs only, hosts {hosts}; no original address in any file")

    # 3. features from the released captures, compared with those from data/
    fdir = stage / "data" / rel["features_dir"]
    fdir.mkdir(parents=True)
    names = np.array(FLAT_FEATURE_NAMES())
    man["features"] = {}
    for s in sets:
        for v in C2_VIEWS:
            new, old = features(stage / "data" / s, v), features(data / s, v)
            same = (np.array_equal(new["X"], old["X"]) and np.array_equal(new["first_request"], old["first_request"])
                    and np.array_equal(new["run_id"], old["run_id"]))
            if not same:
                raise SystemExit(f"{s} at {v}: features from the released captures differ from data/")
            name = f"{sets[s][0]}_{v}"
            np.savez_compressed(fdir / f"{name}.npz", X=new["X"], feature_names=names,
                                first_request_bytes=new["first_request"], run_id=new["run_id"],
                                **{k: new[k] for k in C2_LABELS})
            man["features"][name] = {"traces": int(len(new["run_id"])), "dims": int(new["X"].shape[1]),
                                     "traces_with_nothing_in_view": int(new["empty"]),
                                     "equal_to_data": True}
            print(f"features {name}: {len(new['run_id'])} traces × {new['X'].shape[1]}, "
                  f"{new['empty']} with nothing in view; equal to those from data/")
    (fdir / "README.md").write_text(rel["readme"])
    man["features_definition"] = {"measurement": new["summary"]["measurement"],
                                  "retransmissions": new["summary"]["retransmissions"],
                                  "first_request": new["summary"]["first_request"]}

    # 4. zips and checksums
    zips = {z: [f"data/{s}" for s in rels] for z, rels in rel["zips"].items()}
    if tls:
        for s in TLS_FEATURES:
            if not (data / s).is_dir():
                raise SystemExit(f"missing {data / s}")
            shutil.copytree(data / s, stage / "data" / s, ignore=shutil.ignore_patterns(".DS_Store"))
        zips["tlscontrol-raw-pcaps-headers-only.zip"] = [f"data/{s}" for s in TLS_RAW]
        zips["tlscontrol-features-own-dedup.zip"] = [f"data/{s}" for s in TLS_FEATURES]
    man["archives"] = {}
    for z, rels in zips.items():
        zip_dirs(out / z, stage, rels)
        man["archives"][z] = {"sha256": sha256(out / z), "bytes": (out / z).stat().st_size, "contents": rels}
    text = json.dumps(man, indent=2) + "\n"
    if str(Path.home()) in text:
        raise SystemExit(f"{rel['manifest']} would contain the home path")
    (out / rel["manifest"]).write_text(text)
    with (out / rel["sums"]).open("w") as f:
        for z in list(zips) + [rel["manifest"]]:
            f.write(f"{sha256(out / z)}  {z}\n")
    shutil.rmtree(stage)
    print((out / rel["sums"]).read_text(), end="")
    print(f"→ {out}: upload the zips, {rel['manifest']} and {rel['sums']}; paste the checksums into DATA.md")
    return 0


FEATURES_README = """# C2 features

One file per arm and observer view: `lan`, `lan_pad`, `lan_padmax` × `v1` (building network: the edge
host's flows to the cloud agents and to the local ticket service) and `v2` (upstream: its flows to the
cloud agents only). Each holds what a2a-leakcheck computes from the released captures with
`--vantage v1|v2`:

| Key | Shape | Content |
|---|---|---|
| `X` | 1000 × 195 | trace features (`feature_names`); all zero for a task the view sees nothing of |
| `feature_names` | 195 | `features.names.FLAT_FEATURE_NAMES()` |
| `first_request_bytes` | 1000 | the first request's size in TCP sequence space (0 when nothing is in view) |
| `run_id` | 1000 | the capture's name in `data/raw_c2*/` |
| `task_type`, `escalated`, `cloud_role`, `audit_null`, `prompt_group` | 1000 | labels from the sidecars (`cloud_role` is empty for tasks answered on the edge) |

Built by `scripts/package_paper2_data.py`, which checks that the features from the released captures equal
those from the original captures.
"""

ROUND2_FEATURES_README = """# Round 2 features

One file per collection, arm and observer view, as for C2 (`features_c2`): `c2b1_lan_padmax` and
`c2b1_lan_shaped` (500 traces each), `c2b1x_lan_shaped` (2,000) and `c2b3_lan` (1,000), each at `v1`
(building network: the edge host's flows to the cloud agents and to the local ticket service) and `v2`
(upstream: its flows to the cloud agents only). Each holds what a2a-leakcheck computes from the released
captures with `--vantage v1|v2`:

| Key | Shape | Content |
|---|---|---|
| `X` | traces × 195 | trace features (`feature_names`); all zero for a task the view sees nothing of |
| `feature_names` | 195 | `features.names.FLAT_FEATURE_NAMES()` |
| `first_request_bytes` | traces | the first request's size in TCP sequence space (0 when nothing is in view) |
| `run_id` | traces | the capture's name in its `data/raw_c2b*` folder |
| `task_type`, `escalated`, `cloud_role`, `audit_null`, `prompt_group` | traces | labels from the sidecars (`cloud_role` is empty for tasks answered on the edge) |

Built by `scripts/package_paper2_data.py --release round2`, which checks that the features from the
released captures equal those from the original captures.
"""


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--data", default="data", help="populated data/ folder (default: data)")
    p.add_argument("--out", required=True, help="new output folder (must not exist)")
    p.add_argument("--no-tls-control", action="store_true", dest="no_tls_control",
                   help="package C2 only")
    p.add_argument("--release", choices=("v1", "round2"), default="v1",
                   help="v1: version 1.0 (C2, the TLS control); round2: C2B1, C2B1X, C2B3 for the new version")
    sys.exit(main(p.parse_args()))
