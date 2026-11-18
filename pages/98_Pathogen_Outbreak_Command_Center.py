from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.innovation.engines import demo_outbreak_data
from biointel.innovation.advanced_engines import distance_tree_newick, newick_tree_layout, outbreak_advanced
from biointel.tools.runtime import run_tool_audited, verified_tool_status
from biointel.innovation.excellence_ui import render_outbreak_excellence
from biointel.innovation.professional_ui import render_outbreak_professional
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json
from biointel.ui.workflow import read_uploaded_table, render_upload_preflight
from biointel.ui.theme import apply_theme, hero, insight_callout, section_title

st.set_page_config(page_title="Pathogen Outbreak Genomics Command Center · BioIntel AI", page_icon="🦠", layout="wide")
apply_theme()

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK · TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('pathogen_outbreak_core', expanded=False)

# STEP196_P0_P1_PRIORITY_UPGRADE_HOOK
from biointel.proof_gates_v10.ui import render_module_priority_workbench as _render_step196_p0_p1_priority_workbench
_render_step196_p0_p1_priority_workbench(ROOT, 'pathogen_outbreak_core', expanded=False)

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("pathogen_outbreak", key_prefix="step116_98_Pathogen_Outbreak_Command_Center_pathogen_outbreak_1", expanded=False)
hero(
    "Pathogen Outbreak Genomics Command Center Pro",
    "Combine SNP distance, collection time and geography into provisional clusters, scored links and minimum-spanning transmission review networks.",
    eyebrow="Step 99 · Audited genomic epidemiology",
    chips=["Upload metadata", "Distance matrix", "Phylogeny", "MST", "AMR", "Audited tools"],
)
scientific_boundary_banner(source_kind="synthetic", release_eligible=False, message="This module supports outbreak review but does not establish person-to-person transmission. Organism-specific thresholds, epidemiology, infection-control investigation and validated genomic pipelines remain essential.")

source = st.radio("Data source", ["Deterministic outbreak demo", "Upload metadata + distance matrix"], horizontal=True)
meta_upload = st.file_uploader("Sample metadata CSV/TSV/Excel", type=["csv", "tsv", "xlsx", "xlsm"], disabled=source.startswith("Deterministic"))
distance_upload = st.file_uploader("Square SNP/core-genome distance matrix CSV/TSV/Excel", type=["csv", "tsv", "xlsx", "xlsm"], disabled=source.startswith("Deterministic"))
render_upload_preflight(meta_upload, key="outbreak_metadata", allowed_extensions=["csv", "tsv", "xlsx", "xlsm"], soft_limit_mb=20, hard_limit_mb=200)
render_upload_preflight(distance_upload, key="outbreak_distance", allowed_extensions=["csv", "tsv", "xlsx", "xlsm"], soft_limit_mb=50, hard_limit_mb=400)
try:
    if meta_upload and distance_upload:
        samples = read_uploaded_table(meta_upload)
        distances = read_uploaded_table(distance_upload, index_column=0)
    else:
        samples, distances = demo_outbreak_data()
except Exception as exc:
    st.error(f"Data loading failed: {exc}")
    st.stop()

cols = st.columns(3)
snp_threshold = cols[0].slider("Provisional genomic threshold (SNPs)", 0, 100, 12)
day_threshold = cols[1].slider("Temporal window (days)", 1, 365, 30)
km_threshold = cols[2].slider("Spatial window (km)", 1.0, 1000.0, 50.0, 1.0)
try:
    result = outbreak_advanced(samples, distances, snp_threshold, day_threshold, km_threshold)
except Exception as exc:
    st.error(f"Outbreak analysis failed: {exc}")
    st.stop()
clustered, links, mst, cluster_summary = result["samples"], result["links"], result["mst"], result["cluster_summary"]

