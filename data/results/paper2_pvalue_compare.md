# p-value diagnostics: data/results/paper2_pvalue_pi.json against data/results/paper2_pvalue_mac.json

First difference: **sample/rf-light: null model on the real labels**. Packages that differ: none.

| Stage | Same | Detail |
|---|---|---|
| input X | yes |  |
| input y | yes |  |
| input g | yes |  |
| sample/rf-light: folds | yes |  |
| sample/rf-light: permuted labels | yes |  |
| sample/rf-light: GBT out-of-fold predictions | yes |  |
| sample/rf-light: null model on the real labels | no | {'observed': [0.2616061323930031, 0.27035555297972863]} |
| sample/rf-light: permuted runs' macro-F1 | no | {'differ': 99, 'max_abs': 0.015857213088594835} |
| sample/rf-light: p | no | {'p': [0.22, 0.07]} |
| sample/gbt: folds | yes |  |
| sample/gbt: permuted labels | yes |  |
| sample/gbt: GBT out-of-fold predictions | yes |  |
| sample/gbt: null model on the real labels | yes |  |
| sample/gbt: permuted runs' macro-F1 | yes |  |
| sample/gbt: p | yes |  |
| group/rf-light: folds | yes |  |
| group/rf-light: permuted labels | yes |  |
| group/rf-light: GBT out-of-fold predictions | yes |  |
| group/rf-light: null model on the real labels | no | {'observed': [0.2616061323930031, 0.27035555297972863]} |
| group/rf-light: permuted runs' macro-F1 | no | {'differ': 99, 'max_abs': 0.015890040087517404} |
| group/rf-light: p | no | {'p': [0.2, 0.08]} |
| group/gbt: folds | yes |  |
| group/gbt: permuted labels | yes |  |
| group/gbt: GBT out-of-fold predictions | yes |  |
| group/gbt: null model on the real labels | yes |  |
| group/gbt: permuted runs' macro-F1 | yes |  |
| group/gbt: p | yes |  |
