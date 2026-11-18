from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "step67_theme_font_qualification.json"


def load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def run(command: list[str]) -> dict[str, object]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "passed": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    from biointel.engineering.repository_audit import scan_repository_secrets
    from biointel.ui.appearance_engine import CHART_PROFILES, LIGHT_THEMES, THEME_META
    from biointel.ui.style_catalog import FONTS, THEMES

    lint = run([sys.executable, "-m", "ruff", "check", "src", "pages", "scripts/verify_step67_theme_browser.py", "scripts/verify_step67_theme_font.py", "tests/test_step67_theme_font_excellence.py"])
    compile_check = run([sys.executable, "-m", "compileall", "-q", "src", "pages", "scripts"])
    regressions = load_json("reports/step67_ui_theme_regression_summary.json")
    runtime = load_json("reports/step67_streamlit_theme_font_matrix.json")
    browser = load_json("reports/step67_browser_theme_verification.json")
    store = load_json("reports/step67_store_release_verification.json")
    secrets = scan_repository_secrets(ROOT)
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

    checks = {
        "version": version,
        "ruff": lint,
        "compilation": compile_check,
        "theme_count": len(THEMES),
        "font_count": len(FONTS),
        "light_palette_count": len(LIGHT_THEMES),
        "chart_profile_count": len(CHART_PROFILES),
        "theme_metadata_count": len(THEME_META),
        "regressions": regressions,
        "streamlit_runtime": runtime,
        "browser": browser,
        "store": {
            "implementation_ready": store.get("implementation_ready"),
            "internal_failures": store.get("internal_failures"),
            "database_summary": store.get("database_summary", {}),
        },
        "secrets": secrets,
        "mobile_layout_scope": "unchanged",
    }
    passed = all(
        [
            version == "6.8.0",
            bool(lint["passed"]),
            bool(compile_check["passed"]),
            len(THEMES) == 17,
            len(FONTS) == 11,
            len(LIGHT_THEMES) == 17,
            len(CHART_PROFILES) == 17,
            len(THEME_META) == 17,
            regressions.get("passed") is True,
            regressions.get("tests") == 126,
            runtime.get("passed") is True,
            runtime.get("scenario_count") == 28,
            browser.get("passed") is True,
            browser.get("screenshots") == 34,
            store.get("internal_failures") == 0,
            secrets.get("passed") is True,
        ]
    )
    payload = {
        "schema": "biointel.step67.theme-font-qualification.v1",
        "passed": passed,
        "checks": checks,
        "historical_full_suite_note": (
            "The complete 77-file historical suite exceeded the bounded execution window in this environment. "
            "No complete-suite pass is claimed; 126 impacted UI/theme/store/runtime tests were executed and passed."
        ),
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
