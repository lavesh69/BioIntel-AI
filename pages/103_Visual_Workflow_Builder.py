from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.innovation.engines import WORKFLOW_BLOCKS, WORKFLOW_TEMPLATES
from biointel.innovation.advanced_engines import (
    validate_workflow_dag, workflow_dag_from_blocks, workflow_payload_advanced,
)
from biointel.quality10 import WorkflowRegistry, execute_workflow_v3
from biointel.innovation.excellence_ui import render_workflow_excellence
from biointel.innovation.professional_ui import render_workflow_professional
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json
from biointel.ui.theme import apply_theme, hero, insight_callout, section_title

st.set_page_config(page_title="Visual Workflow Builder & Pipeline Marketplace · BioIntel AI", page_icon="🔗", layout="wide")
apply_theme()

from biointel.ui.scientific_integrations import render_page_integrations as _render_biointel_integrations
_render_biointel_integrations("pages/103_Visual_Workflow_Builder.py", key_prefix="103_visual_workflow_builder", expanded=False)

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK · TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('plugin_marketplace_core', expanded=False)
_render_step196_contextual_online_research('workflow_builder_core', expanded=False)
hero(
    "Visual Workflow Builder & Pipeline Marketplace Pro",
    "Create editable dependency graphs, validate cycles and interfaces, estimate resources, execute resumable internal runs and export portable workflow manifests.",
    eyebrow="Step 99 · Provenance-first orchestration upgrade",
    chips=["Editable DAG", "Real built-in tasks", "Retry & resume", "Artifact SHA-256", "Run registry", "Portable JSON"],
)
scientific_boundary_banner(source_kind="workflow_definition", release_eligible=False, message="Internal blocks execute locally and external-tool blocks require the verified Advanced Tools runtime. Workflow validity does not certify scientific validity of the underlying study.")

if "workflow_dag" not in st.session_state:
    default_blocks = WORKFLOW_TEMPLATES.get(next(iter(WORKFLOW_TEMPLATES)), ["Upload FASTQ", "Read QC", "Quality gate", "Generate report"])
    st.session_state["workflow_dag"] = workflow_dag_from_blocks(default_blocks)

builder_tab, canvas_tab, execute_tab, marketplace_tab = st.tabs(["1 · Builder", "2 · DAG canvas", "3 · Execute & resume", "4 · Templates"])
with builder_tab:
    cols = st.columns([1.2, 1, 1])
    template = cols[0].selectbox("Load template", ["Keep current"] + list(WORKFLOW_TEMPLATES))
    workflow_name = cols[1].text_input("Workflow name", "BioIntel_pro_workflow")
    if cols[2].button("Apply template", width="stretch") and template != "Keep current":
        st.session_state["workflow_dag"] = workflow_dag_from_blocks(WORKFLOW_TEMPLATES[template])
        st.rerun()
    edited = st.data_editor(
        st.session_state["workflow_dag"],
        num_rows="dynamic",
        width="stretch",
        column_config={
            "id": st.column_config.TextColumn("Step ID", required=True),
            "block": st.column_config.SelectboxColumn("Block", options=list(WORKFLOW_BLOCKS), required=True),
            "depends_on": st.column_config.TextColumn("Depends on IDs", help="Comma-separated step IDs"),
            "condition": st.column_config.SelectboxColumn("Condition", options=["always", "on_success", "on_failure", "manual_approval"]),
            "enabled": st.column_config.CheckboxColumn("Enabled"),
        },
        key="workflow_dag_editor",
    )
    st.session_state["workflow_dag"] = edited
    try:
        validated, summary = validate_workflow_dag(edited)
    except Exception as exc:
        st.error(str(exc))
        st.stop()
    metric_cards([
        ("Enabled steps", summary["steps"], None), ("DAG validity", "Pass" if summary["valid"] else "Review", None),
        ("Wall time", f"~{summary['estimated_wall_minutes']} min", None), ("CPU-minutes", summary["cpu_minutes"], None),
        ("Peak memory", f"{summary['peak_memory_gb']} GB", None), ("Warnings", len(summary["warnings"]), None),
    ])
    if summary["warnings"]:
        for warning in summary["warnings"]:
            st.warning(warning)
    else:
        st.success("Dependency graph and registered block interfaces are valid.")
    smart_dataframe(validated, height=420, key="workflow_validated_table")

