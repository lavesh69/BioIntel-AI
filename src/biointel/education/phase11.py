from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import io
import json
import os
import secrets
import shutil
import smtplib
import sqlite3
import tempfile
import zipfile
import ssl
import statistics
import struct
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except ImportError:
    class InvalidToken(Exception): pass
    class Fernet:
        def __init__(self, key): self.key = key
        def encrypt(self, data): return data
        def decrypt(self, data): return data
    class Cipher: pass
    class algorithms:
        class AES:
            def __init__(self, key): pass
    class modes:
        class GCM:
            def __init__(self, iv, tag=None): pass

from .phase7 import EducationPhase7Service, _pin_hash, _token_hash
from .platform import Conflict, Denied, EducationError, Missing, ident, now, parse_time

MIGRATION_ID = "education_phase11_mega_core_v1"

SCHEMA = r"""
CREATE TABLE IF NOT EXISTS education_mfa_enrollments(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 user_id TEXT NOT NULL,
 method TEXT NOT NULL DEFAULT 'totp',
 secret_cipher TEXT NOT NULL,
 enabled INTEGER NOT NULL DEFAULT 0,
 verified_at TEXT,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,user_id,method)
);
CREATE TABLE IF NOT EXISTS education_mfa_recovery_codes(
 id TEXT PRIMARY KEY,
 enrollment_id TEXT NOT NULL REFERENCES education_mfa_enrollments(id) ON DELETE CASCADE,
 code_hash TEXT NOT NULL,
 used_at TEXT,
 created_at TEXT NOT NULL,
 UNIQUE(enrollment_id,code_hash)
);
CREATE TABLE IF NOT EXISTS education_auth_challenges(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 user_id TEXT NOT NULL,
 token_hash TEXT NOT NULL UNIQUE,
 device_label TEXT NOT NULL DEFAULT 'BioIntel Desktop',
 state TEXT NOT NULL DEFAULT 'pending',
 attempts INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL,
 expires_at TEXT NOT NULL,
 completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_education_auth_challenges_user
 ON education_auth_challenges(institution_id,user_id,state,expires_at);

CREATE TABLE IF NOT EXISTS education_security_events(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL DEFAULT '',
 actor_id TEXT NOT NULL DEFAULT '',
 event_type TEXT NOT NULL,
 severity TEXT NOT NULL DEFAULT 'info',
 source TEXT NOT NULL DEFAULT 'education',
 detail_json TEXT NOT NULL DEFAULT '{}',
 previous_hash TEXT NOT NULL DEFAULT '',
 event_hash TEXT NOT NULL UNIQUE,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_education_security_events_tenant
 ON education_security_events(institution_id,created_at,event_type);
CREATE TABLE IF NOT EXISTS education_rate_limit_buckets(
 bucket_key TEXT PRIMARY KEY,
 window_started_at TEXT NOT NULL,
 request_count INTEGER NOT NULL DEFAULT 0,
 updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_question_banks(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 subject_id TEXT REFERENCES subjects(id),
 name TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '',
 visibility TEXT NOT NULL DEFAULT 'restricted',
 state TEXT NOT NULL DEFAULT 'active',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_question_banks_tenant
 ON education_question_banks(institution_id,subject_id,state);
CREATE TABLE IF NOT EXISTS education_questions(
 id TEXT PRIMARY KEY,
 bank_id TEXT NOT NULL REFERENCES education_question_banks(id) ON DELETE CASCADE,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 subject_id TEXT REFERENCES subjects(id),
 question_type TEXT NOT NULL,
 title TEXT NOT NULL,
 body TEXT NOT NULL,
 options_json TEXT NOT NULL DEFAULT '[]',
 answer_json TEXT NOT NULL DEFAULT '{}',
 explanation TEXT NOT NULL DEFAULT '',
 bloom_level TEXT NOT NULL DEFAULT 'understand',
 difficulty TEXT NOT NULL DEFAULT 'medium',
 outcome_code TEXT NOT NULL DEFAULT '',
 marks REAL NOT NULL DEFAULT 1,
 negative_marks REAL NOT NULL DEFAULT 0,
 language TEXT NOT NULL DEFAULT 'English',
 state TEXT NOT NULL DEFAULT 'draft',
 current_version INTEGER NOT NULL DEFAULT 1,
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_questions_search
 ON education_questions(institution_id,subject_id,state,bloom_level,difficulty);
CREATE TABLE IF NOT EXISTS education_question_versions(
 id TEXT PRIMARY KEY,
 question_id TEXT NOT NULL REFERENCES education_questions(id) ON DELETE CASCADE,
 version INTEGER NOT NULL,
 snapshot_json TEXT NOT NULL,
 changed_by TEXT NOT NULL,
 change_reason TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 UNIQUE(question_id,version)
);
CREATE TABLE IF NOT EXISTS education_question_reviews(
 id TEXT PRIMARY KEY,
 question_id TEXT NOT NULL REFERENCES education_questions(id) ON DELETE CASCADE,
 reviewer_id TEXT NOT NULL,
 decision TEXT NOT NULL,
 comments TEXT NOT NULL DEFAULT '',
 reviewed_version INTEGER NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS education_question_exposures(
 id TEXT PRIMARY KEY,
 question_id TEXT NOT NULL REFERENCES education_questions(id),
 exam_id TEXT NOT NULL DEFAULT '',
 student_id TEXT NOT NULL DEFAULT '',
 exposed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS education_question_responses(
 id TEXT PRIMARY KEY,
 question_id TEXT NOT NULL REFERENCES education_questions(id),
 exam_id TEXT NOT NULL DEFAULT '',
 student_id TEXT NOT NULL,
 is_correct INTEGER NOT NULL,
 marks_awarded REAL NOT NULL DEFAULT 0,
 response_seconds REAL NOT NULL DEFAULT 0,
 option_key TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_question_responses_analysis
 ON education_question_responses(question_id,exam_id,is_correct);

CREATE TABLE IF NOT EXISTS education_grade_schemes(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 subject_id TEXT REFERENCES subjects(id),
 name TEXT NOT NULL,
 calculation_mode TEXT NOT NULL DEFAULT 'weighted',
 state TEXT NOT NULL DEFAULT 'active',
 locked INTEGER NOT NULL DEFAULT 0,
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS education_grade_categories(
 id TEXT PRIMARY KEY,
 scheme_id TEXT NOT NULL REFERENCES education_grade_schemes(id) ON DELETE CASCADE,
 name TEXT NOT NULL,
 source_type TEXT NOT NULL,
 weight_percent REAL NOT NULL,
 drop_lowest INTEGER NOT NULL DEFAULT 0,
 position INTEGER NOT NULL DEFAULT 0,
 UNIQUE(scheme_id,name)
);
CREATE TABLE IF NOT EXISTS education_grade_bands(
 id TEXT PRIMARY KEY,
 scheme_id TEXT NOT NULL REFERENCES education_grade_schemes(id) ON DELETE CASCADE,
 label TEXT NOT NULL,
 minimum_percent REAL NOT NULL,
 grade_points REAL NOT NULL DEFAULT 0,
 position INTEGER NOT NULL DEFAULT 0,
 UNIQUE(scheme_id,label)
);
CREATE TABLE IF NOT EXISTS education_grade_calculations(
 id TEXT PRIMARY KEY,
 scheme_id TEXT NOT NULL REFERENCES education_grade_schemes(id),
 student_id TEXT NOT NULL,
 percentage REAL NOT NULL,
 grade_label TEXT NOT NULL,
 grade_points REAL NOT NULL DEFAULT 0,
 evidence_json TEXT NOT NULL DEFAULT '{}',
 calculated_by TEXT NOT NULL,
 created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_transcript_entries(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 student_id TEXT NOT NULL,
 academic_year TEXT NOT NULL DEFAULT '',
 term TEXT NOT NULL DEFAULT '',
 subject_code TEXT NOT NULL,
 subject_name TEXT NOT NULL,
 credits REAL NOT NULL DEFAULT 0,
 marks_percent REAL NOT NULL,
 grade_label TEXT NOT NULL DEFAULT '',
 grade_points REAL NOT NULL DEFAULT 0,
 state TEXT NOT NULL DEFAULT 'final',
 source_ref TEXT NOT NULL DEFAULT '',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,student_id,academic_year,term,subject_code)
);
CREATE TABLE IF NOT EXISTS education_credentials(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 student_id TEXT NOT NULL,
 credential_type TEXT NOT NULL,
 title TEXT NOT NULL,
 serial_number TEXT NOT NULL UNIQUE,
 payload_json TEXT NOT NULL,
 payload_hash TEXT NOT NULL,
 signature TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'active',
 issued_by TEXT NOT NULL,
 issued_at TEXT NOT NULL,
 revoked_at TEXT,
 revocation_reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_credentials_student
 ON education_credentials(institution_id,student_id,state,issued_at);

CREATE TABLE IF NOT EXISTS education_notification_templates(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 template_key TEXT NOT NULL,
 channel TEXT NOT NULL DEFAULT 'in_app',
 subject_template TEXT NOT NULL DEFAULT '',
 body_template TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'active',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,template_key,channel)
);
CREATE TABLE IF NOT EXISTS education_notification_outbox(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 recipient_id TEXT NOT NULL,
 channel TEXT NOT NULL,
 destination TEXT NOT NULL DEFAULT '',
 subject TEXT NOT NULL DEFAULT '',
 body TEXT NOT NULL,
 payload_json TEXT NOT NULL DEFAULT '{}',
 idempotency_key TEXT NOT NULL DEFAULT '',
 priority INTEGER NOT NULL DEFAULT 50,
 state TEXT NOT NULL DEFAULT 'queued',
 attempts INTEGER NOT NULL DEFAULT 0,
 max_attempts INTEGER NOT NULL DEFAULT 3,
 available_at TEXT NOT NULL,
 locked_by TEXT NOT NULL DEFAULT '',
 lock_token TEXT NOT NULL DEFAULT '',
 last_error TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_notification_outbox_idempotency
 ON education_notification_outbox(institution_id,idempotency_key) WHERE idempotency_key<>'';
CREATE INDEX IF NOT EXISTS idx_notification_outbox_queue
 ON education_notification_outbox(state,channel,available_at,priority);
CREATE TABLE IF NOT EXISTS education_notification_deliveries(
 id TEXT PRIMARY KEY,
 outbox_id TEXT NOT NULL REFERENCES education_notification_outbox(id) ON DELETE CASCADE,
 provider_message_id TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL,
 response_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_full_backups(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 label TEXT NOT NULL,
 archive_path TEXT NOT NULL,
 sha256 TEXT NOT NULL,
 size_bytes INTEGER NOT NULL,
 state TEXT NOT NULL DEFAULT 'created',
 encrypted INTEGER NOT NULL DEFAULT 1,
 manifest_json TEXT NOT NULL DEFAULT '{}',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 verified_at TEXT,
 UNIQUE(institution_id,label)
);

CREATE TABLE IF NOT EXISTS education_report_runs(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 report_type TEXT NOT NULL,
 requested_by TEXT NOT NULL,
 parameters_json TEXT NOT NULL DEFAULT '{}',
 state TEXT NOT NULL DEFAULT 'completed',
 output_path TEXT NOT NULL DEFAULT '',
 output_format TEXT NOT NULL DEFAULT 'json',
 sha256 TEXT NOT NULL DEFAULT '',
 row_count INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL,
 completed_at TEXT
);
CREATE TABLE IF NOT EXISTS education_health_snapshots(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 database_ok INTEGER NOT NULL,
 storage_ok INTEGER NOT NULL,
 queue_pending INTEGER NOT NULL DEFAULT 0,
 queue_failed INTEGER NOT NULL DEFAULT 0,
 backup_age_hours REAL,
 detail_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS education_incidents(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 title TEXT NOT NULL,
 severity TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'open',
 summary TEXT NOT NULL DEFAULT '',
 owner_id TEXT NOT NULL DEFAULT '',
 opened_by TEXT NOT NULL,
 opened_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS education_incident_events(
 id TEXT PRIMARY KEY,
 incident_id TEXT NOT NULL REFERENCES education_incidents(id) ON DELETE CASCADE,
 actor_id TEXT NOT NULL,
 event_type TEXT NOT NULL,
 detail TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_retention_policies(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 data_class TEXT NOT NULL,
 retention_days INTEGER NOT NULL,
 action TEXT NOT NULL DEFAULT 'archive',
 legal_hold INTEGER NOT NULL DEFAULT 0,
 state TEXT NOT NULL DEFAULT 'active',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,data_class)
);
CREATE TABLE IF NOT EXISTS education_privacy_requests(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 requester_id TEXT NOT NULL,
 subject_user_id TEXT NOT NULL,
 request_type TEXT NOT NULL,
 reason TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL DEFAULT 'pending',
 decision_by TEXT NOT NULL DEFAULT '',
 decision_note TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 completed_at TEXT
);

INSERT OR IGNORE INTO education_migrations(id,applied_at)
 VALUES('education_phase11_mega_core_v1',datetime('now'));
"""

