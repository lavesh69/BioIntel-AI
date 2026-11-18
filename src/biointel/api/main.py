from __future__ import annotations

import io
import json
import os
import tempfile
from dataclasses import asdict, replace
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, StreamingResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from biointel import __version__
from biointel.api.middleware import (
    OptionalApiKeyMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)
from biointel.api.schemas import (
    AdmetProfileRequest,
    AlignmentRequest,
    BioprocessAnalysisRequest,
    ConnectedHealthRequest,
    ConnectedSearchRequest,
    CopilotQueryRequest,
    CrisprDesignRequest,
    DataCurationRequest,
    DiscoveryBatchStandardizeRequest,
    DiscoveryCompoundRequest,
    DiscoveryDockingQualificationRequest,
    DiscoveryEndpointModelCardRequest,
    DiscoveryProjectCreateRequest,
    DiscoveryRankingRequest,
    DiscoverySimilarityRequest,
    DiscoveryTargetProfileRequest,
    DocumentCompareRequest,
    DocumentDatasetBridgeRequest,
    DocumentEvidenceBridgeRequest,
    DocumentOrganizeRequest,
    DocumentQuestionRequest,
    DtiBatchRequest,
    DtiPredictionRequest,
    ElisaAnalysisRequest,
    EnzymeKineticsRequest,
    EvidenceReviewRequest,
    ExperimentalDesignRequest,
    ExternalValidationRequest,
    FastqQcRequest,
    JobSubmitRequest,
    UnifiedReportRequest,
    UiRegressionRequest,
    OcrCorrectionRequest,
    PathwayEnrichmentRequest,
    PhylogenyRequest,
    PlateQcRequest,
    PrimerDesignRequest,
    ProteinAnnotationRequest,
    QpcrAnalysisRequest,
    ReleaseGateRequest,
    SequenceAnalysisRequest,
    StructureAnalysisRequest,
    SyntheticDatasetRequest,
    VariantSummaryRequest,
)
from biointel.api.security_store import ApiSecurityStore
from biointel.runtime_paths import runtime_data_path, runtime_report_path
from biointel.integrations import integration_summary
from biointel.assets.research_assets import (
    list_collections,
    search_assets,
)
from biointel.assurance import build_final_assurance
from biointel.bioinformatics_capabilities import (
    capabilities_dict as bioinformatics_capabilities_dict,
)
from biointel.synthetic.core import MODULE_SPECS, SyntheticGenerationConfig, SyntheticSafetyError
from biointel.synthetic.service import SyntheticWorkspaceService
from biointel.biotech.assays import qpcr_delta_delta_ct
from biointel.biotech.assays_advanced import (
    bioprocess_advanced_metrics,
    compare_enzyme_models,
    fit_elisa_calibration,
    fit_enzyme_model,
    inverse_calibration_with_flags,
)
from biointel.biotech.experimental_design import (
    equivalence_sample_size,
    noninferiority_sample_size,
    one_way_anova_sample_size,
    paired_sample_size,
    two_group_sample_size,
)
from biointel.biotech.lab_schema import plate_map_audit, plate_spatial_qc
from biointel.chemistry.admet import profile_admet
from biointel.chemistry.admet import profile_dict as admet_profile_dict
from biointel.chemistry.common_compounds import (
    load_common_compound_directory,
    search_common_compounds,
)
from biointel.chemistry.similarity_search import similarity_search
from biointel.compliance import controls as compliance_controls
from biointel.connected import (
    ENTITY_PROVIDER_DEFAULTS,
    ConnectedProviderService,
    public_connection_status,
    test_openai_connection,
)
from biointel.connected import (
    PROVIDERS as CONNECTED_PROVIDERS,
)
from biointel.connected import (
    provider_rows as connected_provider_rows,
)
from biointel.connected import (
    recent_health_checks as recent_connected_health_checks,
)
from biointel.connected import (
    recent_queries as recent_connected_queries,
)
from biointel.connected import (
    registry_summary as connected_registry_summary,
)
from biointel.connected.copilot import OpenAICopilot
from biointel.data.coverage_packs import (
    load_coverage_manifest,
    verify_coverage_integrity,
)
from biointel.data.curation import curate_activity_dataset
from biointel.data.data_packs import data_library_summary
from biointel.data.dataset_registry import list_datasets
from biointel.data.evidence_registry import (
    evidence_readiness,
    list_evidence_links,
    list_import_runs,
    record_review,
    registry_summary,
)
from biointel.data.readiness import (
    dataset_readiness_rows,
    platform_readiness_summary,
    provider_readiness_rows,
)
from biointel.data.relationship_integrity import relationship_edges, relationship_summary
from biointel.data.scientific_registry import scientific_registry_summary
from biointel.discovery.admet_plugins import EndpointModelCard, qualify_endpoint_model
from biointel.discovery.docking import (
    evaluate_docking_qualification,
    external_docking_readiness,
)
from biointel.discovery.docking import (
    readiness_dict as docking_readiness_dict,
)
from biointel.discovery.preparation import preparation_dict, prepare_molecular_states
from biointel.discovery.registry import (
    DEFAULT_PATH as DISCOVERY_DATABASE,
)
from biointel.discovery.registry import (
    add_target_assessment,
    list_endpoint_model_cards,
    register_endpoint_model_card,
)
from biointel.discovery.registry import (
    create_project as create_discovery_project,
)
from biointel.discovery.registry import (
    export_project_bundle as export_discovery_project_bundle,
)
from biointel.discovery.registry import (
    list_compounds as list_discovery_compounds,
)
from biointel.discovery.registry import (
    list_projects as list_discovery_projects,
)
from biointel.discovery.registry import (
    project_snapshot as discovery_project_snapshot,
)
from biointel.discovery.registry import (
    save_ranking as save_discovery_ranking,
)
from biointel.discovery.registry import (
    upsert_compound as upsert_discovery_compound,
)
from biointel.discovery.target_intelligence import (
    build_target_evidence_profile,
)
from biointel.discovery.target_intelligence import (
    profile_dict as target_profile_dict,
)
from biointel.discovery.workflow import rank_discovery_hits
from biointel.documents.bridge import import_table_as_evidence, register_table_as_dataset
from biointel.documents.history import (
    delete_run as delete_document_run,
)
from biointel.documents.history import (
    get_output as get_document_output,
)
from biointel.documents.history import (
    get_run as get_document_run,
)
from biointel.documents.history import (
    history_summary as document_history_summary,
)
from biointel.documents.history import (
    list_entities as list_document_entities,
)
from biointel.documents.history import (
    list_events as list_document_events,
)
from biointel.documents.history import (
    list_ocr_corrections,
    record_ocr_correction,
    update_run_organization,
)
from biointel.documents.history import (
    list_outputs as list_document_outputs,
)
from biointel.documents.history import (
    list_runs as list_document_runs,
)
from biointel.documents.history import (
    restore_run as restore_document_run,
)
from biointel.documents.history import (
    search_content as search_document_content,
)
from biointel.documents.history import (
    soft_delete_run as trash_document_run,
)
from biointel.documents.history import (
    verify_output as verify_document_output,
)
from biointel.documents.knowledge import ask_document_history, compare_document_runs
from biointel.documents.service import process_document, process_documents, resolve_document_path
from biointel.dti.predictor import batch_predict_dti, predict_dti_pair
from biointel.dti.validation_suite import build_validation_matrix
from biointel.engineering import build_engineering_readiness, run_engineering_gates
from biointel.fair import evaluate_fair_object
from biointel.genomics.design import design_primer_pairs, find_crispr_guides
from biointel.genomics.design import result_dict as design_result_dict
from biointel.genomics.fastq import fastq_qc, parse_fastq, trim_fastq
from biointel.genomics.fastq import qc_dict as fastq_qc_dict
from biointel.genomics.phylogeny import consensus_sequence, distance_matrix, upgma_newick
from biointel.genomics.variants import filter_variants, parse_vcf, variant_summary
from biointel.genomics.variants import summary_dict as variant_summary_dict
from biointel.governance.governance_registry import (
    governance_portfolio_summary,
    project_governance_snapshot,
)
from biointel.governance.reproducibility import (
    build_lineage_graph,
    build_project_manifest,
    project_readiness,
)
from biointel.integrations.public_sync import (
    sync_chembl_activities,
    sync_status,
    sync_uniprot_reviewed,
)
from biointel.database.bootstrap import bootstrap_databases
from biointel.runtime_paths import runtime_api_directory
from biointel.intelligence.data_intelligence import (
    all_database_health,
    database_paths,
    universal_search,
)
from biointel.intelligence.knowledge_warehouse import (
    knowledge_summary,
    search_knowledge,
)
from biointel.internet.connectivity import (
    check_internet_services,
    internet_configuration,
)
from biointel.internet.download_registry import (
    download_summary,
    list_downloads,
)
from biointel.internet.downloader import download_public_file
from biointel.internet.network_policy import internet_policy_from_environment
from biointel.internet.pubchem import fetch_pubchem_compound_by_name
from biointel.internet.rcsb import download_rcsb_structure, fetch_rcsb_entry
from biointel.jobs.local_queue import LocalJobQueue
from biointel.live_workspace_v210.api import router as live_workspace_router
from biointel.engine_platform_v196.api import router as engine_platform_router
from biointel.discovery_platform.api import router as discovery_platform_router
from biointel.shiro.api.router import router as shiro_router
from biointel.connect.api import router as connect_router
from biointel.education.api import router as education_router
from biointel.education.phase23_30.api import public_router as education_public_v1_router
from biointel.science_pulse.api import router as science_pulse_router
from biointel.step101.reports import UnifiedScientificReportBuilder
from biointel.maturity import build_maturity_readiness
from biointel.multitenancy.middleware import TenantContextMiddleware
from biointel.multitenancy.store import TenantStore
from biointel.observability.analytics_store import (
    analytics_summary,
    module_performance,
)
from biointel.observability.metrics import METRICS
from biointel.observability.structured_logging import configure_json_logging
from biointel.operations.activity_center import (
    build_timeline,
    visible_alerts,
)
from biointel.operations.executive_summary import build_executive_summary
from biointel.portfolio.project_registry import list_projects
from biointel.privacy import build_privacy_inventory
from biointel.production.config import (
    enforce_runtime_configuration,
    is_production,
    validate_runtime_configuration,
)
from biointel.production.readiness import production_readiness
from biointel.projects.catalog import PROJECT_CATALOG
from biointel.projects.run_registry import list_runs as list_biotechnology_runs
from biointel.proteomics.annotation import annotate_protein
from biointel.proteomics.annotation import annotation_dict as protein_annotation_dict
from biointel.quality.capability_readiness import build_target_capability_readiness
from biointel.quality.model_audit import audit_model_directory
from biointel.quality.scorecard import build_quality_scorecard
from biointel.realworld import (
    OperationalArtifact,
    OperationalAttestation,
    RealWorldEvidenceRegistry,
    build_step41_realworld_readiness,
    build_step42_maximum_evidence,
)
from biointel.release import build_store_readiness
from biointel.reports.workspace_report import build_workspace_report_data
from biointel.research import evaluate_academic_readiness, evaluate_pharma_readiness
from biointel.scientific import (
    ScientificEvidenceLake,
    SiteAttestation,
    ValidationEvidenceRegistry,
    build_scientific_excellence_readiness,
    build_step40_validation_readiness,
)
from biointel.scientific.prospective import ProspectiveStudyRegistry
from biointel.sequence.alignment import align_sequences
from biointel.sequence.dna_analysis import (
    dna_transformations,
    nucleotide_statistics,
)
from biointel.sequence.parser import parse_sequence_text
from biointel.sequence.protein_analysis import protein_statistics
from biointel.sequence.validators import (
    SequenceType,
    detect_sequence_type,
    validate_for_type,
)
from biointel.structural.pdb_analysis import ligand_contacts, structure_summary
from biointel.structural.pdb_analysis import summary_dict as structure_summary_dict
from biointel.systems.pathways import pathway_enrichment
from biointel.training.capabilities import optional_capabilities
from biointel.training.external_validation import evaluate_external_dataset
from biointel.training.model_artifact import (
    load_model_artifact_cached,
    model_artifact_cache_info,
    preload_model_directory,
)
from biointel.training.model_catalog import sync_model_catalog
from biointel.training.release_gate import (
    complete_dti_release_config,
    evaluate_release_gate,
    release_gate_dict,
)
from biointel.ui.navigation import PAGE_CATALOG
from biointel.utils.audit_log import verify_audit_chain
from biointel.utils.diagnostics import diagnostic_summary, run_diagnostics
from biointel.utils.runtime_cache import runtime_cache_info
from biointel.utils.workflow_status import build_workflow_status

