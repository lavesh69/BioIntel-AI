from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from biointel.runtime_paths import (
    runtime_data_directory,
    runtime_database_directory,
    runtime_reports_directory,
)


@dataclass(frozen=True)
class ManagedFile:
    category: str
    name: str
    relative_path: str
    size_bytes: int
    protected: bool


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _iter_files(root: Path):
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != ".gitkeep":
            yield path


def list_managed_files(project_root: str | Path) -> list[ManagedFile]:
    """List user-manageable files through stable virtual paths.

    Runtime data may live outside the installed source tree (for example under
    ``%LOCALAPPDATA%``).  Exposing virtual prefixes avoids leaking absolute
    filesystem paths and keeps delete/backup operations portable.
    """

    root = Path(project_root).resolve()
    managed: list[ManagedFile] = []

    models = root / "models"
    if models.exists():
        for path in sorted(models.iterdir()):
            if not path.is_file() or path.name == "README.md":
                continue
            managed.append(
                ManagedFile(
                    category="Model artifact",
                    name=path.name,
                    relative_path=f"models/{path.name}",
                    size_bytes=path.stat().st_size,
                    protected=path.name.startswith("demo_"),
                )
            )

    databases = runtime_database_directory(root).resolve()
    reports = runtime_reports_directory(root).resolve()
    data = runtime_data_directory(root).resolve()

    # In legacy developer layout databases and reports share one directory.
    # Classify SQLite files as databases and avoid listing them twice.
    database_files: set[Path] = set()
    for path in _iter_files(databases) or ():
        if databases == reports and path.suffix.lower() not in {".sqlite3", ".sqlite", ".db"}:
            continue
        if path.name.endswith(("-wal", "-shm")):
            continue
        database_files.add(path.resolve())
        database_prefix = "reports" if databases == reports else "databases"
        managed.append(
            ManagedFile(
                category="Local database",
                name=path.name,
                relative_path=f"{database_prefix}/{path.relative_to(databases).as_posix()}",
                size_bytes=path.stat().st_size,
                protected=False,
            )
        )

    for path in _iter_files(reports) or ():
        if path.resolve() in database_files or path.name.endswith(("-wal", "-shm")):
            continue
        managed.append(
            ManagedFile(
                category="Report / local history",
                name=path.name,
                relative_path=f"reports/{path.relative_to(reports).as_posix()}",
                size_bytes=path.stat().st_size,
                protected=False,
            )
        )

    # Generated workspace data is user-owned and should be discoverable too.
    if data != reports and data != databases:
        for path in _iter_files(data) or ():
            managed.append(
                ManagedFile(
                    category="Generated data",
                    name=path.name,
                    relative_path=f"data/{path.relative_to(data).as_posix()}",
                    size_bytes=path.stat().st_size,
                    protected=False,
                )
            )

    external_cache = root / "cache" / "external"
    for path in _iter_files(external_cache) or ():
        managed.append(
            ManagedFile(
                category="External database cache",
                name=path.name,
                relative_path=f"cache/external/{path.relative_to(external_cache).as_posix()}",
                size_bytes=path.stat().st_size,
                protected=False,
            )
        )

    return managed


def _resolve_virtual_path(root: Path, relative: str) -> tuple[Path, str]:
    virtual = PurePosixPath(str(relative).replace("\\", "/"))
    if virtual.is_absolute() or ".." in virtual.parts or len(virtual.parts) < 2:
        raise ValueError(f"Refusing to delete an unmanaged path: {relative}")

    prefix = virtual.parts[0]
    remainder = Path(*virtual.parts[1:])
    targets = {
        "models": (root / "models").resolve(),
        "databases": runtime_database_directory(root).resolve(),
        "reports": runtime_reports_directory(root).resolve(),
        "data": runtime_data_directory(root).resolve(),
        "cache": (root / "cache").resolve(),
    }
    if prefix == "cache":
        if len(virtual.parts) < 3 or virtual.parts[1] != "external":
            raise ValueError(f"Refusing to delete an unmanaged path: {relative}")
        base = (root / "cache" / "external").resolve()
        remainder = Path(*virtual.parts[2:])
    else:
        base = targets.get(prefix)
    if base is None or not remainder.parts:
        raise ValueError(f"Refusing to delete an unmanaged path: {relative}")

    candidate = (base / remainder).resolve()
    if not _inside(candidate, base):
        raise ValueError(f"Refusing to delete an unmanaged path: {relative}")
    return candidate, virtual.as_posix()


def delete_managed_files(
    project_root: str | Path,
    relative_paths: list[str],
    allow_demo_models: bool = False,
) -> list[str]:
    """Delete selected generated files using trusted virtual path prefixes."""

    root = Path(project_root).resolve()
    deleted: list[str] = []

    for relative in relative_paths:
        candidate, virtual = _resolve_virtual_path(root, relative)
        if virtual.startswith("models/"):
            if candidate.name == "README.md":
                raise ValueError("The models README is protected.")
            if candidate.name.startswith("demo_") and not allow_demo_models:
                raise ValueError("Bundled demo model files are protected by default.")
        if candidate.name.endswith(("-wal", "-shm")):
            raise ValueError("Live SQLite sidecar files cannot be deleted directly.")
        if candidate.is_file():
            candidate.unlink()
            deleted.append(virtual)

    return deleted


def directory_size_bytes(path: str | Path) -> int:
    root = Path(path)
    if not root.exists():
        return 0
    return sum(file.stat().st_size for file in root.rglob("*") if file.is_file())
