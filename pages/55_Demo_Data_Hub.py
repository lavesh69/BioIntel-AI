from __future__ import annotations

import json
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

from biointel.data.evidence_registry import registry_summary
from biointel.data.relationship_integrity import relationship_summary
from biointel.documents.history import history_summary
from biointel.dti.feature_cache import FeatureCache
from biointel.internet.download_registry import download_summary
from biointel.jobs.local_queue import LocalJobQueue
from biointel.ui.components import (
    metric_cards,
    scientific_boundary_banner,
    smart_dataframe,
)
from biointel.ui.performance import read_csv_cached, read_sql_cached
from biointel.ui.theme import apply_theme, hero, section_title
from biointel.ui.workflow import analysis_run

st.set_page_config(page_title="Data & Reference Hub · BioIntel AI", page_icon="🧰", layout="wide")
apply_theme()
hero(
    "Data & Reference Hub",
    "Explore the populated workspace, distinguish demo data from verified public references, download starter files and rebuild local indexes safely.",
    eyebrow="BioIntel AI · Scientific Intelligence for Life Sciences",
    chips=["Demo datasets", "Public references", "Starter downloads", "Safe reload"],
)
scientific_boundary_banner(
    source_kind="verified_public_reference",
    release_eligible=False,
    message="The workspace contains three clearly separated scopes: simulated demo data, verified public-reference identifiers/datasets, and user-imported evidence. Only reviewed user/official evidence can advance toward scientific release.",
)

history = history_summary(ROOT / "reports" / "document_history.sqlite3")
evidence = registry_summary(ROOT / "reports" / "evidence.sqlite3")
downloads = download_summary(ROOT / "reports" / "internet_downloads.sqlite3")
relations = relationship_summary(ROOT)
queue = LocalJobQueue(ROOT / "reports" / "jobs.sqlite3")
jobs = queue.list(limit=1000)
feature_cache = FeatureCache(ROOT / "reports" / "feature_cache.sqlite3").stats()

datasets = read_sql_cached(
    ROOT / "reports" / "datasets.sqlite3",
    "SELECT dataset_name,dataset_version,task_type,row_count,source_description,metadata_json,created_at_utc,dataset_sha256 FROM datasets ORDER BY created_at_utc DESC",
)
readiness = read_sql_cached(
    ROOT / "reports" / "datasets.sqlite3",
    "SELECT dataset_sha256,integrity_status,scientific_status,metadata_completeness,lineage_count FROM dataset_readiness",
)
projects = read_sql_cached(
    ROOT / "reports" / "projects.sqlite3",
    "SELECT project_code,name,status,priority,owner_label,target_date FROM projects ORDER BY updated_at_utc DESC",
)
documents = read_sql_cached(
    ROOT / "reports" / "document_history.sqlite3",
    "SELECT source_name,file_type,status,table_count,row_count,character_count,project_code,started_at_utc FROM document_extraction_runs ORDER BY started_at_utc DESC",
)
evidence_rows = read_sql_cached(
    ROOT / "reports" / "evidence.sqlite3",
    "SELECT source_record_id,assay_id,publication_id,evidence_quality,review_status,created_at_utc FROM dataset_evidence_links ORDER BY created_at_utc DESC",
)
providers = read_sql_cached(
    ROOT / "reports" / "internet_downloads.sqlite3",
    "SELECT provider,resource_type,local_status,records_available,COALESCE(reference_record_count,0) reference_record_count,COALESCE(data_scope,'connector_only') data_scope,last_checked_at_utc FROM scientific_source_catalog ORDER BY provider",
)

merged = datasets.merge(readiness, on="dataset_sha256", how="left")
merged["scope"] = merged["metadata_json"].map(
    lambda raw: (
        "Public reference"
        if json.loads(raw or "{}").get("public_reference")
        else "Demo / reference"
    )
)
public_catalog = ROOT / "data" / "public_reference" / "verified_public_reference_catalog.csv"
public_refs = read_csv_cached(public_catalog) if public_catalog.is_file() else pd.DataFrame()
public_datasets = merged[merged["scope"] == "Public reference"]

metric_cards(
    [
        ("Registered datasets", f"{len(merged):,}", None),
        (
            "Real public reference rows",
            f"{int(public_datasets['row_count'].sum()):,}",
            "Reference-only, not bundled-model validation",
        ),
        ("Public identifiers", f"{len(public_refs):,}", None),
        ("Validated relationships", f"{relations.get('valid_edges', 0):,}", None),
        ("Document runs", f"{history['total_runs']:,}", None),
        (
            "Evidence links",
            f"{evidence['counts']['dataset_evidence_links']:,}",
            "Bundled evidence is demonstration data",
        ),
        ("Feature cache", f"{feature_cache.entries:,}", None),
        ("Jobs", f"{len(jobs):,}", None),
    ]
)

tabs = st.tabs(
    [
        "Coverage",
        "Datasets",
        "Public references",
        "Documents & evidence",
        "Projects & jobs",
        "Starter files",
        "Reload",
    ]
)

