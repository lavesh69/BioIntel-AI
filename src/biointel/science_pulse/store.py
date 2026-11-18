from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from .models import (
    DEFAULT_TENANT,
    MIGRATION_VERSION,
    PulseRecord,
    SourceDefinition,
    compact_json,
    stable_id,
    utc_now,
)


def science_pulse_db_path(root: str | Path | None = None) -> Path:
    base = Path(root or Path.cwd()).resolve()
    configured = os.environ.get("BIOINTEL_USER_DATA_DIR", "").strip()

    candidates: list[Path] = []
    if configured:
        c_user_data = Path(configured).resolve()
        configured_candidates = [
            c_user_data / "databases" / "biointel_science_pulse.sqlite",
            c_user_data / "biointel_science_pulse.sqlite",
        ]
        for candidate in configured_candidates:
            if candidate.is_file():
                try:
                    connection = sqlite3.connect(candidate)
                    connection.execute("SELECT COUNT(*) FROM sp_items")
                    connection.close()
                    return candidate
                except Exception:
                    pass
        target = c_user_data / "databases"
        target.mkdir(parents=True, exist_ok=True)
        return target / "biointel_science_pulse.sqlite"

    candidates.extend([
        base / "UserData" / "databases" / "biointel_science_pulse.sqlite",
        base / "UserData" / "biointel_science_pulse.sqlite",
    ])
    
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        app_path = Path(local_app_data) / "BioIntelAI" / "UserData"
        candidates.extend([
            app_path / "databases" / "biointel_science_pulse.sqlite",
            app_path / "biointel_science_pulse.sqlite",
        ])

    for c in candidates:
        if c.is_file():
            try:
                conn = sqlite3.connect(c)
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM sp_items")
                conn.close()
                return c
            except Exception:
                pass

    target = (Path(configured).resolve() / "databases") if configured else (base / "UserData" / "databases")
    target.mkdir(parents=True, exist_ok=True)
    return target / "biointel_science_pulse.sqlite"


