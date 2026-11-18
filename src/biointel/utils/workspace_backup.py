from __future__ import annotations

import hashlib
import io
import json
import stat
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from biointel.runtime_paths import (
    runtime_data_directory,
    runtime_database_directory,
    runtime_reports_directory,
)
from biointel.utils.atomic_io import atomic_write_bytes

BACKUP_FORMAT_VERSION = "1.0"
ALLOWED_PREFIXES = ("models/", "databases/", "reports/", "data/", "cache/external/")
PROTECTED_MODEL_PREFIX = "models/demo_"
MAX_BACKUP_FILES = 5000
MAX_UNCOMPRESSED_BYTES = 250 * 1024 * 1024
MAX_COMPRESSED_BYTES = 250 * 1024 * 1024
EPHEMERAL_REPORT_PREFIXES = ("runtime_logs/",)
EPHEMERAL_PARTS = {"__pycache__", ".pytest_cache", ".ruff_cache"}
EPHEMERAL_SUFFIXES = (".tmp", "-wal", "-shm", ".pyc")
DATABASE_SUFFIXES = {".sqlite3", ".sqlite", ".db"}


@dataclass(frozen=True)
class BackupSummary:
    file_count: int
    total_bytes: int
    created_at_utc: str
    included_demo_models: bool
    included_cache: bool
    files: tuple[str, ...]


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _safe_archive_name(name: str) -> bool:
    normalized = str(name).replace("\\", "/")
    path = PurePosixPath(normalized)
    if normalized != name or path.is_absolute() or ".." in path.parts or not path.parts:
        return False
    return any(normalized.startswith(prefix) for prefix in ALLOWED_PREFIXES)


def _zipinfo_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o170000
    return mode == stat.S_IFLNK


def _include_file(relative: str) -> bool:
    path = PurePosixPath(relative)
    if any(part in EPHEMERAL_PARTS for part in path.parts):
        return False
    return not relative.endswith(EPHEMERAL_SUFFIXES)


def _include_report_file(relative: str) -> bool:
    if any(relative.startswith(prefix) for prefix in EPHEMERAL_REPORT_PREFIXES):
        return False
    return _include_file(relative)


def _add_tree(selected: dict[str, bytes], source: Path, archive_prefix: str, *, report: bool = False) -> None:
    if not source.exists():
        return
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.name == ".gitkeep":
            continue
        relative = path.relative_to(source).as_posix()
        if not (_include_report_file(relative) if report else _include_file(relative)):
            continue
        selected[f"{archive_prefix}/{relative}"] = path.read_bytes()


