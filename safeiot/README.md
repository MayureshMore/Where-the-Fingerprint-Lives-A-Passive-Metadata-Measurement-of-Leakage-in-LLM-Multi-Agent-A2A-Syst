# a2a-leakcheck in the SafeIoT pipeline

The five folders here are a contribution to the SafeIoT vulnerability-detection pipeline
([systemsecurity-uiuc/safeiot-vuln-pipeline](https://github.com/systemsecurity-uiuc/safeiot-vuln-pipeline)),
laid out as that repository expects: one folder named after the tool in each stage, plus a harness.

```
1_analysis_object/a2a-leakcheck/     README, fetch.sh, SHA256SUMS.txt   (the captures come from Zenodo)
2_preprocess/a2a-leakcheck/          README, preprocess.sh              (header-only check, features)
3_security_analysis/a2a-leakcheck/   README, analyze.sh, requirements.txt, src/ (a copy of a2a-leakcheck)
4_analysis_output/a2a-leakcheck/     README, example/                   (one representative run)
pipeline_harness/a2a-leakcheck/      README, run.sh                     (clean checkout → result)
```

This README is not part of the contribution: copy the five folders into a clone of the pipeline.

## Keeping the copy current

`3_security_analysis/a2a-leakcheck/src/` is a copy of the files an audit loads. After changing the
tool, commit, then copy again and rebuild the example from that clean commit:

```bash
python scripts/sync_safeiot.py              # refuses uncommitted changes in the copied files
python scripts/sync_safeiot.py --check      # does the copy match the checkout? (tests/test_safeiot.py)
```

## Testing it as the pipeline's maintainers would

```bash
git clone https://github.com/systemsecurity-uiuc/safeiot-vuln-pipeline.git /tmp/safeiot
cp -R safeiot/1_analysis_object/a2a-leakcheck /tmp/safeiot/1_analysis_object/
cp -R safeiot/2_preprocess/a2a-leakcheck /tmp/safeiot/2_preprocess/
cp -R safeiot/3_security_analysis/a2a-leakcheck /tmp/safeiot/3_security_analysis/
cp -R safeiot/4_analysis_output/a2a-leakcheck /tmp/safeiot/4_analysis_output/
cp -R safeiot/pipeline_harness/a2a-leakcheck /tmp/safeiot/pipeline_harness/
cd /tmp/safeiot && ./pipeline_harness/a2a-leakcheck/run.sh quick
```

The committed `4_analysis_output/a2a-leakcheck/example/` is that run's output, copied back.
