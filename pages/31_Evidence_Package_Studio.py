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

from biointel.governance.reproducibility import (
    build_project_evidence_package,
    build_project_manifest,
    build_project_report_html,
    inspect_project_evidence_package,
)
from biointel.portfolio.project_exchange import (
    project_bundle_json,
)
from biointel.portfolio.project_registry import list_projects
from biointel.ui.components import smart_json
from biointel.ui.phase108_visuals import render_phase108_visual_suite  # noqa: E402
from biointel.ui.theme import (
    apply_theme,
    badge,
    executive_kpis,
    hero,
    professional_strip,
    section_title,
)
from biointel.ui.workflow import render_upload_preflight

REGISTRY = ROOT / "reports" / "projects.sqlite3"


@st.cache_data(ttl=120, show_spinner=False)
def _cached_project_manifest(root_text: str, project_id: str):
    return build_project_manifest(root_text, project_id)


st.set_page_config(
    page_title="Evidence Package Studio · BioIntel AI",
    page_icon="📦",
    layout="wide",
)

apply_theme()

hero(
    "Build a controlled, checksum-verified project handoff package.",
    (
        "Combine project metadata, governance controls, lineage, environment "
        "versions, audit integrity and optional model files into one portable ZIP."
    ),
    eyebrow="Quality-Hardened · Evidence Package Studio",
    chips=[
        "SHA-256 manifest",
        "Printable report",
        "Optional model files",
        "Portable handoff",
    ],
)

projects = list_projects(REGISTRY, include_archived=True)
if not projects:
    st.info("Create a project before generating an evidence package.")
    st.stop()

selected_id = st.selectbox(
    "Project",
    [project.project_id for project in projects],
    format_func=lambda project_id: next(
        (
            f"{project.project_code} · {project.name}"
            for project in projects
            if project.project_id == project_id
        ),
        project_id,
    ),
)
selected = next(project for project in projects if project.project_id == selected_id)

try:
    manifest = _cached_project_manifest(str(ROOT), selected_id)
except Exception as exc:
    st.error(f"Could not build project manifest: {exc}")
    st.stop()

readiness = manifest["readiness"]
if readiness["percent"] >= 90:
    badge("● Release-ready evidence package", "success")
elif readiness["percent"] >= 75:
    badge("● Validation-ready evidence package", "warning")
else:
    badge("● Evidence package has readiness gaps", "warning")

professional_strip(
    f"{selected.project_code} · {selected.name}",
    (
        f"Readiness {readiness['percent']}% · "
        f"{len(manifest['governance']['milestones'])} milestone(s) · "
        f"{len(manifest['governance']['decisions'])} decision(s)"
    ),
)

executive_kpis(
    [
        (
            "Readiness",
            f"{readiness['percent']}%",
            readiness["label"],
        ),
        (
            "Lineage nodes",
            str(len(manifest["lineage"]["nodes"])),
            "Project, dataset, model and governance evidence",
        ),
        (
            "Audit integrity",
            ("Verified" if manifest["audit_integrity"]["valid"] else "Failed"),
            (f"{manifest['audit_integrity']['chained_events']} chained event(s)"),
        ),
        (
            "Experiments",
            str(len(manifest["matching_experiments"])),
            "Matching dataset or model evidence",
        ),
    ]
)

evidence_package_view = st.radio(
    "Evidence package view",
    ["Build package", "Manifest preview", "Verify package"],
    horizontal=True,
    key="evidence_package_view",
    label_visibility="collapsed",
)

