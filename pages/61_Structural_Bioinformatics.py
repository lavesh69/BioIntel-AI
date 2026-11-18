from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.discovery.docking import (
    evaluate_docking_qualification,
    external_docking_readiness,
    readiness_dict,
)
from biointel.structural.advanced import (
    chain_interface_contacts,
    ramachandran_table,
    residue_contact_network,
    solvent_accessibility,
    structure_quality_report,
)
from biointel.structural.pdb_analysis import (
    ligand_contacts,
    structure_summary,
    summary_dict,
)
from biointel.structural.pockets import ligand_defined_pockets, protein_surface_hotspots
from biointel.structural.visualization import (
    build_residue_network_figure,
    build_structure_figure,
    select_structure_atoms,
    structure_atom_table,
)
from biointel.ui.components import (
    metric_cards,
    result_summary,
    scientific_boundary_banner,
    smart_dataframe,
)
from biointel.ui.performance import read_csv_cached, read_text_cached
from biointel.ui.theme import apply_theme, hero, section_title
from biointel.ui.workflow import (  # noqa: E402
    analysis_run,
    read_uploaded_text,
    render_methodology,
    render_upload_preflight,
)


@st.cache_data(show_spinner=False, max_entries=12)
def _analyse_structure_cached(
    structure_text: str,
    selected_format: str,
    contact_cutoff: float,
) -> tuple[Any, ...]:
    """Cache expensive structure analyses so viewer controls rerender instantly."""

    summary_payload = summary_dict(
        structure_summary(structure_text, format_hint=selected_format)
    )
    contacts_payload = pd.DataFrame(
        ligand_contacts(
            structure_text, cutoff=float(contact_cutoff), format_hint=selected_format
        )
    )
    residue_quality_payload, quality_summary_payload = structure_quality_report(
        structure_text, format_hint=selected_format
    )
    ramachandran_payload = ramachandran_table(
        structure_text, format_hint=selected_format
    )
    sasa_table_payload, sasa_chains_payload = solvent_accessibility(
        structure_text, format_hint=selected_format
    )
    interface_contacts_payload, interface_summary_payload = chain_interface_contacts(
        structure_text,
        cutoff=max(float(contact_cutoff), 5.0),
        format_hint=selected_format,
    )
    residue_edges_payload, residue_nodes_payload = residue_contact_network(
        structure_text, format_hint=selected_format
    )
    ligand_pockets_payload, pocket_contacts_payload = ligand_defined_pockets(
        structure_text,
        cutoff=max(float(contact_cutoff), 5.0),
        format_hint=selected_format,
    )
    geometry_hotspots_payload = protein_surface_hotspots(
        structure_text, format_hint=selected_format
    )
    atoms_payload = structure_atom_table(structure_text, format_hint=selected_format)
    return (
        summary_payload,
        contacts_payload,
        residue_quality_payload,
        quality_summary_payload,
        ramachandran_payload,
        sasa_table_payload,
        sasa_chains_payload,
        interface_contacts_payload,
        interface_summary_payload,
        residue_edges_payload,
        residue_nodes_payload,
        ligand_pockets_payload,
        pocket_contacts_payload,
        geometry_hotspots_payload,
        atoms_payload,
    )

DEMO = ROOT / "data" / "bioinformatics_demo"
st.set_page_config(page_title="Structural Bioinformatics · BioIntel AI", page_icon="🧩", layout="wide")
apply_theme()

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK · TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('structural_bioinformatics_core', expanded=False)

# STEP196_P0_P1_PRIORITY_UPGRADE_HOOK
from biointel.proof_gates_v10.ui import render_module_priority_workbench as _render_step196_p0_p1_priority_workbench
_render_step196_p0_p1_priority_workbench(ROOT, 'structural_bioinformatics_core', expanded=False)

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("structural_bioinformatics", key_prefix="step116_61_Structural_Bioinformatics_structural_bioinformatics_1", expanded=False)
hero(
    "Structural Bioinformatics",
    "Inspect chains, residues, ligands and contact geometry from PDB structures with selectable reference complexes and interactive summaries.",
    eyebrow="BioIntel AI · Structure Workbench",
    chips=["PDB upload", "Ligand contacts", "Chain summaries", "Reference structures"],
)
scientific_boundary_banner(
    source_kind="demo_reference",
    release_eligible=False,
    message="Bundled complexes are reference/demo structures. Confirm biological assembly, protonation, missing residues and experimental quality before docking or mechanistic interpretation.",
)

