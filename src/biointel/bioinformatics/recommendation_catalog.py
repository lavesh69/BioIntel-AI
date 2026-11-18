from __future__ import annotations

from typing import Any


def _f(text: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in text.split("|") if item.strip())


MODULE_FEATURES: dict[str, tuple[str, ...]] = {
    "sequencing_quality": _f("FASTQ quality interpretation|Per-base quality recommendation|Adapter contamination recommendation|GC-bias detection|Duplicate-read assessment|Overrepresented-sequence assessment|Read-length suitability|Trimming recommendation|Filtering threshold recommendation|Resequencing recommendation|Sample exclusion recommendation|Sequencing-depth adequacy|Contamination warning|Platform-specific QC rules|Per-sample QC score|Cohort QC dashboard|Recommended trimming parameters|Expected retained reads|Downstream analysis impact|Re-sequencing priority|Sample rescue options|Before/after QC comparison|MultiQC-style summary|Exportable QC action plan"),
    "alignment_mapping": _f("Reference genome selection|Aligner recommendation|Mapping-quality threshold|Multimapping assessment|Duplicate handling|Splice-aware alignment recommendation|Read-group validation|Coverage assessment|Reference compatibility check|Annotation compatibility check|Assay-specific aligner selection|Expected compute requirement|Parameter preset recommendation|Mapping failure diagnosis|Alternative aligner comparison|Post-alignment QC checklist"),
    "differential_expression": _f("Design-matrix validation|Group-size assessment|Covariate recommendation|Batch-correction recommendation|Normalization recommendation|Statistical-method recommendation|Fold-change threshold guidance|Multiple-testing correction|Outlier handling|Low-count filtering|Contrast validation|Candidate-gene prioritization|Method selector|Sample-size suitability|Power estimation|Batch-effect diagnostics|Effect-size ranking|Stable-gene identification|Contradictory-result detection|Replication dataset recommendation|qPCR validation panel|Publication-ready result summary"),
    "biomarker_discovery": _f("Candidate ranking|Diagnostic/prognostic/predictive classification|Effect-size assessment|ROC/AUC evaluation|Sensitivity and specificity|Calibration|Cross-validation|Feature stability|Cohort reproducibility|Confounder sensitivity|Multi-marker panel recommendation|Validation assay recommendation|Nested cross-validation|Leakage detection|Single vs panel comparison|Decision-curve analysis|Subgroup performance|Threshold explorer|Validation cohort planner|Assay compatibility|Sample-type suitability|Translational readiness score|Biomarker evidence dossier"),
    "variant_prioritization": _f("Variant consequence|Allele frequency|Pathogenicity predictors|Conservation|Gene-disease association|Phenotype matching|Inheritance model|Population frequency|ClinVar status|ACMG-related evidence support|Splice-impact prediction|Functional evidence|Segregation evidence|Variant evidence aggregation|Transcript-aware interpretation|HPO phenotype matching|Family segregation workflow|Conflicting classification warning|Population-specific frequencies|Literature evidence|Functional validation recommendation|Reanalysis reminder|Research-only versus clinical distinction|Variant review audit trail"),
    "pathway_enrichment": _f("Pathway ranking|Database comparison|Background gene-set validation|Redundancy reduction|Directionality|Gene contribution|Leading-edge analysis|Pathway network|Multiple-testing correction|Pathway stability|Cross-database confirmation|Pathway clustering|Core driver genes|Activation/inhibition inference|Pathway evidence confidence|Network visualization|Literature-supported interpretation|Suggested validation assays|Pathway-specific experimental plan"),
    "multi_omics": _f("Omics-layer compatibility|Sample matching|Missing-layer handling|Normalization compatibility|Batch-effect comparison|Cross-omics correlation|Latent-factor interpretation|Multi-omics biomarker ranking|Conflict detection|Mechanistic integration|Layer contribution analysis|Integration method selector|Shared-sample checker|Layer completeness score|Cross-omics evidence graph|Concordant/discordant feature list|Multi-omics pathway models|Integrated biomarker panels|Experimental validation route|Omics-layer ablation analysis"),
    "single_cell": _f("Cell QC threshold recommendation|Doublet detection|Ambient RNA assessment|Batch integration|Clustering-resolution recommendation|Cell-type annotation confidence|Marker-gene support|Rare-cell detection|Differential abundance|Trajectory suitability|Pseudotime interpretation|Reference atlas matching|Dataset-adaptive QC thresholds|Annotation-method consensus|Marker-evidence table|Cell-label uncertainty|Reference-atlas comparison|Cluster stability analysis|Rare-cell validation plan|Pseudobulk recommendation|Differential-state analysis|Cell-cell communication recommendation|FACS or spatial validation"),
    "proteomics": _f("Protein identification confidence|Missing-value mechanism|Normalization recommendation|Batch correction|Differential abundance|Peptide-to-protein ambiguity|PTM handling|Pathway analysis|Protein-network analysis|Target validation|Missingness-aware imputation|Protein inference confidence|Instrument QC panel|Peptide coverage view|PTM recommendation workflow|DIA/DDA-specific guidance|Targeted proteomics validation|Western blot/ELISA/PRM recommendations|Protein-network prioritization"),
    "metabolomics": _f("Feature quality|Peak-quality assessment|Batch drift|Internal standard evaluation|Compound identification confidence|Pathway mapping|Adduct/isotope handling|Missing-value handling|Differential metabolite analysis|Validation standard recommendation|MSI identification confidence level|Peak and retention-time QC|Batch correction recommendation|Unknown-feature prioritization|Metabolic pathway interpretation|Targeted validation panel|Authentic-standard requirement|Instrument-method compatibility|Multi-omics integration with genes/proteins"),
    "microbiome": _f("Read-quality assessment|Contamination control|Taxonomic profiling method|Diversity analysis suitability|Compositional-data handling|Differential abundance method|Functional profiling|Confounder handling|Batch effect|Negative controls|Reference-database version|Compositional method recommendation|Contamination-risk score|Negative-control workflow|Rarefaction warning|Alpha/beta diversity guidance|Differential-abundance method comparison|Functional pathway recommendation|Strain-level confidence|Host metadata integration|Validation using qPCR or targeted sequencing"),
    "structural_biology": _f("Structure quality|Template confidence|Domain coverage|Residue-level confidence|Binding-pocket assessment|Mutation impact|Docking reliability|Alternative conformations|Experimental structure availability|Validation method|AlphaFold/PDB structure comparison|pLDDT/PAE interpretation|Disorder-region warning|Pocket-confidence score|Docking protocol recommendation|Mutation structural impact|Molecular-dynamics suitability|Experimental validation recommendation|Structure limitation notes"),
    "drug_target_discovery": _f("Target-disease evidence|Druggability|Genetic support|Pathway relevance|Tissue expression|Safety concerns|Essentiality|Existing compounds|Competitive landscape|Biomarker strategy|Validation experiments|Target evidence scorecard|Expression specificity|Essential-gene warning|Druggability assessment|Existing ligand analysis|Off-target risk|Target-validation experiment plan|Go/no-go criteria|Target product profile|Repurposing opportunities|Evidence graph"),
    "experimental_design": _f("Research question definition|Hypothesis|Primary endpoint|Experimental groups|Controls|Replicates|Randomization|Blinding|Sample-size calculation|Batch design|Inclusion/exclusion criteria|Statistical plan|Data-management plan|Power calculator|Minimum sample estimate|Replicate recommendation|Confounder checklist|Randomization planner|Batch allocation|Control-type recommendation|Assay-selection helper|Failure contingency plan|Estimated cost|Estimated duration|Reproducibility checklist"),
    "statistical_analysis": _f("Data-type detection|Distribution assessment|Paired/unpaired design|Repeated measures|Covariates|Multiple testing|Effect size|Confidence intervals|Model assumptions|Missing-data strategy|Sensitivity analysis|Statistical test recommender|Assumption checker|Parametric/non-parametric comparison|Mixed-model recommendation|Survival analysis guidance|Longitudinal analysis guidance|Multiple-testing method|Power analysis|Model diagnostic workflow|Robust alternative|Code and parameter export"),
    "literature_discovery": _f("Search-query builder|Entity extraction|Evidence ranking|Study-type classification|Publication date|Sample size|Organism/model|Contradictory evidence|Retraction/correction check|Duplicate-study detection|Citation provenance|Systematic-search builder|Evidence table|Study-quality assessment|Contradiction detection|Research-gap identification|Emerging-topic detection|Gene-disease-drug knowledge graph|Citation export|Saved literature collections|Evidence refresh workflow"),
    "hypothesis_generation": _f("Hypothesis statement|Supporting observations|Biological rationale|Testable prediction|Competing hypotheses|Required experiment|Falsification criteria|Evidence gaps|Risk|Novelty|Hypothesis generator|Hypothesis ranking|Supporting and contradictory evidence|Causal diagram|Experiment design|Expected observation|Null hypothesis|Failure interpretation|Novelty search|Hypothesis lifecycle tracking"),
    "laboratory_validation": _f("Validation objective|Recommended assay|Required samples|Controls|Replicates|Reagents|Expected signal|Acceptance criteria|Failure criteria|Alternative assay|Cost/time estimate|qPCR validation planner|ELISA validation planner|Western blot validation planner|Flow cytometry panel recommendation|CRISPR validation strategy|Knockdown/overexpression plan|Functional assay selection|Orthogonal method recommendation|SOP linkage|Results capture and comparison"),
    "generic_bioinformatics": _f("Input validation|Data-quality assessment|Evidence review|Uncertainty review|Alternative analysis|Validation route|Reproducibility review"),
}


