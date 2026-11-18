from __future__ import annotations

import os
from pathlib import Path

from .analysis import ScientificAnalysisPlatform
from .execution import DependencyManager, ExecutionEngine
from .ingestion import ScientificFileIngestor
from .operations import LabOperationsService, SystemHealthService
from .provenance import ReproducibilityManager
from .reports import ScientificReportBuilder
from .security import LocalAuthenticationService
from .synthetic_bridge import SyntheticPlatformBridge
from .workflow import WorkflowRegistry
from .constants import ROLES
from .lifecycle import LifecycleService
from .models import validate_choice
from .research import ResearchService
from .storage import DiscoveryPlatformStore
from .workspace import WorkspaceService


def default_platform_paths(project_root: str | Path | None = None) -> tuple[Path, Path]:
    root = Path(project_root or Path(__file__).resolve().parents[3]).resolve()
    user_data = Path(os.environ.get("BIOINTEL_USER_DATA", root / "UserData")).resolve()
    reports = user_data / "reports"
    artifacts = user_data / "discovery_platform_artifacts"
    reports.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    return reports / "discovery_platform.sqlite3", artifacts


class DiscoveryPlatformService(LifecycleService, ResearchService, WorkspaceService):
    """Connected facade for the Step220 discovery platform."""

    def __init__(
        self,
        database_path: str | Path | None = None,
        artifact_root: str | Path | None = None,
        *,
        project_root: str | Path | None = None,
        store: DiscoveryPlatformStore | None = None,
        actor: str = "local_user",
        role: str = "Administrator",
    ):
        validate_choice(role, ROLES, "role")
        default_db, default_artifacts = default_platform_paths(project_root)
        if store is not None and (database_path is not None or artifact_root is not None):
            raise ValueError("Provide either a shared store or database/artifact paths")
        self.store = store or DiscoveryPlatformStore(
            database_path or default_db,
            artifact_root or default_artifacts,
        )
        self.actor = str(actor).strip() or "local_user"
        self.role = role
        self.analysis = ScientificAnalysisPlatform(self.store)
        self.dependencies = DependencyManager(self.store)
        self.execution = ExecutionEngine(self.store)
        self.ingestion = ScientificFileIngestor(self.store)
        self.workflows = WorkflowRegistry(self.store)
        self.reproducibility = ReproducibilityManager(self.store)
        self.reports = ScientificReportBuilder(
            self.store, actor=self.actor, role=self.role
        )
        self.authentication = LocalAuthenticationService(
            self.store, actor=self.actor, role=self.role
        )
        self.health = SystemHealthService(
            self.store,
            cache_roots=(self.store.artifact_root / "cache",),
            log_roots=(self.store.artifact_root / "logs",),
            temp_roots=(self.store.artifact_root / "temporary",),
        )
        self.lab_operations = LabOperationsService(
            self.store, actor=self.actor, role=self.role
        )
        self.synthetic = SyntheticPlatformBridge(
            self.store, actor=self.actor, role=self.role
        )


__all__ = ["DiscoveryPlatformService", "default_platform_paths"]
