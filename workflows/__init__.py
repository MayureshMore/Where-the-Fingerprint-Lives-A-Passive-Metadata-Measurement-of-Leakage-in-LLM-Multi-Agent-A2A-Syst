from .base import CLASSIC_WORKFLOWS, WORKFLOW_SETS, WorkflowClass, WorkflowRun, prompt_seed, workflow_set
from .research_retrieval import ResearchRetrievalWorkflow
from .code_review import CodeReviewWorkflow
from .data_analysis import DataAnalysisWorkflow
from .support_triage import SupportTriageWorkflow
from .sensor_analysis import SensorAnalysisWorkflow
from .fault_diagnosis import FaultDiagnosisWorkflow
from .procedure_lookup import ProcedureLookupWorkflow
from .alert_triage import AlertTriageWorkflow

WORKFLOW_REGISTRY: dict[WorkflowClass, type] = {
    WorkflowClass.RESEARCH_RETRIEVAL: ResearchRetrievalWorkflow,
    WorkflowClass.CODE_REVIEW: CodeReviewWorkflow,
    WorkflowClass.DATA_ANALYSIS: DataAnalysisWorkflow,
    WorkflowClass.SUPPORT_TRIAGE: SupportTriageWorkflow,
    WorkflowClass.SENSOR_ANALYSIS: SensorAnalysisWorkflow,
    WorkflowClass.FAULT_DIAGNOSIS: FaultDiagnosisWorkflow,
    WorkflowClass.PROCEDURE_LOOKUP: ProcedureLookupWorkflow,
    WorkflowClass.ALERT_TRIAGE: AlertTriageWorkflow,
}

__all__ = [
    "WorkflowClass",
    "WorkflowRun",
    "ResearchRetrievalWorkflow",
    "CodeReviewWorkflow",
    "DataAnalysisWorkflow",
    "SupportTriageWorkflow",
    "SensorAnalysisWorkflow",
    "FaultDiagnosisWorkflow",
    "ProcedureLookupWorkflow",
    "AlertTriageWorkflow",
    "WORKFLOW_REGISTRY",
    "WORKFLOW_SETS",
    "CLASSIC_WORKFLOWS",
    "prompt_seed",
    "workflow_set",
]
