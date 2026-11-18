from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from .engines import ENGINE_REGISTRY, detect_engine


@dataclass(frozen=True)
class ReferenceAssetEvidence:
    name: str
    path: str
    sha256: str
    size_bytes: int
    exists: bool
    checksum_matches: bool | None
    release: str
    licence: str
    licence_accepted: bool


@dataclass(frozen=True)
class EngineQualification:
    engine_key: str
    label: str
    executable_available: bool
    executable: str
    version: str
    version_recorded: bool
    required_reference_count: int
    qualified_reference_count: int
    references_complete: bool
    licence_evidence_complete: bool
    reviewer: str
    reviewed_at_utc: str
    qualification_status: str
    blockers: tuple[str, ...]
    references: tuple[ReferenceAssetEvidence, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def qualify_engine(
    engine_key: str,
    *,
    reference_assets: Mapping[str, Mapping[str, Any]] | None = None,
    reviewer: str = "",
    reviewed_at_utc: str = "",
    timeout_seconds: float = 5.0,
) -> EngineQualification:
    """Fail-closed qualification of a specialist executable and its references.

    ``reference_assets`` is keyed by the exact names declared in
    ``EngineSpec.required_databases``. Each value may contain ``path``,
    ``sha256``, ``release``, ``licence`` and ``licence_accepted``.
    """

    if engine_key not in ENGINE_REGISTRY:
        raise KeyError(f"Unknown engine: {engine_key}")
    spec = ENGINE_REGISTRY[engine_key]
    status = detect_engine(engine_key, timeout_seconds=timeout_seconds)
    supplied = dict(reference_assets or {})
    blockers: list[str] = []
    references: list[ReferenceAssetEvidence] = []

    if not status.available:
        blockers.append("Executable was not detected in the qualified runtime.")
    if not status.version or status.version.lower() in {"unknown", "not detected"}:
        blockers.append("Executable version evidence is missing.")

    for required_name in spec.required_databases:
        evidence = dict(supplied.get(required_name, {}))
        raw_path = str(evidence.get("path", "")).strip()
        path = Path(raw_path).expanduser().resolve() if raw_path else Path()
        exists = bool(raw_path) and path.exists() and path.is_file()
        actual_hash = _sha256(path) if exists else ""
        expected_hash = str(evidence.get("sha256", "")).strip().lower()
        checksum_matches: bool | None = None
        if exists and expected_hash:
            checksum_matches = actual_hash.lower() == expected_hash
        release = str(evidence.get("release", "")).strip()
        licence = str(evidence.get("licence", "")).strip()
        licence_accepted = bool(evidence.get("licence_accepted", False))
        references.append(
            ReferenceAssetEvidence(
                name=required_name,
                path=str(path) if raw_path else "",
                sha256=actual_hash,
                size_bytes=int(path.stat().st_size) if exists else 0,
                exists=exists,
                checksum_matches=checksum_matches,
                release=release,
                licence=licence,
                licence_accepted=licence_accepted,
            )
        )
        if not exists:
            blockers.append(f"Required reference asset is missing: {required_name}.")
        if exists and not expected_hash:
            blockers.append(f"Expected checksum is missing for reference asset: {required_name}.")
        if checksum_matches is False:
            blockers.append(f"Checksum mismatch for reference asset: {required_name}.")
        if not release:
            blockers.append(f"Release/version metadata is missing for reference asset: {required_name}.")
        if not licence or not licence_accepted:
            blockers.append(f"Licence evidence is incomplete for reference asset: {required_name}.")

    references_complete = all(
        item.exists and item.checksum_matches is True and bool(item.release)
        for item in references
    ) if references else True
    licences_complete = all(item.licence and item.licence_accepted for item in references) if references else True
    if not reviewer.strip() or not reviewed_at_utc.strip():
        blockers.append("Qualified reviewer and review timestamp are required.")

    qualification_status = "Qualified" if not blockers else "Blocked"
    return EngineQualification(
        engine_key=engine_key,
        label=spec.label,
        executable_available=status.available,
        executable=status.executable,
        version=status.version,
        version_recorded=bool(status.version and status.version.lower() not in {"unknown", "not detected"}),
        required_reference_count=len(spec.required_databases),
        qualified_reference_count=sum(
            item.exists and item.checksum_matches is True and bool(item.release) and bool(item.licence) and item.licence_accepted
            for item in references
        ),
        references_complete=references_complete,
        licence_evidence_complete=licences_complete,
        reviewer=reviewer.strip(),
        reviewed_at_utc=reviewed_at_utc.strip(),
        qualification_status=qualification_status,
        blockers=tuple(dict.fromkeys(blockers)),
        references=tuple(references),
    )


def qualification_to_dict(result: EngineQualification) -> dict[str, Any]:
    return asdict(result)


def qualification_matrix(
    keys: Iterable[str] | None = None,
    *,
    evidence_by_engine: Mapping[str, Mapping[str, Mapping[str, Any]]] | None = None,
    reviewer: str = "",
    reviewed_at_utc: str = "",
    timeout_seconds: float = 2.0,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    evidence = evidence_by_engine or {}
    for key in list(keys or ENGINE_REGISTRY):
        result = qualify_engine(
            key,
            reference_assets=evidence.get(key, {}),
            reviewer=reviewer,
            reviewed_at_utc=reviewed_at_utc,
            timeout_seconds=timeout_seconds,
        )
        rows.append({
            "Engine": result.label,
            "Key": result.engine_key,
            "Executable available": result.executable_available,
            "Version": result.version,
            "References qualified": f"{result.qualified_reference_count}/{result.required_reference_count}",
            "Licence evidence complete": result.licence_evidence_complete,
            "Reviewer recorded": bool(result.reviewer and result.reviewed_at_utc),
            "Qualification status": result.qualification_status,
            "Blockers": " | ".join(result.blockers),
        })
    return pd.DataFrame(rows)


def save_qualification(result: EngineQualification, destination: str | Path) -> Path:
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(qualification_to_dict(result), indent=2, sort_keys=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(payload + "\n", encoding="utf-8")
    temporary.replace(target)
    return target


__all__ = [
    "EngineQualification",
    "ReferenceAssetEvidence",
    "qualification_matrix",
    "qualification_to_dict",
    "qualify_engine",
    "save_qualification",
]
