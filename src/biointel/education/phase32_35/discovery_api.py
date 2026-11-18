from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..paths import education_paths
from .api_context import require_tenant
from .base import Conflict, Missing, PermissionDenied, ResearchPlatformError
from .discovery import DiscoveryEcosystem

router = APIRouter(prefix="/phase35", tags=["Education Phase 35 Scientific Discovery"])
_DISCOVERY: DiscoveryEcosystem | None = None


def discovery() -> DiscoveryEcosystem:
    global _DISCOVERY
    if _DISCOVERY is None:
        database, media = education_paths()
        _DISCOVERY = DiscoveryEcosystem(database, media)
    return _DISCOVERY


def run(operation):
    try:
        return operation()
    except PermissionDenied as exc:
        raise HTTPException(403, detail={"code": "permission_denied", "message": str(exc)}) from exc
    except Missing as exc:
        raise HTTPException(404, detail={"code": "not_found", "message": str(exc)}) from exc
    except Conflict as exc:
        raise HTTPException(409, detail={"code": "conflict", "message": str(exc)}) from exc
    except ResearchPlatformError as exc:
        raise HTTPException(
            422,
            detail={"code": "validation_error", "message": str(exc)},
        ) from exc


def require_resource_tenant(
    request: Request,
    sql: str,
    parameters: tuple[Any, ...],
) -> None:
    row = discovery().store.one(sql, parameters)
    if not row:
        raise HTTPException(404, detail="Scientific Discovery resource not found.")
    require_tenant(request, row["tenant_id"])


class WorkspaceRequest(BaseModel):
    research_project_id: str
    owner_id: str
    title: str = ""
    policy: dict[str, Any] = Field(default_factory=dict)


class EvidenceRequest(BaseModel):
    actor_id: str
    source_type: str
    title: str
    citation: str
    abstract_text: str
    methodology_text: str = ""
    limitations_text: str = ""
    claims: list[str] = Field(default_factory=list)
    persistent_identifier: str = ""
    publication_date: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    retraction_status: str = "not_checked"


class SearchRequest(BaseModel):
    actor_id: str
    topic: str
    source_types: list[str] = Field(default_factory=list)
    include_retracted: bool = False
    limit: int = Field(default=50, ge=1, le=500)


class AgentTaskRequest(BaseModel):
    requested_by: str
    agent_key: str
    task_input: dict[str, Any]
    evidence_ids: list[str] = Field(default_factory=list)
    requested_permissions: list[str] = Field(default_factory=list)
    idempotency_key: str = Field(min_length=1, max_length=240)
    phase24_parent_task_id: str = ""


class ReviewRequest(BaseModel):
    reviewer_id: str
    reviewer_role: str
    operation: str = "task_output_review"
    decision: str
    note: str = ""


class NoveltyRequest(BaseModel):
    actor_id: str
    queries: list[str] = Field(min_length=1)
    related_hypothesis_ids: list[str] = Field(default_factory=list)


class HypothesisCreateRequest(BaseModel):
    actor_id: str
    novelty_search_id: str | None = None


class HypothesisTransitionRequest(BaseModel):
    actor_id: str
    actor_role: str
    new_state: str
    outcome: str = ""
    results: dict[str, Any] = Field(default_factory=dict)


class HypothesisLinksRequest(BaseModel):
    actor_id: str
    dataset_ids: list[str] = Field(default_factory=list)
    workflow_ids: list[str] = Field(default_factory=list)
    digital_twin_scenario_ids: list[str] = Field(default_factory=list)
    results: dict[str, Any] = Field(default_factory=dict)


