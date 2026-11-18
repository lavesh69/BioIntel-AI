from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.systems.pathways import (
    PATHWAY_PACK_VERSION,
    interaction_edges,
    network_metrics,
    parse_gmt,
    pathway_enrichment,
    pathway_pack,
    preranked_gsea,
)
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe
from biointel.ui.scientific_visuals import render_generic_visual_explorer
from biointel.ui.theme import apply_theme, hero
from biointel.ui.workflow import analysis_run, render_methodology, render_upload_preflight

st.set_page_config(page_title="Pathway & Network Analysis · BioIntel AI", page_icon="🕸️", layout="wide")
apply_theme()

from biointel.ui.scientific_integrations import render_page_integrations as _render_biointel_integrations
_render_biointel_integrations("pages/63_Pathway_Network_Analysis.py", key_prefix="63_pathway_network_analysis", expanded=False)

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("pathway", key_prefix="step116_63_Pathway_Network_Analysis_pathway_1", expanded=False)
hero(
    "Pathway & Network Analysis",
    "Run background-corrected over-representation analysis, ranked GSEA and pathway-derived network centrality with organism-aware, versioned local reference packs or custom GMT files.",
    eyebrow="BioIntel AI · Systems Biology",
    chips=["ORA", "Preranked GSEA", "Organism packs", "FDR", "Network centrality"],
)
scientific_boundary_banner(
    source_kind="versioned_local_reference",
    release_eligible=False,
    message=(
        f"Bundled pathway pack {PATHWAY_PACK_VERSION} is an offline reviewed reference. "
        "Publication work should record the exact source release and may import a study-approved GMT file."
    ),
)
render_methodology(
    method="Universe-corrected hypergeometric ORA, permutation-based preranked GSEA and co-membership network analysis.",
    assumptions=[
        "Identifiers are normalized gene symbols or mapped aliases.",
        "The background universe reflects genes that could have been measured.",
    ],
    limitations=[
        "Co-membership edges are not physical-interaction evidence.",
        "Bundled packs are compact and replaceable, not a full online pathway mirror.",
    ],
    validation=[
        "Use a versioned GMT release, preserve the tested universe and review leading-edge genes."
    ],
)

mode = st.radio(
    "Analysis mode", ["Over-representation analysis", "Preranked GSEA"], horizontal=True
)
custom_gmt = st.file_uploader("Optional custom GMT pathway pack", type=["gmt", "txt"])
render_upload_preflight(
    custom_gmt,
    key="pathway_gmt",
    allowed_extensions=["gmt", "txt"],
    soft_limit_mb=10,
    hard_limit_mb=50,
)

with st.form("pathway_form"):
    organism = st.selectbox(
        "Organism context", ["Homo sapiens", "Mus musculus", "Generic reference"]
    )
    default = "TP53, BRCA1, ATM, RAD51, PIK3CA, AKT1, PTEN, MTOR, KRAS, BRAF, MAPK1"
    genes_text = st.text_area(
        "Gene symbols", default, height=130, disabled=mode == "Preranked GSEA"
    )
    ranked_text = st.text_area(
        "Ranked genes (gene,score; one per line)",
        "TP53,3.2\nBRCA1,2.8\nATM,1.9\nRAD51,1.3\nAKT1,0.5\nPTEN,-0.8\nKRAS,-1.2\nBRAF,-2.1",
        height=160,
        disabled=mode != "Preranked GSEA",
    )
    background_text = st.text_area(
        "Optional measured/background gene universe",
        "",
        height=90,
        disabled=mode == "Preranked GSEA",
        help="Each pathway and the submitted query are intersected with this universe before statistics are calculated.",
    )
    cols = st.columns(4)
    minimum_overlap = cols[0].number_input("Minimum overlap", 1, 50, 1)
    maximum_pathways = cols[1].number_input("Maximum pathways", 5, 500, 50)
    permutations = cols[2].number_input("GSEA permutations", 20, 5000, 500, step=20)
    fdr_cutoff = cols[3].number_input("FDR display cutoff", 0.001, 1.0, 0.25, step=0.01)
    run = st.form_submit_button("Run pathway analysis", type="primary", width="stretch")

if not run:
    st.info(
        "Configure a gene list or ranked table and submit the form. Analysis runs only when requested."
    )
    st.stop()

