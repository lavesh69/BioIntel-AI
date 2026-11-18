from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.data.readiness import (
    dataset_readiness_rows,
    platform_readiness_summary,
    provider_readiness_rows,
)
from biointel.data.relationship_integrity import relationship_edges, relationship_summary
from biointel.ui.components import (
    metric_cards,
    scientific_boundary_banner,
    smart_dataframe,
    smart_json,
    source_badges,
)
from biointel.ui.performance import read_csv_cached, read_sql_cached
from biointel.ui.phase108_visuals import render_phase108_visual_suite  # noqa: E402
from biointel.ui.theme import apply_theme, hero, section_title
from biointel.ui.workflow import analysis_run

st.set_page_config(page_title="Scientific Data Readiness · BioIntel AI", page_icon="🧭", layout="wide")
apply_theme()

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("data_readiness", key_prefix="step116_69_Scientific_Data_Readiness_data_readiness_1", expanded=False)
summary = platform_readiness_summary(ROOT)
relations = relationship_summary(ROOT)
datasets = pd.DataFrame(dataset_readiness_rows(ROOT))
providers = pd.DataFrame(provider_readiness_rows(ROOT))

hero(
    "Scientific Data Readiness",
    "Separate registry completeness, relationship integrity, public-reference coverage and true scientific validation—without treating a complete manifest as experimental proof.",
    eyebrow="BioIntel AI · Scientific Intelligence for Life Sciences",
    chips=[
        "Metadata completeness",
        "Scientific validation",
        "Cross-database links",
        "Public references",
    ],
)
scientific_boundary_banner(
    source_kind="verified_public_reference",
    release_eligible=False,
    message="A 100% registry-completeness score means files, schemas, QC and provenance are documented. It does not make a synthetic/reference dataset scientifically release eligible.",
)

metadata_complete = (
    int((datasets.get("metadata_completeness", pd.Series(dtype=float)).fillna(0) >= 100).sum())
    if not datasets.empty
    else 0
)
release_eligible = int(summary["datasets"].get("release_eligible") or 0)
provider_records = (
    int(providers.get("records_available", pd.Series(dtype=float)).fillna(0).sum())
    if not providers.empty
    else 0
)
reference_records = (
    int(providers.get("reference_record_count", pd.Series(dtype=float)).fillna(0).sum())
    if not providers.empty
    else 0
)
metric_cards(
    [
        (
            "Registry complete",
            f"{metadata_complete}/{len(datasets)}",
            "Files, schema, QC and provenance only",
        ),
        ("Release eligible", release_eligible, "Requires real evidence and independent validation"),
        (
            "Relationship integrity",
            f"{relations.get('valid_edges', 0):,}/{relations.get('edge_count', 0):,}",
            None,
        ),
        (
            "Imported provider records",
            f"{provider_records:,}",
            "Verified public identifiers are counted separately",
        ),
    ]
)
source_badges(
    [
        ("Public identifier references", f"{reference_records:,}"),
        ("Blocked model requirements", str(summary["experiments"].get("blocked_requirements", 0))),
        ("Relationship warnings", str(relations.get("warning_edges", 0))),
        ("Broken relationships", str(relations.get("broken_edges", 0))),
    ]
)

tabs = st.tabs(
    [
        "Registry completeness",
        "Scientific validation",
        "Relationships",
        "Providers & references",
        "Experiments",
        "Repair & verification",
    ]
)

with tabs[0]:
    section_title("Dataset registry completeness", "🧾")
    if datasets.empty:
        st.warning("No dataset readiness rows are available.")
    else:
        datasets["metadata_score"] = pd.to_numeric(
            datasets["metadata_completeness"], errors="coerce"
        ).fillna(0)
        datasets["scientific_validation"] = (
            datasets["scientific_status"]
            .map(
                {
                    "release_eligible": "Release eligible",
                    "needs_evidence_review": "Evidence review required",
                    "reference_only": "Reference only",
                }
            )
            .fillna(datasets["scientific_status"])
        )
        filters = st.columns([1.6, 1, 1, 1])
        query = filters[0].text_input("Search datasets", placeholder="RNA-seq, variants, DTI…")
        status = filters[1].selectbox(
            "Scientific validation",
            ["All", *sorted(datasets["scientific_validation"].dropna().unique())],
        )
        integrity = filters[2].selectbox(
            "Integrity", ["All", *sorted(datasets["integrity_status"].dropna().unique())]
        )
        lineage_only = filters[3].checkbox("Only without lineage")
        filtered = datasets.copy()
        if query:
            text = (
                filtered[["dataset_name", "task_type", "source_description"]]
                .fillna("")
                .astype(str)
                .agg(" ".join, axis=1)
            )
            filtered = filtered[text.str.contains(query, case=False, regex=False)]
        if status != "All":
            filtered = filtered[filtered["scientific_validation"] == status]
        if integrity != "All":
            filtered = filtered[filtered["integrity_status"] == integrity]
        if lineage_only:
            filtered = filtered[
                pd.to_numeric(filtered["lineage_count"], errors="coerce").fillna(0) == 0
            ]
        chart_data = datasets.groupby("scientific_validation").size().reset_index(name="datasets")
        st.plotly_chart(
            px.bar(
                chart_data,
                x="scientific_validation",
                y="datasets",
                color="scientific_validation",
                title="Scientific validation status—not metadata score",
            ),
            width="stretch",
        )
        smart_dataframe(
            filtered[
                [
                    "dataset_name",
                    "dataset_version",
                    "task_type",
                    "row_count",
                    "file_count",
                    "column_count",
                    "sample_count",
                    "qc_count",
                    "provenance_count",
                    "lineage_count",
                    "integrity_status",
                    "metadata_score",
                    "scientific_validation",
                    "dataset_sha256",
                ]
            ],
            height=520,
        )
        st.download_button(
            "Download dataset readiness",
            filtered.to_csv(index=False),
            "step32_dataset_readiness.csv",
            "text/csv",
            width="stretch",
        )