if evidence_package_view == "Build package":
    section_title("Package controls", "⚙️")
    include_model_files = st.toggle(
        "Include linked model artifact and sidecars",
        value=False,
        help=(
            "Only trusted local model files are included. This can significantly increase ZIP size."
        ),
    )
    st.warning(
        "Serialized model files should be shared only with trusted recipients. "
        "Recipients must load them in a trusted local environment."
    )

    package_signature = (selected_id, bool(include_model_files))
    if st.button(
        "Prepare evidence package",
        type="primary",
        width="stretch",
        key="prepare_evidence_package",
    ):
        try:
            with st.spinner("Building and checksum-verifying the evidence package…"):
                package_bytes = build_project_evidence_package(
                    ROOT,
                    selected_id,
                    include_model_files=include_model_files,
                )
                package_summary = inspect_project_evidence_package(package_bytes)
        except Exception as exc:
            st.session_state.pop("prepared_evidence_package", None)
            st.error(f"Package generation failed: {exc}")
        else:
            st.session_state["prepared_evidence_package"] = {
                "signature": package_signature,
                "bytes": package_bytes,
                "summary": package_summary,
            }

    prepared = st.session_state.get("prepared_evidence_package")
    if prepared and prepared.get("signature") == package_signature:
        package_bytes = prepared["bytes"]
        package_summary = prepared["summary"]
        package_columns = st.columns(4)
        package_columns[0].metric("Files", package_summary.file_count)
        package_columns[1].metric(
            "Uncompressed",
            f"{package_summary.total_bytes / 1024:.1f} KB",
        )
        package_columns[2].metric(
            "Model files",
            "Included" if package_summary.included_model_files else "Metadata only",
        )
        package_columns[3].metric("Readiness score", package_summary.readiness_score)

        report_html = build_project_report_html(manifest)
        safe_code = "".join(
            character if character.isalnum() or character in "-_" else "_"
            for character in selected.project_code
        )
        download_columns = st.columns(4)
        download_columns[0].download_button(
            "Download evidence ZIP",
            package_bytes,
            f"{safe_code}_evidence_package.zip",
            "application/zip",
            type="primary",
            width="stretch",
        )
        download_columns[1].download_button(
            "Download project report",
            report_html,
            f"{safe_code}_evidence_report.html",
            "text/html",
            width="stretch",
        )
        download_columns[2].download_button(
            "Download manifest JSON",
            json.dumps(manifest, indent=2, default=str),
            f"{safe_code}_manifest.json",
            "application/json",
            width="stretch",
        )
        download_columns[3].download_button(
            "Download project exchange JSON",
            project_bundle_json(REGISTRY, selected_id),
            f"{safe_code}_project_bundle.json",
            "application/json",
            width="stretch",
        )
        with st.expander("Package file list"):
            st.dataframe(
                pd.DataFrame({"File": package_summary.files}),
                width="stretch",
                hide_index=True,
            )
    elif prepared:
        st.info("Project or package options changed. Prepare a new package before downloading.")
    else:
        st.caption("Package generation starts only when requested, keeping navigation responsive.")

if evidence_package_view == "Manifest preview":
    section_title("Controlled project manifest", "▣")
    smart_json(manifest)
    readiness_frame = pd.DataFrame(readiness["criteria"])
    st.dataframe(
        readiness_frame,
        width="stretch",
        hide_index=True,
        column_config={
            "earned": st.column_config.NumberColumn(
                "Earned",
            ),
            "maximum": st.column_config.NumberColumn(
                "Maximum",
            ),
        },
    )

if evidence_package_view == "Verify package":
    section_title("Verify an evidence package", "✓")
    uploaded = st.file_uploader(
        "Upload BioIntel project evidence ZIP",
        type=["zip"],
        key="evidence_package_verifier",
    )
    render_upload_preflight(
        uploaded,
        key="evidence_package",
        allowed_extensions=["zip"],
        soft_limit_mb=100,
        hard_limit_mb=500,
    )
    if uploaded is None:
        st.info("Upload a package to validate its format, safe paths and SHA-256 checksums.")
    elif uploaded.size > 500 * 1024 * 1024:
        st.error("Package exceeds the 500 MB safety limit.")
    else:
        try:
            verified = inspect_project_evidence_package(uploaded.getvalue())
        except Exception as exc:
            st.error(f"Package verification failed: {exc}")
        else:
            st.success("Package integrity verified successfully.")
            smart_json(verified.__dict__)

# Step 108 Phase 1+2 decision visual workspace
render_phase108_visual_suite("evidence_package", ROOT, context=locals())

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
