from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from biointel.automation import (
    DEFAULT_WORKFLOWS,
    list_workflow_runs,
    register_default_workflows,
    resume_workflow_run,
    start_workflow_run,
    update_workflow_step,
    workflow_run_snapshot,
)
from biointel.ui.navigation import PAGE_BY_KEY
from biointel.ui.onboarding import OnboardingProfile, load_onboarding, save_onboarding
from biointel.ui.runtime_guard import runtime_diagnostic_bundle, write_runtime_error


def test_default_workflow_page_keys_are_valid() -> None:
    for definition in DEFAULT_WORKFLOWS:
        assert definition.steps
        keys = {step.key for step in definition.steps}
        for step in definition.steps:
            assert set(step.dependencies).issubset(keys)
            assert not step.page_key or step.page_key in PAGE_BY_KEY


def test_workflow_dependencies_progress_and_resume(tmp_path: Path) -> None:
    database = tmp_path / "automation.sqlite3"
    register_default_workflows(database)
    run_id = start_workflow_run(database, "sequence_to_report")
    initial = workflow_run_snapshot(database, run_id)
    assert initial.status == "running"
    assert initial.progress_percent == 0.0
    assert initial.steps[0]["status"] == "ready"
    assert initial.steps[1]["status"] == "blocked"

    with pytest.raises(ValueError, match="Complete dependencies first"):
        update_workflow_step(database, run_id, "comparison", "completed")

    update_workflow_step(database, run_id, "sequence_qc", "completed")
    after_first = workflow_run_snapshot(database, run_id)
    assert after_first.progress_percent == 25.0
    assert after_first.steps[1]["status"] == "ready"

    failed = update_workflow_step(
        database, run_id, "comparison", "failed", message="synthetic test failure"
    )
    assert failed.status == "failed"
    resumed = resume_workflow_run(database, run_id)
    assert resumed.status == "running"
    assert (
        next(step for step in resumed.steps if step["step_key"] == "comparison")["status"]
        == "ready"
    )

    listed = list_workflow_runs(database)
    assert listed and listed[0].run_id == run_id
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_onboarding_profile_is_durable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BIOINTEL_UI_PROFILE", "test-profile")
    profile = OnboardingProfile(
        role="Bioinformatician",
        experience="Advanced",
        interface_mode="Advanced",
        primary_goal="Analyse biological data",
        completed_at_utc="2026-07-08T12:00:00+00:00",
    )
    saved = save_onboarding(tmp_path, profile)
    assert saved.is_file()
    assert load_onboarding(tmp_path) == profile


def test_runtime_error_report_and_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import biointel.ui.runtime_guard as guard

    monkeypatch.setattr(guard, "LOG_DIR", tmp_path / "runtime_logs")
    error_id, payload = write_runtime_error("step82-test", ValueError("controlled failure"))
    assert error_id.startswith("ERR-")
    assert payload["context"] == "step82-test"
    bundle = json.loads(runtime_diagnostic_bundle(limit=10))
    assert bundle["schema"] == "biointel.runtime_diagnostics.v2"
    assert bundle["reports"][0]["error_id"] == error_id


def test_desktop_shell_contains_step82_reliability_controls() -> None:
    root = Path(__file__).resolve().parents[1]
    main = (root / "platform/desktop/src/main.cjs").read_text(encoding="utf-8")
    package = json.loads((root / "platform/desktop/package.json").read_text(encoding="utf-8"))
    assert "requestSingleInstanceLock" in main
    assert "biointel://" in main
    assert "render-process-gone" in main
    assert "BIOINTEL_UPDATE_MANIFEST_URL" in main
    assert package["version"] == (root / "VERSION").read_text(encoding="utf-8").strip()
    assert package["build"]["protocols"][0]["schemes"] == ["biointel"]
    assert package["build"]["fileAssociations"]


def test_release_version_is_consistent() -> None:
    root = Path(__file__).resolve().parents[1]
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    assert f'__version__ = "{version}"' in (root / "src/biointel/__init__.py").read_text(
        encoding="utf-8"
    )
    assert f'version = "{version}"' in (root / "pyproject.toml").read_text(encoding="utf-8")
