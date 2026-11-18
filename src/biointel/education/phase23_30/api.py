from __future__ import annotations

import time
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from ..paths import user_data_root
from ..platform import Conflict, Denied, EducationError, EducationPlatform, Missing
from .service import EducationEnterprisePlatform

router = APIRouter(prefix="/platform", tags=["Education Phases 23-30"])
public_router = APIRouter(prefix="/api/v1", tags=["BioIntel public API v1"])
_SERVICE: EducationEnterprisePlatform | None = None


def service() -> EducationEnterprisePlatform:
    global _SERVICE
    if _SERVICE is None:
        root = user_data_root()
        platform = EducationPlatform(
            root / "education" / "education.sqlite3",
            root / "education" / "media",
        )
        _SERVICE = EducationEnterprisePlatform(platform, root=str(root))
    return _SERVICE


def run(operation):
    try:
        return operation()
    except Denied as exc:
        raise HTTPException(403, detail={"code": "permission_denied", "message": str(exc)}) from exc
    except Missing as exc:
        raise HTTPException(404, detail={"code": "not_found", "message": str(exc)}) from exc
    except Conflict as exc:
        raise HTTPException(409, detail={"code": "conflict", "message": str(exc)}) from exc
    except EducationError as exc:
        raise HTTPException(422, detail={"code": "validation_error", "message": str(exc)}) from exc


class PilotCreate(BaseModel):
    actor: str
    institution_id: str
    name: str = Field(min_length=1, max_length=200)
    starts_on: str = ""
    ends_on: str = ""
    goals: list[str] = Field(default_factory=list)
    administrator_ids: list[str] = Field(default_factory=list)
    departments: list[str] = Field(default_factory=list)
    user_limit: int = Field(default=500, ge=1, le=100_000)
    feature_flags: dict[str, bool] = Field(default_factory=dict)
    terms_version: str = ""
    terms_accepted: bool = False
    support_contact: str = ""


class PilotTransition(BaseModel):
    actor: str
    to_status: str
    reason: str = ""
    blockers: list[str] = Field(default_factory=list)
    readiness_decision: str = ""


class OnboardingSave(BaseModel):
    actor: str
    user_id: str
    role: str
    completed_steps: list[str] = Field(default_factory=list)
    configuration: dict[str, Any] = Field(default_factory=dict)
    data_mode: Literal["none", "sample", "real_import"] = "none"
    validation_errors: list[str] = Field(default_factory=list)


class ImportDryRun(BaseModel):
    actor: str
    institution_id: str
    entity_type: str
    source_path: str
    pilot_id: str = ""


class ImportCommit(BaseModel):
    actor: str
    confirmation_digest: str = Field(min_length=64, max_length=64)


class AgentTaskCreate(BaseModel):
    actor: str
    institution_id: str
    agent_key: str
    task_input: dict[str, Any]
    requested_tools: list[str] | None = None
    provider: str = "local"
    provider_model: str = ""
    subject_user_id: str = ""
    parent_task_id: str = ""
    idempotency_key: str = Field(min_length=1, max_length=160)
    timeout_seconds: int = Field(default=120, ge=5, le=900)


class AgentApproval(BaseModel):
    actor: str
    decision: Literal["approved", "rejected"]
    note: str = ""


class LabAttemptCreate(BaseModel):
    actor: str
    institution_id: str
    experiment_id: str
    student_id: str = ""
    assigned_by: str = ""
    scenario_seed: int | None = None


class LabStep(BaseModel):
    actor: str
    action: str
    values: dict[str, Any] = Field(default_factory=dict)
    safety_acknowledged: bool = False
    introduce_error: bool = False


class LabNotebook(BaseModel):
    actor: str
    entry_type: str
    body: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    attachment_path: str = ""
    protocol_deviation: bool = False


class LabSubmit(BaseModel):
    actor: str
    results: dict[str, Any]
    discussion: str
    references: list[dict[str, Any]] = Field(default_factory=list)


class LabAssessment(BaseModel):
    actor: str
    procedural_score: float = Field(ge=0, le=100)
    calculation_score: float = Field(ge=0, le=100)
    safety_score: float = Field(ge=0, le=100)
    interpretation_score: float = Field(ge=0, le=100)
    rubric_score: float = Field(ge=0, le=100)
    viva: list[dict[str, Any]] = Field(default_factory=list)
    feedback: str = ""
    override_reason: str = ""


class ConceptCreate(BaseModel):
    actor: str
    institution_id: str
    key: str
    name: str
    subject_id: str = ""
    description: str = ""
    learning_outcomes: list[str] = Field(default_factory=list)
    skill_keys: list[str] = Field(default_factory=list)