with tabs[1]:
    section_title("Scientific validation truth", "🧪")
    validation = (
        datasets.groupby("scientific_status").size().reset_index(name="datasets")
        if not datasets.empty
        else pd.DataFrame()
    )
    if not validation.empty:
        st.plotly_chart(
            px.pie(
                validation,
                names="scientific_status",
                values="datasets",
                hole=0.55,
                title="Bundled dataset scientific status",
            ),
            width="stretch",
        )
    metric_cards(
        [
            (
                "Reference/simulation datasets",
                int((datasets["scientific_status"] == "reference_only").sum())
                if not datasets.empty
                else 0,
                None,
            ),
            (
                "Evidence review required",
                int((datasets["scientific_status"] == "needs_evidence_review").sum())
                if not datasets.empty
                else 0,
                None,
            ),
            ("Release eligible", release_eligible, None),
            ("Synthetic experiments", int(summary["experiments"].get("synthetic", 0)), None),
        ]
    )
    st.warning(
        "The bundled models remain software benchmarks. Registry integrity, artifacts and dataset bindings do not substitute for real experimental training, independent external validation or prospective wet-lab confirmation."
    )
    if not datasets.empty:
        issue_rows = []
        for row in datasets.to_dict(orient="records"):
            if row.get("scientific_status") != "release_eligible":
                issue_rows.append(
                    {
                        "dataset": row.get("dataset_name"),
                        "scientific_status": row.get("scientific_status"),
                        "validation_blocker": "Real evidence and independent validation required",
                        "metadata_complete": float(row.get("metadata_completeness") or 0) >= 100,
                    }
                )
        smart_dataframe(issue_rows, height=440)

with tabs[2]:
    section_title("Cross-database relationship integrity", "🕸️")
    metric_cards(
        [
            ("Resource nodes", f"{relations.get('node_count', 0):,}", None),
            ("Relationship edges", f"{relations.get('edge_count', 0):,}", None),
            ("Warnings", f"{relations.get('warning_edges', 0):,}", None),
            (
                "Broken/orphan",
                f"{relations.get('broken_edges', 0) + relations.get('orphan_findings', 0):,}",
                None,
            ),
        ]
    )
    edges = pd.DataFrame(relationship_edges(ROOT, limit=5000))
    if not edges.empty:
        status_chart = (
            edges.groupby(["relation_type", "validation_status"]).size().reset_index(name="links")
        )
        st.plotly_chart(
            px.bar(
                status_chart.head(50),
                x="relation_type",
                y="links",
                color="validation_status",
                title="Relationship types and validation",
            ),
            width="stretch",
        )
        search = st.text_input(
            "Search relationships", placeholder="dataset, model, project, evidence…"
        )
        if search:
            hay = edges.fillna("").astype(str).agg(" ".join, axis=1)
            edges = edges[hay.str.contains(search, case=False, regex=False)]
        smart_dataframe(edges, height=520)
        st.download_button(
            "Download relationship edges",
            edges.to_csv(index=False),
            "relationship_edges.csv",
            "text/csv",
            width="stretch",
        )

