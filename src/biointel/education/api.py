from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Literal

from biointel.media_tools import ffmpeg_executable
from fastapi import APIRouter, HTTPException, Request
from starlette.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from .module_engines import EducationModuleEngines
from .phase4 import EducationPhase4Service
from .phase5 import EducationPhase5Service
from .phase6 import EducationPhase6Service
from .phase7 import EducationPhase7Service
from .phase11 import EducationPhase11Service
from .phase12 import EducationPhase12Service
from .phase13 import EducationPhase13Service
from .phase14 import EducationPhase14Service
from .phase15 import EducationPhase15Service
from .phase16 import EducationPhase16Service
from .paths import user_data_root
from .platform import Conflict, Denied, EducationError, EducationPlatform, Missing
from .universe import EducationUniverse


def _root() -> Path:
    return user_data_root()


PLATFORM: EducationPlatform | None = None
UNIVERSE: EducationUniverse | None = None
ENGINES: EducationModuleEngines | None = None
PHASE4: EducationPhase4Service | None = None
PHASE5: EducationPhase5Service | None = None
PHASE6: EducationPhase6Service | None = None
PHASE7: EducationPhase7Service | None = None
PHASE11: EducationPhase11Service | None = None
PHASE12: EducationPhase12Service | None = None
PHASE13: EducationPhase13Service | None = None
PHASE14: EducationPhase14Service | None = None
PHASE15: EducationPhase15Service | None = None
PHASE16: EducationPhase16Service | None = None


def platform() -> EducationPlatform:
    global PLATFORM
    if PLATFORM is None:
        root = _root()
        PLATFORM = EducationPlatform(root / "education" / "education.sqlite3", root / "education" / "media")
    return PLATFORM


def engines() -> EducationModuleEngines:
    global ENGINES
    if ENGINES is None:
        ENGINES = EducationModuleEngines(platform())
    return ENGINES



def phase4() -> EducationPhase4Service:
    global PHASE4
    if PHASE4 is None:
        root = _root()
        PHASE4 = EducationPhase4Service(platform(), root=root, shiro_data_dir=root / "education" / "shiro-tutor")
    return PHASE4



def phase5() -> EducationPhase5Service:
    global PHASE5
    if PHASE5 is None:
        PHASE5 = EducationPhase5Service(platform(), root=_root())
    return PHASE5

def phase6() -> EducationPhase6Service:
    global PHASE6
    if PHASE6 is None:
        PHASE6 = EducationPhase6Service(platform(), root=_root())
    return PHASE6


def phase7() -> EducationPhase7Service:
    global PHASE7
    if PHASE7 is None:
        PHASE7 = EducationPhase7Service(platform(), root=_root())
    return PHASE7


def phase11() -> EducationPhase11Service:
    global PHASE11
    if PHASE11 is None:
        PHASE11 = EducationPhase11Service(platform(), root=_root())
    return PHASE11


def phase12() -> EducationPhase12Service:
    global PHASE12
    if PHASE12 is None:
        PHASE12 = EducationPhase12Service(platform(), root=_root())
    return PHASE12


def phase13() -> EducationPhase13Service:
    global PHASE13
    if PHASE13 is None:
        PHASE13 = EducationPhase13Service(platform(), root=_root())
    return PHASE13


def phase14() -> EducationPhase14Service:
    global PHASE14
    if PHASE14 is None:
        PHASE14 = EducationPhase14Service(platform(), root=_root())
    return PHASE14


def phase15() -> EducationPhase15Service:
    global PHASE15
    if PHASE15 is None:
        PHASE15 = EducationPhase15Service(platform(), root=_root())
    return PHASE15


def phase16() -> EducationPhase16Service:
    global PHASE16
    if PHASE16 is None:
        PHASE16 = EducationPhase16Service(platform(), root=_root())
    return PHASE16


def universe() -> EducationUniverse:
    global UNIVERSE
    if UNIVERSE is None:
        UNIVERSE = EducationUniverse(platform())
    return UNIVERSE


router = APIRouter(prefix="/api/v1/education", tags=["BioIntel Education, Science Pulse and Academy"])


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Payload(StrictModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class MemberData(StrictModel):
    user_id: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=80)


class MemberRequest(StrictModel):
    payload: MemberData


class AssignmentData(StrictModel):
    subject_id: str
    title: str = Field(min_length=1, max_length=300)
    instructions: str = Field(default="", max_length=100_000)
    due_at: str
    max_marks: float = Field(gt=0, le=1_000_000)
    allowed_types: list[str] = Field(default_factory=list, max_length=50)
    late_policy: Literal["reject", "allow", "allow_with_penalty", "manual_approval"] = "reject"
    publish: bool = True


class AssignmentRequest(StrictModel):
    payload: AssignmentData


class SubmissionData(StrictModel):
    body: str = Field(default="", max_length=2_000_000)
    file_path: str = Field(default="", max_length=2_000)
    final: bool = True


class SubmissionRequest(StrictModel):
    payload: SubmissionData


class GradeData(StrictModel):
    marks: float
    feedback: str = Field(default="", max_length=100_000)
    reason: str = Field(default="", max_length=1_000)


class GradeRequest(StrictModel):
    payload: GradeData


class ReasonData(StrictModel):
    reason: str = Field(min_length=1, max_length=1_000)


class ReasonRequest(StrictModel):
    payload: ReasonData


class GuardianData(StrictModel):
    guardian_id: str
    student_id: str


class GuardianRequest(StrictModel):
    payload: GuardianData


class GuardianApprovalData(StrictModel):
    guardian_id: str


class GuardianApprovalRequest(StrictModel):
    payload: GuardianApprovalData


class CircularData(StrictModel):
    number: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=500_000)
    audience: list[str] | dict[str, list[str]]
    priority: Literal["low", "normal", "high", "urgent"] = "normal"


class CircularRequest(StrictModel):
    payload: CircularData


class PulseSourceData(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    source_type: Literal["publication_api", "rss", "news_api"]
    base_url: str = Field(min_length=8, max_length=2_000)
    configured: bool = False
    institution_id: str | None = None


class PulseSourceRequest(StrictModel):
    payload: PulseSourceData


class ProgressData(StrictModel):
    seconds: float = Field(ge=0)
    completed: bool = False


class ProgressRequest(StrictModel):
    payload: ProgressData


class ResultData(StrictModel):
    student_id: str
    marks: float
    grade: str = Field(default="", max_length=50)
    reason: str = Field(default="", max_length=1_000)


class ResultRequest(StrictModel):
    payload: ResultData



class ConceptData(StrictModel):
    code: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=20_000)
    prerequisites: list[str] = Field(default_factory=list, max_length=100)
    difficulty: Literal["foundation", "easy", "medium", "hard", "advanced"] = "medium"


class ConceptRequest(StrictModel):
    payload: ConceptData


class MasteryEvidenceData(StrictModel):
    score: float = Field(ge=0, le=1)
    evidence_type: Literal["practice", "assignment", "quiz", "examination", "laboratory", "teacher_observation", "self_check"] = "practice"
    evidence_id: str = Field(default="", max_length=300)
    weight: float = Field(default=1, ge=0.1, le=5)
    occurred_at: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class MasteryEvidenceRequest(StrictModel):
    payload: MasteryEvidenceData


class WeeklyTimetableData(StrictModel):
    subject_id: str
    teacher_id: str
    student_group: str = Field(default="", max_length=300)
    room: str = Field(default="", max_length=200)
    first_start: str
    first_end: str
    weeks: int = Field(default=12, ge=1, le=104)
    meeting_id: str = Field(default="", max_length=500)


class WeeklyTimetableRequest(StrictModel):
    payload: WeeklyTimetableData


class TutorSourceData(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=20, max_length=25_000_000)


class TutorSourceRequest(StrictModel):
    payload: TutorSourceData


class TutorQuestionData(StrictModel):
    question: str = Field(min_length=1, max_length=100_000)
    response_language: str = Field(default="auto", max_length=40)
    policy_mode: Literal["guided", "revision", "teacher_planning"] = "guided"
    conversation_id: str | None = Field(default=None, max_length=200)


class TutorQuestionRequest(StrictModel):
    payload: TutorQuestionData


class NotificationPreferenceData(StrictModel):
    event_type: str = Field(default="*", max_length=100)
    channel: Literal["in_app", "email", "desktop", "sms", "whatsapp"] = "in_app"
    enabled: bool = True
    digest_mode: Literal["instant", "daily", "weekly", "off"] = "instant"
    quiet_start: str = Field(default="", max_length=20)
    quiet_end: str = Field(default="", max_length=20)


class NotificationPreferenceRequest(StrictModel):
    payload: NotificationPreferenceData




class CampusData(StrictModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=300)
    timezone_name: str = Field(default="UTC", max_length=100)
    address: dict[str, Any] = Field(default_factory=dict)


class CampusRequest(StrictModel):
    payload: CampusData


class IdentityProviderData(StrictModel):
    provider_type: Literal["oidc", "saml", "google_workspace", "microsoft_entra"]
    display_name: str = Field(min_length=1, max_length=200)
    issuer_url: str = Field(default="", max_length=2_000)
    client_id: str = Field(default="", max_length=500)
    metadata_url: str = Field(default="", max_length=2_000)
    secret_reference: str = Field(default="", max_length=500)
    allowed_domains: list[str] = Field(default_factory=list, max_length=100)
    activate: bool = False


class IdentityProviderRequest(StrictModel):
    payload: IdentityProviderData


class MFAPolicyData(StrictModel):
    required_roles: list[str] = Field(default_factory=list, max_length=100)
    methods: list[Literal["totp", "webauthn", "email_otp"]] = Field(default_factory=lambda: ["totp"])
    grace_hours: int = Field(default=0, ge=0, le=720)
    recovery_codes_required: bool = True


class MFAPolicyRequest(StrictModel):
    payload: MFAPolicyData


class DatabaseProfileData(StrictModel):
    engine: Literal["sqlite", "postgresql"]
    name: str = Field(min_length=1, max_length=200)
    dsn_reference: str = Field(default="", max_length=500)
    pool_min: int = Field(default=1, ge=1, le=100)
    pool_max: int = Field(default=10, ge=1, le=500)
    ssl_mode: Literal["disable", "allow", "prefer", "require", "verify-ca", "verify-full"] = "require"
    activate: bool = False


class DatabaseProfileRequest(StrictModel):
    payload: DatabaseProfileData


class StorageBackendData(StrictModel):
    backend_type: Literal["local", "s3", "minio"]
    name: str = Field(min_length=1, max_length=200)
    endpoint: str = Field(default="", max_length=2_000)
    bucket: str = Field(default="", max_length=500)
    region: str = Field(default="", max_length=100)
    secret_reference: str = Field(default="", max_length=500)
    activate: bool = False


class StorageBackendRequest(StrictModel):
    payload: StorageBackendData


class BackgroundJobData(StrictModel):
    job_type: str = Field(min_length=1, max_length=120)
    payload: dict[str, Any] = Field(default_factory=dict)
    queue_name: str = Field(default="default", max_length=80)
    priority: int = Field(default=50, ge=0, le=100)
    max_attempts: int = Field(default=3, ge=1, le=20)
    available_at: str | None = None


class BackgroundJobRequest(StrictModel):
    payload: BackgroundJobData


class IntegrationData(StrictModel):
    provider_type: Literal["moodle", "canvas", "google_classroom", "microsoft_teams", "oneroster", "lti_1_3", "scorm", "xapi"]
    name: str = Field(min_length=1, max_length=200)
    base_url: str = Field(default="", max_length=2_000)
    client_id: str = Field(default="", max_length=500)
    secret_reference: str = Field(default="", max_length=500)
    settings: dict[str, Any] = Field(default_factory=dict)
    activate: bool = False


class IntegrationRequest(StrictModel):
    payload: IntegrationData


class ImportPreviewData(StrictModel):
    import_type: Literal["members", "subjects"]
    file_name: str = Field(min_length=1, max_length=255)
    csv_content: str = Field(min_length=1, max_length=25_000_000)


class ImportPreviewRequest(StrictModel):
    payload: ImportPreviewData


class EngineRequest(StrictModel):
    payload: dict[str, Any] = Field(default_factory=dict)


def actor(request: Request) -> str:
    identity = getattr(request.state, "api_identity", None)
    client_id = str(getattr(identity, "client_id", "") or "").strip()
    if not client_id:
        raise HTTPException(status_code=401, detail="Authenticated API identity is required.")
    return client_id


