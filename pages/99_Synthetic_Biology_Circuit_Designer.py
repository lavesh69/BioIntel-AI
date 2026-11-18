from __future__ import annotations

import json
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

from biointel.innovation.engines import PART_LIBRARY, build_construct, simulate_circuit
from biointel.innovation.advanced_engines import (
    codon_optimize, construct_quality, genbank_flatfile, gibson_primer_plan,
)
from biointel.innovation.excellence_ui import render_synthetic_biology_excellence
from biointel.innovation.professional_ui import render_synthetic_biology_professional
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json
from biointel.ui.scientific_visuals import render_generic_visual_explorer
from biointel.ui.theme import apply_theme, hero, insight_callout, section_title

st.set_page_config(page_title="Synthetic Biology & Genetic Circuit Designer · BioIntel AI", page_icon="🧪", layout="wide")
apply_theme()

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK · TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('synthetic_biology_circuit', expanded=False)

# STEP196_P0_P1_PRIORITY_UPGRADE_HOOK
from biointel.proof_gates_v10.ui import render_module_priority_workbench as _render_step196_p0_p1_priority_workbench
_render_step196_p0_p1_priority_workbench(ROOT, 'synthetic_biology_circuit', expanded=False)
# STEP178_19_MODULE_CLINICAL_OPERATIONAL_PRIVACY_ML_ASSURANCE
from biointel.target_modules_v178.ui import render_step178_module_upgrade
render_step178_module_upgrade('synthetic_biology_circuit', expanded=False)


# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("synthetic_biology", key_prefix="step116_99_Synthetic_Biology_Circuit_Designer_synthetic_biology_1", expanded=False)
hero(
    "Synthetic Biology & Genetic Circuit Designer Pro",
    "Design ordered constructs, simulate logic behaviour, audit synthesis risks, prepare Gibson primers, optimize coding regions and export FASTA/GenBank/SBOL-style records.",
    eyebrow="Step 99 · Synthetic biology upgrade",
    chips=["Construct map", "Synthesis QC", "Gibson primers", "Codon optimization", "GenBank", "Logic simulation"],
)
scientific_boundary_banner(source_kind="demo_reference", release_eligible=False, message="Circuit simulations and sequence checks are design aids. Confirm host compatibility, biosafety, synthesis constraints, intellectual-property obligations and experimental performance before use.")

builder_tab, qc_tab, assembly_tab, coding_tab, export_tab = st.tabs(["1 · Build", "2 · Synthesis QC", "3 · Assembly", "4 · Coding optimization", "5 · Export"])
with builder_tab:
    left, right = st.columns([1, 1.6])
    with left:
        parts = st.multiselect("Ordered genetic parts", list(PART_LIBRARY), default=["pLac promoter", "Strong RBS", "GFP CDS", "Double terminator"])
        gate = st.selectbox("Logic behaviour", ["AND", "OR", "NOT A", "NAND", "Direct"])
        inducer_a = st.slider("Input A", 0.0, 1.0, 0.8, 0.05)
        inducer_b = st.slider("Input B", 0.0, 1.0, 0.65, 0.05)
    try:
        sequence, architecture, metrics = build_construct(parts)
        quality = construct_quality(sequence)
    except Exception as exc:
        st.error(f"Construct build failed: {exc}")
        st.stop()
    metric_cards([
        ("Construct length", f"{metrics['length']:,} bp", None), ("Parts", metrics["parts"], None),
        ("GC", f"{metrics['gc']:.1f}%", None), ("Synthesis score", f"{quality['quality_score']:.0f}/100", None),
        ("Restriction sites", len(quality["restriction_sites"]), None), ("Homopolymers", len(quality["homopolymers"]), None),
    ])
    with right:
        plot = architecture.copy()
        plot["midpoint"] = (plot["start"] + plot["end"]) / 2
        fig = go.Figure()
        for row in plot.itertuples(index=False):
            fig.add_trace(go.Bar(x=[row.length], y=["Construct"], base=[row.start], orientation="h", name=row.part, hovertemplate=f"{row.part}<br>{row.start}-{row.end}<extra></extra>"))
        fig.update_layout(barmode="stack", height=280, title="Linear construct architecture", xaxis_title="Position (bp)")
        st.plotly_chart(fig, width="stretch")
    simulation = simulate_circuit(parts, inducer_a, inducer_b, gate)
    st.plotly_chart(px.line(simulation, x="time_h", y="predicted_expression", title=f"Predicted {gate} gate response"), width="stretch")
    smart_dataframe(architecture, height=310, key="synbio_architecture_pro")
    render_generic_visual_explorer(
        simulation,
        key="synbio_simulation_visuals",
        secondary=architecture,
        heading="Circuit simulation visual analytics",
    )

with qc_tab:
    c1, c2 = st.columns(2)
    with c1:
        gc_windows = quality["gc_windows"]
        st.plotly_chart(px.line(gc_windows, x="start", y="gc", markers=True, title="Sliding-window GC profile"), width="stretch")
        smart_dataframe(quality["restriction_sites"], height=300, key="synbio_restriction_sites_pro")
        render_generic_visual_explorer(
            gc_windows,
            key="synbio_qc_visuals",
            secondary=quality["restriction_sites"],
            heading="Construct QC visual analytics",
        )
    with c2:
        if quality["homopolymers"].empty:
            st.success("No homopolymer runs ≥7 bp detected.")
        else:
            smart_dataframe(quality["homopolymers"], height=260, key="synbio_homopolymers")
        if quality["repeats"].empty:
            st.success("No duplicated 12-mer repeats detected at separated positions.")
        else:
            smart_dataframe(quality["repeats"].head(200), height=260, key="synbio_repeats")
    smart_json({k: v for k, v in quality.items() if not isinstance(v, pd.DataFrame)}, key="synbio_quality_json")

