# C5 — Cross-Network (US ⇄ India) WAN Runbook

End-to-end procedure for the C5 robustness experiment: train the attack on the
local (LAN) testbed and test it on real US–India WAN traffic, captured
**post-decapsulation** on the VPN tunnel interface.

> **Goal:** quantify how much the attack degrades under real wide-area latency
> and jitter, with the LLM and prompts held identical so the *only* difference
> between the LAN and WAN runs is the network path.

---

## 0. Testbed parameters (confirmed)

| Thing | US — MacBook (driver + capture) | India — Kali VM (specialists) |
|---|---|---|
| Site role | orchestrator + packet capture + analysis | executor / retriever / validator |
| Reach address | — | **`10.16.0.35`** (user `ms`) |
| VPN tunnel iface (Mac) | **`utun8`** (`192.168.3.5`); route to `10.16.0.35` → `utun8` | — |
| Physical LAN iface | `en0` (`10.0.0.228`) — **not** used for capture | — |
| WAN RTT / loss | ~**320 ms** avg, ~**33 %** ICMP loss (genuine US–India link) | — |
| Deployment | **A** | **A** |
| LLM (local, per site) | `llama3.2:3b` via Ollama | `llama3.2:3b` via Ollama |
| Ports | orchestrator `:8000` (local) | executor `:8001`, retriever `:8002`, validator `:8003` (`0.0.0.0`) |
| `num_predict` | **256** (must match LAN) | **256** (must match LAN) |

```
US — MacBook (utun8)                          India — Kali VM (10.16.0.35)
  orchestrator :8000   (local Ollama)           executor  :8001  (local Ollama)
  ▸ collect_wan.py drives the orchestrator       retriever :8002
  ▸ tcpdump -i utun8 captures here               validator :8003
                                                 ▸ serve_agents.py serves these
        orchestrator ──A2A call──▶ specialists   cross the VPN
        specialists  ──SSE resp──▶ orchestrator  ◀── captured post-decap on utun8
```

**Why `utun8`, not `en0`:** over the VPN, the A2A packets are encrypted *inside*
the tunnel on `en0`, so the BPF filter (`tcp and port 8001-8003`) would match
nothing and you'd get empty captures. On `utun8` the **decapsulated** inner A2A
TCP packets appear — the consistent post-decapsulation vantage required by
proposal §11.3. (Bonus: `utun` is link-type `DLT_NULL`, same as the loopback
`lo0` used for the LAN pilots, so packet parsing stays identical.)

**Topology note (important for interpretation):** in `star`, all three
orchestrator→specialist hops cross the WAN. In `chain`/`mesh`, only the
orchestrator↔executor hop crosses the WAN; executor→retriever→validator stays
local on Kali (`127.0.0.1`). That is *correct* for the threat model (a real
on-path US–India observer only sees inter-site hops), but it means WAN
chain/mesh traces carry fewer flows than the LAN ones. That asymmetry is part of
what C5 measures, and is why Phase D also reports a **WAN-internal CV baseline**
(train+test within the WAN data) to separate "the WAN vantage is impoverished"
from "transfer fails".

---

## Phase A — Provision & verify

### A.1 — Kali (run on the India VM: `ssh ms@10.16.0.35`)

The repo is already on Kali. The serve side needs **no ML libraries** (agents
call Ollama over plain HTTP), so install a light, fast subset.

```bash
# ── set once: path to the repo on Kali (folder containing scripts/, agents/) ──
cd ~/Desktop/Passive-Inference-of-Topology-Roles-and-Workflows-in-LLM-Multi-Agent-via-Encrypted-Traffic-Analysis

# 1) venv + LIGHT serve-only deps (no torch/sklearn/scapy needed to serve agents)
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install "a2a-sdk[http-server]==0.3.26" httpx pydantic "uvicorn[standard]" pyyaml

# 2) Ollama (Kali is Debian-based)
curl -fsSL https://ollama.com/install.sh | sh
( ollama serve >/tmp/ollama.log 2>&1 & ) ; sleep 2     # if systemd didn't auto-start it

# 3) SAME model as LAN deployment A (so only the network differs, not the model)
ollama pull llama3.2:3b

# 4) verify
ollama list                                            # expect llama3.2:3b
curl -s http://localhost:11434/api/tags | head -c 200  # Ollama answers
ip -4 addr show | grep 10.16.0.35                      # confirm this VM's VPN IP
```

