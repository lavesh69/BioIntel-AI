# BioIntel AI Step 60 — Lab Analytics Excellence

## Scope

Step 60 upgrades the four Lab Analytics modules:

1. Primer, CRISPR & Codon Studio
2. Wet-Lab Biotechnology
3. Microbiology & Metagenomics Rapid Screen
4. Professional Metagenomics Pipeline

## Correctness fixes

- Microbiology k-mer range is consistent through UI and backend up to k=31.
- Empty sample selections are blocked instead of silently selecting columns.
- Negative abundance values are rejected instead of clipped.
- Wet-lab instrument columns are mapped through explicit canonical schemas.
- Experimental designs require valid unique arms and design-specific parameters.
- Optional Leiden dependencies no longer crash the local single-cell workflow; a labelled deterministic fallback is used.

## Molecular design

- Nearest-neighbour primer Tm with reaction chemistry.
- Target-flanking PCR/qPCR modes and explicit product constraints.
- Self-dimer, heterodimer, 3-prime complementarity, GC clamp and homopolymer screens.
- Exact compact-panel in-silico PCR and multiplex compatibility audit.
- SpCas9, SpCas9-NG, SaCas9, AsCas12a and LbCas12a PAM-aware design.
- Local mismatch/seed-aware off-target screening.
- CBE/ABE editing-window audits and paired-guide deletion planning.
- Ten host profiles, weighted synonymous optimization, CAI proxy, GC-window limits, rare-codon and synthesis-motif controls.

## Wet-lab analytics

- Canonical templates and column-mapping for arbitrary instrument exports.
- 96/384-well plate audits, duplicate/edge checks and plate heatmaps.
- qPCR standard-curve efficiency, multi-reference normalization, reference-gene stability, NTC/no-RT/positive-control QC, melt-curve screening, biological-group confidence intervals and FDR.
- ELISA weighted 4PL/5PL/log-linear/linear selection, residuals, standard CV, LOD/LOQ, Z-prime, hook-effect, dilution parallelism and recovery screening.
- Michaelis-Menten, Hill, substrate-inhibition and global competitive/noncompetitive/uncompetitive/mixed inhibition fits.
- Initial-rate extraction from reaction progress curves.
- Dynamic growth/yield/productivity, off-gas RQ, OTR, cumulative-feed and golden-batch deviation analytics.
- Independent, paired, repeated-measures, ANOVA, proportions, correlation, non-inferiority, equivalence and cluster-design sample-size planning.
- Stratified variable-block randomization, blinding labels and 96/384-well plate randomization.

## Metagenomics

- Count/fraction/percentage/continuous-abundance awareness.
- Robust multiplicative zero replacement and CLR.
- Restricted permutations, covariate-adjusted CLR association, negative-control contaminant screens and longitudinal alpha slopes.
- NMDS plus PCoA negative-eigenvalue diagnostics.
- Faith phylogenetic diversity and weighted/unweighted UniFrac from user Newick trees.
- Functional feature/pathway aggregation.
- Reproducible Fastp, Bowtie2, Kraken2, Bracken, MetaPhlAn and MultiQC command plans.
- Reviewed local execution without shell invocation when required tools and databases are installed.

## Input templates

A checksum-protected template pack contains qPCR wide/long/standards/melt curves, ELISA plates, enzyme kinetics/progress curves, bioprocess time series, experimental randomization, metagenomics metadata/functional profiles and a Newick tree template.

## Verification

- Full regression suite: 527 collected; 511 passed; 16 environment/browser-gated skips; 0 failures.
- Focused Step 60 suite: 22 passed, including all four Lab Analytics page renders.
- Ruff: 0 findings.
- Python compilation: passed.
- Database integrity, foreign keys, model hashes, secret scan, engineering gates and store-release verification: passed.

## External scientific boundary

The repository cannot manufacture regulated LIMS qualification, GLP/GMP operating history, instrument certification, licensed third-party databases, signed electronic records, independent wet-lab validation, clinical approval or laboratory accreditation. The software provides implementation-ready research workflows and explicit integration points without fabricating those external outcomes.
