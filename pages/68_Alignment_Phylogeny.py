from __future__ import annotations

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

from biointel.genomics.external_tools import run_mafft
from biointel.genomics.phylogeny import consensus_sequence, validate_alignment
from biointel.genomics.phylogeny_advanced import (
    bootstrap_tree,
    build_tree,
    codon_partition_audit,
    external_phylogeny_tools,
    progressive_star_alignment,
    root_tree,
    tree_newick,
    trim_alignment,
)
from biointel.sequence.parser import parse_sequences_text
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe
from biointel.ui.scientific_visuals import render_generic_visual_explorer
from biointel.ui.theme import apply_theme, hero
from biointel.ui.workflow import (
    analysis_run,
    read_uploaded_text,
    render_methodology,
    render_upload_preflight,
)

DEMO = ROOT / "data" / "bioinformatics_demo" / "demo_alignment.fasta"
st.set_page_config(page_title="Alignment & Phylogeny · BioIntel AI", page_icon="🌳", layout="wide")
apply_theme()
hero(
    "Alignment & Phylogeny",
    "Align raw homologous sequences or validate an existing alignment, trim low-information columns, fit evolutionary distances, build NJ/UPGMA trees, root by outgroup or midpoint and calculate bootstrap support.",
    eyebrow="BioIntel AI · Comparative Genomics",
    chips=[
        "Internal MSA",
        "Optional MAFFT",
        "NJ / UPGMA",
        "JC69 / Poisson",
        "Bootstrap",
        "Real rooting",
    ],
)
scientific_boundary_banner(
    source_kind="local_analysis",
    release_eligible=False,
    message="The in-process alignment and distance trees are reproducible local workflows. Publication-grade claims should be confirmed with an appropriate ML/Bayesian package and recorded model/version evidence.",
)
render_methodology(
    method="Progressive/star alignment fallback or optional local MAFFT, column trimming, model-aware pairwise distances, NJ/UPGMA trees and non-parametric bootstrap support.",
    assumptions=[
        "Input sequences are homologous.",
        "The selected model is appropriate for the sequence type and divergence.",
    ],
    limitations=[
        "Distance methods are not full maximum-likelihood inference.",
        "The internal MSA is designed for local robustness, not very large phylogenomic alignments.",
    ],
    validation=[
        "Inspect alignment quality, support values, recombination risk and reproduce final trees in a specialist package."
    ],
)

uploaded = st.file_uploader("FASTA alignment or raw homologous FASTA", type=["fasta", "fa", "aln"])
render_upload_preflight(
    uploaded,
    key="alignment_fasta",
    allowed_extensions=["fasta", "fa", "aln"],
    soft_limit_mb=25,
    hard_limit_mb=150,
)
text = read_uploaded_text(uploaded) if uploaded else DEMO.read_text(encoding="utf-8")
records = parse_sequences_text(text, max_records=10_000)
sequences = {
    record.header or f"seq_{index + 1}": record.sequence for index, record in enumerate(records)
}

with st.form("phylogeny_form"):
    controls = st.columns(5)
    input_state = controls[0].selectbox("Input state", ["Already aligned", "Raw / unaligned"])
    alignment_engine = controls[1].selectbox(
        "Alignment engine",
        ["Internal progressive", "MAFFT if installed"],
        disabled=input_state == "Already aligned",
    )
    tree_method = controls[2].selectbox("Tree method", ["neighbor-joining", "upgma"])
    sequence_symbols = set().union(*(set(value.upper()) for value in sequences.values())) - {
        "-",
        "?",
    }
    nucleotide = sequence_symbols.issubset(set("ACGTUNRYSWKMBDHVX"))
    model_options = ["p-distance", "jukes-cantor"] if nucleotide else ["p-distance", "poisson"]
    model = controls[3].selectbox("Distance model", model_options)
    bootstrap_replicates = controls[4].number_input("Bootstrap replicates", 10, 2000, 100, 10)
    trimming = st.columns(4)
    maximum_gap = trimming[0].slider("Maximum gap fraction", 0.0, 1.0, 0.50, 0.05)
    minimum_major = trimming[1].slider("Minimum major-allele fraction", 0.0, 1.0, 0.0, 0.05)
    rooting = trimming[2].selectbox("Rooting", ["Unrooted", "Midpoint", "Outgroup"])
    outgroup = trimming[3].selectbox("Outgroup", list(sequences), disabled=rooting != "Outgroup")
    consensus_fraction = st.slider("Consensus minimum fraction", 0.50, 1.00, 0.60, 0.05)
    run = st.form_submit_button("Build supported phylogeny", type="primary", width="stretch")

