from __future__ import annotations

from biointel.runtime_paths import runtime_database_path, runtime_report_path

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from biointel.governance.governance_registry import (
    list_gates,
    list_milestones,
)
from biointel.portfolio.project_registry import (
    list_project_events,
    list_projects,
)
from biointel.training.experiment_registry import list_experiments
from biointel.utils.audit_log import read_audit_events
from biointel.utils.workflow_status import build_workflow_status


@dataclass(frozen=True)
class ActivityItem:
    item_id: str
    title: str
    message: str
    severity: str
    category: str
    timestamp_utc: str
    action_key: str | None
    source: str
    dismissible: bool = True


def _item_id(*parts: object) -> str:
    raw = "|".join(map(str, parts))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def build_alerts(
    project_root: str | Path,
    *,
    workflow_status: dict[str, object] | None = None,
) -> list[ActivityItem]:
    root = Path(project_root).resolve()
    status = workflow_status if workflow_status is not None else build_workflow_status(root)
    project_db = runtime_database_path(root, "projects.sqlite3")
    projects = list_projects(project_db)
    alerts: list[ActivityItem] = []

    def add(
        title: str,
        message: str,
        severity: str,
        category: str,
        action_key: str | None,
        source: str = "workspace",
    ) -> None:
        alerts.append(
            ActivityItem(
                item_id=_item_id(
                    title,
                    message,
                    severity,
                    source,
                ),
                title=title,
                message=message,
                severity=severity,
                category=category,
                timestamp_utc=_now(),
                action_key=action_key,
                source=source,
            )
        )

    diagnostic_state = status["diagnostics"]["overall"]
    if diagnostic_state == "FAIL":
        add(
            "Diagnostics require immediate attention",
            "One or more local runtime checks failed.",
            "Critical",
            "System",
            "diagnostics",
        )
    elif diagnostic_state == "WARN":
        add(
            "Diagnostics contain warnings",
            "The workspace can run, but optional checks need review.",
            "Warning",
            "System",
            "diagnostics",
        )

    if status["datasets"]["total"] == 0:
        add(
            "No registered dataset",
            "Register a dataset version before serious model development.",
            "Warning",
            "Data",
            "dataset_registry",
        )

    if status["models"]["total"] == 0:
        add(
            "No trusted model available",
            "Train or import a trusted local model artifact.",
            "Warning",
            "Models",
            "model_training",
        )
    elif not status["models"]["default"]:
        add(
            "Default model not selected",
            "Choose a preferred active model for prediction workflows.",
            "Warning",
            "Models",
            "model_lifecycle",
        )

    candidate_count = status["models"]["candidate"]
    if candidate_count:
        add(
            "Candidate models awaiting review",
            f"{candidate_count} candidate model(s) are not yet active or archived.",
            "Info",
            "Models",
            "model_lifecycle",
        )

    if status["experiments"]["total"] == 0:
        add(
            "No recorded training experiment",
            "Run model training to create a reproducible experiment record.",
            "Info",
            "Experiments",
            "model_training",
        )

    today = date.today()
    for project in projects:
        if project.status in {"Completed", "Archived"}:
            continue
        if project.target_date:
            target = date.fromisoformat(project.target_date)
            days = (target - today).days
            if days < 0:
                add(
                    f"{project.project_code} is overdue",
                    f"Target date passed {-days} day(s) ago.",
                    "Critical",
                    "Portfolio",
                    "project_portfolio",
                    project.project_id,
                )
            elif days <= 14:
                add(
                    f"{project.project_code} target is approaching",
                    f"Target date is in {days} day(s).",
                    "Warning",
                    "Portfolio",
                    "project_portfolio",
                    project.project_id,
                )
        if not project.dataset_sha256:
            add(
                f"{project.project_code} has no linked dataset",
                "Connect a registered dataset for stronger provenance.",
                "Info",
                "Portfolio",
                "project_portfolio",
                project.project_id,
            )
        if project.status in {"Active", "Validation"} and not project.model_filename:
            add(
                f"{project.project_code} has no linked model",
                "Connect a model artifact to the active project.",
                "Info",
                "Portfolio",
                "project_portfolio",
                project.project_id,
            )

    storage = status["storage"]
    if storage["reports_bytes"] > 100 * 1024 * 1024:
        add(
            "Reports storage exceeds 100 MB",
            "Review generated reports, checkpoints and audit history.",
            "Warning",
            "Storage",
            "local_data",
        )
    if storage["cache_bytes"] > 50 * 1024 * 1024:
        add(
            "External cache exceeds 50 MB",
            "Clear expired UniProt and ChEMBL cache entries.",
            "Info",
            "Storage",
            "diagnostics",
        )

    milestones = list_milestones(project_db)
    for milestone in milestones:
        if milestone.status == "Blocked":
            project = next(
                (item for item in projects if item.project_id == milestone.project_id),
                None,
            )
            code = project.project_code if project else milestone.project_id
            add(
                f"{code} milestone is blocked",
                milestone.title,
                "Critical",
                "Governance",
                "governance_hub",
                milestone.milestone_id,
            )
        if milestone.due_date and milestone.status not in {"Completed", "Cancelled"}:
            target = date.fromisoformat(milestone.due_date)
            days = (target - today).days
            if days < 0:
                project = next(
                    (item for item in projects if item.project_id == milestone.project_id),
                    None,
                )
                code = project.project_code if project else milestone.project_id
                add(
                    f"{code} milestone is overdue",
                    f"{milestone.title} passed its due date {-days} day(s) ago.",
                    "Critical",
                    "Governance",
                    "governance_hub",
                    milestone.milestone_id,
                )

    gates = list_gates(project_db)
    for gate in gates:
        project = next(
            (item for item in projects if item.project_id == gate.project_id),
            None,
        )
        code = project.project_code if project else gate.project_id
        if gate.status == "Rejected":
            add(
                f"{code} governance gate rejected",
                f"{gate.gate_name}: {gate.conditions or 'No conditions recorded.'}",
                "Critical",
                "Governance",
                "governance_hub",
                gate.gate_id,
            )
        elif gate.gate_name == "Release approval" and gate.status in {"Pending", "Conditional"}:
            add(
                f"{code} release approval is {gate.status.lower()}",
                gate.conditions or "Complete release evidence and reviewer sign-off.",
                "Warning",
                "Governance",
                "release_readiness",
                gate.gate_id,
            )

    severity_order = {
        "Critical": 0,
        "Warning": 1,
        "Info": 2,
    }
    return sorted(
        alerts,
        key=lambda item: (
            severity_order.get(item.severity, 3),
            item.title,
        ),
    )


