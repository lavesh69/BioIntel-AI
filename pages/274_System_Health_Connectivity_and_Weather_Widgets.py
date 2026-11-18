from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.ui.connectivity_widgets_ui import (
    render_api_health_matrix_widget,
    render_gpu_and_infrastructure_widgets,
    render_internet_status_widget,
)
from biointel.ui.weather_widget_ui import render_global_weather_widget
from biointel.ui.theme import apply_theme, hero

st.set_page_config(
    page_title="System Health, Connectivity & Weather · BioIntel AI",
    page_icon=":material/sensors:",
    layout="wide",
)
apply_theme()
hero(
    "System Health, Connectivity & Weather",
    "Measure real provider and infrastructure state, then explore worldwide provider-backed weather and environment data.",
    eyebrow="Connectivity & Environment",
    chips=["Bounded live probes", "No fixed healthy states", "Real weather & AQI", "Truthful cache provenance"],
)

tabs = st.tabs(["Internet & API health", "Local infrastructure", "Weather & environment"], on_change="rerun")
if tabs[0].open:
    with tabs[0]:
        render_internet_status_widget()
        st.divider()
        render_api_health_matrix_widget()
if tabs[1].open:
    with tabs[1]:
        render_gpu_and_infrastructure_widgets()
if tabs[2].open:
    with tabs[2]:
        render_global_weather_widget()