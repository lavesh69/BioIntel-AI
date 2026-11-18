from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from biointel.education import selective_mega_api
from biointel.education.platform import EducationPlatform
from biointel.education.selective_mega import EducationMegaService


def test_selective_mega_api_enforces_service_permissions(tmp_path: Path, monkeypatch) -> None:
    platform = EducationPlatform(tmp_path / "api.sqlite3", tmp_path / "media")
    institution_id = platform.create_institution("admin", "API University")["id"]
    platform.add_member("admin", institution_id, "viewer", "viewer")
    root = Path(__file__).resolve().parents[1]
    current = EducationMegaService(platform, root / "config" / "education_official_sources.json")
    monkeypatch.setattr(selective_mega_api, "service", lambda: current)
    app = FastAPI()
    app.include_router(selective_mega_api.router)
    client = TestClient(app)

    health = client.get("/mega/health")
    assert health.status_code == 200
    denied = client.post(
        "/mega/entities",
        json={
            "actor": "viewer",
            "institution_id": institution_id,
            "entity_type": "campus",
            "name": "Forbidden",
        },
    )
    assert denied.status_code == 403
    created = client.post(
        "/mega/entities",
        json={
            "actor": "admin",
            "institution_id": institution_id,
            "entity_type": "campus",
            "name": "Main Campus",
            "code": "MAIN",
        },
    )
    assert created.status_code == 201
    snapshot = client.get(
        f"/mega/institutions/{institution_id}/snapshot",
        params={"actor": "viewer"},
    )
    assert snapshot.status_code == 200
    assert snapshot.json()["institutions"] == 1


def test_selective_mega_api_validation_and_conflicts(tmp_path: Path, monkeypatch) -> None:
    platform = EducationPlatform(tmp_path / "api-conflict.sqlite3", tmp_path / "media")
    institution_id = platform.create_institution("admin", "API College")["id"]
    root = Path(__file__).resolve().parents[1]
    current = EducationMegaService(platform, root / "config" / "education_official_sources.json")
    monkeypatch.setattr(selective_mega_api, "service", lambda: current)
    app = FastAPI()
    app.include_router(selective_mega_api.router)
    client = TestClient(app)
    payload = {
        "actor": "admin",
        "institution_id": institution_id,
        "name": "Biology",
        "class_code": "BIO-2026",
    }
    assert client.post("/mega/classes", json=payload).status_code == 201
    assert client.post("/mega/classes", json=payload).status_code == 409
    invalid = client.post("/mega/classes", json={**payload, "class_code": "x"})
    assert invalid.status_code == 422
