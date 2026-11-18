from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EXTERNAL_VALIDATION_DOMAINS: dict[str, str] = {
    "independent_clinical_evidence": "Authentic independent clinical evidence",
    "prospective_clinical_study": "Real prospective clinical study completion",
    "pharma_laboratory_validation": "Real pharmaceutical laboratory validation",
    "peer_reviewed_publication": "Peer-reviewed validation publications",
    "gxp_operating_history": "Completed GxP operating history",
    "regulatory_inspection": "Regulatory inspection history",
    "regulatory_authorization": "Regulatory authorization",
    "approved_patient_care_use": "Approved patient-care usage",
    "post_market_clinical_evidence": "Post-market clinical evidence",
}

SOURCE_TYPES = {
    "clinical_study_report",
    "laboratory_validation_report",
    "journal_article",
    "gxp_quality_record",
    "regulatory_inspection_report",
    "regulatory_authorization",
    "institutional_deployment_record",
    "post_market_report",
    "official_registry_record",
    "other_controlled_record",
}

VERIFICATION_METHODS = {
    "official_registry",
    "publisher_index",
    "authority_portal",
    "direct_issuer_confirmation",
    "onsite_audit",
    "qualified_third_party",
}

ARTIFACT_STATUSES = {"submitted", "approved", "rejected", "revoked", "expired"}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _safe_suffix(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return suffix if re.fullmatch(r"\.[a-z0-9]{1,10}", suffix) else ".bin"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


class ExternalValidationEvidenceMixin:
    """Evidence controls for real-world validation claims.

    The registry records and verifies evidence but never invents external validation.
    Test fixtures are retained for software qualification and are always excluded from
    authentic external-validation scores.
    """

    def register_external_validation_artifact(
        self,
        *,
        program_id: str,
        domain: str,
        title: str,
        source_organization: str,
        source_type: str,
        external_identifier: str,
        content: bytes,
        original_filename: str,
        mime_type: str,
        issued_at: str,
        submitted_by: str,
        independent: bool,
        jurisdiction: str = "",
        source_url: str = "",
        expires_at: str = "",
        metadata: dict[str, Any] | None = None,
        test_fixture: bool = False,
    ) -> dict[str, Any]:
        if domain not in EXTERNAL_VALIDATION_DOMAINS:
            raise ValueError(f"Unsupported external-validation domain: {domain}")
        if source_type not in SOURCE_TYPES:
            raise ValueError(f"Unsupported external evidence source type: {source_type}")
        if not content:
            raise ValueError("External evidence artifact cannot be empty")
        required = {
            "title": title,
            "source_organization": source_organization,
            "external_identifier": external_identifier,
            "issued_at": issued_at,
            "submitted_by": submitted_by,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise ValueError(f"Missing required external evidence fields: {', '.join(missing)}")

        identifier = f"XEV-{uuid.uuid4().hex[:12].upper()}"
        digest = hashlib.sha256(content).hexdigest()
        artifact_root = self.path.parent / "external_validation_artifacts" / program_id / digest[:2]
        artifact_root.mkdir(parents=True, exist_ok=True)
        stored_path = artifact_root / f"{identifier}{_safe_suffix(original_filename)}"
        stored_path.write_bytes(content)
        relative_path = stored_path.relative_to(self.path.parent).as_posix()
        now = _now()
        row = {
            "artifact_id": identifier,
            "program_id": program_id,
            "domain": domain,
            "title": title.strip(),
            "source_organization": source_organization.strip(),
            "source_type": source_type,
            "external_identifier": external_identifier.strip(),
            "source_url": source_url.strip() or None,
            "jurisdiction": jurisdiction.strip() or None,
            "independent": bool(independent),
            "artifact_sha256": digest,
            "artifact_size": len(content),
            "artifact_path": relative_path,
            "original_filename": Path(original_filename).name,
            "mime_type": mime_type.strip() or "application/octet-stream",
            "issued_at": issued_at.strip(),
            "expires_at": expires_at.strip() or None,
            "metadata": metadata or {},
            "test_fixture": bool(test_fixture),
            "status": "submitted",
            "submitted_by": submitted_by.strip(),
            "created_at": now,
            "verified_by": None,
            "verified_at": None,
            "verification_method": None,
            "verification_notes": None,
        }
        with self._connect() as connection:
            program = connection.execute(
                "SELECT 1 FROM validation_programs WHERE program_id=?", (program_id,)
            ).fetchone()
            if program is None:
                stored_path.unlink(missing_ok=True)
                raise KeyError(program_id)
            connection.execute(
                """INSERT INTO external_validation_artifacts(
                artifact_id,program_id,domain,title,source_organization,source_type,
                external_identifier,source_url,jurisdiction,independent,artifact_sha256,
                artifact_size,artifact_path,original_filename,mime_type,issued_at,expires_at,
                metadata_json,test_fixture,status,submitted_by,created_at,verified_by,verified_at,
                verification_method,verification_notes
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    identifier,
                    program_id,
                    domain,
                    row["title"],
                    row["source_organization"],
                    source_type,
                    row["external_identifier"],
                    row["source_url"],
                    row["jurisdiction"],
                    int(independent),
                    digest,
                    len(content),
                    relative_path,
                    row["original_filename"],
                    row["mime_type"],
                    row["issued_at"],
                    row["expires_at"],
                    _canonical(row["metadata"]),
                    int(test_fixture),
                    "submitted",
                    row["submitted_by"],
                    now,
                    None,
                    None,
                    None,
                    None,
                ),
            )
            self._append_audit(
                connection,
                actor=row["submitted_by"],
                action="external_validation_artifact.registered",
                object_type="external_validation_artifact",
                object_id=identifier,
                reason="Register external validation evidence",
                payload={
                    "domain": domain,
                    "source_organization": row["source_organization"],
                    "sha256": digest,
                    "test_fixture": bool(test_fixture),
                },
            )
        return row

    def review_external_validation_artifact(
        self,
        artifact_id: str,
        *,
        reviewer: str,
        status: str,
        verification_method: str,
        notes: str,
    ) -> None:
        if status not in {"approved", "rejected", "revoked", "expired"}:
            raise ValueError("Review status must be approved, rejected, revoked or expired")
        if verification_method not in VERIFICATION_METHODS:
            raise ValueError(f"Unsupported verification method: {verification_method}")
        reviewer = reviewer.strip()
        if not reviewer or not notes.strip():
            raise ValueError("Reviewer and verification notes are required")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT submitted_by,status FROM external_validation_artifacts WHERE artifact_id=?",
                (artifact_id,),
            ).fetchone()
            if row is None:
                raise KeyError(artifact_id)
            if reviewer == row["submitted_by"]:
                raise ValueError("Independent review requires a reviewer different from submitter")
            if row["status"] in {"revoked", "expired"} and status == "approved":
                raise ValueError("Revoked or expired evidence cannot be re-approved")
            connection.execute(
                """UPDATE external_validation_artifacts SET status=?,verified_by=?,verified_at=?,
                verification_method=?,verification_notes=? WHERE artifact_id=?""",
                (status, reviewer, _now(), verification_method, notes.strip(), artifact_id),
            )
            self._append_audit(
                connection,
                actor=reviewer,
                action="external_validation_artifact.reviewed",
                object_type="external_validation_artifact",
                object_id=artifact_id,
                reason=notes,
                payload={"status": status, "verification_method": verification_method},
            )

    def verify_external_artifact_integrity(self, artifact_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM external_validation_artifacts WHERE artifact_id=?", (artifact_id,)
            ).fetchone()
        if row is None:
            raise KeyError(artifact_id)
        path = self.path.parent / row["artifact_path"]
        exists = path.is_file()
        payload = path.read_bytes() if exists else b""
        digest = hashlib.sha256(payload).hexdigest() if exists else ""
        valid = (
            exists
            and len(payload) == int(row["artifact_size"])
            and digest == row["artifact_sha256"]
        )
        return {
            "artifact_id": artifact_id,
            "valid": valid,
            "exists": exists,
            "expected_sha256": row["artifact_sha256"],
            "actual_sha256": digest,
            "expected_size": int(row["artifact_size"]),
            "actual_size": len(payload),
        }
