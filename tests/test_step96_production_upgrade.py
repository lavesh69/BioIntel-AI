from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from biointel.biotech.lab_import import normalize_instrument_export, parse_rdml
from biointel.model_qualification.package import qualify_model_package
from biointel.production.user_data import create_backup, merge_seed_tree, restore_backup, validate_backup
from biointel.reference_assets.manager import ReferenceAssetRegistry, download_asset, safe_extract_archive


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_model_manifest(package: Path, model: Path) -> None:
    protected = [model, package / "model_card.json", package / "dataset_manifest.json", package / "metrics.json"]
    rows = [{"path": item.name, "sha256": digest(item)} for item in protected]
    (package / "FILE_MANIFEST_SHA256.json").write_text(json.dumps({"files": rows}))


def test_complete_user_data_backup_and_restore(tmp_path: Path):
    user = tmp_path / "user"
    (user / "data").mkdir(parents=True)
    (user / "reports" / "nested").mkdir(parents=True)
    (user / "data" / "db.sqlite3").write_bytes(b"database")
    (user / "reports" / "nested" / "custom.txt").write_text("not only databases", encoding="utf-8")
    backup = create_backup(user, tmp_path / "backups", label="test")
    validation = validate_backup(backup)
    assert validation.valid and validation.checked_files == 2
    restored = tmp_path / "restored"
    restore_backup(backup, restored)
    assert (restored / "reports" / "nested" / "custom.txt").read_text() == "not only databases"


def test_seed_merge_never_overwrites_user_files(tmp_path: Path):
    seed = tmp_path / "seed"
    destination = tmp_path / "destination"
    seed.mkdir(); destination.mkdir()
    (seed / "existing.txt").write_text("packaged", encoding="utf-8")
    (seed / "new.txt").write_text("new", encoding="utf-8")
    (destination / "existing.txt").write_text("user", encoding="utf-8")
    result = merge_seed_tree(seed, destination)
    assert result == {"copied": 1, "preserved": 1, "replaced": 0}
    assert (destination / "existing.txt").read_text() == "user"


