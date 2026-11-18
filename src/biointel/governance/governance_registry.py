from __future__ import annotations

import sqlite3
from biointel.database.core import managed_connect
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from biointel.portfolio.project_registry import (
    get_project,
    record_project_event,
)
from biointel.utils.audit_log import append_audit_event

MILESTONE_STATUSES = {
    "Planned",
    "In Progress",
    "Blocked",
    "Completed",
    "Cancelled",
}
DECISION_STATUSES = {
    "Proposed",
    "Approved",
    "Superseded",
    "Reversed",
}
GATE_STATUSES = {
    "Pending",
    "Conditional",
    "Approved",
    "Rejected",
}
STANDARD_GATES = (
    "Data readiness",
    "Model validation",
    "External validation",
    "Reproducibility",
    "Release approval",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS project_milestones (
    milestone_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    due_date TEXT,
    owner_label TEXT NOT NULL,
    acceptance_criteria TEXT NOT NULL,
    evidence_reference TEXT NOT NULL,
    notes TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_milestones_project
ON project_milestones(project_id, status, due_date);

CREATE TABLE IF NOT EXISTS project_decisions (
    decision_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    decision_date TEXT NOT NULL,
    context TEXT NOT NULL,
    decision TEXT NOT NULL,
    rationale TEXT NOT NULL,
    alternatives TEXT NOT NULL,
    impact TEXT NOT NULL,
    approver_label TEXT NOT NULL,
    evidence_reference TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decisions_project
ON project_decisions(project_id, decision_date);

CREATE TABLE IF NOT EXISTS project_gates (
    gate_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    gate_name TEXT NOT NULL,
    status TEXT NOT NULL,
    reviewer_label TEXT NOT NULL,
    conditions TEXT NOT NULL,
    evidence_reference TEXT NOT NULL,
    decision_date TEXT,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    UNIQUE(project_id, gate_name)
);
CREATE INDEX IF NOT EXISTS idx_gates_project
ON project_gates(project_id, status);
"""


@dataclass(frozen=True)
class MilestoneRecord:
    milestone_id: str
    project_id: str
    title: str
    status: str
    due_date: str | None
    owner_label: str
    acceptance_criteria: str
    evidence_reference: str
    notes: str
    created_at_utc: str
    updated_at_utc: str


@dataclass(frozen=True)
class DecisionRecord:
    decision_id: str
    project_id: str
    title: str
    status: str
    decision_date: str
    context: str
    decision: str
    rationale: str
    alternatives: str
    impact: str
    approver_label: str
    evidence_reference: str
    created_at_utc: str
    updated_at_utc: str


@dataclass(frozen=True)
class GateRecord:
    gate_id: str
    project_id: str
    gate_name: str
    status: str
    reviewer_label: str
    conditions: str
    evidence_reference: str
    decision_date: str | None
    created_at_utc: str
    updated_at_utc: str


def initialize_governance_registry(path: str | Path) -> Path:
    registry = Path(path).resolve()
    registry.parent.mkdir(parents=True, exist_ok=True)
    with managed_connect(registry) as connection:
        connection.executescript(SCHEMA)
        connection.commit()
    return registry


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _validate_project(path: str | Path, project_id: str) -> None:
    if get_project(path, project_id) is None:
        raise ValueError("Project not found")


def _optional_date(value: str | None) -> str | None:
    if not value:
        return None
    return date.fromisoformat(value).isoformat()


def _required_date(value: str | None) -> str:
    return _optional_date(value) or date.today().isoformat()


def _row_to_milestone(row: sqlite3.Row) -> MilestoneRecord:
    return MilestoneRecord(
        milestone_id=row["milestone_id"],
        project_id=row["project_id"],
        title=row["title"],
        status=row["status"],
        due_date=row["due_date"],
        owner_label=row["owner_label"],
        acceptance_criteria=row["acceptance_criteria"],
        evidence_reference=row["evidence_reference"],
        notes=row["notes"],
        created_at_utc=row["created_at_utc"],
        updated_at_utc=row["updated_at_utc"],
    )


def _row_to_decision(row: sqlite3.Row) -> DecisionRecord:
    return DecisionRecord(
        decision_id=row["decision_id"],
        project_id=row["project_id"],
        title=row["title"],
        status=row["status"],
        decision_date=row["decision_date"],
        context=row["context"],
        decision=row["decision"],
        rationale=row["rationale"],
        alternatives=row["alternatives"],
        impact=row["impact"],
        approver_label=row["approver_label"],
        evidence_reference=row["evidence_reference"],
        created_at_utc=row["created_at_utc"],
        updated_at_utc=row["updated_at_utc"],
    )


def _row_to_gate(row: sqlite3.Row) -> GateRecord:
    return GateRecord(
        gate_id=row["gate_id"],
        project_id=row["project_id"],
        gate_name=row["gate_name"],
        status=row["status"],
        reviewer_label=row["reviewer_label"],
        conditions=row["conditions"],
        evidence_reference=row["evidence_reference"],
        decision_date=row["decision_date"],
        created_at_utc=row["created_at_utc"],
        updated_at_utc=row["updated_at_utc"],
    )


def create_milestone(
    registry_path: str | Path,
    project_id: str,
    title: str,
    status: str = "Planned",
    due_date: str | None = None,
    owner_label: str = "",
    acceptance_criteria: str = "",
    evidence_reference: str = "",
    notes: str = "",
) -> MilestoneRecord:
    _validate_project(registry_path, project_id)
    if status not in MILESTONE_STATUSES:
        raise ValueError("Invalid milestone status")
    milestone_title = title.strip()
    if not milestone_title:
        raise ValueError("Milestone title is required")

    registry = initialize_governance_registry(registry_path)
    now = _now()
    record = MilestoneRecord(
        milestone_id="mil-" + uuid.uuid4().hex[:20],
        project_id=project_id,
        title=milestone_title[:240],
        status=status,
        due_date=_optional_date(due_date),
        owner_label=owner_label.strip()[:120],
        acceptance_criteria=acceptance_criteria.strip()[:4000],
        evidence_reference=evidence_reference.strip()[:500],
        notes=notes.strip()[:5000],
        created_at_utc=now,
        updated_at_utc=now,
    )
    with managed_connect(registry) as connection:
        connection.execute(
            """
            INSERT INTO project_milestones (
                milestone_id, project_id, title, status, due_date,
                owner_label, acceptance_criteria, evidence_reference,
                notes, created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.milestone_id,
                record.project_id,
                record.title,
                record.status,
                record.due_date,
                record.owner_label,
                record.acceptance_criteria,
                record.evidence_reference,
                record.notes,
                record.created_at_utc,
                record.updated_at_utc,
            ),
        )
        connection.commit()

    record_project_event(
        registry_path,
        project_id,
        "milestone_created",
        f"Milestone created: {record.title}",
        {
            "milestone_id": record.milestone_id,
            "status": record.status,
            "due_date": record.due_date,
        },
    )
    append_audit_event(
        Path(registry_path).resolve().parent / "audit.jsonl",
        "milestone_created",
        "success",
        {
            "project_id": project_id,
            "milestone_id": record.milestone_id,
            "status": record.status,
        },
    )
    return record


def update_milestone(
    registry_path: str | Path,
    milestone_id: str,
    **changes: Any,
) -> MilestoneRecord:
    current = get_milestone(registry_path, milestone_id)
    if current is None:
        raise ValueError("Milestone not found")
    allowed = {
        "title",
        "status",
        "due_date",
        "owner_label",
        "acceptance_criteria",
        "evidence_reference",
        "notes",
    }
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError("Unsupported milestone fields: " + ", ".join(sorted(unknown)))
    payload = asdict(current)
    payload.update(changes)
    if payload["status"] not in MILESTONE_STATUSES:
        raise ValueError("Invalid milestone status")
    payload["title"] = str(payload["title"]).strip()[:240]
    if not payload["title"]:
        raise ValueError("Milestone title is required")
    payload["due_date"] = _optional_date(payload["due_date"])
    payload["owner_label"] = str(payload["owner_label"]).strip()[:120]
    payload["acceptance_criteria"] = str(payload["acceptance_criteria"]).strip()[:4000]
    payload["evidence_reference"] = str(payload["evidence_reference"]).strip()[:500]
    payload["notes"] = str(payload["notes"]).strip()[:5000]
    updated_at = _now()

    registry = initialize_governance_registry(registry_path)
    with managed_connect(registry) as connection:
        connection.execute(
            """
            UPDATE project_milestones SET
                title = ?, status = ?, due_date = ?, owner_label = ?,
                acceptance_criteria = ?, evidence_reference = ?,
                notes = ?, updated_at_utc = ?
            WHERE milestone_id = ?
            """,
            (
                payload["title"],
                payload["status"],
                payload["due_date"],
                payload["owner_label"],
                payload["acceptance_criteria"],
                payload["evidence_reference"],
                payload["notes"],
                updated_at,
                milestone_id,
            ),
        )
        connection.commit()

    record_project_event(
        registry_path,
        current.project_id,
        "milestone_updated",
        f"Milestone updated: {payload['title']}",
        {
            "milestone_id": milestone_id,
            "status": payload["status"],
            "due_date": payload["due_date"],
        },
    )
    updated = get_milestone(registry_path, milestone_id)
    if updated is None:
        raise RuntimeError("Milestone update could not be read back")
    append_audit_event(
        Path(registry_path).resolve().parent / "audit.jsonl",
        "milestone_updated",
        "success",
        {
            "project_id": current.project_id,
            "milestone_id": milestone_id,
            "status": updated.status,
        },
    )
    return updated


def get_milestone(
    registry_path: str | Path,
    milestone_id: str,
) -> MilestoneRecord | None:
    registry = initialize_governance_registry(registry_path)
    with managed_connect(registry) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM project_milestones WHERE milestone_id = ?",
            (milestone_id,),
        ).fetchone()
    return _row_to_milestone(row) if row else None


def list_milestones(
    registry_path: str | Path,
    project_id: str | None = None,
    limit: int = 5000,
) -> list[MilestoneRecord]:
    registry = initialize_governance_registry(registry_path)
    where = "WHERE project_id = ?" if project_id else ""
    params: tuple[object, ...] = (
        (project_id, max(1, min(limit, 5000))) if project_id else (max(1, min(limit, 5000)),)
    )
    with managed_connect(registry) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            f"""
            SELECT * FROM project_milestones
            {where}
            ORDER BY
                CASE status
                    WHEN 'Blocked' THEN 1
                    WHEN 'In Progress' THEN 2
                    WHEN 'Planned' THEN 3
                    WHEN 'Completed' THEN 4
                    ELSE 5
                END,
                due_date IS NULL,
                due_date,
                updated_at_utc DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [_row_to_milestone(row) for row in rows]


def delete_milestone(
    registry_path: str | Path,
    milestone_id: str,
) -> bool:
    current = get_milestone(registry_path, milestone_id)
    if current is None:
        return False
    registry = initialize_governance_registry(registry_path)
    with managed_connect(registry) as connection:
        cursor = connection.execute(
            "DELETE FROM project_milestones WHERE milestone_id = ?",
            (milestone_id,),
        )
        connection.commit()
    if cursor.rowcount:
        record_project_event(
            registry_path,
            current.project_id,
            "milestone_deleted",
            f"Milestone deleted: {current.title}",
            {"milestone_id": milestone_id},
        )
        append_audit_event(
            Path(registry_path).resolve().parent / "audit.jsonl",
            "milestone_deleted",
            "success",
            {
                "project_id": current.project_id,
                "milestone_id": milestone_id,
            },
        )
    return cursor.rowcount > 0


def create_decision(
    registry_path: str | Path,
    project_id: str,
    title: str,
    decision: str,
    status: str = "Approved",
    decision_date: str | None = None,
    context: str = "",
    rationale: str = "",
    alternatives: str = "",
    impact: str = "",
    approver_label: str = "",
    evidence_reference: str = "",
) -> DecisionRecord:
    _validate_project(registry_path, project_id)
    if status not in DECISION_STATUSES:
        raise ValueError("Invalid decision status")
    title_value = title.strip()
    decision_value = decision.strip()
    if not title_value or not decision_value:
        raise ValueError("Decision title and decision text are required")
    registry = initialize_governance_registry(registry_path)
    now = _now()
    record = DecisionRecord(
        decision_id="dec-" + uuid.uuid4().hex[:20],
        project_id=project_id,
        title=title_value[:240],
        status=status,
        decision_date=_required_date(decision_date),
        context=context.strip()[:5000],
        decision=decision_value[:5000],
        rationale=rationale.strip()[:5000],
        alternatives=alternatives.strip()[:5000],
        impact=impact.strip()[:5000],
        approver_label=approver_label.strip()[:120],
        evidence_reference=evidence_reference.strip()[:500],
        created_at_utc=now,
        updated_at_utc=now,
    )
    with managed_connect(registry) as connection:
        connection.execute(
            """
            INSERT INTO project_decisions (
                decision_id, project_id, title, status, decision_date,
                context, decision, rationale, alternatives, impact,
                approver_label, evidence_reference,
                created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.decision_id,
                record.project_id,
                record.title,
                record.status,
                record.decision_date,
                record.context,
                record.decision,
                record.rationale,
                record.alternatives,
                record.impact,
                record.approver_label,
                record.evidence_reference,
                record.created_at_utc,
                record.updated_at_utc,
            ),
        )
        connection.commit()
    record_project_event(
        registry_path,
        project_id,
        "decision_recorded",
        f"Decision recorded: {record.title}",
        {
            "decision_id": record.decision_id,
            "status": record.status,
            "decision_date": record.decision_date,
        },
    )
    append_audit_event(
        Path(registry_path).resolve().parent / "audit.jsonl",
        "decision_recorded",
        "success",
        {
            "project_id": project_id,
            "decision_id": record.decision_id,
            "status": record.status,
        },
    )
    return record


