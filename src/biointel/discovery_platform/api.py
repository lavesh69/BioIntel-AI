from __future__ import annotations

from fastapi import APIRouter

from .api_analytics import router as analytics_router
from .api_core import router as core_router
from .api_research import router as research_router

router = APIRouter(
    prefix="/v1/research-platform",
    tags=["Research Platform"],
)
router.include_router(core_router)
router.include_router(research_router)
router.include_router(analytics_router)

