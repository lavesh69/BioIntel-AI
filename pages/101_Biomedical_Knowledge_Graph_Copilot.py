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

from biointel.innovation.engines import demo_knowledge_graph, evidence_summary, knowledge_graph_layout
from biointel.innovation.advanced_engines import (
    graph_conflicts, graph_research_gaps, knowledge_graph_paths, normalize_graph,
)
from biointel.innovation.excellence_ui import render_knowledge_graph_excellence
from biointel.innovation.professional_ui import render_knowledge_graph_professional
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json
from biointel.ui.workflow import read_uploaded_table, render_upload_preflight
from biointel.ui.phase108_visuals import render_phase108_visual_suite  # noqa: E402
from biointel.ui.theme import apply_theme, hero, insight_callout, section_title

st.set_page_config(page_title="Biomedical Knowledge Graph & Evidence Copilot · BioIntel AI", page_icon="🕸️", layout="wide")
apply_theme()

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK · TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('knowledge_graph_core', expanded=False)
hero(
    "Biomedical Knowledge Graph & Evidence Copilot Pro",
    "Import evidence graphs, inspect citation completeness, trace multi-hop mechanisms, detect conflicts and surface low-evidence research gaps without inventing sources.",
    eyebrow="Step 99 · Evidence-grounded intelligence",
    chips=["Graph import", "Multi-hop paths", "Conflict detection", "Citation coverage", "Research gaps", "Offline export"],
)
scientific_boundary_banner(source_kind="demo_reference", release_eligible=False, message="The copilot summarizes only loaded graph records. It does not browse, verify or invent external evidence; scientific conclusions require source-level review and current literature retrieval.")

source = st.radio("Graph source", ["Bundled evidence demo", "Upload node + edge tables"], horizontal=True)
node_upload = st.file_uploader("Nodes table: node, type", type=["csv", "tsv", "xlsx", "xlsm"], disabled=source.startswith("Bundled"))
edge_upload = st.file_uploader("Edges table: source, target, relation, evidence_score, evidence_type, citation, direction", type=["csv", "tsv", "xlsx", "xlsm"], disabled=source.startswith("Bundled"))
render_upload_preflight(node_upload, key="knowledge_graph_nodes", allowed_extensions=["csv", "tsv", "xlsx", "xlsm"], soft_limit_mb=25, hard_limit_mb=200)
render_upload_preflight(edge_upload, key="knowledge_graph_edges", allowed_extensions=["csv", "tsv", "xlsx", "xlsm"], soft_limit_mb=50, hard_limit_mb=400)
try:
    if node_upload and edge_upload:
        nodes = read_uploaded_table(node_upload)
        edges = read_uploaded_table(edge_upload)
    else:
        nodes, edges = demo_knowledge_graph()
        edges["citation"] = edges.apply(lambda row: row["source"] if str(row["source"]).startswith(("PMID:", "NCT")) else "", axis=1)
        edges["direction"] = "supporting"
    nodes, edges, issues = normalize_graph(nodes, edges)
except Exception as exc:
    st.error(f"Graph loading failed: {exc}")
    st.stop()

minimum = st.slider("Minimum evidence score", 0.0, 1.0, 0.0, 0.05)
filtered_edges = edges[edges["evidence_score"] >= minimum].copy()
conflicts = graph_conflicts(filtered_edges)
gaps = graph_research_gaps(nodes, filtered_edges)
citation_coverage = float(filtered_edges["citation"].astype(str).str.strip().ne("").mean()) if len(filtered_edges) else 0.0
summary = evidence_summary(nodes, filtered_edges, "")
metric_cards([
    ("Entities", len(nodes), None), ("Relationships", len(filtered_edges), None),
    ("Mean evidence", f"{summary['mean_evidence']:.2f}", None), ("Citation coverage", f"{citation_coverage:.1%}", None),
    ("Conflict candidates", len(conflicts), None), ("Unconnected entities", int((gaps["degree"] == 0).sum()), None),
    ("Import issues", len(issues), None),
])

graph_tab, path_tab, conflict_tab, gap_tab, export_tab = st.tabs(["Graph explorer", "Mechanistic paths", "Conflicts", "Research gaps", "Export"])
with graph_tab:
    focus = st.text_input("Focus entity/topic", "BRCA1")
    layout = knowledge_graph_layout(nodes, filtered_edges)
    if focus.strip():
        matched = set(nodes.loc[nodes["node"].str.contains(focus, case=False, regex=False), "node"])
        neighbors = set(filtered_edges.loc[filtered_edges["source"].isin(matched), "target"]) | set(filtered_edges.loc[filtered_edges["target"].isin(matched), "source"])
        visible = matched | neighbors
        if visible:
            layout = layout[layout["node"].isin(visible)]
    positions = layout.set_index("node")[["x", "y"]].to_dict("index")
    edge_x, edge_y = [], []
    for row in filtered_edges.itertuples(index=False):
        if row.source in positions and row.target in positions:
            edge_x += [positions[row.source]["x"], positions[row.target]["x"], None]
            edge_y += [positions[row.source]["y"], positions[row.target]["y"], None]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=edge_x, y=edge_y, mode="lines", hoverinfo="skip", line={"width": 1.2}, name="evidence links"))
    for kind, group in layout.groupby("type"):
        fig.add_trace(go.Scatter(x=group["x"], y=group["y"], text=group["node"], mode="markers+text", textposition="top center", marker={"size": 22}, name=str(kind), hovertemplate="%{text}<extra></extra>"))
    fig.update_layout(height=650, xaxis=dict(visible=False), yaxis=dict(visible=False), margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, width="stretch")
    focus_summary = evidence_summary(nodes, filtered_edges, focus)
    insight_callout("Evidence-grounded summary", focus_summary["summary"], tone="info")
    smart_dataframe(filtered_edges, height=360, key="kg_relationships_pro")

