# leakcheck examples

Two inputs for [a2a-leakcheck](../docs/LEAKCHECK.md), small enough to run in about a minute on a
laptop. Each is 40 header-only captures (packet headers only, no payload bytes) with their label
sidecars, taken from the TLS control's TLS arm (deployment A, TLS on every agent link, loopback;
data CC BY 4.0, [DATA.md](../DATA.md)). `scripts/make_examples.py` builds both from
`data/raw_tlspair_tls`.

| Set | Traces | Labels | Expected verdicts (role / workflow / topology) |
|---|---|---|---|
| `leaky/` | workflows code_review and support_triage × topologies chain and star, 10 each, every trace from its own prompt | real | LEAK / INCONCLUSIVE / LEAK |
| `permuted/` | the same 40 captures | permuted: in each real workflow × topology cell, half the traces get each workflow and half each topology; in each trace the four roles are shuffled across the agent ports | NO LEAK / NO LEAK / INCONCLUSIVE |

```bash
python -m a2a_leakcheck run examples/leaky --out /tmp/leaky --html
python -m a2a_leakcheck run examples/permuted --out /tmp/permuted --html
```

The expected reports are in `expected/leaky/` and `expected/permuted/`. With the versions in
`requirements-lock.txt` the verdicts, scores, intervals and p-values come out the same; the
runtime, memory, date and commit differ. `bash scripts/reproduce_paper2.sh` runs both and
compares them.

What they show:

- **leaky**: role (160 agent samples) and topology leak, p = 0.01. Workflow is visible in the
  traffic (paper 1), but 20 traces per class are not enough to show it: the interval straddles
  chance + margin, and the report says to collect more.
- **permuted**: with labels that say nothing about the traffic, nothing reads LEAK. Role and
  workflow read NO LEAK; topology's interval is too wide for either. A NO LEAK needs enough data
  to rule out a leak, just as a LEAK needs enough to show one.
