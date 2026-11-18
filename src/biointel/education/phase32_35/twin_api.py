from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ..paths import education_paths
from .api_context import require_tenant
from .base import Missing, PermissionDenied, ResearchPlatformError
from .twin import DigitalTwinLab

router = APIRouter(prefix="/phase33", tags=["Education Phase 33 Digital Twin"])
_LAB: DigitalTwinLab | None = None


def lab() -> DigitalTwinLab:
    global _LAB
    if _LAB is None:
        database, media = education_paths()
        _LAB = DigitalTwinLab(database, media)
    return _LAB


def run(operation):
    try:
        return operation()
    except PermissionDenied as exc:
        raise HTTPException(403, detail={"code": "permission_denied", "message": str(exc)}) from exc
    except Missing as exc:
        raise HTTPException(404, detail={"code": "not_found", "message": str(exc)}) from exc
    except ResearchPlatformError as exc:
        raise HTTPException(422, detail={"code": "validation_error", "message": str(exc)}) from exc


def require_resource_tenant(
    request: Request,
    sql: str,
    parameters: tuple[Any, ...],
) -> None:
    row = lab().store.one(sql, parameters)
    if not row:
        raise HTTPException(404, detail="Digital Twin resource not found.")
    require_tenant(request, row["tenant_id"])


class ProjectRequest(BaseModel):
    tenant_id: str
    owner_id: str
    institution_id: str
    title: str = Field(min_length=1, max_length=300)
    purpose: str = Field(min_length=1, max_length=5000)
    classification: str = "Educational Synthetic Twin"
    consent_status: str = "synthetic_not_applicable"
    deidentification_status: str = "synthetic"
    provenance: dict[str, Any] = Field(default_factory=dict)
    ethics_record_reference: str = ""


class SyntheticRequest(BaseModel):
    actor_id: str
    seed: int = 42
    time_points: int = Field(default=12, ge=3, le=500)


class ModelRequest(BaseModel):
    actor_id: str
    model_key: str
    model_name: str = ""
    model_type: str = "imported_definition"
    model_version: str = "1.0.0"
    definition: dict[str, Any] | None = None
    assumptions: list[str] = Field(default_factory=list)
    boundaries: list[str] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)


class ScenarioRequest(BaseModel):
    project_id: str
    model_id: str
    actor_id: str
    name: str
    baseline: dict[str, float] = Field(default_factory=dict)
    time_steps: int = Field(default=48, ge=2, le=20_000)
    step_size: float = Field(default=0.25, gt=0, le=100)
    interventions: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    seed: int = 42
    acknowledgement: bool = False


class SimulationRequest(BaseModel):
    actor_id: str
    replay_of: str | None = None


class LearningActivityRequest(BaseModel):
    teacher_id: str
    classroom_reference: str
    interpretation_prompt: str


class InterpretationRequest(BaseModel):
    student_id: str
    interpretation_text: str = Field(min_length=20, max_length=50_000)


class InterpretationReviewRequest(BaseModel):
    teacher_id: str
    score: float = Field(ge=0, le=100)
    feedback: str = Field(max_length=10_000)
    revision_requested: bool = False


@router.get("/capabilities")
def capabilities():
    return {
        "purpose": "education, research simulation, and hypothesis exploration",
        "clinical_grade_supported": False,
        "default_data": "synthetic/reference",
        "non_clinical": True,
    }


@router.post("/projects", status_code=201)
def create_project(payload: ProjectRequest, request: Request):
    require_tenant(request, payload.tenant_id)
    return run(lambda: lab().create_project(**payload.model_dump()))


@router.post("/projects/{project_id}/synthetic-data", status_code=201)
def generate_synthetic(project_id: str, payload: SyntheticRequest, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p33_twin_projects WHERE project_id=?",
        (project_id,),
    )
    return run(
        lambda: lab().generate_synthetic_profile(
            project_id,
            payload.actor_id,
            seed=payload.seed,
            time_points=payload.time_points,
        )
    )


