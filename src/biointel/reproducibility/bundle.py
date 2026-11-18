from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

FIXED_ZIP_TIMESTAMP = (2020, 1, 1, 0, 0, 0)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def _git_revision(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        revision = result.stdout.strip()
        return revision or None
    except (OSError, subprocess.SubprocessError):
        return None


def _package_versions(names: Iterable[str]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in sorted(set(names)):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    return versions


def _zip_write(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    safe = PurePosixPath(name)
    if safe.is_absolute() or ".." in safe.parts:
        raise ValueError(f"Unsafe archive path: {name}")
    info = zipfile.ZipInfo(str(safe), FIXED_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, data)


@dataclass(frozen=True)
class BundleVerification:
    valid: bool
    checked_files: int
    missing_files: tuple[str, ...]
    mismatched_files: tuple[str, ...]
    manifest_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def create_reproducibility_bundle(
    output: str | Path,
    *,
    project_root: str | Path,
    inputs: Iterable[str | Path],
    code_files: Iterable[str | Path],
    artifacts: Iterable[str | Path] = (),
    parameters: dict[str, Any] | None = None,
    random_seed: int | None = None,
    command: str = "",
    package_names: Iterable[str] = (
        "numpy", "pandas", "scikit-learn", "streamlit", "fastapi", "rdkit", "biopython"
    ),
    include_file_bytes: bool = True,
    maximum_embedded_file_bytes: int = 25 * 1024 * 1024,
) -> Path:
    root = Path(project_root).resolve()
    output_path = Path(output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    categories = {
        "inputs": [Path(item).resolve() for item in inputs],
        "code": [Path(item).resolve() for item in code_files],
        "artifacts": [Path(item).resolve() for item in artifacts],
    }
    entries: list[dict[str, Any]] = []
    embedded: list[tuple[str, bytes]] = []
    for category, paths in categories.items():
        for path in sorted(paths, key=lambda item: str(item)):
            if not path.is_file():
                raise FileNotFoundError(path)
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError:
                relative = path.name
            archive_name = f"files/{category}/{relative}"
            entry = {
                "category": category,
                "source_path": str(path),
                "archive_path": archive_name if include_file_bytes and path.stat().st_size <= maximum_embedded_file_bytes else None,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
            entries.append(entry)
            if entry["archive_path"]:
                embedded.append((archive_name, path.read_bytes()))
    manifest = {
        "schema": "biointel.reproducibility-bundle/v1",
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "project_root": str(root),
        "git_revision": _git_revision(root),
        "command": command,
        "parameters": parameters or {},
        "random_seed": random_seed,
        "environment": {
            "python": sys.version,
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "executable": sys.executable,
            "timezone": os.environ.get("TZ", "system-default"),
            "packages": _package_versions(package_names),
        },
        "files": entries,
        "verification": {
            "hash_algorithm": "sha256",
            "embedded_files": len(embedded),
            "total_files": len(entries),
        },
    }
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True, default=str).encode("utf-8")
    readme = (
        "BioIntel AI reproducibility bundle\n"
        "===================================\n\n"
        "Verify with: python -c \"from biointel.reproducibility import "
        "verify_reproducibility_bundle; print(verify_reproducibility_bundle('bundle.zip'))\"\n"
        "The manifest records inputs, code, outputs, parameters, random seed, environment and SHA-256 checksums.\n"
    ).encode("utf-8")
    with zipfile.ZipFile(output_path, "w") as archive:
        _zip_write(archive, "manifest.json", manifest_bytes)
        _zip_write(archive, "README.txt", readme)
        for archive_name, data in sorted(embedded):
            _zip_write(archive, archive_name, data)
    return output_path


def verify_reproducibility_bundle(path: str | Path) -> BundleVerification:
    bundle_path = Path(path).resolve()
    with zipfile.ZipFile(bundle_path, "r") as archive:
        manifest_bytes = archive.read("manifest.json")
        manifest = json.loads(manifest_bytes)
        names = set(archive.namelist())
        missing: list[str] = []
        mismatched: list[str] = []
        checked = 0
        for entry in manifest.get("files", []):
            archive_path = entry.get("archive_path")
            if not archive_path:
                continue
            checked += 1
            if archive_path not in names:
                missing.append(str(archive_path))
                continue
            data = archive.read(archive_path)
            if _sha256_bytes(data) != entry.get("sha256"):
                mismatched.append(str(archive_path))
    return BundleVerification(
        valid=not missing and not mismatched,
        checked_files=checked,
        missing_files=tuple(missing),
        mismatched_files=tuple(mismatched),
        manifest_sha256=_sha256_bytes(manifest_bytes),
    )