render_methodology(
    method="PDB/mmCIF parsing, structure summaries and spatial-neighbour ligand-contact screening.",
    assumptions=[
        "Coordinates and residue identifiers are parseable.",
        "The selected model/assembly represents the intended biological state.",
    ],
    limitations=[
        "Static contacts do not establish binding affinity or biological relevance.",
        "No molecular dynamics or validated pocket scoring is performed.",
    ],
    validation=[
        "Inspect biological assemblies and experimental resolution.",
        "Confirm contacts with a dedicated structural viewer and domain expert.",
    ],
)

catalog = read_csv_cached(DEMO / "demo_structure_catalog.csv")
selector, cutoff_col = st.columns([2, 1])
selected_path = selector.selectbox(
    "Reference structure",
    catalog["relative_path"].tolist(),
    format_func=lambda value: Path(value).name,
)
cutoff = cutoff_col.slider("Contact cutoff (Å)", 2.0, 8.0, 4.0, 0.25)
uploaded = st.file_uploader("Upload PDB or mmCIF structure", type=["pdb", "cif", "mmcif"])
structure_upload_profile = render_upload_preflight(
    uploaded,
    key="structure_file",
    allowed_extensions=["pdb", "cif", "mmcif"],
    soft_limit_mb=15,
    hard_limit_mb=100,
)
text = read_uploaded_text(uploaded) if uploaded else read_text_cached(ROOT / selected_path)
format_hint = (
    Path(uploaded.name).suffix.lstrip(".") if uploaded else Path(selected_path).suffix.lstrip(".")
)

try:
    with analysis_run(
        "Parsing structure and calculating quality, accessibility and contacts", expanded=True
    ) as structure_run:
        structure_run.stage("Loading cached or fresh structure analysis", progress=0.15)
        (
            summary,
            contacts,
            residue_quality,
            quality_summary,
            ramachandran,
            sasa_table,
            sasa_chains,
            interface_contacts,
            interface_summary,
            residue_edges,
            residue_nodes,
            ligand_pockets,
            pocket_contacts,
            geometry_hotspots,
            atoms_all,
        ) = _analyse_structure_cached(text, format_hint, float(cutoff))
        structure_run.stage("Preparing interactive views", progress=0.96)
except Exception:
    st.info(
        "The structure could not be analysed. Verify that the upload is a complete PDB/mmCIF file "
        "with valid coordinate records, or retry with a bundled reference structure."
    )
    st.stop()
metric_cards(
    [
        ("Atoms", f"{summary.get('atoms', 0):,}", None),
        ("Residues", f"{summary.get('residues', 0):,}", None),
        ("Chains", f"{summary.get('chains', 0):,}", None),
        ("Ligand types", f"{len(summary.get('ligands', {}) or {})}", None),
        ("Contacts", f"{len(contacts):,}", f"Within {cutoff:.2f} Å"),
    ]
)

