from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any

from biointel.synthetic.core import (
    enforce_validation_assignment,
    payload_contains_synthetic,
)

import pandas as pd

from .recommendations import RecommendationStore as BaseRecommendationStore
from .recommendations import _now, recommendation_to_dict


NOTEBOOK_ENTRY_TYPES = ("Note", "Evidence", "Decision", "Review", "Question", "Assignment", "Experiment Link", "Follow-up")
REVIEW_ROLES = ("Researcher", "Analyst", "Reviewer", "Lab Lead", "Project Owner", "Administrator")


class RecommendationStore(BaseRecommendationStore):
    """Extended persistent recommendation workspace.

    The base recommendation row remains backward compatible. Related scientific
    records are normalized into dedicated tables and survive Streamlit sessions.
    """

    def _connect(self) -> sqlite3.Connection:
        connection = super()._connect()
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS recommendation_versions (
                recommendation_id TEXT NOT NULL,
                version_number INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                actor TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                PRIMARY KEY(recommendation_id, version_number)
            );
            CREATE TABLE IF NOT EXISTS recommendation_notebook (
                entry_id TEXT PRIMARY KEY,
                recommendation_id TEXT NOT NULL,
                entry_type TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                actor TEXT NOT NULL,
                assigned_to TEXT NOT NULL,
                related_experiment TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                created_at_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recommendation_attachments (
                attachment_id TEXT PRIMARY KEY,
                recommendation_id TEXT NOT NULL,
                file_name TEXT NOT NULL,
                media_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                content BLOB NOT NULL,
                actor TEXT NOT NULL,
                created_at_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recommendation_validations (
                validation_id TEXT PRIMARY KEY,
                recommendation_id TEXT NOT NULL,
                validation_type TEXT NOT NULL,
                status TEXT NOT NULL,
                result TEXT NOT NULL,
                acceptance_criteria TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                actor TEXT NOT NULL,
                created_at_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recommendation_comparisons (
                comparison_id TEXT PRIMARY KEY,
                recommendation_id TEXT NOT NULL,
                comparison_type TEXT NOT NULL,
                comparison_json TEXT NOT NULL,
                actor TEXT NOT NULL,
                created_at_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recommendation_provenance_registry (
                registry_id TEXT PRIMARY KEY,
                recommendation_id TEXT NOT NULL,
                registry_type TEXT NOT NULL,
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                uri TEXT NOT NULL,
                checksum TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                actor TEXT NOT NULL,
                created_at_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recommendation_cache (
                cache_key TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                created_at_utc TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_rec_versions ON recommendation_versions(recommendation_id, version_number);
            CREATE INDEX IF NOT EXISTS idx_rec_notebook ON recommendation_notebook(recommendation_id, created_at_utc);
            CREATE INDEX IF NOT EXISTS idx_rec_attachments ON recommendation_attachments(recommendation_id, created_at_utc);
            CREATE INDEX IF NOT EXISTS idx_rec_validations ON recommendation_validations(recommendation_id, created_at_utc);
            CREATE INDEX IF NOT EXISTS idx_rec_provenance ON recommendation_provenance_registry(recommendation_id, registry_type);
            """
        )
        connection.commit()
        return connection

    def save(self, record: Mapping[str, Any]) -> str:
        recommendation_id = super().save(record)
        payload = self.get(recommendation_id)
        if payload is None:
            return recommendation_id
        actor = str(payload.get("reproducibility", {}).get("user", "system"))
        with self._connect() as connection:
            version = int(connection.execute(
                "SELECT COALESCE(MAX(version_number), 0) + 1 FROM recommendation_versions WHERE recommendation_id=?",
                (recommendation_id,),
            ).fetchone()[0])
            connection.execute(
                "INSERT INTO recommendation_versions(recommendation_id, version_number, payload_json, actor, created_at_utc) VALUES(?,?,?,?,?)",
                (recommendation_id, version, json.dumps(payload, sort_keys=True, default=str), actor, _now()),
            )
            connection.commit()
        return recommendation_id

    def events(self, recommendation_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM recommendation_events WHERE recommendation_id=? ORDER BY created_at_utc, event_id",
                (recommendation_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def event_frame(self, recommendation_id: str) -> pd.DataFrame:
        return pd.DataFrame(self.events(recommendation_id))

    def versions(self, recommendation_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT version_number, actor, created_at_utc, payload_json FROM recommendation_versions WHERE recommendation_id=? ORDER BY version_number DESC",
                (recommendation_id,),
            ).fetchall()
        return [
            {"version_number": int(row["version_number"]), "actor": row["actor"], "created_at_utc": row["created_at_utc"], "payload": json.loads(row["payload_json"])}
            for row in rows
        ]

    def compare_versions(self, recommendation_id: str, older: int, newer: int) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT version_number, payload_json FROM recommendation_versions WHERE recommendation_id=? AND version_number IN (?,?)",
                (recommendation_id, int(older), int(newer)),
            ).fetchall()
        payloads = {int(row["version_number"]): json.loads(row["payload_json"]) for row in rows}
        if older not in payloads or newer not in payloads:
            raise KeyError("Requested recommendation version is unavailable.")
        fields = ("priority", "priority_score", "confidence_score", "evidence_grade", "status", "recommended_next_action", "validation_status")
        return [{"field": field, "older": payloads[older].get(field), "newer": payloads[newer].get(field), "changed": payloads[older].get(field) != payloads[newer].get(field)} for field in fields]

    def add_notebook_entry(
        self,
        recommendation_id: str,
        entry_type: str,
        title: str,
        body: str,
        *,
        actor: str,
        assigned_to: str = "",
        related_experiment: str = "",
        evidence: Sequence[Mapping[str, Any]] = (),
    ) -> str:
        if self.get(recommendation_id) is None:
            raise KeyError(recommendation_id)
        if entry_type not in NOTEBOOK_ENTRY_TYPES:
            raise ValueError(f"Unsupported notebook entry type: {entry_type}")
        if not title.strip() or not body.strip():
            raise ValueError("Notebook title and body are required.")
        entry_id = f"note-{uuid.uuid4().hex[:16]}"
        now = _now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO recommendation_notebook(entry_id,recommendation_id,entry_type,title,body,actor,assigned_to,related_experiment,evidence_json,created_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (entry_id, recommendation_id, entry_type, title.strip(), body.strip(), actor, assigned_to, related_experiment, json.dumps([dict(row) for row in evidence], sort_keys=True, default=str), now),
            )
            connection.execute(
                "INSERT INTO recommendation_events(event_id,recommendation_id,event_type,actor,note,created_at_utc) VALUES(?,?,?,?,?,?)",
                (f"evt-{uuid.uuid4().hex[:16]}", recommendation_id, "notebook_entry", actor, f"{entry_type}: {title.strip()}", now),
            )
            connection.commit()
        return entry_id

    def notebook(self, recommendation_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM recommendation_notebook WHERE recommendation_id=? ORDER BY created_at_utc DESC",
                (recommendation_id,),
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["evidence"] = json.loads(item.pop("evidence_json"))
            output.append(item)
        return output

    def save_attachment(self, recommendation_id: str, file_name: str, content: bytes, media_type: str, *, actor: str, maximum_bytes: int = 25 * 1024 * 1024) -> str:
        if self.get(recommendation_id) is None:
            raise KeyError(recommendation_id)
        if not content:
            raise ValueError("Attachment is empty.")
        if len(content) > maximum_bytes:
            raise ValueError(f"Attachment exceeds {maximum_bytes} bytes.")
        attachment_id = f"att-{uuid.uuid4().hex[:16]}"
        digest = sha256(content).hexdigest()
        now = _now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO recommendation_attachments(attachment_id,recommendation_id,file_name,media_type,size_bytes,sha256,content,actor,created_at_utc) VALUES(?,?,?,?,?,?,?,?,?)",
                (attachment_id, recommendation_id, Path(file_name).name, media_type or "application/octet-stream", len(content), digest, content, actor, now),
            )
            connection.execute(
                "INSERT INTO recommendation_events(event_id,recommendation_id,event_type,actor,note,created_at_utc) VALUES(?,?,?,?,?,?)",
                (f"evt-{uuid.uuid4().hex[:16]}", recommendation_id, "attachment_saved", actor, f"{Path(file_name).name} ({digest[:12]})", now),
            )
            connection.commit()
        return attachment_id

    def attachments(self, recommendation_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT attachment_id,file_name,media_type,size_bytes,sha256,actor,created_at_utc FROM recommendation_attachments WHERE recommendation_id=? ORDER BY created_at_utc DESC",
                (recommendation_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def attachment_content(self, attachment_id: str) -> tuple[str, str, bytes]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT file_name,media_type,content FROM recommendation_attachments WHERE attachment_id=?",
                (attachment_id,),
            ).fetchone()
        if row is None:
            raise KeyError(attachment_id)
        return str(row["file_name"]), str(row["media_type"]), bytes(row["content"])

    def save_validation_result(
        self,
        recommendation_id: str,
        validation_type: str,
        status: str,
        result: str,
        *,
        acceptance_criteria: str,
        actor: str,
        evidence: Sequence[Mapping[str, Any]] = (),
    ) -> str:
        recommendation = self.get(recommendation_id)
        if recommendation is None:
            raise KeyError(recommendation_id)
        evidence_rows = [dict(row) for row in evidence]
        validation_origin = "synthetic" if payload_contains_synthetic(recommendation) or any(payload_contains_synthetic(row) for row in evidence_rows) else "real"
        validation_payload = {"data_origin": validation_origin, "is_synthetic": validation_origin == "synthetic", "evidence": evidence_rows}
        enforce_validation_assignment(validation_payload, recommendation)
        if payload_contains_synthetic(recommendation):
            for row in evidence_rows:
                row.update({"evidence_origin": "demo_fixture", "data_origin": "synthetic", "is_synthetic": True})
            if status.strip().lower() in {"validated", "passed", "accepted", "completed", "success"}:
                status = "Synthetic Demo Passed - not scientifically validated"
        validation_id = f"val-{uuid.uuid4().hex[:16]}"
        now = _now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO recommendation_validations(validation_id,recommendation_id,validation_type,status,result,acceptance_criteria,evidence_json,actor,created_at_utc) VALUES(?,?,?,?,?,?,?,?,?)",
                (validation_id, recommendation_id, validation_type, status, result, acceptance_criteria, json.dumps(evidence_rows, sort_keys=True, default=str), actor, now),
            )
            connection.execute(
                "INSERT INTO recommendation_events(event_id,recommendation_id,event_type,actor,note,created_at_utc) VALUES(?,?,?,?,?,?)",
                (f"evt-{uuid.uuid4().hex[:16]}", recommendation_id, "validation_result", actor, f"{validation_type}: {status}", now),
            )
            connection.commit()
        return validation_id

    def validations(self, recommendation_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM recommendation_validations WHERE recommendation_id=? ORDER BY created_at_utc DESC",
                (recommendation_id,),
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["evidence"] = json.loads(item.pop("evidence_json"))
            output.append(item)
        return output

    def save_comparison(self, recommendation_id: str, comparison_type: str, comparison: Sequence[Mapping[str, Any]], *, actor: str) -> str:
        comparison_id = f"cmp-{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO recommendation_comparisons(comparison_id,recommendation_id,comparison_type,comparison_json,actor,created_at_utc) VALUES(?,?,?,?,?,?)",
                (comparison_id, recommendation_id, comparison_type, json.dumps([dict(row) for row in comparison], sort_keys=True, default=str), actor, _now()),
            )
            connection.commit()
        return comparison_id

    def register_provenance(self, recommendation_id: str, registry_type: str, name: str, version: str, *, uri: str = "", checksum: str = "", metadata: Mapping[str, Any] | None = None, actor: str = "system") -> str:
        if registry_type not in {"model", "database", "reference", "annotation", "software"}:
            raise ValueError("Unsupported registry type.")
        registry_id = f"reg-{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO recommendation_provenance_registry(registry_id,recommendation_id,registry_type,name,version,uri,checksum,metadata_json,actor,created_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (registry_id, recommendation_id, registry_type, name, version, uri, checksum, json.dumps(dict(metadata or {}), sort_keys=True, default=str), actor, _now()),
            )
            connection.commit()
        return registry_id

    def provenance(self, recommendation_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM recommendation_provenance_registry WHERE recommendation_id=? ORDER BY registry_type,name,version",
                (recommendation_id,),
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json"))
            output.append(item)
        return output

    def cache_get(self, cache_key: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT payload_json FROM recommendation_cache WHERE cache_key=?", (cache_key,)).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def cache_set(self, cache_key: str, payload: Mapping[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO recommendation_cache(cache_key,payload_json,created_at_utc) VALUES(?,?,?) ON CONFLICT(cache_key) DO UPDATE SET payload_json=excluded.payload_json,created_at_utc=excluded.created_at_utc",
                (cache_key, json.dumps(recommendation_to_dict(payload), sort_keys=True, default=str), _now()),
            )
            connection.commit()

    def log_error(self, recommendation_id: str, message: str, *, actor: str = "system") -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO recommendation_events(event_id,recommendation_id,event_type,actor,note,created_at_utc) VALUES(?,?,?,?,?,?)",
                (f"evt-{uuid.uuid4().hex[:16]}", recommendation_id, "error", actor, message[:4000], _now()),
            )
            connection.commit()

