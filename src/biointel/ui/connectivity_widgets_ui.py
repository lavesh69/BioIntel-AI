"""Reusable Streamlit UI for measured connectivity and system probes."""
from __future__ import annotations

import streamlit as st

from biointel.monitoring.system_connectivity_widgets import SystemConnectivityWidgetsEngine


@st.cache_resource(show_spinner=False)
def _engine() -> SystemConnectivityWidgetsEngine:
    return SystemConnectivityWidgetsEngine()


def render_internet_status_widget() -> None:
    engine = _engine()
    mode = st.segmented_control(
        "Application connectivity mode",
        ["Auto Detect", "Online", "Offline", "Air-Gapped"],
        default="Auto Detect",
        key="connectivity_mode",
    )
    if "internet_probe" not in st.session_state or st.button("Check internet now", icon=":material/wifi_find:"):
        with st.spinner("Measuring DNS and HTTPS connectivity…"):
            st.session_state["internet_probe"] = engine.check_internet_status(mode or "Auto Detect")
    result = st.session_state["internet_probe"]
    columns = st.columns(4)
    columns[0].metric("Internet state", result["status"])
    columns[1].metric("HTTPS latency", f"{result['latency_ms']} ms" if result.get("latency_ms") is not None else "Unavailable")
    columns[2].metric("DNS", result["dns_status"])
    columns[3].metric("HTTPS", result["https_status"])
    st.caption(
        f"Checked {result['provenance']['timestamp_utc']} · HTTP {result.get('http_status') or 'N/A'} · "
        f"last success {result.get('last_success') or 'none recorded'}"
    )
    if result.get("safe_error"):
        st.info(result["safe_error"])


def render_api_health_matrix_widget() -> None:
    st.subheader("Central API Health Matrix")
    engine = _engine()
    if "api_health_matrix" not in st.session_state:
        st.info("Run bounded HTTPS probes to measure the configured connectors. No status is assumed before testing.")
    if st.button("Run connector health checks", icon=":material/monitor_heart:", type="primary"):
        with st.spinner("Running parallel bounded provider checks…"):
            st.session_state["api_health_matrix"] = engine.get_api_health_matrix()
    matrix = st.session_state.get("api_health_matrix")
    if not matrix:
        return
    rows = []
    for name, info in matrix["connectors"].items():
        rows.append({
            "Connector / service": name,
            "Status": info["status"],
            "Latency (ms)": info["latency_ms"],
            "HTTP": info["http_status"],
            "Authentication": info["authentication_state"],
            "Rate limit": info["rate_limit_state"],
            "Last success": info["last_success"],
            "Last failure": info["last_failure"],
            "Safe error": info["safe_error"],
            "Cache fallback": info["cache_fallback"],
        })
    st.dataframe(rows, hide_index=True)
    st.caption(
        f"Measured {matrix['timestamp_utc']} · online {matrix['online_count']}/{matrix['total_connectors']} · "
        f"not configured {matrix['not_configured_count']}"
    )


def render_gpu_and_infrastructure_widgets() -> None:
    engine = _engine()
    if st.button("Inspect local infrastructure", icon=":material/computer:", type="primary") or "infra_probe" not in st.session_state:
        with st.spinner("Inspecting BioIntel-owned processes, ports, GPU, Docker, WSL2, and storage…"):
            st.session_state["infra_probe"] = {
                "gpu": engine.check_gpu_telemetry(),
                "runtime": engine.inspect_docker_wsl2_status(),
                "process_storage": engine.inspect_process_supervisor_and_storage(),
                "tls_proxy": engine.inspect_tls_and_proxy(),
            }
    probe = st.session_state["infra_probe"]
    tabs = st.tabs(["GPU", "Docker & WSL2", "Processes & storage", "Proxy & TLS"], on_change="rerun")
    if tabs[0].open:
        with tabs[0]:
            gpu = probe["gpu"]
            st.json(gpu)
            if not gpu["gpu_detected"]:
                st.info("CPU fallback is active; no qualified NVIDIA telemetry was returned.")
    if tabs[1].open:
        with tabs[1]:
            runtime = probe["runtime"]
            columns = st.columns(2)
            with columns[0]:
                st.markdown("#### WSL2")
                st.json(runtime["wsl2"])
            with columns[1]:
                st.markdown("#### Docker")
                st.json(runtime["docker"])
    if tabs[2].open:
        with tabs[2]:
            process_storage = probe["process_storage"]
            st.dataframe(
                [{"component": name, **details} for name, details in process_storage["processes"].items()],
                hide_index=True,
            )
            storage = process_storage["storage_health"]
            columns = st.columns(4)
            columns[0].metric("Free disk", f"{storage['free_gb']} GB")
            columns[1].metric("Used disk", f"{storage['used_gb']} GB")
            columns[2].metric("Write test", storage["write_test"])
            columns[3].metric("Disk warning", "Yes" if storage["disk_full_warning"] else "No")
    if tabs[3].open:
        with tabs[3]:
            st.json(probe["tls_proxy"])