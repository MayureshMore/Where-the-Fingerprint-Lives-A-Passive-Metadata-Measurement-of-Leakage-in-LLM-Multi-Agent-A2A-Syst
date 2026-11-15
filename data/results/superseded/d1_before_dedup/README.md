# D1 (the TLS control) before every payload byte was counted once

These results counted retransmitted TCP segments again: the two a2a-leakcheck audits
(`leakcheck/tls_control_{tls,clear}_own`, commit da31192a), the paired analysis
(`tls_control_own.*`, commit 0c0e6e01, features `data/processed_tlspair_{clear,tls}_own`), the D1 tool
evaluation (`paper2_tool_eval.*`, commit a8556554) and the expected reports of `examples/leaky` and
`examples/permuted` (commit 5e00add8).

Since the C2 work (Nov 13) a2a-leakcheck counts every payload byte once (TCP retransmissions dropped), the
view of an observer that reassembles the stream. On the TLS arm's captures this moves the workflow score;
the cleartext arm is unchanged and no verdict changes. On Nov 14 all of D1 was re-measured that way at
commit 56849f02 (decision: one measure for all of paper 2). `data/results/d1_dedup_comparison.*` sets every
D1 number paper 2 cites old against new. `--keep-retransmissions` (a2a-leakcheck, evaluate_tls_control.py)
reproduces these files. Kept unchanged for provenance.

The cleartext audit (`leakcheck/tls_control_clear_own`) and the D1 tool evaluation were run at commit
1bdb792d, after the fix that measures a cleartext capture's first request from its first client byte
(`--cleartext`; before it, the request was skipped as a TLS handshake and read 0 B).

The figure CSVs exported before the D1 re-measurement (commit 2c1f3ef1; their D1 rows come from the results above) are in `paper2_csv/`; `data/results/paper2_csv` was exported again at commit 9705bd98.
