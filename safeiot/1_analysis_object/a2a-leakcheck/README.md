# a2a-leakcheck — Analysis Object

The object under analysis is the **encrypted network traffic of an edge-AI deployment**: an IoT
gateway agent that answers building-maintenance tasks itself or hands them to agents in the cloud,
talking to them over Google's Agent2Agent protocol (A2A: JSON-RPC 2.0 `message/stream` over HTTP/1.1,
answered with server-sent events) inside TLS 1.3. The question a2a-leakcheck asks of it: can someone
who sees only this encrypted traffic tell which task the gateway is working on, whether it escalated
the task to the cloud, and which cloud agent answered?

The object is not checked in. `fetch.sh` downloads it from Zenodo and checks it:

```bash
./1_analysis_object/a2a-leakcheck/fetch.sh
```

It fetches `c2-raw-pcaps-headers-only.zip` (22 MB) from the record
[doi:10.5281/zenodo.24238559](https://doi.org/10.5281/zenodo.24238559) (version 1.0, CC BY 4.0),
checks it against `SHA256SUMS.txt` in this folder (and checks that the record's own `SHA256SUMS.txt`
is the same file), and unpacks it into `downloads/` (gitignored, about 84 MB unpacked).

## What is in it

Collection C2: 3,000 tasks run on a real deployment on Nov 12–13, 2026.

- **The gateway**: a Raspberry Pi 5 running the edge agent with a local model (llama3.2:1b). It
  answers alert triage itself and escalates the other three task types.
- **The cloud**: two agents (diagnostics, knowledge) with a larger model (llama3.2:3b) behind an
  emulated WAN link (a 6 ms delay each way, about 20 ms round trip), and a ticket service on the LAN.
- **Tasks**: 250 each of alert_triage (local), sensor_analysis and fault_diagnosis (both to the
  diagnostics agent), and procedure_lookup (to the knowledge agent), per arm.
- **Three arms**, the same 1,000 tasks each, with requests to the cloud agents padded differently:
  `data/raw_c2` (no padding), `data/raw_c2_pad` (powers of two from 1 KB), `data/raw_c2_padmax`
  (every request to 8 KB).

Per task, one capture and one sidecar:

| File | What it holds |
|---|---|
| `NAME.pcap` | the packets the gateway exchanged during the task, **headers only**: Ethernet, IP and TCP headers, timestamps and original lengths; every byte past the TCP header was cut before release, so no ciphertext and no TLS record is in it. Ethernet addresses are placeholders |
| `NAME.json` | the task log: the labels (`task_type`, `escalated`, `cloud_role`, `audit_null`: a random label per prompt group, a known non-leak), the task window (`start_ts`, `end_ts`), the agents' endpoints, the prompt group, and the endpoints each observer sees (`vantages`) |

Two observer views, both from the same captures:

- **V1** (on the building's LAN): the gateway's calls to both cloud agents and to the ticket service.
- **V2** (upstream, e.g. the ISP): only the calls to the cloud agents. A task the gateway answers
  locally shows no traffic at V2.

The capture filter matched only the testbed's own hosts. The record's `manifest.json` lists what was
checked, cut and left out.