class MasteryEvidence(BaseModel):
    actor: str
    institution_id: str
    student_id: str
    concept_id: str
    evidence_type: str
    correctness: float = Field(ge=0, le=1)
    confidence: float = Field(default=0, ge=0, le=1)
    difficulty: float = Field(default=0.5, ge=0, le=1)
    hint_use: int = Field(default=0, ge=0)
    time_seconds: float = Field(default=0, ge=0)
    practical_score: float | None = Field(default=None, ge=0, le=100)
    examination_score: float | None = Field(default=None, ge=0, le=100)
    self_assessment: float | None = Field(default=None, ge=0, le=1)
    source_id: str = ""


class PaperCreate(BaseModel):
    actor: str
    institution_id: str
    title: str
    doi: str = ""
    pmid: str = ""
    pmcid: str = ""
    authors: list[str] = Field(default_factory=list)
    journal: str = ""
    published_on: str = ""
    abstract: str = ""
    study_type: str = ""
    findings: str = ""
    limitations: str = ""
    source_metadata: dict[str, Any] = Field(default_factory=dict)


class AssetCreate(BaseModel):
    actor: str
    institution_id: str
    asset_type: str
    title: str
    paper_ids: list[str] = Field(min_length=1)
    claim_ids: list[str] = Field(default_factory=list)
    content: dict[str, Any] | None = None


class AssetReview(BaseModel):
    actor: str
    decision: Literal[
        "evidence_verified",
        "faculty_approved",
        "needs_revision",
        "archived",
    ]
    comments: str = ""
    evidence_check: dict[str, Any] = Field(default_factory=dict)


class CredentialIssue(BaseModel):
    actor: str
    institution_id: str
    owner_id: str
    credential_type: str
    title: str
    criteria: dict[str, Any]
    evidence: list[dict[str, Any]] = Field(min_length=1)
    expires_at: str = ""


class IntegrationCreate(BaseModel):
    actor: str
    institution_id: str
    adapter_type: str
    name: str
    configuration: dict[str, Any] = Field(default_factory=dict)
    secret_reference: str = ""
    enabled: bool = False


class ApiKeyCreate(BaseModel):
    actor: str
    institution_id: str
    name: str
    scopes: list[str] = Field(min_length=1)
    expires_at: str = ""


class WebhookCreate(BaseModel):
    actor: str
    institution_id: str
    name: str
    target_url: str
    event_types: list[str] = Field(min_length=1)


class PluginCreate(BaseModel):
    actor: str
    institution_id: str
    manifest: dict[str, Any]
    development_mode: bool = False


class McpPolicyCreate(BaseModel):
    actor: str
    institution_id: str
    principal_id: str
    tool_key: str
    allowed: bool
    write_approval_required: bool = True
    rate_limit_per_minute: int = Field(default=30, ge=1, le=600)


@router.get("/health/{institution_id}")
def platform_health(institution_id: str, actor: str):
    return run(lambda: service().health_snapshot(actor, institution_id))


@router.get("/snapshot/{institution_id}")
def platform_snapshot(institution_id: str, actor: str):
    return run(lambda: service().platform_snapshot(actor, institution_id))


@router.post("/pilots", status_code=201)
def create_pilot(payload: PilotCreate):
    return run(lambda: service().register_pilot(**payload.model_dump()))


@router.post("/pilots/{pilot_id}/transitions")
def transition_pilot(pilot_id: str, payload: PilotTransition):
    values = payload.model_dump()
    actor = values.pop("actor")
    return run(lambda: service().transition_pilot(actor, pilot_id, **values))


@router.post("/pilots/{pilot_id}/onboarding")
def save_onboarding(pilot_id: str, payload: OnboardingSave):
    values = payload.model_dump()
    actor = values.pop("actor")
    return run(lambda: service().save_onboarding(actor, pilot_id, **values))


@router.post("/imports/dry-run", status_code=201)
def dry_run_import(payload: ImportDryRun):
    values = payload.model_dump()
    actor = values.pop("actor")
    institution_id = values.pop("institution_id")
    entity_type = values.pop("entity_type")
    source_path = values.pop("source_path")
    return run(
        lambda: service().dry_run_import(
            actor,
            institution_id,
            entity_type,
            source_path,
            **values,
        )
    )


@router.post("/imports/{job_id}/commit")
def commit_import(job_id: str, payload: ImportCommit):
    return run(
        lambda: service().commit_import(
            payload.actor,
            job_id,
            confirmation_digest=payload.confirmation_digest,
        )
    )


@router.post("/agent-tasks", status_code=201)
def create_agent_task(payload: AgentTaskCreate):
    return run(lambda: service().create_agent_task(**payload.model_dump()))


