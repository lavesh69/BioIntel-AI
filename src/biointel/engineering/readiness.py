from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EngineeringControl:
    name: str
    path: str
    tokens: tuple[str, ...] = ()


@dataclass(frozen=True)
class EngineeringArea:
    key: str
    label: str
    implementation_score: float
    status: str
    passed_controls: tuple[str, ...]
    failed_controls: tuple[str, ...]
    evidence_boundary: str


DEFINITIONS: tuple[dict[str, Any], ...] = (
    {"key":"ci_cd_maturity","label":"CI/CD Maturity","boundary":"Repository automation is complete; production approvals, credentials and organization-specific release governance remain operational responsibilities.","controls":(
        EngineeringControl("Matrix CI", ".github/workflows/ci.yml", ("matrix", "unit-tests", "integration-tests")),
        EngineeringControl("Release provenance", ".github/workflows/release.yml", ("attest-build-provenance", "sha256sum")),
        EngineeringControl("Security pipeline", ".github/workflows/security.yml", ("codeql", "dependency-review-action")),
        EngineeringControl("Quality gates", "scripts/engineering_quality_gate.py", ("run_engineering_gates", "--json-output")),
        EngineeringControl("Branch/release policy", "docs/engineering/CI_CD_RELEASES.md", ("protected branch", "rollback")),
    )},
    {"key":"dependency_management","label":"Dependency Management","boundary":"Locks and audits reduce supply-chain risk; controlled updates still require review and compatibility testing.","controls":(
        EngineeringControl("Exact runtime lock", "requirements.lock", ("streamlit==", "scikit-learn==")),
        EngineeringControl("Exact CI tool lock", "requirements-ci.txt", ("coverage==", "mypy==", "pip-audit==")),
        EngineeringControl("Dependency policy", "config/dependency_policy.yaml", ("update_cadence", "vulnerability_sla")),
        EngineeringControl("Lock verifier", "scripts/verify_dependency_lock.py", ("verify_lock", "sha256")),
        EngineeringControl("Automated dependency review", ".github/workflows/dependency-management.yml", ("dependency-review-action", "pip-audit")),
    )},
    {"key":"reproducible_builds","label":"Reproducible Builds","boundary":"Deterministic packaging is implemented; byte identity also depends on the qualified builder image and source inputs.","controls":(
        EngineeringControl("Deterministic release builder", "src/biointel/engineering/release.py", ("SOURCE_DATE_EPOCH", "FIXED_ZIP_TIMESTAMP", "sha256")),
        EngineeringControl("Build policy", "config/build_policy.yaml", ("source_date_epoch", "deterministic")),
        EngineeringControl("SBOM generation", "scripts/generate_sbom.py", ("CycloneDX",)),
        EngineeringControl("Provenance manifest", "src/biointel/engineering/release.py", ("build_provenance", "verify_release_bundle")),
        EngineeringControl("Reproducibility tests", "tests/test_step37_engineering_excellence.py", ("test_reproducible_release_bundle",)),
    )},
    {"key":"containerization","label":"Containerization","boundary":"The image is hardened and reproducible; registry signing, runtime policies and host security remain deployment concerns.","controls":(
        EngineeringControl("Multi-stage non-root image", "Dockerfile.production", ("AS builder", "USER 10001:10001", "read-only")),
        EngineeringControl("Container smoke test", "tests/integration/test_container_contract.py", ("Dockerfile.production", "HEALTHCHECK")),
        EngineeringControl("Image scanning", ".github/workflows/container.yml", ("trivy", "hadolint")),
        EngineeringControl("OCI labels and health", "Dockerfile.production", ("org.opencontainers.image", "HEALTHCHECK")),
        EngineeringControl("Production compose", "docker-compose.production.yml", ("read_only: true", "cap_drop")),
    )},
    {"key":"kubernetes_readiness","label":"Kubernetes Readiness","boundary":"Manifests are production-oriented; a target-cluster failure, upgrade and restore exercise remains required.","controls":(
        EngineeringControl("Helm schema", "deploy/helm/biointel/values.schema.json", ("$schema",)),
        EngineeringControl("Autoscaling and disruption", "deploy/helm/biointel/templates/hpa.yaml", ("HorizontalPodAutoscaler", "behavior")),
        EngineeringControl("Topology and rollout", "deploy/helm/biointel/templates/deployments.yaml", ("topologySpreadConstraints", "RollingUpdate")),
        EngineeringControl("Policy resources", "deploy/helm/biointel/templates/platform-policies.yaml", ("ResourceQuota", "LimitRange")),
        EngineeringControl("Cluster validation CI", ".github/workflows/kubernetes.yml", ("kubeconform", "kind")),
    )},
    {"key":"cloud_readiness","label":"Cloud Readiness","boundary":"Portable IaC and service contracts exist; account landing zones, costs and regulated-cloud controls are organization-specific.","controls":(
        EngineeringControl("Cloud-neutral deployment contract", "deploy/cloud/README.md", ("AWS", "Azure", "Google Cloud")),
        EngineeringControl("Terraform root", "deploy/terraform/main.tf", ("required_version", "module")),
        EngineeringControl("AWS example", "deploy/cloud/aws/README.md", ("EKS", "RDS", "S3")),
        EngineeringControl("Azure example", "deploy/cloud/azure/README.md", ("AKS", "PostgreSQL", "Blob")),
        EngineeringControl("GCP example", "deploy/cloud/gcp/README.md", ("GKE", "Cloud SQL", "Cloud Storage")),
    )},
    {"key":"horizontal_scalability","label":"Horizontal Scalability","boundary":"Stateless services and scaling contracts are implemented; real throughput depends on target infrastructure and workload data.","controls":(
        EngineeringControl("Scaling contract", "src/biointel/production/scaling.py", ("ScalingProfile", "validate_horizontal_scaling")),
        EngineeringControl("External state services", "docker-compose.production.yml", ("postgres:", "redis:", "minio:")),
        EngineeringControl("HPA policies", "deploy/helm/biointel/templates/hpa.yaml", ("scaleUp", "scaleDown")),
        EngineeringControl("Worker scaling", "deploy/helm/biointel/values.yaml", ("worker", "autoscaling")),
        EngineeringControl("Scalability tests", "tests/test_step37_engineering_excellence.py", ("test_horizontal_scaling_contract",)),
    )},
    {"key":"load_testing","label":"Load Testing","boundary":"Repeatable thresholds and scenarios exist; certified capacity requires execution on production-equivalent infrastructure.","controls":(
        EngineeringControl("Locust scenarios", "tests/performance/locustfile.py", ("HttpUser", "between")),
        EngineeringControl("k6 scenarios", "tests/performance/k6_load.js", ("thresholds", "http_req_duration")),
        EngineeringControl("Performance thresholds", "config/performance_thresholds.yaml", ("p95_ms", "error_rate")),
        EngineeringControl("Performance gate", "scripts/run_performance_gate.py", ("evaluate_performance", "threshold")),
        EngineeringControl("Scheduled performance CI", ".github/workflows/performance.yml", ("schedule", "k6", "locust")),
    )},
    {"key":"stress_testing","label":"Stress Testing","boundary":"Stress, spike and soak profiles are codified; environment-specific breaking points must be measured during qualification.","controls":(
        EngineeringControl("Stress profile", "tests/performance/k6_stress.js", ("stages", "500")),
        EngineeringControl("Spike profile", "tests/performance/k6_spike.js", ("stages", "1000")),
        EngineeringControl("Soak profile", "tests/performance/k6_soak.js", ("30m", "thresholds")),
        EngineeringControl("Resource guardrails", "config/performance_thresholds.yaml", ("stress", "soak")),
        EngineeringControl("Stress runbook", "docs/runbooks/PERFORMANCE_AND_CAPACITY.md", ("breaking point", "rollback")),
    )},
    {"key":"integration_testing","label":"Integration Testing","boundary":"Service contracts are tested in isolation and compose; remote providers still require approved sandbox credentials.","controls":(
        EngineeringControl("API integration contracts", "tests/integration/test_api_contracts.py", ("TestClient", "/ready")),
        EngineeringControl("Storage integration contracts", "tests/integration/test_storage_contracts.py", ("TenantStorageRouter",)),
        EngineeringControl("Integration compose", "docker-compose.integration.yml", ("integration-tests", "service_healthy")),
        EngineeringControl("Integration CI", ".github/workflows/ci.yml", ("integration-tests", "docker compose")),
        EngineeringControl("Contract fixtures", "tests/integration/conftest.py", ("isolated_workspace",)),
    )},
    {"key":"unit_testing","label":"Unit Testing","boundary":"Coverage and mutation targets are enforced on critical modules; coverage percentage is not proof of scientific correctness.","controls":(
        EngineeringControl("Coverage policy", "pyproject.toml", ("fail_under = 85", "branch = true")),
        EngineeringControl("Unit test marker", "pyproject.toml", ("unit:",)),
        EngineeringControl("Coverage CI", ".github/workflows/ci.yml", ("--cov-report=xml", "--cov-fail-under=85")),
        EngineeringControl("Mutation policy", "config/testing_policy.yaml", ("mutation_score_target",)),
        EngineeringControl("Unit test inventory", "tests/test_step37_engineering_excellence.py", ("test_engineering_readiness_is_complete",)),
    )},
    {"key":"end_to_end_testing","label":"End-to-End Testing","boundary":"Primary journeys are automated; external scientific systems remain mocked unless a sandbox is explicitly enabled.","controls":(
        EngineeringControl("Primary journey suite", "tests/e2e/test_primary_journeys.py", ("playwright", "primary journeys")),
        EngineeringControl("API-to-worker journey", "tests/e2e/test_job_lifecycle.py", ("submit", "job_lifecycle")),
        EngineeringControl("E2E CI", ".github/workflows/e2e.yml", ("playwright", "streamlit run")),
        EngineeringControl("Deterministic E2E data", "tests/e2e/fixtures/workspace.json", ("tenant_id", "dataset")),
        EngineeringControl("E2E runbook", "docs/engineering/TESTING_STRATEGY.md", ("end-to-end", "test pyramid")),
    )},
    {"key":"browser_ui_testing","label":"Browser UI Testing","boundary":"Automated browser journeys cover primary workspaces; browser/device coverage must expand with supported-client policy.","controls":(
        EngineeringControl("Playwright journeys", "tests/e2e/test_primary_journeys.py", ("Playwright", "mobile", "cross-browser")),
        EngineeringControl("Accessibility browser assertions", "tests/e2e/test_accessibility.py", ("landmark", "keyboard")),
        EngineeringControl("Cross-browser CI", ".github/workflows/e2e.yml", ("chromium", "firefox", "webkit")),
        EngineeringControl("Browser artifacts", ".github/workflows/e2e.yml", ("upload-artifact", "screenshots")),
        EngineeringControl("UI health assertions", "tests/visual/test_visual_regression.py", ("_assert_page_healthy",)),
    )},
    {"key":"visual_regression_testing","label":"Visual Regression Testing","boundary":"Approved semantic and browser baselines protect primary interfaces; new interfaces require deliberate baseline review.","controls":(
        EngineeringControl("Semantic baselines", "visual/semantic_baselines/manifest.json", ("png_sha256", "json_sha256")),
        EngineeringControl("Browser baselines policy", "visual/README.md", ("approved", "health assertions", "diffs")),
        EngineeringControl("Semantic visual tests", "tests/visual/test_semantic_visual_regression.py", ("SEMANTIC_VISUAL_SCENARIOS", "test_semantic_manifest_integrity")),
        EngineeringControl("Browser visual tests", "tests/visual/test_visual_regression.py", ("pixel_tolerance", "changed_fraction")),
        EngineeringControl("Strict visual CI", ".github/workflows/visual-regression.yml", ("BIOINTEL_REQUIRE_BROWSER_BASELINES", "semantic-contracts")),
    )},
    {"key":"scientific_regression_testing","label":"Scientific Regression Testing","boundary":"Golden scientific outputs and statistical tolerances protect software behavior; they do not replace independent biological validation.","controls":(
        EngineeringControl("Scientific golden cases", "tests/scientific/golden_cases.json", ("sequence", "chemistry", "dti")),
        EngineeringControl("Scientific regression suite", "tests/scientific/test_golden_regression.py", ("tolerance", "golden_cases")),
        EngineeringControl("Scientific thresholds", "config/scientific_regression_thresholds.yaml", ("absolute_tolerance", "relative_tolerance")),
        EngineeringControl("Scientific CI gate", ".github/workflows/ci.yml", ("scientific-regression",)),
        EngineeringControl("Model release regression gate", "src/biointel/training/release_gate.py", ("validation_matrix",)),
    )},
    {"key":"code_modularity","label":"Code Modularity","boundary":"Architecture boundaries are enforced statically; ongoing feature work must preserve module ownership and dependency direction.","controls":(
        EngineeringControl("Architecture rules", "config/architecture_rules.yaml", ("layers", "forbidden_imports")),
        EngineeringControl("AST architecture checker", "src/biointel/engineering/quality_gates.py", ("ast.Import", "forbidden")),
        EngineeringControl("Architecture CI", ".github/workflows/code-quality.yml", ("check_architecture.py",)),
        EngineeringControl("Architecture documentation", "docs/architecture/OVERVIEW.md", ("dependency direction", "bounded")),
        EngineeringControl("Architecture tests", "tests/test_step37_engineering_excellence.py", ("test_architecture_rules_are_valid",)),
    )},
    {"key":"code_maintainability","label":"Code Maintainability","boundary":"Automated quality budgets reduce deterioration; human design review remains necessary for complex scientific workflows.","controls":(
        EngineeringControl("Lint/format/type gates", ".github/workflows/code-quality.yml", ("ruff", "black", "mypy")),
        EngineeringControl("Complexity budget", "config/quality_budgets.yaml", ("max_cyclomatic_complexity", "max_module_lines")),
        EngineeringControl("Maintainability gate", "src/biointel/engineering/quality_gates.py", ("quality_budgets", "technical_debt")),
        EngineeringControl("Pre-commit hooks", ".pre-commit-config.yaml", ("ruff", "black")),
        EngineeringControl("Code ownership", ".github/CODEOWNERS", ("src/biointel", "tests")),
    )},
    {"key":"technical_debt","label":"Technical Debt Management","boundary":"Debt is explicit, owned and expiry-controlled; the register must be actively maintained by the delivery team.","controls":(
        EngineeringControl("Debt register", "TECHNICAL_DEBT.yaml", ("owner", "due_date", "status")),
        EngineeringControl("Debt policy", "docs/engineering/TECHNICAL_DEBT_POLICY.md", ("severity", "expiry")),
        EngineeringControl("Overdue debt gate", "src/biointel/engineering/quality_gates.py", ("overdue", "due_date")),
        EngineeringControl("Debt CI", ".github/workflows/code-quality.yml", ("check_technical_debt.py",)),
        EngineeringControl("ADR register", "docs/architecture/decisions/README.md", ("ADR", "superseded")),
    )},
    {"key":"documentation_quality","label":"Documentation Quality","boundary":"Documentation is structured, versioned and tested; operational truth still depends on keeping it synchronized with releases.","controls":(
        EngineeringControl("MkDocs site", "mkdocs.yml", ("nav:", "strict: true")),
        EngineeringControl("Architecture docs", "docs/architecture/OVERVIEW.md", ("Architecture", "data flow")),
        EngineeringControl("Testing docs", "docs/engineering/TESTING_STRATEGY.md", ("unit", "integration", "e2e")),
        EngineeringControl("Runbooks", "docs/runbooks/INCIDENT_RESPONSE.md", ("severity", "recovery")),
        EngineeringControl("Docs CI", ".github/workflows/docs.yml", ("mkdocs build --strict",)),
    )},
    {"key":"developer_experience","label":"Developer Experience","boundary":"One-command workflows and a dev container are supplied; local performance depends on the developer workstation.","controls":(
        EngineeringControl("Make targets", "Makefile", ("bootstrap:", "quality:", "test:")),
        EngineeringControl("Task runner", "Taskfile.yml", ("version:", "tasks:")),
        EngineeringControl("Dev container", ".devcontainer/devcontainer.json", ("postCreateCommand", "forwardPorts")),
        EngineeringControl("Environment doctor", "scripts/dev_doctor.py", ("check_environment", "JSON")),
        EngineeringControl("Contributor guide", "CONTRIBUTING.md", ("pull request", "quality gates")),
    )},
    {"key":"installation_experience","label":"Installation Experience","boundary":"Installers validate supported environments; optional native scientific tools may still require platform-specific packages.","controls":(
        EngineeringControl("Cross-platform bootstrap", "scripts/bootstrap.py", ("virtual environment", "verify_dependency_lock")),
        EngineeringControl("Windows installer", "INSTALL_WINDOWS.bat", ("bootstrap.py", "dev_doctor.py")),
        EngineeringControl("Linux installer", "INSTALL_LINUX.sh", ("bootstrap.py", "dev_doctor.py")),
        EngineeringControl("macOS installer", "INSTALL_MACOS.sh", ("bootstrap.py", "dev_doctor.py")),
        EngineeringControl("Installation smoke CI", ".github/workflows/installation.yml", ("windows-latest", "macos-latest")),
    )},
    {"key":"reproducibility","label":"Reproducibility","boundary":"Seeds, environments, inputs and outputs are captured; external service availability and licensed datasets remain outside the bundle.","controls":(
        EngineeringControl("Research bundles", "src/biointel/reproducibility/bundle.py", ("random_seed", "manifest.json")),
        EngineeringControl("Build bundles", "src/biointel/engineering/release.py", ("SOURCE_DATE_EPOCH", "verify_release_bundle")),
        EngineeringControl("Locked environment", "requirements.lock", ("numpy==", "pandas==")),
        EngineeringControl("Reproducibility policy", "config/reproducibility_policy.yaml", ("random_seed", "checksums")),
        EngineeringControl("Qualification script", "scripts/qualify_step37.py", ("build_engineering_readiness", "run_engineering_gates")),
    )},
)