def run(fn):
    try:
        return fn()
    except Missing as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except Denied as exc:
        raise HTTPException(403, detail=str(exc)) from exc
    except Conflict as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    except (EducationError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(422, detail=str(exc)) from exc


@router.get("/health")
def health():
    import shutil
    return {
        "status": "ok" if platform().db.quick_check() else "failed",
        "database": "ready",
        "publication_sources": "configuration_required",
        "video_processing": "ffmpeg_detected" if ffmpeg_executable() else "processing_dependency_required",
        "academic_integrity_migration": "education_science_academy_v2_integrity",
    }


@router.post("/institutions", status_code=201)
def create_institution(p: Payload, r: Request):
    return run(lambda: platform().create_institution(actor(r), **p.payload))


@router.post("/institutions/{institution_id}/members", status_code=201)
def add_member(institution_id: str, p: MemberRequest, r: Request):
    return run(lambda: platform().add_member(actor(r), institution_id, **p.payload.model_dump()))


@router.get("/institutions/{institution_id}/dashboard")
def dashboard(institution_id: str, r: Request):
    return run(lambda: platform().dashboard(actor(r), institution_id))


@router.post("/institutions/{institution_id}/units", status_code=201)
def unit(institution_id: str, p: Payload, r: Request):
    return run(lambda: platform().create_unit(actor(r), institution_id, **p.payload))


@router.post("/institutions/{institution_id}/subjects", status_code=201)
def subject(institution_id: str, p: Payload, r: Request):
    return run(lambda: platform().create_subject(actor(r), institution_id, **p.payload))


@router.post("/institutions/{institution_id}/teacher-assignments", status_code=201)
def teacher(institution_id: str, p: Payload, r: Request):
    return run(lambda: platform().assign_teacher(actor(r), institution_id, **p.payload))


@router.post("/institutions/{institution_id}/enrollments", status_code=201)
def enroll(institution_id: str, p: Payload, r: Request):
    return run(lambda: platform().enroll(actor(r), institution_id, **p.payload))


@router.post("/institutions/{institution_id}/guardian-links", status_code=201)
def guardian_link(institution_id: str, p: GuardianRequest, r: Request):
    return run(lambda: platform().add_guardian_link(actor(r), institution_id, **p.payload.model_dump()))


@router.post("/institutions/{institution_id}/guardian-links/approve")
def guardian_approve(institution_id: str, p: GuardianApprovalRequest, r: Request):
    return run(lambda: platform().approve_guardian_link(actor(r), institution_id, p.payload.guardian_id))


@router.post("/institutions/{institution_id}/guardian-links/revoke")
def guardian_revoke(institution_id: str, p: GuardianData, r: Request):
    return run(lambda: platform().revoke_guardian_link(actor(r), institution_id, p.guardian_id, p.student_id))


@router.post("/institutions/{institution_id}/timetable", status_code=201)
def timetable(institution_id: str, p: Payload, r: Request):
    return run(lambda: platform().create_timetable(actor(r), institution_id, **p.payload))


@router.post("/institutions/{institution_id}/attendance-sessions", status_code=201)
def attendance_session(institution_id: str, p: Payload, r: Request):
    return run(lambda: platform().attendance_session(actor(r), institution_id, **p.payload))


@router.post("/attendance/{session_id}/records")
def attendance_record(session_id: str, p: Payload, r: Request):
    return run(lambda: platform().mark_attendance(actor(r), session_id, **p.payload))


@router.get("/institutions/{institution_id}/students/{student_id}/attendance")
def attendance(institution_id: str, student_id: str, r: Request):
    return run(lambda: platform().student_attendance(actor(r), institution_id, student_id))


@router.post("/institutions/{institution_id}/assignments", status_code=201)
def assignment(institution_id: str, p: AssignmentRequest, r: Request):
    return run(lambda: platform().create_assignment(actor(r), institution_id, **p.payload.model_dump()))


@router.post("/assignments/{assignment_id}/submissions", status_code=201)
def submission(assignment_id: str, p: SubmissionRequest, r: Request):
    return run(lambda: platform().submit_assignment(actor(r), assignment_id, **p.payload.model_dump()))


@router.post("/submissions/{submission_id}/reopen")
def reopen_submission(submission_id: str, p: ReasonRequest, r: Request):
    return run(lambda: platform().reopen_submission(actor(r), submission_id, p.payload.reason))


@router.post("/submissions/{submission_id}/grade")
def grade(submission_id: str, p: GradeRequest, r: Request):
    return run(lambda: platform().grade_submission(actor(r), submission_id, **p.payload.model_dump()))


@router.post("/institutions/{institution_id}/circulars", status_code=201)
def circular(institution_id: str, p: CircularRequest, r: Request):
    return run(lambda: platform().create_circular(actor(r), institution_id, **p.payload.model_dump()))


@router.get("/institutions/{institution_id}/circulars")
def circulars(institution_id: str, r: Request, limit: int = 100):
    return run(lambda: platform().list_circulars(actor(r), institution_id, limit))


@router.post("/circulars/{circular_id}/publish")
def publish(circular_id: str, r: Request):
    return run(lambda: platform().publish_circular(actor(r), circular_id))


@router.post("/circulars/{circular_id}/acknowledge")
def acknowledge(circular_id: str, r: Request):
    return run(lambda: platform().acknowledge_circular(actor(r), circular_id))


@router.post("/pulse/sources", status_code=201)
def pulse_source(p: PulseSourceRequest, r: Request):
    return run(lambda: platform().add_pulse_source(actor(r), **p.payload.model_dump()))


@router.post("/pulse/sources/{source_id}/sync")
def pulse_sync(source_id: str, p: Payload, r: Request):
    return run(lambda: platform().sync_pulse_source(actor(r), source_id, **p.payload))


@router.post("/pulse/publications", status_code=201)
def publication(p: Payload, r: Request):
    source_id = str(p.payload.get("source_id", ""))
    source = platform()._one("SELECT institution_id FROM pulse_sources WHERE id=?", (source_id,))
    if not source:
        raise HTTPException(404, detail="Source not found.")
    return run(lambda: (platform()._source_manager(actor(r), source["institution_id"] or None), platform().ingest_publication(**p.payload))[1])


@router.post("/pulse/news", status_code=201)
def news(p: Payload, r: Request):
    source_id = str(p.payload.get("source_id", ""))
    source = platform()._one("SELECT institution_id FROM pulse_sources WHERE id=?", (source_id,))
    if not source:
        raise HTTPException(404, detail="Source not found.")
    return run(lambda: (platform()._source_manager(actor(r), source["institution_id"] or None), platform().ingest_news(**p.payload))[1])


@router.get("/pulse/search")
def pulse_search(q: str):
    return platform().pulse_search(q)


@router.post("/institutions/{institution_id}/courses", status_code=201)
def course(institution_id: str, p: Payload, r: Request):
    return run(lambda: platform().create_course(actor(r), institution_id, **p.payload))


@router.post("/courses/{course_id}/enroll")
def course_enroll(course_id: str, r: Request):
    return run(lambda: platform().enroll_course(actor(r), course_id))


@router.post("/institutions/{institution_id}/educators/{user_id}/verify")
def educator_verify(institution_id: str, user_id: str, r: Request, approve: bool = True):
    return run(lambda: platform().verify_educator(actor(r), institution_id, user_id, approve))


@router.post("/lectures/{lecture_id}/progress")
def progress(lecture_id: str, p: ProgressRequest, r: Request):
    return run(lambda: platform().update_watch(actor(r), lecture_id, **p.payload.model_dump()))


@router.get("/certificates/{verification_code}/verify")
def certificate_verify(verification_code: str):
    return platform().verify_certificate(verification_code)


@router.post("/examinations/{examination_id}/results")
def result_set(examination_id: str, p: ResultRequest, r: Request):
    return run(lambda: platform().set_result(actor(r), examination_id, **p.payload.model_dump()))


@router.post("/results/{result_id}/unlock")
def result_unlock(result_id: str, p: ReasonRequest, r: Request):
    return run(lambda: platform().unlock_result(actor(r), result_id, p.payload.reason))


@router.get("/institutions/{institution_id}/engines/adaptive-learning")
def adaptive_learning_engine(institution_id: str, r: Request, student_id: str | None = None):
    return run(lambda: engines().adaptive_learning_snapshot(actor(r), institution_id, student_id))


@router.get("/institutions/{institution_id}/engines/learning-analytics")
def learning_analytics_engine(institution_id: str, r: Request, student_id: str | None = None):
    return run(lambda: engines().learning_analytics(actor(r), institution_id, student_id))


@router.post("/institutions/{institution_id}/engines/virtual-lab")
def virtual_lab_engine(institution_id: str, p: EngineRequest, r: Request):
    return run(lambda: engines().virtual_lab(actor(r), institution_id, **p.payload))


@router.post("/institutions/{institution_id}/engines/bioinformatics-sandbox")
def bioinformatics_engine(institution_id: str, p: EngineRequest, r: Request):
    return run(lambda: engines().bioinformatics_sandbox(actor(r), institution_id, **p.payload))


@router.post("/institutions/{institution_id}/engines/assessment-blueprint")
def assessment_blueprint_engine(institution_id: str, p: EngineRequest, r: Request):
    return run(lambda: engines().assessment_blueprint(actor(r), institution_id, **p.payload))


@router.post("/institutions/{institution_id}/engines/reproducibility-check")
def reproducibility_engine(institution_id: str, p: EngineRequest, r: Request):
    return run(lambda: engines().reproducibility_check(actor(r), institution_id, p.payload))



@router.post("/institutions/{institution_id}/subjects/{subject_id}/concepts", status_code=201)
def phase4_create_concept(institution_id: str, subject_id: str, p: ConceptRequest, r: Request):
    return run(lambda: phase4().create_concept(actor(r), institution_id, subject_id, **p.payload.model_dump()))


@router.post("/institutions/{institution_id}/students/{student_id}/concepts/{concept_id}/evidence", status_code=201)
def phase4_mastery_evidence(institution_id: str, student_id: str, concept_id: str, p: MasteryEvidenceRequest, r: Request):
    return run(lambda: phase4().record_mastery_evidence(actor(r), institution_id, student_id, concept_id, **p.payload.model_dump()))


@router.get("/institutions/{institution_id}/students/{student_id}/learning")
def phase4_learning_snapshot(institution_id: str, student_id: str, r: Request, subject_id: str | None = None):
    return run(lambda: phase4().learner_snapshot(actor(r), institution_id, student_id, subject_id))


@router.post("/institutions/{institution_id}/timetable/weekly", status_code=201)
def phase4_weekly_timetable(institution_id: str, p: WeeklyTimetableRequest, r: Request):
    return run(lambda: phase4().create_weekly_timetable(actor(r), institution_id, **p.payload.model_dump()))


@router.get("/institutions/{institution_id}/notifications")
def phase4_notifications(institution_id: str, r: Request, unread_only: bool = False, limit: int = 100):
    return run(lambda: phase4().notification_inbox(actor(r), institution_id, unread_only=unread_only, limit=limit))


@router.post("/institutions/{institution_id}/notifications/preferences")
def phase4_notification_preferences(institution_id: str, p: NotificationPreferenceRequest, r: Request):
    return run(lambda: phase4().save_notification_preference(actor(r), institution_id, **p.payload.model_dump()))


@router.post("/institutions/{institution_id}/subjects/{subject_id}/tutor/sources", status_code=201)
def phase4_tutor_source(institution_id: str, subject_id: str, p: TutorSourceRequest, r: Request):
    return run(lambda: phase4().index_subject_text(actor(r), institution_id, subject_id, **p.payload.model_dump()))


@router.post("/institutions/{institution_id}/subjects/{subject_id}/tutor/chat")
def phase4_tutor_chat(institution_id: str, subject_id: str, p: TutorQuestionRequest, r: Request):
    return run(lambda: phase4().ask_tutor(actor(r), institution_id, subject_id, **p.payload.model_dump()))


@router.get("/institutions/{institution_id}/students/{student_id}/progress-report")
def phase4_progress_report(institution_id: str, student_id: str, r: Request):
    return run(lambda: phase4().learner_progress_report(actor(r), institution_id, student_id))


@router.get("/institutions/{institution_id}/platform/dashboard")
def phase5_dashboard(institution_id: str, r: Request):
    return run(lambda: phase5().dashboard(actor(r), institution_id))


@router.post("/institutions/{institution_id}/campuses", status_code=201)
def phase5_create_campus(institution_id: str, p: CampusRequest, r: Request):
    return run(lambda: phase5().create_campus(actor(r), institution_id, **p.payload.model_dump()))


@router.get("/institutions/{institution_id}/hierarchy")
def phase5_hierarchy(institution_id: str, r: Request):
    return run(lambda: phase5().hierarchy(actor(r), institution_id))


@router.post("/institutions/{institution_id}/identity/providers", status_code=201)
def phase5_identity_provider(institution_id: str, p: IdentityProviderRequest, r: Request):
    return run(lambda: phase5().configure_identity_provider(actor(r), institution_id, **p.payload.model_dump()))


@router.post("/institutions/{institution_id}/identity/mfa")
def phase5_mfa_policy(institution_id: str, p: MFAPolicyRequest, r: Request):
    return run(lambda: phase5().save_mfa_policy(actor(r), institution_id, **p.payload.model_dump()))


@router.get("/institutions/{institution_id}/identity/posture")
def phase5_identity_posture(institution_id: str, r: Request):
    return run(lambda: phase5().identity_posture(actor(r), institution_id))


@router.post("/institutions/{institution_id}/database/profiles", status_code=201)
def phase5_database_profile(institution_id: str, p: DatabaseProfileRequest, r: Request):
    return run(lambda: phase5().configure_database_profile(actor(r), institution_id, **p.payload.model_dump()))


@router.get("/institutions/{institution_id}/database/posture")
def phase5_database_posture(institution_id: str, r: Request):
    return run(lambda: phase5().database_posture(actor(r), institution_id))


@router.post("/institutions/{institution_id}/storage/backends", status_code=201)
def phase5_storage_backend(institution_id: str, p: StorageBackendRequest, r: Request):
    return run(lambda: phase5().configure_storage_backend(actor(r), institution_id, **p.payload.model_dump()))


@router.post("/institutions/{institution_id}/backups", status_code=201)
def phase5_backup(institution_id: str, label: str, r: Request):
    return run(lambda: phase5().create_backup(actor(r), institution_id, label))


@router.post("/backups/{snapshot_id}/restore-rehearsal")
def phase5_restore_rehearsal(snapshot_id: str, r: Request):
    return run(lambda: phase5().restore_rehearsal(actor(r), snapshot_id))


@router.post("/institutions/{institution_id}/jobs", status_code=202)
def phase5_enqueue_job(institution_id: str, p: BackgroundJobRequest, r: Request):
    return run(lambda: phase5().enqueue_job(actor(r), institution_id, **p.payload.model_dump()))


@router.post("/institutions/{institution_id}/integrations", status_code=201)
def phase5_integration(institution_id: str, p: IntegrationRequest, r: Request):
    return run(lambda: phase5().configure_integration(actor(r), institution_id, **p.payload.model_dump()))


@router.post("/integrations/{integration_id}/readiness")
def phase5_integration_readiness(integration_id: str, r: Request):
    return run(lambda: phase5().test_integration_readiness(actor(r), integration_id))


@router.post("/institutions/{institution_id}/imports/preview", status_code=201)
def phase5_import_preview(institution_id: str, p: ImportPreviewRequest, r: Request):
    data = p.payload.model_dump()
    return run(lambda: phase5().preview_import(actor(r), institution_id, data["import_type"], data["file_name"], data["csv_content"]))


@router.post("/imports/{batch_id}/commit")
def phase5_import_commit(batch_id: str, r: Request):
    return run(lambda: phase5().commit_import(actor(r), batch_id))


@router.post("/institutions/{institution_id}/governance-reports", status_code=201)
def phase5_governance_report(institution_id: str, r: Request, report_type: str = "institution_readiness"):
    return run(lambda: phase5().generate_governance_report(actor(r), institution_id, report_type=report_type))


@router.get("/institutions/{institution_id}/search")
def search(institution_id: str, q: str, r: Request):
    return run(lambda: platform().unified_search(actor(r), institution_id, q))


@router.get("/universe/institutions/{institution_id}/modules")
def universe_modules(institution_id: str, r: Request):
    return run(lambda: universe().modules(actor(r), institution_id))


@router.get("/universe/institutions/{institution_id}/dashboard")
def universe_dashboard(institution_id: str, r: Request):
    return run(lambda: universe().dashboard(actor(r), institution_id))


@router.get("/universe/institutions/{institution_id}/records")
def universe_records(institution_id: str, r: Request, module_key: str | None = None, q: str = "", limit: int = 100):
    return run(lambda: universe().list_records(actor(r), institution_id, module_key, q, limit))


@router.post("/universe/institutions/{institution_id}/records", status_code=201)
def universe_create(institution_id: str, p: Payload, r: Request):
    return run(lambda: universe().create_record(actor(r), institution_id, **p.payload))


@router.get("/universe/records/{record_id}")
def universe_record(record_id: str, r: Request):
    return run(lambda: universe().get_record(actor(r), record_id))


@router.patch("/universe/records/{record_id}")
def universe_update(record_id: str, p: Payload, r: Request):
    return run(lambda: universe().update_record(actor(r), record_id, **p.payload))


@router.post("/universe/records/{record_id}/transition")
def universe_transition(record_id: str, p: Payload, r: Request):
    return run(lambda: universe().transition_record(actor(r), record_id, **p.payload))


@router.delete("/universe/records/{record_id}")
def universe_delete(record_id: str, expected_version: int, r: Request):
    return run(lambda: universe().delete_record(actor(r), record_id, expected_version))


@router.get("/universe/records/{record_id}/history")
def universe_history(record_id: str, r: Request):
    return run(lambda: universe().record_history(actor(r), record_id))


@router.post("/universe/institutions/{institution_id}/sync", status_code=202)
def universe_sync_queue(institution_id: str, p: Payload, r: Request):
    return run(lambda: universe().queue_sync(actor(r), institution_id, **p.payload))


@router.post("/universe/sync/{operation_id}/apply")
def universe_sync_apply(operation_id: str, r: Request):
    return run(lambda: universe().apply_sync(actor(r), operation_id))


@router.post("/universe/sync/{operation_id}/resolve")
def universe_sync_resolve(operation_id: str, p: Payload, r: Request):
    return run(lambda: universe().resolve_sync(actor(r), operation_id, **p.payload))

class UIPreferencesData(StrictModel):
    theme: Literal["dark", "light", "system"] = "dark"
    density: Literal["compact", "comfortable"] = "comfortable"
    font_scale: float = Field(default=1.0, ge=0.85, le=1.5)
    high_contrast: bool = False
    reduced_motion: bool = False
    dyslexia_mode: bool = False


class UIPreferencesRequest(StrictModel):
    payload: UIPreferencesData


class ShiroConversationData(StrictModel):
    subject_id: str | None = None
    title: str = Field(min_length=1, max_length=160)
    mode: Literal["guided_learning", "guided", "revision", "teacher_planning"] = "guided_learning"
    language: Literal["English", "Hindi", "Hinglish"] = "English"


class ShiroConversationRequest(StrictModel):
    payload: ShiroConversationData


class ShiroMessageData(StrictModel):
    question: str = Field(min_length=1, max_length=100_000)


class ShiroMessageRequest(StrictModel):
    payload: ShiroMessageData


class WorkerRegistrationData(StrictModel):
    worker_id: str = Field(min_length=1, max_length=120)
    queues: list[str] = Field(default_factory=lambda: ["default"], min_length=1, max_length=20)
    version: str = Field(default="", max_length=80)


class WorkerRegistrationRequest(StrictModel):
    payload: WorkerRegistrationData


class JobProgressData(StrictModel):
    institution_id: str
    worker_id: str = Field(min_length=1, max_length=120)
    lock_token: str = Field(min_length=1, max_length=240)
    percent: float = Field(ge=0, le=100)
    message: str = Field(default="", max_length=500)


class JobProgressRequest(StrictModel):
    payload: JobProgressData


class BackupScheduleData(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    frequency: Literal["daily", "weekly"] = "daily"
    hour_utc: int = Field(default=2, ge=0, le=23)
    weekday: int | None = Field(default=None, ge=0, le=6)
    retention_count: int = Field(default=14, ge=1, le=365)
    include_media: bool = True


class BackupScheduleRequest(StrictModel):
    payload: BackupScheduleData


class IntegrationSyncData(StrictModel):
    direction: Literal["pull", "push", "bidirectional"] = "pull"
    entity_type: str = Field(default="courses", min_length=1, max_length=80)


class IntegrationSyncRequest(StrictModel):
    payload: IntegrationSyncData


class SavedViewData(StrictModel):
    module_key: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    filters: dict[str, Any] = Field(default_factory=dict)
    columns: list[str] = Field(default_factory=list, max_length=100)


class SavedViewRequest(StrictModel):
    payload: SavedViewData


@router.get("/institutions/{institution_id}/phase6/preferences")
def phase6_preferences(institution_id: str, r: Request):
    return run(lambda: phase6().preferences(actor(r), institution_id))


@router.put("/institutions/{institution_id}/phase6/preferences")
def phase6_save_preferences(institution_id: str, p: UIPreferencesRequest, r: Request):
    return run(lambda: phase6().save_preferences(actor(r), institution_id, **p.payload.model_dump()))


@router.get("/institutions/{institution_id}/phase6/dashboard")
def phase6_dashboard(institution_id: str, r: Request):
    return run(lambda: phase6().visual_dashboard(actor(r), institution_id))


@router.get("/institutions/{institution_id}/phase6/calendar")
def phase6_calendar(institution_id: str, r: Request, start_day: str | None = None, days: int = 7):
    return run(lambda: phase6().timetable_calendar(actor(r), institution_id, start_day=start_day, days=days))


@router.get("/institutions/{institution_id}/phase6/gradebook/{subject_id}")
def phase6_gradebook(institution_id: str, subject_id: str, r: Request):
    return run(lambda: phase6().gradebook(actor(r), institution_id, subject_id))


@router.get("/institutions/{institution_id}/phase6/attendance-heatmap")
def phase6_attendance_heatmap(institution_id: str, r: Request, subject_id: str | None = None):
    return run(lambda: phase6().attendance_heatmap(actor(r), institution_id, subject_id=subject_id))


@router.get("/phase6/exams/{exam_id}/analytics")
def phase6_exam_analytics(exam_id: str, r: Request):
    return run(lambda: phase6().exam_analytics(actor(r), exam_id))


@router.get("/institutions/{institution_id}/phase6/conversations")
def phase6_conversations(institution_id: str, r: Request):
    return run(lambda: phase6().conversations(actor(r), institution_id))


@router.post("/institutions/{institution_id}/phase6/conversations", status_code=201)
def phase6_create_conversation(institution_id: str, p: ShiroConversationRequest, r: Request):
    return run(lambda: phase6().create_conversation(actor(r), institution_id, **p.payload.model_dump()))


@router.post("/phase6/conversations/{conversation_id}/messages")
def phase6_ask_conversation(conversation_id: str, p: ShiroMessageRequest, r: Request):
    return run(lambda: phase6().ask_conversation(actor(r), conversation_id, p.payload.question))


@router.post("/institutions/{institution_id}/phase6/workers", status_code=201)
def phase6_register_worker(institution_id: str, p: WorkerRegistrationRequest, r: Request):
    return run(lambda: phase6().register_worker(actor(r), institution_id, **p.payload.model_dump()))


@router.post("/phase6/jobs/{job_id}/progress")
def phase6_job_progress(job_id: str, p: JobProgressRequest):
    data = p.payload.model_dump()
    return run(lambda: phase6().update_job_progress(data["institution_id"], data["worker_id"], job_id, data["lock_token"], data["percent"], data["message"]))


@router.post("/institutions/{institution_id}/phase6/jobs/{job_id}/cancel")
def phase6_cancel_job(institution_id: str, job_id: str, r: Request):
    return run(lambda: phase6().cancel_job(actor(r), institution_id, job_id))


@router.post("/institutions/{institution_id}/phase6/jobs/{job_id}/requeue")
def phase6_requeue_job(institution_id: str, job_id: str, r: Request):
    return run(lambda: phase6().requeue_job(actor(r), institution_id, job_id))


@router.get("/institutions/{institution_id}/phase6/job-operations")
def phase6_job_operations(institution_id: str, r: Request):
    return run(lambda: phase6().job_operations(actor(r), institution_id))


@router.post("/institutions/{institution_id}/phase6/backup-schedules", status_code=201)
def phase6_backup_schedule(institution_id: str, p: BackupScheduleRequest, r: Request):
    return run(lambda: phase6().create_backup_schedule(actor(r), institution_id, **p.payload.model_dump()))


@router.post("/institutions/{institution_id}/phase6/backup-schedules/enqueue-due", status_code=202)
def phase6_enqueue_due_backups(institution_id: str, r: Request):
    return run(lambda: phase6().enqueue_due_backups(actor(r), institution_id))


@router.post("/phase6/integrations/{integration_id}/sync", status_code=202)
def phase6_start_integration_sync(integration_id: str, p: IntegrationSyncRequest, r: Request):
    return run(lambda: phase6().start_integration_sync(actor(r), integration_id, **p.payload.model_dump()))


@router.get("/institutions/{institution_id}/phase6/integration-operations")
def phase6_integration_operations(institution_id: str, r: Request):
    return run(lambda: phase6().integration_operations(actor(r), institution_id))


@router.post("/institutions/{institution_id}/phase6/saved-views", status_code=201)
def phase6_saved_view(institution_id: str, p: SavedViewRequest, r: Request):
    return run(lambda: phase6().save_view(actor(r), institution_id, **p.payload.model_dump()))

@router.post("/phase6/identity-providers/{provider_id}/qualify")
def phase6_qualify_identity_provider(provider_id: str, r: Request):
    return run(lambda: phase6().external.verify_identity_provider(actor(r), provider_id))


@router.post("/phase6/database-profiles/{profile_id}/qualify")
def phase6_qualify_database_profile(profile_id: str, r: Request):
    return run(lambda: phase6().external.verify_database_profile(actor(r), profile_id))


@router.post("/phase6/storage-backends/{backend_id}/qualify")
def phase6_qualify_storage_backend(backend_id: str, r: Request):
    return run(lambda: phase6().external.verify_storage_backend(actor(r), backend_id))


@router.post("/phase6/integrations/{integration_id}/qualify")
def phase6_qualify_integration(integration_id: str, r: Request):
    return run(lambda: phase6().external.verify_integration(actor(r), integration_id))


@router.get("/institutions/{institution_id}/phase6/qualification-history")
def phase6_qualification_history(institution_id: str, r: Request, limit: int = 100):
    return run(lambda: phase6().external.history(actor(r), institution_id, limit=limit))

class DesktopIdentityData(StrictModel):
    user_id: str = Field(min_length=1, max_length=200)
    pin: str = Field(min_length=6, max_length=64)
    display_name: str = Field(default="", max_length=160)
    email: str = Field(default="", max_length=240)


class DesktopIdentityRequest(StrictModel):
    payload: DesktopIdentityData


class DesktopSignInData(StrictModel):
    login: str = Field(min_length=1, max_length=240)
    pin: str = Field(min_length=1, max_length=64)
    device_label: str = Field(default="BioIntel Desktop", max_length=120)


class DesktopSignInRequest(StrictModel):
    payload: DesktopSignInData


class TimetableUpdateData(StrictModel):
    starts_at: str
    ends_at: str
    teacher_id: str = Field(min_length=1, max_length=200)
    student_group: str = Field(default="", max_length=200)
    room: str = Field(default="", max_length=200)
    meeting_id: str = Field(default="", max_length=500)


class TimetableUpdateRequest(StrictModel):
    payload: TimetableUpdateData


class AttendanceRow(StrictModel):
    student_id: str = Field(min_length=1, max_length=200)
    status: Literal["present", "absent", "late", "excused"]
    note: str = Field(default="", max_length=500)


class AttendanceRosterData(StrictModel):
    rows: list[AttendanceRow] = Field(max_length=10_000)
    lock: bool = False


class AttendanceRosterRequest(StrictModel):
    payload: AttendanceRosterData


class GradebookRow(StrictModel):
    submission_id: str = Field(min_length=1, max_length=240)
    marks: float | None = None
    feedback: str = Field(default="", max_length=4_000)


class GradebookSaveData(StrictModel):
    rows: list[GradebookRow] = Field(max_length=10_000)
    reason: str = Field(default="Bulk gradebook update", max_length=1_000)


class GradebookSaveRequest(StrictModel):
    payload: GradebookSaveData


class ConversationRenameData(StrictModel):
    title: str = Field(min_length=1, max_length=160)


class ConversationRenameRequest(StrictModel):
    payload: ConversationRenameData


class LectureNoteData(StrictModel):
    body: str = Field(min_length=1, max_length=8_000)
    position_seconds: float = Field(default=0, ge=0)


class LectureNoteRequest(StrictModel):
    payload: LectureNoteData


class LectureBookmarkData(StrictModel):
    position_seconds: float = Field(ge=0)
    label: str = Field(default="", max_length=200)


class LectureBookmarkRequest(StrictModel):
    payload: LectureBookmarkData


class ExamThresholdData(StrictModel):
    passing_percent: float = Field(gt=0, le=100)


class ExamThresholdRequest(StrictModel):
    payload: ExamThresholdData


class ModerationData(StrictModel):
    event_type: Literal["review_started", "review_completed", "score_flagged", "revaluation_requested", "revaluation_resolved", "publication_approved"]
    session_id: str | None = None
    reason: str = Field(default="", max_length=2_000)
    detail: dict[str, Any] = Field(default_factory=dict)


class ModerationRequest(StrictModel):
    payload: ModerationData


class RubricCriterionData(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2_000)
    max_marks: float = Field(gt=0)


class RubricSaveData(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    criteria: list[RubricCriterionData] = Field(min_length=1, max_length=100)


class RubricSaveRequest(StrictModel):
    payload: RubricSaveData


class RubricScoreData(StrictModel):
    criterion_id: str = Field(min_length=1, max_length=240)
    marks: float = Field(ge=0)
    feedback: str = Field(default="", max_length=2_000)


class RubricGradeData(StrictModel):
    scores: list[RubricScoreData] = Field(min_length=1, max_length=100)
    overall_feedback: str = Field(default="", max_length=4_000)
    reason: str = Field(default="", max_length=1_000)


class RubricGradeRequest(StrictModel):
    payload: RubricGradeData


class LectureTranscriptData(StrictModel):
    body: str = Field(min_length=1, max_length=2_000_000)
    language: str = Field(default="English", min_length=1, max_length=80)


class LectureTranscriptRequest(StrictModel):
    payload: LectureTranscriptData


@router.post("/institutions/{institution_id}/phase7/identity", status_code=201)
def phase7_enroll_identity(institution_id: str, p: DesktopIdentityRequest, r: Request):
    data = p.payload.model_dump()
    return run(lambda: phase7().enroll_identity(actor(r), institution_id, **data))


@router.post("/institutions/{institution_id}/phase7/sign-in")
def phase7_sign_in(institution_id: str, p: DesktopSignInRequest):
    return run(lambda: phase7().authenticate(institution_id, **p.payload.model_dump()))


@router.get("/phase7/sessions/validate")
def phase7_validate_session(token: str):
    return run(lambda: phase7().validate_session(token))


@router.get("/institutions/{institution_id}/phase7/sessions")
def phase7_sessions(institution_id: str, r: Request):
    return run(lambda: phase7().sessions(actor(r), institution_id))


@router.delete("/institutions/{institution_id}/phase7/sessions/{session_id}")
def phase7_revoke_session(institution_id: str, session_id: str, r: Request):
    return run(lambda: phase7().revoke_session(actor(r), institution_id, session_id))


@router.put("/institutions/{institution_id}/phase7/timetable/{entry_id}")
def phase7_update_timetable(institution_id: str, entry_id: str, p: TimetableUpdateRequest, r: Request):
    return run(lambda: phase7().update_timetable_entry(actor(r), institution_id, entry_id, **p.payload.model_dump()))


@router.delete("/institutions/{institution_id}/phase7/timetable/{entry_id}")
def phase7_cancel_timetable(institution_id: str, entry_id: str, p: ReasonRequest, r: Request):
    return run(lambda: phase7().cancel_timetable_entry(actor(r), institution_id, entry_id, p.payload.reason))


@router.get("/institutions/{institution_id}/phase7/attendance/{subject_id}")
def phase7_attendance_roster(institution_id: str, subject_id: str, r: Request, session_id: str | None = None):
    return run(lambda: phase7().attendance_roster(actor(r), institution_id, subject_id, session_id))


@router.put("/phase7/attendance/{session_id}")
def phase7_save_attendance(session_id: str, p: AttendanceRosterRequest, r: Request):
    data = p.payload.model_dump()
    return run(lambda: phase7().save_attendance_roster(actor(r), session_id, data["rows"], lock=data["lock"]))


@router.get("/institutions/{institution_id}/phase7/gradebook/{subject_id}")
def phase7_editable_gradebook(institution_id: str, subject_id: str, r: Request):
    return run(lambda: phase7().editable_gradebook(actor(r), institution_id, subject_id))


@router.put("/institutions/{institution_id}/phase7/gradebook")
def phase7_save_gradebook(institution_id: str, p: GradebookSaveRequest, r: Request):
    data = p.payload.model_dump()
    return run(lambda: phase7().save_gradebook_rows(actor(r), institution_id, data["rows"], reason=data["reason"]))


@router.put("/phase7/conversations/{conversation_id}/title")
def phase7_rename_conversation(conversation_id: str, p: ConversationRenameRequest, r: Request):
    return run(lambda: phase7().rename_conversation(actor(r), conversation_id, p.payload.title))


@router.post("/phase7/conversations/{conversation_id}/archive")
def phase7_archive_conversation(conversation_id: str, r: Request):
    return run(lambda: phase7().archive_conversation(actor(r), conversation_id))


@router.delete("/phase7/conversations/{conversation_id}", status_code=204)
def phase7_delete_conversation(conversation_id: str, r: Request):
    return run(lambda: phase7().delete_conversation(actor(r), conversation_id))


@router.post("/phase7/lectures/{lecture_id}/notes", status_code=201)
def phase7_lecture_note(lecture_id: str, p: LectureNoteRequest, r: Request):
    return run(lambda: phase7().save_lecture_note(actor(r), lecture_id, **p.payload.model_dump()))


@router.post("/phase7/lectures/{lecture_id}/bookmarks", status_code=201)
def phase7_lecture_bookmark(lecture_id: str, p: LectureBookmarkRequest, r: Request):
    return run(lambda: phase7().add_lecture_bookmark(actor(r), lecture_id, **p.payload.model_dump()))


@router.put("/phase7/exams/{exam_id}/passing-threshold")
def phase7_exam_threshold(exam_id: str, p: ExamThresholdRequest, r: Request):
    return run(lambda: phase7().set_exam_passing_percent(actor(r), exam_id, p.payload.passing_percent))


@router.get("/phase7/exams/{exam_id}/analytics")
def phase7_exam_analytics(exam_id: str, r: Request):
    return run(lambda: phase7().exam_analytics_phase7(actor(r), exam_id))


@router.post("/phase7/exams/{exam_id}/moderation", status_code=201)
def phase7_moderation(exam_id: str, p: ModerationRequest, r: Request):
    return run(lambda: phase7().record_moderation_event(actor(r), exam_id, **p.payload.model_dump()))


@router.get("/phase7/exams/{exam_id}/moderation")
def phase7_moderation_timeline(exam_id: str, r: Request):
    return run(lambda: phase7().moderation_timeline(actor(r), exam_id))



@router.put("/phase7/assignments/{assignment_id}/rubric")
def phase7_save_assignment_rubric(assignment_id: str, p: RubricSaveRequest, r: Request):
    data = p.payload.model_dump()
    return run(lambda: phase7().save_assignment_rubric(actor(r), assignment_id, data["title"], data["criteria"]))


@router.get("/phase7/assignments/{assignment_id}/rubric")
def phase7_assignment_rubric(assignment_id: str, r: Request):
    return run(lambda: phase7().assignment_rubric(actor(r), assignment_id))


@router.put("/phase7/submissions/{submission_id}/rubric-grade")
def phase7_grade_with_rubric(submission_id: str, p: RubricGradeRequest, r: Request):
    data = p.payload.model_dump()
    return run(lambda: phase7().grade_with_rubric(actor(r), submission_id, data["scores"], overall_feedback=data["overall_feedback"], reason=data["reason"]))


@router.put("/phase7/lectures/{lecture_id}/transcript")
def phase7_save_lecture_transcript(lecture_id: str, p: LectureTranscriptRequest, r: Request):
    return run(lambda: phase7().save_lecture_transcript(actor(r), lecture_id, **p.payload.model_dump()))


@router.get("/phase7/lectures/{lecture_id}/transcripts")
def phase7_lecture_transcripts(lecture_id: str, r: Request):
    return run(lambda: phase7().lecture_transcripts(actor(r), lecture_id))

# ---------------- Phase 11 Mega Production & Academic Core ----------------

class Phase11TOTPBeginData(StrictModel):
    user_id: str = Field(min_length=1, max_length=200)


class Phase11TOTPBeginRequest(StrictModel):
    payload: Phase11TOTPBeginData


class Phase11TOTPConfirmData(StrictModel):
    user_id: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=6, max_length=12)


class Phase11TOTPConfirmRequest(StrictModel):
    payload: Phase11TOTPConfirmData


class Phase11SecureAuthBeginData(StrictModel):
    login: str = Field(min_length=1, max_length=240)
    pin: str = Field(min_length=1, max_length=128)
    device_label: str = Field(default="BioIntel Desktop", max_length=200)


class Phase11SecureAuthBeginRequest(StrictModel):
    payload: Phase11SecureAuthBeginData


class Phase11SecureAuthCompleteData(StrictModel):
    challenge_token: str = Field(min_length=20, max_length=500)
    code: str = Field(default="", max_length=20)
    recovery_code: str = Field(default="", max_length=50)


class Phase11SecureAuthCompleteRequest(StrictModel):
    payload: Phase11SecureAuthCompleteData


class Phase11QuestionBankData(StrictModel):
    name: str = Field(min_length=1, max_length=240)
    subject_id: str | None = None
    description: str = Field(default="", max_length=20_000)
    visibility: Literal["restricted", "department", "institution"] = "restricted"


class Phase11QuestionBankRequest(StrictModel):
    payload: Phase11QuestionBankData


class Phase11QuestionData(StrictModel):
    question_type: Literal["single_choice", "multiple_choice", "true_false", "short_answer", "long_answer", "numeric", "matching", "ordering"]
    title: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=200_000)
    options: list[Any] = Field(default_factory=list, max_length=200)
    answer: Any = None
    explanation: str = Field(default="", max_length=100_000)
    bloom_level: Literal["remember", "understand", "apply", "analyze", "evaluate", "create"] = "understand"
    difficulty: Literal["foundation", "easy", "medium", "hard", "advanced"] = "medium"
    outcome_code: str = Field(default="", max_length=120)
    marks: float = Field(default=1, gt=0, le=10_000)
    negative_marks: float = Field(default=0, ge=0, le=10_000)
    language: str = Field(default="English", max_length=80)


class Phase11QuestionRequest(StrictModel):
    payload: Phase11QuestionData


class Phase11ReviewData(StrictModel):
    decision: Literal["approve", "request_changes", "reject"]
    comments: str = Field(default="", max_length=20_000)


class Phase11ReviewRequest(StrictModel):
    payload: Phase11ReviewData


class Phase11BlueprintData(StrictModel):
    subject_id: str
    total_marks: float = Field(gt=0, le=100_000)
    bloom_distribution: dict[str, float]
    difficulty_distribution: dict[str, float]


class Phase11BlueprintRequest(StrictModel):
    payload: Phase11BlueprintData


class Phase11GradeSchemeData(StrictModel):
    name: str = Field(min_length=1, max_length=240)
    subject_id: str | None = None
    categories: list[dict[str, Any]] = Field(min_length=1, max_length=100)
    bands: list[dict[str, Any]] = Field(min_length=1, max_length=100)


class Phase11GradeSchemeRequest(StrictModel):
    payload: Phase11GradeSchemeData


class Phase11GradeCalculationData(StrictModel):
    student_id: str
    scores: dict[str, list[float] | float]


class Phase11GradeCalculationRequest(StrictModel):
    payload: Phase11GradeCalculationData


class Phase11TranscriptEntryData(StrictModel):
    student_id: str
    academic_year: str = Field(max_length=40)
    term: str = Field(max_length=80)
    subject_code: str = Field(max_length=80)
    subject_name: str = Field(max_length=300)
    credits: float = Field(ge=0, le=1000)
    marks_percent: float = Field(ge=0, le=100)
    grade_label: str = Field(default="", max_length=40)
    grade_points: float = Field(default=0, ge=0, le=100)
    source_ref: str = Field(default="", max_length=300)


class Phase11TranscriptEntryRequest(StrictModel):
    payload: Phase11TranscriptEntryData


class Phase11CredentialData(StrictModel):
    student_id: str
    credential_type: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    evidence: dict[str, Any] = Field(default_factory=dict)


class Phase11CredentialRequest(StrictModel):
    payload: Phase11CredentialData


class Phase11NotificationTemplateData(StrictModel):
    template_key: str = Field(min_length=1, max_length=120)
    channel: Literal["in_app", "email", "desktop", "sms", "whatsapp"] = "in_app"
    subject_template: str = Field(default="", max_length=500)
    body_template: str = Field(min_length=1, max_length=100_000)


class Phase11NotificationTemplateRequest(StrictModel):
    payload: Phase11NotificationTemplateData


class Phase11NotificationData(StrictModel):
    recipient_id: str
    channel: Literal["in_app", "email", "desktop", "sms", "whatsapp"] = "in_app"
    destination: str = Field(default="", max_length=500)
    template_key: str = Field(default="", max_length=120)
    subject: str = Field(default="", max_length=500)
    body: str = Field(default="", max_length=100_000)
    context: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(default="", max_length=200)
    priority: int = Field(default=50, ge=0, le=100)
    available_at: str | None = None


class Phase11NotificationRequest(StrictModel):
    payload: Phase11NotificationData


class Phase11ReportData(StrictModel):
    report_type: Literal["attendance", "gradebook", "transcript", "audit", "question_bank"]
    parameters: dict[str, Any] = Field(default_factory=dict)
    output_format: Literal["json", "csv"] = "json"


class Phase11ReportRequest(StrictModel):
    payload: Phase11ReportData


class Phase11IncidentData(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    severity: Literal["low", "medium", "high", "critical"]
    summary: str = Field(default="", max_length=20_000)
    owner_id: str = Field(default="", max_length=200)


class Phase11IncidentRequest(StrictModel):
    payload: Phase11IncidentData


class Phase11PrivacyData(StrictModel):
    subject_user_id: str
    request_type: Literal["access", "correction", "export", "deletion", "anonymization", "consent_withdrawal"]
    reason: str = Field(default="", max_length=5000)


class Phase11PrivacyRequest(StrictModel):
    payload: Phase11PrivacyData


class Phase11RetentionData(StrictModel):
    data_class: str = Field(min_length=1, max_length=120)
    retention_days: int = Field(ge=1, le=36500)
    action: Literal["archive", "anonymize", "delete"] = "archive"
    legal_hold: bool = False


class Phase11RetentionRequest(StrictModel):
    payload: Phase11RetentionData


@router.post("/institutions/{institution_id}/phase11/mfa/totp/begin", status_code=201)
def phase11_mfa_begin(institution_id: str, p: Phase11TOTPBeginRequest, r: Request):
    return run(lambda: phase11().begin_totp_enrollment(actor(r), institution_id, p.payload.user_id))


@router.post("/institutions/{institution_id}/phase11/mfa/totp/confirm")
def phase11_mfa_confirm(institution_id: str, p: Phase11TOTPConfirmRequest, r: Request):
    return run(lambda: phase11().confirm_totp_enrollment(actor(r), institution_id, p.payload.user_id, p.payload.code))


@router.get("/institutions/{institution_id}/phase11/mfa/posture")
def phase11_mfa_posture(institution_id: str, r: Request):
    return run(lambda: phase11().mfa_posture(actor(r), institution_id))


@router.post("/institutions/{institution_id}/phase11/auth/begin")
def phase11_auth_begin(institution_id: str, p: Phase11SecureAuthBeginRequest):
    return run(lambda: phase11().begin_secure_authentication(institution_id, **p.payload.model_dump()))


@router.post("/phase11/auth/complete")
def phase11_auth_complete(p: Phase11SecureAuthCompleteRequest):
    return run(lambda: phase11().complete_secure_authentication(**p.payload.model_dump()))


@router.get("/institutions/{institution_id}/phase11/security/chain")
def phase11_security_chain(institution_id: str, r: Request):
    return run(lambda: phase11().verify_security_chain(actor(r), institution_id))


@router.post("/institutions/{institution_id}/phase11/question-banks", status_code=201)
def phase11_question_bank(institution_id: str, p: Phase11QuestionBankRequest, r: Request):
    return run(lambda: phase11().create_question_bank(actor(r), institution_id, **p.payload.model_dump()))


@router.post("/phase11/question-banks/{bank_id}/questions", status_code=201)
def phase11_question_create(bank_id: str, p: Phase11QuestionRequest, r: Request):
    return run(lambda: phase11().create_question(actor(r), bank_id, **p.payload.model_dump()))


@router.post("/phase11/questions/{question_id}/review")
def phase11_question_review(question_id: str, p: Phase11ReviewRequest, r: Request):
    return run(lambda: phase11().review_question(actor(r), question_id, **p.payload.model_dump()))


@router.post("/phase11/questions/{question_id}/publish")
def phase11_question_publish(question_id: str, r: Request):
    return run(lambda: phase11().publish_question(actor(r), question_id))


@router.get("/institutions/{institution_id}/phase11/questions")
def phase11_question_catalog(institution_id: str, r: Request, subject_id: str | None = None, state: str | None = None, bloom_level: str | None = None, difficulty: str | None = None, search: str = ""):
    return run(lambda: phase11().question_catalog(actor(r), institution_id, subject_id=subject_id, state=state, bloom_level=bloom_level, difficulty=difficulty, search=search))


@router.post("/institutions/{institution_id}/phase11/questions/blueprint")
def phase11_question_blueprint(institution_id: str, p: Phase11BlueprintRequest, r: Request):
    return run(lambda: phase11().generate_question_blueprint(actor(r), institution_id, **p.payload.model_dump()))


@router.get("/phase11/questions/{question_id}/analysis")
def phase11_question_analysis(question_id: str, r: Request, exam_id: str = ""):
    return run(lambda: phase11().question_item_analysis(actor(r), question_id, exam_id=exam_id))


@router.post("/institutions/{institution_id}/phase11/grade-schemes", status_code=201)
def phase11_grade_scheme(institution_id: str, p: Phase11GradeSchemeRequest, r: Request):
    return run(lambda: phase11().create_grade_scheme(actor(r), institution_id, **p.payload.model_dump()))


@router.post("/phase11/grade-schemes/{scheme_id}/calculate")
def phase11_grade_calculate(scheme_id: str, p: Phase11GradeCalculationRequest, r: Request):
    return run(lambda: phase11().calculate_grade(actor(r), scheme_id, p.payload.student_id, p.payload.scores))


@router.put("/institutions/{institution_id}/phase11/transcript")
def phase11_transcript_entry(institution_id: str, p: Phase11TranscriptEntryRequest, r: Request):
    data = p.payload.model_dump()
    student_id = data.pop("student_id")
    return run(lambda: phase11().upsert_transcript_entry(actor(r), institution_id, student_id, **data))


@router.get("/institutions/{institution_id}/phase11/transcript/{student_id}")
def phase11_transcript(institution_id: str, student_id: str, r: Request):
    return run(lambda: phase11().transcript(actor(r), institution_id, student_id))


@router.post("/institutions/{institution_id}/phase11/credentials", status_code=201)
def phase11_credential_issue(institution_id: str, p: Phase11CredentialRequest, r: Request):
    data = p.payload.model_dump()
    student_id = data.pop("student_id")
    return run(lambda: phase11().issue_credential(actor(r), institution_id, student_id, **data))


@router.get("/phase11/credentials/{serial_number}/verify")
def phase11_credential_verify(serial_number: str):
    return phase11().verify_credential(serial_number)


@router.post("/institutions/{institution_id}/phase11/notification-templates", status_code=201)
def phase11_notification_template(institution_id: str, p: Phase11NotificationTemplateRequest, r: Request):
    data = p.payload.model_dump()
    template_key = data.pop("template_key")
    return run(lambda: phase11().save_notification_template(actor(r), institution_id, template_key, **data))


@router.post("/institutions/{institution_id}/phase11/notifications", status_code=202)
def phase11_notification_queue(institution_id: str, p: Phase11NotificationRequest, r: Request):
    data = p.payload.model_dump()
    recipient_id = data.pop("recipient_id")
    return run(lambda: phase11().queue_notification(actor(r), institution_id, recipient_id, **data))


@router.get("/institutions/{institution_id}/phase11/notifications/posture")
def phase11_notification_posture(institution_id: str, r: Request):
    return run(lambda: phase11().notification_operations(actor(r), institution_id))


@router.post("/institutions/{institution_id}/phase11/reports", status_code=201)
def phase11_report(institution_id: str, p: Phase11ReportRequest, r: Request):
    data = p.payload.model_dump()
    report_type = data.pop("report_type")
    return run(lambda: phase11().generate_report(actor(r), institution_id, report_type, **data))


@router.post("/institutions/{institution_id}/phase11/health-snapshots", status_code=201)
def phase11_health(institution_id: str, r: Request):
    return run(lambda: phase11().record_health_snapshot(actor(r), institution_id))


@router.get("/institutions/{institution_id}/phase11/operations")
def phase11_operations(institution_id: str, r: Request):
    return run(lambda: phase11().operations_posture(actor(r), institution_id))


@router.post("/institutions/{institution_id}/phase11/incidents", status_code=201)
def phase11_incident(institution_id: str, p: Phase11IncidentRequest, r: Request):
    return run(lambda: phase11().open_incident(actor(r), institution_id, **p.payload.model_dump()))


@router.post("/institutions/{institution_id}/phase11/privacy-requests", status_code=201)
def phase11_privacy_request(institution_id: str, p: Phase11PrivacyRequest, r: Request):
    data = p.payload.model_dump()
    subject_user_id = data.pop("subject_user_id")
    return run(lambda: phase11().create_privacy_request(actor(r), institution_id, subject_user_id, **data))


@router.put("/institutions/{institution_id}/phase11/retention-policies")
def phase11_retention(institution_id: str, p: Phase11RetentionRequest, r: Request):
    data = p.payload.model_dump()
    data_class = data.pop("data_class")
    return run(lambda: phase11().save_retention_policy(actor(r), institution_id, data_class, **data))


@router.get("/institutions/{institution_id}/phase11/external-dependencies")
def phase11_external_dependencies(institution_id: str, r: Request):
    return run(lambda: phase11().external_dependency_posture(actor(r), institution_id))

@router.post("/institutions/{institution_id}/phase11/full-backups", status_code=201)
def phase11_full_backup(institution_id: str, label: str, r: Request):
    return run(lambda: phase11().create_full_backup(actor(r), institution_id, label))


@router.post("/phase11/full-backups/{backup_id}/verify")
def phase11_full_backup_verify(backup_id: str, r: Request):
    return run(lambda: phase11().verify_full_backup(actor(r), backup_id))


@router.post("/phase11/full-backups/{backup_id}/restore-rehearsal")
def phase11_full_backup_rehearsal(backup_id: str, r: Request):
    return run(lambda: phase11().full_backup_restore_rehearsal(actor(r), backup_id))


# ---------------- Phase 12 final-completion typed API ----------------
class Phase12OIDCBeginData(StrictModel):
    provider_id: str = Field(min_length=1, max_length=200)
    redirect_uri: str = Field(min_length=1, max_length=1000)
    login_hint: str = Field(default="", max_length=320)

class Phase12OIDCBeginRequest(StrictModel):
    payload: Phase12OIDCBeginData

class Phase12OIDCCompleteData(StrictModel):
    state: str = Field(min_length=16, max_length=1000)
    code: str = Field(min_length=1, max_length=4000)
    nonce: str = Field(min_length=16, max_length=1000)

class Phase12OIDCCompleteRequest(StrictModel):
    payload: Phase12OIDCCompleteData

class Phase12MigrationExportData(StrictModel):
    profile_id: str = Field(default="", max_length=200)

class Phase12MigrationExportRequest(StrictModel):
    payload: Phase12MigrationExportData

class Phase12MigrationApplyData(StrictModel):
    dry_run: bool = True

class Phase12MigrationApplyRequest(StrictModel):
    payload: Phase12MigrationApplyData

class Phase12OriginalityData(StrictModel):
    threshold: float = Field(default=.35, ge=.05, le=1)

class Phase12OriginalityRequest(StrictModel):
    payload: Phase12OriginalityData

class Phase12OriginalityReviewData(StrictModel):
    state: Literal["confirmed", "dismissed", "needs_revision", "appealed"]
    note: str = Field(min_length=1, max_length=4000)

class Phase12OriginalityReviewRequest(StrictModel):
    payload: Phase12OriginalityReviewData

class Phase12ExamGovernanceData(StrictModel):
    paper_reviewer_id: str = Field(min_length=1, max_length=200)
    answer_key_reviewer_id: str = Field(min_length=1, max_length=200)
    controller_id: str = Field(min_length=1, max_length=200)
    moderation_tolerance: float = Field(default=5, ge=0, le=25)

class Phase12ExamGovernanceRequest(StrictModel):
    payload: Phase12ExamGovernanceData

class Phase12ExamApprovalData(StrictModel):
    stage: Literal["paper", "answer_key", "controller"]
    note: str = Field(default="", max_length=4000)

class Phase12ExamApprovalRequest(StrictModel):
    payload: Phase12ExamApprovalData

class Phase12ExamTransitionData(StrictModel):
    target: str = Field(min_length=1, max_length=40)
    reason: str = Field(default="", max_length=4000)

class Phase12ExamTransitionRequest(StrictModel):
    payload: Phase12ExamTransitionData

class Phase12ExamEvaluationData(StrictModel):
    stage: Literal["first", "second", "moderator"]
    score: float = Field(ge=0)
    max_score: float = Field(gt=0)
    comments: str = Field(default="", max_length=8000)
    rubric: dict[str, Any] = Field(default_factory=dict)

class Phase12ExamEvaluationRequest(StrictModel):
    payload: Phase12ExamEvaluationData

class Phase12ExamAppealData(StrictModel):
    reason: str = Field(min_length=1, max_length=8000)

class Phase12ExamAppealRequest(StrictModel):
    payload: Phase12ExamAppealData

class Phase12ExamAppealDecisionData(StrictModel):
    state: Literal["accepted", "rejected", "completed"]
    note: str = Field(min_length=1, max_length=8000)
    revised_score: float | None = Field(default=None, ge=0)

class Phase12ExamAppealDecisionRequest(StrictModel):
    payload: Phase12ExamAppealDecisionData

class Phase12HeartbeatData(StrictModel):
    connection_state: Literal["online", "unstable", "offline", "reconnected"] = "online"
    current_question_id: str = Field(default="", max_length=200)
    answered_count: int = Field(default=0, ge=0)
    client_clock_offset_ms: int = Field(default=0, ge=-3_600_000, le=3_600_000)
    detail: dict[str, Any] = Field(default_factory=dict)

class Phase12HeartbeatRequest(StrictModel):
    payload: Phase12HeartbeatData

class Phase12ModelProfileData(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    provider_type: Literal["ollama", "openai_compatible", "local_file", "disabled"]
    model_name: str = Field(min_length=1, max_length=300)
    endpoint: str = Field(default="", max_length=1200)
    embedding_model: str = Field(default="", max_length=300)
    reranker_model: str = Field(default="", max_length=300)
    secret_reference: str = Field(default="", max_length=300)
    context_window: int = Field(default=4096, ge=512, le=2_000_000)
    activate: bool = False

class Phase12ModelProfileRequest(StrictModel):
    payload: Phase12ModelProfileData

class Phase12RAGDocumentData(StrictModel):
    project_id: str = Field(min_length=1, max_length=300)
    source_path: str = Field(min_length=1, max_length=4000)
    title: str = Field(default="", max_length=500)
    permissions: dict[str, Any] = Field(default_factory=dict)

class Phase12RAGDocumentRequest(StrictModel):
    payload: Phase12RAGDocumentData

class Phase12RAGReviewData(StrictModel):
    approve: bool
    reason: str = Field(min_length=1, max_length=4000)

class Phase12RAGReviewRequest(StrictModel):
    payload: Phase12RAGReviewData

class Phase12RAGEvaluationData(StrictModel):
    project_id: str = Field(min_length=1, max_length=300)
    query_text: str = Field(min_length=1, max_length=8000)
    expected_refs: list[str] = Field(default_factory=list, max_length=500)
    retrieved_refs: list[str] = Field(default_factory=list, max_length=500)
    cited_refs: list[str] = Field(default_factory=list, max_length=500)

class Phase12RAGEvaluationRequest(StrictModel):
    payload: Phase12RAGEvaluationData

class Phase12DeliveryProviderData(StrictModel):
    channel: Literal["smtp", "webhook", "sms", "whatsapp", "desktop", "in_app"]
    name: str = Field(min_length=1, max_length=160)
    endpoint: str = Field(default="", max_length=1200)
    sender: str = Field(default="", max_length=320)
    secret_reference: str = Field(default="", max_length=300)
    settings: dict[str, Any] = Field(default_factory=dict)
    activate: bool = False

class Phase12DeliveryProviderRequest(StrictModel):
    payload: Phase12DeliveryProviderData

@router.post("/phase12/oidc/authorize")
def phase12_oidc_begin(p: Phase12OIDCBeginRequest):
    return run(lambda: phase12().begin_oidc_authorization(**p.payload.model_dump()))

@router.post("/phase12/oidc/callback")
def phase12_oidc_complete(p: Phase12OIDCCompleteRequest):
    return run(lambda: phase12().complete_oidc_authorization(**p.payload.model_dump()))

@router.post("/institutions/{institution_id}/phase12/database-migration-exports", status_code=201)
def phase12_database_export(institution_id: str, p: Phase12MigrationExportRequest, r: Request):
    return run(lambda: phase12().create_database_migration_export(actor(r), institution_id, **p.payload.model_dump()))

@router.get("/phase12/database-migration-exports/{export_id}/verify")
def phase12_database_export_verify(export_id: str, r: Request):
    return run(lambda: phase12().verify_database_migration_export(actor(r), export_id))

@router.post("/phase12/database-migration-exports/{export_id}/apply")
def phase12_database_export_apply(export_id: str, p: Phase12MigrationApplyRequest, r: Request):
    return run(lambda: phase12().apply_database_migration_export(actor(r), export_id, **p.payload.model_dump()))

@router.post("/phase12/submissions/{submission_id}/originality")
def phase12_originality(submission_id: str, p: Phase12OriginalityRequest, r: Request):
    return run(lambda: phase12().analyze_submission_originality(actor(r), submission_id, **p.payload.model_dump()))

@router.put("/phase12/originality-matches/{match_id}")
def phase12_originality_review(match_id: str, p: Phase12OriginalityReviewRequest, r: Request):
    return run(lambda: phase12().review_originality_match(actor(r), match_id, **p.payload.model_dump()))

@router.put("/phase12/exams/{exam_id}/governance")
def phase12_exam_governance(exam_id: str, p: Phase12ExamGovernanceRequest, r: Request):
    return run(lambda: phase12().configure_exam_governance(actor(r), exam_id, **p.payload.model_dump()))

@router.post("/phase12/exams/{exam_id}/approvals")
def phase12_exam_approval(exam_id: str, p: Phase12ExamApprovalRequest, r: Request):
    return run(lambda: phase12().approve_exam_stage(actor(r), exam_id, **p.payload.model_dump()))

@router.post("/phase12/exams/{exam_id}/lifecycle")
def phase12_exam_transition(exam_id: str, p: Phase12ExamTransitionRequest, r: Request):
    return run(lambda: phase12().transition_exam_lifecycle(actor(r), exam_id, **p.payload.model_dump()))

@router.get("/phase12/exams/{exam_id}/governance")
def phase12_exam_governance_get(exam_id: str, r: Request):
    return run(lambda: phase12().exam_governance(actor(r), exam_id))

@router.post("/phase12/exam-sessions/{session_id}/evaluations")
def phase12_exam_evaluation(session_id: str, p: Phase12ExamEvaluationRequest, r: Request):
    return run(lambda: phase12().submit_exam_evaluation(actor(r), session_id, **p.payload.model_dump()))

@router.get("/phase12/exam-sessions/{session_id}/evaluations")
def phase12_exam_evaluation_get(session_id: str, r: Request):
    return run(lambda: phase12().exam_evaluation_summary(actor(r), session_id))

@router.post("/phase12/exam-sessions/{session_id}/appeals", status_code=201)
def phase12_exam_appeal(session_id: str, p: Phase12ExamAppealRequest, r: Request):
    return run(lambda: phase12().submit_exam_appeal(actor(r), session_id, p.payload.reason))

@router.put("/phase12/exam-appeals/{appeal_id}")
def phase12_exam_appeal_decision(appeal_id: str, p: Phase12ExamAppealDecisionRequest, r: Request):
    return run(lambda: phase12().decide_exam_appeal(actor(r), appeal_id, **p.payload.model_dump()))

@router.put("/phase12/exam-sessions/{session_id}/heartbeat")
def phase12_exam_heartbeat(session_id: str, p: Phase12HeartbeatRequest, r: Request):
    return run(lambda: phase12().record_exam_heartbeat(actor(r), session_id, **p.payload.model_dump()))

@router.get("/phase12/exams/{exam_id}/live-monitor")
def phase12_exam_live_monitor(exam_id: str, r: Request, stale_seconds: int = 45):
    return run(lambda: phase12().live_exam_monitor(actor(r), exam_id, stale_seconds=stale_seconds))

@router.post("/institutions/{institution_id}/phase12/ai-models", status_code=201)
def phase12_model_profile(institution_id: str, p: Phase12ModelProfileRequest, r: Request):
    return run(lambda: phase12().register_ai_model_profile(actor(r), institution_id, **p.payload.model_dump()))

@router.post("/phase12/ai-models/{profile_id}/qualify")
def phase12_model_qualify(profile_id: str, r: Request):
    return run(lambda: phase12().qualify_ai_model_profile(actor(r), profile_id))

@router.get("/phase12/hardware-posture")
def phase12_hardware_posture():
    return phase12().runtime_hardware_posture()

@router.post("/institutions/{institution_id}/phase12/rag-documents", status_code=201)
def phase12_rag_document(institution_id: str, p: Phase12RAGDocumentRequest, r: Request):
    data = p.payload.model_dump()
    project_id = data.pop("project_id")
    source_path = data.pop("source_path")
    return run(lambda: phase12().register_rag_document(actor(r), institution_id, project_id, source_path, **data))

@router.put("/phase12/rag-documents/{document_id}/review")
def phase12_rag_review(document_id: str, p: Phase12RAGReviewRequest, r: Request):
    return run(lambda: phase12().approve_rag_document(actor(r), document_id, **p.payload.model_dump()))

@router.post("/institutions/{institution_id}/phase12/rag-evaluations", status_code=201)
def phase12_rag_evaluation(institution_id: str, p: Phase12RAGEvaluationRequest, r: Request):
    data = p.payload.model_dump()
    project_id = data.pop("project_id")
    query_text = data.pop("query_text")
    return run(lambda: phase12().record_rag_evaluation(actor(r), institution_id, project_id, query_text, **data))

@router.post("/institutions/{institution_id}/phase12/delivery-providers", status_code=201)
def phase12_delivery_provider(institution_id: str, p: Phase12DeliveryProviderRequest, r: Request):
    return run(lambda: phase12().configure_delivery_provider(actor(r), institution_id, **p.payload.model_dump()))

@router.get("/institutions/{institution_id}/phase12/completion-posture")
def phase12_completion_posture(institution_id: str, r: Request):
    return run(lambda: phase12().final_completion_posture(actor(r), institution_id))


# ---------------- Phase 13 local-autonomy typed API ----------------
class Phase13RAGIngestData(StrictModel):
    chunk_chars: int = Field(default=1400, ge=300, le=8000)
    overlap_chars: int = Field(default=180, ge=0, le=2500)

class Phase13RAGIngestRequest(StrictModel):
    payload: Phase13RAGIngestData

class Phase13RAGSearchData(StrictModel):
    project_id: str = Field(min_length=1, max_length=300)
    query: str = Field(min_length=2, max_length=8000)
    limit: int = Field(default=8, ge=1, le=30)

class Phase13RAGSearchRequest(StrictModel):
    payload: Phase13RAGSearchData

class Phase13RAGContextData(StrictModel):
    project_id: str = Field(min_length=1, max_length=300)
    query: str = Field(min_length=2, max_length=8000)
    limit: int = Field(default=8, ge=1, le=30)
    max_characters: int = Field(default=12000, ge=1000, le=50000)

class Phase13RAGContextRequest(StrictModel):
    payload: Phase13RAGContextData

class Phase13TimetableRequirement(StrictModel):
    subject_id: str = Field(min_length=1, max_length=200)
    teacher_id: str = Field(min_length=1, max_length=200)
    student_group: str = Field(min_length=1, max_length=300)
    room_candidates: list[str] = Field(min_length=1, max_length=50)
    sessions_per_week: int = Field(default=1, ge=1, le=20)
    duration_minutes: int = Field(default=60, ge=15, le=360)
    preferred_weekdays: list[int] = Field(default_factory=list, max_length=7)
    priority: int = Field(default=50, ge=0, le=100)

class Phase13TimetableData(StrictModel):
    term_start: str
    weeks: int = Field(ge=1, le=104)
    requirements: list[Phase13TimetableRequirement] = Field(min_length=1, max_length=500)
    weekdays: list[int] = Field(default_factory=lambda: [0,1,2,3,4], min_length=1, max_length=7)
    day_start: str = Field(default="09:00", pattern=r"^\d{2}:\d{2}$")
    day_end: str = Field(default="17:00", pattern=r"^\d{2}:\d{2}$")
    slot_minutes: int = Field(default=60, ge=15, le=180)
    academic_year: str = Field(default="", max_length=80)
    term: str = Field(default="", max_length=80)
    commit: bool = False

class Phase13TimetableRequest(StrictModel):
    payload: Phase13TimetableData

class Phase13NotificationData(StrictModel):
    recipient_id: str = Field(min_length=1, max_length=200)
    event_type: str = Field(min_length=1, max_length=160)
    channel: Literal["in_app", "email", "desktop", "sms", "whatsapp"] = "in_app"
    destination: str = Field(default="", max_length=500)
    template_key: str = Field(default="", max_length=120)
    subject: str = Field(default="", max_length=500)
    body: str = Field(default="", max_length=100000)
    context: dict[str, Any] = Field(default_factory=dict)
    payload_data: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(default="", max_length=200)
    priority: int = Field(default=50, ge=0, le=100)
    requested_at: str | None = None

class Phase13NotificationRequest(StrictModel):
    payload: Phase13NotificationData

class Phase13DigestData(StrictModel):
    recipient_id: str = Field(min_length=1, max_length=200)
    since: str | None = None
    mark_read: bool = False

class Phase13DigestRequest(StrictModel):
    payload: Phase13DigestData

class Phase13RetentionData(StrictModel):
    dry_run: bool = True
    confirmation: str = Field(default="", max_length=300)

class Phase13RetentionRequest(StrictModel):
    payload: Phase13RetentionData

@router.post("/phase13/rag-documents/{document_id}/ingest")
def phase13_rag_ingest(document_id: str, p: Phase13RAGIngestRequest, r: Request):
    return run(lambda: phase13().ingest_rag_document(actor(r), document_id, **p.payload.model_dump()))

@router.post("/institutions/{institution_id}/phase13/rag-search")
def phase13_rag_search(institution_id: str, p: Phase13RAGSearchRequest, r: Request):
    data = p.payload.model_dump()
    project_id, query = data.pop("project_id"), data.pop("query")
    return run(lambda: phase13().search_rag(actor(r), institution_id, project_id, query, **data))

@router.post("/institutions/{institution_id}/phase13/rag-context")
def phase13_rag_context(institution_id: str, p: Phase13RAGContextRequest, r: Request):
    data = p.payload.model_dump()
    project_id, query = data.pop("project_id"), data.pop("query")
    return run(lambda: phase13().rag_context_bundle(actor(r), institution_id, project_id, query, **data))

@router.post("/institutions/{institution_id}/phase13/timetable-plans", status_code=201)
def phase13_timetable_plan(institution_id: str, p: Phase13TimetableRequest, r: Request):
    data = p.payload.model_dump()
    data["requirements"] = [dict(item) for item in data["requirements"]]
    return run(lambda: phase13().generate_timetable_plan(actor(r), institution_id, **data))

@router.get("/phase13/timetable-plans/{run_id}")
def phase13_timetable_run(run_id: str, r: Request):
    return run(lambda: phase13().timetable_generation_run(actor(r), run_id))

@router.post("/institutions/{institution_id}/phase13/notifications", status_code=201)
def phase13_notification(institution_id: str, p: Phase13NotificationRequest, r: Request):
    data = p.payload.model_dump()
    recipient_id = data.pop("recipient_id")
    data["payload"] = data.pop("payload_data")
    return run(lambda: phase13().queue_policy_notification(actor(r), institution_id, recipient_id, **data))

@router.post("/institutions/{institution_id}/phase13/notification-digests")
def phase13_digest(institution_id: str, p: Phase13DigestRequest, r: Request):
    data = p.payload.model_dump()
    recipient_id = data.pop("recipient_id")
    return run(lambda: phase13().build_in_app_digest(actor(r), institution_id, recipient_id, **data))

@router.post("/institutions/{institution_id}/phase13/notifications/requeue-failed")
def phase13_requeue_notifications(institution_id: str, r: Request, limit: int = 100):
    return run(lambda: phase13().requeue_failed_notifications(actor(r), institution_id, limit=limit))

@router.post("/institutions/{institution_id}/phase13/retention/{data_class}")
def phase13_retention(institution_id: str, data_class: str, p: Phase13RetentionRequest, r: Request):
    return run(lambda: phase13().execute_retention_policy(actor(r), institution_id, data_class, **p.payload.model_dump()))

@router.post("/institutions/{institution_id}/phase13/support-bundles", status_code=201)
def phase13_support_bundle(institution_id: str, r: Request):
    return run(lambda: phase13().create_support_bundle(actor(r), institution_id))

@router.get("/phase13/support-bundles/{bundle_id}/verify")
def phase13_support_verify(bundle_id: str, r: Request):
    return run(lambda: phase13().verify_support_bundle(actor(r), bundle_id))

@router.get("/institutions/{institution_id}/phase13/posture")
def phase13_posture(institution_id: str, r: Request):
    return run(lambda: phase13().phase13_posture(actor(r), institution_id))

# ---------------- Phase 14 academic-quality typed API ----------------
class Phase14OutcomeData(StrictModel):
    code: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=20_000)
    outcome_level: Literal["course", "program", "institution"] = "course"
    subject_id: str | None = Field(default=None, max_length=200)
    unit_id: str | None = Field(default=None, max_length=200)
    bloom_level: Literal["remember", "understand", "apply", "analyze", "evaluate", "create"] = "understand"
    target_percent: float = Field(default=60, gt=0, le=100)

class Phase14OutcomeRequest(StrictModel):
    payload: Phase14OutcomeData

class Phase14OutcomeRelationshipData(StrictModel):
    target_outcome_id: str = Field(min_length=1, max_length=200)
    strength: int = Field(default=1, ge=1, le=3)
    rationale: str = Field(default="", max_length=5000)

class Phase14OutcomeRelationshipRequest(StrictModel):
    payload: Phase14OutcomeRelationshipData

class Phase14AssessmentMappingData(StrictModel):
    assessment_type: Literal["assignment", "exam_question", "rubric_criterion"]
    assessment_id: str = Field(min_length=1, max_length=300)
    weight: float = Field(default=1, gt=0, le=100)
    rationale: str = Field(default="", max_length=5000)

class Phase14AssessmentMappingRequest(StrictModel):
    payload: Phase14AssessmentMappingData

class Phase14OutcomeEvidenceData(StrictModel):
    evidence_type: Literal["assessment", "report", "curriculum", "meeting", "survey", "external_review", "other"]
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=20_000)
    target_type: str = Field(default="", max_length=100)
    target_id: str = Field(default="", max_length=300)
    source_path: str = Field(default="", max_length=2000)

class Phase14OutcomeEvidenceRequest(StrictModel):
    payload: Phase14OutcomeEvidenceData

class Phase14EvidenceReviewData(StrictModel):
    decision: Literal["approve", "request_changes", "reject"]
    note: str = Field(default="", max_length=10_000)

class Phase14EvidenceReviewRequest(StrictModel):
    payload: Phase14EvidenceReviewData

class Phase14AttainmentData(StrictModel):
    period_start: str | None = None
    period_end: str | None = None

class Phase14AttainmentRequest(StrictModel):
    payload: Phase14AttainmentData

class Phase14QualityCycleData(StrictModel):
    title: str = Field(min_length=1, max_length=500)
    period_start: str
    period_end: str
    standard_name: str = Field(default="Internal quality review", max_length=500)

class Phase14QualityCycleRequest(StrictModel):
    payload: Phase14QualityCycleData

class Phase14ImprovementActionData(StrictModel):
    title: str = Field(min_length=1, max_length=500)
    rationale: str = Field(min_length=1, max_length=10_000)
    owner_id: str = Field(min_length=1, max_length=200)
    outcome_id: str | None = Field(default=None, max_length=200)
    due_at: str | None = None
    priority: Literal["low", "medium", "high", "critical"] = "medium"

class Phase14ImprovementActionRequest(StrictModel):
    payload: Phase14ImprovementActionData

class Phase14ActionUpdateData(StrictModel):
    state: Literal["open", "in_progress", "completed", "cancelled"]
    review_note: str = Field(default="", max_length=10_000)
    completion_evidence: str = Field(default="", max_length=20_000)

class Phase14ActionUpdateRequest(StrictModel):
    payload: Phase14ActionUpdateData

class Phase14SuccessSnapshotData(StrictModel):
    student_id: str = Field(min_length=1, max_length=200)
    subject_id: str = Field(min_length=1, max_length=200)

class Phase14SuccessSnapshotRequest(StrictModel):
    payload: Phase14SuccessSnapshotData

class Phase14InterventionData(StrictModel):
    reason: str = Field(min_length=1, max_length=10_000)
    action_plan: str = Field(min_length=1, max_length=20_000)
    assigned_to: str = Field(min_length=1, max_length=200)
    due_at: str | None = None
    priority: Literal["low", "medium", "high", "critical"] = "medium"

class Phase14InterventionRequest(StrictModel):
    payload: Phase14InterventionData

class Phase14InterventionUpdateData(StrictModel):
    state: Literal["open", "in_progress", "completed", "cancelled"]
    review_note: str = Field(default="", max_length=10_000)

class Phase14InterventionUpdateRequest(StrictModel):
    payload: Phase14InterventionUpdateData

class Phase14CalendarEventData(StrictModel):
    title: str = Field(min_length=1, max_length=500)
    event_type: str = Field(min_length=1, max_length=100)
    starts_at: str
    ends_at: str
    description: str = Field(default="", max_length=20_000)
    location: str = Field(default="", max_length=500)
    audience: dict[str, Any] = Field(default_factory=dict)
    all_day: bool = False

class Phase14CalendarEventRequest(StrictModel):
    payload: Phase14CalendarEventData

@router.post("/institutions/{institution_id}/phase14/outcomes", status_code=201)
def phase14_create_outcome(institution_id: str, p: Phase14OutcomeRequest, r: Request):
    return run(lambda: phase14().create_learning_outcome(actor(r), institution_id, **p.payload.model_dump()))

@router.post("/phase14/outcomes/{outcome_id}/relationships", status_code=201)
def phase14_outcome_relationship(outcome_id: str, p: Phase14OutcomeRelationshipRequest, r: Request):
    data = p.payload.model_dump()
    target = data.pop("target_outcome_id")
    return run(lambda: phase14().map_outcome_relationship(actor(r), outcome_id, target, **data))

@router.post("/phase14/outcomes/{outcome_id}/assessment-mappings", status_code=201)
def phase14_assessment_mapping(outcome_id: str, p: Phase14AssessmentMappingRequest, r: Request):
    return run(lambda: phase14().map_assessment_to_outcome(actor(r), outcome_id, **p.payload.model_dump()))

@router.post("/phase14/outcomes/{outcome_id}/evidence", status_code=201)
def phase14_outcome_evidence(outcome_id: str, p: Phase14OutcomeEvidenceRequest, r: Request):
    return run(lambda: phase14().submit_outcome_evidence(actor(r), outcome_id, **p.payload.model_dump()))

@router.put("/phase14/outcome-evidence/{evidence_id}/review")
def phase14_review_evidence(evidence_id: str, p: Phase14EvidenceReviewRequest, r: Request):
    return run(lambda: phase14().review_outcome_evidence(actor(r), evidence_id, **p.payload.model_dump()))

@router.post("/phase14/outcomes/{outcome_id}/attainment")
def phase14_outcome_attainment(outcome_id: str, p: Phase14AttainmentRequest, r: Request):
    return run(lambda: phase14().calculate_outcome_attainment(actor(r), outcome_id, **p.payload.model_dump()))

@router.get("/institutions/{institution_id}/phase14/evidence-matrix")
def phase14_evidence_matrix(institution_id: str, r: Request, subject_id: str | None = None):
    return run(lambda: phase14().accreditation_evidence_matrix(actor(r), institution_id, subject_id=subject_id))

@router.post("/institutions/{institution_id}/phase14/quality-cycles", status_code=201)
def phase14_quality_cycle(institution_id: str, p: Phase14QualityCycleRequest, r: Request):
    return run(lambda: phase14().create_quality_cycle(actor(r), institution_id, **p.payload.model_dump()))

@router.post("/phase14/quality-cycles/{cycle_id}/actions", status_code=201)
def phase14_improvement_action(cycle_id: str, p: Phase14ImprovementActionRequest, r: Request):
    return run(lambda: phase14().create_improvement_action(actor(r), cycle_id, **p.payload.model_dump()))

@router.put("/phase14/improvement-actions/{action_id}")
def phase14_update_action(action_id: str, p: Phase14ActionUpdateRequest, r: Request):
    return run(lambda: phase14().update_improvement_action(actor(r), action_id, **p.payload.model_dump()))

@router.post("/phase14/exams/{exam_id}/psychometrics")
def phase14_psychometrics(exam_id: str, r: Request):
    return run(lambda: phase14().run_exam_psychometrics(actor(r), exam_id))

@router.get("/phase14/psychometric-runs/{run_id}")
def phase14_psychometric_run(run_id: str, r: Request):
    return run(lambda: phase14().psychometric_run(actor(r), run_id))

@router.post("/institutions/{institution_id}/phase14/success-snapshots", status_code=201)
def phase14_success_snapshot(institution_id: str, p: Phase14SuccessSnapshotRequest, r: Request):
    data = p.payload.model_dump()
    return run(lambda: phase14().calculate_student_success_snapshot(actor(r), institution_id, data["student_id"], data["subject_id"]))

@router.post("/phase14/success-snapshots/{snapshot_id}/interventions", status_code=201)
def phase14_intervention(snapshot_id: str, p: Phase14InterventionRequest, r: Request):
    return run(lambda: phase14().create_intervention_case(actor(r), snapshot_id, **p.payload.model_dump()))

@router.put("/phase14/interventions/{case_id}")
def phase14_intervention_update(case_id: str, p: Phase14InterventionUpdateRequest, r: Request):
    return run(lambda: phase14().update_intervention_case(actor(r), case_id, **p.payload.model_dump()))

@router.post("/institutions/{institution_id}/phase14/calendar-events", status_code=201)
def phase14_calendar_event(institution_id: str, p: Phase14CalendarEventRequest, r: Request):
    return run(lambda: phase14().create_calendar_event(actor(r), institution_id, **p.payload.model_dump()))

@router.get("/institutions/{institution_id}/phase14/calendar")
def phase14_calendar(institution_id: str, r: Request, start_at: str, end_at: str):
    return run(lambda: phase14().academic_calendar(actor(r), institution_id, start_at=start_at, end_at=end_at))

@router.post("/institutions/{institution_id}/phase14/calendar-export")
def phase14_calendar_export(institution_id: str, r: Request, start_at: str, end_at: str):
    return run(lambda: phase14().export_calendar_ics(actor(r), institution_id, start_at=start_at, end_at=end_at))

@router.get("/institutions/{institution_id}/phase14/posture")
def phase14_posture(institution_id: str, r: Request):
    return run(lambda: phase14().phase14_posture(actor(r), institution_id))


# ---------------------------------------------------------------------------
# Phase 15 — Production runtime, real-time events, semantic RAG and research
# ---------------------------------------------------------------------------
class Phase15EventData(StrictModel):
    channel: str = Field(min_length=1, max_length=120)
    event_type: str = Field(min_length=1, max_length=120)
    payload: dict[str, Any] = Field(default_factory=dict)
    target_type: str = Field(default="", max_length=120)
    target_id: str = Field(default="", max_length=300)
    audience: dict[str, Any] = Field(default_factory=dict)
    expires_at: str | None = None

class Phase15EventRequest(StrictModel):
    payload: Phase15EventData

class Phase15RAGIndexData(StrictModel):
    project_id: str = Field(min_length=1, max_length=300)
    model_name: str = Field(default="biointel-hash-embedding-v1", max_length=300)
    dimensions: int = Field(default=384, ge=64, le=4096)

class Phase15RAGIndexRequest(StrictModel):
    payload: Phase15RAGIndexData

class Phase15HybridSearchData(StrictModel):
    project_id: str = Field(min_length=1, max_length=300)
    query: str = Field(min_length=2, max_length=20_000)
    limit: int = Field(default=8, ge=1, le=30)
    vector_weight: float = Field(default=0.55, ge=0, le=1)
    model_name: str = Field(default="biointel-hash-embedding-v1", max_length=300)

class Phase15HybridSearchRequest(StrictModel):
    payload: Phase15HybridSearchData

class Phase15ModelRuntimeData(StrictModel):
    name: str = Field(min_length=1, max_length=300)
    provider_type: Literal["ollama", "openai_compatible", "llama_cpp"]
    model_name: str = Field(min_length=1, max_length=300)
    endpoint: str = Field(default="", max_length=2000)
    secret_reference: str = Field(default="", max_length=300)
    context_window: int = Field(default=4096, ge=512, le=1_000_000)
    external_processing: bool = False

class Phase15ModelRuntimeRequest(StrictModel):
    payload: Phase15ModelRuntimeData

class Phase15GenerateData(StrictModel):
    prompt: str = Field(min_length=1, max_length=200_000)
    system_prompt: str = Field(default="", max_length=100_000)
    allow_external_processing: bool = False
    max_tokens: int = Field(default=512, ge=1, le=4096)

class Phase15GenerateRequest(StrictModel):
    payload: Phase15GenerateData

class Phase15PulseProviderData(StrictModel):
    provider: Literal["pubmed", "europe_pmc", "crossref", "openalex", "arxiv"]
    name: str = Field(min_length=1, max_length=300)
    query: str = Field(min_length=1, max_length=2000)
    config: dict[str, Any] = Field(default_factory=dict)

class Phase15PulseProviderRequest(StrictModel):
    payload: Phase15PulseProviderData

class Phase15MediaAssetData(StrictModel):
    source_path: str = Field(min_length=1, max_length=4000)
    probe: bool = True

class Phase15MediaAssetRequest(StrictModel):
    payload: Phase15MediaAssetData

class Phase15PlaybackData(StrictModel):
    event_type: Literal["play", "pause", "progress", "seek", "ended", "rate_change"]
    position_seconds: float = Field(ge=0)
    session_id: str = Field(min_length=1, max_length=200)
    client_event_id: str = Field(min_length=1, max_length=200)
    playback_rate: float = Field(default=1, ge=0.25, le=4)

class Phase15PlaybackRequest(StrictModel):
    payload: Phase15PlaybackData

@router.post("/institutions/{institution_id}/phase15/events", status_code=201)
def phase15_publish_event(institution_id: str, p: Phase15EventRequest, r: Request):
    return run(lambda: phase15().publish_event(actor(r), institution_id, **p.payload.model_dump()))

@router.get("/institutions/{institution_id}/phase15/events")
def phase15_poll_events(institution_id: str, r: Request, after_sequence: int = 0, channels: str = "", limit: int = 100):
    values = [value.strip() for value in channels.split(",") if value.strip()]
    return run(lambda: phase15().poll_events(actor(r), institution_id, after_sequence=after_sequence, channels=values, limit=limit))

@router.get("/institutions/{institution_id}/phase15/events/stream")
async def phase15_stream_events(institution_id: str, r: Request, after_sequence: int = 0, channels: str = ""):
    current_actor = actor(r)
    values = [value.strip() for value in channels.split(",") if value.strip()]

    async def events():
        cursor = max(0, int(after_sequence))
        yield "retry: 2000\n\n"
        for _ in range(150):  # bounded five-minute stream
            if await r.is_disconnected():
                break
            result = phase15().poll_events(current_actor, institution_id, after_sequence=cursor, channels=values, limit=100)
            for item in result["events"]:
                cursor = max(cursor, int(item["sequence"]))
                yield f"id: {cursor}\nevent: {item['event_type']}\ndata: {json.dumps(item, ensure_ascii=False, default=str)}\n\n"
            if not result["events"]:
                yield ": keepalive\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@router.post("/institutions/{institution_id}/phase15/rag-indexes", status_code=201)
def phase15_build_rag_index(institution_id: str, p: Phase15RAGIndexRequest, r: Request):
    return run(lambda: phase15().build_hybrid_rag_index(actor(r), institution_id, **p.payload.model_dump()))

@router.post("/institutions/{institution_id}/phase15/rag-search")
def phase15_hybrid_search(institution_id: str, p: Phase15HybridSearchRequest, r: Request):
    return run(lambda: phase15().hybrid_rag_search(actor(r), institution_id, **p.payload.model_dump()))

@router.post("/institutions/{institution_id}/phase15/model-runtimes", status_code=201)
def phase15_model_runtime(institution_id: str, p: Phase15ModelRuntimeRequest, r: Request):
    return run(lambda: phase15().register_model_runtime(actor(r), institution_id, **p.payload.model_dump()))

@router.post("/phase15/model-runtimes/{runtime_id}/verify")
def phase15_verify_model_runtime(runtime_id: str, r: Request):
    return run(lambda: phase15().verify_model_runtime(actor(r), runtime_id))

@router.post("/phase15/model-runtimes/{runtime_id}/generate")
def phase15_generate(runtime_id: str, p: Phase15GenerateRequest, r: Request):
    return run(lambda: phase15().generate_with_runtime(actor(r), runtime_id, **p.payload.model_dump()))

@router.post("/institutions/{institution_id}/phase15/pulse-providers", status_code=201)
def phase15_pulse_provider(institution_id: str, p: Phase15PulseProviderRequest, r: Request):
    return run(lambda: phase15().configure_pulse_provider(actor(r), institution_id, **p.payload.model_dump()))

@router.post("/phase15/pulse-providers/{config_id}/sync")
def phase15_sync_pulse(config_id: str, r: Request, limit: int = 20):
    return run(lambda: phase15().sync_pulse_provider(actor(r), config_id, limit=limit))

@router.post("/phase15/lectures/{lecture_id}/media-assets", status_code=201)
def phase15_media_asset(lecture_id: str, p: Phase15MediaAssetRequest, r: Request):
    return run(lambda: phase15().register_media_asset(actor(r), lecture_id, **p.payload.model_dump()))

@router.post("/phase15/lectures/{lecture_id}/playback-events", status_code=201)
def phase15_playback_event(lecture_id: str, p: Phase15PlaybackRequest, r: Request):
    return run(lambda: phase15().record_playback_event(actor(r), lecture_id, **p.payload.model_dump()))

@router.get("/phase15/lectures/{lecture_id}/playback-summary")
def phase15_playback_summary(lecture_id: str, r: Request):
    return run(lambda: phase15().playback_summary(actor(r), lecture_id))

@router.get("/institutions/{institution_id}/phase15/posture")
def phase15_posture(institution_id: str, r: Request):
    return run(lambda: phase15().phase15_posture(actor(r), institution_id))


class Phase16ConsumerData(StrictModel):
    consumer_key: str = Field(min_length=1, max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict)
class Phase16ConsumerRequest(StrictModel):
    payload: Phase16ConsumerData

class Phase16AdvancedSearchData(StrictModel):
    project_id: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=2, max_length=4000)
    limit: int = Field(default=8, ge=1, le=20)
    vector_weight: float = Field(default=.55, ge=0, le=1)
    diversity_weight: float = Field(default=.25, ge=0, le=.8)
