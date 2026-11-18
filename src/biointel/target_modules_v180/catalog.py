from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TargetModuleProfile:
    module_key: str
    title: str
    page: str
    baseline_rating: float
    focus: str
    workflow: tuple[str, ...]
    data_gates: tuple[str, ...]
    model_gates: tuple[str, ...]
    scientific_gates: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    required_outputs: tuple[str, ...]
    risk_controls: tuple[str, ...]
    monitoring_metrics: tuple[str, ...]
    supplemental_components: tuple[tuple[str, str, str], ...]
    supplemental_references: tuple[str, ...]
    model_assets: tuple[str, ...]
    cohort_assets: tuple[str, ...]
    validation_fixtures: tuple[str, ...]
    governance_assets: tuple[str, ...]
    boundary: str


COMMON_WORKFLOW = (
    "Lock intended use, supported inputs, decision boundary, endpoints and quantitative acceptance thresholds before execution",
    "Verify permissions, sample identity, schema, units, coordinate/build conventions, checksums and complete input lineage",
    "Qualify pinned specialist runtimes, reference releases, model weights, preprocessing and hardware execution profile",
    "Execute deterministic golden, negative, corruption, leakage, sensitivity and reproducibility fixtures in an isolated workspace",
    "Run module-specific uncertainty, subgroup/site/instrument, contamination or selectivity checks and preserve all exclusions",
    "Export a signed evidence bundle and remain fail-closed until independent confirmation, expert review and formal release approval",
)

COMMON_DATA_GATES = (
    "Input identity, permissions, schema, units and SHA-256 lineage are complete",
    "Sample, plate, patient, site, scanner or sequence identifiers are unique and leakage-audited",
    "Required controls, replicates, metadata and exclusion reasons are present",
    "Reference coordinate systems, genome builds, ontologies and database releases are pinned",
    "Missingness, corruption, duplication and implausible-range checks pass",
    "Train, validation, benchmark and external-confirmation assets are isolated",
)

COMMON_MODEL_GATES = (
    "Model provider, architecture, release, weight checksum and licence are recorded",
    "Preprocessing, tokenisation, feature extraction and postprocessing are version locked",
    "Intended use, unsupported use, calibration and applicability domain are documented",
    "Training-data overlap and benchmark leakage are assessed and bounded",
    "Uncertainty, out-of-distribution and abstention behaviour are tested",
    "Subgroup, site, instrument or domain-shift performance is reported",
)

COMMON_ACCEPTANCE = (
    "All mandatory contracts, data gates and scientific checks pass without a critical exception",
    "All required components, references, model assets, cohorts and benchmark fixtures are qualified",
    "Golden results are deterministic and negative/corruption/leakage cases fail safely",
    "Uncertainty and applicability-domain limits are exposed in every export",
    "No unsupported biological, clinical or experimental claim is emitted",
    "Independent confirmation, expert sign-off and formal release review are complete for controlled release",
)

COMMON_OUTPUTS = (
    "Locked intended-use and scientific acceptance contract",
    "Runtime, model-weight, reference and dataset bill of materials",
    "Input lineage, exclusion, leakage and contamination audit",
    "Golden/adverse fixture results with expected-output hashes",
    "Uncertainty, subgroup/site/instrument and applicability-domain report",
    "Signed qualification bundle and fail-closed release decision",
)

COMMON_GOVERNANCE = (
    "risk-register",
    "acceptance-and-validation-plan",
    "monitoring-rollback-and-incident-plan",
)

