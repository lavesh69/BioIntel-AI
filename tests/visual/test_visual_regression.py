from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pytest
pytest.importorskip("playwright")
from PIL import Image, ImageChops
from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
BASELINES = ROOT / "visual" / "browser_baselines"
ARTIFACTS = ROOT / "visual" / "artifacts" / "browser"
PORT = int(os.getenv("BIOINTEL_VISUAL_PORT", "8765"))
BASE_URL = f"http://127.0.0.1:{PORT}"
UPDATE = os.getenv("BIOINTEL_UPDATE_VISUAL_BASELINES", "0") == "1"
RUN = os.getenv("BIOINTEL_RUN_VISUAL_TESTS", "0") == "1" or UPDATE
REQUIRE_BASELINES = os.getenv("BIOINTEL_REQUIRE_BROWSER_BASELINES", "0") == "1"
MANIFEST_PATH = BASELINES / "manifest.json"

SCENARIOS = (
    ("home-desktop", "/", {"width": 1440, "height": 1000}),
    ("quality-desktop", "/Platform_Quality_Center", {"width": 1440, "height": 1000}),
    ("studio-desktop", "/BioIntel_Studio", {"width": 1440, "height": 1000}),
    ("compliance-desktop", "/Compliance_Research_Readiness", {"width": 1440, "height": 1000}),
    ("model-training-desktop", "/Model_Training", {"width": 1440, "height": 1000}),
    ("dti-predictor-desktop", "/DTI_Predictor", {"width": 1440, "height": 1000}),
    ("data-quality-desktop", "/Data_Quality_Activity", {"width": 1440, "height": 1000}),
    ("home-mobile", "/", {"width": 390, "height": 844}),
)


def _wait_ready(timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    url = f"{BASE_URL}/_stcore/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("Streamlit did not become ready for visual regression testing.")


@contextmanager
def streamlit_server():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "app.py",
            "--server.headless=true",
            "--server.address=127.0.0.1",
            f"--server.port={PORT}",
            "--browser.gatherUsageStats=false",
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_ready()
        yield
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def _assert_page_healthy(page: Page, *, route: str) -> None:
    page.wait_for_selector("[data-testid='stAppViewContainer']", state="visible", timeout=30_000)
    exception_count = page.locator("[data-testid='stException']").count()
    body_text = page.locator("body").inner_text(timeout=10_000).lower()
    fatal_tokens = ("traceback:", "has encountered an error", "nameerror:", "importerror:")
    detected = [token for token in fatal_tokens if token in body_text]
    assert exception_count == 0, f"Streamlit exception rendered on {route}."
    assert not detected, f"Fatal error text rendered on {route}: {', '.join(detected)}"
    assert page.locator(".bio-hero").count() >= 1, f"Expected BioIntel hero was not rendered on {route}."


def _stabilize(page: Page, *, route: str) -> None:
    page.add_style_tag(
        content="""
        *, *::before, *::after { animation-duration: 0s !important; transition-duration: 0s !important; caret-color: transparent !important; }
        [data-testid='stStatusWidget'], [data-testid='stToolbar'] { visibility: hidden !important; }
        """
    )
    _assert_page_healthy(page, route=route)
    page.wait_for_timeout(2500)
    _assert_page_healthy(page, route=route)


def _assert_snapshot(actual: Path, baseline: Path, *, max_changed_fraction: float = 0.012, pixel_tolerance: int = 24) -> None:
    if UPDATE:
        baseline.parent.mkdir(parents=True, exist_ok=True)
        baseline.write_bytes(actual.read_bytes())
        return
    if not baseline.exists():
        if REQUIRE_BASELINES:
            pytest.fail(f"Approved browser baseline is missing: {baseline}")
        return
    assert MANIFEST_PATH.is_file(), "Browser baseline manifest is missing."
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    approved = manifest.get("scenarios", {}).get(baseline.stem)
    assert approved, f"Browser baseline is not listed in the approval manifest: {baseline.name}"
    observed_sha = hashlib.sha256(baseline.read_bytes()).hexdigest()
    assert observed_sha == approved.get("png_sha256"), f"Browser baseline hash mismatch: {baseline.name}"
    expected_image = Image.open(baseline).convert("RGB")
    actual_image = Image.open(actual).convert("RGB")
    assert actual_image.size == expected_image.size, f"Viewport changed: {actual_image.size} != {expected_image.size}"
    expected = np.asarray(expected_image, dtype=np.int16)
    observed = np.asarray(actual_image, dtype=np.int16)
    changed = np.max(np.abs(expected - observed), axis=2) > pixel_tolerance
    changed_fraction = float(changed.mean())
    if changed_fraction > max_changed_fraction:
        diff_path = actual.with_name(actual.stem + "-diff.png")
        ImageChops.difference(expected_image, actual_image).save(diff_path)
        pytest.fail(
            f"Visual regression detected: {changed_fraction:.3%} pixels changed; "
            f"allowed {max_changed_fraction:.3%}. Diff: {diff_path}"
        )


@pytest.mark.visual
@pytest.mark.skipif(not RUN, reason="Set BIOINTEL_RUN_VISUAL_TESTS=1 to execute browser snapshots.")
def test_visual_regression_matrix() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with streamlit_server(), sync_playwright() as playwright:
        browser_path = os.getenv("BIOINTEL_CHROMIUM_PATH") or ("/usr/bin/chromium" if Path("/usr/bin/chromium").exists() else playwright.chromium.executable_path)
        browser = playwright.chromium.launch(headless=True, executable_path=browser_path, args=["--disable-dev-shm-usage"])
        try:
            for name, path, viewport in SCENARIOS:
                context = browser.new_context(viewport=viewport, device_scale_factor=1, locale="en-US", color_scheme="dark")
                page = context.new_page()
                page.goto(BASE_URL + path, wait_until="domcontentloaded", timeout=60_000)
                _stabilize(page, route=path)
                actual = ARTIFACTS / f"{name}.png"
                page.screenshot(path=actual, full_page=False)
                _assert_snapshot(actual, BASELINES / f"{name}.png")
                context.close()
        finally:
            browser.close()
