from __future__ import annotations

import pandas as pd


MODULE_RECOMMENDATIONS: tuple[dict[str, object], ...] = (
    {"module": 1, "key": "bbb_permeability", "implemented_step199": "Analogue optimization integration, applicability-aware ranking and reference deltas", "remaining_priority": "Bind and benchmark an approved experimental BBB dataset", "gate": "external calibration"},
    {"module": 2, "key": "neuro_target_curation", "implemented_step199": "Model-selection and rare-disease boards now consume target context", "remaining_priority": "Expand licensed/versioned CNS target registry with isoforms and species", "gate": "approved data binding"},
    {"module": 3, "key": "neurotransmitter_pathway", "implemented_step199": "Pathway context is propagated into advanced review workflows", "remaining_priority": "Add evidence-level pathway graph and publication provenance", "gate": "reference qualification"},
    {"module": 4, "key": "ion_channel_classifier", "implemented_step199": "Safety board can combine channel target occupancy and CNS relevance", "remaining_priority": "Qualify Pfam/InterPro/HMMER topology and subtype adapters", "gate": "specialist engine"},
    {"module": 5, "key": "gpcr_classifier", "implemented_step199": "Safety and dose-effect workflows support receptor-family panels", "remaining_priority": "Bind GPCRdb alignment, numbering and pocket annotations", "gate": "specialist engine"},
    {"module": 6, "key": "cns_disease_targets", "implemented_step199": "Rare disease and model-selection boards consume disease associations", "remaining_priority": "Add genetic/pharmacological evidence separation and source records", "gate": "approved evidence"},
    {"module": 7, "key": "cns_drug_likeness", "implemented_step199": "Multi-objective compound board with configurable normalized weights", "remaining_priority": "Calibrate MPO/ADME weights against independent CNS drug sets", "gate": "external benchmark"},
    {"module": 8, "key": "off_target_neurotoxicity", "implemented_step199": "Exposure-aware occupancy safety-margin matrix", "remaining_priority": "Connect a qualified broad off-target panel and metabolite coverage", "gate": "coverage qualification"},
    {"module": 9, "key": "aggregation_risk", "implemented_step199": "Mutation delta comparison and rescue-hypothesis generation", "remaining_priority": "Integrate and independently benchmark an established aggregation engine", "gate": "method qualification"},
    {"module": 10, "key": "cns_side_effects", "implemented_step199": "Safety-margin context separates supplied-panel coverage from exposure risk", "remaining_priority": "Bind labelled side-effect data with calibration and dose context", "gate": "data feasibility"},
    {"module": 11, "key": "neuroinflammation", "implemented_step199": "Microglia co-culture receives target-specific model-selection weighting", "remaining_priority": "Add disease-stage and cell-state reference atlases", "gate": "curation"},
    {"module": 12, "key": "blood_csf_barrier", "implemented_step199": "Preserved fail-closed status in compound optimization and dose workflows", "remaining_priority": "Identify and validate a route-specific blood-CSF methodology", "gate": "method feasibility"},
    {"module": 13, "key": "model_organism", "implemented_step199": "Ranked orthogonal model assistant including iPSC/organoid/co-culture", "remaining_priority": "Bind ortholog identity, phenotype and knockout viability resources", "gate": "data binding"},
    {"module": 14, "key": "cns_adme_transporters", "implemented_step199": "ADME proxies incorporated into Pareto analogue optimization", "remaining_priority": "Qualify transporter/CYP substrate and inhibitor models", "gate": "model qualification"},
    {"module": 15, "key": "brain_exposure_pk", "implemented_step199": "Integrated time-resolved dose-to-effect window", "remaining_priority": "Add externally qualified PBPK compartments and population variability", "gate": "PK validation"},
    {"module": 16, "key": "receptor_occupancy", "implemented_step199": "Primary/off-target occupancy matrix and time-dependent effect window", "remaining_priority": "Add kinetic, competition, active-metabolite and efficacy models", "gate": "mechanistic validation"},
    {"module": 17, "key": "neurogenetics", "implemented_step199": "Rare neurological disease board with target, expression and model context", "remaining_priority": "Bind VEP/ClinVar/gnomAD/HPO and expert ACMG sign-off", "gate": "clinical-grade evidence"},
    {"module": 18, "key": "brain_expression_atlas", "implemented_step199": "Expression context incorporated in model and safety interpretation", "remaining_priority": "Replace demo summaries with qualified bulk/single-cell/spatial atlases", "gate": "approved data binding"},
    {"module": 19, "key": "neuro_omics_biomarkers", "implemented_step199": "Multivariate cross-validated disease signature builder", "remaining_priority": "Nested feature selection and independent cohort replication", "gate": "external validation"},
    {"module": 20, "key": "eeg_meg_analytics", "implemented_step199": "Synchronized event/channel review board and reviewer decisions", "remaining_priority": "Qualify MNE workflows, montages, ICA, epoching and clinical datasets", "gate": "device/workflow qualification"},
    {"module": 21, "key": "neuroimaging_connectomics", "implemented_step199": "3D surface/overlay digital-twin visualization", "remaining_priority": "Qualify DICOM/NIfTI orientation, registration, atlas and segmentation", "gate": "imaging qualification"},
    {"module": 22, "key": "cns_clinical_trials", "implemented_step199": "Advanced boards retain trial/evidence boundary and project provenance", "remaining_priority": "Connect a current approved trial provider and NLP normalization", "gate": "current provider"},
    {"module": 23, "key": "precision_neurology", "implemented_step199": "Advanced outputs can be combined in persistent project review", "remaining_priority": "External outcome validation, fairness and longitudinal modelling", "gate": "independent cohort"},
    {"module": 24, "key": "neurovascular_research", "implemented_step199": "Step207 transparent vascular-factor cohort triage and completeness review", "remaining_priority": "Prospective external stroke/neurovascular cohort calibration", "gate": "external calibration"},
    {"module": 25, "key": "sleep_circadian", "implemented_step199": "Step207 actigraphy-like rhythm stability and fragmentation analysis", "remaining_priority": "Polysomnography/qualified actigraphy comparison and device harmonisation", "gate": "device/workflow qualification"},
    {"module": 26, "key": "fluid_biomarkers", "implemented_step199": "Step207 effect-size, AUC, missingness and internal panel scoring", "remaining_priority": "Assay-specific calibration and independent CSF/blood cohort replication", "gate": "external validation"},
    {"module": 27, "key": "digital_neurology", "implemented_step199": "Step207 wearable signal windows, variability and candidate-event review", "remaining_priority": "Device-specific validation, sensor placement and labelled-event benchmarks", "gate": "device/workflow qualification"},
    {"module": 28, "key": "neuroimmune_interactions", "implemented_step199": "Step207 cell-state/pathway differential scores and interaction network", "remaining_priority": "Qualified single-cell/spatial neuroimmune references and replication", "gate": "approved data binding"},
    {"module": 29, "key": "cognitive_trajectory", "implemented_step199": "Step207 longitudinal slopes and candidate change-point review", "remaining_priority": "Validated instruments, practice-effect handling and external longitudinal cohorts", "gate": "independent cohort"},
    {"module": 30, "key": "neurorehabilitation", "implemented_step199": "Step207 MCID-aware change and reliable-change research analysis", "remaining_priority": "Protocol-specific MCIDs and prospective rehabilitation outcome validation", "gate": "external validation"},
    {"module": 31, "key": "polypharmacy_cns", "implemented_step199": "Step207 user-annotated CNS medication burden and interaction flags", "remaining_priority": "Current medication knowledge source and clinician-reviewed interaction evidence", "gate": "current provider"},
    {"module": 32, "key": "brain_network_vulnerability", "implemented_step199": "Step207 hub vulnerability, efficiency loss and resilience curves", "remaining_priority": "Atlas/site harmonisation and independent connectome benchmark qualification", "gate": "imaging qualification"},
    {"module": 33, "key": "neurodevelopmental_trajectory", "implemented_step199": "Step207 age-referenced z-trajectories and velocity flags", "remaining_priority": "Age/instrument-specific normative references and longitudinal validation", "gate": "independent cohort"},
    {"module": 34, "key": "neuro_oncology", "implemented_step199": "Step208 multi-marker molecular deviation board", "remaining_priority": "Qualified tumour molecular references and external pathology review", "gate": "approved data binding"},
    {"module": 35, "key": "epilepsy_diary", "implemented_step199": "Step208 event timeline and diary-factor correlations", "remaining_priority": "Prospective diary/EEG/device validation", "gate": "external validation"},
    {"module": 36, "key": "movement_disorders", "implemented_step199": "Step208 tremor-band and movement-peak analytics", "remaining_priority": "Device placement and labelled movement benchmark qualification", "gate": "device/workflow qualification"},
    {"module": 37, "key": "autonomic_hrv", "implemented_step199": "Step208 time-domain HRV and posture summaries", "remaining_priority": "Controlled acquisition and autonomic reference cohorts", "gate": "device/workflow qualification"},
    {"module": 38, "key": "speech_language", "implemented_step199": "Step208 acoustic/language feature QC and deviation", "remaining_priority": "Validated acquisition protocol and external language cohorts", "gate": "independent cohort"},
    {"module": 39, "key": "neurodegeneration_progression", "implemented_step199": "Step208 multimodal longitudinal slopes", "remaining_priority": "Scale harmonisation and independent progression cohorts", "gate": "external validation"},
    {"module": 40, "key": "neuropathology", "implemented_step199": "Step208 image QC and candidate object quantification", "remaining_priority": "Stain-specific segmentation and pathologist validation", "gate": "imaging qualification"},
    {"module": 41, "key": "neurocritical_care", "implemented_step199": "Step208 trend slopes and candidate change points", "remaining_priority": "Prospective monitored-data validation; never bedside deployment", "gate": "external validation"},
)


