"""C2B1X's prompt selection, the commit and collection id in the session records, the WAN check's
capture cleanup, and scripts/b1_audits.py's subsets and summary (no model, no network)."""

import argparse
import json
import random
import subprocess

import pytest

import scripts.check_wan_emulation as cwe
from scripts import b1_audits
from scripts.c2_guard import collection_ids
from scripts.collect_session import read_prompts, select_prompts, selection_key


class Few:
    """A generator with 8 prompts, drawn one at a time from a reseeded generator (as sample_prompts)."""
    def sample_prompts(self, n, seed):
        rng = random.Random(seed)
        return [f"p{rng.randrange(8)}" for _ in range(n)]


def test_without_options_the_prompts_are_the_first_n_as_before():
    from workflows import WORKFLOW_REGISTRY, WorkflowClass, prompt_seed
    cls = WORKFLOW_REGISTRY[WorkflowClass("sensor_analysis")]
    seed = prompt_seed(0, "sensor_analysis", 31000)
    got, sel = select_prompts(cls, 12, seed)
    assert got == cls().sample_prompts(n=12, seed=seed) and sel is None
    later, sel = select_prompts(cls, 5, seed, start=12)               # sensor prompts never repeat
    assert later == cls().sample_prompts(n=17, seed=seed)[12:] and sel["last_position"] == 16


def test_the_selection_continues_the_sequence_and_skips_used_prompts_and_repeats():
    seq = Few().sample_prompts(200, 7)
    used = {seq[3], seq[4]}
    got, sel = select_prompts(Few, 4, 7, start=3, exclude=used)
    assert len(set(got)) == 4 and not set(got) & used
    expect, seen = [], set(used)
    for p in seq[3:]:
        if p not in seen:
            seen.add(p)
            expect.append(p)
        if len(expect) == 4:
            break
    assert got == expect
    pos = sel["last_position"]
    assert sel["first_position"] == 3 and sel["skipped_excluded"] + sel["skipped_repeat"] + 4 == pos - 3 + 1
    assert sel["skipped_excluded"] == sum(p in used for p in seq[3:pos + 1])
    with pytest.raises(SystemExit, match="fewer than 9 new prompts"):
        select_prompts(Few, 9, 7, start=1, limit=5000)                  # only 8 prompts exist
    assert selection_key({"start": 3, "exclude": [], "conditions": {"edge_cloud/x": sel}}) == \
        {"start": 3, "sha1": {"edge_cloud/x": sel["sha1"]}}


def _sidecar(d, run, task, prompt, cid="C2B1", pcap=True):
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{run}.json").write_text(json.dumps({"task_type": task, "input_prompt": prompt, "collection_id": cid}))
    if pcap:
        (d / f"{run}.pcap").write_bytes(b"\xd4\xc3\xb2\xa1")


def test_read_prompts_lists_each_folder_s_collection_and_prompts(tmp_path):
    a, b = tmp_path / "c2", tmp_path / "b1"
    _sidecar(a, "sensor_analysis_edge_cloud_000001", "sensor_analysis", "x", "C2")
    _sidecar(a, "sensor_analysis_edge_cloud_000002", "sensor_analysis", "y", "C2")
    _sidecar(b, "sensor_analysis_edge_cloud_000003", "sensor_analysis", "y", "C2B1")
    (b / "session_meta.json").write_text(json.dumps({"collection_id": "C2B1", "input_prompt": "not a trace"}))
    seen, info = read_prompts([str(a), str(b)])
    assert seen == {"x", "y"}
    assert info == [{"dir": str(a), "collection_ids": ["C2"], "prompts": 2},
                    {"dir": str(b), "collection_ids": ["C2B1"], "prompts": 1}]
    (tmp_path / "empty").mkdir()
    with pytest.raises(SystemExit, match="no trace sidecar"):
        read_prompts([str(tmp_path / "empty")])


