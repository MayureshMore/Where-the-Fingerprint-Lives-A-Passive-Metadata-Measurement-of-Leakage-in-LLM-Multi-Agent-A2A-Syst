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
    repeat          report.py    diff against a previous report; non-zero exit on a new LEAK

Usage: python -m a2a_leakcheck run CAPTURE_DIR --out REPORT_DIR   (docs/LEAKCHECK.md)
"""

__version__ = "0.1.0"
