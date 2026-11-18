# BioIntel AI Step 103 — Advanced Scientific Depth

## Release summary

- Product version: **10.3.0**
- Upgraded workspaces: **21**
- Page range: **112–132**
- Unified hub: **Page 133**
- Evidence schema: **biointel.scientific_expansion.v2**

## What changed

Step 103 upgrades the Step 102 expansion from table-only prioritisation to a deeper local scientific-analysis layer. It adds direct module-relevant file conversion, richer quality control, effect sizes, replicate-aware statistics, multiple-testing correction, auxiliary result tables and explicit separation between built-in methods, transparent proxies and optional specialist software.

### Direct scientific-file conversion

- FASTA/FA/FNA/FAA/FAS
- VCF
- BED/narrowPeak/broadPeak
- H5AD and Matrix Market MTX
- TIFF/OME-compatible raster imports, PNG and JPEG
- PDB/mmCIF and SDF/MOL/MOL2
- mzML/mzXML metadata
- CSV/TSV/TXT/JSON/XLSX/XLS

### Advanced analyses added

- Epigenomics: region parsing, replicate balance, Welch testing, Cohen's d, methylation delta and FDR.
- Metabolomics: log transformation, blank/CV/missingness QC, group statistics and FDR.
- Immunoinformatics: sequence-derived peptide generation, physicochemical flags, promiscuity summary and construct planning.
- Antibody engineering: sequence-liability checks and Pareto-frontier selection.
- Docking/dynamics: ligand descriptor import, pose quality flags and consensus summaries.
- Pharmacogenomics: VCF import, variant normalisation, evidence-curation status and hard clinical-action blocking.
- Spatial omics: H5AD spatial import, region summaries and Moran's I.
- Single-cell: H5AD/MTX import, transparent PCA-rank pseudotime fallback, trajectory slopes and communication networks.
- Bioimage: direct image segmentation, object measurements, condition statistics and image QC.
- Biostatistics: allocation planning, dropout-adjusted sizes, precision/efficiency summaries and reproducible blocked randomisation schedules.
- Clinical biomarkers: ROC/AUC, candidate cut-off and Kaplan–Meier outputs.
- Genome editing: FASTA guide discovery, GC/complexity/homopolymer/poly-T checks.
- Proteogenomics: FASTA peptide generation, manufacturability and multi-layer evidence checks.
- Bioprocess: growth/productivity slope proxies, terminal yield and batch performance.
- LIMS/ELN: orphan/self-parent detection, expiry classification, lineage integrity, a persistent local SQLite registry and checksum audit log.
- Causal modelling: confidence intervals, weak-instrument flags and IVW aggregation.
- Model assurance: ROC, PR, Brier score, ECE, confusion matrix and subgroup gaps.
- Multi-omics: PCA before/after harmonisation and batch-dispersion diagnostics.
- Glycomics: site-resolved differential statistics and FDR.
- One Health: weekly rolling outbreak signals and cross-host summaries.
- Synthetic/privacy: k-anonymity, l-diversity, t-closeness and utility preservation.

## Responsible-use boundary

This release does not falsely label heuristic sequence scores, molecular descriptors or local statistical summaries as validated specialist-tool outputs. MACS2, Vina, GROMACS, Cellpose, NetMHC, clinical pharmacogenomic guidelines, reference databases and other specialist assets remain optional external dependencies and require independent validation.

## Qualification completed

- Python compilation: passed
- Advanced demo analysis matrix: 21/21 passed
- Scientific import matrix: 8/8 passed
- Streamlit pages 112–133: 22/22 passed
- Targeted release and regression tests: 27/27 passed
