# BioIntel AI Step 107 — Scientific Visual Excellence

**Version:** 10.7.0  
**Release objective:** add module-specific scientific visuals without reintroducing heavy reruns, hidden-tab computation or generic decorative charts.

## Delivered

- 35 scientific modules now expose exactly five domain-specific interactive visual choices.
- 175 module-specific scientific visual definitions are covered by automated builder tests.
- 13 high-use legacy pages received dedicated or generic scientific visual explorers.
- Seven platform workspaces received operational visual explorers.
- Charts include interpretation, method/units, underlying data and CSV export.
- Plotly modebar supports SVG export.
- Only one selected visual renders at a time, reducing RAM, browser DOM size and Streamlit rerun cost.
- The existing explicit Run Analysis and cached-result workflow remains intact.

## Scientific visual coverage

### 112 · Epigenomics & Chromatin Regulation Studio
1. **Regulatory signal versus methylation** — Highlights regions where chromatin signal and methylation move together or diverge.
2. **Differential accessibility volcano** — Prioritises regions by effect size and statistical evidence.
3. **Condition-by-region signal heatmap** — Compares mean regulatory signal across regions and conditions.
4. **Methylation-shift distribution** — Shows the range and direction of condition-associated methylation changes.
5. **Top regulatory-region priorities** — Ranks regions combining statistical effect, methylation shift and replicate balance.

### 113 · Metabolomics & Lipidomics Workbench
1. **Signal versus blank contamination** — Separates high-abundance biological features from blank-associated signals.
2. **Differential metabolite volcano** — Combines fold change, FDR and annotation confidence for candidate review.
3. **Feature abundance heatmap** — Displays the dominant abundance patterns across samples.
4. **Analytical QC landscape** — Identifies features with high variation or excessive blank contribution.
5. **Top metabolite priorities** — Ranks reproducible, low-contamination and statistically supported features.

### 114 · Immunoinformatics & Vaccine Design Lab
1. **Epitope evidence landscape** — Shows binding, immunogenicity, conservancy and safety simultaneously.
2. **Top epitope profiles** — Compares normalised evidence dimensions for the highest-ranked peptides.
3. **Allele coverage and candidate quality** — Compares average candidate strength and safety across HLA alleles.
4. **Peptide manufacturability space** — Flags extreme composition and cysteine burden that may complicate synthesis.
5. **Promiscuous epitope ranking** — Prioritises peptides supported across multiple alleles.

### 115 · Antibody & Biologics Engineering Studio
1. **Affinity–stability landscape** — Identifies candidates balancing binding and physical stability.
2. **Top antibody developability profiles** — Compares normalised developability dimensions across leading variants.
3. **Liability and aggregation burden** — Highlights candidates with fewer liabilities and lower aggregation risk.
4. **Candidate priority ranking** — Ranks antibody variants and highlights Pareto-optimal candidates.
5. **Antibody property correlation** — Shows trade-offs and redundant metrics across the candidate panel.

### 116 · Molecular Docking & Dynamics Lab
1. **Pose score versus structural deviation** — Surfaces poses combining favourable scores, low RMSD and stable hydrogen bonding.
2. **Docking-score distribution by ligand** — Compares pose variability and best-score consistency across ligands.
3. **Strain versus interaction persistence** — Flags poses with high conformational strain or weak hydrogen-bond occupancy.
4. **Ligand consensus ranking** — Aggregates best score, RMSD, occupancy and flagged-pose burden.
5. **Docking metric correlation** — Reveals score–stability trade-offs across all poses.

### 117 · Pharmacogenomics & Precision Medicine Board
1. **Gene–drug review matrix** — Shows combinations with the strongest evidence and phenotype risk.
2. **Pharmacogene evidence profile** — Compares review burden by gene and metaboliser phenotype.
3. **Evidence-level review burden** — Counts records requiring review within each evidence tier.
4. **Top variant–drug records** — Ranks research records while keeping curation status visible.
5. **Phenotype-risk distribution** — Shows how phenotype risk varies across medicines.

