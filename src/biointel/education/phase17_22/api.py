from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..paths import user_data_root
from ..platform import Conflict, Denied, EducationError, EducationPlatform, Missing
from .service import EducationOS

router = APIRouter(prefix="/os", tags=["Education OS Phases 17-22"])
_SERVICE: EducationOS | None = None


def service() -> EducationOS:
    global _SERVICE
    if _SERVICE is None:
        data_root = user_data_root()
        platform = EducationPlatform(data_root / "education" / "education.sqlite3", data_root / "education" / "media")
        _SERVICE = EducationOS(platform, root=data_root.parent)
    return _SERVICE


def run(operation):
    try:
        return operation()
    except Denied as exc:
        raise HTTPException(403, detail=str(exc)) from exc
    except Missing as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except Conflict as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    except EducationError as exc:
        raise HTTPException(400, detail=str(exc)) from exc


class WorkspaceCreate(BaseModel):
    actor: str
    institution_id: str
    program_name: str
    course_code: str
    course_name: str
    classroom_name: str
    teacher_id: str
    academic_year: str = ""


class EnrolmentCreate(BaseModel):
    actor: str
    student_id: str


class AssignmentCreate(BaseModel):
    actor: str
    title: str
    instructions: str
    due_at: str
    max_marks: float = Field(default=100.0, gt=0, le=10000)
    allowed_types: list[str] = Field(default_factory=list)
    late_policy: str = "reject"


class SubmissionCreate(BaseModel):
    actor: str
    body: str = ""
    file_path: str = ""
    final: bool = True
    idempotency_key: str = Field(min_length=1, max_length=160)


class GradeCreate(BaseModel):
    actor: str
    marks: float = Field(ge=0)
    feedback: str = ""
    reason: str = ""


class ShiroAsk(BaseModel):
    actor: str
    question: str = Field(min_length=1, max_length=50000)
    mode: str = "tutoring"
    response_language: str = "auto"
    provider: str = "local"


class InterventionRefresh(BaseModel):
    actor: str
    institution_id: str
    student_id: str
    subject_id: str = ""


class InterventionReview(BaseModel):
    actor: str
    decision: Literal["accepted", "dismissed", "corrected"]
    note: str = ""


class StudioCreate(BaseModel):
    actor: str
    institution_id: str
    title: str
    project_type: str
    description: str = ""


class StudioVersion(BaseModel):
    actor: str
    expected_version: int = Field(ge=0)
    content: dict[str, Any]
    change_note: str = ""


class StudioReview(BaseModel):
    actor: str
    decision: Literal["approved", "changes_requested", "rejected"]
    comment: str = ""


class StudioPublish(BaseModel):
    actor: str
    target_type: Literal["academy", "classroom", "connect"]
    target_id: str


@router.get("/health/{institution_id}")
def health(institution_id: str, actor: str):
    return run(lambda: service().run_health_checks(actor, institution_id))


@router.get("/home/{institution_id}")
def home(institution_id: str, actor: str):
    return run(lambda: service().home_snapshot(actor, institution_id))


@router.post("/workflows")
def create_workspace(payload: WorkspaceCreate):
    return run(lambda: service().create_learning_workspace(**payload.model_dump()))


@router.post("/workflows/{workflow_id}/enrolments")
def enrol(workflow_id: str, payload: EnrolmentCreate):
    return run(lambda: service().enroll_student(payload.actor, workflow_id, payload.student_id))


@router.post("/workflows/{workflow_id}/assignments")
def create_assignment(workflow_id: str, payload: AssignmentCreate):
    values = payload.model_dump()
    actor = values.pop("actor")
    return run(lambda: service().create_assignment(actor, workflow_id, **values))


@router.post("/assignments/{assignment_id}/submissions")
def submit_assignment(assignment_id: str, payload: SubmissionCreate):
    values = payload.model_dump()
    actor = values.pop("actor")
    return run(lambda: service().submit_assignment(actor, assignment_id, **values))


@router.post("/submissions/{submission_id}/grade")
def grade_submission(submission_id: str, payload: GradeCreate):
    values = payload.model_dump()
    actor = values.pop("actor")
    return run(lambda: service().grade_submission(actor, submission_id, **values))


@router.post("/shiro/scopes/{scope_id}/ask")
def ask_shiro(scope_id: str, payload: ShiroAsk):
    values = payload.model_dump()
    actor = values.pop("actor")
    return run(lambda: service().ask_shiro(actor, scope_id, **values))


@router.post("/interventions/refresh")
def refresh_interventions(payload: InterventionRefresh):
    return run(lambda: service().refresh_interventions(**payload.model_dump()))


@router.post("/interventions/{intervention_id}/review")
def review_intervention(intervention_id: str, payload: InterventionReview):
    return run(lambda: service().review_intervention(payload.actor, intervention_id, decision=payload.decision, note=payload.note))


@router.post("/studio/projects")
def create_studio_project(payload: StudioCreate):
    return run(lambda: service().create_studio_project(**payload.model_dump()))


@router.post("/studio/projects/{project_id}/versions")
def save_studio_version(project_id: str, payload: StudioVersion):
    return run(lambda: service().save_studio_version(
        payload.actor, project_id, payload.content,
        expected_version=payload.expected_version, change_note=payload.change_note,
    ))


@router.post("/studio/projects/{project_id}/submit-review")
def submit_studio_review(project_id: str, actor: str):
    return run(lambda: service().submit_studio_review(actor, project_id))


@router.post("/studio/projects/{project_id}/review")
def review_studio_project(project_id: str, payload: StudioReview):
    return run(lambda: service().review_studio_project(
        payload.actor, project_id, decision=payload.decision, comment=payload.comment,
    ))


@router.post("/studio/projects/{project_id}/publish")
def publish_studio_project(project_id: str, payload: StudioPublish):
    return run(lambda: service().publish_studio_project(
        payload.actor, project_id, target_type=payload.target_type, target_id=payload.target_id,
    ))


@router.post("/outbox/{institution_id}/dispatch")
def dispatch_outbox(institution_id: str, actor: str, limit: int = 100):
    return run(lambda: service().dispatch_outbox(actor, institution_id, limit=limit))


@router.post("/release/{institution_id}/qualify")
def qualify_release(institution_id: str, actor: str):
    return run(lambda: service().release_qualification(actor, institution_id))
