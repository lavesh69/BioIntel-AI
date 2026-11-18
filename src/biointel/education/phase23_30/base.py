from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from cryptography.fernet import Fernet, InvalidToken

from ..phase17_22.schema import SCHEMA as PHASE17_TO_22_SCHEMA
from ..platform import Denied, EducationError, Missing, ident, now
from .schema import MIGRATION_ID, SCHEMA

ADMIN_ROLES = {
    "platform_administrator",
    "institution_administrator",
    "principal",
    "dean",
    "registrar",
    "department_head",
    "examination_controller",
}
STAFF_ROLES = ADMIN_ROLES | {
    "subject_teacher",
    "class_teacher",
    "lecturer",
    "assistant_professor",
    "professor",
    "teaching_assistant",
    "laboratory_instructor",
    "academic_mentor",
    "class_coordinator",
    "research_mentor",
    "career_counsellor",
    "laboratory_manager",
    "content_moderator",
}
STUDENT_ROLES = {
    "school_student",
    "college_student",
    "university_student",
}
MEMBER_ROLES = STAFF_ROLES | STUDENT_ROLES | {"parent_guardian", "guest_educator"}


def encode_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def decode_json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalized_key(value: str, *, maximum: int = 96) -> str:
    key = re.sub(r"[^a-z0-9._-]+", "-", str(value).strip().casefold()).strip("-._")
    if not key:
        raise EducationError("A non-empty identifier is required.")
    return key[:maximum]


