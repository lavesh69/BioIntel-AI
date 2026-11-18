from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.ui.theme import apply_theme, hero
from biointel.ui.workflow import render_upload_preflight
from biointel.utils.workspace_backup import (
    create_workspace_backup,
    inspect_workspace_backup,
    restore_workspace_backup,
)

st.set_page_config(
    page_title="Workspace Backup & Restore · BioIntel AI",
    page_icon="💾",
    layout="wide",
)

apply_theme()
hero(
    "💾 Workspace Backup & Restore",
    "Guided scientific analysis with validated inputs, clear status, professional results and export-ready outputs.",
    eyebrow="BioIntel AI · Scientific Intelligence for Life Sciences",
)
st.caption(
    "Back up user models, reports, history and optional offline cache. "
    "No login or cloud account is used."
)

backup_tab, restore_tab = st.tabs(["Create backup", "Restore backup"])

with backup_tab:
    include_demo = st.checkbox(
        "Include bundled synthetic demo models",
        value=False,
        help=("Normally unnecessary because demo models are included with every project ZIP."),
    )
    include_cache = st.checkbox(
        "Include external database offline cache",
        value=False,
    )

    backup_signature = (bool(include_demo), bool(include_cache))
    if st.button(
        "Prepare workspace backup",
        type="primary",
        width="stretch",
        key="prepare_workspace_backup",
    ):
        try:
            with st.spinner("Preparing and validating workspace backup…"):
                backup_bytes = create_workspace_backup(
                    ROOT,
                    include_demo_models=include_demo,
                    include_cache=include_cache,
                )
                summary = inspect_workspace_backup(backup_bytes)
        except Exception as exc:
            st.session_state.pop("workspace_backup_prepared", None)
            st.error(f"Backup could not be prepared: {exc}")
        else:
            st.session_state["workspace_backup_prepared"] = {
                "signature": backup_signature,
                "bytes": backup_bytes,
                "summary": summary,
            }

    prepared = st.session_state.get("workspace_backup_prepared")
    if prepared and prepared.get("signature") == backup_signature:
        backup_bytes = prepared["bytes"]
        summary = prepared["summary"]
        columns = st.columns(3)
        columns[0].metric("Files", summary.file_count)
        columns[1].metric(
            "Uncompressed size",
            f"{summary.total_bytes / 1024:.1f} KB",
        )
        columns[2].metric("ZIP size", f"{len(backup_bytes) / 1024:.1f} KB")
        st.download_button(
            "Download workspace backup",
            backup_bytes,
            "BioIntel-AI-Workspace-Backup.zip",
            "application/zip",
            type="primary",
            width="stretch",
        )
        if summary.file_count == 0:
            st.info("The backup is valid but currently contains no user-generated workspace files.")
    elif prepared:
        st.info("Backup options changed. Prepare a new backup before downloading.")
    else:
        st.caption("Backup creation starts only when requested, keeping page navigation fast.")

with restore_tab:
    uploaded = st.file_uploader(
        "Select a BioIntel workspace backup ZIP",
        type=["zip"],
        key="workspace_restore",
    )
    render_upload_preflight(
        uploaded,
        key="workspace_restore",
        allowed_extensions=["zip"],
        soft_limit_mb=100,
        hard_limit_mb=500,
    )

    if uploaded is None:
        st.info("Upload a backup created by this Quality-Hardened workspace tool.")
    else:
        backup_content = uploaded.getvalue()
        try:
            backup_summary = inspect_workspace_backup(backup_content)
        except Exception as exc:
            st.error(f"Backup validation failed: {exc}")
            st.stop()

        columns = st.columns(3)
        columns[0].metric(
            "Files",
            backup_summary.file_count,
        )
        columns[1].metric(
            "Uncompressed size",
            f"{backup_summary.total_bytes / 1024:.1f} KB",
        )
        columns[2].metric(
            "Created",
            backup_summary.created_at_utc,
        )

        with st.expander("Backup file list"):
            st.code(
                "\n".join(backup_summary.files) or "No workspace files",
                language=None,
            )

        overwrite = st.checkbox(
            "Overwrite existing files with the same name",
            value=False,
        )
        restore_demo = st.checkbox(
            "Allow bundled demo model files to be restored",
            value=False,
        )
        confirm = st.checkbox("I have reviewed the backup summary and want to restore it.")

        if st.button(
            "Restore validated backup",
            type="primary",
            disabled=not confirm,
        ):
            try:
                result = restore_workspace_backup(
                    ROOT,
                    backup_content,
                    overwrite=overwrite,
                    allow_demo_models=restore_demo,
                )
            except Exception as exc:
                st.error(f"Restore failed: {exc}")
            else:
                st.success(
                    f"Restored {result['restored_count']} file(s); "
                    f"skipped {result['skipped_count']} file(s)."
                )
                if result["restored"]:
                    st.write("Restored")
                    st.code(
                        "\n".join(result["restored"]),
                        language=None,
                    )
                if result["skipped"]:
                    st.write("Skipped")
                    st.code(
                        "\n".join(result["skipped"]),
                        language=None,
                    )

st.warning(
    "Workspace backups can contain model files and local reports. "
    "Keep them private and restore only backups you created or trust."
)

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
