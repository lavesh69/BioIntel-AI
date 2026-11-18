from __future__ import annotations

from typing import Any

import numpy as np

from biointel.neuro_cns.chemistry import (
    bbb_batch,
    blood_csf_barrier,
    cns_adme_transporters,
    cns_drug_likeness,
    receptor_occupancy,
    simulate_brain_exposure,
)
from biointel.neuro_cns.clinical import trial_intelligence
from biointel.neuro_cns.demos import (
    DEMO_AGGREGATION_SEQUENCE,
    DEMO_GPCR_SEQUENCE,
    DEMO_PROTEIN_SEQUENCE,
    DEMO_SMILES,
    binding_profile,
    cohort,
    eeg,
    omics,
    roi_timeseries,
    trials,
    variants,
)
from biointel.neuro_cns.genetics import prioritize_variants
from biointel.neuro_cns.imaging import connectivity_from_timeseries, profile_image_array
from biointel.neuro_cns.omics import biomarker_discovery
from biointel.neuro_cns.precision import stratify_research_cohort
from biointel.neuro_cns.safety import aggregation_risk, cns_side_effects, off_target_neurotoxicity
from biointel.neuro_cns.signals import analyze_neural_signals
from biointel.neuro_cns.translational_v207 import (
    brain_network_vulnerability_analysis,
    cognitive_trajectory_analysis,
    demo_frame as step207_demo_frame,
    digital_neurology_sensor_analysis,
    fluid_biomarker_panel,
    neurodevelopmental_trajectory_analysis,
    neuroimmune_interaction_analysis,
    neurorehabilitation_response_analysis,
    neurovascular_research_profile,
    polypharmacy_cns_burden,
    sleep_circadian_profile,
)
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
from biointel.module_features_v208.demos import demo_payload as v208_demo_payload
from biointel.module_features_v208.neuro import (
    autonomic_hrv_analysis,
    epilepsy_diary_analysis,
    movement_disorder_quantification,
    multimodal_neurodegeneration_progression,
    neuro_oncology_board,
    neurocritical_care_trends,
    neuropathology_image_analysis,
    speech_language_biomarker_analysis,
)


def demo_brain_volume() -> np.ndarray:
    x, y, z = np.indices((32, 36, 24))
    core = ((x - 16) / 10) ** 2 + ((y - 18) / 13) ** 2 + ((z - 12) / 8) ** 2
    lesion = ((x - 21) / 3.2) ** 2 + ((y - 15) / 4.0) ** 2 + ((z - 11) / 3.0) ** 2
    volume = np.exp(-2.0 * core)
    volume += 1.8 * np.exp(-2.5 * lesion)
    volume[core > 1.2] = 0.0
    return volume.astype(np.float32)


