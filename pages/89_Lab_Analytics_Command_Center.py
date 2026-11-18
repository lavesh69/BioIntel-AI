from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.biotech.lab_registry import list_runs, registry_summary
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe
from biointel.ui.theme import apply_theme, hero, insight_callout, section_title
from biointel.module_runtime_v207.portfolio_ui import render_step207_portfolio_panel

st.set_page_config(page_title="Lab Analytics Command Center · BioIntel AI", page_icon="🧪", layout="wide")
apply_theme()
hero(
    "Lab Analytics Command Center",
    "Connected molecular-assay, process, experimental-design and microbiome workflows with schema controls, run provenance and actionable QC recommendations.",
    eyebrow="BioIntel AI · Lab Analytics",
    chips=["qPCR + ELISA", "Enzyme kinetics", "Bioprocess", "Experimental design", "Microbiome", "Run registry"],
)
scientific_boundary_banner(
    source_kind="research_software",
    release_eligible=False,
    message="The command center supports research analytics and traceability. Laboratory validation, instrument qualification, electronic signatures and GLP/GMP release remain organisation-specific controls.",
)

render_step207_portfolio_panel("Lab Analytics", expanded=False)

summary = registry_summary()
metric_cards(
    [
        ("Registered runs", summary["runs"], None),
        ("Bound artifacts", summary["artifacts"], None),
        ("Recorded reviews", summary["reviews"], None),
        ("Workflow families", 6, None),
    ]
)

section_title("Start a laboratory workflow", "◎")
workflows = [
    {
        "workflow": "Molecular assays",
        "page": "pages/64_Wet_Lab_Biotechnology.py",
        "scope": "qPCR, ELISA, enzyme kinetics, bioprocess and experimental design",
        "input": "Instrument CSV/TSV or canonical template",
        "primary_qc": "Controls, replicate precision, model diagnostics, range and plate QC",
    },
    {
        "workflow": "Primer, CRISPR and codon design",
        "page": "pages/58_Primer_CRISPR_Codon_Studio.py",
        "scope": "Primer panels, guide design, off-target screens and coding-DNA optimization",
        "input": "Sequence/FASTA and optional local specificity panel",
        "primary_qc": "Tm, dimers, product size, PAM/seed mismatches and synthesis motifs",
    },
    {
        "workflow": "Microbiology rapid QC",
        "page": "pages/65_Microbiology_Metagenomics.py",
        "scope": "Diversity, abundance QC and compact genome similarity",
        "input": "Taxonomy/abundance tables and sequences",
        "primary_qc": "Negative values, sample selection, diversity and k-mer diagnostics",
    },
    {
        "workflow": "Professional metagenomics",
        "page": "pages/82_Metagenomics_Pipeline.py",
        "scope": "Compositional statistics, phylogenetic diversity and raw-read plans",
        "input": "Count tables, metadata, Newick tree or FASTQ plan",
        "primary_qc": "Contaminants, restricted permutations, CLR, UniFrac and tool/database checks",
    },
]
for index, item in enumerate(workflows):
    columns = st.columns([1.2, 2.8, 1.2])
    columns[0].markdown(f"**{item['workflow']}**")
    columns[1].caption(f"{item['scope']}  \n**Input:** {item['input']}  \n**QC:** {item['primary_qc']}")
    try:
        columns[2].page_link(item["page"], label="Open workflow", width="stretch")
    except Exception:
        columns[2].caption(item["page"])

section_title("Scientific readiness matrix", "▦")
readiness = pd.DataFrame(
    [
        ["qPCR", "Strong", "Efficiency, replicate QC, controls, melt curves, multi-reference normalization", "Raw amplification/RDML and laboratory MIQE completion"],
        ["ELISA", "Strong", "AICc model selection, range-safe inverse, bootstrap CI, spatial QC", "Organisation-specific validation, stability and incurred-sample policies"],
        ["Enzyme kinetics", "Strong", "Initial-rate direction QC, model comparison, inhibition mechanisms", "Assay-specific unit conversion and independent validation"],
        ["Bioprocess", "Strong", "Per-batch rates, process-mode mass-balance checks, golden-batch comparison", "Validated historian/PAT connectors and laboratory CPP/CQA limits"],
        ["Experimental design", "Strong", "Power, real strata, secure seed, blinded assignments, adjacency QC", "Protocol-specific multiplicity and regulatory statistical review"],
        ["Metagenomics", "Advanced research", "Compositional, covariate, contamination and phylogenetic analytics", "Container-pinned production workflow and specialist differential methods"],
    ],
    columns=["Area", "Software readiness", "Implemented", "External/next boundary"],
)
smart_dataframe(readiness, height=290)

section_title("Recent Lab Run Registry", "◫")
runs = list_runs(limit=100)
if runs.empty:
    st.info("No runs are registered yet. Enable ‘Save successful runs’ on Wet-Lab Biotechnology to store local provenance and artifact hashes.")
else:
    smart_dataframe(runs, height=360)

section_title("Recommended operating sequence", "✓")
recommendations = [
    "Start from a canonical template or explicitly map every required instrument column; duplicate source mappings are blocked.",
    "Confirm units, controls, calibrators, biological versus technical replicate identity and laboratory acceptance criteria before analysis.",
    "Review all QC flags and model diagnostics; results outside calibrated ranges remain non-quantifiable rather than silently extrapolated.",
    "Download the reproducibility ZIP containing raw-table copy, parameters, outputs, recommendations and SHA-256 checksums.",
    "Register only reviewed runs, then retain the original instrument export and signed laboratory record in the laboratory-controlled system.",
]
for item in recommendations:
    st.markdown(f"- {item}")

insight_callout(
    "No fabricated compliance",
    "The software can implement audit-ready structures and validation workflows, but it does not claim laboratory accreditation, electronic-signature compliance, instrument IQ/OQ/PQ or successful regulatory inspection without genuine external evidence.",
    "warning",
)

# STEP127_SCIENTIFIC_DEPTH_LAB_COMMAND
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('lab_command', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='lab_analytics_command_center', title='Lab Analytics Command Center', category='Lab Analytics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='lab_analytics_command_center', title='Lab Analytics Command Center', category='Lab Analytics')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
