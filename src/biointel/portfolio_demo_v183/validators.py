from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
from typing import Any

import pandas as pd

from biointel.runtime_paths import user_data_root
from .catalog import PROFILES


@dataclass(frozen=True)
class PortfolioDemoValidation:
    module_key: str
    demo_ready: bool
    execution_mode: str
    input_records: int
    manifest_passed: bool
    negative_cases_passed: bool
    expected_outputs_passed: bool
    hashes_passed: bool
    real_external_evidence: bool
    controlled_release_eligible: bool
    blockers: tuple[str, ...]
    path: str


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def validate_module_demo(root: str | Path, module_key: str) -> PortfolioDemoValidation:
    project = Path(root).resolve()
    profile = PROFILES[module_key]
    folder = user_data_root(project) / "step183" / "module_demos" / module_key
    blockers: list[str] = []
    manifest_path = folder / "demo_manifest.json"
    payload: dict[str, Any] = {}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        blockers.append(f"manifest missing or invalid: {exc}")
    if payload:
        if payload.get("schema") != "biointel.step183.portfolio-demo-manifest.v1":
            blockers.append("invalid manifest schema")
        if payload.get("module_key") != module_key:
            blockers.append("manifest identity mismatch")
        if payload.get("synthetic_or_demo") is not True:
            blockers.append("synthetic_or_demo must be true")
        if payload.get("real_external_evidence") is not False:
            blockers.append("demo cannot be marked real external evidence")
        if payload.get("controlled_release_eligible") is not False:
            blockers.append("demo cannot unlock controlled release")
        if float(payload.get("demo_operational_rating", 0)) != profile.demo_operational_rating:
            blockers.append("demo rating mismatch")

    hashes_passed = True
    for item in payload.get("files", []) if isinstance(payload.get("files"), list) else []:
        rel = str(item.get("path", "")).replace("\\", "/")
        pure = PurePosixPath(rel)
        target = folder / pure
        expected = str(item.get("sha256", "")).lower()
        if not rel or pure.is_absolute() or ".." in pure.parts or not target.is_file() or len(expected) != 64 or _digest(target) != expected:
            hashes_passed = False
            blockers.append(f"invalid or mismatched file: {rel}")
    if not payload.get("files"):
        hashes_passed = False
        blockers.append("manifest files list is empty")

    input_records = 0
    try:
        input_frame = pd.read_csv(folder / "demo_input.csv")
        input_records = len(input_frame)
        if input_frame.empty:
            blockers.append("demo input is empty")
        if "synthetic_demo" not in input_frame.columns or not input_frame["synthetic_demo"].astype(bool).all():
            blockers.append("demo input is not explicitly synthetic")
    except Exception as exc:
        blockers.append(f"demo input invalid: {exc}")

    negative_cases_passed = False
    try:
        negatives = pd.read_csv(folder / "demo_negative_cases.csv")
        negative_cases_passed = (
            {"case_id", "scenario", "expected_outcome"}.issubset(negatives.columns)
            and (negatives["expected_outcome"] == "pass").any()
            and (negatives["expected_outcome"] == "fail-safe").any()
        )
        if not negative_cases_passed:
            blockers.append("negative-case matrix incomplete")
    except Exception as exc:
        blockers.append(f"negative-case matrix invalid: {exc}")

    expected_outputs_passed = False
    try:
        expected = json.loads((folder / "demo_expected_outputs.json").read_text(encoding="utf-8-sig"))
        expected_outputs_passed = (
            expected.get("module_key") == module_key
            and expected.get("synthetic_demo") is True
            and expected.get("real_external_evidence") is False
            and expected.get("controlled_release_eligible") is False
            and isinstance(expected.get("required_outputs"), list)
        )
        if not expected_outputs_passed:
            blockers.append("expected-output contract invalid")
    except Exception as exc:
        blockers.append(f"expected-output contract invalid: {exc}")

    manifest_passed = bool(payload) and not any("manifest" in item for item in blockers)
    demo_ready = not blockers and hashes_passed and negative_cases_passed and expected_outputs_passed and input_records > 0
    return PortfolioDemoValidation(
        module_key=module_key,
        demo_ready=demo_ready,
        execution_mode=str(payload.get("execution_mode", "unknown")),
        input_records=input_records,
        manifest_passed=manifest_passed,
        negative_cases_passed=negative_cases_passed,
        expected_outputs_passed=expected_outputs_passed,
        hashes_passed=hashes_passed,
        real_external_evidence=False,
        controlled_release_eligible=False,
        blockers=tuple(blockers),
        path=str(folder),
    )


__all__ = ["PortfolioDemoValidation", "validate_module_demo"]
