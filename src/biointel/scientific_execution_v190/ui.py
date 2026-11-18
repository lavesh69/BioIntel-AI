from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from biointel.ui.operational_canvas import render_operational_canvas

from .catalog import PROFILES
from .generator import module_folder
from .qualification import validate_module


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def render_step190_scientific_execution(module_key: str, *, expanded: bool = False) -> None:
    if module_key not in PROFILES:
        return
    root = _root(); profile = PROFILES[module_key]; folder = module_folder(root, module_key); result = validate_module(root, module_key)
    with st.expander("Step 190 · Scientific Execution, Standards & Native Viewers", expanded=expanded):
        a,b,c,d = st.columns(4)
        a.metric("Internal/demo rating", f"{result.rating:.2f}/10")
        b.metric("Execution controls", f"{result.dimensions_passed}/{result.dimensions_total}")
        c.metric("Category", profile.category.replace("_", " ").title())
        d.metric("Controlled release", "PENDING")
        if result.qualified_10_of_10:
            st.success("Native execution, truth benchmarks, standard-format bridges, streaming, viewers, uncertainty and update-impact checks are operational.")
        else:
            st.error("Step 190 blockers: " + ", ".join(result.blockers))
        st.caption("Detected specialist engines are shown honestly. Built-in execution and bundled references are operational demonstrators; they do not replace licensed production tools, references or independent scientific evidence.")
        tabs = st.tabs(["Native Run", "Engines", "Standards", "Benchmark", "Streaming", "Viewer", "Update Impact", "Capabilities", "Qualification"])
        with tabs[0]:
            render_operational_canvas(
                title="Native-run canvas",
                subtitle="Local adapter execution summary and result provenance.",
                payload=_json(folder / "native_analysis_summary.json"),
                stages=("Prepare", "Execute", "Validate", "Store result"),
                key=f"s190_native_{module_key}",
            )
            st.dataframe(pd.read_csv(folder / "native_results.csv").head(500), width="stretch", hide_index=True)
            st.download_button("Download native results", (folder / "native_results.csv").read_bytes(), f"{module_key}_step190_results.csv", "text/csv", key=f"s190_results_{module_key}")
        with tabs[1]:
            st.dataframe(pd.read_csv(folder / "engine_adapter_matrix.csv"), width="stretch", hide_index=True)
            render_operational_canvas(
                title="Engine-plan canvas",
                subtitle="Detected engines, safe command plan and fallback posture.",
                payload=_json(folder / "safe_command_plan.json"),
                stages=("Detect", "Plan", "Validate", "Run or abstain"),
                key=f"s190_engine_{module_key}",
            )
        with tabs[2]:
            st.dataframe(pd.read_csv(folder / "standard_formats/format_bridge_manifest.csv"), width="stretch", hide_index=True)
            render_operational_canvas(
                title="Standards bridge canvas",
                subtitle="Portable format, interoperability and handoff compatibility facts.",
                payload=_json(folder / "interoperability_manifest.json"),
                stages=("Inspect", "Map", "Validate", "Export"),
                key=f"s190_standards_{module_key}",
            )
            st.dataframe(pd.read_csv(folder / "references/reference_intake_manifest.csv"), width="stretch", hide_index=True)
        with tabs[3]:
            st.dataframe(pd.read_csv(folder / "truth_benchmark_metrics.csv"), width="stretch", hide_index=True)
            st.dataframe(pd.read_csv(folder / "subgroup_robustness.csv"), width="stretch", hide_index=True)
        with tabs[4]:
            st.dataframe(pd.read_csv(folder / "streaming_performance.csv"), width="stretch", hide_index=True)
            render_operational_canvas(
                title="Streaming canvas",
                subtitle="Large-file, bounded-memory and performance characteristics.",
                payload=_json(folder / "optimization_profile.json"),
                stages=("Stage", "Stream", "Preview", "Handoff"),
                key=f"s190_streaming_{module_key}",
            )
        with tabs[5]:
            st.iframe((folder / "native_viewer.html").read_text(encoding="utf-8"), height=680)
        with tabs[6]:
            render_operational_canvas(
                title="Update-impact canvas",
                subtitle="Compatibility, migration and regression-impact summary.",
                payload=_json(folder / "update_impact_report.json"),
                stages=("Compare", "Assess", "Mitigate", "Approve"),
                key=f"s190_update_{module_key}",
            )
            st.dataframe(pd.read_csv(folder / "preset_comparison.csv").head(500), width="stretch", hide_index=True)
        with tabs[7]:
            st.dataframe(pd.read_csv(folder / "advanced_capability_matrix.csv"), width="stretch", hide_index=True)
            st.dataframe(pd.read_csv(folder / "error_recovery_catalogue.csv"), width="stretch", hide_index=True)
        with tabs[8]:
            render_operational_canvas(
                title="Execution qualification canvas",
                subtitle="Internal software checks; independent external evidence remains required.",
                payload=_json(folder / "qualification_manifest.json"),
                stages=("Check", "Validate", "Review", "Gate"),
                key=f"s190_qualification_{module_key}",
            )
            render_operational_canvas(
                title="Production-readiness canvas",
                subtitle="Environment and operational readiness factors for local deployment.",
                payload=_json(folder / "production_readiness_matrix.json"),
                stages=("Provision", "Verify", "Monitor", "Recover"),
                key=f"s190_production_{module_key}",
            )
            render_operational_canvas(
                title="Release-boundary canvas",
                subtitle="Software capability versus required external validation.",
                payload=_json(folder / "release_boundary.json"),
                stages=("Local result", "Limitations", "External review", "Controlled release"),
                key=f"s190_boundary_{module_key}",
            )
            st.download_button("Download complete Step 190 bundle", (folder / "step190_execution_bundle.zip").read_bytes(), f"{module_key}_step190_bundle.zip", "application/zip", key=f"s190_bundle_{module_key}")


__all__ = ["render_step190_scientific_execution"]
