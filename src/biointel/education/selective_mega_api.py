from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .platform import Conflict, Denied, EducationError, Missing
from .selective_mega import EducationMegaService

router = APIRouter(prefix="/mega", tags=["Education Selective Mega R9"])


def service() -> EducationMegaService:
    from .api import platform

    root = Path(__file__).resolve().parents[3]
    return EducationMegaService(platform(), root / "config" / "education_official_sources.json")


def call(operation: Any) -> Any:
    try:
        return operation()
    except Denied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Missing as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Conflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except EducationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class Context(BaseModel):
    actor: str = Field(min_length=1, max_length=240)
    institution_id: str = Field(min_length=1, max_length=240)


class EntityCreate(Context):
    entity_type: str
    name: str = Field(min_length=1, max_length=240)
    code: str = Field(default="", max_length=80)
    parent_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class ClassCreate(Context):
    name: str = Field(min_length=1, max_length=240)
    class_code: str = Field(min_length=4, max_length=64)
    subject_id: str | None = None
    section: str = ""
    academic_session: str = ""
    visibility: Literal["private", "institution", "code"] = "institution"
    meeting_url: str = ""
    settings: dict[str, Any] = Field(default_factory=dict)


class StreamPostCreate(Context):
    class_id: str
    body: str = Field(min_length=1, max_length=20000)
    title: str = ""
    post_type: str = "announcement"
    scheduled_at: str | None = None
    pinned: bool = False
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    audience: list[str] = Field(default_factory=list)


class ClassworkCreate(Context):
    class_id: str
    item_type: str
    title: str = Field(min_length=1, max_length=240)
    instructions: str = ""
    topic: str = ""
    due_at: str | None = None
    publish_at: str | None = None
    max_marks: float = Field(default=0, ge=0)
    state: Literal["draft", "scheduled", "published", "closed", "archived"] = "draft"
    settings: dict[str, Any] = Field(default_factory=dict)


class ExamRegistrationCreate(Context):
    examination_id: str
    subjects: list[str] = Field(default_factory=list)
    eligibility: dict[str, Any] = Field(default_factory=dict)


class RegistrationDecision(Context):
    registration_id: str
    approved: bool
    reason: str = ""


class QuestionCreate(Context):
    subject_id: str
    question_type: str
    prompt: str = Field(min_length=1, max_length=30000)
    answer: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScheduleCreate(Context):
    examination_id: str
    subject_id: str = ""
    room: str
    capacity: int = Field(ge=1)
    starts_at: str
    ends_at: str
    invigilators: list[str] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)


class EvaluationCreate(Context):
    examination_id: str
    student_id: str
    marks: dict[str, float]
    flags: dict[str, Any] = Field(default_factory=dict)
    submit: bool = False


class ResultCreate(Context):
    examination_id: str
    student_id: str
    total: float = Field(ge=0)
    rules: dict[str, Any]
    reason: str = "initial processing"
    publish: bool = False


class ProctorPolicy(Context):
    examination_id: str
    enabled: bool = False
    provider: str = ""
    camera: bool = False
    microphone: bool = False
    retention_days: int = Field(default=0, ge=0, le=3650)
    consent_text: str = ""


class OfficialImport(Context):
    source_id: str
    dataset_year: str = ""
    records: list[dict[str, Any]]


@router.get("/health")
def health() -> dict[str, Any]:
    current = service()
    return {
        "status": "ok",
        "migration": "education_selective_mega_r9_v1",
        "coverage": current.directory_coverage()["totals"],
    }


@router.get("/institutions/{institution_id}/snapshot")
def snapshot(institution_id: str, actor: str) -> dict[str, Any]:
    return call(lambda: service().module_snapshot(actor, institution_id))


@router.post("/entities", status_code=201)
def create_entity(payload: EntityCreate) -> dict[str, Any]:
    return call(
        lambda: service().create_entity(
            payload.actor,
            payload.institution_id,
            payload.entity_type,
            payload.name,
            code=payload.code,
            parent_id=payload.parent_id,
            data=payload.data,
        )
    )