if not run:
    lengths = [len(value) for value in sequences.values()]
    metric_cards(
        [
            ("Sequences", len(sequences), None),
            ("Maximum length", max(lengths) if lengths else 0, None),
            ("Unique lengths", len(set(lengths)), "1 indicates pre-aligned input"),
            ("Input source", uploaded.name if uploaded else "Bundled reference", None),
        ]
    )
    smart_dataframe(external_phylogeny_tools(), height=220)
    st.info(
        "Submit the workflow to align/validate, trim, calculate distances, bootstrap and root the tree."
    )
    st.stop()

try:
    with analysis_run("Aligning, trimming and bootstrapping phylogeny"):
        if input_state == "Already aligned":
            aligned = validate_alignment(sequences)
            alignment_source = "uploaded/already aligned"
        elif alignment_engine == "MAFFT if installed":
            try:
                mafft_text = run_mafft(text, timeout_seconds=600)
                mafft_records = parse_sequences_text(mafft_text, max_records=10_000)
                aligned = validate_alignment(
                    {record.header: record.sequence for record in mafft_records}
                )
                alignment_source = "local MAFFT"
            except Exception:
                aligned = progressive_star_alignment(sequences)
                alignment_source = "internal progressive fallback"
        else:
            aligned = progressive_star_alignment(sequences)
            alignment_source = "internal progressive"
        trimmed, trim_audit = trim_alignment(
            aligned,
            maximum_gap_fraction=float(maximum_gap),
            minimum_major_fraction=float(minimum_major),
        )
        if int(bootstrap_replicates) > 0:
            tree, support = bootstrap_tree(
                trimmed,
                replicates=int(bootstrap_replicates),
                method=tree_method,
                model=model,
            )
            _, matrix = build_tree(trimmed, method=tree_method, model=model)
        else:
            tree, matrix = build_tree(trimmed, method=tree_method, model=model)
            support = pd.DataFrame()
        tree = root_tree(
            tree,
            outgroup=outgroup if rooting == "Outgroup" else None,
            midpoint=rooting == "Midpoint",
        )
        newick = tree_newick(tree)
        consensus = consensus_sequence(trimmed, minimum_fraction=consensus_fraction)
except Exception as exc:
    st.error(f"Phylogeny workflow stopped safely: {exc}")
    st.stop()

values = matrix.to_numpy(float)
off_diagonal = values[~np.eye(len(matrix), dtype=bool)] if len(matrix) > 1 else np.array([0.0])
metric_cards(
    [
        ("Sequences", len(trimmed), alignment_source),
        ("Aligned columns", len(next(iter(aligned.values()))), None),
        (
            "Retained columns",
            len(next(iter(trimmed.values()))),
            f"{100 * len(next(iter(trimmed.values()))) / len(next(iter(aligned.values()))):.1f}%",
        ),
        ("Mean distance", f"{float(off_diagonal.mean()):.4f}", model),
        ("Tree", tree_method.upper(), rooting),
    ]
)


def tree_figure(tree):
    terminals = tree.get_terminals()
    y_positions = {terminal.name: index for index, terminal in enumerate(reversed(terminals))}
    x_positions: dict[object, float] = {}

    def place(clade, x=0.0):
        x_positions[clade] = x
        for child in clade.clades:
            place(child, x + float(child.branch_length or 0.0))

    def y_of(clade):
        if clade.is_terminal():
            return y_positions.get(clade.name, 0)
        return sum(y_of(child) for child in clade.clades) / max(len(clade.clades), 1)

    place(tree.root)
    figure = go.Figure()
    for clade in tree.find_clades(order="preorder"):
        if not clade.clades:
            continue
        parent_x = x_positions[clade]
        child_ys = [y_of(child) for child in clade.clades]
        figure.add_trace(
            go.Scatter(
                x=[parent_x, parent_x],
                y=[min(child_ys), max(child_ys)],
                mode="lines",
                showlegend=False,
                hoverinfo="skip",
            )
        )
        for child in clade.clades:
            child_x, child_y = x_positions[child], y_of(child)
            label = (
                f"{float(child.confidence):.0f}%"
                if getattr(child, "confidence", None) is not None
                else ""
            )
            figure.add_trace(
                go.Scatter(
                    x=[parent_x, child_x],
                    y=[child_y, child_y],
                    mode="lines",
                    text=[label, label],
                    showlegend=False,
                    hovertemplate="%{text}<extra></extra>",
                )
            )
    figure.add_trace(
        go.Scatter(
            x=[x_positions[terminal] for terminal in terminals],
            y=[y_positions[terminal.name] for terminal in terminals],
            mode="markers+text",
            text=[terminal.name for terminal in terminals],
            textposition="middle right",
            showlegend=False,
        )
    )
    figure.update_layout(
        title=f"{tree_method.upper()} tree · {model} · {rooting}",
        xaxis_title="Evolutionary distance",
        yaxis={"showticklabels": False},
        height=max(520, len(terminals) * 24),
        margin={"r": 220},
    )
    return figure