tabs = st.tabs(
    [
        "3D viewer",
        "Summary",
        "Contacts",
        "Quality",
        "Ramachandran",
        "SASA",
        "Interfaces",
        "Network",
        "Pockets",
        "PDB/mmCIF",
    ]
)
with tabs[0]:
    available_chains = sorted(atoms_all["chain"].astype(str).unique())
    available_groups = sorted(atoms_all["group"].unique())
    with st.expander("3D structure display options", expanded=True):
        option_row = st.columns([1.2, 1, 1, 1, 1])
        view_preset = option_row[0].selectbox(
            "View preset",
            ["Backbone + ligands", "All selected atoms", "Ligand focus", "C-alpha trace"],
            help="Backbone + ligands is the clearest default. All atoms can be sampled for responsiveness.",
        )
        canvas_height = option_row[1].select_slider(
            "Viewer height",
            options=[600, 720, 840, 960, 1080],
            value=840,
            format_func=lambda value: f"{value}px",
        )
        point_size = option_row[2].slider("Atom size", 2.0, 12.0, 5.0, 0.5)
        point_opacity = option_row[3].slider("Atom opacity", 0.25, 1.0, 0.78, 0.05)
        projection = option_row[4].selectbox("Camera", ["Perspective", "Orthographic"])
        filter_row = st.columns([1.2, 1.2, 0.9, 0.9])
        selected_chains = filter_row[0].multiselect(
            "Visible chains", available_chains, default=available_chains
        )
        visible_groups = filter_row[1].multiselect(
            "Visible atom groups", available_groups, default=available_groups
        )
        maximum_atoms = filter_row[2].select_slider(
            "Maximum displayed atoms",
            options=[2_000, 4_000, 8_000, 12_000, 20_000],
            value=8_000,
            format_func=lambda value: f"{value:,}",
        )
        show_backbone = filter_row[3].toggle("Backbone trace", value=True)
        ligand_focus_radius = st.slider(
            "Ligand-focus radius (Å)",
            4.0,
            20.0,
            10.0,
            0.5,
            disabled=view_preset != "Ligand focus",
        )

    display_atoms, view_summary = select_structure_atoms(
        atoms_all,
        selected_chains=selected_chains,
        visible_groups=visible_groups,
        preset=view_preset,
        maximum_atoms=int(maximum_atoms),
        ligand_focus_radius=float(ligand_focus_radius),
    )
    if display_atoms.empty:
        st.warning("No atoms match the selected chains, groups and view preset.")
    else:
        structure_figure = build_structure_figure(
            display_atoms,
            height=int(canvas_height),
            point_size=float(point_size),
            opacity=float(point_opacity),
            show_backbone=bool(show_backbone),
            projection=projection,
        )
        st.plotly_chart(
            structure_figure,
            width="stretch",
            config={
                "displaylogo": False,
                "scrollZoom": True,
                "responsive": True
            },
            key="structural_3d_view_v68",
        )
        summary_cols = st.columns(5)
        summary_cols[0].metric("Total atoms", f"{view_summary.total_atoms:,}")
        summary_cols[1].metric("Selected", f"{view_summary.selected_atoms:,}")
        summary_cols[2].metric("Displayed", f"{view_summary.displayed_atoms:,}")
        summary_cols[3].metric("Ligand atoms", f"{view_summary.ligand_atoms:,}")
        summary_cols[4].metric("Sampling", "Applied" if view_summary.sampled else "Not needed")
        st.download_button(
            "Download interactive 3D view (HTML)",
            structure_figure.to_html(full_html=True, include_plotlyjs=True),
            "structure_interactive_view.html",
            "text/html",
            width="stretch",
        )
    st.caption(
        "Use mouse drag to orbit, Shift-drag to pan and the wheel to zoom. "
        "The viewer preserves biological coordinates but does not infer protonation, bonds or biological assembly."
    )

with tabs[1]:
    left, right = st.columns([1.1, 1])
    with left:
        result_summary(summary, title="Structure summary")
    with right:
        ligand_counts = summary.get("ligands", {}) or {}
        if ligand_counts:
            ligand_frame = pd.DataFrame(
                [{"Ligand": key, "Count": value} for key, value in ligand_counts.items()]
            )
            st.plotly_chart(
                px.bar(ligand_frame, x="Ligand", y="Count", title="Ligand composition"),
                width="stretch",
            )
        else:
            st.info("No non-polymer ligand types were detected.")
with tabs[2]:
    section_title(f"Ligand contacts within {cutoff:.2f} Å", "🔗")
    smart_dataframe(contacts, height=500)
    if not contacts.empty:
        distance_column = next(
            (column for column in contacts.columns if "distance" in column.lower()), None
        )
        if distance_column:
            st.plotly_chart(
                px.histogram(
                    contacts, x=distance_column, nbins=25, title="Contact-distance distribution"
                ),
                width="stretch",
            )
        st.download_button(
            "Download contact table",
            contacts.to_csv(index=False),
            "ligand_contacts.csv",
            "text/csv",
            width="stretch",
        )
