# Step 29 Biotechnology & Bioinformatics Guide

## Core workflows

Use the sidebar Genomics, Omics, Proteomics, Structure, Systems Biology,
Microbiology and Biotechnology categories. Every Step 29 screen opens with a
populated local demonstration dataset and accepts user files or sequences.

## Supported local inputs

- FASTQ, FASTA, aligned FASTA
- VCF and GFF3/GTF
- gene count matrices
- protein sequences and PDB files
- qPCR, enzyme kinetics, fermentation and microbiome CSV tables
- transcriptomic and proteomic matrices

## Optional advanced tools

The Capability Center detects BLAST+, MAFFT, HMMER, MMseqs2, minimap2,
samtools, bcftools and AutoDock Vina. They are not silently downloaded or
executed. Install them separately and keep them on PATH.

Optional Python packages are listed in `requirements-bioinformatics.txt`.

## Interpretation boundary

- differential-expression p-values are dependency-light screening estimates
- protein family/topology calls are heuristics
- ADMET values are early rule-based alerts
- ANI is a k-mer proxy
- UPGMA uses p-distance from an already aligned input
- primer and CRISPR results require specificity/off-target validation

Use validated specialist pipelines and experimental review before scientific
publication, therapeutic decisions or clinical use.
