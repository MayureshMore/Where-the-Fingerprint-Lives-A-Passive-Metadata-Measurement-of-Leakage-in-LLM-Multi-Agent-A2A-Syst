# B1 size check: C2 lan_padmax at 125 per task type

Commit dad9799dae9589b50d235ec4c739fe08a5b907a3 (dirty: False), seed 42, 10 draws by whole prompt groups (the same traces at V1 and V2), a2a-leakcheck's verdict with margin 0.05, 99 group permutations, 1000 bootstraps. B1: `data/results/b1_audits.json` (commit 615db784).

| Task | View | B1 lan_padmax | C2 at B1's size: median [range] | draws under B1 | verdicts L/I/N | C2 full |
|---|---|---|---|---|---|---|
| task_type | v1 | 0.796 [0.762, 0.825] | 0.872 [0.862, 0.890] | 0 of 10 | 10/0/0 | 0.898 [0.879, 0.915] |
| pair | v1 | 0.612 [0.550, 0.671] | 0.750 [0.708, 0.780] | 0 of 10 | 10/0/0 | 0.774 [0.737, 0.810] |
| escalated_only | v1 | 0.726 [0.682, 0.764] | 0.829 [0.787, 0.849] | 0 of 10 | 10/0/0 | 0.852 [0.827, 0.876] |
| task_type | v2 | 0.784 [0.751, 0.814] | 0.880 [0.858, 0.894] | 0 of 10 | 10/0/0 | 0.889 [0.870, 0.907] |
| pair | v2 | 0.628 [0.570, 0.685] | 0.742 [0.708, 0.796] | 0 of 10 | 10/0/0 | 0.788 [0.750, 0.822] |
| escalated_only | v2 | 0.726 [0.683, 0.763] | 0.841 [0.809, 0.854] | 0 of 10 | 10/0/0 | 0.842 [0.814, 0.868] |

"draws under B1": draws whose macro-F1 is below B1's. B1 inside the range points to sample size; far outside it, to the session.