def recommendation_frame() -> pd.DataFrame:
    frame = pd.DataFrame(MODULE_RECOMMENDATIONS)
    frame["implemented_step200"] = (
        "Structured execution envelopes, payload guardrails, deterministic run fingerprints, isolated failures, "
        "resource-gate visibility, evidence graph support, benchmark/applicability/uncertainty review, and recovery guidance"
    )
    frame["performance_optimization"] = (
        "Interactive/background routing, bounded arrays/tables, deterministic downsampling, cached local resources, "
        "and fail-closed optional-adapter handling"
    )
    frame["implemented_step201"] = (
        "Local scientific-resource binding and checksum registry, specialist-engine detection, privacy/de-identification guardrails, "
        "study-design planning, cohort-leakage auditing, distribution-drift monitoring, multi-site reproducibility review, "
        "professional PDF reporting, and release evidence-pack integrity manifests"
    )
    frame["remaining_external_gate"] = frame["remaining_priority"]
    frame["maximum_potential_status"] = "software_completion_hardened_external_scientific_gate_open"
    return frame


def gate_summary() -> pd.DataFrame:
    frame = recommendation_frame()
    return frame.groupby("gate", dropna=False).size().rename("module_count").reset_index().sort_values("module_count", ascending=False, ignore_index=True)
