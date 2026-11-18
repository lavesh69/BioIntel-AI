# BioIntel AI Step 138 — Bioinformatics Deep Excellence

## Scope

- **15 specialist bioinformatics workflows** deepened.
- **7 existing embedded workspaces** upgraded without duplicate navigation pages.
- **8 Step 137 specialist pages** preserved and upgraded.
- **12 signature scientific visuals per module** — **180 visual assignments**.
- Guided and Expert modes, module-specific QC, bounded execution, provenance, evidence bundles and cross-module handoffs are available across the suite.

## Major implementation upgrades

- Module-specific scientific contracts: organisms, genome builds, analysis profiles, parameters, QC checks, specialist engines, reference assets and review roles.
- Deep post-processing for GWAS/PRS, epigenomics, pharmacogenomics, structural variants, splicing, immune repertoire, multiome, proteogenomics, regulatory networks, federated discovery, viral evolution, annotation, circular DNA, eDNA and comparative regulatory genomics.
- Explicit Run Analysis action prevents expensive calculations from firing on every widget change.
- Background reproducibility jobs use staged inputs with SHA-256 verification and write compressed results plus manifests.
- Duplicate mappings, corrupt compressed files, unsafe ZIP paths, multi-member ZIPs, decompression expansion and unsupported binary specialist formats receive actionable errors.
- Interactive calculations are bounded to 250,000 rows and visual source data to 5,000 rows.
- Each module exposes CSV/JSON evidence, interactive Plotly HTML/JSON, visual data export and a reproducibility ZIP.
- External specialist engines are readiness-detected; unavailable engines are never presented as successfully executed.

## Module coverage

### 1. Population Genetics, GWAS & PRS Studio

- **Workflow:** Import and harmonise → Sample and variant QC → Ancestry structure → Association screening → LD and regional review → PRS exploration → Evidence export
- **QC:** Sample missingness, Variant missingness, Heterozygosity, Relatedness proxy, MAF, Hardy-Weinberg, Population structure, Phenotype balance
- **Deep capabilities:** Sample/variant QC, Ancestry PCA, Association screening, LD proxy, Regional review, Fine-mapping proxy, PRS, Subgroup performance
- **Visuals (12):** Manhattan plot, QQ plot, Ancestry PCA, LD heatmap, Regional association, PRS distribution, Subgroup forest, QC dashboard, Sample QC landscape, Variant QC matrix, Fine-mapping credible set, PRS calibration
- **Handoffs:** Variant Workbench, Pathway Analysis, Clinical Biomarker Studio
- **Boundary:** Exploratory screening does not replace validated PLINK, SAIGE or REGENIE pipelines, imputation, ancestry-matched validation or clinical interpretation.

### 2. Epigenomics & Chromatin Accessibility Workbench

- **Workflow:** Import regions → Assay QC → Consensus regions → Differential signal → Motif and TF analysis → Peak-to-gene links → Export
- **QC:** Replicate balance, Coordinate validity, Peak width, Signal distribution, TSS/fragment profile availability, Genome-build consistency, Batch structure
- **Deep capabilities:** Consensus regions, Differential accessibility, Motif enrichment, TF activity, Peak-to-gene links, Methylation, RNA concordance, Genome tracks
- **Visuals (12):** Peak heatmap, Genome track, Accessibility volcano, Motif heatmap, TF network, Methylation profile, Peak-gene links, RNA concordance, Sample-level assay QC, Condition balance, Regulatory-class composition, Genome-bin signal
- **Handoffs:** Transcriptomics, Gene Regulatory Network, Comparative Regulatory Genomics
- **Boundary:** Screening-level region analysis must be confirmed with replicate-aware specialist pipelines, matched genome builds and orthogonal assays.

### 3. Pharmacogenomics & Clinical Genomics Studio

- **Workflow:** Import variants and medications → Genome-build QC → Allele and diplotype review → Phenotype inference → Drug-gene evidence → Conflict review → Report
- **QC:** Genome build, Gene coverage, Allele completeness, Copy-number availability, Guideline version, Medication mapping, Evidence conflicts
- **Deep capabilities:** Allele review, Diplotype assembly, Phenotype inference, Drug-gene evidence, Conflict review, Population context, Reanalysis alerts
- **Visuals (12):** Pharmacogene coverage, Diplotype waterfall, Drug-gene matrix, Phenotype distribution, Population comparison, Evidence ladder, Conflict matrix, Review timeline, Locus coverage QC, Diplotype confidence, Medication impact board, Reanalysis triggers
- **Handoffs:** Variant Workbench, Clinical Biomarker Studio, Evidence Review
- **Boundary:** Research-use output is not a prescribing recommendation. Clinical decisions require validated genotyping, current guidelines and qualified professional review.