def _passes(root: Path, control: EngineeringControl) -> bool:
    path = root / control.path
    if not path.is_file() or path.stat().st_size == 0:
        return False
    if not control.tokens:
        return True
    text = path.read_text(encoding="utf-8", errors="ignore").lower()
    return all(token.lower() in text for token in control.tokens)


def build_engineering_readiness(root: str | Path) -> dict[str, Any]:
    base = Path(root).resolve()
    areas: list[EngineeringArea] = []
    for definition in DEFINITIONS:
        controls = definition["controls"]
        passed = tuple(c.name for c in controls if _passes(base, c))
        failed = tuple(c.name for c in controls if not _passes(base, c))
        score = round(10.0 * len(passed) / len(controls), 1)
        areas.append(EngineeringArea(
            key=definition["key"], label=definition["label"], implementation_score=score,
            status="complete" if score == 10.0 else "incomplete", passed_controls=passed,
            failed_controls=failed, evidence_boundary=definition["boundary"],
        ))
    return {
        "schema": "biointel.engineering-readiness.v1",
        "areas": [asdict(a) for a in areas],
        "implementation_average": round(sum(a.implementation_score for a in areas) / len(areas), 1),
        "all_targets_complete": all(a.implementation_score == 10.0 for a in areas),
        "control_count": sum(len(d["controls"]) for d in DEFINITIONS),
        "dual_score_policy": "10/10 is repository implementation readiness, not proof of production capacity or scientific validity.",
    }
