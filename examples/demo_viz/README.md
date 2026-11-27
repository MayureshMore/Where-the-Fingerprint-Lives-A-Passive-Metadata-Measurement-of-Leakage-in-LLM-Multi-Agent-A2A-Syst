# Traffic replay demo

`leakcheck_replay.html` replays eight captured C2B1 sessions, one per task type, padded only (`raw_c2b1_padmax`) and padded + shaped (`raw_c2b1_shaped`). It shows each packet's size, time and direction as a passive observer sees them, beside the verdicts a2a-leakcheck gave.

```bash
python examples/demo_viz/extract_traces.py --data-dir data --out examples/demo_viz/traces.json
python examples/demo_viz/build_demo.py
```

The first command needs the C2B1 captures (`data/raw_c2b1_*`, Zenodo version 1.1); `--ids` picks other runs. `traces.json` is committed, so the second command alone builds the page, without the captures.

The verdict and cost numbers on the page are static values typed into `replay_template.html`, from the committed results that `docs/PAPER2_NUMBERS.md` maps (`b1_audits.json`, `b1_pair_pooled.json`, `b1_shaping_overhead.json`, `paper2_round2.json`; C2B1M's from `c2b1m_audits.json`). Rebuilding does not recompute them.