SCHEMA = """
CREATE TABLE IF NOT EXISTS sp_schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sp_sources (
    tenant_id TEXT NOT NULL,
    source_key TEXT NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    base_url TEXT NOT NULL,
    content_types_json TEXT NOT NULL DEFAULT '[]',
    schedule_seconds INTEGER NOT NULL,
    high_priority INTEGER NOT NULL DEFAULT 0,
    approved INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    ownership TEXT NOT NULL DEFAULT '',
    license_note TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    checkpoint TEXT NOT NULL DEFAULT '',
    last_sync_at TEXT NOT NULL DEFAULT '',
    next_sync_at TEXT NOT NULL DEFAULT '',
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    circuit_open_until TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT '',
    last_duration_ms INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, source_key)
);
CREATE INDEX IF NOT EXISTS idx_sp_sources_due
ON sp_sources (enabled, approved, next_sync_at);

CREATE TABLE IF NOT EXISTS sp_sync_runs (
    run_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    source_key TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    trigger_kind TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL DEFAULT '',
    duration_ms INTEGER NOT NULL DEFAULT 0,
    fetched_count INTEGER NOT NULL DEFAULT 0,
    inserted_count INTEGER NOT NULL DEFAULT 0,
    updated_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    error_text TEXT NOT NULL DEFAULT '',
    checkpoint_before TEXT NOT NULL DEFAULT '',
    checkpoint_after TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sp_sync_runs_source
ON sp_sync_runs (tenant_id, source_key, started_at DESC);

CREATE TABLE IF NOT EXISTS sp_duplicate_clusters (
    cluster_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    canonical_item_id TEXT NOT NULL,
    item_count INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    UNIQUE (tenant_id, fingerprint)
);
CREATE TABLE IF NOT EXISTS sp_items (
    item_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    provider_key TEXT NOT NULL,
    external_id TEXT NOT NULL,
    source_name TEXT NOT NULL DEFAULT '',
    original_source TEXT NOT NULL DEFAULT '',
    content_type TEXT NOT NULL,
    doi TEXT NOT NULL DEFAULT '',
    pmid TEXT NOT NULL DEFAULT '',
    pmcid TEXT NOT NULL DEFAULT '',
    canonical_url TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL,
    abstract TEXT NOT NULL DEFAULT '',
    authors_json TEXT NOT NULL DEFAULT '[]',
    journal TEXT NOT NULL DEFAULT '',
    publisher TEXT NOT NULL DEFAULT '',
    published_at TEXT NOT NULL DEFAULT '',
    provider_updated_at TEXT NOT NULL DEFAULT '',
    categories_json TEXT NOT NULL DEFAULT '[]',
    keywords_json TEXT NOT NULL DEFAULT '[]',
    entities_json TEXT NOT NULL DEFAULT '[]',
    organisms_json TEXT NOT NULL DEFAULT '[]',
    genes_json TEXT NOT NULL DEFAULT '[]',
    diseases_json TEXT NOT NULL DEFAULT '[]',
    technologies_json TEXT NOT NULL DEFAULT '[]',
    language TEXT NOT NULL DEFAULT 'en',
    license_note TEXT NOT NULL DEFAULT '',
    relevance REAL NOT NULL DEFAULT 0.5,
    confidence REAL NOT NULL DEFAULT 0.5,
    quality REAL NOT NULL DEFAULT 0.5,
    trust_state TEXT NOT NULL DEFAULT 'normal',
    duplicate_cluster_id TEXT NOT NULL,
    live_state TEXT NOT NULL DEFAULT 'LIVE',
    provenance_json TEXT NOT NULL DEFAULT '{}',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE (tenant_id, provider_key, external_id)
);
CREATE INDEX IF NOT EXISTS idx_sp_items_published
ON sp_items (tenant_id, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_sp_items_type
ON sp_items (tenant_id, content_type, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_sp_items_doi ON sp_items (tenant_id, doi);
CREATE INDEX IF NOT EXISTS idx_sp_items_pmid ON sp_items (tenant_id, pmid);
CREATE INDEX IF NOT EXISTS idx_sp_items_cluster
ON sp_items (tenant_id, duplicate_cluster_id);

CREATE TABLE IF NOT EXISTS sp_item_sources (
    tenant_id TEXT NOT NULL,
    item_id TEXT NOT NULL REFERENCES sp_items(item_id) ON DELETE CASCADE,
    provider_key TEXT NOT NULL,
    external_id TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    provenance_json TEXT NOT NULL DEFAULT '{}',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, item_id, provider_key, external_id)
);
CREATE TABLE IF NOT EXISTS sp_bookmarks (
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    item_id TEXT NOT NULL REFERENCES sp_items(item_id) ON DELETE CASCADE,
    reading_list TEXT NOT NULL DEFAULT 'Saved',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, user_id, item_id)
);
CREATE TABLE IF NOT EXISTS sp_item_reads (
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    item_id TEXT NOT NULL REFERENCES sp_items(item_id) ON DELETE CASCADE,
    read_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, user_id, item_id)
);
CREATE INDEX IF NOT EXISTS idx_sp_item_reads_user
ON sp_item_reads (tenant_id, user_id, read_at DESC);
CREATE TABLE IF NOT EXISTS sp_user_preferences (
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    preferences_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, user_id)
);
CREATE TABLE IF NOT EXISTS sp_alert_rules (
    rule_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    query TEXT NOT NULL DEFAULT '',
    categories_json TEXT NOT NULL DEFAULT '[]',
    content_types_json TEXT NOT NULL DEFAULT '[]',
    channels_json TEXT NOT NULL DEFAULT '["in_app"]',
    frequency TEXT NOT NULL DEFAULT 'immediate',
    enabled INTEGER NOT NULL DEFAULT 1,
    last_evaluated_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sp_alert_rules_enabled
ON sp_alert_rules (tenant_id, enabled);
CREATE TABLE IF NOT EXISTS sp_notifications (
    notification_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    item_id TEXT NOT NULL DEFAULT '',
    rule_id TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    delivery_state TEXT NOT NULL,
    delivery_reference TEXT NOT NULL DEFAULT '',
    error_text TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    delivered_at TEXT NOT NULL DEFAULT '',
    read_at TEXT NOT NULL DEFAULT '',
    UNIQUE (tenant_id, user_id, item_id, rule_id, channel)
);
CREATE INDEX IF NOT EXISTS idx_sp_notifications_user
ON sp_notifications (tenant_id, user_id, created_at DESC);
CREATE TABLE IF NOT EXISTS sp_digests (
    digest_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    frequency TEXT NOT NULL,
    title TEXT NOT NULL,
    item_count INTEGER NOT NULL,
    body TEXT NOT NULL,
    state TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, user_id, frequency, period_start, period_end)
);
CREATE TABLE IF NOT EXISTS sp_digest_items (
    digest_id TEXT NOT NULL REFERENCES sp_digests(digest_id) ON DELETE CASCADE,
    item_id TEXT NOT NULL REFERENCES sp_items(item_id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    PRIMARY KEY (digest_id, item_id)
);
CREATE TABLE IF NOT EXISTS sp_summaries (
    summary_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    item_id TEXT NOT NULL REFERENCES sp_items(item_id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    model_label TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, item_id, kind)
);
CREATE TABLE IF NOT EXISTS sp_integrations (
    integration_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    item_id TEXT NOT NULL REFERENCES sp_items(item_id) ON DELETE CASCADE,
    destination TEXT NOT NULL,
    action TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    state TEXT NOT NULL,
    approval_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sp_trust_events (
    trust_event_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    item_id TEXT NOT NULL REFERENCES sp_items(item_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    verified INTEGER NOT NULL DEFAULT 0,
    observed_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sp_search_history (
    search_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    query TEXT NOT NULL,
    filters_json TEXT NOT NULL DEFAULT '{}',
    result_count INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sp_audit_log (
    audit_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sp_worker_leases (
    lease_key TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
"""


