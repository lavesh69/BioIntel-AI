from __future__ import annotations

import json
import sqlite3
from biointel.database.core import managed_connect
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from biointel.utils.audit_log import append_audit_event

VALID_STATUSES = {
    "Planning",
    "Active",
    "Validation",
    "Paused",
    "Completed",
    "Archived",
}
VALID_PRIORITIES = {"Low", "Medium", "High", "Critical"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    project_code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    priority TEXT NOT NULL,
    objective TEXT NOT NULL,
    owner_label TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    target_date TEXT,
    dataset_sha256 TEXT,
    model_filename TEXT,
    notes TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_projects_status
ON projects(status, priority);
CREATE INDEX IF NOT EXISTS idx_projects_target_date
ON projects(target_date);

CREATE TABLE IF NOT EXISTS project_events (
    event_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    details_json TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(project_id)
);
CREATE INDEX IF NOT EXISTS idx_project_events_project
ON project_events(project_id, created_at_utc);
"""


@dataclass(frozen=True)
class ProjectRecord:
    project_id: str
    project_code: str
    name: str
    status: str
    priority: str
    objective: str
    owner_label: str
    tags: tuple[str, ...]
    target_date: str | None
    dataset_sha256: str | None
    model_filename: str | None
    notes: str
    created_at_utc: str
    updated_at_utc: str


@dataclass(frozen=True)
class ProjectEvent:
    event_id: str
    project_id: str
    event_type: str
    message: str
    created_at_utc: str
    details: dict[str, Any]


def initialize_project_registry(path: str | Path) -> Path:
    registry = Path(path).resolve()
    registry.parent.mkdir(parents=True, exist_ok=True)
    with managed_connect(registry) as connection:
        connection.executescript(SCHEMA)
        connection.commit()
    return registry


def _validate_date(value: str | None) -> str | None:
    if not value:
        return None
    parsed = date.fromisoformat(value)
    return parsed.isoformat()


def _normalise_tags(tags: list[str] | tuple[str, ...] | str) -> tuple[str, ...]:
    if isinstance(tags, str):
        raw = tags.split(",")
    else:
        raw = list(tags)
    cleaned = []
    for item in raw:
        value = str(item).strip()
        if value and value not in cleaned:
            cleaned.append(value[:50])
    return tuple(cleaned[:20])


def _row_to_project(row: sqlite3.Row) -> ProjectRecord:
    return ProjectRecord(
        project_id=row["project_id"],
        project_code=row["project_code"],
        name=row["name"],
        status=row["status"],
        priority=row["priority"],
        objective=row["objective"],
        owner_label=row["owner_label"],
        tags=tuple(json.loads(row["tags_json"])),
        target_date=row["target_date"],
        dataset_sha256=row["dataset_sha256"],
        model_filename=row["model_filename"],
        notes=row["notes"],
        created_at_utc=row["created_at_utc"],
        updated_at_utc=row["updated_at_utc"],
    )


def _record_event(
    connection: sqlite3.Connection,
    project_id: str,
    event_type: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> ProjectEvent:
    event = ProjectEvent(
        event_id="evt-" + uuid.uuid4().hex[:20],
        project_id=project_id,
        event_type=event_type,
        message=message.strip()[:500],
        created_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        details=details or {},
    )
    connection.execute(
        """
        INSERT INTO project_events (
            event_id, project_id, event_type, message,
            created_at_utc, details_json
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            event.event_id,
            event.project_id,
            event.event_type,
            event.message,
            event.created_at_utc,
            json.dumps(event.details, sort_keys=True, default=str),
        ),
    )
    return event


