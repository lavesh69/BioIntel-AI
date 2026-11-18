from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.data.coverage_packs import (  # noqa: E402
    load_coverage_manifest,
    verify_coverage_integrity,
)
from biointel.data.data_packs import (  # noqa: E402
    data_library_summary,
    verify_data_pack_integrity,
)
from biointel.data.relationship_integrity import relationship_summary  # noqa: E402
from biointel.intelligence.data_intelligence import (  # noqa: E402
    all_database_health,
)
from biointel.operations.executive_summary import (  # noqa: E402
    build_executive_summary,
)
from biointel.projects.catalog import PROJECT_CATALOG  # noqa: E402
from biointel.projects.portfolio import ensure_biotechnology_projects  # noqa: E402
from biointel.stability_v145.runtime import (  # noqa: E402
    apply_process_hardening,
    startup_preflight,
)
from biointel.ui.brand import (
    BRAND,
    brand_trust_strip_html,
    branded_page_title,
    home_founder_credit_html,
    compact_module_name,
)  # noqa: E402
from biointel.ui.components import scientific_boundary_banner  # noqa: E402
from biointel.ui.weather_widget_ui import render_compact_weather_card  # noqa: E402
from biointel.ui.navigation import PAGE_BY_KEY  # noqa: E402
from biointel.ui.onboarding import render_first_launch_onboarding  # noqa: E402
from biointel.ui.theme import (  # noqa: E402
    apply_theme,
    badge,
    command_bar,
    database_cards,
    executive_kpis,
    feature_card,
    hero,
    insight_callout,
    professional_strip,
    section_title,
)

VERSION = (ROOT / "VERSION").read_text().strip()

st.set_page_config(
    page_title=branded_page_title("Home"),
    page_icon=str(ROOT / "assets" / "brand" / "biointel-icon-256.png"),
    layout="wide",
)

apply_process_hardening(ROOT)

@st.cache_resource(show_spinner=False)
def _startup_stability_preflight(root_text: str) -> dict[str, object]:
    return startup_preflight(Path(root_text), clean_stale_temp=True)

_runtime_stability = _startup_stability_preflight(str(ROOT))

apply_theme()

if not render_first_launch_onboarding(ROOT):
    st.stop()

if not bool(_runtime_stability.get("passed", False)):
    failed_checks = ", ".join(str(item.get("key")) for item in _runtime_stability.get("failures", []))
    st.error(
        "Startup safety checks found a blocking environment issue: "
        + (failed_checks or "unknown check")
        + ". Open Reliability & Optimization Center before running large analyses."
    )
    st.stop()
elif _runtime_stability.get("warnings"):
    warning_checks = ", ".join(str(item.get("key")) for item in _runtime_stability.get("warnings", []))
    st.warning(
        "The app started in protected mode. Review these advisory checks before large workflows: "
        + warning_checks
    )


@st.cache_resource(show_spinner=False)
def _ensure_project_registry(path_text: str) -> bool:
    ensure_biotechnology_projects(Path(path_text))
    return True


@st.cache_data(ttl=600, show_spinner=False)
def _home_snapshot(root_text: str) -> dict[str, object]:
    root = Path(root_text)
    return {
        "executive": build_executive_summary(root),
        "library": data_library_summary(root),
        "data_integrity": verify_data_pack_integrity(root),
        "coverage_manifest": load_coverage_manifest(root),
        "coverage_integrity": verify_coverage_integrity(root),
        "database_health": all_database_health(root),
        "relationship_health": relationship_summary(root),
    }


def safe_page_link(
    page_key: str,
    label: str | None = None,
) -> None:
    page = PAGE_BY_KEY.get(page_key)
    if page is None:
        st.warning(f"Workspace unavailable: {label or page_key}")
        return
    try:
        st.page_link(
            page.path,
            label=label or compact_module_name(page.key, page.title),
            width="stretch",
        )
    except (KeyError, RuntimeError):
        st.info(
            f"{label or compact_module_name(page.key, page.title)} — open it from the sidebar."
        )


_snapshot = _home_snapshot(str(ROOT))
executive = _snapshot["executive"]
library = _snapshot["library"]
data_integrity = _snapshot["data_integrity"]
coverage_manifest = _snapshot["coverage_manifest"]
coverage_integrity = _snapshot["coverage_integrity"]
database_health = _snapshot["database_health"]
relationship_health = _snapshot["relationship_health"]
benchmark = library["benchmark"]
best_models = benchmark.get("best_models", {})
professional = database_health["professional_warehouses"]