_PROFILE_DATA = {
    "phenotypic_screening": {
        "title": "Phenotypic Screening & High-Content Analysis",
        "page": "pages/141_Phenotypic_Screening_High_Content_Analysis_Lab.py",
        "baseline": 4.36,
        "focus": "control-aware high-content image and feature screening with plate, replicate, leakage, uncertainty and orthogonal-assay safeguards",
        "components": (
            ("python:cellpose", "Cellpose segmentation runtime", "pinned-python-venv"),
            ("python:stardist", "StarDist segmentation runtime", "pinned-python-venv"),
            ("python:skimage", "scikit-image morphology and image QC", "pinned-python-venv"),
            ("python:scipy", "SciPy statistics", "pinned-python-venv"),
            ("python:sklearn", "scikit-learn validation", "pinned-python-venv"),
        ),
        "references": (
            "plate-layout-and-control-map",
            "image-calibration-and-object-feature-schema",
            "compound-identity-and-dose-release",
            "phenotype-ontology-release",
        ),
        "models": (
            "qualified-cell-segmentation-model",
            "qualified-phenotype-classification-model",
            "qualified-hit-prioritisation-model",
        ),
        "cohorts": (
            "independent-plate-benchmark",
            "cross-instrument-screening-cohort",
            "orthogonal-assay-confirmation-set",
        ),
        "fixtures": (
            "z-prime-and-control-separation-fixture",
            "plate-edge-and-batch-effect-fixture",
            "patient-plate-leakage-fixture",
            "segmentation-corruption-and-uncertainty-fixture",
            "dose-response-replicate-reproducibility-fixture",
        ),
        "risks": (
            "plate edge and dispensing artefacts",
            "patient, well or replicate leakage",
            "segmentation domain shift",
            "compound identity or dose mismatch",
            "hit inflation from multiple testing",
            "unsupported translation from phenotype to mechanism",
        ),
        "monitor": (
            "Z-prime and control separation",
            "replicate concordance and plate drift",
            "segmentation failure and abstention rate",
            "hit confirmation and false-discovery rate",
            "instrument/site performance drift",
        ),
        "scientific": (
            "Positive and negative controls achieve the locked Z-prime threshold",
            "Edge, row, column, batch and plate-position effects are measured and bounded",
            "Replicate concordance, robust effect size and multiple-testing correction pass",
            "Patient, plate, well and image-object leakage are absent across evaluation splits",
            "Segmentation masks pass size, count, border-touch and confidence checks",
            "Dose-response direction, potency uncertainty and orthogonal confirmation are reported",
            "Low-confidence or out-of-domain phenotypes abstain instead of becoming hits",
        ),
        "boundary": "Screening outputs are research prioritisation only. Hits require assay-specific orthogonal confirmation, independent plates/sites and qualified biological review.",
    },
    "spatial_omics_pathology": {
        "title": "Spatial Omics & Digital Pathology",
        "page": "pages/118_Spatial_Omics_and_Digital_Pathology_Studio.py",
        "baseline": 4.25,
        "focus": "registered spatial molecular and tissue-image analysis with scanner/site drift, neighbourhood statistics, pathology review and patient-level validation",
        "components": (
            ("python:openslide", "OpenSlide whole-slide runtime", "system-or-pinned-environment"),
            ("python:scanpy", "Scanpy single-cell/spatial matrix runtime", "pinned-python-venv"),
            ("python:squidpy", "Squidpy spatial graph runtime", "pinned-python-venv"),
            ("python:anndata", "AnnData schema runtime", "pinned-python-venv"),
            ("python:cellpose", "Cellpose tissue segmentation runtime", "pinned-python-venv"),
        ),
        "references": (
            "tissue-and-cell-ontology-release",
            "scanner-colour-calibration-profile",
            "spatial-assay-coordinate-specification",
            "reference-cell-type-atlas",
        ),
        "models": (
            "qualified-tissue-segmentation-model",
            "qualified-pathology-embedding-model",
            "qualified-cell-type-deconvolution-model",
        ),
        "cohorts": (
            "independent-patient-spatial-cohort",
            "cross-scanner-cross-site-pathology-cohort",
            "orthogonal-histology-and-molecular-review-set",
        ),
        "fixtures": (
            "coordinate-registration-and-transform-fixture",
            "spatial-neighbourhood-and-morans-i-fixture",
            "scanner-stain-site-drift-fixture",
            "patient-level-leakage-fixture",
            "tile-corruption-ood-and-region-contrast-fixture",
        ),
        "risks": (
            "patient or tile leakage",
            "registration and coordinate-frame mismatch",
            "scanner, stain and site domain shift",
            "segmentation or cell-type transfer error",
            "spatial autocorrelation ignored in inference",
            "pathology claim without expert review",
        ),
        "monitor": (
            "registration residual and tissue coverage",
            "scanner/site embedding drift",
            "segmentation and deconvolution uncertainty",
            "patient-level region-effect stability",
            "pathologist disagreement and abstention rate",
        ),
        "scientific": (
            "Image, spot and cell coordinates are valid, unique, registered and traceable",
            "Spatial adjacency is symmetric and neighbourhood statistics are finite and reproducible",
            "Patient—not tile or spot—is the independent evaluation unit",
            "Scanner, stain, site and assay-batch drift are measured against locked limits",
            "Region contrasts use patient-aware inference and multiple-testing correction",
            "Tissue coverage, segmentation confidence and out-of-domain tiles are reported",
            "Orthogonal tissue review and pathologist adjudication are required for release",
        ),
        "boundary": "Spatial and pathology patterns are exploratory until patient-level external validation, scanner/site qualification, orthogonal tissue review and qualified pathologist sign-off are complete.",
    },
    "protein_language_design": {
        "title": "Protein Language Model & Generative Design",
        "page": "pages/143_Protein_Language_Model_Generative_Design_Lab.py",
        "baseline": 3.50,
        "focus": "licence-aware protein sequence generation with novelty, constraint, structure-confidence, uncertainty and wet-lab confirmation gates",
        "components": (
            ("python:torch", "PyTorch inference runtime", "pinned-python-venv"),
            ("python:transformers", "Transformers model runtime", "pinned-python-venv"),
            ("python:esm", "ESM protein language-model runtime", "pinned-python-venv"),
            ("proteinmpnn", "ProteinMPNN executable or wrapper", "operator-qualified"),
            ("colabfold_batch", "ColabFold structure-prediction runtime", "operator-qualified"),
        ),
        "references": (
            "amino-acid-and-sequence-validation-policy",
            "restricted-motif-and-biosafety-policy",
            "protein-training-overlap-reference-index",
            "structure-confidence-and-design-acceptance-policy",
        ),
        "models": (
            "licensed-protein-language-model-weights",
            "qualified-protein-sequence-design-weights",
            "qualified-structure-prediction-weights",
        ),
        "cohorts": (
            "independent-protein-property-benchmark",
            "remote-homology-novelty-benchmark",
            "wet-lab-expression-stability-activity-set",
        ),
        "fixtures": (
            "sequence-alphabet-length-and-constraint-fixture",
            "training-overlap-and-novelty-fixture",
            "composition-motif-biosafety-fixture",
            "structure-confidence-and-ensemble-fixture",
            "pareto-ranking-and-reproducibility-fixture",
        ),
        "risks": (
            "training-data memorisation",
            "invalid or unexpressible sequences",
            "restricted or hazardous motif generation",
            "overconfidence from a single model",
            "structure-confidence misuse",
            "activity claim without wet-lab evidence",
        ),
        "monitor": (
            "invalid-sequence and constraint-failure rate",
            "training-neighbour similarity and novelty distribution",
            "model disagreement and uncertainty",
            "structure-confidence and aggregation-risk drift",
            "experimental confirmation success rate",
        ),
        "scientific": (
            "Generated sequences use the allowed alphabet and satisfy locked length and motif constraints",
            "Exact duplicates and near-neighbours of training/reference sequences are detected",
            "Composition, charge proxy, hydrophobic runs and aggregation-risk proxies are bounded",
            "Generation seeds, decoding parameters and model versions reproduce candidate sets",
            "Multiple objectives are ranked by a transparent Pareto procedure",
            "Structure confidence and model disagreement are reported without implying activity",
            "Expression, stability, binding or activity claims require independent wet-lab confirmation",
        ),
        "boundary": "Generated proteins are computational hypotheses. Sequence validity, model confidence or predicted structure does not establish expression, folding, binding, activity or safety.",
    },
    "protein_ligand_codesign": {
        "title": "Protein–Ligand Co-Design",
        "page": "pages/183_Protein_Ligand_CoDesign_Studio.py",
        "baseline": 3.50,
        "focus": "joint protein and ligand candidate design with structure preparation, constraint, pose, selectivity, ensemble and experimental-binding gates",
        "components": (
            ("vina", "AutoDock Vina docking runtime", "operator-qualified"),
            ("colabfold_batch", "ColabFold structure-prediction runtime", "operator-qualified"),
            ("proteinmpnn", "ProteinMPNN sequence-design runtime", "operator-qualified"),
            ("rfdiffusion", "RFdiffusion generative-structure runtime", "operator-qualified"),
            ("python:rdkit", "RDKit ligand chemistry runtime", "pinned-python-venv"),
            ("python:openmm", "OpenMM relaxation/runtime", "pinned-python-venv"),
        ),
        "references": (
            "prepared-receptor-and-binding-site-release",
            "ligand-protonation-tautomer-stereochemistry-policy",
            "selectivity-and-off-target-panel",
            "measured-affinity-benchmark-release",
        ),
        "models": (
            "qualified-protein-design-weights",
            "qualified-generative-structure-weights",
            "qualified-affinity-or-pose-model",
        ),
        "cohorts": (
            "independent-protein-ligand-complex-benchmark",
            "cross-target-selectivity-benchmark",
            "experimental-binding-and-functional-confirmation-set",
        ),
        "fixtures": (
            "structure-ligand-preparation-fixture",
            "constraint-clash-and-pose-reproducibility-fixture",
            "decoy-ranking-and-affinity-calibration-fixture",
            "selectivity-off-target-and-novelty-fixture",
            "ensemble-consensus-and-experimental-evidence-fixture",
        ),
        "risks": (
            "incorrect receptor or ligand state",
            "steric clash or violated design constraint",
            "docking-score overinterpretation",
            "selectivity blind spot",
            "training or benchmark leakage",
            "binding or activity claim without experiment",
        ),
        "monitor": (
            "preparation and chemistry validation failures",
            "pose RMSD and ensemble agreement",
            "score calibration and decoy enrichment",
            "off-target selectivity margin",
            "experimental affinity and activity confirmation rate",
        ),
        "scientific": (
            "Protein structures, binding sites and ligand states are complete and versioned",
            "Generated candidates satisfy residue, geometry, chemistry and interaction constraints",
            "Steric clashes, ligand strain and pose instability are detected",
            "Pose or affinity conclusions require consensus or calibrated evidence, not one score",
            "Selectivity is assessed against a locked off-target panel",
            "Candidate novelty and training/benchmark overlap are reported",
            "Affinity, selectivity and activity claims require measured experimental confirmation",
        ),
        "boundary": "Co-design scores rank hypotheses only. They do not establish a valid pose, affinity, selectivity, biological activity, developability or safety without experimental confirmation.",
    },
    "strain_microbiome": {
        "title": "Strain-Resolved Microbiome",
        "page": "pages/139_Strain_Resolved_Microbiome_Functional_Profiling_Studio.py",
        "baseline": 3.50,
        "focus": "strain-level taxonomic and functional profiling with compositional statistics, contamination controls, database pinning, mock communities and orthogonal confirmation",
        "components": (
            ("kraken2", "Kraken2 taxonomic classifier", "operator-qualified"),
            ("bracken", "Bracken abundance estimator", "operator-qualified"),
            ("humann", "HUMAnN functional profiler", "operator-qualified"),
            ("metaphlan", "MetaPhlAn marker profiler", "operator-qualified"),
            ("python:biom", "BIOM table runtime", "pinned-python-venv"),
            ("python:skbio", "scikit-bio compositional statistics", "pinned-python-venv"),
        ),
        "references": (
            "pinned-taxonomy-and-strain-database",
            "marker-gene-and-pangenome-release",
            "functional-pathway-database-release",
            "amr-virulence-reference-release",
        ),
        "models": (
            "qualified-strain-abundance-model",
            "qualified-functional-profile-model",
            "qualified-contamination-or-source-model",
        ),
        "cohorts": (
            "defined-mock-community-benchmark",
            "independent-shotgun-metagenome-cohort",
            "orthogonal-isolate-qPCR-or-culture-confirmation-set",
        ),
        "fixtures": (
            "compositional-closure-and-clr-fixture",
            "negative-control-and-contamination-fixture",
            "strain-ambiguity-and-coverage-fixture",
            "mock-community-precision-recall-fixture",
            "functional-profile-and-differential-reproducibility-fixture",
        ),
        "risks": (
            "database-dependent false assignment",
            "low-coverage strain overcalling",
            "reagent or environmental contamination",
            "compositional-analysis misuse",
            "batch and extraction-kit confounding",
            "function inferred without direct evidence",
        ),
        "monitor": (
            "classified-read and ambiguous-assignment fraction",
            "negative-control contamination burden",
            "strain coverage and confidence distribution",
            "mock-community precision and recall",
            "database and batch drift",
        ),
        "scientific": (
            "Abundance tables are non-negative, finite and compositional closure is verified",
            "CLR or other compositional transformations use an explicit zero-handling policy",
            "Negative controls and prevalence/frequency contamination checks are included",
            "Strain assignments meet locked breadth, depth, uniqueness and ambiguity thresholds",
            "Mock-community precision, recall and abundance error pass acceptance limits",
            "Differential results account for batch, repeated measures and multiple testing",
            "Taxonomic and functional claims remain database-dependent and require orthogonal confirmation",
        ),
        "boundary": "Strain and function calls depend on database content, coverage and ambiguity. They do not establish viable organisms, transmission, resistance phenotype or causal function without orthogonal confirmation.",
    },
}


