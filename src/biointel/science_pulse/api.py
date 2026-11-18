from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from .models import utc_now
from .scheduler import SciencePulseScheduler
from .service import CONTEXTUAL_ACTIONS, INTEGRATION_DESTINATIONS, SciencePulseService


router = APIRouter(prefix="/api/v1/science-pulse", tags=["Science Pulse"])
ROOT = Path(__file__).resolve().parents[3]
_SERVICE: SciencePulseService | None = None


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PreferenceRequest(StrictModel):
    frequency: Literal[
        "instant",
        "hourly",
        "three_hour",
        "morning",
        "evening",
        "daily",
        "weekly",
        "in_app_only",
        "paused",
    ] = "in_app_only"
    timezone: str = "UTC"
    quiet_start: str = ""
    quiet_end: str = ""
    primary_category: str = ""
    max_notifications_per_sync: int = Field(default=50, ge=1, le=100)
    education_institution_id: str = ""


class AlertRequest(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    query: str = Field(default="", max_length=1000)
    categories: list[str] = Field(default_factory=list, max_length=100)
    content_types: list[str] = Field(default_factory=list, max_length=20)
    channels: list[
        Literal[
            "in_app",
            "education_home",
            "connect",
            "desktop",
            "email",
            "institution",
            "shiro_briefing",
        ]
    ] = Field(default_factory=lambda: ["in_app"])
    frequency: str = "immediate"


class BookmarkRequest(StrictModel):
    reading_list: str = Field(default="Saved", max_length=100)


class IntegrationRequest(StrictModel):
    destination: str
    action: str = Field(min_length=1, max_length=200)


class ShiroRequest(StrictModel):
    item_ids: list[str] = Field(min_length=1, max_length=10)
    level: Literal["school", "college", "researcher"] = "researcher"


class FeedRequest(StrictModel):
    name: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=8, max_length=4000)
    schedule_seconds: int = Field(default=10_800, ge=3600, le=604_800)
    approved: bool = False


class ContextActionRequest(StrictModel):
    action_key: str = Field(min_length=1, max_length=100)


def service() -> SciencePulseService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = SciencePulseService(ROOT)
    return _SERVICE


def _identity(request: Request) -> tuple[str, str, str]:
    identity = getattr(request.state, "api_identity", None)
    user_id = str(getattr(identity, "client_id", "") or "local-user")
    role = str(getattr(identity, "role", "") or "local_operator")
    tenant_context = getattr(request.state, "tenant", None)
    tenant_id = str(getattr(tenant_context, "tenant_id", "") or "local")
    return user_id, role, tenant_id


def _admin(request: Request) -> tuple[str, str]:
    user_id, role, tenant_id = _identity(request)
    if role not in {"admin", "local_operator", "owner"}:
        raise HTTPException(status_code=403, detail="Administrator permission is required.")
    return user_id, tenant_id


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    _, _, tenant_id = _identity(request)
    return service().health(tenant_id)


@router.get("/sources")
def sources(request: Request) -> list[dict[str, Any]]:
    _, _, tenant_id = _identity(request)
    return service().source_status(tenant_id)


