from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    file_path = Path(path)
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_json(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return sha256_bytes(encoded)


def hash_dataframe(frame: pd.DataFrame) -> str:
    normalized = frame.copy()
    normalized.columns = [str(value) for value in normalized.columns]
    encoded = normalized.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return sha256_bytes(encoded)


def atomic_write_text(path: str | Path, text: str, encoding: str = "utf-8") -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding=encoding,
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
        temp_path = Path(handle.name)
    os.replace(temp_path, destination)
    return destination


def atomic_write_json(path: str | Path, payload: Any) -> Path:
    return atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


def package_versions(packages: Iterable[str] | None = None) -> dict[str, str]:
    names = tuple(packages or (
        "biointel-ai",
        "numpy",
        "pandas",
        "scipy",
        "scikit-learn",
        "biopython",
        "rdkit",
        "streamlit",
        "plotly",
        "fastapi",
    ))
    versions: dict[str, str] = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    return versions


def environment_snapshot() -> dict[str, Any]:
    return {
        "captured_at": utc_now(),
        "python": sys.version.splitlines()[0],
        "python_executable": sys.executable,
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "hostname": platform.node(),
        "cpu_count": os.cpu_count(),
        "packages": package_versions(),
        "environment_flags": {
            "BIOINTEL_TOOLS_HOME": os.environ.get("BIOINTEL_TOOLS_HOME", ""),
            "BIOINTEL_DATA_HOME": os.environ.get("BIOINTEL_DATA_HOME", ""),
            "BIOINTEL_OFFLINE": os.environ.get("BIOINTEL_OFFLINE", ""),
        },
    }


def artifact_record(path: str | Path, *, step_id: str, role: str, media_type: str = "application/octet-stream", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    file_path = Path(path).resolve()
    payload = {
        "step_id": step_id,
        "role": role,
        "path": str(file_path),
        "sha256": sha256_file(file_path),
        "size_bytes": file_path.stat().st_size,
        "media_type": media_type,
        "metadata": metadata or {},
    }
    payload["artifact_id"] = hash_json({key: payload[key] for key in ("step_id", "role", "path", "sha256")})[:20]
    return payload