class ExperimentRequest(BaseModel):
    actor_id: str
    objective: str
    design: dict[str, Any]
    variables: dict[str, Any] = Field(default_factory=dict)
    controls: list[Any]
    samples: dict[str, Any] = Field(default_factory=dict)
    replicates: dict[str, Any] = Field(default_factory=dict)
    randomization: dict[str, Any] = Field(default_factory=dict)
    blinding: dict[str, Any] = Field(default_factory=dict)
    inclusion_criteria: list[str] = Field(default_factory=list)
    exclusion_criteria: list[str] = Field(default_factory=list)
    endpoints: list[dict[str, Any]]
    analysis_plan: dict[str, Any] = Field(default_factory=dict)
    resources: dict[str, Any] = Field(default_factory=dict)
    timeline: dict[str, Any] = Field(default_factory=dict)
    risks: list[dict[str, Any]] = Field(default_factory=list)
    ethics_status: str = "pending_specialist_review"
    ethics_record_asset_id: str | None = None
    safety_status: str = "pending_specialist_review"
    protocol_version: str = "1.0.0"


class WorkflowRequest(BaseModel):
    actor_id: str
    research_question: str


class EvaluationRequest(BaseModel):
    actor_id: str


class ConsequentialActionRequest(BaseModel):
    actor_id: str
    operation: str
    target_id: str


@router.get("/capabilities")
def capabilities():
    return {
        "human_supervised": True,
        "autonomous_discovery": False,
        "clinical_validity": False,
        "guaranteed_correctness": False,
        "external_communication": False,
        "provider": "deterministic local evidence runtime",
    }


@router.get("/agents")
def agents():
    return run(lambda: discovery().agent_registry())


@router.post("/workspaces", status_code=201)
def create_workspace(payload: WorkspaceRequest, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p34_research_projects WHERE project_id=?",
        (payload.research_project_id,),
    )
    return run(lambda: discovery().create_workspace(**payload.model_dump()))


@router.get("/tenants/{tenant_id}/workspaces")
def workspaces(tenant_id: str, request: Request):
    require_tenant(request, tenant_id)
    return run(lambda: discovery().workspaces(tenant_id))


@router.post("/workspaces/{workspace_id}/evidence", status_code=201)
def register_evidence(workspace_id: str, payload: EvidenceRequest, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p35_research_workspaces WHERE workspace_id=?",
        (workspace_id,),
    )
    values = payload.model_dump()
    actor_id = values.pop("actor_id")
    return run(lambda: discovery().register_evidence(workspace_id, actor_id, **values))


@router.post("/workspaces/{workspace_id}/literature-searches", status_code=201)
def literature_search(workspace_id: str, payload: SearchRequest, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p35_research_workspaces WHERE workspace_id=?",
        (workspace_id,),
    )
    return run(
        lambda: discovery().search_literature(
            workspace_id,
            payload.actor_id,
            topic=payload.topic,
            source_types=payload.source_types or None,
            include_retracted=payload.include_retracted,
            limit=payload.limit,
        )
    )


@router.post("/workspaces/{workspace_id}/tasks", status_code=201)
def create_task(workspace_id: str, payload: AgentTaskRequest, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p35_research_workspaces WHERE workspace_id=?",
        (workspace_id,),
    )
    values = payload.model_dump()
    requested_by = values.pop("requested_by")
    return run(
        lambda: discovery().create_agent_task(
            workspace_id,
            requested_by,
            **values,
        )
    )


@router.post("/tasks/{task_id}/execute")
def execute_task(task_id: str, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p35_agent_tasks WHERE task_id=?",
        (task_id,),
    )
    return run(lambda: discovery().execute_agent_task(task_id))


@router.get("/tasks/{task_id}")
def task(task_id: str, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p35_agent_tasks WHERE task_id=?",
        (task_id,),
    )
    return run(lambda: discovery().task(task_id))


@router.post("/tasks/{task_id}/approvals")
def decide_approval(task_id: str, payload: ReviewRequest, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p35_agent_tasks WHERE task_id=?",
        (task_id,),
    )
    values = payload.model_dump()
    reviewer_id = values.pop("reviewer_id")
    return run(lambda: discovery().decide_approval(task_id, reviewer_id, **values))


