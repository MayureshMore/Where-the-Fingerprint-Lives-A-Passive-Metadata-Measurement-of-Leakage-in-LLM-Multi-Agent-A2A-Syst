# Extending a2a-leakcheck

How to point [a2a-leakcheck](LEAKCHECK.md) at another agent framework, protocol, capture source,
rule or attribute.

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

## A new protocol

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

## A new capture source

- **pcapng** (Wireshark's default): convert first, `editcap -F pcap in.pcapng out.pcap`.
- **Another link type**: add its link-header length to `_LINK_HDR` in `scripts/strip_payload.py`;
  the stripper, the header parser and the checks all use that table.
- **Another vantage point** (a mirrored switch port, a router): only the filter and the interface
  change. Limit the capture to the agent hosts and ports, as `PacketRecorder(hosts=...)` does,
  and record the vantage point in the sidecars or the collection's metadata.

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
`model` from every sidecar. Traces without the key are left out of that attribute only.