with path_tab:
    entities = nodes["node"].astype(str).tolist()
    c1, c2, c3 = st.columns(3)
    start = c1.selectbox("Source", entities, index=0)
    end = c2.selectbox("Target", entities, index=min(1, len(entities) - 1))
    depth = c3.slider("Maximum hops", 1, 6, 4)
    paths = knowledge_graph_paths(filtered_edges, start, end, depth)
    if paths.empty:
        st.info("No path was found within the selected hop limit.")
    else:
        smart_dataframe(paths, height=430, key="kg_mechanistic_paths")
        smart_json(paths.iloc[0].to_dict(), key="kg_best_path")

with conflict_tab:
    if conflicts.empty:
        st.success("No same-pair semantic or directional conflict candidates were detected.")
    else:
        smart_dataframe(conflicts, height=450, key="kg_conflicts")
    if issues.empty:
        st.success("No graph integrity issues were detected.")
    else:
        section_title("Import integrity issues", "⚠")
        smart_dataframe(issues, height=300, key="kg_issues")

with gap_tab:
    smart_dataframe(gaps, height=500, key="kg_research_gaps")
    insight_callout("Gap interpretation", "High gap scores flag disconnected or uncited entities. They identify curation priorities, not evidence that a biological relationship exists.", tone="warning")

with export_tab:
    payload = {
        "schema": "biointel.knowledge_graph.v2",
        "nodes": nodes.to_dict(orient="records"), "edges": filtered_edges.to_dict(orient="records"),
        "conflicts": conflicts.to_dict(orient="records"), "research_gaps": gaps.to_dict(orient="records"),
        "citation_coverage": citation_coverage, "issues": issues.to_dict(orient="records"),
    }
    st.download_button("Download complete evidence graph JSON", json.dumps(payload, indent=2, default=str).encode(), "biomedical_knowledge_graph_pro.json", "application/json", width="stretch")
    st.download_button("Download research gaps CSV", gaps.to_csv(index=False).encode(), "knowledge_graph_research_gaps.csv", "text/csv", width="stretch")

# Step 99 module excellence layer
render_knowledge_graph_excellence(nodes, filtered_edges)

# Step 100 professional integration and optimization layer
render_knowledge_graph_professional(nodes, filtered_edges)

# Step 108 Phase 1+2 decision visual workspace
render_phase108_visual_suite("knowledge_graph", ROOT, context=locals())

# Step 115 scientific depth, validation and optimization layer
from biointel.scientific_depth import render_depth_upgrade_panel as _render_step114_depth

_render_step114_depth("knowledge_graph_core", None, key_prefix="step114_knowledge_graph_core", expanded=False)

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='knowledge_graph_copilot', title='Biomedical Knowledge Graph & Evidence Copilot', category='Intelligence')

# Step 179 platform/core production assurance
from biointel.target_modules_v179.ui import render_step179_module_upgrade as _render_step179_module_upgrade
_render_step179_module_upgrade("knowledge_graph_core", expanded=False)

# Step 183 all-module synthetic demo bundle
from biointel.portfolio_demo_v183.ui import render_step183_portfolio_demo as _render_step183_portfolio_demo
_render_step183_portfolio_demo("knowledge_graph_core", expanded=False)


# Step 186 final platform completion assurance
from biointel.platform_completion_v186.ui import render_step186_platform_completion as _render_step186_platform_completion
_render_step186_platform_completion("knowledge_graph_core", expanded=False)

# STEP188_MAJOR_MODULE_STANDARD_HOOK
from biointel.major_module_standard_v188.ui import render_step188_major_module_standard as _render_step188_major_module_standard
_render_step188_major_module_standard('knowledge_graph_core', expanded=False)

# STEP189_UNIVERSAL_PLATFORM_HOOK
from biointel.universal_platform_v189.ui import render_step189_universal_platform as _render_step189_universal_platform
_render_step189_universal_platform('knowledge_graph_core', expanded=False)

# STEP190_SCIENTIFIC_EXECUTION_HOOK
from biointel.scientific_execution_v190.ui import render_step190_scientific_execution as _render_step190_scientific_execution
_render_step190_scientific_execution('knowledge_graph_core', expanded=False)

# STEP192_RELEASE_INTEGRITY_PUBLICATION_HOOK
from biointel.release_integrity_v192.ui import render_step192_release_integrity as _render_step192_release_integrity
_render_step192_release_integrity('knowledge_graph_core', expanded=False)


# STEP193_MANDATORY_COMPLETION_HOOK
from biointel.mandatory_completion_v193.ui import render_step193_mandatory_completion as _render_step193_mandatory_completion
_render_step193_mandatory_completion('knowledge_graph_core', expanded=False)

