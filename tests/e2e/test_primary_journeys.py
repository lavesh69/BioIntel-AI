"""Playwright primary journeys: desktop, mobile and cross-browser health."""

from __future__ import annotations

import os

import pytest
pytest.importorskip("playwright")
from playwright.sync_api import Page

pytestmark = pytest.mark.e2e


@pytest.mark.skipif(os.getenv("BIOINTEL_RUN_E2E") != "1", reason="Set BIOINTEL_RUN_E2E=1")
def test_primary_journeys(page: Page) -> None:
    base = os.getenv("BIOINTEL_UI_URL", "http://127.0.0.1:8501")
    for route in (
        "/",
        "/BioIntel_Studio",
        "/Platform_Quality_Center",
        "/Compliance_Research_Readiness",
    ):
        page.goto(base + route, wait_until="domcontentloaded")
        page.wait_for_selector("[data-testid='stAppViewContainer']")
        assert page.locator("[data-testid='stException']").count() == 0


@pytest.mark.skipif(os.getenv("BIOINTEL_RUN_E2E") != "1", reason="Set BIOINTEL_RUN_E2E=1")
def test_mobile_primary_journey(page: Page) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(os.getenv("BIOINTEL_UI_URL", "http://127.0.0.1:8501"))
    page.wait_for_selector("[data-testid='stAppViewContainer']")
    assert page.locator(".bio-hero").count() >= 1