with canvas_tab:
    try:
        validated, summary = validate_workflow_dag(st.session_state["workflow_dag"])
    except Exception as exc:
        st.error(str(exc))
        st.stop()
    positions = {}
    levels = {}
    for row in validated.itertuples(index=False):
        deps = [x.strip() for x in str(row.depends_on).split(",") if x.strip()]
        levels[row.id] = 0 if not deps else 1 + max((levels.get(dep, 0) for dep in deps), default=0)
    grouped = {}
    for row in validated.itertuples(index=False):
        grouped.setdefault(levels.get(row.id, 0), []).append(row)
    for level, rows in grouped.items():
        center = (len(rows) - 1) / 2
        for index, row in enumerate(rows):
            positions[row.id] = (float(level), float(center - index))
    fig = go.Figure()
    for row in validated.itertuples(index=False):
        for dep in [x.strip() for x in str(row.depends_on).split(",") if x.strip()]:
            if dep in positions and row.id in positions:
                fig.add_trace(go.Scatter(x=[positions[dep][0], positions[row.id][0]], y=[positions[dep][1], positions[row.id][1]], mode="lines", line={"width": 2}, hoverinfo="skip", showlegend=False))
    for row in validated.itertuples(index=False):
        x, y = positions[row.id]
        fig.add_trace(go.Scatter(x=[x], y=[y], mode="markers+text", text=[f"{row.id}<br>{row.block}"], textposition="top center", marker={"size": 34, "symbol": "circle" if row.enabled else "x"}, name=row.id, hovertemplate=f"{row.block}<br>Condition: {row.condition}<extra></extra>"))
    fig.update_layout(height=620, xaxis=dict(visible=False), yaxis=dict(visible=False), showlegend=False, title="Dependency-aware workflow canvas", margin=dict(l=20, r=20, t=60, b=20))
    st.plotly_chart(fig, width="stretch")
    payload = workflow_payload_advanced(workflow_name, st.session_state["workflow_dag"], {"generated_by": "BioIntel AI Step 99"})
    st.download_button("Download workflow v2 JSON", json.dumps(payload, indent=2, default=str).encode(), "biointel_workflow_v2.json", "application/json", width="stretch")

with execute_tab:
    output_root = st.text_input("Run output directory", str(ROOT / "workspace" / "workflow_runs"))
    registry_path = Path(output_root).expanduser() / "workflow_runs.sqlite3"
    cols = st.columns(4)
    resume = cols[0].toggle("Resume verified steps", value=True)
    retries = cols[1].number_input("Retries per failed step", 0, 5, 1, 1)
    fail_fast = cols[2].toggle("Stop after failure", value=True)
    source_kind = cols[3].selectbox("Evidence source", ["user_supplied", "demo", "synthetic", "reference_only"])
    with st.expander("Execution parameters", expanded=False):
        p1, p2, p3, p4 = st.columns(4)
        genome_size_mb = p1.number_input("Genome size (Mb)", 0.001, 100000.0, 5.0, 0.5)
        max_reads = p2.number_input("Maximum reads", 100, 500000, 20000, 1000)
        minimum_quality_score = p3.number_input("Quality-gate threshold", 0.0, 10.0, 7.0, 0.5)
        seed = p4.number_input("Deterministic seed", 1, 999999, 95, 1)
        fastq_path = st.text_input("Optional local FASTQ path", "", help="Leave blank for the deterministic qualification dataset.")
        assembly_fasta_path = st.text_input("Optional completed assembly FASTA path", "", help="Used by the built-in assembly review block. Specialist assembly can be run with an installed external toolchain.")
        protein_sequence = st.text_area("Optional protein sequence", "", height=100)
        omics_table_path = st.text_input("Optional multi-omics CSV path", "")
    parameters = {
        "genome_size_mb": float(genome_size_mb),
        "max_reads": int(max_reads),
        "minimum_quality_score": float(minimum_quality_score),
        "fail_on_quality_gate": True,
        "seed": int(seed),
        "fastq_path": fastq_path.strip(),
        "assembly_fasta_path": assembly_fasta_path.strip(),
        "protein_sequence": protein_sequence.strip(),
        "omics_table_path": omics_table_path.strip(),
    }
    try:
        _, summary = validate_workflow_dag(st.session_state["workflow_dag"])
    except Exception as exc:
        summary = {"valid": False, "warnings": [str(exc)]}
    if st.button("Execute provenance-first workflow", type="primary", disabled=not summary.get("valid", False), width="stretch"):
        try:
            with st.spinner("Executing real built-in tasks, hashing artifacts and persisting run evidence..."):
                result = execute_workflow_v3(
                    st.session_state["workflow_dag"],
                    output_root,
                    workflow_name,
                    parameters=parameters,
                    resume=resume,
                    retries=int(retries),
                    fail_fast=fail_fast,
                    registry_path=registry_path,
                    source_kind=source_kind,
                    synthetic=source_kind in {"demo", "synthetic"},
                )
            if result.status == "completed":
                st.success(f"Run {result.run_id} completed in {result.duration_seconds:.2f} seconds.")
            else:
                st.error(f"Run {result.run_id} finished with status: {result.status}")
            smart_json({
                "run_id": result.run_id,
                "status": result.status,
                "output_directory": result.output_directory,
                "steps": len(result.steps),
                "artifacts": len(result.artifacts),
                "implementation_readiness": result.implementation_readiness,
                "scientific_evidence_score": result.scientific_evidence_score,
            }, key="workflow_run_result_v3")
            smart_dataframe(pd.DataFrame(result.steps), height=470, key="workflow_run_steps_v3")
        except Exception as exc:
            st.error(f"Workflow execution failed: {exc}")
    try:
        registry = WorkflowRegistry(registry_path)
        integrity = registry.integrity_report()
        metric_cards([
            ("Registry health", "Healthy" if integrity["healthy"] else "Review", None),
            ("Registered runs", integrity["counts"]["workflow_runs"], None),
            ("Registered steps", integrity["counts"]["workflow_steps"], None),
            ("Hashed artifacts", integrity["counts"]["workflow_artifacts"], None),
        ])
        summaries = registry.recent_runs(50)
        if summaries:
            section_title("Persistent run history", "↻")
            smart_dataframe(pd.DataFrame(summaries), height=360, key="workflow_run_history_v3")
    except Exception as exc:
        st.warning(f"Run registry is not available yet: {exc}")
    insight_callout("Execution model", "Step 99 executes registered built-in tasks, writes step logs and checksums, persists a foreign-keyed run registry, supports retry/resume, and creates explicit hand-offs where specialist external tools are required.", tone="info")

