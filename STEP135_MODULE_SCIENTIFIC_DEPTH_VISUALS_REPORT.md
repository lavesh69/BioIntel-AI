# BioIntel AI Step 135 — Module Scientific Depth & Specialist Visuals

## Scope

Step 135 is a module-only patch built on Step 134. It does not add a central hub, navigation category, theme, font or governance workflow. It deepens the fifteen next-generation biomedical modules and preserves product version 13.2.0 for compatibility.

## What was fixed

- Summary-only outputs were extended with module-specific statistical and scientific review layers.
- Generic charts were supplemented with specialist viewers tied to each module's scientific domain.
- Dirty, incomplete, non-finite and duplicate inputs now receive an explicit qualification table instead of silent assumptions.
- Advanced calculations and viewers are isolated from primary module results so a failure cannot crash the main analysis.
- Deep analysis is bounded for memory safety and exposes external-engine requirements rather than fabricating unavailable evidence.

## Added scientific depth

### Digital Pathology
- Tile-grid reconstruction and uncertainty/OOD review.
- Slide-level tumour confidence intervals.
- Scanner/site domain projection.
- Tile tumour-probability and review mosaics.

### Long-Read Epigenome
- Coverage-weighted condition effects.
- Deterministic bootstrap confidence intervals.
- FDR and confidence-excludes-zero DMR review.
- Position-level lollipop and haplotype ribbon viewers.

### Single-Cell Long-Read Isoforms
- Pseudobulk transcript usage.
- Chi-square differential usage screening with BH FDR.
- Isoform entropy and support review.
- Gene → transcript → cluster Sankey and usage heatmap.

### Biomedical Foundation Models
- FP32, FP16, INT8 and INT4 memory profiles.
- Training-memory planning and hardware-fit matrix.
- Accuracy-memory Pareto screening.
- Licence/task/modality view.

### AMR Surveillance
- Wilson resistance-rate confidence intervals.
- Genotype/phenotype confusion audit.
- Temporal acceleration and emergence alerts.
- Species → lineage → AMR-gene flow.

### Spatial Medicine
- k-nearest-cell neighbourhood enrichment.
- Tumour/immune/other compartment mapping.
- Regional gene-expression profile.
- Patient-level spatial replication review.

### Gene Therapy Vector Engineering
- Vector-specific packaging limits and utilisation.
- Optional sequence GC, homopolymer and CpG review.
- Linear construct element map.
- Safety/tropism matrix.

### CAR-T Engineering
- Construct architecture manifest and schematic.
- Efficacy, safety and manufacturability balance.
- Antigen/domain comparison.

### Federated Biomedical AI
- Round convergence and stability diagnostics.
- Final-round fairness gap.
- Conservative basic and advanced privacy composition screens.
- Site-round heatmap and federation topology.

### Clinical Biomarker & Survival
- Exploratory Cox partial-likelihood model.
- Hazard ratios and confidence intervals.
- Schoenfeld-style proportional-hazards diagnostic.
- Median-horizon discrimination, calibration and patient risk views.

### Protein–Ligand Co-Design
- True multi-objective non-dominated set.
- Robust ranking across deterministic weight perturbations.
- Greedy diverse shortlist.
- 3D objective landscape and parallel coordinates.

### Pangenome Population Medicine
- FST-like differentiation screening.
- Population path entropy.
- Population/path/variant Sankey.
- Allele-frequency heatmap.

### Pharmacovigilance
- Fisher exact significance.
- Gamma-Poisson EBGM-like shrinkage and lower bound.
- IC025 screening.
- Duplicate case-fingerprint review and outcome hierarchy.

### Synthetic Trial Simulation
- 500 deterministic Monte Carlo simulations.
- Observed-effect power and null type-I error screens.
- Dropout sensitivity.
- Risk-difference, Love plot and recruitment viewers.

### Autonomous Laboratory Planner
- Bounded factorial design generation.
- Approximate sample-size planning.
- Adjacency-aware 96-well assignment.
- Resource Gantt, factor coverage and cost views.

## Safety and performance

- Deep analysis limit: 200,000 records.
- Specialist plot limit: 20,000 records.
- Statistical group limit: 250.
- Bootstrap limit: 120 iterations.
- Network link limit: 180.
- Deterministic sampling preserves extreme and quantile observations.
- Memory and viewer errors are isolated from primary analysis.
- No external model, database, wet-lab, clinical or regulatory evidence is fabricated.

## Verification boundary

Step 135 validates built-in research-screening calculations, table generation, figure serialisation, Python syntax, database integrity, protected-page hashes and package contents. Specialist tools, physical instruments, licensed references, clinical qualification and independent experiments remain external requirements.
