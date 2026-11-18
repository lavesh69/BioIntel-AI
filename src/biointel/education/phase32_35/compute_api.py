from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ..paths import education_paths
from .api_context import require_tenant
from .base import Conflict, IntegrityFailure, Missing, PermissionDenied, ResearchPlatformError
from .compute import INITIAL_WORKFLOW_LIBRARY, REMOTE_ADAPTER_TYPES, ResearchCompute

router = APIRouter(prefix="/phase34", tags=["Education Phase 34 Research Compute"])
_COMPUTE: ResearchCompute | None = None


def compute() -> ResearchCompute:
    global _COMPUTE
    if _COMPUTE is None:
        database, media = education_paths()
        _COMPUTE = ResearchCompute(database, media)
    return _COMPUTE


def run(operation):
    try:
        return operation()
    except PermissionDenied as exc:
        raise HTTPException(403, detail={"code": "permission_denied", "message": str(exc)}) from exc
    except Missing as exc:
        raise HTTPException(404, detail={"code": "not_found", "message": str(exc)}) from exc
    except Conflict as exc:
        raise HTTPException(409, detail={"code": "conflict", "message": str(exc)}) from exc
    except IntegrityFailure as exc:
        raise HTTPException(
            400,
            detail={"code": "integrity_failure", "message": str(exc)},
        ) from exc
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
    row = compute().store.one(sql, parameters)
    if not row:
        raise HTTPException(404, detail="Research Compute resource not found.")
    require_tenant(request, row["tenant_id"])


class ProjectRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=160)
    owner_id: str = Field(min_length=1, max_length=160)
    institution_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=300)
    hypothesis: str = Field(default="", max_length=5000)
    objectives: list[str] = Field(default_factory=list)
    milestones: list[dict[str, Any]] = Field(default_factory=list)


class DatasetRequest(BaseModel):
    actor_id: str
    title: str = Field(min_length=1, max_length=300)
    source_paths: list[str] = Field(min_length=1, max_length=10_000)
    source: str
    licence: str
    consent_status: str
    access_level: str
    declared_format: str = ""
    description: str = ""
    sample_count: int | None = Field(default=None, ge=0)
    metadata_schema: dict[str, Any] = Field(default_factory=dict)
    data_dictionary: dict[str, Any] = Field(default_factory=dict)
    version: str = "1.0.0"
    lineage: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowRequest(BaseModel):
    actor_id: str
    name: str = Field(min_length=1, max_length=300)
    domain: str = Field(min_length=1, max_length=120)
    version: str = Field(default="1.0.0", min_length=1, max_length=80)
    steps: list[dict[str, Any]] = Field(min_length=1)
    approve: bool = False
    approver_role: str = ""


class RunRequest(BaseModel):
    project_id: str
    workflow_id: str
    dataset_id: str
    user_id: str
    idempotency_key: str = Field(min_length=1, max_length=240)
    parameters: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=50, ge=0, le=100)
    max_retries: int = Field(default=1, ge=0, le=10)
    timeout_seconds: int = Field(default=900, ge=1, le=604_800)
    cpu_limit: int = Field(default=1, ge=1, le=128)
    memory_limit_mb: int = Field(default=1024, ge=128)
    disk_limit_mb: int = Field(default=4096, ge=128)
    gpu_limit: int = Field(default=0, ge=0, le=128)
    seed: int = 42


class ActorRequest(BaseModel):
    actor_id: str


class ResumeImportRequest(ActorRequest):
    max_bytes: int = Field(default=256 * 1024**2, ge=1, le=2 * 1024**3)


class CloneRequest(ActorRequest):
    idempotency_key: str
    parameter_overrides: dict[str, Any] = Field(default_factory=dict)


class NoteRequest(ActorRequest):
    note_type: str
    body: str = Field(min_length=1, max_length=10_000)