### 4. Structural Variant, Repeat Expansion & Mosaicism Studio

- **Workflow:** Import caller outputs → Coordinate harmonisation → Evidence QC → Mosaic and repeat review → Gene and regulatory impact → Family segregation → Export
- **QC:** Coordinate validity, Event size, Read support, Caller concordance, Allele fraction, Copy-number consistency, Family/sample completeness
- **Deep capabilities:** SV normalization, Breakpoint clustering, Multi-caller consensus, Repeat review, Mosaic review, Gene/regulatory impact, Segregation
- **Visuals (12):** Chromosome SV track, Breakpoint Circos, CNV profile, Repeat-size distribution, Mosaic allele fraction, Caller concordance, Segregation view, Priority waterfall, Consensus event clusters, Mosaic candidate review, Repeat expansion candidates, Breakpoint hotspot profile
- **Handoffs:** Variant Workbench, Rare Disease Board, Cancer Genomics
- **Boundary:** Breakpoints and mosaic fractions require raw-read review and orthogonal confirmation; this module does not manufacture clinical classifications.

### 5. RNA Splicing & Isoform Pathology Lab

- **Workflow:** Import transcripts and junctions → Support QC → Event classification → Differential splicing → Variant linkage → Disease prioritisation → Export
- **QC:** Junction support, Group balance, PSI bounds, Transcript consistency, Reference annotation, Replicate structure
- **Deep capabilities:** Event classification, Differential splicing, Isoform switching, Outlier detection, Variant linkage, Fusion review, NMD proxy
- **Visuals (12):** Sashimi-style view, Transcript architecture, Exon-usage heatmap, PSI distribution, Isoform switching, Junction support, Variant-splice map, Gene summary, Group balance and QC, High-confidence isoform switches, Aberrant splicing outliers, NMD-risk proxy
- **Handoffs:** Transcriptomics, Rare Disease Board, Long-Read Isoforms
- **Boundary:** Built-in calculations are exploratory and do not replace splice-aware alignment, transcript assembly or validated DEXSeq, DRIMSeq, MAJIQ or long-read workflows.

### 6. Immunogenomics & Immune Repertoire Studio

- **Workflow:** Import repertoire → Sequence and count QC → Clonotype assignment → Diversity analysis → Expansion tracking → Single-cell integration → Export
- **QC:** Read/count depth, Chain validity, CDR3 completeness, Sample depth balance, Clonotype uniqueness, Longitudinal consistency
- **Deep capabilities:** Clonotype assignment, Diversity, V/J usage, Expansion, Public clonotypes, Longitudinal tracking, Single-cell integration, Isotype switching
- **Visuals (12):** Clonotype network, V/J chord-style matrix, CDR3 length, Diversity curves, Expansion treemap, Clone-cell embedding, Longitudinal tracking, QC dashboard, Chain and depth QC, Public/shared clonotypes, Clonality by sample, Rarefaction profile
- **Handoffs:** Single-Cell Heterogeneity, Vaccine Design, Clinical Biomarker Studio
- **Boundary:** Repertoire frequencies are sensitive to library preparation, sampling depth and clonotype definition; biological conclusions require matched experimental design.

### 7. Single-Cell Multiome & Regulatory Network Studio

- **Workflow:** Import modalities → Modality QC → Cell and feature filtering → Joint embedding → Peak-to-gene links → Regulatory inference → Export
- **QC:** Cell barcode matching, Modality depth, Feature counts, Mitochondrial fraction, Doublet proxy, Batch mixing, Cluster representation
- **Deep capabilities:** Joint embedding, Modality agreement, Peak-to-gene links, TF activity, Regulons, Pseudotime, Differential abundance, Multimodal markers
- **Visuals (12):** Joint embedding, Modality agreement, RNA-ATAC links, TF activity heatmap, Cell trajectory, Feature browser, Batch mixing, Cluster composition, Cell quality landscape, Modality depth, Deep modality agreement, Multimodal marker ranking
- **Handoffs:** Single-Cell Heterogeneity, Cell Atlas Mapping, Gene Regulatory Network
- **Boundary:** Joint embeddings and transferred labels are exploratory. Validate modality integration, cell labels and regulatory links with independent evidence.

### 8. Proteogenomics & Neoantigen Discovery Studio

