# Step200 — 23 Neuro/CNS Modules Maximum-Potential Matrix

## 1. BBB Permeability Predictor

- **Workspace:** Drug Discovery
- **Step199 integration:** Analogue optimization integration, applicability-aware ranking and reference deltas
- **Step200 hardening:** Structured execution envelopes, payload guardrails, deterministic run fingerprints, isolated failures, resource-gate visibility, evidence graph support, benchmark/applicability/uncertainty review, and recovery guidance
- **Performance optimization:** Interactive/background routing, bounded arrays/tables, deterministic downsampling, cached local resources, and fail-closed optional-adapter handling
- **Scientific resources required:** bbb_reference
- **Remaining gate:** Bind and benchmark an approved experimental BBB dataset
- **Qualification class:** external calibration
- **Boundary:** Research screening only; not a measured permeability result.

## 2. Neuro-Target Curation & Tagging

- **Workspace:** Targets & Mechanisms
- **Step199 integration:** Model-selection and rare-disease boards now consume target context
- **Step200 hardening:** Structured execution envelopes, payload guardrails, deterministic run fingerprints, isolated failures, resource-gate visibility, evidence graph support, benchmark/applicability/uncertainty review, and recovery guidance
- **Performance optimization:** Interactive/background routing, bounded arrays/tables, deterministic downsampling, cached local resources, and fail-closed optional-adapter handling
- **Scientific resources required:** target_registry
- **Remaining gate:** Expand licensed/versioned CNS target registry with isoforms and species
- **Qualification class:** approved data binding
- **Boundary:** Coverage is bounded by the bundled curated snapshot.

## 3. Neurotransmitter Pathway Mapper

- **Workspace:** Targets & Mechanisms
- **Step199 integration:** Pathway context is propagated into advanced review workflows
- **Step200 hardening:** Structured execution envelopes, payload guardrails, deterministic run fingerprints, isolated failures, resource-gate visibility, evidence graph support, benchmark/applicability/uncertainty review, and recovery guidance
- **Performance optimization:** Interactive/background routing, bounded arrays/tables, deterministic downsampling, cached local resources, and fail-closed optional-adapter handling
- **Scientific resources required:** target_registry
- **Remaining gate:** Add evidence-level pathway graph and publication provenance
- **Qualification class:** reference qualification
- **Boundary:** Unmapped does not prove absence of pathway involvement.

## 4. Ion Channel Classifier

- **Workspace:** Targets & Mechanisms
- **Step199 integration:** Safety board can combine channel target occupancy and CNS relevance
- **Step200 hardening:** Structured execution envelopes, payload guardrails, deterministic run fingerprints, isolated failures, resource-gate visibility, evidence graph support, benchmark/applicability/uncertainty review, and recovery guidance
- **Performance optimization:** Interactive/background routing, bounded arrays/tables, deterministic downsampling, cached local resources, and fail-closed optional-adapter handling
- **Scientific resources required:** protein_domains
- **Remaining gate:** Qualify Pfam/InterPro/HMMER topology and subtype adapters
- **Qualification class:** specialist engine
- **Boundary:** Heuristic sequence triage is not experimental channel characterization.

## 5. Neuro-Relevant GPCR Classifier

- **Workspace:** Targets & Mechanisms
- **Step199 integration:** Safety and dose-effect workflows support receptor-family panels
- **Step200 hardening:** Structured execution envelopes, payload guardrails, deterministic run fingerprints, isolated failures, resource-gate visibility, evidence graph support, benchmark/applicability/uncertainty review, and recovery guidance
- **Performance optimization:** Interactive/background routing, bounded arrays/tables, deterministic downsampling, cached local resources, and fail-closed optional-adapter handling
- **Scientific resources required:** gpcr_reference
- **Remaining gate:** Bind GPCRdb alignment, numbering and pocket annotations
- **Qualification class:** specialist engine
- **Boundary:** Closely related receptor families require reference-alignment confirmation.

## 6. CNS Disease-Target Database

- **Workspace:** Disease & Molecular Biology
- **Step199 integration:** Rare disease and model-selection boards consume disease associations
- **Step200 hardening:** Structured execution envelopes, payload guardrails, deterministic run fingerprints, isolated failures, resource-gate visibility, evidence graph support, benchmark/applicability/uncertainty review, and recovery guidance
- **Performance optimization:** Interactive/background routing, bounded arrays/tables, deterministic downsampling, cached local resources, and fail-closed optional-adapter handling
- **Scientific resources required:** target_registry
- **Remaining gate:** Add genetic/pharmacological evidence separation and source records
- **Qualification class:** approved evidence
- **Boundary:** Associations are research evidence, not diagnostic claims.

