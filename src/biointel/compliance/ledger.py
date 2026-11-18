from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from biointel.database.core import managed_connect
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .control_catalog import control_ids


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha256(value: str | bytes) -> str:
    raw = value if isinstance(value, bytes) else value.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class AuditVerification:
    valid: bool
    events: int
    first_error_sequence: int | None
    final_hash: str


class ComplianceLedger:
    """Tamper-evident local quality-system ledger.

    The implementation provides controlled records, audit trails, electronic signature
    binding, quality events, training evidence and control evidence. Deployment in a
    regulated process still requires organization-specific validation, procedures,
    identity proofing and independent quality approval.
    """

    VALID_RECORD_STATUS = {"draft", "in_review", "approved", "effective", "retired"}
    VALID_QUALITY_EVENT = {"deviation", "capa", "change_control", "incident", "complaint"}

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = managed_connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS controlled_records (
                    record_version_id TEXT PRIMARY KEY,
                    record_id TEXT NOT NULL,
                    record_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    supersedes_version_id TEXT,
                    created_at TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    approved_at TEXT,
                    approved_by TEXT,
                    UNIQUE(record_id, version),
                    FOREIGN KEY(supersedes_version_id) REFERENCES controlled_records(record_version_id)
                );
                CREATE INDEX IF NOT EXISTS idx_controlled_record_id ON controlled_records(record_id, version DESC);

                CREATE TABLE IF NOT EXISTS audit_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    object_type TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT UNIQUE NOT NULL
                );

                CREATE TABLE IF NOT EXISTS electronic_signatures (
                    signature_id TEXT PRIMARY KEY,
                    record_version_id TEXT NOT NULL,
                    signer TEXT NOT NULL,
                    meaning TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    signed_at TEXT NOT NULL,
                    record_sha256 TEXT NOT NULL,
                    signature_digest TEXT NOT NULL,
                    FOREIGN KEY(record_version_id) REFERENCES controlled_records(record_version_id)
                );

                CREATE TABLE IF NOT EXISTS quality_events (
                    quality_event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    status TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    due_at TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    closed_at TEXT
                );

                CREATE TABLE IF NOT EXISTS training_records (
                    training_id TEXT PRIMARY KEY,
                    person_id TEXT NOT NULL,
                    curriculum_id TEXT NOT NULL,
                    role_name TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    expires_at TEXT,
                    result TEXT NOT NULL,
                    evidence_sha256 TEXT NOT NULL,
                    UNIQUE(person_id, curriculum_id, completed_at)
                );

                CREATE TABLE IF NOT EXISTS control_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    control_id TEXT NOT NULL,
                    evidence_type TEXT NOT NULL,
                    reference TEXT NOT NULL,
                    evidence_sha256 TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    reviewed_by TEXT,
                    reviewed_at TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def _append_audit(
        self,
        connection: sqlite3.Connection,
        *,
        actor: str,
        action: str,
        object_type: str,
        object_id: str,
        reason: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        previous = connection.execute(
            "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous_hash = str(previous[0]) if previous else "0" * 64
        event = {
            "event_id": uuid.uuid4().hex,
            "actor": actor.strip(),
            "action": action.strip(),
            "object_type": object_type.strip(),
            "object_id": object_id.strip(),
            "reason": reason.strip(),
            "payload": payload or {},
            "created_at": utc_now(),
            "previous_hash": previous_hash,
        }
        event_hash = _sha256(_canonical(event))
        connection.execute(
            """
            INSERT INTO audit_events(
                event_id, actor, action, object_type, object_id, reason,
                payload_json, created_at, previous_hash, event_hash
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                event["event_id"], event["actor"], event["action"], event["object_type"],
                event["object_id"], event["reason"], _canonical(event["payload"]),
                event["created_at"], previous_hash, event_hash,
            ),
        )
        return {**event, "event_hash": event_hash}

    def create_record(
        self,
        *,
        record_type: str,
        title: str,
        payload: dict[str, Any],
        actor: str,
        reason: str = "Initial controlled record",
        record_id: str | None = None,
    ) -> dict[str, Any]:
        logical_id = record_id or uuid.uuid4().hex
        version_id = uuid.uuid4().hex
        payload_json = _canonical(payload)
        row = {
            "record_version_id": version_id,
            "record_id": logical_id,
            "record_type": record_type.strip(),
            "title": title.strip(),
            "version": 1,
            "status": "draft",
            "payload": payload,
            "content_sha256": _sha256(payload_json),
            "supersedes_version_id": None,
            "created_at": utc_now(),
            "created_by": actor.strip(),
        }
        with self._connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM controlled_records WHERE record_id=?", (logical_id,)
            ).fetchone()
            if exists:
                raise ValueError("record_id already exists; use revise_record")
            connection.execute(
                """
                INSERT INTO controlled_records(
                    record_version_id, record_id, record_type, title, version, status,
                    payload_json, content_sha256, supersedes_version_id, created_at, created_by
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    version_id, logical_id, row["record_type"], row["title"], 1, "draft",
                    payload_json, row["content_sha256"], None, row["created_at"], row["created_by"],
                ),
            )
            self._append_audit(
                connection, actor=actor, action="record.created", object_type=record_type,
                object_id=version_id, reason=reason, payload={"record_id": logical_id, "version": 1},
            )
        return row

    def get_record(self, record_version_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM controlled_records WHERE record_version_id=?", (record_version_id,)
            ).fetchone()
        if row is None:
            raise KeyError(record_version_id)
        data = dict(row)
        data["payload"] = json.loads(data.pop("payload_json"))
        return data

    def revise_record(
        self,
        record_version_id: str,
        *,
        payload: dict[str, Any],
        actor: str,
        reason: str,
    ) -> dict[str, Any]:
        current = self.get_record(record_version_id)
        payload_json = _canonical(payload)
        new_version_id = uuid.uuid4().hex
        version = int(current["version"]) + 1
        created_at = utc_now()
        content_sha256 = _sha256(payload_json)
        with self._connect() as connection:
            latest = connection.execute(
                "SELECT MAX(version) FROM controlled_records WHERE record_id=?", (current["record_id"],)
            ).fetchone()[0]
            if int(latest) != int(current["version"]):
                raise ValueError("Only the latest controlled-record version can be revised")
            connection.execute(
                """
                INSERT INTO controlled_records(
                    record_version_id, record_id, record_type, title, version, status,
                    payload_json, content_sha256, supersedes_version_id, created_at, created_by
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    new_version_id, current["record_id"], current["record_type"], current["title"],
                    version, "draft", payload_json, content_sha256, record_version_id, created_at, actor,
                ),
            )
            self._append_audit(
                connection, actor=actor, action="record.revised", object_type=current["record_type"],
                object_id=new_version_id, reason=reason,
                payload={"record_id": current["record_id"], "version": version, "supersedes": record_version_id},
            )
        return self.get_record(new_version_id)

    def set_record_status(
        self,
        record_version_id: str,
        *,
        status: str,
        actor: str,
        reason: str,
    ) -> dict[str, Any]:
        if status not in self.VALID_RECORD_STATUS:
            raise ValueError(f"Unsupported status: {status}")
        current = self.get_record(record_version_id)
        with self._connect() as connection:
            connection.execute(
                "UPDATE controlled_records SET status=? WHERE record_version_id=?",
                (status, record_version_id),
            )
            self._append_audit(
                connection, actor=actor, action="record.status_changed",
                object_type=current["record_type"], object_id=record_version_id,
                reason=reason, payload={"from": current["status"], "to": status},
            )
        return self.get_record(record_version_id)

    @staticmethod
    def _signature_message(
        *, record_version_id: str, signer: str, meaning: str, reason: str,
        signed_at: str, record_sha256: str,
    ) -> str:
        return _canonical({
            "record_version_id": record_version_id,
            "signer": signer,
            "meaning": meaning,
            "reason": reason,
            "signed_at": signed_at,
            "record_sha256": record_sha256,
        })

    def approve_record(
        self,
        record_version_id: str,
        *,
        signer: str,
        meaning: str,
        reason: str,
        signing_secret: str,
    ) -> dict[str, Any]:
        if len(signing_secret) < 16:
            raise ValueError("A signing secret of at least 16 characters is required")
        record = self.get_record(record_version_id)
        if record["status"] == "retired":
            raise ValueError("A retired record cannot be approved")
        signed_at = utc_now()
        message = self._signature_message(
            record_version_id=record_version_id, signer=signer, meaning=meaning,
            reason=reason, signed_at=signed_at, record_sha256=record["content_sha256"],
        )
        digest = hmac.new(signing_secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
        signature_id = uuid.uuid4().hex
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO electronic_signatures(
                    signature_id, record_version_id, signer, meaning, reason,
                    signed_at, record_sha256, signature_digest
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    signature_id, record_version_id, signer, meaning, reason,
                    signed_at, record["content_sha256"], digest,
                ),
            )
            connection.execute(
                """
                UPDATE controlled_records
                SET status='approved', approved_at=?, approved_by=?
                WHERE record_version_id=?
                """,
                (signed_at, signer, record_version_id),
            )
            self._append_audit(
                connection, actor=signer, action="record.signed",
                object_type=record["record_type"], object_id=record_version_id,
                reason=reason, payload={"signature_id": signature_id, "meaning": meaning},
            )
        return {
            "signature_id": signature_id,
            "record_version_id": record_version_id,
            "signer": signer,
            "meaning": meaning,
            "reason": reason,
            "signed_at": signed_at,
            "record_sha256": record["content_sha256"],
            "signature_digest": digest,
        }

    def verify_signature(self, signature_id: str, *, signing_secret: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM electronic_signatures WHERE signature_id=?", (signature_id,)
            ).fetchone()
            if row is None:
                return False
            record = connection.execute(
                "SELECT content_sha256 FROM controlled_records WHERE record_version_id=?",
                (row["record_version_id"],),
            ).fetchone()
        if record is None or record["content_sha256"] != row["record_sha256"]:
            return False
        message = self._signature_message(
            record_version_id=row["record_version_id"], signer=row["signer"],
            meaning=row["meaning"], reason=row["reason"], signed_at=row["signed_at"],
            record_sha256=row["record_sha256"],
        )
        expected = hmac.new(
            signing_secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, row["signature_digest"])

    def open_quality_event(
        self,
        *,
        event_type: str,
        title: str,
        severity: str,
        owner: str,
        payload: dict[str, Any],
        actor: str,
        due_at: str | None = None,
    ) -> dict[str, Any]:
        if event_type not in self.VALID_QUALITY_EVENT:
            raise ValueError(f"Unsupported quality event type: {event_type}")
        event_id = uuid.uuid4().hex
        created_at = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO quality_events(
                    quality_event_id, event_type, title, severity, status,
                    owner, due_at, payload_json, created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (event_id, event_type, title, severity, "open", owner, due_at, _canonical(payload), created_at),
            )
            self._append_audit(
                connection, actor=actor, action=f"{event_type}.opened",
                object_type="quality_event", object_id=event_id,
                reason=title, payload={"severity": severity, "owner": owner},
            )
        return {
            "quality_event_id": event_id, "event_type": event_type, "title": title,
            "severity": severity, "status": "open", "owner": owner,
            "due_at": due_at, "payload": payload, "created_at": created_at,
        }

    def close_quality_event(
        self, quality_event_id: str, *, actor: str, reason: str,
        effectiveness_verified: bool,
    ) -> dict[str, Any]:
        if not effectiveness_verified:
            raise ValueError("Effectiveness must be verified before closure")
        closed_at = utc_now()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM quality_events WHERE quality_event_id=?", (quality_event_id,)
            ).fetchone()
            if row is None:
                raise KeyError(quality_event_id)
            connection.execute(
                "UPDATE quality_events SET status='closed', closed_at=? WHERE quality_event_id=?",
                (closed_at, quality_event_id),
            )
            self._append_audit(
                connection, actor=actor, action=f"{row['event_type']}.closed",
                object_type="quality_event", object_id=quality_event_id,
                reason=reason, payload={"effectiveness_verified": True},
            )
        return {"quality_event_id": quality_event_id, "status": "closed", "closed_at": closed_at}

    def record_training(
        self,
        *,
        person_id: str,
        curriculum_id: str,
        role_name: str,
        completed_at: str,
        result: str,
        evidence: bytes,
        actor: str,
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        training_id = uuid.uuid4().hex
        evidence_sha256 = _sha256(evidence)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO training_records(
                    training_id, person_id, curriculum_id, role_name, completed_at,
                    expires_at, result, evidence_sha256
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (training_id, person_id, curriculum_id, role_name, completed_at, expires_at, result, evidence_sha256),
            )
            self._append_audit(
                connection, actor=actor, action="training.recorded", object_type="training",
                object_id=training_id, reason=f"{curriculum_id}: {result}",
                payload={"person_id": person_id, "role_name": role_name, "evidence_sha256": evidence_sha256},
            )
        return {
            "training_id": training_id, "person_id": person_id,
            "curriculum_id": curriculum_id, "role_name": role_name,
            "completed_at": completed_at, "expires_at": expires_at,
            "result": result, "evidence_sha256": evidence_sha256,
        }

    def add_control_evidence(
        self,
        *,
        control_id: str,
        evidence_type: str,
        reference: str,
        content: bytes,
        owner: str,
        status: str = "draft",
        reviewed_by: str | None = None,
    ) -> dict[str, Any]:
        if control_id not in control_ids():
            raise ValueError(f"Unknown control_id: {control_id}")
        if status not in {"draft", "reviewed", "approved", "rejected"}:
            raise ValueError("Unsupported control-evidence status")
        evidence_id = uuid.uuid4().hex
        created_at = utc_now()
        reviewed_at = utc_now() if reviewed_by else None
        digest = _sha256(content)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO control_evidence(
                    evidence_id, control_id, evidence_type, reference, evidence_sha256,
                    owner, reviewed_by, reviewed_at, status, created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (evidence_id, control_id, evidence_type, reference, digest, owner, reviewed_by, reviewed_at, status, created_at),
            )
            self._append_audit(
                connection, actor=owner, action="control.evidence_added",
                object_type="control_evidence", object_id=evidence_id,
                reason=control_id, payload={"status": status, "evidence_sha256": digest},
            )
        return {
            "evidence_id": evidence_id, "control_id": control_id, "evidence_type": evidence_type,
            "reference": reference, "evidence_sha256": digest, "owner": owner,
            "reviewed_by": reviewed_by, "reviewed_at": reviewed_at, "status": status,
            "created_at": created_at,
        }

    def verify_audit_chain(self) -> AuditVerification:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM audit_events ORDER BY sequence").fetchall()
        previous_hash = "0" * 64
        for row in rows:
            event = {
                "event_id": row["event_id"], "actor": row["actor"], "action": row["action"],
                "object_type": row["object_type"], "object_id": row["object_id"],
                "reason": row["reason"], "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"], "previous_hash": row["previous_hash"],
            }
            expected = _sha256(_canonical(event))
            if row["previous_hash"] != previous_hash or row["event_hash"] != expected:
                return AuditVerification(False, len(rows), int(row["sequence"]), previous_hash)
            previous_hash = row["event_hash"]
        return AuditVerification(True, len(rows), None, previous_hash)

    def snapshot(self) -> dict[str, Any]:
        with self._connect() as connection:
            counts = {
                "record_versions": connection.execute("SELECT COUNT(*) FROM controlled_records").fetchone()[0],
                "approved_records": connection.execute("SELECT COUNT(*) FROM controlled_records WHERE status IN ('approved','effective')").fetchone()[0],
                "electronic_signatures": connection.execute("SELECT COUNT(*) FROM electronic_signatures").fetchone()[0],
                "open_quality_events": connection.execute("SELECT COUNT(*) FROM quality_events WHERE status='open'").fetchone()[0],
                "closed_quality_events": connection.execute("SELECT COUNT(*) FROM quality_events WHERE status='closed'").fetchone()[0],
                "training_records": connection.execute("SELECT COUNT(*) FROM training_records").fetchone()[0],
                "approved_control_evidence": connection.execute("SELECT COUNT(*) FROM control_evidence WHERE status='approved'").fetchone()[0],
                "covered_controls": connection.execute("SELECT COUNT(DISTINCT control_id) FROM control_evidence WHERE status='approved'").fetchone()[0],
            }
        audit = self.verify_audit_chain()
        return {**counts, "audit": asdict(audit), "control_catalog_size": len(control_ids())}
