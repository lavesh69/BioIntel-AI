from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..paths import education_paths
from .api_context import require_tenant
from .base import Conflict, IntegrityFailure, Missing, PermissionDenied, ResearchPlatformError
from .sync import SYNC_OPERATIONS, SYNC_SCOPES, SyncEngine

router = APIRouter(prefix="/phase32", tags=["Education Phase 32 Secure Sync"])
_ENGINE: SyncEngine | None = None


def engine() -> SyncEngine:
    global _ENGINE
    if _ENGINE is None:
        database, media = education_paths()
        _ENGINE = SyncEngine(database, media)
    return _ENGINE


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
        raise HTTPException(400, detail={"code": "integrity_failure", "message": str(exc)}) from exc
    except ResearchPlatformError as exc:
        raise HTTPException(422, detail={"code": "validation_error", "message": str(exc)}) from exc


class DeviceRegistration(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=160)
    owner_id: str = Field(min_length=1, max_length=160)
    device_name: str = Field(min_length=1, max_length=160)
    device_type: str = Field(min_length=1, max_length=80)
    operating_system: str = Field(min_length=1, max_length=160)
    permissions: list[str]
    public_key: str = ""
    approved_by: str = ""


class DeviceDecision(BaseModel):
    administrator_id: str = Field(min_length=1, max_length=160)
    lost: bool = False


class PolicyRequest(BaseModel):
    administrator_id: str = Field(min_length=1, max_length=160)
    allowed_categories: list[str]
    excluded_categories: list[str] = Field(default_factory=list)
    data_residency: str = "local"
    retention_days: int = Field(default=365, ge=1, le=3650)
    allowed_device_types: list[str] = Field(default_factory=list)
    bandwidth_limit_kib: int = Field(default=0, ge=0)
    quota_bytes: int = Field(default=10 * 1024**3, ge=0)
    metered_allowed: bool = False
    low_bandwidth_default: bool = False
    paused: bool = False


class JournalRequest(BaseModel):
    tenant_id: str
    device_id: str
    actor_id: str
    entity_type: str
    entity_id: str
    operation: Literal[
        "CREATE",
        "UPDATE",
        "DELETE",
        "RESTORE",
        "ARCHIVE",
        "ATTACH_FILE",
        "REMOVE_FILE",
    ]
    payload: dict[str, Any] | list[Any] | None = None
    idempotency_key: str = Field(min_length=1, max_length=200)
    entity_version: int | None = Field(default=None, ge=1)


class ConflictResolutionRequest(BaseModel):
    tenant_id: str
    resolver_id: str
    decision: Literal["keep_local", "accept_remote", "merge"]
    merged_payload: dict[str, Any] | None = None


@router.get("/capabilities")
def capabilities():
    return {
        "optional": True,
        "local_first": True,
        "scopes": sorted(SYNC_SCOPES),
        "operations": sorted(SYNC_OPERATIONS),
        "transport": "HTTPS with standard certificate validation",
        "remote_provider": "adapter-based and not configured by default",
    }


@router.post("/devices", status_code=201)
def register_device(payload: DeviceRegistration, request: Request):
    require_tenant(request, payload.tenant_id)
    return run(lambda: engine().register_device(**payload.model_dump()))


@router.post("/devices/{device_id}/approve")
def approve_device(device_id: str, payload: DeviceDecision, request: Request):
    require_tenant(request, engine().device(device_id)["tenant_id"])
    return run(lambda: engine().approve_device(device_id, payload.administrator_id))


@router.post("/devices/{device_id}/revoke")
def revoke_device(device_id: str, payload: DeviceDecision, request: Request):
    require_tenant(request, engine().device(device_id)["tenant_id"])
    return run(
        lambda: engine().revoke_device(
            device_id,
            payload.administrator_id,
            lost=payload.lost,
        )
    )


@router.put("/tenants/{tenant_id}/policy")
def update_policy(tenant_id: str, payload: PolicyRequest, request: Request):
    require_tenant(request, tenant_id)
    values = payload.model_dump()
    administrator_id = values.pop("administrator_id")
    return run(lambda: engine().set_policy(tenant_id, administrator_id, **values))


@router.post("/journal", status_code=201)
def append_journal(payload: JournalRequest, request: Request):
    require_tenant(request, payload.tenant_id)
    return run(lambda: engine().append_change(**payload.model_dump()))


@router.get("/tenants/{tenant_id}/conflicts")
def conflicts(tenant_id: str, request: Request, state: str = "open"):
    require_tenant(request, tenant_id)
    return run(lambda: engine().conflicts(tenant_id, state=state))


@router.post("/conflicts/{conflict_id}/resolve")
def resolve_conflict(
    conflict_id: str,
    payload: ConflictResolutionRequest,
    request: Request,
):
    require_tenant(request, payload.tenant_id)
    return run(
        lambda: engine().resolve_conflict(
            payload.tenant_id,
            conflict_id,
            payload.resolver_id,
            decision=payload.decision,
            merged_payload=payload.merged_payload,
        )
    )


@router.get("/tenants/{tenant_id}/status")
def sync_status(tenant_id: str, request: Request):
    require_tenant(request, tenant_id)
    return run(lambda: engine().status(tenant_id))


@router.get("/tenants/{tenant_id}/diagnostics")
def sync_diagnostics(tenant_id: str, request: Request):
    require_tenant(request, tenant_id)
    return run(lambda: engine().diagnostic_bundle(tenant_id))
