from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.jobs.local_queue import LocalJobQueue
from biointel.step101.reports import UnifiedScientificReportBuilder
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_json
from biointel.ui.theme import apply_theme, hero, section_title

st.set_page_config(page_title="Unified Scientific Report Builder · BioIntel AI", page_icon="📦", layout="wide")
apply_theme()
hero(
    "Unified Scientific Report Builder",
    "Create one checksum-bound reproducibility package containing methods, inputs, QC, results, limitations, jobs, tool/database versions, model evidence and provenance.",
    eyebrow="BioIntel AI 10.1 · Evidence Packaging",
    chips=["PDF", "DOCX", "XLSX", "HTML", "JSON", "CSV", "Reproducibility ZIP"],
)
scientific_boundary_banner(
    source_kind="mixed",
    release_eligible=False,
    message="The bundle documents computational evidence. Independent experimental, clinical and regulatory review remains required.",
)

builder = UnifiedScientificReportBuilder(ROOT)
queue = LocalJobQueue(ROOT / "reports" / "jobs.sqlite3")
sections_available = {
    "Workspace portfolio": "workspace",
    "Background jobs and workers": "jobs",
    "Reference databases": "references",
    "Configuration provenance": "provenance",
    "Scientific limitations": "limitations",
}

section_title("Report configuration", "✎")
with st.form("step101_unified_report"):
    title = st.text_input("Report title", value="BioIntel AI Unified Scientific Report")
    reviewer = st.text_input("Reviewer/operator", value="")
    notes = st.text_area("Research notes", height=150, placeholder="Project context, intended use, QC decisions and next experimental steps.")
    selected_labels = st.multiselect("Included sections", list(sections_available), default=list(sections_available))
    mode = st.radio("Generation mode", ["Generate now", "Queue as background job"], horizontal=True)
    submitted = st.form_submit_button("Build report package", type="primary", width="stretch")

if submitted:
    sections = [sections_available[label] for label in selected_labels]
    if mode == "Queue as background job":
        record = queue.submit(
            "unified_report_generate",
            {"title": title, "reviewer": reviewer, "notes": notes, "sections": sections},
            stages=["collect", "render", "package", "finalize"],
            resources={"cpu_threads": 1, "ram_gb": 2, "gpu_required": False},
            estimated_seconds=30,
        )
        st.success(f"Report job submitted: {record.job_id}. Open Background Jobs & Performance to monitor it.")
    else:
        with st.spinner("Collecting evidence and rendering all report formats…"):
            try:
                bundle = builder.build(title=title, notes=notes, reviewer=reviewer, sections=sections)
            except Exception as exc:
                st.error(f"Report generation failed: {exc}")
            else:
                st.session_state["step101_report_bundle"] = bundle
                output = ROOT / "reports" / "generated"
                output.mkdir(parents=True, exist_ok=True)
                safe = re.sub(r"[^A-Za-z0-9_-]+", "_", title).strip("_")[:80] or "scientific_report"
                path = output / f"{safe}.zip"
                path.write_bytes(bundle.zip_bytes())
                st.session_state["step101_report_path"] = str(path.relative_to(ROOT))
                st.success(f"Unified report generated and saved to {path.relative_to(ROOT)}.")

bundle = st.session_state.get("step101_report_bundle")
if bundle is None:
    st.info("Configure and generate a report to unlock all export formats.")
    st.stop()

metric_cards(
    [
        ("Files", len(bundle.files) + 1, "Includes manifest.json"),
        ("Generated", bundle.generated_at_utc, None),
        ("Bundle size", f"{len(bundle.zip_bytes()) / 1024**2:.2f} MB", None),
        ("Saved path", st.session_state.get("step101_report_path", "Session only"), None),
    ]
)

section_title("Download complete evidence package", "⬇️")
st.download_button(
    "Download reproducibility ZIP",
    bundle.zip_bytes(),
    "biointel_unified_scientific_report.zip",
    "application/zip",
    type="primary",
    width="stretch",
)

columns = st.columns(5)
formats = [
    ("PDF", "report.pdf", "application/pdf"),
    ("DOCX", "report.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ("XLSX", "report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ("HTML", "report.html", "text/html"),
    ("JSON", "report.json", "application/json"),
]
for column, (label, filename, mime) in zip(columns, formats):
    column.download_button(f"Download {label}", bundle.files[filename], filename, mime, width="stretch")

preview, manifest = st.tabs(["HTML preview", "Manifest & hashes"])
with preview:
    st.iframe(bundle.files["report.html"].decode("utf-8", errors="replace"), height=780)
with manifest:
    smart_json(bundle.manifest, title="Checksum manifest", download_name="manifest.json")

st.caption("CSV tables are included inside the reproducibility ZIP whenever a report section contains tabular records.")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
