from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import APIRouter, Query, Request

from .api_schemas import (
    AnalysisRunBody,
    DatasetCreateBody,
    ProjectCreateBody,
    ProjectUpdateBody,
    SampleBatchBody,
    StageGateBody,
    WorkflowCreateBody,
)
from .api_shared import invoke, page, service_for
from .models import ProjectCreate

router = APIRouter()


@router.get("/projects")
def projects(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    stage: str | None = None,
) -> dict[str, Any]:
    items = invoke(
        service_for(request).list_projects,
        limit=limit,
        offset=offset,
        stage=stage,
    )
    return page(items, limit, offset)


@router.post("/projects", status_code=201)
def create_project(request: Request, body: ProjectCreateBody) -> dict[str, Any]:
    return invoke(
        service_for(request).create_project,
        ProjectCreate(**body.model_dump()),
    )


@router.get("/projects/{project_id}")
def project(request: Request, project_id: str) -> dict[str, Any]:
    return invoke(service_for(request).get_project, project_id)


@router.patch("/projects/{project_id}")
def update_project(
    request: Request,
    project_id: str,
    body: ProjectUpdateBody,
) -> dict[str, Any]:
    changes = body.model_dump(exclude_none=True)
    aliases = {
        "assay_types": "assay_types_json",
        "contributors": "contributors_json",
        "reviewers": "reviewers_json",
        "milestones": "milestones_json",
        "risks": "risks_json",
        "blockers": "blockers_json",
    }
    changes = {aliases.get(key, key): value for key, value in changes.items()}
    return invoke(service_for(request).update_project, project_id, **changes)


@router.post("/projects/{project_id}/stage-gates")
def set_stage_gate(
    request: Request,
    project_id: str,
    body: StageGateBody,
) -> dict[str, Any]:
    return invoke(
        service_for(request).set_stage_gate,
        project_id,
        body.stage,
        artifact_ids=body.artifact_ids,
        criteria=body.criteria,
        status=body.status,
        note=body.note,
    )


@router.post("/projects/{project_id}/advance")
def advance_stage(
    request: Request,
    project_id: str,
    target_stage: str | None = None,
) -> dict[str, Any]:
    return invoke(service_for(request).advance_stage, project_id, target_stage)


@router.get("/projects/{project_id}/dashboard")
def dashboard(request: Request, project_id: str) -> dict[str, Any]:
    return invoke(service_for(request).dashboard_summary, project_id)


@router.get("/projects/{project_id}/datasets")
def datasets(
    request: Request,
    project_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    items = invoke(
        service_for(request).list_datasets,
        project_id,
        limit=limit,
        offset=offset,
    )
    return page(items, limit, offset)


@router.post("/projects/{project_id}/datasets", status_code=201)
def create_dataset(
    request: Request,
    project_id: str,
    body: DatasetCreateBody,
) -> dict[str, Any]:
    return invoke(
        service_for(request).register_dataset,
        project_id,
        **body.model_dump(),
    )


@router.get("/samples")
def samples(
    request: Request,
    dataset_id: str | None = None,
    query: str = "",
    qc_status: str | None = None,
    inclusion_status: str | None = None,
    limit: int = Query(default=200, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    items = invoke(
        service_for(request).search_samples,
        dataset_id,
        query=query,
        qc_status=qc_status,
        inclusion_status=inclusion_status,
        limit=limit,
        offset=offset,
    )
    return page(items, limit, offset)


@router.post("/datasets/{dataset_id}/samples", status_code=201)
def add_samples(
    request: Request,
    dataset_id: str,
    body: SampleBatchBody,
) -> dict[str, Any]:
    return invoke(service_for(request).add_samples, dataset_id, body.samples)


@router.get("/projects/{project_id}/workflows")
def workflows(
    request: Request,
    project_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    items = invoke(
        service_for(request).workflows.list_workflows,
        project_id=project_id,
        limit=min(5000, limit + offset),
    )
    return page(items[offset : offset + limit], limit, offset)


@router.post("/projects/{project_id}/workflows", status_code=201)
def create_workflow(
    request: Request,
    project_id: str,
    body: WorkflowCreateBody,
) -> dict[str, Any]:
    service = service_for(request)
    return invoke(
        service.workflows.create,
        project_id=project_id,
        created_by=service.actor,
        **body.model_dump(),
    )


@router.post("/analysis-runs", status_code=201)
def run_analysis(request: Request, body: AnalysisRunBody) -> dict[str, Any]:
    return invoke(
        service_for(request).analysis.run_and_persist,
        project_id=body.project_id,
        module_id=body.module_id,
        frame=pd.DataFrame(body.rows),
        parameters=body.parameters,
        dataset_id=body.dataset_id,
        is_synthetic=body.is_synthetic,
        seed=body.seed,
    )


@router.get("/runs")
def runs(
    request: Request,
    project_id: str | None = None,
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    filters = {
        key: value
        for key, value in {"project_id": project_id, "status": status}.items()
        if value is not None
    }
    items = invoke(
        service_for(request).store.rows,
        "runs",
        filters=filters or None,
        order_by="started_at_utc",
        limit=limit,
        offset=offset,
    )
    return page(items, limit, offset)


@router.get("/runs/{run_id}")
def run_detail(request: Request, run_id: str) -> dict[str, Any]:
    return invoke(service_for(request).execution.run_snapshot, run_id)


@router.post("/runs/{run_id}/clone", status_code=201)
def clone_run(request: Request, run_id: str) -> dict[str, Any]:
    return invoke(service_for(request).execution.clone_run, run_id)


@router.post("/runs/{run_id}/freeze")
def freeze_run(request: Request, run_id: str) -> dict[str, Any]:
    return invoke(service_for(request).execution.freeze_run, run_id)


@router.get("/runs/{run_id}/reproducibility")
def reproducibility(request: Request, run_id: str) -> dict[str, Any]:
    return invoke(service_for(request).reproducibility.manifest, run_id)


@router.get("/runs/{run_id}/verify")
def verify_run(request: Request, run_id: str) -> dict[str, Any]:
    return invoke(service_for(request).reproducibility.verify, run_id)


@router.get("/runs/compare/{first_id}/{second_id}")
def compare_runs(
    request: Request,
    first_id: str,
    second_id: str,
) -> dict[str, Any]:
    return invoke(service_for(request).execution.compare_runs, first_id, second_id)
