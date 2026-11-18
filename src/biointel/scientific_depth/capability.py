from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

import pandas as pd

from .evidence_readiness import EvidenceReadiness, assess_evidence_readiness
from .profiles import MODULE_PROFILES, profile_for


@dataclass(frozen=True)
class PipelineStage:
    key: str
    label: str
    mode: str
    purpose: str
    required_columns: tuple[str, ...] = ()
    engines: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    validation_gate: str = ""


@dataclass(frozen=True)
class ModuleCapabilitySpec:
    module_key: str
    title: str
    stages: tuple[PipelineStage, ...]
    release_blockers: tuple[str, ...]
    evidence_boundary: str


@dataclass(frozen=True)
class CapabilityAssessment:
    module_key: str
    tier: str
    tier_label: str
    coverage: float
    built_in_ready: int
    adapter_ready: int
    blocked: int
    release_ready: bool
    readiness_score: float
    readiness_grade: str
    stage_table: pd.DataFrame
    quality_checks: pd.DataFrame
    evidence_table: pd.DataFrame
    blockers: tuple[str, ...]
    evidence_readiness: EvidenceReadiness
    manifest: dict[str, Any]


def _stage(
    key: str,
    label: str,
    mode: str,
    purpose: str,
    *,
    columns: Iterable[str] = (),
    engines: Iterable[str] = (),
    references: Iterable[str] = (),
    validation: str = "",
) -> PipelineStage:
    return PipelineStage(
        key=key,
        label=label,
        mode=mode,
        purpose=purpose,
        required_columns=tuple(columns),
        engines=tuple(engines),
        references=tuple(references),
        validation_gate=validation,
    )


