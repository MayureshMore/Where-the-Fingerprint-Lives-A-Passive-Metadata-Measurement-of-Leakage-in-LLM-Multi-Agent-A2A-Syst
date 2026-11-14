# leakcheck examples

Small inputs for [a2a-leakcheck](../docs/LEAKCHECK.md), each 20 to 40 header-only captures (packet
headers only, no payload bytes) with their label sidecars, and the report each should give
(`expected/`). Data CC BY 4.0, [DATA.md](../DATA.md).

## The TLS control (paper 1's deployment A on loopback)

Taken from the TLS control's TLS arm (TLS on every agent link). `scripts/make_examples.py` builds
both from `data/raw_tlspair_tls`. Each runs in about a minute on a laptop.

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

- **leaky**: role (120 agent samples: the capture sees three of the four agents; the
  orchestrator's own link is not captured) and topology leak, p = 0.01. Workflow is visible in the
  traffic (paper 1), but 20 traces per class are not enough to show it: the interval straddles
  chance + margin, and the report says to collect more.
- **permuted**: with labels that say nothing about the traffic, nothing reads LEAK. Role and
  workflow read NO LEAK; topology's interval is too wide for either. A NO LEAK needs enough data
  to rule out a leak, just as a LEAK needs enough to show one.

## C2: the edge-cloud use case (paper 2)

Taken from C2 (the edge agent on a Raspberry Pi, the cloud agents behind an emulated WAN,
[docs/LAN_SETUP.md](../docs/LAN_SETUP.md)) by `scripts/make_c2_examples.py`. Ethernet addresses are
replaced by placeholders, as in the data release. Both task types go to the same cloud agent
(`diagnostics`), so the upstream observer (V2) sees one agent and must tell the tasks apart by
the traffic's shape.

| Set | Traces | Expected verdict for task_type at V2 |
|---|---|---|
| `c2_lan/` | 20 sensor_analysis + 20 fault_diagnosis tasks, no padding (`data/raw_c2`) | LEAK, macro-F1 0.77 [0.64, 0.90], p = 0.01 |
| `c2_lan_padmax/` | the same 40 tasks (same prompts) with every cloud request padded to 8 KB (`data/raw_c2_padmax`) | LEAK, 0.75 [0.60, 0.87], p = 0.01 |
| `c2_ci_baseline/` | the first 10 tasks of each type in `c2_lan/` | INCONCLUSIVE: too few traces per class |

```bash
python -m a2a_leakcheck run examples/c2_lan --vantage v2 --attributes task_type --html --out /tmp/c2_lan
python -m a2a_leakcheck run examples/c2_lan_padmax --vantage v2 --attributes task_type --html --out /tmp/c2_padmax
python -m a2a_leakcheck run examples/c2_lan --vantage v2 --attributes task_type --out /tmp/c2_gate \
    --baseline examples/expected/c2_ci_baseline_v2/report.json; echo "exit $?"      # 3: a new LEAK
bash scripts/demo_paper2.sh        # all three, with a verdict table: under a minute
```

What they show:

- **c2_lan**: the task type leaks to an observer who sees only the encrypted calls to one cloud
  agent. Message sizes carry it (counts and direction match them).
- **c2_lan_padmax**: padding every request to 8 KB hides the task input's size (paper 2, the
  first-request estimator), yet the task type still leaks: the report names what still carries it
  and what to try next. On all of C2 this holds at both views
  (`data/results/paper2_tool_eval_c2.md`).
- **c2_ci_baseline**: an earlier audit of the same deployment on 10 tasks per type. Too few to decide,
  so INCONCLUSIVE. Audited against it with `--baseline`, `c2_lan` is a new LEAK and the run exits
  with code 3, as a CI job would fail.

The examples are 40 of C2's 3,000 traces. Claims about C2 as a whole come from the full
evaluation.
