from __future__ import annotations

import os

import pytest
pytest.importorskip("playwright")
from playwright.sync_api import Page

pytestmark = pytest.mark.e2e


def _ui_url() -> str:
    return os.getenv("BIOINTEL_UI_URL", "http://127.0.0.1:8501")


@pytest.mark.skipif(os.getenv("BIOINTEL_RUN_E2E") != "1", reason="Set BIOINTEL_RUN_E2E=1")
def test_landmarks_skip_link_and_keyboard_focus(page: Page) -> None:
    page.goto(_ui_url())
    page.wait_for_selector("[data-testid='stAppViewContainer']")

    assert page.locator("main").count() == 1
    assert page.locator("nav").count() >= 1

    page.keyboard.press("Tab")
    focused = page.locator(":focus")
    assert focused.count() == 1
    assert focused.evaluate("el => el !== document.body")

    skip_link = page.locator("a.bio-skip-link")
    assert skip_link.count() == 1
    skip_link.focus()
    assert skip_link.is_visible()
    skip_link.press("Enter")
    assert page.evaluate("location.hash === '#bio-main-content'")

    focus_style = focused.evaluate(
        "el => { const s = getComputedStyle(el); return `${s.outlineStyle}|${s.outlineWidth}`; }"
    )
    assert "none|0px" not in focus_style


@pytest.mark.skipif(os.getenv("BIOINTEL_RUN_E2E") != "1", reason="Set BIOINTEL_RUN_E2E=1")
def test_interactive_controls_have_accessible_names(page: Page) -> None:
    page.goto(_ui_url())
    page.wait_for_selector("[data-testid='stAppViewContainer']")

    unnamed = page.locator("button, a[href], input, select, textarea").evaluate_all(
        """
        elements => elements.filter(el => {
          if (el.hidden || el.getAttribute('aria-hidden') === 'true') return false;
          const style = getComputedStyle(el);
          if (style.display === 'none' || style.visibility === 'hidden') return false;
          const labelledBy = el.getAttribute('aria-labelledby');
          const labelledText = labelledBy
            ? labelledBy.split(/\\s+/).map(id => document.getElementById(id)?.textContent || '').join(' ')
            : '';
          const name = [
            el.getAttribute('aria-label') || '',
            labelledText,
            el.getAttribute('title') || '',
            el.getAttribute('alt') || '',
            el.value || '',
            el.textContent || ''
          ].join(' ').trim();
          return name.length === 0;
        }).length
        """
    )
    assert unnamed == 0, f"Found {unnamed} interactive elements without an accessible name."


@pytest.mark.skipif(os.getenv("BIOINTEL_RUN_E2E") != "1", reason="Set BIOINTEL_RUN_E2E=1")
def test_reduced_motion_and_live_status_contract(page: Page) -> None:
    page.emulate_media(reduced_motion="reduce")
    page.goto(_ui_url())
    page.wait_for_selector("[data-testid='stAppViewContainer']")

    reduced_motion = page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches")
    assert reduced_motion is True
    assert page.locator("[aria-live], [role='status'], [role='progressbar']").count() >= 1