with assembly_tab:
    overlap = st.slider("Gibson overlap length", 15, 60, 25)
    body = st.slider("Primer annealing body", 15, 35, 20)
    primers = gibson_primer_plan(parts, overlap, body)
    smart_dataframe(primers, height=430, key="gibson_primers")
    st.download_button("Export Gibson primer plan", primers.to_csv(index=False).encode(), "gibson_primer_plan.csv", "text/csv")
    insight_callout("Assembly review", "Check primer melting temperature, secondary structure, synthesis limits and part-junction biology with a validated primer-design tool before ordering.", tone="info")

with coding_tab:
    coding_parts = [name for name in parts if "CDS" in name]
    if not coding_parts:
        st.info("Add a CDS part to enable host codon optimization.")
    else:
        selected_cds = st.selectbox("Coding part", coding_parts)
        host = st.selectbox("Expression host", ["E. coli", "Human", "S. cerevisiae"])
        try:
            optimization = codon_optimize(PART_LIBRARY[selected_cds], host)
            metric_cards([
                ("Protein length", len(optimization["protein"]), None),
                ("Original GC", f"{optimization['original_gc']:.1f}%", None),
                ("Optimized GC", f"{optimization['optimized_gc']:.1f}%", None),
                ("DNA identity", f"{optimization['sequence_identity']:.1%}", None),
            ])
            st.code(f">{selected_cds.replace(' ', '_')}_{host.replace(' ', '_')}_optimized\n{optimization['optimized']}", language="text")
            st.download_button("Download optimized CDS", f">optimized_CDS\n{optimization['optimized']}\n".encode(), "optimized_cds.fasta", "text/plain")
        except Exception as exc:
            st.warning(str(exc))

with export_tab:
    genbank = genbank_flatfile("BioIntel_construct", sequence, architecture)
    sbol_like = {
        "schema": "biointel.sbol-lite.v2", "name": "BioIntel synthetic construct",
        "parts": architecture.to_dict(orient="records"), "sequence": sequence,
        "quality": {k: v for k, v in quality.items() if not isinstance(v, pd.DataFrame)},
    }
    st.code(f">BioIntel_synthetic_construct\n{sequence}", language="text")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button("FASTA", f">BioIntel_synthetic_construct\n{sequence}\n".encode(), "synthetic_construct.fasta", "text/plain", width="stretch")
    with c2:
        st.download_button("GenBank", genbank.encode(), "synthetic_construct.gb", "text/plain", width="stretch")
    with c3:
        st.download_button("SBOL-style JSON", json.dumps(sbol_like, indent=2).encode(), "synthetic_construct.sbol.json", "application/json", width="stretch")

# Step 99 module excellence layer
render_synthetic_biology_excellence(sequence, architecture, "BioIntel construct")

# Step 100 professional integration and optimization layer
render_synthetic_biology_professional(sequence, architecture, "BioIntel construct")

# Step 115 scientific depth, validation and optimization layer
from biointel.scientific_depth import render_depth_upgrade_panel as _render_step114_depth

_render_step114_depth("synthetic_biology_core", None, key_prefix="step114_synthetic_biology_core", expanded=False)

# STEP127_SCIENTIFIC_DEPTH_SYNTHETIC_BIOLOGY
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('synthetic_biology', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='synthetic_biology_designer', title='Synthetic Biology & Genetic Circuit Designer', category='Lab Analytics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='synthetic_biology_designer', title='Synthetic Biology & Genetic Circuit Designer', category='Lab Analytics')

# Step 183 all-module synthetic demo bundle
from biointel.portfolio_demo_v183.ui import render_step183_portfolio_demo as _render_step183_portfolio_demo
_render_step183_portfolio_demo("synthetic_biology_circuit", expanded=False)


# Step 185 operational assurance panel (synthetic/demo boundary preserved)
try:
    from biointel.operational_assurance_v185.ui import render_step185_operational_assurance as _render_step185_operational_assurance
    _render_step185_operational_assurance("synthetic_biology_circuit")
except Exception as _step185_exc:
    try:
        import streamlit as st
        st.info(f"Step 185 assurance panel unavailable: {_step185_exc}")
    except Exception:
        pass

# STEP188_MAJOR_MODULE_STANDARD_HOOK
from biointel.major_module_standard_v188.ui import render_step188_major_module_standard as _render_step188_major_module_standard
_render_step188_major_module_standard('synthetic_biology_circuit', expanded=False)

# STEP189_UNIVERSAL_PLATFORM_HOOK
from biointel.universal_platform_v189.ui import render_step189_universal_platform as _render_step189_universal_platform
_render_step189_universal_platform('synthetic_biology_circuit', expanded=False)

# STEP190_SCIENTIFIC_EXECUTION_HOOK
from biointel.scientific_execution_v190.ui import render_step190_scientific_execution as _render_step190_scientific_execution
_render_step190_scientific_execution('synthetic_biology_circuit', expanded=False)

# STEP192_RELEASE_INTEGRITY_PUBLICATION_HOOK
from biointel.release_integrity_v192.ui import render_step192_release_integrity as _render_step192_release_integrity
_render_step192_release_integrity('synthetic_biology_circuit', expanded=False)


# STEP193_MANDATORY_COMPLETION_HOOK
from biointel.mandatory_completion_v193.ui import render_step193_mandatory_completion as _render_step193_mandatory_completion
_render_step193_mandatory_completion('synthetic_biology_circuit', expanded=False)