metric_cards([
    ("Samples", len(clustered), None), ("Provisional clusters", clustered["outbreak_cluster"].nunique(), None),
    ("Candidate links", len(links), None), ("MST edges", len(mst), None),
    ("AMR-positive", int((clustered.get("amr_gene", pd.Series("none", index=clustered.index)).astype(str).str.lower() != "none").sum()), None),
    ("Locations", clustered.get("location", pd.Series("unknown", index=clustered.index)).nunique(), None),
])

map_tab, network_tab, phylogeny_tab, timeline_tab, audit_tab = st.tabs(["Map", "Genomic network", "Phylogeny & tools", "Timeline", "Cluster audit"])
with map_tab:
    hover = [c for c in ["sample_id", "collection_date", "location", "species", "amr_gene", "outbreak_cluster"] if c in clustered]
    fig = px.scatter_map(clustered, lat="latitude", lon="longitude", color="outbreak_cluster", size="cluster_size", hover_data=hover, zoom=9, height=620, title="Linked genomic-spatiotemporal map")
    st.plotly_chart(fig, width="stretch")

with network_tab:
    # Deterministic circular layout per cluster for a browser-safe linked graph.
    nodes = clustered[["sample_id", "outbreak_cluster", "cluster_size"]].copy()
    positions = {}
    x_offset = 0.0
    for cluster, group in nodes.groupby("outbreak_cluster"):
        import numpy as np
        angles = np.linspace(0, 2 * np.pi, len(group), endpoint=False)
        radius = max(1.0, len(group) / 5)
        for angle, sample_id in zip(angles, group["sample_id"]):
            positions[str(sample_id)] = (x_offset + radius * np.cos(angle), radius * np.sin(angle))
        x_offset += radius * 2.8 + 2
    edge_x, edge_y = [], []
    for row in mst.itertuples(index=False):
        if row.source in positions and row.target in positions:
            edge_x += [positions[row.source][0], positions[row.target][0], None]
            edge_y += [positions[row.source][1], positions[row.target][1], None]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=edge_x, y=edge_y, mode="lines", line={"width": 2}, hoverinfo="skip", name="MST"))
    for cluster, group in nodes.groupby("outbreak_cluster"):
        fig.add_trace(go.Scatter(
            x=[positions[str(x)][0] for x in group["sample_id"]], y=[positions[str(x)][1] for x in group["sample_id"]],
            text=group["sample_id"], mode="markers+text", textposition="top center", marker={"size": 18}, name=str(cluster),
            hovertemplate="%{text}<extra></extra>",
        ))
    fig.update_layout(height=620, xaxis=dict(visible=False), yaxis=dict(visible=False), title="Minimum-spanning genomic forest", margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig, width="stretch")
    smart_dataframe(mst, height=330, key="outbreak_mst")

