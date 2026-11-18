from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

PERSISTENT_DIRECTORIES: tuple[str, ...] = (
    "data",
    "reports",
    "workspace",
    "exports",
    "projects",
)
MANIFEST_NAME = "BIOINTEL_BACKUP_MANIFEST.json"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(path: Path, root: Path) -> str:
    relative = path.resolve().relative_to(root.resolve())
    if any(part in {"..", ""} for part in relative.parts):
        raise ValueError(f"Unsafe relative path: {path}")
    return relative.as_posix()


def build_manifest(root: str | Path, *, label: str = "user-data") -> dict[str, object]:
    base = Path(root).expanduser().resolve()
    files: list[dict[str, object]] = []
    if base.exists():
        for path in sorted((item for item in base.rglob("*") if item.is_file()), key=lambda item: item.as_posix().lower()):
            if path.name == MANIFEST_NAME:
                continue
            files.append({
                "path": _safe_relative(path, base),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            })
    return {
        "schema": "biointel.user-data-backup.v2",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "label": label,
        "root_name": base.name,
        "file_count": len(files),
        "total_size_bytes": sum(int(row["size_bytes"]) for row in files),
        "files": files,
    }


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


@dataclass(frozen=True)
class BackupValidation:
    valid: bool
    checked_files: int
    missing_files: tuple[str, ...]
    mismatched_files: tuple[str, ...]
    unexpected_files: tuple[str, ...]
    manifest_path: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def validate_backup(backup_directory: str | Path, *, reject_unexpected: bool = False) -> BackupValidation:
    root = Path(backup_directory).expanduser().resolve()
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        return BackupValidation(False, 0, (MANIFEST_NAME,), (), (), str(manifest_path))
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return BackupValidation(False, 0, (), (MANIFEST_NAME,), (), str(manifest_path))
    expected = {str(row["path"]): row for row in manifest.get("files", [])}
    missing: list[str] = []
    mismatched: list[str] = []
    for relative, row in expected.items():
        path = root / relative
        try:
            path.resolve().relative_to(root)
        except ValueError:
            mismatched.append(relative)
            continue
        if not path.is_file():
            missing.append(relative)
            continue
        if path.stat().st_size != int(row.get("size_bytes", -1)) or sha256_file(path) != str(row.get("sha256", "")):
            mismatched.append(relative)
    observed = {
        _safe_relative(path, root)
        for path in root.rglob("*")
        if path.is_file() and path.name != MANIFEST_NAME
    }
    unexpected = sorted(observed - set(expected))
    valid = not missing and not mismatched and (not reject_unexpected or not unexpected)
    return BackupValidation(valid, len(expected), tuple(sorted(missing)), tuple(sorted(mismatched)), tuple(unexpected), str(manifest_path))


def merge_seed_tree(source: str | Path, destination: str | Path, *, overwrite: bool = False) -> dict[str, int]:
    """Merge packaged seed content without overwriting user-owned files by default."""

    src = Path(source).expanduser().resolve()
    dst = Path(destination).expanduser().resolve()
    if not src.is_dir():
        return {"copied": 0, "preserved": 0, "replaced": 0}
    dst.mkdir(parents=True, exist_ok=True)
    copied = preserved = replaced = 0
    for item in sorted(src.rglob("*"), key=lambda path: path.as_posix().lower()):
        relative = item.relative_to(src)
        target = dst / relative
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not overwrite:
            preserved += 1
            continue
        existed = target.exists()
        temp = target.with_name(target.name + ".biointel-seed.tmp")
        shutil.copy2(item, temp)
        os.replace(temp, target)
        if existed:
            replaced += 1
        else:
            copied += 1
    return {"copied": copied, "preserved": preserved, "replaced": replaced}


def create_backup(
    user_data_root: str | Path,
    backup_parent: str | Path,
    *,
    label: str = "upgrade",
    include_directories: Iterable[str] = PERSISTENT_DIRECTORIES,
) -> Path:
    source = Path(user_data_root).expanduser().resolve()
    parent = Path(backup_parent).expanduser().resolve()
    parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    destination = parent / f"BioIntel-{label}-{timestamp}"
    staging = Path(tempfile.mkdtemp(prefix=".biointel-backup-", dir=parent))
    try:
        selected = tuple(dict.fromkeys(str(name) for name in include_directories))
        for name in selected:
            src = source / name
            if src.exists():
                shutil.copytree(src, staging / name, copy_function=shutil.copy2, dirs_exist_ok=True)
        manifest = build_manifest(staging, label=label)
        manifest["source_root"] = str(source)
        manifest["persistent_directories"] = list(selected)
        _atomic_write_json(staging / MANIFEST_NAME, manifest)
        validation = validate_backup(staging)
        if not validation.valid:
            raise RuntimeError(f"Backup verification failed: {validation.to_dict()}")
        os.replace(staging, destination)
        return destination
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def restore_backup(
    backup_directory: str | Path,
    user_data_root: str | Path,
    *,
    overwrite: bool = True,
    mirror: bool = False,
) -> dict[str, int]:
    backup = Path(backup_directory).expanduser().resolve()
    destination = Path(user_data_root).expanduser().resolve()
    validation = validate_backup(backup)
    if not validation.valid:
        raise RuntimeError(f"Refusing to restore an invalid backup: {validation.to_dict()}")
    if mirror and destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    copied = preserved = replaced = 0
    for path in sorted(backup.rglob("*"), key=lambda item: item.as_posix().lower()):
        if not path.is_file() or path.name == MANIFEST_NAME:
            continue
        relative = path.relative_to(backup)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not overwrite:
            preserved += 1
            continue
        existed = target.exists()
        temp = target.with_name(target.name + ".biointel-restore.tmp")
        shutil.copy2(path, temp)
        os.replace(temp, target)
        if existed:
            replaced += 1
        else:
            copied += 1
    return {"copied": copied, "preserved": preserved, "replaced": replaced}