hero(
    "Scientific intelligence for life sciences.",
    (
        "Move from biological data to traceable analysis, evidence-aware interpretation and reproducible reports across genomics, omics, discovery, laboratory analytics and machine learning."
    ),
    eyebrow=f"{BRAND.name} · Created & Developed by {BRAND.founder}",
    chips=[
        f"{database_health['database_count']} database systems",
        f"{database_health['total_rows']:,} indexed rows",
        "Demo/reference assets labelled",
        f"Created by {BRAND.founder}",
        f"{relationship_health.get('valid_edges', 0):,} validated links",
    ],
)

st.markdown(home_founder_credit_html(), unsafe_allow_html=True)



cta_columns = st.columns(3, gap="small")
with cta_columns[0]:
    safe_page_link("quick_start", "Start analysis")
with cta_columns[1]:
    safe_page_link("biotechnology_projects", "Open project")
with cta_columns[2]:
    safe_page_link("command_center", "Explore workflows")

platform_cta_columns = st.columns(3, gap="small")
with platform_cta_columns[0]:
    safe_page_link("collaboration_review_v2", "Open BioIntel Live Workspace")
with platform_cta_columns[1]:
    safe_page_link("engine_control_center", "Open Engine Control Center")
with platform_cta_columns[2]:
    safe_page_link("production_enablement", "Review production readiness")

integration_columns = st.columns(4, gap="small")
with integration_columns[0]:
    safe_page_link("lab_pdf_notebook_rag", "Open lab document RAG")
with integration_columns[1]:
    safe_page_link("live_clinical_trials", "Search clinical trials")
with integration_columns[2]:
    safe_page_link("system_health_connectivity_weather", "Open connectivity & weather")
with integration_columns[3]:
    safe_page_link("engine_license_compliance", "Legal & component notices")

render_compact_weather_card()

section_title("Learning, teaching and scientific updates", "▦")
from biointel.education.selective_mega_ui import render_education_launch_cards  # noqa: E402

render_education_launch_cards(ROOT, safe_page_link)

education_learning = st.columns(3, gap="small")
with education_learning[0]:
    safe_page_link("biointel_academy", "Open Academy & Lecture Studio")
with education_learning[1]:
    safe_page_link("biointel_science_pulse", "Open Science Pulse")
with education_learning[2]:
    safe_page_link("biointel_education_universe", "Open Education Universe")

education_ai = st.columns(2, gap="small")
with education_ai[0]:
    safe_page_link("shiro_ai", "Open Shiro AI")
with education_ai[1]:
    safe_page_link("connect_home", "Open BioIntel Connect")

st.markdown(
    brand_trust_strip_html(
        evidence="Explicitly labelled",
        confidence="Shown with results",
        dataset_status="Provenance-aware",
        model_status="Evidence-gated",
        reviewed=f"Workspace v{VERSION}",
    ),
    unsafe_allow_html=True,
)

all_healthy = (
    data_integrity["valid"]
    and coverage_integrity["valid"]
    and database_health["healthy_count"] == database_health["database_count"]
)

if not all_healthy:
    badge(
        "● Workspace integrity requires attention",
        "warning",
    )
elif executive["risk_counts"]["critical"]:
    badge(
        f"● {executive['risk_counts']['critical']} critical project risk(s)",
        "danger",
    )
else:
    badge(
        "● Software integrity ready · scientific release remains evidence-gated",
        "success",
    )

professional_strip(
    BRAND.edition,
    (
        f"{database_health['database_count']} databases · secure outbound internet · "
        f"{database_health['total_indices']} indices · "
        f"{len(list((ROOT / 'models').glob('*.joblib')))} models · "
        "Genomics · Omics · Wet-lab · Local"
    ),
)