### 118 · Spatial Omics & Digital Pathology Studio
1. **Spatial expression map** — Maps expression and priority across tissue coordinates.
2. **Regional expression heatmap** — Compares gene expression across annotated tissue regions.
3. **Spatial autocorrelation ranking** — Highlights genes with clustered rather than random spatial patterns.
4. **Expression distribution by region** — Shows within-region variability and potential tissue heterogeneity.
5. **Top spatial priority spots** — Ranks spots with strong regional enrichment and expression.

### 119 · Single-Cell Trajectory & Communication Lab
1. **Expression along pseudotime** — Shows state-dependent expression changes across the inferred trajectory.
2. **Communication signal by cell state** — Compares average ligand–receptor activity across inferred states.
3. **Ligand–receptor network** — Displays the dominant communication edges identified across clusters.
4. **Cluster trajectory slopes** — Compares expression trends and statistical support across clusters.
5. **Communication heatmap** — Summarises ligand–receptor scores across the analysed cells.

### 120 · Bioimage & Microscopy AI Lab
1. **Image-derived phenotype space** — Separates phenotypes by size, intensity, circularity and condition.
2. **Object-size distribution** — Shows size heterogeneity and condition-specific shifts.
3. **Intensity by condition** — Compares signal distributions while preserving QC flags.
4. **Image QC ranking** — Identifies images with excessive object-level anomalies.
5. **Condition effect sizes** — Compares morphology and intensity shifts across conditions.

### 121 · Biostatistics, Power & Experimental Design Studio
1. **Sample size sensitivity** — Shows how total recruitment changes with the assumed effect size.
2. **Power versus recruitment burden** — Compares statistical power against the required sample size.
3. **Allocation plan** — Displays the planned participants per study arm.
4. **Dropout inflation** — Shows the recruitment penalty introduced by anticipated attrition.
5. **Design efficiency ranking** — Ranks scenarios by efficiency and practical feasibility.

### 122 · Clinical Trial Biomarker & Patient Stratification Studio
1. **Biomarker ROC curve** — Shows sensitivity–specificity trade-offs across candidate cut-offs.
2. **Kaplan–Meier screening curves** — Compares survival trajectories across arm and biomarker strata.
3. **Biomarker distribution by response** — Shows whether biomarker levels differ between responders and non-responders.
4. **Biomarker and time-to-event landscape** — Combines biomarker magnitude, follow-up time and outcome status.
5. **Response rate by biomarker group** — Compares response proportions across treatment and biomarker strata.

### 123 · Genome Editing Safety & Off-Target Validation Lab
1. **Efficiency versus off-target burden** — Highlights guides balancing on-target activity and genome-wide specificity.
2. **Guide sequence-quality space** — Identifies extreme GC, low-complexity and homopolymer liabilities.
3. **Guide safety ranking** — Ranks candidates using on-target evidence and multiple off-target liabilities.
4. **Off-target burden by mismatch class** — Shows how predicted off-target counts vary with tolerated mismatches and SNP overlap.
5. **Guide metric correlation** — Reveals trade-offs among activity, sequence quality and specificity.

### 124 · Proteogenomics & Neoantigen Discovery Studio
1. **Neoantigen evidence landscape** — Integrates spectral support, HLA binding, expression and clonality.
2. **Top neoantigen evidence profiles** — Compares normalised evidence dimensions for leading peptides.
3. **Spectral confidence versus candidate priority** — Flags high-priority candidates with weak spectral-confidence proxies.
4. **Peptide-length distribution** — Shows candidate size distribution and multi-layer support.
5. **Neoantigen priority ranking** — Ranks candidates supported across variant, expression, spectral and HLA evidence.

### 125 · Bioprocess & Fermentation Optimization Studio
1. **Product trajectory by batch** — Compares product accumulation across process runs.
2. **Biomass growth trajectory** — Shows growth dynamics and between-batch consistency.
3. **Dissolved-oxygen profile** — Highlights oxygen demand shifts and potential process deviations.
4. **Biomass–product relationship** — Shows productivity trade-offs and deviation states.
5. **Batch performance ranking** — Combines growth, productivity, yield and deviation burden.

