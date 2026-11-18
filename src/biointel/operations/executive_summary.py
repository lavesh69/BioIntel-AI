from __future__ import annotations

from biointel.runtime_paths import runtime_database_path, runtime_report_path

from datetime import date
from pathlib import Path

from biointel.data.dataset_registry import list_datasets
from biointel.governance.governance_registry import governance_portfolio_summary
from biointel.operations.activity_center import visible_alerts
from biointel.portfolio.project_registry import (
    list_projects,
    portfolio_summary,
)
from biointel.training.experiment_registry import list_experiments
from biointel.training.model_catalog import sync_model_catalog
from biointel.utils.workflow_status import build_workflow_status


def _maturity_label(score: int) -> str:
    if score >= 85:
        return "Operationally mature"
    if score >= 70:
        return "Research ready"
    if score >= 50:
        return "Developing"
    if score >= 30:
        return "Early foundation"
    return "Initial setup"


def build_executive_summary(
    project_root: str | Path,
    *,
    workflow_status: dict[str, object] | None = None,
) -> dict[str, object]:
    root = Path(project_root).resolve()
    workflow = workflow_status or build_workflow_status(root)
    project_db = runtime_database_path(root, "projects.sqlite3")
    projects = list_projects(project_db)
    project_metrics = portfolio_summary(project_db)
    models = sync_model_catalog(root / "models")
    datasets = list_datasets(runtime_database_path(root, "datasets.sqlite3"))
    experiments = list_experiments(runtime_database_path(root, "experiments.sqlite3"))
    diagnostics = workflow["diagnostics"]
    alerts = visible_alerts(
        root,
        workflow_status=workflow,
    )
    governance = governance_portfolio_summary(project_db)

    governance_points = 0
    governance_points += 5 if governance["milestones_total"] else 0
    governance_points += 5 if governance["approved_decisions"] else 0
    governance_points += 5 if governance["gates_approved"] else 0

    score_components = {
        "diagnostics": 15 if diagnostics["overall"] == "PASS" else 6,
        "datasets": 10 if datasets else 0,
        "models": 10 if models else 0,
        "default_model": 10 if workflow["models"]["default"] else 0,
        "experiments": 10 if experiments else 0,
        "active_project": 10 if project_metrics["active"] else 0,
        "linked_projects": (
            10
            if any(project.dataset_sha256 and project.model_filename for project in projects)
            else 0
        ),
        "governance": governance_points,
        "completed_project": 5 if project_metrics["completed"] else 0,
        "reporting": (5 if any((runtime_report_path(root, "generated")).glob("*.html")) else 0),
    }
    score = min(100, sum(score_components.values()))

    risk_counts = {
        "critical": sum(alert.severity == "Critical" for alert in alerts),
        "warning": sum(alert.severity == "Warning" for alert in alerts),
        "info": sum(alert.severity == "Info" for alert in alerts),
    }

    priority_projects = [
        {
            "project_id": project.project_id,
            "project_code": project.project_code,
            "name": project.name,
            "status": project.status,
            "priority": project.priority,
            "target_date": project.target_date,
            "dataset_linked": bool(project.dataset_sha256),
            "model_linked": bool(project.model_filename),
        }
        for project in projects
        if project.status not in {"Completed", "Archived"}
    ][:10]

    return {
        "generated_on": date.today().isoformat(),
        "maturity_score": score,
        "maturity_label": _maturity_label(score),
        "score_components": score_components,
        "portfolio": project_metrics,
        "governance": governance,
        "workflow": workflow,
        "risk_counts": risk_counts,
        "open_alerts": len(alerts),
        "priority_projects": priority_projects,
        "latest_experiment": (experiments[0]["trained_at_utc"] if experiments else None),
        "default_model": workflow["models"]["default"],
        "diagnostics": diagnostics,
    }
