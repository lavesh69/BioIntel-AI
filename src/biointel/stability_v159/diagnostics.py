from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

_SECRET_TOKENS = ("password", "secret", "token", "api_key", "apikey", "authorization", "credential")


def _redact(value: Any, key: str = "") -> Any:
    if any(token in key.casefold() for token in _SECRET_TOKENS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write_failure_diagnostic(
    root: str | Path,
    *,
    module_key: str,
    fingerprint: str,
    error_type: str,
    error_message: str,
    metadata: dict[str, Any] | None = None,
    resources: dict[str, Any] | None = None,
) -> Path:
    project_root = Path(root).expanduser().resolve()
    output_dir = project_root / "UserData" / "runtime_diagnostics" / "native_failures"
    stable_id = hashlib.sha256(f"{module_key}|{fingerprint}|{error_type}|{error_message}".encode("utf-8")).hexdigest()[:16]
    path = output_dir / f"NATIVE-{stable_id}.json"
    payload = {
        "schema": "biointel.step159.native-failure.v1",
        "error_id": f"NATIVE-{stable_id}",
        "module_key": module_key,
        "fingerprint": fingerprint,
        "error_type": error_type,
        "error_message": error_message,
        "metadata": _redact(metadata or {}),
        "resources": _redact(resources or {}),
    }
    _atomic_write(path, payload)
    return path
