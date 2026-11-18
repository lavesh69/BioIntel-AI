from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.scientific.validation_depth import build_step40_validation_readiness  # noqa: E402
from biointel.ui.components import scientific_boundary_banner, smart_dataframe  # noqa: E402
from biointel.ui.phase108_visuals import render_phase108_visual_suite  # noqa: E402
from biointel.ui.theme import apply_theme, badge, hero, insight_callout, section_title  # noqa: E402

st.set_page_config(page_title="DTI Validation Evidence Center · BioIntel AI", page_icon="🧪", layout="wide")
apply_theme()

@st.cache_data(ttl=30, show_spinner=False)
def _load(root: str):
    return build_step40_validation_readiness(Path(root))

report = _load(str(ROOT))
summary = report["summary"]
hero(
    "DTI Validation & Wet-Lab Evidence Center",
    "Hash-verified external validation, prediction locking, independent review, laboratory attestations and multi-site evidence gates.",
    eyebrow="Evidence cannot be manufactured",
    chips=[
        f"Implementation {report['implementation_average']:.1f}/10",
        f"Actual evidence {report['evidence_average']:.1f}/10",
        f"{summary['release_eligible_studies']} release-eligible studies",
        f"{summary['verified_provider_releases']} verified provider releases",
    ],
)

badge("● Validation controls complete" if report["implementation_average"] == 10 else "● Validation controls incomplete", "success" if report["implementation_average"] == 10 else "warning")
try:
    st.page_link("pages/75_Real_World_Operations_Evidence.py", label="Open Maximum Verifiable Evidence", icon="🏭")
except (KeyError, RuntimeError):
    st.info("🏭 Open Maximum Verifiable Evidence from the sidebar.")
scientific_boundary_banner(
    source_kind="validation_evidence",
    release_eligible=False,
    message=(
        "Framework readiness and completed evidence are separate. Public-reference replays, placeholder hashes and self-attestation "
        "cannot count as independent wet-lab or multi-site validation."
    ),
)

cols = st.columns(6)
cols[0].metric("Studies", summary["studies"])
cols[1].metric("External DTI", summary["completed_external_dti"])
cols[2].metric("Blinded prospective", summary["completed_blinded_prospective"])
cols[3].metric("Wet-lab", summary["completed_wetlab"])
cols[4].metric("Independent sites", summary["independent_sites"])
cols[5].metric("Multi-site", summary["completed_multisite"])

matrix_tab, rules_tab, evidence_tab, import_tab = st.tabs(["Readiness matrix", "Qualification rules", "Evidence summary", "Import workflow"])

with matrix_tab:
    frame = pd.DataFrame(report["capabilities"])
    chart = px.bar(
        frame.sort_values("evidence_score"), x=["implementation_score", "evidence_score"], y="label",
        orientation="h", barmode="group", range_x=[0, 10],
        labels={"value": "Score", "label": "Area", "variable": "Score type"},
    )
    chart.update_layout(height=max(760, len(frame) * 38), legend_title_text="")
    st.plotly_chart(chart, width="stretch")
    display = frame.rename(columns={
        "label": "Area", "implementation_score": "Implementation", "evidence_score": "Actual evidence",
        "status": "Status", "controls": "Controls", "blockers": "Missing controls", "boundary": "Boundary",
    })
    display["Controls"] = display["Controls"].apply(lambda values: " • ".join(values))
    display["Missing controls"] = display["Missing controls"].apply(lambda values: " • ".join(values))
    smart_dataframe(
        display[["Area", "Implementation", "Actual evidence", "Status", "Controls", "Missing controls", "Boundary"]],
        height=720,
        columns={
            "Implementation": st.column_config.ProgressColumn("Implementation", min_value=0, max_value=10, format="%.1f"),
            "Actual evidence": st.column_config.ProgressColumn("Actual evidence", min_value=0, max_value=10, format="%.1f"),
        },
    )

with rules_tab:
    section_title("Hard evidence gates", "🔐")
    smart_dataframe(pd.DataFrame([
        {"Claim": "Independent external DTI", "Minimum evidence": "Distinct source/training providers, real SHA-256 artifacts, ≥100 outcomes, independent signed review"},
        {"Claim": "Blinded prospective", "Minimum evidence": "Preregistered protocol, predictions locked before outcome import, blind codes, ≥100 pairs"},
        {"Claim": "Wet-lab evidence", "Minimum evidence": "Raw outcomes, site attestation, protocol/reagent/QC traceability, non-analytical evidence class"},
        {"Claim": "Independent lab replication", "Minimum evidence": "At least two sponsor-independent laboratories with approved signed review"},
        {"Claim": "Multi-site validation", "Minimum evidence": "At least three independent organizations across two countries plus site-effect analysis"},
    ]), height=360)
    insight_callout("Anti-inflation control", "Placeholder hashes, deterministic demo records and public-reference replays are automatically blocked from wet-lab and independent-site claims.", "warning")

with evidence_tab:
    st.code(json.dumps(summary, indent=2, sort_keys=True), language="json")
    if report["integrity"]["ok"]:
        st.success("Validation evidence database and hash chain verified.")
    else:
        st.error("Validation evidence integrity failure.")
        st.code(json.dumps(report["integrity"], indent=2, sort_keys=True), language="json")

with import_tab:
    st.code(
        "python scripts/register_step40_validation_study.py study_manifest.json\n"
        "python scripts/qualify_step40_validation.py",
        language="bash",
    )
    insight_callout(
        "External work required",
        "The platform is ready to ingest independently generated laboratory and multi-site outcomes. Actual scores rise only after authentic artifacts and signed reviews pass the gates.",
        "info",
    )

# Step 108 Phase 1+2 decision visual workspace
render_phase108_visual_suite("dti_validation", ROOT, context=locals())

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
