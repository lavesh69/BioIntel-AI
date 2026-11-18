from __future__ import annotations

import os
import re
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

from biointel.innovation.engines import apply_mutations, demo_protein_sequence
from biointel.innovation.advanced_engines import (
    advanced_protein_design, compare_protein_design, parse_pdb_residues, protein_properties,
)
from biointel.tools.runtime import resolve_tool, run_tool_audited
from biointel.ui.public_branding import public_engine_name
from biointel.innovation.excellence_ui import render_protein_design_excellence
from biointel.innovation.professional_ui import render_protein_design_professional
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json
from biointel.ui.theme import apply_theme, hero, insight_callout, section_title
from biointel.ui.workflow import render_upload_preflight

st.set_page_config(page_title="AI Protein Design & Mutation Engineering Lab · BioIntel AI", page_icon="🧫", layout="wide")
apply_theme()

from biointel.ui.scientific_integrations import render_page_integrations as _render_biointel_integrations
_render_biointel_integrations("pages/96_AI_Protein_Design_Lab.py", key_prefix="96_ai_protein_design_lab", expanded=False)

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("protein_design", key_prefix="step116_96_AI_Protein_Design_Lab_protein_design_1", expanded=False)
hero(
    "AI Protein Design & Mutation Engineering Lab Pro",
    "Rank conservative and multi-objective mutations with BLOSUM62, developability descriptors, Pareto analysis, uncertainty flags and optional PDB residue context.",
    eyebrow="Step 122 · Resumable real-model protein design",
    chips=["BioIntel Sequence Design", "BioIntel Structure Generation", "BioIntel Structure Review", "BioIntel Stability Review", "Resumable runs", "Checksum-verified assets"],
)
scientific_boundary_banner(source_kind="derived_model", release_eligible=False, message="Built-in mutation ranking remains transparent decision support. BioIntel can execute qualified local protein-design components through protected plans, but generated designs still require independent structural review and wet-lab confirmation.")

input_tab, design_tab, structure_tab, external_tab, validation_tab = st.tabs(["1 · Sequence", "2 · Mutation design", "3 · Structure context", "4 · BioIntel engine execution", "5 · Design validation"])
with input_tab:
    sequence_text = st.text_area("Protein FASTA or sequence", value=">demo_protein\n" + demo_protein_sequence(), height=190)
    sequence = "".join(line.strip() for line in sequence_text.splitlines() if not line.startswith(">"))
    try:
        properties = protein_properties(sequence)
    except Exception as exc:
        st.error(str(exc))
        st.stop()
    metric_cards([
        ("Length", int(properties["length"]), None), ("Molecular weight", f"{properties['molecular_weight'] / 1000:.2f} kDa", None),
        ("pI", f"{properties['isoelectric_point']:.2f}", None), ("GRAVY", f"{properties['gravy']:.2f}", None),
        ("Instability index", f"{properties['instability_index']:.1f}", None), ("Aggregation windows", int(properties["aggregation_windows"]), None),
        ("Charge proxy", f"{properties['charge_proxy']:.1f}", None), ("Sequence liabilities", int(properties["sequence_liabilities"]), None),
    ])
    smart_json(properties, key="protein_wildtype_properties")

with design_tab:
    objective = st.selectbox("Design objective", ["Balanced developability", "Stability first", "Solubility first", "Binding-site exploration"])
    cols = st.columns(3)
    locked_text = cols[0].text_input("Locked/conserved positions", "1,2,3,25")
    target_text = cols[1].text_input("Target positions (optional)", "42,43,44")
    top_n = cols[2].slider("Candidates", 20, 500, 120, 20)
    parse_positions = lambda value: [int(token) for token in re.findall(r"\d+", value)]
    try:
        candidates = advanced_protein_design(sequence, objective, parse_positions(locked_text), parse_positions(target_text), int(top_n))
    except Exception as exc:
        st.error(f"Design failed: {exc}")
        st.stop()
    metric_cards([
        ("Candidates", len(candidates), None), ("Pareto optimal", int(candidates["pareto_optimal"].sum()) if not candidates.empty else 0, None),
        ("Conservative", int((candidates["risk_flag"] == "conservative").sum()) if not candidates.empty else 0, None),
        ("Mean confidence", f"{candidates['confidence'].mean():.1%}" if not candidates.empty else "—", None),
        ("Best score", f"{candidates['design_score'].max():.3f}" if not candidates.empty else "—", None),
    ])
    if not candidates.empty:
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(px.scatter(candidates, x="stability_score", y="solubility_score", color="risk_flag", size="confidence", symbol="pareto_optimal", hover_name="mutation", title="Multi-objective mutation landscape"), width="stretch")
        with c2:
            top = candidates.head(25).sort_values("design_score")
            st.plotly_chart(px.bar(top, x="design_score", y="mutation", color="confidence", orientation="h", title="Top ranked candidates"), width="stretch")
        smart_dataframe(candidates, height=470, key="protein_design_pro_candidates")
        st.caption("Pairwise mutation compatibility and epistasis-risk analysis are included in the Step 99 excellence panel below; shortlist low-risk combinations before external structure and wet-lab validation.")
        st.download_button("Export mutation candidates", candidates.to_csv(index=False).encode(), "protein_design_candidates_pro.csv", "text/csv")

