from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from .core import build_demo_bundle


@st.cache_data(show_spinner=False, max_entries=256)
def _cached_bundle(page_key: str, title: str, category: str):
    return build_demo_bundle(page_key, title, category)


def _has_static_starter_kit(project_root: Path, page_key: str) -> bool:
    catalog_path = project_root / "data" / "module_starter_kits" / "catalog.json"
    if not catalog_path.is_file():
        return False
    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    kits = payload.get("kits", {}) if isinstance(payload, dict) else {}
    return isinstance(kits, dict) and isinstance(kits.get(page_key), dict)


def render_generated_demo_sidebar(project_root: Path, page_key: str, title: str, category: str) -> None:
    if _has_static_starter_kit(project_root, page_key):
        return
    try:
        bundle = _cached_bundle(page_key, title, category)
    except Exception as exc:
        with st.sidebar.expander("Synthetic demo input", expanded=False):
            st.warning(f"Demo input could not be prepared: {type(exc).__name__}: {exc}")
        return
    with st.sidebar.expander("Synthetic demo input", expanded=False):
        st.caption(
            "This module did not have a dedicated static starter kit, so BioIntel prepared a small deterministic input bundle for local workflow testing."
        )
        st.markdown(f"**Input family:** `{bundle.family}`")
        st.download_button(
            "Download labelled demo bundle",
            data=bundle.content,
            file_name=bundle.archive_name,
            mime="application/zip",
            key=f"v209_demo_bundle_{page_key}",
            width="stretch",
        )
        with st.popover("Bundle contents", width="stretch"):
            for name in bundle.file_names:
                st.markdown(f"- `{name}`")
            st.code(f"SHA-256: {bundle.sha256}", language=None)
        st.info("Synthetic input only—not a scientific result, patient dataset, clinical validation or online evidence.")


def render_generated_demo_panel(page_key: str, title: str, category: str, *, expanded: bool = False) -> None:
    try:
        bundle = _cached_bundle(page_key, title, category)
    except Exception as exc:
        with st.expander("Labelled module demo", expanded=expanded):
            st.warning(f"Demo input could not be prepared: {type(exc).__name__}: {exc}")
        return
    with st.expander("Labelled module demo input", expanded=expanded):
        st.caption("Deterministic synthetic inputs for testing this module's upload, validation and reporting flow.")
        st.download_button(
            "Download module demo bundle",
            data=bundle.content,
            file_name=bundle.archive_name,
            mime="application/zip",
            key=f"v209_demo_panel_{page_key}",
            width="stretch",
        )
        st.caption(f"Family: {bundle.family} · SHA-256: {bundle.sha256[:16]}…")
        st.info("Synthetic input only. It is not a patient dataset, experimental result, clinical validation or online evidence.")


__all__ = ["render_generated_demo_sidebar", "render_generated_demo_panel"]
