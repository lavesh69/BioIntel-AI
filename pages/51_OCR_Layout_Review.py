from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.documents.history import list_ocr_corrections, list_runs, record_ocr_correction
from biointel.documents.service import load_processed_document
from biointel.ui.theme import apply_theme, hero

st.set_page_config(page_title="OCR & Layout Review · BioIntel AI", page_icon="🔎", layout="wide")
apply_theme()
hero("🔎 OCR & Layout Review", "Guided scientific analysis with validated inputs, clear status, professional results and export-ready outputs.", eyebrow="BioIntel AI · Scientific Intelligence for Life Sciences")
st.caption(
    "Review OCR confidence, page/cell provenance and numeric tokens before using extracted "
    "scientific values. Corrections are audit-tracked and never overwrite the source file."
)

HISTORY = ROOT / "reports" / "document_history.sqlite3"
runs = [run for run in list_runs(HISTORY, limit=2000) if run.status == "completed"]
if not runs:
    st.info("No completed extraction run is available.")
    st.stop()

labels = {run.run_id: f"{run.started_at_utc} · {run.source_name}" for run in runs}
run_id = st.selectbox("Extraction run", list(labels), format_func=labels.get)
processed = load_processed_document(ROOT, run_id)
extraction = processed.extraction
regions = list(extraction.regions)

left, middle, right = st.columns(3)
left.metric("Layout regions", len(regions))
ocr_regions = [region for region in regions if region.kind == "ocr_word"]
middle.metric("OCR tokens", len(ocr_regions))
low_confidence = [
    region
    for region in ocr_regions
    if region.confidence is None or region.confidence < 0.70
]
right.metric("Review-required OCR", len(low_confidence))

kind_options = ["all", *sorted({region.kind for region in regions})]
kind = st.selectbox("Region type", kind_options)
confidence_limit = st.slider("Maximum confidence to show", 0.0, 1.0, 1.0, 0.05)
filtered = [
    region
    for region in regions
    if (kind == "all" or region.kind == kind)
    and (region.confidence is None or region.confidence <= confidence_limit)
]
frame = pd.DataFrame(
    [
        {
            "Region": region.region_id,
            "Kind": region.kind,
            "Source": region.source,
            "Page": region.page_number,
            "Confidence": region.confidence,
            "Bounding box": region.bbox,
            "Text": region.text,
        }
        for region in filtered
    ]
)
st.dataframe(frame, width="stretch", hide_index=True)

if filtered:
    region_map = {region.region_id: region for region in filtered}
    selected_id = st.selectbox(
        "Region to correct",
        list(region_map),
        format_func=lambda value: f"{region_map[value].source} · {region_map[value].text[:80]}",
    )
    selected = region_map[selected_id]
    original = st.text_area("Original extracted text", selected.text, disabled=True)
    corrected = st.text_area("Corrected text", selected.text)
    reviewer = st.text_input("Reviewer")
    comment = st.text_area("Review comment")
    if st.button("Record OCR correction", type="primary"):
        try:
            correction_id = record_ocr_correction(
                HISTORY,
                run_id=run_id,
                region_id=selected.region_id,
                original_text=original,
                corrected_text=corrected,
                reviewer=reviewer,
                comment=comment,
            )
            st.success(f"Correction recorded: {correction_id}")
        except Exception as exc:
            st.error(str(exc))

st.subheader("Correction history")
st.dataframe(pd.DataFrame(list_ocr_corrections(HISTORY, run_id)), width="stretch", hide_index=True)

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='ocr_layout_review', title='OCR & Layout Review', category='Data')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
