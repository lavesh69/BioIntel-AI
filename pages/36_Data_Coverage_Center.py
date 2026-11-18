from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.data.coverage_packs import (
    load_coverage_manifest,
    register_coverage_datasets,
    seed_demo_workspace,
    verify_coverage_integrity,
)
from biointel.data.dataset_registry import list_datasets
from biointel.governance.governance_registry import (
    governance_portfolio_summary,
)
from biointel.portfolio.project_registry import (
    list_projects,
    portfolio_summary,
)
from biointel.training.experiment_registry import (
    list_experiments,
)
from biointel.training.model_catalog import sync_model_catalog
from biointel.ui.components import smart_json
from biointel.ui.navigation import PAGE_BY_KEY
from biointel.ui.theme import (
    apply_theme,
    badge,
    executive_kpis,
    hero,
    professional_strip,
    section_title,
)

st.set_page_config(
    page_title="Data Coverage Center · BioIntel AI",
    page_icon="🧰",
    layout="wide",
)

apply_theme()

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("data_coverage", key_prefix="step116_36_Data_Coverage_Center_data_coverage_1", expanded=False)
manifest = load_coverage_manifest(ROOT)
integrity = verify_coverage_integrity(ROOT)
assets = manifest.get("assets", [])
totals = manifest.get("totals", {})
datasets = list_datasets(
    ROOT / "reports" / "datasets.sqlite3",
    limit=5000,
)
projects = list_projects(
    ROOT / "reports" / "projects.sqlite3",
)
portfolio = portfolio_summary(ROOT / "reports" / "projects.sqlite3")
governance = governance_portfolio_summary(ROOT / "reports" / "projects.sqlite3")
models = sync_model_catalog(ROOT / "models")
experiments = list_experiments(
    ROOT / "reports" / "experiments.sqlite3",
    limit=5000,
)

hero(
    "Complete ready-data coverage across scientific and professional modules.",
    (
        "Inspect every bundled coverage asset, download ready inputs, "
        "refresh registry metadata and seed a professional project/governance "
        "workspace without manual data entry."
    ),
    eyebrow="Quality-Hardened · Data Coverage Center",
    chips=[
        "800 sequences",
        "1,000 molecules",
        "14,000 validation rows",
        "12 demo projects",
    ],
)

badge(
    (
        "● Complete coverage pack verified"
        if integrity["valid"]
        else "● Coverage integrity requires attention"
    ),
    "success" if integrity["valid"] else "danger",
)

professional_strip(
    "Complete Coverage Pack",
    (
        f"{integrity['checked_files']} verified files · "
        f"{len(datasets)} dataset records · "
        f"{len(models)} registered models · "
        f"{len(experiments)} experiment records"
    ),
)

executive_kpis(
    [
        (
            "Sequence records",
            f"{int(totals.get('sequence_records', 0)):,}",
            "DNA, RNA and protein libraries",
        ),
        (
            "Molecules",
            f"{int(totals.get('molecules', 0)):,}",
            "Ready BioIntel-validated SMILES structures",
        ),
        (
            "Validation rows",
            f"{int(totals.get('external_validation_rows', 0)):,}",
            "Independent and shifted classification/regression files",
        ),
        (
            "Professional workspace",
            f"{portfolio['total']} projects",
            (
                f"{governance['milestones_total']} milestones · "
                f"{governance['gates_total']} gates"
            ),
        ),
    ]
)

coverage_tab, downloads_tab, workspace_tab, matrix_tab = st.tabs(
    [
        "Coverage assets",
        "Downloads",
        "Workspace seed",
        "Module matrix",
    ]
)

with coverage_tab:
    section_title("Verified assets", "✓")
    if assets:
        frame = pd.DataFrame(assets)
        st.dataframe(
            frame,
            width="stretch",
            hide_index=True,
        )
    else:
        st.warning("Coverage pack is missing. Run " "SEED_COMPLETE_DATA_WINDOWS.bat.")
    smart_json(integrity)

