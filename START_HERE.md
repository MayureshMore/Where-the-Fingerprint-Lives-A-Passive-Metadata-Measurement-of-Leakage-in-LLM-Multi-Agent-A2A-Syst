# START HERE — quickstart

> **SafeIoT Track 1 reviewers start here.** Paper 2 is **a2a-leakcheck**; the steps below this box collect
> paper 1's data and can be skipped.
>
> | To | Run or read | Time |
> |---|---|---|
> | Install the tool alone (Python 3.11 to 3.13, no GPU) | `python3 -m venv venv-leakcheck && venv-leakcheck/bin/pip install -r requirements-leakcheck.txt` | 1 min |
> | See it work: the C2 examples audited, the HTML report, the CI gate failing a build on a new leak | `PYTHON=venv-leakcheck/bin/python bash scripts/demo_paper2.sh` | under 1 min |
> | Run the pipeline contribution: the five folders laid out as [safeiot-vuln-pipeline](https://github.com/systemsecurity-uiuc/safeiot-vuln-pipeline) expects, from the Zenodo download to a report | [`safeiot/`](safeiot/README.md): `bash safeiot/pipeline_harness/a2a-leakcheck/run.sh` | about 4 min |
> | Find any number in the paper: its file and field | [docs/PAPER2_NUMBERS.md](docs/PAPER2_NUMBERS.md) | |
> | Rebuild the paper's numbers from the released data and compare each with the committed one; it stops and names any missing archive | `bash scripts/reproduce_paper2.sh --section c2b1m,c2b2` (the two pre-registered sessions), `--section d3,b3` (shaping and the second day), `--quick` (every section's fast part), or no option (everything) | 1 h, 2 h, 6 h, about two days |
>
> Data: Zenodo [doi:10.5281/zenodo.24238558](https://doi.org/10.5281/zenodo.24238558) (all versions;
> D3 and B3 from version 1.1, C2B1M and C2B2 from version 1.2), header-only captures; checksums in
> [DATA.md](DATA.md). The tool's
> manual: [docs/LEAKCHECK.md](docs/LEAKCHECK.md).

The fastest path from a clone to results. Each step is **one command**; deeper docs are
linked where a step has more to it.

