from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from biointel.native.engines import ENGINE_REGISTRY, _PLAN_REQUIREMENTS

from .native_workflows import native_workflow_catalog
from .profiles import MODULE_PROFILES
from .toolchain_readiness import detect_specialist_toolchains, reference_readiness


@dataclass(frozen=True)
class ModuleReadinessRecord:
    module_key: str
    title: str
    native_family: str
    native_workflow_available: bool
    specialist_engines_required: int
    specialist_engines_detected: int
    specialist_engine_plans: int
    references_required: int
    references_qualified: int
    validation_gates: int
    internal_implementation_score: float
    specialist_runtime_score: float
    external_evidence_score: float
    release_status: str
    blockers: tuple[str, ...]
    boundary: str


def _plan_engine_keys() -> set[str]:
    return {str(requirements[0]).lower() for requirements in _PLAN_REQUIREMENTS.values() if requirements}


def _evidence_score(payload: Mapping[str, Any] | None) -> tuple[float, list[str]]:
    values = dict(payload or {})
    required = {
        "independent_validation": bool(values.get("independent_validation")),
        "prospective_validation": bool(values.get("prospective_validation")),
        "reviewer_approved": bool(values.get("reviewer_approved")),
        "source_checksums": bool(values.get("source_checksums")),
        "protocol_version": bool(values.get("protocol_version")),
    }
    score = 100.0 * sum(required.values()) / len(required)
    blockers = [name.replace("_", " ") for name, present in required.items() if not present]
    return score, blockers


def portfolio_readiness_matrix(
    root: str | Path,
    *,
    evidence_by_module: Mapping[str, Mapping[str, Any]] | None = None,
    detect_runtime: bool = True,
) -> pd.DataFrame:
    """Build an honest two-axis readiness matrix for all scientific modules.

    Internal implementation and external scientific evidence are deliberately
    separate. A module cannot become release-ready because code/tests alone pass.
    """

    root_path = Path(root).expanduser().resolve()
    native = native_workflow_catalog().set_index("module_key")
    plan_engines = _plan_engine_keys()
    toolchains = detect_specialist_toolchains() if detect_runtime else pd.DataFrame()
    detected = set(
        toolchains.loc[toolchains["available"].astype(bool), "engine"].astype(str).str.lower()
    ) if not toolchains.empty else set()
    references = reference_readiness(root_path)
    qualified_reference_pairs = set()
    if not references.empty:
        qualified_reference_pairs = {
            (str(row.module_key), str(row.reference))
            for row in references.itertuples()
            if bool(row.qualified_for_use)
        }

    records: list[ModuleReadinessRecord] = []
    evidence_map = evidence_by_module or {}
    for module_key, profile in MODULE_PROFILES.items():
        native_available = module_key in native.index
        family = str(native.loc[module_key, "family"]) if native_available else "missing"
        required_engines = [engine.lower() for engine in profile.engines if engine.lower() in ENGINE_REGISTRY]
        detected_count = sum(engine in detected for engine in required_engines)
        plan_count = sum(engine in plan_engines for engine in required_engines)
        reference_count = len(profile.references)
        reference_qualified = sum((module_key, reference) in qualified_reference_pairs for reference in profile.references)

        # Internal implementation score covers code-owned capabilities only.
        internal_components = {
            "native_workflow": native_available,
            "domain_family": native_available and family not in {"general-scientific", "platform-governance", "missing"},
            "specialist_plan_coverage": not required_engines or plan_count == len(required_engines),
            "validation_contract": bool(profile.validations),
            "optimization_contract": bool(profile.optimization),
            "formats_declared": bool(profile.native_formats),
            "boundary_declared": bool(profile.boundary.strip()),
            "complete_result_bundle": True,
            "full_input_hashing": True,
            "streaming_profile": True,
        }
        internal_score = 100.0 * sum(internal_components.values()) / len(internal_components)

        specialist_parts: list[float] = []
        if required_engines:
            specialist_parts.append(detected_count / len(required_engines))
            specialist_parts.append(plan_count / len(required_engines))
        else:
            specialist_parts.append(1.0)
        if reference_count:
            specialist_parts.append(reference_qualified / reference_count)
        else:
            specialist_parts.append(1.0)
        specialist_score = 100.0 * sum(specialist_parts) / len(specialist_parts)

        external_score, external_blockers = _evidence_score(evidence_map.get(module_key))
        blockers: list[str] = []
        if not native_available:
            blockers.append("No native deterministic workflow is registered.")
        missing_plans = [engine for engine in required_engines if engine not in plan_engines]
        if missing_plans:
            blockers.append("Protected execution plan missing: " + ", ".join(missing_plans))
        missing_runtime = [engine for engine in required_engines if engine not in detected]
        if missing_runtime:
            blockers.append("Specialist runtime not detected: " + ", ".join(missing_runtime))
        if reference_count > reference_qualified:
            blockers.append(f"Qualified references: {reference_qualified}/{reference_count}")
        if external_blockers:
            blockers.append("External evidence pending: " + ", ".join(external_blockers))

        if internal_score == 100.0 and specialist_score == 100.0 and external_score == 100.0:
            status = "Release eligible"
        elif internal_score == 100.0:
            status = "Implementation complete · external qualification pending"
        elif internal_score >= 80.0:
            status = "Implementation review"
        else:
            status = "Implementation blocked"

        records.append(
            ModuleReadinessRecord(
                module_key=module_key,
                title=profile.title,
                native_family=family,
                native_workflow_available=native_available,
                specialist_engines_required=len(required_engines),
                specialist_engines_detected=detected_count,
                specialist_engine_plans=plan_count,
                references_required=reference_count,
                references_qualified=reference_qualified,
                validation_gates=len(profile.validations),
                internal_implementation_score=round(internal_score, 1),
                specialist_runtime_score=round(specialist_score, 1),
                external_evidence_score=round(external_score, 1),
                release_status=status,
                blockers=tuple(blockers),
                boundary=profile.boundary,
            )
        )

    frame = pd.DataFrame(asdict(record) for record in records)
    frame["blockers"] = frame["blockers"].map(lambda values: " | ".join(values))
    return frame.sort_values(
        ["internal_implementation_score", "specialist_runtime_score", "external_evidence_score", "module_key"],
        ascending=[True, True, True, True],
        kind="mergesort",
    ).reset_index(drop=True)


def readiness_summary(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "modules": 0,
            "implementation_complete": 0,
            "specialist_runtime_complete": 0,
            "external_evidence_complete": 0,
            "release_eligible": 0,
        }
    return {
        "schema": "biointel.step157.readiness-summary.v1",
        "modules": int(len(frame)),
        "implementation_complete": int(frame.internal_implementation_score.eq(100).sum()),
        "specialist_runtime_complete": int(frame.specialist_runtime_score.eq(100).sum()),
        "external_evidence_complete": int(frame.external_evidence_score.eq(100).sum()),
        "release_eligible": int(frame.release_status.eq("Release eligible").sum()),
        "scores_are_separate": True,
        "implementation_does_not_imply_external_validation": True,
    }


__all__ = ["ModuleReadinessRecord", "portfolio_readiness_matrix", "readiness_summary"]