class ReviewRequest(BaseModel):
    reviewer_id: str
    reviewer_role: str
    decision: str
    comments: str = Field(default="", max_length=10_000)


class HandoffRequest(ActorRequest):
    destination: str
    payload: dict[str, Any] = Field(default_factory=dict)


class RemoteAdapterRequest(BaseModel):
    tenant_id: str
    administrator_id: str
    administrator_role: str
    adapter_type: str
    endpoint: str
    allowed_hosts: list[str]
    command_templates: list[str]
    credentials: dict[str, Any]
    resource_limits: dict[str, Any] = Field(default_factory=dict)


@router.get("/capabilities")
def capabilities():
    return {
        "execution": "controlled local native worker",
        "remote_adapters": sorted(REMOTE_ADAPTER_TYPES),
        "remote_validation_performed": False,
        "workflow_library": INITIAL_WORKFLOW_LIBRARY,
        "arbitrary_user_shell": False,
        "clinical_interpretation": False,
    }


@router.get("/tools")
def approved_tools():
    return run(lambda: compute().approved_tools())


@router.post("/projects", status_code=201)
def create_project(payload: ProjectRequest, request: Request):
    require_tenant(request, payload.tenant_id)
    return run(lambda: compute().create_project(**payload.model_dump()))


@router.get("/tenants/{tenant_id}/projects")
def projects(tenant_id: str, request: Request):
    require_tenant(request, tenant_id)
    return run(lambda: compute().projects(tenant_id))


@router.get("/projects/{project_id}")
def project_workspace(project_id: str, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p34_research_projects WHERE project_id=?",
        (project_id,),
    )
    return run(lambda: compute().project_workspace(project_id))


def _approved_import_paths(source_paths: list[str]) -> list[Path]:
    configured = os.environ.get("BIOINTEL_RESEARCH_IMPORT_ROOT", "").strip()
    if not configured:
        raise PermissionDenied(
            "Server-path import is disabled; configure BIOINTEL_RESEARCH_IMPORT_ROOT."
        )
    root = Path(configured).resolve()
    resolved = [Path(item).resolve() for item in source_paths]
    if any(not path.is_relative_to(root) for path in resolved):
        raise PermissionDenied("A dataset source is outside the approved import root.")
    return resolved


@router.post("/projects/{project_id}/datasets", status_code=201)
def register_dataset(project_id: str, payload: DatasetRequest, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p34_research_projects WHERE project_id=?",
        (project_id,),
    )
    def operation():
        values = payload.model_dump()
        actor_id = values.pop("actor_id")
        values["source_paths"] = _approved_import_paths(values["source_paths"])
        return compute().register_dataset(project_id, actor_id, **values)

    return run(operation)


@router.post("/projects/{project_id}/dataset-imports", status_code=201)
def begin_dataset_import(project_id: str, payload: DatasetRequest, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p34_research_projects WHERE project_id=?",
        (project_id,),
    )
    def operation():
        values = payload.model_dump()
        actor_id = values.pop("actor_id")
        values["source_paths"] = _approved_import_paths(values["source_paths"])
        return compute().begin_dataset_import(project_id, actor_id, **values)

    return run(operation)


@router.post("/dataset-imports/{session_id}/resume")
def resume_dataset_import(
    session_id: str,
    payload: ResumeImportRequest,
    request: Request,
):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p34_dataset_import_sessions WHERE session_id=?",
        (session_id,),
    )
    return run(
        lambda: compute().resume_dataset_import(
            session_id,
            payload.actor_id,
            max_bytes=payload.max_bytes,
        )
    )


@router.post("/dataset-imports/{session_id}/cancel")
def cancel_dataset_import(
    session_id: str,
    payload: ActorRequest,
    request: Request,
):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p34_dataset_import_sessions WHERE session_id=?",
        (session_id,),
    )
    return run(lambda: compute().cancel_dataset_import(session_id, payload.actor_id))