ROOT = Path(__file__).resolve().parents[3]
MODELS_DIRECTORY = ROOT / "models"


def _writable_runtime_reports_directory() -> Path:
    candidate = runtime_api_directory(ROOT)
    candidate.mkdir(parents=True, exist_ok=True)
    probe = candidate / f".biointel-api-write-probe-{os.getpid()}"
    probe.write_bytes(b"ok")
    probe.unlink(missing_ok=True)
    return candidate.resolve()


RUNTIME_REPORTS_DIRECTORY = _writable_runtime_reports_directory()
def _database_path(name: str) -> Path:
    return database_paths(ROOT)[name]


DATABASE_PATHS = database_paths(ROOT)
FEATURE_CACHE_PATH = _database_path("feature_cache")
JOB_QUEUE = LocalJobQueue(_database_path("jobs"))
API_SECURITY_PATH = _database_path("api_security")
TENANT_STORE_PATH = _database_path("tenants")
BIOTECH_RUN_REGISTRY_PATH = DATABASE_PATHS.get("biotechnology_project_runs", RUNTIME_REPORTS_DIRECTORY / "biotechnology_project_runs.sqlite3")
API_SECURITY = ApiSecurityStore(API_SECURITY_PATH)
TENANT_STORE = TenantStore(TENANT_STORE_PATH)
API_LOGGER = configure_json_logging(RUNTIME_REPORTS_DIRECTORY / "logs" / "api.jsonl", logger_name="biointel.api")
API_KEY = os.getenv("BIOINTEL_API_KEY", "").strip() or None
RATE_LIMIT = int(os.getenv("BIOINTEL_API_RATE_LIMIT", "120"))

def _register_configured_api_clients() -> int:
    registered = 0
    if API_KEY:
        API_SECURITY.register_client(
            client_id="legacy-operator",
            display_name="Legacy operator",
            role="operator",
            raw_key=API_KEY,
            quota_per_minute=int(os.getenv("BIOINTEL_API_RATE_LIMIT", "120")),
            metadata={"source": "BIOINTEL_API_KEY", "tenant_ids": ["default"], "default_tenant": "default"},
        )
        TENANT_STORE.add_membership("default", "legacy-operator", "owner")
        registered += 1
    raw = os.getenv("BIOINTEL_API_CLIENTS_JSON", "").strip()
    if not raw:
        return registered
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("BIOINTEL_API_CLIENTS_JSON must contain valid JSON") from exc
    clients = payload if isinstance(payload, list) else payload.get("clients", [])
    for item in clients:
        if not isinstance(item, dict) or not item.get("key"):
            continue
        client_id = str(item.get("client_id") or item.get("name") or f"client-{registered+1}")
        api_role = str(item.get("role", "viewer"))
        tenant_ids = [str(value).strip().lower() for value in item.get("tenant_ids", [item.get("default_tenant", "default")]) if str(value).strip()] or ["default"]
        default_tenant = str(item.get("default_tenant") or tenant_ids[0]).strip().lower()
        for tenant_id in tenant_ids:
            TENANT_STORE.ensure_tenant(
                tenant_id,
                str(item.get("tenant_display_names", {}).get(tenant_id, tenant_id.replace("-", " ").title())),
                plan=str(item.get("tenant_plan", "standard")),
            )
        API_SECURITY.register_client(
            client_id=client_id,
            display_name=str(item.get("display_name") or item.get("name") or "API client"),
            role=api_role,
            raw_key=str(item["key"]),
            quota_per_minute=int(item.get("quota_per_minute", RATE_LIMIT)),
            metadata={
                "source": "BIOINTEL_API_CLIENTS_JSON",
                "tenant_ids": tenant_ids,
                "default_tenant": default_tenant,
            },
        )
        membership_role = str(item.get("tenant_role") or ("owner" if api_role == "admin" else api_role))
        for tenant_id in tenant_ids:
            TENANT_STORE.add_membership(tenant_id, client_id, membership_role)
        registered += 1
    return registered

LAN_MODE = os.getenv("BIOINTEL_COLLABORATION_HOST", "").strip().lower() in {"1", "true", "yes", "on"}
TRUSTED_HOSTS = [
    host.strip()
    for host in os.getenv(
        "BIOINTEL_TRUSTED_HOSTS",
        "*" if LAN_MODE else "127.0.0.1,localhost,testserver",
    ).split(",")
    if host.strip()
]
CONFIGURED_API_CLIENTS = _register_configured_api_clients()
LOCAL_SESSION_TOKEN = os.getenv("BIOINTEL_LOCAL_SESSION_TOKEN", "").strip()
if LOCAL_SESSION_TOKEN:
    TENANT_STORE.add_membership("default", "desktop-session", "owner")

PRELOAD_STATUS = (
    preload_model_directory(
        MODELS_DIRECTORY,
        limit=int(os.getenv("BIOINTEL_PRELOAD_MODEL_LIMIT", "6")),
    )
    if os.getenv("BIOINTEL_PRELOAD_MODELS", "0").strip().lower() in {"1", "true", "yes"}
    else {"loaded": [], "failed": {}, "requested_limit": 0, "cache": model_artifact_cache_info()}
)

RUNTIME_CONFIGURATION = validate_runtime_configuration()
enforce_runtime_configuration()

app = FastAPI(
    title="BioIntel AI API",
    version=__version__,
    description=(
        "Role-aware research API for sequence analysis, scientific registries, "
        "quality diagnostics and evidence-gated Drug–Target Interaction workflows."
    ),
)

CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "BIOINTEL_CORS_ORIGINS",
        "capacitor://localhost,http://localhost,https://localhost",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=TRUSTED_HOSTS,
)
app.add_middleware(
    RequestSizeLimitMiddleware,
    max_bytes=int(os.getenv("BIOINTEL_API_JSON_LIMIT_BYTES", str(16 * 1024 * 1024))),
    upload_max_bytes=int(os.getenv("BIOINTEL_API_UPLOAD_LIMIT_BYTES", str(100 * 1024 * 1024))),
)
app.add_middleware(
    SecurityHeadersMiddleware,
    api_version="v1",
    strict_transport_security=is_production(),
)
app.add_middleware(
    RateLimitMiddleware,
    requests_per_minute=RATE_LIMIT,
    security_store=API_SECURITY,
    redis_url=os.getenv("BIOINTEL_REDIS_URL", ""),
)
app.add_middleware(
    TenantContextMiddleware,
    tenant_store=TENANT_STORE,
)
app.add_middleware(
    OptionalApiKeyMiddleware,
    api_key=API_KEY,
    security_store=API_SECURITY,
    require_auth=is_production(),
    default_quota_per_minute=RATE_LIMIT,
)
app.add_middleware(RequestContextMiddleware, security_store=API_SECURITY, logger=API_LOGGER)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=os.getenv(
        "BIOINTEL_CORS_ORIGIN_REGEX",
        r"https?://(localhost|127\.0\.0\.1|\[::1\]|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?",
    ) if LAN_MODE or not is_production() else None,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID", "X-Idempotency-Key"],
)
app.include_router(live_workspace_router)
app.include_router(engine_platform_router)
app.include_router(discovery_platform_router)
app.include_router(shiro_router)
app.include_router(connect_router)
app.include_router(education_router)
app.include_router(education_public_v1_router)
app.include_router(science_pulse_router)


def _trusted_model(filename: str):
    safe_name = Path(filename).name
    if safe_name != filename:
        raise HTTPException(
            status_code=400,
            detail="model_filename must be a plain local filename.",
        )
    try:
        return load_model_artifact_cached(
            MODELS_DIRECTORY / safe_name,
            trusted_root=MODELS_DIRECTORY,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _legal_html(name: str) -> str:
    path = ROOT / "docs" / "legal" / "site" / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Legal document is unavailable.")
    return path.read_text(encoding="utf-8")


@app.get("/legal/privacy", response_class=HTMLResponse, include_in_schema=False)
def legal_privacy() -> str:
    return _legal_html("privacy.html")


@app.get("/legal/terms", response_class=HTMLResponse, include_in_schema=False)
def legal_terms() -> str:
    return _legal_html("terms.html")


@app.get("/legal/support", response_class=HTMLResponse, include_in_schema=False)
def legal_support() -> str:
    return _legal_html("support.html")


@app.get("/legal/components", response_class=HTMLResponse, include_in_schema=False)
def legal_components() -> str:
    return _legal_html("component-notices.html")


@app.get("/v1/mobile/bootstrap")
def mobile_bootstrap() -> dict[str, object]:
    public_url = os.getenv("BIOINTEL_PUBLIC_URL", "").rstrip("/")
    return {
        "app_name": "BioIntel AI",
        "version": __version__,
        "api_version": "v1",
        "status": "ready",
        "authentication_required": bool(CONFIGURED_API_CLIENTS or is_production()),
        "ui_auth_required": os.getenv("BIOINTEL_UI_AUTH_REQUIRED", "").strip().lower()
        in {"1", "true", "yes", "on"} or is_production(),
        "workspace_url": public_url,
        "legal": {
            "privacy": f"{public_url}/legal/privacy" if public_url else "/legal/privacy",
            "terms": f"{public_url}/legal/terms" if public_url else "/legal/terms",
            "support": f"{public_url}/legal/support" if public_url else "/legal/support",
            "components": f"{public_url}/legal/components" if public_url else "/legal/components",
        },
        "features": {
            "connected_providers": True,
            "document_intelligence": True,
            "biotechnology_projects": True,
            "local_desktop_mode": True,
            "mobile_requires_hosted_server": True,
        },
        "scientific_boundary": "Research and education only; not medical diagnosis or treatment advice.",
    }


@app.get("/v1/mobile/privacy")
def mobile_privacy_inventory() -> dict[str, object]:
    return build_privacy_inventory(ROOT)


@app.get("/v1/store/readiness")
def store_readiness() -> dict[str, object]:
    return build_store_readiness(ROOT)


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "version": __version__,
        "trusted_models": len(list(MODELS_DIRECTORY.glob("*.joblib"))),
        "access_mode": "role_aware_api_key" if (CONFIGURED_API_CLIENTS or is_production()) else "no_login_local",
        "authentication_required": bool(CONFIGURED_API_CLIENTS or is_production()),
        "configured_api_clients": CONFIGURED_API_CLIENTS,
        "api_version": "v1",
        "host_policy": TRUSTED_HOSTS,
        "rate_limit_per_minute": RATE_LIMIT,
        "request_limit_bytes": int(os.getenv("BIOINTEL_API_JSON_LIMIT_BYTES", str(16 * 1024 * 1024))),
        "upload_limit_bytes": int(os.getenv("BIOINTEL_API_UPLOAD_LIMIT_BYTES", str(100 * 1024 * 1024))),
        "database_systems": int(all_database_health(ROOT).get("database_count", 0)),
        "model_scope": "bundled synthetic/reference benchmarks; scientific release remains evidence-gated",
        "professional_warehouses": 3,
        "internet_access": internet_configuration(),
        "model_preload": PRELOAD_STATUS,
        "feature_cache_path": str(FEATURE_CACHE_PATH),
        "api_security_path": str(API_SECURITY_PATH),
        "tenant_store_path": str(TENANT_STORE_PATH),
        "multi_tenant": True,
        "job_orchestration": JOB_QUEUE.orchestration_summary(),
        "runtime_configuration": RUNTIME_CONFIGURATION,
        "metrics": METRICS.snapshot(),
    }


