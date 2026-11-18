from __future__ import annotations

from typing import Any, Mapping

from .bioinformatics import (
    build_reproducibility_manifest,
    external_tool_readiness,
    genomic_cohort_qc,
    microbiome_contamination_qc,
    multiomics_batch_qc,
    single_cell_qc,
    spatial_omics_qc,
)
from .discovery import (
    admet_calibration_and_domain,
    antibody_developability,
    assay_design_and_power,
    docking_validation,
    lead_optimization_ranking,
    neoantigen_prioritization,
    protein_design_qc,
    standardize_compounds,
)
from .ingestion import format_support_table, optional_adapter_status
from .lab import (
    autonomous_experiment_plan,
    bioprocess_time_series,
    gene_therapy_vector_qc,
    high_content_plate_qc,
    metagenomics_control_qc,
    microscopy_image_qc,
    organoid_3d_analysis,
    primer_crispr_qc,
    synthetic_construct_qc,
)
from .neuro import (
    autonomic_hrv_analysis,
    eeg_meg_research_pipeline,
    epilepsy_diary_analysis,
    expression_atlas_analysis,
    movement_disorder_quantification,
    multimodal_neurodegeneration_progression,
    neuro_omics_biomarker_validation,
    neuro_oncology_board,
    neurocritical_care_trends,
    neuroimaging_volume_workflow,
    neuropathology_image_analysis,
    normalize_neuro_variants,
    normalize_trial_portfolio,
    precision_neurology_consensus,
    simulate_multicompartment_neuro_pk,
    speech_language_biomarker_analysis,
    target_evidence_graph,
)