# Step 120 converts the weakest scientific workspaces from an undifferentiated
# table renderer into explicit domain pipelines.  Stages marked "adapter" are
# intentionally not reported as executable unless every requested engine is
# detected.  "external-validation" stages are never auto-passed by software.
_CAPABILITY_SPECS: tuple[ModuleCapabilitySpec, ...] = (
    ModuleCapabilitySpec(
        "epigenomics_chromatin",
        "Epigenomics & chromatin",
        (
            _stage("region_qc", "Region and replicate QC", "built-in", "Validate genomic intervals, replicate balance, signal ranges and genome-build metadata.", columns=("region", "condition", "signal"), validation="Replicate and interval checks pass"),
            _stage("peak_calling", "Peak calling", "adapter", "Run control-aware peak calling and retain caller/version provenance.", engines=("macs2",), references=("Reference FASTA",), validation="Peak caller logs and controls reviewed"),
            _stage("signal_tracks", "Signal tracks and enrichment", "adapter", "Create normalized coverage tracks and FRiP/TSS-style summaries.", engines=("samtools", "deeptools"), references=("Gene annotation",), validation="Library QC thresholds prespecified"),
            _stage("differential", "Replicate-aware differential analysis", "built-in", "Generate effect sizes, p-values, FDR and replicate-balance diagnostics from harmonized region tables.", columns=("region", "condition", "signal"), validation="Design and multiplicity reviewed"),
            _stage("motif", "Motif and regulatory interpretation", "adapter", "Annotate candidate regions with pinned motif/reference assets.", references=("Motif database", "Gene annotation"), validation="Reference release recorded"),
            _stage("orthogonal", "Orthogonal confirmation", "external-validation", "Confirm priority regions using an independent assay or validated reference workflow.", validation="Independent evidence attached"),
        ),
        ("Genome build is missing or mixed", "No replicate-aware design", "No peak/control provenance", "No independent confirmation"),
        "Region rankings remain exploratory until peak calling, genome-build harmonisation, replicate-aware statistics and orthogonal evidence are complete.",
    ),
    ModuleCapabilitySpec(
        "metabolomics_lipidomics",
        "Metabolomics & lipidomics",
        (
            _stage("raw_conversion", "Raw conversion", "adapter", "Convert supported vendor files to mzML while recording converter version and checksums.", engines=("msconvert",), validation="Raw-to-mzML conversion log retained"),
            _stage("feature_detection", "Peak detection and alignment", "adapter", "Perform peak picking, retention-time correction, alignment and deconvolution.", engines=("openms",), references=("Adduct table",), validation="Peak parameters and QC pool recorded"),
            _stage("qc_filtering", "Blank and pooled-QC filtering", "built-in", "Calculate missingness, CV, blank ratio and batch/QC drift flags.", columns=("feature", "intensity"), validation="Blank/QC thresholds prespecified"),
            _stage("statistics", "Differential abundance", "built-in", "Produce effect sizes, FDR and transparent group comparisons from aligned feature tables.", columns=("feature", "group", "intensity"), validation="Replicates and normalization reviewed"),
            _stage("identification", "MS/MS identification", "adapter", "Match spectra against versioned libraries and retain score, decoy and confidence evidence.", engines=("openms",), references=("Spectral library", "Retention-time standards"), validation="Identification confidence level assigned"),
            _stage("standards", "Authentic-standard confirmation", "external-validation", "Confirm high-priority identities with authentic standards and retention time.", validation="Standard and MS/MS evidence attached"),
        ),
        ("No pooled-QC/blank samples", "No MS/MS or spectral-library evidence", "Identification confidence not recorded", "No authentic-standard confirmation"),
        "A mass feature is not a confirmed metabolite or lipid without appropriate MS/MS, retention-time and standard evidence.",
    ),
    ModuleCapabilitySpec(
        "bioimage_microscopy",
        "Bioimage & microscopy",
        (
            _stage("metadata", "Image metadata and calibration", "built-in", "Validate image/object identifiers, pixel calibration, channel metadata and condition balance.", columns=("image_id", "object_id", "condition"), validation="Pixel and channel metadata reviewed"),
            _stage("correction", "Illumination and registration", "adapter", "Apply tiled illumination correction, registration and stitching with saved transforms.", references=("Calibration image",), validation="Correction residuals reviewed"),
            _stage("segmentation", "Segmentation", "adapter", "Run Cellpose/StarDist-style segmentation in bounded tiles and save masks plus model metadata.", engines=("cellpose", "stardist"), references=("Segmentation model",), validation="Representative masks manually reviewed"),
            _stage("phenotyping", "Object phenotyping", "built-in", "Summarize morphology, intensity and condition effects with outlier and batch flags.", columns=("image_id", "object_id", "condition"), validation="Image is the experimental unit where appropriate"),
            _stage("tracking", "Time-lapse/3D tracking", "adapter", "Link objects across frames or z-stacks and report ambiguous tracks.", validation="Track quality and split/merge events reviewed"),
            _stage("ground_truth", "Ground-truth validation", "external-validation", "Compare masks/classes against representative manual annotations using Dice/IoU and error review.", references=("Ground-truth annotations",), validation="Acceptance criteria met"),
        ),
        ("Pixel calibration absent", "Segmentation model/version absent", "No representative manual review", "No ground-truth accuracy evidence"),
        "Automated segmentation and phenotyping require representative ground-truth review before scientific interpretation.",
    ),
    ModuleCapabilitySpec(
        "spatial_omics_pathology",
        "Spatial omics & digital pathology",
        (
            _stage("coordinate_qc", "Coordinate and assay QC", "built-in", "Validate coordinates, duplicate spots/cells, region labels, missingness and sample balance.", columns=("spot", "x", "y", "gene", "expression"), validation="Coordinate and sample QC pass"),
            _stage("registration", "Histology registration", "adapter", "Register tissue image and molecular coordinates while preserving transforms and residuals.", engines=("openslide",), references=("Tissue image", "Spatial assay manifest"), validation="Registration landmarks reviewed"),
            _stage("segmentation", "Cell/tissue segmentation", "adapter", "Run tiled segmentation with model/version provenance and manual correction handoff.", engines=("cellpose",), validation="Segmentation QC accepted"),
            _stage("domains", "Spatial domains and neighborhoods", "built-in", "Calculate region contrasts, neighborhood composition and spatial autocorrelation from harmonized tables.", columns=("x", "y", "region", "expression"), validation="Permutation/statistical assumptions reviewed"),
            _stage("deconvolution", "Cell-type deconvolution", "adapter", "Map spots/cells to a pinned reference atlas and report uncertainty.", references=("Reference atlas",), validation="Atlas compatibility and uncertainty reviewed"),
            _stage("pathology_review", "Pathology review", "external-validation", "Attach pathologist/assay-review decisions for clinically relevant regions.", validation="Independent tissue review attached"),
        ),
        ("Image-coordinate registration not reviewed", "No sample/section replication", "Reference atlas not pinned", "No pathology review"),
        "Spatial patterns remain exploratory until registration, segmentation, batch correction, replication and pathology review are complete.",
    ),
    ModuleCapabilitySpec(
        "glycomics_glycoproteomics",
        "Glycomics & glycoproteomics",
        (
            _stage("spectrum_qc", "Spectrum and precursor QC", "built-in", "Review abundance, confidence, missingness and candidate/site consistency.", columns=("glycan", "site", "abundance", "confidence"), validation="Acquisition and precursor QC reviewed"),
            _stage("search", "Glycan/glycopeptide search", "adapter", "Search spectra against a versioned glycan/protein database with decoys.", engines=("openms",), references=("Glycan database", "Protein annotation"), validation="Search space and decoy policy recorded"),
            _stage("fdr", "PSM/glycopeptide FDR", "built-in", "Apply q-value/FDR checks when score/decoy fields are provided and block unsupported claims.", validation="FDR threshold met"),
            _stage("localization", "Site localization", "built-in", "Track localization confidence and flag ambiguous sites.", columns=("site", "confidence"), validation="Localization threshold prespecified"),
            _stage("fragments", "Fragment evidence review", "adapter", "Display and verify diagnostic ions and fragment-level support.", references=("Fragment rules",), validation="Manual spectrum review complete"),
            _stage("orthogonal", "Orthogonal confirmation", "external-validation", "Confirm selected glycoforms/sites using an independent method.", validation="Independent confirmation attached"),
        ),
        ("No decoy/FDR evidence", "Site localization confidence absent", "No fragment-level review", "No orthogonal confirmation"),
        "Glycan and glycopeptide assignments require spectrum-level evidence, controlled FDR and site-localization review.",
    ),
    ModuleCapabilitySpec(
        "proteogenomics_neoantigen",
        "Proteogenomics & neoantigen discovery",
        (
            _stage("variant_proteome", "Variant-derived proteome", "adapter", "Normalize variants and create a provenance-linked custom protein database.", engines=("bcftools",), references=("Reference proteome",), validation="Variant-to-protein traceability complete"),
            _stage("search", "Target-decoy spectrum search", "adapter", "Run a registered peptide-spectrum engine with an explicit target-decoy search space.", engines=("comet", "msgfplus"), validation="Search logs and database hashes retained"),
            _stage("fdr", "PSM/peptide/protein FDR", "built-in", "Evaluate q-values/decoys when supplied and block high-FDR candidates.", validation="PSM, peptide and protein thresholds met"),
            _stage("integration", "Multi-layer evidence integration", "built-in", "Combine expression, spectral score, clonality and HLA evidence without converting proxies into measured facts.", columns=("expression", "spectral_score", "hla_binding", "clonality"), validation="At least two independent evidence layers"),
            _stage("hla", "HLA and antigen-processing review", "adapter", "Use a pinned HLA call and prediction engine with population/context metadata.", references=("HLA alleles",), validation="HLA provenance and thresholds reviewed"),
            _stage("immune_validation", "Functional immune validation", "external-validation", "Confirm selected candidates using orthogonal peptide and immune-function assays.", validation="Independent functional evidence attached"),
        ),
        ("No target-decoy FDR", "No variant-to-protein provenance", "HLA call/version absent", "No functional immune validation"),
        "Neoantigen candidates remain hypotheses until peptide identity, tumour specificity and immune function are independently validated.",
    ),
    ModuleCapabilitySpec(
        "population_gwas",
        "Population genetics & GWAS",
        (
            _stage("sample_qc", "Sample and variant QC", "built-in", "Review missingness, allele frequency, duplicates and phenotype/covariate completeness.", columns=("variant", "maf", "missingness"), validation="QC exclusions and thresholds recorded"),
            _stage("ancestry", "Ancestry and relatedness", "adapter", "Compute PCA/kinship and identify ancestry/relatedness structure.", engines=("plink2",), references=("Reference panel",), validation="Ancestry and relatedness plan reviewed"),
            _stage("association", "Association model", "adapter", "Run PLINK2/REGENIE/SAIGE-style models appropriate to outcome balance and relatedness.", engines=("plink2", "regenie", "saige"), validation="Model, covariates and convergence recorded"),
            _stage("summary_qc", "Summary-statistics QC", "built-in", "Apply FDR, genomic-control and result sanity checks when compatible fields are supplied.", columns=("variant", "p_value"), validation="Inflation and calibration reviewed"),
            _stage("rare_variants", "Rare-variant burden", "adapter", "Run gene/set tests with annotation masks and ancestry-aware controls.", engines=("regenie", "saige"), references=("Gene annotation",), validation="Mask definitions and multiplicity recorded"),
            _stage("replication", "Independent replication", "external-validation", "Replicate priority associations in an independent cohort.", validation="Replication evidence attached"),
        ),
        ("Ancestry/relatedness not modelled", "Outcome/covariate definition not locked", "No suitable association engine", "No independent replication"),
        "Association is not causation and requires ancestry-aware QC, robust modelling and independent replication.",
    ),
    ModuleCapabilitySpec(
        "structural_variant_repeat",
        "Structural variant & repeat expansion",
        (
            _stage("interval_qc", "Breakpoint and interval QC", "built-in", "Validate intervals, SV types, support values and sample/caller metadata.", validation="Invalid intervals resolved"),
            _stage("calling", "SV/repeat calling", "adapter", "Run caller-specific workflows for short or long reads with versioned parameters.", engines=("sniffles", "expansionhunter"), references=("Reference FASTA",), validation="Caller QC and input suitability reviewed"),
            _stage("consensus", "Multi-caller consensus", "built-in", "Cluster compatible calls, expose caller agreement and avoid silently merging ambiguous events.", validation="Consensus tolerance recorded"),
            _stage("evidence", "Read-evidence review", "adapter", "Review split-read, paired-end, read-depth or long-read support.", engines=("samtools",), validation="Supporting reads inspected"),
            _stage("annotation", "Gene/clinical annotation", "adapter", "Annotate breakpoints and overlap against pinned gene/population references.", engines=("vep",), references=("Gene annotation", "Population SV reference"), validation="Build and reference release recorded"),
            _stage("confirmation", "Orthogonal confirmation", "external-validation", "Confirm clinically or biologically important events using an independent method.", validation="Confirmation attached"),
        ),
        ("Caller/support provenance absent", "Genome build missing", "No read-evidence review", "No orthogonal confirmation"),
        "SV and repeat-expansion calls require read-level review and orthogonal confirmation for high-impact interpretation.",
    ),
    ModuleCapabilitySpec(
        "rna_isoform_splicing",
        "RNA isoform & alternative splicing",
        (
            _stage("annotation_qc", "Transcript/junction QC", "built-in", "Validate transcript identifiers, junction support, replicate balance and fraction bounds.", validation="Annotation/build and replicate QC pass"),
            _stage("quantification", "Isoform quantification", "adapter", "Quantify transcripts/junctions using a pinned transcriptome and strand-aware settings.", references=("Transcript annotation",), validation="Quantifier and annotation version recorded"),
            _stage("events", "Splicing event detection", "adapter", "Run rMATS/MAJIQ/SUPPA-style event analysis with replicate-aware uncertainty.", engines=("rmats", "majiq", "suppa2"), validation="Event model and coverage filters recorded"),
            _stage("statistics", "Differential splicing", "built-in", "Compute effect sizes/FDR from compatible event tables and flag low support.", validation="Multiplicity and minimum-support gates met"),
            _stage("visual_review", "Sashimi/read-evidence review", "adapter", "Inspect junction/read support for priority events.", engines=("samtools",), validation="Priority events visually reviewed"),
            _stage("confirmation", "Orthogonal confirmation", "external-validation", "Confirm selected events by an independent assay.", validation="Independent confirmation attached"),
        ),
        ("Annotation/build not pinned", "Replicate-aware event model absent", "Junction support not reviewed", "No orthogonal confirmation"),
        "Splicing conclusions require strand-aware, coverage-aware, replicate-aware analysis and independent confirmation.",
    ),
    ModuleCapabilitySpec(
        "pharmacogenomics",
        "Pharmacogenomics & precision medicine",
        (
            _stage("variant_qc", "Variant normalization and build QC", "adapter", "Normalize variants, verify genome build and retain caller/filter provenance.", engines=("bcftools",), references=("Reference FASTA",), validation="Build and normalization checks pass"),
            _stage("phasing", "Phasing and CNV-aware allele calling", "adapter", "Resolve haplotypes and copy-number-sensitive loci with versioned allele definitions.", engines=("whatshap",), references=("Allele-definition release",), validation="Phasing/CNV uncertainty recorded"),
            _stage("star_alleles", "Star-allele/diplotype interpretation", "built-in", "Require explicit allele-definition, diplotype and phenotype evidence fields; flag incomplete records.", columns=("gene", "drug", "phenotype", "evidence_level"), validation="Allele definition and phenotype mapping reviewed"),
            _stage("guidelines", "Guideline evidence mapping", "adapter", "Map to pinned CPIC/DPWG-style evidence without issuing autonomous dose instructions.", references=("Guideline release",), validation="Guideline version and evidence level recorded"),
            _stage("report", "Human-review report", "built-in", "Generate an uncertainty-aware clinician/research review package with no autonomous treatment recommendation.", validation="Qualified human review required"),
            _stage("clinical_validation", "Clinical validation", "external-validation", "Validate the complete workflow under an approved clinical governance process.", validation="Regulated validation and authorization attached"),
        ),
        ("Genome build/allele release absent", "Phasing or CNV uncertainty unresolved", "Guideline version absent", "No qualified human review"),
        "This research module must not issue treatment or dose instructions and is not a validated clinical decision-support system.",
    ),
    ModuleCapabilitySpec(
        "docking_dynamics",
        "Molecular docking & dynamics",
        (
            _stage("preparation", "Receptor and ligand preparation", "adapter", "Prepare structures, protonation/tautomer states and search box with explicit provenance.", engines=("obabel",), references=("Prepared receptor",), validation="Preparation and box reviewed"),
            _stage("docking", "Docking execution", "adapter", "Run registered Vina-style docking with saved command, seed and logs.", engines=("vina",), validation="Redocking/control protocol recorded"),
            _stage("pose_qc", "Pose and interaction QC", "built-in", "Compare score, RMSD, strain and interaction occupancy; flag implausible or duplicate poses.", columns=("ligand", "pose", "docking_score", "rmsd"), validation="Pose quality thresholds reviewed"),
            _stage("consensus", "Consensus/rescoring", "built-in", "Support transparent consensus ranking when multiple score fields are supplied.", validation="Consensus method prespecified"),
            _stage("dynamics", "Molecular dynamics", "adapter", "Run checkpointed GROMACS/OpenMM trajectories through background execution.", engines=("gromacs", "openmm"), references=("Force-field assets",), validation="Equilibration and convergence reviewed"),
            _stage("affinity", "Experimental affinity confirmation", "external-validation", "Link priority poses to measured affinity and orthogonal binding evidence.", validation="Measured affinity attached"),
        ),
        ("Preparation/protonation provenance absent", "No redocking or positive control", "No convergence/equilibration review", "No measured affinity"),
        "Docking and simulation scores are model-dependent and must not be represented as measured binding affinity.",
    ),
    ModuleCapabilitySpec(
        "antibody_biologics",
        "Antibody & biologics engineering",
        (
            _stage("numbering", "Numbering and germline assignment", "adapter", "Apply ANARCI/IgBLAST-style numbering, CDR annotation and germline assignment.", engines=("anarci", "igblast"), references=("IMGT germlines",), validation="Numbering and chain pairing reviewed"),
            _stage("sequence_qc", "Sequence and liability QC", "built-in", "Validate sequences and screen common developability liabilities with explicit proxy labels.", validation="Sequence syntax and liabilities reviewed"),
            _stage("humanization", "Humanization analysis", "adapter", "Compare framework/CDR choices against pinned germlines and structural constraints.", references=("IMGT germlines", "Structure templates"), validation="Back-mutation rationale reviewed"),
            _stage("developability", "Developability triage", "built-in", "Integrate affinity, stability, humanness, aggregation and liability evidence with missing-assay flags.", columns=("variant", "affinity", "stability", "humanness", "aggregation_risk"), validation="Assay provenance and uncertainty reviewed"),
            _stage("structure", "Structure/paratope review", "adapter", "Load structure templates and record paratope/epitope hypotheses.", references=("Structure templates",), validation="Structural model quality reviewed"),
            _stage("experimental", "Experimental confirmation", "external-validation", "Confirm affinity, specificity, aggregation and manufacturability in validated assays.", validation="Independent assay package attached"),
        ),
        ("Numbering/germline assignment absent", "Chain pairing/CDR definition uncertain", "Developability assays missing", "No experimental confirmation"),
        "Computational developability and humanization scores do not establish efficacy, manufacturability or clinical safety.",
    ),
    ModuleCapabilitySpec(
        "immunoinformatics_vaccine",
        "Immunoinformatics & vaccine design",
        (
            _stage("peptide_qc", "Peptide and allele QC", "built-in", "Validate peptide syntax/length, allele nomenclature, duplicates and source-protein provenance.", columns=("peptide", "allele"), validation="Peptide and allele QC pass"),
            _stage("binding", "MHC binding prediction", "adapter", "Run versioned MHC-I/MHC-II predictors and retain percentile/rank outputs.", engines=("netmhcpan", "netmhciipan"), validation="Predictor/version and thresholds recorded"),
            _stage("processing", "Antigen-processing evidence", "adapter", "Assess proteasomal/TAP or processing evidence where supported.", references=("Pathogen proteome",), validation="Processing assumptions reviewed"),
            _stage("coverage", "Population and conservancy analysis", "built-in", "Summarize allele coverage, conservancy and candidate redundancy from supplied evidence.", validation="Population source and allele frequencies recorded"),
            _stage("safety", "Safety and similarity review", "built-in", "Flag toxicity/allergenicity proxies and host-similarity evidence without claiming safety.", references=("Allergen/toxin references",), validation="Safety evidence reviewed"),
            _stage("immunogenicity", "Experimental immunogenicity", "external-validation", "Validate selected candidates in appropriate immune assays and populations.", validation="Independent immunogenicity/safety evidence attached"),
        ),
        ("Predictor/version absent", "Population frequencies not pinned", "Host similarity/safety review absent", "No experimental immunogenicity"),
        "In-silico epitope predictions are hypotheses and require experimental immunogenicity and safety validation.",
    ),
    ModuleCapabilitySpec(
        "single_cell_trajectory",
        "Single-cell trajectory & communication",
        (
            _stage("cell_qc", "Cell/sample QC", "built-in", "Review cell labels, group sizes, missingness, annotation confidence and replicate structure.", validation="Cell and sample QC pass"),
            _stage("batch", "Batch integration", "adapter", "Integrate samples while preserving biological condition and recording latent-model parameters.", engines=("scanpy",), references=("Cell atlas",), validation="Batch mixing and signal preservation reviewed"),
            _stage("trajectory", "Trajectory/velocity inference", "adapter", "Run Scanpy/scVelo/CellRank-style trajectory inference with uncertainty.", engines=("scanpy", "scvelo", "cellrank"), validation="Root/direction assumptions and uncertainty reviewed"),
            _stage("communication", "Ligand-receptor communication", "built-in", "Rank supplied ligand-receptor candidates and expose expression/support limitations.", references=("Ligand-receptor database",), validation="Database release and sample replication recorded"),
            _stage("replicate_stats", "Replicate-aware testing", "built-in", "Require sample/replicate-level inference rather than treating cells as independent replicates.", validation="Pseudobulk/mixed model reviewed"),
            _stage("validation", "Biological validation", "external-validation", "Confirm lineage direction or communication candidates using independent evidence.", validation="Independent evidence attached"),
        ),
        ("Biological replicates not identified", "Trajectory root/direction not justified", "Atlas/database version absent", "No independent validation"),
        "Trajectory and communication results are model-dependent and require replicate-aware biological validation.",
    ),
    ModuleCapabilitySpec(
        "cell_atlas_mapping",
        "Cell atlas mapping",
        (
            _stage("query_qc", "Query-cell QC", "built-in", "Review cell identifiers, cluster sizes, annotation confidence and batch composition.", validation="Query QC passes"),
            _stage("reference", "Reference atlas compatibility", "adapter", "Validate feature space, organism/tissue, assay and atlas release compatibility.", engines=("scanpy",), references=("Cell atlas",), validation="Atlas compatibility documented"),
            _stage("mapping", "Probabilistic mapping", "adapter", "Run a registered mapping model and retain uncertainty/nearest-reference evidence.", engines=("scanpy",), validation="Confidence and OOD thresholds recorded"),
            _stage("marker_review", "Marker agreement", "built-in", "Compare supplied marker-agreement and similarity metrics and flag discordant cells/clusters.", columns=("reference_label", "similarity", "marker_agreement"), validation="Discordant mappings reviewed"),
            _stage("batch_review", "Batch and subgroup review", "built-in", "Assess mapping confidence across batches and query clusters.", validation="Subgroup performance accepted"),
            _stage("orthogonal", "Orthogonal annotation review", "external-validation", "Confirm critical labels using expert/experimental evidence.", validation="Independent review attached"),
        ),
        ("Atlas release/compatibility absent", "No OOD/confidence policy", "Batch-specific failures not reviewed", "No independent annotation review"),
        "Reference mapping is probabilistic and does not replace expert marker and biological-context review.",
    ),
    ModuleCapabilitySpec(
        "genome_editing_safety",
        "Genome editing safety",
        (
            _stage("guide_qc", "Guide syntax and basic QC", "built-in", "Validate guide sequence, length, duplicates and supplied target metadata.", validation="Guide QC passes"),
            _stage("genome_search", "Genome-wide off-target search", "adapter", "Search a pinned genome allowing mismatches/bulges with explicit parameters.", engines=("bowtie2", "blastn"), references=("Reference genome",), validation="Search space and genome build recorded"),
            _stage("variant_overlap", "Population-variant overlap", "adapter", "Intersect guide/off-target sites with a versioned population reference.", engines=("bcftools",), references=("Population VCF",), validation="Population reference release recorded"),
            _stage("annotation", "Functional annotation", "built-in", "Rank supplied off-target evidence and flag coding/regulatory overlaps.", references=("Annotation GTF/GFF",), validation="Annotation build matches genome"),
            _stage("risk_report", "Uncertainty-aware risk report", "built-in", "Separate in-silico specificity from measured editing safety and preserve all candidate sites.", validation="No automatic safety claim"),
            _stage("assay", "Orthogonal safety assay", "external-validation", "Confirm editing specificity and major off-target risks experimentally.", validation="Independent safety assay attached"),
        ),
        ("Genome build/reference missing", "Bulge/mismatch search incomplete", "Population variants not considered", "No orthogonal safety assay"),
        "In-silico specificity is not proof of editing safety.",
    ),
)


