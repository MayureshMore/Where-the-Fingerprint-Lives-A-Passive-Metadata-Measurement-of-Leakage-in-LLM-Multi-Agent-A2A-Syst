# Baselines

What a2a-leakcheck is compared with in paper 2. Two answer the auditor's usual question (is the TLS
set up right?); two answer the tool's question (does the traffic's shape give the task away?) with
a simpler detector.

| Baseline | Question it answers | Run | Committed output |
|---|---|---|---|
| sslyze 6.3.1 | TLS versions, cipher suites, certificate, known TLS vulnerabilities | `bash baselines/run_tls_scanners.sh` (live endpoints) | `data/results/tls_scanners/` |
| testssl.sh 3.2.5 | the same, plus a grade | same script | same folder |
| k-FP | website fingerprinting (Hayes and Danezis, 2016): packet direction and timing, random forest | `python baselines/run_detectors.py CAPTURES` | `full.kfp_rf` in `data/results/paper2_tool_eval*.json` |
| first-request rule | the size of the first request alone, GBT | same script | `full.first_request` in the same files |

## TLS scanners

`run_tls_scanners.sh` scans C2's nine TLS endpoints: the two cloud agents and the ticket service, for
each of the three arms. It needs the cloud agents and the ticket service running
(`scripts/serve_cloud.py`, [docs/LAN_SETUP.md](../docs/LAN_SETUP.md)). It also needs
`venv-scanners/bin/sslyze` (`python3 -m venv venv-scanners && venv-scanners/bin/pip install
sslyze==6.3.1`) and `testssl.sh` on PATH (`brew install testssl`).

```bash
bash baselines/run_tls_scanners.sh                               # → data/results/tls_scanners/
python baselines/summarize_tls_scanners.py data/results/tls_scanners --out /tmp/tls_scanners_summary
```

What they reported for C2 (`data/results/tls_scanners_summary.md`) was the same for all nine endpoints:
- **Versions:** TLS 1.2 (five ECDHE suites, two of them CBC) and TLS 1.3 (three suites). The agents'
  own connections negotiated TLS 1.3 (`session_meta.json`, `tls_params`).
- **sslyze:** no vulnerability check positive.
- **testssl.sh:** grade B.
  - CRITICAL: chain of trust incomplete (the testbed's private CA);
  - HIGH: no CRL or OCSP;
  - MEDIUM: security headers;
  - LOW: LUCKY13, among others, because of the CBC suites.

Each of these findings is about the TLS configuration. Neither scanner has a check on the sizes or
timing of the encrypted traffic.

## k-FP and the first-request rule

`run_detectors.py` runs either detector on any a2a-leakcheck input folder, at any observer view. It
uses the same code as the tool evaluation (`scripts/evaluate_leakcheck.py`: `load_arm`, `verdict`),
so it gives the same verdicts as `paper2_tool_eval*.json`.

```bash
python baselines/run_detectors.py examples/c2_lan --attributes task_type --vantage v2
python baselines/run_detectors.py data/raw_c2_padmax --attributes task_type,escalated,cloud_role \
    --vantage v2 --methods kfp_rf,first_request,leakcheck --out /tmp/detectors
```

- **k-FP**: the k-fingerprinting features (`features/kfp.py`: 138 values from packet direction and
  timing, no sizes), with the tool's random forest. A trace's vector covers every agent flow in view.
  For role, each agent's flow gets its own vector.
- **First-request rule**: one number per trace, the size of the first request that reaches an agent.
  It is measured in TCP sequence space (`features/first_request.py`, `first_request_seq`), which is
  where the task input travels. For role, it is the bytes each agent receives.

Both detectors go through a2a-leakcheck's verdict rule unchanged:
- 5-fold cross-validation grouped by prompt;
- macro-F1 with a 1,000-resample cluster-bootstrap interval;
- LEAK when the lower bound clears chance + 0.05 and the 99-permutation test passes at 0.05;
- NO LEAK when the upper bound stays below chance + 0.05;
- INCONCLUSIVE otherwise, or with fewer than 20 samples per class.

So a difference between methods is a difference in what each detector sees, not in how it is judged.
What neither baseline gives is the tool's attribution (which feature family carries the leak) and
its mitigation hint.