with phylogeny_tab:
    section_title("Distance-derived phylogeny", "♧")
    method = st.radio("Tree method", ["Neighbor joining", "UPGMA"], horizontal=True)
    try:
        newick = distance_tree_newick(result["distance_matrix"], method="upgma" if method == "UPGMA" else "nj")
        layout = newick_tree_layout(newick)
        tree_nodes, tree_edges = layout["nodes"], layout["edges"]
        edge_x, edge_y = [], []
        for row in tree_edges.itertuples(index=False):
            # Orthogonal phylogram: vertical segment at parent x then horizontal to child x.
            edge_x.extend([row.x0, row.x0, row.x1, None])
            edge_y.extend([row.y0, row.y1, row.y1, None])
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=edge_x, y=edge_y, mode="lines", line={"width": 1.8}, hoverinfo="skip", name="Branches"))
        tips = tree_nodes[tree_nodes["is_terminal"]].copy()
        internals = tree_nodes[~tree_nodes["is_terminal"]].copy()
        fig.add_trace(go.Scatter(
            x=tips["x"], y=tips["y"], mode="markers+text", text=tips["label"], textposition="middle right",
            marker={"size": 9}, customdata=tips[["node_id", "confidence"]],
            hovertemplate="%{text}<br>distance=%{x:.3f}<extra></extra>", name="Samples",
        ))
        fig.add_trace(go.Scatter(
            x=internals["x"], y=internals["y"], mode="markers", marker={"size": 6},
            hovertemplate="internal node<br>distance=%{x:.3f}<extra></extra>", name="Internal nodes",
        ))
        fig.update_layout(height=620, title=f"{method} phylogram", yaxis={"visible": False}, xaxis_title="Genomic distance", margin={"l": 20, "r": 150, "t": 55, "b": 40})
        st.plotly_chart(fig, width="stretch")
        c1, c2 = st.columns(2)
        c1.download_button("Download Newick", newick.encode(), "outbreak_distance_tree.newick", "text/plain", width="stretch")
        c2.download_button("Download tree nodes", tree_nodes.to_csv(index=False).encode(), "outbreak_tree_nodes.csv", "text/csv", width="stretch")
    except Exception as exc:
        st.warning(f"Tree construction could not complete: {exc}")

    section_title("Audited external pathogen tools", "⚙")
    status_rows = [verified_tool_status(name) for name in ["mash", "iqtree", "amrfinderplus"]]
    smart_dataframe(pd.DataFrame(status_rows), height=240, key="outbreak_tool_status")
    with st.form("outbreak_external_tool_form"):
        selected_tool = st.selectbox("Tool", ["mash", "iqtree", "amrfinderplus"])
        input_path = st.text_input("Local input path", help="Use a FASTA/FASTQ/alignment/protein file appropriate for the selected tool.")
        output_dir = st.text_input("Evidence directory", str(ROOT / "reports" / "tool_runs" / "outbreak"))
        extra_arguments = st.text_input("Additional arguments", help="Parsed as an argument vector; no shell interpolation is used.")
        run_external = st.form_submit_button("Run selected tool with audit evidence", width="stretch")
    if run_external:
        source_path = Path(input_path).expanduser()
        if not source_path.is_file():
            st.error("Choose an existing local input file.")
        else:
            try:
                if selected_tool == "mash":
                    arguments = ["dist", str(source_path), str(source_path)]
                elif selected_tool == "iqtree":
                    arguments = ["-s", str(source_path), "-nt", "AUTO", "-redo"]
                else:
                    arguments = ["-p", str(source_path)]
                arguments.extend(shlex.split(extra_arguments, posix=False))
                execution = run_tool_audited(
                    selected_tool,
                    arguments,
                    run_directory=Path(output_dir).expanduser(),
                    cwd=source_path.parent,
                    timeout_seconds=7200,
                )
                st.success(f"{selected_tool} completed with immutable execution evidence.")
                smart_json(execution.to_dict(), key="98_execution_manifest")
                manifest_payload = Path(execution.manifest_path).read_bytes()
                st.download_button("Download execution manifest", manifest_payload, Path(execution.manifest_path).name, "application/json")
            except Exception as exc:
                st.error(str(exc))
                st.caption("The failure log and manifest are retained when the registered executable starts but exits unsuccessfully.")

with timeline_tab:
    timeline = clustered.sort_values("collection_date")
    st.plotly_chart(px.scatter(timeline, x="collection_date", y="outbreak_cluster", color="outbreak_cluster", hover_name="sample_id", size="cluster_size", title="Collection timeline by provisional cluster"), width="stretch")
    if not links.empty:
        top_links = links.sort_values("link_score", ascending=False).head(100)
        st.plotly_chart(px.scatter(top_links, x="days_apart", y="snp_distance", size="link_score", color="distance_km", hover_data=["source", "target"], title="Genomic, temporal and geographic link landscape"), width="stretch")

with audit_tab:
    section_title("Cluster-level summary", "◎")
    smart_dataframe(cluster_summary, height=360, key="outbreak_cluster_summary")
    section_title("Candidate links", "↔")
    smart_dataframe(links.sort_values("link_score", ascending=False), height=430, key="outbreak_candidate_links")
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("Export clustered samples", clustered.to_csv(index=False).encode(), "outbreak_clustered_samples.csv", "text/csv", width="stretch")
    with c2:
        st.download_button("Export candidate links", links.to_csv(index=False).encode(), "outbreak_candidate_links.csv", "text/csv", width="stretch")
    insight_callout("Interpretation rule", "Treat clusters and link scores as investigation priorities—not proof of transmission. Review sequencing QC, recombination, within-host diversity, patient movement and sampling completeness.", tone="warning")

