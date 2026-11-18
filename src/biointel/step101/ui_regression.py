from __future__ import annotations

import csv
import html
import io
import json
import py_compile
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class PageResult:
    page: str
    mode: str
    status: str
    duration_ms: float
    exceptions: int
    warnings: list[str]
    detail: str = ""


def discover_pages(root: str | Path) -> list[Path]:
    base = Path(root).resolve()
    return [base / "app.py", *sorted((base / "pages").glob("*.py"))]


def static_page_check(page: Path) -> PageResult:
    started = time.perf_counter()
    warnings: list[str] = []
    status = "passed"
    detail = ""
    try:
        py_compile.compile(str(page), doraise=True)
        text = page.read_text(encoding="utf-8", errors="replace")
        if "st.set_page_config" not in text and page.name != "app.py":
            warnings.append("missing st.set_page_config")
        upload_safety_tokens = (
            "UploadReadError",
            "read_uploaded",
            "render_upload_preflight",
            "render_upload_collection_preflight",
            "profile_streamlit_upload",
        )
        if "st.file_uploader" in text and not any(token in text for token in upload_safety_tokens):
            warnings.append("uploader may not use universal validation")
        if text.count("st.json(") > 3:
            warnings.append("high raw JSON presentation count")
        if len(text.splitlines()) > 1500:
            warnings.append("large page module")
    except Exception as exc:
        status = "failed"
        detail = f"{type(exc).__name__}: {exc}"
    return PageResult(page.name, "static", status, (time.perf_counter() - started) * 1000, int(status == "failed"), warnings, detail)


def apptest_page_check(page: Path, *, timeout_seconds: int = 30) -> PageResult:
    started = time.perf_counter()
    warnings: list[str] = []
    status = "passed"
    detail = ""
    exceptions = 0
    try:
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(str(page), default_timeout=max(5, int(timeout_seconds)))
        app.run(timeout=max(5, int(timeout_seconds)))
        exceptions = len(app.exception)
        if exceptions:
            status = "failed"
            detail = " | ".join(str(item.value) for item in app.exception[:5])
        if len(app.warning):
            warnings.extend(str(item.value) for item in app.warning[:10])
    except Exception as exc:
        status = "failed"
        exceptions = 1
        detail = f"{type(exc).__name__}: {exc}"
    return PageResult(page.name, "apptest", status, (time.perf_counter() - started) * 1000, exceptions, warnings, detail)


def run_ui_regression(
    root: str | Path,
    *,
    mode: str = "static",
    selected_pages: Iterable[str] | None = None,
    timeout_seconds: int = 30,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    base = Path(root).resolve()
    selected = set(selected_pages or [])
    pages = [page for page in discover_pages(base) if not selected or page.name in selected]
    results = []
    for page in pages:
        results.append(static_page_check(page))
        if mode in {"apptest", "full"} and results[-1].status == "passed":
            results.append(apptest_page_check(page, timeout_seconds=timeout_seconds))
    payload = {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "platform": __import__("platform").platform(),
        "python": __import__("sys").version,
        "mode": mode,
        "page_count": len(pages),
        "checks": len(results),
        "passed": sum(item.status == "passed" for item in results),
        "failed": sum(item.status == "failed" for item in results),
        "warnings": sum(len(item.warnings) for item in results),
        "results": [asdict(item) for item in results],
    }
    target = Path(output_dir or base / "reports" / "ui_regression").resolve()
    target.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = target / f"ui-regression-{stamp}.json"
    csv_path = target / f"ui-regression-{stamp}.csv"
    html_path = target / f"ui-regression-{stamp}.html"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["page", "mode", "status", "duration_ms", "exceptions", "warnings", "detail"])
        writer.writeheader()
        for item in payload["results"]:
            writer.writerow({**item, "warnings": " | ".join(item["warnings"])})
    rows = "".join(
        f"<tr><td>{html.escape(item.page)}</td><td>{item.mode}</td><td>{item.status}</td><td>{item.duration_ms:.1f}</td><td>{html.escape(item.detail[:500])}</td></tr>"
        for item in results
    )
    html_path.write_text(
        f"<!doctype html><html><body><h1>BioIntel UI Regression</h1><p>{payload['passed']} passed · {payload['failed']} failed</p><table border='1'><tr><th>Page</th><th>Mode</th><th>Status</th><th>ms</th><th>Detail</th></tr>{rows}</table></body></html>",
        encoding="utf-8",
    )
    payload["artifacts"] = {"json": str(json_path), "csv": str(csv_path), "html": str(html_path)}
    return payload