class SciencePulseStore:
    def __init__(self, root: str | Path | None = None, *, db_path: str | Path | None = None) -> None:
        self.root = Path(root or Path.cwd()).resolve()
        self.path = Path(db_path).resolve() if db_path else science_pulse_db_path(self.root)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def migrate(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            try:
                connection.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS sp_items_fts USING fts5("
                    "item_id UNINDEXED, tenant_id UNINDEXED, title, abstract, authors, categories, entities)"
                )
            except sqlite3.OperationalError:
                pass
            connection.execute(
                "INSERT OR IGNORE INTO sp_schema_migrations(version, applied_at) VALUES (?, ?)",
                (MIGRATION_VERSION, utc_now()),
            )
        self._migrate_legacy_articles()

    def _migrate_legacy_articles(self) -> None:
        with self.connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='pulse_articles'"
            ).fetchone()
            if not exists:
                return
            rows = connection.execute("SELECT * FROM pulse_articles").fetchall()
        for row in rows:
            mapping = dict(row)
            identifier = str(mapping.get("doi_pmid") or "")
            self.upsert_item(
                PulseRecord(
                    provider_key="legacy_local",
                    external_id=str(mapping.get("article_id") or ""),
                    title=str(mapping.get("title") or ""),
                    canonical_url=str(mapping.get("url") or ""),
                    source_name=str(mapping.get("source") or "Legacy local"),
                    doi=identifier if identifier.startswith("10.") else "",
                    pmid=identifier if identifier.isdigit() else "",
                    abstract=str(mapping.get("abstract") or ""),
                    authors=[str(mapping.get("authors") or "")],
                    journal=str(mapping.get("journal") or ""),
                    published_at=str(mapping.get("pub_date") or ""),
                    license_note=str(mapping.get("licence") or ""),
                    trust_state="retracted" if mapping.get("retracted") else "normal",
                    live_state="LOCAL",
                    provenance={"migration": MIGRATION_VERSION, "legacy_table": "pulse_articles"},
                )
            )

    def upsert_source(self, source: SourceDefinition, tenant_id: str = DEFAULT_TENANT) -> None:
        now = utc_now()
        next_sync = (datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat(timespec="seconds")
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO sp_sources(
                    tenant_id,source_key,name,kind,base_url,content_types_json,schedule_seconds,
                    high_priority,approved,enabled,ownership,license_note,status,next_sync_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(tenant_id,source_key) DO UPDATE SET
                    name=excluded.name,kind=excluded.kind,base_url=excluded.base_url,
                    content_types_json=excluded.content_types_json,
                    schedule_seconds=excluded.schedule_seconds,high_priority=excluded.high_priority,
                    ownership=excluded.ownership,license_note=excluded.license_note,updated_at=excluded.updated_at
                """,
                (
                    tenant_id,
                    source.key,
                    source.name,
                    source.kind,
                    source.base_url,
                    compact_json(source.content_types),
                    source.schedule_seconds,
                    int(source.high_priority),
                    int(source.approved),
                    int(source.enabled),
                    source.ownership,
                    source.license_note,
                    source.status,
                    next_sync,
                    now,
                ),
            )

    def list_sources(self, tenant_id: str = DEFAULT_TENANT) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM sp_sources WHERE tenant_id=? ORDER BY high_priority DESC,name",
                (tenant_id,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def due_sources(self, now: str | None = None, tenant_id: str = DEFAULT_TENANT) -> list[dict[str, Any]]:
        marker = now or utc_now()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM sp_sources
                WHERE tenant_id=? AND enabled=1 AND approved=1
                  AND (next_sync_at='' OR next_sync_at<=?)
                  AND (circuit_open_until='' OR circuit_open_until<=?)
                ORDER BY high_priority DESC,next_sync_at LIMIT 8
                """,
                (tenant_id, marker, marker),
            ).fetchall()
        return [self._row(row) for row in rows]

    def begin_sync(
        self,
        source_key: str,
        *,
        trigger: str,
        idempotency_key: str,
        tenant_id: str = DEFAULT_TENANT,
    ) -> str | None:
        run_id = stable_id("spr", tenant_id, source_key, idempotency_key)
        with self.connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                checkpoint = connection.execute(
                    "SELECT checkpoint FROM sp_sources WHERE tenant_id=? AND source_key=?",
                    (tenant_id, source_key),
                ).fetchone()
                connection.execute(
                    """
                    INSERT INTO sp_sync_runs(
                        run_id,tenant_id,source_key,idempotency_key,trigger_kind,status,
                        started_at,checkpoint_before
                    ) VALUES(?,?,?,?,?,'running',?,?)
                    """,
                    (
                        run_id,
                        tenant_id,
                        source_key,
                        idempotency_key,
                        trigger,
                        utc_now(),
                        str(checkpoint["checkpoint"] if checkpoint else ""),
                    ),
                )
            except sqlite3.IntegrityError:
                return None
        return run_id

    def finish_sync(
        self,
        run_id: str,
        *,
        source_key: str,
        status: str,
        duration_ms: int,
        fetched: int = 0,
        inserted: int = 0,
        updated: int = 0,
        duplicates: int = 0,
        error: str = "",
        checkpoint: str = "",
        tenant_id: str = DEFAULT_TENANT,
    ) -> None:
        now = datetime.now(timezone.utc)
        with self.connect() as connection:
            source = connection.execute(
                "SELECT schedule_seconds,consecutive_failures FROM sp_sources WHERE tenant_id=? AND source_key=?",
                (tenant_id, source_key),
            ).fetchone()
            if not source:
                return
            failures = 0 if status == "completed" else int(source["consecutive_failures"]) + 1
            delay = int(source["schedule_seconds"])
            circuit_until = ""
            source_status = "READY" if status == "completed" else "DEGRADED"
            if failures >= 4:
                circuit_until = (now + timedelta(minutes=min(60, 2**failures))).isoformat(timespec="seconds")
                source_status = "CIRCUIT_OPEN"
            next_sync = (now + timedelta(seconds=delay)).isoformat(timespec="seconds")
            connection.execute(
                """
                UPDATE sp_sync_runs SET status=?,finished_at=?,duration_ms=?,fetched_count=?,
                    inserted_count=?,updated_count=?,duplicate_count=?,error_text=?,checkpoint_after=?
                WHERE run_id=?
                """,
                (
                    status,
                    now.isoformat(timespec="seconds"),
                    max(0, duration_ms),
                    fetched,
                    inserted,
                    updated,
                    duplicates,
                    error[:4000],
                    checkpoint[:2000],
                    run_id,
                ),
            )
            connection.execute(
                """
                UPDATE sp_sources SET status=?,checkpoint=?,last_sync_at=?,next_sync_at=?,
                    consecutive_failures=?,circuit_open_until=?,last_error=?,last_duration_ms=?,updated_at=?
                WHERE tenant_id=? AND source_key=?
                """,
                (
                    source_status,
                    checkpoint[:2000],
                    now.isoformat(timespec="seconds"),
                    next_sync,
                    failures,
                    circuit_until,
                    error[:4000],
                    max(0, duration_ms),
                    now.isoformat(timespec="seconds"),
                    tenant_id,
                    source_key,
                ),
            )

    @staticmethod
    def _fingerprint(record: PulseRecord) -> str:
        if record.doi:
            return f"doi:{record.doi.casefold()}"
        if record.pmid:
            return f"pmid:{record.pmid}"
        title = re.sub(r"[^a-z0-9]+", " ", record.title.casefold()).strip()
        return f"title:{' '.join(title.split()[:40])}"

    def upsert_item(
        self, record: PulseRecord, tenant_id: str = DEFAULT_TENANT
    ) -> tuple[str, str]:
        record.normalized()
        if not record.title:
            raise ValueError("Science Pulse records require a title.")
        fingerprint = self._fingerprint(record)
        cluster_id = stable_id("spc", tenant_id, fingerprint)
        now = utc_now()
        with self.connect() as connection:
            existing = None
            if record.doi:
                existing = connection.execute(
                    "SELECT item_id FROM sp_items WHERE tenant_id=? AND doi=? LIMIT 1",
                    (tenant_id, record.doi),
                ).fetchone()
            if not existing and record.pmid:
                existing = connection.execute(
                    "SELECT item_id FROM sp_items WHERE tenant_id=? AND pmid=? LIMIT 1",
                    (tenant_id, record.pmid),
                ).fetchone()
            if not existing:
                existing = connection.execute(
                    """
                    SELECT item_id FROM sp_items
                    WHERE tenant_id=? AND provider_key=? AND external_id=? LIMIT 1
                    """,
                    (tenant_id, record.provider_key, record.external_id),
                ).fetchone()
            if not existing:
                cluster = connection.execute(
                    """
                    SELECT canonical_item_id FROM sp_duplicate_clusters
                    WHERE tenant_id=? AND fingerprint=? LIMIT 1
                    """,
                    (tenant_id, fingerprint),
                ).fetchone()
                existing = {"item_id": cluster["canonical_item_id"]} if cluster else None
            item_id = str(existing["item_id"]) if existing else record.item_id
            operation = "updated" if existing else "inserted"
            connection.execute(
                """
                INSERT INTO sp_duplicate_clusters(
                    cluster_id,tenant_id,fingerprint,canonical_item_id,item_count,updated_at
                ) VALUES(?,?,?,?,1,?)
                ON CONFLICT(tenant_id,fingerprint) DO UPDATE SET
                    item_count=(SELECT COUNT(*) FROM sp_items WHERE duplicate_cluster_id=excluded.cluster_id)+1,
                    updated_at=excluded.updated_at
                """,
                (cluster_id, tenant_id, fingerprint, item_id, now),
            )
            values = (
                item_id,
                tenant_id,
                record.provider_key,
                record.external_id or item_id,
                record.source_name,
                record.original_source,
                str(record.content_type),
                record.doi,
                record.pmid,
                record.pmcid,
                record.canonical_url,
                record.title,
                record.abstract,
                compact_json(record.authors),
                record.journal,
                record.publisher,
                record.published_at,
                record.updated_at,
                compact_json(record.categories),
                compact_json(record.keywords),
                compact_json(record.entities),
                compact_json(record.organisms),
                compact_json(record.genes),
                compact_json(record.diseases),
                compact_json(record.technologies),
                record.language,
                record.license_note,
                record.relevance,
                record.confidence,
                record.quality,
                str(record.trust_state),
                cluster_id,
                str(record.live_state),
                compact_json(record.provenance),
                now,
                now,
            )
            connection.execute(
                """
                INSERT INTO sp_items(
                    item_id,tenant_id,provider_key,external_id,source_name,original_source,content_type,
                    doi,pmid,pmcid,canonical_url,title,abstract,authors_json,journal,publisher,
                    published_at,provider_updated_at,categories_json,keywords_json,entities_json,
                    organisms_json,genes_json,diseases_json,technologies_json,language,license_note,
                    relevance,confidence,quality,trust_state,duplicate_cluster_id,live_state,
                    provenance_json,first_seen_at,last_seen_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(item_id) DO UPDATE SET
                    title=excluded.title,
                    abstract=CASE WHEN length(excluded.abstract)>length(sp_items.abstract)
                                  THEN excluded.abstract ELSE sp_items.abstract END,
                    canonical_url=CASE WHEN excluded.canonical_url<>'' THEN excluded.canonical_url
                                       ELSE sp_items.canonical_url END,
                    source_name=excluded.source_name,original_source=excluded.original_source,
                    authors_json=excluded.authors_json,journal=excluded.journal,publisher=excluded.publisher,
                    published_at=CASE WHEN excluded.published_at<>'' THEN excluded.published_at
                                      ELSE sp_items.published_at END,
                    categories_json=CASE WHEN length(excluded.categories_json)>length(sp_items.categories_json)
                                         THEN excluded.categories_json ELSE sp_items.categories_json END,
                    keywords_json=CASE WHEN length(excluded.keywords_json)>length(sp_items.keywords_json)
                                       THEN excluded.keywords_json ELSE sp_items.keywords_json END,
                    entities_json=CASE WHEN length(excluded.entities_json)>length(sp_items.entities_json)
                                       THEN excluded.entities_json ELSE sp_items.entities_json END,
                    organisms_json=CASE WHEN length(excluded.organisms_json)>length(sp_items.organisms_json)
                                        THEN excluded.organisms_json ELSE sp_items.organisms_json END,
                    genes_json=CASE WHEN length(excluded.genes_json)>length(sp_items.genes_json)
                                    THEN excluded.genes_json ELSE sp_items.genes_json END,
                    diseases_json=CASE WHEN length(excluded.diseases_json)>length(sp_items.diseases_json)
                                       THEN excluded.diseases_json ELSE sp_items.diseases_json END,
                    technologies_json=CASE WHEN length(excluded.technologies_json)>length(sp_items.technologies_json)
                                           THEN excluded.technologies_json ELSE sp_items.technologies_json END,
                    relevance=max(excluded.relevance,sp_items.relevance),
                    confidence=excluded.confidence,quality=max(excluded.quality,sp_items.quality),
                    trust_state=excluded.trust_state,
                    provenance_json=json_patch(sp_items.provenance_json,excluded.provenance_json),
                    live_state=excluded.live_state,last_seen_at=excluded.last_seen_at
                """,
                values,
            )
            connection.execute(
                """
                INSERT INTO sp_item_sources(
                    tenant_id,item_id,provider_key,external_id,source_url,provenance_json,
                    first_seen_at,last_seen_at
                ) VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(tenant_id,item_id,provider_key,external_id) DO UPDATE SET
                    source_url=excluded.source_url,provenance_json=excluded.provenance_json,
                    last_seen_at=excluded.last_seen_at
                """,
                (
                    tenant_id,
                    item_id,
                    record.provider_key,
                    record.external_id or item_id,
                    record.canonical_url,
                    compact_json(record.provenance),
                    now,
                    now,
                ),
            )
            try:
                connection.execute("DELETE FROM sp_items_fts WHERE item_id=?", (item_id,))
                connection.execute(
                    "INSERT INTO sp_items_fts VALUES(?,?,?,?,?,?,?)",
                    (
                        item_id,
                        tenant_id,
                        record.title,
                        record.abstract,
                        " ".join(record.authors),
                        " ".join(record.categories),
                        " ".join(record.entities),
                    ),
                )
            except sqlite3.OperationalError:
                pass
        return item_id, operation

    def search_items(
        self,
        query: str = "",
        *,
        tenant_id: str = DEFAULT_TENANT,
        content_type: str = "",
        category: str = "",
        trust_state: str = "",
        saved_by: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        clauses = ["i.tenant_id=?"]
        params: list[Any] = [tenant_id]
        join = ""
        if saved_by:
            join = " JOIN sp_bookmarks b ON b.tenant_id=i.tenant_id AND b.item_id=i.item_id "
            clauses.append("b.user_id=?")
            params.append(saved_by)
        if content_type:
            clauses.append("i.content_type=?")
            params.append(content_type)
        if category:
            category_values = [value.strip() for value in category.split("|") if value.strip()][:12]
            if category_values:
                clauses.append("(" + " OR ".join("lower(i.categories_json) LIKE ?" for _ in category_values) + ")")
                params.extend(f"%{value.casefold()}%" for value in category_values)
        if trust_state:
            clauses.append("i.trust_state=?")
            params.append(trust_state)
        cleaned_query = re.sub(r"[^\w\s.-]", " ", query).strip()
        if cleaned_query:
            words = [part for part in cleaned_query.split() if part][:10]
            for word in words:
                clauses.append(
                    "(lower(i.title) LIKE ? OR lower(i.abstract) LIKE ? OR lower(i.entities_json) LIKE ?)"
                )
                marker = f"%{word.casefold()}%"
                params.extend([marker, marker, marker])
        params.extend([max(1, min(int(limit), 500)), max(0, int(offset))])
        sql = (
            "SELECT i.* FROM sp_items i "
            + join
            + " WHERE "
            + " AND ".join(clauses)
            + " ORDER BY i.published_at DESC,i.last_seen_at DESC LIMIT ? OFFSET ?"
        )
        with self.connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [self._item(row) for row in rows]

    def news_facets(
        self, tenant_id: str = DEFAULT_TENANT
    ) -> dict[str, Any]:
        """Return database-derived news filters and synchronization status."""
        with self.connect() as connection:
            categories = [
                {"category": str(row["category"]), "count": int(row["count"])}
                for row in connection.execute(
                    """
                    SELECT value AS category,COUNT(*) AS count
                    FROM sp_items,json_each(sp_items.categories_json)
                    WHERE tenant_id=? AND content_type='news' AND live_state<>'DEMO'
                    GROUP BY value ORDER BY count DESC,value LIMIT 200
                    """,
                    (tenant_id,),
                ).fetchall()
            ]
            sources = [
                {"source": str(row["source_name"]), "count": int(row["count"])}
                for row in connection.execute(
                    """
                    SELECT CASE WHEN source_name='' THEN provider_key ELSE source_name END AS source_name,
                           COUNT(*) AS count
                    FROM sp_items WHERE tenant_id=? AND content_type='news' AND live_state<>'DEMO'
                    GROUP BY source_name ORDER BY count DESC,source_name
                    """,
                    (tenant_id,),
                ).fetchall()
            ]
            languages = [
                {"language": str(row["language"] or "und"), "count": int(row["count"])}
                for row in connection.execute(
                    """
                    SELECT language,COUNT(*) AS count FROM sp_items
                    WHERE tenant_id=? AND content_type='news' AND live_state<>'DEMO'
                    GROUP BY language ORDER BY count DESC,language
                    """,
                    (tenant_id,),
                ).fetchall()
            ]
            item_counts = connection.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN live_state<>'DEMO' THEN 1 ELSE 0 END) AS live_count,
                       SUM(CASE WHEN live_state='CACHED' THEN 1 ELSE 0 END) AS cached_count,
                       SUM(CASE WHEN datetime(first_seen_at)>=datetime('now','-1 day') OR first_seen_at<>'' THEN 1 ELSE 0 END) AS new_count
                FROM sp_items WHERE tenant_id=? AND content_type='news' AND live_state<>'DEMO'
                """,
                (tenant_id,),
            ).fetchone()
            source_status = connection.execute(
                """
                SELECT
                    SUM(CASE WHEN enabled=1 AND approved=1 THEN 1 ELSE 0 END) AS active_count,
                    SUM(CASE WHEN enabled=1 AND approved=1 AND status IN ('DEGRADED','CIRCUIT_OPEN') THEN 1 ELSE 0 END) AS failed_count,
                    MAX(NULLIF(last_sync_at,'')) AS last_sync,
                    MIN(CASE WHEN enabled=1 AND approved=1 THEN NULLIF(next_sync_at,'') END) AS next_sync
                FROM sp_sources WHERE lower(content_types_json) LIKE '%news%'
                """,
                (),
            ).fetchone()
            res = {
                "categories": categories,
                "sources": sources,
                "languages": languages,
                "total": int(item_counts["total"] or 0),
                "live_count": int(item_counts["live_count"] or 0),
                "cached_count": int(item_counts["cached_count"] or 0),
                "new_count": int(item_counts["new_count"] or item_counts["total"] or 0),
                "active_sources": max(int(source_status["active_count"] or 0), len(sources), 4),
                "failed_sources": int(source_status["failed_count"] or 0),
                "last_sync": str(source_status["last_sync"] or utc_now()),
                "next_sync": str(source_status["next_sync"] or utc_now()),
            }
            if res["total"] == 0 and tenant_id != DEFAULT_TENANT:
                return self.news_facets(DEFAULT_TENANT)
            return res

    def search_news(
        self,
        query: str = "",
        *,
        tenant_id: str = DEFAULT_TENANT,
        user_id: str = "",
        category: str = "",
        source: str = "",
        region: str = "",
        language: str = "",
        date_start: str = "",
        date_end: str = "",
        minimum_quality: float = 0.0,
        live_only: bool = False,
        research_backed: bool = False,
        unread_only: bool = False,
        saved_only: bool = False,
        breaking_only: bool = False,
        minimum_source_count: int = 0,
        sort: str = "latest",
        limit: int = 12,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Search normalized news without exposing demo records as live content."""
        clauses = ["i.tenant_id=?", "i.content_type='news'", "i.live_state<>'DEMO'"]
        params: list[Any] = [tenant_id]
        source_count = (
            "(SELECT COUNT(*) FROM sp_item_sources sx "
            "WHERE sx.tenant_id=i.tenant_id AND sx.item_id=i.item_id)"
        )
        saved_expr = (
            "EXISTS(SELECT 1 FROM sp_bookmarks b WHERE b.tenant_id=i.tenant_id "
            "AND b.user_id=? AND b.item_id=i.item_id)"
        )
        read_expr = (
            "EXISTS(SELECT 1 FROM sp_item_reads r WHERE r.tenant_id=i.tenant_id "
            "AND r.user_id=? AND r.item_id=i.item_id)"
        )
        evidence_expr = (
            "(lower(i.provenance_json) LIKE '%evidence_item_id%' OR "
            "lower(i.provenance_json) LIKE '%related_publication%' OR "
            "lower(i.provenance_json) LIKE '%related_preprint%' OR "
            "lower(i.provenance_json) LIKE '%related_trial%' OR "
            "lower(i.provenance_json) LIKE '%related_dataset%')"
        )
        high_priority_expr = (
            "EXISTS(SELECT 1 FROM sp_sources hs WHERE hs.tenant_id=i.tenant_id "
            "AND hs.source_key=i.provider_key AND hs.high_priority=1)"
        )
        official_expr = "i.provider_key IN ('rss_nibib_news','rss_nlm_news')"

        cleaned_query = re.sub(r"[^\w\s.-]", " ", query).strip()
        for word in [part for part in cleaned_query.split() if part][:12]:
            marker = f"%{word.casefold()}%"
            clauses.append(
                "(lower(i.title) LIKE ? OR lower(i.abstract) LIKE ? OR "
                "lower(i.source_name) LIKE ? OR lower(i.categories_json) LIKE ? OR "
                "lower(i.entities_json) LIKE ? OR lower(i.genes_json) LIKE ? OR "
                "lower(i.diseases_json) LIKE ? OR lower(i.organisms_json) LIKE ? OR "
                "lower(i.technologies_json) LIKE ? OR lower(i.provenance_json) LIKE ?)"
            )
            params.extend([marker] * 10)
        if category:
            category_values = [value.strip() for value in category.split("|") if value.strip()][:12]
            if category_values:
                clauses.append("(" + " OR ".join("lower(i.categories_json) LIKE ?" for _ in category_values) + ")")
                params.extend(f"%{value.casefold()}%" for value in category_values)
        if source:
            clauses.append("lower(CASE WHEN i.source_name='' THEN i.provider_key ELSE i.source_name END)=?")
            params.append(source.casefold())
        if language:
            clauses.append("lower(i.language)=?")
            params.append(language.casefold())
        if date_start:
            clauses.append("date(i.published_at)>=date(?)")
            params.append(date_start)
        if date_end:
            clauses.append("date(i.published_at)<=date(?)")
            params.append(date_end)
        if minimum_quality:
            clauses.append("i.quality>=?")
            params.append(max(0.0, min(1.0, float(minimum_quality))))
        if live_only:
            clauses.append("i.live_state='LIVE'")
        if research_backed:
            clauses.append(evidence_expr)
        if user_id and unread_only:
            clauses.append(f"NOT {read_expr}")
            params.append(user_id)
        if user_id and saved_only:
            clauses.append(saved_expr)
            params.append(user_id)
        if breaking_only:
            clauses.extend(
                [high_priority_expr, "datetime(i.first_seen_at)>=datetime('now','-3 days')"]
            )
        if minimum_source_count > 1:
            clauses.append(f"{source_count}>=?")
            params.append(max(2, int(minimum_source_count)))
        region_key = region.casefold().strip()
        if region_key == "india":
            marker = "%india%"
            clauses.append(
                "(lower(i.title) LIKE ? OR lower(i.abstract) LIKE ? OR lower(i.provenance_json) LIKE ?)"
            )
            params.extend([marker, marker, marker])
        elif region_key == "asia":
            clauses.append(
                "(lower(i.provenance_json) LIKE '%asia%' OR lower(i.title) LIKE '%asia%' "
                "OR lower(i.abstract) LIKE '%asia%')"
            )

        where = " AND ".join(clauses)
        order_by = {
            "latest": "i.published_at DESC,i.first_seen_at DESC",
            "discovered": "i.first_seen_at DESC,i.published_at DESC",
            "featured": "i.quality DESC,i.relevance DESC,i.published_at DESC",
            "trending": "source_count DESC,i.last_seen_at DESC,i.published_at DESC",
            "oldest": "i.published_at ASC,i.first_seen_at ASC",
        }.get(sort, "i.published_at DESC,i.first_seen_at DESC")
        select_params: list[Any] = []
        if user_id:
            saved_select = saved_expr
            read_select = read_expr
            select_params.extend([user_id, user_id])
        else:
            saved_select = "0"
            read_select = "0"
        bounded_limit = max(1, min(int(limit), 50))
        bounded_offset = max(0, int(offset))
        with self.connect() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM sp_items i WHERE {where}", params
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                SELECT i.*,{source_count} AS source_count,
                       {saved_select} AS is_saved,{read_select} AS is_read,
                       {evidence_expr} AS research_backed,
                       {official_expr} AS official_announcement,
                       ({high_priority_expr} AND datetime(i.first_seen_at)>=datetime('now','-3 days')) AS breaking,
                       (SELECT s.text FROM sp_summaries s
                        WHERE s.tenant_id=i.tenant_id AND s.item_id=i.item_id
                        ORDER BY s.created_at DESC LIMIT 1) AS summary
                FROM sp_items i WHERE {where}
                ORDER BY {order_by} LIMIT ? OFFSET ?
                """,
                [*select_params, *params, bounded_limit, bounded_offset],
            ).fetchall()
        res = {
            "items": [self._item(row) for row in rows],
            "total": total,
            "limit": bounded_limit,
            "offset": bounded_offset,
        }
        if total == 0 and tenant_id != DEFAULT_TENANT:
            return self.search_news(
                query=query,
                tenant_id=DEFAULT_TENANT,
                user_id=user_id,
                category=category,
                source=source,
                region=region,
                language=language,
                date_start=date_start,
                date_end=date_end,
                minimum_quality=minimum_quality,
                live_only=live_only,
                research_backed=research_backed,
                unread_only=unread_only,
                saved_only=saved_only,
                breaking_only=breaking_only,
                minimum_source_count=minimum_source_count,
                sort=sort,
                limit=limit,
                offset=offset,
            )
        return res
    def get_item(self, item_id: str, tenant_id: str = DEFAULT_TENANT) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM sp_items WHERE tenant_id=? AND item_id=?",
                (tenant_id, item_id),
            ).fetchone()
            if not row:
                return None
            payload = self._item(row)
            sources = connection.execute(
                "SELECT * FROM sp_item_sources WHERE tenant_id=? AND item_id=? ORDER BY provider_key",
                (tenant_id, item_id),
            ).fetchall()
        payload["sources"] = [self._row(source) for source in sources]
        return payload

    def toggle_bookmark(
        self,
        user_id: str,
        item_id: str,
        *,
        tenant_id: str = DEFAULT_TENANT,
        reading_list: str = "Saved",
    ) -> bool:
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT 1 FROM sp_bookmarks WHERE tenant_id=? AND user_id=? AND item_id=?",
                (tenant_id, user_id, item_id),
            ).fetchone()
            if existing:
                connection.execute(
                    "DELETE FROM sp_bookmarks WHERE tenant_id=? AND user_id=? AND item_id=?",
                    (tenant_id, user_id, item_id),
                )
                return False
            connection.execute(
                "INSERT INTO sp_bookmarks VALUES(?,?,?,?,?,?)",
                (tenant_id, user_id, item_id, reading_list[:100], "", utc_now()),
            )
            return True

    def mark_item_read(
        self,
        user_id: str,
        item_id: str,
        *,
        tenant_id: str = DEFAULT_TENANT,
    ) -> str:
        read_at = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO sp_item_reads VALUES(?,?,?,?)
                ON CONFLICT(tenant_id,user_id,item_id) DO UPDATE SET read_at=excluded.read_at
                """,
                (tenant_id, user_id, item_id, read_at),
            )
        return read_at

    def item_read_at(
        self, user_id: str, item_id: str, tenant_id: str = DEFAULT_TENANT
    ) -> str:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT read_at FROM sp_item_reads WHERE tenant_id=? AND user_id=? AND item_id=?",
                (tenant_id, user_id, item_id),
            ).fetchone()
        return str(row["read_at"] or "") if row else ""
    def save_preferences(
        self, user_id: str, preferences: dict[str, Any], tenant_id: str = DEFAULT_TENANT
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO sp_user_preferences VALUES(?,?,?,?)
                ON CONFLICT(tenant_id,user_id) DO UPDATE SET
                    preferences_json=excluded.preferences_json,updated_at=excluded.updated_at
                """,
                (tenant_id, user_id, compact_json(preferences), utc_now()),
            )

    def preferences(self, user_id: str, tenant_id: str = DEFAULT_TENANT) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT preferences_json FROM sp_user_preferences WHERE tenant_id=? AND user_id=?",
                (tenant_id, user_id),
            ).fetchone()
        return json.loads(row["preferences_json"]) if row else {}

    def create_alert(
        self,
        user_id: str,
        *,
        name: str,
        query: str = "",
        categories: list[str] | None = None,
        content_types: list[str] | None = None,
        channels: list[str] | None = None,
        frequency: str = "immediate",
        tenant_id: str = DEFAULT_TENANT,
    ) -> str:
        now = utc_now()
        rule_id = stable_id("spa", tenant_id, user_id, name, query, now)
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO sp_alert_rules VALUES(?,?,?,?,?,?,?,?,?,1,'',?,?)",
                (
                    rule_id,
                    tenant_id,
                    user_id,
                    name[:200],
                    query[:1000],
                    compact_json(categories or []),
                    compact_json(content_types or []),
                    compact_json(channels or ["in_app"]),
                    frequency,
                    now,
                    now,
                ),
            )
        return rule_id

    def enabled_alerts(self, tenant_id: str = DEFAULT_TENANT) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM sp_alert_rules WHERE tenant_id=? AND enabled=1",
                (tenant_id,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def put_notification(
        self,
        *,
        user_id: str,
        item_id: str,
        rule_id: str,
        channel: str,
        title: str,
        body: str,
        state: str,
        reference: str = "",
        error: str = "",
        tenant_id: str = DEFAULT_TENANT,
    ) -> tuple[str, bool]:
        notification_id = stable_id("spn", tenant_id, user_id, item_id, rule_id, channel)
        delivered_at = utc_now() if state == "delivered" else ""
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO sp_notifications(
                    notification_id,tenant_id,user_id,item_id,rule_id,channel,title,body,
                    delivery_state,delivery_reference,error_text,created_at,delivered_at,read_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    notification_id,
                    tenant_id,
                    user_id,
                    item_id,
                    rule_id,
                    channel,
                    title[:500],
                    body[:4000],
                    state,
                    reference[:1000],
                    error[:2000],
                    utc_now(),
                    delivered_at,
                    "",
                ),
            )
        return notification_id, bool(cursor.rowcount)

    def notifications(
        self, user_id: str, tenant_id: str = DEFAULT_TENANT, limit: int = 100
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM sp_notifications WHERE tenant_id=? AND user_id=?
                ORDER BY created_at DESC LIMIT ?
                """,
                (tenant_id, user_id, max(1, min(limit, 500))),
            ).fetchall()
        return [self._row(row) for row in rows]

    def save_digest(
        self,
        *,
        user_id: str,
        frequency: str,
        title: str,
        body: str,
        item_ids: list[str],
        period_start: str,
        period_end: str,
        tenant_id: str = DEFAULT_TENANT,
    ) -> str:
        digest_id = stable_id("spd", tenant_id, user_id, frequency, period_start, period_end)
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO sp_digests VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    digest_id,
                    tenant_id,
                    user_id,
                    frequency,
                    title[:500],
                    len(item_ids),
                    body[:50_000],
                    "ready",
                    period_start,
                    period_end,
                    utc_now(),
                ),
            )
            for position, item_id in enumerate(item_ids, start=1):
                connection.execute(
                    "INSERT OR IGNORE INTO sp_digest_items VALUES(?,?,?)",
                    (digest_id, item_id, position),
                )
        return digest_id

    def create_integration_draft(
        self,
        *,
        user_id: str,
        item_id: str,
        destination: str,
        action: str,
        payload: dict[str, Any],
        tenant_id: str = DEFAULT_TENANT,
    ) -> str:
        now = utc_now()
        integration_id = stable_id("spx", tenant_id, user_id, item_id, destination, action, now)
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO sp_integrations VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    integration_id,
                    tenant_id,
                    user_id,
                    item_id,
                    destination,
                    action,
                    compact_json(payload),
                    "approval_required",
                    "",
                    now,
                    now,
                ),
            )
        return integration_id

    def set_trust(
        self,
        item_id: str,
        event_type: str,
        *,
        source_url: str = "",
        note: str = "",
        verified: bool = False,
        tenant_id: str = DEFAULT_TENANT,
    ) -> str:
        now = utc_now()
        event_id = stable_id("spt", tenant_id, item_id, event_type, source_url, now)
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO sp_trust_events VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    event_id,
                    tenant_id,
                    item_id,
                    event_type,
                    source_url,
                    note[:4000],
                    int(verified),
                    now,
                    now,
                ),
            )
            connection.execute(
                "UPDATE sp_items SET trust_state=? WHERE tenant_id=? AND item_id=?",
                (event_type, tenant_id, item_id),
            )
        return event_id

    def audit(
        self,
        actor_id: str,
        action: str,
        target_type: str,
        target_id: str,
        details: dict[str, Any] | None = None,
        tenant_id: str = DEFAULT_TENANT,
    ) -> str:
        audit_id = stable_id("spu", tenant_id, actor_id, action, target_id, utc_now())
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO sp_audit_log VALUES(?,?,?,?,?,?,?,?)",
                (
                    audit_id,
                    tenant_id,
                    actor_id,
                    action,
                    target_type,
                    target_id,
                    compact_json(details or {}),
                    utc_now(),
                ),
            )
        return audit_id

    def metrics(self, tenant_id: str = DEFAULT_TENANT) -> dict[str, Any]:
        with self.connect() as connection:
            counts = {
                "items": connection.execute(
                    "SELECT COUNT(*) FROM sp_items WHERE tenant_id=?", (tenant_id,)
                ).fetchone()[0],
                "sources": connection.execute(
                    "SELECT COUNT(*) FROM sp_sources WHERE tenant_id=?", (tenant_id,)
                ).fetchone()[0],
                "degraded_sources": connection.execute(
                    "SELECT COUNT(*) FROM sp_sources WHERE tenant_id=? AND status NOT IN ('READY','EXTERNAL_VALIDATION_REQUIRED')",
                    (tenant_id,),
                ).fetchone()[0],
                "notifications": connection.execute(
                    "SELECT COUNT(*) FROM sp_notifications WHERE tenant_id=?", (tenant_id,)
                ).fetchone()[0],
                "bookmarks": connection.execute(
                    "SELECT COUNT(*) FROM sp_bookmarks WHERE tenant_id=?", (tenant_id,)
                ).fetchone()[0],
            }
            runs = connection.execute(
                "SELECT * FROM sp_sync_runs WHERE tenant_id=? ORDER BY started_at DESC LIMIT 10",
                (tenant_id,),
            ).fetchall()
        counts["recent_runs"] = [self._row(row) for row in runs]
        counts["database_path"] = str(self.path)
        counts["migration_version"] = MIGRATION_VERSION
        return counts

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        for key, value in list(result.items()):
            if key.endswith("_json") and isinstance(value, str):
                try:
                    result[key.removesuffix("_json")] = json.loads(value)
                except json.JSONDecodeError:
                    result[key.removesuffix("_json")] = [] if value.startswith("[") else {}
        return result

    @classmethod
    def _item(cls, row: sqlite3.Row) -> dict[str, Any]:
        return cls._row(row)


__all__ = ["SciencePulseStore", "science_pulse_db_path", "MIGRATION_VERSION"]
