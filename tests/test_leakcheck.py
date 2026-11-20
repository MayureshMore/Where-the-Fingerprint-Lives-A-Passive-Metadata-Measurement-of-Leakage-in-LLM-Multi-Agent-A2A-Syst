"""a2a-leakcheck on synthetic captures with a known leak and a known no-leak.

The fixture writes TLS-like traces (handshake, one request, a streamed response) for three
agents. With leak=True the request size follows the workflow and the response pattern follows
the role. The no-leak set is the same traffic with permuted labels: the workflow labels are
shuffled across traces and the roles across each trace's ports, so nothing predicts them.
"""

import json

import numpy as np
import pytest

from a2a_leakcheck.analyze import INCONCLUSIVE, LEAK, NO_LEAK, Config, analyze, gbt_min_leaf, verdict
from a2a_leakcheck.cli import main
from a2a_leakcheck.report import compatibility, diff, release_policy, write_markdown
from a2a_leakcheck.rules import facts, hints, load_rules
from scripts.compare_reports import compare

scapy_all = pytest.importorskip("scapy.all")
Ether, IP, TCP, Raw, wrpcap = (scapy_all.Ether, scapy_all.IP, scapy_all.TCP, scapy_all.Raw,
                               scapy_all.wrpcap)

ORCH, ROLES = 9000, {"executor": 9001, "retriever": 9002, "validator": 9003}
REQUEST = {"alpha": 2400, "beta": 700}                       # request bytes by workflow
RESPONSE = {"executor": (8, 900), "retriever": (20, 400), "validator": (4, 1300)}   # (events, bytes)
FAST = ["--model", "rf", "--permutations", "9", "--alpha", "0.1", "--n-boot", "300"]


def _pkt(t, sport, dport, flags, n):
    p = Ether(src="02:00:00:00:00:01", dst="02:00:00:00:00:02") / IP(src="10.0.0.1", dst="10.0.0.2") / TCP(sport=sport, dport=dport, flags=flags)
    if n:
        p = p / Raw(b"\x17" * n)
    p.time = t
    return p


def _trace(i, workflow, rng, seen=tuple(ROLES)):
    pkts, t0 = [], 1000.0 + 10 * i
    for k, (role, port) in enumerate(ROLES.items()):
        if role not in seen:
            continue
        c, t = 40000 + 3 * i + k, t0 + 0.01 * k
        seq = [(c, port, "S", 0), (port, c, "SA", 0), (c, port, "A", 0),
               (c, port, "PA", 517), (port, c, "PA", 1374), (c, port, "PA", 80),
               (c, port, "PA", REQUEST[workflow] + int(rng.integers(-150, 150)))]
        n_ev, size = RESPONSE[role]
        seq += [(port, c, "PA", size + int(rng.integers(-80, 80))) for _ in range(n_ev + int(rng.integers(-1, 2)))]
        seq += [(c, port, "FA", 0), (port, c, "FA", 0)]
        for j, (s, d, f, n) in enumerate(seq):
            pkts.append(_pkt(t + 0.002 * j + (0.02 * j if j > 6 else 0), s, d, f, n))
    return sorted(pkts, key=lambda p: p.time)


