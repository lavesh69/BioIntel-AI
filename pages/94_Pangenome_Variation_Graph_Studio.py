from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.innovation.engines import demo_pangenome_graph, graph_layout
from biointel.innovation.advanced_engines import (
    detect_graph_bubbles, graph_component_labels, parse_gfa_extended,
    pangenome_quality_report, path_comparison,
)
from biointel.tools.runtime import resolve_tool, run_tool_audited
from biointel.innovation.excellence_ui import render_pangenome_excellence
from biointel.innovation.professional_ui import render_pangenome_professional
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json
from biointel.ui.scientific_visuals import render_generic_visual_explorer
from biointel.ui.theme import apply_theme, hero, insight_callout, section_title
from biointel.ui.workflow import render_upload_preflight

st.set_page_config(page_title="Pangenome & Variation Graph Studio · BioIntel AI", page_icon="🧬", layout="wide")
apply_theme()

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK · TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('pangenome_core', expanded=False)

# STEP196_P0_P1_PRIORITY_UPGRADE_HOOK
from biointel.proof_gates_v10.ui import render_module_priority_workbench as _render_step196_p0_p1_priority_workbench
_render_step196_p0_p1_priority_workbench(ROOT, 'pangenome_core', expanded=False)

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("pangenome", key_prefix="step116_94_Pangenome_Variation_Graph_Studio_pangenome_1", expanded=False)
hero(
    "Pangenome & Variation Graph Studio Pro",
    "Import GFA1/GFA2 graphs, audit topology, detect branch–rejoin bubbles, compare haplotype paths and export reproducible graph evidence.",
    eyebrow="Step 99 · Executable graph genomics upgrade",
    chips=["GFA1/GFA2", "Walks & paths", "Bubble detection", "ODGI/VG/minigraph", "Audited execution", "Quality audit"],
)
scientific_boundary_banner(source_kind="demo_reference", release_eligible=False, message="Graph analytics are research-grade exploratory checks. Population or clinical interpretation still requires validated assemblies, cohort provenance and specialist graph callers.")

source = st.radio("Graph source", ["Deterministic demo", "Upload GFA/GFA2"], horizontal=True)
upload = st.file_uploader("GFA graph", type=["gfa", "gfa1", "gfa2", "txt"], disabled=source == "Deterministic demo")
render_upload_preflight(
    upload, key="pangenome_gfa", allowed_extensions=["gfa", "gfa1", "gfa2", "txt"],
    soft_limit_mb=100, hard_limit_mb=500,
)
try:
    if upload:
        nodes, edges, paths, issues = parse_gfa_extended(upload.getvalue().decode("utf-8", errors="replace"))
    else:
        nodes, edges, paths = demo_pangenome_graph()
        edges = edges.assign(source_orient="+", target_orient="+", overlap="0M", record_type="L", tags="{}")
        paths = paths.assign(segment_count=paths["nodes"].str.split(",").str.len(), sample=paths["population"], haplotype="", record_type="P")
        nodes = nodes.assign(tags="{}")
        issues = pd.DataFrame(columns=["severity", "line", "issue"])
    quality = pangenome_quality_report(nodes, edges, paths, issues)
    components = quality["components_table"]
    bubbles = quality["bubbles_table"]
except Exception as exc:
    st.error(f"Graph analysis failed: {exc}")
    st.stop()

metric_cards([
    ("Segments", f"{quality['nodes']:,}", None), ("Edges", f"{quality['edges']:,}", None),
    ("Paths/walks", f"{quality['paths']:,}", None), ("Graph span", f"{quality['sequence_bp']:,} bp", None),
    ("Components", quality["components"], None), ("Bubble candidates", quality["bubble_candidates"], None),
    ("Path coverage", f"{quality['path_node_coverage']:.1%}", None), ("Quality score", f"{quality['quality_score']:.0f}/100", None),
])