### 126 · LIMS, ELN & Sample Chain-of-Custody Hub
1. **Sample status and custody risk** — Shows which operational states carry the greatest review burden.
2. **Storage-location occupancy** — Summarises sample counts and expiry states across storage locations.
3. **Expiry horizon distribution** — Shows the timing of upcoming sample and reagent expiries.
4. **Freeze–thaw burden and custody risk** — Identifies samples with repeated handling and elevated operational risk.
5. **Lineage-integrity findings** — Counts orphan and self-referential parent relationships requiring correction.

### 127 · Causal Biology & Perturbation Modelling
1. **Effect–uncertainty landscape** — Highlights precise effects supported by stronger instruments.
2. **Instrument strength versus priority** — Shows how weak instruments reduce confidence in causal hypotheses.
3. **IVW meta-analysis effects** — Summarises pooled causal estimates and heterogeneity across instruments.
4. **Causal effect waterfall** — Orders effect estimates to reveal positive and negative hypotheses.
5. **Causal metric correlation** — Shows relationships among effect magnitude, uncertainty and instrument strength.

### 128 · Explainable AI & Model Assurance Center
1. **Prediction calibration by subgroup** — Compares predicted scores with observed outcomes and uncertainty.
2. **ROC curve** — Shows sensitivity–specificity performance over thresholds.
3. **Precision–recall curve** — Focuses on performance under class imbalance.
4. **Subgroup accuracy audit** — Compares subgroup performance and highlights gaps from the best-performing group.
5. **Uncertainty versus error** — Checks whether uncertainty rises when predictions are wrong or inaccurate.

### 129 · Multi-Omics Harmonization & Batch-Correction Studio
1. **PCA before and after harmonisation** — Shows whether batch structure is reduced while samples remain distinguishable.
2. **Batch distributions before and after correction** — Compares batch location shifts while retaining raw values.
3. **Raw versus harmonised values** — Highlights features receiving large corrections.
4. **Batch-effect reduction by feature** — Ranks features by the reduction in between-batch variability.
5. **Harmonised feature heatmap** — Shows remaining batch-level structure after correction.

### 130 · Glycomics & Glycoproteomics Workbench
1. **Glycoform abundance and confidence** — Balances abundance, annotation confidence and condition context.
2. **Glycan abundance heatmap** — Compares glycan abundance across biological conditions.
3. **Site-resolved glycosylation shifts** — Ranks sites by condition-associated abundance change and confidence.
4. **Annotation confidence by condition** — Shows confidence distributions and potential condition-specific annotation bias.
5. **Top glycopeptide priorities** — Ranks site-specific candidates for expert spectral review.

### 131 · One Health & Environmental Genomics Center
1. **Surveillance signal over time** — Tracks pathogen abundance across locations and reporting periods.
2. **Host–pathogen surveillance matrix** — Shows pathogen signals shared across human, animal and environmental hosts.
3. **Outbreak signal screen** — Flags unusually strong signals relative to recent local history.
4. **Cross-host pathogen diversity** — Highlights pathogens detected across multiple host categories.
5. **AMR burden by location** — Compares antimicrobial-resistance signals across sites and host sources.

### 132 · Synthetic Data & Privacy Engineering Lab
1. **Privacy class size versus measurement** — Shows records with small equivalence classes and potential disclosure risk.
2. **Equivalence-class distribution** — Displays the distribution of anonymity-set sizes.
3. **Privacy-risk trade-off** — Compares diversity and distributional distance across equivalence classes.
4. **Synthetic-data utility by column** — Highlights features with the largest source-versus-synthetic distribution shift.
5. **Synthetic feature correlation** — Checks whether major numerical relationships remain visible after synthesis.

### 134 · Population Genetics & GWAS Studio
1. **Genome-wide association overview** — Shows association evidence across chromosomes with the conventional genome-wide threshold.
2. **Association effect volcano** — Combines effect magnitude, statistical evidence and variant QC.
3. **Sample call rate and phenotype** — Identifies low-call-rate samples and phenotype outliers.
4. **Minor-allele frequency distribution** — Shows the frequency spectrum and variants failing QC.
5. **Top association candidates** — Ranks variants using effect, p-value and QC evidence.

### 135 · Structural Variant & Repeat Expansion Lab
1. **Structural-variant landscape** — Maps event size, genomic position, type and support.
2. **SV burden by type** — Compares event size and confidence across structural-variant classes.
3. **Gene-impact heatmap** — Highlights genes repeatedly affected by high-priority SV classes.
4. **Caller evidence and quality** — Identifies poorly supported or low-quality calls requiring review.
5. **Top structural-variant candidates** — Ranks variants by support, quality, size and gene impact.