def _r(ids: str, scores: str, columns: str, decisions: tuple[tuple[str, str, str], ...]) -> dict[str, Any]:
    return {"id": _f(ids), "scores": _f(scores), "columns": _f(columns), "decisions": decisions}


MODULE_RULES: dict[str, dict[str, Any]] = {
    "sequencing_quality": _r("sample|sample_id|read_id", "qc_score|mean_quality|quality", "cycle|mean_quality|adapter_read_fraction|duplicate_read_fraction|gc_fraction|read_length|overrepresented_sequence", (
        ("Trimming recommendation", "Trim adapters or low-quality tails only when observed metrics cross configured thresholds.", "Avoids unconditional trimming."),
        ("Resequencing recommendation", "Escalate samples below Q20 or below the configured retained-read requirement.", "Uses explicit blocking thresholds."),
        ("Sample exclusion recommendation", "Require sample-level failure evidence and reviewer approval before exclusion.", "Aggregate metrics are insufficient."),
        ("Platform-specific QC rules", "Use the declared platform profile; never infer a platform from sequence alone.", "Platform metadata is required."),
    )),
    "alignment_mapping": _r("sample|sample_id|contig", "mapping_rate|mapped_fraction|mean_mapq|coverage", "assay_type|reference_genome|annotation_version|mapping_rate|multimapping_fraction|duplicate_fraction|coverage|read_group", (
        ("Aligner recommendation", "Use STAR/HISAT2 for splice-aware short RNA, BWA-MEM2 for short DNA, and minimap2 for long reads.", "Rule uses assay, platform and read length."),
        ("Reference compatibility check", "Block interpretation until build, contigs and annotation release are compatible.", "Build mismatch changes coordinates."),
        ("Mapping-quality threshold", "Choose MAPQ after aligner-specific multimapping review.", "MAPQ scales are aligner dependent."),
        ("Alternative aligner comparison", "Benchmark a representative subset and compare mapping, runtime and failure modes.", "Provides a defensible fallback."),
    )),
    "differential_expression": _r("gene|gene_id|symbol|feature", "decision_score|log2_fold_change|log2fc|effect_size", "sample|group|condition|batch|fdr|padj|log2_fold_change|base_mean|contrast", (
        ("Statistical-method recommendation", "Use DESeq2/edgeR for raw counts or limma for appropriate transformed values.", "Method follows input scale."),
        ("Design-matrix validation", "Require non-confounded groups, valid contrasts and explicit covariates.", "Invalid design cannot support claims."),
        ("Low-count filtering", "Apply a prespecified information filter before multiple testing.", "Reduces unstable tests."),
        ("qPCR validation panel", "Select effect-size-stable candidates and qualified reference genes.", "Validation is separate from discovery."),
    )),
    "biomarker_discovery": _r("feature|biomarker|gene|protein", "decision_score|external_auc|cv_auc|auc|stability", "auc|sensitivity|specificity|calibration|selection_frequency|subgroup|external_auc|leakage_detected", (
        ("Nested cross-validation", "Keep feature selection, preprocessing and threshold tuning inside the inner loop.", "Prevents optimistic performance."),
        ("Leakage detection", "Block acceptance when data cross train/test boundaries.", "Leakage invalidates performance."),
        ("Single vs panel comparison", "Compare locked single-marker and parsimonious panel models under identical outer folds.", "Complexity must add reproducible value."),
        ("Validation assay recommendation", "Match the locked marker to an orthogonal assay and sample matrix.", "Feasibility is distinct from model performance."),
    )),
    "variant_prioritization": _r("variant|gene|symbol|id", "evidence_score|pathogenicity_score|cadd|revel|phenotype_match", "chrom|position|consequence|allele_frequency|gnomad_af|clinvar|acmg|hpo_score|inheritance|segregation", (
        ("ACMG-related evidence support", "Display criteria as evidence tags without automatic clinical classification.", "Preserves research-only status."),
        ("Transcript-aware interpretation", "Show consequence differences and record the selected transcript.", "Transcript choice changes interpretation."),
        ("Conflicting classification warning", "Keep conflicting and uncertain classifications visible.", "Negative evidence must not be hidden."),
        ("Reanalysis reminder", "Re-run against pinned newer releases on schedule.", "Variant knowledge changes."),
    )),
    "pathway_enrichment": _r("pathway|term|description|name", "pathway_priority|nes|enrichment_score|score", "fdr|q_value|genes|leading_edge|direction|database|background", (
        ("Background gene-set validation", "Use the measured/tested feature universe.", "An all-gene background can bias results."),
        ("Redundancy reduction", "Cluster terms by gene overlap and retain representative themes.", "Reduces repetition without hiding evidence."),
        ("Cross-database confirmation", "Compare pinned Reactome, GO and KEGG releases where possible.", "Agreement strengthens interpretation."),
        ("Pathway stability", "Repeat across reasonable ranking and background choices.", "Reports sensitivity."),
    )),
    "multi_omics": _r("feature|entity|gene", "integrated_score|correlation|loading|importance", "sample|layer|normalization|batch|correlation|latent_factor|direction", (
        ("Integration method selector", "Use MOFA, DIABLO, SNF or CCA only after endpoint and layer review.", "Method depends on design."),
        ("Sample matching", "Block integration until biospecimen identities are reconciled.", "Mismatches invalidate evidence."),
        ("Conflict detection", "Report concordant and discordant directions separately.", "Averaging can hide disagreement."),
        ("Omics-layer ablation analysis", "Re-fit while removing one layer at a time.", "Quantifies layer contribution."),
    )),
    "single_cell": _r("cell_type|cluster|gene", "annotation_confidence|marker_score|log2fc|score", "n_genes|total_counts|pct_mito|doublet_score|cluster|cell_type|sample|batch", (
        ("Dataset-adaptive QC thresholds", "Start from robust quantiles/MAD and inspect each sample.", "Fixed thresholds do not transfer."),
        ("Cell-type annotation confidence", "Combine marker support, reference mapping and independent methods.", "A single source is insufficient."),
        ("Pseudobulk recommendation", "Use sample-level pseudobulk for replicated differential-state tests.", "Cells are not biological replicates."),
        ("FACS or spatial validation", "Validate rare populations with orthogonal markers.", "Confirms identity and localization."),
    )),
    "proteomics": _r("protein|protein_id|accession|gene", "priority_score|log2fc|effect_size|identification_confidence", "abundance|peptide_count|unique_peptides|fdr|missing_fraction|ptm|run_qc|acquisition_mode", (
        ("Missingness-aware imputation", "Model missingness by acquisition and include a no-imputation sensitivity analysis.", "Blind imputation can create signal."),
        ("Peptide-to-protein ambiguity", "Expose shared peptides and unique/razor evidence.", "Inference uncertainty must remain visible."),
        ("DIA/DDA-specific guidance", "Use acquisition-specific library, FDR and missingness rules.", "Evidence behavior differs."),
        ("Targeted proteomics validation", "Confirm by PRM/SRM plus an orthogonal assay.", "Separates discovery and validation."),
    )),
    "metabolomics": _r("metabolite|compound|feature|feature_id", "priority_score|log2fc|effect_size|peak_quality", "peak_quality|retention_time|batch|internal_standard|msi_level|adduct|isotope|fdr", (
        ("MSI identification confidence level", "Report MSI level; level 1 requires an authentic matched standard.", "Prevents identity overclaiming."),
        ("Batch drift", "Use pooled QC trends and internal standards.", "Run order is required."),
        ("Adduct/isotope handling", "Collapse related features with traceable rules.", "Prevents double counting."),
        ("Validation standard recommendation", "Require an authentic standard for confirming identity.", "Similarity alone is insufficient."),
    )),
    "microbiome": _r("taxon|feature|pathway", "priority_score|effect_size|prevalence|abundance", "sample|count|relative_abundance|negative_control|batch|database_version|diversity|host_metadata", (
        ("Compositional-data handling", "Use ANCOM-BC/ALDEx2 or a justified log-ratio workflow.", "Relative abundance is constrained."),
        ("Negative-control workflow", "Include extraction blanks through the same pipeline.", "Contamination can dominate."),
        ("Rarefaction warning", "Use rarefaction for coverage visualization, not automatic differential testing.", "Discarding reads reduces information."),
        ("Validation using qPCR or targeted sequencing", "Confirm priority taxa/functions with a targeted method.", "Classification is not validation."),
    )),
    "structural_biology": _r("residue|position|pocket|mutation", "pocket_score|plddt|confidence|docking_score", "plddt|pae|domain|coverage|template_identity|pocket|docking|experimental_structure", (
        ("AlphaFold/PDB structure comparison", "Prefer qualified experimental structures and compare local confidence.", "Model confidence is not validation."),
        ("pLDDT/PAE interpretation", "Use local and pairwise confidence; flag weak regions.", "Global scores can hide uncertainty."),
        ("Docking reliability", "Treat docking rank as a hypothesis and verify measured affinity.", "Scores are protocol dependent."),
        ("Molecular-dynamics suitability", "Run dynamics only for a defined question and qualified system.", "Simulation does not repair weak structure."),
    )),
    "drug_target_discovery": _r("target|gene|protein", "evidence_score|genetic_score|druggability|disease_score", "genetic_evidence|disease_evidence|druggability|tissue_expression|safety|essentiality|existing_ligands|off_target", (
        ("Target evidence scorecard", "Keep genetics, disease, tractability, expression and safety decomposed.", "Opaque scores are insufficient."),
        ("Essential-gene warning", "Flag broadly essential targets before go/no-go.", "Essentiality can remove the safety window."),
        ("Off-target risk", "Screen homologs, pathway neighbors and ligand polypharmacology.", "Negative evidence remains visible."),
        ("Validation experiments", "Require perturbation, rescue and target-engagement assays.", "Ranking is not validation."),
    )),
    "experimental_design": _r("group|endpoint|factor", "power|feasibility_score|priority", "research_question|hypothesis|primary_endpoint|group|control|effect_size|alpha|power|batch", (
        ("Randomization", "Generate a reproducible sequence stratified by blocking factors.", "Reduces allocation bias."),
        ("Blinding", "Blind acquisition and outcome assessment where feasible.", "Reduces observer bias."),
        ("Batch allocation", "Distribute groups across batches.", "Avoids condition/run confounding."),
        ("Failure contingency plan", "Predefine QC failure, dropout and deviation handling.", "Reduces post-hoc decisions."),
    )),
    "statistical_analysis": _r("variable|feature|endpoint", "effect_size|importance|score", "outcome_type|design|paired|repeated_measures|covariate|p_value|fdr|effect_size|confidence_interval", (
        ("Statistical test recommender", "Select from outcome type, dependence, covariates and assumptions.", "No one test fits every design."),
        ("Multiple-testing method", "Use BH-FDR for exploratory families or a prespecified confirmatory correction.", "Multiplicity must match inference."),
        ("Robust alternative", "Run a robust/non-parametric sensitivity analysis.", "Stability matters."),
        ("Code and parameter export", "Export formula, contrasts, filters, seed and versions.", "Enables reproduction."),
    )),
    "literature_discovery": _r("title|doi|pmid|citation", "evidence_score|quality_score|sample_size|year", "title|doi|pmid|study_type|year|sample_size|organism|contradictory|retracted", (
        ("Systematic-search builder", "Record databases, query, dates, filters and screening rules.", "Makes retrieval reproducible."),
        ("Contradictory evidence", "Retain negative/null findings and code direction.", "Consensus must not hide disagreement."),
        ("Gene-disease-drug knowledge graph", "Create edges only from cited rows.", "Prevents unsupported relationships."),
        ("Evidence refresh workflow", "Save search date and rerun the pinned query on schedule.", "Evidence changes."),
    )),
    "hypothesis_generation": _r("hypothesis|statement|id", "testability_score|evidence_score|novelty_score", "hypothesis|observation|rationale|prediction|competing_hypothesis|falsification|experiment|novelty", (
        ("Hypothesis generator", "Transform supplied observations into a bounded testable statement; never invent observations.", "Maintains integrity."),
        ("Null hypothesis", "Define no-effect using the same endpoint and population.", "Supports formal testing."),
        ("Competing hypotheses", "Record an alternative mechanism and discriminating observation.", "Reduces confirmation bias."),
        ("Novelty search", "Search a saved evidence corpus before lab prioritization.", "Novelty is not assumed."),
    )),
    "laboratory_validation": _r("assay|candidate|target", "feasibility_score|priority|expected_signal", "validation_objective|analyte_type|assay|samples|controls|replicates|reagents|acceptance_criteria|sop", (
        ("Recommended assay", "Select from analyte, dynamic range, matrix and objective.", "Assay choice is context dependent."),
        ("Controls", "Include positive, negative and process/assay-specific controls.", "Controls cover failure modes."),
        ("Replicates", "Use independent biological replicates.", "Technical replicates do not replace them."),
        ("SOP linkage", "Link approved SOP, equipment method and reagent lots.", "Required for audit."),
    )),
    "generic_bioinformatics": _r("entity|feature|id", "score|priority|confidence", "", (
        ("Validation route", "Select a module-specific engine or document generic use.", "Generic review cannot replace assay logic."),
    )),
}

RULE_CATALOG_VERSION = "Step218.1"

