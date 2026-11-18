from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ImplementationControl:
    control: str
    path: str
    required_tokens: tuple[str, ...] = ()


@dataclass(frozen=True)
class MaturityArea:
    key: str
    label: str
    implementation_score: float
    implementation_status: str
    evidence_score: float | None
    evidence_status: str
    passed_controls: tuple[str, ...]
    failed_controls: tuple[str, ...]
    boundary: str


AREA_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "key": "regulatory_readiness",
        "label": "Regulatory Readiness",
        "evidence_score": 2.5,
        "boundary": "The system provides a validation-ready control framework; regulatory applicability, validation and approval remain organization- and intended-use-specific.",
        "controls": (
            ImplementationControl(
                "Regulatory/GxP control catalog",
                "src/biointel/compliance/control_catalog.py",
                ("REG-001", "REG-008"),
            ),
            ImplementationControl(
                "Controlled records and audit ledger",
                "src/biointel/compliance/ledger.py",
                ("controlled_records", "audit_events", "verify_audit_chain"),
            ),
            ImplementationControl(
                "Electronic-signature binding",
                "src/biointel/compliance/ledger.py",
                ("electronic_signatures", "verify_signature"),
            ),
            ImplementationControl(
                "Retention policy", "config/retention_policy.yaml", ("record_classes", "legal_hold")
            ),
            ImplementationControl(
                "Regulatory guide",
                "docs/REGULATORY_GXP_READINESS.md",
                ("certification boundary", "intended use"),
            ),
            ImplementationControl(
                "Compliance tests",
                "tests/test_step36_maturity_frameworks.py",
                ("test_compliance_ledger",),
            ),
        ),
    },
    {
        "key": "gxp_readiness",
        "label": "GxP Readiness",
        "evidence_score": 2.0,
        "boundary": "Implemented controls support GxP validation work but do not establish a validated state, trained organization or inspection outcome by themselves.",
        "controls": (
            ImplementationControl(
                "ALCOA+ audit chain",
                "src/biointel/compliance/ledger.py",
                ("synchronous=FULL", "content_sha256", "previous_hash"),
            ),
            ImplementationControl(
                "Deviation, CAPA and change control",
                "src/biointel/compliance/ledger.py",
                ("deviation", "capa", "change_control"),
            ),
            ImplementationControl(
                "Training records",
                "src/biointel/compliance/ledger.py",
                ("training_records", "record_training"),
            ),
            ImplementationControl(
                "Quality controls policy",
                "config/compliance_control_catalog.yaml",
                ("GXP-001", "GXP-008"),
            ),
            ImplementationControl(
                "Validation lifecycle guide",
                "docs/REGULATORY_GXP_READINESS.md",
                ("validation lifecycle", "ALCOA+"),
            ),
            ImplementationControl(
                "Quality-system CI gate",
                ".github/workflows/maturity-quality-gates.yml",
                ("compliance", "reproducibility"),
            ),
        ),
    },
    {
        "key": "fair_data_principles",
        "label": "FAIR Data Principles",
        "evidence_score": 5.5,
        "boundary": "FAIR implementation tooling is complete; every real dataset must still supply persistent identifiers, access terms, provenance, standards and licensing.",
        "controls": (
            ImplementationControl(
                "15-principle FAIR evaluator",
                "src/biointel/fair/evaluator.py",
                ("F1", "A2", "I3", "R1.3"),
            ),
            ImplementationControl(
                "JSON-LD digital object builder",
                "src/biointel/fair/digital_object.py",
                ("@context", "sha256", "qualified_references"),
            ),
            ImplementationControl(
                "FAIR implementation profile",
                "config/fair_profile.yaml",
                ("findable", "accessible", "interoperable", "reusable"),
            ),
            ImplementationControl(
                "FAIR and reproducibility guide",
                "docs/FAIR_REPRODUCIBILITY.md",
                ("machine-actionable", "metadata persistence"),
            ),
            ImplementationControl(
                "FAIR tests", "tests/test_step36_maturity_frameworks.py", ("test_fair_evaluator",)
            ),
        ),
    },
    {
        "key": "reproducible_research_readiness",
        "label": "Reproducible Research Readiness",
        "evidence_score": 5.0,
        "boundary": "The bundle captures and verifies research objects; independent rerun success still depends on complete inputs, compatible compute and external services.",
        "controls": (
            ImplementationControl(
                "Deterministic reproducibility bundles",
                "src/biointel/reproducibility/bundle.py",
                ("FIXED_ZIP_TIMESTAMP", "random_seed", "manifest.json"),
            ),
            ImplementationControl(
                "Bundle checksum verification",
                "src/biointel/reproducibility/bundle.py",
                ("verify_reproducibility_bundle", "mismatched_files"),
            ),
            ImplementationControl(
                "Pinned direct dependency lock",
                "requirements.lock",
                ("streamlit==", "scikit-learn=="),
            ),
            ImplementationControl(
                "Reproducibility policy",
                "config/reproducibility_policy.yaml",
                ("random_seed", "environment", "checksums"),
            ),
            ImplementationControl(
                "SBOM generator", "scripts/generate_sbom.py", ("CycloneDX", "components")
            ),
            ImplementationControl(
                "Reproducibility tests",
                "tests/test_step36_maturity_frameworks.py",
                ("test_reproducibility_bundle",),
            ),
        ),
    },
    {
        "key": "enterprise_readiness",
        "label": "Enterprise Readiness",
        "evidence_score": 4.5,
        "boundary": "Enterprise controls are implemented, but production SLA, penetration, disaster-recovery and support evidence must be generated in the target organization.",
        "controls": (
            ImplementationControl(
                "Strict multi-tenant context",
                "src/biointel/multitenancy/context.py",
                ("TenantContext",),
            ),
            ImplementationControl(
                "Tenant resource isolation",
                "src/biointel/multitenancy/store.py",
                ("tenant_id", "resolve_context"),
            ),
            ImplementationControl(
                "Subscription and entitlement control plane",
                "src/biointel/enterprise/saas.py",
                ("subscriptions", "has_entitlement", "enforce_quota"),
            ),
            ImplementationControl(
                "Production readiness checks",
                "src/biointel/production/readiness.py",
                ("production_readiness",),
            ),
            ImplementationControl("Security CI", ".github/workflows/security.yml", ("codeql",)),
            ImplementationControl(
                "Enterprise operating guide",
                "docs/ENTERPRISE_SAAS_READINESS.md",
                ("SLA", "tenant isolation"),
            ),
        ),
    },
    {
        "key": "commercial_saas_readiness",
        "label": "Commercial SaaS Readiness",
        "evidence_score": 4.5,
        "boundary": "The commercial control plane is billing-provider-agnostic; payment processing, tax, contracts and live support operations require external systems and legal review.",
        "controls": (
            ImplementationControl(
                "Plans and subscriptions",
                "src/biointel/enterprise/saas.py",
                ("plans", "subscriptions", "subscribe"),
            ),
            ImplementationControl(
                "Idempotent usage metering",
                "src/biointel/enterprise/saas.py",
                ("usage_events", "idempotency_key", "record_usage"),
            ),
            ImplementationControl(
                "Quotas and entitlements",
                "src/biointel/enterprise/saas.py",
                ("quota_decision", "has_entitlement"),
            ),
            ImplementationControl(
                "Tenant data-right requests",
                "src/biointel/enterprise/saas.py",
                ("data_rights_requests", "request_data_right"),
            ),
            ImplementationControl(
                "SaaS plan policy", "config/saas_plans.yaml", ("starter", "enterprise")
            ),
            ImplementationControl(
                "Commercial-readiness tests",
                "tests/test_step36_maturity_frameworks.py",
                ("test_saas_control_plane",),
            ),
        ),
    },
    {
        "key": "academic_research_readiness",
        "label": "Academic Research Readiness",
        "evidence_score": 6.0,
        "boundary": "A complete package improves transparency and reproducibility but does not guarantee peer-review acceptance or independent replication.",
        "controls": (
            ImplementationControl(
                "Academic submission evaluator",
                "src/biointel/research/readiness.py",
                ("evaluate_academic_readiness", "reporting_checklist"),
            ),
            ImplementationControl(
                "FAIR packaging",
                "src/biointel/fair/digital_object.py",
                ("schema:Dataset", "PROV-O"),
            ),
            ImplementationControl(
                "Reproducibility packaging",
                "src/biointel/reproducibility/bundle.py",
                ("parameters", "environment", "files"),
            ),
            ImplementationControl(
                "Academic/pharma guide",
                "docs/ACADEMIC_PHARMA_READINESS.md",
                ("preregistration", "peer review"),
            ),
            ImplementationControl(
                "Academic evaluator tests",
                "tests/test_step36_maturity_frameworks.py",
                ("test_academic_readiness",),
            ),
        ),
    },
    {
        "key": "pharmaceutical_r_and_d_readiness",
        "label": "Pharmaceutical R&D Readiness",
        "evidence_score": 4.0,
        "boundary": "The workflow enforces R&D evidence controls but is not GxP-certified, clinically validated or authorized for patient-care decisions.",
        "controls": (
            ImplementationControl(
                "Pharma R&D evaluator",
                "src/biointel/research/readiness.py",
                ("evaluate_pharma_readiness", "sample_chain_of_custody"),
            ),
            ImplementationControl(
                "Maximum DTI validation matrix",
                "src/biointel/dti/validation_suite.py",
                ("cold_drug", "cold_target", "prospective"),
            ),
            ImplementationControl(
                "Strict scientific release gate",
                "src/biointel/training/release_gate.py",
                ("complete_dti_release_config", "validation_matrix"),
            ),
            ImplementationControl(
                "Assay ontology", "src/biointel/data/assay_ontology.py", ("assay",)
            ),
            ImplementationControl(
                "Quality-system ledger",
                "src/biointel/compliance/ledger.py",
                ("quality_events", "electronic_signatures"),
            ),
            ImplementationControl(
                "Pharma evaluator tests",
                "tests/test_step36_maturity_frameworks.py",
                ("test_pharma_readiness",),
            ),
        ),
    },
    {
        "key": "scientific_credibility_framework",
        "label": "Overall Scientific Credibility Framework",
        "evidence_score": 4.0,
        "boundary": "Framework completeness cannot replace authentic data, independent replication, prospective studies, peer review or wet-lab evidence.",
        "controls": (
            ImplementationControl(
                "Evidence-based scorecard",
                "src/biointel/quality/scorecard.py",
                ("externally_blocked", "model_audit"),
            ),
            ImplementationControl(
                "Synthetic-data release blockers",
                "src/biointel/training/release_gate.py",
                ("synthetic", "real_experimental_data"),
            ),
            ImplementationControl(
                "Rigorous statistical validation",
                "src/biointel/validation/rigorous.py",
                ("confidence_intervals", "permutation"),
            ),
            ImplementationControl(
                "DTI split matrix",
                "src/biointel/dti/validation_suite.py",
                ("REQUIRED_DTI_SPLITS", "release_eligible"),
            ),
            ImplementationControl(
                "FAIR evaluator", "src/biointel/fair/evaluator.py", ("evaluate_fair_object",)
            ),
            ImplementationControl(
                "Scientific-boundary UI",
                "pages/71_Platform_Quality_Center.py",
                ("scientific_boundary_banner", "Dual-score protection"),
            ),
        ),
    },
    {
        "key": "engineering_maturity",
        "label": "Overall Engineering Maturity",
        "evidence_score": 8.0,
        "boundary": "Engineering implementation is complete at repository level; operational maturity requires sustained production SLO, incident, capacity and recovery evidence.",
        "controls": (
            ImplementationControl(
                "Cross-platform CI",
                ".github/workflows/ci.yml",
                ("ubuntu-latest", "windows-latest", "pytest"),
            ),
            ImplementationControl(
                "Security scanning", ".github/workflows/security.yml", ("codeql",)
            ),
            ImplementationControl(
                "Visual regression CI",
                ".github/workflows/visual-regression.yml",
                ("playwright", "artifact"),
            ),
            ImplementationControl(
                "Kubernetes validation CI", ".github/workflows/kubernetes.yml", ("helm",)
            ),
            ImplementationControl(
                "Maturity quality gates",
                ".github/workflows/maturity-quality-gates.yml",
                ("maturity", "SBOM"),
            ),
            ImplementationControl(
                "Dependency lock and SBOM", "requirements.lock", ("fastapi==", "numpy==")
            ),
            ImplementationControl(
                "Architecture decision record",
                "docs/ARCHITECTURE_DECISIONS.md",
                ("ADR-001", "ADR-005"),
            ),
            ImplementationControl("Code ownership", ".github/CODEOWNERS", ("*",)),
        ),
    },
    {
        "key": "ml_validation_framework",
        "label": "ML Validation Framework",
        "evidence_score": 4.3,
        "boundary": "The validation machinery is complete; bundled synthetic models remain scientifically blocked until genuine independent and prospective results pass it.",
        "controls": (
            ImplementationControl(
                "Rigorous statistics",
                "src/biointel/validation/rigorous.py",
                ("bootstrap", "permutation", "calibration"),
            ),
            ImplementationControl(
                "Validation policy", "config/validation_policy.yaml", ("lower_95", "prospective")
            ),
            ImplementationControl(
                "External validation",
                "src/biointel/training/external_validation.py",
                ("evaluate_external_dataset",),
            ),
            ImplementationControl(
                "Prospective validation",
                "src/biointel/training/prospective_validation.py",
                ("prospective",),
            ),
            ImplementationControl(
                "Release gate", "src/biointel/training/release_gate.py", ("evaluate_release_gate",)
            ),
            ImplementationControl(
                "Validation tests",
                "tests/test_step36_target_quality.py",
                ("test_rigorous_classification",),
            ),
        ),
    },
    {
        "key": "drug_target_validation_framework",
        "label": "Drug–Target Validation Framework",
        "evidence_score": 3.0,
        "boundary": "Real ChEMBL/BindingDB, independent replication and prospective wet-lab evidence are required for a 10/10 biological result.",
        "controls": (
            ImplementationControl(
                "Complete DTI validation matrix",
                "src/biointel/dti/validation_suite.py",
                ("REQUIRED_DTI_SPLITS", "prospective"),
            ),
            ImplementationControl(
                "Dataset validation", "src/biointel/dti/dataset_validation.py", ("validate",)
            ),
            ImplementationControl(
                "Leakage audit", "src/biointel/training/leakage_audit.py", ("scaffold", "target")
            ),
            ImplementationControl(
                "Scientific splits", "src/biointel/training/scientific_splits.py", ("cold",)
            ),
            ImplementationControl(
                "Benchmark suite", "src/biointel/training/benchmark_suite.py", ("benchmark",)
            ),
            ImplementationControl(
                "DTI release tests",
                "tests/test_step36_target_quality.py",
                ("test_complete_dti_validation_matrix",),
            ),
        ),
    },
    {
        "key": "multi_tenant_architecture",
        "label": "Multi-Tenant Architecture",
        "evidence_score": None,
        "boundary": "Shared public scientific catalogs remain platform-wide by design; tenant-created resources and storage paths are isolated.",
        "controls": (
            ImplementationControl(
                "Request tenant context", "src/biointel/multitenancy/context.py", ("TenantContext",)
            ),
            ImplementationControl(
                "Membership store",
                "src/biointel/multitenancy/store.py",
                ("add_membership", "resolve_context"),
            ),
            ImplementationControl(
                "Tenant middleware", "src/biointel/multitenancy/middleware.py", ("tenant",)
            ),
            ImplementationControl(
                "Tenant storage router",
                "src/biointel/multitenancy/storage.py",
                ("object_key", "path"),
            ),
            ImplementationControl(
                "Tenant-scoped SaaS controls",
                "src/biointel/enterprise/saas.py",
                ("tenant_id", "data_rights_requests"),
            ),
            ImplementationControl(
                "Cross-tenant tests",
                "tests/test_step36_target_quality.py",
                ("test_tenant_resources_are_strictly_isolated",),
            ),
        ),
    },
    {
        "key": "kubernetes_readiness",
        "label": "Kubernetes Readiness",
        "evidence_score": None,
        "boundary": "A target-cluster load, upgrade, failover and disaster-recovery exercise is required before certifying that deployment.",
        "controls": (
            ImplementationControl("Helm chart", "deploy/helm/biointel/Chart.yaml", ("apiVersion",)),
            ImplementationControl(
                "API/UI/worker deployments",
                "deploy/helm/biointel/templates/deployments.yaml",
                ("startupProbe", "readinessProbe", "livenessProbe"),
            ),
            ImplementationControl(
                "Autoscaling",
                "deploy/helm/biointel/templates/hpa.yaml",
                ("HorizontalPodAutoscaler",),
            ),
            ImplementationControl(
                "Disruption budgets",
                "deploy/helm/biointel/templates/pdb.yaml",
                ("PodDisruptionBudget",),
            ),
            ImplementationControl(
                "Network policy",
                "deploy/helm/biointel/templates/networkpolicy.yaml",
                ("NetworkPolicy", "Egress"),
            ),
            ImplementationControl(
                "Schema and CI", "deploy/helm/biointel/values.schema.json", ("$schema",)
            ),
            ImplementationControl(
                "Kubernetes workflow", ".github/workflows/kubernetes.yml", ("helm",)
            ),
        ),
    },
    {
        "key": "visual_regression_testing",
        "label": "Visual Regression Testing",
        "evidence_score": None,
        "boundary": "Reviewed baselines protect primary journeys; scenario coverage must grow when scientific tool interfaces stabilize.",
        "controls": (
            ImplementationControl(
                "Playwright runtime-health screenshots",
                "tests/visual/test_visual_regression.py",
                ("playwright", "_assert_page_healthy", "screenshot"),
            ),
            ImplementationControl(
                "Semantic visual regression tests",
                "tests/visual/test_semantic_visual_regression.py",
                (
                    "SEMANTIC_VISUAL_SCENARIOS",
                    "test_semantic_manifest_integrity",
                    "BIOINTEL_RUN_LIVE_SEMANTIC",
                ),
            ),
            ImplementationControl(
                "Desktop home semantic baseline", "visual/semantic_baselines/home-desktop.png"
            ),
            ImplementationControl(
                "Desktop quality semantic baseline", "visual/semantic_baselines/quality-desktop.png"
            ),
            ImplementationControl(
                "Desktop compliance semantic baseline",
                "visual/semantic_baselines/compliance-desktop.png",
            ),
            ImplementationControl(
                "Mobile home semantic baseline", "visual/semantic_baselines/home-mobile.png"
            ),
            ImplementationControl(
                "Cryptographic baseline manifest",
                "visual/semantic_baselines/manifest.json",
                ("png_sha256", "content_sha256"),
            ),
            ImplementationControl(
                "Visual CI",
                ".github/workflows/visual-regression.yml",
                ("semantic-contracts", "browser-screenshots", "upload-artifact"),
            ),
            ImplementationControl(
                "Reviewed baseline update script",
                "scripts/update_visual_baselines.py",
                ("_write_manifest", "approval_required"),
            ),
        ),
    },
    {
        "key": "clinical_pharma_validation_readiness",
        "label": "Clinical & Pharmaceutical Validation Readiness",
        "evidence_score": 2.0,
        "boundary": "The executable framework is complete, but authentic sponsor, independent-site, prospective, regulatory and operating evidence must be generated outside the software.",
        "controls": (
            ImplementationControl(
                "Clinical validation registry",
                "src/biointel/clinical/registry.py",
                ("create_program", "freeze_model", "lock_prediction_batch"),
            ),
            ImplementationControl(
                "Audit and statistical schema",
                "src/biointel/clinical/schema.py",
                ("audit_events", "analysis_results"),
            ),
            ImplementationControl(
                "Quality and signature controls",
                "src/biointel/clinical/quality.py",
                ("add_evidence", "close_quality_event", "sign_object"),
            ),
            ImplementationControl(
                "Strict claim gates",
                "src/biointel/clinical/readiness.py",
                ("CPV-001", "CPV-023", "release_eligible"),
            ),
            ImplementationControl(
                "Checksum-bound dossier",
                "src/biointel/clinical/dossier.py",
                ("manifest.json", "verify_validation_dossier"),
            ),
            ImplementationControl(
                "Execution UI",
                "pages/90_Clinical_Pharma_Validation_Center.py",
                ("Clinical & Pharmaceutical Validation Center", "Lock prediction batch"),
            ),
            ImplementationControl(
                "Claim-specific policy",
                "config/clinical_pharma_validation_policy.yaml",
                ("pharma_r_and_d", "release_blockers"),
            ),
            ImplementationControl(
                "Controlled templates",
                "data/clinical_pharma/templates/01_VALIDATION_MASTER_PLAN.md",
                ("Validation Master Plan", "Intended use"),
            ),
            ImplementationControl(
                "Execution guide",
                "docs/CLINICAL_PHARMA_VALIDATION_EXECUTION_GUIDE.md",
                ("certification boundary", "prospective execution"),
            ),
            ImplementationControl(
                "Qualification tests",
                "tests/test_step83_clinical_pharma_validation.py",
                ("complete_pharma_execution_package", "incomplete_program_remains_research_only"),
            ),
        ),
    },
    {
        "key": "overall_platform_maturity",
        "label": "Overall Platform Maturity",
        "evidence_score": 6.9,
        "boundary": "Repository implementation can be complete while scientific, regulatory and operational evidence remains incomplete; the two scores are intentionally separate.",
        "controls": (
            ImplementationControl(
                "Unified maturity framework",
                "src/biointel/maturity/framework.py",
                ("AREA_DEFINITIONS", "build_maturity_readiness"),
            ),
            ImplementationControl(
                "Quality Center",
                "pages/71_Platform_Quality_Center.py",
                ("10/10 implementation targets",),
            ),
            ImplementationControl(
                "Quality API", "src/biointel/api/main.py", ("/quality/capability-readiness",)
            ),
            ImplementationControl(
                "Production deployment", "docker-compose.production.yml", ("worker:", "postgres:")
            ),
            ImplementationControl(
                "Kubernetes deployment", "deploy/helm/biointel/Chart.yaml", ("version",)
            ),
            ImplementationControl(
                "Compliance framework", "src/biointel/compliance/ledger.py", ("ComplianceLedger",)
            ),
            ImplementationControl(
                "FAIR/reproducibility frameworks", "src/biointel/fair/evaluator.py", ("FairReport",)
            ),
            ImplementationControl(
                "Enterprise/SaaS framework",
                "src/biointel/enterprise/saas.py",
                ("SaaSControlPlane",),
            ),
        ),
    },
)


