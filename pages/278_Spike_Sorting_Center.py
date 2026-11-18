from __future__ import annotations

import sys
import json
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.ui.theme import apply_theme
from biointel.electrophysiology.spike_sorting_center import SpikeSortingCenter

st.set_page_config(page_title="Spike-Sorting & Electrophysiology Center · BioIntel AI", page_icon="⚡", layout="wide")
apply_theme()

st.title("⚡ Native Neural Electrophysiology & Spike-Sorting Center")
st.caption("BioIntel AI 15.6.0 · Biology, Engineered into Intelligence. Owner: Lavesh Dobriyal")

center = SpikeSortingCenter(str(ROOT))

t_status, t_run, t_probe = st.tabs([
    "🔌 Native Sorter Adapters & Qualification",
    "🚀 Spike-Sorting Pipeline Execution",
    "📐 Probe Geometry & Channel Mapping"
])

with t_status:
    st.subheader("Registered Spike-Sorter Adapters Matrix")
    st.write("Displays native executable paths, hardware requirements, qualification status, and fail-closed diagnostics.")

    adapters = center.get_sorter_adapters_status()
    ad_list = []
    for name, st_obj in adapters.items():
        ad_list.append({
            "Sorter": st_obj.name,
            "Installed": "Yes" if st_obj.installed else "No",
            "Version": st_obj.version_found,
            "Environment": st_obj.environment_type,
            "License": st_obj.license,
            "Hardware Req": st_obj.cpu_ram_gpu_vram,
            "Status": "🟢 QUALIFIED" if st_obj.qualification_status == "QUALIFIED" else ("🟡 SIMULATION" if st_obj.qualification_status == "SIMULATION_TESTED" else "🔴 UNAVAILABLE"),
            "Failure / Diagnostics": st_obj.failure_diagnostics
        })
    
    st.dataframe(ad_list, use_container_width=True, hide_index=True)

with t_run:
    st.subheader("Execute Automated Spike Sorting & Unit Curation")
    col1, col2 = st.columns(2)
    with col1:
        sorter = st.selectbox("Select Spike Sorter Engine", ["SpikeInterface", "Kilosort (v4.0)", "MountainSort5", "IronClust"])
        probe_sel = st.selectbox("Select Probe Layout", ["Neuropixels 1.0", "Utah 96-Channel Array", "32-Channel Linear SEEG Probe"])
        duration = st.slider("Recording Duration (seconds)", 1.0, 60.0, 10.0)

    with col2:
        st.markdown("**Pipeline Configuration Overview**")
        st.info("Pipeline will perform bandpass filtering (300-6000 Hz), spatial whitening, automated unit clustering, SNR calculation, and interneuron vs pyramidal cell classification.")

    if st.button("⚡ Run Spike Sorting Pipeline", type="primary"):
        with st.spinner("Processing neural traces and clustering unit waveforms..."):
            res = center.run_spike_sorting_pipeline(sorter, probe_sel, duration)
            st.success(f"Pipeline executed successfully in {res['execution_time_seconds']}s")
            
            st.markdown("#### Sorted Unit Curation & Classification Table")
            st.dataframe(res["units"], use_container_width=True, hide_index=True)

with t_probe:
    st.subheader("Electrode & Probe Geometry Layout")
    p_sel = st.selectbox("Inspect Probe Type", ["Neuropixels 1.0", "Utah 96-Channel Array", "32-Channel Linear SEEG Probe"], key="probe_inspect")
    p_geo = center.get_probe_geometry(p_sel)
    
    st.metric("Probe Name", p_geo.probe_name)
    st.metric("Total Channels", f"{p_geo.num_channels} channels @ {p_geo.sampling_frequency_hz/1000:.1f} kHz")
    st.write(f"Sample Electrode Contact Coordinates (x, y in µm): {p_geo.channel_positions_um[:10]}")