try:
    pathways = (
        parse_gmt(custom_gmt.getvalue().decode("utf-8-sig"))
        if custom_gmt
        else pathway_pack(organism)
    )
    with analysis_run("Calculating enrichment, FDR and network statistics"):
        if mode == "Over-representation analysis":
            genes = [
                gene.strip().upper()
                for gene in genes_text.replace("\n", ",").split(",")
                if gene.strip()
            ]
            background = {
                gene.strip().upper()
                for gene in background_text.replace("\n", ",").split(",")
                if gene.strip()
            } or None
            results = pathway_enrichment(genes, pathways=pathways, universe=background)
            results = results[results["overlap_count"] >= int(minimum_overlap)]
            network_genes = genes
        else:
            rows = []
            for line in ranked_text.splitlines():
                if not line.strip():
                    continue
                gene, separator, score = line.replace("\t", ",").partition(",")
                if not separator:
                    raise ValueError(f"Ranked line requires gene,score: {line}")
                rows.append({"gene": gene.strip(), "score": float(score.strip())})
            ranked = pd.DataFrame(rows)
            results = preranked_gsea(ranked, pathways=pathways, permutations=int(permutations))
            network_genes = ranked["gene"].tolist()
            background = None
        results = results.head(int(maximum_pathways)).reset_index(drop=True)
        edges = interaction_edges(network_genes, pathways)
        metrics = network_metrics(edges)
except Exception as exc:
    st.error(f"Pathway analysis could not be completed: {exc}")
    st.stop()

significant = int(
    (
        pd.to_numeric(results.get("fdr_bh", pd.Series(dtype=float)), errors="coerce")
        <= float(fdr_cutoff)
    ).sum()
)
metric_cards(
    [
        ("Reference pathways", len(pathways), organism if not custom_gmt else "Custom GMT"),
        ("Reported pathways", len(results), None),
        (f"FDR ≤ {fdr_cutoff:g}", significant, None),
        ("Network edges", len(edges), "Co-membership evidence"),
    ]
)

tabs = st.tabs(["Enrichment", "Network", "Centrality", "Reference audit", "Exports"])
with tabs[0]:
    smart_dataframe(results, height=520)
    render_generic_visual_explorer(
        results,
        key="pathway_enrichment_visuals",
        secondary=metrics if "metrics" in locals() else None,
        heading="Pathway enrichment visual analytics",
    )
    if not results.empty:
        score_col = (
            "normalized_enrichment_score"
            if "normalized_enrichment_score" in results
            else "enrichment_ratio"
        )
        chart = results.head(25).copy()
        st.bar_chart(chart.set_index("pathway")[score_col])
with tabs[1]:
    smart_dataframe(edges, height=300)
    if not edges.empty:
        nodes = sorted(set(edges["source"]) | set(edges["target"]))
        positions = {
            node: (
                math.cos(2 * math.pi * index / max(len(nodes), 1)),
                math.sin(2 * math.pi * index / max(len(nodes), 1)),
            )
            for index, node in enumerate(nodes)
        }
        edge_x, edge_y = [], []
        for row in edges.itertuples(index=False):
            x0, y0 = positions[row.source]
            x1, y1 = positions[row.target]
            edge_x += [x0, x1, None]
            edge_y += [y0, y1, None]
        figure = go.Figure()
        figure.add_trace(
            go.Scatter(x=edge_x, y=edge_y, mode="lines", hoverinfo="none", line={"width": 1})
        )
        sizes = {
            row.gene: 12 + 6 * row.degree_centrality for row in metrics.itertuples(index=False)
        }
        figure.add_trace(
            go.Scatter(
                x=[positions[node][0] for node in nodes],
                y=[positions[node][1] for node in nodes],
                text=nodes,
                mode="markers+text",
                textposition="top center",
                marker={"size": [sizes.get(node, 12) for node in nodes]},
            )
        )
        figure.update_layout(
            title="Pathway co-membership network",
            showlegend=False,
            xaxis={"visible": False},
            yaxis={"visible": False},
        )
        st.plotly_chart(figure, width="stretch")
with tabs[2]:
    smart_dataframe(metrics, height=500)
with tabs[3]:
    reference_rows = [
        {
            "pathway": name,
            "genes": len(members),
            "version": PATHWAY_PACK_VERSION,
            "source": "custom_gmt" if custom_gmt else organism,
        }
        for name, members in pathways.items()
    ]
    smart_dataframe(reference_rows, height=500)
with tabs[4]:
    st.download_button(
        "Download pathway results",
        results.to_csv(index=False),
        "pathway_results.csv",
        "text/csv",
        width="stretch",
    )
    st.download_button(
        "Download network edges",
        edges.to_csv(index=False),
        "pathway_network_edges.csv",
        "text/csv",
        width="stretch",
    )
    st.download_button(
        "Download network centrality",
        metrics.to_csv(index=False),
        "pathway_network_metrics.csv",
        "text/csv",
        width="stretch",
    )

# STEP127_SCIENTIFIC_DEPTH_PATHWAY_NETWORK
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('pathway_network', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='pathway_network', title='Pathway & Network Analysis', category='Discovery')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='pathway_network', title='Pathway & Network Analysis', category='Discovery')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
