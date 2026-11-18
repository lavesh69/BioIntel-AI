from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator, Sequence
from uuid import uuid4

from biointel.shiro.exceptions import ProjectAccessError
from biointel.shiro.models import ChunkRecord, SourceRecord


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class ShiroRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS shiro_projects (
                    project_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS shiro_sources (
                    source_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    byte_size INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    uploaded_at TEXT NOT NULL,
                    author TEXT NOT NULL DEFAULT '',
                    internal INTEGER NOT NULL,
                    external INTEGER NOT NULL,
                    synthetic INTEGER NOT NULL,
                    confidential INTEGER NOT NULL,
                    warnings_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    UNIQUE(project_id, sha256),
                    FOREIGN KEY(project_id) REFERENCES shiro_projects(project_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_shiro_sources_project ON shiro_sources(project_id);
                CREATE TABLE IF NOT EXISTS shiro_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    location TEXT NOT NULL,
                    section TEXT NOT NULL,
                    embedding_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    UNIQUE(source_id, ordinal),
                    FOREIGN KEY(source_id) REFERENCES shiro_sources(source_id) ON DELETE CASCADE,
                    FOREIGN KEY(project_id) REFERENCES shiro_projects(project_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_shiro_chunks_project ON shiro_chunks(project_id);
                CREATE TABLE IF NOT EXISTS shiro_jobs (
                    job_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    job_type TEXT NOT NULL,
                    state TEXT NOT NULL,
                    progress REAL NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS shiro_conversations (
                    conversation_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    language_preference TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES shiro_projects(project_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_shiro_conversations_project ON shiro_conversations(project_id);
                CREATE TABLE IF NOT EXISTS shiro_messages (
                    message_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    citations_json TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    retrieval_json TEXT NOT NULL,
                    source_filters_json TEXT NOT NULL,
                    language TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(conversation_id) REFERENCES shiro_conversations(conversation_id) ON DELETE CASCADE,
                    FOREIGN KEY(project_id) REFERENCES shiro_projects(project_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_shiro_messages_conversation ON shiro_messages(conversation_id, created_at);
                """
            )
            job_columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(shiro_jobs)")}
            migrations = {
                "cancel_requested": "INTEGER NOT NULL DEFAULT 0",
                "result_json": "TEXT NOT NULL DEFAULT '{}'",
                "started_at": "TEXT NOT NULL DEFAULT ''",
                "completed_at": "TEXT NOT NULL DEFAULT ''",
            }
            for column, definition in migrations.items():
                if column not in job_columns:
                    connection.execute(f"ALTER TABLE shiro_jobs ADD COLUMN {column} {definition}")
            connection.commit()

    def upsert_project(self, project_id: str, name: str | None = None) -> None:
        value = project_id.strip()
        if not value or len(value) > 160:
            raise ValueError("A project ID of at most 160 characters is required.")
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO shiro_projects(project_id, name, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET name=excluded.name, updated_at=excluded.updated_at
                """,
                (value, (name or value).strip()[:200], now, now),
            )
            connection.commit()

    def project_name(self, project_id: str) -> str:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT name FROM shiro_projects WHERE project_id = ?", (project_id,)
            ).fetchone()
        return str(row["name"]) if row else project_id

    def list_projects(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT project_id, name, created_at, updated_at FROM shiro_projects ORDER BY name"
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _source(row: sqlite3.Row) -> SourceRecord:
        return SourceRecord(
            source_id=row["source_id"],
            project_id=row["project_id"],
            filename=row["filename"],
            source_type=row["source_type"],
            mime_type=row["mime_type"],
            byte_size=int(row["byte_size"]),
            sha256=row["sha256"],
            uploaded_at=row["uploaded_at"],
            author=row["author"],
            internal=bool(row["internal"]),
            external=bool(row["external"]),
            synthetic=bool(row["synthetic"]),
            confidential=bool(row["confidential"]),
            warnings=tuple(json.loads(row["warnings_json"])),
            metadata=json.loads(row["metadata_json"]),
            file_path=row["file_path"],
        )

    @staticmethod
    def _chunk(row: sqlite3.Row) -> ChunkRecord:
        return ChunkRecord(
            chunk_id=row["chunk_id"],
            source_id=row["source_id"],
            project_id=row["project_id"],
            ordinal=int(row["ordinal"]),
            text=row["text"],
            location=row["location"],
            section=row["section"],
            embedding=tuple(float(value) for value in json.loads(row["embedding_json"])),
            metadata=json.loads(row["metadata_json"]),
        )

    def find_source_by_hash(self, project_id: str, sha256: str) -> SourceRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM shiro_sources WHERE project_id = ? AND sha256 = ?",
                (project_id, sha256),
            ).fetchone()
        return self._source(row) if row else None

    def add_source(self, source: SourceRecord, chunks: Sequence[ChunkRecord]) -> None:
        if any(chunk.project_id != source.project_id or chunk.source_id != source.source_id for chunk in chunks):
            raise ProjectAccessError("A chunk attempted to cross a source or project boundary.")
        self.upsert_project(source.project_id, str(source.metadata.get("project_name", source.project_id)))
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO shiro_sources(
                    source_id, project_id, filename, source_type, mime_type, byte_size,
                    sha256, uploaded_at, author, internal, external, synthetic,
                    confidential, warnings_json, metadata_json, file_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source.source_id, source.project_id, source.filename, source.source_type,
                    source.mime_type, source.byte_size, source.sha256, source.uploaded_at,
                    source.author, int(source.internal), int(source.external), int(source.synthetic),
                    int(source.confidential), json.dumps(source.warnings, ensure_ascii=False),
                    json.dumps(source.metadata, ensure_ascii=False), source.file_path,
                ),
            )
            connection.executemany(
                """
                INSERT INTO shiro_chunks(
                    chunk_id, source_id, project_id, ordinal, text, location, section,
                    embedding_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk.chunk_id, chunk.source_id, chunk.project_id, chunk.ordinal,
                        chunk.text, chunk.location, chunk.section,
                        json.dumps(chunk.embedding), json.dumps(chunk.metadata, ensure_ascii=False),
                    )
                    for chunk in chunks
                ],
            )
            connection.commit()

    def get_source(self, project_id: str, source_id: str) -> SourceRecord:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM shiro_sources WHERE project_id = ? AND source_id = ?",
                (project_id, source_id),
            ).fetchone()
        if row is None:
            raise ProjectAccessError("Source not found in the active project.")
        return self._source(row)

    def list_sources(self, project_id: str, limit: int = 500) -> list[SourceRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM shiro_sources WHERE project_id = ? ORDER BY uploaded_at DESC LIMIT ?",
                (project_id, max(1, min(limit, 2000))),
            ).fetchall()
        return [self._source(row) for row in rows]

    def delete_source(self, project_id: str, source_id: str) -> SourceRecord:
        source = self.get_source(project_id, source_id)
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM shiro_sources WHERE project_id=? AND source_id=?",
                (project_id, source_id),
            )
            connection.commit()
        if not cursor.rowcount:
            raise ProjectAccessError("Source not found in the active project.")
        return source

    def delete_project(self, project_id: str) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT file_path FROM shiro_sources WHERE project_id=?", (project_id,)
            ).fetchall()
            connection.execute("DELETE FROM shiro_jobs WHERE project_id=?", (project_id,))
            connection.execute("DELETE FROM shiro_projects WHERE project_id=?", (project_id,))
            connection.commit()
        return [str(row["file_path"]) for row in rows]

    def list_chunks(
        self,
        project_id: str,
        *,
        source_ids: Sequence[str] | None = None,
        source_types: Sequence[str] | None = None,
        limit: int = 20000,
    ) -> list[tuple[ChunkRecord, SourceRecord]]:
        clauses = ["c.project_id = ?"]
        params: list[Any] = [project_id]
        if source_ids:
            clauses.append("c.source_id IN (" + ",".join("?" for _ in source_ids) + ")")
            params.extend(source_ids)
        if source_types:
            clauses.append("s.source_type IN (" + ",".join("?" for _ in source_types) + ")")
            params.extend(source_types)
        params.append(max(1, min(limit, 100000)))
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT c.*, s.filename, s.source_type, s.mime_type, s.byte_size, s.sha256,
                       s.uploaded_at, s.author, s.internal, s.external, s.synthetic,
                       s.confidential, s.warnings_json, s.metadata_json AS source_metadata_json,
                       s.file_path
                FROM shiro_chunks c JOIN shiro_sources s ON s.source_id = c.source_id
                WHERE {' AND '.join(clauses)}
                ORDER BY c.source_id, c.ordinal LIMIT ?
                """,
                params,
            ).fetchall()
        pairs: list[tuple[ChunkRecord, SourceRecord]] = []
        for row in rows:
            chunk = self._chunk(row)
            source = SourceRecord(
                source_id=row["source_id"], project_id=row["project_id"], filename=row["filename"],
                source_type=row["source_type"], mime_type=row["mime_type"], byte_size=int(row["byte_size"]),
                sha256=row["sha256"], uploaded_at=row["uploaded_at"], author=row["author"],
                internal=bool(row["internal"]), external=bool(row["external"]), synthetic=bool(row["synthetic"]),
                confidential=bool(row["confidential"]), warnings=tuple(json.loads(row["warnings_json"])),
                metadata=json.loads(row["source_metadata_json"]), file_path=row["file_path"],
            )
            pairs.append((chunk, source))
        return pairs

    def source_preview(self, project_id: str, source_id: str, limit: int = 20) -> dict[str, Any]:
        source = self.get_source(project_id, source_id)
        pairs = self.list_chunks(project_id, source_ids=[source_id], limit=limit)
        return {
            "source": source.to_dict(),
            "chunks": [
                {"chunk_id": chunk.chunk_id, "location": chunk.location, "section": chunk.section, "text": chunk.text}
                for chunk, _ in pairs
            ],
        }

    def index_status(self, project_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(DISTINCT s.source_id) AS sources, COUNT(c.chunk_id) AS chunks,
                       COALESCE(SUM(s.byte_size), 0) AS bytes
                FROM shiro_sources s LEFT JOIN shiro_chunks c ON c.source_id = s.source_id
                WHERE s.project_id = ?
                """,
                (project_id,),
            ).fetchone()
        return {"project_id": project_id, "sources": int(row["sources"]), "chunks": int(row["chunks"]), "bytes": int(row["bytes"]), "persistent": True}

    def update_embeddings(self, project_id: str, values: Sequence[tuple[str, Sequence[float]]]) -> int:
        with self.connect() as connection:
            count = 0
            for chunk_id, embedding in values:
                cursor = connection.execute(
                    "UPDATE shiro_chunks SET embedding_json = ? WHERE chunk_id = ? AND project_id = ?",
                    (json.dumps(tuple(embedding)), chunk_id, project_id),
                )
                count += cursor.rowcount
            connection.commit()
        return count

    def create_job(self, project_id: str, job_type: str) -> str:
        self.upsert_project(project_id)
        job_id = "job-" + uuid4().hex
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO shiro_jobs(
                    job_id, project_id, job_type, state, progress, error,
                    created_at, updated_at, cancel_requested, result_json,
                    started_at, completed_at
                ) VALUES (?, ?, ?, 'queued', 0, '', ?, ?, 0, '{}', '', '')
                """,
                (job_id, project_id, job_type, now, now),
            )
            connection.commit()
        return job_id

    def update_job(
        self,
        job_id: str,
        state: str,
        progress: float,
        error: str = "",
        result: dict[str, Any] | None = None,
    ) -> None:
        now = utc_now()
        started = now if state == "running" else ""
        completed = now if state in {"completed", "failed", "cancelled"} else ""
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE shiro_jobs
                SET state=?, progress=?, error=?, result_json=COALESCE(?, result_json),
                    started_at=CASE WHEN started_at='' AND ?<>'' THEN ? ELSE started_at END,
                    completed_at=CASE WHEN ?<>'' THEN ? ELSE completed_at END,
                    updated_at=?
                WHERE job_id=?
                """,
                (
                    state, min(1.0, max(0.0, progress)), error[:2000],
                    json.dumps(result, ensure_ascii=False) if result is not None else None,
                    started, started, completed, completed, now, job_id,
                ),
            )
            connection.commit()

    @staticmethod
    def _job_dict(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["cancel_requested"] = bool(item.get("cancel_requested", 0))
        item["result"] = json.loads(item.pop("result_json", "{}") or "{}")
        return item

    def get_job(self, job_id: str, project_id: str | None = None) -> dict[str, Any] | None:
        with self.connect() as connection:
            if project_id is None:
                row = connection.execute("SELECT * FROM shiro_jobs WHERE job_id=?", (job_id,)).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM shiro_jobs WHERE job_id=? AND project_id=?", (job_id, project_id)
                ).fetchone()
        return self._job_dict(row) if row else None

    def list_jobs(self, project_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM shiro_jobs WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
                (project_id, max(1, min(limit, 200))),
            ).fetchall()
        return [self._job_dict(row) for row in rows]

    def request_job_cancel(self, project_id: str, job_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT state FROM shiro_jobs WHERE project_id=? AND job_id=?", (project_id, job_id)
            ).fetchone()
            if row is None:
                raise ProjectAccessError("Job not found in the active project.")
            if row["state"] in {"completed", "failed", "cancelled"}:
                return self.get_job(job_id, project_id) or {}
            state = "cancelled" if row["state"] == "queued" else row["state"]
            completed = utc_now() if state == "cancelled" else ""
            connection.execute(
                """
                UPDATE shiro_jobs SET cancel_requested=1, state=?, completed_at=?, updated_at=?
                WHERE project_id=? AND job_id=?
                """,
                (state, completed, utc_now(), project_id, job_id),
            )
            connection.commit()
        return self.get_job(job_id, project_id) or {}

    def job_cancel_requested(self, project_id: str, job_id: str) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT cancel_requested FROM shiro_jobs WHERE project_id=? AND job_id=?",
                (project_id, job_id),
            ).fetchone()
        if row is None:
            raise ProjectAccessError("Job not found in the active project.")
        return bool(row["cancel_requested"])

    def create_conversation(self, project_id: str, title: str = "New conversation", language: str = "auto") -> str:
        self.upsert_project(project_id)
        conversation_id = "conv-" + uuid4().hex
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO shiro_conversations VALUES (?, ?, ?, ?, ?, ?)",
                (conversation_id, project_id, title.strip()[:160] or "New conversation", language, now, now),
            )
            connection.commit()
        return conversation_id

    def ensure_conversation(self, project_id: str, conversation_id: str | None, title: str, language: str) -> str:
        if not conversation_id:
            return self.create_conversation(project_id, title, language)
        with self.connect() as connection:
            row = connection.execute(
                "SELECT project_id FROM shiro_conversations WHERE conversation_id = ?", (conversation_id,)
            ).fetchone()
        if row is None or row["project_id"] != project_id:
            raise ProjectAccessError("Conversation not found in the active project.")
        return conversation_id

    def save_message(
        self,
        conversation_id: str,
        project_id: str,
        role: str,
        content: str,
        *,
        citations: Sequence[dict[str, Any]] = (),
        provider: str = "local",
        model: str = "",
        retrieval: dict[str, Any] | None = None,
        source_filters: Sequence[str] = (),
        language: str = "auto",
        status: str = "completed",
        error: str = "",
    ) -> str:
        message_id = "msg-" + uuid4().hex
        now = utc_now()
        with self.connect() as connection:
            conversation = connection.execute(
                "SELECT project_id FROM shiro_conversations WHERE conversation_id = ?", (conversation_id,)
            ).fetchone()
            if conversation is None or conversation["project_id"] != project_id:
                raise ProjectAccessError("Conversation attempted to cross a project boundary.")
            connection.execute(
                """
                INSERT INTO shiro_messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id, conversation_id, project_id, role, content,
                    json.dumps(list(citations), ensure_ascii=False), provider, model,
                    json.dumps(retrieval or {}, ensure_ascii=False), json.dumps(list(source_filters)),
                    language, status, error[:2000], now,
                ),
            )
            connection.execute(
                "UPDATE shiro_conversations SET updated_at = ? WHERE conversation_id = ?", (now, conversation_id)
            )
            connection.commit()
        return message_id

    def list_conversations(self, project_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM shiro_conversations WHERE project_id = ? ORDER BY updated_at DESC LIMIT ?",
                (project_id, max(1, min(limit, 500))),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_messages(self, project_id: str, conversation_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            conversation = connection.execute(
                "SELECT project_id FROM shiro_conversations WHERE conversation_id = ?", (conversation_id,)
            ).fetchone()
            if conversation is None or conversation["project_id"] != project_id:
                raise ProjectAccessError("Conversation not found in the active project.")
            rows = connection.execute(
                "SELECT * FROM shiro_messages WHERE conversation_id = ? ORDER BY created_at, rowid",
                (conversation_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["citations"] = json.loads(item.pop("citations_json"))
            item["retrieval"] = json.loads(item.pop("retrieval_json"))
            item["source_filters"] = json.loads(item.pop("source_filters_json"))
            result.append(item)
        return result

    def rename_conversation(self, project_id: str, conversation_id: str, title: str) -> None:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE shiro_conversations SET title=?, updated_at=? WHERE project_id=? AND conversation_id=?",
                (title.strip()[:160] or "Conversation", utc_now(), project_id, conversation_id),
            )
            connection.commit()
        if not cursor.rowcount:
            raise ProjectAccessError("Conversation not found in the active project.")

    def clear_conversation(self, project_id: str, conversation_id: str) -> None:
        with self.connect() as connection:
            conversation = connection.execute(
                "SELECT 1 FROM shiro_conversations WHERE project_id=? AND conversation_id=?",
                (project_id, conversation_id),
            ).fetchone()
            if conversation is None:
                raise ProjectAccessError("Conversation not found in the active project.")
            connection.execute("DELETE FROM shiro_messages WHERE conversation_id=?", (conversation_id,))
            connection.execute(
                "UPDATE shiro_conversations SET updated_at=? WHERE conversation_id=?", (utc_now(), conversation_id)
            )
            connection.commit()

    def delete_conversation(self, project_id: str, conversation_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM shiro_conversations WHERE project_id=? AND conversation_id=?",
                (project_id, conversation_id),
            )
            connection.commit()
        return cursor.rowcount > 0