@app.get("/v1/biotechnology/projects")
def biotechnology_projects() -> dict[str, object]:
    return {
        "count": len(PROJECT_CATALOG),
        "projects": [
            {
                "code": project.code,
                "key": project.key,
                "title": project.title,
                "short_title": project.short_title,
                "domain": project.domain,
                "objective": project.objective,
                "workflow": list(project.workflow),
                "deliverables": list(project.deliverables),
                "tags": list(project.tags),
                "maturity": "step49_deep_professional_workbench",
            }
            for project in PROJECT_CATALOG
        ],
    }


@app.post("/api/v1/synthetic-datasets")
def create_synthetic_dataset(request: SyntheticDatasetRequest) -> dict[str, object]:
    """Generate a controlled synthetic package without exposing unbounded matrices."""
    service = SyntheticWorkspaceService(ROOT)
    try:
        project = service.registry.get_project(request.project_id) if request.project_id else None
        if request.project_id and project is None:
            raise HTTPException(status_code=404, detail="Synthetic demo project was not found")
        if project is not None and not bool(project.get("is_synthetic")):
            raise SyntheticSafetyError("The selected project is not a synthetic demo project.")
        if project is None:
            project_type = str(MODULE_SPECS[request.module_id]["title"])
            project = service.create_demo_project(
                project_type,
                request.scenario,
                request.seed,
                actor="api_demo_user",
            )

        config = SyntheticGenerationConfig.from_preset(
            module_id=request.module_id,
            scenario=request.scenario,
            size_preset=request.size_preset,
            preset_name=request.preset_name,
            seed=request.seed,
            sample_count=request.sample_count,
            feature_count=request.feature_count,
            group_count=request.group_count,
            effect_size=request.effect_size,
            noise_level=request.noise_level,
            missing_data_rate=request.missing_data_rate,
            batch_effect_strength=request.batch_effect_strength,
        )
        dataset, saved = service.generate_dataset(
            str(project["project_id"]),
            config,
            actor="api_demo_user",
        )
        previews: dict[str, object] = {}
        for name, table in dataset.tables.items():
            frame = table if isinstance(table, pd.DataFrame) else pd.DataFrame(table)
            previews[name] = {
                "rows": int(len(frame)),
                "columns": [str(column) for column in frame.columns],
                "preview": json.loads(frame.head(20).to_json(orient="records", date_format="iso")),
                "preview_truncated": len(frame) > 20,
            }
        return {
            "project_id": project["project_id"],
            "dataset_id": saved["dataset_id"],
            "job_id": saved["job_id"],
            "data_origin": "synthetic",
            "is_synthetic": True,
            "generator_id": dataset.manifest.generator_id,
            "generator_version": dataset.manifest.generator_version,
            "manifest": dataset.manifest.to_dict(),
            "package_sha256": saved["package_sha256"],
            "memory_warning": config.memory_warning,
            "tables": previews,
            "allowed_use": list(dataset.manifest.allowed_use),
            "prohibited_use": list(dataset.manifest.prohibited_use),
            "watermark": "SYNTHETIC / DEMO DATA - NOT FOR SCIENTIFIC OR CLINICAL USE",
        }
    except HTTPException:
        raise
    except (ValueError, SyntheticSafetyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Synthetic resource not found: {exc.args[0]}") from exc

@app.get("/v1/biotechnology/runs")
def biotechnology_runs(project_code: str | None = None, limit: int = 100) -> dict[str, object]:
    safe_limit = min(max(int(limit), 1), 500)
    frame = list_biotechnology_runs(BIOTECH_RUN_REGISTRY_PATH, project_code=project_code, limit=safe_limit)
    records = frame.to_dict(orient="records") if not frame.empty else []
    return {"count": len(records), "project_code": project_code, "runs": records}


@app.get("/live")
def liveness() -> dict[str, object]:
    return {"status": "alive", "version": __version__}


@app.get("/ready")
def service_readiness() -> dict[str, object]:
    bootstrap = bootstrap_databases(ROOT)
    database = all_database_health(ROOT)
    healthy = int(database.get("healthy_count", 0))
    total = int(database.get("database_count", 0))
    warehouses = database.get("professional_warehouses", {})
    warehouse_ready = all(bool(item.get("healthy")) for item in warehouses.values()) if isinstance(warehouses, dict) else False
    ready = (
        bootstrap.passed
        and total > 0
        and healthy == total
        and warehouse_ready
        and bool(RUNTIME_CONFIGURATION.get("valid", True))
    )
    payload = {
        "status": "ready" if ready else "not_ready",
        "healthy_databases": healthy,
        "database_count": total,
        "professional_warehouses_ready": warehouse_ready,
        "bootstrap_failures": bootstrap.failures,
        "runtime_configuration": RUNTIME_CONFIGURATION,
    }
    if not ready:
        raise HTTPException(status_code=503, detail=payload)
    return payload


@app.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics() -> str:
    return METRICS.prometheus_text()


@app.get("/quality/scorecard")
def quality_scorecard() -> dict[str, object]:
    return build_quality_scorecard(ROOT)


@app.get("/quality/models")
def quality_models() -> dict[str, object]:
    return audit_model_directory(MODELS_DIRECTORY)


@app.get("/quality/capability-readiness")
def quality_capability_readiness() -> dict[str, object]:
    return build_target_capability_readiness(ROOT)


@app.get("/quality/maturity-readiness")
def quality_maturity_readiness() -> dict[str, object]:
    return build_maturity_readiness(ROOT)


@app.get("/quality/engineering-readiness")
def quality_engineering_readiness() -> dict[str, object]:
    return build_engineering_readiness(ROOT)


@app.get("/quality/engineering-gates")
def quality_engineering_gates() -> dict[str, object]:
    return run_engineering_gates(ROOT)




@app.get("/scientific/readiness")
def scientific_readiness() -> dict[str, object]:
    return build_scientific_excellence_readiness(ROOT)


@app.get("/scientific/evidence-summary")
def scientific_evidence_summary() -> dict[str, object]:
    lake = ScientificEvidenceLake(_database_path("scientific_evidence"))
    return {"summary": lake.summary(), "integrity": lake.verify_integrity()}


@app.get("/scientific/prospective-summary")
def scientific_prospective_summary() -> dict[str, object]:
    registry = ProspectiveStudyRegistry(database_paths(ROOT)["prospective_validation"])
    return registry.summary()


@app.get("/scientific/validation-depth")
def scientific_validation_depth() -> dict[str, object]:
    return build_step40_validation_readiness(ROOT)


@app.get("/scientific/validation-evidence-summary")
def scientific_validation_evidence_summary() -> dict[str, object]:
    registry = ValidationEvidenceRegistry(database_paths(ROOT)["validation_evidence"])
    return {"summary": registry.summary(), "integrity": registry.verify_integrity()}


@app.post("/scientific/validation-studies")
def scientific_register_validation_study(payload: dict[str, object]) -> dict[str, object]:
    registry = ValidationEvidenceRegistry(database_paths(ROOT)["validation_evidence"])
    sites = [SiteAttestation(**dict(item)) for item in payload.get("sites", [])]
    study = registry.register_study(
        payload=dict(payload.get("study") or {}),
        sites=sites,
        outcomes=[dict(item) for item in payload.get("outcomes", [])],
        metrics=[dict(item) for item in payload.get("metrics", [])],
        reviews=[dict(item) for item in payload.get("reviews", [])],
        metadata=dict(payload.get("metadata") or {}),
    )
    return {"study": asdict(study), "summary": registry.summary(), "integrity": registry.verify_integrity()}

@app.get("/operations/realworld-readiness")
def operations_realworld_readiness() -> dict[str, object]:
    return build_step41_realworld_readiness(ROOT)


@app.get("/operations/realworld-evidence-summary")
def operations_realworld_evidence_summary() -> dict[str, object]:
    registry = RealWorldEvidenceRegistry(database_paths(ROOT)["realworld_evidence"])
    return {"summary": registry.summary(), "integrity": registry.verify_integrity()}


@app.get("/operations/maximum-verifiable-evidence")
def operations_maximum_verifiable_evidence() -> dict[str, object]:
    return build_step42_maximum_evidence(ROOT)


@app.post("/operations/realworld-evidence")
def operations_register_realworld_evidence(payload: dict[str, object]) -> dict[str, object]:
    registry = RealWorldEvidenceRegistry(database_paths(ROOT)["realworld_evidence"])
    record = registry.register_evidence(
        payload=dict(payload.get("study") or {}),
        artifacts=[OperationalArtifact(**dict(item)) for item in payload.get("artifacts", [])],
        metrics=[dict(item) for item in payload.get("metrics", [])],
        attestations=[OperationalAttestation(**dict(item)) for item in payload.get("attestations", [])],
        entities=[dict(item) for item in payload.get("entities", [])],
    )
    return {"record": asdict(record), "summary": registry.summary(), "integrity": registry.verify_integrity()}


@app.get("/compliance/controls")
def compliance_control_catalog() -> dict[str, object]:
    rows = compliance_controls()
    return {"count": len(rows), "controls": rows}


@app.post("/quality/fair-evaluate")
def quality_fair_evaluate(payload: dict[str, object]) -> dict[str, object]:
    return evaluate_fair_object(payload).to_dict()


@app.post("/quality/academic-readiness")
def quality_academic_readiness(payload: dict[str, object]) -> dict[str, object]:
    return evaluate_academic_readiness(payload).to_dict()


@app.post("/quality/pharma-readiness")
def quality_pharma_readiness(payload: dict[str, object]) -> dict[str, object]:
    return evaluate_pharma_readiness(payload).to_dict()


@app.post("/quality/dti-validation-matrix")
def dti_validation_matrix(payload: dict[str, object]) -> dict[str, object]:
    model_filename = Path(str(payload.get("model_filename", ""))).name
    if not model_filename or model_filename != str(payload.get("model_filename", "")):
        raise HTTPException(status_code=422, detail="A plain local model filename is required.")
    model_path = MODELS_DIRECTORY / model_filename
    if not model_path.is_file():
        raise HTTPException(status_code=404, detail="Model artifact was not found.")
    evidence = payload.get("evidence", [])
    if not isinstance(evidence, list):
        raise HTTPException(status_code=422, detail="evidence must be a list of split reports.")
    try:
        return build_validation_matrix(model_path, evidence).to_dict()
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/tenants")
def list_tenants(request: Request) -> dict[str, object]:
    identity = request.state.api_identity
    if identity.role == "local_operator":
        return {"count": 1, "tenants": [{"tenant_id": "default", "display_name": "Default Workspace", "membership_role": "owner"}]}
    rows = TENANT_STORE.list_for_client(identity.client_id)
    return {"count": len(rows), "tenants": rows}


@app.get("/tenants/current")
def current_tenant_details(request: Request) -> dict[str, object]:
    context = request.state.tenant
    tenant = TENANT_STORE.get_tenant(context.tenant_id)
    return {**asdict(tenant), "membership_role": context.membership_role, "client_id": context.client_id}


@app.post("/tenants")
def create_tenant(request: Request, payload: dict[str, object]) -> dict[str, object]:
    identity = request.state.api_identity
    if identity.role not in {"admin", "local_operator"}:
        raise HTTPException(status_code=403, detail="Only an administrator can create tenants.")
    try:
        tenant = TENANT_STORE.ensure_tenant(
            str(payload.get("tenant_id", "")),
            str(payload.get("display_name", "")),
            plan=str(payload.get("plan", "standard")),
            metadata=dict(payload.get("metadata") or {}),
        )
        TENANT_STORE.add_membership(tenant.tenant_id, identity.client_id, "owner")
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return asdict(tenant)


@app.get("/tenant-resources")
def tenant_resources(request: Request, resource_type: str | None = None, limit: int = 100) -> dict[str, object]:
    rows = TENANT_STORE.list_resources(request.state.tenant, resource_type=resource_type, limit=limit)
    return {"tenant_id": request.state.tenant.tenant_id, "count": len(rows), "resources": rows}


@app.post("/tenant-resources")
def upsert_tenant_resource(request: Request, payload: dict[str, object]) -> dict[str, object]:
    try:
        return TENANT_STORE.put_resource(
            request.state.tenant,
            resource_type=str(payload.get("resource_type", "generic")),
            name=str(payload.get("name", "Untitled resource")),
            payload=dict(payload.get("payload") or {}),
            resource_id=(str(payload["resource_id"]) if payload.get("resource_id") else None),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/production/configuration")
def production_configuration() -> dict[str, object]:
    return validate_runtime_configuration()


@app.get("/readiness/summary")
def readiness_summary() -> dict[str, object]:
    return platform_readiness_summary(ROOT)


@app.get("/readiness/datasets")
def readiness_datasets() -> dict[str, object]:
    rows = dataset_readiness_rows(ROOT)
    summary = platform_readiness_summary(ROOT).get("datasets", {})
    return {
        "count": len(rows),
        "registered_dataset_count": int(summary.get("datasets") or len(rows)),
        "readiness_scored_dataset_count": int(summary.get("readiness_scored") or 0),
        "rows": rows,
    }


@app.get("/readiness/providers")
def readiness_providers() -> dict[str, object]:
    rows = provider_readiness_rows(ROOT)
    return {"count": len(rows), "rows": rows}


@app.get("/relationships/summary")
def relationships_summary() -> dict[str, object]:
    return relationship_summary(ROOT)


@app.get("/relationships/edges")
def relationships_edges(limit: int = 500) -> dict[str, object]:
    safe_limit = max(1, min(int(limit), 5000))
    rows = relationship_edges(ROOT, limit=safe_limit)
    return {"count": len(rows), "limit": safe_limit, "rows": rows}


@app.get("/public-reference")
def public_reference(provider: str | None = None, record_type: str | None = None, limit: int = 500) -> dict[str, object]:
    path = ROOT / "data" / "public_reference" / "verified_public_reference_catalog.csv"
    if not path.is_file():
        return {"count": 0, "rows": [], "scope": "identifier_reference_only"}
    frame = pd.read_csv(path)
    if provider:
        frame = frame[frame["provider"].astype(str).str.casefold() == provider.casefold()]
    if record_type:
        frame = frame[frame["record_type"].astype(str).str.casefold() == record_type.casefold()]
    safe_limit = max(1, min(int(limit), 5000))
    frame = frame.head(safe_limit)
    return {
        "count": len(frame),
        "rows": frame.where(pd.notna(frame), None).to_dict(orient="records"),
        "scope": "verified public identifiers only; not training or validation payloads",
    }




@app.get("/v1/scientific-integrations")
def scientific_integrations_status() -> dict[str, object]:
    """Return public BioIntel integration readiness without internal identifiers."""
    return integration_summary()

@app.get("/system/capabilities")
def system_capabilities() -> dict[str, object]:
    capabilities = optional_capabilities()
    return {
        "capabilities": [asdict(item) for item in capabilities],
        "available": sum(item.available for item in capabilities),
        "total": len(capabilities),
    }


@app.post("/data/curate-activity")
def data_curate_activity(request: DataCurationRequest) -> dict[str, object]:
    try:
        curated, errors, summary = curate_activity_dataset(
            pd.DataFrame(request.rows),
            active_threshold=request.active_threshold,
            aggregate_duplicates=request.aggregate_duplicates,
            source_database=request.source_database,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "summary": asdict(summary),
        "rows": curated.where(pd.notna(curated), None).to_dict(orient="records"),
        "errors": errors.where(pd.notna(errors), None).to_dict(orient="records"),
    }


@app.post("/model/release-gate")
def model_release_gate(request: ReleaseGateRequest) -> dict[str, object]:
    artifact = _trusted_model(request.model_filename)
    return release_gate_dict(
        evaluate_release_gate(
            metadata=artifact.metadata,
            external_validation=request.external_validation,
            prospective_validation=request.prospective_validation,
            split_summary=request.split_summary,
            evidence_manifest=request.evidence_manifest,
            dataset_metadata=request.dataset_metadata,
            leakage_audit=request.leakage_audit,
            drift_report=request.drift_report,
            validation_matrix=request.validation_matrix,
            config=complete_dti_release_config() if request.strict else None,
        )
    )


@app.post("/jobs")
def submit_job(request: JobSubmitRequest) -> dict[str, object]:
    return asdict(
        JOB_QUEUE.submit(
            request.job_type,
            request.payload,
            priority=request.priority,
            max_attempts=request.max_attempts,
            dependencies=request.dependencies,
            stages=request.stages or None,
            resources=request.resources,
            estimated_seconds=request.estimated_seconds,
        )
    )


@app.get("/jobs")
def list_jobs(status: str | None = None, limit: int = 100) -> dict[str, object]:
    try:
        records = JOB_QUEUE.list(status=status, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"jobs": [asdict(record) for record in records]}


@app.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, object]:
    try:
        return asdict(JOB_QUEUE.request_cancel(job_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found.") from exc


@app.post("/jobs/{job_id}/pause")
def pause_job(job_id: str) -> dict[str, object]:
    try:
        return asdict(JOB_QUEUE.request_pause(job_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/jobs/{job_id}/resume")
def resume_job(job_id: str) -> dict[str, object]:
    try:
        return asdict(JOB_QUEUE.resume(job_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/jobs/recover-stale")
def recover_stale_jobs() -> dict[str, int]:
    return JOB_QUEUE.recover_orphaned_jobs(stale_after_seconds=60)


@app.post("/quality/ui-regression")
def queue_ui_regression(request: UiRegressionRequest) -> dict[str, object]:
    record = JOB_QUEUE.submit(
        "ui_regression_run",
        request.model_dump(),
        stages=["discover", "compile", "apptest", "report"],
        resources={"cpu_threads": 2, "ram_gb": 4, "gpu_required": False},
        estimated_seconds=max(30, len(request.selected_pages or [1]) * request.timeout_seconds / 3),
    )
    return asdict(record)


@app.post("/reports/unified")
def unified_report(request: UnifiedReportRequest) -> StreamingResponse:
    try:
        bundle = UnifiedScientificReportBuilder(ROOT).build(
            title=request.title,
            notes=request.notes,
            reviewer=request.reviewer,
            sections=request.sections or None,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return StreamingResponse(
        io.BytesIO(bundle.zip_bytes()),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="biointel_unified_scientific_report.zip"'},
    )


@app.post("/jobs/{job_id}/retry")
def retry_job(job_id: str) -> dict[str, object]:
    try:
        return asdict(JOB_QUEUE.retry(job_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/jobs/{job_id}/timeline")
def job_timeline(job_id: str) -> dict[str, object]:
    try:
        return JOB_QUEUE.timeline(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found.") from exc


@app.get("/jobs/workers/status")
def job_workers() -> dict[str, object]:
    rows = JOB_QUEUE.workers()
    return {"count": len(rows), "rows": rows, "summary": JOB_QUEUE.orchestration_summary()}


@app.get("/security/status")
def api_security_status() -> dict[str, object]:
    return {
        "mode": "role_aware_api_key" if CONFIGURED_API_CLIENTS else "no_login_local",
        "configured_clients": CONFIGURED_API_CLIENTS,
        "audit": API_SECURITY.status(),
        "database": str(API_SECURITY_PATH),
    }



@app.get("/assurance/final")
def final_assurance() -> dict[str, object]:
    """Return the final evidence-aware platform assurance report."""
    return build_final_assurance(ROOT)

@app.get("/production/readiness")
def production_status() -> dict[str, object]:
    return production_readiness()


@app.get("/v1/health")
def v1_health() -> dict[str, object]:
    return {"api_version": "v1", "data": health()}


@app.get("/v1/platform/summary")
def v1_platform_summary() -> dict[str, object]:
    return {
        "api_version": "v1",
        "data": {
            "health": health(),
            "readiness": platform_readiness_summary(ROOT),
            "relationships": relationship_summary(ROOT),
            "jobs": JOB_QUEUE.orchestration_summary(),
            "security": API_SECURITY.status(),
        },
    }


@app.post("/scientific-sync/chembl/jobs")
def queue_scientific_sync_chembl(maximum_records: int = 1000, organism: str = "Homo sapiens") -> dict[str, object]:
    job = JOB_QUEUE.submit(
        "scientific_sync_chembl",
        {"maximum_records": max(1, min(int(maximum_records), 10_000)), "organism": organism.strip() or "Homo sapiens"},
        priority=40,
        stages=["prepare", "download", "normalize", "validate", "finalize"],
    )
    return asdict(job)


@app.post("/scientific-sync/uniprot/jobs")
def queue_scientific_sync_uniprot(maximum_records: int = 1000, organism_id: int = 9606) -> dict[str, object]:
    job = JOB_QUEUE.submit(
        "scientific_sync_uniprot",
        {"maximum_records": max(1, min(int(maximum_records), 5000)), "organism_id": int(organism_id)},
        priority=40,
        stages=["prepare", "download", "normalize", "validate", "finalize"],
    )
    return asdict(job)


@app.post("/maintenance/database-optimize/jobs")
def queue_database_optimization() -> dict[str, object]:
    return asdict(JOB_QUEUE.submit(
        "database_optimize",
        {"databases": list(all_database_health(ROOT)["databases"])},
        priority=80,
        stages=["prepare", "execute", "validate", "finalize"],
    ))


@app.get("/scientific-sync/status")
def scientific_sync_status(limit: int = 100) -> dict[str, object]:
    return sync_status(ROOT, limit=max(1, min(int(limit), 1000)))


@app.post("/scientific-sync/chembl")
def scientific_sync_chembl(maximum_records: int = 1000, organism: str = "Homo sapiens") -> dict[str, object]:
    try:
        result = sync_chembl_activities(
            ROOT,
            maximum_records=max(1, min(int(maximum_records), 10_000)),
            organism=organism.strip() or "Homo sapiens",
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return asdict(result)


@app.post("/scientific-sync/uniprot")
def scientific_sync_uniprot(maximum_records: int = 1000, organism_id: int = 9606) -> dict[str, object]:
    try:
        result = sync_uniprot_reviewed(
            ROOT,
            maximum_records=max(1, min(int(maximum_records), 5000)),
            organism_id=int(organism_id),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return asdict(result)


@app.get("/system/diagnostics")
def system_diagnostics() -> dict[str, object]:
    checks = run_diagnostics(ROOT)
    return {
        "summary": diagnostic_summary(checks),
        "checks": [check.to_dict() for check in checks],
    }


@app.get("/evidence/summary")
def evidence_summary() -> dict[str, object]:
    return registry_summary(_database_path("evidence"))


@app.get("/evidence/import-runs")
def evidence_import_runs(limit: int = 100) -> list[dict[str, object]]:
    return list_import_runs(_database_path("evidence"), limit=limit)


@app.get("/evidence/datasets/{dataset_sha256}/readiness")
def evidence_dataset_readiness(dataset_sha256: str) -> dict[str, object]:
    return evidence_readiness(_database_path("evidence"), dataset_sha256)


@app.get("/evidence/datasets/{dataset_sha256}/links")
def evidence_dataset_links(
    dataset_sha256: str,
    review_status: str | None = None,
    limit: int = 1000,
) -> list[dict[str, object]]:
    return list_evidence_links(
        _database_path("evidence"),
        dataset_sha256=dataset_sha256,
        review_status=review_status,
        limit=limit,
    )


@app.post("/evidence/datasets/{dataset_sha256}/reviews")
def evidence_review(dataset_sha256: str, request: EvidenceReviewRequest) -> dict[str, object]:
    review_id = record_review(
        _database_path("evidence"),
        dataset_sha256=dataset_sha256,
        evidence_key=request.evidence_key,
        decision=request.decision,
        reviewer=request.reviewer,
        comment=request.comment,
        original=request.original,
        revised=request.revised,
    )
    return {
        "review_id": review_id,
        "readiness": evidence_readiness(_database_path("evidence"), dataset_sha256),
    }


@app.post("/documents/extract")
async def document_extract(
    file: UploadFile = File(...),
    password: str | None = Form(default=None),
    keep_source: bool = Form(default=False),
    max_rows_per_table: int = Form(default=50_000),
    max_columns: int = Form(default=256),
    allow_macro_workbooks: bool = Form(default=False),
    allow_embedded_objects: bool = Form(default=False),
    ocr_mode: str = Form(default="off"),
    ocr_language: str = Form(default="eng"),
    ocr_confidence_threshold: float = Form(default=70.0),
    redact_sensitive: bool = Form(default=False),
    duplicate_policy: str = Form(default="warn"),
    project_code: str = Form(default=""),
    tags: str = Form(default=""),
    notes: str = Form(default=""),
) -> dict[str, object]:
    try:
        data = await file.read()
        processed = process_document(
            file.filename or "uploaded_document",
            data,
            project_root=ROOT,
            password=password or None,
            keep_source=keep_source,
            max_rows_per_table=max_rows_per_table,
            max_columns=max_columns,
            allow_macro_workbooks=allow_macro_workbooks,
            allow_embedded_objects=allow_embedded_objects,
            ocr_mode=ocr_mode,
            ocr_language=ocr_language,
            ocr_confidence_threshold=ocr_confidence_threshold,
            redact_sensitive=redact_sensitive,
            duplicate_policy=duplicate_policy,
            project_code=project_code,
            tags=[value.strip() for value in tags.split(",") if value.strip()],
            notes=notes,
        )
        return processed.to_dict(include_extracted_rows=False)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/documents/batch-extract")
async def document_batch_extract(
    files: list[UploadFile] = File(...),
    keep_source: bool = Form(default=False),
    max_rows_per_table: int = Form(default=50_000),
    max_columns: int = Form(default=256),
    ocr_mode: str = Form(default="off"),
    redact_sensitive: bool = Form(default=False),
    duplicate_policy: str = Form(default="warn"),
) -> dict[str, object]:
    try:
        payloads = []
        total_bytes = 0
        for item in files:
            data = await item.read()
            total_bytes += len(data)
            if total_bytes > 100 * 1024 * 1024:
                raise ValueError("Combined batch exceeds the 100 MB request safety limit.")
            payloads.append((item.filename or "uploaded_document", data))
        result = process_documents(
            payloads,
            project_root=ROOT,
            keep_source=keep_source,
            max_rows_per_table=max_rows_per_table,
            max_columns=max_columns,
            ocr_mode=ocr_mode,
            redact_sensitive=redact_sensitive,
            duplicate_policy=duplicate_policy,
        )
        return result.to_dict(include_extracted_rows=False)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/documents/history/summary")
def documents_history_summary() -> dict[str, object]:
    return document_history_summary(_database_path("documents"))


@app.get("/documents/history")
def documents_history(
    q: str = "",
    file_type: str = "all",
    status: str = "all",
    project_code: str | None = None,
    tag: str | None = None,
    include_deleted: bool = False,
    limit: int = 500,
) -> dict[str, object]:
    records = list_document_runs(
        _database_path("documents"),
        query=q,
        file_type=file_type,
        status=status,
        project_code=project_code,
        tag=tag,
        include_deleted=include_deleted,
        limit=limit,
    )
    return {"runs": [asdict(record) for record in records]}


@app.get("/documents/history/{run_id}")
def document_history_detail(run_id: str) -> dict[str, object]:
    try:
        run = get_document_run(_database_path("documents"), run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Document extraction run not found.") from exc
    return {
        "run": asdict(run),
        "outputs": [
            asdict(output)
            for output in list_document_outputs(
                _database_path("documents"), run_id
            )
        ],
        "events": list_document_events(
            _database_path("documents"), run_id
        ),
    }


@app.get("/documents/outputs/{output_id}/download")
def document_output_download(output_id: str):
    try:
        output = get_document_output(
            _database_path("documents"), output_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Document output not found.") from exc
    path = resolve_document_path(ROOT, output.path).resolve()
    allowed_root = runtime_data_path(ROOT, "document_extractions").resolve()
    if not path.is_file() or allowed_root not in path.parents:
        raise HTTPException(status_code=404, detail="Stored output file is unavailable.")
    return FileResponse(path, filename=output.filename)


@app.delete("/documents/history/{run_id}")
def document_history_delete(run_id: str) -> dict[str, object]:
    try:
        get_document_run(_database_path("documents"), run_id)
        trash_document_run(_database_path("documents"), run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Document extraction run not found.") from exc
    return {"trashed": True, "run_id": run_id}


@app.post("/documents/history/{run_id}/restore")
def document_history_restore(run_id: str) -> dict[str, object]:
    try:
        restore_document_run(_database_path("documents"), run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Document extraction run not found.") from exc
    return {"restored": True, "run_id": run_id}


@app.delete("/documents/history/{run_id}/purge")
def document_history_purge(run_id: str) -> dict[str, object]:
    try:
        delete_document_run(_database_path("documents"), run_id, delete_files=True)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Document extraction run not found.") from exc
    return {"purged": True, "run_id": run_id}


@app.post("/documents/history/{run_id}/organize")
def document_history_organize(run_id: str, request: DocumentOrganizeRequest) -> dict[str, object]:
    try:
        update_run_organization(
            _database_path("documents"),
            run_id,
            tags=request.tags,
            project_code=request.project_code,
            notes=request.notes,
        )
        return {"run": asdict(get_document_run(_database_path("documents"), run_id))}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Document extraction run not found.") from exc


@app.get("/documents/search")
def document_search(q: str, entity_type: str | None = None, limit: int = 100) -> dict[str, object]:
    return {
        "query": q,
        "results": search_document_content(
            _database_path("documents"),
            q,
            entity_type=entity_type,
            limit=limit,
        ),
    }


@app.get("/documents/entities")
def document_entities(
    run_id: str | None = None,
    entity_type: str = "all",
    q: str = "",
    limit: int = 1000,
) -> dict[str, object]:
    return {
        "entities": list_document_entities(
            _database_path("documents"),
            run_id=run_id,
            entity_type=entity_type,
            query=q,
            limit=limit,
        )
    }


@app.post("/documents/ask")
def document_ask(request: DocumentQuestionRequest) -> dict[str, object]:
    return ask_document_history(
        ROOT,
        request.question,
        run_ids=request.run_ids,
        maximum_documents=request.maximum_documents,
        maximum_citations=request.maximum_citations,
    )


@app.post("/documents/compare")
def document_compare(request: DocumentCompareRequest) -> dict[str, object]:
    try:
        return compare_document_runs(ROOT, request.left_run_id, request.right_run_id)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/documents/history/{run_id}/ocr-corrections")
def document_ocr_correction(run_id: str, request: OcrCorrectionRequest) -> dict[str, object]:
    try:
        get_document_run(_database_path("documents"), run_id)
        correction_id = record_ocr_correction(
            _database_path("documents"),
            run_id=run_id,
            region_id=request.region_id,
            original_text=request.original_text,
            corrected_text=request.corrected_text,
            reviewer=request.reviewer,
            comment=request.comment,
        )
        return {
            "correction_id": correction_id,
            "corrections": list_ocr_corrections(
                _database_path("documents"), run_id
            ),
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Document extraction run not found.") from exc


@app.post("/documents/history/{run_id}/dataset")
def document_dataset_bridge(run_id: str, request: DocumentDatasetBridgeRequest) -> dict[str, object]:
    try:
        return register_table_as_dataset(
            ROOT,
            run_id=run_id,
            table_index=request.table_index,
            dataset_name=request.dataset_name,
            dataset_version=request.dataset_version,
            task_type=request.task_type,
            activity_type=request.activity_type,
            notes=request.notes,
        )
    except (KeyError, IndexError, FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/documents/history/{run_id}/evidence")
def document_evidence_bridge(run_id: str, request: DocumentEvidenceBridgeRequest) -> dict[str, object]:
    try:
        return import_table_as_evidence(
            ROOT,
            run_id=run_id,
            table_index=request.table_index,
            column_mapping=request.column_mapping,
            provider=request.provider,
            source_release=request.source_release,
            active_threshold=request.active_threshold,
        )
    except (KeyError, IndexError, FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/documents/outputs/{output_id}/verify")
def document_output_verify(output_id: str) -> dict[str, object]:
    try:
        return verify_document_output(_database_path("documents"), output_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Document output not found.") from exc


@app.get("/system/cache-status")
def system_cache_status() -> dict[str, object]:
    return {
        "file_caches": runtime_cache_info(),
        "model_cache": model_artifact_cache_info(),
        "invalidation": "path_mtime_size",
    }


@app.get("/databases/status")
def database_status() -> dict[str, object]:
    return all_database_health(ROOT)


@app.get("/scientific-data/summary")
def scientific_data_summary() -> dict[str, object]:
    return scientific_registry_summary(ROOT)


@app.get("/intelligence/search")
def intelligence_search(
    q: str,
    limit: int = 25,
) -> dict[str, object]:
    return universal_search(
        ROOT,
        q,
        limit_per_source=min(max(limit, 1), 100),
    )


@app.get("/knowledge/search")
def knowledge_search(
    q: str = "",
    entity_type: str = "all",
    status: str = "all",
    limit: int = 100,
) -> dict[str, object]:
    database = _database_path("knowledge")
    return {
        "summary": asdict(knowledge_summary(database)),
        "results": search_knowledge(
            database,
            q,
            entity_type=entity_type,
            status=status,
            limit=min(max(limit, 1), 500),
        ),
    }


@app.get("/analytics/overview")
def analytics_overview(
    days: int = 180,
) -> dict[str, object]:
    database = _database_path("analytics")
    return {
        "summary": asdict(
            analytics_summary(
                database,
                days=min(max(days, 1), 365),
            )
        ),
        "modules": module_performance(
            database,
            days=min(max(days, 1), 365),
            limit=100,
        ),
    }


@app.get("/assets/search")
def assets_search(
    q: str = "",
    asset_type: str = "all",
    collection_id: str = "all",
    favourites_only: bool = False,
    limit: int = 100,
) -> dict[str, object]:
    database = _database_path("assets")
    return {
        "collections": list_collections(database),
        "results": search_assets(
            database,
            q,
            asset_type=asset_type,
            collection_id=collection_id,
            favourites_only=favourites_only,
            limit=min(max(limit, 1), 500),
        ),
    }


@app.get("/internet/status")
def internet_status() -> dict[str, object]:
    return {
        "configuration": internet_configuration(),
        "downloads": download_summary(_database_path("downloads")),
    }


@app.get("/internet/check")
def internet_check() -> dict[str, object]:
    return check_internet_services(policy=internet_policy_from_environment())


@app.get("/internet/downloads")
def internet_downloads(
    provider: str = "all",
    limit: int = 100,
) -> dict[str, object]:
    records = list_downloads(
        _database_path("downloads"),
        provider=provider,
        limit=min(max(limit, 1), 1000),
    )
    return {
        "summary": download_summary(_database_path("downloads")),
        "records": [asdict(record) for record in records],
    }


@app.get("/chemistry/common-compounds")
def common_compounds(
    q: str = "",
    name_type: str = "all",
    limit: int = 100,
) -> dict[str, object]:
    directory = load_common_compound_directory(ROOT)
    try:
        results = search_common_compounds(
            directory,
            q,
            name_type=name_type,
            limit=min(max(limit, 1), 1000),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "directory_rows": len(directory),
        "unique_structures": int(directory["canonical_smiles"].nunique()),
        "curated_common_names": int((directory["name_type"] == "curated_common_name").sum()),
        "results": results.to_dict(orient="records"),
    }


@app.get("/internet/pubchem/name/{compound_name}")
def internet_pubchem_name(
    compound_name: str,
) -> dict[str, object]:
    try:
        return asdict(
            fetch_pubchem_compound_by_name(
                compound_name,
                policy=internet_policy_from_environment(),
            )
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/internet/pdb/{pdb_id}")
def internet_pdb_metadata(pdb_id: str) -> dict[str, object]:
    try:
        return asdict(
            fetch_rcsb_entry(
                pdb_id,
                policy=internet_policy_from_environment(),
            )
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/internet/pdb/{pdb_id}/download")
def internet_pdb_download(
    pdb_id: str,
    file_format: str = "cif",
) -> dict[str, object]:
    try:
        result, record = download_rcsb_structure(
            pdb_id,
            file_format,
            project_root=ROOT,
            policy=internet_policy_from_environment(),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = asdict(result)
    payload["path"] = str(result.path)
    return {"download": payload, "registry": asdict(record)}


@app.post("/internet/url-download")
def internet_url_download(
    url: str,
    provider: str = "Public HTTPS",
    filename: str | None = None,
    official_hosts_only: bool = False,
    max_mb: int = 100,
) -> dict[str, object]:
    policy = replace(
        internet_policy_from_environment(),
        official_hosts_only=official_hosts_only,
    )
    try:
        result, record = download_public_file(
            url,
            runtime_data_path(ROOT, "internet_downloads", "public_https"),
            project_root=ROOT,
            registry_path=_database_path("downloads"),
            provider=provider,
            resource_id=None,
            preferred_filename=filename,
            policy=policy,
            max_bytes=min(max(max_mb, 1), 250) * 1024 * 1024,
            notes="API-requested public HTTPS research download.",
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = asdict(result)
    payload["path"] = str(result.path)
    return {"download": payload, "registry": asdict(record)}


@app.get("/data/packs")
def data_packs() -> dict[str, object]:
    return data_library_summary(ROOT)


@app.get("/data/coverage")
def data_coverage() -> dict[str, object]:
    return {
        "manifest": load_coverage_manifest(ROOT),
        "integrity": verify_coverage_integrity(ROOT),
    }


@app.get("/models/benchmark")
def model_benchmark() -> dict[str, object]:
    return data_library_summary(ROOT)["benchmark"]


@app.get("/models/double-benchmark")
def double_model_benchmark() -> dict[str, object]:
    benchmark = data_library_summary(ROOT)["benchmark"]
    ranking = [
        row for row in benchmark.get("ranking", []) if row.get("training_pack") == "double_ultra"
    ]
    return {
        "data_pack_version": benchmark.get("data_pack_version"),
        "source_rows": 32000,
        "ranking": ranking,
        "overall_best_models": benchmark.get("best_models", {}),
    }


@app.get("/models/5x-benchmark")
def five_x_model_benchmark() -> dict[str, object]:
    benchmark = data_library_summary(ROOT)["benchmark"]
    ranking = [
        row for row in benchmark.get("ranking", []) if row.get("training_pack") == "five_x_ultra"
    ]
    return {
        "data_pack_version": benchmark.get("data_pack_version"),
        "source_rows": 160000,
        "unique_compounds": 1000,
        "unique_targets": 160,
        "ranking": ranking,
        "overall_best_models": benchmark.get(
            "best_models",
            {},
        ),
    }


@app.get("/catalog/models")
def model_catalog() -> dict[str, object]:
    entries = sync_model_catalog(MODELS_DIRECTORY)
    return {
        "models": [asdict(entry) for entry in entries],
    }


@app.get("/catalog/datasets")
def dataset_catalog() -> dict[str, object]:
    records = list_datasets(_database_path("datasets"))
    return {
        "datasets": [asdict(record) for record in records],
    }


@app.get("/workflow/status")
def workflow_status() -> dict[str, object]:
    return build_workflow_status(ROOT)


@app.get("/ui/catalog")
def ui_catalog() -> dict[str, object]:
    return {
        "tools": [
            {
                "key": page.key,
                "path": page.path,
                "title": page.title,
                "icon": page.icon,
                "category": page.category,
                "description": page.description,
                "featured": page.featured,
            }
            for page in PAGE_CATALOG
        ]
    }


@app.get("/v1/connectors/providers")
def connected_providers() -> dict[str, object]:
    return {
        "count": len(CONNECTED_PROVIDERS),
        "providers": connected_provider_rows(),
        "entity_defaults": ENTITY_PROVIDER_DEFAULTS,
        "configuration": public_connection_status(),
        "registry": connected_registry_summary(_database_path("connected_sources")),
    }


@app.post("/v1/connectors/search")
def connected_search(request: ConnectedSearchRequest) -> dict[str, object]:
    providers = request.providers or list(ENTITY_PROVIDER_DEFAULTS.get(request.entity_type, ("ncbi",)))
    unknown = sorted(set(providers) - set(CONNECTED_PROVIDERS))
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown connected provider(s): {', '.join(unknown)}")
    return ConnectedProviderService(ROOT).universal_search(
        request.query,
        entity_type=request.entity_type,
        providers=providers,
        limit=request.limit,
    )


@app.post("/v1/connectors/health")
def connected_health(request: ConnectedHealthRequest) -> dict[str, object]:
    providers = request.providers or list(CONNECTED_PROVIDERS)
    unknown = sorted(set(providers) - set(CONNECTED_PROVIDERS))
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown connected provider(s): {', '.join(unknown)}")
    rows = ConnectedProviderService(ROOT, persist_queries=False).probe_all(providers)
    available = sum(1 for row in rows if row.get("available"))
    return {
        "requested": len(providers),
        "available": available,
        "failed": len(providers) - available,
        "results": rows,
    }


@app.get("/v1/connectors/history")
def connected_history(limit: int = 100) -> dict[str, object]:
    registry = _database_path("connected_sources")
    return {
        "summary": connected_registry_summary(registry),
        "queries": recent_connected_queries(registry, limit=min(max(1, limit), 500)),
        "health_checks": recent_connected_health_checks(registry, limit=min(max(1, limit), 500)),
    }


@app.get("/v1/copilot/status")
def copilot_status() -> dict[str, object]:
    configuration = public_connection_status()
    return {
        "configured": bool(configuration["openai_configured"]),
        "model": configuration["openai_model"],
        "base_url": configuration["openai_base_url"],
        "provider_tools": sorted(CONNECTED_PROVIDERS),
        "secret_persistence": False,
        "response_storage_requested": configuration["openai_store_responses"],
        "research_use_only": True,
    }


@app.get("/v1/copilot/connection-test")
def copilot_connection_test() -> dict[str, object]:
    return test_openai_connection(ROOT)


@app.post("/v1/copilot/query")
def copilot_query(request: CopilotQueryRequest) -> dict[str, object]:
    providers = request.providers or ["ncbi", "uniprot", "pubchem", "rcsb", "chembl", "europepmc"]
    unknown = sorted(set(providers) - set(CONNECTED_PROVIDERS))
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown Copilot provider tool(s): {', '.join(unknown)}")
    try:
        return OpenAICopilot(ROOT, model=request.model).run(
            request.query,
            allowed_providers=providers,
            context=request.context,
        ).to_dict()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/workflow/report-data")
def workflow_report_data() -> dict[str, object]:
    return build_workspace_report_data(
        ROOT,
        title="BioIntel AI Workspace API Report",
    )


@app.get("/portfolio/projects")
def portfolio_projects() -> dict[str, object]:
    projects = list_projects(_database_path("projects"))
    return {"projects": [asdict(project) for project in projects]}


@app.get("/operations/alerts")
def operations_alerts() -> dict[str, object]:
    return {"alerts": [asdict(item) for item in visible_alerts(ROOT)]}


@app.get("/operations/timeline")
def operations_timeline() -> dict[str, object]:
    return {"timeline": [asdict(item) for item in build_timeline(ROOT)]}


@app.get("/executive/summary")
def executive_summary() -> dict[str, object]:
    return build_executive_summary(ROOT)


@app.get("/governance/summary")
def governance_summary() -> dict[str, object]:
    return governance_portfolio_summary(_database_path("projects"))


@app.get("/governance/projects/{project_id}")
def governance_project(
    project_id: str,
) -> dict[str, object]:
    try:
        return project_governance_snapshot(
            _database_path("projects"),
            project_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@app.get("/projects/{project_id}/readiness")
def project_release_readiness(
    project_id: str,
) -> dict[str, object]:
    try:
        return project_readiness(ROOT, project_id)
    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@app.get("/projects/{project_id}/lineage")
def project_lineage(
    project_id: str,
) -> dict[str, object]:
    try:
        return build_lineage_graph(ROOT, project_id)
    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@app.get("/projects/{project_id}/evidence-manifest")
def project_evidence_manifest(
    project_id: str,
) -> dict[str, object]:
    try:
        return build_project_manifest(ROOT, project_id)
    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@app.get("/audit/integrity")
def audit_integrity() -> dict[str, object]:
    return verify_audit_chain(runtime_report_path(ROOT, "audit.jsonl"))


@app.get("/model/status")
def model_status() -> dict[str, object]:
    catalog_lookup = {entry.filename: entry for entry in sync_model_catalog(MODELS_DIRECTORY)}
    models = []
    for path in sorted(MODELS_DIRECTORY.glob("*.joblib")):
        try:
            artifact = load_model_artifact_cached(
                path,
                trusted_root=MODELS_DIRECTORY,
            )
            metadata = artifact.metadata
            models.append(
                {
                    "filename": path.name,
                    "experiment_id": metadata.experiment_id,
                    "model_name": metadata.model_name,
                    "model_version": metadata.model_version,
                    "task_type": metadata.task_type,
                    "dataset_name": metadata.dataset_name,
                    "dataset_sha256": metadata.dataset_sha256,
                    "synthetic_demo": metadata.synthetic_demo,
                    "lifecycle_state": (
                        catalog_lookup[path.name].state
                        if path.name in catalog_lookup
                        else "candidate"
                    ),
                    "is_default": (
                        catalog_lookup[path.name].is_default
                        if path.name in catalog_lookup
                        else False
                    ),
                }
            )
        except Exception as exc:
            models.append(
                {
                    "filename": path.name,
                    "error": str(exc),
                }
            )
    return {"models": models}







@app.get("/discovery/projects")
def discovery_projects() -> dict[str, object]:
    frame = list_discovery_projects(path=DISCOVERY_DATABASE)
    return {"projects": frame.to_dict(orient="records"), "count": len(frame)}


@app.post("/discovery/projects")
def discovery_project_create(request: DiscoveryProjectCreateRequest) -> dict[str, object]:
    try:
        project_id = create_discovery_project(
            request.project_name,
            indication=request.indication,
            objective=request.objective,
            owner=request.owner,
            settings=request.settings,
            path=DISCOVERY_DATABASE,
        )
        return discovery_project_snapshot(project_id, path=DISCOVERY_DATABASE)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/discovery/projects/{project_id}")
def discovery_project_get(project_id: str) -> dict[str, object]:
    try:
        return discovery_project_snapshot(project_id, path=DISCOVERY_DATABASE)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Discovery project not found") from exc


@app.get("/discovery/projects/{project_id}/bundle")
def discovery_project_bundle(project_id: str) -> StreamingResponse:
    try:
        payload = export_discovery_project_bundle(project_id, path=DISCOVERY_DATABASE)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Discovery project not found") from exc
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{project_id}_discovery_bundle.zip"'},
    )


@app.post("/discovery/projects/{project_id}/targets/profile")
def discovery_target_profile(
    project_id: str,
    request: DiscoveryTargetProfileRequest,
) -> dict[str, object]:
    try:
        profile = build_target_evidence_profile(
            request.target_id,
            request.evidence_rows,
            indication=request.indication,
            template=request.template,
            custom_weights=request.custom_weights,
            hard_gates=request.hard_gates,
        )
        payload = target_profile_dict(profile)
        target_record_id = add_target_assessment(
            project_id,
            target_id=request.target_id,
            scoring=payload,
            evidence=profile.evidence_register,
            path=DISCOVERY_DATABASE,
        )
        return {"target_record_id": target_record_id, "profile": payload}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Discovery project not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/discovery/projects/{project_id}/compounds")
def discovery_compounds(project_id: str) -> dict[str, object]:
    try:
        discovery_project_snapshot(project_id, path=DISCOVERY_DATABASE)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Discovery project not found") from exc
    frame = list_discovery_compounds(project_id, path=DISCOVERY_DATABASE)
    records = frame.drop(columns=["profile_json", "source_json"], errors="ignore").to_dict(orient="records")
    return {"compounds": records, "count": len(records)}


@app.post("/discovery/projects/{project_id}/compounds")
def discovery_compound_add(
    project_id: str,
    request: DiscoveryCompoundRequest,
) -> dict[str, object]:
    try:
        preparation = prepare_molecular_states(
            request.smiles,
            mode=request.preparation_mode,
            ph=request.ph,
        )
        profile = admet_profile_dict(profile_admet(preparation.standardized_parent_smiles))
        profile["molecular_preparation"] = preparation_dict(preparation)
        result = upsert_discovery_compound(
            project_id,
            compound_id=request.compound_id,
            original_smiles=request.smiles,
            standardized_smiles=str(profile["standardized_smiles"]),
            inchikey=profile.get("inchikey"),
            profile=profile,
            source=request.source,
            duplicate_policy=request.duplicate_policy,
            path=DISCOVERY_DATABASE,
        )
        return {**result, "profile": profile}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Discovery project not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/discovery/projects/{project_id}/rankings")
def discovery_rank_project(
    project_id: str,
    request: DiscoveryRankingRequest,
) -> dict[str, object]:
    try:
        compounds = list_discovery_compounds(project_id, path=DISCOVERY_DATABASE)
        if compounds.empty:
            raise ValueError("Project has no compounds")
        rows = []
        for row in compounds.to_dict(orient="records"):
            profile = row.pop("profile", {})
            row.pop("profile_json", None)
            row.pop("source", None)
            row.pop("source_json", None)
            rows.append({**row, **profile})
        frame = pd.DataFrame(rows)
        ranked = rank_discovery_hits(
            frame,
            id_column="compound_id",
            benefit_columns=request.benefit_columns or None,
            cost_columns=request.cost_columns or None,
            method=request.method,
            missing_penalty=request.missing_penalty,
            minimum_completeness=request.minimum_completeness,
        )
        ranking_id = save_discovery_ranking(
            project_id,
            result=ranked,
            method=request.method,
            parameters=request.model_dump(),
            path=DISCOVERY_DATABASE,
        )
        return {"ranking_id": ranking_id, "rows": ranked.to_dict(orient="records")}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Discovery project not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/discovery/batch/jobs")
def discovery_batch_job(request: DiscoveryBatchStandardizeRequest) -> dict[str, object]:
    job = JOB_QUEUE.submit(
        "discovery_batch_triage",
        request.model_dump(),
        stages=["prepare", "standardize", "profile", "deduplicate", "validate", "finalize"],
    )
    return asdict(job)


@app.post("/discovery/standardize-batch")
def discovery_standardize_batch(
    request: DiscoveryBatchStandardizeRequest,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for index, item in enumerate(request.rows, start=1):
        try:
            preparation = prepare_molecular_states(
                item.smiles,
                mode=request.preparation_mode,
                ph=request.ph,
            )
            rows.append(
                {
                    "source_row": index,
                    "compound_id": item.compound_id or f"row_{index}",
                    **preparation_dict(preparation),
                }
            )
        except Exception as exc:
            failures.append(
                {
                    "source_row": index,
                    "compound_id": item.compound_id,
                    "smiles": item.smiles,
                    "error": str(exc),
                }
            )
    frame = pd.DataFrame(rows)
    if request.deduplicate and not frame.empty:
        frame = frame.drop_duplicates("parent_inchikey", keep="first").reset_index(drop=True)
    return {"rows": frame.to_dict(orient="records"), "failures": failures}


@app.post("/discovery/similarity")
def discovery_similarity(request: DiscoverySimilarityRequest) -> dict[str, object]:
    try:
        hits, failures = similarity_search(
            request.query_smiles,
            request.rows,
            smiles_column=request.smiles_column,
            name_column=request.name_column,
            top_n=request.top_n,
        )
        return {
            "hits": hits.to_dict(orient="records"),
            "failures": failures.to_dict(orient="records"),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/discovery/admet-models")
def discovery_admet_models() -> dict[str, object]:
    frame = list_endpoint_model_cards(path=DISCOVERY_DATABASE)
    records = [] if frame.empty else frame.drop(columns=["model_card_json", "qualification_json"]).to_dict(orient="records")
    return {"models": records, "count": len(records)}


@app.post("/discovery/admet-models/qualify")
def discovery_admet_model_qualify(
    request: DiscoveryEndpointModelCardRequest,
) -> dict[str, object]:
    card = EndpointModelCard(**request.model_dump())
    qualification = qualify_endpoint_model(card)
    payload = asdict(qualification)
    persisted = register_endpoint_model_card(
        model_card=asdict(card),
        qualification=payload,
        path=DISCOVERY_DATABASE,
    )
    return {**payload, "persisted": persisted}


@app.get("/discovery/capabilities")
def discovery_capabilities() -> dict[str, object]:
    readiness = docking_readiness_dict(external_docking_readiness())
    return {
        "version": __version__,
        "persistent_projects": True,
        "target_intelligence": "evidence-weighted",
        "molecular_state_modes": [
            "submitted_form",
            "neutral_parent",
            "tautomer_ensemble",
            "stereoisomer_ensemble",
            "assay_context",
            "physiological_context",
        ],
        "ranking_methods": ["robust_percentile", "winsorized_minmax", "minmax", "zscore"],
        "docking": readiness,
        "scientific_boundary": "Unqualified biological endpoints remain not assessed",
    }


@app.post("/discovery/docking/qualify")
def discovery_docking_qualify(
    request: DiscoveryDockingQualificationRequest,
) -> dict[str, object]:
    return docking_readiness_dict(
        evaluate_docking_qualification(**request.model_dump())
    )


@app.post("/bioinformatics/phylogeny")
def bioinformatics_phylogeny(request: PhylogenyRequest) -> dict[str, object]:
    try:
        return {"consensus": consensus_sequence(request.sequences), "distance_matrix": distance_matrix(request.sequences), "newick": upgma_newick(request.sequences)}
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/bioinformatics/capabilities")
def bioinformatics_capabilities() -> dict[str, object]:
    capabilities = bioinformatics_capabilities_dict()
    return {"capabilities": capabilities, "available": sum(bool(item["available"]) for item in capabilities), "total": len(capabilities)}


@app.post("/bioinformatics/fastq/qc")
def bioinformatics_fastq_qc(request: FastqQcRequest) -> dict[str, object]:
    try:
        records = parse_fastq(request.fastq_text)
        result = fastq_qc(records)
        trimmed, trim_summary = trim_fastq(records, adapter=request.adapter, minimum_quality=request.minimum_quality, minimum_length=request.minimum_length)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"qc": fastq_qc_dict(result), "trim_summary": trim_summary, "trimmed_read_count": len(trimmed)}


@app.post("/bioinformatics/variants/summary")
def bioinformatics_variant_summary(request: VariantSummaryRequest) -> dict[str, object]:
    try:
        frame = parse_vcf(request.vcf_text)
        summary = variant_summary(frame)
        filtered = filter_variants(frame, minimum_quality=request.minimum_quality, require_pass=request.require_pass)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    safe = filtered.drop(columns=["info", "samples"], errors="ignore").head(500)
    return {"summary": variant_summary_dict(summary), "filtered_rows": len(filtered), "preview": safe.where(pd.notna(safe), None).to_dict(orient="records")}


@app.post("/bioinformatics/primers/design")
def bioinformatics_primer_design(request: PrimerDesignRequest) -> dict[str, object]:
    try:
        pairs = design_primer_pairs(request.sequence, minimum_product=request.minimum_product, maximum_product=request.maximum_product, maximum_pairs=request.maximum_pairs)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"pairs": [{"forward": pair.forward.sequence, "reverse": pair.reverse.sequence, "product_size": pair.product_size, "tm_difference": pair.tm_difference, "score": pair.score} for pair in pairs]}


@app.post("/bioinformatics/crispr/guides")
def bioinformatics_crispr_guides(request: CrisprDesignRequest) -> dict[str, object]:
    try:
        guides = find_crispr_guides(request.sequence, guide_length=request.guide_length)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"guides": [design_result_dict(item) for item in guides[:500]], "total": len(guides)}


@app.post("/bioinformatics/protein/annotate")
def bioinformatics_protein_annotation(request: ProteinAnnotationRequest) -> dict[str, object]:
    try:
        return protein_annotation_dict(annotate_protein(request.sequence))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/bioinformatics/structure/analyze")
def bioinformatics_structure_analysis(request: StructureAnalysisRequest) -> dict[str, object]:
    try:
        summary = structure_summary(request.pdb_text)
        contacts = ligand_contacts(request.pdb_text, cutoff=request.contact_cutoff)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"summary": structure_summary_dict(summary), "ligand_contacts": contacts}


@app.post("/bioinformatics/admet/profile")
def bioinformatics_admet_profile(request: AdmetProfileRequest) -> dict[str, object]:
    try:
        return admet_profile_dict(profile_admet(request.smiles))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/bioinformatics/pathways/enrichment")
def bioinformatics_pathway_enrichment(request: PathwayEnrichmentRequest) -> dict[str, object]:
    try:
        frame = pathway_enrichment(request.genes)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"rows": frame.where(pd.notna(frame), None).to_dict(orient="records")}


@app.post("/biotechnology/qpcr/ddct")
def biotechnology_qpcr(request: QpcrAnalysisRequest) -> dict[str, object]:
    try:
        frame = qpcr_delta_delta_ct(pd.DataFrame(request.rows), calibrator_sample=request.calibrator_sample)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"rows": frame.where(pd.notna(frame), None).to_dict(orient="records")}


@app.post("/biotechnology/elisa/quantify")
def biotechnology_elisa(request: ElisaAnalysisRequest) -> dict[str, object]:
    try:
        frame = pd.DataFrame(request.rows)
        if not {"type", "concentration", "absorbance"}.issubset(frame.columns):
            raise ValueError("Rows require type, concentration and absorbance columns.")
        labels = frame["type"].astype(str).str.lower()
        standards = frame[labels.eq("standard")].copy()
        unknowns = frame[labels.eq("unknown")].copy()
        calibration = fit_elisa_calibration(
            standards,
            candidate_models=tuple(request.candidate_models),
            maximum_replicate_cv_percent=request.maximum_replicate_cv_percent,
        )
        quantified = inverse_calibration_with_flags(
            unknowns["absorbance"],
            model=calibration["selected_model"],
            parameters=calibration["parameters"],
            concentration_range=calibration["concentration_range"],
            response_range=calibration["response_range"],
        )
        unknowns = unknowns.reset_index(drop=True)
        unknowns["estimated_concentration"] = quantified["estimated_concentration"]
        unknowns["quantification_status"] = quantified["quantification_status"]
        unknowns["recommendation"] = quantified["recommendation"]
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "selected_model": calibration["selected_model"],
        "parameters": calibration["parameters"],
        "fit_table": calibration["fit_table"].where(pd.notna(calibration["fit_table"]), None).to_dict(orient="records"),
        "unknowns": unknowns.where(pd.notna(unknowns), None).to_dict(orient="records"),
        "failures": calibration["failures"],
    }


@app.post("/biotechnology/enzyme/fit")
def biotechnology_enzyme(request: EnzymeKineticsRequest) -> dict[str, object]:
    try:
        frame = pd.DataFrame(request.rows)
        if not {"substrate", "velocity"}.issubset(frame.columns):
            raise ValueError("Rows require substrate and velocity columns.")
        comparison = compare_enzyme_models(frame["substrate"], frame["velocity"])
        selected_model = str(comparison.iloc[0]["model"]) if request.model == "auto" else request.model
        result = fit_enzyme_model(frame["substrate"], frame["velocity"], model=selected_model)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "selected_model": selected_model,
        "comparison": comparison.where(pd.notna(comparison), None).to_dict(orient="records"),
        "result": result,
    }


@app.post("/biotechnology/bioprocess/analyze")
def biotechnology_bioprocess(request: BioprocessAnalysisRequest) -> dict[str, object]:
    try:
        trajectory, summary = bioprocess_advanced_metrics(
            pd.DataFrame(request.rows),
            batch_column=request.batch_column,
            process_mode=request.process_mode,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"summary": summary, "trajectory": trajectory.where(pd.notna(trajectory), None).to_dict(orient="records")}


@app.post("/biotechnology/design/sample-size")
def biotechnology_design(request: ExperimentalDesignRequest) -> dict[str, object]:
    try:
        if request.design_type == "two_group":
            result = two_group_sample_size(request.effect_size, alpha=request.alpha, power=request.power, dropout_fraction=request.dropout_fraction)
        elif request.design_type == "paired":
            result = paired_sample_size(request.effect_size, alpha=request.alpha, power=request.power, dropout_fraction=request.dropout_fraction)
        elif request.design_type == "anova":
            result = one_way_anova_sample_size(request.effect_size, request.groups, alpha=request.alpha, power=request.power, dropout_fraction=request.dropout_fraction)
        elif request.design_type == "noninferiority":
            result = noninferiority_sample_size(request.margin, assumed_standard_deviation=request.assumed_standard_deviation, alpha=request.alpha / 2, power=request.power, dropout_fraction=request.dropout_fraction)
        else:
            result = equivalence_sample_size(request.margin, assumed_standard_deviation=request.assumed_standard_deviation, alpha=request.alpha, power=request.power, dropout_fraction=request.dropout_fraction)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@app.post("/biotechnology/plate/qc")
def biotechnology_plate_qc(request: PlateQcRequest) -> dict[str, object]:
    try:
        frame = pd.DataFrame(request.rows)
        layout = plate_map_audit(frame, well_column=request.well_column, plate_column=request.plate_column, plate_format=request.plate_format)
        spatial = plate_spatial_qc(frame, value_column=request.value_column, well_column=request.well_column, plate_column=request.plate_column, plate_format=request.plate_format)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"layout": layout, "spatial": spatial.where(pd.notna(spatial), None).to_dict(orient="records")}


@app.post("/sequence/analyze")
def sequence_analyze(
    request: SequenceAnalysisRequest,
) -> dict[str, object]:
    try:
        parsed = parse_sequence_text(request.sequence)
        detection = detect_sequence_type(parsed.sequence)
        if request.sequence_type == "auto":
            selected_type = detection.detected_type
            if selected_type not in {
                SequenceType.DNA,
                SequenceType.RNA,
                SequenceType.PROTEIN,
            }:
                raise ValueError(
                    "Automatic detection is ambiguous. " "Provide sequence_type explicitly."
                )
        else:
            selected_type = SequenceType(request.sequence_type)

        invalid = validate_for_type(parsed.sequence, selected_type)
        if invalid:
            preview = ", ".join(
                f"{character} at {position}" for position, character in invalid[:20]
            )
            raise ValueError(f"Invalid symbols for {selected_type.value}: {preview}")

        if selected_type in {SequenceType.DNA, SequenceType.RNA}:
            analysis: dict[str, object] = nucleotide_statistics(
                parsed.sequence,
                is_rna=selected_type == SequenceType.RNA,
            )
            if selected_type == SequenceType.DNA:
                analysis["transformations"] = dna_transformations(parsed.sequence)
        else:
            analysis = protein_statistics(parsed.sequence)

        return {
            "header": parsed.header,
            "selected_type": selected_type.value,
            "automatic_detection": detection.detected_type.value,
            "detection_message": detection.message,
            "analysis": analysis,
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/sequence/align")
def sequence_align(
    request: AlignmentRequest,
) -> dict[str, object]:
    try:
        query = parse_sequence_text(request.query)
        target = parse_sequence_text(request.target)
        selected_type = SequenceType(request.sequence_type)

        for label, parsed in (("query", query), ("target", target)):
            invalid = validate_for_type(parsed.sequence, selected_type)
            if invalid:
                raise ValueError(f"{label} contains invalid symbols for " f"{selected_type.value}.")

        return align_sequences(
            query.sequence,
            target.sequence,
            selected_type.value,
            mode=request.mode,
            match_score=request.match_score,
            mismatch_score=request.mismatch_score,
            gap_open=request.gap_open,
            gap_extend=request.gap_extend,
            substitution_matrix=request.substitution_matrix,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/dti/predict")
def dti_predict(
    request: DtiPredictionRequest,
) -> dict[str, object]:
    artifact = _trusted_model(request.model_filename)
    try:
        return asdict(
            predict_dti_pair(
                artifact,
                request.canonical_smiles,
                request.protein_sequence,
            )
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/dti/batch-predict")
def dti_batch_predict(
    request: DtiBatchRequest,
) -> dict[str, object]:
    artifact = _trusted_model(request.model_filename)
    dataframe = pd.DataFrame([row.model_dump() for row in request.rows])
    try:
        output = batch_predict_dti(
            artifact,
            dataframe,
            max_rows=100,
            n_jobs=0,
            feature_cache_path=FEATURE_CACHE_PATH,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"rows": output.where(pd.notna(output), None).to_dict(orient="records")}


@app.post("/model/external-validate")
def model_external_validate(
    request: ExternalValidationRequest,
) -> dict[str, object]:
    artifact = _trusted_model(request.model_filename)
    dataframe = pd.DataFrame(request.rows)
    try:
        result = evaluate_external_dataset(
            artifact,
            dataframe,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "task_type": result.task_type,
        "dataset_sha256": result.dataset_sha256,
        "input_rows": result.input_rows,
        "valid_rows": result.valid_rows,
        "invalid_rows": result.invalid_rows,
        "metrics": result.metrics,
        "conformal_diagnostics": result.conformal_diagnostics,
        "drift": result.drift,
        "data_quality_summary": result.data_quality_summary,
        "predictions": result.predictions.where(pd.notna(result.predictions), None).to_dict(
            orient="records"
        ),
        "errors": result.errors.where(pd.notna(result.errors), None).to_dict(orient="records"),
    }