def create_workspace_backup(
    project_root: str | Path,
    include_demo_models: bool = False,
    include_cache: bool = False,
) -> bytes:
    """Create a portable backup of user-owned models, databases, reports and data.

    Runtime directories can live outside the installed source tree. Archive names
    therefore use stable virtual prefixes instead of host-specific absolute paths.
    SQLite WAL/SHM files and ephemeral caches are deliberately excluded.
    """

    root = Path(project_root).resolve()
    selected: dict[str, bytes] = {}

    models = root / "models"
    if models.exists():
        for path in sorted(models.iterdir()):
            if not path.is_file() or path.name == "README.md":
                continue
            if path.name.startswith("demo_") and not include_demo_models:
                continue
            selected[f"models/{path.name}"] = path.read_bytes()

    databases = runtime_database_directory(root).resolve()
    reports = runtime_reports_directory(root).resolve()
    data = runtime_data_directory(root).resolve()

    if databases == reports:
        # Legacy source layout stores reports and SQLite files together.
        if databases.exists():
            for path in sorted(databases.rglob("*")):
                if not path.is_file() or path.name == ".gitkeep":
                    continue
                relative = path.relative_to(databases).as_posix()
                if not _include_file(relative):
                    continue
                # Preserve the historical reports/ archive contract for unconfigured
                # developer layouts; isolated packaged runtimes use databases/.
                prefix = "reports"
                if not _include_report_file(relative):
                    continue
                selected[f"{prefix}/{relative}"] = path.read_bytes()
    else:
        _add_tree(selected, databases, "databases")
        _add_tree(selected, reports, "reports", report=True)

    if data not in {databases, reports}:
        _add_tree(selected, data, "data")

    if include_cache:
        _add_tree(selected, root / "cache" / "external", "cache/external")

    if len(selected) > MAX_BACKUP_FILES:
        raise ValueError(f"Backup exceeds the {MAX_BACKUP_FILES}-file limit.")

    total_bytes = sum(len(content) for content in selected.values())
    if total_bytes > MAX_UNCOMPRESSED_BYTES:
        raise ValueError("Backup exceeds the 250 MB uncompressed limit.")

    created_at = datetime.now(UTC).isoformat(timespec="seconds")
    manifest = {
        "backup_format_version": BACKUP_FORMAT_VERSION,
        "created_at_utc": created_at,
        "included_demo_models": include_demo_models,
        "included_cache": include_cache,
        "file_count": len(selected),
        "total_bytes": total_bytes,
        "sha256": {name: _sha256(content) for name, content in selected.items()},
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "WORKSPACE_MANIFEST.json",
            json.dumps(manifest, indent=2, sort_keys=True),
        )
        for name, content in selected.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def inspect_workspace_backup(backup_bytes: bytes) -> BackupSummary:
    """Validate a backup and return a safe summary without extracting it."""

    if len(backup_bytes) > MAX_COMPRESSED_BYTES:
        raise ValueError("Backup ZIP exceeds the supported size limit.")

    try:
        archive_context = zipfile.ZipFile(io.BytesIO(backup_bytes), "r")
    except zipfile.BadZipFile as exc:
        raise ValueError("Workspace backup is not a valid ZIP archive.") from exc

    with archive_context as archive:
        infos = archive.infolist()
        if len(infos) > MAX_BACKUP_FILES + 1:
            raise ValueError("Backup contains too many files.")
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError("Backup contains duplicate archive paths.")
        if "WORKSPACE_MANIFEST.json" not in names:
            raise ValueError("Workspace manifest is missing.")

        try:
            manifest = json.loads(archive.read("WORKSPACE_MANIFEST.json").decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Workspace manifest is invalid.") from exc
        if manifest.get("backup_format_version") != BACKUP_FORMAT_VERSION:
            raise ValueError("Unsupported workspace backup version.")

        expected_hashes = manifest.get("sha256")
        if not isinstance(expected_hashes, dict):
            raise ValueError("Workspace manifest hashes are invalid.")

        total_uncompressed = 0
        checked_files: list[str] = []
        for info in infos:
            if info.filename == "WORKSPACE_MANIFEST.json" or info.is_dir():
                continue
            if info.flag_bits & 0x1:
                raise ValueError("Encrypted backup entries are not supported.")
            if _zipinfo_is_symlink(info):
                raise ValueError(f"Symbolic links are not allowed: {info.filename}")
            if not _safe_archive_name(info.filename):
                raise ValueError(f"Unsafe backup path: {info.filename}")
            total_uncompressed += int(info.file_size)
            if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                raise ValueError("Backup exceeds the 250 MB uncompressed limit.")
            content = archive.read(info.filename)
            if expected_hashes.get(info.filename) != _sha256(content):
                raise ValueError(f"Checksum mismatch: {info.filename}")
            checked_files.append(info.filename)

        if set(checked_files) != set(expected_hashes):
            raise ValueError("Backup file list does not match its manifest.")
        if int(manifest.get("file_count", -1)) != len(checked_files):
            raise ValueError("Backup manifest file count is inconsistent.")
        if int(manifest.get("total_bytes", -1)) != total_uncompressed:
            raise ValueError("Backup manifest byte count is inconsistent.")

        return BackupSummary(
            file_count=len(checked_files),
            total_bytes=total_uncompressed,
            created_at_utc=str(manifest["created_at_utc"]),
            included_demo_models=bool(manifest.get("included_demo_models", False)),
            included_cache=bool(manifest.get("included_cache", False)),
            files=tuple(sorted(checked_files)),
        )


def _restore_destination(root: Path, name: str) -> Path:
    path = PurePosixPath(name)
    parts = path.parts
    prefix = parts[0]
    remainder = Path(*parts[1:])
    if prefix == "models":
        base = (root / "models").resolve()
    elif prefix == "databases":
        base = runtime_database_directory(root).resolve()
    elif prefix == "reports":
        # Backward compatibility: legacy backups put SQLite registries under reports/.
        base = (
            runtime_database_directory(root).resolve()
            if remainder.suffix.lower() in DATABASE_SUFFIXES
            else runtime_reports_directory(root).resolve()
        )
    elif prefix == "data":
        base = runtime_data_directory(root).resolve()
    elif prefix == "cache" and len(parts) >= 3 and parts[1] == "external":
        base = (root / "cache" / "external").resolve()
        remainder = Path(*parts[2:])
    else:
        raise ValueError(f"Unsupported backup destination: {name}")
    destination = (base / remainder).resolve()
    try:
        destination.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"Backup destination escapes its managed root: {name}") from exc
    return destination


def restore_workspace_backup(
    project_root: str | Path,
    backup_bytes: bytes,
    overwrite: bool = False,
    allow_demo_models: bool = False,
) -> dict[str, object]:
    """Restore validated files into their canonical managed runtime directories."""

    root = Path(project_root).resolve()
    summary = inspect_workspace_backup(backup_bytes)
    restored: list[str] = []
    skipped: list[str] = []

    with zipfile.ZipFile(io.BytesIO(backup_bytes), "r") as archive:
        for name in summary.files:
            if name.startswith(PROTECTED_MODEL_PREFIX) and not allow_demo_models:
                skipped.append(name)
                continue
            destination = _restore_destination(root, name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and not overwrite:
                skipped.append(name)
                continue
            atomic_write_bytes(destination, archive.read(name))
            restored.append(name)

    return {
        "restored": restored,
        "skipped": skipped,
        "restored_count": len(restored),
        "skipped_count": len(skipped),
        "backup_created_at_utc": summary.created_at_utc,
    }