section_title("Choose a scientific workflow", "✦")
st.caption(
    "Start with an outcome. BioIntel keeps related tools inside a consistent product family and surfaces evidence, provenance and next actions at every stage."
)
start_actions = [
    (
        "biointel_studio",
        "Research cockpit",
        "Open the guided workspace for daily scientific work.",
        "✨",
    ),
    (
        "quick_start",
        "Guided analysis",
        "Select a scientific task and follow a clear launch path.",
        "▶",
    ),
    (
        "platform_quality",
        "Quality review",
        "Inspect engineering quality, evidence gaps and blockers.",
        "✓",
    ),
    (
        "scientific_data_readiness",
        "Data readiness",
        "Review provenance, authenticity and release eligibility.",
        "▤",
    ),
    (
        "final_assurance",
        "Final assurance",
        "Consolidate technical controls and external evidence boundaries.",
        "🏁",
    ),
    (
        "biotechnology_projects",
        "Biotechnology projects",
        "Launch five deep professional workbenches with quality gates, run history and research reports.",
        "🧪",
    ),
    (
        "neuro_cns_studio",
        "Neuro/CNS Studio",
        "Run 23 integrated neuroscience engines for compounds, targets, omics, signals and translation.",
        "🧠",
    ),
    (
        "biointel_copilot",
        "BioIntel Copilot",
        "Ask scientific questions with approved provider tools and source-separated evidence.",
        "🤖",
    ),
    (
        "connected_data_explorer",
        "Connected data",
        "Search NCBI, UniProt, PubChem, RCSB, ChEMBL and more.",
        "🌐",
    ),
    (
        "provider_integration_center",
        "Provider connections",
        "Configure and audit provider health, cache, rate limits and provenance.",
        "🔌",
    ),
    (
        "advanced_bioinformatics_tools",
        "Advanced tools",
        "Install and verify native Windows or WSL bioinformatics executables.",
        "🧰",
    ),
    (
        "scientific_integration_center",
        "Scientific integrations",
        "Review BioIntel engine readiness across genomics, omics, discovery, imaging and workflows.",
        "🧬",
    ),
    (
        "innovation_modules_hub",
        "Innovation modules",
        "Launch ten new graph genomics, protein design, CRISPR, outbreak, synthetic biology and AI workbenches.",
        "✨",
    ),
    (
        "scientific_expansion_hub",
        "Scientific expansion",
        "Open twenty-one new workbenches for epigenomics, metabolomics, biologics, clinical research, lab operations and privacy engineering.",
        "🚀",
    ),
]
for row_start in range(0, len(start_actions), 3):
    action_columns = st.columns(3)
    for column, (page_key, title, copy, icon) in zip(
        action_columns,
        start_actions[row_start : row_start + 3],
        strict=False,
    ):
        with column:
            feature_card(title, copy, icon)
            safe_page_link(page_key, "Open")

scientific_boundary_banner(
    source_kind="demo_reference",
    release_eligible=False,
    message=(
        "Bundled models and most bundled datasets are demonstration/reference assets. "
        "Verified public identifiers are included for lookup, but publication-grade use still requires genuine imported evidence and independent validation."
    ),
)

_ensure_project_registry(str(ROOT / "reports" / "projects.sqlite3"))
section_title("Applied biotechnology projects", "🧪")
st.caption(
    "Five full-depth workbenches now match the interaction and analysis maturity of the DTI Predictor and Sequence Analyzer."
)
for row_start in range(0, len(PROJECT_CATALOG), 3):
    project_columns = st.columns(3)
    for column, project in zip(
        project_columns, PROJECT_CATALOG[row_start : row_start + 3], strict=False
    ):
        with column:
            feature_card(project.short_title, project.objective, project.icon)
            safe_page_link(project.key, "Open project")