class Phase16AdvancedSearchRequest(StrictModel):
    payload: Phase16AdvancedSearchData

class Phase16RagEvalCaseData(StrictModel):
    project_id: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=2, max_length=4000)
    expected_document_ids: list[str] = Field(default_factory=list)
    expected_chunk_ids: list[str] = Field(default_factory=list)
class Phase16RagEvalCaseRequest(StrictModel):
    payload: Phase16RagEvalCaseData

class Phase16PulseAlertRuleData(StrictModel):
    name: str = Field(min_length=1, max_length=180)
    query_terms: list[str] = Field(min_length=1, max_length=50)
    providers: list[str] = Field(default_factory=list)
    record_types: list[str] = Field(default_factory=list)
class Phase16PulseAlertRuleRequest(StrictModel):
    payload: Phase16PulseAlertRuleData

class Phase16ScientificDatasetData(StrictModel):
    source_path: str = Field(min_length=1, max_length=2000)
    name: str = Field(default="", max_length=200)
class Phase16ScientificDatasetRequest(StrictModel):
    payload: Phase16ScientificDatasetData

class Phase16ScientificRunData(StrictModel):
    analysis_type: str = Field(min_length=1, max_length=40)
    parameters: dict[str, Any] = Field(default_factory=dict)
class Phase16ScientificRunRequest(StrictModel):
    payload: Phase16ScientificRunData

