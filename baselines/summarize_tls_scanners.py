#!/usr/bin/env python3
"""
Summarize what the TLS scanners reported for C2's endpoints (baselines/run_tls_scanners.sh).

Per endpoint, from sslyze: the protocol versions and cipher suites the server accepts, and its
vulnerability checks (Heartbleed, CCS injection, ROBOT, client renegotiation, compression); from
testssl.sh: the overall grade and every finding rated MEDIUM, HIGH or CRITICAL (and how many LOW).
Endpoints with identical results are grouped. Neither scanner has a check that looks at the sizes
or timing of the encrypted traffic, which is what a2a-leakcheck audits.

Usage (never overwrites):
    python baselines/summarize_tls_scanners.py data/results/tls_scanners --out data/results/tls_scanners_summary
        → tls_scanners_summary.json, tls_scanners_summary.md
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from a2a_leakcheck.cli import _git  # noqa: E402

VERSIONS = [("ssl_2_0", "SSL 2.0"), ("ssl_3_0", "SSL 3.0"), ("tls_1_0", "TLS 1.0"), ("tls_1_1", "TLS 1.1"),
            ("tls_1_2", "TLS 1.2"), ("tls_1_3", "TLS 1.3")]
SERIOUS = ("CRITICAL", "HIGH", "MEDIUM")


def sslyze(path: Path) -> dict:
    s = json.loads(path.read_text())["server_scan_results"][0]["scan_result"]

    def res(k):
        return (s.get(k) or {}).get("result") or {}
    suites = {name: [c["cipher_suite"]["name"] for c in res(f"{k}_cipher_suites").get("accepted_cipher_suites", [])]
              for k, name in VERSIONS}
    return {"versions": [n for n, c in suites.items() if c], "suites": {n: c for n, c in suites.items() if c},
            "vulnerable": {"heartbleed": res("heartbleed").get("is_vulnerable_to_heartbleed"),
                           "ccs_injection": res("openssl_ccs_injection").get("is_vulnerable_to_ccs_injection"),
                           "robot": res("robot").get("robot_result"),
                           "client_renegotiation_dos": res("session_renegotiation").get(
                               "is_vulnerable_to_client_renegotiation_dos"),
                           "compression": res("tls_compression").get("supports_compression")}}


def testssl(path: Path) -> dict:
    t = json.loads(path.read_text())
    sev = collections.Counter(x["severity"] for x in t)
    return {"grade": next((x["finding"] for x in t if x["id"] == "overall_grade"), None),
            "severity_counts": dict(sorted(sev.items())),
            "findings": [{"id": x["id"], "severity": x["severity"], "finding": x["finding"]}
                         for x in t if x["severity"] in SERIOUS and x["id"] != "overall_grade"],
            "low": sorted({x["id"] for x in t if x["severity"] == "LOW"})}


def summarize(folder: Path) -> dict:
    meta = json.loads((folder / "scanners.json").read_text())
    per = {}
    for ep in meta["endpoints"]:
        f = ep.replace(":", "_")
        per[ep] = {"sslyze": sslyze(folder / f"sslyze_{f}.json"), "testssl": testssl(folder / f"testssl_{f}.json")}
    groups: dict[str, list[str]] = {}
    for ep, r in per.items():
        groups.setdefault(json.dumps(r, sort_keys=True), []).append(ep)
    scanners = {k: meta[k] for k in ("sslyze", "testssl", "git_commit", "started", "finished", "failed")}
    scanners["testssl"] = " ".join(re.sub(r"\x1b\[[0-9;]*m", "", str(scanners["testssl"])).split())
    return {"paper": "P2", "collection_id": "C2", "source": str(folder), **_git(), "scanners": scanners,
            "groups": [{"endpoints": eps, **json.loads(k)} for k, eps in groups.items()],
            "traffic_metadata_checks": 0,
            "note": "neither scanner has a check on the sizes or timing of encrypted traffic"}


def markdown(s: dict) -> str:
    out = [f"# TLS scanners on C2's endpoints\n",
           f"sslyze {s['scanners']['sslyze']}, {s['scanners']['testssl']}; "
           f"{s['scanners']['started']} to {s['scanners']['finished']}; commit {s['scanners']['git_commit'][:8]}; "
           f"failed: {', '.join(s['scanners']['failed']) or 'none'}.\n"]
    for g in s["groups"]:
        sl, ts = g["sslyze"], g["testssl"]
        out.append(f"## {len(g['endpoints'])} endpoint(s): {', '.join(g['endpoints'])}\n")
        out.append(f"- Versions accepted: {', '.join(sl['versions'])}")
        for v, c in sl["suites"].items():
            out.append(f"  - {v}: {', '.join(c)}")
        vuln = [k for k, v in sl["vulnerable"].items() if v not in (False, None, "NOT_VULNERABLE_RSA_NOT_SUPPORTED",
                                                                    "NOT_VULNERABLE_NO_ORACLE")]
        out.append(f"- sslyze vulnerability checks: {'none positive' if not vuln else ', '.join(vuln)}")
        out.append(f"- testssl.sh grade {ts['grade']}; findings rated MEDIUM or above:")
        for x in ts["findings"]:
            out.append(f"  - {x['severity']} `{x['id']}`: {x['finding']}")
        out.append(f"- LOW: {', '.join(f'`{x}`' for x in ts['low'])}")
        out.append("")
    out.append("Neither scanner has a check on the sizes or timing of the encrypted traffic: what "
               "a2a-leakcheck audits is outside what they test.\n")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("folder", help="output folder of run_tls_scanners.sh")
    p.add_argument("--out", default=None, help="path stem for .json and .md (not overwritten)")
    a = p.parse_args(argv)
    s = summarize(Path(a.folder))
    md = markdown(s)
    print(md)
    if a.out:
        for ext, text in ((".json", json.dumps(s, indent=2) + "\n"), (".md", md)):
            f = Path(a.out + ext)
            if f.exists():
                raise SystemExit(f"{f} exists: not overwritten")
            f.write_text(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
