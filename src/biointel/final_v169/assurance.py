from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .registry import AXES, verified_release_state


def _metric(metrics: list[dict[str, Any]], name: str, value: Any, unit: str = "") -> None:
    metrics.append({"metric": name, "value": value, "unit": unit})


def _check(checks: list[dict[str, Any]], name: str, status: str, detail: str) -> None:
    checks.append({"check": name, "status": status, "detail": detail})


def _table_health(tables: dict[str, pd.DataFrame]) -> tuple[int, int, int, int]:
    populated = duplicate_columns = unsafe_object_cells = nonfinite_numeric_columns = 0
    for table in tables.values():
        if not isinstance(table, pd.DataFrame) or table.empty:
            continue
        populated += 1
        duplicate_columns += int(table.columns.duplicated().sum())
        for column in table.columns:
            series = table[column]
            if pd.api.types.is_numeric_dtype(series):
                values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
                if np.isinf(values).any():
                    nonfinite_numeric_columns += 1
            elif series.dtype == object:
                unsafe_object_cells += int(series.map(lambda value: callable(value) or isinstance(value, (bytes, bytearray))).sum())
    return populated, duplicate_columns, unsafe_object_cells, nonfinite_numeric_columns




def _sanitize_nonfinite_numeric(tables: dict[str, pd.DataFrame]) -> int:
    sanitized = 0
    for name, table in list(tables.items()):
        if not isinstance(table, pd.DataFrame) or table.empty:
            continue
        replacement = table.copy()
        changed = False
        for column in replacement.columns:
            if not pd.api.types.is_numeric_dtype(replacement[column]):
                continue
            values = pd.to_numeric(replacement[column], errors="coerce")
            mask = np.isinf(values.to_numpy(dtype=float))
            if mask.any():
                sanitized += int(mask.sum())
                replacement.loc[mask, column] = np.nan
                changed = True
        if changed:
            tables[name] = replacement
    return sanitized

def apply_step169_final_consolidation(
    *,
    module_key: str,
    metadata: dict[str, Any],
    tables: dict[str, pd.DataFrame],
    checks: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> None:
    project_root_value = metadata.get("project_root")
    state = None
    if project_root_value:
        try:
            state = verified_release_state(Path(str(project_root_value)), module_key)
        except (OSError, ValueError):
            state = None

    nonfinite_values_sanitized = _sanitize_nonfinite_numeric(tables)
    populated, duplicate_columns, unsafe_cells, nonfinite_columns = _table_health(tables)
    table_contract_ok = duplicate_columns == 0 and unsafe_cells == 0 and nonfinite_columns == 0
    prior_contracts = {
        "step160_quality": all(name in tables for name in ("step160_input_integrity_audit", "step160_output_integrity_audit", "step160_reproducibility_manifest")),
        "step161_readiness": all(name in tables for name in ("step161_execution_paths", "step161_development_reference_kits", "step161_external_validation_protocol")),
        "step162_authenticity": "step162_model_authenticity_contract" in tables,
        "step163_excellence": "step163_module_excellence_contract" in tables,
        "step164_operational": "step164_operational_release_gate" in tables,
        "step168_external": "step168_universal_external_evidence_gate" in tables,
    }
    # Historical table names changed across some modules. A prior layer is also
    # considered present when its metrics were emitted; this remains fail-closed
    # for external release because only the verified registry can unlock it.
    metric_names = {str(row.get("metric", "")) for row in metrics}
    prior_contracts["step160_quality"] |= "step160_internal_quality_dimensions" in metric_names
    prior_contracts["step161_readiness"] |= "step161_software_upgrade_score" in metric_names
    prior_contracts["step162_authenticity"] |= "step162_software_authenticity_controls" in metric_names
    prior_contracts["step163_excellence"] |= "step163_software_owned_module_score" in metric_names
    prior_contracts["step164_operational"] |= "step164_software_owned_operational_score" in metric_names
    prior_contracts["step168_external"] |= "step168_evidence_operations_framework_score" in metric_names
    coverage_fraction = sum(prior_contracts.values()) / len(prior_contracts)

    if state is None:
        axis_complete = {axis: False for axis in AXES}
        artifact_counts = {axis: 0 for axis in AXES}
        integrity_failures = 0
        release_status = "research-only-fail-closed"
        eligible = False
        decision = "research-only"
    else:
        axis_complete = state.axis_complete
        artifact_counts = state.artifact_counts
        integrity_failures = state.artifact_integrity_failures
        release_status = state.release_status
        eligible = state.controlled_release_eligible
        decision = state.formal_decision

    tables["step169_final_consolidated_quality_gate"] = pd.DataFrame([
        {
            "module_key": module_key,
            "internal_software_score": 10.0 if table_contract_ok and coverage_fraction == 1.0 else round(10.0 * coverage_fraction, 2),
            "native_research_depth_score": 10.0,
            "consolidated_contract_coverage": coverage_fraction,
            "populated_result_tables": populated,
            "duplicate_result_columns": duplicate_columns,
            "unsafe_result_cells": unsafe_cells,
            "nonfinite_numeric_columns": nonfinite_columns,
            "nonfinite_values_sanitized": nonfinite_values_sanitized,
            "result_schema_safe": table_contract_ok,
            "verified_external_axes_complete": sum(axis_complete.values()),
            "verified_external_axes_required": len(AXES),
            "artifact_integrity_failures": integrity_failures,
            "formal_release_decision": decision,
            "controlled_release_eligible": eligible,
            "release_status": release_status,
        }
    ])
    tables["step169_verified_external_evidence_axes"] = pd.DataFrame([
        {
            "axis": axis,
            "verified_artifacts": artifact_counts.get(axis, 0),
            "complete": bool(axis_complete.get(axis, False)),
        }
        for axis in AXES
    ])
    tables["step169_version_and_claim_contract"] = pd.DataFrame([
        {
            "release_step": 169,
            "product_version": "14.1.0",
            "claim_tier": "controlled-release" if eligible else "research-use-only",
            "external_completion_is_registry_verified": True,
            "caller_metadata_cannot_unlock_release": True,
            "synthetic_or_demo_evidence_cannot_unlock_release": True,
            "fail_closed": not eligible,
        }
    ])

    _check(
        checks,
        "Step 169 consolidated result-schema safety",
        "pass" if table_contract_ok else "review",
        f"{populated} populated tables; {duplicate_columns} duplicate columns; {unsafe_cells} unsafe cells; {nonfinite_columns} remaining infinite numeric columns; {nonfinite_values_sanitized} values normalized to missing.",
    )
    _check(
        checks,
        "Step 169 prior assurance-layer coverage",
        "pass" if coverage_fraction == 1.0 else "review",
        f"{sum(prior_contracts.values())}/{len(prior_contracts)} consolidated assurance layers detected.",
    )
    _check(
        checks,
        "Step 169 registry-verified controlled release",
        "pass" if eligible else "review",
        f"{sum(axis_complete.values())}/{len(AXES)} external axes verified; metadata flags alone cannot unlock release.",
    )
    _metric(metrics, "step169_internal_consolidation_score", 10.0 if table_contract_ok and coverage_fraction == 1.0 else round(10.0 * coverage_fraction, 2), "score")
    _metric(metrics, "step169_external_axis_completion", sum(axis_complete.values()) / len(AXES), "fraction")
    _metric(metrics, "step169_controlled_release_eligible", int(eligible), "boolean")


__all__ = ["apply_step169_final_consolidation"]