with marketplace_tab:
    rows = []
    for name, blocks in WORKFLOW_TEMPLATES.items():
        dag = workflow_dag_from_blocks(blocks)
        _, summary = validate_workflow_dag(dag)
        rows.append({"template": name, "steps": len(blocks), "estimated_minutes": summary["estimated_wall_minutes"], "peak_memory_gb": summary["peak_memory_gb"], "blocks": " → ".join(blocks)})
    marketplace = pd.DataFrame(rows)
    smart_dataframe(marketplace, height=500, key="workflow_marketplace")

# Step 99 module excellence layer
render_workflow_excellence(st.session_state["workflow_dag"])

# Step 100 professional integration and optimization layer
render_workflow_professional(st.session_state["workflow_dag"])

# Step 110 advanced scientific viewers
from biointel.ui.advanced_scientific_viewers import render_embedded_viewer as _render_step110_viewer

_render_step110_viewer("workflow_dag", key_prefix="step110_103_Visual_Workflow_Builder_workflow_dag")

# Step 115 module-specific non-chart workspace: workflow
from biointel.ui.non_chart_scientific_visuals import render_module_non_chart_panel as _render_step115_module_non_chart
_render_step115_module_non_chart("workflow", key_prefix="step115_103_Visual_Workflow_Builder_workflow", expanded=False)

# Step 179 platform/core production assurance
from biointel.target_modules_v179.ui import render_step179_module_upgrade as _render_step179_module_upgrade
_render_step179_module_upgrade("plugin_marketplace_core", expanded=False)

# Step 179 platform/core production assurance
from biointel.target_modules_v179.ui import render_step179_module_upgrade as _render_step179_module_upgrade
_render_step179_module_upgrade("workflow_builder_core", expanded=False)

# Step 183 all-module synthetic demo bundle
from biointel.portfolio_demo_v183.ui import render_step183_portfolio_demo as _render_step183_portfolio_demo
_render_step183_portfolio_demo("plugin_marketplace_core", expanded=False)

# Step 183 all-module synthetic demo bundle
from biointel.portfolio_demo_v183.ui import render_step183_portfolio_demo as _render_step183_portfolio_demo
_render_step183_portfolio_demo("workflow_builder_core", expanded=False)


# Step 186 final platform completion assurance
from biointel.platform_completion_v186.ui import render_step186_platform_completion as _render_step186_platform_completion
_render_step186_platform_completion("plugin_marketplace_core", expanded=False)


# Step 186 final platform completion assurance
from biointel.platform_completion_v186.ui import render_step186_platform_completion as _render_step186_platform_completion
_render_step186_platform_completion("workflow_builder_core", expanded=False)

# STEP188_MAJOR_MODULE_STANDARD_HOOK
from biointel.major_module_standard_v188.ui import render_step188_major_module_standard as _render_step188_major_module_standard
_render_step188_major_module_standard('plugin_marketplace_core', expanded=False)
_render_step188_major_module_standard('workflow_builder_core', expanded=False)

# STEP189_UNIVERSAL_PLATFORM_HOOK
from biointel.universal_platform_v189.ui import render_step189_universal_platform as _render_step189_universal_platform
_render_step189_universal_platform('plugin_marketplace_core', expanded=False)
_render_step189_universal_platform('workflow_builder_core', expanded=False)

# STEP190_SCIENTIFIC_EXECUTION_HOOK
from biointel.scientific_execution_v190.ui import render_step190_scientific_execution as _render_step190_scientific_execution
_render_step190_scientific_execution('plugin_marketplace_core', expanded=False)
_render_step190_scientific_execution('workflow_builder_core', expanded=False)

# STEP192_RELEASE_INTEGRITY_PUBLICATION_HOOK
from biointel.release_integrity_v192.ui import render_step192_release_integrity as _render_step192_release_integrity
_render_step192_release_integrity('plugin_marketplace_core', expanded=False)


# STEP193_MANDATORY_COMPLETION_HOOK
from biointel.mandatory_completion_v193.ui import render_step193_mandatory_completion as _render_step193_mandatory_completion
_render_step193_mandatory_completion('plugin_marketplace_core', expanded=False)
_render_step193_mandatory_completion('workflow_builder_core', expanded=False)