> Full alternative: `venv/bin/pip install -r requirements.txt` also works — it
> just additionally pulls ~1 GB of torch/sklearn you won't use on the serve side.

### A.2 — Mac (run on the US MacBook, from the repo root)

```bash
# already-confirmed values, re-check before a long run:
route -n get 10.16.0.35 | grep interface     # expect: interface: utun8
ping -c 5 10.16.0.35                          # note RTT (~320 ms) — this is your WAN
ollama list                                   # expect llama3.2:3b (orchestrator's local LLM)
ls data/processed/labels.json                 # LAN train set must exist
```

---

## Phase B — WAN Phase-0 gate (MUST pass before the 600-run job)

### B.1 — Kali: start `star` specialists (leave running; use `tmux`)

```bash
cd ~/REPO_PATH_ON_KALI
tmux new -s serve            # so an SSH drop doesn't kill the agents
venv/bin/python scripts/serve_agents.py --topology star --deployment a
# expect: "Serving deployment-A specialists on 0.0.0.0 ports [8001, 8002, 8003]"
# detach with Ctrl-b then d
```

### B.2 — Mac: reachability across the VPN

```bash
curl -m 10 http://10.16.0.35:8001/.well-known/agent-card.json
# expect a JSON agent card. If it hangs/refuses → Kali firewall (ufw/iptables)
# is blocking 8001-8003 to the VPN, or serve_agents isn't up.
```

### B.3 — Mac: tiny capture on `utun8` (1 workflow, n=2)

```bash
sudo venv/bin/python scripts/collect_wan.py \
  --remote-host 10.16.0.35 --iface utun8 \
  --deployment a --topology star --workflow research_retrieval \
  --n 2 --num-predict 256 --out data/raw_wan_poc
```

### B.4 — Mac: prove the capture is non-empty AND parses

```bash
ls -la data/raw_wan_poc/*.pcap                # each pcap must be > 24 bytes
venv/bin/python scripts/extract_features.py \
  --raw data/raw_wan_poc --out data/processed_wan_poc --scapy
ls data/processed_wan_poc/labels.json        # ≥1 trace parsed
```

**Gate criteria:** pcaps > 24 bytes **and** `extract_features` parses ≥1 trace.
If pcaps are header-only/empty, the BPF filter saw nothing → wrong interface;
re-run `route -n get 10.16.0.35` and use whatever it reports for `--iface`.

> Throwaway PoC artifacts: `rm -rf data/raw_wan_poc data/processed_wan_poc`
> once the gate passes.

---

## Phase C — Full WAN collection (600 traces)

3 topologies × 4 workflows × 50 = **600 traces**, all written to one
`data/raw_wan`. Run **one topology per round**; the remote specialists are wired
for a single topology at startup, so `--topology` must match on both hosts.
Restart `serve_agents` between rounds.

Run the Mac collector inside `tmux` too — at ~320 ms RTT with loss, the full job
takes hours.

### Round 1 — `star`

```bash
# Kali (tmux):
venv/bin/python scripts/serve_agents.py --topology star --deployment a

# Mac (tmux):
sudo venv/bin/python scripts/collect_wan.py \
  --remote-host 10.16.0.35 --iface utun8 \
  --deployment a --topology star --n 50 --num-predict 256 --out data/raw_wan
```

### Round 2 — `chain`  (Ctrl-C `serve_agents` on Kali, restart with new topology)

```bash
# Kali:
venv/bin/python scripts/serve_agents.py --topology chain --deployment a

# Mac:
sudo venv/bin/python scripts/collect_wan.py \
  --remote-host 10.16.0.35 --iface utun8 \
  --deployment a --topology chain --n 50 --num-predict 256 --out data/raw_wan
```

### Round 3 — `mesh`

```bash
# Kali:
venv/bin/python scripts/serve_agents.py --topology mesh --deployment a

# Mac:
sudo venv/bin/python scripts/collect_wan.py \
  --remote-host 10.16.0.35 --iface utun8 \
  --deployment a --topology mesh --n 50 --num-predict 256 --out data/raw_wan
```

Each collector run prints a per-(topology, workflow) success summary. Check the
pcap count after all three rounds:

```bash
ls data/raw_wan/*.pcap | wc -l        # target: 600 (some loss-driven misses are OK)
```

---

## Phase D — Extract features & evaluate

### D.1 — Extract WAN features

