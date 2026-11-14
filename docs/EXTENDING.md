# Extending a2a-leakcheck

How to point [a2a-leakcheck](LEAKCHECK.md) at another agent framework, protocol, capture source or
vantage point, rule or attribute, and the test to add for each.

## A new agent framework

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

Test: a handful of its stripped captures with sidecars as a fixture, audited end to end as
`tests/test_examples.py` does for the examples.

## A new protocol

The features read packet sizes, times and direction from TCP headers. What to change for:

- **Another protocol over TCP+TLS** (HTTP/2, gRPC, WebSocket, MCP over HTTP): nothing for the
  features. If calls are multiplexed on one connection, the per-flow vectors describe connections
  rather than calls, which is still what an observer sees. Check that the first-request measure
  still picks out one request. leakcheck uses `first_request_seq` in `features/first_request.py`:
  in TCP sequence space, after the TLS handshake (ClientHello, then a client segment of at most
  100 B as the Finished), a request ends at the acknowledgment number of the first server data
  that acknowledges every client byte sent so far. That holds for any request–response protocol
  in which the server answers only once it has the whole request. A protocol that streams the
  request while the server already answers (bidirectional gRPC streams, WebSocket) needs its own
  end-of-request rule there.
- **Without TLS on TCP**: `first_request_seq(..., tls=False)` starts at the first client byte
  instead of skipping a handshake; pass it through in `a2a_leakcheck/extract.py` for cleartext
  captures.
- **QUIC or other UDP transports**: extend the packet readers to UDP
  (`FeatureExtractor._read_with_scapy` in `features/extractor.py` and `tcp_packets` in
  `features/kfp.py`), and give `first_request.py` a QUIC-aware handshake skip.

Add a fixture for the new case to `tests/test_leakcheck.py` (see `_trace`).

## A new capture source or vantage point

- **pcapng** (Wireshark's default): convert first, `editcap -F pcap in.pcapng out.pcap`.
- **Another link type**: add its link-header length to `_LINK_HDR` in `scripts/strip_payload.py`;
  the stripper, the header parser and the checks all use that table.
- **Ethernet or Wi-Fi captures** hold the hardware (MAC) addresses of the hosts on the link. No
  feature reads them, but they identify devices: before sharing captures, replace them with
  `python scripts/strip_payload.py --out STAGE --placeholder-macs DIR` (one placeholder per address,
  02:00:00:00:00:01, :02, ..., consistent across all files of one run), and check with
  `--check --placeholder-macs STAGE/DIR`.
- **Another capture point** (a mirrored switch port, a router): only the filter and the interface
  change. Limit the capture to the agent hosts and ports, as `PacketRecorder(hosts=...)` does.
- **Several observers on one capture.** An observer further out sees fewer agents: in C2 the
  building network (V1) sees the edge host's calls to the cloud agents and to the local ticket
  service, the upstream observer (V2) only the cloud calls. Rather than capture twice, list per
  view the agents it sees in every sidecar,

  ```json
  "agent_endpoints": {"diagnostics": "172.30.0.100:8101", "knowledge": "172.30.0.100:8102",
                      "ticket": "10.0.0.228:8105"},
  "vantages": {"v1": ["diagnostics", "knowledge", "ticket"], "v2": ["diagnostics", "knowledge"]}
  ```

  and run once per view with `--vantage v1` and `--vantage v2`. Only the flows of the endpoints in
  view are kept, before extraction. A trace with nothing in view stays in, with all-zero features
  and a first request of 0 B: a task the observer never sees is an observation too (in C2, a task
  answered on the edge host). The collector writes `vantages` (`scripts/collect_session.py
  --placement edge-cloud`); for another setup write it with the sidecars. A view needs no code.

Test: a fixture capture for the new source in `tests/test_leakcheck.py` (see `_trace`); for a
view, a case next to `test_upstream_view_keeps_tasks_it_cannot_see` in `tests/test_edge_cloud.py`.

## A new rule

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

## A new attribute

A trace-level attribute is a sidecar key: `--attributes role,workflow,topology,model` reads
`model` from every sidecar. Traces without the key (or with an empty value) are left out of that
attribute only. C2 audits `task_type`, `escalated` (did the edge host call the cloud) and
`cloud_role` (which cloud agent served an escalated task; empty for tasks answered on the edge, so
it is scored on escalated tasks only).

A known non-leak makes a useful companion: a label drawn at random per prompt group, which no
traffic can predict. C2's sidecars carry one, `audit_null`
(`random.Random(f"{seed}:{prompt_group}").choice("abcd")`); audit it next to the real attributes
and it must not read LEAK.

To score a new attribute in the tool evaluation (`scripts/evaluate_leakcheck.py`), give it a fixed
random stream in `STREAMS` there, so adding it leaves the draws of the other attributes unchanged.

Test: a sidecar with the new key in a fixture (`tests/test_leakcheck.py`).
