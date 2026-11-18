# Step 127 — Bioinformatics, Discovery & Lab Analytics Scientific Depth

## Release

- Product version: **12.8.0**
- Core modules covered: **33/33**
- Bioinformatics: **17**
- Discovery: **9**
- Lab Analytics: **7**
- Registered external scientific tools: **86**
- New command center: `pages/172_Scientific_Depth_Command_Center.py`

## What Step 127 adds

### Module-specific scientific pipelines

Every core module now has a machine-readable specification covering:

- accepted and native scientific formats;
- built-in, adapter and external-validation stages;
- tool and Python-package requirements;
- reference database requirements;
- statistical safeguards;
- evidence boundaries;
- release blockers;
- module-specific feature expansion recommendations.

Thirty-one non-locked module pages receive a full scientific-depth panel. Two source-locked core pages—DTI Predictor and Lab Instrument Import Center—remain byte-identical and receive shared readiness through the global sidebar and command center.

### Execution tiers

- **Tier A:** executable pipeline is configured for detected tools/references.
- **Tier B:** adapter-ready, but one or more external requirements remain.
- **Tier C:** built-in or heuristic workflow only.

The tier is calculated from real local availability. Missing binaries, packages, references or validation evidence are shown as blockers rather than silently reported as available.

### Native-format readiness

The common inspector classifies and routes formats including FASTA/FASTQ, VCF/BCF, BAM/CRAM, GFF/GTF/BED, GFA, PDB/mmCIF, h5ad/Zarr/MTX, FCS, mzML/mzXML, RDML, SDF/MOL, CSV/TSV/XLSX and Parquet. Formats requiring specialist libraries or binaries remain labelled adapter-dependent.

### Protected execution plans

Bounded, shell-free execution plans were added for supported external tools. Plans validate executable allow-lists, input paths, output directories and resource limits before execution. The expanded tool catalogue includes Dorado, InterProScan, SignalP 6, DeepTMHMM, Panaroo, sourmash, Nextclade, Pangolin, Cutadapt and Mosdepth.

### Reference database contracts

Reference manifests now require:

- provider/release version;
- local path;
- SHA-256 checksum;
- licence acknowledgement;
- genome build, organism or lineage context where applicable.

A reference cannot be marked ready solely because a directory exists.

### Statistical and scientific safeguards

Shared safeguards include:

- missingness, duplicate and constant-feature audits;
- group and replicate-size checks;
- robust outlier flags;
- Benjamini–Hochberg FDR;
- effect-size support;
- design-matrix rank checks;
- FASTQ pair auditing;
- variant normalization;
- qPCR role filtering;
- safe calibration inverse with no silent out-of-range extrapolation;
- batch-wise bioprocess time validation;
- duplicate column-mapping rejection.

### Persistent provenance

The shared run registry records input fingerprints, parameters, execution tier, tool/reference readiness, stage outcomes and output evidence. Run comparison is available through the Step 127 integration layer. The database is created in user workspace at runtime and is not shipped with fabricated run history.

## Domain coverage

### Bioinformatics

Sequence analysis/comparison, pangenome graphs, long-read assembly, CRISPR screens, outbreak genomics, rare-disease interpretation, batch sequence processing, FASTQ QC, variant annotation, transcriptomics, protein annotation/proteomics, omics integration, phylogeny, comparative pathogen genomics, single cell and cancer genomics.

### Discovery

SMILES analysis, DTI features, source-locked DTI Predictor readiness, protein design, ChEMBL datasets, structural bioinformatics, ADMET, pathway/network analysis and Discovery Command Center.

### Lab Analytics

Synthetic biology, source-locked instrument import readiness, Primer/CRISPR/Codon Studio, wet-lab assays, microbiology/metagenomics, Lab Analytics Command Center and professional metagenomics pipeline.

## Validation completed

- Step 127 verifier: **14/14 checks passed**
- Non-overlapping completed pytest regressions: **375 passed, 0 failures**
- Representative Streamlit runtime pages: **7/7 passed with no reported runtime exception**
- Python syntax compilation: **899/899 files passed**
- Engineering quality gates: **4/4 passed**
- SQLite integrity: **36/36 databases healthy**
- Database rows checked: **108,425**
- Locked modules: **5/5 byte-identical**

The monolithic repository-wide test run did not complete inside the available execution window. Two version/catalogue compatibility failures found during partial execution were fixed and their focused suites were rerun successfully. This report therefore does not claim an uncompleted full-suite pass.

## Honest external boundary

Step 127 does not bundle or fabricate licensed databases, proprietary executables, large model weights, clinical cohorts, wet-lab results, regulatory approval or independent validation. Module panels distinguish executable local capability from adapter readiness and external validation requirements. Installing a tool or generating a command plan does not by itself establish scientific validity.

## Installation

Extract all four Step 127 ZIP files into the same destination and run:

```bat
VERIFY_STEP127_WINDOWS.bat
INSTALL_WINDOWS.bat
RUN_APP_SMOOTH_WINDOWS.bat
```

Optional scientific packages can be prepared with:

```bat
INSTALL_STEP127_SCIENTIFIC_EXTRAS_WINDOWS.bat
```
