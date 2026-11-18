"""Safe reset of only the isolated Education demo database and media."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ..paths import education_paths


def validate_demo_targets(database_path: Path, media_path: Path) -> tuple[Path, Path]:
    database_path = Path(database_path)
    media_path = Path(media_path)
    if database_path.name != "education-demo.sqlite3":
        raise ValueError("Refusing to operate on a non-demo database path.")
    if media_path.name != "demo-media":
        raise ValueError("Refusing to operate on a non-demo media path.")
    if database_path.parent != media_path.parent or database_path.parent.name != "education":
        raise ValueError("Demo database and media must share the Education data directory.")
    if database_path.is_symlink() or media_path.is_symlink():
        raise ValueError("Refusing to operate on symbolic-link demo targets.")
    resolved_database = database_path.resolve(strict=False)
    resolved_media = media_path.resolve(strict=False)
    if resolved_database.parent != resolved_media.parent:
        raise ValueError("Resolved demo targets do not share a directory.")
    if resolved_database.name != "education-demo.sqlite3" or resolved_media.name != "demo-media":
        raise ValueError("Resolved targets are not the exact demo paths.")
    if resolved_database.parent.name != "education":
        raise ValueError("Resolved demo targets are outside the Education data directory.")
    if resolved_database == Path(resolved_database.anchor) or resolved_media == Path(resolved_media.anchor):
        raise ValueError("Refusing to operate on a filesystem root.")
    return resolved_database, resolved_media


def reset_demo(candidate_project_root: str | Path | None = None) -> dict[str, Any]:
    database_path, media_path = education_paths(candidate_project_root, demo=True)
    database_path, media_path = validate_demo_targets(database_path, media_path)
    removed: list[str] = []
    for candidate in (
        database_path,
        database_path.with_name(database_path.name + "-wal"),
        database_path.with_name(database_path.name + "-shm"),
    ):
        if candidate.is_file():
            candidate.unlink()
            removed.append(str(candidate))
    if media_path.is_dir():
        shutil.rmtree(media_path)
        removed.append(str(media_path))
    return {
        "status": "reset", "is_demo": True,
        "database_path": str(database_path), "media_path": str(media_path),
        "removed": removed,
    }