def list_decisions(
    registry_path: str | Path,
    project_id: str | None = None,
    limit: int = 5000,
) -> list[DecisionRecord]:
    registry = initialize_governance_registry(registry_path)
    where = "WHERE project_id = ?" if project_id else ""
    params: tuple[object, ...] = (
        (project_id, max(1, min(limit, 5000))) if project_id else (max(1, min(limit, 5000)),)
    )
    with managed_connect(registry) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            f"""
            SELECT * FROM project_decisions
            {where}
            ORDER BY decision_date DESC, created_at_utc DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [_row_to_decision(row) for row in rows]


def upsert_gate(
    registry_path: str | Path,
    project_id: str,
    gate_name: str,
    status: str = "Pending",
    reviewer_label: str = "",
    conditions: str = "",
    evidence_reference: str = "",
    decision_date: str | None = None,
) -> GateRecord:
    _validate_project(registry_path, project_id)
    if status not in GATE_STATUSES:
        raise ValueError("Invalid gate status")
    gate_value = gate_name.strip()
    if not gate_value:
        raise ValueError("Gate name is required")
    registry = initialize_governance_registry(registry_path)
    now = _now()
    final_date = _optional_date(decision_date) if status != "Pending" else None
    with managed_connect(registry) as connection:
        connection.row_factory = sqlite3.Row
        existing = connection.execute(
            """
            SELECT * FROM project_gates
            WHERE project_id = ? AND gate_name = ?
            """,
            (project_id, gate_value),
        ).fetchone()
        if existing:
            gate_id = existing["gate_id"]
            created_at = existing["created_at_utc"]
            connection.execute(
                """
                UPDATE project_gates SET
                    status = ?, reviewer_label = ?, conditions = ?,
                    evidence_reference = ?, decision_date = ?,
                    updated_at_utc = ?
                WHERE gate_id = ?
                """,
                (
                    status,
                    reviewer_label.strip()[:120],
                    conditions.strip()[:5000],
                    evidence_reference.strip()[:500],
                    final_date,
                    now,
                    gate_id,
                ),
            )
            event_type = "gate_updated"
        else:
            gate_id = "gat-" + uuid.uuid4().hex[:20]
            created_at = now
            connection.execute(
                """
                INSERT INTO project_gates (
                    gate_id, project_id, gate_name, status,
                    reviewer_label, conditions, evidence_reference,
                    decision_date, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    gate_id,
                    project_id,
                    gate_value[:240],
                    status,
                    reviewer_label.strip()[:120],
                    conditions.strip()[:5000],
                    evidence_reference.strip()[:500],
                    final_date,
                    created_at,
                    now,
                ),
            )
            event_type = "gate_created"
        connection.commit()

    record_project_event(
        registry_path,
        project_id,
        event_type,
        f"Governance gate {gate_value}: {status}",
        {
            "gate_id": gate_id,
            "gate_name": gate_value,
            "status": status,
        },
    )
    append_audit_event(
        Path(registry_path).resolve().parent / "audit.jsonl",
        event_type,
        "success",
        {
            "project_id": project_id,
            "gate_id": gate_id,
            "gate_name": gate_value,
            "status": status,
        },
    )
    return GateRecord(
        gate_id=gate_id,
        project_id=project_id,
        gate_name=gate_value[:240],
        status=status,
        reviewer_label=reviewer_label.strip()[:120],
        conditions=conditions.strip()[:5000],
        evidence_reference=evidence_reference.strip()[:500],
        decision_date=final_date,
        created_at_utc=created_at,
        updated_at_utc=now,
    )


