# The six C2 audits as the tool evaluation read them (commit eb8fbbfb)

`scripts/evaluate_leakcheck.py` (`paper2_tool_eval_c2.*`, commit e485f117) read these reports with
`--tool-reports`. The C2 mitigation rules came after it, so the audits were run again at commit
2c1f3ef1 into `data/results/leakcheck/c2_<arm>_<view>`. Every verdict, score, interval, p-value and
attribution is identical; only the mitigation hints differ (`data/results/leakcheck/c2_rerun_compare.*`).
Kept unchanged for provenance.