# Step 99 module excellence layer
render_outbreak_excellence(clustered, result["distance_matrix"], links)

# Step 100 professional integration and optimization layer
render_outbreak_professional(clustered, result["distance_matrix"])

# Step 110 advanced scientific viewers
from biointel.ui.advanced_scientific_viewers import render_embedded_viewer as _render_step110_viewer

_render_step110_viewer("phylogenetic_tree", key_prefix="step110_98_Pathogen_Outbreak_Command_Center_phylogenetic_tree")
_render_step110_viewer("outbreak_map", key_prefix="step110_98_Pathogen_Outbreak_Command_Center_outbreak_map")

# Step 115 scientific depth, validation and optimization layer
from biointel.scientific_depth import render_depth_upgrade_panel as _render_step114_depth

_render_step114_depth("pathogen_outbreak_core", None, key_prefix="step114_pathogen_outbreak_core", expanded=False)

# Step 115 non-chart visual: phylogeny_canvas
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("phylogeny_canvas", key_prefix="step115_98_Pathogen_Outbreak_Command_Center_phylogeny_canvas", expanded=False)

# Step 115 non-chart visual: outbreak_map_canvas
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("outbreak_map_canvas", key_prefix="step115_98_Pathogen_Outbreak_Command_Center_outbreak_map_canvas", expanded=False)

# STEP127_SCIENTIFIC_DEPTH_PATHOGEN_OUTBREAK
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('pathogen_outbreak', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='pathogen_outbreak', title='Pathogen Outbreak Genomics Command Center', category='Bioinformatics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='pathogen_outbreak', title='Pathogen Outbreak Genomics Command Center', category='Bioinformatics')

# STEP177_21_MODULE_MODEL_COHORT_RUNTIME_EXCELLENCE
from biointel.target_modules_v177.ui import render_step177_module_upgrade
render_step177_module_upgrade('pathogen_outbreak_core', expanded=False)

# Step 183 all-module synthetic demo bundle
from biointel.portfolio_demo_v183.ui import render_step183_portfolio_demo as _render_step183_portfolio_demo
_render_step183_portfolio_demo("pathogen_outbreak_core", expanded=False)

# Step 184 advanced deterministic demo assurance
from biointel.demo_assurance_v184.ui import render_step184_demo_assurance as _render_step184_demo_assurance
_render_step184_demo_assurance("pathogen_outbreak_core", expanded=False)

# STEP188_MAJOR_MODULE_STANDARD_HOOK
from biointel.major_module_standard_v188.ui import render_step188_major_module_standard as _render_step188_major_module_standard
_render_step188_major_module_standard('pathogen_outbreak_core', expanded=False)

# STEP189_UNIVERSAL_PLATFORM_HOOK
from biointel.universal_platform_v189.ui import render_step189_universal_platform as _render_step189_universal_platform
_render_step189_universal_platform('pathogen_outbreak_core', expanded=False)

# STEP190_SCIENTIFIC_EXECUTION_HOOK
from biointel.scientific_execution_v190.ui import render_step190_scientific_execution as _render_step190_scientific_execution
_render_step190_scientific_execution('pathogen_outbreak_core', expanded=False)

# STEP192_RELEASE_INTEGRITY_PUBLICATION_HOOK
from biointel.release_integrity_v192.ui import render_step192_release_integrity as _render_step192_release_integrity
_render_step192_release_integrity('pathogen_outbreak_core', expanded=False)


# STEP193_MANDATORY_COMPLETION_HOOK
from biointel.mandatory_completion_v193.ui import render_step193_mandatory_completion as _render_step193_mandatory_completion
_render_step193_mandatory_completion('pathogen_outbreak_core', expanded=False)

