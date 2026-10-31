# TLS control — summary

Deployment A, cleartext and TLS traces alternating in one session (same prompt per pair). macro-F1 with 95% cluster-bootstrap CIs over prompt groups; cleartext → TLS is prompt-disjoint.

| Task | Chance | Within cleartext | Within TLS | Cleartext → TLS | n (TLS) |
|---|---|---|---|---|---|
| workflow | 0.250 | 0.642 [0.588, 0.692] | 0.727 [0.675, 0.779] | 0.586 [0.522, 0.639] | 432 |
| topology | 0.333 | 0.998 [0.992, 1.000] | 0.998 [0.992, 1.000] | 0.995 [0.989, 1.000] | 432 |
| role | 0.333 | 0.988 [0.982, 0.994] | 0.988 [0.982, 0.994] | 0.929 [0.915, 0.943] | 1296 |

| On-wire, mean per trace | Cleartext | TLS | Ratio |
|---|---|---|---|
| bytes | 198,172 | 215,214 | ×1.086 |
| packets | 607 | 638 | ×1.051 |
| TCP connections | 3.47 | 3.45 | ×0.994 |

TLS parameters: TLSv1.3, TLS_AES_256_GCM_SHA384 (256-bit), HTTP/1.1.
Record check (raw captures, before stripping): passed; 1.0 TLS handshakes per connection, 3.45 connections per trace.
Session: 2026-10-31T00:33:30-0700 → 2026-10-31T04:32:24-0700; 432 complete pairs; 0 failed attempts (retried).