@router.get("/institutions/{institution_id}/entities")
def list_entities(
    institution_id: str,
    actor: str,
    entity_type: str = "",
    query: str = "",
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    return call(
        lambda: service().list_entities(
            actor, institution_id, entity_type, query, limit=limit, offset=offset
        )
    )


@router.post("/classes", status_code=201)
def create_class(payload: ClassCreate) -> dict[str, Any]:
    return call(
        lambda: service().create_class(
            payload.actor,
            payload.institution_id,
            payload.name,
            payload.class_code,
            subject_id=payload.subject_id,
            section=payload.section,
            academic_session=payload.academic_session,
            visibility=payload.visibility,
            meeting_url=payload.meeting_url,
            settings=payload.settings,
        )
    )


@router.post("/stream", status_code=201)
def create_stream_post(payload: StreamPostCreate) -> dict[str, Any]:
    return call(
        lambda: service().add_stream_post(
            payload.actor,
            payload.institution_id,
            payload.class_id,
            payload.body,
            title=payload.title,
            post_type=payload.post_type,
            scheduled_at=payload.scheduled_at,
            attachments=payload.attachments,
            audience=payload.audience,
            pinned=payload.pinned,
        )
    )


@router.post("/classwork", status_code=201)
def create_classwork(payload: ClassworkCreate) -> dict[str, Any]:
    return call(
        lambda: service().create_classwork(
            payload.actor,
            payload.institution_id,
            payload.class_id,
            payload.item_type,
            payload.title,
            instructions=payload.instructions,
            topic=payload.topic,
            due_at=payload.due_at,
            publish_at=payload.publish_at,
            max_marks=payload.max_marks,
            settings=payload.settings,
            state=payload.state,
        )
    )


@router.post("/exam/registrations", status_code=201)
def register_exam(payload: ExamRegistrationCreate) -> dict[str, Any]:
    return call(
        lambda: service().register_exam(
            payload.actor,
            payload.institution_id,
            payload.examination_id,
            payload.subjects,
            payload.eligibility,
        )
    )


@router.post("/exam/registrations/decision")
def decide_registration(payload: RegistrationDecision) -> dict[str, Any]:
    return call(
        lambda: service().decide_exam_registration(
            payload.actor,
            payload.institution_id,
            payload.registration_id,
            payload.approved,
            payload.reason,
        )
    )


@router.post("/exam/questions", status_code=201)
def add_question(payload: QuestionCreate) -> dict[str, Any]:
    return call(
        lambda: service().add_question(
            payload.actor,
            payload.institution_id,
            payload.subject_id,
            payload.question_type,
            payload.prompt,
            answer=payload.answer,
            metadata=payload.metadata,
        )
    )


@router.post("/exam/schedules", status_code=201)
def schedule_exam(payload: ScheduleCreate) -> dict[str, Any]:
    return call(
        lambda: service().schedule_exam(
            payload.actor,
            payload.institution_id,
            payload.examination_id,
            payload.room,
            payload.capacity,
            payload.starts_at,
            payload.ends_at,
            subject_id=payload.subject_id,
            invigilators=payload.invigilators,
            settings=payload.settings,
        )
    )


@router.post("/exam/evaluations")
def save_evaluation(payload: EvaluationCreate) -> dict[str, Any]:
    return call(
        lambda: service().save_evaluation(
            payload.actor,
            payload.institution_id,
            payload.examination_id,
            payload.student_id,
            payload.marks,
            flags=payload.flags,
            submit=payload.submit,
        )
    )


@router.post("/exam/results")
def process_result(payload: ResultCreate) -> dict[str, Any]:
    return call(
        lambda: service().process_result(
            payload.actor,
            payload.institution_id,
            payload.examination_id,
            payload.student_id,
            payload.total,
            payload.rules,
            reason=payload.reason,
            publish=payload.publish,
        )
    )


@router.put("/exam/proctor-policy")
def proctor_policy(payload: ProctorPolicy) -> dict[str, Any]:
    return call(
        lambda: service().set_proctor_policy(
            payload.actor,
            payload.institution_id,
            payload.examination_id,
            enabled=payload.enabled,
            provider=payload.provider,
            camera=payload.camera,
            microphone=payload.microphone,
            retention_days=payload.retention_days,
            consent_text=payload.consent_text,
        )
    )


@router.post("/official-directory/import")
def official_import(payload: OfficialImport) -> dict[str, Any]:
    return call(
        lambda: service().import_official_records(
            payload.actor,
            payload.institution_id,
            payload.source_id,
            payload.records,
            dataset_year=payload.dataset_year,
        )
    )


@router.get("/institutions/{institution_id}/search")
def search(
    institution_id: str, actor: str, q: str, category: str = "", limit: int = 50
) -> list[dict[str, Any]]:
    return call(lambda: service().search(actor, institution_id, q, category=category, limit=limit))