with downloads_tab:
    section_title("Ready module inputs", "📥")
    for asset in assets:
        path = ROOT / str(asset["filename"])
        with st.container(border=True):
            columns = st.columns([2.2, 1, 1])
            columns[0].markdown(f"### {asset['title']}")
            columns[1].metric(
                "Rows / records",
                f"{int(asset['rows']):,}",
            )
            columns[2].metric(
                "Section",
                str(asset["section"]),
            )
            st.caption(str(asset["description"]))
            if path.is_file():
                mime = "text/csv" if path.suffix.lower() == ".csv" else "text/plain"
                st.download_button(
                    f"Download {path.name}",
                    path.read_bytes(),
                    path.name,
                    mime,
                    key=f"coverage_download_{asset['key']}",
                )

with workspace_tab:
    section_title("Professional demo workspace", "📁")
    st.info(
        "The packaged workspace already includes 12 DEMO projects, "
        "48 milestones, 12 decisions and 60 approval gates. "
        "Reseeding replaces only DEMO-prefixed projects; user projects remain untouched."
    )
    workspace_columns = st.columns(4)
    workspace_columns[0].metric(
        "Projects",
        portfolio["total"],
    )
    workspace_columns[1].metric(
        "Milestones",
        governance["milestones_total"],
    )
    workspace_columns[2].metric(
        "Decisions",
        governance["decisions_total"],
    )
    workspace_columns[3].metric(
        "Approval gates",
        governance["gates_total"],
    )

    action_columns = st.columns(2)
    if action_columns[0].button(
        "Refresh coverage dataset registry",
        type="primary",
        width="stretch",
    ):
        try:
            records = register_coverage_datasets(ROOT)
        except Exception as exc:
            st.error(f"Registry refresh failed: {exc}")
        else:
            st.success(f"Registered {len(records)} coverage datasets.")
            st.rerun()

    confirm = action_columns[1].checkbox(
        "Confirm replacement of DEMO projects",
    )
    if st.button(
        "Reseed complete DEMO workspace",
        disabled=not confirm,
        width="stretch",
    ):
        try:
            summary = seed_demo_workspace(
                ROOT,
                replace_existing_demo=True,
            )
        except Exception as exc:
            st.error(f"Workspace seed failed: {exc}")
        else:
            st.success("Professional demo workspace seeded.")
            smart_json(summary)
            st.rerun()

with matrix_tab:
    section_title("Section-by-section data coverage", "◎")
    rows = [
        ("Sequence Analyzer", "800 sequence records", "sequence_analyzer"),
        ("Sequence Comparison", "180 ready pairs", "sequence_comparison"),
        ("Batch Sequence", "800-record FASTA", "batch_sequence"),
        ("SMILES Analyzer", "1,000 molecules", "drug_analyzer"),
        ("DTI Feature Builder", "32,000-pair Double pack", "feature_builder"),
        ("Model Training", "Five dataset sizes", "model_training"),
        ("DTI Predictor", "250 / 1,000 / 2,000-row inputs", "dti_predictor"),
        ("External Validation", "14,000 validation/drift rows", "external_validation"),
        ("External Databases", "20 starter identifiers", "external_databases"),
        ("Dataset Registry", f"{len(datasets)} records", "dataset_registry"),
        ("Experiment Registry", f"{len(experiments)} experiments", "experiment_registry"),
        ("Project Portfolio", f"{portfolio['total']} projects", "project_portfolio"),
        ("Governance Hub", f"{governance['milestones_total']} milestones", "governance_hub"),
        ("Evidence Studio", "Seeded linked projects", "evidence_studio"),
    ]
    st.dataframe(
        pd.DataFrame(
            rows,
            columns=["Module", "Ready data", "Page key"],
        ),
        width="stretch",
        hide_index=True,
    )

    link_columns = st.columns(4)
    for column, key in zip(
        link_columns,
        (
            "sequence_analyzer",
            "drug_analyzer",
            "external_validation",
            "project_portfolio",
        ),
        strict=True,
    ):
        page = PAGE_BY_KEY[key]
        with column:
            try:
                st.page_link(
                    page.path,
                    label=page.title,
                    icon=page.icon,
                    width="stretch",
                )
            except (KeyError, RuntimeError):
                st.caption(f"Open {page.title} from the sidebar.")

    st.download_button(
        "Download coverage manifest JSON",
        json.dumps(
            manifest,
            indent=2,
            default=str,
        ),
        "biointel_coverage_manifest.json",
        "application/json",
    )

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='data_coverage', title='Data Coverage Center', category='Data')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
