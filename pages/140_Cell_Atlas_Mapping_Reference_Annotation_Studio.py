from __future__ import annotations

from dataclasses import asdict

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

from biointel.nextgen.renderer import render_nextgen_module
from biointel.ui.theme import apply_theme
from biointel.neuro_cns.brain_cell_spatial_atlas import BrainCellSpatialAtlasStudio

st.set_page_config(page_title='3D Brain Cell & Spatial Atlas Studio · BioIntel AI', page_icon='🗺️', layout="wide")
apply_theme()

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK - TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('cell_atlas_mapping', expanded=False)

st.title("🗺️ 3D Brain Cell & Spatial Atlas Studio")
st.caption("BioIntel AI 15.6.0 · Biology, Engineered into Intelligence. Owner: Lavesh Dobriyal")

studio = BrainCellSpatialAtlasStudio(str(ROOT / "UserData" / "spatial_atlas"))

t_3d, t_connectors, t_lr, t_mouse, t_nextgen = st.tabs([
    "🧠 P0 3D Interactive Brain Cell Atlas",
    "🔌 Atlas Connectors & Census Registry",
    "🔬 Spatial Ligand-Receptor Interactions",
    "🐭 Mouse ↔ Human Ortholog Mapping",
    "📊 Legacy Cell Atlas Workbench"
])

with t_3d:
    st.subheader("3D Anatomical Brain Cell Point-Cloud Visualizer")
    st.write("Renders 3D cell coordinates, UBERON region annotations, and marker expression across spatial anatomical volumes.")

    c1, c2 = st.columns([1, 3])
    with c1:
        num_cells = st.slider("Cell Sampling Density", 100, 2000, 400)
        color_by = st.selectbox("Color Point Cloud By", ["cell_type", "brain_region_uberon", "expression_marker"])
        if st.button("Generate 3D Spatial Render", type="primary"):
            st.rerun()

    with c2:
        cells = studio.generate_3d_brain_cell_pointcloud(num_cells)
        cells_df = pd.DataFrame([asdict(c) for c in cells])

        fig = px.scatter_3d(
            cells_df,
            x="x", y="y", z="z",
            color=color_by,
            size="expression_marker",
            hover_data=["cell_id", "cell_type", "brain_region_uberon"],
            title="3D Brain Anatomical Spatial Point Cloud (Plotly 3D)"
        )
        fig.update_layout(margin=dict(l=0, r=0, b=0, t=30), height=550)
        st.plotly_chart(fig, use_container_width=True)

with t_connectors:
    st.subheader("Reference Atlas Connectors & CELLxGENE Census Registry")
    conn_status = studio.get_atlas_connector_status()
    
    conn_df = pd.DataFrame([
        {
            "Atlas Name": meta.atlas_name,
            "Version": meta.version,
            "Access Protocol": meta.access_protocol,
            "Total Cell Count": f"{meta.num_cells:,}",
            "Modalities": ", ".join(meta.modalities),
            "Brain Regions": ", ".join(meta.brain_regions[:3])
        }
        for meta in conn_status.values()
    ])
    st.dataframe(conn_df, use_container_width=True, hide_index=True)

with t_lr:
    st.subheader("Spatial Microenvironment Ligand-Receptor Communications")
    lr_df = studio.compute_ligand_receptor_interactions(["Microglia", "Astrocytes", "Neurons"])
    st.dataframe(lr_df, use_container_width=True, hide_index=True)

with t_mouse:
    st.subheader("Mouse ↔ Human Cross-Species Cell Homology Mapping")
    mouse_input = st.text_area("Mouse Gene Symbols (Comma-separated)", "Grn, Trem2, Apoe, Tyrobp, C1qa")
    mouse_list = [g.strip() for g in mouse_input.split(",") if g.strip()]
    if mouse_list:
        ortholog_df = studio.mouse_to_human_ortholog_mapping(mouse_list)
        st.dataframe(ortholog_df, hide_index=True)

with t_nextgen:
    # STEP196_P0_P1_PRIORITY_UPGRADE_HOOK
    from biointel.proof_gates_v10.ui import render_module_priority_workbench as _render_step196_p0_p1_priority_workbench
    _render_step196_p0_p1_priority_workbench(ROOT, 'cell_atlas_mapping', expanded=False)

    render_nextgen_module('cell_atlas_mapping')
