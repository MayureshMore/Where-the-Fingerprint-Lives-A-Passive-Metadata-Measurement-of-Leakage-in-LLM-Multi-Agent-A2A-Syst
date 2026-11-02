# a2a-leakcheck

Does the encrypted traffic of a multi-agent system reveal which agent does what (role), which
task is running (workflow), or how the agents are wired (topology)? `a2a_leakcheck` answers per
attribute with LEAK, NO LEAK or INCONCLUSIVE, from packet headers alone.

```bash
python -m a2a_leakcheck run CAPTURE_DIR --out REPORT_DIR [--html]
python -m a2a_leakcheck run CAPTURE_DIR --out REPORT_DIR --baseline LAST/report.json   # CI
python -m a2a_leakcheck diff NEW/report.json OLD/report.json
```

## Pipeline

| Stage | What it does | Code |
|---|---|---|
| Collection | reads a folder of header-only pcaps, each with a JSON label sidecar; refuses captures that still hold payload bytes (`--strip` analyses header-only copies instead) | `collect.py` |
| Extraction | the repository's header-only features: a 195-dim vector per trace, a 35-dim vector per agent per trace, and the size of the first request that reaches an agent | `extract.py`, `features/` |
| Analysis | per attribute, out-of-fold predictions from 5-fold `StratifiedGroupKFold` (a group of traces sharing a prompt is never split), GBT by default; macro-F1 with a 95% cluster-bootstrap CI over groups | `analyze.py` |
| Detection | chance = 1/k classes. **LEAK** if the CI lower bound is above chance + margin; **NO LEAK** if the CI upper bound is at most chance + margin; **INCONCLUSIVE** otherwise. `--margin`, default 0.05 | `analyze.py` |
| Validation | minimum-sample check (each class needs `--min-per-class` samples, default 20, in at least as many groups as folds; else INCONCLUSIVE). Label-permutation test: the same CV on `--permutations` shuffles of the labels (default 19). A LEAK whose p-value exceeds `--alpha` (0.05) becomes INCONCLUSIVE. The share of permuted runs that would read LEAK is reported as the false-positive rate | `analyze.py` |
| Prioritization | effect size = (macro-F1 − chance) / (1 − chance); severity high ≥ 0.6, medium ≥ 0.3, else low (thresholds in `rules.yaml`) | `analyze.py` |
| Attribution | the same CV on each feature family alone (sizes; timing; counts and direction) and on one request-size feature alone, each paired against all features | `analyze.py` |
| Report | `report.json` (everything), `report.md`, `report.html` with `--html`; mitigation hints from `rules.yaml`; runtime per stage and peak memory | `report.py`, `rules.py` |
| Repeat | `--baseline` (or `diff`) compares verdicts with a previous report | `report.py` |

Exit codes: 0 done; 1 error; 2 any LEAK, with `--fail-on-leak`; 3 an attribute that is LEAK now
and was not in the baseline.

## Input

One `NAME.pcap` and one `NAME.json` per trace. The sidecar fields read:

| Field | Use |
|---|---|
| `agent_endpoints` | `{"executor": "10.0.0.2:8101", ...}`: the role behind each agent port (required) |
| `workflow_class` or `workflow`, `topology` | labels for those attributes |
| any other key | a label, if named in `--attributes` |
| `prompt_group`, else `input_prompt` | grouping key (the prompt's hash); without either, every trace is its own group, and the report says so under `collection.group_source` |
| `success: false` | the trace is skipped |

Captures are classic pcap (not pcapng) with link type BSD loopback, Ethernet, raw IP or Linux
cooked. A packet *to* an agent port is a request, one *from* it a response; ports are never
features.

## Reading a verdict

- **LEAK** says an observer does better than chance + margin, with 95% confidence, and the
  permutation test agrees. "Carried by" names what is enough on its own: one request-size
  feature, or a family that alone is not below all features.
- **NO LEAK** says the observer, with these features and this much data, stays within the margin
  of chance. It is not a proof that no other attack would work.
- **INCONCLUSIVE** says to collect more data, or that the permutation test did not back a LEAK.

The verdict only covers what the captures contain: one deployment, one vantage point, one
period. Re-run when any of them changes; `--baseline` makes that a CI step.

## Extending

### A new agent framework

leakcheck needs only captures and sidecars, so any framework works if:

1. Each agent listens on its own port (or address). With one shared endpoint for all agents,
   role cannot be told apart by port, and the role attribute is meaningless.
2. Traces are captured one task at a time, with a filter on the agent ports and hosts, at a
   96-byte snaplen or less (`capture/recorder.py` does this), then stripped with
   `scripts/strip_payload.py` (or use `--strip`).
3. Each capture gets a sidecar with `agent_endpoints` and the labels. In this repo the
   collectors write them (`capture/automation.py`); for another framework, write the same JSON
   from its run log.

Then `python -m a2a_leakcheck run DIR --out OUT`. Nothing in the tool knows about A2A.

### A new protocol

The features read packet sizes, times and direction from TCP headers. What to change for:

- **Another protocol over TCP+TLS** (HTTP/2, gRPC, WebSocket, MCP over HTTP): nothing for the
  features. If calls are multiplexed on one connection, the per-flow vectors describe connections
  rather than calls, which is still what an observer sees. Check that the first-request measure
  (`features/first_request.py`, which skips the TLS ClientHello and client Finished and groups
  request writes ≤ 50 ms apart) still picks out one request; if not, adjust it there.
- **Without TLS on TCP**: the first-request measure skips two packets it assumes are the TLS
  handshake. Disable the skip in `first_request_bytes` for cleartext captures.
- **QUIC or other UDP transports**: extend the packet readers to UDP
  (`FeatureExtractor._read_with_scapy` in `features/extractor.py` and `tcp_packets` in
  `features/kfp.py`), and give `first_request.py` a QUIC-aware handshake skip.

Add a fixture for the new case to `tests/test_leakcheck.py` (see `_trace`).

### A new capture source

- **pcapng** (Wireshark's default): convert first, `editcap -F pcap in.pcapng out.pcap`.
- **Another link type**: add its link-header length to `_LINK_HDR` in `scripts/strip_payload.py`;
  the stripper, the header parser and the checks all use that table.
- **Another vantage point** (a mirrored switch port, a router): only the filter and the interface
  change. Limit the capture to the agent hosts and ports, as `PacketRecorder(hosts=...)` does,
  and record the vantage point in the sidecars or the collection's metadata.

### A new rule

Rules live in `a2a_leakcheck/rules.yaml`; pass another file with `--rules`. Each rule has an
`id`, a `when` mapping and a `hint`. Every rule whose `when` matches an attribute's facts adds
its hint, in file order. A `when` value must equal the fact, or be a list containing it; dotted
keys reach nested facts.

```yaml
rules:
  - id: pad-task-inputs
    when: {verdict: LEAK, request_size_single_matches_all: true}
    hint: One request-size feature alone matches all features ... pad request bodies to buckets.
  - id: timing-on-workflow
    when: {verdict: LEAK, attribute: workflow, family_matches_all.timing: true}
    hint: ...
```

Facts: `attribute`, `verdict`, `severity`, `top_family`, `top_family_matches_all`,
`request_size_single_matches_all`, `family_matches_all.<sizes|timing|counts_direction>`,
`too_few_samples`. A new fact goes in `facts()` in `a2a_leakcheck/rules.py`. Add a test next to
`test_rules_file_is_configurable`.

### A new attribute

A trace-level attribute is a sidecar key: `--attributes role,workflow,topology,model` reads
`model` from every sidecar. Traces without the key are left out of that attribute only.
