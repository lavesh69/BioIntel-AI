from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from .api_schemas import (
    CandidateCreateBody,
    EvidenceCreateBody,
    ExperimentCreateBody,
    HypothesisCreateBody,
    ModelCreateBody,
    RecommendationCreateBody,
    ReportCreateBody,
    StrictModel,
    ValidationResultBody,
)
from .api_shared import invoke, page, service_for

router = APIRouter()


class CandidateRankingBody(StrictModel):
    weights: dict[str, float]


@router.get("/projects/{project_id}/candidates")
def candidates(
    request: Request,
    project_id: str,
    candidate_type: str | None = None,
    lifecycle_state: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    items = invoke(
        service_for(request).list_candidates,
        project_id,
        candidate_type=candidate_type,
        lifecycle_state=lifecycle_state,
        limit=limit,
        offset=offset,
    )
    return page(items, limit, offset)


@router.post("/projects/{project_id}/candidates", status_code=201)
def create_candidate(
    request: Request,
    project_id: str,
    body: CandidateCreateBody,
) -> dict[str, Any]:
    return invoke(
        service_for(request).create_candidate,
        project_id,
        **body.model_dump(),
    )


@router.post("/projects/{project_id}/candidate-ranking")
def candidate_ranking(
    request: Request,
    project_id: str,
    body: CandidateRankingBody,
) -> list[dict[str, Any]]:
    return invoke(
        service_for(request).rank_candidates,
        project_id,
        body.weights,
    )


@router.get("/candidates/{candidate_id}/dossier")
def candidate_dossier(request: Request, candidate_id: str) -> dict[str, Any]:
    return invoke(service_for(request).candidate_dossier, candidate_id)


@router.get("/projects/{project_id}/evidence")
def evidence(
    request: Request,
    project_id: str,
    evidence_type: str | None = None,
    verification_state: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    items = invoke(
        service_for(request).list_evidence,
        project_id,
        evidence_type=evidence_type,
        verification_state=verification_state,
        limit=limit,
        offset=offset,
    )
    return page(items, limit, offset)


@router.post("/projects/{project_id}/evidence", status_code=201)
def add_evidence(
    request: Request,
    project_id: str,
    body: EvidenceCreateBody,
) -> dict[str, Any]:
    return invoke(
        service_for(request).add_evidence,
        project_id,
        **body.model_dump(),
    )


@router.get("/projects/{project_id}/evidence/contradictions")
def evidence_contradictions(
    request: Request,
    project_id: str,
) -> list[dict[str, Any]]:
    return invoke(service_for(request).evidence_contradictions, project_id)


@router.get("/projects/{project_id}/hypotheses")
def hypotheses(
    request: Request,
    project_id: str,
    status: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    items = invoke(
        service_for(request).list_hypotheses,
        project_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return page(items, limit, offset)


@router.post("/projects/{project_id}/hypotheses", status_code=201)
def create_hypothesis(
    request: Request,
    project_id: str,
    body: HypothesisCreateBody,
) -> dict[str, Any]:
    return invoke(
        service_for(request).create_hypothesis,
        project_id,
        **body.model_dump(),
    )


@router.get("/projects/{project_id}/recommendations")
def recommendations(
    request: Request,
    project_id: str,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    items = invoke(
        service_for(request).store.rows,
        "recommendations",
        filters={"project_id": project_id},
        order_by="updated_at_utc",
        limit=limit,
        offset=offset,
    )
    return page(items, limit, offset)


@router.post("/projects/{project_id}/recommendations", status_code=201)
def create_recommendation(
    request: Request,
    project_id: str,
    body: RecommendationCreateBody,
) -> dict[str, Any]:
    values = body.model_dump()
    recommendation = values.pop("recommendation")
    return invoke(
        service_for(request).register_recommendation,
        project_id,
        recommendation,
        **values,
    )


@router.get("/projects/{project_id}/experiments")
def experiments(
    request: Request,
    project_id: str,
    status: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    items = invoke(
        service_for(request).list_experiments,
        project_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return page(items, limit, offset)


@router.post("/projects/{project_id}/experiments", status_code=201)
def create_experiment(
    request: Request,
    project_id: str,
    body: ExperimentCreateBody,
) -> dict[str, Any]:
    return invoke(
        service_for(request).create_experiment,
        project_id,
        **body.model_dump(),
    )


@router.post("/experiments/{experiment_id}/validation", status_code=201)
def record_validation(
    request: Request,
    experiment_id: str,
    body: ValidationResultBody,
) -> dict[str, Any]:
    return invoke(
        service_for(request).record_validation_result,
        experiment_id,
        **body.model_dump(),
    )


@router.get("/projects/{project_id}/validations")
def validations(
    request: Request,
    project_id: str,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    items = invoke(
        service_for(request).list_validations,
        project_id,
        limit=limit,
        offset=offset,
    )
    return page(items, limit, offset)


@router.post("/projects/{project_id}/reports", status_code=201)
def create_report(
    request: Request,
    project_id: str,
    body: ReportCreateBody,
) -> dict[str, Any]:
    return invoke(
        service_for(request).reports.create_report,
        project_id,
        title=body.title,
        selected_sections=body.selected_sections,
    )


@router.get("/reports/{report_id}/export/{output_format}")
def export_report(
    request: Request,
    report_id: str,
    output_format: str,
) -> StreamingResponse:
    content, filename, media_type = invoke(
        service_for(request).reports.render,
        report_id,
        output_format,
    )
    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/models")
def models(
    request: Request,
    project_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    filters = {"project_id": project_id} if project_id else None
    items = invoke(
        service_for(request).store.rows,
        "models",
        filters=filters,
        order_by="updated_at_utc",
        limit=limit,
        offset=offset,
    )
    return page(items, limit, offset)


@router.post("/models", status_code=201)
def create_model(request: Request, body: ModelCreateBody) -> dict[str, Any]:
    return invoke(
        service_for(request).register_model,
        artifact_path=Path(body.artifact_path),
        **body.model_dump(exclude={"artifact_path"}),
    )


@router.get("/models/compare/{first_id}/{second_id}")
def compare_models(
    request: Request,
    first_id: str,
    second_id: str,
) -> dict[str, Any]:
    return invoke(service_for(request).compare_models, first_id, second_id)


@router.get("/projects/{project_id}/graph")
def graph(
    request: Request,
    project_id: str,
    relationship_type: str | None = None,
    contradiction_only: bool = False,
    limit: int = Query(default=1000, ge=1, le=5000),
) -> dict[str, Any]:
    return invoke(
        service_for(request).graph_view,
        project_id,
        relationship_type=relationship_type,
        contradiction_only=contradiction_only,
        limit=limit,
    )


@router.get("/projects/{project_id}/activity")
def activity(
    request: Request,
    project_id: str,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    items = invoke(
        service_for(request).activity_feed,
        project_id,
        limit=limit,
        offset=offset,
    )
    return page(items, limit, offset)