## 7. CNS Drug-Likeness Scorer

- **Workspace:** Drug Discovery
- **Step199 integration:** Multi-objective compound board with configurable normalized weights
- **Step200 hardening:** Structured execution envelopes, payload guardrails, deterministic run fingerprints, isolated failures, resource-gate visibility, evidence graph support, benchmark/applicability/uncertainty review, and recovery guidance
- **Performance optimization:** Interactive/background routing, bounded arrays/tables, deterministic downsampling, cached local resources, and fail-closed optional-adapter handling
- **Scientific resources required:** bbb_reference
- **Remaining gate:** Calibrate MPO/ADME weights against independent CNS drug sets
- **Qualification class:** external benchmark
- **Boundary:** Composite weights are transparent screening choices requiring external calibration.

## 8. Off-Target Neurotoxicity Flagging

- **Workspace:** Targets & Mechanisms
- **Step199 integration:** Exposure-aware occupancy safety-margin matrix
- **Step200 hardening:** Structured execution envelopes, payload guardrails, deterministic run fingerprints, isolated failures, resource-gate visibility, evidence graph support, benchmark/applicability/uncertainty review, and recovery guidance
- **Performance optimization:** Interactive/background routing, bounded arrays/tables, deterministic downsampling, cached local resources, and fail-closed optional-adapter handling
- **Scientific resources required:** target_registry
- **Remaining gate:** Connect a qualified broad off-target panel and metabolite coverage
- **Qualification class:** coverage qualification
- **Boundary:** Cannot discover off-targets absent from the supplied binding profile.

## 9. Neurodegeneration Protein Aggregation Risk

- **Workspace:** Disease & Molecular Biology
- **Step199 integration:** Mutation delta comparison and rescue-hypothesis generation
- **Step200 hardening:** Structured execution envelopes, payload guardrails, deterministic run fingerprints, isolated failures, resource-gate visibility, evidence graph support, benchmark/applicability/uncertainty review, and recovery guidance
- **Performance optimization:** Interactive/background routing, bounded arrays/tables, deterministic downsampling, cached local resources, and fail-closed optional-adapter handling
- **Scientific resources required:** aggregation_method
- **Remaining gate:** Integrate and independently benchmark an established aggregation engine
- **Qualification class:** method qualification
- **Boundary:** Heuristic propensity is not a validated TANGO/WALTZ replacement.

## 10. CNS Side-Effect Predictor

- **Workspace:** Targets & Mechanisms
- **Step199 integration:** Safety-margin context separates supplied-panel coverage from exposure risk
- **Step200 hardening:** Structured execution envelopes, payload guardrails, deterministic run fingerprints, isolated failures, resource-gate visibility, evidence graph support, benchmark/applicability/uncertainty review, and recovery guidance
- **Performance optimization:** Interactive/background routing, bounded arrays/tables, deterministic downsampling, cached local resources, and fail-closed optional-adapter handling
- **Scientific resources required:** side_effect_map, side_effect_reference
- **Remaining gate:** Bind labelled side-effect data with calibration and dose context
- **Qualification class:** data feasibility
- **Boundary:** Unobserved targets are excluded rather than treated as zero risk.

## 11. Neuroinflammation Target Set

- **Workspace:** Disease & Molecular Biology
- **Step199 integration:** Microglia co-culture receives target-specific model-selection weighting
- **Step200 hardening:** Structured execution envelopes, payload guardrails, deterministic run fingerprints, isolated failures, resource-gate visibility, evidence graph support, benchmark/applicability/uncertainty review, and recovery guidance
- **Performance optimization:** Interactive/background routing, bounded arrays/tables, deterministic downsampling, cached local resources, and fail-closed optional-adapter handling
- **Scientific resources required:** target_registry
- **Remaining gate:** Add disease-stage and cell-state reference atlases
- **Qualification class:** curation
- **Boundary:** The field is evolving and requires periodic curation.

## 12. Blood-CSF Barrier Module

- **Workspace:** Drug Discovery
- **Step199 integration:** Preserved fail-closed status in compound optimization and dose workflows
- **Step200 hardening:** Structured execution envelopes, payload guardrails, deterministic run fingerprints, isolated failures, resource-gate visibility, evidence graph support, benchmark/applicability/uncertainty review, and recovery guidance
- **Performance optimization:** Interactive/background routing, bounded arrays/tables, deterministic downsampling, cached local resources, and fail-closed optional-adapter handling
- **Scientific resources required:** blood_csf_method
- **Remaining gate:** Identify and validate a route-specific blood-CSF methodology
- **Qualification class:** method feasibility
- **Boundary:** No claim of clinically validated blood-CSF permeability prediction.

