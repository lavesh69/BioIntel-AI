from __future__ import annotations

from typing import Any, Iterable

from biointel.neuro_cns.chemistry import (
    bbb_permeability,
    blood_csf_barrier,
    cns_adme_transporters,
    cns_drug_likeness,
    receptor_occupancy,
    simulate_brain_exposure,
)
from biointel.neuro_cns.consistency import evaluate_results, result_quality_summary
from biointel.neuro_cns.safety import cns_side_effects, off_target_neurotoxicity
from biointel.neuro_cns.targets import (
    brain_expression_profile,
    classify_gpcr,
    classify_ion_channel,
    disease_target_table,
    model_organism_cross_reference,
    neuroinflammation_lookup,
    pathway_mapping,
    target_tagging,
)


def compound_to_clinic_workflow(
    smiles: str,
    *,
    compound_id: str | None = None,
    binding_rows: Iterable[dict[str, Any]] | None = None,
    pk_parameters: dict[str, Any] | None = None,
    free_brain_concentration: float | None = None,
    affinity_rows: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    results: dict[str, Any] = {
        "bbb_permeability": bbb_permeability(smiles, compound_id),
        "cns_drug_likeness": cns_drug_likeness(smiles),
        "cns_adme_transporters": cns_adme_transporters(smiles),
        "blood_csf_barrier": blood_csf_barrier(smiles),
    }
    if binding_rows is not None:
        rows = list(binding_rows)
        results["off_target_neurotoxicity"] = off_target_neurotoxicity(rows)
        results["cns_side_effects"] = cns_side_effects(rows)
    if pk_parameters:
        results["brain_exposure_pk"] = simulate_brain_exposure(**pk_parameters)
    if free_brain_concentration is not None and affinity_rows is not None:
        results["receptor_occupancy"] = receptor_occupancy(free_brain_concentration, affinity_rows)
    return {
        "workflow": "compound_to_clinic",
        "results": results,
        "consistency_findings": evaluate_results(results),
        "quality_summary": result_quality_summary(results),
        "scientific_boundary": "Integrated research screening workflow; each engine retains its own applicability limits.",
    }


def target_to_translation_workflow(identifier: str, *, sequence: str | None = None) -> dict[str, Any]:
    results: dict[str, Any] = {
        "neuro_target_curation": target_tagging(identifier, sequence),
        "neurotransmitter_pathway": pathway_mapping(identifier),
        "cns_disease_targets": disease_target_table(target=identifier),
        "neuroinflammation": neuroinflammation_lookup(identifier),
        "model_organism": model_organism_cross_reference(identifier),
        "brain_expression_atlas": brain_expression_profile(identifier),
    }
    if sequence:
        results["ion_channel_classifier"] = classify_ion_channel(sequence)
        results["gpcr_classifier"] = classify_gpcr(sequence)
    return {
        "workflow": "target_to_translation",
        "results": results,
        "consistency_findings": evaluate_results(results),
        "quality_summary": result_quality_summary(results),
        "scientific_boundary": "Integrated target-context workflow; unmatched data indicates coverage gaps, not biological absence.",
    }


DISEASE_WORKFLOWS: dict[str, tuple[str, ...]] = {
    "Alzheimer disease": ("neuro_target_curation", "cns_disease_targets", "aggregation_risk", "neuroinflammation", "brain_expression_atlas", "neuro_omics_biomarkers", "cns_clinical_trials"),
    "Parkinson disease": ("neurotransmitter_pathway", "aggregation_risk", "brain_expression_atlas", "neuro_omics_biomarkers", "model_organism", "cns_clinical_trials"),
    "Epilepsy": ("ion_channel_classifier", "neurogenetics", "eeg_meg_analytics", "cns_side_effects", "model_organism"),
    "Multiple sclerosis": ("neuroinflammation", "brain_expression_atlas", "neuro_omics_biomarkers", "neuroimaging_connectomics", "cns_clinical_trials"),
    "Brain tumour": ("brain_expression_atlas", "neuro_omics_biomarkers", "neuroimaging_connectomics", "cns_clinical_trials", "precision_neurology"),
    "Psychiatry": ("gpcr_classifier", "neurotransmitter_pathway", "cns_drug_likeness", "off_target_neurotoxicity", "cns_side_effects", "precision_neurology"),
    "ALS/neuromuscular": ("neurogenetics", "aggregation_risk", "brain_expression_atlas", "model_organism", "cns_clinical_trials"),
}


def disease_workflow_plan(disease: str) -> dict[str, Any]:
    selected = DISEASE_WORKFLOWS.get(disease)
    if selected is None:
        raise ValueError(f"Unknown guided disease workflow: {disease}")
    return {
        "disease": disease,
        "recommended_module_keys": list(selected),
        "sequence": [{"order": index + 1, "module_key": key} for index, key in enumerate(selected)],
        "boundary": "Workflow plan only; inputs, evidence and specialist validation remain module-specific.",
    }
