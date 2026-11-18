from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.data.public_reference import build_public_reference_catalog
from biointel.data.relationship_integrity import rebuild_relationship_registry


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def stable_id(*parts: object, length: int = 28) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:length]


def sync_physical_assets_and_issues() -> dict[str, int]:
    path = ROOT / "reports" / "datasets.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS physical_data_assets (
                asset_sha256 TEXT PRIMARY KEY,
                primary_relative_path TEXT NOT NULL,
                file_format TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                data_scope TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS dataset_asset_bindings (
                dataset_sha256 TEXT NOT NULL,
                asset_sha256 TEXT NOT NULL,
                role TEXT NOT NULL,
                is_shared INTEGER NOT NULL DEFAULT 0 CHECK(is_shared IN (0,1)),
                created_at_utc TEXT NOT NULL,
                PRIMARY KEY(dataset_sha256,asset_sha256,role),
                FOREIGN KEY(dataset_sha256) REFERENCES datasets(dataset_sha256) ON DELETE CASCADE,
                FOREIGN KEY(asset_sha256) REFERENCES physical_data_assets(asset_sha256) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_dataset_asset_bindings_asset ON dataset_asset_bindings(asset_sha256);
            """
        )
        timestamp = now()
        file_rows = connection.execute(
            """
            SELECT f.dataset_sha256,f.relative_path,f.file_format,f.size_bytes,f.sha256,f.role,d.metadata_json
            FROM dataset_files f JOIN datasets d USING(dataset_sha256)
            ORDER BY f.dataset_sha256,f.role
            """
        ).fetchall()
        counts: dict[str, int] = {}
        for _, _, _, _, sha256, _, _ in file_rows:
            counts[sha256] = counts.get(sha256, 0) + 1
        for (
            dataset_sha,
            relative_path,
            file_format,
            size_bytes,
            file_sha,
            role,
            metadata_json,
        ) in file_rows:
            try:
                metadata = json.loads(metadata_json or "{}")
            except json.JSONDecodeError:
                metadata = {}
            scope = "public_reference" if metadata.get("public_reference") else "demo_reference"
            connection.execute(
                """
                INSERT INTO physical_data_assets(asset_sha256,primary_relative_path,file_format,size_bytes,data_scope,metadata_json,created_at_utc,updated_at_utc)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(asset_sha256) DO UPDATE SET
                    primary_relative_path=excluded.primary_relative_path,file_format=excluded.file_format,
                    size_bytes=excluded.size_bytes,data_scope=excluded.data_scope,updated_at_utc=excluded.updated_at_utc
                """,
                (
                    file_sha,
                    relative_path,
                    file_format,
                    int(size_bytes),
                    scope,
                    json.dumps({"source": "dataset_files"}),
                    timestamp,
                    timestamp,
                ),
            )
            connection.execute(
                """
                INSERT INTO dataset_asset_bindings(dataset_sha256,asset_sha256,role,is_shared,created_at_utc)
                VALUES(?,?,?,?,?)
                ON CONFLICT(dataset_sha256,asset_sha256,role) DO UPDATE SET is_shared=excluded.is_shared
                """,
                (dataset_sha, file_sha, role, int(counts.get(file_sha, 0) > 1), timestamp),
            )

        readiness_rows = connection.execute(
            "SELECT dataset_sha256,scientific_status FROM dataset_readiness"
        ).fetchall()
        for dataset_sha, scientific_status in readiness_rows:
            if scientific_status == "release_eligible":
                continue
            category = "scientific_scope"
            severity = (
                "warning" if scientific_status == "needs_evidence_review" else "informational"
            )
            message = (
                "Evidence review and independent validation are required before scientific release."
                if scientific_status == "needs_evidence_review"
                else "Dataset is registered as reference/demo data and is not scientific-release eligible."
            )
            issue_id = stable_id(dataset_sha, category)
            connection.execute(
                """
                INSERT INTO dataset_validation_issues(issue_id,dataset_sha256,severity,category,message,resolution_status,metadata_json,created_at_utc,resolved_at_utc)
                VALUES(?,?,?,?,?,'open',?,?,NULL)
                ON CONFLICT(issue_id) DO UPDATE SET severity=excluded.severity,message=excluded.message,resolution_status='open',metadata_json=excluded.metadata_json
                """,
                (
                    issue_id,
                    dataset_sha,
                    severity,
                    category,
                    message,
                    json.dumps({"scientific_status": scientific_status, "step": 32}),
                    timestamp,
                ),
            )
        connection.commit()
        physical = connection.execute("SELECT COUNT(*) FROM physical_data_assets").fetchone()[0]
        bindings = connection.execute("SELECT COUNT(*) FROM dataset_asset_bindings").fetchone()[0]
        shared = connection.execute(
            "SELECT COUNT(*) FROM dataset_asset_bindings WHERE is_shared=1"
        ).fetchone()[0]
        issues = connection.execute(
            "SELECT COUNT(*) FROM dataset_validation_issues WHERE resolution_status='open'"
        ).fetchone()[0]
    return {
        "physical_assets": int(physical),
        "asset_bindings": int(bindings),
        "shared_bindings": int(shared),
        "open_scientific_scope_issues": int(issues),
    }


def sync_step32_assets() -> dict[str, int]:
    database = ROOT / "reports" / "assets.sqlite3"
    timestamp = now()
    targets = [
        (
            "database",
            "Cross-database Relationship Registry",
            ROOT / "reports" / "relationships.sqlite3",
            "Step 32 relationship registry with foreign-key-enforced nodes and edges.",
        ),
        (
            "dataset",
            "UCI Breast Cancer Wisconsin Diagnostic Public Reference",
            ROOT / "data" / "public_reference" / "uci_breast_cancer_wisconsin_diagnostic.csv",
            "Real public biomedical reference dataset; CC BY 4.0; not bundled-model validation.",
        ),
        (
            "metadata",
            "Verified Public Reference Catalogue",
            ROOT / "data" / "public_reference" / "verified_public_reference_catalog.csv",
            "Stable UniProt, NCBI Gene and RCSB PDB identifier references.",
        ),
        (
            "metadata",
            "Step 32 Public Reference Manifest",
            ROOT / "data" / "public_reference" / "verified_public_reference_manifest.json",
            "Checksum and scientific-scope manifest for public references.",
        ),
    ]
    inserted = 0
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        for asset_type, title, path, description in targets:
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT).as_posix()
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            asset_id = stable_id(asset_type, relative)
            connection.execute(
                """
                INSERT INTO research_assets(asset_id,asset_type,title,path,source,sha256,size_bytes,mime_type,status,description,metadata_json,created_at_utc,updated_at_utc)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(asset_id) DO UPDATE SET title=excluded.title,sha256=excluded.sha256,size_bytes=excluded.size_bytes,status=excluded.status,description=excluded.description,metadata_json=excluded.metadata_json,updated_at_utc=excluded.updated_at_utc
                """,
                (
                    asset_id,
                    asset_type,
                    title,
                    relative,
                    "BioIntel Step 32 foundation",
                    sha,
                    path.stat().st_size,
                    "application/octet-stream",
                    "active",
                    description,
                    json.dumps({"step": 32, "portable": True}),
                    timestamp,
                    timestamp,
                ),
            )
            inserted += 1
        connection.commit()
        databases = connection.execute(
            "SELECT COUNT(*) FROM research_assets WHERE asset_type='database'"
        ).fetchone()[0]
    return {"assets_synchronized": inserted, "database_assets": int(databases)}


def main() -> None:
    public = build_public_reference_catalog(ROOT)
    dataset_foundation = sync_physical_assets_and_issues()
    assets = sync_step32_assets()
    relationships = rebuild_relationship_registry(ROOT)
    output = ROOT / "reports" / "generated" / "step32_foundation_summary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "3.2.0",
        "milestone": "Step 32 Scientific UX & Performance",
        "public_reference": public.__dict__,
        "dataset_foundation": dataset_foundation,
        "assets": assets,
        "relationships": relationships.__dict__,
        "scientific_boundary": "Public reference data is separated from demo data and from model-release evidence.",
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