def _profile(module_key: str, data: dict[str, object]) -> TargetModuleProfile:
    slug = module_key.replace("_", "-")
    governance = tuple(f"{slug}-{suffix}" for suffix in COMMON_GOVERNANCE)
    return TargetModuleProfile(
        module_key=module_key,
        title=str(data["title"]),
        page=str(data["page"]),
        baseline_rating=float(data["baseline"]),
        focus=str(data["focus"]),
        workflow=COMMON_WORKFLOW,
        data_gates=COMMON_DATA_GATES,
        model_gates=COMMON_MODEL_GATES,
        scientific_gates=tuple(data["scientific"]),
        acceptance_criteria=COMMON_ACCEPTANCE,
        required_outputs=COMMON_OUTPUTS,
        risk_controls=tuple(data["risks"]),
        monitoring_metrics=tuple(data["monitor"]),
        supplemental_components=tuple(data["components"]),
        supplemental_references=tuple(data["references"]),
        model_assets=tuple(data["models"]),
        cohort_assets=tuple(data["cohorts"]),
        validation_fixtures=tuple(data["fixtures"]),
        governance_assets=governance,
        boundary=str(data["boundary"]),
    )


TARGET_PROFILES = {key: _profile(key, value) for key, value in _PROFILE_DATA.items()}
TARGET_MODULES = tuple(TARGET_PROFILES)

__all__ = ["TargetModuleProfile", "TARGET_MODULES", "TARGET_PROFILES"]
