from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.integrations import (
    execute_integration,
    integration_catalog,
    integration_status_rows,
    integration_summary,
)
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json
from biointel.ui.theme import apply_theme, hero, insight_callout, section_title

st.set_page_config(
    page_title="BioIntel Scientific Integration Center",
    page_icon="🧬",
    layout="wide",
)
apply_theme()

hero(
    "BioIntel Scientific Integration Center",
    "Audited P0, P1 and P2 execution adapters for sequence, genomics, single-cell, multi-omics, drug discovery, structural biology, imaging and reproducible pipelines.",
    eyebrow="BioIntel AI · Scientific Integration Runtime v2",
    chips=["20 real adapters", "P0 + P1 + P2", "Isolated runtimes", "Timeout protection", "SHA-256 provenance", "BioIntel identity"],
)
scientific_boundary_banner(
    source_kind="qualified_runtime",
    release_eligible=False,
    message="Runtime readiness confirms technical execution only. Models, reference databases, cohorts and project-specific evidence remain qualification-gated.",
)

summary = integration_summary()
rows = integration_status_rows()
frame = pd.DataFrame(rows)

metric_cards(
    [
        ("Integration adapters", summary["total"], None),
        ("Ready now", summary["ready"], None),
        ("Setup required", summary["setup_required"], None),
        ("P0 coverage", f"{summary['priorities']['P0']['ready']}/{summary['priorities']['P0']['total']}", None),
        ("P1 coverage", f"{summary['priorities']['P1']['ready']}/{summary['priorities']['P1']['total']}", None),
        ("P2 coverage", f"{summary['priorities']['P2']['ready']}/{summary['priorities']['P2']['total']}", None),
    ]
)

section_title("BioIntel integration readiness", "◈")
filters = st.columns(3)
priority_options = ["All", "P0", "P1", "P2"]
selected_priority = filters[0].selectbox("Priority", priority_options)
category_options = ["All", *sorted(frame["category"].dropna().unique().tolist())] if not frame.empty else ["All"]
selected_category = filters[1].selectbox("Scientific domain", category_options)
state_filter = filters[2].selectbox("Readiness", ["All", "Ready", "Setup required", "Assets require qualification"])

visible = frame.copy()
if selected_priority != "All":
    visible = visible[visible["priority"] == selected_priority]
if selected_category != "All":
    visible = visible[visible["category"] == selected_category]
if state_filter == "Ready":
    visible = visible[visible["state"] == "Ready"]
elif state_filter == "Setup required":
    visible = visible[visible["state"] == "Setup required"]
elif state_filter == "Assets require qualification":
    visible = visible[visible["state"].str.contains("assets require", case=False, na=False)]

if not visible.empty:
    visible = visible.assign(
        **{
            "Target modules": visible["target_modules"].map(lambda values: " · ".join(values)),
            "Capabilities": visible["capabilities"].map(lambda values: " · ".join(values)),
            "Operations": visible["operations"].map(
                lambda values: " · ".join(
                    item.replace("_", " ").title()
                    for item in values
                    if item != "technical_diagnostic"
                )
            ),
        }
    )
    public_columns = [
        "public_key",
        "name",
        "priority",
        "category",
        "state",
        "execution_mode",
        "Target modules",
        "Capabilities",
        "Operations",
        "setup_profile",
        "qualification_note",
    ]
    smart_dataframe(visible[public_columns], height=650, key="biointel_integration_readiness_v2")
else:
    st.info("No BioIntel integrations match the selected filters.")

section_title("Technical runtime diagnostic", "✓")
catalog = integration_catalog()
options = {f"{spec.priority} · {spec.public_name}": spec for spec in catalog}
selected_label = st.selectbox("BioIntel integration", list(options))
selected = options[selected_label]
left, right = st.columns([1, 2])
with left:
    run_diagnostic = st.button("Run technical diagnostic", type="primary", width="stretch")
with right:
    st.caption(
        "This test verifies import or executable availability through the same isolated adapter used by modules. It does not download model weights or scientific databases."
    )

