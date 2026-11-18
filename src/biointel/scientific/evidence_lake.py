from __future__ import annotations

import hashlib
import json
import sqlite3
from biointel.database.core import managed_connect
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class EvidenceSnapshot:
    snapshot_id: str
    provider: str
    resource_type: str
    release: str
    retrieved_at: str
    source_url: str
    source_sha256: str
    record_count: int
    licence: str
    review_status: str
    metadata: dict[str, Any]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: bytes | str) -> str:
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


class ScientificEvidenceLake:
    """Normalized, provenance-first evidence store for public scientific records.

    This store deliberately separates provider authenticity, curator review and
    scientific release eligibility. A downloaded official record is authentic to
    the provider, but it is not automatically fit for a model release.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connection(self):
        connection = managed_connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS providers (
                    provider TEXT PRIMARY KEY,
                    official_host TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    licence TEXT NOT NULL,
                    api_url TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL REFERENCES providers(provider),
                    resource_type TEXT NOT NULL,
                    release TEXT NOT NULL,
                    retrieved_at TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    record_count INTEGER NOT NULL,
                    licence TEXT NOT NULL,
                    review_status TEXT NOT NULL CHECK(review_status IN ('pending','approved','rejected')),
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS evidence_records (
                    record_id TEXT PRIMARY KEY,
                    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id) ON DELETE CASCADE,
                    provider_record_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    organism TEXT,
                    taxonomy_id INTEGER,
                    assay_type TEXT,
                    target_id TEXT,
                    molecule_id TEXT,
                    publication_id TEXT,
                    clinical_trial_id TEXT,
                    structure_id TEXT,
                    value REAL,
                    unit TEXT,
                    relation TEXT,
                    confidence_score REAL,
                    record_sha256 TEXT NOT NULL,
                    review_status TEXT NOT NULL CHECK(review_status IN ('pending','approved','rejected')),
                    release_eligible INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL,
                    UNIQUE(snapshot_id, provider_record_id)
                );
                CREATE TABLE IF NOT EXISTS validation_studies (
                    study_id TEXT PRIMARY KEY,
                    study_type TEXT NOT NULL CHECK(study_type IN ('external','prospective','retrospective','benchmark')),
                    protocol_sha256 TEXT NOT NULL,
                    dataset_sha256 TEXT,
                    model_sha256 TEXT,
                    preregistered_at TEXT NOT NULL,
                    locked_at TEXT,
                    completed_at TEXT,
                    blinded INTEGER NOT NULL DEFAULT 0,
                    independent_site INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL CHECK(status IN ('draft','registered','locked','completed','reviewed')),
                    metrics_json TEXT NOT NULL DEFAULT '{}',
                    evidence_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS evidence_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    previous_hash TEXT,
                    event_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_records_provider ON evidence_records(snapshot_id, entity_type);
                CREATE INDEX IF NOT EXISTS idx_records_organism ON evidence_records(organism, taxonomy_id);
                CREATE INDEX IF NOT EXISTS idx_records_assay ON evidence_records(assay_type, unit);
                CREATE INDEX IF NOT EXISTS idx_records_release ON evidence_records(release_eligible, review_status);
                """
            )

    def register_provider(
        self,
        *,
        provider: str,
        official_host: str,
        resource_type: str,
        licence: str,
        api_url: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self.connection() as db:
            db.execute(
                """INSERT INTO providers(provider, official_host, resource_type, licence, api_url, metadata_json)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(provider) DO UPDATE SET
                     official_host=excluded.official_host,
                     resource_type=excluded.resource_type,
                     licence=excluded.licence,
                     api_url=excluded.api_url,
                     metadata_json=excluded.metadata_json""",
                (provider, official_host, resource_type, licence, api_url, _canonical_json(metadata or {})),
            )

    def import_snapshot(
        self,
        *,
        provider: str,
        resource_type: str,
        release: str,
        source_url: str,
        licence: str,
        records: Iterable[dict[str, Any]],
        retrieved_at: str | None = None,
        review_status: str = "pending",
        metadata: dict[str, Any] | None = None,
    ) -> EvidenceSnapshot:
        rows = [dict(item) for item in records]
        retrieved = retrieved_at or datetime.now(UTC).isoformat()
        raw = _canonical_json(rows)
        source_hash = _sha256(raw)
        snapshot_id = _sha256(f"{provider}|{release}|{source_hash}")[:24]
        snapshot = EvidenceSnapshot(
            snapshot_id=snapshot_id,
            provider=provider,
            resource_type=resource_type,
            release=release,
            retrieved_at=retrieved,
            source_url=source_url,
            source_sha256=source_hash,
            record_count=len(rows),
            licence=licence,
            review_status=review_status,
            metadata=metadata or {},
        )
        with self.connection() as db:
            db.execute(
                """INSERT OR REPLACE INTO snapshots
                   (snapshot_id, provider, resource_type, release, retrieved_at, source_url, source_sha256,
                    record_count, licence, review_status, metadata_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    snapshot.snapshot_id, provider, resource_type, release, retrieved, source_url,
                    source_hash, len(rows), licence, review_status, _canonical_json(metadata or {}),
                ),
            )
            for index, row in enumerate(rows):
                provider_record_id = str(row.get("provider_record_id") or row.get("record_id") or index)
                record_hash = _sha256(_canonical_json(row))
                record_id = _sha256(f"{snapshot_id}|{provider_record_id}")[:32]
                db.execute(
                    """INSERT OR REPLACE INTO evidence_records
                       (record_id, snapshot_id, provider_record_id, entity_type, organism, taxonomy_id,
                        assay_type, target_id, molecule_id, publication_id, clinical_trial_id, structure_id,
                        value, unit, relation, confidence_score, record_sha256, review_status,
                        release_eligible, payload_json)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        record_id, snapshot_id, provider_record_id, str(row.get("entity_type") or resource_type),
                        row.get("organism"), row.get("taxonomy_id"), row.get("assay_type"), row.get("target_id"),
                        row.get("molecule_id"), row.get("publication_id"), row.get("clinical_trial_id"),
                        row.get("structure_id"), row.get("value"), row.get("unit"), row.get("relation"),
                        row.get("confidence_score"), record_hash, str(row.get("review_status") or review_status),
                        int(bool(row.get("release_eligible", False))), _canonical_json(row),
                    ),
                )
        self.append_event("snapshot_imported", snapshot_id, "system", asdict(snapshot))
        return snapshot

    def append_event(self, event_type: str, subject_id: str, actor: str, payload: dict[str, Any]) -> str:
        with self.connection() as db:
            previous = db.execute("SELECT event_hash FROM evidence_events ORDER BY rowid DESC LIMIT 1").fetchone()
            previous_hash = str(previous[0]) if previous else ""
            occurred = datetime.now(UTC).isoformat()
            event_payload = _canonical_json(payload)
            event_hash = _sha256(f"{previous_hash}|{event_type}|{subject_id}|{occurred}|{actor}|{event_payload}")
            event_id = event_hash[:32]
            db.execute(
                "INSERT INTO evidence_events VALUES(?,?,?,?,?,?,?,?)",
                (event_id, event_type, subject_id, occurred, actor, previous_hash or None, event_hash, event_payload),
            )
            return event_id

    def register_validation_study(
        self, *, study_id: str, study_type: str, protocol: dict[str, Any], dataset_sha256: str | None,
        model_sha256: str | None, status: str, metrics: dict[str, Any] | None = None,
        evidence: dict[str, Any] | None = None, blinded: bool = False, independent_site: bool = False,
        completed_at: str | None = None,
    ) -> None:
        if study_type not in {"external", "prospective", "retrospective", "benchmark"}:
            raise ValueError("Unsupported validation study type.")
        protocol_hash = _sha256(_canonical_json(protocol))
        preregistered = str(protocol.get("preregistered_at") or datetime.now(UTC).isoformat())
        with self.connection() as db:
            db.execute(
                """INSERT OR REPLACE INTO validation_studies
                   (study_id, study_type, protocol_sha256, dataset_sha256, model_sha256, preregistered_at,
                    locked_at, completed_at, blinded, independent_site, status, metrics_json, evidence_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (study_id, study_type, protocol_hash, dataset_sha256, model_sha256, preregistered,
                 protocol.get("locked_at"), completed_at, int(blinded), int(independent_site), status,
                 _canonical_json(metrics or {}), _canonical_json(evidence or {})),
            )
        self.append_event("validation_study_registered", study_id, "system", {
            "study_type": study_type, "status": status, "independent_site": independent_site,
            "dataset_sha256": dataset_sha256, "model_sha256": model_sha256,
        })

    def summary(self) -> dict[str, Any]:
        with self.connection() as db:
            providers = db.execute("SELECT COUNT(*) FROM providers").fetchone()[0]
            snapshots = db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
            records = db.execute("SELECT COUNT(*) FROM evidence_records").fetchone()[0]
            organisms = db.execute("SELECT COUNT(DISTINCT taxonomy_id) FROM evidence_records WHERE taxonomy_id IS NOT NULL").fetchone()[0]
            assay_types = db.execute("SELECT COUNT(DISTINCT assay_type) FROM evidence_records WHERE assay_type IS NOT NULL AND assay_type!=''").fetchone()[0]
            clinical = db.execute("SELECT COUNT(*) FROM evidence_records WHERE clinical_trial_id IS NOT NULL OR entity_type LIKE 'clinical_%'").fetchone()[0]
            structures = db.execute("SELECT COUNT(*) FROM evidence_records WHERE structure_id IS NOT NULL").fetchone()[0]
            approved = db.execute("SELECT COUNT(*) FROM evidence_records WHERE review_status='approved'").fetchone()[0]
            release_eligible = db.execute("SELECT COUNT(*) FROM evidence_records WHERE release_eligible=1 AND review_status='approved'").fetchone()[0]
            validations = db.execute("SELECT COUNT(*) FROM validation_studies").fetchone()[0]
            reviewed_benchmarks = db.execute("SELECT COUNT(*) FROM validation_studies WHERE study_type='benchmark' AND status='reviewed'").fetchone()[0]
            external_completed = db.execute("SELECT COUNT(*) FROM validation_studies WHERE study_type='external' AND independent_site=1 AND status IN ('completed','reviewed')").fetchone()[0]
            prospective_completed = db.execute("SELECT COUNT(*) FROM validation_studies WHERE study_type='prospective' AND blinded=1 AND independent_site=1 AND status IN ('completed','reviewed')").fetchone()[0]
            dti_external_completed = db.execute("SELECT COUNT(*) FROM validation_studies WHERE study_id LIKE 'DTI-%' AND study_type='external' AND independent_site=1 AND status IN ('completed','reviewed')").fetchone()[0]
            dti_prospective_completed = db.execute("SELECT COUNT(*) FROM validation_studies WHERE study_id LIKE 'DTI-%' AND study_type='prospective' AND blinded=1 AND independent_site=1 AND status IN ('completed','reviewed')").fetchone()[0]
            independent = db.execute("SELECT COUNT(*) FROM validation_studies WHERE independent_site=1 AND status IN ('completed','reviewed')").fetchone()[0]
        return {
            "providers": int(providers), "snapshots": int(snapshots), "records": int(records),
            "organisms": int(organisms), "assay_types": int(assay_types), "clinical_records": int(clinical),
            "structure_records": int(structures), "approved_records": int(approved), "release_eligible_records": int(release_eligible),
            "validation_studies": int(validations), "reviewed_benchmarks": int(reviewed_benchmarks),
            "external_completed_studies": int(external_completed), "prospective_completed_studies": int(prospective_completed),
            "dti_external_completed_studies": int(dti_external_completed), "dti_prospective_completed_studies": int(dti_prospective_completed),
            "independent_completed_studies": int(independent),
        }

    def verify_integrity(self) -> dict[str, Any]:
        errors: list[str] = []
        previous = ""
        with self.connection() as db:
            fk = db.execute("PRAGMA foreign_key_check").fetchall()
            errors.extend([f"foreign_key:{tuple(row)}" for row in fk])
            for row in db.execute("SELECT * FROM evidence_events ORDER BY rowid"):
                expected = _sha256(
                    f"{previous}|{row['event_type']}|{row['subject_id']}|{row['occurred_at']}|{row['actor']}|{row['payload_json']}"
                )
                if expected != row["event_hash"]:
                    errors.append(f"event_hash:{row['event_id']}")
                previous = row["event_hash"]
            for row in db.execute("SELECT record_id, record_sha256, payload_json FROM evidence_records"):
                if _sha256(row["payload_json"]) != row["record_sha256"]:
                    errors.append(f"record_hash:{row['record_id']}")
        return {"ok": not errors, "errors": errors}