with tabs[3]:
    result_summary(quality_summary, title="Experimental and coordinate quality")
    smart_dataframe(residue_quality, height=500)
    st.download_button(
        "Download residue quality audit",
        residue_quality.to_csv(index=False),
        "structure_residue_quality.csv",
        "text/csv",
        width="stretch",
    )
with tabs[4]:
    smart_dataframe(ramachandran, height=360)
    valid_angles = ramachandran.dropna(subset=["phi", "psi"])
    if not valid_angles.empty:
        st.plotly_chart(
            px.scatter(
                valid_angles,
                x="phi",
                y="psi",
                color="region",
                hover_data=["chain", "residue_number", "residue"],
                title="Ramachandran angle distribution",
                range_x=[-180, 180],
                range_y=[-180, 180],
            ),
            width="stretch",
        )
with tabs[5]:
    smart_dataframe(sasa_chains, height=240)
    smart_dataframe(sasa_table, height=440)
    if not sasa_table.empty:
        st.plotly_chart(
            px.histogram(
                sasa_table,
                x="sasa",
                color="exposure_class",
                title="Residue solvent-accessible surface area",
            ),
            width="stretch",
        )
with tabs[6]:
    smart_dataframe(interface_summary, height=240)
    smart_dataframe(interface_contacts, height=440)
with tabs[7]:
    network_controls = st.columns([1, 1, 2])
    network_height = network_controls[0].select_slider(
        "Network height", options=[500, 620, 720, 840, 960], value=720
    )
    maximum_network_nodes = network_controls[1].select_slider(
        "Maximum nodes", options=[100, 200, 350, 500, 800], value=350
    )
    network_controls[2].caption(
        "Large networks retain the highest-degree residues for an interactive overview; the complete edge table remains downloadable."
    )
    network_figure = build_residue_network_figure(
        residue_edges,
        residue_nodes,
        height=int(network_height),
        maximum_nodes=int(maximum_network_nodes),
    )
    if network_figure is not None:
        st.plotly_chart(
            network_figure,
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True, "responsive": True},
            key="residue_contact_network_v68",
        )
    else:
        st.info("Interactive residue-network rendering requires NetworkX and a non-empty contact graph.")
    smart_dataframe(residue_nodes, height=300)
    smart_dataframe(residue_edges, height=340)
    st.download_button(
        "Download residue contact network",
        residue_edges.to_csv(index=False),
        "residue_contact_network.csv",
        "text/csv",
        width="stretch",
    )
with tabs[8]:
    section_title("Ligand-defined pockets", "◉")
    smart_dataframe(ligand_pockets, height=300)
    if not pocket_contacts.empty:
        smart_dataframe(pocket_contacts, height=360)
    section_title("Geometry hotspot screen", "⌖")
    st.caption("Dense residue neighborhoods are a geometry screen only; they are not validated pocket scores.")
    smart_dataframe(geometry_hotspots, height=360)
    readiness = readiness_dict(external_docking_readiness())
    result_summary(readiness, title="External docking-tool readiness")
    with st.form("docking_qualification"):
        qcols = st.columns(4)
        receptor_prepared = qcols[0].checkbox("Receptor prepared")
        ligand_prepared = qcols[1].checkbox("Ligand prepared")
        grid_defined = qcols[2].checkbox("Grid/pocket defined")
        reference_available = qcols[3].checkbox("Reference ligand available")
        rmsd = st.number_input("Redocking RMSD (Å); 0 means not measured", min_value=0.0, max_value=20.0, value=0.0, step=0.1)
        enrichment = st.number_input("Top-1% enrichment factor; 0 means not measured", min_value=0.0, max_value=100.0, value=0.0, step=0.1)
        pose_review = st.checkbox("Expert pose review completed")
        qualify = st.form_submit_button("Evaluate docking protocol gate", type="primary")
    if qualify:
        qualification = evaluate_docking_qualification(
            receptor_prepared=receptor_prepared,
            ligand_prepared=ligand_prepared,
            grid_defined=grid_defined,
            reference_ligand_available=reference_available,
            redocking_rmsd_angstrom=(rmsd if rmsd > 0 else None),
            enrichment_factor_1_percent=(enrichment if enrichment > 0 else None),
            pose_review_completed=pose_review,
            protocol={"contact_cutoff": cutoff, "structure_source": uploaded.name if uploaded else selected_path},
        )
        result_summary(readiness_dict(qualification), title="Docking qualification result")
        if not qualification.qualified:
            st.error("Docking protocol is blocked. Do not use docking scores as hit-selection evidence.")
        else:
            st.success("Protocol gate passed for the documented configuration; prospective review is still required.")
