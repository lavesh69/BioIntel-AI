from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_step101_version_is_synchronized():
    assert (ROOT / "VERSION").read_text().strip() == "13.2.0"
    assert 'version = "13.2.0"' in (ROOT / "pyproject.toml").read_text()
    assert '__version__ = "13.2.0"' in (ROOT / "src/biointel/__init__.py").read_text()
    assert json.loads((ROOT / "platform/desktop/package.json").read_text())["version"] == "13.2.0"
    assert json.loads((ROOT / "store/release-manifest.json").read_text())["release_version"] == "13.2.0"


def test_step101_requested_features_are_packaged():
    required = [
        "src/biointel/step101/background.py",
        "src/biointel/step101/ui_regression.py",
        "src/biointel/step101/performance.py",
        "src/biointel/step101/reference_lifecycle.py",
        "src/biointel/step101/reports.py",
        "pages/111_Windows_UI_Regression_Performance_Center.py",
        "RUN_FULL_WINDOWS_UI_REGRESSION.bat",
        "START_BACKGROUND_WORKER_WINDOWS.bat",
        "STOP_BACKGROUND_WORKER_WINDOWS.bat",
        "config/ui_performance_policy.yaml",
        "config/reference_lifecycle_policy.yaml",
        "config/background_job_policy.yaml",
    ]
    for item in required:
        assert (ROOT / item).is_file(), item


def test_step101_navigation_and_launchers_are_connected():
    navigation = (ROOT / "src/biointel/ui/navigation.py").read_text()
    assert "windows_ui_regression_performance" in navigation
    assert "111_Windows_UI_Regression_Performance_Center.py" in navigation
    run_helper = (ROOT / "scripts/run_biointel_step97.py").read_text()
    assert "BackgroundJobService" in run_helper
    assert "worker_pid" in run_helper
    report_page = (ROOT / "pages/26_Research_Report_Studio.py").read_text()
    assert "UnifiedScientificReportBuilder" in report_page
    reference_page = (ROOT / "pages/106_Reference_Database_Manager.py").read_text()
    assert "ReferenceLifecycleManager" in reference_page


def test_step101_self_test_expects_current_version():
    text = (ROOT / "scripts/step97_self_test.py").read_text()
    assert 'version != "13.2.0"' in text
    assert "biointel.step101.self-test.v1" in text
