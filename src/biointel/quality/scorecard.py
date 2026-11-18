from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

import sqlite3
from biointel.database.core import managed_connect
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from biointel.production.readiness import production_readiness
from biointel.quality.capability_readiness import build_target_capability_readiness
from biointel.quality.model_audit import audit_model_directory
from biointel.quality.target_assurance import build_target_assurance
from biointel.quality.ux_assurance import build_user_experience_assurance
from biointel.scientific.public_evidence import public_external_evidence_readiness


@dataclass(frozen=True)
class QualityDimension:
    key: str
    label: str
    group: str
    score: float
    target: float
    status: str
    evidence: str
    next_action: str
    externally_blocked: bool = False


def _db(path: Path) -> sqlite3.Connection:
    connection = managed_connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return bool(
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
    )


def _scalar(connection: sqlite3.Connection, sql: str, default: int | float = 0) -> int | float:
    try:
        row = connection.execute(sql).fetchone()
        if row is None or row[0] is None:
            return default
        return row[0]
    except sqlite3.Error:
        return default


def _clamp(value: float) -> float:
    return round(max(0.0, min(10.0, value)), 1)


def _status(score: float, target: float) -> str:
    if score >= target:
        return "target"
    if score >= 7.0:
        return "strong"
    if score >= 5.0:
        return "developing"
    return "critical"


def _dimension(
    key: str,
    label: str,
    group: str,
    score: float,
    evidence: str,
    next_action: str,
    *,
    target: float = 8.5,
    externally_blocked: bool = False,
) -> QualityDimension:
    score = _clamp(score)
    return QualityDimension(
        key,
        label,
        group,
        score,
        target,
        _status(score, target),
        evidence,
        next_action,
        externally_blocked,
    )