class Phase16MediaPlanData(StrictModel):
    profile: Literal["thumbnail", "mp4_720p", "hls_720p"]
class Phase16MediaPlanRequest(StrictModel):
    payload: Phase16MediaPlanData

class Phase16TranscriptionPlanData(StrictModel):
    language: Literal["auto", "english", "hindi", "hinglish"] = "auto"
class Phase16TranscriptionPlanRequest(StrictModel):
    payload: Phase16TranscriptionPlanData

class Phase16TranscriptionApproveData(StrictModel):
    replace_existing: bool = False
class Phase16TranscriptionApproveRequest(StrictModel):
    payload: Phase16TranscriptionApproveData

class Phase16TranscriptionRejectData(StrictModel):
    reason: str = Field(min_length=1, max_length=1000)
class Phase16TranscriptionRejectRequest(StrictModel):
    payload: Phase16TranscriptionRejectData

@router.post("/institutions/{institution_id}/phase16/event-consumers", status_code=201)
def phase16_register_consumer(institution_id: str, p: Phase16ConsumerRequest, r: Request):
    return run(lambda: phase16().register_event_consumer(actor(r), institution_id, **p.payload.model_dump()))

@router.post("/phase16/event-consumers/{consumer_id}/heartbeat")
def phase16_consumer_heartbeat(consumer_id: str, r: Request):
    return run(lambda: phase16().heartbeat_event_consumer(actor(r), consumer_id))

