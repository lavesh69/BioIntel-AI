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
from biointel.electrophysiology.ieeg_ecog_seeg_studio import IntracranialEEGStudio, SAFETY_DISCLAIMER

st.set_page_config(page_title="iEEG, ECoG & SEEG Research Studio · BioIntel AI", page_icon="🧠", layout="wide")
apply_theme()

st.title("🧠 iEEG, ECoG & SEEG Research Studio")
st.caption("BioIntel AI 15.6.0 · Biology, Engineered into Intelligence. Owner: Lavesh Dobriyal")

# MANDATORY SCIENTIFIC SAFETY BANNER
st.warning(f"⚠️ **SCIENTIFIC SAFETY BOUNDARY**: {SAFETY_DISCLAIMER}. Candidate electrophysiology events are for signal research only. Never use for clinical diagnosis or surgical planning.")

studio = IntracranialEEGStudio(str(ROOT))

t_3d, t_pac, t_report = st.tabs([
    "📍 3D SEEG/ECoG Contact Localization",
    "🌊 Phase-Amplitude Coupling (PAC) & High-Gamma",
    "📄 Research Export Package"
])

with t_3d:
    st.subheader("3D Cortical & Stereotactic Contact Reconstruction")
    col1, col2 = st.columns([1, 3])
    with col1:
        num_c = st.slider("Number of Contacts", 16, 128, 48)
        mod = st.selectbox("Modality", ["SEEG Depth Electrodes", "ECoG Subdural Grids"])
        st.info("Coregisters pre-op T1 MRI and post-op CT to project contacts onto cortical surfaces.")

    with col2:
        contacts = studio.localize_seeg_ecog_contacts(num_c, mod)
        df_c = pd.DataFrame([asdict(c) for c in contacts])
        
        fig = px.scatter_3d(
            df_c, x="x", y="y", z="z",
            color="high_gamma_power_db",
            size="ied_candidate_count",
            hover_data=["contact_id", "electrode_name", "anatomical_location"],
            title="3D Intracranial Contact Reconstruction (Plotly 3D)"
        )
        fig.update_layout(margin=dict(l=0, r=0, b=0, t=30), height=500)
        st.plotly_chart(fig, use_container_width=True)

with t_pac:
    st.subheader("Phase-Amplitude Coupling (PAC) & Time-Frequency Analysis")
    pac_res = studio.compute_phase_amplitude_coupling()
    
    st.markdown("#### Modulation Index (MI) Results")
    m1, m2, m3 = st.columns(3)
    m1.metric("Phase Freq Band", f"{pac_res.phase_freq_hz[0]}-{pac_res.phase_freq_hz[1]} Hz (Theta)")
    m2.metric("Amplitude Freq Band", f"{pac_res.amp_freq_hz[0]}-{pac_res.amp_freq_hz[1]} Hz (High-Gamma)")
    m3.metric("PAC Modulation Index (MI)", f"{pac_res.modulation_index:.4f} (Z = {pac_res.z_score})")

with t_report:
    st.subheader("Generate Provenance-Preserving Research Export")
    if st.button("📥 Build iEEG Research Package", type="primary"):
        rep = studio.generate_ieeg_analysis_report()
        st.json(rep)
