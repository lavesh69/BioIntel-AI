from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from .core import LiveWorkspaceStore, PermissionDenied, RecordLocked, RevisionConflict, utc_text
from .advanced import LiveWorkspaceAdvancedStore

router = APIRouter(prefix="/v1/live-workspace", tags=["Live Workspace"])
STORE: LiveWorkspaceStore = LiveWorkspaceAdvancedStore()


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    default_join_role: str = "researcher"
    access_code: str | None = Field(default=None, max_length=80)


class WorkspaceJoin(BaseModel):
    access_code: str = Field(min_length=4, max_length=80)
    display_name: str = Field(min_length=1, max_length=80)
    requested_role: str | None = None


class PresenceHeartbeat(BaseModel):
    session_id: str
    display_name: str = Field(min_length=1, max_length=80)
    page_key: str = ""
    page_title: str = ""
    category: str = ""
    project_id: str = ""
    record_type: str = ""
    record_id: str = ""
    activity_state: str = "viewing"
    status_message: str = ""
    client_label: str = ""
    ttl_seconds: int = Field(default=45, ge=20, le=300)


class LockRequest(BaseModel):
    session_id: str
    resource_type: str
    resource_id: str
    note: str = Field(default="", max_length=240)
    ttl_seconds: int = Field(default=120, ge=30, le=900)
    force: bool = False


class ResourceRequest(BaseModel):
    resource_type: str
    resource_id: str
    force: bool = False


class CommentCreate(BaseModel):
    resource_type: str
    resource_id: str
    body: str = Field(min_length=1, max_length=4000)


class ReviewCreate(BaseModel):
    resource_type: str
    resource_id: str
    title: str = Field(min_length=1, max_length=200)
    assigned_to: str = ""
    priority: str = "normal"


class ReviewUpdate(BaseModel):
    status: str
    decision_note: str = Field(default="", max_length=2000)


class MemberRoleUpdate(BaseModel):
    target_user_id: str
    role: str


class RecordRevisionCreate(BaseModel):
    session_id: str
    resource_type: str
    resource_id: str
    expected_revision: int = Field(default=0, ge=0)
    payload_sha256: str = Field(min_length=64, max_length=64)
    summary: str = Field(default="", max_length=500)


class SharedJobUpsert(BaseModel):
    job_id: str
    workflow: str = Field(min_length=1, max_length=180)
    status: str
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    page_key: str = ""
    current_stage: str = Field(default="", max_length=160)
    safe_detail: str = Field(default="", max_length=500)
    result_reference: str = ""


class AccessCodeRotate(BaseModel):
    new_code: str | None = Field(default=None, max_length=80)


class WorkspaceSettingsUpdate(BaseModel):
    settings: dict[str, Any]


class MemberProfileUpdate(BaseModel):
    availability: str = "available"
    status_message: str = Field(default="", max_length=140)
    presence_visibility: str = "workspace"
    notification_mode: str = "all"


class InviteCreate(BaseModel):
    role: str = "researcher"
    project_id: str = ""
    note: str = Field(default="", max_length=500)
    expires_hours: int = Field(default=24, ge=1, le=720)
    max_uses: int = Field(default=1, ge=1, le=100)


class InviteRedeem(BaseModel):
    token: str = Field(min_length=8, max_length=120)
    display_name: str = Field(min_length=1, max_length=80)


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    assigned_to: str = ""
    priority: str = "normal"
    project_id: str = ""
    resource_type: str = ""
    resource_id: str = ""
    due_at_utc: str | None = None


class TaskUpdate(BaseModel):
    status: str | None = None
    assigned_to: str | None = None
    priority: str | None = None
    description: str | None = Field(default=None, max_length=4000)


class BookmarkCreate(BaseModel):
    kind: str
    title: str = Field(min_length=1, max_length=240)
    safe_reference: str = Field(min_length=1, max_length=1000)
    source_name: str = Field(default="", max_length=160)
    evidence_level: str = "ungraded"
    notes: str = Field(default="", max_length=3000)
    project_id: str = ""


class TimelineCreate(BaseModel):
    event_type: str
    title: str = Field(min_length=1, max_length=240)
    safe_detail: str = Field(default="", max_length=3000)
    project_id: str = ""
    subject_alias: str = ""
    occurred_at_utc: str | None = None