**Just want a paper's numbers?** Skip steps 2–6: **step 7** regenerates them deterministically
from the published archives (no GPU, no network, no Ollama, no testbed). Steps 2–6 collect a
*fresh* dataset with the earlier, per-deployment pipeline; paper 1's collection C1 is
`scripts/run_c1_collection.sh` ([RECREATE.md §7f](RECREATE.md#7f-session-collections-c1-and-later))
and paper 2's C2 is [docs/LAN_SETUP.md](docs/LAN_SETUP.md).

**Only auditing captures with a2a-leakcheck?** `pip install -r requirements-leakcheck.txt` is
enough; see the paper 2 quick start in [README.md](README.md#paper-2-safeiot-track-1-a2a-leakcheck).

**Prerequisites:** Python 3.11+, `tcpdump`, and (for real-LLM capture) [Ollama](https://ollama.com).

---

## 1. Install

```bash
python3 -m venv venv && source venv/bin/activate && pip install -r requirements-lock.txt
```

`requirements-lock.txt` holds the exact versions that produced `data/results/`;
`requirements.txt` holds looser ranges.

## 2. Verify A2A traffic is on the wire (Phase 0 — must pass before collecting)

```bash
python scripts/smoke_test_a2a.py --mode local --use-llm --model llama3.2:3b
```

Expect `OVERALL : PASS`. (Drop `--use-llm --model …` for a no-Ollama loopback check.)

## 3. Capture (96-byte snaplen, BPF-scoped to the agent ports)

```bash
mkdir -p logs && sudo venv/bin/python scripts/collect_deployment.py --n 50 --out data/raw 2>&1 | tee logs/pilot.log
```

Collects all 12 topology×workflow pairs (50 runs each = 600 traces). `sudo` is only for
tcpdump's BPF access (macOS: `chmod o+r /dev/bpf*` once lets you drop `sudo`; on Linux use
`sudo`, or `setcap cap_net_raw+ep $(command -v tcpdump)`). The 96-byte snaplen keeps a short slice of
payload per packet; `scripts/package_data.sh` strips captures to headers before any release.

## 4. Extract features (195-dim flat vector)

```bash
python scripts/extract_features.py --raw data/raw --out data/processed --scapy
```

## 5. Train

```bash
python scripts/train_models.py --task all --model all
```

Tree models (RF/GBT) are the headline attackers; the deep CNN/Transformer are a
data-scale sensitivity check — see [docs/DEEP_MODEL_APPENDIX.md](docs/DEEP_MODEL_APPENDIX.md).
(`all` also trains the deep sensitivity-check models; use `--model gbt` for the headline path alone.)

## 6. Evaluate (closed-world + open-world, into a fresh results folder)

```bash
A2A_RESULTS_DIR=data/results_rerun python scripts/evaluate.py --mode all
```

Use `--rf-only` for a fast RF-only pass. Without `A2A_RESULTS_DIR` the script writes into
`data/results/` and replaces the committed results of the earlier suite. Those results are
superseded (captures cut by the streaming bug, RECREATE §7e); [RESULTS.md](RESULTS.md) marks which
results are valid.

## 7. Reproduce a paper from the published archives (no collection needed)

Download the archive from Zenodo and unzip it into the repository root (files and checksums in
[DATA.md](DATA.md)).

- **Paper 1** (C1, [doi:10.5281/zenodo.23938311](https://doi.org/10.5281/zenodo.23938311)):

  ```bash
  A2A_RESULTS_DIR=data/results_p1 python scripts/evaluate_c1.py
  ```

  `scripts/evaluate_c1_revision.py` adds the first-request and padding analyses; it writes into
  `data/results/` directly, so run it in a separate clone.
- **Paper 2** (C2, the TLS control, D3, B3, C2B1M and C2B2, [doi:10.5281/zenodo.24238558](https://doi.org/10.5281/zenodo.24238558),
  version 1.2):

  ```bash
  bash scripts/reproduce_paper2.sh --section c2b1m,c2b2   # the two pre-registered sessions, about 1 h
  bash scripts/reproduce_paper2.sh --section d3,b3        # shaping and the second day, about 2 h
  bash scripts/reproduce_paper2.sh --quick                # every section's fast part, about 6 h
  ```

  Rebuilds the paper's numbers into a **sandbox** (`data/results_paper2_demo/`) and compares each
  with the committed one, in six sections: the v1.0 path, round 2, D3, B3, C2B1M and C2B2 (C2B1M and
  C2B2 need version 1.2's archives). Without `--quick` or
  `--section` it runs everything, round 2's long parts and the tool evaluations included (about two
  days). A missing archive stops it before anything runs.

`bash scripts/reproduce.sh` reproduces the earlier, superseded suite into `data/results_demo/`;
its inputs (deployment A's captures and features) are not in a published archive.

---

## Where to go next

| You want to… | Go to |
|---|---|
| Rebuild the **entire project from scratch** (datasets → results) | [RECREATE.md](RECREATE.md) |
| Understand the results, scope, and honest caveats, and which results are superseded | [RESULTS.md](RESULTS.md) |
| Find the file behind each paper 2 number | [docs/PAPER2_NUMBERS.md](docs/PAPER2_NUMBERS.md) |
| Get the data archive + reproduction inputs | [DATA.md](DATA.md) |
| Run the US⇄India WAN cross-network experiment (C5) | [docs/WAN_COLLECTION.md](docs/WAN_COLLECTION.md) |
| Read the deep-model architectures / training budget | [docs/DEEP_MODEL_APPENDIX.md](docs/DEEP_MODEL_APPENDIX.md) |
| See the full pipeline, threat model, and every variant | [README.md](README.md) |
