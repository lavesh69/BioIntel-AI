from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .manager import EngineManager

router = APIRouter(prefix="/engine-platform", tags=["Engine Platform"])


class PlanRequest(BaseModel):
    engine: str = Field(min_length=1, max_length=80)
    offline_pack: str = Field(default="", max_length=4096)


class PackInstallRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    engines: list[str] = Field(default_factory=list, max_length=100)
    accept_restricted_licences: bool = False


def manager() -> EngineManager:
    return EngineManager()


@router.get("/health")
def engine_health() -> dict[str, Any]:
    return manager().health_report()


@router.get("/catalog")
def engine_catalog() -> dict[str, Any]:
    frame = manager().catalog()
    return {"rows": frame.where(frame.notna(), None).to_dict(orient="records"), "count": len(frame)}


@router.get("/adapters")
def adapters() -> dict[str, Any]:
    frame = manager().adapter_status()
    return {"rows": frame.where(frame.notna(), None).to_dict(orient="records"), "count": len(frame)}


@router.post("/plan")
def plan(request: PlanRequest) -> dict[str, Any]:
    try:
        return manager().plan(request.engine, offline_pack=request.offline_pack or None).to_dict()
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/probe/{engine}")
def probe(engine: str) -> dict[str, Any]:
    try:
        return manager().probe(engine)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown engine") from exc


@router.post("/install-pack")
def install_pack(request: PackInstallRequest) -> dict[str, Any]:
    path = Path(request.path).expanduser()
    try:
        return manager().install_pack(path, engines=request.engines or None, accept_restricted_licences=request.accept_restricted_licences)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
