from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from biointel.scientific_depth.native_workflows import is_native_engine
from biointel.scientific_depth.profiles import MODULE_PROFILES

from .catalog import runtime_inventory, safe_slug


def _root(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def reference_intake_template(module_key: str, reference_name: str, index: int) -> dict[str, Any]:
    return {
        "schema": "biointel.step164.production-reference-intake.v1",
        "module_key": module_key,
        "reference_name": reference_name,
        "asset_id": f"{module_key}-{index:02d}-{safe_slug(reference_name)}",
        "provider": "",
        "provider_release_id": "",
        "licence_identifier": "",
        "licence_reviewed": False,
        "source_url_or_accession": "",
        "local_relative_path": "",
        "expected_sha256": "",
        "record_count": None,
        "schema_or_format": "",
        "schema_validation_passed": False,
        "scientific_reviewer": "",
        "review_date": "",
        "intended_use": "research",
        "production_qualified": False,
        "qualification_notes": "",
    }


def model_intake_template(module_key: str) -> dict[str, Any]:
    return {
        "schema": "biointel.step164.task-model-intake.v1",
        "module_key": module_key,
        "model_id": "",
        "model_version": "",
        "artifact_relative_path": "",
        "artifact_sha256": "",
        "training_dataset_sha256": "",
        "task_matches_module": False,
        "model_card_relative_path": "",
        "split_manifest_relative_path": "",
        "untouched_holdout_outputs_relative_path": "",
        "calibration_or_uncertainty_relative_path": "",
        "environment_manifest_relative_path": "",
        "licence_identifier": "",
        "intended_use": "research",
        "limitations_documented": False,
        "independent_validation_complete": False,
        "production_eligible": False,
    }


def evidence_intake_template(module_key: str) -> dict[str, Any]:
    return {
        "schema": "biointel.step164.external-evidence-intake.v1",
        "module_key": module_key,
        "study_id": "",
        "protocol_version": "",
        "source_data_manifest_relative_path": "",
        "locked_software_manifest_relative_path": "",
        "results_relative_path": "",
        "independent_dataset_or_site": False,
        "prespecified_acceptance_thresholds": False,
        "negative_controls_complete": False,
        "calibration_and_failure_analysis_complete": False,
        "prospective_or_orthogonal_validation_complete": False,
        "domain_expert_name": "",
        "domain_expert_signoff_relative_path": "",
        "release_review_complete": False,
    }


def _asset_file(project_root: Path, relative: str) -> Path | None:
    text = str(relative or "").strip()
    if not text:
        return None
    path = (project_root / text).resolve()
    try:
        path.relative_to(project_root)
    except ValueError:
        return None
    return path


def qualify_reference_manifest(project_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    required_text = ["provider", "provider_release_id", "licence_identifier", "source_url_or_accession", "local_relative_path", "expected_sha256", "schema_or_format", "scientific_reviewer", "review_date"]
    fields_complete = all(str(payload.get(key) or "").strip() for key in required_text)
    asset = _asset_file(project_root, str(payload.get("local_relative_path") or ""))
    exists = bool(asset and asset.is_file())
    actual_sha = _sha256(asset) if exists and asset else ""
    checksum_match = bool(actual_sha and actual_sha == str(payload.get("expected_sha256") or "").lower())
    record_count_valid = isinstance(payload.get("record_count"), int) and int(payload["record_count"]) >= 0
    qualified = bool(
        fields_complete
        and exists
        and checksum_match
        and record_count_valid
        and payload.get("licence_reviewed") is True
        and payload.get("schema_validation_passed") is True
        and payload.get("production_qualified") is True
    )
    return {
        "asset_id": payload.get("asset_id", ""),
        "reference_name": payload.get("reference_name", ""),
        "fields_complete": fields_complete,
        "asset_exists": exists,
        "actual_sha256": actual_sha,
        "checksum_match": checksum_match,
        "record_count_valid": record_count_valid,
        "licence_reviewed": payload.get("licence_reviewed") is True,
        "schema_validation_passed": payload.get("schema_validation_passed") is True,
        "reviewer_present": bool(str(payload.get("scientific_reviewer") or "").strip()),
        "production_qualified": qualified,
    }


def qualify_model_manifest(project_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    artifact = _asset_file(project_root, str(payload.get("artifact_relative_path") or ""))
    artifact_exists = bool(artifact and artifact.is_file())
    artifact_sha = _sha256(artifact) if artifact_exists and artifact else ""
    hash_match = bool(artifact_sha and artifact_sha == str(payload.get("artifact_sha256") or "").lower())
    required_files = [
        "model_card_relative_path",
        "split_manifest_relative_path",
        "untouched_holdout_outputs_relative_path",
        "calibration_or_uncertainty_relative_path",
        "environment_manifest_relative_path",
    ]
    evidence_files_complete = all(bool((p := _asset_file(project_root, str(payload.get(key) or ""))) and p.is_file()) for key in required_files)
    eligible = bool(
        artifact_exists
        and hash_match
        and evidence_files_complete
        and str(payload.get("training_dataset_sha256") or "").strip()
        and payload.get("task_matches_module") is True
        and payload.get("limitations_documented") is True
        and str(payload.get("licence_identifier") or "").strip()
        and payload.get("production_eligible") is True
    )
    return {
        "model_id": payload.get("model_id", ""),
        "model_version": payload.get("model_version", ""),
        "artifact_exists": artifact_exists,
        "artifact_sha256": artifact_sha,
        "artifact_hash_match": hash_match,
        "evidence_files_complete": evidence_files_complete,
        "task_matches_module": payload.get("task_matches_module") is True,
        "limitations_documented": payload.get("limitations_documented") is True,
        "independent_validation_complete": payload.get("independent_validation_complete") is True,
        "production_model_eligible": eligible,
    }


def qualify_evidence_manifest(project_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    required_files = [
        "source_data_manifest_relative_path",
        "locked_software_manifest_relative_path",
        "results_relative_path",
        "domain_expert_signoff_relative_path",
    ]
    files_complete = all(bool((p := _asset_file(project_root, str(payload.get(key) or ""))) and p.is_file()) for key in required_files)
    independent = bool(
        files_complete
        and str(payload.get("protocol_version") or "").strip()
        and payload.get("independent_dataset_or_site") is True
        and payload.get("prespecified_acceptance_thresholds") is True
        and payload.get("negative_controls_complete") is True
        and payload.get("calibration_and_failure_analysis_complete") is True
    )
    prospective = bool(independent and payload.get("prospective_or_orthogonal_validation_complete") is True)
    expert = bool(prospective and str(payload.get("domain_expert_name") or "").strip())
    release = bool(expert and payload.get("release_review_complete") is True)
    return {
        "study_id": payload.get("study_id", ""),
        "evidence_files_complete": files_complete,
        "independent_validation_complete": independent,
        "prospective_or_orthogonal_validation_complete": prospective,
        "domain_expert_signoff_complete": expert,
        "release_review_complete": release,
    }


def module_operational_assessment(root: str | Path, module_key: str, *, detect_runtime: bool = False) -> dict[str, Any]:
    project_root = _root(root)
    profile = MODULE_PROFILES[module_key]
    external_engines = [str(e).lower() for e in profile.engines if not is_native_engine(e)]
    inventory = runtime_inventory(external_engines) if detect_runtime and external_engines else pd.DataFrame()
    engines_installed = int(inventory["installed"].astype(bool).sum()) if not inventory.empty else 0
    engines_required = len(external_engines)

    ref_dir = project_root / "UserData" / "step164" / "references" / module_key
    reference_results: list[dict[str, Any]] = []
    for manifest_path in sorted(ref_dir.glob("*.json")) if ref_dir.is_dir() else []:
        reference_results.append(qualify_reference_manifest(project_root, _read_json(manifest_path)))
    references_required = len(profile.references)
    references_qualified = sum(bool(row.get("production_qualified")) for row in reference_results)

    model_dir = project_root / "UserData" / "step164" / "models" / module_key
    model_results = [qualify_model_manifest(project_root, _read_json(path)) for path in sorted(model_dir.glob("*.json"))] if model_dir.is_dir() else []
    eligible_models = sum(bool(row.get("production_model_eligible")) for row in model_results)

    evidence_dir = project_root / "UserData" / "step164" / "evidence" / module_key
    evidence_results = [qualify_evidence_manifest(project_root, _read_json(path)) for path in sorted(evidence_dir.glob("*.json"))] if evidence_dir.is_dir() else []
    independent = any(bool(row.get("independent_validation_complete")) for row in evidence_results)
    prospective = any(bool(row.get("prospective_or_orthogonal_validation_complete")) for row in evidence_results)
    expert = any(bool(row.get("domain_expert_signoff_complete")) for row in evidence_results)
    release_review = any(bool(row.get("release_review_complete")) for row in evidence_results)

    specialist_ready = engines_required == 0 or engines_installed == engines_required
    references_ready = references_required == 0 or references_qualified == references_required
    # Modules without a learned task model do not require a model package. The
    # benchmark/evidence gate still remains mandatory for external release.
    model_required = any(token in module_key for token in ("model", "ai", "foundation", "protein_language", "codesign", "pathology", "screening", "copilot"))
    model_ready = (eligible_models > 0) if model_required else True
    release_eligible = bool(specialist_ready and references_ready and model_ready and independent and prospective and expert and release_review)

    return {
        "schema": "biointel.step164.module-operational-assessment.v1",
        "module_key": module_key,
        "module_title": profile.title,
        "software_owned_score": 10.0,
        "native_research_workflow_ready": True,
        "specialist_engines_required": engines_required,
        "specialist_engines_installed": engines_installed,
        "specialist_runtime_ready": specialist_ready,
        "production_references_required": references_required,
        "production_references_qualified": references_qualified,
        "production_references_ready": references_ready,
        "task_specific_model_required": model_required,
        "eligible_task_specific_models": eligible_models,
        "task_specific_model_ready": model_ready,
        "independent_validation_complete": independent,
        "prospective_or_orthogonal_validation_complete": prospective,
        "domain_expert_signoff_complete": expert,
        "release_review_complete": release_review,
        "real_world_release_eligible": release_eligible,
        "release_decision": "eligible-for-controlled-release-review" if release_eligible else "research-only-fail-closed",
    }


def operational_matrix(root: str | Path, *, detect_runtime: bool = False, module_keys: Iterable[str] | None = None) -> pd.DataFrame:
    keys = sorted(set(module_keys or MODULE_PROFILES))
    return pd.DataFrame([module_operational_assessment(root, key, detect_runtime=detect_runtime) for key in keys])


__all__ = [
    "evidence_intake_template",
    "model_intake_template",
    "module_operational_assessment",
    "operational_matrix",
    "qualify_evidence_manifest",
    "qualify_model_manifest",
    "qualify_reference_manifest",
    "reference_intake_template",
]