def run_complete_demo_showcase() -> dict[str, Any]:
    compounds = [{"compound_id": name.lower(), "smiles": smiles} for name, smiles in DEMO_SMILES.items()]
    binding_rows = binding_profile().to_dict(orient="records")
    pk = simulate_brain_exposure(
        initial_plasma_concentration=100.0,
        half_life_hours=6.0,
        duration_hours=36.0,
        passive_permeability_factor=0.75,
        efflux_ratio=0.25,
        fraction_unbound_plasma=0.12,
        fraction_unbound_brain=0.08,
        effective_threshold=4.0,
        route="oral",
        absorption_half_life_hours=1.2,
        dose_count=2,
        dosing_interval_hours=12.0,
    )
    occupancy_rows = [
        {"target": "DRD2", "kd": 5, "unit": "nM", "role": "primary", "hill_coefficient": 1.0},
        {"target": "HTR2A", "kd": 45, "unit": "nM", "role": "off_target", "hill_coefficient": 1.0},
        {"target": "SCN1A", "kd": 120, "unit": "nM", "role": "off_target", "hill_coefficient": 1.2},
    ]
    volume = demo_brain_volume()
    return {
        "bbb_permeability": bbb_batch(compounds),
        "neuro_target_curation": target_tagging("DRD2"),
        "neurotransmitter_pathway": pathway_mapping("DRD2"),
        "ion_channel_classifier": classify_ion_channel(DEMO_PROTEIN_SEQUENCE),
        "gpcr_classifier": classify_gpcr(DEMO_GPCR_SEQUENCE),
        "cns_disease_targets": disease_target_table(disease="Alzheimer disease"),
        "cns_drug_likeness": cns_drug_likeness(DEMO_SMILES["Caffeine"]),
        "off_target_neurotoxicity": off_target_neurotoxicity(binding_rows, primary_target="EGFR", brain_exposure_factor=0.8),
        "aggregation_risk": aggregation_risk(DEMO_AGGREGATION_SEQUENCE),
        "cns_side_effects": cns_side_effects(binding_rows, brain_exposure_factor=0.8),
        "neuroinflammation": neuroinflammation_lookup("TREM2"),
        "blood_csf_barrier": blood_csf_barrier(DEMO_SMILES["Caffeine"]),
        "model_organism": model_organism_cross_reference("DRD2"),
        "cns_adme_transporters": cns_adme_transporters(DEMO_SMILES["Diazepam"]),
        "brain_exposure_pk": pk,
        "receptor_occupancy": receptor_occupancy(20.0, occupancy_rows, concentration_unit="nM"),
        "neurogenetics": prioritize_variants(variants(), genome_build="GRCh38"),
        "brain_expression_atlas": brain_expression_profile("TREM2"),
        "neuro_omics_biomarkers": biomarker_discovery(omics(), "group", bootstrap_iterations=40),
        "eeg_meg_analytics": analyze_neural_signals(eeg(), 256.0, "time"),
        "neuroimaging_connectomics": {
            "image_profile": profile_image_array(volume, threshold_method="otsu", voxel_volume_mm3=1.0, minimum_component_voxels=5),
            "connectivity": connectivity_from_timeseries(roi_timeseries(), "time"),
        },
        "cns_clinical_trials": trial_intelligence(trials()),
        "precision_neurology": stratify_research_cohort(cohort(), identifier_column="sample_id", cluster_count=None, bootstrap_iterations=10),
        "neurovascular_research": neurovascular_research_profile(step207_demo_frame("neurovascular_research")),
        "sleep_circadian": sleep_circadian_profile(step207_demo_frame("sleep_circadian")),
        "fluid_biomarkers": fluid_biomarker_panel(step207_demo_frame("fluid_biomarkers")),
        "digital_neurology": digital_neurology_sensor_analysis(step207_demo_frame("digital_neurology")),
        "neuroimmune_interactions": neuroimmune_interaction_analysis(step207_demo_frame("neuroimmune_interactions")),
        "cognitive_trajectory": cognitive_trajectory_analysis(step207_demo_frame("cognitive_trajectory")),
        "neurorehabilitation": neurorehabilitation_response_analysis(step207_demo_frame("neurorehabilitation")),
        "polypharmacy_cns": polypharmacy_cns_burden(step207_demo_frame("polypharmacy_cns")),
        "brain_network_vulnerability": brain_network_vulnerability_analysis(step207_demo_frame("brain_network_vulnerability")),
        "neurodevelopmental_trajectory": neurodevelopmental_trajectory_analysis(step207_demo_frame("neurodevelopmental_trajectory")),
        "neuro_oncology": neuro_oncology_board(v208_demo_payload("neuro_oncology")),
        "epilepsy_diary": epilepsy_diary_analysis(v208_demo_payload("epilepsy_diary")),
        "movement_disorders": movement_disorder_quantification(v208_demo_payload("movement_disorders")["data"], sampling_rate=v208_demo_payload("movement_disorders")["sampling_rate"]),
        "autonomic_hrv": autonomic_hrv_analysis(v208_demo_payload("autonomic_hrv")),
        "speech_language": speech_language_biomarker_analysis(v208_demo_payload("speech_language")),
        "neurodegeneration_progression": multimodal_neurodegeneration_progression(v208_demo_payload("neurodegeneration_progression")),
        "neuropathology": neuropathology_image_analysis(v208_demo_payload("neuropathology")),
        "neurocritical_care": neurocritical_care_trends(v208_demo_payload("neurocritical_care")),
    }
