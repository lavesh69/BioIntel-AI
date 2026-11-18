from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from biointel import __version__
from biointel.module_runtime_v207.core import (
    PROTECTED_PAGE_PATHS,
    TARGET_CATEGORIES,
    audit_tabular_dataset,
    build_diagnostic_bundle,
    profile_module_source,
)
from biointel.ui.runtime_guard import runtime_error_reports, write_runtime_error
from biointel.ui.workflow import read_uploaded_table, render_upload_preflight

_AUDIT_KEY_PREFIX = "_biointel_step207_data_audit_"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _upload_profiles_for_page(page_key: str) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for key, value in st.session_state.items():
        text = str(key).lower()
        if "upload_profile" not in text:
            continue
        if isinstance(value, dict):
            profiles.append(dict(value))
        elif isinstance(value, list):
            profiles.extend(dict(item) for item in value if isinstance(item, dict))
    return profiles[-50:]


def _reset_transient_module_state(page_key: str) -> int:
    tokens = {page_key.lower(), page_key.lower().replace("_", "")}
    hints = ("result", "output", "analysis", "frame", "preview", "upload", "error", "manifest", "audit")
    removed = 0
    for key in list(st.session_state.keys()):
        lowered = str(key).lower()
        if lowered.startswith(("ui_", "nav_", "auth_", "privacy_")):
            continue
        related = any(token and token in lowered.replace("_", "") for token in tokens)
        if related or (lowered.startswith("step207_") and any(hint in lowered for hint in hints)):
            try:
                del st.session_state[key]
                removed += 1
            except KeyError:
                pass
    return removed


def _render_data_audit(page_key: str, category: str) -> dict[str, Any] | None:
    audit_key = f"{_AUDIT_KEY_PREFIX}{page_key}"
    uploaded = st.file_uploader(
        "Optional CSV/TSV readiness audit",
        type=["csv", "tsv", "txt"],
        key=f"step207_audit_upload_{page_key}",
        help="Runs local quality checks only. It does not replace the module's scientific workflow.",
    )
    if uploaded is not None:
        render_upload_preflight(
            uploaded,
            key=f"step207_audit_preflight_{page_key}",
            allowed_extensions=["csv", "tsv", "txt"],
            soft_limit_mb=100,
            hard_limit_mb=1024,
            module_key=f"step207_{page_key}",
        )
        if st.button("Run data-readiness audit", key=f"step207_run_audit_{page_key}", width="stretch"):
            try:
                frame = read_uploaded_table(uploaded)
                st.session_state[audit_key] = audit_tabular_dataset(frame, category)
            except Exception as exc:
                error_id, _ = write_runtime_error(f"module_runtime_v209.data_audit.{page_key}", exc)
                st.error(f"Data-readiness audit stopped safely · {error_id}")
                st.caption("No uploaded rows were included in the error report. Check the file delimiter, headers and numeric columns, then retry.")
    audit = st.session_state.get(audit_key)
    if not isinstance(audit, dict):
        return None
    summary = audit.get("summary", {})
    c1, c2 = st.columns(2)
    c1.metric("Readiness", f"{float(summary.get('readiness_score_internal', 0.0)):.1f}/10")
    c2.metric("Blocking checks", int(summary.get("blocking_checks", 0)))
    warnings = list(audit.get("warnings", []))
    if warnings:
        for warning in warnings[:4]:
            st.warning(str(warning))
        if len(warnings) > 4:
            st.caption(f"{len(warnings) - 4} additional findings are available in the exported diagnostic bundle.")
    checks = audit.get("category_checks")
    if isinstance(checks, pd.DataFrame) and not checks.empty:
        st.dataframe(checks, hide_index=True, width="stretch", height=min(260, 38 + 35 * len(checks)))
    return audit


