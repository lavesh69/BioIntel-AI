from __future__ import annotations

import csv
import hashlib
import hmac
import json
import sqlite3
import zipfile
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook

from ..platform import Conflict, Denied, EducationError, Missing, ident, now
from .base import (
    ADMIN_ROLES,
    Phase30Base,
    decode_json,
    encode_json,
    normalized_key,
    sha256_bytes,
    utc_datetime,
)

PILOT_STATUSES = (
    "draft",
    "technical_validation",
    "institution_onboarding",
    "data_import",
    "staff_training",
    "student_activation",
    "controlled_live_pilot",
    "pilot_review",
    "acceptance_or_remediation",
    "production_readiness_decision",
)
PILOT_TRANSITIONS = {
    current: {PILOT_STATUSES[index + 1]}
    for index, current in enumerate(PILOT_STATUSES[:-1])
}
PILOT_TRANSITIONS["acceptance_or_remediation"].add("controlled_live_pilot")
PILOT_TRANSITIONS["production_readiness_decision"] = set()

ONBOARDING_ROLES = {
    "institution_administrator",
    "department_administrator",
    "teacher",
    "student",
    "parent",
    "examiner",
    "instructor",
    "research_supervisor",
}
ONBOARDING_STEPS = {
    "institution_administrator": [
        "confirm_institution_profile",
        "configure_departments",
        "review_security_and_privacy",
        "approve_feature_flags",
        "validate_backup",
    ],
    "department_administrator": [
        "confirm_department",
        "configure_programs",
        "assign_staff",
        "validate_courses",
    ],
    "teacher": [
        "confirm_profile",
        "review_classroom",
        "review_shiro_safety",
        "publish_sample_resource",
    ],
    "student": [
        "confirm_profile",
        "review_privacy",
        "join_classroom",
        "complete_orientation",
    ],
    "parent": [
        "confirm_guardian_link",
        "review_privacy",
        "review_parent_safe_summary",
    ],
    "examiner": [
        "confirm_profile",
        "review_exam_security",
        "validate_accommodations",
    ],
    "instructor": [
        "confirm_profile",
        "review_virtual_lab",
        "review_assessment_rubric",
    ],
    "research_supervisor": [
        "confirm_profile",
        "review_research_integrity",
        "validate_evidence_workflow",
    ],
}

IMPORT_SCHEMAS: dict[str, dict[str, list[str]]] = {
    "institutions": {"required": ["external_key", "name"], "optional": ["kind"]},
    "departments": {"required": ["external_key", "name"], "optional": ["parent_external_key"]},
    "programs": {"required": ["external_key", "name"], "optional": ["parent_external_key"]},
    "semesters": {"required": ["external_key", "name"], "optional": ["parent_external_key"]},
    "courses": {"required": ["external_key", "code", "name"], "optional": ["parent_external_key"]},
    "subjects": {"required": ["external_key", "code", "name"], "optional": ["parent_external_key"]},
    "batches": {"required": ["external_key", "name"], "optional": ["parent_external_key"]},
    "staff": {"required": ["external_key", "user_id", "role"], "optional": ["name", "email"]},
    "students": {"required": ["external_key", "user_id"], "optional": ["name", "email"]},
    "parents": {"required": ["external_key", "user_id"], "optional": ["student_id", "name", "email"]},
    "enrolments": {
        "required": ["external_key", "student_id", "subject_code"],
        "optional": [],
    },
    "timetables": {
        "required": [
            "external_key",
            "subject_code",
            "teacher_id",
            "starts_at",
            "ends_at",
        ],
        "optional": ["student_group", "room"],
    },
    "previous_attendance": {
        "required": ["external_key", "student_id", "subject_code", "status"],
        "optional": ["session_date", "period"],
    },
    "historical_marks": {
        "required": ["external_key", "student_id", "subject_code", "marks"],
        "optional": ["maximum_marks", "assessment_name"],
    },
    "course_materials": {
        "required": ["external_key", "subject_code", "title"],
        "optional": ["source_path", "source_url"],
    },
}


