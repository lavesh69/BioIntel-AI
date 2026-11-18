from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.model_qualification.package import qualify_model_package
from biointel.ui.components import metric_cards, smart_json
from biointel.ui.theme import apply_theme, badge, hero, insight_callout
from biointel.ui.workflow import render_upload_preflight

st.set_page_config(page_title="External Model Qualification · BioIntel AI", page_icon="🧾", layout="wide")
apply_theme()
hero(
    "External Scientific Model Qualification",
    "Verify imported model packages, dataset hashes, model cards, generalisation evidence and independent-validation claims before allowing scientific release.",
    eyebrow="BioIntel AI · Step 96 real-evidence intake",
    chips=["No model execution", "Hash verification", "Model cards", "External validation", "Release blockers", "Evidence score"],
)

upload = st.file_uploader("Model evidence package ZIP", type=["zip"])
render_upload_preflight(upload, key="external_model_package", allowed_extensions=["zip"], soft_limit_mb=100, hard_limit_mb=500)
require_external = st.toggle("Require independent external validation", value=True)
if upload is None:
    st.info("Upload a ZIP containing model_card.json, dataset_manifest.json, metrics.json, FILE_MANIFEST_SHA256.json and the referenced artifacts.")
else:
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as handle:
        handle.write(upload.getvalue())
        path = Path(handle.name)
    try:
        result = qualify_model_package(path, require_external_validation=require_external)
        metric_cards([
            ("Qualified", "Yes" if result.qualified else "No", None),
            ("Implementation", f"{result.implementation_score:.1f}/10", None),
            ("Evidence", f"{result.evidence_score:.1f}/10", None),
            ("Files verified", result.files_verified, None),
            ("Blockers", len(result.blockers), None),
            ("Warnings", len(result.warnings), None),
        ])
        badge("● Release-qualified package" if result.qualified else "● Scientific release blocked", "success" if result.qualified else "danger")
        left, right = st.columns(2)
        with left:
            st.subheader("Blockers")
            if result.blockers:
                for item in result.blockers:
                    st.error(item)
            else:
                st.success("No qualification blockers found.")
        with right:
            st.subheader("Warnings")
            if result.warnings:
                for item in result.warnings:
                    st.warning(item)
            else:
                st.success("No warnings found.")
        smart_json(result.model_card, key="external_model_card")
        st.download_button("Download qualification JSON", json.dumps(result.to_dict(), indent=2, default=str).encode(), "external_model_qualification.json", "application/json")
        insight_callout("Security boundary", "The qualification reader never deserializes or executes the model artifact. Passing the package check does not replace independent reproduction, wet-lab validation, peer review or regulatory assessment.", tone="info")
    except Exception as exc:
        st.exception(exc)
    finally:
        path.unlink(missing_ok=True)

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
