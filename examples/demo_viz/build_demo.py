#!/usr/bin/env python3
"""
Build leakcheck_replay.html: replay_template.html with the traces from extract_traces.py in place of
__DATA__. A single self-contained page; open it in a browser.

    python examples/demo_viz/build_demo.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEYS = {"arm", "task", "role", "p"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    ap.add_argument("--traces", default=str(HERE / "traces.json"))
    ap.add_argument("--template", default=str(HERE / "replay_template.html"))
    ap.add_argument("--out", default=str(HERE / "leakcheck_replay.html"))
    a = ap.parse_args(argv)
    data = json.loads(Path(a.traces).read_text())
    if not isinstance(data, list) or not data or any(set(r) != KEYS for r in data):
        raise SystemExit(f"{a.traces}: expected a list of {{{', '.join(sorted(KEYS))}}} records (extract_traces.py)")
    pairs = sorted((r["arm"], r["task"]) for r in data)
    if len(set(pairs)) != len(pairs):
        raise SystemExit(f"{a.traces}: an arm and task appear twice; the page shows one trace per arm and task")
    page = Path(a.template).read_text()
    if page.count("__DATA__") != 1:
        raise SystemExit(f"{a.template}: expected __DATA__ exactly once, found {page.count('__DATA__')}")
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")      # safe inside <script>
    Path(a.out).write_text(page.replace("__DATA__", blob))
    print(f"{len(data)} traces ({', '.join(f'{arm}/{task}' for arm, task in pairs)}) -> {a.out} "
          f"({Path(a.out).stat().st_size:,} B)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