def list_gates(
    registry_path: str | Path,
    project_id: str | None = None,
    limit: int = 5000,
) -> list[GateRecord]:
    registry = initialize_governance_registry(registry_path)
    where = "WHERE project_id = ?" if project_id else ""
    params: tuple[object, ...] = (
        (project_id, max(1, min(limit, 5000))) if project_id else (max(1, min(limit, 5000)),)
    )
    with managed_connect(registry) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            f"""
            SELECT * FROM project_gates
            {where}
            ORDER BY
                CASE status
                    WHEN 'Rejected' THEN 1
                    WHEN 'Conditional' THEN 2
                    WHEN 'Pending' THEN 3
                    ELSE 4
                END,
                gate_name
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [_row_to_gate(row) for row in rows]


def project_governance_snapshot(
    registry_path: str | Path,
    project_id: str,
) -> dict[str, object]:
    _validate_project(registry_path, project_id)
    milestones = list_milestones(registry_path, project_id)
    decisions = list_decisions(registry_path, project_id)
    gates = list_gates(registry_path, project_id)
    completed = sum(item.status == "Completed" for item in milestones)
    blocked = sum(item.status == "Blocked" for item in milestones)
    approved_gates = sum(item.status == "Approved" for item in gates)
    return {
        "project_id": project_id,
        "milestones": [asdict(item) for item in milestones],
        "decisions": [asdict(item) for item in decisions],
        "gates": [asdict(item) for item in gates],
        "summary": {
            "milestones_total": len(milestones),
            "milestones_completed": completed,
            "milestones_blocked": blocked,
            "milestone_completion_percent": (
                round(completed / len(milestones) * 100, 1) if milestones else 0.0
            ),
            "decisions_total": len(decisions),
            "approved_decisions": sum(item.status == "Approved" for item in decisions),
            "gates_total": len(gates),
            "gates_approved": approved_gates,
            "gates_pending": sum(item.status == "Pending" for item in gates),
            "gates_conditional": sum(item.status == "Conditional" for item in gates),
            "gates_rejected": sum(item.status == "Rejected" for item in gates),
        },
    }


def governance_portfolio_summary(
    registry_path: str | Path,
) -> dict[str, object]:
    projects: set[str] = set()
    milestones = list_milestones(registry_path)
    decisions = list_decisions(registry_path)
    gates = list_gates(registry_path)
    projects.update(item.project_id for item in milestones)
    projects.update(item.project_id for item in decisions)
    projects.update(item.project_id for item in gates)
    return {
        "projects_with_governance": len(projects),
        "milestones_total": len(milestones),
        "milestones_completed": sum(item.status == "Completed" for item in milestones),
        "milestones_blocked": sum(item.status == "Blocked" for item in milestones),
        "decisions_total": len(decisions),
        "approved_decisions": sum(item.status == "Approved" for item in decisions),
        "gates_total": len(gates),
        "gates_approved": sum(item.status == "Approved" for item in gates),
        "gates_pending": sum(item.status == "Pending" for item in gates),
        "gates_rejected": sum(item.status == "Rejected" for item in gates),
    }
