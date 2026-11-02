"""a2a-leakcheck on synthetic captures with a known leak and a known no-leak.

The fixture writes TLS-like traces (handshake, one request, a streamed response) for three
agents. With leak=True the request size follows the workflow and the response pattern follows
the role. The no-leak set is the same traffic with permuted labels: the workflow labels are
shuffled across traces and the roles across each trace's ports, so nothing predicts them.
"""

import json

import numpy as np
import pytest

from a2a_leakcheck.analyze import INCONCLUSIVE, LEAK, NO_LEAK, verdict
from a2a_leakcheck.cli import main
from a2a_leakcheck.rules import facts, hints, load_rules

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


def _trace(i, workflow, rng):
    pkts, t0 = [], 1000.0 + 10 * i
    for k, (role, port) in enumerate(ROLES.items()):
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
    """n traces, half alpha and half beta; topology labels are random noise."""
    rng = np.random.default_rng(seed)
    folder.mkdir(parents=True, exist_ok=True)
    workflows = ["alpha" if i % 2 == 0 else "beta" for i in range(n)]
    labels = list(rng.permutation(workflows)) if not leak else workflows
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


def test_repeat_mode_exits_3_on_a_new_leak(leak_report, noleak_report, tmp_path):
    new, old = leak_report[2] / "report.json", noleak_report[2] / "report.json"
    assert main(["diff", str(new), str(old)]) == 3                    # workflow, role: NO LEAK → LEAK
    assert main(["diff", str(new), str(new)]) == 0
    assert main(["diff", str(old), str(new)]) == 0                    # a resolved leak is not a failure


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