CAPABILITY_SPECS: dict[str, ModuleCapabilitySpec] = {spec.module_key: spec for spec in _CAPABILITY_SPECS}


CAPABILITY_SPECS["flow_cytometry"] = ModuleCapabilitySpec(
    "flow_cytometry",
    "Flow cytometry",
    (
        _stage("fcs_qc", "FCS/event acquisition QC", "built-in", "Validate event count, channel completeness, saturation, duplicates and acquisition-time drift.", validation="Acquisition QC reviewed"),
        _stage("compensation", "Spillover compensation", "built-in", "Validate and apply an explicit square compensation matrix with numerical-stability checks.", validation="Single-stained controls and matrix provenance attached"),
        _stage("transform", "Locked transformation", "built-in", "Apply a recorded arcsinh transformation and preserve untransformed source data.", validation="Cofactor and channels locked"),
        _stage("gating", "Hierarchical gating", "built-in", "Apply singlet and rectangular/polygon gates with parent fractions and audit metadata.", validation="Gate hierarchy and controls reviewed"),
        _stage("controls", "FMO/unstained control thresholds", "built-in", "Calculate control-derived thresholds when control events are supplied; label percentile-only thresholds exploratory.", validation="Controls match panel and acquisition settings"),
        _stage("reproducibility", "Manual and cross-run validation", "external-validation", "Compare representative manual gates and repeat runs/panels before reporting populations.", validation="Independent gating/reproducibility evidence attached"),
    ),
    ("Compensation controls absent", "FMO/unstained controls absent", "Gate hierarchy not independently reviewed", "Panel/instrument QC metadata incomplete"),
    "Flow-cytometry populations require instrument QC, validated compensation, control-aware gating and representative manual review.",
)


