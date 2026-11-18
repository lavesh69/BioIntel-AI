# Step 47 — Professional Biotechnology Projects

## Scope

Step 47 adds five complete applied biotechnology and bioinformatics projects to the BioIntel AI workspace. The implementation extends the application from 78 to 84 registered routes while preserving the Step 46 professional UI shell and existing scientific boundaries.

## New project center

- `Biotechnology Project Center`
- Portfolio status for every new project
- Project objectives, four-stage workflows and deliverables
- Direct launch links to each project workbench
- Research-use and release-boundary controls

## Project 1 — Protein Interaction ML

**Module:** `Protein Interaction ML`  
**Portfolio code:** `BIO-PPI-ML`

Implemented capabilities:

- Labelled protein-pair CSV validation
- Protein-sequence alphabet validation and duplicate-pair control
- Sequence-derived pair features covering composition, length, charge, hydrophobicity, entropy and k-mer similarity
- Logistic-regression, random-forest and calibrated-random-forest workflows
- Cross-validated algorithm comparison
- Held-out ROC AUC, accuracy, balanced accuracy, precision, recall, F1 and confusion matrix
- Feature-importance interpretation
- Candidate-pair probability scoring with confidence bands and model fingerprints
- CSV export of features and predictions

## Project 2 — Comparative Pathogen Genomics

**Module:** `Comparative Pathogen Genomics`  
**Portfolio code:** `BIO-CG-PATH`

Implemented capabilities:

- Query and reference FASTA ingestion
- DNA alphabet and unique-identifier validation
- Canonical k-mer genome fingerprints
- Bidirectional containment, Jaccard similarity and GC-composition agreement
- Ranked reference screening
- Pairwise genome-distance heatmap
- Genome length, GC, ambiguous-base and k-mer-complexity profiles
- Editable marker panel with exact forward/reverse-complement screening
- CSV exports for rankings, profiles and marker results

## Project 3 — Single-Cell Heterogeneity

**Module:** `Single-Cell Heterogeneity`  
**Portfolio code:** `BIO-SCRNA`

Implemented capabilities:

- Genes-by-cells count-matrix validation
- Cell QC using total counts, detected genes, mitochondrial fraction and ribosomal fraction
- Configurable filtering thresholds
- Library-size normalization and log1p transformation
- Highly-variable-gene selection
- Standardization and PCA
- K-means clustering with deterministic random seed
- Silhouette-based cluster quality metric
- Cluster marker screening using fold change, prevalence and marker score
- Cell embedding, cluster-size, QC and variable-gene visualizations
- CSV exports for QC, cluster assignments and marker genes

## Project 4 — Cancer Genomics

**Module:** `Cancer Genomics`  
**Portfolio code:** `BIO-CANCER-GX`

Implemented capabilities:

- Somatic-variant table validation
- VAF, depth, filter and duplicate control
- Transparent consequence-impact annotation
- Research-only cancer-gene and pathway reference mapping
- Research-priority score and tiering
- Sample-level mutation burden and research TMB screen
- Gene and pathway burden summaries
- VAF-versus-depth landscape
- Exportable prioritized variants, sample summaries and pathway tables
- Explicit non-diagnostic and non-treatment boundary

## Project 5 — Metagenomics Pipeline

**Module:** `Metagenomics Pipeline`  
**Portfolio code:** `BIO-META-PIPE`

Implemented capabilities:

- Taxon-abundance and sample-metadata validation
- Editable group design
- Sample-depth, observed-taxa, dominance and zero-fraction QC
- Prevalence and total-count filtering
- Relative-abundance normalization
- Shannon, Simpson and Pielou diversity
- Bray–Curtis distance matrix
- Principal coordinates analysis
- Group-aware effect-size differential-taxa screening
- Composition, alpha-diversity, PCoA and effect-screen visualizations
- CSV exports for normalized abundance, diversity and differential taxa

## Application integration

- Home page project lane
- BioIntel Studio project lane
- Central project launcher
- Global search keywords and category placement
- API UI catalogue integration
- Portfolio Registry integration
- Knowledge Warehouse module/project indexing
- Research Assets indexing
- Existing Step 46 styling, accessibility and responsive shell retained

## Scientific boundary

All bundled project datasets are deterministic demonstration/reference assets. The software does not claim clinical diagnosis, confirmed pathogen identity, experimentally proven PPI, clinically actionable cancer interpretation, publication-grade cell annotation or validated differential abundance. Real data, independent validation, appropriate specialist methods and qualified review remain required.