@router.post("/projects/{project_id}/models", status_code=201)
def register_model(project_id: str, payload: ModelRequest, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p33_twin_projects WHERE project_id=?",
        (project_id,),
    )
    values = payload.model_dump()
    actor_id = values.pop("actor_id")
    return run(lambda: lab().register_model(project_id, actor_id, **values))


@router.post("/scenarios", status_code=201)
def create_scenario(payload: ScenarioRequest, request: Request):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p33_twin_projects WHERE project_id=?",
        (payload.project_id,),
    )
    return run(lambda: lab().create_scenario(**payload.model_dump()))


@router.post("/scenarios/{scenario_id}/run", status_code=201)
def run_scenario(scenario_id: str, payload: SimulationRequest, request: Request):
    require_resource_tenant(
        request,
        """SELECT p.tenant_id FROM education_p33_twin_scenarios s
        JOIN education_p33_twin_projects p ON p.project_id=s.project_id
        WHERE s.scenario_id=?""",
        (scenario_id,),
    )
    return run(
        lambda: asdict(
            lab().run_scenario(
                scenario_id,
                payload.actor_id,
                replay_of=payload.replay_of,
            )
        )
    )


@router.get("/models/{model_id}/shiro-explanation")
def shiro_explanation(model_id: str, request: Request):
    require_resource_tenant(
        request,
        """SELECT p.tenant_id FROM education_p33_twin_models m
        JOIN education_p33_twin_projects p ON p.project_id=m.project_id
        WHERE m.model_id=?""",
        (model_id,),
    )
    return run(lambda: lab().shiro_model_explanation(model_id))


@router.post("/projects/{project_id}/simulations/{simulation_id}/learning-activities", status_code=201)
def create_learning_activity(
    project_id: str,
    simulation_id: str,
    payload: LearningActivityRequest,
    request: Request,
):
    require_resource_tenant(
        request,
        "SELECT tenant_id FROM education_p33_twin_projects WHERE project_id=?",
        (project_id,),
    )
    return run(
        lambda: lab().create_learning_activity(
            project_id,
            simulation_id,
            payload.teacher_id,
            classroom_reference=payload.classroom_reference,
            interpretation_prompt=payload.interpretation_prompt,
        )
    )


@router.post("/learning-activities/{activity_id}/submissions", status_code=201)
def submit_interpretation(
    activity_id: str,
    payload: InterpretationRequest,
    request: Request,
):
    require_resource_tenant(
        request,
        """SELECT p.tenant_id FROM education_p33_twin_learning_activities a
        JOIN education_p33_twin_projects p ON p.project_id=a.project_id
        WHERE a.activity_id=?""",
        (activity_id,),
    )
    return run(
        lambda: lab().submit_interpretation(
            activity_id,
            payload.student_id,
            interpretation_text=payload.interpretation_text,
        )
    )


@router.post("/learning-submissions/{submission_id}/review")
def review_interpretation(
    submission_id: str,
    payload: InterpretationReviewRequest,
    request: Request,
):
    require_resource_tenant(
        request,
        """SELECT p.tenant_id FROM education_p33_twin_learning_submissions s
        JOIN education_p33_twin_learning_activities a ON a.activity_id=s.activity_id
        JOIN education_p33_twin_projects p ON p.project_id=a.project_id
        WHERE s.submission_id=?""",
        (submission_id,),
    )
    return run(
        lambda: lab().review_interpretation(
            submission_id,
            payload.teacher_id,
            score=payload.score,
            feedback=payload.feedback,
            revision_requested=payload.revision_requested,
        )
    )


@router.get("/simulations/{simulation_id}/bundle")
def export_bundle(simulation_id: str, request: Request):
    require_resource_tenant(
        request,
        """SELECT p.tenant_id FROM education_p33_twin_simulations s
        JOIN education_p33_twin_projects p ON p.project_id=s.project_id
        WHERE s.simulation_id=?""",
        (simulation_id,),
    )
    data = run(lambda: lab().export_result_bundle(simulation_id))
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="biointel-digital-twin-{simulation_id}.zip"'
            )
        },
    )
