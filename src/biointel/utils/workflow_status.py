from __future__ import annotations

from biointel.runtime_paths import runtime_database_path, runtime_reports_directory

from dataclasses import asdict
from pathlib import Path

from biointel.data.dataset_registry import list_datasets
from biointel.governance.governance_registry import governance_portfolio_summary
from biointel.integrations.cache import ExternalResponseCache
from biointel.integrations.http_client import DEFAULT_CACHE_DIRECTORY
from biointel.portfolio.project_registry import portfolio_summary
from biointel.training.experiment_registry import list_experiments
from biointel.training.model_catalog import sync_model_catalog
from biointel.utils.diagnostics import (
    diagnostic_summary,
    run_diagnostics,
)
from biointel.utils.local_data import directory_size_bytes


def build_workflow_status(
    project_root: str | Path,
    *,
    diagnostic_checks: list[object] | None = None,
) -> dict[str, object]:
    root = Path(project_root).resolve()
    models = sync_model_catalog(root / "models")
    datasets = list_datasets(runtime_database_path(root, "datasets.sqlite3"))
    experiments = list_experiments(runtime_database_path(root, "experiments.sqlite3"))
    diagnostics = (
        diagnostic_checks
        if diagnostic_checks is not None
        else run_diagnostics(root, profile="quick")
    )
    cache = ExternalResponseCache(DEFAULT_CACHE_DIRECTORY)
    project_registry = runtime_database_path(root, "projects.sqlite3")
    projects = portfolio_summary(project_registry)
    governance = governance_portfolio_summary(project_registry)

    active_models = [entry for entry in models if entry.state == "active"]
    candidate_models = [entry for entry in models if entry.state == "candidate"]
    archived_models = [entry for entry in models if entry.state == "archived"]
    default_model = next(
        (entry.filename for entry in models if entry.is_default),
        None,
    )

    return {
        "models": {
            "total": len(models),
            "active": len(active_models),
            "candidate": len(candidate_models),
            "archived": len(archived_models),
            "default": default_model,
            "entries": [asdict(entry) for entry in models],
        },
        "datasets": {
            "total": len(datasets),
            "classification": sum(item.task_type == "classification" for item in datasets),
            "regression": sum(item.task_type == "regression" for item in datasets),
            "unlabelled": sum(item.task_type == "unlabelled" for item in datasets),
        },
        "projects": projects,
        "governance": governance,
        "experiments": {
            "total": len(experiments),
            "latest": (experiments[0]["trained_at_utc"] if experiments else None),
        },
        "diagnostics": diagnostic_summary(diagnostics),
        "storage": {
            "models_bytes": directory_size_bytes(root / "models"),
            "reports_bytes": directory_size_bytes(runtime_reports_directory(root)),
            "cache_bytes": cache.total_size_bytes(),
        },
    }
