"""
a2a-leakcheck: does the encrypted traffic of a multi-agent system reveal who does what?

Given header-only packet captures of an agent system and a label sidecar per capture, it
measures how well an on-path observer can infer each attribute (agent role, workflow,
topology) from packet sizes, timing and counts alone, and gives a verdict per attribute.

Pipeline (one module per stage):

    collection      collect.py   header-only pcaps + label sidecars → traces
    extraction      extract.py   the repository's header-only features (features/)
    analysis        analyze.py   grouped CV per attribute, cluster-bootstrap CIs
    detection       analyze.py   LEAK / NO LEAK / INCONCLUSIVE against chance + margin
    validation      analyze.py   label-permutation test, minimum-sample check
    prioritization  analyze.py   severity from effect size
    report          report.py    JSON + Markdown (+ HTML), mitigation hints (rules.py)
    repeat          report.py    diff against a previous report: refused (exit 4) if the two are not
                                 comparable; exit 3 on a new LEAK; a lost LEAK is listed for review
    policy          report.py    audit completed vs release policy satisfied (--baseline, --fail-on-leak,
                                 --strict, --require); the exit code

`leakcheck extract` runs collection and extraction alone and saves the features; `leakcheck run` on
that folder runs the rest (the two halves of the SafeIoT pipeline's stages 2 and 3).

Usage: python -m a2a_leakcheck run CAPTURE_DIR --out REPORT_DIR   (docs/LEAKCHECK.md)
"""

__version__ = "0.3.0"