def make_dataset(folder, n, leak=True, seed=0):
    """n traces, half alpha and half beta; topology labels are random noise. leak=False: workflow
    labels balanced against the real workflow, roles shuffled across the agent ports."""
    rng = np.random.default_rng(seed)
    folder.mkdir(parents=True, exist_ok=True)
    workflows = ["alpha" if i % 2 == 0 else "beta" for i in range(n)]
    labels = list(workflows)
    if not leak:      # half of each real workflow gets each label: independent of the traffic in-sample
        for wf in ("alpha", "beta"):
            idx = [i for i, w in enumerate(workflows) if w == wf]
            for i, lab in zip(idx, rng.permutation(["alpha", "beta"] * (len(idx) // 2) + ["alpha"] * (len(idx) % 2))):
                labels[i] = str(lab)
    for i, wf in enumerate(workflows):
        run_id = f"t{i:04d}"
        wrpcap(str(folder / f"{run_id}.pcap"), _trace(i, wf, rng))
        roles = list(ROLES)
        if not leak:
            roles = list(rng.permutation(roles))
        eps = {"orchestrator": f"10.0.0.1:{ORCH}",
               **{r: f"10.0.0.2:{p}" for r, p in zip(roles, ROLES.values())}}
        (folder / f"{run_id}.json").write_text(json.dumps({
            "run_id": run_id, "workflow_class": labels[i], "topology": str(rng.choice(["star", "chain"])),
            "agent_endpoints": eps, "input_prompt": f"prompt {i}", "success": True}))
    return folder


@pytest.fixture(scope="module")
def leak_report(tmp_path_factory):
    d = make_dataset(tmp_path_factory.mktemp("leak"), 60, leak=True)
    out = tmp_path_factory.mktemp("leak_out")
    code = main(["run", str(d), "--out", str(out), "--strip", "--html", "--attributes", "role,workflow,topology", *FAST])
    return code, json.loads((out / "report.json").read_text()), out


@pytest.fixture(scope="module")
def noleak_report(tmp_path_factory):
    d = make_dataset(tmp_path_factory.mktemp("noleak"), 160, leak=False, seed=1)
    out = tmp_path_factory.mktemp("noleak_out")
    code = main(["run", str(d), "--out", str(out), "--strip", "--attributes", "role,workflow",
                 "--margin", "0.15", *FAST])
    return code, json.loads((out / "report.json").read_text()), out


def test_verdict_rule():
    assert verdict(0.40, 0.60, 0.25, 0.05) == LEAK
    assert verdict(0.20, 0.30, 0.25, 0.05) == NO_LEAK
    assert verdict(0.20, 0.31, 0.25, 0.05) == INCONCLUSIVE
    assert verdict(0.31, 0.50, 0.25, 0.10) == INCONCLUSIVE          # the margin is configurable


def test_known_leak_is_found_and_attributed(leak_report):
    code, rep, out = leak_report
    assert code == 0
    wf, role = rep["attributes"]["workflow"], rep["attributes"]["role"]
    assert wf["verdict"] == LEAK and role["verdict"] == LEAK
    assert wf["validation"]["permutation"]["p_value"] <= 0.1
    assert wf["attribution"]["single_request_size"]["matches_all"]
    assert "pad-task-inputs" in [h["id"] for h in wf["mitigations"]]
    assert wf["prioritization"]["severity"] == "high"
    assert rep["attributes"]["topology"]["verdict"] != LEAK              # topology labels are noise
    assert rep["collection"]["stripped_copies"] == 60
    for f in ("report.json", "report.md", "report.html"):
        assert (out / f).stat().st_size > 0
    assert "**LEAK**" in (out / "report.md").read_text()


def test_known_no_leak_permuted_labels(noleak_report):
    code, rep, _ = noleak_report
    assert code == 0
    for attr in ("workflow", "role"):
        r = rep["attributes"][attr]
        assert r["verdict"] == NO_LEAK, (attr, r["reason"])
        assert r["validation"]["permutation"]["false_positive_rate"] == 0.0


def test_runtime_and_memory_are_recorded(leak_report):
    rt = leak_report[1]["runtime"]
    assert rt["total_s"] > 0 and rt["peak_rss_mb"] > 0
    assert set(rt["stages_s"]) == {"collection", "extraction", "analysis"}
    assert set(rt["peak_rss_by_stage_mb"]) == {"collection", "extraction", "analysis:role",
                                               "analysis:workflow", "analysis:topology"}


def test_gbt_leaf_size_allows_a_split_on_small_folds():
    assert gbt_min_leaf(345, 4) == 20                     # full collections keep the repository's GBT
    assert gbt_min_leaf(32, 2) == 8                       # 40 traces, 5 folds: 20 per leaf could not split


def test_small_separable_data_is_not_an_all_clear():
    """40 samples, 2 classes, one feature that separates them: GBT with 20 per leaf would predict
    one class (macro-F1 1/3) and read NO LEAK."""
    rng = np.random.default_rng(0)
    y = np.array(["a", "b"] * 20)
    X = np.c_[np.where(y == "a", 0.0, 1.0) + rng.normal(0, 0.05, 40), rng.normal(size=(40, 5))]
    g = np.array([f"g{i}" for i in range(40)])
    cfg = Config(permutations=19, n_boot=200, jobs=1)
    r = analyze(X, y, g, {}, None, cfg, {})
    assert r["verdict"] == LEAK, r["reason"]
    assert r["attribution"] is None                       # no families, no single feature


def test_contradicted_no_leak_is_inconclusive(monkeypatch):
    """A NO LEAK the permutation test contradicts (its model finds a signal) is INCONCLUSIVE."""
    import a2a_leakcheck.analyze as an
    rng = np.random.default_rng(1)
    y = np.array(["a", "b"] * 30)
    X = np.c_[np.where(y == "a", 0.0, 1.0), rng.normal(size=(60, 3))]
    g = np.array([f"g{i}" for i in range(60)])
    real_oof = an._oof

    def blind_main_model(X, y, splits, cfg, model=None):     # the main model sees nothing
        if model is None:
            return np.array([y[0]] * len(y), dtype=object)
        return real_oof(X, y, splits, cfg, model)
    monkeypatch.setattr(an, "_oof", blind_main_model)
    r = an.analyze(X, y, g, {}, None, Config(permutations=19, n_boot=200, jobs=1), {})
    assert r["verdict"] == INCONCLUSIVE and "the two models disagree" in r["reason"]


def test_role_within_one_topology(tmp_path):
    """A gateway-like view: chain traces carry only the executor, star traces all three agents.
    role_within_star scores the star traces' agents alone, next to the pooled role score, and the
    pooled role section says the agents seen differ by topology."""
    rng = np.random.default_rng(3)
    d = tmp_path / "gw"
    d.mkdir()
    for i in range(60):
        top = "star" if i % 2 else "chain"
        wrpcap(str(d / f"t{i:04d}.pcap"), _trace(i, "alpha", rng, ROLES if top == "star" else ("executor",)))
        (d / f"t{i:04d}.json").write_text(json.dumps({
            "run_id": f"t{i:04d}", "workflow_class": "alpha", "topology": top, "input_prompt": f"prompt {i}",
            "agent_endpoints": {"orchestrator": f"10.0.0.1:{ORCH}", **{r: f"10.0.0.2:{p}" for r, p in ROLES.items()}},
            "success": True}))
    out = tmp_path / "out"
    assert main(["run", str(d), "--out", str(out), "--strip", "--attributes", "role", "--role-within", "star", *FAST]) == 0
    rep = json.loads((out / "report.json").read_text())
    assert list(rep["attributes"]) == ["role", "role_within_star"]
    pooled, star = rep["attributes"]["role"], rep["attributes"]["role_within_star"]
    assert pooled["validation"]["min_samples"]["per_class"] == {"executor": 60, "retriever": 30, "validator": 30}
    assert star["validation"]["min_samples"]["per_class"] == {"executor": 30, "retriever": 30, "validator": 30}
    assert star["within_topology"] == "star" and star["verdict"] == LEAK
    assert any(h["id"] == "role-endpoints" for h in star["mitigations"])
    md = (out / "report.md").read_text()
    assert "The agents seen differ by topology (chain: executor; star: executor, retriever, validator)" in md
    assert "Role scored on the star traces only (90 agent samples" in md
    with pytest.raises(SystemExit, match="no trace has topology mesh"):
        main(["run", str(d), "--out", str(out), "--strip", "--attributes", "role", "--role-within", "mesh", *FAST])


def test_minimum_sample_check(tmp_path):
    d = make_dataset(tmp_path / "small", 12)
    main(["run", str(d), "--out", str(tmp_path / "o"), "--strip", "--attributes", "workflow", *FAST])
    r = json.loads((tmp_path / "o" / "report.json").read_text())["attributes"]["workflow"]
    assert r["verdict"] == INCONCLUSIVE and "too few samples" in r["reason"]
    assert "collect-more" in [h["id"] for h in r["mitigations"]]


def test_payload_captures_are_refused_without_strip(tmp_path):
    d = make_dataset(tmp_path / "raw", 4)
    with pytest.raises(SystemExit, match="payload bytes"):
        main(["run", str(d), "--out", str(tmp_path / "o"), "--attributes", "workflow", *FAST])


def _with_verdict(report, **verdicts):
    r = json.loads(json.dumps(report))
    for k, v in verdicts.items():
        r["attributes"][k]["verdict"] = v
    r["summary"] = {v: [k for k, x in r["attributes"].items() if x["verdict"] == v] for v in (LEAK, NO_LEAK, INCONCLUSIVE)}
    return r


def test_repeat_mode_exits_3_on_a_new_leak(leak_report, tmp_path):
    new, old = tmp_path / "new.json", tmp_path / "old.json"
    new.write_text(json.dumps(leak_report[1]))
    old.write_text(json.dumps(_with_verdict(leak_report[1], workflow=NO_LEAK)))
    assert main(["diff", str(new), str(old)]) == 3                    # workflow: NO LEAK → LEAK
    assert main(["diff", str(new), str(new)]) == 0
    assert main(["diff", str(old), str(new)]) == 0                    # a resolved leak is not a failure


def test_repeat_mode_refuses_reports_that_are_not_comparable(leak_report, noleak_report, capsys):
    new, old = leak_report[2] / "report.json", noleak_report[2] / "report.json"
    assert main(["diff", str(new), str(old)]) == 4                    # margin 0.05 vs 0.15
    out = capsys.readouterr().out
    assert "not comparable" in out and "parameters.margin 0.05 vs 0.15" in out
    d = diff(leak_report[1], noleak_report[1], "old.json")
    assert not d["compatible"] and d["changes"] == [] and d["new_leaks"] == []


def _report(**verdicts):
    return {"attributes": {k: {"verdict": v} for k, v in verdicts.items()},
            "summary": {v: [k for k, x in verdicts.items() if x == v] for v in (LEAK, NO_LEAK, INCONCLUSIVE)}}


def test_diff_lists_leak_to_inconclusive_for_review_not_as_resolved():
    old = _report(a=LEAK, b=LEAK, c=NO_LEAK, d=INCONCLUSIVE, e=LEAK)
    new = _report(a=INCONCLUSIVE, b=NO_LEAK, c=INCONCLUSIVE, d=LEAK, e=LEAK, f=LEAK)
    d = diff(new, old, "old.json")
    assert d["needs_review"] == [{"attribute": "a", "before": LEAK, "after": INCONCLUSIVE, "reason": "inconclusive"}]
    assert d["resolved"] == ["b"]                     # LEAK → NO LEAK
    assert d["new_leaks"] == ["d", "f"]               # INCONCLUSIVE → LEAK, absent → LEAK
    assert {x["attribute"] for x in d["changes"]} == {"a", "b", "c", "d", "f"}


def test_diff_lists_a_missing_leak_for_review():
    old = _report(a=LEAK, b=NO_LEAK, c=INCONCLUSIVE, d=LEAK)
    new = _report(d=LEAK)
    d = diff(new, old, "old.json")
    assert d["needs_review"] == [{"attribute": "a", "before": LEAK, "after": "absent", "reason": "missing"}]
    assert {(x["attribute"], x["after"]) for x in d["changes"]} == {("a", "absent"), ("b", "absent"), ("c", "absent")}
    assert d["new_leaks"] == [] and d["resolved"] == []
    st = release_policy(new, d)
    assert st["release_policy"]["exit_code"] == 0                      # listed for review, not a failure
    assert st["for_review"] == [{"attribute": "a", "reason": "missing; LEAK in the baseline"}]


def test_leak_to_inconclusive_does_not_fail_and_is_reported(tmp_path, capsys):
    old, new = tmp_path / "old.json", tmp_path / "new.json"
    old.write_text(json.dumps(_report(workflow=LEAK, role=LEAK)))
    new.write_text(json.dumps(_report(workflow=INCONCLUSIVE, role=LEAK)))
    assert main(["diff", str(new), str(old)]) == 0                    # INCONCLUSIVE never fails a run by default
    out = capsys.readouterr().out
    assert "workflow: LEAK → INCONCLUSIVE" in out
    assert "needs review: workflow (LEAK → INCONCLUSIVE, inconclusive)" in out
    assert main(["diff", str(new), str(old), "--strict"]) == 5        # unless the policy is strict
    assert main(["diff", str(new), str(old), "--require", "role"]) == 0
    assert main(["diff", str(new), str(old), "--require", "workflow"]) == 5
    assert main(["diff", str(new), str(old), "--require", "topology"]) == 5


def test_report_lists_needs_review_against_the_baseline(leak_report, tmp_path):
    report = _with_verdict(leak_report[1], workflow=INCONCLUSIVE)
    report["diff"] = diff(report, leak_report[1], "base.json")
    report["status"] = release_policy(report, report["diff"])
    write_markdown(report, tmp_path / "report.md")
    md = (tmp_path / "report.md").read_text()
    assert "- workflow: LEAK → INCONCLUSIVE" in md
    assert "**Needs review**: workflow (LEAK in the baseline, INCONCLUSIVE now: the leak is not shown to be gone)." in md
    assert "Resolved" not in md
    assert "**Release policy satisfied** (baseline); exit 0." in md
    assert "**For review**: " in md and "workflow (INCONCLUSIVE; LEAK in the baseline)" in md


def _params(**kw):
    p = {"margin": 0.05, "alpha": 0.05, "permutations": 99, "null_model": "rf-light", "model": "gbt", "folds": 5,
         "n_boot": 1000, "min_per_class": 20, "seed": 42, "jobs": -1}
    return {**p, **kw}


def _full(params=None, vantage="v2", classes=("x", "y"), extraction=None):
    return {"parameters": params or _params(), "input": {"vantage": vantage},
            "extraction": extraction or {"schema_version": 1, "trace_dims": 195, "role_dims": 35,
                                         "measurement": "own", "retransmissions": "dropped"},
            "attributes": {"t": {"verdict": LEAK, "classes": list(classes)}}}


def test_compatibility_names_each_field_that_differs():
    base = _full()
    assert compatibility(_full(_params(seed=7, jobs=4)), base) == []       # seed and workers do not matter
    assert compatibility(_full(classes=("y", "x")), base) == []            # class order does not matter
    fields = [x["field"] for x in compatibility(_full(_params(margin=0.1, null_model="gbt"), "v1", ("x", "z")), base)]
    assert fields == ["parameters.margin", "parameters.null_model", "input.vantage", "attributes.t.classes"]
    other = _full(extraction={"schema_version": 2, "trace_dims": 195, "role_dims": 35,
                              "measurement": "own", "retransmissions": "dropped"})
    assert [x["field"] for x in compatibility(other, base)] == ["features.schema_version"]
    old = _full(extraction={"trace_dims": 195, "role_dims": 35, "measurement": "own", "retransmissions": "dropped"})
    assert compatibility(old, base) == []                                  # 0.1.x reports: schema 1


def test_release_policy_exit_codes_and_precedence():
    r = _report(a=LEAK, b=INCONCLUSIVE)
    code = lambda **kw: release_policy(r, **kw)["release_policy"]["exit_code"]   # noqa: E731
    assert code() == 0 and not release_policy(r)["release_policy"]["configured"]
    assert code(fail_on_leak=True) == 2
    assert code(strict=True) == 5
    assert code(require=["a"]) == 0 and code(require=["b"]) == 5 and code(require=["c"]) == 5
    assert code(fail_on_leak=True, strict=True) == 2                       # a LEAK outranks an INCONCLUSIVE
    new_leak = diff(r, _report(a=NO_LEAK, b=INCONCLUSIVE), "old")
    assert code(d=new_leak, fail_on_leak=True, strict=True) == 3
    refused = {**new_leak, "compatible": False, "incompatible": [{"field": "parameters.margin", "new": 0.05, "baseline": 0.1}]}
    assert code(d=refused, fail_on_leak=True) == 4
    st = release_policy(r, strict=True)
    assert st["audit_completed"] and not st["release_policy"]["satisfied"]
    assert st["release_policy"]["failures"] == [{"check": "strict", "exit": 5, "reason": "INCONCLUSIVE: b"}]


def test_strict_and_require_in_a_run(tmp_path):
    d = make_dataset(tmp_path / "small", 12)
    args = ["run", str(d), "--strip", "--attributes", "workflow", *FAST]
    assert main([*args, "--out", str(tmp_path / "a")]) == 0                # INCONCLUSIVE: too few samples
    assert main([*args, "--out", str(tmp_path / "b"), "--strict"]) == 5
    assert main([*args, "--out", str(tmp_path / "c"), "--require", "topology"]) == 5
    r = json.loads((tmp_path / "c" / "report.json").read_text())
    assert [f["reason"] for f in r["status"]["release_policy"]["failures"]] == ["required, missing: topology"]
    md = (tmp_path / "b" / "report.md").read_text()
    assert "**Audit completed**: 1 attributes, 0 LEAK, 0 NO LEAK, 1 INCONCLUSIVE." in md
    assert "**Release policy not satisfied**, exit 5: INCONCLUSIVE: workflow." in md
    assert "**Release policy**: none configured" in (tmp_path / "a" / "report.md").read_text()


def test_extract_then_run_gives_the_same_report(tmp_path):
    d = make_dataset(tmp_path / "data", 40, leak=True)
    common = ["--attributes", "role,workflow", "--strip"]
    assert main(["run", str(d), "--out", str(tmp_path / "once"), *common, *FAST]) == 0
    assert main(["extract", str(d), "--out", str(tmp_path / "features"), *common]) == 0
    assert main(["run", str(tmp_path / "features"), "--out", str(tmp_path / "split"), *FAST]) == 0
    a = json.loads((tmp_path / "split" / "report.json").read_text())
    b = json.loads((tmp_path / "once" / "report.json").read_text())
    c = compare(a, b)
    assert c["same"], c["differences"][:5]
    assert a["input"]["features"] == str(tmp_path / "features") and a["input"]["folder"] == str(d)
    assert a["parameters"]["strip"] is True and a["extraction"]["schema_version"] == 1
    with pytest.raises(SystemExit, match="other settings"):
        main(["run", str(tmp_path / "features"), "--out", str(tmp_path / "x"), "--keep-retransmissions", *FAST])
    with pytest.raises(SystemExit, match="not extracted: topology"):
        main(["run", str(tmp_path / "features"), "--out", str(tmp_path / "x"), "--attributes", "topology", *FAST])


def test_rules_file_is_configurable(tmp_path, leak_report):
    rules = tmp_path / "rules.yaml"
    rules.write_text("severity: {high: 0.99, medium: 0.98}\nrules:\n"
                     "  - {id: timing-only, when: {verdict: LEAK, top_family: [timing]}, hint: t}\n"
                     "  - {id: any-leak, when: {verdict: LEAK, attribute: [workflow, role]}, hint: x}\n")
    r = load_rules(rules)
    wf = leak_report[1]["attributes"]["workflow"]
    assert wf["attribution"]["top_family"] == "sizes"
    assert [h["id"] for h in hints(facts("workflow", wf), r)] == ["any-leak"]
    assert r["severity"]["high"] == 0.99


def _result(verdict="LEAK", top="sizes", single=False, matches=("sizes",)):
    fams = {f: {"all_minus_this": {"ci_lo": -0.01 if f in matches else 0.02}} for f in ("sizes", "timing", "counts_direction")}
    return {"verdict": verdict, "prioritization": {"severity": "high"}, "validation": {"min_samples": {"ok": True}},
            "attribution": {"top_family": top, "top_family_matches_all": True, "families": fams,
                            "single_request_size": {"matches_all": single}}}


def _ids(attribute, result, ctx=None):
    return [h["id"] for h in hints(facts(attribute, result, ctx), load_rules())]


def test_c2_rules_escalation_and_cloud_role_are_final():
    assert _ids("escalated", _result(single=True)) == ["hide-escalation"]            # not pad-task-inputs
    assert _ids("cloud_role", _result(top="timing", single=True)) == ["one-cloud-front-end"]
    assert _ids("escalated", _result(verdict="NO LEAK")) == []


def test_c2_rules_timing_after_padding_and_local_posts():
    padded = {"vantage": "v2", "padded": True, "unpadded_in_view": False}
    v1 = {"vantage": "v1", "padded": True, "unpadded_in_view": True}
    timing = _result(top="timing", matches=("timing",))
    assert _ids("task_type", timing, padded) == ["padding-not-enough-timing"]         # not the generic shape-timing
    assert _ids("task_type", timing, v1) == ["padding-not-enough-timing", "pad-local-posts"]
    assert _ids("task_type", timing) == ["shape-timing"]                               # unpadded: unchanged
    assert _ids("task_type", _result(), v1) == ["pad-messages", "pad-local-posts"]
    assert _ids("task_type", _result(), {"vantage": "v1", "padded": False, "unpadded_in_view": False}) == ["pad-messages"]


def test_padding_context_from_sidecars(tmp_path):
    from a2a_leakcheck.collect import read_trace
    from a2a_leakcheck.rules import context
    eps = {"diagnostics": "172.30.0.100:8101", "ticket": "10.0.0.228:8105"}
    views = {"v1": ["diagnostics", "ticket"], "v2": ["diagnostics"]}
    for name, pad in (("p", [8192]), ("u", [])):
        (tmp_path / f"{name}.pcap").write_bytes(b"")
        (tmp_path / f"{name}.json").write_text(json.dumps({"agent_endpoints": eps, "vantages": views, "pad_buckets": pad,
                                                          "padded_endpoints": ["diagnostics"] if pad else []}))
    p1, _ = read_trace(tmp_path / "p.pcap", [], "v1")
    p2, _ = read_trace(tmp_path / "p.pcap", [], "v2")
    u1, _ = read_trace(tmp_path / "u.pcap", [], "v1")
    assert (p1.padded, p1.unpadded_in_view, p2.unpadded_in_view, u1.padded) == (True, ("ticket",), (), False)
    assert context([p1], "v1") == {"vantage": "v1", "padded": True, "unpadded_in_view": True}
    assert context([p2], "v2")["unpadded_in_view"] is False
    assert context([p1, u1], "v1")["padded"] is False                                 # every trace must be padded


# ── 0.3.0: group-level permutation, per-index seeds, adaptive test, non-inferiority match ────────────

def _grouped(seed=0):
    rng = np.random.default_rng(seed)
    g = np.array([f"g{i}" for i in range(30)] + [f"p{i // 2}" for i in range(20)])        # 30 singletons, 10 pairs
    y = np.array(["a", "b", "c"] * 10 + [x for i in range(10) for x in ("a", "a") if i < 5]
                 + [x for i in range(10) for x in ("b", "b") if i >= 5])
    return y, g, rng


def test_group_permutation_moves_whole_group_labels():
    from a2a_leakcheck.analyze import group_plan, permute_group
    y, g, _ = _grouped()
    plan = group_plan(y, g)
    assert plan["groups"] == 40 and plan["within_groups"] == 0 and plan["sizes"] == {1: 30, 2: 10}
    group_label = lambda lab: sorted(lab[g == k][0] for k in set(g.tolist()))      # noqa: E731
    changed = 0
    for i in range(20):
        yp = permute_group(y, plan, np.random.default_rng(i))
        for k in set(g.tolist()):
            assert len(set(yp[g == k].tolist())) == 1                         # a group keeps one label
        assert group_label(yp) == group_label(y)                              # groups per class kept
        changed += int((yp != y).any())
    assert changed == 20


def test_group_permutation_permutes_within_groups_whose_labels_vary():
    from a2a_leakcheck.analyze import group_plan, permute_group
    g = np.repeat([f"t{i}" for i in range(12)], 4)                            # role samples: 4 agents a trace
    y = np.tile(["executor", "retriever", "validator", "orchestrator"], 12)
    plan = group_plan(y, g)
    assert plan["within_groups"] == 12 and plan["const"] == []
    yp = permute_group(y, plan, np.random.default_rng(3))
    assert all(sorted(yp[g == k]) == sorted(y[g == k]) for k in set(g.tolist()))
    assert (yp != y).any()                       # not the identity, unlike swapping whole sequences


def test_permutations_are_indexed_and_the_sample_unit_keeps_the_0_1_stream():
    from a2a_leakcheck.analyze import permutations
    y, g, _ = _grouped()
    cfg = Config(perm_unit="group")
    ten = permutations(y, g, cfg, 0, 10)
    assert all((a == b).all() for a, b in zip(permutations(y, g, cfg, 0, 5), ten[:5]))
    assert all((a == b).all() for a, b in zip(permutations(y, g, cfg, 5, 10), ten[5:]))
    rng = np.random.default_rng(42)
    legacy = [rng.permutation(y) for _ in range(10)]
    assert all((a == b).all() for a, b in zip(permutations(y, g, Config(perm_unit="sample"), 0, 10), legacy))


def test_match_rule_is_non_inferiority_and_keeps_the_old_rule_apart():
    from a2a_leakcheck.analyze import matches
    assert matches({"ci_lo": -0.01, "ci_hi": 0.031}, 0.05) == {"matches_all": True, "no_detected_deficit": True}
    assert matches({"ci_lo": -0.010, "ci_hi": 0.062}, 0.05) == {"matches_all": False, "no_detected_deficit": True}
    assert matches({"ci_lo": 0.003, "ci_hi": 0.031}, 0.05) == {"matches_all": True, "no_detected_deficit": False}


def test_adaptive_permutations_extend_a_p_value_in_the_window():
    rng = np.random.default_rng(0)
    X, y = rng.normal(size=(80, 4)), np.array(["a", "b"] * 40)
    g = np.array([f"g{i}" for i in range(80)])
    base = dict(permutations=9, n_boot=100, jobs=2, model="rf-light")
    r = analyze(X, y, g, {}, None, Config(**base, perm_max=19, perm_window=(0.0, 1.0)), {})
    perm = r["validation"]["permutation"]
    assert perm["permutations_run"] == 19 and "p_value_first" in perm
    r = analyze(X, y, g, {}, None, Config(**base, perm_max=19, perm_window=(0.0, 0.0)), {})
    assert r["validation"]["permutation"]["permutations_run"] == 9


def test_fold_seed_changes_only_the_split():
    from a2a_leakcheck.analyze import _splits
    y, g, _ = _grouped()
    a, b = _splits(y, g, Config()), _splits(y, g, Config(fold_seed=43))
    assert [sorted(te) for _, te in a] != [sorted(te) for _, te in b]
    assert [sorted(te) for _, te in a] == [sorted(te) for _, te in _splits(y, g, Config(fold_seed=42))]


def test_a_0_1_report_is_not_comparable_with_a_group_permutation_one():
    old, new = _full(), _full(_params(perm_unit="group", perm_max=0))
    assert [x["field"] for x in compatibility(new, old)] == ["parameters.perm_unit"]
    assert compatibility(_full(_params(perm_unit="sample", perm_max=0)), old) == []