class PilotMixin(Phase30Base):
    def register_pilot(
        self,
        actor: str,
        institution_id: str,
        *,
        name: str,
        starts_on: str = "",
        ends_on: str = "",
        goals: list[str] | None = None,
        administrator_ids: list[str] | None = None,
        departments: list[str] | None = None,
        user_limit: int = 500,
        feature_flags: dict[str, bool] | None = None,
        terms_version: str = "",
        terms_accepted: bool = False,
        support_contact: str = "",
    ) -> dict[str, Any]:
        self._require(actor, institution_id, "admin")
        if not str(name).strip():
            raise EducationError("Pilot name is required.")
        if starts_on:
            start = utc_datetime(starts_on, field="starts_on")
            if ends_on and utc_datetime(ends_on, field="ends_on") <= start:
                raise EducationError("Pilot end must follow its start.")
        if int(user_limit) < 1 or int(user_limit) > 100_000:
            raise EducationError("Pilot user limit must be between 1 and 100,000.")
        admins = sorted({str(item).strip() for item in administrator_ids or [actor] if str(item).strip()})
        pilot_id = ident("pilot")
        timestamp = now()
        consent_state = "accepted" if terms_accepted and terms_version else "pending"
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_pilots
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    pilot_id,
                    institution_id,
                    str(name).strip(),
                    "draft",
                    starts_on,
                    ends_on,
                    encode_json(goals or []),
                    encode_json(admins),
                    encode_json(departments or []),
                    int(user_limit),
                    encode_json(feature_flags or {}),
                    str(terms_version),
                    consent_state,
                    actor if consent_state == "accepted" else "",
                    timestamp if consent_state == "accepted" else None,
                    str(support_contact),
                    0.0,
                    0.0,
                    0,
                    "pending",
                    "",
                    None,
                    actor,
                    timestamp,
                    timestamp,
                ),
            )
            db.execute(
                """INSERT INTO education_p30_pilot_transitions
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    ident("pilottr"),
                    institution_id,
                    pilot_id,
                    "",
                    "draft",
                    actor,
                    "Pilot registered.",
                    "[]",
                    timestamp,
                ),
            )
        self._audit(actor, institution_id, "pilot_registered", "pilot", pilot_id)
        return self._tenant_row("education_p30_pilots", pilot_id, institution_id)

    def transition_pilot(
        self,
        actor: str,
        pilot_id: str,
        to_status: str,
        *,
        reason: str = "",
        blockers: list[str] | None = None,
        readiness_decision: str = "",
    ) -> dict[str, Any]:
        pilot = self._tenant_row("education_p30_pilots", pilot_id)
        institution_id = str(pilot["institution_id"])
        self._require(actor, institution_id, "admin")
        current = str(pilot["status"])
        target = normalized_key(to_status)
        if target not in PILOT_STATUSES or target not in PILOT_TRANSITIONS.get(current, set()):
            raise Conflict(f"Pilot cannot transition from {current} to {target}.")
        unresolved = [str(item).strip() for item in blockers or [] if str(item).strip()]
        if target == "controlled_live_pilot":
            if pilot["consent_state"] != "accepted":
                raise Conflict("Accepted pilot terms are required before controlled launch.")
            if float(pilot["onboarding_percent"]) < 80:
                raise Conflict("At least 80% onboarding completion is required.")
        if target == "production_readiness_decision":
            allowed = {"accepted", "remediation_required", "not_ready"}
            if readiness_decision not in allowed:
                raise EducationError("A truthful production readiness decision is required.")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """UPDATE education_p30_pilots SET status=?,blocker_count=?,
                readiness_decision=CASE WHEN ?<>'' THEN ? ELSE readiness_decision END,
                updated_at=? WHERE id=?""",
                (
                    target,
                    len(unresolved),
                    readiness_decision,
                    readiness_decision,
                    timestamp,
                    pilot_id,
                ),
            )
            db.execute(
                """INSERT INTO education_p30_pilot_transitions
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    ident("pilottr"),
                    institution_id,
                    pilot_id,
                    current,
                    target,
                    actor,
                    str(reason),
                    encode_json(unresolved),
                    timestamp,
                ),
            )
        self._audit(
            actor,
            institution_id,
            "pilot_transitioned",
            "pilot",
            pilot_id,
            {"from": current, "to": target, "blockers": unresolved},
        )
        return self._tenant_row("education_p30_pilots", pilot_id, institution_id)

    def save_onboarding(
        self,
        actor: str,
        pilot_id: str,
        user_id: str,
        role: str,
        *,
        completed_steps: list[str],
        configuration: dict[str, Any] | None = None,
        data_mode: str = "none",
        validation_errors: list[str] | None = None,
    ) -> dict[str, Any]:
        pilot = self._tenant_row("education_p30_pilots", pilot_id)
        institution_id = str(pilot["institution_id"])
        roles = self._require(actor, institution_id, "member")
        if actor != user_id and not roles.intersection(ADMIN_ROLES):
            raise Denied("Only the user or an administrator may update onboarding.")
        role_key = normalized_key(role)
        if role_key not in ONBOARDING_ROLES:
            raise EducationError("Unsupported onboarding role.")
        allowed_steps = ONBOARDING_STEPS[role_key]
        completed = sorted(set(completed_steps).intersection(allowed_steps))
        errors = [str(item) for item in validation_errors or [] if str(item).strip()]
        percent = round(100 * len(completed) / len(allowed_steps), 2)
        state = "ready_for_approval" if percent == 100 and not errors else "in_progress"
        onboarding_id = ident("onboard")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_onboarding
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(pilot_id,user_id,role) DO UPDATE SET
                checklist_json=excluded.checklist_json,
                tutorial_state_json=excluded.tutorial_state_json,
                configuration_json=excluded.configuration_json,
                data_mode=excluded.data_mode,
                validation_errors_json=excluded.validation_errors_json,
                progress_percent=excluded.progress_percent,
                state=excluded.state,
                approved_by='',
                approved_at=NULL,
                updated_at=excluded.updated_at""",
                (
                    onboarding_id,
                    institution_id,
                    pilot_id,
                    user_id,
                    role_key,
                    encode_json(completed),
                    encode_json({step: step in completed for step in allowed_steps}),
                    encode_json(configuration or {}),
                    data_mode,
                    encode_json(errors),
                    percent,
                    state,
                    "",
                    None,
                    timestamp,
                    timestamp,
                ),
            )
            aggregate = db.execute(
                """SELECT COALESCE(AVG(progress_percent),0) FROM education_p30_onboarding
                WHERE pilot_id=?""",
                (pilot_id,),
            ).fetchone()[0]
            db.execute(
                "UPDATE education_p30_pilots SET onboarding_percent=?,updated_at=? WHERE id=?",
                (float(aggregate), timestamp, pilot_id),
            )
        self._audit(actor, institution_id, "onboarding_saved", "user", user_id, {"role": role_key})
        return self._one(
            """SELECT * FROM education_p30_onboarding
            WHERE pilot_id=? AND user_id=? AND role=?""",
            (pilot_id, user_id, role_key),
        ) or {}

    def approve_onboarding(
        self,
        actor: str,
        onboarding_id: str,
    ) -> dict[str, Any]:
        row = self._tenant_row("education_p30_onboarding", onboarding_id)
        self._require(actor, str(row["institution_id"]), "admin")
        if row["state"] != "ready_for_approval":
            raise Conflict("Onboarding must be complete and valid before approval.")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """UPDATE education_p30_onboarding
                SET state='approved',approved_by=?,approved_at=?,updated_at=? WHERE id=?""",
                (actor, timestamp, timestamp, onboarding_id),
            )
        self._audit(
            actor,
            str(row["institution_id"]),
            "onboarding_approved",
            "onboarding",
            onboarding_id,
        )
        return self._tenant_row(
            "education_p30_onboarding",
            onboarding_id,
            str(row["institution_id"]),
        )

    def generate_import_template(
        self,
        actor: str,
        institution_id: str,
        entity_type: str,
        *,
        file_format: str = "csv",
    ) -> dict[str, Any]:
        self._require(actor, institution_id, "admin")
        entity = normalized_key(entity_type)
        schema = IMPORT_SCHEMAS.get(entity)
        if not schema:
            raise EducationError("Unsupported pilot import entity.")
        extension = file_format.casefold()
        if extension not in {"csv", "xlsx"}:
            raise EducationError("Import templates support CSV or XLSX.")
        headers = schema["required"] + schema["optional"]
        destination = self._safe_storage_path(
            institution_id,
            "imports",
            "templates",
            f"{entity}.{extension}",
        )
        if extension == "csv":
            with destination.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(headers)
        else:
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = entity[:31]
            sheet.append(headers)
            workbook.save(destination)
        return {
            "path": str(destination),
            "entity_type": entity,
            "required_columns": schema["required"],
            "optional_columns": schema["optional"],
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        }

    def _read_import_file(self, path: Path) -> tuple[list[dict[str, str]], str]:
        if path.stat().st_size > 50 * 1024 * 1024:
            raise EducationError("Import file exceeds the 50 MiB pilot limit.")
        if path.suffix.casefold() == ".csv":
            last_error: UnicodeDecodeError | None = None
            for encoding in ("utf-8-sig", "utf-8", "cp1252"):
                try:
                    with path.open("r", encoding=encoding, newline="") as handle:
                        return [
                            {str(key).strip(): str(value or "").strip() for key, value in row.items()}
                            for row in csv.DictReader(handle)
                        ], encoding
                except UnicodeDecodeError as exc:
                    last_error = exc
            raise EducationError(f"CSV encoding could not be decoded: {last_error}")
        if path.suffix.casefold() == ".xlsx":
            workbook = load_workbook(path, read_only=True, data_only=True)
            sheet = workbook.active
            iterator = sheet.iter_rows(values_only=True)
            try:
                headers = [str(value or "").strip() for value in next(iterator)]
            except StopIteration:
                return [], "xlsx"
            rows = [
                {headers[index]: str(value or "").strip() for index, value in enumerate(values)}
                for values in iterator
            ]
            workbook.close()
            return rows, "xlsx"
        raise EducationError("Import file must be CSV or XLSX.")

    def dry_run_import(
        self,
        actor: str,
        institution_id: str,
        entity_type: str,
        source_path: str | Path,
        *,
        pilot_id: str = "",
    ) -> dict[str, Any]:
        self._require(actor, institution_id, "admin")
        if pilot_id:
            self._tenant_row("education_p30_pilots", pilot_id, institution_id)
        entity = normalized_key(entity_type)
        schema = IMPORT_SCHEMAS.get(entity)
        if not schema:
            raise EducationError("Unsupported pilot import entity.")
        source = Path(source_path).expanduser().resolve()
        if not source.is_file():
            raise Missing("Import file not found.")
        rows, encoding = self._read_import_file(source)
        if len(rows) > 100_000:
            raise EducationError("Import contains more than 100,000 rows.")
        source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
        job_id = ident("import")
        timestamp = now()
        seen: dict[str, int] = {}
        staged_keys = {
            normalized_key(str(row.get("external_key", "")))
            for row in rows
            if str(row.get("external_key", "")).strip()
        }
        analyzed: list[dict[str, Any]] = []
        duplicate_count = 0
        invalid_count = 0
        for number, payload in enumerate(rows, start=2):
            errors: list[str] = []
            missing = [column for column in schema["required"] if not str(payload.get(column, "")).strip()]
            if missing:
                errors.append("missing:" + ",".join(missing))
            raw_key = str(payload.get("external_key", "")).strip()
            key = normalized_key(raw_key) if raw_key else ""
            duplicate_of = ""
            if key and key in seen:
                duplicate_of = str(seen[key])
                errors.append(f"duplicate_in_file:{duplicate_of}")
                duplicate_count += 1
            elif key:
                seen[key] = number
                existing = self._one(
                    """SELECT id FROM education_p30_pilot_records
                    WHERE institution_id=? AND entity_type=? AND external_key=? AND state='active'""",
                    (institution_id, entity, key),
                )
                if existing:
                    duplicate_of = str(existing["id"])
                    errors.append("duplicate_existing")
                    duplicate_count += 1
            parent_key = str(payload.get("parent_external_key", "")).strip()
            if parent_key:
                normalized_parent = normalized_key(parent_key)
                parent_exists = normalized_parent in staged_keys or self._one(
                    """SELECT 1 ok FROM education_p30_pilot_records
                    WHERE institution_id=? AND external_key=? AND state='active'""",
                    (institution_id, normalized_parent),
                )
                if not parent_exists:
                    errors.append("relationship:parent_external_key_not_found")
            if entity == "timetables":
                try:
                    if utc_datetime(payload.get("ends_at", ""), field="ends_at") <= utc_datetime(
                        payload.get("starts_at", ""),
                        field="starts_at",
                    ):
                        errors.append("relationship:end_must_follow_start")
                except EducationError as exc:
                    errors.append(str(exc))
            if errors:
                invalid_count += 1
            analyzed.append(
                {
                    "row_number": number,
                    "external_key": key,
                    "payload": payload,
                    "errors": errors,
                    "duplicate_of": duplicate_of,
                    "state": "invalid" if errors else "valid",
                }
            )
        confirmation_digest = sha256_bytes(
            encode_json(
                {
                    "job_id": job_id,
                    "institution_id": institution_id,
                    "entity_type": entity,
                    "source_sha256": source_sha,
                    "valid_rows": [
                        {"external_key": row["external_key"], "payload": row["payload"]}
                        for row in analyzed
                        if row["state"] == "valid"
                    ],
                }
            ).encode("utf-8")
        )
        error_path = self._safe_storage_path(
            institution_id,
            "imports",
            job_id,
            "error-report.csv",
        )
        with error_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["row_number", "external_key", "errors"])
            for item in analyzed:
                if item["errors"]:
                    writer.writerow(
                        [
                            item["row_number"],
                            item["external_key"],
                            ";".join(item["errors"]),
                        ]
                    )
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_import_jobs
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job_id,
                    institution_id,
                    pilot_id or None,
                    entity,
                    source.name,
                    source_sha,
                    encoding,
                    1,
                    "validated" if not invalid_count else "validation_failed",
                    confirmation_digest,
                    len(analyzed),
                    len(analyzed) - invalid_count,
                    invalid_count,
                    duplicate_count,
                    str(error_path),
                    actor,
                    "",
                    None,
                    timestamp,
                    timestamp,
                ),
            )
            db.executemany(
                """INSERT INTO education_p30_import_rows
                VALUES(?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        ident("improw"),
                        job_id,
                        item["row_number"],
                        item["external_key"],
                        encode_json(item["payload"]),
                        encode_json(item["errors"]),
                        item["duplicate_of"],
                        item["state"],
                        timestamp,
                    )
                    for item in analyzed
                ],
            )
        self._audit(
            actor,
            institution_id,
            "pilot_import_dry_run",
            "import_job",
            job_id,
            {
                "entity_type": entity,
                "rows": len(analyzed),
                "invalid": invalid_count,
                "duplicates": duplicate_count,
            },
        )
        return self._tenant_row("education_p30_import_jobs", job_id, institution_id)

    def _mirror_import_row(
        self,
        db: sqlite3.Connection,
        institution_id: str,
        entity: str,
        payload: dict[str, Any],
        timestamp: str,
    ) -> None:
        if entity in {"departments", "programs", "semesters", "batches"}:
            db.execute(
                """INSERT INTO academic_units
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO NOTHING""",
                (
                    f"p30unit_{sha256_bytes((institution_id + entity + payload['external_key']).encode())[:24]}",
                    institution_id,
                    None,
                    entity[:-1],
                    payload["name"],
                    str(payload.get("academic_year", "")),
                    "active",
                    timestamp,
                    timestamp,
                ),
            )
        elif entity in {"courses", "subjects"}:
            db.execute(
                """INSERT INTO subjects
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,code) DO UPDATE SET
                name=excluded.name,updated_at=excluded.updated_at""",
                (
                    f"p30subj_{sha256_bytes((institution_id + payload['code']).encode())[:24]}",
                    institution_id,
                    None,
                    payload["code"],
                    payload["name"],
                    str(payload.get("syllabus", "")),
                    "active",
                    timestamp,
                    timestamp,
                ),
            )
        elif entity in {"staff", "students", "parents"}:
            default_role = {
                "students": "university_student",
                "parents": "parent_guardian",
            }.get(entity, "subject_teacher")
            role = str(payload.get("role") or default_role)
            db.execute(
                """INSERT INTO memberships
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,user_id,role) DO UPDATE SET
                state='active',updated_at=excluded.updated_at""",
                (
                    ident("mem"),
                    institution_id,
                    payload["user_id"],
                    role,
                    "active",
                    timestamp,
                    timestamp,
                ),
            )
        elif entity == "enrolments":
            subject = db.execute(
                "SELECT id FROM subjects WHERE institution_id=? AND code=?",
                (institution_id, payload["subject_code"]),
            ).fetchone()
            student = db.execute(
                """SELECT 1 FROM memberships WHERE institution_id=? AND user_id=?
                AND role IN ('school_student','college_student','university_student')
                AND state='active'""",
                (institution_id, payload["student_id"]),
            ).fetchone()
            if not subject or not student:
                raise Conflict("Enrolment relationship could not be resolved.")
            db.execute(
                """INSERT INTO enrollments VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(subject_id,student_id) DO UPDATE SET
                state='active',updated_at=excluded.updated_at""",
                (
                    ident("enr"),
                    institution_id,
                    subject[0],
                    payload["student_id"],
                    "active",
                    timestamp,
                    timestamp,
                ),
            )
        elif entity == "timetables":
            subject = db.execute(
                "SELECT id FROM subjects WHERE institution_id=? AND code=?",
                (institution_id, payload["subject_code"]),
            ).fetchone()
            if not subject:
                raise Conflict("Timetable subject relationship could not be resolved.")
            db.execute(
                """INSERT INTO timetable_entries
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    ident("time"),
                    institution_id,
                    subject[0],
                    payload["teacher_id"],
                    str(payload.get("student_group", "")),
                    str(payload.get("room", "")),
                    payload["starts_at"],
                    payload["ends_at"],
                    "",
                    "scheduled",
                    timestamp,
                    timestamp,
                ),
            )

    def commit_import(
        self,
        actor: str,
        job_id: str,
        *,
        confirmation_digest: str,
    ) -> dict[str, Any]:
        job = self._tenant_row("education_p30_import_jobs", job_id)
        institution_id = str(job["institution_id"])
        self._require(actor, institution_id, "admin")
        if job["state"] != "validated" or int(job["invalid_count"]):
            raise Conflict("Only a fully valid dry-run may be committed.")
        if not hmac.compare_digest(
            str(job["confirmation_digest"]),
            str(confirmation_digest),
        ):
            raise Denied("Import confirmation digest does not match the validated dry-run.")
        rows = self._all(
            """SELECT * FROM education_p30_import_rows
            WHERE job_id=? AND state='valid' ORDER BY row_number""",
            (job_id,),
        )
        timestamp = now()
        try:
            with self.db.connection() as db:
                for item in rows:
                    payload = decode_json(item["payload_json"], {})
                    db.execute(
                        """INSERT INTO education_p30_pilot_records
                        VALUES(?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(institution_id,entity_type,external_key) DO UPDATE SET
                        payload_json=excluded.payload_json,
                        source_job_id=excluded.source_job_id,
                        state='active',updated_at=excluded.updated_at""",
                        (
                            ident("pilotrec"),
                            institution_id,
                            job["entity_type"],
                            item["external_key"],
                            item["payload_json"],
                            job_id,
                            "active",
                            timestamp,
                            timestamp,
                        ),
                    )
                    self._mirror_import_row(
                        db,
                        institution_id,
                        str(job["entity_type"]),
                        payload,
                        timestamp,
                    )
                db.execute(
                    """UPDATE education_p30_import_jobs
                    SET dry_run=0,state='committed',committed_by=?,committed_at=?,updated_at=?
                    WHERE id=?""",
                    (actor, timestamp, timestamp, job_id),
                )
        except (sqlite3.Error, KeyError, Conflict) as exc:
            with self.db.connection() as db:
                db.execute(
                    "UPDATE education_p30_import_jobs SET state='commit_failed',updated_at=? WHERE id=?",
                    (now(), job_id),
                )
            raise Conflict(f"Import transaction rolled back: {exc}") from exc
        self._audit(
            actor,
            institution_id,
            "pilot_import_committed",
            "import_job",
            job_id,
            {"rows": len(rows), "entity_type": job["entity_type"]},
        )
        return self._tenant_row("education_p30_import_jobs", job_id, institution_id)

    def record_health(
        self,
        institution_id: str,
        module: str,
        component: str,
        status: str,
        *,
        latency_ms: float = 0,
        failure_rate: float = 0,
        retry_count: int = 0,
        metrics: dict[str, Any] | None = None,
        sensitive_content_collected: bool = False,
    ) -> dict[str, Any]:
        if sensitive_content_collected:
            raise Denied("Sensitive content telemetry requires explicit configured consent.")
        allowed = {"healthy", "degraded", "unavailable", "not_configured"}
        if status not in allowed:
            raise EducationError("Unsupported health status.")
        sample_id = ident("health")
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_health_samples
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    sample_id,
                    institution_id,
                    normalized_key(module),
                    normalized_key(component),
                    status,
                    max(0.0, float(latency_ms)),
                    max(0.0, min(1.0, float(failure_rate))),
                    max(0, int(retry_count)),
                    encode_json(metrics or {}),
                    0,
                    now(),
                ),
            )
        return self._one(
            "SELECT * FROM education_p30_health_samples WHERE id=?",
            (sample_id,),
        ) or {}

    def health_snapshot(
        self,
        actor: str,
        institution_id: str,
    ) -> dict[str, Any]:
        self._require(actor, institution_id, "admin")
        latest = self._all(
            """SELECT h.* FROM education_p30_health_samples h
            JOIN (
              SELECT module,component,MAX(recorded_at) recorded_at
              FROM education_p30_health_samples
              WHERE institution_id IN ('',?)
              GROUP BY module,component
            ) x ON x.module=h.module AND x.component=h.component
               AND x.recorded_at=h.recorded_at
            WHERE h.institution_id IN ('',?)
            ORDER BY h.module,h.component""",
            (institution_id, institution_id),
        )
        db_ok = self.db.quick_check()
        queued = self._one(
            """SELECT COUNT(*) count FROM education_p30_jobs
            WHERE institution_id=? AND state IN ('queued','retry')""",
            (institution_id,),
        )
        statuses = [str(row["status"]) for row in latest]
        overall = (
            "unavailable"
            if not db_ok or "unavailable" in statuses
            else "degraded"
            if "degraded" in statuses
            else "healthy"
        )
        return {
            "institution_id": institution_id,
            "overall": overall,
            "database": "healthy" if db_ok else "unavailable",
            "queued_jobs": int((queued or {}).get("count", 0)),
            "components": latest,
            "sensitive_content_collected": False,
            "generated_at": now(),
        }

    def create_diagnostic_bundle(
        self,
        actor: str,
        institution_id: str,
    ) -> dict[str, Any]:
        self._require(actor, institution_id, "admin")
        destination = self._safe_storage_path(
            institution_id,
            "diagnostics",
            f"diagnostic-{ident('bundle')}.zip",
        )
        health = self.health_snapshot(actor, institution_id)
        tables = self._all(
            """SELECT name FROM sqlite_master
            WHERE type='table' AND name LIKE 'education_p30_%' ORDER BY name"""
        )
        counts: dict[str, int] = {}
        with self.db.connection() as db:
            for table in tables:
                name = str(table["name"])
                counts[name] = int(db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
        audit = self.verify_audit_chain(institution_id)
        payloads = {
            "health.json": health,
            "database.json": {
                "migration": self.migrate(),
                "quick_check": self.db.quick_check(),
                "table_counts": counts,
            },
            "audit-chain.json": audit,
            "privacy.json": {
                "student_content_included": False,
                "secrets_included": False,
                "paths_redacted": True,
            },
        }
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, payload in payloads.items():
                archive.writestr(name, json.dumps(payload, ensure_ascii=False, indent=2))
        result = {
            "path": str(destination),
            "size_bytes": destination.stat().st_size,
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "files": sorted(payloads),
            "contains_sensitive_student_content": False,
        }
        self._audit(
            actor,
            institution_id,
            "diagnostic_bundle_created",
            "diagnostic_bundle",
            result["sha256"],
        )
        return result

    def create_support_ticket(
        self,
        actor: str,
        institution_id: str,
        *,
        module: str,
        severity: str,
        title: str,
        description: str,
        pilot_id: str = "",
        screenshot_path: str = "",
        attach_diagnostics: bool = False,
        consent: bool = False,
    ) -> dict[str, Any]:
        self._require(actor, institution_id, "member")
        if severity not in {"low", "medium", "high", "critical"}:
            raise EducationError("Unsupported support severity.")
        if not title.strip() or not description.strip():
            raise EducationError("Support title and description are required.")
        if pilot_id:
            self._tenant_row("education_p30_pilots", pilot_id, institution_id)
        managed_screenshot = ""
        if screenshot_path:
            if not consent:
                raise Denied("Attachment consent is required.")
            destination = self._safe_storage_path(
                institution_id,
                "support",
                ident("shot") + Path(screenshot_path).suffix.casefold(),
            )
            managed_screenshot = self._copy_managed_file(
                screenshot_path,
                destination,
                maximum_bytes=15 * 1024 * 1024,
                allowed_suffixes={".png", ".jpg", ".jpeg", ".webp"},
            )["path"]
        diagnostic_path = ""
        if attach_diagnostics:
            if not consent:
                raise Denied("Diagnostic attachment consent is required.")
            roles = self._roles(actor, institution_id)
            if not roles.intersection(ADMIN_ROLES):
                raise Denied("Only an administrator may attach institutional diagnostics.")
            diagnostic_path = self.create_diagnostic_bundle(actor, institution_id)["path"]
        ticket_id = ident("ticket")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_support_tickets
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    ticket_id,
                    institution_id,
                    pilot_id or None,
                    actor,
                    normalized_key(module),
                    severity,
                    title.strip(),
                    description.strip(),
                    managed_screenshot,
                    diagnostic_path,
                    int(consent),
                    "open",
                    "",
                    "",
                    0,
                    timestamp,
                    timestamp,
                ),
            )
        self._audit(actor, institution_id, "support_ticket_created", "support_ticket", ticket_id)
        return self._tenant_row("education_p30_support_tickets", ticket_id, institution_id)

    def update_support_ticket(
        self,
        actor: str,
        ticket_id: str,
        *,
        state: str | None = None,
        assigned_to: str | None = None,
        resolution: str | None = None,
        comment: str = "",
        internal_only: bool = False,
    ) -> dict[str, Any]:
        ticket = self._tenant_row("education_p30_support_tickets", ticket_id)
        institution_id = str(ticket["institution_id"])
        roles = self._require(actor, institution_id, "member")
        admin = bool(roles.intersection(ADMIN_ROLES))
        if (assigned_to is not None or resolution is not None or internal_only) and not admin:
            raise Denied("Administrator permission is required for support administration.")
        target_state = str(state or ticket["state"])
        if target_state not in {"open", "triaged", "in_progress", "resolved", "closed", "reopened"}:
            raise EducationError("Unsupported ticket state.")
        if target_state == "reopened" and ticket["state"] not in {"resolved", "closed"}:
            raise Conflict("Only resolved or closed tickets may be reopened.")
        if actor != ticket["reporter_id"] and not admin:
            raise Denied("Ticket access denied.")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """UPDATE education_p30_support_tickets SET
                state=?,assigned_to=?,resolution=?,reopened_count=reopened_count+?,
                updated_at=? WHERE id=?""",
                (
                    target_state,
                    assigned_to if assigned_to is not None else ticket["assigned_to"],
                    resolution if resolution is not None else ticket["resolution"],
                    1 if target_state == "reopened" else 0,
                    timestamp,
                    ticket_id,
                ),
            )
            if comment.strip():
                db.execute(
                    """INSERT INTO education_p30_support_comments
                    VALUES(?,?,?,?,?,?)""",
                    (
                        ident("ticketcomment"),
                        ticket_id,
                        actor,
                        comment.strip(),
                        int(internal_only),
                        timestamp,
                    ),
                )
        self._audit(
            actor,
            institution_id,
            "support_ticket_updated",
            "support_ticket",
            ticket_id,
            {"state": target_state},
        )
        return self._tenant_row("education_p30_support_tickets", ticket_id, institution_id)

    def export_pilot(
        self,
        actor: str,
        pilot_id: str,
    ) -> dict[str, Any]:
        pilot = self._tenant_row("education_p30_pilots", pilot_id)
        institution_id = str(pilot["institution_id"])
        self._require(actor, institution_id, "admin")
        payload = {
            "pilot": pilot,
            "transitions": self._all(
                "SELECT * FROM education_p30_pilot_transitions WHERE pilot_id=? ORDER BY created_at",
                (pilot_id,),
            ),
            "onboarding": self._all(
                "SELECT * FROM education_p30_onboarding WHERE pilot_id=? ORDER BY user_id,role",
                (pilot_id,),
            ),
            "imports": self._all(
                "SELECT * FROM education_p30_import_jobs WHERE pilot_id=? ORDER BY created_at",
                (pilot_id,),
            ),
            "tickets": self._all(
                "SELECT * FROM education_p30_support_tickets WHERE pilot_id=? ORDER BY created_at",
                (pilot_id,),
            ),
            "generated_at": now(),
        }
        destination = self._safe_storage_path(
            institution_id,
            "pilots",
            pilot_id,
            "pilot-export.json",
        )
        destination.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {
            "path": str(destination),
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "size_bytes": destination.stat().st_size,
        }

    @staticmethod
    def load_profiles() -> list[dict[str, Any]]:
        scenarios = [
            "classroom_activity",
            "connect_messaging",
            "shiro_queries",
            "examination_start_spike",
            "examination_submission_spike",
            "report_generation",
            "bulk_imports",
            "lecture_uploads",
        ]
        return [
            {
                "name": "500-users",
                "users": 500,
                "classification": "not_verified",
                "recommended_concurrency": 32,
                "scenarios": scenarios,
            },
            {
                "name": "1000-users",
                "users": 1000,
                "classification": "not_verified",
                "recommended_concurrency": 48,
                "scenarios": scenarios,
            },
            {
                "name": "5000-users",
                "users": 5000,
                "classification": "not_verified",
                "recommended_concurrency": 64,
                "scenarios": scenarios,
            },
        ]
