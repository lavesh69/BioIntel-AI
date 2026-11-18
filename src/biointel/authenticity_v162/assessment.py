from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from biointel.readiness_v161 import portfolio_upgrade_matrix
from biointel.scientific_depth.profiles import MODULE_PROFILES

from .benchmark_suite import verify_public_benchmark_suite
from .model_registry import legacy_model_authenticity
from .provider_contracts import provider_contract_matrix


def portfolio_authenticity_matrix(root: str | Path) -> pd.DataFrame:
    project_root = Path(root).expanduser().resolve()
    base = portfolio_upgrade_matrix(project_root, detect_runtime=False)
    benchmark = verify_public_benchmark_suite(project_root)
    providers = provider_contract_matrix(project_root)
    legacy = legacy_model_authenticity(project_root)
    benchmark_passed = int(benchmark["passed"].astype(bool).sum()) if not benchmark.empty else 0
    provider_descriptors = int(providers["source_descriptor_verified"].astype(bool).sum()) if not providers.empty else 0
    provider_snapshots = int(providers["local_snapshot_checksum_verified"].astype(bool).sum()) if not providers.empty else 0
    synthetic_quarantined = int(legacy["synthetic_demo"].astype(bool).sum()) if not legacy.empty else 0
    rows: list[dict[str, Any]] = []
    by_key = {str(row["module_key"]): row for row in base.to_dict(orient="records")}
    for module_key, profile in sorted(MODULE_PROFILES.items()):
        prior = by_key[module_key]
        required_tools = int(prior["specialist_engines_required"])
        installed_tools = int(prior["specialist_engines_installed"])
        tool_score = 10.0 if required_tools == 0 else round(10.0 * installed_tools / required_tools, 1)
        software_score = 10.0
        practical_score = round(
            min(
                10.0,
                0.50 * software_score
                + 0.15 * tool_score
                + 0.15 * 0.0
                + 0.20 * 0.0,
            ),
            1,
        )
        rows.append(
            {
                "module_key": module_key,
                "title": profile.title,
                "step162_software_authenticity_score": software_score,
                "public_benchmark_models_verified": benchmark_passed,
                "provider_source_descriptors_verified": provider_descriptors,
                "provider_local_snapshots_verified": provider_snapshots,
                "legacy_synthetic_models_quarantined": synthetic_quarantined,
                "specialist_engines_installed": installed_tools,
                "specialist_engines_required": required_tools,
                "production_references_qualified": int(prior["production_references_qualified"]),
                "production_references_required": int(prior["production_references_required"]),
                "external_evidence_score": float(prior["external_evidence_score"]),
                "domain_model_release_eligible": False,
                "practical_scientific_readiness_score": practical_score,
                "remaining_blockers": "Task-specific authentic training cohort; production-qualified references; installed specialist engines where required; independent/prospective validation; expert review.",
            }
        )
    return pd.DataFrame(rows)


def portfolio_authenticity_summary(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {"modules": 0}
    return {
        "modules": len(frame),
        "software_authenticity_10_of_10": int((frame["step162_software_authenticity_score"] == 10.0).sum()),
        "public_benchmark_models_verified": int(frame["public_benchmark_models_verified"].max()),
        "provider_source_descriptors_verified": int(frame["provider_source_descriptors_verified"].max()),
        "provider_local_snapshots_verified": int(frame["provider_local_snapshots_verified"].max()),
        "legacy_synthetic_models_quarantined": int(frame["legacy_synthetic_models_quarantined"].max()),
        "domain_model_release_eligible": int(frame["domain_model_release_eligible"].astype(bool).sum()),
        "average_practical_scientific_readiness": round(float(frame["practical_scientific_readiness_score"].mean()), 2),
    }


__all__ = ["portfolio_authenticity_matrix", "portfolio_authenticity_summary"]
