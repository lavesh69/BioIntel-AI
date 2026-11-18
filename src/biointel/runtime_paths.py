from __future__ import annotations

import os
from pathlib import Path


def user_data_root(project_root: str | Path) -> Path:
    """Return the canonical writable BioIntel user-data root.

    Windows installations always default to ``%LOCALAPPDATA%/BioIntelAI/UserData``.
    Tests and non-Windows source runs retain a project-local fallback unless an
    explicit ``BIOINTEL_USER_DATA_DIR`` or XDG data directory is configured.
    """

    configured = os.environ.get("BIOINTEL_USER_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return (Path(local_app_data).expanduser() / "BioIntelAI" / "UserData").resolve()

    if os.name == "nt":
        return (Path.home() / "AppData" / "Local" / "BioIntelAI" / "UserData").resolve()

    xdg_data_home = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg_data_home:
        return (Path(xdg_data_home).expanduser() / "BioIntelAI" / "UserData").resolve()

    return (Path(project_root).expanduser().resolve() / "UserData").resolve()



def _project_local_compatibility_layout(project_root: str | Path) -> bool:
    """Preserve the historical source-tree layout only for unconfigured non-Windows runs.

    Packaged Windows builds and explicitly configured environments always use the
    isolated UserData tree. This keeps legacy developer tests compatible without
    reintroducing mutable files into managed Windows installations.
    """
    if os.environ.get("BIOINTEL_PROJECT_LOCAL_RUNTIME", "").strip().casefold() in {
        "1",
        "true",
        "yes",
    }:
        return True
    return (
        os.name != "nt"
        and not os.environ.get("BIOINTEL_USER_DATA_DIR", "").strip()
        and not os.environ.get("LOCALAPPDATA", "").strip()
        and not os.environ.get("XDG_DATA_HOME", "").strip()
    )


def user_data_path(project_root: str | Path, *parts: str) -> Path:
    return user_data_root(project_root).joinpath(*parts)


def runtime_database_directory(project_root: str | Path) -> Path:
    if _project_local_compatibility_layout(project_root):
        return Path(project_root).expanduser().resolve() / "reports"
    return user_data_path(project_root, "databases")


def runtime_database_path(project_root: str | Path, filename: str) -> Path:
    """Return a canonical writable database path by filename."""
    return runtime_database_directory(project_root) / Path(filename).name


def runtime_api_directory(project_root: str | Path) -> Path:
    return user_data_path(project_root, "runtime", "api")


def runtime_reports_directory(project_root: str | Path) -> Path:
    """Return the writable reports/audit directory outside managed Windows source."""
    if _project_local_compatibility_layout(project_root):
        return Path(project_root).expanduser().resolve() / "reports"
    return user_data_path(project_root, "reports")


def runtime_data_directory(project_root: str | Path) -> Path:
    """Return the writable generated-data directory outside managed Windows source."""
    if _project_local_compatibility_layout(project_root):
        return Path(project_root).expanduser().resolve() / "data"
    return user_data_path(project_root, "data")


def runtime_workspace_directory(project_root: str | Path) -> Path:
    """Return the writable workspace directory outside managed Windows source."""
    if _project_local_compatibility_layout(project_root):
        return Path(project_root).expanduser().resolve() / "workspace"
    return user_data_path(project_root, "workspace")


def runtime_report_path(project_root: str | Path, *parts: str) -> Path:
    return runtime_reports_directory(project_root).joinpath(*parts)


def runtime_data_path(project_root: str | Path, *parts: str) -> Path:
    return runtime_data_directory(project_root).joinpath(*parts)


__all__ = [
    "runtime_api_directory",
    "runtime_database_directory",
    "runtime_database_path",
    "runtime_data_directory",
    "runtime_data_path",
    "runtime_report_path",
    "runtime_reports_directory",
    "runtime_workspace_directory",
    "user_data_path",
    "user_data_root",
]