section_title("Intelligence layer", "🗄️")
database_cards(
    [
        {
            "icon": "🧠",
            "title": "Research Knowledge Warehouse",
            "copy": (
                "Search compounds, sequences, targets, models, datasets, "
                "projects, protocols and DTI relationships."
            ),
            "status": ("healthy" if professional["knowledge"]["healthy"] else "review"),
            "stats": [
                (
                    "Entities",
                    f"{professional['knowledge']['summary']['entities']:,}",
                ),
                (
                    "Relations",
                    f"{professional['knowledge']['summary']['relations']:,}",
                ),
                (
                    "Protocols",
                    f"{professional['knowledge']['summary']['protocols']:,}",
                ),
            ],
        },
        {
            "icon": "📈",
            "title": "Analytics & Observability",
            "copy": (
                "Monitor workflow success, latency, data quality, system "
                "performance and operational alerts."
            ),
            "status": ("healthy" if professional["analytics"]["healthy"] else "review"),
            "stats": [
                (
                    "Events",
                    f"{professional['analytics']['summary']['run_events']:,}",
                ),
                (
                    "Success",
                    f"{professional['analytics']['summary']['success_rate']:.1f}%",
                ),
                (
                    "Alerts",
                    f"{professional['analytics']['summary']['alerts']:,}",
                ),
            ],
        },
        {
            "icon": "📚",
            "title": "Research Assets & Collections",
            "copy": (
                "Organise models, reports, datasets, modules, notes, tags and executive favourites."
            ),
            "status": ("healthy" if professional["assets"]["healthy"] else "review"),
            "stats": [
                (
                    "Assets",
                    f"{professional['assets']['summary']['assets']:,}",
                ),
                (
                    "Tags",
                    f"{professional['assets']['summary']['tags']:,}",
                ),
                (
                    "Notes",
                    f"{professional['assets']['summary']['notes']:,}",
                ),
            ],
        },
    ]
)

intelligence_links = st.columns(4)
for column, key, label in (
    (
        intelligence_links[0],
        "data_intelligence",
        "Open Data Intelligence Hub",
    ),
    (
        intelligence_links[1],
        "knowledge_warehouse",
        "Search Knowledge",
    ),
    (
        intelligence_links[2],
        "analytics_observability",
        "View Analytics",
    ),
    (
        intelligence_links[3],
        "research_assets",
        "Browse Assets",
    ),
):
    with column:
        safe_page_link(key, label)

section_title("Executive pulse", "◎")
coverage_totals = coverage_manifest.get("totals", {})
executive_kpis(
    [
        (
            "Indexed knowledge",
            f"{database_health['total_rows']:,}",
            "Rows across twelve SQLite systems",
        ),
        (
            "DTI benchmark",
            "160,000",
            "1,000 molecules × 160 targets",
        ),
        (
            "Scientific coverage",
            f"{coverage_totals.get('sequence_records', 0):,} sequences",
            (
                f"{coverage_totals.get('molecules', 0):,} compounds · "
                f"{coverage_totals.get('external_validation_rows', 0):,} validation rows"
            ),
        ),
        (
            "Portfolio state",
            str(executive["portfolio"]["total"]),
            (
                f"{executive['portfolio']['active']} active · "
                f"{executive['risk_counts']['critical']} critical risks"
            ),
        ),
    ]
)