viz_tab, path_tab, topology_tab, audit_tab, execution_tab, export_tab = st.tabs(["Graph explorer", "Path comparison", "Topology", "Import audit", "Tool execution", "Export"])
with viz_tab:
    max_nodes = st.slider("Maximum displayed nodes", 50, 5000, min(800, max(50, len(nodes))), 50)
    display_nodes = nodes.head(max_nodes).copy()
    display_edges = edges[edges["source"].isin(display_nodes["node"].astype(str)) & edges["target"].isin(display_nodes["node"].astype(str))].copy()
    layout = graph_layout(display_nodes, display_edges)
    view = display_nodes.merge(layout, on="node", how="left").merge(components[["node", "component", "degree"]], on="node", how="left")
    positions = view.set_index("node")[["x", "y"]].to_dict("index")
    edge_x, edge_y = [], []
    for row in display_edges.itertuples(index=False):
        if str(row.source) in positions and str(row.target) in positions:
            edge_x += [positions[str(row.source)]["x"], positions[str(row.target)]["x"], None]
            edge_y += [positions[str(row.source)]["y"], positions[str(row.target)]["y"], None]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=edge_x, y=edge_y, mode="lines", hoverinfo="skip", line={"width": 1.2}, name="links"))
    fig.add_trace(go.Scatter(
        x=view["x"], y=view["y"], mode="markers+text", text=view["node"], textposition="top center",
        marker={"size": np.clip(np.sqrt(pd.to_numeric(view["length"], errors="coerce").fillna(1)) * 5, 12, 38), "color": view["component"], "showscale": True, "colorbar": {"title": "Component"}},
        customdata=np.column_stack([view["length"], view["degree"], view["gc"].fillna(-1)]),
        hovertemplate="Node %{text}<br>Length %{customdata[0]} bp<br>Degree %{customdata[1]}<br>GC %{customdata[2]:.1f}%<extra></extra>",
    ))
    fig.update_layout(height=650, margin=dict(l=10, r=10, t=20, b=10), xaxis=dict(visible=False), yaxis=dict(visible=False), showlegend=False)
    st.plotly_chart(fig, width="stretch")
    if len(nodes) > max_nodes:
        st.warning(f"Showing {max_nodes:,} of {len(nodes):,} segments to protect browser memory. All metrics and exports use the complete graph.")

with path_tab:
    if paths.empty:
        st.info("No P or W path records were present.")
    else:
        reference = st.selectbox("Reference path", paths["path"].astype(str).tolist())
        comparison = path_comparison(paths, reference)
        st.plotly_chart(px.bar(comparison.head(30).sort_values("jaccard"), x="jaccard", y="path", orientation="h", title="Path similarity to reference"), width="stretch")
        smart_dataframe(comparison, height=420, key="pangenome_path_comparison")
        render_generic_visual_explorer(
            comparison,
            key="pangenome_path_visuals",
            heading="Path comparison visual analytics",
        )
        selected = st.selectbox("Inspect path segments", paths["path"].astype(str).tolist(), key="inspect_path")
        st.code(paths.loc[paths["path"].astype(str) == selected, "nodes"].iloc[0], language="text")

with topology_tab:
    c1, c2 = st.columns(2)
    with c1:
        section_title("Component and degree profile", "◎")
        degree_counts = components.groupby("degree").size().reset_index(name="nodes")
        st.plotly_chart(px.bar(degree_counts, x="degree", y="nodes", title="Node degree distribution"), width="stretch")
        component_table = components.sort_values(["component_size", "degree"], ascending=False)
        smart_dataframe(component_table, height=350, key="pangenome_components")
        render_generic_visual_explorer(
            component_table,
            key="pangenome_topology_visuals",
            heading="Graph topology visual analytics",
        )
    with c2:
        section_title("Branch–rejoin bubble candidates", "◇")
        if bubbles.empty:
            st.info("No branch–rejoin bubble candidates were detected within the configured search depth.")
        else:
            smart_dataframe(bubbles, height=500, key="pangenome_bubbles")
    insight_callout("Topology interpretation", f"Cyclomatic number: {quality['cyclomatic_number']}. Tips: {quality['tips']}. Branch nodes: {quality['branch_nodes']}.", tone="info")

with audit_tab:
    if issues.empty:
        st.success("No structural import errors were detected.")
    else:
        smart_dataframe(issues, height=430, key="pangenome_issues")
    smart_json({k: v for k, v in quality.items() if not str(k).endswith("_table")}, key="pangenome_quality_json")

with execution_tab:
    section_title("Audited pangenome tool execution", "▶")
    cols = st.columns([1, 2, 2])
    tool = cols[0].selectbox("Tool", ["odgi", "vg", "minigraph"], key="pangenome_exec_tool")
    graph_path = cols[1].text_input("Local graph/assembly path", "", key="pangenome_exec_input")
    evidence_dir = cols[2].text_input("Evidence directory", str(ROOT / "workspace" / "tool_runs" / "pangenome"), key="pangenome_exec_dir")
    templates = {
        "odgi": 'build -g "{input}" -o "{run}/graph.og"',
        "vg": 'stats -z "{input}"',
        "minigraph": '-xggs -t8 "{input}"',
    }
    command_text = st.text_area(
        "Arguments",
        templates[tool].format(input=graph_path or "INPUT_GFA", run=evidence_dir.replace("\\", "/")),
        height=110,
        key=f"pangenome_exec_args_{tool}",
    )
    resolution = resolve_tool(tool)
    if resolution.available:
        st.success(f"{tool} detected via {resolution.backend}: {resolution.executable}")
    else:
        st.warning(f"{tool} is not installed. Use Advanced Bioinformatics Tools first.")
    confirm = st.checkbox("I reviewed graph format, paths, memory and output requirements", key="pangenome_exec_confirm")
    if st.button("Run pangenome tool with audit evidence", type="primary", disabled=not (resolution.available and graph_path.strip() and confirm), width="stretch"):
        try:
            arguments = shlex.split(command_text, posix=False)
            with st.spinner(f"Running {tool} and capturing provenance..."):
                result = run_tool_audited(tool, arguments, run_directory=evidence_dir, timeout_seconds=24 * 60 * 60)
            st.success(f"{tool} completed in {result.duration_seconds:.1f} seconds.")
            smart_json(result.to_dict(), key="pangenome_exec_result")
        except Exception as exc:
            st.error(f"Pangenome tool execution failed: {exc}")
    insight_callout("Execution evidence", "Step 99 captures the resolved executable, backend, binary hash where available, command vector, stdout, stderr, exit code and timestamps. Graph interpretation still requires cohort and assembly provenance.", tone="info")