with tabs[9]:
    st.code("\n".join(text.splitlines()[:500]), language="text")

# Step 110 advanced scientific viewers
from biointel.ui.advanced_scientific_viewers import render_embedded_viewer as _render_step110_viewer

_render_step110_viewer("molecular_3d", key_prefix="step110_61_Structural_Bioinformatics_molecular_3d")

# Step 115 scientific depth, validation and optimization layer
from biointel.scientific_depth import render_depth_upgrade_panel as _render_step114_depth

_render_step114_depth("structural_bioinformatics_core", None, key_prefix="step114_structural_bioinformatics_core", expanded=False)

# Step 115 non-chart visual: molecular_scene
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("molecular_scene", key_prefix="step115_61_Structural_Bioinformatics_molecular_scene", expanded=False)

# STEP127_SCIENTIFIC_DEPTH_STRUCTURAL_BIOINFORMATICS
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('structural_bioinformatics', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='structural_bioinformatics', title='Structural Bioinformatics', category='Discovery')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='structural_bioinformatics', title='Structural Bioinformatics', category='Discovery')

# STEP177_21_MODULE_MODEL_COHORT_RUNTIME_EXCELLENCE
from biointel.target_modules_v177.ui import render_step177_module_upgrade
render_step177_module_upgrade('structural_bioinformatics_core', expanded=False)

# Step 183 all-module synthetic demo bundle
from biointel.portfolio_demo_v183.ui import render_step183_portfolio_demo as _render_step183_portfolio_demo
_render_step183_portfolio_demo("structural_bioinformatics_core", expanded=False)

# Step 184 advanced deterministic demo assurance
from biointel.demo_assurance_v184.ui import render_step184_demo_assurance as _render_step184_demo_assurance
_render_step184_demo_assurance("structural_bioinformatics_core", expanded=False)

# STEP188_MAJOR_MODULE_STANDARD_HOOK
from biointel.major_module_standard_v188.ui import render_step188_major_module_standard as _render_step188_major_module_standard
_render_step188_major_module_standard('structural_bioinformatics_core', expanded=False)

# STEP189_UNIVERSAL_PLATFORM_HOOK
from biointel.universal_platform_v189.ui import render_step189_universal_platform as _render_step189_universal_platform
_render_step189_universal_platform('structural_bioinformatics_core', expanded=False)

# STEP190_SCIENTIFIC_EXECUTION_HOOK
from biointel.scientific_execution_v190.ui import render_step190_scientific_execution as _render_step190_scientific_execution
_render_step190_scientific_execution('structural_bioinformatics_core', expanded=False)

# STEP192_RELEASE_INTEGRITY_PUBLICATION_HOOK
from biointel.release_integrity_v192.ui import render_step192_release_integrity as _render_step192_release_integrity
_render_step192_release_integrity('structural_bioinformatics_core', expanded=False)


# STEP193_MANDATORY_COMPLETION_HOOK
from biointel.mandatory_completion_v193.ui import render_step193_mandatory_completion as _render_step193_mandatory_completion
_render_step193_mandatory_completion('structural_bioinformatics_core', expanded=False)