ADMIN_ROLES = {
    "platform_administrator", "institution_administrator", "principal", "dean",
    "registrar", "department_head", "examination_controller",
}
TEACHER_ROLES = ADMIN_ROLES | {
    "subject_teacher", "class_teacher", "lecturer", "professor", "assistant_professor",
    "teaching_assistant", "laboratory_instructor", "academic_mentor", "class_coordinator",
}
QUESTION_TYPES = {"single_choice", "multiple_choice", "true_false", "short_answer", "long_answer", "numeric", "matching", "ordering"}
BLOOM_LEVELS = {"remember", "understand", "apply", "analyze", "evaluate", "create"}
DIFFICULTIES = {"foundation", "easy", "medium", "hard", "advanced"}
REVIEW_DECISIONS = {"approve", "request_changes", "reject"}
SEVERITIES = {"info", "low", "medium", "high", "critical"}
NOTIFICATION_CHANNELS = {"in_app", "email", "desktop", "sms", "whatsapp"}
PRIVACY_REQUEST_TYPES = {"access", "correction", "export", "deletion", "anonymization", "consent_withdrawal"}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _b64_secret(raw: bytes) -> str:
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _totp(secret: str, *, at_time: int | None = None, digits: int = 6, period: int = 30) -> str:
    timestamp = int(time.time() if at_time is None else at_time)
    counter = timestamp // period
    padded = secret.upper() + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return f"{code:0{digits}d}"


def _verify_totp(secret: str, code: str, *, window: int = 1) -> bool:
    text = str(code).strip().replace(" ", "")
    if not text.isdigit() or len(text) != 6:
        return False
    current = int(time.time())
    return any(hmac.compare_digest(_totp(secret, at_time=current + offset * 30), text) for offset in range(-window, window + 1))


def _hash_recovery(code: str, salt: str) -> str:
    return hashlib.scrypt(code.encode("utf-8"), salt=salt.encode("utf-8"), n=2**14, r=8, p=1, dklen=32).hex()


def _render_template(template: str, context: dict[str, Any]) -> str:
    text = str(template)
    for key, value in context.items():
        text = text.replace("{{" + str(key) + "}}", str(value))
    return text


