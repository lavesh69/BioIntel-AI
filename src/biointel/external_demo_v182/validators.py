from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
from typing import Any

import pandas as pd

from biointel.external_readiness_v181 import PROFILES
from biointel.external_readiness_v181.catalog import EvidenceRequirement
from biointel.external_readiness_v181.validators import VALIDATORS


@dataclass(frozen=True)
class DemoValidation:
    module_key: str
    evidence_id: str
    manifest_passed: bool
    data_passed: bool
    demo_ready: bool
    real_evidence: bool
    controlled_release_eligible: bool
    record_count: int
    metrics: dict[str, Any]
    blockers: tuple[str, ...]
    path: str


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _validate_manifest(folder: Path, module_key: str, requirement: EvidenceRequirement) -> tuple[bool, dict[str, Any], list[str]]:
    path = folder / "qualification_manifest.json"
    blockers: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return False, {}, [f"demo manifest missing or invalid: {exc}"]
    if payload.get("schema") != "biointel.step182.demo-evidence-manifest.v1":
        blockers.append("invalid Step 182 demo manifest schema")
    if payload.get("module_key") != module_key or payload.get("evidence_id") != requirement.evidence_id:
        blockers.append("demo manifest identity mismatch")
    if payload.get("real_world_evidence") is not False:
        blockers.append("demo manifest must keep real_world_evidence false")
    if payload.get("synthetic_or_demo") is not True:
        blockers.append("demo manifest must set synthetic_or_demo true")
    if payload.get("controlled_release_eligible") is not False:
        blockers.append("demo manifest must never enable controlled release")
    if payload.get("demo_execution_eligible") is not True:
        blockers.append("demo_execution_eligible must be true")
    files = payload.get("files", [])
    if not isinstance(files, list) or not files:
        blockers.append("demo manifest files list is empty")
    else:
        for i, item in enumerate(files):
            rel = str(item.get("path", "")).replace("\\", "/").strip()
            expected = str(item.get("sha256", "")).lower().strip()
            pure = PurePosixPath(rel)
            if not rel or pure.is_absolute() or ".." in pure.parts:
                blockers.append(f"unsafe demo file path at files[{i}]")
                continue
            target = folder / pure
            if not target.is_file():
                blockers.append(f"missing demo file: {rel}")
                continue
            if len(expected) != 64 or _sha256(target) != expected:
                blockers.append(f"demo SHA-256 mismatch: {rel}")
    if requirement.data_file and not any(item.get("path") == requirement.data_file for item in files if isinstance(item, dict)):
        blockers.append(f"required demo data file not declared: {requirement.data_file}")
    return not blockers, payload, blockers


def validate_demo_folder(root: str | Path, module_key: str, requirement: EvidenceRequirement) -> DemoValidation:
    folder = Path(root).resolve() / "UserData" / "step182" / "demo_evidence" / module_key / requirement.evidence_id
    manifest_passed, payload, blockers = _validate_manifest(folder, module_key, requirement)
    data_passed = False
    metrics: dict[str, Any] = {}
    record_count = 0
    if manifest_passed:
        required_columns, validator = VALIDATORS[requirement.validator]
        if requirement.data_file is None:
            frame = pd.DataFrame()
        else:
            path = folder / requirement.data_file
            try:
                frame = pd.read_csv(path)
            except Exception as exc:
                frame = pd.DataFrame()
                blockers.append(f"cannot read demo CSV: {exc}")
            missing = [col for col in required_columns if col not in frame.columns]
            if missing:
                blockers.append("missing demo columns: " + ", ".join(missing))
            if frame.empty:
                blockers.append("demo CSV contains no records")
        record_count = len(frame)
        if not blockers:
            data_passed, metrics, data_blockers = validator(folder, frame)
            blockers.extend(data_blockers)
    demo_ready = manifest_passed and data_passed and not blockers
    return DemoValidation(
        module_key=module_key,
        evidence_id=requirement.evidence_id,
        manifest_passed=manifest_passed,
        data_passed=data_passed,
        demo_ready=demo_ready,
        real_evidence=False,
        controlled_release_eligible=False,
        record_count=record_count,
        metrics={str(k): v for k, v in metrics.items()},
        blockers=tuple(blockers),
        path=str(folder),
    )


__all__ = ["DemoValidation", "validate_demo_folder"]