tabs = st.tabs(
    [
        "Tree",
        "Bootstrap",
        "Distance heatmap",
        "Alignment QC",
        "Consensus",
        "Codon audit",
        "Tools",
        "Exports",
    ]
)
with tabs[0]:
    st.plotly_chart(tree_figure(tree), width="stretch")
with tabs[1]:
    if support.empty:
        st.info("Bootstrap support is unavailable.")
    else:
        smart_dataframe(support, height=440)
        st.bar_chart(support.set_index("clade")["bootstrap_support"])
        render_generic_visual_explorer(
            support,
            key="phylogeny_bootstrap_visuals",
            heading="Bootstrap support visual analytics",
        )
with tabs[2]:
    st.plotly_chart(
        px.imshow(
            matrix,
            text_auto=".3f" if len(matrix) <= 30 else False,
            aspect="auto",
            title=f"Pairwise {model} distance",
        ),
        width="stretch",
    )
with tabs[3]:
    smart_dataframe(trim_audit, height=420)
    render_generic_visual_explorer(
        trim_audit,
        key="alignment_qc_visuals",
        heading="Alignment QC visual analytics",
    )
    alignment_frame = pd.DataFrame(
        {"sequence": list(trimmed), "aligned_sequence": list(trimmed.values())}
    )
    smart_dataframe(alignment_frame, height=320)
with tabs[4]:
    st.code(consensus, language="text")
    conservation = []
    for index, column in enumerate(zip(*trimmed.values()), start=1):
        counts = pd.Series(column).value_counts(normalize=True)
        conservation.append({"position": index, "major_fraction": float(counts.iloc[0])})
    st.plotly_chart(
        px.line(
            pd.DataFrame(conservation),
            x="position",
            y="major_fraction",
            title="Alignment conservation",
        ),
        width="stretch",
    )
with tabs[5]:
    if nucleotide:
        try:
            smart_dataframe(codon_partition_audit(trimmed), height=260)
        except Exception as exc:
            st.info(f"Codon partition audit unavailable: {exc}")
    else:
        st.info("Codon partitioning applies to nucleotide coding alignments.")
with tabs[6]:
    smart_dataframe(external_phylogeny_tools(), height=260)
with tabs[7]:
    aligned_fasta = "\n".join(f">{name}\n{sequence}" for name, sequence in trimmed.items()) + "\n"
    st.download_button(
        "Download rooted Newick", newick + "\n", "supported_tree.nwk", "text/plain", width="stretch"
    )
    st.download_button(
        "Download trimmed alignment",
        aligned_fasta,
        "trimmed_alignment.fasta",
        "text/plain",
        width="stretch",
    )
    st.download_button(
        "Download distances",
        matrix.to_csv(),
        "evolutionary_distance_matrix.csv",
        "text/csv",
        width="stretch",
    )
    st.download_button(
        "Download bootstrap support",
        support.to_csv(index=False),
        "bootstrap_support.csv",
        "text/csv",
        width="stretch",
    )

# Step 110 advanced scientific viewers
from biointel.ui.advanced_scientific_viewers import render_embedded_viewer as _render_step110_viewer

_render_step110_viewer("phylogenetic_tree", key_prefix="step110_68_Alignment_Phylogeny_phylogenetic_tree")


# Step 112 shared bioinformatics feature upgrades
from biointel.ui.bioinformatics_upgrades import render_bioinformatics_upgrade_panel
render_bioinformatics_upgrade_panel("phylogeny", expanded=False)

# Step 115 non-chart visual: phylogeny_canvas
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("phylogeny_canvas", key_prefix="step115_68_Alignment_Phylogeny_phylogeny_canvas", expanded=False)

# STEP127_SCIENTIFIC_DEPTH_ALIGNMENT_PHYLOGENY
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('alignment_phylogeny', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='alignment_phylogeny', title='Alignment & Phylogeny', category='Bioinformatics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='alignment_phylogeny', title='Alignment & Phylogeny', category='Bioinformatics')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
