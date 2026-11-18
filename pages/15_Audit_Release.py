from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.quality.model_audit import audit_model_directory
from biointel.reports.release_bundle import build_model_release_bundle
from biointel.training.model_artifact import (
    discover_compatible_model_artifacts,
    load_model_artifact_cached,
)
from biointel.ui.brand import branded_model_label_from_sidecar
from biointel.ui.theme import apply_theme, hero
from biointel.ui.workflow import analysis_run
from biointel.utils.audit_log import read_audit_events

st.set_page_config(page_title="Audit & Release · BioIntel AI", page_icon="📦", layout="wide")
apply_theme()
hero(
    "📦 Audit Log & Model Release",
    "Audit and release work now runs on demand instead of reopening every model on each page rerun.",
    eyebrow="Step 97 · Responsive model governance",
)

events = read_audit_events(ROOT / "reports" / "audit.jsonl", 2000)
if events:
    rows = []
    for event in events:
        row = {
            "timestamp_utc": event.get("timestamp_utc"),
            "event": event.get("event"),
            "status": event.get("status"),
        }
        if isinstance(event.get("fields"), dict):
            row.update(event["fields"])
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), width="stretch", height=330)
else:
    st.info("No audit events yet.")

models, incompatible_models = discover_compatible_model_artifacts(ROOT / "models")
if incompatible_models:
    st.caption(f"{len(incompatible_models)} non-BioIntel or incompatible artifact(s) are excluded.")
if not models:
    st.warning("No compatible BioIntel model artifacts are available.")
    st.stop()

selected = st.selectbox(
    "Model",
    models,
    format_func=lambda path: branded_model_label_from_sidecar(path, {}),
)
controls = st.columns(2)
run_audit = controls[0].button("Run complete model-directory audit", width="stretch")
build_bundle = controls[1].button("Build selected release bundle", type="primary", width="stretch")

if run_audit:
    try:
        with analysis_run("Auditing trusted model artifacts") as run:
            run.stage("Inspecting model envelopes and metadata", progress=0.3)
            model_audit = audit_model_directory(ROOT / "models")
            run.stage("Preparing governance summary", progress=0.9)
        st.session_state["model_directory_audit"] = model_audit
    except Exception as exc:
        st.error(f"Model directory audit could not complete: {exc}")

model_audit = st.session_state.get("model_directory_audit")
if model_audit:
    st.markdown("#### Latest model-directory audit")
    st.dataframe(pd.DataFrame(model_audit.get("models", [])), width="stretch", height=380)

if build_bundle:
    try:
        with analysis_run("Building the selected model release bundle") as run:
            run.stage("Loading verified model envelope", progress=0.25)
            artifact = load_model_artifact_cached(selected, trusted_root=ROOT / "models")
            run.stage("Writing model card, metadata and checksums", progress=0.65)
            bundle = build_model_release_bundle(artifact, selected)
            digest = hashlib.sha256(bundle).hexdigest()
        st.session_state["selected_release_bundle"] = bundle
        st.session_state["selected_release_bundle_name"] = f"{selected.stem}_release.zip"
        st.session_state["selected_release_bundle_digest"] = digest
    except Exception as exc:
        st.error(f"Release bundle could not be built: {exc}")

bundle = st.session_state.get("selected_release_bundle")
if bundle:
    st.code("Bundle SHA-256: " + str(st.session_state.get("selected_release_bundle_digest", "")))
    st.download_button(
        "Download release ZIP",
        bundle,
        str(st.session_state.get("selected_release_bundle_name", "model_release.zip")),
        "application/zip",
        width="stretch",
    )

st.code("python -m biointel --help", language="powershell")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