## 13. Species/Model Organism Cross-Reference

- **Workspace:** Translation
- **Step199 integration:** Ranked orthogonal model assistant including iPSC/organoid/co-culture
- **Step200 hardening:** Structured execution envelopes, payload guardrails, deterministic run fingerprints, isolated failures, resource-gate visibility, evidence graph support, benchmark/applicability/uncertainty review, and recovery guidance
- **Performance optimization:** Interactive/background routing, bounded arrays/tables, deterministic downsampling, cached local resources, and fail-closed optional-adapter handling
- **Scientific resources required:** model_organisms
- **Remaining gate:** Bind ortholog identity, phenotype and knockout viability resources
- **Qualification class:** data binding
- **Boundary:** Availability does not establish model validity for a specific experiment.

## 14. CNS ADME & Transporter Interaction Studio

- **Workspace:** Drug Discovery
- **Step199 integration:** ADME proxies incorporated into Pareto analogue optimization
- **Step200 hardening:** Structured execution envelopes, payload guardrails, deterministic run fingerprints, isolated failures, resource-gate visibility, evidence graph support, benchmark/applicability/uncertainty review, and recovery guidance
- **Performance optimization:** Interactive/background routing, bounded arrays/tables, deterministic downsampling, cached local resources, and fail-closed optional-adapter handling
- **Scientific resources required:** adme_models
- **Remaining gate:** Qualify transporter/CYP substrate and inhibitor models
- **Qualification class:** model qualification
- **Boundary:** Outputs are structural alerts and proxies, not measured ADME.

## 15. Brain Exposure & Neuro-PK Simulator

- **Workspace:** Drug Discovery
- **Step199 integration:** Integrated time-resolved dose-to-effect window
- **Step200 hardening:** Structured execution envelopes, payload guardrails, deterministic run fingerprints, isolated failures, resource-gate visibility, evidence graph support, benchmark/applicability/uncertainty review, and recovery guidance
- **Performance optimization:** Interactive/background routing, bounded arrays/tables, deterministic downsampling, cached local resources, and fail-closed optional-adapter handling
- **Scientific resources required:** pk_validation
- **Remaining gate:** Add externally qualified PBPK compartments and population variability
- **Qualification class:** PK validation
- **Boundary:** Reliable interpretation depends on user-supplied PK parameters.

## 16. Receptor Occupancy & Target Engagement Lab

- **Workspace:** Drug Discovery
- **Step199 integration:** Primary/off-target occupancy matrix and time-dependent effect window
- **Step200 hardening:** Structured execution envelopes, payload guardrails, deterministic run fingerprints, isolated failures, resource-gate visibility, evidence graph support, benchmark/applicability/uncertainty review, and recovery guidance
- **Performance optimization:** Interactive/background routing, bounded arrays/tables, deterministic downsampling, cached local resources, and fail-closed optional-adapter handling
- **Scientific resources required:** pk_validation
- **Remaining gate:** Add kinetic, competition, active-metabolite and efficacy models
- **Qualification class:** mechanistic validation
- **Boundary:** Equilibrium occupancy omits complex kinetics and active metabolites.

## 17. Neurogenetics & Variant Interpretation

- **Workspace:** Disease & Molecular Biology
- **Step199 integration:** Rare neurological disease board with target, expression and model context
- **Step200 hardening:** Structured execution envelopes, payload guardrails, deterministic run fingerprints, isolated failures, resource-gate visibility, evidence graph support, benchmark/applicability/uncertainty review, and recovery guidance
- **Performance optimization:** Interactive/background routing, bounded arrays/tables, deterministic downsampling, cached local resources, and fail-closed optional-adapter handling
- **Scientific resources required:** variant_evidence
- **Remaining gate:** Bind VEP/ClinVar/gnomAD/HPO and expert ACMG sign-off
- **Qualification class:** clinical-grade evidence
- **Boundary:** Research interpretation only; no clinical diagnosis or ACMG sign-out.

## 18. Brain Cell-Type & Regional Expression Atlas