# Step 121 extends explicit capability contracts to the next seven weak modules.
CAPABILITY_SPECS.update({
    "rare_variant_family": ModuleCapabilitySpec(
        "rare_variant_family",
        "Rare variant and family genetics",
        (
            _stage("pedigree_qc", "Pedigree identity and structure QC", "built-in", "Validate IDs, parents, family boundaries, sex codes and ancestry cycles.", columns=("family_id", "individual_id", "father_id", "mother_id"), validation="Pedigree errors resolved"),
            _stage("mendelian", "Mendelian consistency", "built-in", "Calculate trio consistency and inheritance labels from long genotype records.", columns=("variant_id", "sample_id", "genotype"), validation="Error rate and callable trios reviewed"),
            _stage("kinship", "Kinship and sample identity", "built-in", "Calculate genotype concordance, IBS0 and dosage-correlation relationship flags.", columns=("variant_id", "sample_id", "genotype"), validation="Expected relationships confirmed"),
            _stage("phasing", "Read-backed phasing", "adapter", "Phase compound-heterozygous and inherited variants with pinned reads/reference.", engines=("whatshap", "bcftools"), references=("Reference FASTA",), validation="Phase blocks and read evidence reviewed"),
            _stage("annotation", "Clinical evidence annotation", "adapter", "Annotate population frequency, consequence and gene-disease evidence.", engines=("vep",), references=("ClinVar", "gnomAD", "Gene-disease source"), validation="Reference releases recorded"),
            _stage("confirmation", "Orthogonal variant confirmation", "external-validation", "Confirm priority de-novo, mosaic and diagnostic candidates independently.", validation="Independent confirmation and clinical review attached"),
        ),
        ("Pedigree/identity errors unresolved", "Read-backed phase absent", "Reference releases absent", "Independent diagnostic confirmation absent"),
        "Family-genetics prioritisation is research support and is not a diagnostic conclusion.",
    ),
    "explainable_ai_assurance": ModuleCapabilitySpec(
        "explainable_ai_assurance",
        "Explainable AI and model assurance",
        (
            _stage("heldout", "Held-out performance", "built-in", "Fit a leakage-safe reference model and preserve held-out metrics.", validation="Test split locked before review"),
            _stage("calibration", "Calibration and threshold review", "built-in", "Calculate Brier score, calibration bins and threshold-independent metrics.", validation="Calibration acceptance criteria reviewed"),
            _stage("subgroups", "Subgroup assurance", "built-in", "Compare performance across supplied subgroups and expose unstable small groups.", validation="Disparities and sample sizes reviewed"),
            _stage("ood", "Out-of-distribution screen", "built-in", "Flag robust multivariate distance beyond the training distribution.", validation="OOD threshold and consequences prespecified"),
            _stage("explanations", "Explanation stability and counterfactuals", "built-in", "Bootstrap coefficient rankings and create local linear counterfactual candidates.", validation="Stability and feasibility reviewed"),
            _stage("external", "Independent model qualification", "external-validation", "Validate the locked model on an independent cohort and intended-use workflow.", validation="Independent qualification package attached"),
        ),
        ("Subgroup/calibration/OOD issues unresolved", "Explanation stability below threshold", "External cohort absent", "Causal interpretation prohibited"),
        "Explanations describe model behaviour and do not establish biological causality.",
    ),
    "microbiology_metagenomics": ModuleCapabilitySpec(
        "microbiology_metagenomics",
        "Microbiology and metagenomics rapid screen",
        (
            _stage("assembly_qc", "Assembly and isolate QC", "built-in", "Calculate assembly continuity, GC and ambiguity metrics.", validation="Assembly QC thresholds reviewed"),
            _stage("taxonomy", "Candidate taxonomy screen", "built-in", "Compare bounded k-mer containment against versioned reference sequences.", references=("Taxonomy reference",), validation="Top matches confirmed with validated classifier"),
            _stage("mlst", "MLST/cgMLST typing", "built-in", "Call supplied allele profiles and expose low-confidence loci.", references=("MLST allele/profile database",), validation="Scheme and release recorded"),
            _stage("amr_vf", "AMR and virulence screen", "built-in", "Screen versioned gene catalogues and retain containment evidence.", references=("AMR/VF database",), validation="Hits confirmed with validated tool/database"),
            _stage("phenotype", "Phenotype-genotype concordance", "built-in", "Compare candidate gene evidence with supplied susceptibility phenotype.", validation="Discordance manually adjudicated"),
            _stage("lab_confirmation", "Laboratory confirmation", "external-validation", "Confirm identity and susceptibility using validated laboratory methods.", validation="Laboratory report attached"),
        ),
        ("Reference releases absent", "Typing loci unresolved", "Phenotype/genotype discordance unresolved", "Laboratory confirmation absent"),
        "Rapid k-mer screens do not replace validated clinical microbiology or susceptibility testing.",
    ),
    "ml_autolab": ModuleCapabilitySpec(
        "ml_autolab",
        "ML AutoLab",
        (
            _stage("schema", "Dataset and leakage preflight", "built-in", "Validate labelled rows, target, features and bounded resource policy.", validation="Leakage and split unit reviewed"),
            _stage("pipelines", "Leakage-safe feature pipelines", "built-in", "Fit imputation/encoding/scaling inside each cross-validation fold.", validation="Preprocessing provenance retained"),
            _stage("search", "Resource-bounded candidate search", "built-in", "Compare deterministic linear and ensemble candidates under fixed folds.", validation="Search space and seed recorded"),
            _stage("holdout", "Locked hold-out evaluation", "built-in", "Evaluate the selected champion on an untouched hold-out split.", validation="Champion selection and holdout metrics reviewed"),
            _stage("artifact", "Artifact and model card", "built-in", "Export joblib, hash, model card, importance and prediction tables.", validation="Artifact hash and environment recorded"),
            _stage("external", "Independent external validation", "external-validation", "Validate the frozen artifact on a new cohort and intended workflow.", validation="External validation report attached"),
        ),
        ("Leakage review incomplete", "Subgroup/calibration review incomplete", "External cohort absent", "Production serving qualification absent"),
        "Automated search improves reproducibility but does not prove biological or production performance.",
    ),
    "evidence_citation_engine": ModuleCapabilitySpec(
        "evidence_citation_engine",
        "Scientific evidence and citation engine",
        (
            _stage("normalize", "DOI/PMID normalization", "built-in", "Normalize imported identifiers and deduplicate records.", columns=("claim_id", "claim_text"), validation="Identifiers and duplicates reviewed"),
            _stage("resolve", "Provider metadata resolution", "adapter", "Resolve DOI/PMID metadata from authoritative providers with cached provenance.", engines=("internet",), references=("Crossref", "PubMed"), validation="Authoritative metadata timestamped"),
            _stage("claim_link", "Claim-source graph", "built-in", "Link each source to an exact claim and preserve evidence direction/strength.", columns=("claim_id", "claim_text"), validation="Exact claim support manually verified"),
            _stage("integrity", "Retraction, correction and version review", "built-in", "Expose imported retraction/correction/version metadata and unresolved records.", validation="Provider integrity status reviewed"),
            _stage("bibliography", "Bibliography export", "built-in", "Export BibTeX, RIS and claim-source edge tables.", validation="Export round-trip checked"),
            _stage("editorial", "Editorial evidence adjudication", "external-validation", "Independently verify that each source supports the exact published claim.", validation="Editorial sign-off attached"),
        ),
        ("Unresolved identifiers", "Retraction/correction status unverified", "Claim-source conflicts unresolved", "Editorial sign-off absent"),
        "Citation metadata and links do not establish that a paper supports an exact claim.",
    ),
    "organoid_3d": ModuleCapabilitySpec(
        "organoid_3d",
        "Organoid and 3D cell analytics",
        (
            _stage("volume", "3D segmentation and measurements", "built-in", "Segment bounded 3D arrays and calculate calibrated object phenotypes.", validation="Voxel calibration and masks reviewed"),
            _stage("tracking", "Time-lapse tracking", "built-in", "Link 3D centroids across frames and flag unmatched events.", validation="Ambiguous tracks manually reviewed"),
            _stage("plate", "Plate normalization and QC", "built-in", "Apply median-polish row/column correction, robust z-scores and Z-prime.", columns=("object_id", "well"), validation="Controls and plate quality accepted"),
            _stage("dose", "Dose-response modelling", "built-in", "Fit transparent four-parameter logistic curves when dose replication is sufficient.", validation="Fit quality and replicate assumptions reviewed"),
            _stage("embedding", "Morphology embedding", "built-in", "Generate standardized PCA morphology embeddings with explained variance.", validation="Batch and biological interpretation reviewed"),
            _stage("ground_truth", "Ground-truth validation", "external-validation", "Compare representative masks/classes with expert annotations and biological replicates.", validation="Dice/IoU and replicate criteria met"),
        ),
        ("Voxel/image metadata absent", "Plate controls inadequate", "Ground-truth masks absent", "Biological replication absent"),
        "Automated organoid phenotypes require representative manual QC and biological replication.",
    ),
    "real_evidence_studio": ModuleCapabilitySpec(
        "real_evidence_studio",
        "Real Evidence Studio",
        (
            _stage("schema", "Cross-domain evidence schema", "built-in", "Normalize genomics, omics, imaging, wet-lab and discovery evidence records.", validation="Required source/domain/claim fields complete"),
            _stage("provenance", "Source, version and licence controls", "built-in", "Require traceable source, release/version and licence metadata.", validation="Source and licence audit passes"),
            _stage("review", "Independent reviewer workflow", "built-in", "Aggregate reviewer decisions and require multiple reviewers for acceptance.", validation="Reviewer independence and votes reviewed"),
            _stage("conflict", "Conflict and adjudication queue", "built-in", "Queue direction/reviewer conflicts and blocked records for adjudication.", validation="Conflicts resolved by authorized adjudicator"),
            _stage("graph", "Cross-domain evidence graph", "built-in", "Export subject-evidence nodes and weighted relationships.", validation="Graph entities and claims verified"),
            _stage("independent", "Independent scientific validation", "external-validation", "Attach genuinely independent study, assay or external-site evidence.", validation="Independent evidence qualification completed"),
        ),
        ("Source/version/licence incomplete", "Reviewer conflict unresolved", "No independent evidence", "Domain-specific release criteria absent"),
        "Evidence curation and reviewer consensus do not create independent scientific validation.",
    ),
})



