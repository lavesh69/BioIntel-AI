from __future__ import annotations

import hashlib
import importlib.metadata
import io
import json
import os
import platform
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, Iterable, Mapping

from .models import PlatformConflictError, PlatformValidationError, utc_now
from .storage import DiscoveryPlatformStore

DEFAULT_PACKAGES = (
    "numpy", "pandas", "scipy", "scikit-learn", "streamlit", "fastapi",
    "biopython", "anndata", "h5py", "pydicom", "nibabel", "pymzml",
)
SECRET_MARKERS = ("SECRET", "TOKEN", "PASSWORD", "PRIVATE_KEY", "API_KEY", "CREDENTIAL")


def _command_version(arguments: list[str], timeout: float = 3.0) -> str:
    try:
        result = subprocess.run(
            arguments,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            shell=False,
            creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    return next((line.strip() for line in combined.splitlines() if line.strip()), "")


def environment_manifest(
    package_names: Iterable[str] = DEFAULT_PACKAGES,
    *,
    source_root: str | Path | None = None,
) -> dict[str, Any]:
    packages: dict[str, str] = {}
    for name in package_names:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not installed"
    rscript = shutil_which("Rscript")
    version_file = Path(source_root).resolve() / "VERSION" if source_root else None
    return {
        "captured_at_utc": utc_now(),
        "os": platform.platform(),
        "machine": platform.machine(),
        "python": sys.version,
        "python_executable": sys.executable,
        "r_version": _command_version([rscript, "--version"]) if rscript else "not installed",
        "packages": packages,
        "environment": {
            key: value
            for key, value in sorted(os.environ.items())
            if not any(marker in key.upper() for marker in SECRET_MARKERS)
            and key.upper() in {
                "PATH", "PYTHONPATH", "R_HOME", "JAVA_HOME", "BIOINTEL_USER_DATA",
                "OMP_NUM_THREADS", "MKL_NUM_THREADS", "CUDA_VISIBLE_DEVICES",
            }
        },
        "source_version": (
            version_file.read_text(encoding="utf-8").strip()
            if version_file and version_file.is_file()
            else ""
        ),
    }


def shutil_which(name: str) -> str | None:
    from shutil import which

    return which(name)


def file_hashes(paths: Iterable[str | Path]) -> dict[str, str]:
    output: dict[str, str] = {}
    for raw_path in paths:
        path = Path(raw_path).resolve()
        if not path.is_file():
            raise PlatformValidationError(f"File was not found for hashing: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        output[str(path)] = digest.hexdigest()
    return output


class ReproducibilityManager:
    def __init__(self, store: DiscoveryPlatformStore):
        self.store = store

    def manifest(self, run_id: str) -> dict[str, Any]:
        run = self.store.row("runs", "run_id", run_id)
        if run is None:
            raise KeyError(run_id)
        artifacts = self.store.rows(
            "artifacts", filters={"run_id": run_id},
            order_by="created_at_utc", descending=False, limit=5000,
        )
        steps = self.store.rows(
            "run_steps", filters={"run_id": run_id},
            order_by="started_at_utc", descending=False, limit=5000,
        )
        manifest = {
            "schema": "biointel.reproducibility.v1",
            "generated_at_utc": utc_now(),
            "run": run,
            "steps": steps,
            "artifacts": [
                {
                    "artifact_id": item["artifact_id"], "name": item["name"],
                    "sha256": item["sha256"], "size_bytes": item["size_bytes"],
                    "media_type": item["media_type"], "path": item["path"],
                }
                for item in artifacts
            ],
        }
        manifest["manifest_sha256"] = hashlib.sha256(
            json.dumps(manifest, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return manifest

    def verify(self, run_id: str) -> dict[str, Any]:
        manifest = self.manifest(run_id)
        checks = []
        for artifact in manifest["artifacts"]:
            path = Path(artifact["path"])
            if not path.is_file():
                checks.append(
                    {"artifact_id": artifact["artifact_id"], "status": "missing"}
                )
                continue
            actual = file_hashes([path])[str(path.resolve())]
            checks.append(
                {
                    "artifact_id": artifact["artifact_id"],
                    "status": "verified" if actual == artifact["sha256"] else "hash mismatch",
                    "expected": artifact["sha256"], "actual": actual,
                }
            )
        return {
            "run_id": run_id,
            "valid": all(item["status"] == "verified" for item in checks),
            "checks": checks,
        }

    def environment_drift(self, run_id: str) -> dict[str, Any]:
        run = self.store.row("runs", "run_id", run_id)
        if run is None:
            raise KeyError(run_id)
        recorded = run.get("environment") or {}
        current = environment_manifest()
        recorded_packages = recorded.get("packages") or {}
        current_packages = current.get("packages") or {}
        package_changes = {
            name: {"recorded": recorded_packages.get(name), "current": current_packages.get(name)}
            for name in sorted(set(recorded_packages) | set(current_packages))
            if recorded_packages.get(name) != current_packages.get(name)
        }
        return {
            "run_id": run_id,
            "drift_detected": bool(
                recorded.get("os") != current.get("os")
                or recorded.get("python") != current.get("python")
                or package_changes
            ),
            "os_changed": recorded.get("os") != current.get("os"),
            "python_changed": recorded.get("python") != current.get("python"),
            "package_changes": package_changes,
        }

    def export_package(
        self, run_id: str, *, include_artifacts: bool = True
    ) -> bytes:
        manifest = self.manifest(run_id)
        files: dict[str, bytes] = {
            "manifest.json": json.dumps(
                manifest, indent=2, sort_keys=True, default=str
            ).encode("utf-8")
        }
        if include_artifacts:
            for artifact in manifest["artifacts"]:
                path = Path(artifact["path"])
                if not path.is_file():
                    continue
                name = f"artifacts/{artifact['artifact_id']}/{path.name}"
                if name in files:
                    raise PlatformConflictError(f"Duplicate package path: {name}")
                files[name] = path.read_bytes()
        package_manifest = {
            "schema": "biointel.reproducibility.package.v1",
            "run_id": run_id,
            "files": {
                name: {
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "size_bytes": len(content),
                }
                for name, content in sorted(files.items())
            },
        }
        files["package_manifest.json"] = json.dumps(
            package_manifest, indent=2, sort_keys=True
        ).encode("utf-8")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in sorted(files.items()):
                archive.writestr(name, content)
        return buffer.getvalue()

    def import_package(self, content: bytes) -> dict[str, Any]:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            bad = archive.testzip()
            if bad:
                raise PlatformValidationError(f"Reproducibility package CRC failed: {bad}")
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise PlatformValidationError("Reproducibility package has duplicate paths")
            if "package_manifest.json" not in names or "manifest.json" not in names:
                raise PlatformValidationError("Reproducibility package manifest is missing")
            for name in names:
                path = Path(name)
                if path.is_absolute() or ".." in path.parts:
                    raise PlatformValidationError(f"Unsafe package path: {name}")
            package_manifest = json.loads(archive.read("package_manifest.json"))
            failures = []
            for name, expected in package_manifest.get("files", {}).items():
                if name not in names:
                    failures.append({"name": name, "status": "missing"})
                    continue
                actual = hashlib.sha256(archive.read(name)).hexdigest()
                if actual != expected["sha256"]:
                    failures.append(
                        {"name": name, "status": "hash mismatch", "actual": actual}
                    )
            if failures:
                raise PlatformValidationError(
                    "Reproducibility package hash verification failed"
                )
            manifest = json.loads(archive.read("manifest.json"))
        return {
            "valid": True,
            "run_id": manifest.get("run", {}).get("run_id"),
            "manifest": manifest,
            "files": len(names),
        }


__all__ = [
    "ReproducibilityManager",
    "environment_manifest",
    "file_hashes",
]
