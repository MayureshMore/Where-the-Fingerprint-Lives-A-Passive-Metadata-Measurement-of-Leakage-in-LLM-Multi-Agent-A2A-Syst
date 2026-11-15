# TLS control — summary

Deployment A, cleartext and TLS traces alternating in one session (same prompt per pair). macro-F1 with 95% cluster-bootstrap CIs over prompt groups; cleartext → TLS is prompt-disjoint. Measurement: own connections: only TCP connections whose SYN is in the trace (features/connections.py); commit `56849f02`.

| Task | Chance | Within cleartext | Within TLS | TLS − cleartext (paired) | Cleartext → TLS | n (TLS) |
|---|---|---|---|---|---|---|
| workflow | 0.250 | 0.659 [0.603, 0.708] | 0.577 [0.520, 0.627] | -0.083 [-0.137, -0.025] | 0.474 [0.418, 0.526] | 432 |
| topology | 0.333 | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | +0.000 [+0.000, +0.000] (n.s.) | 0.995 [0.988, 1.000] | 432 |
| role | 0.333 | 0.990 [0.984, 0.996] | 0.991 [0.984, 0.996] | +0.001 [-0.007, +0.008] (n.s.) | 0.961 [0.948, 0.973] | 1296 |

Within-arm cells: macro-F1 on the out-of-fold predictions pooled across the 5 folds (CI from the cluster bootstrap). The transfer is scored on its predictions pooled across folds. The paired difference scores the same out-of-fold predictions and resamples the 231 prompt groups both arms share (2000 resamples).

| On-wire, mean per trace | Cleartext | TLS | Ratio |
|---|---|---|---|
| bytes | 197,992 | 214,922 | ×1.086 |
| packets | 604 | 633 | ×1.048 |
| TCP connections | 3.47 | 3.45 | ×0.994 |

TLS parameters: TLSv1.3, TLS_AES_256_GCM_SHA384 (256-bit), HTTP/1.1.
Record check (raw captures, before stripping): passed; 1.0 TLS handshakes per connection, 3.45 connections per trace.
Session: 2026-10-31T00:33:30-0700 → 2026-10-31T04:32:24-0700; 432 complete pairs; 0 failed attempts (retried).
