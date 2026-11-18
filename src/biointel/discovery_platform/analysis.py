from __future__ import annotations

import hashlib
from typing import Any, Callable, Mapping

import pandas as pd

from .analysis_common import (
    alignment_mapping,
    biomarker_discovery,
    differential_expression,
    pathway_enrichment,
    sequencing_quality,
    variant_prioritization,
)
from .analysis_omics import (
    metabolomics,
    microbiome,
    multi_omics,
    proteomics,
    single_cell,
    structural_biology,
)
from .analysis_research import (
    drug_target_discovery,
    experimental_design,
    hypothesis_generation,
    laboratory_validation,
    literature_discovery,
    statistical_analysis,
)
from .constants import MODULE_DEPENDENCIES, MODULE_LABELS, SYNTHETIC_NOTICE
from .execution import DependencyManager, ExecutionEngine
from .models import PlatformConflictError, PlatformValidationError, utc_now
from .storage import DiscoveryPlatformStore

Handler = Callable[[pd.DataFrame, Mapping[str, Any]], dict[str, Any]]

HANDLERS: dict[str, Handler] = {
    "sequencing_quality": sequencing_quality,
    "alignment_mapping": alignment_mapping,
    "differential_expression": differential_expression,
    "biomarker_discovery": biomarker_discovery,
    "variant_prioritization": variant_prioritization,
    "pathway_enrichment": pathway_enrichment,
    "multi_omics": multi_omics,
    "single_cell": single_cell,
    "proteomics": proteomics,
    "metabolomics": metabolomics,
    "microbiome": microbiome,
    "structural_biology": structural_biology,
    "drug_target_discovery": drug_target_discovery,
    "experimental_design": experimental_design,
    "statistical_analysis": statistical_analysis,
    "literature_discovery": literature_discovery,
    "hypothesis_generation": hypothesis_generation,
    "laboratory_validation": laboratory_validation,
}

NATIVE_METHODS = {
    "sequencing_quality": "Imported QC-metric validation and rescue/exclusion rules",
    "alignment_mapping": "Imported mapping-metric and reference compatibility analysis",
    "differential_expression": "Welch contrast with BH-FDR; external count-model adapters available",
    "biomarker_discovery": "Leakage-safe nested CV, calibration, stability, and decision curve",
    "variant_prioritization": "Transparent multi-evidence ranking without automated ACMG classification",
    "pathway_enrichment": "Validated-background ORA with leading edge and BH-FDR",
    "multi_omics": "Sample harmonization, layer QC, joint latent factors, concordance, ablation",
    "single_cell": "Adaptive cell QC and bounded PCA embedding",
    "proteomics": "Peptide/protein FDR gates, missingness, differential abundance",
    "metabolomics": "Blank correction, QC CV, and run-order drift assessment",
    "microbiome": "Negative-control prevalence, CLR transformation, differential screening",
    "structural_biology": "Residue-level pLDDT, PAE, disorder, and pocket evidence review",
    "drug_target_discovery": "Evidence completeness, druggability, safety, off-target ranking",
    "experimental_design": "Power approximation, dropout adjustment, randomization, balance review",
    "statistical_analysis": "Parametric/non-parametric tests, diagnostics, bootstrap, Kaplan-Meier",
    "literature_discovery": "Identifier format validation, deduplication, retraction flags, contradictions",
    "hypothesis_generation": "Evidence-gated testable and competing hypothesis construction",
    "laboratory_validation": "qPCR delta-delta Ct and explicit acceptance-criteria evaluation",
}


def stable_frame_sha256(frame: pd.DataFrame) -> str:
    normalized = frame.copy()
    normalized.columns = [str(column) for column in normalized.columns]
    payload = normalized.to_csv(
        index=False, lineterminator="\n", na_rep="<NA>", float_format="%.17g"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def analysis_catalog() -> list[dict[str, Any]]:
    return [
        {
            "module_id": module_id,
            "module": MODULE_LABELS[module_id],
            "native_method": NATIVE_METHODS[module_id],
            "optional_external_dependencies": list(MODULE_DEPENDENCIES[module_id]),
            "result_origin": "real_calculation or synthetic_demo_output",
            "clinical_use": "Research only",
        }
        for module_id in HANDLERS
    ]


class ScientificAnalysisPlatform:
    def __init__(self, store: DiscoveryPlatformStore):
        self.store = store
        self.dependencies = DependencyManager(store)
        self.execution = ExecutionEngine(store)

    def run(
        self,
        module_id: str,
        frame: pd.DataFrame,
        parameters: Mapping[str, Any] | None = None,
        *,
        is_synthetic: bool = False,
        seed: int | None = None,
        strict_external: bool = False,
    ) -> dict[str, Any]:
        if module_id not in HANDLERS:
            raise KeyError(module_id)
        if not isinstance(frame, pd.DataFrame):
            raise PlatformValidationError("Scientific module input must be a pandas DataFrame")
        dependency = self.dependencies.module_status(module_id)
        if strict_external and dependency["missing"]:
            raise PlatformConflictError(
                "External execution is blocked by missing dependencies: "
                + ", ".join(dependency["missing"])
            )
        result = HANDLERS[module_id](frame.copy(), dict(parameters or {}))
        origin = "synthetic_demo_output" if is_synthetic else "real_calculation"
        result["provenance"] = {
            "module_id": module_id,
            "module": MODULE_LABELS[module_id],
            "origin": origin,
            "is_synthetic": bool(is_synthetic),
            "seed": seed,
            "input_sha256": stable_frame_sha256(frame),
            "created_at_utc": utc_now(),
            "native_method": NATIVE_METHODS[module_id],
            "external_dependency_status": dependency,
        }
        if is_synthetic:
            result["synthetic_notice"] = SYNTHETIC_NOTICE
        return result

    def run_and_persist(
        self,
        *,
        project_id: str,
        module_id: str,
        frame: pd.DataFrame,
        parameters: Mapping[str, Any] | None = None,
        dataset_id: str | None = None,
        is_synthetic: bool = False,
        seed: int | None = None,
    ) -> dict[str, Any]:
        project = self.store.row("projects", "project_id", project_id)
        if project is None:
            raise KeyError(project_id)
        if bool(project["is_synthetic"]) != bool(is_synthetic):
            raise PlatformConflictError("Analysis origin must match its project boundary")
        frame_hash = stable_frame_sha256(frame)
        clean_parameters = dict(parameters or {})

        def execute(_: Mapping[str, Any]) -> Mapping[str, Any]:
            return self.run(
                module_id, frame, clean_parameters,
                is_synthetic=is_synthetic, seed=seed,
            )

        return self.execution.run_python(
            project_id=project_id, dataset_id=dataset_id, module_id=module_id,
            function=execute,
            payload={
                "input_frame_sha256": frame_hash,
                "rows": len(frame),
                "columns": [str(column) for column in frame.columns],
                "parameters": clean_parameters,
                "is_synthetic": is_synthetic,
            },
            random_seed=seed,
            provenance={
                "origin": "synthetic_demo_output" if is_synthetic else "real_calculation",
                "module_id": module_id,
                "input_frame_sha256": frame_hash,
            },
        )


__all__ = [
    "HANDLERS",
    "ScientificAnalysisPlatform",
    "analysis_catalog",
    "stable_frame_sha256",
]