def record_project_event(
    registry_path: str | Path,
    project_id: str,
    event_type: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> ProjectEvent:
    """Append a privacy-safe event to an existing project timeline."""

    if get_project(registry_path, project_id) is None:
        raise ValueError("Project not found")
    registry = initialize_project_registry(registry_path)
    with managed_connect(registry) as connection:
        event = _record_event(
            connection,
            project_id,
            event_type,
            message,
            details,
        )
        connection.commit()
    return event


def create_project(
    registry_path: str | Path,
    project_code: str,
    name: str,
    status: str = "Planning",
    priority: str = "Medium",
    objective: str = "",
    owner_label: str = "",
    tags: list[str] | tuple[str, ...] | str = (),
    target_date: str | None = None,
    dataset_sha256: str | None = None,
    model_filename: str | None = None,
    notes: str = "",
) -> ProjectRecord:
    code = project_code.strip().upper()
    project_name = name.strip()
    if not code or len(code) > 40:
        raise ValueError("project_code is required and must be at most 40 characters")
    if not project_name or len(project_name) > 160:
        raise ValueError("name is required and must be at most 160 characters")
    if status not in VALID_STATUSES:
        raise ValueError("Invalid project status")
    if priority not in VALID_PRIORITIES:
        raise ValueError("Invalid project priority")

    registry = initialize_project_registry(registry_path)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    record = ProjectRecord(
        project_id="prj-" + uuid.uuid4().hex[:20],
        project_code=code,
        name=project_name,
        status=status,
        priority=priority,
        objective=objective.strip()[:2000],
        owner_label=owner_label.strip()[:120],
        tags=_normalise_tags(tags),
        target_date=_validate_date(target_date),
        dataset_sha256=(dataset_sha256 or "").strip() or None,
        model_filename=Path(model_filename).name if model_filename else None,
        notes=notes.strip()[:5000],
        created_at_utc=now,
        updated_at_utc=now,
    )

    with managed_connect(registry) as connection:
        try:
            connection.execute(
                """
                INSERT INTO projects (
                    project_id, project_code, name, status, priority,
                    objective, owner_label, tags_json, target_date,
                    dataset_sha256, model_filename, notes,
                    created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.project_id,
                    record.project_code,
                    record.name,
                    record.status,
                    record.priority,
                    record.objective,
                    record.owner_label,
                    json.dumps(record.tags),
                    record.target_date,
                    record.dataset_sha256,
                    record.model_filename,
                    record.notes,
                    record.created_at_utc,
                    record.updated_at_utc,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Project code already exists: {record.project_code}") from exc
        _record_event(
            connection,
            record.project_id,
            "created",
            f"Project {record.project_code} created",
            {"status": record.status, "priority": record.priority},
        )
        connection.commit()
    append_audit_event(
        Path(registry_path).resolve().parent / "audit.jsonl",
        "project_created",
        "success",
        {
            "project_id": record.project_id,
            "project_code": record.project_code,
            "status": record.status,
            "priority": record.priority,
        },
    )
    return record


def list_projects(
    registry_path: str | Path,
    include_archived: bool = True,
    limit: int = 2000,
) -> list[ProjectRecord]:
    registry = initialize_project_registry(registry_path)
    where = "" if include_archived else "WHERE status != 'Archived'"
    with managed_connect(registry) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            f"""
            SELECT * FROM projects
            {where}
            ORDER BY
                CASE priority
                    WHEN 'Critical' THEN 1
                    WHEN 'High' THEN 2
                    WHEN 'Medium' THEN 3
                    ELSE 4
                END,
                updated_at_utc DESC
            LIMIT ?
            """,
            (max(1, min(limit, 5000)),),
        ).fetchall()
    return [_row_to_project(row) for row in rows]


def get_project(
    registry_path: str | Path,
    project_id: str,
) -> ProjectRecord | None:
    registry = initialize_project_registry(registry_path)
    with managed_connect(registry) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
    return _row_to_project(row) if row else None


def update_project(
    registry_path: str | Path,
    project_id: str,
    **changes: Any,
) -> ProjectRecord:
    current = get_project(registry_path, project_id)
    if current is None:
        raise ValueError("Project not found")

    allowed = {
        "project_code",
        "name",
        "status",
        "priority",
        "objective",
        "owner_label",
        "tags",
        "target_date",
        "dataset_sha256",
        "model_filename",
        "notes",
    }
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError("Unsupported project fields: " + ", ".join(sorted(unknown)))

    payload = asdict(current)
    payload.update(changes)
    payload["project_code"] = str(payload["project_code"]).strip().upper()
    payload["name"] = str(payload["name"]).strip()
    payload["objective"] = str(payload["objective"]).strip()[:2000]
    payload["owner_label"] = str(payload["owner_label"]).strip()[:120]
    payload["notes"] = str(payload["notes"]).strip()[:5000]
    payload["tags"] = _normalise_tags(payload["tags"])
    payload["target_date"] = _validate_date(payload["target_date"])
    payload["dataset_sha256"] = (
        str(payload["dataset_sha256"]).strip() if payload["dataset_sha256"] else None
    )
    payload["model_filename"] = (
        Path(str(payload["model_filename"])).name if payload["model_filename"] else None
    )
    if payload["status"] not in VALID_STATUSES:
        raise ValueError("Invalid project status")
    if payload["priority"] not in VALID_PRIORITIES:
        raise ValueError("Invalid project priority")
    if not payload["project_code"] or not payload["name"]:
        raise ValueError("Project code and name are required")

    changed_fields = {key: payload[key] for key in allowed if payload[key] != getattr(current, key)}
    now = datetime.now(UTC).isoformat(timespec="seconds")
    registry = initialize_project_registry(registry_path)
    with managed_connect(registry) as connection:
        try:
            connection.execute(
                """
                UPDATE projects SET
                    project_code = ?, name = ?, status = ?, priority = ?,
                    objective = ?, owner_label = ?, tags_json = ?,
                    target_date = ?, dataset_sha256 = ?, model_filename = ?,
                    notes = ?, updated_at_utc = ?
                WHERE project_id = ?
                """,
                (
                    payload["project_code"],
                    payload["name"],
                    payload["status"],
                    payload["priority"],
                    payload["objective"],
                    payload["owner_label"],
                    json.dumps(payload["tags"]),
                    payload["target_date"],
                    payload["dataset_sha256"],
                    payload["model_filename"],
                    payload["notes"],
                    now,
                    project_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Project code already exists: {payload['project_code']}") from exc
        if changed_fields:
            _record_event(
                connection,
                project_id,
                "updated",
                f"Project {payload['project_code']} updated",
                changed_fields,
            )
        connection.commit()

    updated = get_project(registry_path, project_id)
    if updated is None:
        raise RuntimeError("Project update could not be read back")
    append_audit_event(
        Path(registry_path).resolve().parent / "audit.jsonl",
        "project_updated",
        "success",
        {
            "project_id": project_id,
            "project_code": updated.project_code,
            "changed_fields": sorted(changed_fields),
        },
    )
    return updated


def delete_project(
    registry_path: str | Path,
    project_id: str,
) -> bool:
    registry = initialize_project_registry(registry_path)
    with managed_connect(registry) as connection:
        existing_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        for table in (
            "project_milestones",
            "project_decisions",
            "project_gates",
        ):
            if table in existing_tables:
                connection.execute(
                    f"DELETE FROM {table} WHERE project_id = ?",
                    (project_id,),
                )
        connection.execute(
            "DELETE FROM project_events WHERE project_id = ?",
            (project_id,),
        )
        cursor = connection.execute(
            "DELETE FROM projects WHERE project_id = ?",
            (project_id,),
        )
        connection.commit()
        deleted = cursor.rowcount > 0
    if deleted:
        append_audit_event(
            Path(registry_path).resolve().parent / "audit.jsonl",
            "project_deleted",
            "success",
            {"project_id": project_id},
        )
    return deleted


def list_project_events(
    registry_path: str | Path,
    project_id: str | None = None,
    limit: int = 1000,
) -> list[ProjectEvent]:
    registry = initialize_project_registry(registry_path)
    where = "WHERE project_id = ?" if project_id else ""
    params: tuple[object, ...] = (
        (project_id, max(1, min(limit, 5000))) if project_id else (max(1, min(limit, 5000)),)
    )
    with managed_connect(registry) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            f"""
            SELECT * FROM project_events
            {where}
            ORDER BY created_at_utc DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [
        ProjectEvent(
            event_id=row["event_id"],
            project_id=row["project_id"],
            event_type=row["event_type"],
            message=row["message"],
            created_at_utc=row["created_at_utc"],
            details=json.loads(row["details_json"]),
        )
        for row in rows
    ]


def portfolio_summary(
    registry_path: str | Path,
) -> dict[str, object]:
    projects = list_projects(registry_path)
    today = date.today()
    overdue = 0
    due_soon = 0
    for project in projects:
        if not project.target_date or project.status in {
            "Completed",
            "Archived",
        }:
            continue
        target = date.fromisoformat(project.target_date)
        if target < today:
            overdue += 1
        elif (target - today).days <= 14:
            due_soon += 1

    return {
        "total": len(projects),
        "active": sum(project.status in {"Active", "Validation"} for project in projects),
        "planning": sum(project.status == "Planning" for project in projects),
        "paused": sum(project.status == "Paused" for project in projects),
        "completed": sum(project.status == "Completed" for project in projects),
        "archived": sum(project.status == "Archived" for project in projects),
        "critical": sum(project.priority == "Critical" for project in projects),
        "overdue": overdue,
        "due_soon": due_soon,
    }
