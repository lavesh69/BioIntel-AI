from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from biointel.scientific_depth.capability import capability_spec_for
from biointel.scientific_depth.native_workflows import native_workflow_spec
from biointel.scientific_depth.profiles import MODULE_PROFILES


@dataclass(frozen=True)
class QualityDimension:
    key: str
    label: str
    description: str
    weight: float = 1.0


@dataclass(frozen=True)
class ModuleQualityContract:
    module_key: str
    title: str
    native_family: str
    dimensions: tuple[QualityDimension, ...]
    validation_gates: tuple[str, ...]
    optimization_controls: tuple[str, ...]
    native_formats: tuple[str, ...]
    boundary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


QUALITY_DIMENSIONS: tuple[QualityDimension, ...] = (
    QualityDimension("input_contract", "Input contract", "Declared formats, expected schema and fail-closed input validation."),
    QualityDimension("data_integrity", "Data integrity", "Full-input hashing, duplicate/missing/infinite-value checks and bounded previews."),
    QualityDimension("deterministic_execution", "Deterministic execution", "Seeded local analysis with reproducible parameters and stable ordering."),
    QualityDimension("resource_safety", "Resource safety", "Memory-aware admission, row/feature budgets and safe-mode downgrade before allocation."),
    QualityDimension("failure_isolation", "Failure isolation", "Crash-loop circuit breaking, redacted diagnostics and page-preserving fail-closed behavior."),
    QualityDimension("provenance", "Provenance", "Module, workflow, input, parameter, environment and runtime provenance in every result manifest."),
    QualityDimension("result_integrity", "Result integrity", "Complete non-truncated table bundle with per-table checksums and preview completeness flags."),
    QualityDimension("specialist_adapter", "Specialist adapter", "Protected execution plans and honest detection for every declared third-party engine."),
    QualityDimension("evidence_gate", "Evidence gate", "Explicit validation requirements and a scientific boundary that blocks unsupported claims."),
    QualityDimension("usability_export", "Usability and export", "Runnable demo/template plus machine-readable JSON and ZIP/CSV export surfaces."),
)


def contract_for(module_key: str) -> ModuleQualityContract:
    profile = MODULE_PROFILES[module_key]
    workflow = native_workflow_spec(module_key)
    capability = capability_spec_for(module_key)
    validation_gates = tuple(profile.validations)
    if capability is not None:
        validation_gates = tuple(
            dict.fromkeys(
                [*validation_gates, *(stage.validation_gate for stage in capability.stages if stage.validation_gate)]
            )
        )
    return ModuleQualityContract(
        module_key=module_key,
        title=profile.title,
        native_family=workflow.family,
        dimensions=QUALITY_DIMENSIONS,
        validation_gates=validation_gates,
        optimization_controls=tuple(profile.optimization),
        native_formats=tuple(profile.native_formats),
        boundary=profile.boundary,
    )


def quality_contracts() -> dict[str, ModuleQualityContract]:
    return {key: contract_for(key) for key in sorted(MODULE_PROFILES)}


def quality_contract_manifest(module_key: str) -> dict[str, Any]:
    contract = contract_for(module_key)
    return {
        "schema": "biointel.step160.module-quality-contract.v1",
        "release_step": 160,
        **contract.to_dict(),
        "maximum_internal_score": 10.0,
        "score_scope": "Software-owned module quality only; specialist installation and external scientific evidence are separate axes.",
        "external_claims_not_inferred": True,
    }


__all__ = [
    "QUALITY_DIMENSIONS",
    "ModuleQualityContract",
    "QualityDimension",
    "contract_for",
    "quality_contract_manifest",
    "quality_contracts",
]
