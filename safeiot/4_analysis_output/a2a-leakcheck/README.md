# a2a-leakcheck — Analysis Output

A run writes one report per arm and observer view: `report.md` (to read), `report.json` (every
number, for scripts and CI) and `report.html` (the same table in a browser).

## Committed example

`example/` is the harness's quick run (`run.sh quick`): the arm whose requests to the cloud are all
padded to 8 KB, seen upstream (V2).

| File | What it is |
|---|---|
| `example/report.md` | the report: header, verdict table, one section per attribute, runtime |
| `example/report.json` | the same with every number; `git_commit` names the a2a-leakcheck commit it ran from |
| `example/report.html` | the verdict table for a browser |
| `example/example_run.log` | the console output of that run, from a fresh checkout |

What it shows: padding every request to the same 8 KB does not hide the task. The task type still
reads **LEAK** (macro-F1 0.889 against chance 0.25), carried by timing, and the report's hint names
what to try next (shape the replies and their timing too). Whether the gateway escalated, and which
cloud agent answered, read LEAK as well; `audit_null`, the random control label, reads NO LEAK.

Running the harness also writes `last_run/` here (gitignored).

## Reading a verdict

- **LEAK**: an observer of the encrypted traffic does better than chance + 0.05 macro-F1, with 95%
  confidence, and the label-permutation test agrees (p ≤ 0.05). "Carried by" names what suffices
  on its own (one feature family, or the first request's size).
- **NO LEAK**: with these features and this much data the observer stays within 0.05 of chance.
  This bounds this audit's observer; it is not a proof that no other attack works.
- **INCONCLUSIVE**: the data cannot decide (too few tasks, an interval that straddles the
  threshold, or a permutation test that disagrees). Collect more traffic; until then, review it.

A verdict covers what the captures contain: this deployment, this observer view, this period.

## The CI gate

The header of every report keeps two things apart: **audit completed** (the verdicts) and
**release policy** (whether a release may proceed). Without options there is no policy, and the run
exits 0 whatever the verdicts. A pipeline gates a release with:

```bash
./pipeline_harness/a2a-leakcheck/run.sh quick --baseline OLD/report.json   # fail on a new LEAK
./pipeline_harness/a2a-leakcheck/run.sh quick --strict                     # also fail on INCONCLUSIVE
```

| Exit | Meaning |
|---|---|
| 0 | audit completed; the release policy, if any, is satisfied |
| 1 | error (e.g. a capture with payload bytes, a missing sidecar folder) |
| 2 | any LEAK, with `--fail-on-leak` |
| 3 | an attribute is LEAK now that was not LEAK in the baseline report |
| 4 | the baseline is not comparable (another verdict rule, observer view, feature schema or class set): no verdict was compared, and the report names each differing field |
| 5 | `--strict`: an attribute is INCONCLUSIVE; `--require A,B`: A or B is missing or INCONCLUSIVE |

When several apply: 4, then 3, 2, 5. Against a baseline, a LEAK that is now INCONCLUSIVE or missing
is listed for review (`needs_review`), not as resolved; only LEAK → NO LEAK counts as resolved.