class EducationPhase11Service(EducationPhase7Service):
    """Mega production and academic core layered over Phase 10/Hotfix 1.

    All external services remain opt-in and are reported as configured, dependency-ready,
    or live-verified. The service never treats a configuration record as proof of a working
    external system.
    """

    def __init__(self, platform: Any, *, root: str | Path | None = None):
        super().__init__(platform, root=root)
        self.root = Path(root or self.root)
        self.migrate_phase11()
        self._fernet = Fernet(self._load_fernet_key())

    def migrate_phase11(self) -> str:
        with self.db.connection() as db:
            db.executescript(SCHEMA)
        return MIGRATION_ID

    def _load_fernet_key(self) -> bytes:
        folder = self.root / "education" / "secrets"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "phase11-fernet.key"
        if not path.exists():
            path.write_bytes(Fernet.generate_key())
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        key = path.read_bytes().strip()
        try:
            Fernet(key)
        except (ValueError, TypeError) as exc:
            raise EducationError("The local Phase 11 encryption key is invalid.") from exc
        return key

    def _admin(self, actor: str, institution_id: str) -> set[str]:
        roles = self._roles(actor, institution_id)
        if not roles & ADMIN_ROLES:
            raise Denied("Institution administrator permission required.")
        return roles

    def _self_or_admin(self, actor: str, institution_id: str, user_id: str) -> None:
        roles = self._roles(actor, institution_id)
        if actor != user_id and not roles & ADMIN_ROLES:
            raise Denied("Only the account owner or an institution administrator may perform this action.")

    # ---------- tamper-evident security events and rate limits ----------
    def security_event(
        self,
        institution_id: str,
        event_type: str,
        *,
        actor_id: str = "",
        severity: str = "info",
        source: str = "education",
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        sev = str(severity).lower()
        if sev not in SEVERITIES:
            raise EducationError("Unsupported security-event severity.")
        stamp = now()
        previous = self.platform._one(
            "SELECT event_hash FROM education_security_events WHERE institution_id=? ORDER BY created_at DESC,id DESC LIMIT 1",
            (institution_id,),
        )
        previous_hash = str(previous["event_hash"]) if previous else ""
        payload = _json({
            "institution_id": institution_id,
            "actor_id": actor_id,
            "event_type": str(event_type),
            "severity": sev,
            "source": str(source),
            "detail": detail or {},
            "created_at": stamp,
            "previous_hash": previous_hash,
        })
        event_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        event_id = ident("sevt")
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_security_events VALUES(?,?,?,?,?,?,?,?,?,?)",
                (event_id, institution_id, actor_id, str(event_type), sev, str(source), _json(detail or {}), previous_hash, event_hash, stamp),
            )
        return self.platform._one("SELECT * FROM education_security_events WHERE id=?", (event_id,))

    def verify_security_chain(self, actor: str, institution_id: str) -> dict[str, Any]:
        self._admin(actor, institution_id)
        rows = self.platform._all(
            "SELECT * FROM education_security_events WHERE institution_id=? ORDER BY created_at,id",
            (institution_id,),
        )
        previous_hash = ""
        failures: list[dict[str, Any]] = []
        for row in rows:
            payload = _json({
                "institution_id": row["institution_id"],
                "actor_id": row["actor_id"],
                "event_type": row["event_type"],
                "severity": row["severity"],
                "source": row["source"],
                "detail": json.loads(row["detail_json"] or "{}"),
                "created_at": row["created_at"],
                "previous_hash": row["previous_hash"],
            })
            expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            if row["previous_hash"] != previous_hash or not hmac.compare_digest(row["event_hash"], expected):
                failures.append({"id": row["id"], "reason": "chain_or_hash_mismatch"})
            previous_hash = row["event_hash"]
        return {"passed": not failures, "event_count": len(rows), "failures": failures}

    def enforce_rate_limit(self, bucket_key: str, *, limit: int = 20, window_seconds: int = 60) -> dict[str, Any]:
        if not 1 <= int(limit) <= 100_000 or not 1 <= int(window_seconds) <= 86_400:
            raise EducationError("Invalid rate-limit policy.")
        key = hashlib.sha256(str(bucket_key).encode("utf-8")).hexdigest()
        stamp = datetime.now(timezone.utc)
        with self.db.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM education_rate_limit_buckets WHERE bucket_key=?", (key,)).fetchone()
            if not row or (stamp - parse_time(row["window_started_at"])).total_seconds() >= window_seconds:
                count = 1
                db.execute(
                    "INSERT INTO education_rate_limit_buckets VALUES(?,?,?,?) ON CONFLICT(bucket_key) DO UPDATE SET window_started_at=excluded.window_started_at,request_count=1,updated_at=excluded.updated_at",
                    (key, stamp.isoformat(), count, stamp.isoformat()),
                )
            else:
                count = int(row["request_count"]) + 1
                if count > limit:
                    raise Denied("Too many requests. Try again after the current security window.")
                db.execute("UPDATE education_rate_limit_buckets SET request_count=?,updated_at=? WHERE bucket_key=?", (count, stamp.isoformat(), key))
        return {"allowed": True, "count": count, "limit": limit, "window_seconds": window_seconds}

    # ---------- real TOTP MFA and recovery codes ----------
    def begin_totp_enrollment(self, actor: str, institution_id: str, user_id: str) -> dict[str, Any]:
        self._self_or_admin(actor, institution_id, user_id)
        if not self.platform.membership(user_id, institution_id):
            raise Missing("Active institution membership not found.")
        if not self.platform._one(
            "SELECT id FROM education_identity_accounts WHERE institution_id=? AND user_id=? AND state='active'",
            (institution_id, user_id),
        ):
            raise Conflict("Enroll a local desktop identity before configuring MFA.")
        secret = _b64_secret(secrets.token_bytes(20))
        cipher = self._fernet.encrypt(secret.encode("ascii")).decode("ascii")
        stamp = now()
        enrollment_id = ident("mfa")
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_mfa_enrollments VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,user_id,method) DO UPDATE SET
                secret_cipher=excluded.secret_cipher,enabled=0,verified_at=NULL,updated_at=excluded.updated_at""",
                (enrollment_id, institution_id, user_id, "totp", cipher, 0, None, stamp, stamp),
            )
            row = db.execute(
                "SELECT id FROM education_mfa_enrollments WHERE institution_id=? AND user_id=? AND method='totp'",
                (institution_id, user_id),
            ).fetchone()
            db.execute("DELETE FROM education_mfa_recovery_codes WHERE enrollment_id=?", (row["id"],))
            enrollment_id = row["id"]
        institution = self.platform._one("SELECT name FROM institutions WHERE id=?", (institution_id,)) or {"name": "BioIntel"}
        account = self.platform._one(
            "SELECT email,user_id FROM education_identity_accounts WHERE institution_id=? AND user_id=?",
            (institution_id, user_id),
        ) or {"email": "", "user_id": user_id}
        label = account["email"] or account["user_id"]
        uri = f"otpauth://totp/{quote(str(institution['name']))}:{quote(str(label))}?secret={secret}&issuer={quote(str(institution['name']))}&algorithm=SHA1&digits=6&period=30"
        self.security_event(institution_id, "mfa_enrollment_started", actor_id=actor, severity="medium", detail={"user_id": user_id})
        return {"enrollment_id": enrollment_id, "user_id": user_id, "secret": secret, "otpauth_uri": uri, "enabled": False}

    def confirm_totp_enrollment(self, actor: str, institution_id: str, user_id: str, code: str) -> dict[str, Any]:
        self._self_or_admin(actor, institution_id, user_id)
        enrollment = self.platform._one(
            "SELECT * FROM education_mfa_enrollments WHERE institution_id=? AND user_id=? AND method='totp'",
            (institution_id, user_id),
        )
        if not enrollment:
            raise Missing("TOTP enrollment not found.")
        try:
            secret = self._fernet.decrypt(enrollment["secret_cipher"].encode("ascii")).decode("ascii")
        except (InvalidToken, ValueError) as exc:
            raise EducationError("MFA secret cannot be decrypted with the local security key.") from exc
        if not _verify_totp(secret, code):
            self.security_event(institution_id, "mfa_enrollment_failed", actor_id=actor, severity="high", detail={"user_id": user_id})
            raise Denied("Invalid authenticator code.")
        recovery_codes = [secrets.token_hex(5).upper() for _ in range(10)]
        stamp = now()
        with self.db.connection() as db:
            db.execute("UPDATE education_mfa_enrollments SET enabled=1,verified_at=?,updated_at=? WHERE id=?", (stamp, stamp, enrollment["id"]))
            db.execute("DELETE FROM education_mfa_recovery_codes WHERE enrollment_id=?", (enrollment["id"],))
            for recovery in recovery_codes:
                db.execute(
                    "INSERT INTO education_mfa_recovery_codes VALUES(?,?,?,?,?)",
                    (ident("rcv"), enrollment["id"], _hash_recovery(recovery, enrollment["id"]), None, stamp),
                )
        self.security_event(institution_id, "mfa_enabled", actor_id=actor, severity="medium", detail={"user_id": user_id})
        return {"enabled": True, "user_id": user_id, "recovery_codes": recovery_codes}

    def disable_mfa(self, actor: str, institution_id: str, user_id: str, *, reason: str) -> dict[str, Any]:
        self._self_or_admin(actor, institution_id, user_id)
        if not str(reason).strip():
            raise EducationError("A reason is required to disable MFA.")
        enrollment = self.platform._one(
            "SELECT * FROM education_mfa_enrollments WHERE institution_id=? AND user_id=? AND enabled=1",
            (institution_id, user_id),
        )
        if not enrollment:
            raise Missing("Enabled MFA enrollment not found.")
        stamp = now()
        with self.db.connection() as db:
            db.execute("UPDATE education_mfa_enrollments SET enabled=0,updated_at=? WHERE id=?", (stamp, enrollment["id"]))
            db.execute("DELETE FROM education_mfa_recovery_codes WHERE enrollment_id=?", (enrollment["id"],))
        self.security_event(institution_id, "mfa_disabled", actor_id=actor, severity="high", detail={"user_id": user_id, "reason": str(reason)[:500]})
        return {"enabled": False, "user_id": user_id}

    def _verify_credentials_without_session(self, institution_id: str, login: str, pin: str) -> dict[str, Any]:
        key = str(login).strip().lower()
        account = self.platform._one(
            "SELECT * FROM education_identity_accounts WHERE institution_id=? AND state='active' AND (lower(user_id)=? OR lower(email)=?)",
            (institution_id, key, key),
        )
        if not account:
            raise Denied("Invalid sign-in credentials.")
        stamp = datetime.now(timezone.utc)
        if account["locked_until"] and parse_time(account["locked_until"]) > stamp:
            raise Denied("Account temporarily locked after repeated failed attempts.")
        expected = _pin_hash(str(pin), account["pin_salt"])
        if not hmac.compare_digest(expected, account["pin_hash"]):
            failed = int(account["failed_attempts"]) + 1
            locked_until = (stamp + timedelta(minutes=15)).isoformat() if failed >= 5 else None
            with self.db.connection() as db:
                db.execute("UPDATE education_identity_accounts SET failed_attempts=?,locked_until=?,updated_at=? WHERE id=?", (failed, locked_until, stamp.isoformat(), account["id"]))
            self.security_event(institution_id, "sign_in_failed", actor_id=account["user_id"], severity="high", detail={"failed_attempts": failed, "locked": bool(locked_until)})
            raise Denied("Invalid sign-in credentials.")
        with self.db.connection() as db:
            db.execute("UPDATE education_identity_accounts SET failed_attempts=0,locked_until=NULL,updated_at=? WHERE id=?", (stamp.isoformat(), account["id"]))
        return account

    def _create_desktop_session(self, institution_id: str, user_id: str, device_label: str, hours: int = 12) -> dict[str, Any]:
        token = secrets.token_urlsafe(48)
        stamp = datetime.now(timezone.utc)
        expires = stamp + timedelta(hours=max(1, min(168, int(hours))))
        session_id = ident("session")
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_desktop_sessions VALUES(?,?,?,?,?,?,?,?,?,?)",
                (session_id, institution_id, user_id, _token_hash(token), str(device_label)[:200], "active", stamp.isoformat(), stamp.isoformat(), expires.isoformat(), None),
            )
        roles = sorted({row["role"] for row in self.platform.membership(user_id, institution_id)})
        return {"status": "authenticated", "token": token, "session_id": session_id, "institution_id": institution_id, "user_id": user_id, "roles": roles, "expires_at": expires.isoformat(), "mfa_verified": True}

    def begin_secure_authentication(self, institution_id: str, login: str, pin: str, *, device_label: str = "BioIntel Desktop") -> dict[str, Any]:
        self.enforce_rate_limit(f"auth:{institution_id}:{str(login).lower()}", limit=10, window_seconds=300)
        account = self._verify_credentials_without_session(institution_id, login, pin)
        enrollment = self.platform._one(
            "SELECT * FROM education_mfa_enrollments WHERE institution_id=? AND user_id=? AND enabled=1",
            (institution_id, account["user_id"]),
        )
        if not enrollment:
            result = self._create_desktop_session(institution_id, account["user_id"], device_label)
            result["mfa_verified"] = False
            self.security_event(institution_id, "sign_in_completed_without_mfa", actor_id=account["user_id"], severity="medium")
            return result
        challenge_token = secrets.token_urlsafe(40)
        stamp = datetime.now(timezone.utc)
        expires = stamp + timedelta(minutes=5)
        challenge_id = ident("challenge")
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_auth_challenges VALUES(?,?,?,?,?,?,?,?,?,?)",
                (challenge_id, institution_id, account["user_id"], _token_hash(challenge_token), str(device_label)[:200], "pending", 0, stamp.isoformat(), expires.isoformat(), None),
            )
        self.security_event(institution_id, "mfa_challenge_created", actor_id=account["user_id"], severity="info")
        return {"status": "mfa_required", "challenge_token": challenge_token, "expires_at": expires.isoformat(), "methods": ["totp", "recovery_code"]}

    def complete_secure_authentication(self, challenge_token: str, *, code: str = "", recovery_code: str = "") -> dict[str, Any]:
        token_hash = _token_hash(str(challenge_token))
        challenge = self.platform._one("SELECT * FROM education_auth_challenges WHERE token_hash=?", (token_hash,))
        if not challenge or challenge["state"] != "pending":
            raise Denied("Authentication challenge is invalid or already used.")
        if parse_time(challenge["expires_at"]) <= datetime.now(timezone.utc):
            with self.db.connection() as db:
                db.execute("UPDATE education_auth_challenges SET state='expired' WHERE id=?", (challenge["id"],))
            raise Denied("Authentication challenge expired.")
        if int(challenge["attempts"]) >= 5:
            raise Denied("Authentication challenge locked after repeated failures.")
        enrollment = self.platform._one(
            "SELECT * FROM education_mfa_enrollments WHERE institution_id=? AND user_id=? AND enabled=1",
            (challenge["institution_id"], challenge["user_id"]),
        )
        if not enrollment:
            raise Conflict("MFA enrollment is no longer active.")
        passed = False
        used_recovery_id = ""
        if code:
            try:
                secret = self._fernet.decrypt(enrollment["secret_cipher"].encode("ascii")).decode("ascii")
                passed = _verify_totp(secret, code)
            except (InvalidToken, ValueError):
                passed = False
        elif recovery_code:
            code_hash = _hash_recovery(str(recovery_code).strip().upper(), enrollment["id"])
            recovery = self.platform._one(
                "SELECT * FROM education_mfa_recovery_codes WHERE enrollment_id=? AND code_hash=? AND used_at IS NULL",
                (enrollment["id"], code_hash),
            )
            if recovery:
                passed = True
                used_recovery_id = recovery["id"]
        if not passed:
            with self.db.connection() as db:
                db.execute("UPDATE education_auth_challenges SET attempts=attempts+1 WHERE id=?", (challenge["id"],))
            self.security_event(challenge["institution_id"], "mfa_challenge_failed", actor_id=challenge["user_id"], severity="high")
            raise Denied("Invalid MFA or recovery code.")
        stamp = now()
        with self.db.connection() as db:
            db.execute("UPDATE education_auth_challenges SET state='completed',completed_at=? WHERE id=?", (stamp, challenge["id"]))
            if used_recovery_id:
                db.execute("UPDATE education_mfa_recovery_codes SET used_at=? WHERE id=?", (stamp, used_recovery_id))
        result = self._create_desktop_session(challenge["institution_id"], challenge["user_id"], challenge["device_label"])
        self.security_event(challenge["institution_id"], "mfa_sign_in_completed", actor_id=challenge["user_id"], severity="info", detail={"recovery_code_used": bool(used_recovery_id)})
        return result

    def mfa_posture(self, actor: str, institution_id: str) -> dict[str, Any]:
        self._admin(actor, institution_id)
        rows = self.platform._all(
            """SELECT a.user_id,a.display_name,a.email,a.state,COALESCE(m.enabled,0) mfa_enabled,m.verified_at,
            (SELECT COUNT(*) FROM education_mfa_recovery_codes r WHERE r.enrollment_id=m.id AND r.used_at IS NULL) recovery_codes
            FROM education_identity_accounts a
            LEFT JOIN education_mfa_enrollments m ON m.institution_id=a.institution_id AND m.user_id=a.user_id AND m.method='totp'
            WHERE a.institution_id=? ORDER BY a.display_name,a.user_id""",
            (institution_id,),
        )
        enabled = sum(int(row["mfa_enabled"]) for row in rows)
        return {"accounts": rows, "total": len(rows), "enabled": enabled, "coverage_percent": round(100 * enabled / len(rows), 2) if rows else 0.0}

    # ---------- governed question bank ----------
    def create_question_bank(self, actor: str, institution_id: str, name: str, *, subject_id: str | None = None, description: str = "", visibility: str = "restricted") -> dict[str, Any]:
        roles = self._roles(actor, institution_id)
        if not roles & TEACHER_ROLES:
            raise Denied("Teaching or academic-administration access required.")
        if subject_id:
            self._staff_subject(actor, institution_id, subject_id)
        if visibility not in {"restricted", "institution", "department"}:
            raise EducationError("Unsupported question-bank visibility.")
        if not str(name).strip():
            raise EducationError("Question-bank name is required.")
        bank_id = ident("qbank")
        stamp = now()
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_question_banks VALUES(?,?,?,?,?,?,?,?,?,?)",
                (bank_id, institution_id, subject_id, str(name).strip()[:240], str(description)[:20_000], visibility, "active", actor, stamp, stamp),
            )
        self.platform._audit(actor, "question_bank_created", "question_bank", bank_id, institution_id, {"subject_id": subject_id, "visibility": visibility})
        return self.platform._one("SELECT * FROM education_question_banks WHERE id=?", (bank_id,))

    def _question_snapshot(self, row: dict[str, Any]) -> dict[str, Any]:
        return {key: row[key] for key in (
            "question_type", "title", "body", "options_json", "answer_json", "explanation",
            "bloom_level", "difficulty", "outcome_code", "marks", "negative_marks", "language", "state",
        ) if key in row}

    def create_question(
        self,
        actor: str,
        bank_id: str,
        *,
        question_type: str,
        title: str,
        body: str,
        options: list[Any] | None = None,
        answer: Any = None,
        explanation: str = "",
        bloom_level: str = "understand",
        difficulty: str = "medium",
        outcome_code: str = "",
        marks: float = 1,
        negative_marks: float = 0,
        language: str = "English",
    ) -> dict[str, Any]:
        bank = self.platform._one("SELECT * FROM education_question_banks WHERE id=? AND state='active'", (bank_id,))
        if not bank:
            raise Missing("Active question bank not found.")
        self._staff_subject(actor, bank["institution_id"], bank["subject_id"]) if bank["subject_id"] else self._admin(actor, bank["institution_id"])
        qtype = str(question_type).lower()
        if qtype not in QUESTION_TYPES:
            raise EducationError("Unsupported question type.")
        bloom = str(bloom_level).lower()
        difficulty_value = str(difficulty).lower()
        if bloom not in BLOOM_LEVELS or difficulty_value not in DIFFICULTIES:
            raise EducationError("Unsupported Bloom level or difficulty.")
        if not str(body).strip() or not str(title).strip():
            raise EducationError("Question title and body are required.")
        max_marks = float(marks)
        negative = float(negative_marks)
        if max_marks <= 0 or negative < 0 or negative > max_marks:
            raise EducationError("Question marks or negative marks are invalid.")
        if qtype in {"single_choice", "multiple_choice"} and len(options or []) < 2:
            raise EducationError("Choice questions require at least two options.")
        question_id = ident("question")
        stamp = now()
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_questions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (question_id, bank_id, bank["institution_id"], bank["subject_id"], qtype, str(title).strip()[:500], str(body).strip(), _json(options or []), _json(answer), str(explanation), bloom, difficulty_value, str(outcome_code)[:120], max_marks, negative, str(language)[:80], "draft", 1, actor, stamp, stamp),
            )
            row = dict(db.execute("SELECT * FROM education_questions WHERE id=?", (question_id,)).fetchone())
            db.execute(
                "INSERT INTO education_question_versions VALUES(?,?,?,?,?,?,?)",
                (ident("qver"), question_id, 1, _json(self._question_snapshot(row)), actor, "Initial question", stamp),
            )
        self.platform._audit(actor, "question_created", "question", question_id, bank["institution_id"], {"bank_id": bank_id, "question_type": qtype})
        return self.platform._one("SELECT * FROM education_questions WHERE id=?", (question_id,))

    def revise_question(self, actor: str, question_id: str, changes: dict[str, Any], *, reason: str) -> dict[str, Any]:
        question = self.platform._one("SELECT * FROM education_questions WHERE id=?", (question_id,))
        if not question:
            raise Missing("Question not found.")
        if question["state"] == "retired":
            raise Conflict("Retired questions cannot be revised.")
        self._staff_subject(actor, question["institution_id"], question["subject_id"]) if question["subject_id"] else self._admin(actor, question["institution_id"])
        if not str(reason).strip():
            raise EducationError("Question revision reason is required.")
        allowed = {"title", "body", "options", "answer", "explanation", "bloom_level", "difficulty", "outcome_code", "marks", "negative_marks", "language"}
        unknown = set(changes) - allowed
        if unknown:
            raise EducationError(f"Unsupported question fields: {', '.join(sorted(unknown))}")
        current = dict(question)
        if "options" in changes:
            current["options_json"] = _json(changes["options"])
        if "answer" in changes:
            current["answer_json"] = _json(changes["answer"])
        for key in allowed - {"options", "answer"}:
            if key in changes:
                current[key] = changes[key]
        if str(current["bloom_level"]).lower() not in BLOOM_LEVELS or str(current["difficulty"]).lower() not in DIFFICULTIES:
            raise EducationError("Unsupported Bloom level or difficulty.")
        if float(current["marks"]) <= 0 or not 0 <= float(current["negative_marks"]) <= float(current["marks"]):
            raise EducationError("Question marks are invalid.")
        version = int(question["current_version"]) + 1
        stamp = now()
        with self.db.connection() as db:
            db.execute(
                """UPDATE education_questions SET title=?,body=?,options_json=?,answer_json=?,explanation=?,bloom_level=?,difficulty=?,outcome_code=?,marks=?,negative_marks=?,language=?,state='draft',current_version=?,updated_at=? WHERE id=?""",
                (str(current["title"])[:500], str(current["body"]), str(current["options_json"]), str(current["answer_json"]), str(current["explanation"]), str(current["bloom_level"]).lower(), str(current["difficulty"]).lower(), str(current["outcome_code"])[:120], float(current["marks"]), float(current["negative_marks"]), str(current["language"])[:80], version, stamp, question_id),
            )
            updated = dict(db.execute("SELECT * FROM education_questions WHERE id=?", (question_id,)).fetchone())
            db.execute(
                "INSERT INTO education_question_versions VALUES(?,?,?,?,?,?,?)",
                (ident("qver"), question_id, version, _json(self._question_snapshot(updated)), actor, str(reason)[:1000], stamp),
            )
        self.platform._audit(actor, "question_revised", "question", question_id, question["institution_id"], {"version": version, "reason": str(reason)[:500]})
        return self.platform._one("SELECT * FROM education_questions WHERE id=?", (question_id,))

    def review_question(self, actor: str, question_id: str, decision: str, *, comments: str = "") -> dict[str, Any]:
        question = self.platform._one("SELECT * FROM education_questions WHERE id=?", (question_id,))
        if not question:
            raise Missing("Question not found.")
        roles = self._roles(actor, question["institution_id"])
        if not roles & (ADMIN_ROLES | {"content_moderator", "professor", "department_head"}):
            raise Denied("Question-review permission required.")
        if actor == question["created_by"] and not roles & ADMIN_ROLES:
            raise Denied("Question authors cannot self-approve their own questions.")
        value = str(decision).lower()
        if value not in REVIEW_DECISIONS:
            raise EducationError("Unsupported review decision.")
        state = "approved" if value == "approve" else ("changes_requested" if value == "request_changes" else "rejected")
        stamp = now()
        review_id = ident("qreview")
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_question_reviews VALUES(?,?,?,?,?,?,?)",
                (review_id, question_id, actor, value, str(comments)[:20_000], int(question["current_version"]), stamp),
            )
            db.execute("UPDATE education_questions SET state=?,updated_at=? WHERE id=?", (state, stamp, question_id))
        self.platform._audit(actor, "question_reviewed", "question", question_id, question["institution_id"], {"decision": value, "version": question["current_version"]})
        return self.platform._one("SELECT * FROM education_questions WHERE id=?", (question_id,))

    def publish_question(self, actor: str, question_id: str) -> dict[str, Any]:
        question = self.platform._one("SELECT * FROM education_questions WHERE id=?", (question_id,))
        if not question:
            raise Missing("Question not found.")
        roles = self._roles(actor, question["institution_id"])
        if not roles & ADMIN_ROLES:
            raise Denied("Academic administrator permission required to publish questions.")
        review = self.platform._one(
            "SELECT * FROM education_question_reviews WHERE question_id=? AND decision='approve' AND reviewed_version=? ORDER BY created_at DESC LIMIT 1",
            (question_id, int(question["current_version"])),
        )
        if not review:
            raise Conflict("The current question version must be independently approved before publication.")
        stamp = now()
        with self.db.connection() as db:
            db.execute("UPDATE education_questions SET state='published',updated_at=? WHERE id=?", (stamp, question_id))
        self.platform._audit(actor, "question_published", "question", question_id, question["institution_id"], {"review_id": review["id"]})
        return self.platform._one("SELECT * FROM education_questions WHERE id=?", (question_id,))

    def question_catalog(self, actor: str, institution_id: str, *, subject_id: str | None = None, state: str | None = None, bloom_level: str | None = None, difficulty: str | None = None, search: str = "") -> list[dict[str, Any]]:
        roles = self._roles(actor, institution_id)
        if not roles & TEACHER_ROLES:
            raise Denied("Question-bank access requires teaching or academic-administration permission.")
        clauses = ["q.institution_id=?"]
        params: list[Any] = [institution_id]
        for column, value in (("q.subject_id", subject_id), ("q.state", state), ("q.bloom_level", bloom_level), ("q.difficulty", difficulty)):
            if value:
                clauses.append(f"{column}=?")
                params.append(value)
        if search:
            clauses.append("(lower(q.title) LIKE ? OR lower(q.body) LIKE ? OR lower(q.outcome_code) LIKE ?)")
            needle = f"%{str(search).lower()}%"
            params.extend([needle, needle, needle])
        return self.platform._all(
            "SELECT q.*,b.name bank_name FROM education_questions q JOIN education_question_banks b ON b.id=q.bank_id WHERE " + " AND ".join(clauses) + " ORDER BY q.updated_at DESC LIMIT 1000",
            tuple(params),
        )

    def generate_question_blueprint(self, actor: str, institution_id: str, *, subject_id: str, total_marks: float, bloom_distribution: dict[str, float], difficulty_distribution: dict[str, float]) -> dict[str, Any]:
        self._staff_subject(actor, institution_id, subject_id)
        total = float(total_marks)
        if total <= 0:
            raise EducationError("Total marks must be greater than zero.")
        for mapping, valid, label in ((bloom_distribution, BLOOM_LEVELS, "Bloom"), (difficulty_distribution, DIFFICULTIES, "difficulty")):
            if not mapping or set(mapping) - valid:
                raise EducationError(f"Invalid {label} distribution.")
            if abs(sum(float(value) for value in mapping.values()) - 100.0) > 0.5:
                raise EducationError(f"{label.title()} distribution must total 100 percent.")
        questions = self.platform._all(
            "SELECT id,title,marks,bloom_level,difficulty,outcome_code FROM education_questions WHERE institution_id=? AND subject_id=? AND state='published' ORDER BY updated_at DESC",
            (institution_id, subject_id),
        )
        if not questions:
            raise Conflict("No published questions are available for this subject.")
        remaining_bloom = {key: total * float(value) / 100.0 for key, value in bloom_distribution.items()}
        remaining_difficulty = {key: total * float(value) / 100.0 for key, value in difficulty_distribution.items()}
        selected: list[dict[str, Any]] = []
        marks_selected = 0.0
        ranked = sorted(
            questions,
            key=lambda q: (
                remaining_bloom.get(q["bloom_level"], 0) + remaining_difficulty.get(q["difficulty"], 0),
                -float(q["marks"]),
            ),
            reverse=True,
        )
        for question in ranked:
            marks = float(question["marks"])
            if marks_selected + marks > total + 1e-9:
                continue
            if remaining_bloom.get(question["bloom_level"], 0) <= -marks / 2 or remaining_difficulty.get(question["difficulty"], 0) <= -marks / 2:
                continue
            selected.append(question)
            marks_selected += marks
            remaining_bloom[question["bloom_level"]] = remaining_bloom.get(question["bloom_level"], 0) - marks
            remaining_difficulty[question["difficulty"]] = remaining_difficulty.get(question["difficulty"], 0) - marks
            if abs(marks_selected - total) < 1e-9:
                break
        return {
            "subject_id": subject_id,
            "requested_marks": total,
            "selected_marks": round(marks_selected, 4),
            "complete": abs(marks_selected - total) < 1e-9,
            "questions": selected,
            "remaining_bloom_marks": {key: round(value, 3) for key, value in remaining_bloom.items()},
            "remaining_difficulty_marks": {key: round(value, 3) for key, value in remaining_difficulty.items()},
        }

    def record_question_response(self, actor: str, question_id: str, student_id: str, *, is_correct: bool, marks_awarded: float, response_seconds: float = 0, exam_id: str = "", option_key: str = "") -> dict[str, Any]:
        question = self.platform._one("SELECT * FROM education_questions WHERE id=?", (question_id,))
        if not question:
            raise Missing("Question not found.")
        roles = self._roles(actor, question["institution_id"])
        if actor != student_id and not roles & TEACHER_ROLES:
            raise Denied("Question-response evidence access denied.")
        if not 0 <= float(marks_awarded) <= float(question["marks"]):
            raise EducationError("Marks awarded are outside the question range.")
        response_id = ident("qresp")
        stamp = now()
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_question_responses VALUES(?,?,?,?,?,?,?,?,?)",
                (response_id, question_id, str(exam_id), student_id, int(bool(is_correct)), float(marks_awarded), max(0.0, float(response_seconds)), str(option_key)[:200], stamp),
            )
        return self.platform._one("SELECT * FROM education_question_responses WHERE id=?", (response_id,))

    def question_item_analysis(self, actor: str, question_id: str, *, exam_id: str = "") -> dict[str, Any]:
        question = self.platform._one("SELECT * FROM education_questions WHERE id=?", (question_id,))
        if not question:
            raise Missing("Question not found.")
        roles = self._roles(actor, question["institution_id"])
        if not roles & TEACHER_ROLES:
            raise Denied("Academic analytics permission required.")
        params: list[Any] = [question_id]
        clause = "question_id=?"
        if exam_id:
            clause += " AND exam_id=?"
            params.append(exam_id)
        rows = self.platform._all(f"SELECT * FROM education_question_responses WHERE {clause}", tuple(params))
        if not rows:
            return {"question_id": question_id, "attempts": 0, "difficulty_index": None, "average_marks": None, "average_seconds": None, "distractors": {}}
        correct = sum(int(row["is_correct"]) for row in rows)
        distractors: dict[str, int] = {}
        for row in rows:
            key = str(row["option_key"] or "unclassified")
            distractors[key] = distractors.get(key, 0) + 1
        return {
            "question_id": question_id,
            "attempts": len(rows),
            "difficulty_index": round(correct / len(rows), 4),
            "average_marks": round(statistics.fmean(float(row["marks_awarded"]) for row in rows), 4),
            "average_seconds": round(statistics.fmean(float(row["response_seconds"]) for row in rows), 3),
            "distractors": distractors,
            "human_review_required": len(rows) < 30,
        }

    # ---------- institutional grade policies ----------
    def create_grade_scheme(self, actor: str, institution_id: str, name: str, *, subject_id: str | None, categories: list[dict[str, Any]], bands: list[dict[str, Any]]) -> dict[str, Any]:
        self._admin(actor, institution_id)
        if subject_id:
            self.platform._subject(institution_id, subject_id)
        if not str(name).strip():
            raise EducationError("Grade-scheme name is required.")
        weights = sum(float(item.get("weight_percent", 0)) for item in categories)
        if abs(weights - 100.0) > 0.01:
            raise EducationError("Grade category weights must total 100 percent.")
        if not bands:
            raise EducationError("At least one grade band is required.")
        minimums = [float(item.get("minimum_percent", -1)) for item in bands]
        if any(value < 0 or value > 100 for value in minimums) or len(set(minimums)) != len(minimums):
            raise EducationError("Grade-band minimum percentages must be unique values from 0 to 100.")
        scheme_id = ident("gscheme")
        stamp = now()
        with self.db.connection() as db:
            db.execute("INSERT INTO education_grade_schemes VALUES(?,?,?,?,?,?,?,?,?,?)", (scheme_id, institution_id, subject_id, str(name).strip()[:240], "weighted", "active", 0, actor, stamp, stamp))
            for position, item in enumerate(categories):
                source_type = str(item.get("source_type", "assignment"))
                if source_type not in {"assignment", "examination", "laboratory", "participation", "manual"}:
                    raise EducationError("Unsupported grade category source type.")
                db.execute(
                    "INSERT INTO education_grade_categories VALUES(?,?,?,?,?,?,?)",
                    (ident("gcat"), scheme_id, str(item.get("name", source_type)).strip()[:160], source_type, float(item["weight_percent"]), max(0, int(item.get("drop_lowest", 0))), position),
                )
            for position, item in enumerate(sorted(bands, key=lambda value: float(value["minimum_percent"]), reverse=True)):
                db.execute(
                    "INSERT INTO education_grade_bands VALUES(?,?,?,?,?,?)",
                    (ident("gband"), scheme_id, str(item["label"]).strip()[:40], float(item["minimum_percent"]), float(item.get("grade_points", 0)), position),
                )
        self.platform._audit(actor, "grade_scheme_created", "grade_scheme", scheme_id, institution_id, {"subject_id": subject_id})
        return self.grade_scheme(actor, scheme_id)

    def grade_scheme(self, actor: str, scheme_id: str) -> dict[str, Any]:
        scheme = self.platform._one("SELECT * FROM education_grade_schemes WHERE id=?", (scheme_id,))
        if not scheme:
            raise Missing("Grade scheme not found.")
        self._roles(actor, scheme["institution_id"])
        scheme["categories"] = self.platform._all("SELECT * FROM education_grade_categories WHERE scheme_id=? ORDER BY position", (scheme_id,))
        scheme["bands"] = self.platform._all("SELECT * FROM education_grade_bands WHERE scheme_id=? ORDER BY minimum_percent DESC", (scheme_id,))
        return scheme

    def calculate_grade(self, actor: str, scheme_id: str, student_id: str, scores: dict[str, list[float] | float]) -> dict[str, Any]:
        scheme = self.grade_scheme(actor, scheme_id)
        roles = self._roles(actor, scheme["institution_id"])
        if actor != student_id and not roles & TEACHER_ROLES:
            raise Denied("Student grade calculation access denied.")
        evidence: dict[str, Any] = {}
        weighted = 0.0
        for category in scheme["categories"]:
            raw = scores.get(category["name"], [])
            values = [float(raw)] if isinstance(raw, (int, float)) else [float(value) for value in raw]
            if any(value < 0 or value > 100 for value in values):
                raise EducationError("Category scores must be percentages from 0 to 100.")
            drop = min(max(0, int(category["drop_lowest"])), max(0, len(values) - 1))
            kept = sorted(values)[drop:] if values else []
            category_percent = statistics.fmean(kept) if kept else 0.0
            contribution = category_percent * float(category["weight_percent"]) / 100.0
            weighted += contribution
            evidence[category["name"]] = {"scores": values, "kept": kept, "category_percent": round(category_percent, 4), "weight_percent": category["weight_percent"], "contribution": round(contribution, 4)}
        percentage = max(0.0, min(100.0, weighted))
        chosen = next((band for band in scheme["bands"] if percentage >= float(band["minimum_percent"])), scheme["bands"][-1])
        calculation_id = ident("gcalc")
        stamp = now()
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_grade_calculations VALUES(?,?,?,?,?,?,?,?,?)",
                (calculation_id, scheme_id, student_id, percentage, chosen["label"], float(chosen["grade_points"]), _json(evidence), actor, stamp),
            )
        return {"id": calculation_id, "scheme_id": scheme_id, "student_id": student_id, "percentage": round(percentage, 4), "grade_label": chosen["label"], "grade_points": chosen["grade_points"], "evidence": evidence}

    # ---------- transcript and signed credentials ----------
    def upsert_transcript_entry(self, actor: str, institution_id: str, student_id: str, *, academic_year: str, term: str, subject_code: str, subject_name: str, credits: float, marks_percent: float, grade_label: str = "", grade_points: float = 0, source_ref: str = "") -> dict[str, Any]:
        self._admin(actor, institution_id)
        if not self.platform.membership(student_id, institution_id):
            raise Missing("Student membership not found.")
        if not 0 <= float(marks_percent) <= 100 or float(credits) < 0 or float(grade_points) < 0:
            raise EducationError("Transcript marks, credits or grade points are invalid.")
        stamp = now()
        entry_id = ident("transcript")
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_transcript_entries VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,student_id,academic_year,term,subject_code) DO UPDATE SET
                subject_name=excluded.subject_name,credits=excluded.credits,marks_percent=excluded.marks_percent,
                grade_label=excluded.grade_label,grade_points=excluded.grade_points,state='final',source_ref=excluded.source_ref,
                created_by=excluded.created_by,updated_at=excluded.updated_at""",
                (entry_id, institution_id, student_id, str(academic_year)[:40], str(term)[:80], str(subject_code)[:80], str(subject_name)[:300], float(credits), float(marks_percent), str(grade_label)[:40], float(grade_points), "final", str(source_ref)[:300], actor, stamp, stamp),
            )
        self.platform._audit(actor, "transcript_entry_saved", "student", student_id, institution_id, {"subject_code": subject_code, "term": term})
        return self.platform._one(
            "SELECT * FROM education_transcript_entries WHERE institution_id=? AND student_id=? AND academic_year=? AND term=? AND subject_code=?",
            (institution_id, student_id, str(academic_year), str(term), str(subject_code)),
        )

    def transcript(self, actor: str, institution_id: str, student_id: str) -> dict[str, Any]:
        roles = self._roles(actor, institution_id)
        if actor != student_id and not roles & TEACHER_ROLES and not self.platform._guardian_can(actor, institution_id, student_id):
            raise Denied("Transcript access denied.")
        rows = self.platform._all(
            "SELECT * FROM education_transcript_entries WHERE institution_id=? AND student_id=? AND state='final' ORDER BY academic_year,term,subject_code",
            (institution_id, student_id),
        )
        credits = sum(float(row["credits"]) for row in rows)
        weighted_points = sum(float(row["credits"]) * float(row["grade_points"]) for row in rows)
        cgpa = weighted_points / credits if credits else 0.0
        return {"institution_id": institution_id, "student_id": student_id, "entries": rows, "total_credits": round(credits, 4), "cgpa": round(cgpa, 4)}

    def issue_credential(self, actor: str, institution_id: str, student_id: str, *, credential_type: str, title: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        self._admin(actor, institution_id)
        if not self.platform.membership(student_id, institution_id):
            raise Missing("Student membership not found.")
        serial = f"BIO-{datetime.now(timezone.utc):%Y%m%d}-{secrets.token_hex(6).upper()}"
        issued_at = now()
        payload = {
            "institution_id": institution_id,
            "student_id": student_id,
            "credential_type": str(credential_type)[:80],
            "title": str(title)[:300],
            "serial_number": serial,
            "issued_at": issued_at,
            "evidence": evidence or {},
        }
        payload_json = _json(payload)
        payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        signature = self.platform._signature(payload_hash)
        credential_id = ident("credential")
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_credentials VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (credential_id, institution_id, student_id, str(credential_type)[:80], str(title)[:300], serial, payload_json, payload_hash, signature, "active", actor, issued_at, None, ""),
            )
        self.platform._audit(actor, "credential_issued", "credential", credential_id, institution_id, {"student_id": student_id, "serial_number": serial})
        return self.platform._one("SELECT * FROM education_credentials WHERE id=?", (credential_id,))

    def verify_credential(self, serial_number: str) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_credentials WHERE serial_number=?", (str(serial_number).strip(),))
        if not row:
            return {"valid": False, "reason": "not_found"}
        calculated_hash = hashlib.sha256(str(row["payload_json"]).encode("utf-8")).hexdigest()
        signature_valid = hmac.compare_digest(str(row["signature"]), self.platform._signature(calculated_hash))
        return {
            "valid": bool(signature_valid and row["state"] == "active" and hmac.compare_digest(calculated_hash, row["payload_hash"])),
            "state": row["state"],
            "serial_number": row["serial_number"],
            "payload": json.loads(row["payload_json"]),
            "issued_at": row["issued_at"],
            "revoked_at": row["revoked_at"],
            "revocation_reason": row["revocation_reason"],
            "signature_valid": signature_valid,
        }

    def revoke_credential(self, actor: str, credential_id: str, *, reason: str) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_credentials WHERE id=?", (credential_id,))
        if not row:
            raise Missing("Credential not found.")
        self._admin(actor, row["institution_id"])
        if row["state"] != "active":
            raise Conflict("Only active credentials can be revoked.")
        if not str(reason).strip():
            raise EducationError("Credential revocation reason is required.")
        stamp = now()
        with self.db.connection() as db:
            db.execute("UPDATE education_credentials SET state='revoked',revoked_at=?,revocation_reason=? WHERE id=?", (stamp, str(reason)[:1000], credential_id))
        self.platform._audit(actor, "credential_revoked", "credential", credential_id, row["institution_id"], {"reason": str(reason)[:500]})
        return self.platform._one("SELECT * FROM education_credentials WHERE id=?", (credential_id,))

    # ---------- governed notification outbox ----------
    def save_notification_template(self, actor: str, institution_id: str, template_key: str, *, channel: str, subject_template: str = "", body_template: str) -> dict[str, Any]:
        self._admin(actor, institution_id)
        channel_value = str(channel).lower()
        if channel_value not in NOTIFICATION_CHANNELS:
            raise EducationError("Unsupported notification channel.")
        if not str(template_key).strip() or not str(body_template).strip():
            raise EducationError("Template key and body are required.")
        template_id = ident("ntpl")
        stamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_notification_templates VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,template_key,channel) DO UPDATE SET
                subject_template=excluded.subject_template,body_template=excluded.body_template,state='active',created_by=excluded.created_by,updated_at=excluded.updated_at""",
                (template_id, institution_id, str(template_key)[:120], channel_value, str(subject_template)[:500], str(body_template)[:100_000], "active", actor, stamp, stamp),
            )
        return self.platform._one(
            "SELECT * FROM education_notification_templates WHERE institution_id=? AND template_key=? AND channel=?",
            (institution_id, str(template_key)[:120], channel_value),
        )

    def queue_notification(self, actor: str, institution_id: str, recipient_id: str, *, channel: str = "in_app", destination: str = "", template_key: str = "", subject: str = "", body: str = "", context: dict[str, Any] | None = None, payload: dict[str, Any] | None = None, idempotency_key: str = "", priority: int = 50, available_at: str | None = None) -> dict[str, Any]:
        roles = self._roles(actor, institution_id)
        if actor != recipient_id and not roles & TEACHER_ROLES:
            raise Denied("Notification creation permission required.")
        channel_value = str(channel).lower()
        if channel_value not in NOTIFICATION_CHANNELS:
            raise EducationError("Unsupported notification channel.")
        context_value = context or {}
        if template_key:
            template = self.platform._one(
                "SELECT * FROM education_notification_templates WHERE institution_id=? AND template_key=? AND channel=? AND state='active'",
                (institution_id, str(template_key), channel_value),
            )
            if not template:
                raise Missing("Notification template not found.")
            subject = _render_template(template["subject_template"], context_value)
            body = _render_template(template["body_template"], context_value)
        if not str(body).strip():
            raise EducationError("Notification body is required.")
        if channel_value in {"email", "sms", "whatsapp"} and not str(destination).strip():
            raise EducationError("External notification channels require a destination.")
        available = parse_time(available_at).isoformat() if available_at else now()
        outbox_id = ident("nout")
        stamp = now()
        try:
            with self.db.connection() as db:
                db.execute(
                    "INSERT INTO education_notification_outbox VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (outbox_id, institution_id, recipient_id, channel_value, str(destination)[:500], str(subject)[:500], str(body), _json(payload or {}), str(idempotency_key)[:200], max(0, min(100, int(priority))), "queued", 0, 3, available, "", "", "", stamp, stamp),
                )
        except Exception as exc:
            if idempotency_key and "UNIQUE" in str(exc).upper():
                existing = self.platform._one(
                    "SELECT * FROM education_notification_outbox WHERE institution_id=? AND idempotency_key=?",
                    (institution_id, str(idempotency_key)[:200]),
                )
                if existing:
                    return existing
            raise
        return self.platform._one("SELECT * FROM education_notification_outbox WHERE id=?", (outbox_id,))

    def claim_notification(self, worker_id: str, *, channel: str = "in_app") -> dict[str, Any] | None:
        if not str(worker_id).strip():
            raise EducationError("Worker ID is required.")
        channel_value = str(channel).lower()
        stamp = now()
        with self.db.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM education_notification_outbox WHERE state='queued' AND channel=? AND available_at<=? ORDER BY priority DESC,created_at LIMIT 1",
                (channel_value, stamp),
            ).fetchone()
            if not row:
                return None
            token = secrets.token_urlsafe(24)
            db.execute(
                "UPDATE education_notification_outbox SET state='processing',locked_by=?,lock_token=?,attempts=attempts+1,updated_at=? WHERE id=? AND state='queued'",
                (str(worker_id)[:200], token, stamp, row["id"]),
            )
            claimed = db.execute("SELECT * FROM education_notification_outbox WHERE id=?", (row["id"],)).fetchone()
        result = dict(claimed)
        result["lock_token_plain"] = token
        return result

    def complete_notification(self, worker_id: str, outbox_id: str, lock_token: str, *, state: str = "delivered", provider_message_id: str = "", response: dict[str, Any] | None = None, error_text: str = "") -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_notification_outbox WHERE id=?", (outbox_id,))
        if not row or row["state"] != "processing" or row["locked_by"] != worker_id or not hmac.compare_digest(str(row["lock_token"]), str(lock_token)):
            raise Denied("Notification worker lock does not match.")
        final_state = str(state).lower()
        if final_state not in {"delivered", "failed"}:
            raise EducationError("Notification completion state must be delivered or failed.")
        stamp = now()
        with self.db.connection() as db:
            if final_state == "failed" and int(row["attempts"]) < int(row["max_attempts"]):
                db.execute(
                    "UPDATE education_notification_outbox SET state='queued',available_at=?,locked_by='',lock_token='',last_error=?,updated_at=? WHERE id=?",
                    ((datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(), str(error_text)[:4000], stamp, outbox_id),
                )
            else:
                db.execute(
                    "UPDATE education_notification_outbox SET state=?,locked_by='',lock_token='',last_error=?,updated_at=? WHERE id=?",
                    (final_state, str(error_text)[:4000], stamp, outbox_id),
                )
            db.execute(
                "INSERT INTO education_notification_deliveries VALUES(?,?,?,?,?,?)",
                (ident("ndel"), outbox_id, str(provider_message_id)[:500], final_state, _json(response or {"error": error_text}), stamp),
            )
        return self.platform._one("SELECT * FROM education_notification_outbox WHERE id=?", (outbox_id,))

    def deliver_smtp_notification(self, worker_id: str, outbox_id: str, lock_token: str, *, host: str, port: int, username: str = "", password_env: str = "", sender: str, use_tls: bool = True, timeout: int = 20) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_notification_outbox WHERE id=?", (outbox_id,))
        if not row or row["channel"] != "email":
            raise Missing("Email notification not found.")
        if row["state"] != "processing" or row["locked_by"] != worker_id or not hmac.compare_digest(str(row["lock_token"]), str(lock_token)):
            raise Denied("Notification worker lock does not match.")
        password = os.environ.get(str(password_env), "") if password_env else ""
        message = EmailMessage()
        message["From"] = sender
        message["To"] = row["destination"]
        message["Subject"] = row["subject"]
        message.set_content(row["body"])
        try:
            if use_tls:
                context = ssl.create_default_context()
                with smtplib.SMTP(str(host), int(port), timeout=int(timeout)) as client:
                    client.ehlo()
                    client.starttls(context=context)
                    client.ehlo()
                    if username:
                        client.login(username, password)
                    client.send_message(message)
            else:
                with smtplib.SMTP(str(host), int(port), timeout=int(timeout)) as client:
                    if username:
                        client.login(username, password)
                    client.send_message(message)
        except Exception as exc:
            self.complete_notification(worker_id, outbox_id, lock_token, state="failed", error_text=f"{type(exc).__name__}: {exc}")
            raise EducationError(f"SMTP delivery failed: {type(exc).__name__}") from exc
        return self.complete_notification(worker_id, outbox_id, lock_token, state="delivered", response={"transport": "smtp", "host": host, "port": int(port)})

    def notification_operations(self, actor: str, institution_id: str) -> dict[str, Any]:
        self._admin(actor, institution_id)
        states = self.platform._all(
            "SELECT state,channel,COUNT(*) count FROM education_notification_outbox WHERE institution_id=? GROUP BY state,channel ORDER BY state,channel",
            (institution_id,),
        )
        recent = self.platform._all(
            "SELECT id,recipient_id,channel,subject,state,attempts,last_error,created_at,updated_at FROM education_notification_outbox WHERE institution_id=? ORDER BY created_at DESC LIMIT 100",
            (institution_id,),
        )
        return {"states": states, "recent": recent}

    # ---------- encrypted full backup and restore rehearsal ----------
    def _backup_key(self) -> bytes:
        key = self._load_fernet_key()
        raw = base64.urlsafe_b64decode(key)
        if len(raw) != 32:
            raise EducationError("Phase 11 backup encryption key is invalid.")
        return raw

    def _encrypt_file(self, source: Path, destination: Path) -> dict[str, str]:
        nonce = secrets.token_bytes(12)
        encryptor = Cipher(algorithms.AES(self._backup_key()), modes.GCM(nonce)).encryptor()
        digest = hashlib.sha256()
        with source.open("rb") as inp, destination.open("wb") as out:
            header = b"BIOINTEL11-AESGCM\x00" + nonce
            out.write(header)
            digest.update(header)
            while chunk := inp.read(1024 * 1024):
                encrypted = encryptor.update(chunk)
                out.write(encrypted)
                digest.update(encrypted)
            final = encryptor.finalize()
            if final:
                out.write(final)
                digest.update(final)
            out.write(encryptor.tag)
            digest.update(encryptor.tag)
        return {"sha256": digest.hexdigest(), "nonce": base64.b64encode(nonce).decode("ascii"), "tag": base64.b64encode(encryptor.tag).decode("ascii")}

    def _decrypt_file(self, source: Path, destination: Path) -> None:
        header_len = len(b"BIOINTEL11-AESGCM\x00")
        with source.open("rb") as inp:
            header = inp.read(header_len)
            if header != b"BIOINTEL11-AESGCM\x00":
                raise EducationError("Backup encryption header is invalid.")
            nonce = inp.read(12)
            if len(nonce) != 12:
                raise EducationError("Backup nonce is missing.")
            total = source.stat().st_size
            encrypted_size = total - header_len - 12 - 16
            if encrypted_size < 0:
                raise EducationError("Backup archive is truncated.")
            inp.seek(total - 16)
            tag = inp.read(16)
            inp.seek(header_len + 12)
            decryptor = Cipher(algorithms.AES(self._backup_key()), modes.GCM(nonce, tag)).decryptor()
            remaining = encrypted_size
            with destination.open("wb") as out:
                while remaining:
                    chunk = inp.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise EducationError("Backup archive ended unexpectedly.")
                    remaining -= len(chunk)
                    out.write(decryptor.update(chunk))
                out.write(decryptor.finalize())

    def create_full_backup(self, actor: str, institution_id: str, label: str) -> dict[str, Any]:
        self._admin(actor, institution_id)
        safe_label = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in str(label).strip()).strip("-.") or "snapshot"
        if self.platform._one("SELECT id FROM education_full_backups WHERE institution_id=? AND label=?", (institution_id, safe_label)):
            raise Conflict("A full backup with this label already exists.")
        backup_dir = self.root / "education" / "full-backups" / institution_id
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_id = ident("fullbackup")
        temp_dir = Path(tempfile.mkdtemp(prefix="biointel-phase11-backup-"))
        plain_zip = temp_dir / "payload.zip"
        database_copy = temp_dir / "education.sqlite3"
        source_db = sqlite3.connect(self.db.path, timeout=30)
        target_db = sqlite3.connect(database_copy)
        try:
            source_db.backup(target_db)
        finally:
            target_db.close()
            source_db.close()
        check = sqlite3.connect(database_copy)
        try:
            if check.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise EducationError("Full backup database copy failed integrity validation.")
        finally:
            check.close()
        roots: list[tuple[str, Path]] = [
            ("media", Path(self.platform.storage) / institution_id),
            ("institution-platform", self.phase5.data_root / institution_id),
            ("reports", self.root / "education" / "reports" / institution_id),
        ]
        manifest_files: list[dict[str, Any]] = []
        with zipfile.ZipFile(plain_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
            archive.write(database_copy, "database/education.sqlite3")
            manifest_files.append({"path": "database/education.sqlite3", "size_bytes": database_copy.stat().st_size, "sha256": hashlib.sha256(database_copy.read_bytes()).hexdigest()})
            seen: set[Path] = set()
            for namespace, root in roots:
                if not root.exists():
                    continue
                for file_path in sorted(root.rglob("*")):
                    if not file_path.is_file() or file_path in seen:
                        continue
                    if "full-backups" in file_path.parts or file_path.resolve() == self.db.path.resolve():
                        continue
                    seen.add(file_path)
                    relative = f"{namespace}/{file_path.relative_to(root).as_posix()}"
                    archive.write(file_path, relative)
                    digest = hashlib.sha256()
                    with file_path.open("rb") as stream:
                        while chunk := stream.read(1024 * 1024):
                            digest.update(chunk)
                    manifest_files.append({"path": relative, "size_bytes": file_path.stat().st_size, "sha256": digest.hexdigest()})
            manifest = {
                "schema": "biointel.education-full-backup.v1",
                "backup_id": backup_id,
                "institution_id": institution_id,
                "created_at": now(),
                "file_count": len(manifest_files),
                "files": manifest_files,
                "encrypted": True,
                "algorithm": "AES-256-GCM",
            }
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2))
        destination = backup_dir / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{safe_label}.biointel-backup"
        encryption = self._encrypt_file(plain_zip, destination)
        stamp = now()
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_full_backups VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (backup_id, institution_id, safe_label, str(destination), encryption["sha256"], destination.stat().st_size, "created", 1, _json(manifest), actor, stamp, None),
            )
        shutil.rmtree(temp_dir, ignore_errors=True)
        self.platform._audit(actor, "full_backup_created", "full_backup", backup_id, institution_id, {"file_count": len(manifest_files), "encrypted": True})
        return self.verify_full_backup(actor, backup_id)

    def verify_full_backup(self, actor: str, backup_id: str) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_full_backups WHERE id=?", (backup_id,))
        if not row:
            raise Missing("Full backup not found.")
        self._admin(actor, row["institution_id"])
        source = Path(row["archive_path"])
        valid = source.is_file()
        if valid:
            digest = hashlib.sha256()
            with source.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            valid = hmac.compare_digest(digest.hexdigest(), row["sha256"])
        temp_dir = Path(tempfile.mkdtemp(prefix="biointel-phase11-verify-"))
        failure = ""
        file_count = 0
        if valid:
            try:
                plain = temp_dir / "payload.zip"
                self._decrypt_file(source, plain)
                with zipfile.ZipFile(plain, "r") as archive:
                    bad = archive.testzip()
                    if bad:
                        raise EducationError(f"ZIP member failed CRC: {bad}")
                    manifest = json.loads(archive.read("manifest.json"))
                    file_count = int(manifest.get("file_count", 0))
                    for item in manifest.get("files", []):
                        payload = archive.read(item["path"])
                        if len(payload) != int(item["size_bytes"]) or hashlib.sha256(payload).hexdigest() != item["sha256"]:
                            raise EducationError(f"Backup member mismatch: {item['path']}")
                    database_payload = archive.read("database/education.sqlite3")
                    database_path = temp_dir / "education.sqlite3"
                    database_path.write_bytes(database_payload)
                    db = sqlite3.connect(database_path)
                    try:
                        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                            raise EducationError("Backup database integrity_check failed.")
                    finally:
                        db.close()
            except Exception as exc:
                valid = False
                failure = f"{type(exc).__name__}: {exc}"
        state = "verified" if valid else "invalid"
        stamp = now()
        with self.db.connection() as db:
            db.execute("UPDATE education_full_backups SET state=?,verified_at=? WHERE id=?", (state, stamp, backup_id))
        shutil.rmtree(temp_dir, ignore_errors=True)
        result = self.platform._one("SELECT * FROM education_full_backups WHERE id=?", (backup_id,))
        result.update({"integrity_valid": valid, "file_count": file_count, "failure": failure, "live_data_replaced": False})
        return result

    def full_backup_restore_rehearsal(self, actor: str, backup_id: str) -> dict[str, Any]:
        verified = self.verify_full_backup(actor, backup_id)
        if not verified["integrity_valid"]:
            raise Conflict("Invalid full backup cannot be rehearsed.")
        source = Path(verified["archive_path"])
        rehearsal_root = source.parent / f"restore-rehearsal-{backup_id}"
        if rehearsal_root.exists():
            shutil.rmtree(rehearsal_root)
        rehearsal_root.mkdir(parents=True)
        plain = rehearsal_root / "payload.zip"
        self._decrypt_file(source, plain)
        with zipfile.ZipFile(plain, "r") as archive:
            for name in archive.namelist():
                target = (rehearsal_root / "extracted" / name).resolve()
                allowed = (rehearsal_root / "extracted").resolve()
                if allowed != target and allowed not in target.parents:
                    raise Denied("Unsafe path in backup archive.")
            archive.extractall(rehearsal_root / "extracted")
        db_path = rehearsal_root / "extracted" / "database" / "education.sqlite3"
        db = sqlite3.connect(db_path)
        try:
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
            institution_count = db.execute("SELECT COUNT(*) FROM institutions").fetchone()[0]
        finally:
            db.close()
        return {"backup_id": backup_id, "rehearsal_path": str(rehearsal_root), "integrity": integrity, "institution_count": institution_count, "live_data_replaced": False}

    # ---------- governed reports ----------
    def generate_report(self, actor: str, institution_id: str, report_type: str, *, parameters: dict[str, Any] | None = None, output_format: str = "json") -> dict[str, Any]:
        roles = self._roles(actor, institution_id)
        if not roles & TEACHER_ROLES:
            raise Denied("Report-generation permission required.")
        report = str(report_type).lower()
        fmt = str(output_format).lower()
        if fmt not in {"json", "csv"}:
            raise EducationError("Report format must be JSON or CSV.")
        params = parameters or {}
        rows: list[dict[str, Any]]
        if report == "attendance":
            rows = self.platform._all(
                """SELECT r.student_id,r.status,r.note,s.session_date,s.period,sub.code subject_code,sub.name subject_name
                FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id
                JOIN subjects sub ON sub.id=s.subject_id WHERE r.institution_id=? ORDER BY s.session_date,r.student_id""",
                (institution_id,),
            )
        elif report == "gradebook":
            rows = self.platform._all(
                """SELECT sub.student_id,a.title assignment_title,a.max_marks,g.marks,g.feedback,g.updated_at
                FROM submissions sub JOIN assignments a ON a.id=sub.assignment_id
                LEFT JOIN grades g ON g.submission_id=sub.id WHERE sub.institution_id=? ORDER BY sub.student_id,a.due_at""",
                (institution_id,),
            )
        elif report == "transcript":
            student_id = str(params.get("student_id", ""))
            if not student_id:
                raise EducationError("Transcript report requires student_id.")
            transcript = self.transcript(actor, institution_id, student_id)
            rows = transcript["entries"]
        elif report == "audit":
            if not roles & ADMIN_ROLES:
                raise Denied("Audit reports require administrator permission.")
            rows = self.platform._all(
                "SELECT actor_id,action,target_type,target_id,detail_json,created_at FROM education_audit_events WHERE institution_id=? ORDER BY created_at DESC LIMIT 10000",
                (institution_id,),
            )
        elif report == "question_bank":
            rows = self.platform._all(
                "SELECT title,question_type,bloom_level,difficulty,outcome_code,marks,state,current_version,updated_at FROM education_questions WHERE institution_id=? ORDER BY updated_at DESC",
                (institution_id,),
            )
        else:
            raise EducationError("Unsupported report type.")
        report_id = ident("report")
        folder = self.root / "education" / "reports" / institution_id
        folder.mkdir(parents=True, exist_ok=True)
        suffix = ".json" if fmt == "json" else ".csv"
        path = folder / f"{report_id}{suffix}"
        if fmt == "json":
            content = json.dumps({"report_type": report, "institution_id": institution_id, "parameters": params, "rows": rows}, ensure_ascii=False, indent=2, default=str)
        else:
            output = io.StringIO(newline="")
            fieldnames = sorted({key for row in rows for key in row}) if rows else ["no_data"]
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in fieldnames})
            content = output.getvalue()
        path.write_text(content, encoding="utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        stamp = now()
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_report_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (report_id, institution_id, report, actor, _json(params), "completed", str(path), fmt, digest, len(rows), stamp, stamp),
            )
        self.platform._audit(actor, "report_generated", "report", report_id, institution_id, {"report_type": report, "format": fmt, "row_count": len(rows)})
        return self.platform._one("SELECT * FROM education_report_runs WHERE id=?", (report_id,))

    # ---------- health monitoring and incidents ----------
    def record_health_snapshot(self, actor: str, institution_id: str) -> dict[str, Any]:
        self._admin(actor, institution_id)
        database_ok = bool(self.db.quick_check())
        storage_root = self.root / "education"
        storage_root.mkdir(parents=True, exist_ok=True)
        probe = storage_root / f".health-{secrets.token_hex(4)}"
        storage_ok = False
        try:
            probe.write_text("ok", encoding="utf-8")
            storage_ok = probe.read_text(encoding="utf-8") == "ok"
        finally:
            probe.unlink(missing_ok=True)
        pending = self.platform._one("SELECT COUNT(*) count FROM education_background_jobs WHERE institution_id=? AND state IN ('queued','running')", (institution_id,)) or {"count": 0}
        failed = self.platform._one("SELECT COUNT(*) count FROM education_background_jobs WHERE institution_id=? AND state='failed'", (institution_id,)) or {"count": 0}
        backup = self.platform._one("SELECT created_at FROM education_backup_snapshots WHERE institution_id=? AND state='verified' ORDER BY created_at DESC LIMIT 1", (institution_id,))
        backup_age = None
        if backup:
            backup_age = max(0.0, (datetime.now(timezone.utc) - parse_time(backup["created_at"])).total_seconds() / 3600)
        detail = {
            "disk_free_bytes": shutil.disk_usage(storage_root).free,
            "database_path": str(self.db.path),
            "storage_root": str(storage_root),
        }
        snapshot_id = ident("health")
        stamp = now()
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_health_snapshots VALUES(?,?,?,?,?,?,?,?,?)",
                (snapshot_id, institution_id, int(database_ok), int(storage_ok), int(pending["count"]), int(failed["count"]), backup_age, _json(detail), stamp),
            )
        if not database_ok or not storage_ok:
            self.security_event(institution_id, "health_check_failed", actor_id=actor, severity="critical", detail={"database_ok": database_ok, "storage_ok": storage_ok})
        return self.platform._one("SELECT * FROM education_health_snapshots WHERE id=?", (snapshot_id,))

    def open_incident(self, actor: str, institution_id: str, title: str, *, severity: str, summary: str = "", owner_id: str = "") -> dict[str, Any]:
        self._admin(actor, institution_id)
        severity_value = str(severity).lower()
        if severity_value not in {"low", "medium", "high", "critical"}:
            raise EducationError("Unsupported incident severity.")
        if not str(title).strip():
            raise EducationError("Incident title is required.")
        incident_id = ident("incident")
        stamp = now()
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_incidents VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (incident_id, institution_id, str(title).strip()[:300], severity_value, "open", str(summary)[:20_000], str(owner_id)[:200], actor, stamp, stamp, None),
            )
            db.execute("INSERT INTO education_incident_events VALUES(?,?,?,?,?,?)", (ident("ievent"), incident_id, actor, "opened", str(summary)[:20_000], stamp))
        self.security_event(institution_id, "incident_opened", actor_id=actor, severity=severity_value, detail={"incident_id": incident_id, "title": title})
        return self.incident(actor, incident_id)

    def update_incident(self, actor: str, incident_id: str, *, status: str, detail: str = "", owner_id: str | None = None) -> dict[str, Any]:
        incident = self.platform._one("SELECT * FROM education_incidents WHERE id=?", (incident_id,))
        if not incident:
            raise Missing("Incident not found.")
        self._admin(actor, incident["institution_id"])
        status_value = str(status).lower()
        if status_value not in {"open", "investigating", "mitigated", "resolved"}:
            raise EducationError("Unsupported incident status.")
        stamp = now()
        with self.db.connection() as db:
            db.execute(
                "UPDATE education_incidents SET status=?,owner_id=COALESCE(?,owner_id),updated_at=?,resolved_at=? WHERE id=?",
                (status_value, owner_id, stamp, stamp if status_value == "resolved" else None, incident_id),
            )
            db.execute("INSERT INTO education_incident_events VALUES(?,?,?,?,?,?)", (ident("ievent"), incident_id, actor, status_value, str(detail)[:20_000], stamp))
        return self.incident(actor, incident_id)

    def incident(self, actor: str, incident_id: str) -> dict[str, Any]:
        incident = self.platform._one("SELECT * FROM education_incidents WHERE id=?", (incident_id,))
        if not incident:
            raise Missing("Incident not found.")
        self._admin(actor, incident["institution_id"])
        incident["events"] = self.platform._all("SELECT * FROM education_incident_events WHERE incident_id=? ORDER BY created_at", (incident_id,))
        return incident

    def operations_posture(self, actor: str, institution_id: str) -> dict[str, Any]:
        self._admin(actor, institution_id)
        latest = self.platform._one("SELECT * FROM education_health_snapshots WHERE institution_id=? ORDER BY created_at DESC LIMIT 1", (institution_id,))
        incidents = self.platform._all("SELECT * FROM education_incidents WHERE institution_id=? ORDER BY opened_at DESC LIMIT 100", (institution_id,))
        security = self.platform._all("SELECT event_type,severity,COUNT(*) count FROM education_security_events WHERE institution_id=? GROUP BY event_type,severity ORDER BY count DESC", (institution_id,))
        notification = self.notification_operations(actor, institution_id)
        return {"latest_health": latest, "incidents": incidents, "security_summary": security, "notification_summary": notification["states"]}

    # ---------- privacy and retention governance ----------
    def save_retention_policy(self, actor: str, institution_id: str, data_class: str, *, retention_days: int, action: str = "archive", legal_hold: bool = False) -> dict[str, Any]:
        self._admin(actor, institution_id)
        if not 1 <= int(retention_days) <= 36500:
            raise EducationError("Retention days must be between 1 and 36500.")
        if action not in {"archive", "anonymize", "delete"}:
            raise EducationError("Unsupported retention action.")
        policy_id = ident("retention")
        stamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_retention_policies VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,data_class) DO UPDATE SET retention_days=excluded.retention_days,action=excluded.action,
                legal_hold=excluded.legal_hold,state='active',created_by=excluded.created_by,updated_at=excluded.updated_at""",
                (policy_id, institution_id, str(data_class)[:120], int(retention_days), action, int(bool(legal_hold)), "active", actor, stamp, stamp),
            )
        return self.platform._one("SELECT * FROM education_retention_policies WHERE institution_id=? AND data_class=?", (institution_id, str(data_class)[:120]))

    def create_privacy_request(self, actor: str, institution_id: str, subject_user_id: str, *, request_type: str, reason: str = "") -> dict[str, Any]:
        self._roles(actor, institution_id)
        value = str(request_type).lower()
        if value not in PRIVACY_REQUEST_TYPES:
            raise EducationError("Unsupported privacy request type.")
        roles = self._roles(actor, institution_id)
        if actor != subject_user_id and not roles & ADMIN_ROLES and not self.platform._guardian_can(actor, institution_id, subject_user_id):
            raise Denied("Privacy request access denied.")
        request_id = ident("privacy")
        stamp = now()
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_privacy_requests VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (request_id, institution_id, actor, subject_user_id, value, str(reason)[:5000], "pending", "", "", stamp, stamp, None),
            )
        self.platform._audit(actor, "privacy_request_created", "privacy_request", request_id, institution_id, {"subject_user_id": subject_user_id, "request_type": value})
        return self.platform._one("SELECT * FROM education_privacy_requests WHERE id=?", (request_id,))

    def decide_privacy_request(self, actor: str, request_id: str, *, state: str, note: str = "") -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_privacy_requests WHERE id=?", (request_id,))
        if not row:
            raise Missing("Privacy request not found.")
        self._admin(actor, row["institution_id"])
        value = str(state).lower()
        if value not in {"approved", "rejected", "in_progress", "completed"}:
            raise EducationError("Unsupported privacy request state.")
        stamp = now()
        with self.db.connection() as db:
            db.execute(
                "UPDATE education_privacy_requests SET state=?,decision_by=?,decision_note=?,updated_at=?,completed_at=? WHERE id=?",
                (value, actor, str(note)[:5000], stamp, stamp if value == "completed" else None, request_id),
            )
        return self.platform._one("SELECT * FROM education_privacy_requests WHERE id=?", (request_id,))

    # ---------- honest external qualification ----------
    def external_dependency_posture(self, actor: str, institution_id: str) -> dict[str, Any]:
        self._admin(actor, institution_id)
        import importlib.util
        dependencies = {
            "postgresql": {"module": "psycopg", "available": importlib.util.find_spec("psycopg") is not None},
            "s3": {"module": "boto3", "available": importlib.util.find_spec("boto3") is not None},
            "redis": {"module": "redis", "available": importlib.util.find_spec("redis") is not None},
            "celery": {"module": "celery", "available": importlib.util.find_spec("celery") is not None},
            "cryptography": {"module": "cryptography", "available": importlib.util.find_spec("cryptography") is not None},
        }
        profiles = self.phase5.database_posture(actor, institution_id)
        storage = self.platform._all("SELECT id,backend_type,name,state,endpoint,bucket,region FROM education_storage_backends WHERE institution_id=? ORDER BY created_at DESC", (institution_id,))
        integrations = self.platform._all("SELECT id,provider_type,name,state,last_tested_at,readiness_json FROM education_integrations WHERE institution_id=? ORDER BY created_at DESC", (institution_id,))
        return {
            "dependencies": dependencies,
            "database_profiles": profiles,
            "storage_profiles": storage,
            "integrations": integrations,
            "qualification_rule": "Configured is not equivalent to live verified. External credentials, network access and provider-side tests are required.",
        }
