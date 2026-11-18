# BioIntel P0 + P1 + P2 Scientific Integration Runtime v2

## Scope completed

This release upgrades the earlier readiness-only profile layer into an executable BioIntel scientific integration runtime. It registers 20 integration adapters, exposes 41 non-diagnostic operations, wires them to 29 scientifically relevant module pages, and keeps heavy optional dependencies isolated from the core desktop environment.

### Priority coverage

- P0: 7 core integrations
- P1: 10 advanced integrations
- P2: 3 model and pipeline integrations
- Total: 20 adapters and 61 registered operations including diagnostics

## Runtime architecture

- Core operations use the existing BioIntel environment only where dependencies are already qualified.
- Heavy P0/P1/P2 Python packages use separate managed environments under `%LOCALAPPDATA%\BioIntelAI\ScientificRuntimes`.
- Docking uses a dedicated native worker.
- Taxonomy, workflow, protein-design and reproducible-pipeline workers use an isolated WSL layer.
- Every execution uses argument-vector invocation, timeout protection, protected stdout/stderr logs, a run manifest, and SHA-256 artifact records.
- Missing optional runtimes return `Setup required` or a controlled failure instead of stopping the core app.
- Model weights, reference databases, gene sets and downloaded pipelines remain separately qualification-gated.

## Integration matrix

| Priority | BioIntel public integration | Relevant BioIntel modules | Runtime | Operations |
|---|---|---|---|---:|
| P0 | BioIntel Sequence Intelligence Engine | Sequence Analyzer, Sequence Comparison, Comparative Genomics | In-process Python | 2 |
| P0 | BioIntel Variant File Engine | Cancer Genomics, Variant Workbench, NGS QC | Isolated Python adapter | 2 |
| P0 | BioIntel Biological Statistics Engine | Metagenomics Pipeline, Microbiome Analytics, Phylogeny | Isolated Python adapter | 2 |
| P0 | BioIntel Single-Cell Analysis Engine | Single-Cell Heterogeneity, Cell Atlas Mapping, Perturb-seq Analytics | Isolated Python adapter | 2 |
| P1 | BioIntel Single-Cell AI Engine | Single-Cell Heterogeneity, Cell Atlas Mapping, Multi-Omics Biomarker Discovery | GPU/CPU model adapter | 2 |
| P1 | BioIntel Multi-Omics Integration Engine | Multi-Omics Biomarker Discovery, Cell Atlas Mapping, Knowledge Integration | Isolated Python adapter | 2 |
| P1 | BioIntel Spatial Omics Engine | Spatial Omics, Digital Pathology, Single-Cell Heterogeneity | Isolated Python adapter | 2 |
| P0 | BioIntel Molecular Intelligence Engine | Drug SMILES Analyzer, ADMET Drug Discovery, Discovery Command Center | In-process Python | 2 |
| P1 | BioIntel Molecular AI Engine | DTI Predictor, Molecular Property Modelling, Discovery Command Center | Isolated Python adapter | 2 |
| P1 | BioIntel Molecular Docking Engine | Molecular Docking Lab, Discovery Command Center, Protein-Ligand Co-Design | Audited CLI worker | 2 |
| P1 | BioIntel Molecular Simulation Engine | Molecular Dynamics Lab, Protein-Ligand Co-Design, Structural Bioinformatics | GPU/CPU Python worker | 2 |
| P1 | BioIntel Molecular Trajectory Engine | Molecular Dynamics Lab, Structural Bioinformatics, Protein-Ligand Co-Design | Isolated Python adapter | 2 |
| P2 | BioIntel Protein Language Engine | AI Protein Design Lab, Protein Annotation, Mutation Engineering | GPU/CPU model adapter | 2 |
| P2 | BioIntel Structure-Conditioned Protein Design Engine | AI Protein Design Lab, Mutation Engineering, Enzyme Design | Audited model worker | 2 |
| P0 | BioIntel Pathway Intelligence Engine | Pathway & Network Analysis, Multi-Omics Biomarker Discovery, Cancer Genomics | Isolated Python adapter | 2 |
| P1 | BioIntel Taxonomic Classification Engine | Metagenomics Pipeline, Pathogen Outbreak Command Center, One Health Surveillance | Audited WSL/CLI worker | 2 |
| P1 | BioIntel Medical Imaging AI Engine | Medical Imaging, Digital Pathology, Spatial Biology | GPU/CPU model adapter | 2 |
| P0 | BioIntel Bioimaging Workspace | Microscopy Analysis, Spatial Biology, Digital Pathology | Desktop companion adapter | 2 |
| P1 | BioIntel Workflow Automation Engine | Visual Workflow Builder, Pipeline Marketplace, Background Job Engine | Audited WSL/CLI worker | 2 |
| P2 | BioIntel Reproducible Pipeline Engine | Visual Workflow Builder, Pipeline Marketplace, RNA-seq and Genomics Workflows | Audited WSL/CLI worker | 3 |

## Product wiring

- `pages/356_BioIntel_Scientific_Integration_Center.py` now provides readiness filters, technical diagnostics and an audited JSON operation console.
- 29 relevant scientific pages include the reusable BioIntel integration panel.
- Public exports include only BioIntel identities and qualification state.
- Internal executable/package names are kept outside normal product surfaces.

## Setup

Run `BIOINTEL_ENGINE_SETUP.bat` and choose P0, P1, P2 or All. P1 installs only the focused docking, taxonomy and workflow workers. P2 installs only the focused protein-intelligence and reproducible-pipeline workers. The legacy full specialist-tool suite is not invoked by this setup.

## Identity and legal boundary

Normal UI, selectors, tables, reports and exports use BioIntel names. Required upstream identities and licences remain in `docs/legal/THIRD_PARTY_NOTICES.md` and installed-package metadata. Those notices must not be removed from redistributed builds.

## Verification completed in the build environment

- Python compilation of integration runtime, worker, UI and all registered pages: passed.
- Focused integration, branding, runtime and current Windows-startup regression suite: 73 passed.
- P0 core sequence and molecular operations executed successfully with audited manifests.
- Full native Windows, WSL2, GPU, model-weight and database execution could not be performed in the Linux packaging environment and must be verified on the target Windows machine.

## Scientific boundary

Technical execution readiness is not independent scientific validation, wet-lab validation, clinical validation or regulatory clearance. Each model, reference database, cohort and pipeline requires use-case-specific qualification.