def utc_datetime(value: str, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise EducationError(f"{field} must be ISO-8601.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class Phase30Base:
    def __init__(self, platform: Any, *, root: str | Path) -> None:
        self.platform = platform
        self.db = platform.db
        self.root = Path(root).resolve()
        self.storage = (Path(platform.storage) / "phase23-30").resolve()
        self.storage.mkdir(parents=True, exist_ok=True)
        key = base64.urlsafe_b64encode(hashlib.sha256(platform._signing_key).digest())
        self._cipher = Fernet(key)
        self.migrate()

    def migrate(self) -> str:
        with self.db.connection() as db:
            # Phase 23-30 publishes through the durable Phase 17-22 outbox.
            # Applying the idempotent predecessor schema also makes a direct
            # upgrade from a Phase 16 installation safe and deterministic.
            db.executescript(PHASE17_TO_22_SCHEMA)
            db.executescript(SCHEMA)
        return MIGRATION_ID

    def _one(self, sql: str, args: Iterable[Any] = ()) -> dict[str, Any] | None:
        return self.platform._one(sql, tuple(args))

    def _all(self, sql: str, args: Iterable[Any] = ()) -> list[dict[str, Any]]:
        return self.platform._all(sql, tuple(args))

    def _institution(self, institution_id: str) -> dict[str, Any]:
        row = self._one(
            "SELECT * FROM institutions WHERE id=? AND state='active'",
            (institution_id,),
        )
        if not row:
            raise Missing("Active institution not found.")
        return row

    def _roles(self, actor: str, institution_id: str) -> set[str]:
        self._institution(institution_id)
        return {
            str(row["role"])
            for row in self.platform.membership(actor, institution_id)
            if row["state"] == "active"
        }

    def _require(
        self,
        actor: str,
        institution_id: str,
        level: str = "member",
    ) -> set[str]:
        roles = self._roles(actor, institution_id)
        allowed = {
            "admin": ADMIN_ROLES,
            "staff": STAFF_ROLES,
            "student": STUDENT_ROLES,
            "member": MEMBER_ROLES,
        }.get(level)
        if allowed is None:
            raise EducationError("Unsupported authorization level.")
        if not roles.intersection(allowed):
            raise Denied(f"{level.title()} permission is required.")
        return roles

    def _tenant_row(
        self,
        table: str,
        row_id: str,
        institution_id: str | None = None,
    ) -> dict[str, Any]:
        if not re.fullmatch(r"education_p30_[a-z_]+", table):
            raise EducationError("Unsafe table reference.")
        row = self._one(f"SELECT * FROM {table} WHERE id=?", (row_id,))
        if not row:
            raise Missing("Record not found.")
        if institution_id and row.get("institution_id") != institution_id:
            raise Denied("Cross-institution record access denied.")
        return row

    def _audit(
        self,
        actor: str,
        institution_id: str,
        action: str,
        target_type: str,
        target_id: str,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        timestamp = now()
        previous = self._one(
            """SELECT event_hash FROM education_p30_audit_chain
            WHERE institution_id=? ORDER BY created_at DESC,id DESC LIMIT 1""",
            (institution_id,),
        )
        previous_hash = str(previous["event_hash"]) if previous else "0" * 64
        canonical = encode_json(
            {
                "institution_id": institution_id,
                "actor_id": actor,
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
                "detail": detail or {},
                "previous_hash": previous_hash,
                "created_at": timestamp,
            }
        )
        event_hash = sha256_bytes(canonical.encode("utf-8"))
        event_id = ident("p30aud")
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_audit_chain
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    event_id,
                    institution_id,
                    actor,
                    action,
                    target_type,
                    target_id,
                    encode_json(detail or {}),
                    previous_hash,
                    event_hash,
                    timestamp,
                ),
            )
        self.platform._audit(
            actor,
            action,
            target_type,
            target_id,
            institution_id,
            detail or {},
        )
        return self._one(
            "SELECT * FROM education_p30_audit_chain WHERE id=?",
            (event_id,),
        ) or {}

    def verify_audit_chain(self, institution_id: str) -> dict[str, Any]:
        rows = self._all(
            """SELECT * FROM education_p30_audit_chain
            WHERE institution_id=? ORDER BY created_at,id""",
            (institution_id,),
        )
        previous_hash = "0" * 64
        bad: list[str] = []
        for row in rows:
            canonical = encode_json(
                {
                    "institution_id": row["institution_id"],
                    "actor_id": row["actor_id"],
                    "action": row["action"],
                    "target_type": row["target_type"],
                    "target_id": row["target_id"],
                    "detail": decode_json(row["detail_json"], {}),
                    "previous_hash": row["previous_hash"],
                    "created_at": row["created_at"],
                }
            )
            expected = sha256_bytes(canonical.encode("utf-8"))
            if row["previous_hash"] != previous_hash or row["event_hash"] != expected:
                bad.append(str(row["id"]))
            previous_hash = str(row["event_hash"])
        return {
            "passed": not bad,
            "events": len(rows),
            "bad_event_ids": bad,
        }

    def _encrypt(self, value: str) -> str:
        return self._cipher.encrypt(str(value).encode("utf-8")).decode("ascii")

    def _decrypt(self, value: str) -> str:
        try:
            return self._cipher.decrypt(str(value).encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError) as exc:
            raise EducationError("Encrypted secret could not be read.") from exc

    def _safe_storage_path(self, *parts: str) -> Path:
        clean = [normalized_key(part, maximum=120) for part in parts]
        path = self.storage.joinpath(*clean).resolve()
        if not path.is_relative_to(self.storage):
            raise Denied("Storage path escaped the managed root.")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _copy_managed_file(
        self,
        source_path: str | Path,
        destination: Path,
        *,
        maximum_bytes: int,
        allowed_suffixes: set[str],
    ) -> dict[str, Any]:
        source = Path(source_path).expanduser().resolve()
        if not source.is_file():
            raise Missing("Source file not found.")
        if source.stat().st_size > maximum_bytes:
            raise EducationError("File exceeds the configured size limit.")
        if source.suffix.casefold() not in allowed_suffixes:
            raise EducationError("File type is not allowed.")
        destination = destination.resolve()
        if not destination.is_relative_to(self.storage):
            raise Denied("Destination escaped managed storage.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        with source.open("rb") as incoming, destination.open("wb") as outgoing:
            for block in iter(lambda: incoming.read(1024 * 1024), b""):
                digest.update(block)
                outgoing.write(block)
        return {
            "path": str(destination),
            "size_bytes": destination.stat().st_size,
            "sha256": digest.hexdigest(),
            "original_name": source.name,
        }

    @staticmethod
    def paginate(page: int, page_size: int, *, maximum: int = 200) -> tuple[int, int]:
        safe_page = max(1, int(page))
        safe_size = min(maximum, max(1, int(page_size)))
        return safe_size, (safe_page - 1) * safe_size
