# Pre-fix results (snapshot of 2026-10-31)

A copy of `data/results/` as it stood after commit `4adc0ea`, kept for comparison. Nothing here is
updated again.

**Why it is superseded.** Most of these results were computed from captures in which every
specialist SSE reply of the chain and mesh topologies was cut after its first event
(sse-starlette < 3.6.0 drained every stream in a process once one agent set had shut down; fixed
in `28a1b23`). `stream_integrity.json` measures this per data set and topology, and RECREATE §7e
explains it.

Still valid from this snapshot: `tls_control.*` and `stream_integrity.json` (collected or
computed after the fix), and the results built only on `raw_wan`, `raw_wf_interleaved_full`,
`a2a_mcp`, AutoGen or CrewAI captures. Everything that reads deployment A, A-model, B, B-logic,
LangGraph C, the live defenses or the interleaved sets carries the truncation and is replaced by
new same-session TLS collections.
