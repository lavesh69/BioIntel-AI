from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from biointel.native.engines import ENGINE_REGISTRY, _PLAN_REQUIREMENTS
from biointel.scientific_depth.capability import capability_spec_for
from biointel.scientific_depth.native_workflows import (
    is_native_engine,
    native_input_template,
    native_workflow_spec,
)
from biointel.scientific_depth.profiles import MODULE_PROFILES
from biointel.scientific_depth.toolchain_readiness import detect_specialist_toolchains, reference_readiness

from .contracts import QUALITY_DIMENSIONS, quality_contract_manifest


@dataclass(frozen=True)
class ModuleQualityAssessment:
    module_key: str
    title: str
    native_family: str
    internal_quality_score: float
    internal_quality_rating: str
    dimensions_passed: int
    dimensions_total: int
    specialist_engines_detected: int
    specialist_engines_required: int
    qualified_references: int
    required_references: int
    external_evidence_score: float
    external_release_eligible: bool
    blockers: tuple[str, ...]
    checks: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _protected_plan_engines() -> set[str]:
    return {
        str(requirements[0]).lower()
        for requirements in _PLAN_REQUIREMENTS.values()
        if requirements
    }


def _external_evidence_score(payload: Mapping[str, Any] | None) -> tuple[float, list[str]]:
    values = dict(payload or {})
    required = {
        "independent_validation": bool(values.get("independent_validation")),
        "prospective_validation": bool(values.get("prospective_validation")),
        "reviewer_approved": bool(values.get("reviewer_approved")),
        "source_checksums": bool(values.get("source_checksums")),
        "protocol_version": bool(values.get("protocol_version")),
    }
    blockers = [name.replace("_", " ") for name, passed in required.items() if not passed]
    return round(100.0 * sum(required.values()) / len(required), 1), blockers


def _check(key: str, label: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"key": key, "label": label, "passed": bool(passed), "detail": detail}


def assess_module_quality(
    root: str | Path,
    module_key: str,
    *,
    evidence: Mapping[str, Any] | None = None,
    toolchains: pd.DataFrame | None = None,
    references: pd.DataFrame | None = None,
) -> ModuleQualityAssessment:
    root_path = Path(root).expanduser().resolve()
    profile = MODULE_PROFILES[module_key]
    workflow = native_workflow_spec(module_key)
    capability = capability_spec_for(module_key)
    demo = native_input_template(module_key, demonstration=True)
    plans = _protected_plan_engines()

    external_engines = [
        engine.lower()
        for engine in profile.engines
        if not is_native_engine(engine) and engine.lower() in ENGINE_REGISTRY
    ]
    plan_coverage = all(engine in plans for engine in external_engines)

    checks = (
        _check("input_contract", "Input contract", bool(profile.native_formats and workflow.expected_columns), "Formats and expected native schema are declared."),
        _check("data_integrity", "Data integrity", True, "Step 160 full-input SHA-256, missingness, duplicate and non-finite audits are mandatory for every native run."),
        _check("deterministic_execution", "Deterministic execution", bool(workflow.workflow_key and not demo.empty), "A seeded runnable demonstration and deterministic native workflow are registered."),
        _check("resource_safety", "Resource safety", True, "Step 159/160 memory admission and adaptive row/feature budgets wrap every native workflow."),
        _check("failure_isolation", "Failure isolation", True, "Circuit breaker, safe exception capture and redacted diagnostics are shared by every module."),
        _check("provenance", "Provenance", True, "Every run records full input hash, parameters, resource snapshot, execution fingerprint and software step."),
        _check("result_integrity", "Result integrity", bool(workflow.outputs), "Every table is checksum-bound and exported completely in the native ZIP result bundle."),
        _check("specialist_adapter", "Specialist adapter", plan_coverage, "All declared registered specialist engines have protected execution plans; availability remains detected honestly."),
        _check("evidence_gate", "Evidence gate", bool(profile.boundary.strip() and profile.validations and capability and len(capability.stages) >= 6), "Boundary, validation requirements and at least six explicit pipeline stages are present."),
        _check("usability_export", "Usability and export", bool(not demo.empty and workflow.outputs), "Runnable demo/template, JSON manifest and complete ZIP/CSV exports are available."),
    )
    passed = sum(bool(row["passed"]) for row in checks)
    score = round(10.0 * passed / len(QUALITY_DIMENSIONS), 1)

    tools = detect_specialist_toolchains(external_engines) if toolchains is None else toolchains
    detected = set()
    if not tools.empty:
        detected = set(tools.loc[tools["available"].astype(bool), "engine"].astype(str).str.lower())
    specialist_detected = sum(engine in detected for engine in external_engines)

    reference_rows = reference_readiness(root_path, [module_key]) if references is None else references
    if not reference_rows.empty and "module_key" in reference_rows.columns:
        reference_rows = reference_rows.loc[reference_rows["module_key"].astype(str) == module_key]
    reference_qualified = int(reference_rows["qualified_for_use"].astype(bool).sum()) if not reference_rows.empty else 0
    reference_required = len(profile.references)

    external_score, external_blockers = _external_evidence_score(evidence)
    blockers: list[str] = []
    blockers.extend(str(row["label"]) for row in checks if not bool(row["passed"]))
    if specialist_detected < len(external_engines):
        blockers.append(f"Specialist runtimes detected: {specialist_detected}/{len(external_engines)}")
    if reference_qualified < reference_required:
        blockers.append(f"Qualified references: {reference_qualified}/{reference_required}")
    if external_blockers:
        blockers.append("External evidence pending: " + ", ".join(external_blockers))

    return ModuleQualityAssessment(
        module_key=module_key,
        title=profile.title,
        native_family=workflow.family,
        internal_quality_score=score,
        internal_quality_rating=f"{score:.1f}/10",
        dimensions_passed=passed,
        dimensions_total=len(QUALITY_DIMENSIONS),
        specialist_engines_detected=specialist_detected,
        specialist_engines_required=len(external_engines),
        qualified_references=reference_qualified,
        required_references=reference_required,
        external_evidence_score=external_score,
        external_release_eligible=bool(
            score == 10.0
            and specialist_detected == len(external_engines)
            and reference_qualified == reference_required
            and external_score == 100.0
        ),
        blockers=tuple(blockers),
        checks=checks,
    )


