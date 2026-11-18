from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = int(os.environ.get("BIOINTEL_UI_TEST_PORT", "8765"))


def wait_for_server(url: str, timeout: float = 45.0) -> None:
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return
        except Exception:
            time.sleep(0.75)
    raise RuntimeError(f"Streamlit did not become ready at {url}")


def main() -> int:
    missing = [name for name in ("streamlit", "playwright") if importlib.util.find_spec(name) is None]
    if missing:
        print("SKIP: browser runtime dependencies are unavailable: " + ", ".join(missing))
        return 2
    from playwright.sync_api import sync_playwright

    command = [
        sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
        "--server.headless=true", f"--server.port={PORT}", "--browser.gatherUsageStats=false",
    ]
    process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    url = f"http://127.0.0.1:{PORT}"
    try:
        wait_for_server(url)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            for width, height, scale in ((1366, 768, 1.0), (1600, 900, 1.25), (1920, 1080, 1.5)):
                context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=scale)
                page = context.new_page()
                page.goto(url, wait_until="networkidle")
                page.wait_for_timeout(1200)
                overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 2")
                if overflow:
                    raise AssertionError(f"Horizontal overflow at {width}x{height} scale={scale}")
                icons = page.locator(".bio-svg-icon")
                for index in range(min(icons.count(), 80)):
                    box = icons.nth(index).bounding_box()
                    if box and (box["width"] > 64 or box["height"] > 64):
                        raise AssertionError(f"Oversized branded icon at {width}x{height}: {box}")
                page.screenshot(path=str(ROOT / "reports" / f"peak_phase2_{width}x{height}_{scale}.png"), full_page=True)
                context.close()
            browser.close()
        print("PASS: Peak Phase 2 browser regression")
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