def test_safe_reference_extract_blocks_traversal(tmp_path: Path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../escape.txt", "blocked")
    with pytest.raises(ValueError):
        safe_extract_archive(archive, tmp_path / "out")


def test_reference_registry_has_foreign_keys_and_events(tmp_path: Path):
    registry = ReferenceAssetRegistry(tmp_path / "assets.sqlite3")
    from biointel.reference_assets.manager import AssetRecord
    record = AssetRecord("asset", "provider", "v1", "verified", "", "/tmp/a", "", "abc", 1, "CC0", True, "2026-01-01T00:00:00Z")
    registry.upsert(record, event_type="test")
    assert registry.list_assets()[0]["asset_id"] == "asset"
    assert registry.events("asset")[0]["event_type"] == "test"


def test_quantstudio_normalization_preserves_source_columns():
    frame = pd.DataFrame({"Well Position": ["A1"], "Sample Name": ["S1"], "Target Name": ["ACTB"], "CT Mean": [21.5], "Task": ["UNKNOWN"]})
    output = normalize_instrument_export(frame)
    assert output.loc[0, "sample"] == "S1"
    assert output.loc[0, "gene"] == "ACTB"
    assert output.loc[0, "ct"] == 21.5
    assert "Sample Name" in output.columns
    assert output.attrs["instrument_profile"] == "QuantStudio"


def test_rdml_parser_marks_format():
    data = b"<?xml version='1.0'?><rdml><sample id='S1'><type>unkn</type></sample><experiment><run><react id='A1'><sample id='S1'/><data><tar id='ACTB'/><cq>22.1</cq></data></react></run></experiment></rdml>"
    frame = parse_rdml(data)
    assert frame.loc[0, "ct"] == 22.1
    assert frame.loc[0, "instrument_format"] == "RDML"


def test_external_model_package_rejects_missing_external_validation(tmp_path: Path):
    package = tmp_path / "model"
    package.mkdir()
    model = package / "model.bin"
    model.write_bytes(b"safe artifact")
    (package / "model_card.json").write_text(json.dumps({
        "model_name": "test", "model_version": "1", "intended_use": "research", "algorithm": "logistic",
        "created_at_utc": "2026-01-01T00:00:00Z", "artifact_path": "model.bin", "synthetic_training_data": False,
        "validation": {"independent_external": False, "calibration_assessed": True},
        "limitations": ["example"], "applicability_domain": "example",
    }))
    (package / "dataset_manifest.json").write_text(json.dumps({"dataset_sha256": "a" * 64, "license": "CC BY"}))
    (package / "metrics.json").write_text(json.dumps({"roc_auc": 0.9}))
    write_model_manifest(package, model)
    result = qualify_model_package(package, require_external_validation=True)
    assert not result.qualified
    assert any("Independent external validation" in blocker for blocker in result.blockers)


def test_external_model_package_qualifies_complete_evidence(tmp_path: Path):
    package = tmp_path / "model"
    package.mkdir()
    model = package / "model.bin"
    model.write_bytes(b"safe artifact")
    (package / "model_card.json").write_text(json.dumps({
        "model_name": "test", "model_version": "1", "intended_use": "research", "algorithm": "logistic",
        "created_at_utc": "2026-01-01T00:00:00Z", "artifact_path": "model.bin", "synthetic_training_data": False,
        "validation": {"independent_external": True, "temporal_or_scaffold_split": True, "calibration_assessed": True},
        "limitations": ["example"], "applicability_domain": "example",
    }))
    (package / "dataset_manifest.json").write_text(json.dumps({"dataset_sha256": "a" * 64, "license": "CC BY"}))
    (package / "metrics.json").write_text(json.dumps({"roc_auc": 0.9}))
    write_model_manifest(package, model)
    result = qualify_model_package(package)
    assert result.qualified
    assert result.files_verified == 4



def test_reference_extract_enforces_uncompressed_limit(tmp_path: Path):
    archive = tmp_path / "large.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("large.txt", "x" * 128)
    with pytest.raises(ValueError, match="uncompressed-size"):
        safe_extract_archive(archive, tmp_path / "out", max_uncompressed_bytes=64)


def test_download_rejects_credentials_and_insecure_scheme(tmp_path: Path):
    with pytest.raises(ValueError, match="HTTPS"):
        download_asset("http://example.org/file", tmp_path / "file")
    with pytest.raises(ValueError, match="Credentials"):
        download_asset("https://user:secret@example.org/file", tmp_path / "file")


def test_restore_mirror_removes_new_files(tmp_path: Path):
    user = tmp_path / "user"
    (user / "data").mkdir(parents=True)
    (user / "data" / "original.txt").write_text("original")
    backup = create_backup(user, tmp_path / "backups")
    (user / "data" / "new.txt").write_text("new")
    restore_backup(backup, user, mirror=True)
    assert (user / "data" / "original.txt").is_file()
    assert not (user / "data" / "new.txt").exists()


def test_external_model_manifest_duplicate_path_is_blocked(tmp_path: Path):
    package = tmp_path / "model"
    package.mkdir()
    model = package / "model.bin"
    model.write_bytes(b"artifact")
    row = {"path": "model.bin", "sha256": digest(model)}
    (package / "FILE_MANIFEST_SHA256.json").write_text(json.dumps({"files": [row, row]}))
    (package / "model_card.json").write_text(json.dumps({
        "model_name": "test", "model_version": "1", "intended_use": "research", "algorithm": "x",
        "created_at_utc": "2026-01-01T00:00:00Z", "artifact_path": "model.bin",
        "synthetic_training_data": False, "validation": {"independent_external": True},
        "limitations": ["x"], "applicability_domain": "x"
    }))
    (package / "dataset_manifest.json").write_text(json.dumps({"dataset_sha256": "a" * 64, "license": "CC0"}))
    (package / "metrics.json").write_text(json.dumps({"auc": 0.9}))
    result = qualify_model_package(package)
    assert not result.qualified
    assert any("Duplicate" in item for item in result.blockers)


def test_step96_version_and_persistent_paths_are_synchronized():
    import tomllib
    root = Path(__file__).resolve().parents[1]
    assert (root / "VERSION").read_text().strip() == "13.2.0"
    pyproject = tomllib.loads((root / "pyproject.toml").read_text())
    assert pyproject["project"]["version"] == "13.2.0"
    assert pyproject["tool"]["ruff"]["target-version"] == "py311"
    assert json.loads((root / "platform/desktop/package.json").read_text())["version"] == "13.2.0"
    assert json.loads((root / "store/release-manifest.json").read_text())["release_version"] == "13.2.0"
    assert json.loads((root / "store/model-manifest.json").read_text())["version"] == "13.2.0"
    runtime = (root / "src/biointel/tools/runtime.py").read_text()
    assert 'Path(local) / "BioIntelAI" / "Tools"' in runtime


def test_transactional_installer_has_full_rollback_controls():
    root = Path(__file__).resolve().parents[1]
    transaction = (root / "scripts/install_step96_transaction.ps1").read_text()
    rollback = (root / "scripts/rollback_step96.ps1").read_text()
    assert "BIOINTEL_BACKUP_MANIFEST.json" in transaction
    assert "Get-FileHash -Algorithm SHA256" in transaction
    assert "mklink /J" in transaction
    assert "Restore-UserDataMirror" in transaction
    assert "FailedActivation" in rollback
    assert (root / "scripts/finalize_step96_install.ps1").is_file()