if run_diagnostic:
    with st.spinner(f"Checking {selected.public_name}..."):
        result = execute_integration(selected.integration_id, "technical_diagnostic", {})
    if result.status == "completed":
        st.success(result.message)
    else:
        st.warning(result.message)
    metric_cards(
        [
            ("Engine", result.public_key, None),
            ("Priority", result.priority, None),
            ("Status", result.status.title(), None),
            ("Duration", f"{result.duration_seconds:.2f}s", None),
        ]
    )
    smart_json(dict(result.metrics))
    st.caption(f"Run ID: {result.run_id}. Protected diagnostics are retained in BioIntel user data.")

section_title("Audited scientific operation console", "▶")
st.caption(
    "Run a registered BioIntel operation through the same timeout, logging, provenance and fail-safe contract used by module adapters. File paths must point to data available on this computer."
)
operation_options = [item for item in selected.operations if item != "technical_diagnostic"]
selected_operation = st.selectbox(
    "Operation",
    operation_options,
    format_func=lambda value: value.replace("_", " ").title(),
    key="biointel_integration_operation",
)
PAYLOAD_TEMPLATES = {
    "sequence_summary": {"sequence": "ATGCGTACGTAG"},
    "fasta_summary": {"input_path": "C:\\BioIntelData\\sequences.fasta", "format": "fasta"},
    "variant_summary": {"input_path": "C:\\BioIntelData\\variants.vcf", "max_records": 100000},
    "alignment_summary": {"input_path": "C:\\BioIntelData\\alignment.bam", "max_records": 100000},
    "alpha_diversity": {"matrix": [[10, 2, 0], [3, 4, 8]], "sample_ids": ["sample_1", "sample_2"], "metric": "shannon"},
    "distance_matrix": {"matrix": [[10, 2, 0], [3, 4, 8]], "sample_ids": ["sample_1", "sample_2"], "metric": "braycurtis"},
    "single_cell_qc": {"matrix": [[1, 0, 3], [0, 2, 1], [4, 1, 0]]},
    "single_cell_embedding": {"input_path": "C:\\BioIntelData\\single_cell.h5ad", "components": 10},
    "single_cell_ai_diagnostic": {},
    "single_cell_latent": {"matrix": [[1, 0, 3, 2], [0, 2, 1, 1], [4, 1, 0, 2], [2, 3, 1, 0]], "epochs": 1},
    "multiomics_summary": {"input_path": "C:\\BioIntelData\\multiomics.h5mu"},
    "joint_container": {"modalities": {"rna": [[1, 2], [3, 4]], "protein": [[2, 1], [0, 3]]}},
    "spatial_neighbors": {"input_path": "C:\\BioIntelData\\spatial.h5ad"},
    "spatial_summary": {"input_path": "C:\\BioIntelData\\spatial.h5ad"},
    "molecule_summary": {"smiles": "CCO"},
    "fingerprint": {"smiles": "CCO", "radius": 2, "bits": 2048},
    "molecular_featurize": {"smiles": ["CCO", "CCN"]},
    "model_diagnostic": {},
    "dock": {"receptor_path": "C:\\BioIntelData\\receptor.pdbqt", "ligand_path": "C:\\BioIntelData\\ligand.pdbqt"},
    "score_only": {"receptor_path": "C:\\BioIntelData\\receptor.pdbqt", "ligand_path": "C:\\BioIntelData\\ligand.pdbqt"},
    "simulation_diagnostic": {},
    "energy_minimize": {"positions_nm": [[0.0, 0.0, 0.0], [0.2, 0.0, 0.0]]},
    "trajectory_summary": {"topology_path": "C:\\BioIntelData\\topology.pdb", "trajectory_path": "C:\\BioIntelData\\trajectory.dcd"},
    "rmsd": {"topology_path": "C:\\BioIntelData\\topology.pdb", "trajectory_path": "C:\\BioIntelData\\trajectory.dcd", "selection": "backbone"},
    "protein_model_diagnostic": {},
    "protein_embedding": {"model_path": "C:\\BioIntelModels\\qualified_model.pt", "sequence": "MKTIIALSYIFCLVFAD"},
    "design_sequences": {"input_path": "C:\\BioIntelData\\structure.pdb", "num_sequences": 4},
    "score_sequence": {"input_path": "C:\\BioIntelData\\structure.pdb", "fasta_path": "C:\\BioIntelData\\candidates.fasta"},
    "offline_prerank": {"ranking": {"GENE1": 2.1, "GENE2": -1.4, "GENE3": 0.8}, "gene_sets": {"BioIntel_Set": ["GENE1", "GENE3"]}, "permutations": 100},
    "gene_set_score": {"ranking": {"GENE1": 2.1, "GENE2": -1.4, "GENE3": 0.8}, "gene_sets": {"BioIntel_Set": ["GENE1", "GENE3"]}, "permutations": 100},
    "classify_reads": {"database_path": "C:\\BioIntelDatabases\\taxonomy", "read_paths": ["C:\\BioIntelData\\reads_1.fastq", "C:\\BioIntelData\\reads_2.fastq"]},
    "database_check": {"database_path": "C:\\BioIntelDatabases\\taxonomy"},
    "imaging_preprocess": {"array": [[0, 1], [2, 3]], "spatial_size": [64, 64]},
    "open_image": {"input_path": "C:\\BioIntelData\\image.tif"},
    "viewer_diagnostic": {},
    "run_workflow": {"workflow_path": "C:\\BioIntelWorkflows\\Snakefile", "cores": 2},
    "dry_run": {"workflow_path": "C:\\BioIntelWorkflows\\Snakefile", "cores": 1},
    "run_pipeline": {"pipeline": "biointel/rnaseq", "profile": "docker"},
    "pipeline_catalog": {},
    "download_pipeline": {"pipeline": "biointel/rnaseq"},
}
payload_default = PAYLOAD_TEMPLATES.get(selected_operation, {})
payload_text = st.text_area(
    "Operation input (JSON)",
    value=json.dumps(payload_default, indent=2),
    height=220,
    key=f"biointel_payload_{selected.integration_id}_{selected_operation}",
)
run_operation = st.button("Run audited BioIntel operation", type="primary", width="stretch")
if run_operation:
    try:
        operation_payload = json.loads(payload_text or "{}")
        if not isinstance(operation_payload, dict):
            raise ValueError("Operation input must be a JSON object.")
    except (json.JSONDecodeError, ValueError) as exc:
        st.error(f"BioIntel input validation failed: {exc}")
    else:
        with st.spinner(f"Running {selected.public_name}..."):
            operation_result = execute_integration(selected.integration_id, selected_operation, operation_payload)
        if operation_result.status == "completed":
            st.success(operation_result.message)
        elif operation_result.status == "timed_out":
            st.warning(operation_result.message)
        else:
            st.error(operation_result.message)
        metric_cards(
            [
                ("Run", operation_result.run_id, None),
                ("Status", operation_result.status.title(), None),
                ("Priority", operation_result.priority, None),
                ("Duration", f"{operation_result.duration_seconds:.2f}s", None),
            ]
        )
        smart_json(dict(operation_result.metrics))
        if operation_result.artifacts:
            smart_dataframe(pd.DataFrame(operation_result.artifacts), key="biointel_operation_artifacts")
        st.caption(operation_result.qualification)

setup_left, setup_right = st.columns(2)
with setup_left:
    insight_callout(
        "One setup entry point",
        "Run BIOINTEL_ENGINE_SETUP.bat and choose P0, P1, P2 or All. Each heavy dependency is installed into a separate BioIntel environment so it cannot destabilise the core desktop app.",
        tone="info",
    )
with setup_right:
    insight_callout(
        "Identity and licensing",
        "Normal screens, module panels, selectors, reports and exports use BioIntel identities. Required upstream attribution remains only in Legal & Component Notices and protected technical diagnostics.",
        tone="success",
    )

public_export = {
    "schema": summary["schema"],
    "total": summary["total"],
    "ready": summary["ready"],
    "setup_required": summary["setup_required"],
    "priorities": summary["priorities"],
    "identity_policy": summary["identity_policy"],
    "execution_contract": summary["execution_contract"],
    "integrations": rows,
}
st.download_button(
    "Export BioIntel integration readiness",
    json.dumps(public_export, indent=2).encode("utf-8"),
    "biointel_scientific_integration_readiness_v2.json",
    "application/json",
    width="stretch",
)
