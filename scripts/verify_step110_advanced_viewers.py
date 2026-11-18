from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.ui.advanced_scientific_viewers import ADVANCED_VIEWER_CATALOG, build_advanced_viewer_visuals


def _viewer_data_checks() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for key in ADVANCED_VIEWER_CATALOG:
        try:
            visuals = build_advanced_viewer_visuals(key)
            passed = 3 <= len(visuals) <= 5 and all(not item.data.empty for item in visuals)
            rows.append({
                "viewer": key,
                "passed": passed,
                "visuals": len(visuals),
                "records": [len(item.data) for item in visuals],
            })
        except Exception as exc:
            rows.append({"viewer": key, "passed": False, "error": f"{type(exc).__name__}: {exc}"})
    return rows


def _runtime_hub_check() -> dict[str, object]:
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(ROOT / "pages/165_Advanced_Scientific_Viewers.py"), default_timeout=45)
    app.run(timeout=45)
    rows: list[dict[str, object]] = []
    for key in ADVANCED_VIEWER_CATALOG:
        app.selectbox(key="advanced_viewer_hub_choice").select(key)
        app.run(timeout=45)
        single_ok = not app.exception and not app.error and len(app.get("plotly_chart")) == 1
        app.radio(key=f"hub_{key}_layout").set_value("Compare two views")
        app.run(timeout=45)
        compare_ok = not app.exception and not app.error and len(app.get("plotly_chart")) == 2
        rows.append({
            "viewer": key,
            "single_view": single_ok,
            "compare_view": compare_ok,
            "exceptions": [str(item.value) for item in app.exception],
            "errors": [str(item.value) for item in app.error],
        })
    return {
        "passed": all(row["single_view"] and row["compare_view"] for row in rows),
        "viewers": rows,
    }


def main() -> int:
    tests = [
        "tests/test_step107_scientific_visual_excellence.py",
        "tests/test_step108_decision_visuals.py",
        "tests/test_step109_visual_interaction.py",
        "tests/test_step110_advanced_scientific_viewers.py",
        "tests/visual/test_semantic_visual_regression.py::test_semantic_manifest_integrity",
    ]
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *tests],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=480,
        check=False,
    )
    data_checks = _viewer_data_checks()
    runtime = _runtime_hub_check()
    embedded_path = ROOT / "reports/step110_embedded_page_runtime.json"
    embedded = json.loads(embedded_path.read_text(encoding="utf-8")) if embedded_path.exists() else {}
    report = {
        "schema": "biointel.step110.advanced-viewers-verification.v1",
        "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "viewer_count": len(ADVANCED_VIEWER_CATALOG),
        "data_checks_passed": sum(bool(row.get("passed")) for row in data_checks),
        "data_checks": data_checks,
        "runtime_hub": runtime,
        "embedded_pages": embedded,
        "pytest_returncode": completed.returncode,
        "pytest_stdout": completed.stdout,
        "pytest_stderr": completed.stderr,
    }
    output = ROOT / "reports/step110_advanced_viewers_verification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(completed.stdout)
    if completed.stderr:
        print(completed.stderr, file=sys.stderr)
    print(json.dumps({
        "viewers": len(data_checks),
        "data_passed": report["data_checks_passed"],
        "runtime_passed": runtime["passed"],
        "embedded_pages_passed": embedded.get("passed"),
        "embedded_pages_total": embedded.get("total"),
        "report": str(output),
    }, indent=2))
    passed = (
        completed.returncode == 0
        and report["data_checks_passed"] == len(data_checks)
        and runtime["passed"]
        and embedded.get("passed") == embedded.get("total")
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
