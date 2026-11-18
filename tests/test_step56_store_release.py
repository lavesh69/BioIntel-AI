from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from biointel.api.main import app
from biointel.privacy.controls import (
    build_privacy_inventory,
    clear_local_activity,
    export_local_activity,
)
from biointel.release.store_readiness import build_store_readiness
from biointel.security.passwords import hash_password, verify_password
from biointel.security.ui_users import parse_ui_users

ROOT = Path(__file__).resolve().parents[1]


def test_password_hash_round_trip_and_malformed_input() -> None:
    encoded = hash_password("A-professional-password-2026!", iterations=310_000, salt=b"0123456789abcdef")
    assert encoded.startswith("pbkdf2_sha256$310000$")
    assert verify_password("A-professional-password-2026!", encoded)
    assert not verify_password("incorrect-password", encoded)
    assert not verify_password("anything", "not-a-supported-hash")


def test_ui_user_configuration_supports_mapping_and_list(monkeypatch) -> None:
    encoded = hash_password("A-professional-password-2026!", iterations=310_000, salt=b"0123456789abcdef")
    mapping = {"admin": {"display_name": "Administrator", "role": "admin", "password_hash": encoded}}
    monkeypatch.setenv("BIOINTEL_UI_USERS_JSON", json.dumps(mapping))
    assert parse_ui_users(json.dumps(mapping))["admin"]["role"] == "admin"

    listed = {"users": [{"username": "reviewer", "display_name": "Reviewer", "role": "reviewer", "password_hash": encoded}]}
    monkeypatch.setenv("BIOINTEL_UI_USERS_JSON", json.dumps(listed))
    assert parse_ui_users(json.dumps(listed))["reviewer"]["display_name"] == "Reviewer"


def test_privacy_inventory_export_and_clear_preserve_scientific_data(tmp_path: Path) -> None:
    (tmp_path / "reports/security").mkdir(parents=True)
    (tmp_path / "reports/logs").mkdir(parents=True)
    (tmp_path / "reports/ui_preferences.json").write_text("{}", encoding="utf-8")
    profile_preferences = tmp_path / "reports/ui_profiles/default/preferences.json"
    profile_preferences.parent.mkdir(parents=True)
    profile_preferences.write_text('{"font_family":"Georgia"}', encoding="utf-8")
    (tmp_path / "reports/security/ui_access_events.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "data").mkdir()
    scientific = tmp_path / "data/study.csv"
    scientific.write_text("sample,value\nA,1\n", encoding="utf-8")

    inventory = build_privacy_inventory(tmp_path)
    assert inventory["processing_model"].startswith("local-first")
    payload = export_local_activity(tmp_path)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert "privacy_inventory.json" in archive.namelist()
        assert "reports/ui_preferences.json" in archive.namelist()
        assert "reports/ui_profiles/default/preferences.json" in archive.namelist()
        assert "data/study.csv" not in archive.namelist()

    result = clear_local_activity(tmp_path)
    assert result["completed"] is True
    assert scientific.is_file()
    assert not (tmp_path / "reports/ui_preferences.json").exists()
    assert not profile_preferences.exists()


def test_store_readiness_and_native_release_contracts() -> None:
    readiness = build_store_readiness(ROOT)
    assert readiness["repository_readiness_percent"] == 100.0
    assert all(readiness["repository_checks"].values())

    variables = (ROOT / "platform/mobile/android/variables.gradle").read_text(encoding="utf-8")
    assert "targetSdkVersion = 36" in variables
    project = (ROOT / "platform/mobile/ios/App/App.xcodeproj/project.pbxproj").read_text(encoding="utf-8")
    assert "PrivacyInfo.xcprivacy in Resources" in project
    desktop = json.loads((ROOT / "platform/desktop/package.json").read_text(encoding="utf-8"))
    assert {"appx", "nsis"}.issubset(set(desktop["build"]["win"]["target"]))


def test_mobile_bootstrap_legal_and_store_readiness_endpoints() -> None:
    client = TestClient(app)
    bootstrap = client.get("/v1/mobile/bootstrap")
    assert bootstrap.status_code == 200
    payload = bootstrap.json()
    assert payload["version"] == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert payload["status"] == "ready"
    assert "not medical diagnosis" in payload["scientific_boundary"].lower()

    for route in ("/legal/privacy", "/legal/terms", "/legal/support", "/v1/mobile/privacy", "/v1/store/readiness"):
        response = client.get(route)
        assert response.status_code == 200, (route, response.text)
