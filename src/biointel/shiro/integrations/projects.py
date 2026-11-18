from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectOption:
    project_id: str
    name: str
    source: str
    synthetic: bool = False


def list_project_options(root: str | Path) -> tuple[ProjectOption, ...]:
    values: dict[str, ProjectOption] = {}
    try:
        from biointel.projects.catalog import PROJECT_CATALOG
        for project in PROJECT_CATALOG:
            values[project.code] = ProjectOption(project.code, project.short_title, "biotechnology_catalog")
    except Exception:
        pass
    registry = runtime_database_path(Path(root), "projects.sqlite3")
    if registry.is_file():
        try:
            from biointel.portfolio.project_registry import list_projects
            for project in list_projects(registry, include_archived=False, limit=500):
                values[project.project_id] = ProjectOption(project.project_id, project.name, "portfolio_registry")
        except Exception:
            pass
    if not values:
        values["LOCAL-RESEARCH"] = ProjectOption("LOCAL-RESEARCH", "Local research project", "shiro")
    return tuple(sorted(values.values(), key=lambda item: item.name.casefold()))