def build_timeline(
    project_root: str | Path,
    limit: int = 200,
) -> list[ActivityItem]:
    root = Path(project_root).resolve()
    items: list[ActivityItem] = []

    for event in list_project_events(
        runtime_database_path(root, "projects.sqlite3"),
        limit=limit,
    ):
        items.append(
            ActivityItem(
                item_id=event.event_id,
                title=event.message,
                message=json.dumps(
                    event.details,
                    sort_keys=True,
                    default=str,
                )[:500],
                severity="Info",
                category="Portfolio",
                timestamp_utc=event.created_at_utc,
                action_key="project_portfolio",
                source=event.project_id,
                dismissible=False,
            )
        )

    for experiment in list_experiments(
        runtime_database_path(root, "experiments.sqlite3"),
        limit=limit,
    ):
        items.append(
            ActivityItem(
                item_id=_item_id(
                    "experiment",
                    experiment["experiment_id"],
                ),
                title="Training experiment recorded",
                message=(
                    f"{experiment['model_name']} · "
                    f"{experiment['task_type']} · "
                    f"{experiment['dataset_name']}"
                ),
                severity="Info",
                category="Experiments",
                timestamp_utc=experiment["trained_at_utc"],
                action_key="experiments",
                source=experiment["experiment_id"],
                dismissible=False,
            )
        )

    for event in read_audit_events(
        runtime_report_path(root, "audit.jsonl"),
        limit=limit,
    ):
        fields = event.get("fields") or {}
        items.append(
            ActivityItem(
                item_id=_item_id(
                    "audit",
                    event.get("timestamp_utc"),
                    event.get("event"),
                ),
                title=str(event.get("event", "Audit event")),
                message=json.dumps(
                    fields,
                    sort_keys=True,
                    default=str,
                )[:500],
                severity=(
                    "Warning"
                    if str(event.get("status", "")).lower() not in {"ok", "success", "passed"}
                    else "Info"
                ),
                category="Audit",
                timestamp_utc=str(event.get("timestamp_utc", "")),
                action_key="audit_release",
                source="audit",
                dismissible=False,
            )
        )

    return sorted(
        items,
        key=lambda item: item.timestamp_utc,
        reverse=True,
    )[: max(1, min(limit, 1000))]


def _state_path(project_root: str | Path) -> Path:
    return runtime_report_path(Path(project_root).resolve(), "activity_state.json")


def load_activity_state(
    project_root: str | Path,
) -> dict[str, Any]:
    path = _state_path(project_root)
    if not path.is_file():
        return {"dismissed": [], "last_reviewed_utc": None}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"dismissed": [], "last_reviewed_utc": None}
    if not isinstance(payload, dict):
        return {"dismissed": [], "last_reviewed_utc": None}
    return {
        "dismissed": list(dict.fromkeys(payload.get("dismissed", [])))[:1000],
        "last_reviewed_utc": payload.get("last_reviewed_utc"),
    }


def save_activity_state(
    project_root: str | Path,
    state: dict[str, Any],
) -> Path:
    path = _state_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "dismissed": list(dict.fromkeys(state.get("dismissed", [])))[:1000],
        "last_reviewed_utc": state.get("last_reviewed_utc"),
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def visible_alerts(
    project_root: str | Path,
    *,
    workflow_status: dict[str, object] | None = None,
) -> list[ActivityItem]:
    dismissed = set(load_activity_state(project_root)["dismissed"])
    return [
        item
        for item in build_alerts(
            project_root,
            workflow_status=workflow_status,
        )
        if item.item_id not in dismissed
    ]


def dismiss_alert(
    project_root: str | Path,
    item_id: str,
) -> None:
    state = load_activity_state(project_root)
    dismissed = list(state["dismissed"])
    if item_id not in dismissed:
        dismissed.append(item_id)
    state["dismissed"] = dismissed
    save_activity_state(project_root, state)


def mark_activity_reviewed(
    project_root: str | Path,
) -> None:
    state = load_activity_state(project_root)
    state["last_reviewed_utc"] = _now()
    save_activity_state(project_root, state)


def activity_export(
    project_root: str | Path,
) -> dict[str, object]:
    return {
        "generated_at_utc": _now(),
        "alerts": [asdict(item) for item in visible_alerts(project_root)],
        "timeline": [asdict(item) for item in build_timeline(project_root)],
    }