### 136 · Longitudinal Multi-Omics & Time-Series Studio
1. **Mean multi-omics trajectories** — Shows average temporal patterns across omics layers and groups.
2. **Subject-level trajectory slopes** — Compares individual baseline values and longitudinal change.
3. **Temporal effect landscape** — Highlights features with strong between-group slope differences.
4. **Subject-by-feature slope heatmap** — Displays heterogeneous temporal responses across subjects.
5. **Top longitudinal features** — Ranks features using effect size, slope difference and statistical evidence.

### 137 · RNA Isoform & Alternative Splicing Studio
1. **Differential isoform-usage volcano** — Combines usage shift, FDR and junction support.
2. **Isoform abundance and junction support** — Separates well-supported abundant isoforms from weak candidates.
3. **Transcript abundance heatmap** — Compares transcript usage across biological groups.
4. **Isoform complexity by gene** — Shows genes with the largest number of represented transcripts.
5. **Top isoform-switch candidates** — Ranks transcripts by differential usage and junction evidence.

### 138 · RNA Modification & Epitranscriptomics Lab
1. **Differential modification volcano** — Combines modification change, FDR and coverage QC.
2. **Coverage and replicate consistency** — Highlights sites with adequate depth and low replicate variability.
3. **Modification-fraction heatmap** — Compares site-level modification fractions across conditions.
4. **Modification burden by transcript** — Shows transcripts carrying many or highly modified sites.
5. **Top modification-site priorities** — Ranks sites using change, statistical support, depth and consistency.

### 139 · Strain-Resolved Microbiome & Functional Profiling Studio
1. **Strain abundance heatmap** — Shows strain-level abundance patterns across samples.
2. **Alpha diversity by group** — Compares within-sample strain diversity across groups.
3. **Differential microbial features** — Highlights group-associated strains, pathways and resistance features.
4. **Taxa and strain richness** — Shows sample-level richness and diversity patterns.
5. **Top microbiome features** — Ranks prevalent, differential and statistically supported features.

### 140 · Cell Atlas Mapping & Reference Annotation Studio
1. **Reference mapping confidence** — Shows agreement between similarity and marker evidence for each cell.
2. **Confidence by transferred label** — Compares annotation confidence and novelty flags across labels.
3. **Cluster-to-reference mapping matrix** — Shows the dominant reference labels assigned to query clusters.
4. **Novel-state burden by label** — Highlights labels associated with many low-confidence or novel cells.
5. **Batch-shift diagnostic** — Shows whether mapping confidence differs systematically across batches.

### 141 · Phenotypic Screening & High-Content Analysis Lab
1. **Dose–response profiles** — Shows normalised response across dose for each compound.
2. **Hit priority ranking** — Ranks compounds by potency, reproducibility and dose-response consistency.
3. **Reproducibility versus response area** — Separates strong reproducible hits from noisy responses.
4. **Plate Z-prime quality** — Compares assay separation and identifies weak plates.
5. **Plate-response heatmap** — Shows spatial response patterns and potential edge effects.

### 142 · Organoid & 3D Cell Model Analytics
1. **Organoid growth trajectories** — Compares mean organoid area over time across conditions.
2. **Growth and viability landscape** — Balances expansion rate, viability and final size.
3. **Morphology by condition** — Shows shape consistency and QC flags across treatment conditions.
4. **Condition-level organoid performance** — Compares growth and viability across experimental conditions.
5. **Top organoid responses** — Ranks organoids by growth, viability and morphology quality.

### 143 · Protein Language Model & Generative Design Lab
1. **Protein design candidate space** — Shows activity, stability, sequence quality and design constraints.
2. **Top sequence profiles** — Compares normalised design dimensions for leading sequences.
3. **Sequence complexity and liabilities** — Flags low-complexity or motif-heavy candidates.
4. **Protein candidate ranking** — Ranks sequences by activity, stability and quality proxies.
5. **Mutation proposal mix** — Shows the types and parent coverage of generated mutation proposals.

