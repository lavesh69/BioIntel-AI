from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from biointel.jobs.local_queue import JobRecord, LocalJobQueue
from biointel.neuro_cns.chemistry import bbb_batch
from biointel.neuro_cns.advanced import (
    brain_digital_twin_viewer,
    compound_optimization_board,
    multiomics_disease_signature_builder,
    neurophysiology_review_board,
    rare_neurological_disease_board,
)
from biointel.neuro_cns.clinical import trial_intelligence
from biointel.neuro_cns.completion import (
    dataset_drift_monitor,
    leakage_split_audit,
    multisite_reproducibility_analyzer,
    privacy_scan_frame,
)
from biointel.neuro_cns.genetics import prioritize_variants
from biointel.neuro_cns.imaging import connectivity_from_timeseries, profile_image_array
from biointel.neuro_cns.omics import biomarker_discovery
from biointel.neuro_cns.precision import stratify_research_cohort
from biointel.neuro_cns.projects import serialise
from biointel.neuro_cns.signals import analyze_neural_signals


BACKGROUND_MODULES = {
    "bbb_permeability",
    "neurogenetics",
    "neuro_omics_biomarkers",
    "eeg_meg_analytics",
    "neuroimaging_connectomics",
    "cns_clinical_trials",
    "precision_neurology",
    "advanced_compound_optimization",
    "advanced_multiomics_signature",
    "advanced_neurophysiology_review",
    "advanced_brain_digital_twin",
    "advanced_rare_disease",
    "completion_privacy_scan",
    "completion_leakage_audit",
    "completion_drift_monitor",
    "completion_multisite",
}


def _frame(payload: dict[str, Any], key: str = "table_records") -> pd.DataFrame:
    records = payload.get(key)
    if not isinstance(records, list):
        raise ValueError(f"{key} must be a list of row objects.")
    return pd.DataFrame(records)


def recommend_execution_mode(module_key: str, *, row_count: int = 0, byte_size: int = 0) -> dict[str, Any]:
    heavy = module_key in BACKGROUND_MODULES and (row_count >= 5_000 or byte_size >= 20 * 1024 * 1024)
    return {
        "module_key": module_key,
        "recommended_mode": "background" if heavy else "interactive",
        "reason": "large input or specialist workload" if heavy else "input is within interactive guardrails",
        "row_count": int(max(row_count, 0)),
        "byte_size": int(max(byte_size, 0)),
        "queue_supported": module_key in BACKGROUND_MODULES,
    }


def execute_neuro_job_payload(payload: dict[str, Any]) -> dict[str, Any]:
    module_key = str(payload.get("module_key", "")).strip()
    parameters = dict(payload.get("parameters") or {})
    if module_key == "bbb_permeability":
        result = bbb_batch(payload.get("compound_rows") or payload.get("table_records") or [])
    elif module_key == "neurogenetics":
        result = prioritize_variants(_frame(payload), **parameters)
    elif module_key == "neuro_omics_biomarkers":
        group_column = str(payload.get("group_column") or "")
        if not group_column:
            raise ValueError("group_column is required for neuro-omics background jobs.")
        result = biomarker_discovery(_frame(payload), group_column, **parameters)
    elif module_key == "eeg_meg_analytics":
        sampling_rate = float(payload.get("sampling_rate_hz", 0))
        result = analyze_neural_signals(_frame(payload), sampling_rate, payload.get("time_column"), **parameters)
    elif module_key == "neuroimaging_connectomics":
        mode = str(payload.get("mode", "connectivity"))
        if mode == "connectivity":
            result = connectivity_from_timeseries(_frame(payload), payload.get("time_column"), **parameters)
        elif mode == "array":
            array = np.asarray(payload.get("array"), dtype=float)
            result = profile_image_array(array, **parameters)
        else:
            raise ValueError("Neuroimaging job mode must be 'connectivity' or 'array'.")
    elif module_key == "cns_clinical_trials":
        result = trial_intelligence(_frame(payload), **parameters)
    elif module_key == "precision_neurology":
        result = stratify_research_cohort(_frame(payload), **parameters)
    elif module_key == "advanced_compound_optimization":
        result = compound_optimization_board(payload.get("compound_rows") or payload.get("table_records") or [], **parameters)
    elif module_key == "advanced_multiomics_signature":
        group_column = str(payload.get("group_column") or "")
        if not group_column:
            raise ValueError("group_column is required for the multi-omics signature background job.")
        result = multiomics_disease_signature_builder(_frame(payload), group_column, **parameters)
    elif module_key == "advanced_neurophysiology_review":
        sampling_rate = float(payload.get("sampling_rate_hz", 0))
        result = neurophysiology_review_board(_frame(payload), sampling_rate, payload.get("time_column"), reviewer_event_rows=payload.get("reviewer_event_rows") or [], **parameters)
    elif module_key == "advanced_brain_digital_twin":
        result = brain_digital_twin_viewer(np.asarray(payload.get("array"), dtype=float), **parameters)
    elif module_key == "advanced_rare_disease":
        result = rare_neurological_disease_board(_frame(payload), **parameters)
    elif module_key == "completion_privacy_scan":
        result = privacy_scan_frame(_frame(payload), **parameters)
    elif module_key == "completion_leakage_audit":
        result = leakage_split_audit(_frame(payload), **parameters)
    elif module_key == "completion_drift_monitor":
        reference = _frame(payload, "reference_records")
        current = _frame(payload, "current_records")
        result = dataset_drift_monitor(reference, current, **parameters)
    elif module_key == "completion_multisite":
        result = multisite_reproducibility_analyzer(_frame(payload), **parameters)
    else:
        raise ValueError(f"Unsupported Neuro/CNS background module: {module_key}")
    return {
        "schema": "biointel.neuro-cns.background-result.v1",
        "module_key": module_key,
        "result": serialise(result),
        "controlled_release_eligible": False,
    }


def submit_neuro_job(
    project_root: str | Path,
    module_key: str,
    payload: dict[str, Any],
    *,
    priority: int = 100,
    max_attempts: int = 2,
    estimated_seconds: float | None = None,
) -> JobRecord:
    if module_key not in BACKGROUND_MODULES:
        raise ValueError(f"Module {module_key!r} is not enabled for the Neuro/CNS background queue.")
    root = Path(project_root).resolve()
    queue = LocalJobQueue(runtime_database_path(root, "jobs.sqlite3"))
    job_payload = dict(payload)
    job_payload["module_key"] = module_key
    return queue.submit(
        "neuro_cns_analysis",
        job_payload,
        priority=priority,
        max_attempts=max_attempts,
        estimated_seconds=estimated_seconds,
        stages=["validate_input", "execute_neuro_engine", "quality_checks", "persist_result"],
        resources={"execution": "local", "release_eligible": False},
    )
