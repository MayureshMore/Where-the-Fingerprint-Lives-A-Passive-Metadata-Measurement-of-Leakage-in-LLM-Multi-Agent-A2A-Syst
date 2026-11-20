#!/usr/bin/env python3
"""
Copy a2a-leakcheck's code into the SafeIoT pipeline tree (safeiot/3_security_analysis/a2a-leakcheck/src).

The SafeIoT pipeline (github.com/systemsecurity-uiuc/safeiot-vuln-pipeline) keeps each tool's code
inside its stage-3 folder, and a contribution only adds files under folders named after the tool.
a2a-leakcheck is not a pip package and its modules have generic top-level names (features, models,
evaluation), so the tree carries a copy of exactly the files an audit loads (VENDOR, about 4,000
lines; tests/test_safeiot.py checks the list against what a run imports), plus SOURCE.json: the
commit they were copied from and each file's sha256. A run from the copy reports that commit, and
`git_dirty: true` if a copied file has changed since (a2a_leakcheck.cli._git).

Copy from a clean checkout, so that SOURCE.json names a commit that holds exactly these files:

    python scripts/sync_safeiot.py                       # into safeiot/3_security_analysis/a2a-leakcheck/src
    python scripts/sync_safeiot.py --check               # exit 1 if the copy differs from the checkout
    python scripts/sync_safeiot.py --dest DIR --allow-dirty   # a test copy elsewhere, from uncommitted code
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "safeiot" / "3_security_analysis" / "a2a-leakcheck" / "src"
REPOSITORY = ("https://github.com/MayureshMore/Where-the-Fingerprint-Lives-A-Passive-Metadata-Measurement-"
              "of-Leakage-in-LLM-Multi-Agent-A2A-Syst")
VENDOR = [
    "a2a_leakcheck/__init__.py", "a2a_leakcheck/__main__.py", "a2a_leakcheck/analyze.py", "a2a_leakcheck/cli.py",
    "a2a_leakcheck/collect.py", "a2a_leakcheck/extract.py", "a2a_leakcheck/report.py", "a2a_leakcheck/rules.py",
    "a2a_leakcheck/rules.yaml",
    "evaluation/__init__.py", "evaluation/stats.py",
    "features/__init__.py", "features/burst.py", "features/connections.py", "features/extractor.py",
    "features/families.py", "features/first_request.py", "features/kfp.py", "features/per_flow.py",
    "features/per_system.py", "features/roles.py",
    "models/__init__.py", "models/gradient_boosted.py", "models/random_forest.py",
    "scripts/strip_payload.py",
    "LICENSE",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=ROOT, check=True).stdout.strip()


def dirty_files() -> list[str]:
    out = _git("status", "--porcelain", "--", *VENDOR)
    return [line[3:] for line in out.splitlines()]


def differences(dest: Path) -> list[str]:
    """Files whose copy is missing, changed, or not in VENDOR; empty when the copy matches the checkout."""
    out = [f for f in VENDOR if not (dest / f).exists() or sha256(dest / f) != sha256(ROOT / f)]
    extra = sorted(str(p.relative_to(dest)) for p in dest.rglob("*")
                   if p.is_file() and "__pycache__" not in p.parts and p.name != "SOURCE.json"
                   and str(p.relative_to(dest)) not in VENDOR)
    return out + [f"{f} (not in VENDOR)" for f in extra]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--dest", type=Path, default=DEST)
    p.add_argument("--check", action="store_true", help="only compare the copy with the checkout")
    p.add_argument("--allow-dirty", action="store_true", dest="allow_dirty",
                   help="copy uncommitted code (SOURCE.json then says dirty: true); for a test copy only")
    a = p.parse_args(argv)
    if a.check:
        diffs = differences(a.dest)
        print("the copy matches the checkout" if not diffs else "differ: " + ", ".join(diffs))
        return 1 if diffs else 0
    dirty = dirty_files()
    if dirty and not a.allow_dirty:
        raise SystemExit("uncommitted changes in copied files (" + ", ".join(dirty) + "): commit first, "
                         "or --allow-dirty for a test copy")
    if a.dest.exists():
        shutil.rmtree(a.dest)
    for f in VENDOR:
        (a.dest / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / f, a.dest / f)
    source = {"repository": REPOSITORY, "commit": _git("rev-parse", "HEAD"), "dirty": bool(dirty),
              "note": "copied by scripts/sync_safeiot.py; do not edit here, change the repository and copy again",
              "files": {f: sha256(a.dest / f) for f in VENDOR}}
    (a.dest / "SOURCE.json").write_text(json.dumps(source, indent=1) + "\n")
    print(f"{len(VENDOR)} files from {source['commit'][:8]}{' (dirty)' if dirty else ''} → {a.dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
