from __future__ import annotations

import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import streamlit as st

from biointel.engine_platform_v196.ui import render_engine_control_center
from biointel.engines.engine_runtime_center import ScientificEngineRuntimeCenter, TARGET_ENGINES
from biointel.ui.theme import apply_theme

st.set_page_config(
    page_title="Engine Control Center · BioIntel AI",
    page_icon="⚙️",
    layout="wide",
)
apply_theme()

st.title("⚙️ Native Scientific Engine Runtime Center")
st.caption("BioIntel AI 15.6.0 · Biology, Engineered into Intelligence.")

# Active Runtime Center Engine Manager
runtime_center = ScientificEngineRuntimeCenter(str(ROOT))
env = runtime_center.env_report

# Hardware & System Bar
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Operating System", f"{env.os_name} {env.architecture}")
c2.metric("CPU Cores", f"{env.cpu_cores_physical} phys / {env.cpu_cores_logical} log")
c3.metric("RAM (Available / Total)", f"{env.ram_available_gb} / {env.ram_total_gb} GB")
c4.metric("GPU Acceleration", f"{env.gpu_name}" if env.gpu_available else "CPU Only")
c5.metric("WSL2 / Docker", f"{'WSL2 Ready' if env.wsl2_available else 'No WSL2'} | {'Docker' if env.docker_available else 'No Docker'}")

st.divider()

# Primary Tabs
t_runtime, t_legacy = st.tabs(["🚀 P0 Native Engine Runtime Center (15 Engines)", "📊 Legacy Engine Platform Catalogue"])

with t_runtime:
    st.subheader("Native Scientific & ML Engine Matrix")
    st.write("Live status, version pinning, fail-closed boundaries, and qualification for all 15 core scientific engines.")
    
    statuses = runtime_center.probe_all_engines()
    
    table_data = []
    for eng_name, status in statuses.items():
        table_data.append({
            "Engine": eng_name,
            "Mode Status": "🟢 NATIVE" if status.mode == "NATIVE" else ("🟡 PROXY / SIMULATION" if status.mode == "PROXY_SIMULATION" else "🔴 UNAVAILABLE"),
            "Installed": "Yes" if status.installed else "No",
            "Version Found": status.version_found,
            "Pinned Version": status.pinned_version,
            "Match": "✅ Pinned" if status.version_matched else "⚠️ Unpinned / Alternate",
            "Executable Path": status.executable_path,
            "Execution Scope": status.execution_type,
            "Fail-Closed Status": status.fail_closed_reason or "Operational"
        })
    
    st.dataframe(table_data, use_container_width=True)
    
    st.divider()
    
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.subheader("Run Qualification Benchmark")
        sel_engine = st.selectbox("Select Target Engine for Diagnostic Test", TARGET_ENGINES)
        if st.button("⚡ Execute Qualification Benchmark", key="run_qual_bench"):
            with st.spinner(f"Running diagnostic qualification on {sel_engine}..."):
                res = runtime_center.run_benchmark_qualification(sel_engine)
                st.success(f"Qualification benchmark completed in {res['duration_seconds']}s")
                st.json(res)
                
    with col_b:
        st.subheader("Diagnostic Export & Recovery")
        if st.button("📥 Generate Diagnostic Health Report", key="gen_diag_report"):
            report = runtime_center.export_diagnostics_report()
            st.json(report)
            st.download_button(
                "💾 Download Health Report (JSON)",
                data=json.dumps(report, indent=2),
                file_name="biointel_engine_runtime_health.json",
                mime="application/json"
            )

with t_legacy:
    render_engine_control_center()
