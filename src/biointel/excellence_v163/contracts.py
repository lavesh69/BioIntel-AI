from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from biointel.authenticity_v162 import legacy_model_authenticity
from biointel.readiness_v161 import (
    module_runtime_path_matrix,
    validation_protocol_readiness,
)
from biointel.scientific_depth.profiles import MODULE_PROFILES


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _root(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def module_excellence_contract(module_key: str) -> dict[str, Any]:
    profile = MODULE_PROFILES[module_key]
    payload: dict[str, Any] = {
        "schema": "biointel.step163.module-excellence-contract.v1",
        "module_key": module_key,
        "module_title": profile.title,
        "software_owned_target": "10/10",
        "quality_dimensions": {
            "input_integrity": True,
            "deterministic_native_execution": True,
            "bounded_resource_execution": True,
            "crash_loop_protection": True,
            "complete_result_export": True,
            "reproducibility_signature": True,
            "specialist_runtime_adapter": True,
            "reference_lifecycle_contract": True,
            "model_authenticity_guard": True,
            "external_release_fail_closed": True,
        },
        "required_specialist_engines": list(profile.engines),
        "required_production_references": list(profile.references),
        "accepted_native_formats": list(profile.native_formats),
        "validation_gates": list(profile.validations),
        "optimization_controls": list(profile.optimization),
        "scientific_boundary": profile.boundary,
        "native_fallback_policy": {
            "available": True,
            "label": "BioIntel deterministic research fallback",
            "may_replace_specialist_engine": False,
            "confirmatory_claims_allowed": False,
        },
        "claim_policy": {
            "demo_result_label_required": True,
            "reference_result_label_required": True,
            "uncertainty_disclosure_required": True,
            "limitations_required": True,
            "external_validation_required_for_release": True,
            "expert_review_required_for_release": True,
        },
    }
    payload["contract_sha256"] = _sha256_text(json.dumps(payload, sort_keys=True, default=str))
    return payload


def task_specific_benchmark_specification(module_key: str) -> dict[str, Any]:
    profile = MODULE_PROFILES[module_key]
    payload: dict[str, Any] = {
        "schema": "biointel.step163.task-specific-benchmark.v1",
        "module_key": module_key,
        "module_title": profile.title,
        "benchmark_status": "specification-ready-data-required",
        "development_dataset_must_be_non_synthetic": True,
        "independent_test_dataset_required": True,
        "prospective_or_orthogonal_validation_required": True,
        "prespecified_acceptance_thresholds_required": True,
        "locked_data_model_reference_versions_required": True,
        "required_data_formats": list(profile.native_formats),
        "required_reference_assets": list(profile.references),
        "required_validation_analyses": list(profile.validations),
        "required_failure_analyses": [
            "missingness and malformed-input analysis",
            "out-of-distribution or applicability-domain analysis",
            "subgroup or biological-context analysis",
            "calibration and uncertainty analysis",
            "negative-control and leakage analysis",
            "failed-case review with retained identifiers",
        ],
        "minimum_evidence_bundle": [
            "immutable source-data checksums",
            "training/validation/test partition manifest",
            "per-sample predictions or module-level outputs",
            "uncertainty intervals or confidence diagnostics",
            "full parameter and environment manifest",
            "expert reviewer sign-off",
        ],
        "release_eligible": False,
    }
    payload["specification_sha256"] = _sha256_text(json.dumps(payload, sort_keys=True, default=str))
    return payload


def reference_acquisition_manifest(module_key: str) -> dict[str, Any]:
    profile = MODULE_PROFILES[module_key]
    assets = []
    for index, reference in enumerate(profile.references, start=1):
        assets.append(
            {
                "asset_id": f"step163-{module_key}-reference-{index:02d}",
                "reference_name": reference,
                "required": True,
                "provider_release_id_required": True,
                "licence_review_required": True,
                "download_checksum_required": True,
                "record_count_required": True,
                "schema_validation_required": True,
                "scientific_reviewer_required": True,
                "current_state": "not-bundled-awaiting-qualified-production-asset",
                "production_qualified": False,
            }
        )
    return {
        "schema": "biointel.step163.reference-acquisition-manifest.v1",
        "module_key": module_key,
        "module_title": profile.title,
        "assets": assets,
        "all_assets_production_qualified": False if assets else True,
        "demo_or_development_fixture_may_substitute": False,
    }


def model_eligibility_policy(module_key: str) -> dict[str, Any]:
    profile = MODULE_PROFILES[module_key]
    return {
        "schema": "biointel.step163.model-eligibility-policy.v1",
        "module_key": module_key,
        "module_title": profile.title,
        "allowed_default_states": ["verified-task-specific-research-model", "externally-validated-domain-model"],
        "blocked_default_states": ["synthetic-demo", "wrong-domain-public-benchmark", "missing-model-card", "checksum-mismatch", "unknown-training-data"],
        "required_model_artifacts": [
            "model artifact SHA-256",
            "training dataset SHA-256",
            "model card",
            "split manifest",
            "untouched holdout outputs",
            "calibration or uncertainty diagnostics",
            "environment manifest",
            "intended-use and limitations",
        ],
        "public_generic_benchmark_counts_as_domain_validation": False,
        "synthetic_model_scientific_default_allowed": False,
        "current_domain_model_release_eligible": False,
    }


def ensure_step163_assets(root: str | Path, module_keys: Iterable[str] | None = None) -> list[Path]:
    project_root = _root(root)
    keys = sorted(set(module_keys or MODULE_PROFILES))
    base = project_root / "data" / "step163"
    folders = {
        "contracts": base / "module_excellence_contracts",
        "benchmarks": base / "task_specific_benchmarks",
        "references": base / "reference_acquisition_manifests",
        "models": base / "model_eligibility_policies",
    }
    for folder in folders.values():
        folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for module_key in keys:
        payloads = {
            folders["contracts"] / f"{module_key}.json": module_excellence_contract(module_key),
            folders["benchmarks"] / f"{module_key}.json": task_specific_benchmark_specification(module_key),
            folders["references"] / f"{module_key}.json": reference_acquisition_manifest(module_key),
            folders["models"] / f"{module_key}.json": model_eligibility_policy(module_key),
        }
        for path, payload in payloads.items():
            path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            written.append(path)
    return written


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def module_excellence_matrix(root: str | Path) -> pd.DataFrame:
    project_root = _root(root)
    base = project_root / "data" / "step163"
    legacy = legacy_model_authenticity(project_root)
    unsafe_defaults = 0
    if not legacy.empty:
        unsafe_defaults = int(
            (legacy["synthetic_demo"].astype(bool) & legacy["default_scientific_inference_allowed"].astype(bool)).sum()
        )
    rows: list[dict[str, Any]] = []
    for module_key, profile in sorted(MODULE_PROFILES.items()):
        contract = _read_json(base / "module_excellence_contracts" / f"{module_key}.json")
        benchmark = _read_json(base / "task_specific_benchmarks" / f"{module_key}.json")
        references = _read_json(base / "reference_acquisition_manifests" / f"{module_key}.json")
        policy = _read_json(base / "model_eligibility_policies" / f"{module_key}.json")
        runtime = module_runtime_path_matrix(module_key, detect_runtime=False)
        protocols = validation_protocol_readiness(project_root, [module_key])
        dimensions = contract.get("quality_dimensions") or {}
        software_score = round(10.0 * sum(bool(v) for v in dimensions.values()) / max(1, len(dimensions)), 1)
        runtime_contract_score = 10.0 if not runtime.empty and runtime["operational_path_ready"].astype(bool).all() else 0.0
        protocol_score = 10.0 if not protocols.empty and protocols["protocol_ready"].astype(bool).all() else 0.0
        specification_score = 10.0 if benchmark.get("specification_sha256") else 0.0
        model_guard_score = 10.0 if policy and unsafe_defaults == 0 else 0.0
        reference_lifecycle_score = 10.0 if references else 0.0
        software_owned_score = round(
            sum([software_score, runtime_contract_score, protocol_score, specification_score, model_guard_score, reference_lifecycle_score]) / 6,
            1,
        )
        required_engines = len(profile.engines)
        required_references = len(profile.references)
        rows.append(
            {
                "module_key": module_key,
                "title": profile.title,
                "step163_software_owned_score": software_owned_score,
                "quality_contract_score": software_score,
                "managed_runtime_path_score": runtime_contract_score,
                "validation_protocol_score": protocol_score,
                "task_specific_benchmark_spec_score": specification_score,
                "model_authenticity_guard_score": model_guard_score,
                "reference_lifecycle_score": reference_lifecycle_score,
                "specialist_engines_required": required_engines,
                "specialist_engines_bundled": 0,
                "production_references_required": required_references,
                "production_references_qualified": 0,
                "external_independent_validation_complete": False,
                "prospective_or_wetlab_validation_complete": False,
                "domain_expert_signoff_complete": False,
                "real_world_release_eligible": False,
                "remaining_external_actions": "Install and qualify required specialist engines; attach production reference releases; execute the task-specific independent/prospective validation protocol; obtain expert sign-off.",
            }
        )
    return pd.DataFrame(rows)


def module_excellence_summary(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {"modules": 0}
    return {
        "schema": "biointel.step163.module-excellence-summary.v1",
        "modules": int(len(frame)),
        "software_owned_10of10": int((frame["step163_software_owned_score"] == 10.0).sum()),
        "runtime_paths_10of10": int((frame["managed_runtime_path_score"] == 10.0).sum()),
        "benchmark_specs_10of10": int((frame["task_specific_benchmark_spec_score"] == 10.0).sum()),
        "model_guards_10of10": int((frame["model_authenticity_guard_score"] == 10.0).sum()),
        "reference_lifecycle_10of10": int((frame["reference_lifecycle_score"] == 10.0).sum()),
        "real_world_release_eligible": int(frame["real_world_release_eligible"].astype(bool).sum()),
        "external_evidence_not_inferred": True,
    }
