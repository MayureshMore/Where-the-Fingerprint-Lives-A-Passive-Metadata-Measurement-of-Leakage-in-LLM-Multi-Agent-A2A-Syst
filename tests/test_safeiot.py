"""The SafeIoT pipeline tree (safeiot/): the copy of a2a-leakcheck matches the repository, runs on its
own and loads only copied files, and says where it came from; every stage has a README; the scripts
parse; the committed checksums are the release's; the example run is clean and names no home folder."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.sync_safeiot import ROOT, VENDOR, differences

TREE = ROOT / "safeiot"
SRC = TREE / "3_security_analysis" / "a2a-leakcheck" / "src"
EXAMPLE = TREE / "4_analysis_output" / "a2a-leakcheck" / "example"
STAGES = ["1_analysis_object", "2_preprocess", "3_security_analysis", "4_analysis_output", "pipeline_harness"]
pytestmark = pytest.mark.skipif(not (SRC / "SOURCE.json").exists(),
                                reason="no copy in safeiot/ yet (python scripts/sync_safeiot.py)")


def _source() -> dict:
    return json.loads((SRC / "SOURCE.json").read_text())


def test_the_copy_matches_the_repository():
    assert differences(SRC) == [], "run python scripts/sync_safeiot.py (from a clean commit)"
    src = _source()
    assert sorted(src["files"]) == sorted(VENDOR) and src["dirty"] is False
    for f, h in src["files"].items():
        assert hashlib.sha256((SRC / f).read_bytes()).hexdigest() == h


def test_every_stage_has_a_readme_and_the_scripts_parse():
    for s in STAGES:
        assert (TREE / s / "a2a-leakcheck" / "README.md").exists(), s
    scripts = sorted(TREE.rglob("*.sh"))
    assert len(scripts) == 4
    for sh in scripts:
        assert os.access(sh, os.X_OK), sh
        subprocess.run(["bash", "-n", str(sh)], check=True)


def test_requirements_pin_the_tested_versions():
    def pins(p: Path) -> list[str]:
        return sorted(x.split("#")[0].strip() for x in p.read_text().splitlines() if x.strip() and not x.startswith("#"))
    assert pins(TREE / "3_security_analysis/a2a-leakcheck/requirements.txt") == pins(ROOT / "requirements-leakcheck.txt")


def test_the_checksums_are_the_release_s():
    sums = dict(reversed(x.split()) for x in (TREE / "1_analysis_object/a2a-leakcheck/SHA256SUMS.txt").read_text().splitlines())
    assert sums["c2-raw-pcaps-headers-only.zip"] in (ROOT / "DATA.md").read_text()
    assert "RECORD=24238559" in (TREE / "1_analysis_object/a2a-leakcheck/fetch.sh").read_text()


DRIVER = r"""
import json, os, sys
src, ex, out = sys.argv[1:4]
sys.path.insert(0, src)
from a2a_leakcheck.cli import _git, main
code = main(["run", ex, "--vantage", "v2", "--attributes", "task_type", "--out", out,
             "--permutations", "9", "--n-boot", "100", "--jobs", "2"])
mods = sorted({os.path.relpath(m.__file__, src) for m in list(sys.modules.values())
               if getattr(m, "__file__", None) and os.path.realpath(m.__file__).startswith(os.path.realpath(src))})
print(json.dumps({"code": code, "modules": mods, "git": _git()}))
"""


def test_the_copy_runs_alone_and_says_where_it_came_from(tmp_path):
    copy = tmp_path / "src"                          # outside any git checkout
    shutil.copytree(SRC, copy, ignore=shutil.ignore_patterns("__pycache__"))
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}

    def drive(n):
        r = subprocess.run([sys.executable, "-c", DRIVER, str(copy), str(ROOT / "examples" / "c2_lan"), str(tmp_path / f"o{n}")],
                           capture_output=True, text=True, cwd=tmp_path, env=env, check=True)
        return json.loads(r.stdout.strip().splitlines()[-1])

    r = drive(1)
    assert r["code"] == 0
    loaded = set(r["modules"])
    assert loaded <= set(VENDOR)                     # nothing from outside the copy
    assert {f for f in VENDOR if f.endswith(".py")} - loaded == {"a2a_leakcheck/__main__.py"}
    src = _source()
    assert r["git"]["git_commit"] == src["commit"] and r["git"]["git_dirty"] is src["dirty"]
    report = json.loads((tmp_path / "o1" / "report.json").read_text())
    assert report["git_commit"] == src["commit"] and report["source"].startswith("vendored copy of ")

    (copy / "a2a_leakcheck" / "rules.yaml").write_text("rules: []\n")
    assert drive(2)["git"]["git_dirty"] is True      # a changed copy says so
    (copy / "SOURCE.json").unlink()
    assert drive(3)["git"] == {"git_commit": None, "git_dirty": None}     # unknown, not "clean"


@pytest.mark.skipif(not (EXAMPLE / "report.json").exists(), reason="no example run yet")
def test_the_example_run_is_clean():
    r = json.loads((EXAMPLE / "report.json").read_text())
    version = re.search(r'__version__ = "([^"]+)"', (SRC / "a2a_leakcheck" / "__init__.py").read_text()).group(1)
    assert r["git_commit"] == _source()["commit"] and r["git_dirty"] is False and r["version"] == version
    assert r["input"]["folder"].startswith("1_analysis_object/a2a-leakcheck/downloads/")
    for f in EXAMPLE.iterdir():
        text = f.read_text()
        assert "/Users/" not in text and "/home/" not in text, f