### 144 · Enzyme Engineering & Metabolic Pathway Design Studio
1. **Enzyme activity–stability landscape** — Shows enzyme performance and pathway flux across hosts.
2. **Top enzyme variant profiles** — Compares normalised catalytic and pathway dimensions.
3. **Pathway bottleneck ranking** — Highlights reactions with low flux or weak activity support.
4. **Reaction flux by host** — Compares pathway throughput across host organisms.
5. **Cofactor and host performance** — Shows how cofactor usage and host context influence candidate quality.

### 145 · Host–Pathogen Interaction Studio
1. **Host–pathogen target landscape** — Prioritises essential, druggable and well-supported interactions.
2. **Host–pathogen interaction network** — Displays the dominant cross-species protein interactions.
3. **Pathogen target ranking** — Ranks pathogen proteins by host-partner support and essentiality.
4. **Interaction-priority heatmap** — Shows concentrated interaction evidence across host and pathogen proteins.
5. **Host effect versus pathogen essentiality** — Highlights interactions combining strong host phenotype and pathogen dependence.

### 146 · Virology & Viral Evolution Workbench
1. **Viral variant-frequency landscape** — Maps within-sample variant frequencies across the genome.
2. **Sample-by-gene variant heatmap** — Shows gene-level variant burden across samples.
3. **Within-sample diversity** — Highlights samples with heterogeneous viral populations.
4. **Minor variants by gene** — Counts low-frequency variation and lineage-marker status across genes.
5. **Top viral variants** — Ranks variants by frequency, minor/consensus status and lineage relevance.

### 147 · Rare Variant Burden & Family Genetics Lab
1. **Rarity–phenotype prioritisation** — Shows how rarity, impact, phenotype match and inheritance combine.
2. **Candidate priority waterfall** — Orders genes from lower to higher family-specific priority.
3. **Gene-by-inheritance evidence** — Shows which genes are supported under different inheritance models.
4. **Family gene-burden ranking** — Ranks genes by maximum priority and inheritance consistency across families.
5. **Manual review burden** — Counts review-required variants by predicted impact and inheritance consistency.

## Legacy-page upgrades

- `2_Sequence_Comparison.py` — Alignment identity, gap and event visual suite
- `4_DTI_Feature_Builder.py` — Feature-distribution and quality explorer
- `6_DTI_Predictor.py` — Prediction confidence, applicability and molecular-property visuals
- `7_Model_Evaluation.py` — Metric, error and subgroup explorer
- `16_Batch_Sequence_Analysis.py` — Batch length, composition and outlier explorer
- `58_Primer_CRISPR_Codon_Studio.py` — Candidate, score and sequence-design explorer
- `60_Protein_Annotation_Proteomics.py` — Protein annotation and feature explorer
- `63_Pathway_Network_Analysis.py` — Pathway and network result explorer
- `66_Omics_Integration_Hub.py` — Cross-omics integration explorer
- `68_Alignment_Phylogeny.py` — Alignment and phylogenetic result explorer
- `94_Pangenome_Variation_Graph_Studio.py` — Pangenome variation explorer
- `99_Synthetic_Biology_Circuit_Designer.py` — Circuit design and simulation explorer
- `100_Rare_Disease_Genome_Interpretation.py` — Variant and evidence explorer

## Performance and reliability controls

- Plotly figures are built from bounded/aggregated data where needed.
- One chart is rendered per visual card selection instead of loading five charts simultaneously.
- Chart computations are downstream of the cached analysis result.
- Empty, missing-column and partial-payload cases use safe fallbacks.
- Underlying data remains exportable for reproducibility.

## Verification

- Scientific workbench AppTest: **35/35 passed** after switching to demo data and running the analysis.
- Patched legacy-page default load: **13/13 passed**.
- Visual builder: **35/35 modules produced five serialisable Plotly figures**.
- Selected release/regression suite: **75/75 passed**.
- Application self-test: **7/7 passed**.
- Python compilation: passed.

## Honest boundary

No software build can guarantee that every future dataset, optional external binary, driver or Windows machine will never fail. This release verifies the listed code paths and supplies safe empty/error handling. Specialist tools, current reference databases and independent scientific validation remain required where applicable.
