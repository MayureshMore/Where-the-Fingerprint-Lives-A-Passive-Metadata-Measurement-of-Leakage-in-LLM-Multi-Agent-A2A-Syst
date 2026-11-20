# a2a-leakcheck

Does the encrypted traffic of a multi-agent system reveal which agent does what (role), which
task is running (workflow), or how the agents are wired (topology)? `a2a_leakcheck` answers per
attribute with LEAK, NO LEAK or INCONCLUSIVE, from packet headers alone.

```bash
python -m a2a_leakcheck run CAPTURE_DIR --out REPORT_DIR [--html]
python -m a2a_leakcheck run CAPTURE_DIR --out REPORT_DIR --baseline LAST/report.json   # CI
python -m a2a_leakcheck run CAPTURE_DIR --out REPORT_DIR --baseline LAST/report.json --strict
python -m a2a_leakcheck diff NEW/report.json OLD/report.json
python -m a2a_leakcheck extract CAPTURE_DIR --out FEATURES_DIR      # stage 2 only: check and features
python -m a2a_leakcheck run FEATURES_DIR --out REPORT_DIR           # stage 3 on saved features
```

## Pipeline

| Stage | What it does | Code |
|---|---|---|
| Collection | reads a folder of header-only pcaps, each with a JSON label sidecar; refuses captures that still hold payload bytes (`--strip` analyses header-only copies instead) | `collect.py` |
| Extraction | the repository's header-only features: a 195-dim vector per trace, a 35-dim vector per agent per trace, and the size of the first request that reaches an agent; only from the TCP connections each capture opens itself (the tail of an earlier trace's connections is dropped; `--legacy-all-connections` keeps it) | `extract.py`, `features/` |
| Analysis | per attribute, out-of-fold predictions from 5-fold `StratifiedGroupKFold` (a group of traces sharing a prompt is never split), GBT by default (the repository's, with the leaf size lowered on training folds under 2 × 20 samples per class, where 20 per leaf allows no split); macro-F1 with a 95% cluster-bootstrap CI over groups | `analyze.py` |
| Detection | chance = 1/k classes. **LEAK** if the CI lower bound is above chance + margin; **NO LEAK** if the CI upper bound is at most chance + margin; **INCONCLUSIVE** otherwise. `--margin`, default 0.05 | `analyze.py` |
| Validation | minimum-sample check (each class needs `--min-per-class` samples, default 20, in at least as many groups as folds; else INCONCLUSIVE). Label-permutation test: the same CV on `--permutations` shuffles of the labels (default 99, so p can reach 0.01), scored with `--null-model` (default `rf-light`, a 100-tree random forest); that model also scores the real labels, so the p-value is exact for it, and a weaker null model only makes the test more conservative. A LEAK whose p-value exceeds `--alpha` (0.05) becomes INCONCLUSIVE, and so does a NO LEAK whose p-value is at most `--alpha` (the two models disagree). The share of permuted runs that would read LEAK is reported as the false-positive rate | `analyze.py` |
| Prioritization | effect size = (macro-F1 − chance) / (1 − chance); severity high ≥ 0.6, medium ≥ 0.3, else low (thresholds in `rules.yaml`) | `analyze.py` |
| Attribution | the same CV on each feature family alone (sizes; timing; counts and direction) and on one request-size feature alone, each paired against all features | `analyze.py` |
| Report | `report.json` (everything), `report.md`, `report.html` with `--html`; mitigation hints from `rules.yaml`; runtime per stage and peak memory | `report.py`, `rules.py` |
| Repeat | `--baseline` (or `diff`) first checks that the two reports are comparable, then compares verdicts: `new_leaks` (LEAK now, not LEAK before), `needs_review` (LEAK before, INCONCLUSIVE or missing now), `resolved` (LEAK before, NO LEAK now) and every change | `report.py` |
| Policy | the report's `status` keeps "audit completed" apart from "release policy satisfied": which checks were asked for (`--baseline`, `--fail-on-leak`, `--strict`, `--require`), which failed, the exit code, and what is left for review | `report.py` |

All cross-validations of an attribute (the model on all features, on each family, on the single
feature, and the permutations) run in parallel worker processes: `--jobs` (default one per core).

`leakcheck extract` runs collection and extraction alone and writes `features.npz` (the feature arrays)
and `features.json` (per trace its group, labels and topology; the collection and extraction
summaries; the feature schema version). `leakcheck run` on that folder analyses it and gives the same
report as a run on the captures; it refuses options that would need another extraction (another
`--vantage`, `--keep-retransmissions`, ...) or attributes that were not extracted.

### Exit codes and the release policy

| Code | Meaning |
|---|---|
| 0 | the audit completed and the release policy, if one was given, is satisfied |
| 1 | error (no usable capture, a capture with payload bytes without `--strip`, bad options) |
| 2 | any LEAK, with `--fail-on-leak` |
| 3 | an attribute that is LEAK now and was not LEAK in the baseline (`--baseline`, `diff`) |
| 4 | the baseline is not comparable, so no verdict was compared (`--baseline`, `diff`) |
| 5 | `--strict`: an attribute is INCONCLUSIVE; `--require A,B`: A or B is missing or INCONCLUSIVE |

When several apply, the run exits with the first of 4, 3, 2, 5. Codes 0 to 3 mean what they meant in
0.1.x; 4 and 5 are new in 0.2.0. Without any of these options the run exits 0 whatever the verdicts:
the report's header then says "Release policy: none configured". With options, it says whether the
policy is satisfied and, if not, why. Either way it lists what is left for review (every
INCONCLUSIVE, and a LEAK in the baseline that is now INCONCLUSIVE or missing).

**Comparable reports.** Before comparing verdicts, `--baseline` and `diff` check that both reports use
the same verdict rule (`margin`, `alpha`, `permutations`, `null_model`, `model`, `folds`, `n_boot`,
`min_per_class`), the same observer view (`--vantage`), the same features (schema version, vector
sizes, own-connection measurement, retransmissions, cleartext) and, for every attribute in both, the
same class set and topology (`--role-within`). If any differs, nothing is compared: the run exits 4
and the report and the terminal name each differing field with both values. The seed, `--jobs` and
the rules file are not compared, as they do not change what a verdict means. Reports from 0.1.x,
which do not record the feature schema, count as schema 1 when their vectors have its sizes (195
trace, 35 role dimensions).

**Review, not failure.** By default INCONCLUSIVE never fails a run, with or without a baseline.
Against a baseline, a LEAK that is now INCONCLUSIVE, or that is missing from the new report, is
listed under `needs_review` (reason `inconclusive` or `missing`), with a "Needs review" line in
`report.md` and on the terminal. It does not count as resolved: the audit no longer shows the leak
but has not shown it gone. Only a LEAK that is now NO LEAK is listed under `resolved`. A missing
attribute that was not LEAK is listed among the changes (after: `absent`). To make an INCONCLUSIVE
fail a release, add `--strict` (every attribute) or `--require ATTR,...` (the listed ones, which must
also be present).

## Input

One `NAME.pcap` and one `NAME.json` per trace. The sidecar fields read:

| Field | Use |
|---|---|
| `agent_endpoints` | `{"executor": "10.0.0.2:8101", ...}`: the role behind each agent port (required) |
| `workflow_class` or `workflow`, `topology` | labels for those attributes |
| any other key | a label, if named in `--attributes` |
| `prompt_group`, else `input_prompt` | grouping key (the prompt's hash); without either, every trace is its own group, and the report says so under `collection.group_source` |
| `success: false` | the trace is skipped |
| `tls: false` | a capture without TLS: the first request is measured from the first client byte (or `--cleartext` for every trace) |

Captures are classic pcap (not pcapng) with link type BSD loopback, Ethernet, raw IP or Linux
cooked. A packet *to* an agent port is a request, one *from* it a response; ports are never
features.

### Agents the capture does not see

A vantage point may see only some agents. At a gateway between the orchestrator's host and the
specialists' host only the orchestrator's calls cross the link (star: three agents; chain: the
executor; mesh: executor and retriever), and calls between specialists never appear. Keep every
agent in `agent_endpoints`: an agent with no traffic in a capture gives no role sample there, so
the role classes follow what the capture shows and can be unbalanced. The minimum-sample check
applies to each class. The report's collection section lists, per topology, in how many traces
each agent carries traffic (`collection.visible_agents`).

When the agents seen differ by topology, the pooled role score can partly reflect the topology:
at the gateway the validator appears only in star traces, so "validator" can be predicted from
"this is a star trace". The report says so under role. `--role-within star` also scores role on
the star traces alone (attribute `role_within_star`, with its own verdict, permutation test and
hints), next to the pooled score; within one topology the score cannot come from telling the
topologies apart. Give several topologies comma-separated. On the gateway view of the TLS
control's TLS arm (`scripts/make_gateway_view.py`), pooled role reads LEAK at 0.955 [0.939,
0.969] and role within star LEAK at 0.988 [0.976, 0.998], p = 0.01 for both.

### Observer views (`--vantage`)

One capture can stand for several observers. A sidecar may list, per view, the endpoints that
observer sees (`"vantages": {"v1": ["diagnostics", "knowledge", "ticket"], "v2": ["diagnostics",
"knowledge"]}`, written by `scripts/collect_session.py --placement edge-cloud`), and
`--vantage v2` keeps only those endpoints' flows before feature extraction. A trace in which the
view sees nothing stays in the analysis with all-zero features and a first-request size of 0:
at C2's upstream view every task answered on the gateway looks like that, and that the observer
sees no traffic is what it learns. The report says how many traces were empty. Trace attributes
missing from some sidecars (C2's `cloud_role`, set only for escalated tasks) are scored on the
traces that have them.

## Reading a verdict

- **LEAK** says an observer does better than chance + margin, with 95% confidence, and the
  permutation test agrees. "Carried by" names what is enough on its own: one request-size
  feature, or a family that alone is not below all features.
- **NO LEAK** says the observer, with these features and this much data, stays within the margin
  of chance. It is not a proof that no other attack would work.
- **INCONCLUSIVE** says to collect more data, or that the permutation test did not back a LEAK.

The verdict only covers what the captures contain: one deployment, one vantage point, one
period. Re-run when any of them changes; `--baseline` makes that a CI step. A role verdict holds
for the topologies in the captures; a role profile need not transfer to another topology. After a
mitigation (padding, timing shaping), re-run the audit on the changed deployment: other features
can still carry the leak.

## On a Raspberry Pi

The audit needs only `requirements-leakcheck.txt` (Python 3.11+): numpy, SciPy, scikit-learn,
joblib, threadpoolctl, PyYAML and scapy, at the versions in `requirements-lock.txt`. PyTorch is
not needed (`models/` and `evaluation/` import their deep-model code lazily). To time a full audit
of the TLS control's TLS arm with one worker per core, with the Pi's agents stopped so that they
do not compete for the cores:

```bash
# on the Mac: code (as in LAN_SETUP.md) and the captures; the Pi's address and login user
# come from configs/c2_network.conf
. configs/c2_network.conf
rsync -a --exclude data --exclude venv --exclude 'venv-*' --exclude .git --exclude dist ./ "$C2_PI_USER@$C2_PI:a2a/"
rsync -a data/raw_tlspair_tls "$C2_PI_USER@$C2_PI:a2a/data/"
rsync -aR data/results/leakcheck/tls_control_tls_own "$C2_PI_USER@$C2_PI:a2a/"      # the Mac's report

# on the Pi
sudo apt install -y time                        # GNU time, for -v
cd ~/a2a && python3 -m venv venv-leakcheck && venv-leakcheck/bin/pip install -r requirements-leakcheck.txt
mkdir -p data/results/leakcheck_pi
{ cat /proc/device-tree/model; echo; nproc; free -m; python3 --version; du -sh venv-leakcheck; } \
    > data/results/leakcheck_pi/machine.txt
/usr/bin/time -v -o data/results/leakcheck_pi/time_tls.txt \
    venv-leakcheck/bin/python -m a2a_leakcheck run data/raw_tlspair_tls --strip --jobs 4 \
    --out data/results/leakcheck_pi/tls_control_tls_own
venv-leakcheck/bin/python -m a2a_leakcheck diff data/results/leakcheck_pi/tls_control_tls_own/report.json \
    data/results/leakcheck/tls_control_tls_own/report.json      # same verdicts as on the Mac
```

`time_tls.txt` gives the wall-clock time, CPU time and the maximum resident set size of the
largest single process, main or worker (GNU time does not add the workers up); the report's runtime section gives the time per stage and
the peak memory of the main process and of one worker after each stage.

## Extending

Another agent framework, protocol, capture source, rule or attribute: [EXTENDING.md](EXTENDING.md).
