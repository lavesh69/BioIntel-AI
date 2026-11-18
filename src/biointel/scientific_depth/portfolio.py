from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable

import pandas as pd

from .capability import CAPABILITY_SPECS
from .evidence_readiness import build_evidence_manifest_template
from .profiles import MODULE_PROFILES
from .native_workflows import is_native_engine, native_portfolio_manifest, native_workflow_spec
from .toolchain_readiness import detect_specialist_toolchains, toolchain_summary


def scientific_portfolio_catalog(module_keys: Iterable[str] | None = None) -> pd.DataFrame:
    """Return a deterministic, auditable inventory of scientific-depth contracts."""
    keys = sorted(set(module_keys or MODULE_PROFILES))
    rows: list[dict[str, Any]] = []
    for module_key in keys:
        profile = MODULE_PROFILES.get(module_key)
        spec = CAPABILITY_SPECS.get(module_key)
        if profile is None or spec is None:
            continue
        modes = [stage.mode for stage in spec.stages]
        rows.append(
            {
                "module_key": module_key,
                "title": profile.title,
                "pipeline_stages": len(spec.stages),
                "built_in_stages": modes.count("built-in"),
                "adapter_stages": modes.count("adapter"),
                "external_validation_stages": modes.count("external-validation"),
                "registered_engines": len(profile.engines),
                "native_engines": sum(is_native_engine(engine) for engine in profile.engines),
                "native_workflow_family": native_workflow_spec(module_key).family,
                "native_workflow_available": True,
                "reference_assets": len(profile.references),
                "native_formats": len(profile.native_formats),
                "validation_gates": len(profile.validations),
                "has_release_boundary": bool(profile.boundary.strip() and spec.evidence_boundary.strip()),
                "release_blocker_count": len(spec.release_blockers),
                "minimum_contract_complete": bool(
                    len(spec.stages) >= 6
                    and "external-validation" in modes
                    and profile.validations
                    and profile.boundary.strip()
                ),
            }
        )
    return pd.DataFrame(rows)


def scientific_portfolio_summary(catalog: pd.DataFrame | None = None) -> dict[str, Any]:
    frame = scientific_portfolio_catalog() if catalog is None else catalog.copy()
    if frame.empty:
        return {
            "schema": "biointel.step154.scientific-portfolio.v4",
            "modules": 0,
            "complete_contracts": 0,
            "pipeline_stages": 0,
            "adapter_stages": 0,
            "external_validation_stages": 0,
            "registered_engines": 0,
            "native_engines": 0,
            "reference_assets": 0,
        }
    return {
        "schema": "biointel.step154.scientific-portfolio.v4",
        "modules": int(len(frame)),
        "complete_contracts": int(frame["minimum_contract_complete"].astype(bool).sum()),
        "pipeline_stages": int(frame["pipeline_stages"].sum()),
        "built_in_stages": int(frame["built_in_stages"].sum()),
        "adapter_stages": int(frame["adapter_stages"].sum()),
        "external_validation_stages": int(frame["external_validation_stages"].sum()),
        "registered_engines": int(frame["registered_engines"].sum()),
        "native_engines": int(frame["native_engines"].sum()),
        "all_native_workflows_available": bool(frame["native_workflow_available"].astype(bool).all()),
        "reference_assets": int(frame["reference_assets"].sum()),
        "validation_gates": int(frame["validation_gates"].sum()),
        "all_contracts_complete": bool(frame["minimum_contract_complete"].astype(bool).all()),
    }


def scientific_portfolio_manifest(module_keys: Iterable[str] | None = None) -> dict[str, Any]:
    catalog = scientific_portfolio_catalog(module_keys)
    modules: list[dict[str, Any]] = []
    for module_key in catalog["module_key"].tolist() if not catalog.empty else []:
        profile = MODULE_PROFILES[module_key]
        spec = CAPABILITY_SPECS[module_key]
        modules.append(
            {
                "module_key": module_key,
                "profile": asdict(profile),
                "capability": asdict(spec),
                "evidence_template": build_evidence_manifest_template(
                    module_key,
                    profile_references=profile.references,
                    profile_validations=profile.validations,
                ),
            }
        )
    return {
        "schema": "biointel.step154.scientific-portfolio-manifest.v4",
        "summary": scientific_portfolio_summary(catalog),
        "catalog": catalog.to_dict(orient="records"),
        "native_portfolio": native_portfolio_manifest(module_keys),
        "specialist_toolchains": {
            "summary": toolchain_summary(detect_specialist_toolchains()),
            "catalog": detect_specialist_toolchains().to_dict(orient="records"),
        },
        "modules": modules,
        "policy": {
            "module_coverage_is_not_scientific_certification": True,
            "external_validation_is_fail_closed": True,
            "clinical_and_regulatory_qualification_is_external": True,
        },
    }
