# B1 power check: permuted sensor_analysis vs fault_diagnosis (lan_padmax_v2)

Commit dd9320b5b962ab684d0ae11393a2ec335ca93a63 (dirty: False), seed 42, 20 draws per size, margin 0.05: NO LEAK needs the CI's upper bound at or under 0.55 and no significant permutation test.

| per class | NO LEAK | INCONCLUSIVE | LEAK | CI NO LEAK | median CI upper | range | median upper half-width | p < 0.05 |
|---|---|---|---|---|---|---|---|---|
| 125 + 125 | 8 | 12 | 0 | 8 | 0.568 | 0.455-0.635 | 0.060 | 2 |
| 250 + 250 | 9 | 11 | 0 | 9 | 0.552 | 0.508-0.598 | 0.042 | 1 |
| 375 + 375 (pooled lan_padmax + lan_pad) | 15 | 5 | 0 | 15 | 0.534 | 0.481-0.590 | 0.036 | 1 |

Predicted from the largest measured size by 1/sqrt(n) (CI verdicts only):

| per class | CI NO LEAK | median CI upper | largest CI upper |
|---|---|---|---|
| 375 + 375 | 12 of 20 | 0.543 | 0.580 |
| 500 + 500 | 14 of 20 | 0.537 | 0.569 |