@router.post("/agent-tasks/{task_id}/approval")
def approve_agent_task(task_id: str, payload: AgentApproval):
    return run(
        lambda: service().approve_agent_task(
            payload.actor,
            task_id,
            decision=payload.decision,
            note=payload.note,
        )
    )


@router.post("/agent-tasks/{task_id}/execute")
def execute_agent_task(task_id: str, actor: str):
    return run(lambda: service().execute_agent_task(actor, task_id))


@router.get("/labs/{institution_id}")
def lab_catalog(
    institution_id: str,
    actor: str,
    discipline: str = "",
    page: int = 1,
    page_size: int = 50,
):
    return run(
        lambda: service().lab_catalog(
            actor,
            institution_id,
            discipline=discipline,
            page=page,
            page_size=page_size,
        )
    )


@router.post("/lab-attempts", status_code=201)
def start_lab_attempt(payload: LabAttemptCreate):
    return run(lambda: service().start_lab_attempt(**payload.model_dump()))


@router.post("/lab-attempts/{attempt_id}/steps")
def record_lab_step(attempt_id: str, payload: LabStep):
    values = payload.model_dump()
    actor = values.pop("actor")
    return run(lambda: service().record_lab_step(actor, attempt_id, **values))


@router.post("/lab-attempts/{attempt_id}/notebook")
def add_lab_notebook(attempt_id: str, payload: LabNotebook):
    values = payload.model_dump()
    actor = values.pop("actor")
    return run(lambda: service().add_lab_notebook_entry(actor, attempt_id, **values))


@router.post("/lab-attempts/{attempt_id}/submit")
def submit_lab_attempt(attempt_id: str, payload: LabSubmit):
    values = payload.model_dump()
    actor = values.pop("actor")
    return run(lambda: service().submit_lab_attempt(actor, attempt_id, **values))


@router.post("/lab-attempts/{attempt_id}/assess")
def assess_lab_attempt(attempt_id: str, payload: LabAssessment):
    values = payload.model_dump()
    actor = values.pop("actor")
    return run(lambda: service().assess_lab_attempt(actor, attempt_id, **values))


@router.post("/concepts", status_code=201)
def create_concept(payload: ConceptCreate):
    return run(lambda: service().create_concept(**payload.model_dump()))


@router.post("/mastery/evidence", status_code=201)
def record_mastery(payload: MasteryEvidence):
    values = payload.model_dump()
    actor = values.pop("actor")
    institution_id = values.pop("institution_id")
    student_id = values.pop("student_id")
    concept_id = values.pop("concept_id")
    return run(
        lambda: service().record_mastery_evidence(
            actor,
            institution_id,
            student_id,
            concept_id,
            **values,
        )
    )


@router.post("/mastery/{institution_id}/{student_id}/{concept_id}/recommend")
def recommend_next(institution_id: str, student_id: str, concept_id: str, actor: str):
    return run(
        lambda: service().recommend_next(
            actor,
            institution_id,
            student_id,
            concept_id,
        )
    )


@router.post("/research/papers", status_code=201)
def create_paper(payload: PaperCreate):
    return run(lambda: service().ingest_research_paper(**payload.model_dump()))


@router.post("/research/assets", status_code=201)
def create_asset(payload: AssetCreate):
    return run(lambda: service().transform_research_asset(**payload.model_dump()))


@router.post("/research/assets/{asset_id}/review")
def review_asset(asset_id: str, payload: AssetReview):
    values = payload.model_dump()
    actor = values.pop("actor")
    return run(lambda: service().review_research_asset(actor, asset_id, **values))


@router.post("/research/assets/{asset_id}/publish")
def publish_asset(asset_id: str, actor: str, target: str):
    return run(lambda: service().publish_research_asset(actor, asset_id, target=target))


@router.post("/credentials", status_code=201)
def issue_credential(payload: CredentialIssue):
    values = payload.model_dump()
    actor = values.pop("actor")
    institution_id = values.pop("institution_id")
    owner_id = values.pop("owner_id")
    return run(
        lambda: service().issue_credential(
            actor,
            institution_id,
            owner_id,
            **values,
        )
    )


@router.get("/credentials/verify/{unique_code}")
def verify_credential(unique_code: str):
    return service().verify_credential(unique_code)


@router.post("/integrations", status_code=201)
def create_integration(payload: IntegrationCreate):
    return run(lambda: service().configure_integration(**payload.model_dump()))


@router.post("/api-keys", status_code=201)
def create_api_key(payload: ApiKeyCreate):
    return run(lambda: service().create_api_key(**payload.model_dump()))


@router.post("/webhooks", status_code=201)
def create_webhook(payload: WebhookCreate):
    return run(lambda: service().register_webhook(**payload.model_dump()))


