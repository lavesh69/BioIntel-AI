# STEP139_BIOINFORMATICS_NATIVE_REVIEW_PUBLICATION_PEAK
from __future__ import annotations

from dataclasses import asdict

import sys
import pandas as pd
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.nextgen.renderer import render_nextgen_module
from biointel.ui.theme import apply_theme
from biointel.neuro_cns.causal_neurogenomics import CausalNeurogenomicsStudio, HarmonizedVariant

st.set_page_config(page_title='Population Genetics & Causal Neurogenomics Studio · BioIntel AI', page_icon='🧬', layout="wide")
apply_theme()

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK - TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('population_gwas', expanded=False)

st.title("🧬 Causal Neurogenomics & Target Discovery Studio")
st.caption("BioIntel AI 15.6.0 · Biology, Engineered into Intelligence. Owner: Lavesh Dobriyal")

# P0 Causal Studio Workbench
causal_studio = CausalNeurogenomicsStudio(str(ROOT))

t_mr, t_graph, t_nextgen = st.tabs(["⚡ P0 Mendelian Randomization & Fine-Mapping", "🕸️ Interactive 7-Tier Target Graph", "📊 NextGen GWAS Engine"])

with t_mr:
    st.subheader("Mendelian Randomization & Variant Harmonization Workflow")
    st.write("Executes Two-Sample Mendelian Randomization (IVW, MR-Egger, Weighted Median) with horizontal pleiotropy & instrument strength checks.")

    col1, col2 = st.columns(2)
    with col1:
        exposure = st.multiselect("Exposure Traits / Biomarkers", ["Plasma Progranulin (GRN)", "sTREM2 Level", "Cortical Thickness", "NFL Level"], ["Plasma Progranulin (GRN)"])
        outcome = st.selectbox("Outcome Trait", ["Frontotemporal Dementia (FTD)", "Alzheimer's Disease (AD)", "Amyotrophic Lateral Sclerosis (ALS)", "Parkinson's Disease (PD)"])
        build = st.selectbox("Reference Genome Build", ["GRCh38", "GRCh37"])

    with col2:
        st.markdown("**Sample Variant Instruments Payload**")
        sample_df = pd.DataFrame([
            {"rsid": "rs5848", "chr": "17", "bp": 44358617, "ea": "T", "oa": "C", "beta": 0.38, "se": 0.04, "pvalue": 1.2e-12},
            {"rsid": "rs1990622", "chr": "7", "bp": 12854911, "ea": "C", "oa": "T", "beta": -0.24, "se": 0.03, "pvalue": 4.5e-9},
            {"rsid": "rs708727", "chr": "10", "bp": 11823901, "ea": "G", "oa": "A", "beta": 0.19, "se": 0.03, "pvalue": 8.1e-7}
        ])
        st.dataframe(sample_df, hide_index=True)

    if st.button("🚀 Run Harmonization & Mendelian Randomization", type="primary"):
        instruments = causal_studio.intake_and_harmonize_gwas(sample_df, build)
        res = causal_studio.calculate_mendelian_randomization(exposure, outcome, instruments)
        
        st.success(f"Mendelian Randomization Analysis Complete for {res.exposure_trait} -> {res.outcome_trait}")
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("IVW Beta (95% CI)", f"{res.ivw_beta:.3f} (p={res.ivw_pvalue:.2e})")
        m2.metric("MR-Egger Beta", f"{res.mr_egger_beta:.3f}")
        m3.metric("Weighted Median Beta", f"{res.weighted_median_beta:.3f}")
        m4.metric("Mean F-Statistic", f"{res.mean_f_statistic:.1f}", delta="Strong (>10)" if not res.instrument_strength_warning else "Weak (<10)")

        if res.horizontal_pleiotropy_warning:
            st.warning("⚠️ Warning: Significant horizontal pleiotropy detected (Egger intercept p < 0.05).")
        else:
            st.info("✅ Horizontal Pleiotropy Check Passed (No directional pleiotropy detected).")

        st.markdown("#### Provenance & Scientific Boundary Record")
        st.json(asdict(res.provenance))

with t_graph:
    st.subheader("7-Tier Causal Cascade Visualization")
    st.write("Variant → Locus → Gene → Cell Type → Pathway → Target → Compound Graph")
    
    gene_target = st.text_input("Target Gene Symbol", "GRN")
    disease_ctx = st.text_input("Disease Context", "Frontotemporal Dementia")
    
    nodes, edges = causal_studio.generate_seven_tier_causal_graph(gene_target, disease_ctx)
    
    st.markdown("##### Cascade Flow Matrix")
    flow_df = pd.DataFrame([
        {"Tier": n.tier, "Node Label": n.label, "ID": n.id, "Metadata": str(n.properties)} for n in nodes
    ])
    st.dataframe(flow_df, use_container_width=True, hide_index=True)
    
    st.markdown("##### Graph Edge Connections")
    edge_df = pd.DataFrame([
        {"From": e.source_id, "To": e.target_id, "Relationship": e.relationship, "Weight / Confidence": e.weight} for e in edges
    ])
    st.dataframe(edge_df, use_container_width=True, hide_index=True)

with t_nextgen:
    # STEP196_P0_P1_PRIORITY_UPGRADE_HOOK
    from biointel.proof_gates_v10.ui import render_module_priority_workbench as _render_step196_p0_p1_priority_workbench
    _render_step196_p0_p1_priority_workbench(ROOT, 'population_gwas', expanded=False)

    render_nextgen_module('population_gwas')
