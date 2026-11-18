from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import json

import pandas as pd
import streamlit as st

from biointel import __version__
from biointel.step127 import ALL_MODULE_SPECS, assess_module, format_support, release_manifest
from biointel.step127.ui import render_step127_upgrade_panel
from biointel.ui.theme import apply_theme, hero
from biointel.ui.components import smart_json

st.set_page_config(page_title="Scientific Depth Command Center · BioIntel AI", page_icon="🧭", layout="wide")
apply_theme()
hero(
    "Scientific Depth Command Center",
    "Execution tiers, protected tool plans, native-format readiness, statistical safeguards and evidence boundaries across Bioinformatics, Discovery and Lab Analytics.",
    eyebrow=f"BioIntel AI {__version__} · Step 127",
    chips=["33 core modules", "Tier A/B/C", "Protected plans", "Native formats", "Run provenance"],
)

domain = st.segmented_control(
    "Domain",
    ["All", "Bioinformatics", "Discovery", "Lab Analytics"],
    default="All",
    key="step127_domain",
)
selected_specs = [spec for spec in ALL_MODULE_SPECS if domain == "All" or spec.domain == domain]
rows = []
for spec in selected_specs:
    assessment = assess_module(spec.key)
    rows.append({
        "Module": spec.title,
        "Domain": spec.domain,
        "Tier": assessment.tier,
        "Readiness %": round(assessment.execution_readiness * 100, 1),
        "Tools": f"{assessment.tools_available}/{assessment.tools_required}",
        "New capabilities": len(spec.features_added),
        "Locked source": spec.locked_source,
        "Page": spec.page_path,
    })
frame = pd.DataFrame(rows).sort_values(["Domain", "Readiness %", "Module"], ascending=[True, False, True])
st.dataframe(frame, width="stretch", hide_index=True)

summary = st.columns(4)
summary[0].metric("Core modules", len(selected_specs))
summary[1].metric("Tier A", int((frame["Tier"] == "A").sum()))
summary[2].metric("Tier B", int((frame["Tier"] == "B").sum()))
summary[3].metric("Capabilities standardized", int(frame["New capabilities"].sum()))

module_key = st.selectbox(
    "Inspect module",
    [spec.key for spec in selected_specs],
    format_func=lambda key: next(spec.title for spec in selected_specs if spec.key == key),
)
render_step127_upgrade_panel(module_key, expanded=True)

with st.expander("Native-format quick inspector", expanded=False):
    filename = st.text_input("Scientific filename", placeholder="sample.h5ad, variants.bcf, reads.fastq.gz, spectra.mzML")
    if filename.strip():
        smart_json(format_support(filename.strip()), title="Native format support", key="step127_native_format_support")

manifest_bundle = {
    "schema": "biointel.step127.domain-depth-bundle.v1",
    "version": __version__,
    "modules": [release_manifest(spec.key) for spec in selected_specs],
}
st.download_button(
    "Download domain-depth manifest",
    json.dumps(manifest_bundle, indent=2, sort_keys=True, default=str),
    "biointel_step127_scientific_depth_manifest.json",
    "application/json",
    width="stretch",
)

st.info(
    "Tier A means the configured executable pipeline is locally available. It does not mean clinical, regulatory, wet-lab or independent scientific validation has been completed."
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
