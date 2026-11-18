# BioIntel AI Step 114 — Scientific Depth & Optimization Report

## Release

- Product version: **11.4.0**
- Release name: **Scientific Depth & Optimization**
- New central workspace: `pages/168_Scientific_Depth_Optimization_Center.py`
- Eligible scientific/platform depth profiles: **64**
- External-engine readiness adapters: **53**
- Protected shell-free execution plans: **21**

## Explicit exclusions

The user requested that the following modules must not be upgraded in this release:

- DTI Predictor
- DTI Validation Evidence Center
- Lab Instrument Import Center
- LIMS, ELN & Sample Chain of Custody Hub
- Instrument Integration Hub

All five page sources remain byte-identical to the Step 113 baseline. Their SHA-256 hashes are enforced by an automated regression test and the Step 114 verifier.

## Scientific depth layer

A reusable scientific-depth layer was added under `src/biointel/scientific_depth/`. It provides:

- module-specific external-engine readiness requirements;
- reference-asset and database requirements;
- supported native scientific-format expectations;
- validation gates and scientific limitations;
- bounded, module-specific DataFrame quality assessment;
- Benjamini–Hochberg FDR support;
- robust outlier and missingness checks;
- sequence-liability screening;
- scientific boundary and optimization recommendations;
- downloadable readiness and assessment outputs.

Expansion and next-generation module renderers consume the shared layer without duplicating code. Selected older scientific and platform pages also expose the same readiness/validation panel.

## Expanded external-engine readiness

The native engine registry now contains **53** adapters. Step 114 adds readiness for areas such as:

- variant annotation and phasing: VEP, WhatsHap;
- population genetics: REGENIE, SAIGE;
- structural variants and repeat expansion: Sniffles2, ExpansionHunter;
- long-read assembly and validation: Flye, hifiasm, BUSCO, Merqury;
- pangenomics: minigraph, vg, odgi, GraphAligner;
- antibody and immunoinformatics: ANARCI, IgBLAST, NetMHCpan, NetMHCIIpan;
- single-cell trajectory: Scanpy, scVelo, CellRank;
- proteomics and mass spectrometry: Comet, MS-GF+, msconvert;
- genomics and microbiology utilities: BEDTools, Bowtie 2, BLASTN, ABRicate;
- approved local language-model inference: llama.cpp.

Detection never silently runs an external tool. Availability, path, version, capabilities, GPU needs and reference-database requirements are shown separately from built-in heuristic analysis.

## Protected execution plans

Nine additional plan templates were added, bringing the total to **21**:

- VEP annotation;
- Sniffles structural-variant calling;
- ExpansionHunter repeat-expansion calling;
- Flye assembly;
- hifiasm assembly;
- BUSCO assembly assessment;
- minigraph graph construction;
- ANARCI numbering;
- msconvert mzML conversion.

Plans use argument arrays rather than shell command strings, validate that input/output paths remain inside the protected workspace, expose expected outputs and resources, and do not execute automatically on page load.

## Module-specific depth and quality checks

Eligible modules receive domain-aware checks rather than a single generic score. Examples include:

- metabolomics: blank ratio, pooled-QC variability and identification confidence;
- protein and antibody design: sequence liabilities, humanness/developability requirements and structural readiness;
- population genetics: MAF, missingness and FDR summaries;
- rare-disease/family genetics: genotype-pattern and de-novo candidate review;
- single-cell: cell/gene metadata, sparse/backed-data requirements and replicate-aware validation;
- structural variants: event class, breakpoint and evidence requirements;
- clinical biomarkers: cohort size, missingness, endpoint and external-validation requirements;
- causal analysis: instrument strength, confounding and sensitivity requirements;
- explainable AI: calibration, subgroup, OOD and explanation-stability requirements;
- bioprocess: batch-specific time order, units and mass-balance requirements;
- genome editing: guide/off-target/reference requirements;
- privacy engineering: k-anonymity, l-diversity, t-closeness and attack-testing requirements.

These checks support review and planning. They do not replace specialist tools, current reference data, wet-lab confirmation, clinical review or regulatory validation.

## Stability and UI fixes

- Updated visible Windows launchers from stale Step 104 branding to Step 114.
- Updated the installer log, marker and self-test names to Step 114.
- Replaced stale Step 104 wording inside current report/model/reference UI paths.
- Updated README and release surfaces to version 11.4.0.
- Added a central searchable readiness matrix rather than duplicating large status blocks across pages.
- Preserved lazy rendering and bounded previews to avoid page-load execution of heavy tools.
- Kept the upload transport at 1 GB with a 100 MB interactive-processing boundary.

## Verification evidence

- Selected Step 100–114 regression tests: **114 passed**
- Step 114 focused tests: **10 passed**
- Python files compiled: **825**, errors: **0**
- Static UI checks: **170/170 passed**, warnings: **0**
- Targeted Streamlit pages: **20/20 passed**, captured exceptions: **0**
- Build-runtime self-test: **7/7 passed**
- SQLite files checked: **36/36 healthy**
- SQLite rows checked: **108,077**
- Excluded page hashes: **5/5 preserved**
- Step 114 release verifier: **9/9 passed**

The build-runtime self-test used the supported source-verification range of Python 3.11–3.13. The Windows installer remains intentionally strict on Python 3.11 x64 for the bundled offline wheelhouse.

## Scientific boundary

Step 114 improves readiness, QC, evidence disclosure and safe integration architecture. It does not bundle every third-party binary, licensed database, model weight, provider release or laboratory result. An absent engine or database remains visibly unavailable, and computational findings are not labelled experimentally or clinically validated without corresponding evidence.