class AnnotationCreate(BaseModel):
    resource_type: str
    resource_id: str
    annotation_type: str
    label: str = Field(min_length=1, max_length=500)
    status: str = "draft"
    confidence: float | None = Field(default=None, ge=0, le=1)
    geometry: dict[str, Any] = Field(default_factory=dict)
    attributes: dict[str, Any] = Field(default_factory=dict)
    project_id: str = ""


class AnnotationUpdate(BaseModel):
    expected_revision: int = Field(ge=1)
    label: str | None = Field(default=None, max_length=500)
    status: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    geometry: dict[str, Any] | None = None
    attributes: dict[str, Any] | None = None


class CollaborationSessionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    sync_navigation: bool = True


class CollaborationNavigation(BaseModel):
    page_key: str = ""
    page_title: str = Field(default="", max_length=160)
    resource_type: str = ""
    resource_id: str = ""
    cursor: dict[str, Any] = Field(default_factory=dict)


class CollaborationSessionState(BaseModel):
    status: str


class NotificationPreferencesUpdate(BaseModel):
    muted: bool = False
    mention_only: bool = False
    browser_notifications: bool = False


class JobActionCreate(BaseModel):
    job_id: str
    action: str
    note: str = Field(default="", max_length=500)


class MemberPermissionsUpdate(BaseModel):
    target_user_id: str
    allowed_categories: list[str] = Field(default_factory=list)
    allowed_modules: list[str] = Field(default_factory=list)
    allowed_projects: list[str] = Field(default_factory=list)


class MemberEnabledUpdate(BaseModel):
    target_user_id: str
    enabled: bool


class CommentReplyCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class CommentEdit(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class CommentResolve(BaseModel):
    resolved: bool


class OfflineDraftCreate(BaseModel):
    resource_type: str
    resource_id: str
    base_revision: int = Field(default=0, ge=0)
    draft: dict[str, Any] = Field(default_factory=dict)


class OfflineDraftSync(BaseModel):
    current_revision: int = Field(ge=0)


class RecoverableDelete(BaseModel):
    item_type: str
    item_id: str


class AccountSessionRevokeAll(BaseModel):
    target_user_id: str | None = None
    keep_session_id: str = ""


def _identity(request: Request) -> tuple[str, str, str, str]:
    identity = request.state.api_identity
    tenant = request.state.tenant
    return str(identity.client_id), str(identity.display_name), str(identity.role), str(tenant.tenant_id)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionDenied):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, RecordLocked):
        return HTTPException(status_code=409, detail={"message": str(exc), "lock": exc.lock})
    if isinstance(exc, RevisionConflict):
        return HTTPException(status_code=409, detail={"message": str(exc), "current_revision": exc.current_revision})
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail="Live Workspace resource was not found.")
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="Live Workspace operation stopped safely.")


@router.get("/status")
def status(request: Request) -> dict[str, Any]:
    user_id, display_name, role, tenant_id = _identity(request)
    return {
        "available": True,
        "mode": "local-first",
        "tenant_id": tenant_id,
        "client_id": user_id,
        "display_name": display_name,
        "api_role": role,
        "capabilities": [
            "presence", "same-record-viewers", "record-locking", "comments", "mentions",
            "review-queue", "notifications", "audit-feed", "websocket", "secure-invites",
            "tasks", "evidence-library", "cross-module-links", "scientific-annotations",
            "collaborative-sessions", "offline-drafts", "backup-restore", "admin-health",
        ],
    }