@router.get("/items")
def items(
    request: Request,
    query: str = Query(default="", max_length=500),
    content_type: str = Query(default="", max_length=100),
    category: str = Query(default="", max_length=200),
    trust_state: str = Query(default="", max_length=100),
    bookmarked: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> list[dict[str, Any]]:
    user_id, _, tenant_id = _identity(request)
    return service().store.search_items(
        query,
        tenant_id=tenant_id,
        content_type=content_type,
        category=category,
        trust_state=trust_state,
        saved_by=user_id if bookmarked else "",
        limit=limit,
        offset=offset,
    )


@router.get("/news")
def news(
    request: Request,
    query: str = Query(default="", max_length=500),
    category: str = Query(default="", max_length=200),
    source: str = Query(default="", max_length=300),
    region: str = Query(default="", max_length=100),
    language: str = Query(default="", max_length=30),
    date_start: str = Query(default="", max_length=30),
    date_end: str = Query(default="", max_length=30),
    minimum_quality: float = Query(default=0.0, ge=0.0, le=1.0),
    live_only: bool = False,
    research_backed: bool = False,
    unread_only: bool = False,
    saved_only: bool = False,
    breaking_only: bool = False,
    minimum_source_count: int = Query(default=0, ge=0, le=100),
    sort: str = Query(default="latest", max_length=30),
    limit: int = Query(default=12, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> dict[str, Any]:
    user_id, _, tenant_id = _identity(request)
    return service().news_feed(
        tenant_id=tenant_id, user_id=user_id, query=query, category=category,
        source=source, region=region, language=language, date_start=date_start,
        date_end=date_end, minimum_quality=minimum_quality, live_only=live_only,
        research_backed=research_backed, unread_only=unread_only,
        saved_only=saved_only, breaking_only=breaking_only,
        minimum_source_count=minimum_source_count, sort=sort, limit=limit, offset=offset,
    )


@router.get("/news/{item_id}")
def news_detail(item_id: str, request: Request) -> dict[str, Any]:
    user_id, _, tenant_id = _identity(request)
    try:
        return service().news_detail(item_id, user_id=user_id, tenant_id=tenant_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/news/{item_id}/read")
def mark_news_read(item_id: str, request: Request) -> dict[str, Any]:
    user_id, _, tenant_id = _identity(request)
    try:
        value = service().news_detail(item_id, user_id=user_id, tenant_id=tenant_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"item_id": item_id, "read_at": value["read_at"]}


@router.post("/news/{item_id}/action", status_code=201)
def news_action(item_id: str, payload: ContextActionRequest, request: Request) -> dict[str, Any]:
    if payload.action_key not in CONTEXTUAL_ACTIONS:
        raise HTTPException(status_code=422, detail="Unsupported Science Pulse contextual action.")
    user_id, _, tenant_id = _identity(request)
    try:
        return service().perform_contextual_action(
            item_id, user_id=user_id, action_key=payload.action_key, tenant_id=tenant_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@router.get("/items/{item_id}")
def item(item_id: str, request: Request) -> dict[str, Any]:
    _, _, tenant_id = _identity(request)
    value = service().store.get_item(item_id, tenant_id)
    if not value:
        raise HTTPException(status_code=404, detail="Science Pulse item not found.")
    return value


@router.post("/items/{item_id}/bookmark")
def bookmark(item_id: str, payload: BookmarkRequest, request: Request) -> dict[str, Any]:
    user_id, _, tenant_id = _identity(request)
    if not service().store.get_item(item_id, tenant_id):
        raise HTTPException(status_code=404, detail="Science Pulse item not found.")
    saved = service().store.toggle_bookmark(
        user_id, item_id, tenant_id=tenant_id, reading_list=payload.reading_list
    )
    service().store.audit(
        user_id,
        "bookmark_added" if saved else "bookmark_removed",
        "science_pulse_item",
        item_id,
        tenant_id=tenant_id,
    )
    return {"item_id": item_id, "saved": saved}


@router.put("/preferences")
def preferences(payload: PreferenceRequest, request: Request) -> dict[str, Any]:
    user_id, _, tenant_id = _identity(request)
    value = payload.model_dump()
    service().store.save_preferences(user_id, value, tenant_id)
    return {"saved": True, "preferences": value}


@router.post("/alerts", status_code=201)
def create_alert(payload: AlertRequest, request: Request) -> dict[str, Any]:
    user_id, _, tenant_id = _identity(request)
    rule_id = service().store.create_alert(
        user_id,
        name=payload.name,
        query=payload.query,
        categories=payload.categories,
        content_types=payload.content_types,
        channels=payload.channels,
        frequency=payload.frequency,
        tenant_id=tenant_id,
    )
    return {"rule_id": rule_id, "state": "active"}


@router.get("/notifications")
def notifications(request: Request, limit: int = Query(default=100, ge=1, le=500)):
    user_id, _, tenant_id = _identity(request)
    return service().store.notifications(user_id, tenant_id, limit)


@router.get("/digests")
def digests(request: Request, limit: int = Query(default=50, ge=1, le=200)):
    user_id, _, tenant_id = _identity(request)
    with service().store.connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM sp_digests WHERE tenant_id=? AND user_id=?
            ORDER BY created_at DESC LIMIT ?
            """,
            (tenant_id, user_id, limit),
        ).fetchall()
    return [service().store._row(row) for row in rows]


@router.post("/digests/{frequency}")
def generate_digest(frequency: str, request: Request) -> dict[str, Any]:
    if frequency not in {"hourly", "three_hour", "daily", "weekly"}:
        raise HTTPException(status_code=422, detail="Unsupported digest frequency.")
    user_id, _, tenant_id = _identity(request)
    return service().generate_digest(user_id, frequency=frequency, tenant_id=tenant_id)


@router.post("/items/{item_id}/integration", status_code=201)
def integration(
    item_id: str, payload: IntegrationRequest, request: Request
) -> dict[str, Any]:
    if payload.destination not in INTEGRATION_DESTINATIONS:
        raise HTTPException(status_code=422, detail="Unsupported integration destination.")
    user_id, _, tenant_id = _identity(request)
    try:
        return service().integration_draft(
            item_id,
            user_id=user_id,
            destination=payload.destination,
            action=payload.action,
            tenant_id=tenant_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/shiro/context")
def shiro_context(payload: ShiroRequest, request: Request) -> dict[str, Any]:
    _, _, tenant_id = _identity(request)
    return service().shiro_context(payload.item_ids, level=payload.level, tenant_id=tenant_id)


@router.get("/trends")
def trends(request: Request, limit: int = Query(default=20, ge=1, le=100)):
    _, _, tenant_id = _identity(request)
    return service().trends(tenant_id, limit)


@router.post("/admin/sources", status_code=201)
def register_source(payload: FeedRequest, request: Request) -> dict[str, Any]:
    user_id, tenant_id = _admin(request)
    try:
        source_key = service().register_feed(
            payload.name,
            payload.url,
            schedule_seconds=payload.schedule_seconds,
            approved=payload.approved,
            tenant_id=tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    service().store.audit(user_id, "feed_registered", "science_pulse_source", source_key,
                          {"approved": payload.approved}, tenant_id)
    return {"source_key": source_key, "approved": payload.approved}


@router.post("/admin/sources/{source_key}/connection-test")
def connection_test(source_key: str, request: Request) -> dict[str, Any]:
    _, tenant_id = _admin(request)
    try:
        return service().test_connection(source_key, tenant_id=tenant_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/admin/sources/{source_key}/enabled")
def set_source_enabled(source_key: str, enabled: bool, request: Request) -> dict[str, Any]:
    user_id, tenant_id = _admin(request)
    with service().store.connect() as connection:
        changed = connection.execute(
            """
            UPDATE sp_sources SET enabled=?,updated_at=?
            WHERE tenant_id=? AND source_key=?
            """,
            (int(enabled), utc_now(), tenant_id, source_key),
        ).rowcount
    if not changed:
        raise HTTPException(status_code=404, detail="Science Pulse source not found.")
    service().store.audit(
        user_id,
        "source_enabled" if enabled else "source_disabled",
        "science_pulse_source",
        source_key,
        {"enabled": enabled},
        tenant_id,
    )
    return {"source_key": source_key, "enabled": enabled}


@router.post("/admin/sources/{source_key}/sync")
def force_sync(source_key: str, request: Request) -> dict[str, Any]:
    _, tenant_id = _admin(request)
    return SciencePulseScheduler(ROOT, service=service()).force_sync(
        source_key, tenant_id=tenant_id
    )


@router.post("/admin/repair")
def repair(request: Request) -> dict[str, Any]:
    _, tenant_id = _admin(request)
    return SciencePulseScheduler(ROOT, service=service()).repair(tenant_id)


__all__ = ["router"]