@router.post("/projects/{project_id}/workflows", status_code=201)
def define_workflow(project_id: str, payload: WorkflowRequest, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p34_research_projects WHERE project_id=?",
        (project_id,),
    )
    values = payload.model_dump()
    actor_id = values.pop("actor_id")
    return run(lambda: compute().define_workflow(project_id, actor_id, **values))


@router.post("/runs", status_code=201)
def submit_run(payload: RunRequest, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p34_research_projects WHERE project_id=?",
        (payload.project_id,),
    )
    return run(lambda: compute().submit_run(**payload.model_dump()))


@router.post("/runs/{run_id}/execute")
def execute_run(run_id: str, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p34_runs WHERE run_id=?",
        (run_id,),
    )
    return run(lambda: compute().execute_run(run_id))


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, payload: ActorRequest, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p34_runs WHERE run_id=?",
        (run_id,),
    )
    return run(lambda: compute().cancel_run(run_id, payload.actor_id))


@router.post("/runs/{run_id}/retry")
def retry_run(run_id: str, payload: ActorRequest, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p34_runs WHERE run_id=?",
        (run_id,),
    )
    return run(lambda: compute().retry_run(run_id, payload.actor_id))


@router.post("/runs/{run_id}/clone", status_code=201)
def clone_run(run_id: str, payload: CloneRequest, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p34_runs WHERE run_id=?",
        (run_id,),
    )
    return run(
        lambda: compute().clone_run(
            run_id,
            payload.actor_id,
            idempotency_key=payload.idempotency_key,
            parameter_overrides=payload.parameter_overrides,
        )
    )


@router.get("/runs/{run_id}")
def result_explorer(run_id: str, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p34_runs WHERE run_id=?",
        (run_id,),
    )
    return run(lambda: compute().result_explorer(run_id))


@router.post("/runs/{run_id}/notes", status_code=201)
def add_note(run_id: str, payload: NoteRequest, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p34_runs WHERE run_id=?",
        (run_id,),
    )
    return run(
        lambda: compute().add_result_note(
            run_id,
            payload.actor_id,
            note_type=payload.note_type,
            body=payload.body,
        )
    )


@router.post("/runs/{run_id}/reviews", status_code=201)
def review_run(run_id: str, payload: ReviewRequest, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p34_runs WHERE run_id=?",
        (run_id,),
    )
    return run(lambda: compute().review_run(run_id, **payload.model_dump()))


@router.post("/runs/{run_id}/handoffs", status_code=201)
def create_handoff(run_id: str, payload: HandoffRequest, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p34_runs WHERE run_id=?",
        (run_id,),
    )
    return run(
        lambda: compute().create_handoff(
            run_id,
            payload.actor_id,
            destination=payload.destination,
            payload=payload.payload,
        )
    )


@router.get("/runs/{run_id}/bundle")
def export_bundle(run_id: str, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p34_runs WHERE run_id=?",
        (run_id,),
    )
    data = run(lambda: compute().export_run_bundle(run_id))
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="biointel-compute-{run_id}.zip"'
        },
    )


@router.post("/tenants/{tenant_id}/imported-run-bundles", status_code=201)
def import_bundle(
    tenant_id: str,
    actor_id: str,
    request: Request,
    data: bytes = Body(media_type="application/zip"),
):
    require_tenant(request, tenant_id)
    return run(lambda: compute().import_run_bundle(tenant_id, actor_id, data))


@router.post("/remote-adapters", status_code=201)
def register_remote_adapter(payload: RemoteAdapterRequest, request: Request):
    require_tenant(request, payload.tenant_id)
    return run(lambda: compute().register_remote_adapter(**payload.model_dump()))


@router.get("/remote-adapters/{adapter_id}")
def remote_adapter_status(adapter_id: str, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p34_remote_adapters WHERE adapter_id=?",
        (adapter_id,),
    )
    return run(lambda: compute().remote_adapter_status(adapter_id))