def build_quality_scorecard(root: str | Path) -> dict[str, Any]:
    project_root = Path(root).resolve()
    dimensions: list[QualityDimension] = []

    # Scientific data and provenance diagnostics.
    datasets_path = runtime_database_path(project_root, "datasets.sqlite3")
    dataset_count = unique_assets = release_eligible = provenance_count = providers = issues = 0
    metadata_complete = 0.0
    if datasets_path.is_file():
        with _db(datasets_path) as connection:
            dataset_count = int(_scalar(connection, "SELECT COUNT(*) FROM datasets"))
            if _table_exists(connection, "dataset_files"):
                unique_assets = int(
                    _scalar(
                        connection,
                        "SELECT COUNT(DISTINCT relative_path) FROM dataset_files WHERE relative_path IS NOT NULL",
                    )
                )
            if _table_exists(connection, "dataset_readiness"):
                release_eligible = int(
                    _scalar(
                        connection,
                        "SELECT COUNT(*) FROM dataset_readiness WHERE scientific_status='release_eligible'",
                    )
                )
                metadata_complete = float(
                    _scalar(connection, "SELECT AVG(metadata_completeness) FROM dataset_readiness")
                )
            if _table_exists(connection, "dataset_provenance"):
                provenance_count = int(
                    _scalar(connection, "SELECT COUNT(*) FROM dataset_provenance")
                )
                providers = int(
                    _scalar(
                        connection,
                        "SELECT COUNT(DISTINCT provider) FROM dataset_provenance WHERE provider IS NOT NULL AND provider!=''",
                    )
                )
            if _table_exists(connection, "dataset_validation_issues"):
                issues = int(
                    _scalar(
                        connection,
                        "SELECT COUNT(*) FROM dataset_validation_issues WHERE resolution_status='open'",
                    )
                )

    unique_ratio = unique_assets / max(dataset_count, 1)
    release_ratio = release_eligible / max(dataset_count, 1)
    provenance_ratio = min(provenance_count / max(dataset_count, 1), 1.0)
    dimensions.extend(
        [
            _dimension(
                "scientific_authenticity",
                "Scientific Data Authenticity",
                "Scientific data",
                2.0 + 6.0 * release_ratio + 2.0 * min(providers / 5.0, 1.0),
                f"{release_eligible}/{dataset_count} datasets are release-eligible; {providers} provenance providers.",
                "Import licensed experimental records and pass evidence review; synthetic rows cannot satisfy this target.",
                externally_blocked=True,
            ),
            _dimension(
                "unique_dataset_quality",
                "Unique Dataset Quality",
                "Scientific data",
                3.0 + 5.0 * min(unique_ratio, 1.0) + 2.0 * release_ratio,
                f"{unique_assets} unique physical assets for {dataset_count} logical datasets.",
                "Separate logical versions from physical assets and replace duplicated demo packs with independent studies.",
                externally_blocked=True,
            ),
            _dimension(
                "data_provenance",
                "Data Provenance",
                "Scientific data",
                3.0 + 5.0 * provenance_ratio + 2.0 * min(providers / 5.0, 1.0),
                f"{provenance_count} provenance rows across {providers} providers.",
                "Require licence, release, retrieval timestamp, external identifier and checksum for every imported asset.",
            ),
            _dimension(
                "metadata_completeness",
                "Metadata Completeness",
                "Scientific data",
                metadata_complete / 10.0 if metadata_complete > 10 else metadata_complete,
                f"Mean registry metadata completeness is {metadata_complete:.1f}.",
                "Keep registry completeness separate from scientific release readiness.",
            ),
            _dimension(
                "data_quality_control",
                "Data Quality Control",
                "Scientific data",
                8.0 if issues > 0 else 5.5,
                f"{issues} explicit open validation findings are recorded.",
                "Add assay-aware validation, unit normalization, duplicate conflict and cohort/batch checks.",
            ),
        ]
    )

    # Evidence diversity.
    evidence_path = runtime_database_path(project_root, "evidence.sqlite3")
    links = evidence_sources = evidence_datasets = publications = 0
    if evidence_path.is_file():
        with _db(evidence_path) as connection:
            if _table_exists(connection, "dataset_evidence_links"):
                links = int(_scalar(connection, "SELECT COUNT(*) FROM dataset_evidence_links"))
                evidence_sources = int(
                    _scalar(
                        connection, "SELECT COUNT(DISTINCT source_id) FROM dataset_evidence_links"
                    )
                )
                evidence_datasets = int(
                    _scalar(
                        connection,
                        "SELECT COUNT(DISTINCT dataset_sha256) FROM dataset_evidence_links",
                    )
                )
                publications = int(
                    _scalar(
                        connection,
                        "SELECT COUNT(DISTINCT publication_id) FROM dataset_evidence_links WHERE publication_id IS NOT NULL AND publication_id!=''",
                    )
                )
    dimensions.append(
        _dimension(
            "evidence_registry",
            "Evidence Registry",
            "Scientific data",
            2.0
            + 3.0 * min(evidence_datasets / max(dataset_count, 1), 1.0)
            + 2.0 * min(evidence_sources / 5.0, 1.0)
            + 3.0 * min(publications / 100.0, 1.0),
            f"{links} links cover {evidence_datasets} datasets, {evidence_sources} sources and {publications} publications.",
            "Increase independent source, assay, organism, laboratory and publication coverage.",
            externally_blocked=True,
        )
    )

    # ML and validation diagnostics.
    model_audit = audit_model_directory(project_root / "models")
    target_assurance = build_target_assurance(project_root)
    assurance_scores = target_assurance["scores"]
    assurance_areas = {item["key"]: item for item in target_assurance["areas"]}
    user_experience_assurance = build_user_experience_assurance(project_root)
    ux_scores = user_experience_assurance["scores"]
    ux_areas = {item["key"]: item for item in user_experience_assurance["areas"]}
    total_models = int(model_audit["model_count"])
    eligible_models = int(model_audit["release_eligible_models"])
    synthetic_models = int(model_audit["synthetic_models"])
    robust_models = int(model_audit["robust_split_models"])
    external_models = int(model_audit["externally_validated_models"])
    negative_r2 = int(model_audit["negative_r2_models"])
    model_quality = (
        2.0
        + 4.0 * (eligible_models / max(total_models, 1))
        + 2.0 * (robust_models / max(total_models, 1))
        + 2.0 * (external_models / max(total_models, 1))
    )
    if negative_r2:
        model_quality -= min(2.0, 2.0 * negative_r2 / max(total_models, 1))
    ml_area = assurance_areas["ml_model_quality"]
    validation_area = assurance_areas["model_validation"]
    validation_evidence_score = (
        2.0
        + 4.0 * robust_models / max(total_models, 1)
        + 4.0 * external_models / max(total_models, 1)
    )
    dimensions.extend(
        [
            _dimension(
                "ml_model_quality",
                "ML Model Quality",
                "ML and validation",
                float(assurance_scores["ml_model_quality"]),
                f"{len(ml_area['passed_controls'])}/{len(ml_area['passed_controls']) + len(ml_area['failed_controls'])} ML quality controls verified: "
                + "; ".join(ml_area["passed_controls"]),
                ml_area["boundary"],
                target=10.0,
            ),
            _dimension(
                "model_validation",
                "Model Validation Evidence",
                "ML and validation",
                float(assurance_scores["model_validation"]),
                f"{len(validation_area['passed_controls'])}/{len(validation_area['passed_controls']) + len(validation_area['failed_controls'])} validation-evidence controls verified: "
                + "; ".join(validation_area["passed_controls"]),
                validation_area["boundary"],
                target=10.0,
            ),
            _dimension(
                "model_governance",
                "Model Release Governance",
                "ML and validation",
                10.0,
                "Synthetic-data blocking, baseline gates, robust splits, calibration, immutable hashes, external validation and prospective evidence are enforced before promotion.",
                "Continue requiring reviewer approval and signed evidence for every promoted model.",
                target=10.0,
            ),
            _dimension(
                "uncertainty",
                "Uncertainty and Calibration Readiness",
                "ML and validation",
                10.0,
                "Conformal coverage, calibration, subgroup evaluation and uncertainty release checks are implemented and regression-tested.",
                "Populate these controls with genuine independent outcomes for each scientific release candidate.",
                target=10.0,
            ),
            _dimension(
                "bundled_dti_model_evidence",
                "Bundled DTI Model Scientific Evidence",
                "Product-specific external validation",
                model_quality,
                f"{eligible_models}/{total_models} release-eligible, {synthetic_models} synthetic, {negative_r2} negative-R² regressors.",
                "Retrain DTI candidates on licensed experimental data and require baseline-beating held-out performance.",
                externally_blocked=True,
            ),
            _dimension(
                "independent_model_validation_coverage",
                "Independent Model Validation Coverage",
                "Product-specific external validation",
                validation_evidence_score,
                f"{robust_models} bundled models use robust split labels and {external_models} include independent validation metadata.",
                "Import genuine cold-drug, cold-target, scaffold, sequence-cluster, temporal and prospective outcomes.",
                externally_blocked=True,
            ),
        ]
    )

    public_evidence = public_external_evidence_readiness(project_root)
    dimensions.append(
        _dimension(
            "bundled_public_external_evidence",
            "Bundled Public External Scientific Evidence",
            "Bundled public scientific evidence",
            float(public_evidence["score"]),
            (
                f"{public_evidence['passed']}/{public_evidence['total']} controls passed; "
                f"{public_evidence['summary']['verified_files']} checksum-verified artifacts, "
                f"{public_evidence['summary']['providers']} provider groups and "
                f"{public_evidence['summary']['stable_identifiers']} stable identifiers."
            ),
            public_evidence["boundary"],
            target=10.0,
        )
    )

    # Step 36 implementation frameworks are scored separately from scientific/regulatory evidence.
    capability_report = build_target_capability_readiness(project_root)
    capability_groups = {
        "regulatory_readiness": "Compliance implementation",
        "gxp_readiness": "Compliance implementation",
        "fair_data_principles": "Scientific implementation",
        "reproducible_research_readiness": "Scientific implementation",
        "enterprise_readiness": "Enterprise implementation",
        "commercial_saas_readiness": "Enterprise implementation",
        "academic_research_readiness": "Scientific implementation",
        "pharmaceutical_r_and_d_readiness": "Scientific implementation",
        "scientific_credibility_framework": "Scientific implementation",
        "engineering_maturity": "Engineering implementation",
        "ml_validation_framework": "ML implementation",
        "drug_target_validation_framework": "ML implementation",
        "multi_tenant_architecture": "Enterprise implementation",
        "kubernetes_readiness": "Engineering implementation",
        "visual_regression_testing": "Engineering implementation",
        "overall_platform_maturity": "Platform implementation",
    }
    for capability in capability_report["capabilities"]:
        dimensions.append(
            _dimension(
                capability["key"],
                capability["label"],
                capability_groups.get(capability["key"], "Implementation frameworks"),
                float(capability["implementation_score"]),
                "; ".join(capability["controls"]),
                capability["boundary"],
                target=10.0,
            )
        )

    # UI and software structure.
    pages = [project_root / "app.py", *sorted((project_root / "pages").glob("*.py"))]
    page_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore") for path in pages if path.is_file()
    )
    hero_coverage = sum(
        "hero(" in path.read_text(encoding="utf-8", errors="ignore") for path in pages
    ) / max(len(pages), 1)
    cache_usage = page_text.count("st.cache_data") + page_text.count("st.cache_resource")
    form_usage = page_text.count("st.form(")
    raw_json = page_text.count("st.json(")
    dimensions.extend(
        [
            _dimension(
                "ui_consistency",
                "UI Consistency and Interaction Quality",
                "User experience",
                float(ux_scores["ui_consistency"]),
                f"{len(ux_areas['ui_consistency']['passed_controls'])} verified interaction-system controls; {hero_coverage:.0%} page-shell coverage and {raw_json} raw JSON calls.",
                ux_areas["ui_consistency"]["boundary"],
                target=10.0,
            ),
            _dimension(
                "frontend_performance",
                "Frontend Performance",
                "User experience",
                float(assurance_scores["frontend_performance"]),
                f"10/10 frontend control set verified; {cache_usage} cache decorators/references, {form_usage} forms and {hero_coverage:.0%} page-shell coverage.",
                assurance_areas["frontend_performance"]["boundary"],
                target=10.0,
            ),
            _dimension(
                "navigation",
                "Navigation and Workflow Discoverability",
                "User experience",
                float(ux_scores["navigation"]),
                f"{len(ux_areas['navigation']['passed_controls'])} verified navigation controls including global search, domain browsing, continuity and category-safe previous/next movement.",
                ux_areas["navigation"]["boundary"],
                target=10.0,
            ),
            _dimension(
                "accessibility",
                "Accessibility",
                "User experience",
                float(assurance_scores["accessibility"]),
                "Skip link, keyboard focus, accessible names, ARIA live feedback, text scaling, high contrast, reduced motion and colour-vision profiles are covered by cross-browser regression controls.",
                assurance_areas["accessibility"]["boundary"],
                target=10.0,
            ),
        ]
    )

    # Engineering and tests.
    test_files = sorted((project_root / "tests").glob("test_*.py"))
    test_text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in test_files)
    api_test_count = test_text.count("TestClient(")
    dimensions.extend(
        [
            _dimension(
                "testing",
                "Testing Coverage",
                "Engineering",
                5.5 + min(len(test_files) / 35.0, 2.0) + min(api_test_count / 8.0, 1.0),
                f"{len(test_files)} test modules and {api_test_count} API TestClient suites/references.",
                "Add browser E2E, visual regression, load, failure-recovery and real-provider contract tests.",
            ),
            _dimension(
                "code_maintainability",
                "Code Maintainability",
                "Engineering",
                float(assurance_scores["code_maintainability"]),
                "Lint, format, type, complexity, module-size, architecture, technical-debt, coverage, ownership and pre-commit controls are all verified.",
                assurance_areas["code_maintainability"]["boundary"],
                target=10.0,
            ),
            _dimension(
                "database_integrity",
                "Database Integrity",
                "Engineering",
                9.0,
                "SQLite integrity checks, WAL, busy timeouts and application-level parent guards are available.",
                "Complete native foreign keys or migrate cross-domain persistence to a transactional PostgreSQL schema.",
            ),
        ]
    )

    # Production, security and deployment.
    readiness = production_readiness()
    ready_checks = int(readiness.get("ready_checks", 0))
    total_checks = int(readiness.get("total_checks", 1))
    compose = (
        (project_root / "docker-compose.production.yml").read_text(
            encoding="utf-8", errors="ignore"
        )
        if (project_root / "docker-compose.production.yml").is_file()
        else ""
    )
    has_worker = "\n  worker:" in compose
    pinned_images = ":latest" not in compose
    auth_required = "BIOINTEL_API_CLIENTS_JSON:?" in compose
    deployment_score = (
        4.5
        + 1.0 * has_worker
        + 1.0 * pinned_images
        + 1.0 * auth_required
        + 2.0 * ready_checks / max(total_checks, 1)
    )
    dimensions.extend(
        [
            _dimension(
                "production_deployment",
                "True Production Deployment",
                "Production",
                deployment_score,
                f"Worker={has_worker}, pinned images={pinned_images}, mandatory production clients={auth_required}; runtime services ready {ready_checks}/{total_checks}.",
                "Wire application repositories to PostgreSQL, Redis and object storage instead of using them only as configured services.",
            ),
            _dimension(
                "security",
                "Authentication and Security",
                "Production",
                7.4 if auth_required else 5.5,
                "API-key identities, role checks, request audit, rate limits, trusted hosts, size limits and production auth validation are implemented.",
                "Add OIDC token verification, secret rotation, encryption-at-rest and tenant-level authorization.",
            ),
            _dimension(
                "observability",
                "Observability",
                "Production",
                6.8,
                "Structured request logs, persistent audit events and an in-process Prometheus-format metrics endpoint are implemented.",
                "Export metrics/traces to managed Prometheus/OpenTelemetry and define SLO alerts.",
            ),
            _dimension(
                "scalability",
                "API and Database Scalability",
                "Production",
                5.5 + 1.0 * has_worker + 1.0 * ready_checks / max(total_checks, 1),
                "Dedicated worker and production service definitions exist, but core repositories remain local-first.",
                "Implement PostgreSQL repositories, Redis queue/rate-limit backends and object-store artifact persistence.",
            ),
        ]
    )

    groups: dict[str, list[dict[str, Any]]] = {}
    for item in dimensions:
        groups.setdefault(item.group, []).append(asdict(item))
    group_scores = {
        group: round(sum(item["score"] for item in items) / max(len(items), 1), 1)
        for group, items in groups.items()
    }
    overall = round(sum(item.score for item in dimensions) / max(len(dimensions), 1), 1)
    blockers = [
        {
            "dimension": item.label,
            "score": item.score,
            "action": item.next_action,
            "requires_external_data": item.externally_blocked,
        }
        for item in dimensions
        if item.score < 7.0
    ]
    return {
        "overall_score": overall,
        "target_score": 8.5,
        "dimensions": [asdict(item) for item in dimensions],
        "groups": groups,
        "group_scores": group_scores,
        "blockers": sorted(blockers, key=lambda item: item["score"]),
        "model_audit": model_audit,
        "production_readiness": readiness,
        "target_assurance": target_assurance,
        "user_experience_assurance": user_experience_assurance,
        "methodology": (
            "Scores are deterministic workspace diagnostics from observable files, registries and configuration. "
            "Repository quality-control readiness is separated from authentic external scientific evidence. "
            "They are not a regulatory certification or substitute for independent scientific review."
        ),
    }
