from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def user_data_root(root: str | Path | None = None) -> Path:
    if root is not None:
        return Path(root).expanduser().resolve()
    configured = os.environ.get("BIOINTEL_USER_DATA_DIR", "").strip()
    return Path(configured).expanduser().resolve() if configured else (project_root() / "UserData").resolve()


def engine_home(root: str | Path | None = None) -> Path:
    base = user_data_root(root) / "engine_platform_v196"
    for child in (base, base / "packs", base / "staging", base / "logs", base / "reports", base / "locks"):
        child.mkdir(parents=True, exist_ok=True)
    return base


def tools_root(root: str | Path | None = None) -> Path:
    configured = os.environ.get("BIOINTEL_TOOLS_DIR", "").strip()
    if configured:
        path = Path(configured).expanduser().resolve()
    else:
        local = os.environ.get("LOCALAPPDATA", "").strip()
        path = Path(local).expanduser().resolve() / "BioIntelAI" / "Tools" if local else user_data_root(root) / "Tools"
    path.mkdir(parents=True, exist_ok=True)
    return path


def contained_path(base: str | Path, relative: str | Path) -> Path:
    base_path = Path(base).expanduser().resolve()
    candidate = (base_path / Path(relative)).resolve()
    try:
        candidate.relative_to(base_path)
    except ValueError as exc:
        raise ValueError("Path escapes the permitted engine directory.") from exc
    return candidate