with export_tab:
    payload = {
        "schema": "biointel.pangenome.audit.v2",
        "quality": {k: v for k, v in quality.items() if not str(k).endswith("_table")},
        "nodes": nodes.to_dict(orient="records"), "edges": edges.to_dict(orient="records"),
        "paths": paths.to_dict(orient="records"), "bubbles": bubbles.to_dict(orient="records"),
        "issues": issues.to_dict(orient="records"),
    }
    st.download_button("Download complete graph audit JSON", json.dumps(payload, indent=2, default=str).encode(), "pangenome_graph_audit.json", "application/json", width="stretch")
    st.download_button("Download bubble candidates CSV", bubbles.to_csv(index=False).encode(), "pangenome_bubbles.csv", "text/csv", width="stretch")

# Step 99 module excellence layer
render_pangenome_excellence(nodes, edges, paths, bubbles, quality)

# Step 100 professional integration and optimization layer
render_pangenome_professional(nodes, edges, paths, bubbles)

# Step 110 advanced scientific viewers
from biointel.ui.advanced_scientific_viewers import render_embedded_viewer as _render_step110_viewer

_render_step110_viewer("pangenome_graph", key_prefix="step110_94_Pangenome_Variation_Graph_Studio_pangenome_graph")


# Step 112 shared bioinformatics feature upgrades
from biointel.ui.bioinformatics_upgrades import render_bioinformatics_upgrade_panel
render_bioinformatics_upgrade_panel("pangenome", expanded=False)

# Step 115 scientific depth, validation and optimization layer
from biointel.scientific_depth import render_depth_upgrade_panel as _render_step114_depth

_render_step114_depth("pangenome_core", None, key_prefix="step114_pangenome_core", expanded=False)

# Step 115 non-chart visual: pangenome_canvas
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("pangenome_canvas", key_prefix="step115_94_Pangenome_Variation_Graph_Studio_pangenome_canvas", expanded=False)

# STEP127_SCIENTIFIC_DEPTH_PANGENOME
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('pangenome', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='pangenome_graph', title='Pangenome & Variation Graph Studio', category='Bioinformatics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='pangenome_graph', title='Pangenome & Variation Graph Studio', category='Bioinformatics')

# STEP177_21_MODULE_MODEL_COHORT_RUNTIME_EXCELLENCE
from biointel.target_modules_v177.ui import render_step177_module_upgrade
render_step177_module_upgrade('pangenome_core', expanded=False)

# Step 183 all-module synthetic demo bundle
from biointel.portfolio_demo_v183.ui import render_step183_portfolio_demo as _render_step183_portfolio_demo
_render_step183_portfolio_demo("pangenome_core", expanded=False)

# Step 184 advanced deterministic demo assurance
from biointel.demo_assurance_v184.ui import render_step184_demo_assurance as _render_step184_demo_assurance
_render_step184_demo_assurance("pangenome_core", expanded=False)

# STEP188_MAJOR_MODULE_STANDARD_HOOK
from biointel.major_module_standard_v188.ui import render_step188_major_module_standard as _render_step188_major_module_standard
_render_step188_major_module_standard('pangenome_core', expanded=False)

# STEP189_UNIVERSAL_PLATFORM_HOOK
from biointel.universal_platform_v189.ui import render_step189_universal_platform as _render_step189_universal_platform
_render_step189_universal_platform('pangenome_core', expanded=False)

# STEP190_SCIENTIFIC_EXECUTION_HOOK
from biointel.scientific_execution_v190.ui import render_step190_scientific_execution as _render_step190_scientific_execution
_render_step190_scientific_execution('pangenome_core', expanded=False)

# STEP192_RELEASE_INTEGRITY_PUBLICATION_HOOK
from biointel.release_integrity_v192.ui import render_step192_release_integrity as _render_step192_release_integrity
_render_step192_release_integrity('pangenome_core', expanded=False)


# STEP193_MANDATORY_COMPLETION_HOOK
from biointel.mandatory_completion_v193.ui import render_step193_mandatory_completion as _render_step193_mandatory_completion
_render_step193_mandatory_completion('pangenome_core', expanded=False)

