from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from biointel.training import model_artifact
from biointel.ui.onboarding import OnboardingProfile, load_onboarding, save_onboarding
from biointel.ui.preferences import UiPreferences, load_preferences, save_preferences
from biointel.utils.atomic_io import atomic_write_json, atomic_write_text
from biointel.utils.diagnostics import run_diagnostics


def test_atomic_text_replace_preserves_previous_file_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "state.json"
    destination.write_text("stable", encoding="utf-8")

    def fail_replace(_source: object, _destination: object) -> None:
        raise OSError("controlled replacement failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="controlled replacement failure"):
        atomic_write_text(destination, "partial")

    assert destination.read_text(encoding="utf-8") == "stable"
    assert not list(tmp_path.glob(".state.json.*.tmp"))


def test_atomic_json_and_profile_state_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BIOINTEL_UI_PROFILE", "quality-test")
    payload_path = atomic_write_json(tmp_path / "payload.json", {"value": 7})
    assert json.loads(payload_path.read_text(encoding="utf-8")) == {"value": 7}

    preferences = UiPreferences(palette="Genomic Noir", reduce_effects=True)
    save_preferences(tmp_path, preferences)
    loaded_preferences = load_preferences(tmp_path)
    assert loaded_preferences.palette == "Genomic Noir"
    assert loaded_preferences.reduce_effects is True

    onboarding = OnboardingProfile(role="Bioinformatician", interface_mode="Advanced")
    save_onboarding(tmp_path, onboarding)
    assert load_onboarding(tmp_path) == onboarding


def test_model_discovery_cache_is_change_aware(tmp_path: Path) -> None:
    model_artifact.clear_model_artifact_cache()
    compatible, rejected = model_artifact.discover_compatible_model_artifacts(tmp_path)
    assert compatible == []
    assert rejected == {}
    first = model_artifact._discover_compatible_model_artifacts_cached.cache_info()

    model_artifact.discover_compatible_model_artifacts(tmp_path)
    second = model_artifact._discover_compatible_model_artifacts_cached.cache_info()
    assert second.hits == first.hits + 1

    invalid = tmp_path / "foreign.joblib"
    invalid.write_bytes(b"not-a-joblib")
    compatible, rejected = model_artifact.discover_compatible_model_artifacts(tmp_path)
    assert compatible == []
    assert "foreign.joblib" in rejected
    third = model_artifact._discover_compatible_model_artifacts_cached.cache_info()
    assert third.misses == second.misses + 1


def test_quick_diagnostics_do_not_deep_load_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "models").mkdir(parents=True)
    (tmp_path / "models" / "placeholder.joblib").write_bytes(b"placeholder")

    def forbidden_loader(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("quick diagnostics must not load model payloads")

    monkeypatch.setattr("biointel.utils.diagnostics.load_model_artifact", forbidden_loader)
    checks = run_diagnostics(tmp_path, profile="quick")
    model_check = next(check for check in checks if check.name == "Trusted model artifacts")
    assert model_check.status == "PASS"
    assert "deep compatibility loading" in model_check.message


def test_diagnostics_page_uses_quick_initial_profile() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "pages" / "19_System_Diagnostics.py").read_text(encoding="utf-8")
    assert 'run_diagnostics(root_text, profile="quick")' in source
    assert 'run_diagnostics(ROOT, profile="full")' in source
    assert 'if "diagnostic_checks" not in st.session_state' in source


def test_backup_creation_is_explicitly_request_gated() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "pages" / "18_Workspace_Backup_Restore.py").read_text(encoding="utf-8")
    assert '"Prepare workspace backup"' in source
    assert 'key="prepare_workspace_backup"' in source
    assert 'st.session_state["workspace_backup_prepared"]' in source


def test_patch_version_is_consistent_across_release_surfaces() -> None:
    root = Path(__file__).resolve().parents[1]
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    expected = {
        "pyproject.toml": f'version = "{version}"',
        "src/biointel/__init__.py": f'__version__ = "{version}"',
        "platform/desktop/package.json": f'"version": "{version}"',
        "platform/desktop/src/main.cjs": f"const APP_VERSION = '{version}';",
        "platform/mobile/package.json": f'"version": "{version}"',
        "platform/mobile/android/app/build.gradle": f'versionName "{version}"',
        "deploy/helm/biointel/Chart.yaml": f'appVersion: "{version}"',
        "deploy/terraform/variables.tf": f'default = "{version}"',
    }
    for relative, token in expected.items():
        assert token in (root / relative).read_text(encoding="utf-8"), relative


def test_heavy_release_workspaces_are_cached_or_request_gated() -> None:
    root = Path(__file__).resolve().parents[1]
    evidence = (root / "pages" / "31_Evidence_Package_Studio.py").read_text(encoding="utf-8")
    lineage = (root / "pages" / "32_Release_Readiness_Lineage.py").read_text(encoding="utf-8")
    library = (root / "pages" / "33_Data_Model_Library.py").read_text(encoding="utf-8")

    assert '"Prepare evidence package"' in evidence
    assert "@st.cache_data(ttl=120, show_spinner=False)" in evidence
    assert 'st.session_state["prepared_evidence_package"]' in evidence
    assert "def _cached_release_snapshot" in lineage
    assert "def _cached_data_library_summary" in library
    assert "def _cached_model_library" in library


def test_model_lifecycle_reads_are_cached_and_catalog_writes_are_atomic() -> None:
    root = Path(__file__).resolve().parents[1]
    lifecycle = (root / "pages" / "22_Model_Lifecycle.py").read_text(encoding="utf-8")
    catalog = (root / "src" / "biointel" / "training" / "model_catalog.py").read_text(
        encoding="utf-8"
    )
    assert "def _cached_model_quality" in lifecycle
    assert "def _cached_experiment_depth" in lifecycle
    assert "atomic_write_json(_catalog_path(models_directory), payload)" in catalog


def test_ml_autolab_snapshot_is_cached() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "pages" / "34_ML_AutoLab.py").read_text(encoding="utf-8")
    assert "def _cached_autolab_snapshot" in source
    assert '"artifact_rows": artifact_rows' in source
    assert 'rows = snapshot["artifact_rows"]' in source


def test_workspace_backup_excludes_ephemeral_runtime_residue(tmp_path: Path) -> None:
    from biointel.utils.workspace_backup import create_workspace_backup, inspect_workspace_backup

    reports = tmp_path / "reports"
    (reports / "runtime_logs").mkdir(parents=True)
    for index in range(5_100):
        (reports / "runtime_logs" / f"ERR-{index}.json").write_text("{}", encoding="utf-8")
    (reports / "study.json").write_text('{"status":"reviewed"}', encoding="utf-8")
    (reports / "database.sqlite3-wal").write_bytes(b"transient")

    backup = create_workspace_backup(tmp_path)
    summary = inspect_workspace_backup(backup)
    assert summary.files == ("reports/study.json",)


def test_atomic_binary_write_round_trip(tmp_path: Path) -> None:
    from biointel.utils.atomic_io import atomic_write_bytes

    path = atomic_write_bytes(tmp_path / "artifact.bin", b"biointel")
    assert path.read_bytes() == b"biointel"
