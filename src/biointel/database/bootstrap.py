from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from biointel.assets.research_assets import initialize_asset_store
from biointel.connected.registry import initialize_registry as initialize_connected_registry
from biointel.data.dataset_registry import initialize_dataset_registry
from biointel.data.evidence_registry import initialize_evidence_registry
from biointel.data.relationship_integrity import initialize_relationship_registry
from biointel.data.scientific_registry import initialize_scientific_registries
from biointel.database.core import execute_script
from biointel.documents.history import initialize_document_history
from biointel.dti.feature_cache import FeatureCache
from biointel.intelligence.data_intelligence import clear_database_fleet_cache, database_paths
from biointel.intelligence.knowledge_warehouse import initialize_knowledge_warehouse
from biointel.internet.download_registry import initialize_download_registry
from biointel.jobs.local_queue import LocalJobQueue
from biointel.multitenancy.store import TenantStore
from biointel.observability.analytics_store import initialize_analytics_store
from biointel.portfolio.project_registry import initialize_project_registry
from biointel.realworld.evidence import RealWorldEvidenceRegistry
from biointel.scientific.prospective import ProspectiveStudyRegistry
from biointel.scientific.validation_depth import ValidationEvidenceRegistry
from biointel.training.experiment_registry import initialize_registry as initialize_experiment_registry

_GENERIC_SCHEMA = """
CREATE TABLE IF NOT EXISTS biointel_registry_metadata(
    registry_key TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    initialized_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


@dataclass(frozen=True)
class BootstrapResult:
    initialized: tuple[str, ...]
    migrated: tuple[str, ...]
    failures: dict[str, str]

    @property
    def passed(self) -> bool:
        return not self.failures


def _migrate_legacy_database(project_root: Path, destination: Path) -> bool:
    if destination.is_file():
        return False
    candidates = (
        project_root / "reports" / destination.name,
        project_root / "data" / destination.name,
        project_root / "UserData" / "databases" / destination.name,
    )
    for source in candidates:
        if source.is_file() and source.resolve() != destination.resolve():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            return True
    return False


def bootstrap_databases(root: str | Path) -> BootstrapResult:
    """Create every active local registry before readiness is evaluated.

    The operation is idempotent and migrates an existing legacy database out of
    the immutable application tree on first run.
    """

    project_root = Path(root).resolve()
    paths = database_paths(project_root)
    initialized: list[str] = []
    migrated: list[str] = []
    failures: dict[str, str] = {}

    for key, destination in paths.items():
        try:
            if _migrate_legacy_database(project_root, destination):
                migrated.append(key)
        except OSError as exc:
            failures[key] = f"legacy migration failed: {exc}"

    initializers: dict[str, Callable[[], object]] = {
        "knowledge": lambda: initialize_knowledge_warehouse(paths["knowledge"]),
        "analytics": lambda: initialize_analytics_store(paths["analytics"]),
        "assets": lambda: initialize_asset_store(paths["assets"]),
        "downloads": lambda: initialize_download_registry(paths["downloads"]),
        "evidence": lambda: initialize_evidence_registry(paths["evidence"]),
        "documents": lambda: initialize_document_history(paths["documents"]),
        "datasets": lambda: initialize_dataset_registry(paths["datasets"]),
        "experiments": lambda: initialize_experiment_registry(paths["experiments"]),
        "projects": lambda: initialize_project_registry(paths["projects"]),
        "relationships": lambda: initialize_relationship_registry(paths["relationships"]),
        "connected_sources": lambda: initialize_connected_registry(paths["connected_sources"]),
        "jobs": lambda: LocalJobQueue(paths["jobs"]),
        "feature_cache": lambda: FeatureCache(paths["feature_cache"]),
        "tenants": lambda: TenantStore(paths["tenants"]),
        "prospective_validation": lambda: ProspectiveStudyRegistry(paths["prospective_validation"]),
        "validation_evidence": lambda: ValidationEvidenceRegistry(paths["validation_evidence"]),
        "realworld_evidence": lambda: RealWorldEvidenceRegistry(paths["realworld_evidence"]),
    }

    for key, initializer in initializers.items():
        try:
            initializer()
            initialized.append(key)
        except Exception as exc:  # surfaced in readiness; never silently ignored
            failures[key] = f"{type(exc).__name__}: {exc}"

    try:
        initialize_scientific_registries(project_root)
        initialized.append("scientific_extensions")
    except Exception as exc:
        failures["scientific_extensions"] = f"{type(exc).__name__}: {exc}"

    for key, destination in paths.items():
        if key in initializers or key in failures:
            continue
        try:
            execute_script(destination, _GENERIC_SCHEMA)
            initialized.append(key)
        except Exception as exc:
            failures[key] = f"{type(exc).__name__}: {exc}"

    clear_database_fleet_cache()
    return BootstrapResult(tuple(sorted(set(initialized))), tuple(sorted(set(migrated))), failures)


__all__ = ["BootstrapResult", "bootstrap_databases"]