@router.get("/phase16/event-consumers/{consumer_id}/events")
def phase16_consume_events(consumer_id: str, r: Request, channels: str = "", limit: int = 100, acknowledge: bool = True):
    values = [value.strip() for value in channels.split(",") if value.strip()]
    return run(lambda: phase16().consume_events(actor(r), consumer_id, channels=values, limit=limit, acknowledge=acknowledge))

@router.post("/institutions/{institution_id}/phase16/events/cleanup")
def phase16_cleanup_events(institution_id: str, r: Request, retention_days: int = 14):
    return run(lambda: phase16().cleanup_event_stream(actor(r), institution_id, retention_days=retention_days))

@router.post("/institutions/{institution_id}/phase16/rag-search")
def phase16_advanced_search(institution_id: str, p: Phase16AdvancedSearchRequest, r: Request):
    return run(lambda: phase16().advanced_rag_search(actor(r), institution_id, **p.payload.model_dump()))

@router.post("/institutions/{institution_id}/phase16/rag-evaluation-cases", status_code=201)
def phase16_rag_eval_case(institution_id: str, p: Phase16RagEvalCaseRequest, r: Request):
    return run(lambda: phase16().create_rag_evaluation_case(actor(r), institution_id, **p.payload.model_dump()))

@router.post("/institutions/{institution_id}/phase16/rag-evaluations/{project_id}")
def phase16_run_rag_eval(institution_id: str, project_id: str, r: Request, top_k: int = 5):
    return run(lambda: phase16().run_rag_evaluation(actor(r), institution_id, project_id, top_k=top_k))

