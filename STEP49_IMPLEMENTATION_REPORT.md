# Step 49 — Deep Professional Biotechnology Platform

## Objective

Step 49 moves the five biotechnology projects beyond equal-depth feature parity into a shared professional research-platform standard. The focus is not adding more project names or cosmetic charts. It adds project-specific scientific assurance, uncertainty/stability diagnostics, reproducible reporting, persistent run operations, method cards and API-visible project controls.

## Shared professional architecture

All five workbenches now implement the following common contract:

- Multi-stage validated input and deterministic demonstration modes
- Domain-specific primary analysis pipeline
- Domain-specific deep validation and assurance layer
- Structured quality gates with `pass`, `review` and `block` semantics
- Explicit evidence, score and recommendation for each gate
- Schema-v2 run manifest with environment and table profiles
- SHA-256 lineage for every input and output table
- Portable HTML research report
- JSON method/model card covering intended use, out-of-scope use, methods, metrics, validation and limitations
- Verified ZIP bundle containing inputs, outputs, report, method card, methods and quality gates
- Local SQLite run registry with historical comparison
- FastAPI project catalogue and run-history endpoints
- Clear research-only, non-diagnostic and non-clinical boundaries

## Project 1 — Protein–Protein Interaction ML

### Existing professional workflow retained

- Pair schema and amino-acid validation
- Sequence-derived feature engineering
- Logistic regression, random forest and calibrated random forest
- Cross-validation, held-out evaluation, ROC/PR curves and calibration
- Threshold analysis, feature importance and candidate network

### Step 49 deep development

- Protein-disjoint cold-start validation
- Cold-one and cold-both evaluation labels
- Bootstrap confidence intervals for ROC AUC, balanced accuracy, F1, precision and recall
- Candidate out-of-domain audit using standardized nearest-training distance
- Feature-range extrapolation detection
- Decision-curve net-benefit screening
- Network topology summary covering density, degree and isolated nodes
- Five structured gates: dataset integrity, pair performance, cold-start validation, calibration and candidate domain coverage
- Professional method/model card and run registration

## Project 2 — Comparative Pathogen Genomics

### Existing professional workflow retained

- FASTA validation and composition QC
- Canonical k-mer ranking and best-hit margins
- Distance matrix and UPGMA screening tree
- Pairwise substitutions/indels
- Mismatch-tolerant marker screening

### Step 49 deep development

- Bootstrap reference-assignment stability through k-mer subsampling
- Window-level reference assignment for contamination/chimerism review
- Window assignment margins and low-confidence region identification
- Sliding-window GC percentage and GC-skew profiles
- Six-frame open-reading-frame screening
- Core, shell and unique pangenome k-mer summaries
- Five structured gates: sequence quality, reference coverage, bootstrap support, window consistency and marker-context boundary
- Professional method card and run registration

## Project 3 — Single-Cell RNA-seq Heterogeneity

### Existing professional workflow retained

- Cell QC and heuristic doublet screening
- Normalization, HVG selection and PCA
- Deterministic clustering and multi-seed stability
- Marker discovery and provisional cell annotation
- Cluster comparison and expression heatmaps

### Step 49 deep development

- Batch/sample/condition variance-explained audit across principal components
- Per-cluster silhouette quality and negative-silhouette review
- Davies–Bouldin cluster quality metric
- Sample-by-cluster pseudobulk expression matrix
- Marker specificity margin and specificity ratio
- Geometry-based exploratory pseudotime and ordered cluster edges
- Gene dropout, zero-fraction and detected-cell profile
- Five structured gates: retention, cluster stability, separation, batch effect and annotation evidence
- Professional method card and run registration

## Project 4 — Cancer Genomics

### Existing professional workflow retained

- Variant validation and QC
- Transparent research-priority scoring
- Mutation burden/TMB screening
- SNV spectrum, pathway summaries and oncoprint
- Co-occurrence, clonality and threshold sensitivity

### Step 49 deep development

- Wilson 95% confidence intervals for variant allele fraction
- Recurrent genomic-hotspot screen across samples
- Sample mutation-profile Jaccard similarity matrix
- Gene co-occurrence/mutual-exclusion screening z-scores
- Sample technical-quality tiers
- Six-class substitution-exposure profile with explicit non-COSMIC boundary
- Five structured gates: variant pass rate, sample quality, VAF precision, recurrence evidence and clinical boundary
- Professional method card and run registration

## Project 5 — Metagenomics Pipeline

### Existing professional workflow retained

- Abundance-table and metadata validation
- Prevalence/count filtering and relative abundance
- Alpha diversity, Bray–Curtis and Aitchison geometry
- PCoA, PERMANOVA, rarefaction and core microbiome
- Differential-taxa screening

### Step 49 deep development

- Permutation differential-abundance testing
- Benjamini–Hochberg false-discovery-rate correction
- Beta-dispersion diagnostics by group
- Indicator-taxon scoring by abundance and prevalence
- Prevalence-filter sensitivity curve
- Leave-one-sample-out PCoA geometry stability
- Five structured gates: sample depth, filtering robustness, community structure, dispersion and ordination stability
- Professional method card and run registration

## Reporting and reproducibility upgrade

`src/biointel/projects/reporting.py` now creates a schema-v2 research package with:

- `manifest.json`
- `report.html`
- `quality_gates.csv`
- `methods.json`
- `model_card.json` when supplied
- `README.txt`
- all input CSV files
- all output CSV files

Every generated ZIP is reopened and integrity-tested before it is returned to the user.

The schema-v2 manifest adds:

- Python implementation and platform
- executable label
- pandas and NumPy versions
- per-table row/column/missing/duplicate/numeric-column profiles
- SHA-256 hashes for each input and output

## Run registry

A new local SQLite operations layer is implemented in `src/biointel/projects/run_registry.py`.

It supports:

- checksum-bound run registration
- project code and name
- qualified/blocked status
- quality score
- input/output row counts
- parameters and metrics JSON
- run event history
- project-specific historical comparison

The registry is created at runtime and is intentionally not pre-populated with fabricated operating history.

## Application and API integration

- Biotechnology Project Center upgraded to Step 49
- Central run-history and comparison interface added
- Home and BioIntel Studio copy updated
- Project catalogue workflows and deliverables expanded
- Portfolio notes updated to Step 49 maturity
- New API endpoints:
  - `GET /v1/biotechnology/projects`
  - `GET /v1/biotechnology/runs`
- Existing 84-page application catalogue preserved

## Scientific boundary

Step 49 improves implementation depth, internal validation and research discipline. It does not manufacture experimental PPI evidence, validated pathogen identification, publication-grade cell annotations, clinical cancer interpretation or causal microbiome findings. Real study design, suitable controls, external validation, accepted domain methods and qualified review remain mandatory.
