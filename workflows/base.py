"""
Base workflow types and the WorkflowRun record that is written alongside each
packet capture for ground-truth labeling.
"""

from __future__ import annotations

import enum
import random
import time
import uuid

from pydantic import BaseModel, Field


class WorkflowClass(str, enum.Enum):
    RESEARCH_RETRIEVAL = "research_retrieval"
    CODE_REVIEW = "code_review"
    DATA_ANALYSIS = "data_analysis"
    SUPPORT_TRIAGE = "support_triage"
    # IoT use case (C2): an edge AI assistant for building and factory operations
    SENSOR_ANALYSIS = "sensor_analysis"
    FAULT_DIAGNOSIS = "fault_diagnosis"
    PROCEDURE_LOOKUP = "procedure_lookup"
    ALERT_TRIAGE = "alert_triage"


# Workflow sets: a collection draws all its workflows from one set. "classic" is every collection
# up to C1 and must not change (its prompts depend on this order); "iot" is C2's use case. Both
# have the same design: two long-input workflows and two short-input ones.
WORKFLOW_SETS: dict[str, tuple[WorkflowClass, ...]] = {
    "classic": (WorkflowClass.RESEARCH_RETRIEVAL, WorkflowClass.CODE_REVIEW,
                WorkflowClass.DATA_ANALYSIS, WorkflowClass.SUPPORT_TRIAGE),
    "iot": (WorkflowClass.SENSOR_ANALYSIS, WorkflowClass.FAULT_DIAGNOSIS,
            WorkflowClass.PROCEDURE_LOOKUP, WorkflowClass.ALERT_TRIAGE),
}
CLASSIC_WORKFLOWS = WORKFLOW_SETS["classic"]


def workflow_set(workflow: str | WorkflowClass) -> str:
    wf = WorkflowClass(workflow)
    return next(name for name, members in WORKFLOW_SETS.items() if wf in members)


def prompt_seed(topology_index: int, workflow: str | WorkflowClass, seed_offset: int) -> int:
    """Seed of one topology × workflow condition's prompt sample: topology_index × 4 + the
    workflow's index in its set + 100 + seed_offset. For the classic set this is the formula every
    collection up to C1 used (with the enum's first four members), so their prompts are unchanged."""
    members = WORKFLOW_SETS[workflow_set(workflow)]
    return topology_index * len(members) + members.index(WorkflowClass(workflow)) + 100 + seed_offset


class TopologyType(str, enum.Enum):
    STAR = "star"
    CHAIN = "chain"
    MESH = "mesh"


class WorkflowRun(BaseModel):
    """Ground-truth record written as JSON alongside every pcap."""
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    workflow_class: WorkflowClass
    topology: TopologyType
    # Participating agents: role → "host:port"
    agent_endpoints: dict[str, str] = {}
    # Directed edges in the interaction graph: list of [src_role, dst_role]
    topology_edges: list[list[str]] = []
    input_prompt: str = ""
    start_ts: float = Field(default_factory=time.time)
    end_ts: float = 0.0
    pcap_path: str = ""
    success: bool = False
    error: str = ""
    # Which agent implementation produced this trace.  Default "a" keeps all
    # existing sidecars (which lack this field) backward-compatible.
    deployment: str = "a"

    def duration_s(self) -> float:
        return self.end_ts - self.start_ts


class BaseWorkflow:
    """
    Abstract workflow.  Sub-classes set `workflow_class` and implement
    `generate_prompt()` to produce varied task inputs for data collection.
    """

    workflow_class: WorkflowClass
    # sizes of the template pools a generator draws from (recorded per collection)
    template_pools: dict[str, int] = {}

    def generate_prompt(self) -> str:
        raise NotImplementedError

    def sample_prompts(self, n: int = 10, seed: int | None = None) -> list[str]:
        if seed is not None:
            random.seed(seed)
        return [self.generate_prompt() for _ in range(n)]
