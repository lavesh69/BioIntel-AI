from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from biointel.governance.governance_registry import (
    DECISION_STATUSES,
    GATE_STATUSES,
    MILESTONE_STATUSES,
    create_decision,
    create_milestone,
    project_governance_snapshot,
    upsert_gate,
)
from biointel.portfolio.project_registry import (
    ProjectRecord,
    create_project,
    get_project,
)

PROJECT_EXCHANGE_VERSION = "1.0"


def export_project_bundle(
    registry_path: str | Path,
    project_id: str,
) -> dict[str, object]:
    project = get_project(registry_path, project_id)
    if project is None:
        raise ValueError("Project not found")
    return {
        "project_exchange_version": PROJECT_EXCHANGE_VERSION,
        "exported_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "project": asdict(project),
        "governance": project_governance_snapshot(
            registry_path,
            project_id,
        ),
    }


def project_bundle_json(
    registry_path: str | Path,
    project_id: str,
) -> str:
    return json.dumps(
        export_project_bundle(registry_path, project_id),
        indent=2,
        sort_keys=True,
        default=str,
    )


def _validate_payload(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if payload.get("project_exchange_version") != PROJECT_EXCHANGE_VERSION:
        raise ValueError("Unsupported project exchange version.")
    project = payload.get("project")
    governance = payload.get("governance")
    if not isinstance(project, dict):
        raise ValueError("Project record is missing.")
    if not isinstance(governance, dict):
        raise ValueError("Governance record is missing.")
    for key in ("project_code", "name", "status", "priority"):
        if not str(project.get(key, "")).strip():
            raise ValueError(f"Project field is missing: {key}")
    milestones = governance.get("milestones", [])
    decisions = governance.get("decisions", [])
    gates = governance.get("gates", [])
    if not all(isinstance(item, dict) for item in milestones):
        raise ValueError("Milestone records are invalid.")
    if not all(isinstance(item, dict) for item in decisions):
        raise ValueError("Decision records are invalid.")
    if not all(isinstance(item, dict) for item in gates):
        raise ValueError("Gate records are invalid.")
    for item in milestones:
        if str(item.get("status", "Planned")) not in MILESTONE_STATUSES:
            raise ValueError("Imported milestone status is invalid.")
    for item in decisions:
        if str(item.get("status", "Approved")) not in DECISION_STATUSES:
            raise ValueError("Imported decision status is invalid.")
    for item in gates:
        if str(item.get("status", "Pending")) not in GATE_STATUSES:
            raise ValueError("Imported gate status is invalid.")
    return project, governance


def import_project_bundle(
    registry_path: str | Path,
    payload: dict[str, Any],
    project_code: str | None = None,
    name_suffix: str = "",
) -> ProjectRecord:
    source, governance = _validate_payload(payload)
    code = (
        project_code.strip().upper()
        if project_code
        else str(source["project_code"]).strip().upper()
    )
    name = str(source["name"]).strip()
    if name_suffix.strip():
        name += " " + name_suffix.strip()

    created = create_project(
        registry_path,
        project_code=code,
        name=name,
        status=str(source.get("status", "Planning")),
        priority=str(source.get("priority", "Medium")),
        objective=str(source.get("objective", "")),
        owner_label=str(source.get("owner_label", "")),
        tags=source.get("tags", []),
        target_date=source.get("target_date"),
        dataset_sha256=source.get("dataset_sha256"),
        model_filename=source.get("model_filename"),
        notes=str(source.get("notes", "")),
    )

    for milestone in governance.get("milestones", []):
        if not isinstance(milestone, dict):
            continue
        create_milestone(
            registry_path,
            created.project_id,
            title=str(milestone.get("title", "Imported milestone")),
            status=str(milestone.get("status", "Planned")),
            due_date=milestone.get("due_date"),
            owner_label=str(milestone.get("owner_label", "")),
            acceptance_criteria=str(milestone.get("acceptance_criteria", "")),
            evidence_reference=str(milestone.get("evidence_reference", "")),
            notes=str(milestone.get("notes", "")),
        )

    for decision in governance.get("decisions", []):
        if not isinstance(decision, dict):
            continue
        create_decision(
            registry_path,
            created.project_id,
            title=str(decision.get("title", "Imported decision")),
            decision=str(decision.get("decision", "Imported")),
            status=str(decision.get("status", "Approved")),
            decision_date=decision.get("decision_date"),
            context=str(decision.get("context", "")),
            rationale=str(decision.get("rationale", "")),
            alternatives=str(decision.get("alternatives", "")),
            impact=str(decision.get("impact", "")),
            approver_label=str(decision.get("approver_label", "")),
            evidence_reference=str(decision.get("evidence_reference", "")),
        )

    for gate in governance.get("gates", []):
        if not isinstance(gate, dict):
            continue
        upsert_gate(
            registry_path,
            created.project_id,
            gate_name=str(gate.get("gate_name", "Imported gate")),
            status=str(gate.get("status", "Pending")),
            reviewer_label=str(gate.get("reviewer_label", "")),
            conditions=str(gate.get("conditions", "")),
            evidence_reference=str(gate.get("evidence_reference", "")),
            decision_date=gate.get("decision_date"),
        )

    return created