with tabs[0]:
    section_title("Workspace coverage by scientific scope", "📊")
    scope = (
        merged.groupby(["scope", "scientific_status"], dropna=False)
        .agg(datasets=("dataset_sha256", "count"), rows=("row_count", "sum"))
        .reset_index()
    )
    st.plotly_chart(
        px.bar(
            scope,
            x="scope",
            y="rows",
            color="scientific_status",
            barmode="stack",
            title="Dataset rows by scope and scientific status",
        ),
        width="stretch",
    )
    provider_long = providers[["provider", "records_available", "reference_record_count"]].melt(
        id_vars="provider", var_name="record_kind", value_name="records"
    )
    st.plotly_chart(
        px.bar(
            provider_long,
            x="provider",
            y="records",
            color="record_kind",
            barmode="group",
            title="Actual imported records versus identifier references",
        ),
        width="stretch",
    )
    st.info(
        "Large synthetic DTI packs remain available for software/load testing. The real public layer is deliberately smaller and visibly separated so volume is not confused with validation."
    )

with tabs[1]:
    filters = st.columns([1.5, 1, 1])
    query = filters[0].text_input("Search datasets", placeholder="breast cancer, RNA-seq, VCF…")
    scope_filter = filters[1].selectbox("Scope", ["All", *sorted(merged["scope"].unique())])
    status_filter = filters[2].selectbox(
        "Scientific status", ["All", *sorted(merged["scientific_status"].dropna().unique())]
    )
    view = merged.copy()
    if query:
        hay = (
            view[["dataset_name", "source_description", "task_type"]]
            .fillna("")
            .astype(str)
            .agg(" ".join, axis=1)
        )
        view = view[hay.str.contains(query, case=False, regex=False)]
    if scope_filter != "All":
        view = view[view["scope"] == scope_filter]
    if status_filter != "All":
        view = view[view["scientific_status"] == status_filter]
    smart_dataframe(
        view[
            [
                "dataset_name",
                "dataset_version",
                "scope",
                "task_type",
                "row_count",
                "integrity_status",
                "scientific_status",
                "metadata_completeness",
                "lineage_count",
                "source_description",
                "dataset_sha256",
            ]
        ],
        height=520,
    )
    st.download_button(
        "Download dataset catalogue",
        view.to_csv(index=False),
        "biointel_dataset_catalogue.csv",
        "text/csv",
        width="stretch",
    )

with tabs[2]:
    st.subheader("Verified public identifier references")
    smart_dataframe(public_refs, height=430)
    st.subheader("Bundled real public reference datasets")
    smart_dataframe(
        public_datasets[
            [
                "dataset_name",
                "row_count",
                "source_description",
                "scientific_status",
                "dataset_sha256",
            ]
        ],
        height=260,
    )
    reference_dir = ROOT / "data" / "public_reference"
    files = [path for path in sorted(reference_dir.glob("*")) if path.is_file()]
    columns = st.columns(3)
    for index, path in enumerate(files):
        columns[index % 3].download_button(
            f"Download {path.name}",
            path.read_bytes(),
            path.name,
            "application/octet-stream",
            key=f"public_ref_{path.name}",
            width="stretch",
        )

with tabs[3]:
    doc_tab, evidence_tab = st.tabs(["Documents", "Evidence"])
    with doc_tab:
        smart_dataframe(documents, height=500)
    with evidence_tab:
        smart_dataframe(evidence_rows, height=500)

with tabs[4]:
    project_tab, job_tab = st.tabs(["Projects", "Jobs"])
    with project_tab:
        smart_dataframe(projects, height=480)
    with job_tab:
        job_frame = pd.DataFrame(
            [
                {
                    "job_id": j.job_id,
                    "job_type": j.job_type,
                    "status": j.status,
                    "priority": j.priority,
                    "attempts": j.attempts,
                    "created_at_utc": j.created_at_utc,
                }
                for j in jobs
            ]
        )
        smart_dataframe(job_frame, height=480)

with tabs[5]:
    sample_dir = ROOT / "data" / "examples" / "demo_workspace"
    samples = [
        path
        for path in sorted(sample_dir.rglob("*"))
        if path.is_file() and path.suffix.lower() != ".png"
    ]
    smart_dataframe(
        [
            {
                "file": path.relative_to(sample_dir).as_posix(),
                "format": path.suffix.upper().lstrip("."),
                "size_kb": round(path.stat().st_size / 1024, 1),
            }
            for path in samples
        ],
        height=400,
    )
    columns = st.columns(3)
    for index, path in enumerate(samples):
        columns[index % 3].download_button(
            f"Download {path.name}",
            path.read_bytes(),
            path.name,
            "application/octet-stream",
            key=f"starter_{index}_{path.name}",
            width="stretch",
        )

with tabs[6]:
    st.write(
        "Reload operations are idempotent. They rebuild demo records, public-reference metadata and relationship indexes without marking any bundled model as scientifically validated."
    )
    confirm = st.checkbox("Reload missing demo/reference data and Quality-Hardened indexes")
    if st.button(
        "Reload workspace foundation", type="primary", disabled=not confirm, width="stretch"
    ):
        with analysis_run("Rebuilding data catalogues and relationship indexes"):
            commands = [
                [sys.executable, str(ROOT / "scripts" / "seed_demo_workspace.py")],
                [sys.executable, str(ROOT / "scripts" / "build_step32_foundation.py")],
            ]
            outputs = []
            for command in commands:
                result = subprocess.run(
                    command, cwd=ROOT, capture_output=True, text=True, timeout=900
                )
                if result.returncode:
                    raise RuntimeError(result.stderr or result.stdout or "Reload failed")
                outputs.append(result.stdout.strip())
        st.success("Workspace foundation refreshed.")
        st.code("\n".join(outputs))
        st.rerun()
    st.code("BUILD_STEP33_FOUNDATION_WINDOWS.bat", language=None)

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='demo_data_hub', title='Demo Data Hub', category='Start')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
