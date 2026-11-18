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

from biointel.biotech.lab_import import INSTRUMENT_PROFILES, list_excel_sheets, read_lab_table
from biointel.ui.components import metric_cards, smart_dataframe, smart_json
from biointel.ui.theme import apply_theme, badge, hero, insight_callout
from biointel.ui.workflow import render_upload_preflight

st.set_page_config(page_title="Lab Instrument Import · BioIntel AI", page_icon="🔌", layout="wide")
apply_theme()
hero(
    "Laboratory Instrument Import Center",
    "Normalize RDML, QuantStudio, Bio-Rad CFX, Roche LightCycler, SoftMax Pro and BioTek Gen5 exports while retaining original source columns and mapping provenance.",
    eyebrow="BioIntel AI · Step 96 instrument interoperability",
    chips=["RDML", "QuantStudio", "CFX", "LightCycler", "SoftMax", "Gen5", "Metadata preserved"],
)

upload = st.file_uploader("Instrument export", type=["rdml", "csv", "tsv", "txt", "xlsx", "xlsm", "xls"])
render_upload_preflight(
    upload, key="instrument_import",
    allowed_extensions=["rdml", "csv", "tsv", "txt", "xlsx", "xlsm", "xls"],
    soft_limit_mb=100, hard_limit_mb=500,
)
if upload is None:
    st.info("Upload a supported instrument export. The detected profile and canonical source-column map will be shown before analysis.")
else:
    sheets = list_excel_sheets(upload)
    sheet = st.selectbox("Worksheet", sheets) if sheets else 0
    try:
        frame = read_lab_table(upload, sheet_name=sheet, normalize_instrument=True)
        profile = str(frame.attrs.get("instrument_profile", frame.get("instrument_format", pd.Series(["Generic table"])).iloc[0]))
        source_map = frame.attrs.get("canonical_source_columns", {})
        metric_cards([
            ("Detected format", profile, None),
            ("Rows", len(frame), None),
            ("Columns retained", len(frame.columns), None),
            ("Canonical mappings", len(source_map), None),
        ])
        badge(f"● {profile} import normalized", "success" if profile != "Generic table" else "warning")
        smart_json(source_map, key="instrument_source_map")
        smart_dataframe(frame, height=560, key="instrument_import_preview")
        st.download_button("Download normalized CSV", frame.to_csv(index=False).encode(), "normalized_instrument_export.csv", "text/csv")
        st.download_button("Download mapping JSON", json.dumps({"profile": profile, "source_columns": source_map}, indent=2).encode(), "instrument_mapping.json", "application/json")
        insight_callout("Provenance", "Original columns are retained by default. Store the raw file hash, instrument ID, software version, run date, operator, reagent lot and SOP version with the assay run record.", tone="info")
    except Exception as exc:
        st.exception(exc)

# Step 110 advanced scientific viewers
from biointel.ui.advanced_scientific_viewers import render_embedded_viewer as _render_step110_viewer

_render_step110_viewer("bioprocess_live", key_prefix="step110_109_Lab_Instrument_Import_Center_bioprocess_live")

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='lab_instrument_import', title='Lab Instrument Import Center', category='Lab Analytics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='lab_instrument_import', title='Lab Instrument Import Center', category='Lab Analytics')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
