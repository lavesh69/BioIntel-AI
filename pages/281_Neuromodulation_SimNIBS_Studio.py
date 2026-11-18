from __future__ import annotations

import sys
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.ui.theme import apply_theme
from biointel.neuromodulation.simnibs_targeting_studio import SimNIBSTargetingStudio, SIMULATION_LABEL

st.set_page_config(page_title="Neuromodulation & SimNIBS Studio · BioIntel AI", page_icon="⚡", layout="wide")
apply_theme()

st.title("⚡ Neuromodulation Simulation & SimNIBS Targeting Studio")
st.caption("BioIntel AI 15.6.0 · Biology, Engineered into Intelligence. Owner: Lavesh Dobriyal")

# MANDATORY SCIENTIFIC SAFETY BANNER
st.warning(f"⚠️ **STRICT RESEARCH BOUNDARY**: {SIMULATION_LABEL}. All electric field calculations and coil montages are research models.")

studio = SimNIBSTargetingStudio(str(ROOT))

t_sim, t_tissues, t_3d = st.tabs([
    "⚡ Electric Field (E-Field) Solver",
    "🧠 5-Tissue Realistic Head Mesh",
    "🌐 3D Vector Magnitude Render"
])

with t_sim:
    st.subheader("TMS & HD-tDCS Cortical E-Field Distribution Solver")
    
    col1, col2 = st.columns(2)
    with col1:
        stim_type = st.selectbox("Stimulation Modality", ["TMS_Figure8", "HD_tDCS_4x1", "tACS"])
        target_reg = st.selectbox("Target Cortical Region", ["Left Primary Motor Cortex (M1)", "Dorsolateral Prefrontal Cortex (DLPFC)", "Primary Visual Cortex (V1)"])
        intensity = st.slider("Stimulation Intensity (mA or dI/dt %)", 0.2, 5.0, 1.5)

    with col2:
        st.markdown("**SimNIBS Adapter & Solver Controls**")
        st.info("Uses Finite Element Method (FEM) 5-tissue volume conductor models to compute electric field vector magnitudes across cortical surface triangles.")

    if st.button("⚡ Solve 3D Electric Field Distribution", type="primary"):
        res = studio.solve_e_field_simulation(stim_type, target_reg, intensity)
        st.success("Finite Element Method (FEM) E-field simulation complete!")
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Peak E-Field (V/m)", f"{res.peak_e_field_v_m:.3f} V/m")
        m2.metric("Mean Cortical E-Field", f"{res.mean_cortical_e_field_v_m:.3f} V/m")
        m3.metric("Stimulated Cortical Volume", f"{res.stimulated_volume_mm3:.1f} mm³")
        
        st.json(asdict(res))

with t_tissues:
    st.subheader("5-Tissue Conductive Boundary Parameters")
    tissues = studio.get_tissue_conductivities()
    t_df = pd.DataFrame([asdict(t) for t in tissues])
    st.dataframe(t_df, use_container_width=True, hide_index=True)

with t_3d:
    st.subheader("3D Electric Field Spatial Vector Plot")
    pts = studio.generate_e_field_spatial_grid(150)
    pts_df = pd.DataFrame(pts)
    
    fig = px.scatter_3d(
        pts_df, x="x", y="y", z="z",
        color="e_field_v_m",
        size="e_field_v_m",
        title="3D Cortical Electric Field Vector Magnitude (Plotly 3D)"
    )
    fig.update_layout(margin=dict(l=0, r=0, b=0, t=30), height=500)
    st.plotly_chart(fig, use_container_width=True)
