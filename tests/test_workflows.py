"""Workflow sets: the classic prompts are unchanged, the IoT generators are deterministic and sized
as designed, and the session collector resolves --workflows."""

import hashlib

import pytest

from scripts.collect_session import resolve_workflows
from workflows import CLASSIC_WORKFLOWS, WORKFLOW_REGISTRY, WORKFLOW_SETS, WorkflowClass, prompt_seed

TOPOLOGIES = ["star", "chain", "mesh"]


def _draw(workflow, offset, n=50):
    return [p for t in TOPOLOGIES
            for p in WORKFLOW_REGISTRY[workflow]().sample_prompts(n=n, seed=prompt_seed(TOPOLOGIES.index(t), workflow, offset))]


def test_classic_seed_formula_is_unchanged():
    """Every collection up to C1 used topology_index × 4 + index in the (then four-member) enum + 100 +
    offset; the classic set must keep giving those seeds and prompts."""
    old_order = ["research_retrieval", "code_review", "data_analysis", "support_triage"]
    assert [w.value for w in CLASSIC_WORKFLOWS] == old_order == [w.value for w in list(WorkflowClass)[:4]]
    for t in range(3):
        for i, w in enumerate(old_order):
            assert prompt_seed(t, w, 10000) == t * 4 + i + 100 + 10000
    # the first star prompt of each workflow in C1 (seed offset 10000), as in data/raw_c1's sidecars
    c1_first = {"research_retrieval": "0515b1e2", "code_review": "ef3697aa", "data_analysis": "4f0a4755",
                "support_triage": "d3fbf03f"}
    for w in CLASSIC_WORKFLOWS:
        p = WORKFLOW_REGISTRY[w]().sample_prompts(n=1, seed=prompt_seed(0, w, 10000))[0]
        assert hashlib.sha1(p.encode()).hexdigest()[:8] == c1_first[w.value]


def test_iot_generators_are_deterministic_sized_and_disjoint():
    classic = {p for w in CLASSIC_WORKFLOWS for p in _draw(w, 20000, n=10)}
    bounds = {"sensor_analysis": (300, 8000), "fault_diagnosis": (1500, 8000),
              "procedure_lookup": (30, 300), "alert_triage": (80, 400)}
    medians = {}
    for w in WORKFLOW_SETS["iot"]:
        ps = _draw(w, 20000)
        assert ps == _draw(w, 20000)                                     # fixed seed, same prompts
        sizes = sorted(len(p.encode()) for p in ps)
        lo, hi = bounds[w.value]
        assert lo <= sizes[0] and sizes[-1] <= hi, (w, sizes[0], sizes[-1])
        assert len(set(ps)) >= 0.9 * len(ps)                             # varied content
        assert not set(ps) & classic
        assert WORKFLOW_REGISTRY[w].template_pools
        medians[w.value] = sizes[len(sizes) // 2]
    # same design as the classic set: two long-input workflows, two short-input ones
    assert min(medians["sensor_analysis"], medians["fault_diagnosis"]) > 5 * max(
        medians["procedure_lookup"], medians["alert_triage"])
    # under the top padding bucket (32 KB) with room for the request envelope
    assert max(len(p.encode()) for w in WORKFLOW_SETS["iot"] for p in _draw(w, 20000)) < 16384


def test_resolve_workflows():
    assert resolve_workflows("iot", None) == ["sensor_analysis", "fault_diagnosis", "procedure_lookup", "alert_triage"]
    assert resolve_workflows("classic", None) == [w.value for w in CLASSIC_WORKFLOWS]
    assert resolve_workflows("alert_triage,sensor_analysis", None) == ["alert_triage", "sensor_analysis"]
    assert resolve_workflows("iot", "alert_triage") == ["alert_triage"]
    for bad in ("nope", "code_review,alert_triage"):
        with pytest.raises(SystemExit):
            resolve_workflows(bad, None)
    with pytest.raises(SystemExit):
        resolve_workflows("classic", "alert_triage")