def render_module_runtime_sidebar(
    *,
    page_key: str | None,
    page_path: str | None,
    title: str | None,
    category: str | None,
) -> None:
    """Render shared stability, provenance and data-readiness tools for target modules.

    Protected modules are explicitly excluded so their functionality and UI remain
    unchanged under the project handover contract.
    """

    if not page_key or not page_path or not title or category not in TARGET_CATEGORIES:
        return
    if page_path in PROTECTED_PAGE_PATHS:
        return

    # Step210 BioIntel Live Workspace presence. Protected pages are excluded above.
    live_workspace_allowed = True
    try:
        from biointel.live_workspace_v210.ui import render_live_workspace_sidebar

        live_workspace_allowed = render_live_workspace_sidebar(page_key, title, category)
    except Exception as exc:
        write_runtime_error(f"module_runtime_v210.live_workspace.{page_key}", exc)
    if live_workspace_allowed is False:
        st.error("This module is restricted by the active BioIntel Live Workspace.")
        st.caption("Switch workspace or ask an Owner/Admin to update Member access.")
        st.stop()

    # Step209 shared professional layer. Both helpers are fail-isolated so an
    # optional online source or generated demo can never block the module.
    try:
        from biointel.scientific_resources_v209.ui import render_scientific_resources_sidebar

        render_scientific_resources_sidebar(page_key, title, category)
    except Exception as exc:
        write_runtime_error(f"module_runtime_v209.scientific_resources.{page_key}", exc)
    try:
        from biointel.demo_coverage_v209.ui import render_generated_demo_sidebar

        render_generated_demo_sidebar(_project_root(), page_key, title, category)
    except Exception as exc:
        write_runtime_error(f"module_runtime_v209.demo_bundle.{page_key}", exc)

    try:
        profile = profile_module_source(
            _project_root(),
            page_key=page_key,
            title=title,
            category=category,
            page_path=page_path,
        )
    except (OSError, ValueError) as exc:
        with st.sidebar.expander("Module stability", expanded=False):
            st.warning(f"Source profile unavailable: {exc}")
        return

    with st.sidebar.expander("Module stability & data QC", expanded=False):
        st.caption("Step209 · Local-first reliability, demo and evidence layer")
        c1, c2 = st.columns(2)
        c1.metric("Source checks", f"{profile.quality_score:.1f}/10")
        c2.metric("Source hash", profile.source_sha256[:8])
        status_rows = pd.DataFrame(
            [
                ["Upload preflight", "Ready" if (not profile.has_upload or profile.has_upload_preflight) else "Review"],
                ["Scientific boundary", "Ready" if profile.has_scientific_boundary else "Review"],
                ["Calculated visual", "Ready" if profile.has_visual_output else "Review"],
                ["Export/report", "Ready" if profile.has_download_export else "Review"],
                ["Progress/error state", "Ready" if profile.has_workflow_status else "Review"],
            ],
            columns=["Control", "Status"],
        )
        st.dataframe(status_rows, hide_index=True, width="stretch", height=212)
        if profile.findings:
            with st.popover("Review source findings", width="stretch"):
                for finding in profile.findings:
                    st.markdown(f"- {finding}")

        audit = _render_data_audit(page_key, category)
        errors = runtime_error_reports(limit=50)
        relevant_errors = [
            item
            for item in errors
            if page_key.lower() in str(item.get("context", "")).lower()
            or Path(page_path).stem.lower() in str(item.get("context", "")).lower()
        ]
        uploads = _upload_profiles_for_page(page_key)
        bundle = build_diagnostic_bundle(
            profile,
            release=__version__,
            runtime_errors=relevant_errors,
            upload_profiles=uploads,
            data_audit=audit,
        )
        st.download_button(
            "Download sanitized module diagnostics",
            data=bundle,
            file_name=f"BioIntel-{page_key}-Step209-diagnostics.zip",
            mime="application/zip",
            key=f"step207_diag_{page_key}",
            width="stretch",
        )
        st.caption(
            "Diagnostics contain hashes, checks and error metadata only. Uploaded rows and project datasets are excluded."
        )
        confirm = st.checkbox("Enable module-session reset", key=f"step207_reset_confirm_{page_key}")
        if st.button(
            "Reset transient state",
            key=f"step207_reset_{page_key}",
            disabled=not confirm,
            width="stretch",
        ):
            removed = _reset_transient_module_state(page_key)
            st.success(f"Cleared {removed} transient session item(s). Project files were not changed.")
            st.rerun()


__all__ = ["render_module_runtime_sidebar"]