def _generic_capability_spec(module_key: str) -> ModuleCapabilitySpec:
    profile = MODULE_PROFILES[module_key]
    engine_stage_mode = "adapter" if profile.engines else "built-in"
    stages = (
        _stage(
            "input_qc",
            "Input schema and integrity",
            "built-in",
            "Validate schema, identifiers, missingness, duplicates and bounded resource use.",
            validation="Input quality checks reviewed",
        ),
        _stage(
            "design_qc",
            "Study-design and replication review",
            "built-in",
            "Review independent experimental units, group balance, controls and prespecified analysis design.",
            validation="Replication and controls documented",
        ),
        _stage(
            "domain_analysis",
            "Domain-specific analysis",
            "built-in",
            "Run deterministic built-in analysis while preserving assumptions, uncertainty and scientific boundaries.",
            validation="Results and assumptions reviewed",
        ),
        _stage(
            "specialist_execution",
            "Specialist engine execution",
            engine_stage_mode,
            "Use explicit, version-pinned specialist engines when deeper native execution is required.",
            engines=profile.engines,
            references=profile.references,
            validation="Engine versions, parameters and logs retained",
        ),
        _stage(
            "reproducibility",
            "Provenance and reproducibility",
            "built-in",
            "Record input hashes, software/reference releases, parameters and exportable manifests.",
            references=profile.references,
            validation="Exact rerun package generated",
        ),
        _stage(
            "independent_validation",
            "Independent scientific validation",
            "external-validation",
            "Confirm priority findings with an independent cohort, assay, reviewer or qualified external workflow.",
            validation="Independent evidence attached and adjudicated",
        ),
    )
    blockers = tuple(dict.fromkeys((*profile.validations, "Independent validation evidence absent", "Reference/software versions not pinned")))
    return ModuleCapabilitySpec(
        module_key=module_key,
        title=profile.title,
        stages=stages,
        release_blockers=blockers,
        evidence_boundary=profile.boundary,
    )