with structure_tab:
    pdb_upload = st.file_uploader("Optional PDB structure", type=["pdb", "ent"])
    render_upload_preflight(
        pdb_upload, key="protein_design_pdb", allowed_extensions=["pdb", "ent"],
        soft_limit_mb=50, hard_limit_mb=250,
    )
    if pdb_upload:
        residues = parse_pdb_residues(pdb_upload.getvalue().decode("utf-8", errors="replace"))
        if residues.empty:
            st.warning("No C-alpha residues were parsed from the structure.")
        else:
            target_set = set(int(x) for x in re.findall(r"\d+", st.session_state.get("Target positions (optional)", "")))
            residues["target"] = residues["residue_number"].isin(target_set)
            fig = px.scatter_3d(residues, x="x", y="y", z="z", color="chain", symbol="target", hover_data=["residue_number", "residue"], title="C-alpha structure trace and target residues")
            fig.update_traces(marker={"size": 4})
            st.plotly_chart(fig, width="stretch")
            smart_dataframe(residues, height=360, key="pdb_residue_table")
    else:
        st.info("Upload a PDB file to inspect target residues in 3D. Sequence-only design remains available without a structure.")

with external_tab:
    section_title("BioIntel advanced compatibility runner", "▶")
    legacy_enabled = os.environ.get("BIOINTEL_ENABLE_LEGACY_PROTEIN_TOOL_ARGS", "0").strip() == "1"
    if not legacy_enabled:
        st.warning("Free-form model arguments are disabled by default in Step 122. Use the protected guided pipeline below. Administrators can temporarily enable legacy compatibility with BIOINTEL_ENABLE_LEGACY_PROTEIN_TOOL_ARGS=1.")
    tool = st.selectbox("BioIntel design engine", ["proteinmpnn", "rfdiffusion", "colabfold_batch", "foldseek", "foldx", "rosetta_scripts"], format_func=public_engine_name, key="protein_external_tool")
    cols = st.columns(3)
    executable_override = cols[0].text_input("Optional BioIntel engine location", "", help="Administrators can register a qualified local GPU or licensed component here.", key="protein_external_executable")
    input_path = cols[1].text_input("Input PDB/FASTA path", "", key="protein_external_input")
    evidence_dir = cols[2].text_input("Evidence directory", str(ROOT / "workspace" / "tool_runs" / "protein_design"), key="protein_external_dir")
    templates = {
        "proteinmpnn": '--pdb_path "{input}" --out_folder "{run}/biointel-sequence-design" --num_seq_per_target 16 --sampling_temp 0.1',
        "rfdiffusion": 'inference.input_pdb="{input}" inference.output_prefix="{run}/biointel-structure-generation/design" inference.num_designs=8',
        "colabfold_batch": '"{input}" "{run}/biointel-structure-review" --num-models 3',
        "foldseek": 'easy-search "{input}" "{input}" "{run}/biointel-structure-search.tsv" "{run}/biointel-structure-search-tmp"',
        "foldx": '--command=BuildModel --pdb="{input}" --output-dir="{run}/biointel-stability-review"',
        "rosetta_scripts": '-s "{input}" -out:path:all "{run}/biointel-design-review"',
    }
    run_dir_posix = evidence_dir.replace("\\", "/")
    arguments_text = st.text_area("Advanced execution parameters", templates[tool].format(input=input_path or "INPUT_FILE", run=run_dir_posix), height=120, key=f"protein_external_args_{tool}")
    if executable_override.strip():
        override_path = Path(executable_override).expanduser()
        if override_path.is_file():
            os.environ[f"BIOINTEL_TOOL_{tool.upper().replace('-', '_')}"] = str(override_path.resolve())
            st.success(f"BioIntel engine location registered for {public_engine_name(tool)}.")
        else:
            st.warning("The selected BioIntel engine location does not exist.")
    resolution = resolve_tool(tool)
    if resolution.available:
        st.success(f"{public_engine_name(tool)} is ready through the BioIntel runtime.")
    else:
        st.warning(f"{public_engine_name(tool)} requires setup. Run BIOINTEL_ENGINE_SETUP.bat or ask an administrator to register it.")
    confirm = st.checkbox("I reviewed BioIntel engine assets, licence terms, hardware, input structure and output location", key="protein_external_confirm")
    if st.button("Run BioIntel compatibility engine with audit evidence", type="primary", disabled=not (legacy_enabled and resolution.available and input_path.strip() and confirm), width="stretch"):
        try:
            args = shlex.split(arguments_text, posix=False)
            with st.spinner(f"Running {public_engine_name(tool)} and capturing execution provenance..."):
                result = run_tool_audited(tool, args, run_directory=evidence_dir, timeout_seconds=48 * 60 * 60)
            st.success(f"{public_engine_name(tool)} completed in {result.duration_seconds:.1f} seconds.")
            smart_json(result.to_dict(), key="protein_external_result")
        except Exception as exc:
            st.error(f"BioIntel protein-design execution failed: {exc}")
    insight_callout("Evidence boundary", "BioIntel provides audited adapters for qualified local design and folding components. Asset availability, licence terms, GPU compatibility and experimental confirmation remain project responsibilities.", tone="info")