with tabs[3]:
    section_title("Scientific providers and verified identifier references", "🌐")
    if providers.empty:
        st.warning("No provider profiles are registered.")
    else:
        providers["record_scope"] = providers.get("data_scope", "connector_only")
        providers["actual_imported_records"] = pd.to_numeric(
            providers["records_available"], errors="coerce"
        ).fillna(0)
        providers["identifier_references"] = pd.to_numeric(
            providers.get("reference_record_count", 0), errors="coerce"
        ).fillna(0)
        provider_chart = providers[
            ["provider", "actual_imported_records", "identifier_references"]
        ].melt(id_vars="provider", var_name="record_kind", value_name="records")
        st.plotly_chart(
            px.bar(
                provider_chart,
                x="provider",
                y="records",
                color="record_kind",
                barmode="group",
                title="Imported data versus identifier-only references",
            ),
            width="stretch",
        )
        smart_dataframe(
            providers[
                [
                    "provider",
                    "resource_type",
                    "access_method",
                    "licence_profile",
                    "local_status",
                    "record_scope",
                    "actual_imported_records",
                    "identifier_references",
                    "download_records",
                    "last_checked_at_utc",
                ]
            ],
            height=470,
        )
    catalog = ROOT / "data" / "public_reference" / "verified_public_reference_catalog.csv"
    if catalog.is_file():
        public = read_csv_cached(catalog)
        st.subheader("Curated public identifier reference panel")
        smart_dataframe(public, height=420)
        st.download_button(
            "Download public reference catalogue",
            catalog.read_bytes(),
            catalog.name,
            "text/csv",
            width="stretch",
        )
    st.info(
        "Identifier references provide stable IDs and official links. They are not locally downloaded sequence/structure payloads and are not eligible for model training or validation."
    )

with tabs[4]:
    section_title("Model experiments and validation blockers", "🤖")
    experiment_db = ROOT / "reports" / "experiments.sqlite3"
    experiments = read_sql_cached(
        experiment_db,
        "SELECT experiment_id,model_name,task_type,model_name AS algorithm,synthetic_demo,dataset_sha256,trained_at_utc AS created_at_utc FROM experiments ORDER BY trained_at_utc DESC",
    )
    requirements = read_sql_cached(
        experiment_db,
        "SELECT experiment_id,requirement_label,status,message,evidence_reference,checked_at_utc FROM experiment_validation_requirements ORDER BY status,experiment_id",
    )
    artifacts = read_sql_cached(
        experiment_db,
        "SELECT experiment_id,artifact_type,relative_path,size_bytes,status,sha256 FROM experiment_artifacts ORDER BY experiment_id,artifact_type",
    )
    bindings = read_sql_cached(
        experiment_db,
        "SELECT experiment_id,binding_role,dataset_sha256,resolved_dataset_sha256,resolution_type,verified,verification_message FROM experiment_dataset_bindings ORDER BY experiment_id,binding_role",
    )
    metric_cards(
        [
            ("Experiments", len(experiments), None),
            (
                "Synthetic",
                int(experiments["synthetic_demo"].sum()) if not experiments.empty else 0,
                None,
            ),
            (
                "Verified bindings",
                int(bindings["verified"].sum()) if not bindings.empty else 0,
                None,
            ),
            (
                "Blocked requirements",
                int((requirements["status"] == "blocked").sum()) if not requirements.empty else 0,
                None,
            ),
        ]
    )
    req_chart = (
        requirements.groupby(["requirement_label", "status"]).size().reset_index(name="experiments")
        if not requirements.empty
        else pd.DataFrame()
    )
    if not req_chart.empty:
        st.plotly_chart(
            px.bar(
                req_chart,
                x="requirement_label",
                y="experiments",
                color="status",
                barmode="group",
                title="Model validation requirements",
            ),
            width="stretch",
        )
    exp_tabs = st.tabs(["Experiments", "Requirements", "Artifacts", "Dataset bindings"])
    with exp_tabs[0]:
        smart_dataframe(experiments, height=430)
    with exp_tabs[1]:
        smart_dataframe(requirements, height=430)
    with exp_tabs[2]:
        smart_dataframe(artifacts, height=430)
    with exp_tabs[3]:
        smart_dataframe(bindings, height=430)

with tabs[5]:
    section_title("Idempotent Quality-Hardened foundation repair", "🛠️")
    st.write(
        "Rebuild public identifier references and the foreign-key-enforced cross-database relationship index from the files already in this workspace. No remote records or experimental evidence are fabricated."
    )
    confirm = st.checkbox("I understand this rebuilds indexes and reference metadata only")
    if st.button(
        "Rebuild Quality-Hardened foundation", type="primary", disabled=not confirm, width="stretch"
    ):
        with analysis_run("Rebuilding relationship and public-reference indexes"):
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "build_step32_foundation.py")],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=900,
            )
        if result.returncode:
            st.error(result.stderr or result.stdout or "Foundation rebuild failed")
        else:
            st.success("Quality-Hardened foundation rebuilt successfully.")
            try:
                smart_json(json.loads(result.stdout))
            except Exception:
                st.code(result.stdout)
            st.rerun()
    st.code("BUILD_STEP33_FOUNDATION_WINDOWS.bat", language=None)

# Step 108 Phase 1+2 decision visual workspace
render_phase108_visual_suite("data_readiness", ROOT, context=locals())

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='scientific_data_readiness', title='Scientific Data Readiness', category='Data')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
