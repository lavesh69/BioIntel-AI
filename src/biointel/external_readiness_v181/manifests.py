from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
from typing import Any

from .catalog import EvidenceRequirement
from .metrics import as_bool


@dataclass(frozen=True)
class ManifestValidation:
    passed: bool
    blockers: tuple[str, ...]
    payload: dict[str, Any]
    verified_files: tuple[str, ...]


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(folder: Path) -> dict[str, Any]:
    path = folder / "qualification_manifest.json"
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _nonempty(payload: dict[str, Any], key: str) -> bool:
    return bool(str(payload.get(key, "")).strip())


def validate_manifest(folder: Path, module_key: str, requirement: EvidenceRequirement) -> ManifestValidation:
    payload = load_manifest(folder)
    blockers: list[str] = []
    verified: list[str] = []
    if not payload:
        return ManifestValidation(False, ("qualification_manifest.json is missing or invalid",), {}, ())
    if payload.get("schema") != "biointel.step181.evidence-manifest.v1":
        blockers.append("manifest schema is not biointel.step181.evidence-manifest.v1")
    if payload.get("module_key") != module_key:
        blockers.append("manifest module_key does not match the target module")
    if payload.get("evidence_id") != requirement.evidence_id:
        blockers.append("manifest evidence_id does not match the evidence folder")
    for key in ("source_organization", "acquisition_date", "licence_or_permission", "provenance_record"):
        if not _nonempty(payload, key):
            blockers.append(f"{key} is missing")
    if not as_bool(payload.get("real_world_evidence")):
        blockers.append("real_world_evidence must be true")
    if as_bool(payload.get("synthetic_or_demo")):
        blockers.append("synthetic_or_demo must be false for qualification")
    if requirement.requires_independent_source and not as_bool(payload.get("independent_from_development_team")):
        blockers.append("independent_from_development_team must be true")
    if requirement.requires_reviewer_signature:
        for key in ("reviewer_name", "reviewer_role", "review_date"):
            if not _nonempty(payload, key):
                blockers.append(f"{key} is missing")
        if not as_bool(payload.get("review_signed")):
            blockers.append("review_signed must be true")
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        blockers.append("manifest files list is empty")
    else:
        for index, item in enumerate(files):
            if not isinstance(item, dict):
                blockers.append(f"files[{index}] is not an object")
                continue
            relative = str(item.get("path", "")).strip().replace("\\", "/")
            expected = str(item.get("sha256", "")).strip().lower()
            pure = PurePosixPath(relative)
            if not relative or pure.is_absolute() or ".." in pure.parts:
                blockers.append(f"files[{index}].path is unsafe")
                continue
            path = folder / pure
            if not path.is_file():
                blockers.append(f"declared file is missing: {relative}")
                continue
            if len(expected) != 64:
                blockers.append(f"declared SHA-256 is invalid: {relative}")
                continue
            actual = sha256_file(path)
            if actual != expected:
                blockers.append(f"SHA-256 mismatch: {relative}")
                continue
            verified.append(relative)
    if requirement.data_file and requirement.data_file not in verified:
        blockers.append(f"required data file is not checksum-verified: {requirement.data_file}")
    return ManifestValidation(not blockers, tuple(blockers), payload, tuple(verified))


__all__ = ["ManifestValidation", "sha256_file", "load_manifest", "validate_manifest"]