- **Workflow:** Import variants and peptides → Peptide QC → HLA binding review → RNA and MS support → Clonality and safety → Panel selection → Export
- **QC:** HLA completeness, Peptide length, Expression support, MS support, Clonality, Normal-tissue risk, Variant uniqueness
- **Deep capabilities:** Variant peptide generation, HLA ranking, RNA/MS evidence, Clonality, Normal-tissue review, Shared candidates, Panel diversity
- **Visuals (12):** Variant-peptide Sankey, HLA heatmap, Peptide coverage, RNA-MS evidence, Candidate waterfall, Normal-tissue risk, Clonality map, Panel diversity, Candidate panel, Shared neoantigens, Evidence-tier composition, Peptide QC
- **Handoffs:** Cancer Genomics, Vaccine Design, Clinical Biomarker Studio
- **Boundary:** Predicted binding and immunogenicity do not establish therapeutic efficacy. Candidates require validated HLA typing, assays and safety review.

### 9. Gene Regulatory Network & TF Activity Studio

- **Workflow:** Import regulatory evidence → Edge QC → Regulon scoring → Condition comparison → Master-regulator ranking → Perturbation scenarios → Export
- **QC:** TF/target completeness, Replicate balance, Activity variance, Motif support, Edge evidence, Network density
- **Deep capabilities:** Regulon scoring, Differential TF activity, Master regulators, Network centrality, Perturbation simulation, Enhancer-promoter links, Time-series comparison
- **Visuals (12):** TF network, Regulon heatmap, TF volcano, Target Sankey, Centrality plot, Circuit diagram, Evidence matrix, Condition comparison, Master regulator ranking, Network statistics, Perturbation simulation, Edge-confidence distribution
- **Handoffs:** Epigenomics, Transcriptomics, Causal Biology
- **Boundary:** Inferred regulatory edges are hypotheses and must be validated with perturbation, binding or orthogonal evidence.

### 10. Federated Genomic Discovery & Phenopacket Studio

- **Workflow:** Import cases → Phenotype validation → Access and consent review → Federated query → Case matching → Human review → Export
- **QC:** Phenopacket validity, HPO identifiers, Variant representation, Consent scope, Access status, Source availability, De-identification
- **Deep capabilities:** Phenotype similarity, Genotype-phenotype matching, Federated source discovery, Consent review, Case matching, Query provenance, De-identification review
- **Visuals (12):** Phenotype-case matrix, Federated source map, Variant-match network, Pedigree view, Access badges, Query timeline, Match waterfall, Source coverage, Consent and access matrix, Federated query plan, Case-level match summary, Phenopacket QC
- **Handoffs:** Rare Disease Board, Variant Workbench, Evidence Review
- **Boundary:** Federated discovery does not grant access to restricted records and must respect consent, governance and source-specific interpretation rules.

### 11. Viral Genomics & Within-Host Evolution Studio

- **Workflow:** Import variants → Depth and frequency QC → Consensus and minor variants → Longitudinal dynamics → Lineage and recombination → Selection review → Export
- **QC:** Depth, Reference consistency, Mixed infection, Primer dropout, Timepoint order, Contamination, Lineage database version
- **Deep capabilities:** Consensus QC, Minor variants, Quasispecies proxy, Lineage assignment, Recombination, Selection proxy, Transmission distance, Resistance/antigenic review
- **Visuals (12):** Frequency trajectories, Minor-variant spectrum, Lineage map, Recombination matrix, Selection profile, Subject timeline, Mutation heatmap, QC dashboard, Depth QC, Primer-dropout profile, Mixed-infection review, Transmission summary
- **Handoffs:** Pathogen Outbreak, Comparative Pathogen Genomics, AMR Surveillance
- **Boundary:** Low-frequency variants are highly sensitive to sequencing and contamination artefacts; confirm with validated callers, controls and replicate evidence.

### 12. Genome Annotation & Comparative Annotation Studio

- **Workflow:** Import annotation → Syntax and coordinate QC → Gene-model comparison → Functional evidence → Orthology and synteny → Completeness review → Export
- **QC:** FASTA/GFF compatibility, Coordinate validity, Feature overlap, Evidence support, ORF length, Completeness, Version consistency
- **Deep capabilities:** GFF/GTF validation, Gene-model comparison, Orthology, Synteny, Functional annotation, Pseudogene review, Completeness, Manual curation
- **Visuals (12):** Genome feature track, Annotation diff, Completeness dashboard, Orthology matrix, Synteny blocks, Evidence distribution, Feature-length profile, Review funnel, Annotation conflict map, Orphan feature review, Version consistency, Feature QC matrix
- **Handoffs:** Long-Read Assembly, Protein Annotation, Comparative Genomics
- **Boundary:** Automated annotation transfer can propagate errors. Curated gene models and experimental evidence remain authoritative.

