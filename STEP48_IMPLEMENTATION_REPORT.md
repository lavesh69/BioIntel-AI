# Step 48 — Equal-Depth Professional Biotechnology Workbenches

## Objective

Step 48 upgrades all five applied biotechnology projects to the same professional maturity tier as the mature Drug–Target Interaction Predictor and DNA/Protein Sequence Analyzer. The upgrade focuses on complete workflow depth rather than adding more project names or superficial cards.

## Shared professional architecture

Every project now includes:

- Clearly documented input contracts
- Deterministic demo mode and user-upload mode
- Schema, range and biological-alphabet validation where applicable
- Multi-stage configuration forms
- Advanced quality-control evidence
- Interactive visual analytics and researcher-readable tables
- Explicit scientific and clinical boundaries
- Analysis-ready CSV exports
- JSON run manifest with SHA-256 input/output digests
- Complete downloadable ZIP containing inputs, outputs, manifest and boundary notes
- Stable session-state result persistence
- Production-style workflow status and error handling

## Project 1 — Protein Interaction ML

**Module:** `pages/78_Protein_Interaction_ML.py`  
**Backend:** `src/biointel/projects/ppi.py`  
**Code:** `BIO-PPI-ML`

Added capabilities:

- Pair dataset QC for duplicate unordered pairs, self-interactions and identifier/sequence conflicts
- Class-balance review and unique-protein accounting
- Logistic regression, random forest and calibrated random forest
- Cross-validated algorithm benchmark
- Held-out ROC and precision–recall curves
- Confusion matrix and per-pair error table
- Decision-threshold precision/recall/specificity/F1 trade-off analysis
- Probability-calibration table and visual screen
- Global feature importance and engineered feature matrix
- Explicit train/test protein-overlap leakage audit
- Candidate interaction scoring and confidence bands
- Thresholded protein-interaction network with node degree summaries
- Model/run manifest and complete project bundle

## Project 2 — Comparative Pathogen Genomics

**Module:** `pages/79_Comparative_Pathogen_Genomics.py`  
**Backend:** `src/biointel/projects/comparative_genomics.py`  
**Code:** `BIO-CG-PATH`

Added capabilities:

- Demo, FASTA upload and FASTA paste modes for both query and reference panels
- Genome QC covering length, GC, ambiguity, k-mer complexity and low-complexity flags
- Canonical k-mer Jaccard and bidirectional-containment ranking
- Best-hit score, second-best score and assignment-margin review
- Combined query/reference distance matrix
- Deterministic UPGMA Newick screening tree
- Best-reference positional substitution/indel screen
- Transition/transversion classification for substitutions
- Mismatch-tolerant marker screening with position and strand
- Query k-mer composition analysis
- Complete ranked, QC, marker, variant and tree exports

## Project 3 — Single-Cell Heterogeneity

**Module:** `pages/80_Single_Cell_Heterogeneity.py`  
**Backend:** `src/biointel/projects/single_cell.py`  
**Code:** `BIO-SCRNA`

Added capabilities:

- Configurable demo matrix and CSV/TSV upload
- Editable cell metadata for sample, batch and condition overlays
- Cell QC with counts, detected genes, mitochondrial and ribosomal fractions
- Transparent robust-z doublet screening
- Library-size normalization, log transform and highly-variable-gene selection
- PCA and deterministic clustering
- Two- and three-dimensional embedding views
- Multi-seed adjusted-Rand cluster-stability analysis
- Cluster marker discovery
- Editable marker-panel scoring and provisional cell-type annotation
- Cluster-to-cluster differential-expression screening
- Cluster-average marker-expression heatmap
- Optional filtered/raw matrix inclusion in reproducibility bundle

## Project 4 — Cancer Genomics

**Module:** `pages/81_Cancer_Genomics.py`  
**Backend:** `src/biointel/projects/cancer_genomics.py`  
**Code:** `BIO-CANCER-GX`

Added capabilities:

- Configurable demo cohort and CSV/TSV upload
- Editable sample metadata for cohort, tumour type and batch
- Variant and per-sample QC evidence
- Transparent impact/gene/VAF/depth research-priority scoring
- Depth/VAF threshold-sensitivity surface
- Sample burden and research TMB screen
- Six-class SNV substitution spectrum
- Gene/pathway burden summaries
- Binary gene-by-sample oncoprint
- Gene co-occurrence matrix
- VAF-derived exploratory clonality bands
- Explicit non-clinical/non-treatment boundary
- Full annotated-variant and project-bundle exports

## Project 5 — Metagenomics Pipeline

**Module:** `pages/82_Metagenomics_Pipeline.py`  
**Backend:** `src/biointel/projects/metagenomics_pipeline.py`  
**Code:** `BIO-META-PIPE`

Added capabilities:

- Configurable demo abundance table and CSV/TSV upload
- Editable sample metadata and group design
- Sample quality flags for low depth, dominance and sparsity
- Prevalence/total-count filtering
- Relative-abundance normalization and taxon prevalence
- Top-taxon composition views
- Shannon, Simpson, observed richness and Pielou evenness
- Bray–Curtis and Aitchison distance matrices
- PCoA community embedding
- Permutation-based PERMANOVA screening for both geometries
- Rarefaction screening curves
- Core-microbiome prevalence/abundance screen
- Group-aware differential-taxa screen
- Complete matrix, inference and bundle exports

## Application integration

- Existing 84-route application catalogue preserved
- Home project copy updated to identify equal-depth workbenches
- BioIntel Studio project lane updated
- Biotechnology Project Center upgraded to Step 48 positioning
- Project catalogue workflows and deliverables expanded
- Five active/high-priority portfolio records updated with Step 48 capability notes
- Five deterministic project-upgrade events recorded in the project registry
- Existing Step 46 design system, accessibility and responsive shell retained

## Scientific boundary

The added algorithms and visualizations are implementation and research-screening tools. They do not create experimental PPI evidence, validated pathogen identification, publication-grade cell annotation, clinical cancer interpretation or definitive microbiome inference. Genuine study data, suitable controls, external validation, specialist methods and qualified review remain mandatory.
