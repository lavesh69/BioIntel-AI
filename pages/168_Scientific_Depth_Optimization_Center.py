from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.scientific_depth import (
    MODULE_PROFILES,
    engine_status_frame,
    render_depth_upgrade_panel,
)
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe
from biointel.ui.theme import apply_theme, hero, section_title

st.set_page_config(
    page_title="Scientific Depth & Optimization · BioIntel AI",
    page_icon="🧪",
    layout="wide",
)
apply_theme()
hero(
    "Scientific Depth & Optimization Center",
    "Review real-engine readiness, reference requirements, native formats, validation gates and performance plans across upgraded modules.",
    eyebrow="BioIntel AI 15.6.0 · Excludes DTI validation and LIMS/instrument upgrades by request",
)
scientific_boundary_banner(
    source_kind="reference_only",
    release_eligible=False,
    message="Detected tools and implemented QC do not manufacture external datasets, clinical evidence, wet-lab confirmation or regulatory acceptance.",
)

rows: list[dict[str, object]] = []
for key, profile in MODULE_PROFILES.items():
    status = engine_status_frame(key)
    rows.append(
        {
            "module_key": key,
            "profile": profile.title,
            "engines_detected": int(status["available"].sum()) if not status.empty else 0,
            "engines_total": int(len(status)),
            "reference_assets": len(profile.references),
            "native_formats": len(profile.native_formats),
            "validation_gates": len(profile.validations),
        }
    )
frame = pd.DataFrame(rows).sort_values(["engines_total", "profile"], ascending=[False, True])
metric_cards(
    [
        ("Profiles", len(frame), "Upgraded scientific/operational workspaces"),
        ("Engine requirements", int(frame["engines_total"].sum()), "Explicit readiness checks"),
        ("Detected engines", int(frame["engines_detected"].sum()), "Current machine"),
        ("Validation gates", int(frame["validation_gates"].sum()), "No automatic pass"),
    ]
)
section_title("Coverage matrix", "▦")
smart_dataframe(frame, height=520, key="step114_depth_coverage")

options = {profile.title: key for key, profile in MODULE_PROFILES.items()}
selected_label = st.selectbox("Open a module depth profile", sorted(options), key="step114_depth_profile")
render_depth_upgrade_panel(
    options[selected_label],
    None,
    key_prefix="step114_depth_center",
    expanded=True,
)

st.info(
    "DTI Predictor/DTI Validation and LIMS/Instrument Integration were intentionally not upgraded in this release."
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
