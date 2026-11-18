from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    """Return the assembled BioIntel project root."""
    return Path(__file__).resolve().parents[3]


def user_data_root(candidate_project_root: str | Path | None = None) -> Path:
    """Resolve one shared Education data root for Streamlit, API, scripts, and tests."""
    configured = os.environ.get("BIOINTEL_USER_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()

    root = Path(candidate_project_root) if candidate_project_root else project_root()
    legacy = root / "UserData"
    if (legacy / "education" / "education.sqlite3").is_file():
        return legacy

    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return Path(local_app_data) / "BioIntelAI" / "UserData"
    return legacy


def education_paths(
    candidate_project_root: str | Path | None = None,
    *,
    demo: bool = False,
) -> tuple[Path, Path]:
    root = user_data_root(candidate_project_root)
    education_root = root / "education"
    database_name = "education-demo.sqlite3" if demo else "education.sqlite3"
    media_name = "demo-media" if demo else "media"
    return education_root / database_name, education_root / media_name