- **Workspace:** Disease & Molecular Biology
- **Step199 integration:** Expression context incorporated in model and safety interpretation
- **Step200 hardening:** Structured execution envelopes, payload guardrails, deterministic run fingerprints, isolated failures, resource-gate visibility, evidence graph support, benchmark/applicability/uncertainty review, and recovery guidance
- **Performance optimization:** Interactive/background routing, bounded arrays/tables, deterministic downsampling, cached local resources, and fail-closed optional-adapter handling
- **Scientific resources required:** brain_expression
- **Remaining gate:** Replace demo summaries with qualified bulk/single-cell/spatial atlases
- **Qualification class:** approved data binding
- **Boundary:** Bundled values are reference/demo summaries and must be replaced for release use.

## 19. Neuro-Omics Biomarker Discovery Studio

- **Workspace:** Disease & Molecular Biology
- **Step199 integration:** Multivariate cross-validated disease signature builder
- **Step200 hardening:** Structured execution envelopes, payload guardrails, deterministic run fingerprints, isolated failures, resource-gate visibility, evidence graph support, benchmark/applicability/uncertainty review, and recovery guidance
- **Performance optimization:** Interactive/background routing, bounded arrays/tables, deterministic downsampling, cached local resources, and fail-closed optional-adapter handling
- **Scientific resources required:** omics_external_validation
- **Remaining gate:** Nested feature selection and independent cohort replication
- **Qualification class:** external validation
- **Boundary:** Discovery statistics require independent-cohort validation.

## 20. EEG/MEG & Neural Signal Analytics

- **Workspace:** Imaging & Signals
- **Step199 integration:** Synchronized event/channel review board and reviewer decisions
- **Step200 hardening:** Structured execution envelopes, payload guardrails, deterministic run fingerprints, isolated failures, resource-gate visibility, evidence graph support, benchmark/applicability/uncertainty review, and recovery guidance
- **Performance optimization:** Interactive/background routing, bounded arrays/tables, deterministic downsampling, cached local resources, and fail-closed optional-adapter handling
- **Scientific resources required:** neural_signal_adapters
- **Remaining gate:** Qualify MNE workflows, montages, ICA, epoching and clinical datasets
- **Qualification class:** device/workflow qualification
- **Boundary:** Not a medical-device seizure or sleep diagnostic.

## 21. Neuroimaging & Connectomics Studio

- **Workspace:** Imaging & Signals
- **Step199 integration:** 3D surface/overlay digital-twin visualization
- **Step200 hardening:** Structured execution envelopes, payload guardrails, deterministic run fingerprints, isolated failures, resource-gate visibility, evidence graph support, benchmark/applicability/uncertainty review, and recovery guidance
- **Performance optimization:** Interactive/background routing, bounded arrays/tables, deterministic downsampling, cached local resources, and fail-closed optional-adapter handling
- **Scientific resources required:** neuroimaging_adapters
- **Remaining gate:** Qualify DICOM/NIfTI orientation, registration, atlas and segmentation
- **Qualification class:** imaging qualification
- **Boundary:** NIfTI/DICOM support is optional and depends on separately qualified adapters.

## 22. CNS Clinical Evidence & Trial Intelligence

- **Workspace:** Translation
- **Step199 integration:** Advanced boards retain trial/evidence boundary and project provenance
- **Step200 hardening:** Structured execution envelopes, payload guardrails, deterministic run fingerprints, isolated failures, resource-gate visibility, evidence graph support, benchmark/applicability/uncertainty review, and recovery guidance
- **Performance optimization:** Interactive/background routing, bounded arrays/tables, deterministic downsampling, cached local resources, and fail-closed optional-adapter handling
- **Scientific resources required:** clinical_trials
- **Remaining gate:** Connect a current approved trial provider and NLP normalization
- **Qualification class:** current provider
- **Boundary:** No live-trial completeness is implied unless an approved current provider is connected.

## 23. Precision Neurology & Patient Stratification

- **Workspace:** Translation
- **Step199 integration:** Advanced outputs can be combined in persistent project review
- **Step200 hardening:** Structured execution envelopes, payload guardrails, deterministic run fingerprints, isolated failures, resource-gate visibility, evidence graph support, benchmark/applicability/uncertainty review, and recovery guidance
- **Performance optimization:** Interactive/background routing, bounded arrays/tables, deterministic downsampling, cached local resources, and fail-closed optional-adapter handling
- **Scientific resources required:** precision_external_cohort
- **Remaining gate:** External outcome validation, fairness and longitudinal modelling
- **Qualification class:** independent cohort
- **Boundary:** Not a treatment recommendation or clinical risk score.
