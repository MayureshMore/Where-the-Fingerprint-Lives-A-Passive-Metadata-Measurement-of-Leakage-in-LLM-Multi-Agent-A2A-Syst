# a2a-leakcheck — Security Analysis

Decides, per attribute, whether an on-path observer of the encrypted traffic can infer it:
**LEAK**, **NO LEAK** or **INCONCLUSIVE**. The attributes for C2 are the task type (4 classes),
whether the gateway escalated the task to the cloud, which cloud agent answered (`cloud_role`), and
`audit_null`, a label drawn at random per prompt group that must read NO LEAK (a built-in control).

```bash
./3_security_analysis/a2a-leakcheck/analyze.sh lan_padmax:v2 [-- --strict]
```

runs `python -m a2a_leakcheck run` on each arm and view's features from
[stage 2](../../2_preprocess/a2a-leakcheck/README.md) and writes the reports to
[stage 4](../../4_analysis_output/a2a-leakcheck/README.md).

## How a verdict is reached

1. **Grouped cross-validation.** A gradient-boosted tree model predicts the attribute from the
   features, out of fold, with 5-fold `StratifiedGroupKFold`: tasks that share a prompt form a group
   and are never split between training and test.
2. **Score with uncertainty.** Macro-F1 of the out-of-fold predictions, with a 95% cluster-bootstrap
   interval over prompt groups (1,000 resamples of the fixed predictions; the interval is conditional
   on the fitted cross-validation).
3. **Rule.** Chance is 1/k for k classes (no predictor that ignores the traffic can expect a higher
   macro-F1, whatever the class sizes). LEAK if the interval's lower bound is above chance + 0.05;
   NO LEAK if its upper bound is at most chance + 0.05; INCONCLUSIVE otherwise.
4. **Validation.** At least 20 samples per class in at least 5 groups, else INCONCLUSIVE. A
   label-permutation test (99 permutations, scored with a light random forest that also scores the
   real labels): a LEAK with p > 0.05, or a NO LEAK with p ≤ 0.05, becomes INCONCLUSIVE. Labels are
   permuted by prompt group, as the cross-validation splits: whole groups exchange labels, and
   where a group's labels differ (the agents of one task, for role) they are shuffled within it.
5. **Attribution.** The same cross-validation on each feature family alone (sizes; timing; counts
   and direction) and on the first-request size alone, each paired against all features over the
   same folds and resamples: what carries a leak. A family alone matches all features when the
   upper bound of the paired 95% interval of all − family is at most 0.05 (non-inferiority).
6. **Hints.** Mitigation hints from `src/a2a_leakcheck/rules.yaml` (editable), e.g. pad responses as
   well as requests when sizes still carry the leak.

## Files

| File | Purpose |
|---|---|
| `analyze.sh` | stage 3 for the harness: one audit per arm and view |
| `requirements.txt` | pinned Python dependencies (Python 3.11+) |
| `src/` | the a2a-leakcheck code: `a2a_leakcheck/` (collection, extraction, analysis, report, rules) and the feature, model and statistics modules it uses |
| `src/SOURCE.json` | where `src/` was copied from: repository, commit, sha256 of every file |
| `src/LICENSE` | MIT |

## Why the code is copied here

a2a-leakcheck lives in its authors' research repository, which also holds two papers' experiments.
It is not a pip package, and the modules it needs have generic top-level names (`features`,
`models`, `evaluation`) that should not be installed into a shared environment. So this folder holds
a copy of exactly the 25 files an audit loads (about 4,000 lines), as the pipeline keeps each tool's
code under its own folder. The copy is made by the repository's `scripts/sync_safeiot.py` from a
clean commit, which it records in `SOURCE.json`; the repository's tests fail if the copy and the
repository drift apart. Every report names the commit (`git_commit`) and whether any copied file
has changed since (`git_dirty`). The alternative, installing from a pinned git tag of the research
repository, would tie the pipeline to that repository's name and layout.

The full documentation, the paper's evaluation and the tests are in the repository
(`docs/LEAKCHECK.md`).
