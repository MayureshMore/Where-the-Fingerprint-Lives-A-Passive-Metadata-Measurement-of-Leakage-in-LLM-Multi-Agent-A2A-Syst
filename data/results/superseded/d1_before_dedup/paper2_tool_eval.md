# a2a-leakcheck on known answers (TLS control)

Commit `a8556554` (dirty: False), seed 42. Arms: tls (`data/raw_tlspair_tls`, 432 traces), cleartext (`data/raw_tlspair_clear`, 432 traces).

Full-data verdicts on the real labels, and runtime and memory, from `python -m a2a_leakcheck run --strip` in a fresh process per arm. Permuted labels, baselines and subsamples go through the same verdict rule (a2a_leakcheck.analyze: 5-fold StratifiedGroupKFold by prompt group, macro-F1 with a 1000-resample cluster-bootstrap 95% CI, LEAK above chance + 0.05, 99-permutation test with the rf-light null at alpha 0.05, at least 20 samples per class in 5 groups), without feature attribution, which the verdict does not use. Own connections only. Ports are never features.

## Full data

| Method | Recall [95% CI] | False-negative rate | of which NO LEAK | False-positive rate [95% CI] | Precision [95% CI] | Known leaks | Known non-leaks |
|---|---|---|---|---|---|---|---|
| leakcheck | 1.00 [0.61, 1.00] | 0.00 | 0 | 0.00 [0.00, 0.03] | 1.00 [0.61, 1.00] | 6 | 120 |
| kfp_rf | 1.00 [0.61, 1.00] | 0.00 | 0 | 0.00 [0.00, 0.03] | 1.00 [0.61, 1.00] | 6 | 120 |
| first_request | 0.67 [0.30, 0.90] | 0.33 | 0 | 0.00 [0.00, 0.03] | 1.00 [0.51, 1.00] | 6 | 120 |

| Arm | Attribute | Classes | leakcheck: real | kfp_rf: real | first_request: real | leakcheck: permuted L/I/N | kfp_rf: permuted L/I/N | first_request: permuted L/I/N |
|---|---|---|---|---|---|---|---|---|
| tls | role | 3 | LEAK 0.99 [0.98, 1.00] | LEAK 0.99 [0.99, 1.00] | LEAK 0.53 [0.49, 0.56] | 0/0/20 | 0/0/20 | 0/1/19 |
| tls | workflow | 4 | LEAK 0.61 [0.56, 0.66] | LEAK 0.54 [0.48, 0.59] | LEAK 0.58 [0.51, 0.64] | 0/6/14 | 0/3/17 | 0/7/13 |
| tls | topology | 3 | LEAK 1.00 [1.00, 1.00] | LEAK 1.00 [0.99, 1.00] | INCONCLUSIVE 0.36 [0.31, 0.40] | 0/6/14 | 0/5/15 | 0/7/13 |
| cleartext | role | 3 | LEAK 0.99 [0.98, 1.00] | LEAK 0.99 [0.99, 1.00] | LEAK 0.52 [0.48, 0.55] | 0/3/17 | 0/2/18 | 0/2/18 |
| cleartext | workflow | 4 | LEAK 0.66 [0.60, 0.71] | LEAK 0.51 [0.45, 0.56] | LEAK 0.59 [0.53, 0.64] | 0/7/13 | 0/7/13 | 0/7/13 |
| cleartext | topology | 3 | LEAK 1.00 [1.00, 1.00] | LEAK 1.00 [1.00, 1.00] | INCONCLUSIVE 0.35 [0.30, 0.39] | 0/14/6 | 0/10/10 | 0/12/8 |

## Sample size (a2a-leakcheck)

20 draws per size, attribute and arm, by whole prompt groups; each draw also scored with its labels permuted.

| Samples per class | Recall [95% CI] | INCONCLUSIVE on leaks | NO LEAK on leaks | Agreement with full data | False-positive rate [95% CI] |
|---|---|---|---|---|---|
| 5 | 0.00 [0.00, 0.03] | 120 of 120 | 0 | 0.00 | 0.00 [0.00, 0.03] |
| 10 | 0.00 [0.00, 0.03] | 120 of 120 | 0 | 0.00 | 0.00 [0.00, 0.03] |
| 20 | 0.88 [0.80, 0.92] | 15 of 120 | 0 | 0.88 | 0.01 [0.00, 0.05] |
| 30 | 0.98 [0.94, 1.00] | 2 of 120 | 0 | 0.98 | 0.01 [0.00, 0.05] |
| 50 | 1.00 [0.97, 1.00] | 0 of 120 | 0 | 1.00 | 0.00 [0.00, 0.03] |

| Arm | Attribute | n=5 L/I/N (agree) | n=10 L/I/N (agree) | n=20 L/I/N (agree) | n=30 L/I/N (agree) | n=50 L/I/N (agree) |
|---|---|---|---|---|---|---|
| tls | role | 0/20/0 (0.00) | 0/20/0 (0.00) | 20/0/0 (1.00) | 20/0/0 (1.00) | 20/0/0 (1.00) |
| tls | workflow | 0/20/0 (0.00) | 0/20/0 (0.00) | 12/8/0 (0.60) | 18/2/0 (0.90) | 20/0/0 (1.00) |
| tls | topology | 0/20/0 (0.00) | 0/20/0 (0.00) | 20/0/0 (1.00) | 20/0/0 (1.00) | 20/0/0 (1.00) |
| cleartext | role | 0/20/0 (0.00) | 0/20/0 (0.00) | 20/0/0 (1.00) | 20/0/0 (1.00) | 20/0/0 (1.00) |
| cleartext | workflow | 0/20/0 (0.00) | 0/20/0 (0.00) | 13/7/0 (0.65) | 20/0/0 (1.00) | 20/0/0 (1.00) |
| cleartext | topology | 0/20/0 (0.00) | 0/20/0 (0.00) | 20/0/0 (1.00) | 20/0/0 (1.00) | 20/0/0 (1.00) |

## Runtime and memory (a2a-leakcheck run, full data)

| Arm | Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |
|---|---|---|---|---|
| tls | collection | 0.5 | 168 | — |
| tls | extraction | 21.3 | 246 | — |
| tls | analysis:role | 39.6 | 265 | 208 |
| tls | analysis:workflow | 37.3 | 273 | 268 |
| tls | analysis:topology | 26.4 | 276 | 268 |
| tls | total | 125.8 | 276 | 268 |
| cleartext | collection | 0.6 | 171 | — |
| cleartext | extraction | 23.0 | 250 | — |
| cleartext | analysis:role | 44.1 | 250 | 205 |
| cleartext | analysis:workflow | 40.8 | 250 | 265 |
| cleartext | analysis:topology | 28.8 | 250 | 265 |
| cleartext | total | 138.3 | 250 | 265 |

14 worker processes; macOS-27.0.1-arm64-arm-64bit. This evaluation took 251 min.