@router.post("/institutions/{institution_id}/phase16/pulse-alert-rules", status_code=201)
def phase16_pulse_alert_rule(institution_id: str, p: Phase16PulseAlertRuleRequest, r: Request):
    return run(lambda: phase16().create_pulse_alert_rule(actor(r), institution_id, **p.payload.model_dump()))

@router.post("/institutions/{institution_id}/phase16/pulse-alerts/evaluate")
def phase16_evaluate_pulse_alerts(institution_id: str, r: Request):
    return run(lambda: phase16().evaluate_pulse_alerts(actor(r), institution_id))

@router.get("/institutions/{institution_id}/phase16/pulse-alerts")
def phase16_pulse_alert_hits(institution_id: str, r: Request, unread_only: bool = False):
    return run(lambda: phase16().pulse_alert_hits(actor(r), institution_id, unread_only=unread_only))

@router.post("/phase16/pulse-alerts/{hit_id}/read")
def phase16_mark_pulse_alert_read(hit_id: str, r: Request):
    return run(lambda: phase16().mark_pulse_alert_read(actor(r), hit_id))

@router.post("/institutions/{institution_id}/phase16/scientific-datasets", status_code=201)
def phase16_scientific_dataset(institution_id: str, p: Phase16ScientificDatasetRequest, r: Request):
    return run(lambda: phase16().register_scientific_dataset(actor(r), institution_id, **p.payload.model_dump()))