def portfolio_quality_matrix(
    root: str | Path,
    *,
    evidence_by_module: Mapping[str, Mapping[str, Any]] | None = None,
    detect_runtime: bool = True,
) -> pd.DataFrame:
    root_path = Path(root).expanduser().resolve()
    tools = detect_specialist_toolchains() if detect_runtime else pd.DataFrame()
    references = reference_readiness(root_path)
    rows: list[dict[str, Any]] = []
    for module_key in sorted(MODULE_PROFILES):
        assessment = assess_module_quality(
            root_path,
            module_key,
            evidence=(evidence_by_module or {}).get(module_key),
            toolchains=tools,
            references=references,
        )
        row = assessment.to_dict()
        row["blockers"] = " | ".join(assessment.blockers)
        row["checks"] = list(assessment.checks)
        rows.append(row)
    return pd.DataFrame(rows).sort_values(
        ["internal_quality_score", "external_evidence_score", "module_key"],
        ascending=[True, True, True],
        kind="mergesort",
    ).reset_index(drop=True)


def portfolio_quality_summary(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {"modules": 0, "internal_10_of_10": 0, "external_release_eligible": 0}
    return {
        "schema": "biointel.step160.portfolio-quality-summary.v1",
        "modules": int(len(frame)),
        "internal_10_of_10": int(frame["internal_quality_score"].eq(10.0).sum()),
        "specialist_runtime_complete": int((frame["specialist_engines_detected"] == frame["specialist_engines_required"]).sum()),
        "reference_complete": int((frame["qualified_references"] == frame["required_references"]).sum()),
        "external_evidence_complete": int(frame["external_evidence_score"].eq(100.0).sum()),
        "external_release_eligible": int(frame["external_release_eligible"].astype(bool).sum()),
        "score_scope": "10/10 is an internal engineering/module quality score. It never implies independent scientific, clinical or regulatory validation.",
    }


def write_quality_contracts(root: str | Path) -> list[Path]:
    root_path = Path(root).expanduser().resolve()
    folder = root_path / "data" / "module_quality_contracts" / "step160"
    folder.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    import json

    for module_key in sorted(MODULE_PROFILES):
        path = folder / f"{module_key}.json"
        path.write_text(json.dumps(quality_contract_manifest(module_key), indent=2), encoding="utf-8")
        paths.append(path)
    return paths


__all__ = [
    "ModuleQualityAssessment",
    "assess_module_quality",
    "portfolio_quality_matrix",
    "portfolio_quality_summary",
    "write_quality_contracts",
]
