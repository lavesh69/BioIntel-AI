from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).resolve().open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha_content_or_file(
    content: bytes | None,
    path: str | Path | None,
    *,
    label: str,
) -> str:
    """Hash one non-empty payload without requiring large evidence in RAM."""

    if content is not None and path is not None:
        raise ValueError(f"Provide either {label} content or {label} path, not both.")
    if content is not None:
        if not content:
            raise ValueError(f"{label.capitalize()} content is empty.")
        return _sha(content)
    if path is None:
        raise ValueError(f"{label.capitalize()} content or a staged local path is required.")
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"{label.capitalize()} staged file is unavailable.")
    if resolved.stat().st_size <= 0:
        raise ValueError(f"{label.capitalize()} staged file is empty.")
    return _sha_file(resolved)


class ClinicalQualityMixin:
    EVIDENCE_STATUSES = {"draft", "submitted", "reviewed", "approved", "rejected"}
    QUALITY_EVENT_TYPES = {"deviation", "capa", "change_control", "incident", "complaint"}

    def add_evidence(
        self,
        *,
        program_id: str,
        category: str,
        evidence_type: str,
        reference: str,
        source_organization: str,
        independent: bool,
        content: bytes | None,
        owner: str,
        actor: str,
        metadata: dict[str, Any] | None = None,
        status: str = "submitted",
        content_path: str | Path | None = None,
    ) -> dict[str, Any]:
        if status not in self.EVIDENCE_STATUSES:
            raise ValueError(f"Unsupported evidence status: {status}")
        identifier = f"EVD-{uuid.uuid4().hex[:10].upper()}"
        row = {
            "evidence_id": identifier,
            "program_id": program_id,
            "category": category.strip(),
            "evidence_type": evidence_type.strip(),
            "reference": reference.strip(),
            "source_organization": source_organization.strip(),
            "independent": bool(independent),
            "evidence_sha256": _sha_content_or_file(
                content, content_path, label="evidence"
            ),
            "metadata": metadata or {},
            "status": status,
            "owner": owner.strip(),
            "reviewed_by": None,
            "reviewed_at": None,
            "created_at": _now(),
        }
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO evidence_items(
                evidence_id,program_id,category,evidence_type,reference,source_organization,
                independent,evidence_sha256,metadata_json,status,owner,reviewed_by,reviewed_at,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    identifier,
                    program_id,
                    row["category"],
                    row["evidence_type"],
                    row["reference"],
                    row["source_organization"],
                    int(independent),
                    row["evidence_sha256"],
                    _canonical(row["metadata"]),
                    status,
                    row["owner"],
                    None,
                    None,
                    row["created_at"],
                ),
            )
            self._append_audit(
                connection,
                actor=actor,
                action="evidence.added",
                object_type="evidence_item",
                object_id=identifier,
                reason="Add validation evidence",
                payload={"category": row["category"], "independent": independent},
            )
        return row

    def review_evidence(self, evidence_id: str, *, reviewer: str, status: str, reason: str) -> None:
        if status not in {"approved", "rejected", "reviewed"}:
            raise ValueError("Review status must be approved, rejected or reviewed")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE evidence_items SET status=?,reviewed_by=?,reviewed_at=? WHERE evidence_id=?",
                (status, reviewer.strip(), _now(), evidence_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(evidence_id)
            self._append_audit(
                connection,
                actor=reviewer,
                action="evidence.reviewed",
                object_type="evidence_item",
                object_id=evidence_id,
                reason=reason,
                payload={"status": status},
            )

    def open_quality_event(
        self,
        *,
        program_id: str,
        event_type: str,
        severity: str,
        title: str,
        description: str,
        owner: str,
        actor: str,
        due_at: str = "",
    ) -> dict[str, Any]:
        if event_type not in self.QUALITY_EVENT_TYPES:
            raise ValueError(f"Unsupported quality event type: {event_type}")
        identifier = f"QEV-{uuid.uuid4().hex[:10].upper()}"
        row = {
            "quality_event_id": identifier,
            "program_id": program_id,
            "event_type": event_type,
            "severity": severity.strip(),
            "title": title.strip(),
            "description": description.strip(),
            "owner": owner.strip(),
            "due_at": due_at.strip() or None,
            "status": "open",
            "effectiveness_verified": False,
            "created_at": _now(),
        }
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO quality_events(
                quality_event_id,program_id,event_type,severity,title,description,root_cause,
                action_plan,owner,due_at,status,effectiveness_verified,created_at,closed_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    identifier,
                    program_id,
                    event_type,
                    row["severity"],
                    row["title"],
                    row["description"],
                    None,
                    None,
                    row["owner"],
                    row["due_at"],
                    "open",
                    0,
                    row["created_at"],
                    None,
                ),
            )
            self._append_audit(
                connection,
                actor=actor,
                action="quality_event.opened",
                object_type="quality_event",
                object_id=identifier,
                reason="Open validation quality event",
                payload={"event_type": event_type, "severity": row["severity"]},
            )
        return row

    def close_quality_event(
        self,
        quality_event_id: str,
        *,
        root_cause: str,
        action_plan: str,
        effectiveness_verified: bool,
        actor: str,
        reason: str,
    ) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE quality_events SET root_cause=?,action_plan=?,effectiveness_verified=?,
                status='closed',closed_at=? WHERE quality_event_id=?""",
                (
                    root_cause.strip(),
                    action_plan.strip(),
                    int(effectiveness_verified),
                    _now(),
                    quality_event_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(quality_event_id)
            self._append_audit(
                connection,
                actor=actor,
                action="quality_event.closed",
                object_type="quality_event",
                object_id=quality_event_id,
                reason=reason,
                payload={"effectiveness_verified": effectiveness_verified},
            )

    def record_training(
        self,
        *,
        program_id: str,
        person_id: str,
        role_name: str,
        curriculum_id: str,
        completed_at: str,
        result: str,
        evidence: bytes | None,
        actor: str,
        expires_at: str = "",
        evidence_path: str | Path | None = None,
    ) -> dict[str, Any]:
        identifier = f"TRN-{uuid.uuid4().hex[:10].upper()}"
        row = {
            "training_id": identifier,
            "program_id": program_id,
            "person_id": person_id.strip(),
            "role_name": role_name.strip(),
            "curriculum_id": curriculum_id.strip(),
            "completed_at": completed_at.strip(),
            "expires_at": expires_at.strip() or None,
            "result": result.strip(),
            "evidence_sha256": _sha_content_or_file(
                evidence, evidence_path, label="training evidence"
            ),
            "created_at": _now(),
        }
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO training_records(
                training_id,program_id,person_id,role_name,curriculum_id,completed_at,
                expires_at,result,evidence_sha256,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                tuple(row.values()),
            )
            self._append_audit(
                connection,
                actor=actor,
                action="training.recorded",
                object_type="training_record",
                object_id=identifier,
                reason="Record role-based validation training",
                payload={"person_id": row["person_id"], "result": row["result"]},
            )
        return row

    def sign_object(
        self,
        *,
        program_id: str,
        object_type: str,
        object_id: str,
        object_sha256: str,
        signer: str,
        meaning: str,
        reason: str,
        signing_secret: str,
    ) -> dict[str, Any]:
        if len(signing_secret) < 12:
            raise ValueError("Signing secret must contain at least 12 characters")
        signed_at = _now()
        payload = {
            "program_id": program_id,
            "object_type": object_type,
            "object_id": object_id,
            "object_sha256": object_sha256,
            "signer": signer.strip(),
            "meaning": meaning.strip(),
            "reason": reason.strip(),
            "signed_at": signed_at,
        }
        digest = _sha(f"{_canonical(payload)}::{signing_secret}".encode())
        signature_id = f"SIG-{uuid.uuid4().hex[:10].upper()}"
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO signatures(signature_id,program_id,object_type,object_id,
                object_sha256,signer,meaning,reason,signed_at,signature_digest)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (signature_id, *payload.values(), digest),
            )
            self._append_audit(
                connection,
                actor=signer,
                action="electronic_signature.applied",
                object_type=object_type,
                object_id=object_id,
                reason=reason,
                payload={"signature_id": signature_id, "meaning": meaning},
            )
        return {"signature_id": signature_id, **payload, "signature_digest": digest}

    def verify_signature(self, signature_id: str, *, signing_secret: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM signatures WHERE signature_id=?", (signature_id,)
            ).fetchone()
        if row is None:
            return False
        payload = {
            key: row[key]
            for key in (
                "program_id",
                "object_type",
                "object_id",
                "object_sha256",
                "signer",
                "meaning",
                "reason",
                "signed_at",
            )
        }
        return _sha(f"{_canonical(payload)}::{signing_secret}".encode()) == row["signature_digest"]