@router.post("/phase16/scientific-datasets/{dataset_id}/runs", status_code=201)
def phase16_scientific_run(dataset_id: str, p: Phase16ScientificRunRequest, r: Request):
    return run(lambda: phase16().run_sequence_analysis(actor(r), dataset_id, **p.payload.model_dump()))

@router.post("/phase16/media-assets/{asset_id}/processing-jobs", status_code=201)
def phase16_media_plan(asset_id: str, p: Phase16MediaPlanRequest, r: Request):
    return run(lambda: phase16().plan_media_processing(actor(r), asset_id, **p.payload.model_dump()))

@router.post("/phase16/media-processing-jobs/{job_id}/execute")
def phase16_media_execute(job_id: str, r: Request, timeout_seconds: int = 900):
    return run(lambda: phase16().execute_media_processing(actor(r), job_id, timeout_seconds=timeout_seconds))

@router.get("/phase16/transcription/readiness")
def phase16_transcription_readiness():
    return phase16().transcription_readiness()

@router.post("/phase16/lectures/{lecture_id}/transcription-jobs", status_code=201)
def phase16_transcription_plan(lecture_id: str, p: Phase16TranscriptionPlanRequest, r: Request):
    return run(lambda: phase16().plan_lecture_transcription(actor(r), lecture_id, **p.payload.model_dump()))