def execute_feature(
    category: str,
    feature_key: str,
    payload: Any,
    *,
    options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute one Step208 feature without importing Streamlit.

    The dispatcher is intentionally UI-independent so installers, background
    workers and automated tests can exercise the same scientific code path.
    """

    config = dict(options or {})
    if category == "Neuro/CNS":
        if feature_key == "advanced_eeg_meg":
            if isinstance(payload, dict):
                return eeg_meg_research_pipeline(
                    payload["data"],
                    sampling_rate=float(payload["sampling_rate"]),
                    time_col=payload.get("time_col"),
                )
            return eeg_meg_research_pipeline(
                payload,
                sampling_rate=float(config.get("sampling_rate", 128.0)),
                time_col=config.get("time_col", "time" if "time" in payload.columns else None),
            )
        if feature_key == "advanced_neuroimaging":
            if isinstance(payload, dict):
                return neuroimaging_volume_workflow(
                    payload["volume"],
                    voxel_spacing_mm=payload.get("voxel_spacing_mm"),
                    atlas=payload.get("atlas"),
                )
            return neuroimaging_volume_workflow(payload)
        if feature_key == "advanced_neurogenetics":
            return normalize_neuro_variants(payload, hpo_terms=config.get("hpo_terms", ("seizure", "developmental delay")))
        if feature_key == "advanced_expression_atlas":
            return expression_atlas_analysis(payload)
        if feature_key == "advanced_neuro_omics":
            return neuro_omics_biomarker_validation(payload, group_col=str(config.get("group_col", "group")))
        if feature_key == "advanced_precision_neurology":
            return precision_neurology_consensus(payload, repeats=int(config.get("repeats", 20)))
        if feature_key == "advanced_neuro_pk":
            return simulate_multicompartment_neuro_pk(**dict(payload or {}))
        if feature_key == "advanced_target_evidence":
            return target_evidence_graph(payload)
        if feature_key == "advanced_trial_intelligence":
            return normalize_trial_portfolio(payload)
        if feature_key == "neuro_oncology":
            return neuro_oncology_board(payload)
        if feature_key == "epilepsy_diary":
            return epilepsy_diary_analysis(payload)
        if feature_key == "movement_disorders":
            if isinstance(payload, dict):
                return movement_disorder_quantification(payload["data"], sampling_rate=float(payload["sampling_rate"]))
            return movement_disorder_quantification(payload, sampling_rate=float(config.get("sampling_rate", 50.0)))
        if feature_key == "autonomic_hrv":
            return autonomic_hrv_analysis(payload)
        if feature_key == "speech_language":
            return speech_language_biomarker_analysis(payload)
        if feature_key == "neurodegeneration_progression":
            return multimodal_neurodegeneration_progression(payload)
        if feature_key == "neuropathology":
            return neuropathology_image_analysis(payload)
        if feature_key == "neurocritical_care":
            return neurocritical_care_trends(payload)

    if category == "Bioinformatics":
        if feature_key == "format_readiness":
            support = format_support_table()
            adapters = optional_adapter_status()
            return {
                "format_support": support,
                "optional_adapters": adapters,
                "summary": {
                    "formats": len(support),
                    "available_optional_adapters": int(adapters["available"].sum()) if not adapters.empty else 0,
                },
                "scientific_boundary": "Capability status only; target-machine validation is required.",
            }
        if feature_key == "genomic_cohort_qc":
            return genomic_cohort_qc(payload)
        if feature_key == "single_cell_qc":
            if isinstance(payload, dict):
                return single_cell_qc(payload["matrix"], gene_names=payload.get("gene_names"))
            return single_cell_qc(payload)
        if feature_key == "spatial_qc":
            return spatial_omics_qc(payload)
        if feature_key == "multiomics_qc":
            return multiomics_batch_qc(payload)
        if feature_key == "microbiome_controls":
            if not isinstance(payload, dict):
                raise ValueError("Microbiome control QC requires abundance and metadata tables.")
            return microbiome_contamination_qc(payload["abundance"], payload["metadata"])
        if feature_key == "tool_readiness":
            table = external_tool_readiness(tools=config.get("tools"))
            return {
                "tools": table,
                "summary": {"tools": len(table), "available": int(table["available"].sum()) if not table.empty else 0},
                "scientific_boundary": "Tool discovery does not qualify scientific correctness.",
            }
        if feature_key == "reproducibility":
            return build_reproducibility_manifest(
                inputs=config.get("inputs", ()),
                parameters=config.get("parameters", {"feature_center": "Bioinformatics V208"}),
                references=config.get("references", ()),
            )

    if category == "Discovery":
        if feature_key == "compound_standardization":
            return standardize_compounds(payload)
        if feature_key == "docking_validation":
            return docking_validation(payload)
        if feature_key == "admet_calibration":
            if not isinstance(payload, dict):
                raise ValueError("ADMET calibration requires reference and query datasets.")
            return admet_calibration_and_domain(payload["reference"], payload["query"])
        if feature_key == "lead_optimization":
            return lead_optimization_ranking(
                payload,
                maximize=config.get("maximize", ("potency", "selectivity")),
                minimize=config.get("minimize", ("clearance", "toxicity")),
            )
        if feature_key == "protein_design":
            if not isinstance(payload, dict):
                raise ValueError("Protein design QC requires a reference sequence and candidate table.")
            return protein_design_qc(
                payload["reference"],
                payload["candidates"],
                conserved_positions=payload.get("conserved_positions", ()),
            )
        if feature_key == "antibody_developability":
            return antibody_developability(payload)
        if feature_key == "neoantigen":
            return neoantigen_prioritization(payload)
        if feature_key == "assay_planning":
            return assay_design_and_power(**dict(payload or {}))

    if category == "Lab Analytics":
        if feature_key == "microscopy_qc":
            return microscopy_image_qc(payload)
        if feature_key == "plate_qc":
            return high_content_plate_qc(payload)
        if feature_key == "bioprocess":
            return bioprocess_time_series(payload)
        if feature_key == "metagenomics_controls":
            return metagenomics_control_qc(payload)
        if feature_key == "synthetic_biology":
            return synthetic_construct_qc(**dict(payload or {}))
        if feature_key == "primer_crispr":
            if not isinstance(payload, dict):
                raise ValueError("Primer/CRISPR QC requires primer and target inputs.")
            return primer_crispr_qc(**payload)
        if feature_key == "organoid":
            return organoid_3d_analysis(payload)
        if feature_key == "gene_therapy":
            return gene_therapy_vector_qc(**dict(payload or {}))
        if feature_key == "experiment_planner":
            return autonomous_experiment_plan(**dict(payload or {}))

    raise KeyError(f"Unknown Step208 feature: {category} / {feature_key}")