# Step 151 gives every registered depth profile an explicit six-stage capability
# contract. Bespoke domain contracts above remain authoritative.
for _module_key in MODULE_PROFILES:
    CAPABILITY_SPECS.setdefault(_module_key, _generic_capability_spec(_module_key))

def capability_spec_for(module_key: str) -> ModuleCapabilitySpec | None:
    return CAPABILITY_SPECS.get(module_key)


def _column_status(data: pd.DataFrame | None, required: tuple[str, ...]) -> tuple[bool, str]:
    if not required:
        return True, "No table columns required"
    if data is None or data.empty:
        return False, "No dataset loaded"
    lookup = {str(column).lower() for column in data.columns}
    missing = [column for column in required if column.lower() not in lookup]
    if missing:
        return False, "Missing columns: " + ", ".join(missing)
    return True, "Required columns detected"


def assess_capability(
    module_key: str,
    data: pd.DataFrame | None,
    engine_rows: pd.DataFrame | None = None,
    *,
    evidence_metadata: dict[str, Any] | None = None,
    source_mode: str | None = None,
    run_summary: dict[str, Any] | None = None,
) -> CapabilityAssessment | None:
    spec = capability_spec_for(module_key)
    if spec is None:
        return None

    engine_available: dict[str, bool] = {}
    if isinstance(engine_rows, pd.DataFrame) and not engine_rows.empty:
        engine_column = "engine" if "engine" in engine_rows.columns else "tool" if "tool" in engine_rows.columns else None
        available_column = "available" if "available" in engine_rows.columns else "installed" if "installed" in engine_rows.columns else None
        if engine_column and available_column:
            engine_available = {
                str(row[engine_column]).lower(): bool(row[available_column])
                for _, row in engine_rows.iterrows()
            }

    rows: list[dict[str, Any]] = []
    built_in_ready = 0
    adapter_ready = 0
    blocked = 0
    automatic_passable = 0
    automatic_ready = 0

    for stage in spec.stages:
        columns_ok, column_detail = _column_status(data, stage.required_columns)
        missing_engines = [engine for engine in stage.engines if not engine_available.get(engine.lower(), False)]
        if stage.mode == "built-in":
            automatic_passable += 1
            status = "ready" if columns_ok else "blocked"
            if status == "ready":
                built_in_ready += 1
                automatic_ready += 1
            else:
                blocked += 1
            detail = column_detail
        elif stage.mode == "adapter":
            automatic_passable += 1
            if not columns_ok:
                status = "blocked"
                detail = column_detail
                blocked += 1
            elif missing_engines:
                status = "adapter-ready"
                detail = "Install/configure: " + ", ".join(missing_engines)
            else:
                status = "ready"
                detail = "Required engines detected"
                adapter_ready += 1
                automatic_ready += 1
        else:
            status = "external-validation"
            detail = "Requires independent human/experimental evidence"

        rows.append({
            "stage": stage.label,
            "mode": stage.mode,
            "status": status,
            "purpose": stage.purpose,
            "required_columns": ", ".join(stage.required_columns),
            "engines": ", ".join(stage.engines),
            "references": ", ".join(stage.references),
            "validation_gate": stage.validation_gate,
            "detail": detail,
        })

    coverage = automatic_ready / max(automatic_passable, 1)
    external_stages = sum(stage.mode == "external-validation" for stage in spec.stages)
    if blocked:
        tier, tier_label = "C", "Tier C · data/schema blocked"
    elif coverage >= 0.85:
        tier, tier_label = "A", "Tier A · executable pipeline ready"
    elif coverage >= 0.45 or built_in_ready:
        tier, tier_label = "B", "Tier B · built-in analysis + adapters"
    else:
        tier, tier_label = "C", "Tier C · review/scaffold mode"

    profile = profile_for(module_key)
    evidence_readiness = assess_evidence_readiness(
        module_key,
        data,
        profile_references=profile.references if profile else (),
        profile_validations=profile.validations if profile else (),
        metadata=evidence_metadata,
        source_mode=source_mode,
        run_summary=run_summary,
    )

    blockers: list[str] = []
    for row in rows:
        if row["status"] in {"blocked", "adapter-ready", "external-validation"}:
            blockers.append(f"{row['stage']}: {row['detail']}")
    blockers.extend(blocker for blocker in evidence_readiness.blockers if blocker not in blockers)
    release_ready = bool(tier == "A" and external_stages == 0 and evidence_readiness.release_ready)

    manifest = {
        "schema": "biointel.step151.capability.v3",
        "module_key": module_key,
        "title": spec.title,
        "tier": tier,
        "tier_label": tier_label,
        "automatic_stage_coverage": coverage,
        "release_ready": release_ready,
        "scientific_readiness_score": evidence_readiness.score,
        "scientific_readiness_grade": evidence_readiness.grade,
        "stages": [asdict(stage) for stage in spec.stages],
        "stage_status": rows,
        "release_blockers": list(spec.release_blockers),
        "evidence_boundary": spec.evidence_boundary,
        "profile": asdict(profile) if profile else None,
        "evidence_readiness": evidence_readiness.manifest,
    }
    return CapabilityAssessment(
        module_key=module_key,
        tier=tier,
        tier_label=tier_label,
        coverage=coverage,
        built_in_ready=built_in_ready,
        adapter_ready=adapter_ready,
        blocked=blocked,
        release_ready=release_ready,
        readiness_score=evidence_readiness.score,
        readiness_grade=evidence_readiness.grade,
        stage_table=pd.DataFrame(rows),
        quality_checks=evidence_readiness.checks,
        evidence_table=evidence_readiness.requirements,
        blockers=tuple(blockers),
        evidence_readiness=evidence_readiness,
        manifest=manifest,
    )
