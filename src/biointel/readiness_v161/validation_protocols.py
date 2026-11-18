from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from biointel.scientific_depth.profiles import MODULE_PROFILES


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def protocol_manifest(module_key: str) -> dict[str, Any]:
    profile = MODULE_PROFILES[module_key]
    content = {
        "schema": "biointel.step161.external-validation-protocol.v1",
        "module_key": module_key,
        "module_title": profile.title,
        "protocol_version": "1.0.0",
        "protocol_status": "ready-for-external-execution",
        "intended_use_boundary": profile.boundary,
        "required_validation_gates": list(profile.validations),
        "required_reference_assets": list(profile.references),
        "required_specialist_engines": [engine for engine in profile.engines if not engine.startswith("biointel_native::")],
        "study_design_requirements": [
            "Independent dataset or site not used during development",
            "Prespecified endpoints and acceptance thresholds",
            "Locked software, model and reference versions",
            "Source-data checksums and immutable analysis manifest",
            "Blinded or independently adjudicated review where applicable",
            "Subgroup, calibration, uncertainty and failure analysis",
        ],
        "prospective_validation_required": True,
        "reviewer_signoff_required": True,
        "source_checksums_required": True,
        "negative_controls_required": True,
        "external_evidence_attached": False,
        "release_eligible": False,
        "completion_fields": {
            "independent_validation": False,
            "prospective_validation": False,
            "reviewer_approved": False,
            "source_checksums": False,
            "protocol_version": True,
        },
    }
    content["protocol_sha256"] = _sha256_text(json.dumps(content, sort_keys=True, default=str))
    return content


def ensure_validation_protocols(root: str | Path) -> list[Path]:
    root_path = Path(root).expanduser().resolve()
    folder = root_path / "data" / "step161" / "validation_protocols"
    folder.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for module_key in sorted(MODULE_PROFILES):
        path = folder / f"{module_key}.json"
        path.write_text(json.dumps(protocol_manifest(module_key), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def validation_protocol_readiness(
    root: str | Path,
    module_keys: Iterable[str] | None = None,
) -> pd.DataFrame:
    root_path = Path(root).expanduser().resolve()
    keys = sorted(set(module_keys or MODULE_PROFILES))
    folder = root_path / "data" / "step161" / "validation_protocols"
    rows: list[dict[str, Any]] = []
    for module_key in keys:
        path = folder / f"{module_key}.json"
        payload: dict[str, Any] = {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
        required = {
            "version": bool(payload.get("protocol_version")),
            "boundary": bool(payload.get("intended_use_boundary")),
            "gates": bool(payload.get("required_validation_gates")),
            "design": len(payload.get("study_design_requirements") or []) >= 6,
            "prospective_gate": payload.get("prospective_validation_required") is True,
            "reviewer_gate": payload.get("reviewer_signoff_required") is True,
            "checksum_gate": payload.get("source_checksums_required") is True,
            "no_false_release": payload.get("release_eligible") is False,
        }
        ready = all(required.values())
        rows.append(
            {
                "module_key": module_key,
                "protocol_present": path.is_file(),
                "protocol_ready": ready,
                "protocol_version": str(payload.get("protocol_version") or ""),
                "protocol_sha256": str(payload.get("protocol_sha256") or ""),
                "external_evidence_attached": bool(payload.get("external_evidence_attached", False)),
                "release_eligible": bool(payload.get("release_eligible", False)),
                "checks_passed": sum(required.values()),
                "checks_total": len(required),
                "path": str(path),
            }
        )
    return pd.DataFrame(rows)


def validation_protocol_summary(frame: pd.DataFrame) -> dict[str, Any]:
    return {
        "schema": "biointel.step161.validation-protocol-summary.v1",
        "modules": int(len(frame)),
        "protocol_ready": int(frame["protocol_ready"].astype(bool).sum()) if not frame.empty else 0,
        "all_protocols_ready": bool(not frame.empty and frame["protocol_ready"].astype(bool).all()),
        "external_evidence_attached": int(frame["external_evidence_attached"].astype(bool).sum()) if not frame.empty else 0,
        "external_release_not_inferred": True,
    }


__all__ = [
    "ensure_validation_protocols",
    "protocol_manifest",
    "validation_protocol_readiness",
    "validation_protocol_summary",
]