@router.post("/tasks/{task_id}/consequential-actions", status_code=201)
def request_consequential_action(
    task_id: str,
    payload: ConsequentialActionRequest,
    request: Request,
):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p35_agent_tasks WHERE task_id=?",
        (task_id,),
    )
    return run(
        lambda: discovery().request_consequential_action(
            task_id,
            payload.actor_id,
            operation=payload.operation,
            target_id=payload.target_id,
        )
    )


@router.post("/workspaces/{workspace_id}/novelty-searches", status_code=201)
def novelty_search(workspace_id: str, payload: NoveltyRequest, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p35_research_workspaces WHERE workspace_id=?",
        (workspace_id,),
    )
    return run(
        lambda: discovery().record_novelty_search(
            workspace_id,
            payload.actor_id,
            queries=payload.queries,
            related_hypothesis_ids=payload.related_hypothesis_ids,
        )
    )


@router.post("/tasks/{task_id}/hypotheses", status_code=201)
def create_hypothesis(
    task_id: str,
    payload: HypothesisCreateRequest,
    request: Request,
):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p35_agent_tasks WHERE task_id=?",
        (task_id,),
    )
    return run(
        lambda: discovery().create_hypothesis_from_task(
            task_id,
            payload.actor_id,
            novelty_search_id=payload.novelty_search_id,
        )
    )


@router.post("/hypotheses/{hypothesis_id}/transition")
def transition_hypothesis(
    hypothesis_id: str,
    payload: HypothesisTransitionRequest,
    request: Request,
):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p35_hypotheses WHERE hypothesis_id=?",
        (hypothesis_id,),
    )
    values = payload.model_dump()
    actor_id = values.pop("actor_id")
    return run(
        lambda: discovery().transition_hypothesis(
            hypothesis_id,
            actor_id,
            **values,
        )
    )


@router.post("/hypotheses/{hypothesis_id}/links")
def link_hypothesis(
    hypothesis_id: str,
    payload: HypothesisLinksRequest,
    request: Request,
):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p35_hypotheses WHERE hypothesis_id=?",
        (hypothesis_id,),
    )
    values = payload.model_dump()
    actor_id = values.pop("actor_id")
    return run(
        lambda: discovery().link_hypothesis_resources(
            hypothesis_id,
            actor_id,
            **values,
        )
    )


@router.post("/hypotheses/{hypothesis_id}/experiments", status_code=201)
def create_experiment(
    hypothesis_id: str,
    payload: ExperimentRequest,
    request: Request,
):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p35_hypotheses WHERE hypothesis_id=?",
        (hypothesis_id,),
    )
    values = payload.model_dump()
    actor_id = values.pop("actor_id")
    return run(
        lambda: discovery().create_experiment_plan(
            hypothesis_id,
            actor_id,
            **values,
        )
    )


@router.get("/workspaces/{workspace_id}/claim-evidence-graph")
def claim_evidence_graph(workspace_id: str, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p35_research_workspaces WHERE workspace_id=?",
        (workspace_id,),
    )
    return run(lambda: discovery().claim_evidence_graph(workspace_id))


@router.post("/workspaces/{workspace_id}/discovery-workflows", status_code=201)
def create_discovery_workflow(
    workspace_id: str,
    payload: WorkflowRequest,
    request: Request,
):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p35_research_workspaces WHERE workspace_id=?",
        (workspace_id,),
    )
    return run(
        lambda: discovery().create_discovery_workflow(
            workspace_id,
            payload.actor_id,
            research_question=payload.research_question,
        )
    )


@router.post("/workspaces/{workspace_id}/evaluations", status_code=201)
def run_evaluation(
    workspace_id: str,
    payload: EvaluationRequest,
    request: Request,
):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p35_research_workspaces WHERE workspace_id=?",
        (workspace_id,),
    )
    return run(lambda: discovery().run_evaluation_suite(workspace_id, payload.actor_id))