### 13. Circular DNA, Mobile Elements & Genome Instability Studio

- **Workflow:** Import instability events → Breakpoint QC → Circle and insertion classification → Copy-number review → Gene impact → Recurrence analysis → Export
- **QC:** Breakpoint support, Copy-number context, Circular topology, Gene impact, Sample recurrence, Long-read support, Integration-site validity
- **Deep capabilities:** Circular topology, Breakpoint clusters, Focal amplification, Mobile elements, Integration sites, Sample recurrence, Instability score
- **Visuals (12):** Circular breakpoint map, Copy-number profile, Amplification topology, Mobile-element map, Recurrence heatmap, Gene impact, Event-size distribution, Priority waterfall, Consensus topology clusters, Sample recurrence, Amplification topology summary, Breakpoint hotspots
- **Handoffs:** Structural Variant Studio, Cancer Genomics, Long-Read Assembly
- **Boundary:** Complex rearrangement structures require raw-read, assembly and orthogonal validation; inferred circles are research hypotheses.

### 14. Environmental Genomics & eDNA Surveillance Studio

- **Workflow:** Import detections → Control and depth QC → Taxonomy harmonisation → Occupancy and biodiversity → Spatial and temporal review → Alert generation → Export
- **QC:** Negative controls, Positive controls, Sequencing depth, Reference confidence, Taxonomic ambiguity, Site/date completeness, Replicate consistency
- **Deep capabilities:** Contamination filtering, Species detection, Occupancy, Biodiversity, Rare/invasive alerts, Temporal/spatial surveillance, Reference confidence
- **Visuals (12):** Species-site heatmap, Occupancy map, Biodiversity curves, Control contamination, Temporal trends, Reference confidence, Community ordination, Alert dashboard, Control QC, Replicate concordance, Taxonomic ambiguity, Surveillance alerts
- **Handoffs:** One Health Center, Microbiology & Metagenomics, Pathogen Outbreak
- **Boundary:** eDNA detection depends on sampling design, assay specificity, reference coverage and environmental persistence; presence does not prove abundance or viability.

### 15. Comparative Regulatory Genomics Studio

- **Workflow:** Import orthologous regions → Coordinate and orthology QC → Conservation analysis → Motif turnover → Activity comparison → Regulatory synteny → Export
- **QC:** Species/build consistency, Lift-over quality, Ortholog completeness, Motif mapping, Activity normalization, Tissue matching
- **Deep capabilities:** Conserved elements, Enhancer conservation, Motif turnover, Regulatory synteny, TF activity comparison, Gain/loss, Comparative networks
- **Visuals (12):** Conservation landscape, Motif turnover heatmap, Activity comparison, Regulatory synteny, Ortholog network, Constraint distribution, Species clustering, Evidence matrix, Species support, Regulatory gain/loss, Tissue matching, Conservation QC
- **Handoffs:** Epigenomics, Comparative Genomics, Gene Regulatory Network
- **Boundary:** Conservation and motif presence are indirect evidence. Functional claims require species- and tissue-matched experimental validation.

## Shared stability and performance controls

- Explicit run-on-demand processing.
- Guided/Expert parameter separation.
- Required-column and one-to-one mapping validation.
- Missingness, duplicates and non-finite value audits.
- Deterministic sampling and seeds.
- Bounded memory and rendering limits.
- Background staging with file hash verification.
- Visual failure isolation with stable recovery identifiers.
- On-demand evidence generation rather than regeneration on every rerun.
- Cross-module handoff manifests preserve selected rows and reference context.

## Completed verification

| Check | Result |
|---|---:|
| Step 138 focused tests | **20 passed** |
| Step 137 compatibility tests | **19 passed** |
| Selected regression groups | **81 passed** |
| Total completed selected tests | **120 passed, 0 failures** |
| Python compilation | **1002/1002 passed** |
| Navigation integrity | **205/205 pages healthy** |
| SQLite databases | **40/40 healthy** |
| Database rows inspected | **108,493** |
| Foreign-key violations | **0** |
| Module smoke analyses | **15/15 non-empty** |
| Visual construction smoke | **12/12 per module** |
| Background worker smoke | **Completed** |

## Honest environment boundary

Live Streamlit browser/AppTest execution was not available in the build environment because the compatible Streamlit/PyArrow browser runtime was absent. Physical clean Windows installation, optional external binaries, licensed/current reference databases, clinical interpretation and wet-lab validation were not fabricated or falsely certified. Known defects covered by the completed focused and regression suites are resolved; an absolute zero-defect guarantee across every machine, dataset and third-party executable is not technically truthful.