@router.post("/phase16/transcription-jobs/{job_id}/execute")
def phase16_transcription_execute(job_id: str, r: Request):
    return run(lambda: phase16().execute_lecture_transcription(actor(r), job_id))

@router.get("/phase16/transcription-jobs/{job_id}/candidate")
def phase16_transcription_candidate(job_id: str, r: Request):
    return run(lambda: phase16().transcription_candidate(actor(r), job_id))

@router.post("/phase16/transcription-jobs/{job_id}/approve")
def phase16_transcription_approve(job_id: str, p: Phase16TranscriptionApproveRequest, r: Request):
    return run(lambda: phase16().approve_lecture_transcription(actor(r), job_id, **p.payload.model_dump()))

@router.post("/phase16/transcription-jobs/{job_id}/reject")
def phase16_transcription_reject(job_id: str, p: Phase16TranscriptionRejectRequest, r: Request):
    return run(lambda: phase16().reject_lecture_transcription(actor(r), job_id, **p.payload.model_dump()))

@router.get("/institutions/{institution_id}/phase16/transcription-jobs")
def phase16_transcription_jobs(institution_id: str, r: Request, lecture_id: str = ""):
    return run(lambda: phase16().transcription_jobs(actor(r), institution_id, lecture_id=lecture_id))

@router.get("/institutions/{institution_id}/phase16/posture")
def phase16_posture(institution_id: str, r: Request):
    return run(lambda: phase16().phase16_posture(actor(r), institution_id))

# Phase 17-22 Education OS routes share the canonical Education database.
from .phase17_22.api import router as education_os_router
router.include_router(education_os_router)

# Phase 23-30 enterprise Education platform routes share the canonical database.
from .phase23_30.api import router as education_enterprise_router
router.include_router(education_enterprise_router)

# Phase 31-35 research platform routes share the canonical Education database.
from .phase32_35.api import router as education_research_platform_router
router.include_router(education_research_platform_router)
from .phase32_35.twin_api import router as education_digital_twin_router
router.include_router(education_digital_twin_router)
from .phase32_35.compute_api import router as education_research_compute_router
router.include_router(education_research_compute_router)
from .phase32_35.discovery_api import router as education_scientific_discovery_router
router.include_router(education_scientific_discovery_router)

# Selective Education Mega R9 routes are additive; every legacy route above remains registered.
from .selective_mega_api import router as education_selective_mega_router
router.include_router(education_selective_mega_router)
