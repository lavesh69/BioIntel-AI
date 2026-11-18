from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceRequirement:
    evidence_id: str
    title: str
    description: str
    data_file: str | None
    validator: str
    acceptance_summary: str
    requires_independent_source: bool = True
    requires_reviewer_signature: bool = True


@dataclass(frozen=True)
class ExternalReadinessProfile:
    module_key: str
    title: str
    page: str
    weakness_summary: str
    requirements: tuple[EvidenceRequirement, ...]
    release_boundary: str


def _req(
    evidence_id: str,
    title: str,
    description: str,
    data_file: str | None,
    validator: str,
    acceptance: str,
    *,
    independent: bool = True,
) -> EvidenceRequirement:
    return EvidenceRequirement(
        evidence_id=evidence_id,
        title=title,
        description=description,
        data_file=data_file,
        validator=validator,
        acceptance_summary=acceptance,
        requires_independent_source=independent,
    )


PROFILES: dict[str, ExternalReadinessProfile] = {
    "phenotypic_screening": ExternalReadinessProfile(
        module_key="phenotypic_screening",
        title="Phenotypic Screening & High-Content Analysis",
        page="pages/141_Phenotypic_Screening_High_Content_Analysis_Lab.py",
        weakness_summary="Physical imaging qualification, multi-plate reproducibility, segmentation ground truth, biological replicates and orthogonal assay evidence.",
        requirements=(
            _req(
                "physical_instrument_qualification",
                "Physical imaging instrument qualification",
                "Calibration and repeatability evidence from the target microscope or high-content imager.",
                "instrument_runs.csv",
                "phenotypic_instrument",
                "At least 3 real runs; field/focus/illumination variation <=10%, stage error <=5 µm, all runs accepted.",
                independent=False,
            ),
            _req(
                "multi_plate_validation",
                "Real multi-plate validation",
                "Positive/negative controls, replicate concordance and plate-position artefact measurements across real plates.",
                "plate_qc.csv",
                "phenotypic_plates",
                "At least 3 plates; Z-prime >=0.5, replicate correlation >=0.80, edge effect <=15%.",
            ),
            _req(
                "segmentation_ground_truth",
                "Segmentation ground-truth validation",
                "Expert-labelled masks or object annotations compared with model output.",
                "segmentation_metrics.csv",
                "phenotypic_segmentation",
                "At least 20 images; mean Dice >=0.85, IoU >=0.75, object F1 >=0.85; all reviewed.",
            ),
            _req(
                "biological_replicates_external_site",
                "Biological replicate and external-site validation",
                "Reproducibility across batches, biological replicates, instruments and independent sites.",
                "external_site_replicates.csv",
                "phenotypic_replicates",
                "At least 2 sites and 3 batches; mean replicate correlation >=0.80 and confirmed-hit rate >=0.70.",
            ),
            _req(
                "orthogonal_assay_confirmation",
                "Orthogonal assay confirmation",
                "Primary-screen effects confirmed using a biologically distinct assay.",
                "orthogonal_confirmation.csv",
                "phenotypic_orthogonal",
                "At least 10 candidates; effect correlation >=0.70 and confirmed fraction >=0.70.",
            ),
        ),
        release_boundary="Research-prioritisation only until every real-world evidence pack is qualified and formal expert release review is approved.",
    ),
    "spatial_omics_pathology": ExternalReadinessProfile(
        module_key="spatial_omics_pathology",
        title="Spatial Omics & Digital Pathology",
        page="pages/118_Spatial_Omics_and_Digital_Pathology_Studio.py",
        weakness_summary="Scanner qualification, stain/site drift, patient-level external cohorts, pathologist agreement and prospective clinical evidence.",
        requirements=(
            _req(
                "scanner_qualification",
                "Real scanner qualification",
                "Target whole-slide scanner calibration, focus, colour and registration performance.",
                "scanner_runs.csv",
                "spatial_scanner",
                "At least 3 runs; colour ΔE <=5, focus/tile artefacts <=2%, registration error <=10 µm, all accepted.",
                independent=False,
            ),
            _req(
                "stain_site_drift_validation",
                "Stain, scanner and site drift validation",
                "Cross-site and cross-scanner drift measurements using locked preprocessing.",
                "drift_metrics.csv",
                "spatial_drift",
                "At least 2 sites and 2 stain batches; embedding shift <=0.20, AUC drop <=0.05, calibration error <=0.05.",
            ),
            _req(
                "patient_external_cohort",
                "Patient-level external cohort",
                "Independent patient cohort with locked labels and patient-level split integrity.",
                "patient_validation.csv",
                "spatial_patient",
                "At least 30 unique patients across >=2 sites; ROC-AUC >=0.80 and balanced accuracy >=0.75.",
            ),
            _req(
                "pathologist_agreement",
                "Pathologist agreement study",
                "Blinded model-versus-pathologist and inter-pathologist agreement analysis.",
                "pathology_review.csv",
                "spatial_pathologists",
                "At least 30 cases; inter-reviewer kappa >=0.70 and model-versus-consensus kappa >=0.70.",
            ),
            _req(
                "prospective_clinical_validation",
                "Prospective clinical validation",
                "Temporally prospective, pre-specified validation performed after model lock.",
                "prospective_outcomes.csv",
                "spatial_prospective",
                "At least 30 prospective cases; all pre-specified before outcome; balanced accuracy >=0.75.",
            ),
        ),
        release_boundary="No diagnostic claim until scanner/site qualification, patient-level external validation, pathologist agreement and prospective review are complete.",
    ),
    "protein_language_design": ExternalReadinessProfile(
        module_key="protein_language_design",
        title="Protein Language Model & Generative Design",
        page="pages/143_Protein_Language_Model_Generative_Design_Lab.py",
        weakness_summary="Authentic trained weights, independent sequence benchmarks, novelty verification, structural confirmation and wet-lab expression evidence.",
        requirements=(
            _req(
                "authentic_trained_weights",
                "Authentic trained model weights",
                "Provider/release/licence records and cryptographic checksums for actual weights and tokenizer assets.",
                None,
                "manifest_only",
                "All declared model/tokenizer files exist, hashes match, provider/release/licence/provenance are recorded and reviewer signed.",
                independent=False,
            ),
            _req(
                "independent_sequence_benchmark",
                "Independent sequence benchmark",
                "Task-specific benchmark isolated from training and model selection.",
                "benchmark_summary.csv",
                "protein_benchmark",
                "At least 2 independent benchmarks; every locked metric meets its threshold and maximum train identity <=70%.",
            ),
            _req(
                "novelty_verification",
                "Novelty and memorisation verification",
                "Generated sequences screened against training/reference sets for identity, k-mer overlap, duplicates and restricted motifs.",
                "generated_sequences.csv",
                "protein_novelty",
                "At least 20 sequences; identity <=70%, k-mer Jaccard <=0.60, no duplicate or restricted-motif failures.",
            ),
            _req(
                "structure_confirmation",
                "Independent structure confirmation",
                "Orthogonal structure prediction or experimental structural confirmation with confidence and provenance.",
                "structure_confirmation.csv",
                "protein_structure",
                "At least 10 sequences; >=80% meet pLDDT >=70 and pTM >=0.50; at least one independent/experimental confirmation.",
            ),
            _req(
                "wet_lab_expression",
                "Wet-lab expression and activity evidence",
                "Real expression, solubility, purity and activity measurements from designed proteins.",
                "expression_results.csv",
                "protein_expression",
                "At least 5 designs; >=60% meet soluble fraction >=0.50, purity >=80% and activity confirmation.",
            ),
        ),
        release_boundary="Generated proteins remain computational hypotheses until authentic weights, novelty, independent structure and wet-lab expression/activity evidence qualify.",
    ),
    "protein_ligand_codesign": ExternalReadinessProfile(
        module_key="protein_ligand_codesign",
        title="Protein–Ligand Co-Design",
        page="pages/183_Protein_Ligand_CoDesign_Studio.py",
        weakness_summary="Qualified docking/structure engines, experimental binding affinity, selectivity, ADMET and prospective assay validation.",
        requirements=(
            _req(
                "docking_engine_qualification",
                "Docking and structure-engine qualification",
                "Redocking benchmark on experimentally resolved complexes using pinned engine and preparation versions.",
                "docking_benchmark.csv",
                "ligand_docking",
                "At least 20 complexes; median pose RMSD <=2 Å and top-1 success fraction >=0.60.",
            ),
            _req(
                "experimental_binding_affinity",
                "Experimental binding-affinity validation",
                "Predictions compared with real biochemical/biophysical affinity measurements.",
                "binding_affinity.csv",
                "ligand_binding",
                "At least 20 measurements; Pearson correlation >=0.60 and RMSE <=1.50 pK units.",
            ),
            _req(
                "selectivity_panel",
                "Experimental selectivity panel",
                "On-target and off-target panel measured with matched assay conditions.",
                "selectivity_panel.csv",
                "ligand_selectivity",
                "At least 10 compounds, panel size >=5 and >=70% pass the locked selectivity criterion.",
            ),
            _req(
                "admet_confirmation",
                "Experimental ADMET confirmation",
                "Solubility, permeability, cytotoxicity, hERG and metabolic-stability evidence.",
                "admet_results.csv",
                "ligand_admet",
                "At least 10 compounds; >=60% pass every mandatory ADMET gate.",
            ),
            _req(
                "prospective_assay_validation",
                "Prospective assay validation",
                "Predictions and decision thresholds locked before experimental assay execution.",
                "prospective_assay.csv",
                "ligand_prospective",
                "At least 20 compounds; all pre-specified; precision and recall >=0.60.",
            ),
        ),
        release_boundary="No binding, selectivity, safety or developability claim until experimental and prospective assay evidence passes.",
    ),
    "strain_microbiome": ExternalReadinessProfile(
        module_key="strain_microbiome",
        title="Strain-Resolved Microbiome",
        page="pages/139_Strain_Resolved_Microbiome_Functional_Profiling_Studio.py",
        weakness_summary="Licensed reference databases, real mock communities, contamination controls, strain-level ground truth and independent sequencing-site validation.",
        requirements=(
            _req(
                "licensed_reference_database",
                "Licensed strain/reference database",
                "Pinned database release, licence/terms, taxonomy, build scripts and checksums.",
                None,
                "manifest_only",
                "All database/index files exist, hashes match and licence, release, taxonomy and provenance are reviewer approved.",
                independent=False,
            ),
            _req(
                "real_mock_community",
                "Real mock-community benchmark",
                "Wet-lab mock community with known strain identities and abundances.",
                "mock_community_results.csv",
                "microbiome_mock",
                "Precision and recall >=0.90 and abundance correlation >=0.90.",
            ),
            _req(
                "contamination_controls",
                "Contamination-control validation",
                "Extraction blanks, negative controls and spike-ins processed with study samples.",
                "contamination_controls.csv",
                "microbiome_contamination",
                "At least 5 negative controls; all controls above 1% contamination are flagged and no unflagged critical contamination remains.",
            ),
            _req(
                "strain_ground_truth",
                "Strain-level ground-truth validation",
                "Samples with verified isolate, assembly or synthetic truth for strain assignment.",
                "strain_ground_truth.csv",
                "microbiome_ground_truth",
                "Precision/recall >=0.90; called strains meet ANI >=0.99 and coverage >=0.80; ambiguous calls abstain.",
            ),
            _req(
                "independent_site_validation",
                "Independent sequencing-site validation",
                "Cross-site and cross-platform sequencing validation with locked pipeline and references.",
                "site_validation.csv",
                "microbiome_sites",
                "At least 2 sites; mean precision/recall/abundance correlation >=0.85 at every site.",
            ),
        ),
        release_boundary="Strain and functional calls remain research outputs until licensed references, mock-community truth, controls and independent-site validation qualify.",
    ),
}

TARGET_MODULES = tuple(PROFILES)

__all__ = ["EvidenceRequirement", "ExternalReadinessProfile", "PROFILES", "TARGET_MODULES"]