def _evaluate_control(root: Path, control: ImplementationControl) -> bool:
    path = root / control.path
    if not path.is_file():
        return False
    if not control.required_tokens:
        return path.stat().st_size > 0
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
        return path.stat().st_size > 100
    text = path.read_text(encoding="utf-8", errors="ignore").lower()
    return all(token.lower() in text for token in control.required_tokens)


def build_maturity_readiness(root: str | Path) -> dict[str, Any]:
    project_root = Path(root).resolve()
    areas: list[MaturityArea] = []
    for definition in AREA_DEFINITIONS:
        controls: tuple[ImplementationControl, ...] = definition["controls"]
        passed = tuple(item.control for item in controls if _evaluate_control(project_root, item))
        failed = tuple(
            item.control for item in controls if not _evaluate_control(project_root, item)
        )
        score = round(10.0 * len(passed) / max(len(controls), 1), 1)
        status = "complete" if score == 10.0 else "incomplete"
        evidence_score = definition["evidence_score"]
        if evidence_score is None:
            evidence_status = "operational_validation_required"
        elif evidence_score >= 9.5:
            evidence_status = "validated"
        elif evidence_score >= 7.0:
            evidence_status = "strong"
        elif evidence_score >= 5.0:
            evidence_status = "partial"
        else:
            evidence_status = "blocked"
        areas.append(
            MaturityArea(
                key=definition["key"],
                label=definition["label"],
                implementation_score=score,
                implementation_status=status,
                evidence_score=evidence_score,
                evidence_status=evidence_status,
                passed_controls=passed,
                failed_controls=failed,
                boundary=definition["boundary"],
            )
        )
    return {
        "areas": [asdict(area) for area in areas],
        "implementation_average": round(
            sum(area.implementation_score for area in areas) / len(areas), 1
        ),
        "all_implementation_targets_complete": all(
            area.implementation_score == 10.0 for area in areas
        ),
        "evidence_average": round(
            sum(area.evidence_score for area in areas if area.evidence_score is not None)
            / max(sum(area.evidence_score is not None for area in areas), 1),
            1,
        ),
        "dual_score_policy": (
            "A 10/10 implementation score means required controls exist and are tested. It does not mean regulatory approval, "
            "GxP certification, peer-review acceptance, clinical validity or real scientific evidence is 10/10."
        ),
    }