section_title("Workspace hubs", "🧭")
st.caption(
    "Open tools by task instead of scanning one long list. Each hub keeps related workflows together."
)
workspace_hubs = {
    "Analyze": [
        (
            "sequence_analyzer",
            "Sequence Analyzer",
            "Inspect DNA, RNA and protein sequences with clean exports.",
            "🧬",
        ),
        (
            "fastq_genomics_qc",
            "FASTQ & Genome QC",
            "Quality-control reads, adapters and assembly metrics.",
            "🧬",
        ),
        (
            "variant_annotation",
            "Variant & Annotation",
            "Filter VCF variants and inspect genomic annotations.",
            "🧬",
        ),
        (
            "transcriptomics_expression",
            "Transcriptomics Lab",
            "Normalize expression data and screen differential genes.",
            "📈",
        ),
        (
            "wetlab_biotechnology",
            "Wet-Lab Biotechnology",
            "Analyse qPCR, ELISA, kinetics and bioprocess outputs.",
            "🧪",
        ),
        (
            "document_intelligence",
            "Document Intelligence",
            "Extract structured data from PDF, Excel and DOCX files.",
            "📄",
        ),
    ],
    "Data & knowledge": [
        (
            "data_library",
            "Data & Model Library",
            "Browse registered datasets, models and lineage in one place.",
            "🗃️",
        ),
        (
            "data_intelligence",
            "Data Intelligence",
            "Inspect database coverage, health and cross-system relationships.",
            "🧠",
        ),
        (
            "knowledge_warehouse",
            "Knowledge Warehouse",
            "Search compounds, sequences, targets, protocols and relations.",
            "🔎",
        ),
        (
            "scientific_curation",
            "Scientific Curation",
            "Review provenance, source quality and curation status.",
            "🧹",
        ),
        (
            "internet_research",
            "Internet Research",
            "Retrieve public scientific structures and research files.",
            "🌐",
        ),
        (
            "demo_data_hub",
            "Demo Workspace",
            "Explore populated starter assets and safe demonstration workflows.",
            "🧰",
        ),
    ],
    "AI & discovery": [
        (
            "discovery_command_center",
            "Discovery Command Center",
            "Run the connected target-to-hit workflow and rank compound evidence.",
            "🔭",
        ),
        (
            "drug_analyzer",
            "Drug SMILES Analyzer",
            "Validate structures and inspect chemistry descriptors.",
            "💊",
        ),
        (
            "dti_features",
            "DTI Feature Builder",
            "Build reproducible drug-target feature vectors.",
            "🧩",
        ),
        (
            "model_training",
            "Model Training",
            "Train and compare controlled demonstration models.",
            "🤖",
        ),
        (
            "dti_predictor",
            "DTI Predictor",
            "Run schema-checked single and batch predictions.",
            "🎯",
        ),
        ("ml_autolab", "ML AutoLab", "Compare candidate models and champion metrics.", "🧠"),
        (
            "admet_discovery",
            "ADMET Triage & Developability",
            "Run rule-based developability triage and qualified endpoint plugins.",
            "⚗️",
        ),
    ],
    "Validate & release": [
        (
            "scientific_data_readiness",
            "Scientific Readiness",
            "Audit files, schemas, QC, provenance and source imports.",
            "🧭",
        ),
        (
            "benchmark_leakage_lab",
            "Leakage Lab",
            "Check train-test separation and benchmark integrity.",
            "🧪",
        ),
        (
            "scientific_release_gate",
            "Scientific Release Gate",
            "Review blockers before publication or release claims.",
            "🚦",
        ),
        (
            "clinical_pharma_validation",
            "Clinical & Pharma Validation",
            "Execute controlled site, protocol, prospective evidence and validation-dossier workflows.",
            "🏥",
        ),
        (
            "real_external_validation",
            "Real External Validation",
            "Score authentic independent studies, publications, inspections, authorizations and post-market evidence.",
            "🌍",
        ),
        (
            "final_assurance",
            "Final Assurance",
            "View the consolidated quality and evidence boundary.",
            "🏁",
        ),
    ],
    "Operate": [
        (
            "workflow_dashboard",
            "Workflow Dashboard",
            "Plan and track active research workflows.",
            "🗺️",
        ),
        (
            "project_portfolio",
            "Project Portfolio",
            "Manage priorities, ownership and milestones.",
            "📁",
        ),
        (
            "performance_jobs",
            "Performance & Jobs",
            "Monitor batch activity, latency and operational work.",
            "⚡",
        ),
        (
            "analytics_observability",
            "Analytics & Observability",
            "Inspect success rates, events and alerts.",
            "📈",
        ),
        (
            "governance_hub",
            "Governance Hub",
            "Control decisions, approvals and evidence gates.",
            "🛡️",
        ),
    ],
}
hub_tabs = st.tabs(list(workspace_hubs))
for hub_tab, (_, hub_items) in zip(hub_tabs, workspace_hubs.items(), strict=False):
    with hub_tab:
        for row_start in range(0, len(hub_items), 3):
            hub_columns = st.columns(3)
            for column, (key, title, copy, icon) in zip(
                hub_columns,
                hub_items[row_start : row_start + 3],
                strict=False,
            ):
                with column:
                    feature_card(title, copy, icon)
                    safe_page_link(key, "Open workspace")

command_bar(
    "Professional local operation",
    (
        "All scientific data, telemetry and database content remains local. "
        "No account, external tracking or API key is required."
    ),
)

best_classifier = best_models.get("classification", {}).get(
    "model_name",
    "Not available",
)
best_regressor = best_models.get("regression", {}).get(
    "model_name",
    "Not available",
)
insight_callout(
    "Current ML champions",
    (
        f"Classification: {best_classifier}. "
        f"Regression: {best_regressor}. "
        "Synthetic benchmark metrics are software evidence, not clinical evidence."
    ),
    "🏆",
)

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='home', title='Home', category='Start')

def legacy_education_navigation_links() -> None:
    """Compatibility wrapper for the three R8 Education launch entry points."""
    safe_page_link("biointel_education_home", "Open Education Home")
    safe_page_link("biointel_classroom", "Open BioIntel Classroom")
    safe_page_link("biointel_examinations", "Open Examination Command Center")
