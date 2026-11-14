# The Pi's packages against requirements-lock.txt

| Package | Pi | requirements-lock.txt | Pinned in requirements-leakcheck.txt | Same |
|---|---|---|---|---|
| joblib | 1.5.3 | 1.5.3 | yes | yes |
| narwhals | 2.28.0 | 2.22.1 | no | no |
| numpy | 2.4.6 | 2.4.6 | yes | yes |
| pyyaml | 6.0.3 | 6.0.3 | yes | yes |
| scapy | 2.7.0 | 2.7.0 | yes | yes |
| scikit-learn | 1.9.0 | 1.9.0 | yes | yes |
| scipy | 1.17.1 | 1.17.1 | yes | yes |
| threadpoolctl | 3.6.0 | 3.6.0 | yes | yes |

Python: 3.13.5 on the Pi (machine_c2.txt), 3.12.1 on the Mac. narwhals is required by scikit-learn 1.9 (narwhals>=2.0.1) but not pinned in requirements-leakcheck.txt, so the Pi installed the newest release.
