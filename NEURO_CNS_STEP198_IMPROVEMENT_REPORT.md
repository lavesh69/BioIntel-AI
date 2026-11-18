# BioIntel AI Step198 — Neuro/CNS Improvement Report

## Release objective

Upgrade the unified 23-module Neuro/CNS Intelligence Studio from a functional Step197 implementation into a more resilient, auditable and workflow-complete research platform while keeping the existing Windows two-step installation and launch design intact.

## Improvements across all 23 modules

| # | Module | Step198 improvement |
|---:|---|---|
| 1 | BBB Permeability | Structure standardization, expanded descriptors, applicability-domain status, auditable rules, batch isolation and uncertainty labels. |
| 2 | Neuro-Target Curation | Normalized identifier matching, versioned registry output, evidence/category context and explicit unmatched handling. |
| 3 | Neurotransmitter Pathways | Multi-pathway output, traceable reference version and no forced mapping. |
| 4 | Ion Channel Classifier | Sequence QC, topology evidence, subtype motifs, confidence and partial-sequence warnings. |
| 5 | GPCR Classifier | Seven-TM architecture checks, family motifs, confidence and ambiguous-family handling. |
| 6 | CNS Disease Targets | Bidirectional disease/target lookup, evidence types, confidence and pagination-ready tables. |
| 7 | CNS Drug-Likeness | Interpretable weighted factors, BBB reuse, efflux/stability proxies and applicability warnings. |
| 8 | Off-Target Neurotoxicity | Binding-score normalization, primary/off-target context, expression weighting, coverage and source-row traceability. |
| 9 | Aggregation Risk | Residue-window track, high-risk regions, entropy/context features and reference-versus-variant delta analysis. |
| 10 | CNS Side Effects | Coverage-aware association estimates, excluded-target reporting, exposure weighting and bounded likelihoods. |
| 11 | Neuroinflammation | Microglial, complement, cytokine and inflammasome context with versioned curation. |
| 12 | Blood-CSF Barrier | Fail-closed provisional score, applicability domain and required-confirmation checklist. |
| 13 | Model Organisms | Organism/ortholog metadata, source labels and empty-result handling without false biological negatives. |
| 14 | CNS ADME & Transporters | P-gp/BCRP proxies, metabolic alerts, CYP liabilities, stability and developability warnings. |
| 15 | Brain Exposure & Neuro-PK | Oral/IV routes, repeated dosing, absorption, brain equilibration, Kp/Kp,uu, AUC and threshold exposure. |
| 16 | Receptor Occupancy | Unit normalization, Hill coefficients, invalid affinity isolation, engagement bands and selectivity margin. |
| 17 | Neurogenetics | VCF-like parsing, genome build, QUAL/FILTER QC, SNV/INDEL/SV recognition, frequency/inheritance/phenotype evidence. |
| 18 | Brain Expression Atlas | Regional and cell-type profiles, top-expression summaries and explicit snapshot boundary. |
| 19 | Neuro-Omics Biomarkers | Missingness filters, optional batch centering, Welch/Mann-Whitney tests, BH-FDR, bootstrap CIs and CV AUC. |
| 20 | EEG/MEG Analytics | Band-pass/notch filtering, artifact QC, PSD, relative bands, spectral entropy, correlation, coherence and candidate events. |
| 21 | Neuroimaging & Connectomics | Adapter-aware NIfTI/DICOM, 2D/3D/4D QC, threshold methods, components, volume, partial correlation and confound regression. |
| 22 | CNS Trial Intelligence | Column normalization, phase/status summaries, eligibility tags, attrition records, recency warnings and evidence gaps. |
| 23 | Precision Neurology | Imputation/scaling, cluster-count comparison, PCA, quality metrics, bootstrap stability, subgroup/outcome summaries and warnings. |

## Platform-level additions

1. Guided disease and translation workflows.
2. Cross-module consistency checker.
3. Resource/version/checksum/licence readiness registry.
4. Persistent local Neuro projects and portable project files.
5. Unified JSON, HTML and Markdown reports with inventory, provenance and consistency findings.
6. Optional specialist adapter status instead of silently claiming unsupported formats.
7. Persistent background queue support for heavy Neuro workloads.
8. Expanded qualification suite with module, workflow, file-loader, project, report and background-worker tests.

## Qualification result

- Neuro/CNS module catalogue: **23/23 present**
- Neuro/CNS workspaces: **5/5 present**
- Streamlit page boot: **passed**
- Focused Step197 + Step198 test suite: **37 passed**
- Python compilation: **passed**
- Controlled clinical/scientific release: **not eligible**

## Remaining external requirements

- Approved provider snapshots and licence review for B3DB-style BBB data, UniProt/GO target records, GPCR/domain resources, disease associations, side-effect data, brain expression atlases, variant evidence and model-organism databases.
- Independent benchmark datasets and specialist review for aggregation, side-effect, blood-CSF, imaging, neural-signal and patient-stratification outputs.
- Native Windows CPU/GPU installation qualification on the user's target machine.