@router.post("/plugins", status_code=201)
def create_plugin(payload: PluginCreate):
    return run(lambda: service().register_plugin(**payload.model_dump()))


@router.post("/mcp/policies")
def create_mcp_policy(payload: McpPolicyCreate):
    return run(lambda: service().set_mcp_policy(**payload.model_dump()))


@router.get("/release/{institution_id}")
def release_qualification(institution_id: str, actor: str):
    return run(lambda: service().release_qualification(actor, institution_id))


def _bearer(authorization: str) -> str:
    scheme, _, value = authorization.partition(" ")
    if scheme.casefold() != "bearer" or not value.strip():
        raise HTTPException(
            401,
            detail={"code": "authentication_required", "message": "Bearer API key required."},
        )
    return value.strip()


def _public_auth(
    authorization: str,
    scope: str,
    request: Request,
    *,
    idempotency_key: str = "",
) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    auth = run(
        lambda: service().authenticate_api_key(
            _bearer(authorization),
            required_scope=scope,
            route=request.url.path,
            method=request.method,
            request_id=request.headers.get("X-Request-ID", ""),
            idempotency_key=idempotency_key,
        )
    )
    return auth, started


def _record_public(
    auth: dict[str, Any],
    request: Request,
    started: float,
    *,
    status_code: int = 200,
    idempotency_key: str = "",
) -> None:
    service().record_api_usage(
        auth,
        route=request.url.path,
        method=request.method,
        status_code=status_code,
        latency_ms=(time.perf_counter() - started) * 1000,
        request_id=request.headers.get("X-Request-ID", ""),
        idempotency_key=idempotency_key,
    )


@public_router.get("/institutions/{institution_id}/courses")
def public_courses(
    institution_id: str,
    request: Request,
    authorization: str = Header(default=""),
    page: int = 1,
    page_size: int = 50,
):
    auth, started = _public_auth(authorization, "courses:read", request)
    if auth["institution_id"] != institution_id:
        raise HTTPException(403, detail={"code": "tenant_scope_denied"})
    limit, offset = service().paginate(page, page_size)
    rows = service()._all(
        """SELECT id,title,description,difficulty,state,created_at,updated_at
        FROM courses WHERE institution_id=? ORDER BY updated_at DESC LIMIT ? OFFSET ?""",
        (institution_id, limit, offset),
    )
    _record_public(auth, request, started)
    return {"items": rows, "page": max(1, page), "page_size": limit}


@public_router.get("/institutions/{institution_id}/science-records")
def public_science_records(
    institution_id: str,
    request: Request,
    authorization: str = Header(default=""),
    page: int = 1,
    page_size: int = 50,
):
    auth, started = _public_auth(authorization, "science:read", request)
    if auth["institution_id"] != institution_id:
        raise HTTPException(403, detail={"code": "tenant_scope_denied"})
    limit, offset = service().paginate(page, page_size)
    rows = service()._all(
        """SELECT id,doi,pmid,pmcid,title,journal,published_on,
        retraction_state,verification_state
        FROM education_p30_research_papers WHERE institution_id=?
        ORDER BY updated_at DESC LIMIT ? OFFSET ?""",
        (institution_id, limit, offset),
    )
    _record_public(auth, request, started)
    return {"items": rows, "page": max(1, page), "page_size": limit}


@public_router.get("/institutions/{institution_id}/credentials/{unique_code}")
def public_credential(
    institution_id: str,
    unique_code: str,
    request: Request,
    authorization: str = Header(default=""),
):
    auth, started = _public_auth(authorization, "credentials:read", request)
    if auth["institution_id"] != institution_id:
        raise HTTPException(403, detail={"code": "tenant_scope_denied"})
    result = service().verify_credential(unique_code)
    if result.get("institution_id") not in {None, institution_id}:
        raise HTTPException(403, detail={"code": "tenant_scope_denied"})
    _record_public(auth, request, started)
    return result


@public_router.get("/institutions/{institution_id}/agent-tasks")
def public_agent_tasks(
    institution_id: str,
    request: Request,
    authorization: str = Header(default=""),
    page: int = 1,
    page_size: int = 50,
):
    auth, started = _public_auth(authorization, "agent_tasks:read", request)
    if auth["institution_id"] != institution_id:
        raise HTTPException(403, detail={"code": "tenant_scope_denied"})
    limit, offset = service().paginate(page, page_size)
    rows = service()._all(
        """SELECT id,agent_key,state,approval_state,requested_by,
        validation_json,error,created_at,updated_at
        FROM education_p30_agent_tasks WHERE institution_id=?
        ORDER BY updated_at DESC LIMIT ? OFFSET ?""",
        (institution_id, limit, offset),
    )
    _record_public(auth, request, started)
    return {"items": rows, "page": max(1, page), "page_size": limit}
