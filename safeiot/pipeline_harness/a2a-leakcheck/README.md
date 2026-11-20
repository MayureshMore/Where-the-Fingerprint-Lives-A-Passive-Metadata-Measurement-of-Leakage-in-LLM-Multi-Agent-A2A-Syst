# a2a-leakcheck — Pipeline Harness

a2a-leakcheck audits the **encrypted traffic of an IoT/edge-AI agent system** for metadata
leakage: can someone who sees only TLS-encrypted packets (their sizes, timing and direction) tell
which task an edge gateway is working on, whether it escalated to the cloud, or which cloud agent
answered? It answers per attribute with LEAK, NO LEAK or INCONCLUSIVE, with a confidence interval,
a permutation test, what carries the leak, and a mitigation hint, and it can gate a release in CI.

The analysis object here is collection C2: 3,000 tasks of a Raspberry Pi 5 gateway agent and two
cloud agents talking A2A over TLS 1.3, published header-only on Zenodo.

## Flow

| Stage | What happens |
|---|---|
| [1 — Analysis object](../../1_analysis_object/a2a-leakcheck/README.md) | `fetch.sh` downloads the header-only captures and task logs (22 MB) from Zenodo and checks their sha256 |
| [2 — Preprocess](../../2_preprocess/a2a-leakcheck/README.md) | `preprocess.sh` refuses any capture with bytes past the TCP header, keeps the chosen observer's flows, and extracts size, timing and count features (`a2a_leakcheck extract`) |
| [3 — Security analysis](../../3_security_analysis/a2a-leakcheck/README.md) | `analyze.sh` decides per attribute: grouped cross-validation, cluster-bootstrap interval, permutation test, attribution, hints (`a2a_leakcheck run`) |
| [4 — Analysis output](../../4_analysis_output/a2a-leakcheck/README.md) | `report.md`, `report.json`, `report.html` per arm and view; the release-policy status and the exit code |

## Prerequisites

- Python 3.11 to 3.13 (the harness makes its own venv in `3_security_analysis/a2a-leakcheck/.venv`
  and installs the pinned `requirements.txt`: numpy, SciPy, scikit-learn, joblib, PyYAML, scapy)
- `curl`, and `unzip` or Python's `zipfile`
- network access to zenodo.org and PyPI; about 350 MB of disk (the venv 220 MB, the unpacked
  captures 115 MB)
- no root, no capture rights, no GPU: the analysis reads files only

## Running

From the repository root:

```bash
./pipeline_harness/a2a-leakcheck/run.sh            # quick: one arm, one view (lan_padmax, V2)
./pipeline_harness/a2a-leakcheck/run.sh full       # all three arms at both views
./pipeline_harness/a2a-leakcheck/run.sh quick --strict    # with a release policy (exit 5 on INCONCLUSIVE)
```

Reports land in `4_analysis_output/a2a-leakcheck/last_run/<arm>_<view>/`. The run exits with the
audits' exit code, so a CI job can gate on it (exit codes in
[stage 4's README](../../4_analysis_output/a2a-leakcheck/README.md)).

Time from a fresh clone on a 14-core laptop (Apple M-series): **quick** 4 min 16 s in all
(dependencies 12 s, download 40 s, features 35 s, audit 2 min 48 s). **full** runs the features and
the audit six times. The audit scales with cores: on a Raspberry Pi 5 (4 cores) one arm and view
takes about 27 minutes.

## To audit your own deployment

Capture your agents' traffic with a filter restricted to their hosts, cut the captures to their
headers, and write one JSON sidecar per task with `agent_endpoints` and the labels to test; then
`python -m a2a_leakcheck run YOUR_FOLDER --attributes task_type,... --out REPORT_DIR`. The sidecar
format and every option are in the research repository's `docs/LEAKCHECK.md`.

## Paper and data

Mayuresh Sanjay More, Shradha Devendra Pujari, Solomon Berhe (University of the Pacific).
*a2a-leakcheck: Auditing Encrypted Agent-to-Agent Traffic for Metadata Leakage in Edge-AI
Deployments.* SafeIoT Hackathon 2026.
Data: [doi:10.5281/zenodo.24238559](https://doi.org/10.5281/zenodo.24238559) (CC BY 4.0).
Code: MIT.