@router.post("/workspaces")
def create_workspace(payload: WorkspaceCreate, request: Request) -> dict[str, Any]:
    user_id, display_name, api_role, tenant_id = _identity(request)
    if api_role not in {"admin", "operator", "local_operator"}:
        raise HTTPException(status_code=403, detail="Only an operator or admin can create a workspace.")
    try:
        workspace, join_code = STORE.create_workspace(
            tenant_id=tenant_id, owner_user_id=user_id, owner_display_name=display_name,
            name=payload.name, description=payload.description,
            default_join_role=payload.default_join_role, access_code=payload.access_code,
        )
        return {"workspace": workspace.to_dict(), "join_code": join_code, "join_code_visible_once": True}
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/workspaces")
def list_workspaces(request: Request) -> list[dict[str, Any]]:
    user_id, _display_name, _api_role, tenant_id = _identity(request)
    try:
        return STORE.list_workspaces(tenant_id=tenant_id, user_id=user_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/join")
def join_workspace(workspace_id: str, payload: WorkspaceJoin, request: Request) -> dict[str, Any]:
    user_id, _display_name, _api_role, tenant_id = _identity(request)
    try:
        workspace = STORE.get_workspace(workspace_id)
        if workspace.tenant_id != tenant_id:
            raise PermissionDenied("Workspace belongs to another tenant.")
        return STORE.join_workspace(
            workspace_id=workspace_id, access_code=payload.access_code, user_id=user_id,
            display_name=payload.display_name, requested_role=payload.requested_role,
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/workspaces/{workspace_id}/dashboard")
def dashboard(workspace_id: str, request: Request) -> dict[str, Any]:
    user_id, _display_name, _api_role, _tenant_id = _identity(request)
    try:
        return STORE.dashboard(workspace_id, actor_user_id=user_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/workspaces/{workspace_id}/members")
def members(workspace_id: str, request: Request) -> list[dict[str, Any]]:
    user_id, _display_name, _api_role, _tenant_id = _identity(request)
    try:
        return STORE.list_members(workspace_id, actor_user_id=user_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/members/role")
def update_member_role(workspace_id: str, payload: MemberRoleUpdate, request: Request) -> dict[str, Any]:
    user_id, _display_name, _api_role, _tenant_id = _identity(request)
    try:
        STORE.set_member_role(workspace_id, actor_user_id=user_id, target_user_id=payload.target_user_id, role=payload.role)
        return STORE.get_member(workspace_id, payload.target_user_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/presence/heartbeat")
def heartbeat(workspace_id: str, payload: PresenceHeartbeat, request: Request) -> dict[str, Any]:
    user_id, _display_name, _api_role, _tenant_id = _identity(request)
    try:
        return STORE.heartbeat(workspace_id=workspace_id, user_id=user_id, **payload.model_dump())
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/workspaces/{workspace_id}/presence")
def presence(
    workspace_id: str, request: Request, page_key: str = Query(default=""),
    record_type: str = Query(default=""), record_id: str = Query(default=""),
) -> list[dict[str, Any]]:
    user_id, _display_name, _api_role, _tenant_id = _identity(request)
    try:
        return STORE.list_presence(
            workspace_id, actor_user_id=user_id, page_key=page_key,
            record_type=record_type, record_id=record_id,
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/locks/acquire")
def acquire_lock(workspace_id: str, payload: LockRequest, request: Request) -> dict[str, Any]:
    user_id, _display_name, _api_role, _tenant_id = _identity(request)
    try:
        return STORE.acquire_lock(workspace_id=workspace_id, user_id=user_id, **payload.model_dump())
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/locks/renew")
def renew_lock(workspace_id: str, payload: LockRequest, request: Request) -> dict[str, Any]:
    user_id, _display_name, _api_role, _tenant_id = _identity(request)
    try:
        return STORE.renew_lock(
            workspace_id=workspace_id, user_id=user_id, session_id=payload.session_id,
            resource_type=payload.resource_type, resource_id=payload.resource_id,
            ttl_seconds=payload.ttl_seconds,
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/locks/release")
def release_lock(workspace_id: str, payload: ResourceRequest, request: Request) -> dict[str, Any]:
    user_id, _display_name, _api_role, _tenant_id = _identity(request)
    try:
        return {"released": STORE.release_lock(
            workspace_id=workspace_id, user_id=user_id, resource_type=payload.resource_type,
            resource_id=payload.resource_id, force=payload.force,
        )}
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/workspaces/{workspace_id}/locks/{resource_type}/{resource_id}")
def get_lock(workspace_id: str, resource_type: str, resource_id: str, request: Request) -> dict[str, Any]:
    user_id, _display_name, _api_role, _tenant_id = _identity(request)
    try:
        return {"lock": STORE.get_lock(workspace_id, resource_type, resource_id, actor_user_id=user_id)}
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/records/revisions")
def commit_record_revision(workspace_id: str, payload: RecordRevisionCreate, request: Request) -> dict[str, Any]:
    user_id, _display_name, _api_role, _tenant_id = _identity(request)
    try:
        return STORE.commit_record_revision(workspace_id=workspace_id, user_id=user_id, **payload.model_dump())
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/workspaces/{workspace_id}/records/revisions")
def record_revisions(
    workspace_id: str, resource_type: str, resource_id: str, request: Request,
) -> list[dict[str, Any]]:
    user_id, _display_name, _api_role, _tenant_id = _identity(request)
    try:
        return STORE.list_record_versions(
            workspace_id, actor_user_id=user_id, resource_type=resource_type, resource_id=resource_id
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/jobs")
def upsert_shared_job(workspace_id: str, payload: SharedJobUpsert, request: Request) -> dict[str, Any]:
    user_id, _display_name, _api_role, _tenant_id = _identity(request)
    try:
        return STORE.upsert_shared_job(workspace_id=workspace_id, user_id=user_id, **payload.model_dump())
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/workspaces/{workspace_id}/jobs")
def shared_jobs(workspace_id: str, request: Request, status: str = Query(default="")) -> list[dict[str, Any]]:
    user_id, _display_name, _api_role, _tenant_id = _identity(request)
    try:
        return STORE.list_shared_jobs(workspace_id, actor_user_id=user_id, status=status)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/access-code/rotate")
def rotate_access_code(workspace_id: str, payload: AccessCodeRotate, request: Request) -> dict[str, Any]:
    user_id, _display_name, _api_role, _tenant_id = _identity(request)
    try:
        code = STORE.rotate_access_code(workspace_id, actor_user_id=user_id, new_code=payload.new_code)
        return {"join_code": code, "join_code_visible_once": True}
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/comments")
def add_comment(workspace_id: str, payload: CommentCreate, request: Request) -> dict[str, Any]:
    user_id, _display_name, _api_role, _tenant_id = _identity(request)
    try:
        return STORE.add_comment(workspace_id=workspace_id, user_id=user_id, **payload.model_dump())
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/workspaces/{workspace_id}/comments")
def comments(workspace_id: str, resource_type: str, resource_id: str, request: Request) -> list[dict[str, Any]]:
    user_id, _display_name, _api_role, _tenant_id = _identity(request)
    try:
        return STORE.list_comments(
            workspace_id, actor_user_id=user_id, resource_type=resource_type, resource_id=resource_id,
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/reviews")
def request_review(workspace_id: str, payload: ReviewCreate, request: Request) -> dict[str, Any]:
    user_id, _display_name, _api_role, _tenant_id = _identity(request)
    try:
        return STORE.request_review(workspace_id=workspace_id, user_id=user_id, **payload.model_dump())
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/workspaces/{workspace_id}/reviews")
def reviews(workspace_id: str, request: Request, status: str = Query(default="")) -> list[dict[str, Any]]:
    user_id, _display_name, _api_role, _tenant_id = _identity(request)
    try:
        return STORE.list_reviews(workspace_id, actor_user_id=user_id, status=status)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/reviews/{review_id}/update")
def update_review(review_id: str, payload: ReviewUpdate, request: Request) -> dict[str, Any]:
    user_id, _display_name, _api_role, _tenant_id = _identity(request)
    try:
        return STORE.update_review(review_id=review_id, user_id=user_id, **payload.model_dump())
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/workspaces/{workspace_id}/activity")
def activity(workspace_id: str, request: Request, limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, Any]]:
    user_id, _display_name, _api_role, _tenant_id = _identity(request)
    try:
        return STORE.list_activity(workspace_id, actor_user_id=user_id, limit=limit)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/workspaces/{workspace_id}/notifications")
def notifications(workspace_id: str, request: Request, unread_only: bool = Query(default=False)) -> list[dict[str, Any]]:
    user_id, _display_name, _api_role, _tenant_id = _identity(request)
    try:
        return STORE.list_notifications(workspace_id, user_id=user_id, unread_only=unread_only)
    except Exception as exc:
        raise _http_error(exc) from exc



@router.get("/workspaces/{workspace_id}/settings")
def workspace_settings(workspace_id: str, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.workspace_settings(workspace_id, actor_user_id=user_id)  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/settings")
def update_workspace_settings(workspace_id: str, payload: WorkspaceSettingsUpdate, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.update_workspace_settings(workspace_id, actor_user_id=user_id, settings=payload.settings)  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/profile")
def update_member_profile(workspace_id: str, payload: MemberProfileUpdate, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.update_member_profile(workspace_id, user_id=user_id, **payload.model_dump())  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/invites")
def create_invite(workspace_id: str, payload: InviteCreate, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.create_invite(workspace_id, actor_user_id=user_id, **payload.model_dump())  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/workspaces/{workspace_id}/invites")
def list_invites(workspace_id: str, request: Request) -> list[dict[str, Any]]:
    user_id, *_ = _identity(request)
    try:
        return STORE.list_invites(workspace_id, actor_user_id=user_id)  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.delete("/invites/{invite_id}")
def revoke_invite(invite_id: str, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return {"revoked": STORE.revoke_invite(invite_id, actor_user_id=user_id)}  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/invites/redeem")
def redeem_invite(payload: InviteRedeem, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.redeem_invite(token=payload.token, user_id=user_id, display_name=payload.display_name)  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/tasks")
def create_task(workspace_id: str, payload: TaskCreate, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.create_task(workspace_id=workspace_id, user_id=user_id, **payload.model_dump())  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/workspaces/{workspace_id}/tasks")
def list_tasks(workspace_id: str, request: Request, status: str = Query(default=""), assigned_to: str = Query(default="")) -> list[dict[str, Any]]:
    user_id, *_ = _identity(request)
    try:
        return STORE.list_tasks(workspace_id, actor_user_id=user_id, status=status, assigned_to=assigned_to)  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.patch("/tasks/{task_id}")
def update_task(task_id: str, payload: TaskUpdate, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.update_task(task_id, user_id=user_id, **payload.model_dump())  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/bookmarks")
def add_bookmark(workspace_id: str, payload: BookmarkCreate, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.add_bookmark(workspace_id=workspace_id, user_id=user_id, **payload.model_dump())  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/workspaces/{workspace_id}/bookmarks")
def list_bookmarks(workspace_id: str, request: Request, kind: str = Query(default="")) -> list[dict[str, Any]]:
    user_id, *_ = _identity(request)
    try:
        return STORE.list_bookmarks(workspace_id, actor_user_id=user_id, kind=kind)  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/timeline")
def add_timeline_event(workspace_id: str, payload: TimelineCreate, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.add_timeline_event(workspace_id=workspace_id, user_id=user_id, **payload.model_dump())  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/workspaces/{workspace_id}/timeline")
def list_timeline(workspace_id: str, request: Request, project_id: str = Query(default=""), subject_alias: str = Query(default="")) -> list[dict[str, Any]]:
    user_id, *_ = _identity(request)
    try:
        return STORE.list_timeline(workspace_id, actor_user_id=user_id, project_id=project_id, subject_alias=subject_alias)  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/annotations")
def create_annotation(workspace_id: str, payload: AnnotationCreate, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.create_annotation(workspace_id=workspace_id, user_id=user_id, **payload.model_dump())  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/workspaces/{workspace_id}/annotations")
def list_annotations(workspace_id: str, request: Request, resource_type: str = Query(default=""), resource_id: str = Query(default=""), status: str = Query(default="")) -> list[dict[str, Any]]:
    user_id, *_ = _identity(request)
    try:
        return STORE.list_annotations(workspace_id, actor_user_id=user_id, resource_type=resource_type, resource_id=resource_id, status=status)  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.patch("/annotations/{annotation_id}")
def update_annotation(annotation_id: str, payload: AnnotationUpdate, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.update_annotation(annotation_id, user_id=user_id, **payload.model_dump())  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/collaboration-sessions")
def create_collaboration_session(workspace_id: str, payload: CollaborationSessionCreate, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.create_collaboration_session(workspace_id=workspace_id, user_id=user_id, **payload.model_dump())  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/workspaces/{workspace_id}/collaboration-sessions")
def list_collaboration_sessions(workspace_id: str, request: Request) -> list[dict[str, Any]]:
    user_id, *_ = _identity(request)
    try:
        return STORE.list_collaboration_sessions(workspace_id, actor_user_id=user_id)  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/collaboration-sessions/{collaboration_session_id}/join")
def join_collaboration_session(collaboration_session_id: str, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.join_collaboration_session(collaboration_session_id, user_id=user_id, follow_host=True)  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/collaboration-sessions/{collaboration_session_id}/navigation")
def update_collaboration_navigation(collaboration_session_id: str, payload: CollaborationNavigation, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.update_collaboration_navigation(collaboration_session_id, user_id=user_id, **payload.model_dump())  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/collaboration-sessions/{collaboration_session_id}/end")
def end_collaboration_session(collaboration_session_id: str, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.end_collaboration_session(collaboration_session_id, user_id=user_id)  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/collaboration-sessions/{collaboration_session_id}/state")
def update_collaboration_session_state(collaboration_session_id: str, payload: CollaborationSessionState, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.set_collaboration_session_status(collaboration_session_id, user_id=user_id, status=payload.status)  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/collaboration-sessions/{collaboration_session_id}/leave")
def leave_collaboration_session(collaboration_session_id: str, request: Request) -> dict[str, bool]:
    user_id, *_ = _identity(request)
    try:
        return {"left": STORE.leave_collaboration_session(collaboration_session_id, user_id=user_id)}  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/notification-preferences")
def update_notification_preferences(workspace_id: str, payload: NotificationPreferencesUpdate, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.update_notification_preferences(workspace_id, user_id=user_id, **payload.model_dump())  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/notifications/read-all")
def mark_all_notifications_read(workspace_id: str, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return {"marked_read": STORE.mark_all_notifications_read(workspace_id, user_id=user_id)}  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/job-actions")
def request_job_action(workspace_id: str, payload: JobActionCreate, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.request_job_action(workspace_id=workspace_id, user_id=user_id, **payload.model_dump())  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/workspaces/{workspace_id}/activity/since")
def activity_since(workspace_id: str, request: Request, after_event_id: int = Query(default=0, ge=0), limit: int = Query(default=200, ge=1, le=1000)) -> list[dict[str, Any]]:
    user_id, *_ = _identity(request)
    try:
        return STORE.list_activity_filtered(workspace_id, actor_user_id=user_id, after_event_id=after_event_id, limit=limit)  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/workspaces/{workspace_id}/admin-health")
def admin_health(workspace_id: str, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.admin_health(workspace_id, actor_user_id=user_id)  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/workspaces/{workspace_id}/backup")
def download_workspace_backup(workspace_id: str, request: Request) -> Response:
    user_id, *_ = _identity(request)
    try:
        data, manifest = STORE.export_workspace_backup(workspace_id, actor_user_id=user_id)  # type: ignore[attr-defined]
        return Response(content=data, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename={manifest['file_name']}", "X-BioIntel-Backup-SHA256": manifest["archive_sha256"]})
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/member-permissions")
def update_member_permissions(workspace_id: str, payload: MemberPermissionsUpdate, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.set_member_permissions(  # type: ignore[attr-defined]
            workspace_id,
            actor_user_id=user_id,
            target_user_id=payload.target_user_id,
            allowed_categories=payload.allowed_categories,
            allowed_modules=payload.allowed_modules,
            allowed_projects=payload.allowed_projects,
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/members/enabled")
def update_member_enabled(workspace_id: str, payload: MemberEnabledUpdate, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.set_member_enabled(  # type: ignore[attr-defined]
            workspace_id, actor_user_id=user_id, target_user_id=payload.target_user_id, enabled=payload.enabled
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/comments/{comment_id}/reply")
def reply_to_comment(comment_id: str, payload: CommentReplyCreate, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        parent = STORE.get_comment(comment_id, actor_user_id=user_id)
        return STORE.add_reply(  # type: ignore[attr-defined]
            workspace_id=parent["workspace_id"], user_id=user_id, parent_comment_id=comment_id, body=payload.body
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.patch("/comments/{comment_id}")
def edit_comment(comment_id: str, payload: CommentEdit, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.edit_comment(comment_id, user_id=user_id, body=payload.body)  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/comments/{comment_id}/resolved")
def resolve_comment(comment_id: str, payload: CommentResolve, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.set_comment_resolved(comment_id, user_id=user_id, resolved=payload.resolved)  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/offline-drafts")
def create_offline_draft(workspace_id: str, payload: OfflineDraftCreate, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.save_offline_draft(  # type: ignore[attr-defined]
            workspace_id=workspace_id,
            user_id=user_id,
            resource_type=payload.resource_type,
            resource_id=payload.resource_id,
            base_revision=payload.base_revision,
            draft=payload.draft,
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/workspaces/{workspace_id}/offline-drafts")
def list_offline_drafts(workspace_id: str, request: Request, status: str = "pending") -> list[dict[str, Any]]:
    user_id, *_ = _identity(request)
    try:
        return STORE.list_offline_drafts(workspace_id, user_id=user_id, status=status)  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/offline-drafts/{draft_id}/sync")
def sync_offline_draft(draft_id: str, payload: OfflineDraftSync, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.sync_offline_draft(draft_id, user_id=user_id, current_revision=payload.current_revision)  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/trash")
def move_item_to_trash(workspace_id: str, payload: RecoverableDelete, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.soft_delete_item(  # type: ignore[attr-defined]
            workspace_id=workspace_id, user_id=user_id, item_type=payload.item_type, item_id=payload.item_id
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/workspaces/{workspace_id}/trash")
def list_trash(workspace_id: str, request: Request) -> list[dict[str, Any]]:
    user_id, *_ = _identity(request)
    try:
        return STORE.list_deleted_items(workspace_id, actor_user_id=user_id)  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/trash/{deleted_item_id}/restore")
def restore_trash_item(deleted_item_id: str, request: Request) -> dict[str, Any]:
    user_id, *_ = _identity(request)
    try:
        return STORE.restore_deleted_item(deleted_item_id, actor_user_id=user_id)  # type: ignore[attr-defined]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/workspaces/{workspace_id}/account-sessions/revoke-all")
def revoke_account_sessions(workspace_id: str, payload: AccountSessionRevokeAll, request: Request) -> dict[str, int]:
    user_id, *_ = _identity(request)
    try:
        count = STORE.revoke_all_account_sessions(  # type: ignore[attr-defined]
            workspace_id,
            actor_user_id=user_id,
            target_user_id=payload.target_user_id,
            keep_session_id=payload.keep_session_id,
        )
        return {"revoked": count}
    except Exception as exc:
        raise _http_error(exc) from exc


class ConnectionHub:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, workspace_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections[workspace_id].add(websocket)

    async def disconnect(self, workspace_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections[workspace_id].discard(websocket)
            if not self._connections[workspace_id]:
                self._connections.pop(workspace_id, None)

    async def broadcast(self, workspace_id: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._connections.get(workspace_id, set()))
        stale: list[WebSocket] = []
        for websocket in targets:
            try:
                await websocket.send_json(payload)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            await self.disconnect(workspace_id, websocket)


HUB = ConnectionHub()


@router.websocket("/ws/{workspace_id}")
async def live_websocket(websocket: WebSocket, workspace_id: str) -> None:
    """Privacy-bounded real-time collaboration channel.

    The channel transports presence, safe aliases and coordination metadata only.
    Raw scientific uploads/results are never accepted through this endpoint.
    """
    await websocket.accept()
    session_id = ""
    user_id = ""
    try:
        auth = await asyncio.wait_for(websocket.receive_json(), timeout=15)
        if not isinstance(auth, dict) or auth.get("type") != "authenticate":
            await websocket.close(code=4401, reason="Authentication message required.")
            return
        if len(json.dumps(auth, default=str).encode("utf-8")) > 64 * 1024:
            await websocket.close(code=4400, reason="Authentication message is too large.")
            return
        access_code = str(auth.get("access_code", ""))
        invite_token = str(auth.get("invite_token", ""))
        user_id = str(auth.get("user_id", ""))
        display_name = str(auth.get("display_name", ""))
        session_id = str(auth.get("session_id", ""))
        authenticated = False
        if access_code and STORE.verify_access_code(workspace_id, access_code):
            authenticated = True
            try:
                STORE.get_member(workspace_id, user_id)
            except PermissionDenied:
                STORE.join_workspace(
                    workspace_id=workspace_id,
                    access_code=access_code,
                    user_id=user_id,
                    display_name=display_name,
                    requested_role=str(auth.get("requested_role", "viewer")),
                )
        elif invite_token and isinstance(STORE, LiveWorkspaceAdvancedStore):
            redeemed = STORE.redeem_invite(token=invite_token, user_id=user_id, display_name=display_name)
            authenticated = str(redeemed.get("workspace_id", "")) == workspace_id
        if not authenticated:
            await websocket.close(code=4403, reason="Invalid workspace access code or invite token.")
            return

        if isinstance(STORE, LiveWorkspaceAdvancedStore):
            STORE.register_account_session(
                workspace_id,
                user_id=user_id,
                account_session_id=session_id,
                client_label=str(auth.get("client_label", "WebSocket browser"))[:120],
                auth_source="websocket",
                ttl_hours=12,
            )
        STORE.heartbeat(
            workspace_id=workspace_id,
            session_id=session_id,
            user_id=user_id,
            display_name=display_name,
            page_key="live-workspace",
            page_title="BioIntel Live Workspace",
            category="Collaboration",
            activity_state="viewing",
            client_label="WebSocket",
        )
        await HUB.connect(workspace_id, websocket)
        await HUB.broadcast(workspace_id, {"type": "presence_changed", "workspace_id": workspace_id, "server_time_utc": utc_text()})
        recent = STORE.list_activity(workspace_id, actor_user_id=user_id, limit=1)
        cursor = int(recent[0]["event_id"]) if recent else 0
        await websocket.send_json(
            {
                "type": "authenticated",
                "workspace_id": workspace_id,
                "session_id": session_id,
                "server_time_utc": utc_text(),
                "event_cursor": cursor,
                "capabilities": ["presence", "resync", "dashboard", "notifications", "collaboration_sessions"],
            }
        )
        while True:
            message = await websocket.receive_json()
            if not isinstance(message, dict):
                continue
            if len(json.dumps(message, default=str).encode("utf-8")) > 64 * 1024:
                await websocket.send_json({"type": "error", "reason": "Message exceeds the 64 KB coordination limit."})
                continue
            event_type = str(message.get("type", ""))
            if event_type in {"ping", "context"}:
                STORE.heartbeat(
                    workspace_id=workspace_id,
                    session_id=session_id,
                    user_id=user_id,
                    display_name=display_name,
                    page_key=str(message.get("page_key", "")),
                    page_title=str(message.get("page_title", "")),
                    category=str(message.get("category", "")),
                    project_id=str(message.get("project_id", "")),
                    record_type=str(message.get("record_type", "")),
                    record_id=str(message.get("record_id", "")),
                    activity_state=str(message.get("activity_state", "viewing")),
                    status_message=str(message.get("status_message", "")),
                    client_label="WebSocket",
                )
                await HUB.broadcast(workspace_id, {"type": "presence_changed", "workspace_id": workspace_id, "server_time_utc": utc_text()})
                await websocket.send_json({"type": "pong", "server_time_utc": utc_text()})
            elif event_type == "request_snapshot":
                snapshot = STORE.list_presence(workspace_id, actor_user_id=user_id)
                await websocket.send_json({"type": "presence_snapshot", "items": snapshot, "server_time_utc": utc_text()})
            elif event_type in {"request_resync", "request_activity_since"}:
                after_event_id = max(int(message.get("after_event_id", 0)), 0)
                if isinstance(STORE, LiveWorkspaceAdvancedStore):
                    events = STORE.list_activity_filtered(workspace_id, actor_user_id=user_id, after_event_id=after_event_id, limit=500)
                else:
                    events = [item for item in reversed(STORE.list_activity(workspace_id, actor_user_id=user_id, limit=500)) if int(item.get("event_id", 0)) > after_event_id]
                next_cursor = max([after_event_id, *[int(item.get("event_id", 0)) for item in events]])
                await websocket.send_json({"type": "activity_resync", "events": events, "event_cursor": next_cursor, "server_time_utc": utc_text()})
            elif event_type == "request_dashboard":
                await websocket.send_json({"type": "dashboard_snapshot", "dashboard": STORE.dashboard(workspace_id, actor_user_id=user_id), "server_time_utc": utc_text()})
            elif event_type == "request_notifications":
                notifications = STORE.list_notifications(workspace_id, user_id=user_id, unread_only=bool(message.get("unread_only", False)), limit=200)
                await websocket.send_json({"type": "notification_snapshot", "items": notifications, "server_time_utc": utc_text()})
            elif event_type == "request_collaboration_sessions" and isinstance(STORE, LiveWorkspaceAdvancedStore):
                sessions = STORE.list_collaboration_sessions(workspace_id, actor_user_id=user_id)
                await websocket.send_json({"type": "collaboration_session_snapshot", "items": sessions, "server_time_utc": utc_text()})
            else:
                await websocket.send_json({"type": "ignored", "reason": "Unsupported event type."})
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except (PermissionDenied, ValueError, KeyError):
        try:
            await websocket.close(code=4403, reason="Live Workspace authorization or validation failed.")
        except Exception:
            pass
    except Exception:
        try:
            await websocket.close(code=1011, reason="Live Workspace connection stopped safely.")
        except Exception:
            pass
    finally:
        await HUB.disconnect(workspace_id, websocket)
        if session_id and user_id:
            try:
                STORE.disconnect(workspace_id, session_id, user_id=user_id)
            except Exception:
                pass
        await HUB.broadcast(workspace_id, {"type": "presence_changed", "workspace_id": workspace_id, "server_time_utc": utc_text()})


__all__ = ["router", "STORE", "HUB"]
