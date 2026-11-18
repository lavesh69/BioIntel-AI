from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from biointel.api.main import app
from biointel.utils.local_data import (
    delete_managed_files,
    list_managed_files,
)


def test_api_is_available_without_login_or_headers() -> None:
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    payload = health.json()
    assert payload["access_mode"] == "no_login_local"
    assert payload["authentication_required"] is False

    status = client.get("/model/status")
    assert status.status_code == 200
    assert "models" in status.json()

    analysis = client.post(
        "/sequence/analyze",
        json={
            "sequence": ">dna\nATGCGCTAA",
            "sequence_type": "DNA",
        },
    )
    assert analysis.status_code == 200
    assert analysis.json()["analysis"]["length"] == 9


def test_local_data_manager_deletes_only_managed_files(
    tmp_path: Path,
) -> None:
    models = tmp_path / "models"
    reports = tmp_path / "reports"
    models.mkdir()
    reports.mkdir()

    user_model = models / "user_model.joblib"
    user_model.write_bytes(b"model")
    report = reports / "run.json"
    report.write_text("{}", encoding="utf-8")

    listed = list_managed_files(tmp_path)
    assert {item.name for item in listed} == {
        "user_model.joblib",
        "run.json",
    }

    deleted = delete_managed_files(
        tmp_path,
        [
            "models/user_model.joblib",
            "reports/run.json",
        ],
    )
    assert set(deleted) == {
        "models/user_model.joblib",
        "reports/run.json",
    }
    assert not user_model.exists()
    assert not report.exists()


def test_demo_models_are_protected_by_default(
    tmp_path: Path,
) -> None:
    models = tmp_path / "models"
    reports = tmp_path / "reports"
    models.mkdir()
    reports.mkdir()

    demo = models / "demo_classification_model.joblib"
    demo.write_bytes(b"demo")

    with pytest.raises(ValueError, match="protected"):
        delete_managed_files(
            tmp_path,
            ["models/demo_classification_model.joblib"],
        )
    assert demo.exists()


def test_local_data_manager_rejects_path_escape(
    tmp_path: Path,
) -> None:
    (tmp_path / "models").mkdir()
    (tmp_path / "reports").mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("do not delete", encoding="utf-8")

    with pytest.raises(ValueError, match="unmanaged"):
        delete_managed_files(
            tmp_path,
            ["outside.txt"],
        )
    assert outside.exists()
