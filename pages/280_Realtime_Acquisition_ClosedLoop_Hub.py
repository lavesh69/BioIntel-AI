from __future__ import annotations

import sys
import json
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.ui.theme import apply_theme
from biointel.acquisition.realtime_acquisition_hub import RealTimeAcquisitionHub

st.set_page_config(page_title="Real-Time Acquisition & Closed-Loop Hub · BioIntel AI", page_icon="📡", layout="wide")
apply_theme()

st.title("📡 Real-Time Multimodal Acquisition & Closed-Loop Experiment Hub")
st.caption("BioIntel AI 15.6.0 · Biology, Engineered into Intelligence. Owner: Lavesh Dobriyal")

if "hub" not in st.session_state:
    st.session_state.hub = RealTimeAcquisitionHub(str(ROOT / "UserData" / "realtime_hub"))
hub = st.session_state.hub

# EMERGENCY STOP & SAFETY HEADER
c_em1, c_em2 = st.columns([3, 1])
with c_em1:
    if hub._emergency_stop_triggered:
        st.error("🚨 **EMERGENCY STOP ACTIVE**: Outbound hardware stimulation and device commands are strictly BLOCKED.")
    else:
        st.success("🟢 **Closed-Loop Safety System Ready**: Mandatory Human Approval Gate is ACTIVE.")

with c_em2:
    if st.button("🚨 EMERGENCY STOP", type="primary", use_container_width=True):
        res = hub.trigger_emergency_stop()
        st.error("EMERGENCY STOP ACTIVATED!")
        st.rerun()

t_streams, t_closedloop, t_audit = st.tabs([
    "📡 Live Stream Discovery & Buffer Health",
    "🛡️ Closed-Loop Human Approval Queue",
    "📜 Immutable Command Audit Log"
])

with t_streams:
    st.subheader("Discovered Real-Time LSL & Open Ephys Streams")
    streams = hub.discover_active_streams()
    s_df = pd.DataFrame([asdict(s) for s in streams])
    st.dataframe(s_df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Ring Buffer & Clock Synchronization Metrics")
    health = hub.get_ring_buffer_health()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("End-to-End Latency", f"{health.latency_end_to_end_ms:.2f} ms")
    m2.metric("Clock Drift", f"{health.clock_drift_ms:.2f} ms")
    m3.metric("Dropped Samples", health.dropped_samples_total)
    m4.metric("Buffer Occupancy", f"{health.current_occupancy_samples} / {health.buffer_capacity_samples} samples")

with t_closedloop:
    st.subheader("Closed-Loop Hardware Command Request & Approval")
    
    col_req, col_app = st.columns(2)
    with col_req:
        st.markdown("#### Request Outbound Device Command")
        dev = st.text_input("Target Hardware Device", "STIM_UNIT_01")
        cmd_t = st.selectbox("Command Type", ["STIMULATION_PULSE", "TRIGGER_OUT", "GAIN_ADJUST"])
        freq = st.number_input("Pulse Frequency (Hz)", 1, 100, 20)
        curr = st.number_input("Current Amplitude (mA)", 0.1, 5.0, 1.0)
        
        if st.button("Submit Command for Approval"):
            try:
                cmd = hub.request_outbound_command(dev, cmd_t, {"frequency_hz": freq, "current_ma": curr})
                st.info(f"Command `{cmd.command_id}` submitted to Human Approval Queue.")
            except Exception as e:
                st.error(str(e))

    with col_app:
        st.markdown("#### Pending Human Approval Queue")
        if hub._pending_commands:
            for cid, cmd in list(hub._pending_commands.items()):
                st.write(f"**ID:** {cmd.command_id} | **Target:** {cmd.target_device} | **Type:** {cmd.command_type}")
                st.write(f"Parameters: {cmd.parameters}")
                col_y, col_n = st.columns(2)
                if col_y.button(f"✅ APPROVE {cid}"):
                    try:
                        hub.approve_command(cid)
                        st.success(f"Command {cid} approved and executed.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
        else:
            st.caption("No pending commands in human approval queue.")

with t_audit:
    st.subheader("Immutable Command Audit History")
    if hub._audit_records:
        st.dataframe(pd.DataFrame(hub._audit_records), use_container_width=True, hide_index=True)
    else:
        st.caption("No executed commands in audit log.")