```bash
venv/bin/python scripts/extract_features.py \
  --raw data/raw_wan --out data/processed_wan --scapy
```

### D.2 — Cross-network evaluation (LAN→WAN transfer + internal baselines; the headline C5 result)

```bash
venv/bin/python scripts/evaluate_c5.py \
  --local data/processed --wan data/processed_wan \
  --tasks workflow role parallelism topology
# → data/results/c5_cross_network.json  + data/results/figures/c5_cross_network.png
```

One command reports three numbers per task, each with 95% bootstrap CIs:

1. **LAN-internal** — RF group-safe 5-fold CV on the LAN testbed (in-deployment ceiling).
2. **WAN-internal** — RF group-safe 5-fold CV on the WAN capture (WAN-vantage ceiling).
3. **LAN→WAN transfer** — RF trained on LAN, tested on WAN (the cross-network result).

The WAN-internal baseline is the key control: it separates "the WAN vantage is
impoverished" (low WAN-internal) from "the model doesn't transfer vantages"
(high WAN-internal but low LAN→WAN). `data/results/c5_cross_network.json` is the
**single source of truth** cited by [`RESULTS.md`](../RESULTS.md) §4 and the paper.

> An earlier `evaluate_cross_network.py` (transfer-only, no CIs, an earlier n=395 run)
> has been removed; `evaluate_c5.py` and the canonical file above are the only C5 result.

---

## Operational notes

- **Run long jobs under `tmux`/`screen`** on *both* hosts. A dropped SSH session
  or laptop sleep otherwise kills agents (Kali) or the collector (Mac).
- **Keep the Mac awake** during collection: `caffeinate -dimsu &` (kill it after).
- **`sudo` is only for the Mac collector** (tcpdump/BPF). `serve_agents` on Kali
  runs unprivileged.
- **Identical inference both sides:** `llama3.2:3b` + `--num-predict 256` on Mac
  *and* Kali. Changing either makes the WAN comparison measure token length, not
  the network.
- **Loss tolerance:** ~33 % ICMP loss won't necessarily mean 33 % failed traces
  (TCP retransmits), but expect some misses — the collector's success/total
  summary shows them. <600 final pcaps is acceptable; large shortfalls warrant
  investigation.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `collect_wan` errors "Remote executor not reachable" | `serve_agents` not up, or firewall | Start Kali agents; check `curl http://10.16.0.35:8001/.well-known/agent-card.json`; open 8001-8003 in `ufw`/iptables on Kali |
| pcaps are header-only / "empty capture" error | Captured the encrypted tunnel, not the decap'd A2A | Use `--iface utun8` (confirm with `route -n get 10.16.0.35`) |
| `curl` to `:8001` refuses/hangs | Kali firewall or agents bound wrong | `serve_agents` binds `0.0.0.0`; allow the VPN subnet to 8001-8003 |
| Very slow / frequent timeouts | 320 ms RTT + CPU inference on Kali | Expected; `httpx` timeout is 180 s. Let it run; check Kali `top`/`/tmp/ollama.log` |
| `ollama pull` / `serve` fails on Kali | Ollama not running | `( ollama serve >/tmp/ollama.log 2>&1 & )`, then re-pull |
| Topology mismatch (weird flow counts) | `serve_agents` and `collect_wan` `--topology` differ | They MUST match each round; restart `serve_agents` per topology |

---

## What "done" looks like

- `data/raw_wan/` ≈ 600 pcaps (50 × 4 workflows × 3 topologies, minus any loss).
- `data/processed_wan/labels.json` + feature matrices present.
- `data/results/c5_cross_network.json` + `data/results/figures/c5_cross_network.png`:
  per-task LAN-internal, WAN-internal, and LAN→WAN macro-F1 with 95% CIs.

---

## Appendix — optional deployment B over WAN

To repeat the run for deployment B (qwen, the cross-deployment LLM), on **Kali**:
`ollama pull qwen2.5:7b`, then use `--deployment b` on both hosts (specialist
ports become `8011-8013`, orchestrator `8010`):

```bash
# Kali:  venv/bin/python scripts/serve_agents.py --topology star --deployment b
# Mac:   sudo venv/bin/python scripts/collect_wan.py --remote-host 10.16.0.35 \
#          --iface utun8 --deployment b --topology star --n 50 --num-predict 256 \
#          --out data/raw_wan_b
```

Deployment A (above) is the primary C5 path; B is optional extra robustness.