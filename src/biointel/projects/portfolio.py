from __future__ import annotations

from pathlib import Path

from biointel.portfolio.project_registry import ProjectRecord, create_project, list_projects
from biointel.projects.catalog import PROJECT_CATALOG


def ensure_biotechnology_projects(registry_path: str | Path) -> list[ProjectRecord]:
    """Idempotently register the five applied biotechnology projects."""

    existing = {project.project_code: project for project in list_projects(registry_path)}
    created: list[ProjectRecord] = []
    for definition in PROJECT_CATALOG:
        if definition.code in existing:
            created.append(existing[definition.code])
            continue
        record = create_project(
            registry_path,
            project_code=definition.code,
            name=definition.title,
            status="Active",
            priority="High",
            objective=definition.objective,
            owner_label="BioIntel Applied Research",
            tags=list(definition.tags),
            notes=(
                "Deep professional local analysis workbench upgraded in Step 49 with quality gates, method cards, HTML reports and persistent run history. "
                "Bundled inputs are deterministic demo/reference assets; real-study evidence, "
                "independent validation and domain review remain pending."
            ),
        )
        created.append(record)
    return created
