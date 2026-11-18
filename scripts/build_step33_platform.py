from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Reuse the proven Step 32 physical-asset/readiness foundation without mutating scientific scope.
from build_step32_foundation import sync_physical_assets_and_issues

from biointel.api.security_store import ApiSecurityStore
from biointel.data.public_reference import build_public_reference_catalog
from biointel.data.relationship_integrity import rebuild_relationship_registry
from biointel.database.integrity_guards import install_integrity_guards
from biointel.integrations.public_sync import initialize_sync_registry
from biointel.jobs.local_queue import LocalJobQueue


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def stable_id(*parts: object, length: int = 28) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:length]


def sync_step33_assets() -> dict[str, int]:
    database = ROOT / "reports" / "assets.sqlite3"
    timestamp = utc_now()
    targets = [
        (
            "database",
            "API Security & Request Audit Database",
            ROOT / "reports" / "api_security.sqlite3",
            "Persistent API identities, role-aware access, request audit, idempotency and restart-safe rate limits.",
        ),
        (
            "configuration",
            "Production Docker Compose",
            ROOT / "docker-compose.production.yml",
            "Optional PostgreSQL, Redis, MinIO, API and Streamlit production topology.",
        ),
        (
            "configuration",
            "Production Environment Template",
            ROOT / "config" / "production.example.env",
            "Production security and service configuration template without bundled secrets.",
        ),
        (
            "configuration",
            "Production Python Requirements",
            ROOT / "requirements-production.txt",
            "Optional production dependencies for PostgreSQL, Redis, workers, storage and telemetry.",
        ),
        (
            "source",
            "Official Scientific Sync Manager",
            ROOT / "src" / "biointel" / "integrations" / "public_sync.py",
            "Bounded official ChEMBL and UniProt reference synchronization with provenance and checksums.",
        ),
        (
            "source",
            "Native Database Integrity Guards",
            ROOT / "src" / "biointel" / "database" / "integrity_guards.py",
            "Trigger-based parent integrity enforcement for legacy SQLite registries.",
        ),
        (
            "source",
            "Role-aware API Security Store",
            ROOT / "src" / "biointel" / "api" / "security_store.py",
            "Hashed API clients, audit logs, rate windows, security events and idempotency.",
        ),
        (
            "source",
            "Local Background Worker",
            ROOT / "src" / "biointel" / "jobs" / "worker.py",
            "Executes supported scientific synchronization, diagnostics and database-maintenance jobs with staged progress.",
        ),
    ]
    inserted = 0
    with sqlite3.connect(database) as connection:
        for asset_type, title, path, description in targets:
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT).as_posix()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            asset_id = stable_id("step33", asset_type, relative)
            connection.execute(
                """
                INSERT INTO research_assets(
                    asset_id,asset_type,title,path,source,sha256,size_bytes,mime_type,
                    status,description,metadata_json,created_at_utc,updated_at_utc
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(asset_id) DO UPDATE SET
                    title=excluded.title,sha256=excluded.sha256,size_bytes=excluded.size_bytes,
                    status=excluded.status,description=excluded.description,
                    metadata_json=excluded.metadata_json,updated_at_utc=excluded.updated_at_utc
                """,
                (
                    asset_id,
                    asset_type,
                    title,
                    relative,
                    "BioIntel Step 33 production platform",
                    digest,
                    path.stat().st_size,
                    "application/octet-stream",
                    "active",
                    description,
                    json.dumps(
                        {
                            "step": 33,
                            "portable": True,
                            "scientific_scope": "software_infrastructure",
                        }
                    ),
                    timestamp,
                    timestamp,
                ),
            )
            inserted += 1
        connection.commit()
        database_assets = int(
            connection.execute(
                "SELECT COUNT(*) FROM research_assets WHERE asset_type='database'"
            ).fetchone()[0]
        )
    return {"assets_synchronized": inserted, "database_assets": database_assets}


def build() -> dict[str, object]:
    public_reference = build_public_reference_catalog(ROOT)
    dataset_foundation = sync_physical_assets_and_issues()
    security = ApiSecurityStore(ROOT / "reports" / "api_security.sqlite3")
    queue = LocalJobQueue(ROOT / "reports" / "jobs.sqlite3")
    orchestration_backfill = queue.backfill_existing_history()
    queue.heartbeat(
        "local-step33-worker",
        worker_type="local",
        status="online",
        capabilities={"cpu": True, "document_jobs": True, "bioinformatics_jobs": True},
        metadata={"milestone": 33, "purpose": "local orchestration readiness"},
    )
    initialize_sync_registry(ROOT / "reports" / "internet_downloads.sqlite3")
    guards = install_integrity_guards(ROOT)
    assets = sync_step33_assets()
    relationships = rebuild_relationship_registry(ROOT)
    payload: dict[str, object] = {
        "version": "3.3.0",
        "milestone": "Step 33 Production Scientific Platform",
        "public_reference": asdict(public_reference),
        "dataset_foundation": dataset_foundation,
        "api_security": security.status(),
        "job_orchestration": queue.orchestration_summary(),
        "job_orchestration_backfill": orchestration_backfill,
        "integrity_guards": {name: asdict(result) for name, result in guards.items()},
        "assets": assets,
        "relationships": asdict(relationships),
        "scientific_boundary": (
            "Official provider synchronization and public identifiers remain reference-only until "
            "curation, licence review, independent validation and release-gate approval."
        ),
    }
    output = ROOT / "reports" / "generated" / "step33_platform_summary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return payload


def main() -> None:
    print(json.dumps(build(), indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