def test_the_guard_reads_the_collection_id_of_its_folders(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    assert collection_ids([a, b]) is None
    (a / "session_meta.json").write_text(json.dumps({"collection_id": "C2B1X"}))
    assert collection_ids([a, b]) == "C2B1X"
    (b / "session_meta.json").write_text(json.dumps({"collection_id": "C2B1"}))
    assert collection_ids([a, b]) == ["C2B1", "C2B1X"]


def test_the_wan_check_stops_and_deletes_its_capture_when_a_probe_raises(tmp_path, monkeypatch):
    started, made = [], []
    real_popen, real_mkdtemp = subprocess.Popen, cwe.tempfile.mkdtemp

    def fake_popen(cmd, **kw):                                         # a stand-in for tcpdump
        started.append(real_popen(["sleep", "60"], **kw))
        return started[-1]

    def mkdtemp(prefix):
        made.append(real_mkdtemp(prefix=prefix, dir=tmp_path))
        return made[-1]

    class Down:
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, url, json):
            raise cwe.httpx.ConnectError("edge agent down")

    target = tmp_path / "plan.json"
    target.write_text(json.dumps({"target_rtt_ms": 22.6, "delay_ms": 12}))
    monkeypatch.setattr(cwe.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(cwe.tempfile, "mkdtemp", mkdtemp)
    monkeypatch.setattr(cwe.httpx, "Client", Down)
    monkeypatch.setattr(cwe, "c2_network", lambda: {"C2_PI": "10.0.0.171", "C2_IFACE": "en0", "C2_BASES": "8400"})
    monkeypatch.setattr(cwe, "check_network", lambda *x: {"ok": True, "checks": []})
    monkeypatch.setattr(cwe, "wan_target", lambda *x: {})
    monkeypatch.setattr(cwe.time, "sleep", lambda s: None)
    a = argparse.Namespace(json=str(tmp_path / "wan_check.json"), edge_host=None, no_capture=False, interface=None,
                           target=str(target), fallback_pi=False, bases=None, tolerance=0.2, n=3)
    with pytest.raises(cwe.httpx.ConnectError):
        cwe.main(a)
    assert started and started[0].poll() is not None                  # the capture was stopped
    assert made and not (tmp_path / made[0]).exists()                  # and its folder deleted
    (tmp_path / "wan_check.json").write_text("{}")
    with pytest.raises(SystemExit, match="exists"):
        cwe.main(a)


def test_subsets_are_symlinks_with_a_manifest_of_their_sources(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    b1, x = tmp_path / "raw_b1", tmp_path / "raw_b1x"
    for i, t in enumerate(["sensor_analysis", "fault_diagnosis", "alert_triage", "procedure_lookup"]):
        _sidecar(b1, f"{t}_edge_cloud_00000{i}", t, f"b1-{t}", "C2B1")
        _sidecar(x, f"{t}_edge_cloud_10000{i}", t, f"x-{t}", "C2B1X")
    (x / "session_meta.json").write_text(json.dumps({"collection_id": "C2B1X"}))
    m = b1_audits.subset([b1, x], b1_audits.PAIR, tmp_path / "sub" / "pair")
    assert m["traces"] == 4 and m["per_task_type"] == {"fault_diagnosis": 2, "sensor_analysis": 2}
    assert m["per_collection"] == {"C2B1": 2, "C2B1X": 2}
    assert [s["collection_id"] for s in m["sources"]] == ["C2B1", "C2B1X"]
    links = sorted(p.name for p in (tmp_path / "sub" / "pair").iterdir() if p.is_symlink())
    assert len(links) == 8 and all((tmp_path / "sub" / "pair" / n).resolve().exists() for n in links)
    assert b1_audits.subset([b1, x], b1_audits.PAIR, tmp_path / "sub" / "pair") == m      # the same folder is reused
    with pytest.raises(SystemExit, match="exists with other traces"):
        b1_audits.subset([b1], b1_audits.PAIR, tmp_path / "sub" / "pair")
    cmd = b1_audits.command(tmp_path / "sub" / "pair", tmp_path / "rep", "v2", "task_type", "lbl", tmp_path / "base.json", 2)
    assert cmd[-2:] == ["--baseline", str(tmp_path / "base.json")] and "--strip" in cmd and "v2" in cmd


def test_the_summary_reads_verdicts_carried_by_and_the_baseline_gate():
    fam = lambda m: {"macro_f1": 0.9, "matches_all": m}  # noqa: E731
    report = {"attributes": {
        "task_type": {"verdict": "LEAK", "n": 500, "n_groups": 500, "classes": {"a": 250, "b": 250}, "threshold": 0.3,
                      "analysis": {"macro_f1": 0.9, "ci_lo": 0.88, "ci_hi": 0.92},
                      "validation": {"permutation": {"p_value": 0.01}},
                      "attribution": {"top_family": "timing", "families": {"timing": fam(True)},
                                      "single_request_size": {"feature": "first_request_bytes", "matches_all": False}}},
        "audit_null": {"verdict": "NO LEAK", "analysis": {"macro_f1": 0.25, "ci_lo": 0.2, "ci_hi": 0.29},
                       "validation": {"permutation": {"p_value": 0.6}}, "attribution": None}},
        "diff": {"baseline": "b/report.json", "compatible": True, "changes": [{"attribute": "pair", "before": "LEAK",
                                                                              "after": "INCONCLUSIVE"}],
                 "new_leaks": [], "needs_review": [{"attribute": "pair", "after": "INCONCLUSIVE"}], "resolved": []},
        "status": {"release_policy": {"exit_code": 0}}}
    s = b1_audits.summarize(report)
    assert s["attributes"]["task_type"]["carried_by"] == "timing (alone matches all)"
    assert s["attributes"]["audit_null"]["carried_by"] == "-" and s["attributes"]["task_type"]["p"] == 0.01
    assert s["exit_code"] == 0 and s["baseline"]["needs_review"][0]["attribute"] == "pair"
    assert b1_audits.carried({"top_family": "sizes", "families": {"sizes": fam(False)},
                              "single_request_size": {"feature": "first_request_bytes", "matches_all": True}}) \
        == "first_request_bytes alone"


def test_audits_are_never_written_over(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _sidecar(tmp_path / "raw", "sensor_analysis_edge_cloud_000001", "sensor_analysis", "p")
    (tmp_path / "res.json").write_text("{}")
    with pytest.raises(SystemExit, match="not written over"):
        b1_audits.main(["--arm", f"x={tmp_path / 'raw'}", "--prefix", "t", "--out", str(tmp_path / "res"), "--allow-dirty"])
