# a2a-leakcheck — Preprocess

Turns the captures from [stage 1](../../1_analysis_object/a2a-leakcheck/README.md) into the features
the analysis reads, after checking that they hold headers only.

```bash
./2_preprocess/a2a-leakcheck/preprocess.sh lan_padmax:v2        # one arm, one observer view
```

runs, per arm and view, `python -m a2a_leakcheck extract` (the code is in
[stage 3](../../3_security_analysis/a2a-leakcheck/README.md)'s `src/`).

**In**: a folder of `NAME.pcap` + `NAME.json` (one arm of C2, e.g. `downloads/data/raw_c2_padmax`).

**Checks**, before any feature is computed:
- **Header-only**: every capture is parsed, and one that has any byte past the TCP header in any
  packet is refused (the run stops and names it). a2a-leakcheck analyses metadata, never content.
- Every capture has a sidecar, with the agents' endpoints; failed tasks are skipped and listed.

**Then, per task:**
- **View**: only the flows of the endpoints the chosen observer sees (`--vantage v1` or `v2`, from
  the sidecar's `vantages`). A task with nothing in view (at V2, every task the gateway answers
  locally) stays in, as an all-zero vector: seeing nothing is what that observer sees.
- **Own connections**: only TCP connections whose SYN is in the capture, so the tail of an earlier
  task's connection does not leak into this one.
- **Each payload byte once**: TCP retransmissions are dropped, as an observer that reassembles the
  stream sees it.
- **Features** from packet sizes, timestamps and direction only (never addresses or ports): a
  195-value vector per task (per-flow and system-wide sizes, timing, bursts, counts), a 35-value
  vector per agent, and the size of the first request that reaches an agent (in TCP sequence
  space, after the TLS handshake).

**Out**: `features/<arm>_<view>/features.npz` (the arrays) and `features.json` (per task its prompt
group, labels and topology; what was checked, skipped and kept; the feature schema version). The
folder is gitignored.

Running the analysis on these features gives the same report as running it on the captures in one
go (`a2a_leakcheck run CAPTURES`); the repository's tests check that.
