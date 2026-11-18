from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from .specs import get_spec


@dataclass(frozen=True)
class ReferenceRecord:
    name: str
    version: str
    path: str
    sha256: str
    licence: str
    licence_acknowledged: bool
    active: bool = True


@dataclass(frozen=True)
class ReferenceAudit:
    module_key: str
    required: tuple[str, ...]
    configured: tuple[str, ...]
    missing: tuple[str, ...]
    invalid: tuple[str, ...]
    ready: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def required_references(module_key: str) -> tuple[str, ...]:
    spec = get_spec(module_key)
    return tuple(dict.fromkeys(reference for stage in spec.stages for reference in stage.references))


def template_manifest(module_key: str) -> dict[str, Any]:
    spec = get_spec(module_key)
    return {
        "schema": "biointel.step127.reference-manifest.v1",
        "module_key": module_key,
        "module_title": spec.title,
        "references": [
            {
                "name": name,
                "version": "",
                "path": "",
                "sha256": "",
                "licence": "",
                "licence_acknowledged": False,
                "active": True,
            }
            for name in required_references(module_key)
        ],
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_reference_manifest(module_key: str, payload: Mapping[str, Any]) -> ReferenceAudit:
    required = required_references(module_key)
    configured: list[str] = []
    invalid: list[str] = []
    by_name = {str(item.get("name", "")).strip().lower(): item for item in payload.get("references", []) if isinstance(item, Mapping)}
    for name in required:
        item = by_name.get(name.lower())
        if not item:
            continue
        version = str(item.get("version", "")).strip()
        path_text = str(item.get("path", "")).strip()
        expected = str(item.get("sha256", "")).strip().lower()
        licence = str(item.get("licence", "")).strip()
        acknowledged = bool(item.get("licence_acknowledged", False))
        active = bool(item.get("active", True))
        problems: list[str] = []
        if not version:
            problems.append("missing version")
        if not path_text:
            problems.append("missing path")
        else:
            path = Path(path_text).expanduser()
            if not path.exists():
                problems.append("path not found")
            elif expected and path.is_file() and _sha256(path) != expected:
                problems.append("checksum mismatch")
        if not expected:
            problems.append("missing checksum")
        if not licence or not acknowledged:
            problems.append("licence not acknowledged")
        if not active:
            problems.append("inactive")
        if problems:
            invalid.append(f"{name}: {', '.join(problems)}")
        else:
            configured.append(name)
    missing = tuple(name for name in required if name not in configured and not any(item.startswith(f"{name}:") for item in invalid))
    return ReferenceAudit(module_key, required, tuple(configured), missing, tuple(invalid), not missing and not invalid)


def load_reference_manifest(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Reference manifest must be a JSON object")
    return payload