with validation_tab:
    if "candidates" not in locals() or candidates.empty:
        st.info("Generate mutation candidates in the Mutation design tab first.")
    else:
        choices = st.multiselect("Build a combined design", candidates["mutation"].head(60).tolist(), max_selections=10)
        if choices:
            try:
                designed = apply_mutations(sequence, choices)
                comparison = compare_protein_design(sequence, choices)
                metric_cards([
                    ("Selected mutations", len(choices), None),
                    ("Δ instability", f"{comparison.loc[comparison['metric'] == 'instability_index', 'delta'].iloc[0]:+.2f}", None),
                    ("Δ GRAVY", f"{comparison.loc[comparison['metric'] == 'gravy', 'delta'].iloc[0]:+.3f}", None),
                    ("Δ pI", f"{comparison.loc[comparison['metric'] == 'isoelectric_point', 'delta'].iloc[0]:+.2f}", None),
                ])
                st.plotly_chart(px.bar(comparison, x="metric", y="delta", title="Designed minus wild-type property deltas"), width="stretch")
                smart_dataframe(comparison, height=360, key="protein_design_property_comparison")
                st.code(f">BioIntel_design_{'_'.join(choices)}\n{designed}", language="text")
                st.download_button("Download designed FASTA", f">BioIntel_design\n{designed}\n".encode(), "biointel_designed_protein.fasta", "text/plain")
            except Exception as exc:
                st.error(str(exc))
        insight_callout("Required external validation", "Shortlist only candidates with acceptable uncertainty, inspect structural contacts, re-score with validated structure-aware tools, then confirm expression, folding, stability, binding and biological activity experimentally.", tone="info")

# Step 99 module excellence layer
render_protein_design_excellence(sequence, candidates, objective)

# Step 100 professional integration and optimization layer
render_protein_design_professional(sequence, candidates)

# Step 110 advanced scientific viewers
from biointel.ui.advanced_scientific_viewers import render_embedded_viewer as _render_step110_viewer

_render_step110_viewer("molecular_3d", key_prefix="step110_96_AI_Protein_Design_Lab_molecular_3d")
_render_step110_viewer("sequence_track", key_prefix="step110_96_AI_Protein_Design_Lab_sequence_track")

# Step 115 scientific depth, validation and optimization layer
from biointel.scientific_depth import render_depth_upgrade_panel as _render_step114_depth

_render_step114_depth("protein_language_design", None, key_prefix="step114_protein_language_design", expanded=False)

# Step 115 non-chart visual: molecular_scene
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("molecular_scene", key_prefix="step115_96_AI_Protein_Design_Lab_molecular_scene", expanded=False)

# Step 115 non-chart visual: sequence_feature_track
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("sequence_feature_track", key_prefix="step115_96_AI_Protein_Design_Lab_sequence_feature_track", expanded=False)

# Step 122 real model execution, asset verification and resumable runs
from biointel.step122.panels import render_protein_design_execution_upgrade as _render_step122_protein_design

_render_step122_protein_design(
    root=ROOT,
    default_sequence=sequence,
    key_prefix="step122_96_AI_Protein_Design_Lab",
)

# STEP127_SCIENTIFIC_DEPTH_AI_PROTEIN_DESIGN
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('ai_protein_design', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='protein_design_lab', title='AI Protein Design & Mutation Engineering Lab', category='Discovery')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='protein_design_lab', title='AI Protein Design & Mutation Engineering Lab', category='Discovery')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
