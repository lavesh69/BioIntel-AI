from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

from biointel.step122.protein_design import (
    BACKENDS,
    build_protein_design_plan,
    discover_protein_design_runs,
    execute_protein_design_plan,
    protein_design_preflight,
    register_model_asset,
    stage_protein_design_input,
)
from biointel.ui.components import metric_cards, smart_dataframe, smart_json
from biointel.ui.theme import insight_callout, section_title

_BACKEND_LABELS = {
    "proteinmpnn": "ProteinMPNN · structure-conditioned sequence design",
    "rfdiffusion": "RFdiffusion · generative backbone design",
    "colabfold_batch": "ColabFold · structure/confidence validation",
    "foldx": "FoldX · mutation stability rescoring",
    "rosetta_scripts": "RosettaScripts · protocol-driven refinement/design",
}


def _workspace(root: Path) -> Path:
    path = root / "workspace" / "protein_design_runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _plan_parameters(backend: str, key_prefix: str) -> dict[str, Any]:
    cols = st.columns(3)
    threads = cols[0].number_input("CPU threads", 1, 128, min(8, max(1, 4)), key=f"{key_prefix}_threads")
    seed = cols[1].number_input("Deterministic seed", 0, 2_147_483_647, 42, key=f"{key_prefix}_seed")
    timeout_hours = cols[2].number_input("Timeout (hours)", 1, 240, 48, key=f"{key_prefix}_timeout")
    params: dict[str, Any] = {"threads": int(threads), "seed": int(seed), "timeout_hours": int(timeout_hours)}
    if backend == "proteinmpnn":
        c1, c2, c3 = st.columns(3)
        params["num_sequences"] = int(c1.number_input("Sequences per target", 1, 1000, 16, key=f"{key_prefix}_mpnn_n"))
        params["sampling_temperature"] = float(c2.number_input("Sampling temperature", 0.01, 1.0, 0.10, 0.01, key=f"{key_prefix}_mpnn_temp"))
        params["batch_size"] = int(c3.number_input("Batch size", 1, 64, 1, key=f"{key_prefix}_mpnn_batch"))
        params["chains"] = [value for value in st.text_input("Chains to design (comma separated; blank = wrapper default)", "", key=f"{key_prefix}_mpnn_chains").replace(" ", "").split(",") if value]
        params["fixed_positions"] = st.text_input("Fixed positions (1-based)", "", key=f"{key_prefix}_mpnn_fixed")
        params["design_positions"] = st.text_input("Explicit design positions (1-based, optional)", "", key=f"{key_prefix}_mpnn_design")
    elif backend == "rfdiffusion":
        c1, c2 = st.columns(2)
        params["num_designs"] = int(c1.number_input("Backbone designs", 1, 256, 8, key=f"{key_prefix}_rfd_n"))
        params["contigs"] = c2.text_input("Contig expression", "", help="Blank uses the full first chain.", key=f"{key_prefix}_rfd_contigs")
        params["hotspot_residues"] = [value.strip() for value in st.text_input("Hotspot residues (for example A42,B77)", "", key=f"{key_prefix}_rfd_hotspots").split(",") if value.strip()]
    elif backend == "colabfold_batch":
        c1, c2, c3 = st.columns(3)
        params["num_models"] = int(c1.number_input("Models", 1, 5, 3, key=f"{key_prefix}_cf_models"))
        params["num_recycles"] = int(c2.number_input("Recycles", 1, 20, 3, key=f"{key_prefix}_cf_recycles"))
        params["amber_relax"] = bool(c3.checkbox("Amber relaxation", value=False, key=f"{key_prefix}_cf_amber"))
        params["use_templates"] = bool(st.checkbox("Use templates", value=False, key=f"{key_prefix}_cf_templates"))
    elif backend == "foldx":
        params["mutations"] = [value.strip() for value in st.text_area("FoldX mutations, one per line (for example AA42V;)", "", height=110, key=f"{key_prefix}_foldx_mut").replace(",", "\n").splitlines() if value.strip()]
    else:
        params["protocol_xml"] = st.text_input("Staged RosettaScripts XML path", "", key=f"{key_prefix}_rosetta_xml")
        params["nstruct"] = int(st.number_input("Rosetta nstruct", 1, 10000, 10, key=f"{key_prefix}_rosetta_n"))
    return params


def render_protein_design_execution_upgrade(
    *,
    root: Path,
    default_sequence: str = "",
    key_prefix: str = "step122_protein_design",
) -> None:
    st.divider()
    section_title("Step 122 · Real protein-model execution and resumable design runs", "🧬")
    workspace = _workspace(root)
    readiness_tab, run_tab, history_tab, assets_tab = st.tabs([
        "Execution readiness", "Guided model run", "Run history", "Model assets",
    ])

    with readiness_tab:
        report = protein_design_preflight(workspace)
        backend_table = report["backends"]
        metric_cards([
            ("Ready backends", int((backend_table["status"] == "Ready").sum()), None),
            ("Detected executables", int(backend_table["executable_available"].sum()), None),
            ("Verified model assets", int(backend_table["model_asset_checksum_verified"].sum()), None),
            ("CUDA available", "Yes" if report["hardware"]["gpu"]["cuda_available"] else "No", None),
            ("Free workspace", f"{report['hardware']['workspace_free_gb']:.1f} GB", None),
        ])
        smart_dataframe(backend_table, height=360, key=f"{key_prefix}_readiness")
        with st.expander("Hardware and asset detail", expanded=False):
            smart_json({"hardware": report["hardware"], "assets": report["assets"]}, key=f"{key_prefix}_preflight_json")
        insight_callout("Honest execution tier", report["boundary"], tone="info")

    with run_tab:
        backend = st.selectbox("Protected backend", list(BACKENDS), format_func=lambda value: _BACKEND_LABELS[value], key=f"{key_prefix}_backend")
        required_kind = "Protein FASTA" if backend == "colabfold_batch" else "PDB structure"
        st.caption(f"Required input: {required_kind}. Arbitrary shell arguments are intentionally disabled.")
        source_mode_options = ["Upload file"] + (["Use current sequence"] if backend == "colabfold_batch" and default_sequence else [])
        source_mode = st.radio("Input source", source_mode_options, horizontal=True, key=f"{key_prefix}_source_mode")
        upload = None
        if source_mode == "Upload file":
            allowed = ["fa", "fasta", "faa"] if backend == "colabfold_batch" else ["pdb", "ent"]
            upload = st.file_uploader(f"Upload {required_kind}", type=allowed, key=f"{key_prefix}_upload_{backend}")
        run_name = st.text_input("Run name", f"{backend}-design", key=f"{key_prefix}_run_name")
        params = _plan_parameters(backend, key_prefix)

        stage_clicked = st.button("Stage immutable input", type="secondary", width="stretch", key=f"{key_prefix}_stage")
        if stage_clicked:
            try:
                if source_mode == "Use current sequence":
                    staged = stage_protein_design_input(workspace=workspace, sequence=default_sequence, filename="current_sequence.fasta", run_name=run_name)
                elif upload is not None:
                    staged = stage_protein_design_input(workspace=workspace, source_bytes=upload.getvalue(), filename=upload.name, run_name=run_name)
                else:
                    raise ValueError("Upload the required input before staging")
                st.session_state[f"{key_prefix}_staged"] = staged
                st.success(f"Input staged: {staged['run_id']}")
            except Exception as exc:
                st.error(f"Input staging failed: {exc}")

        staged = st.session_state.get(f"{key_prefix}_staged")
        if staged:
            smart_json(staged, key=f"{key_prefix}_staged_json")
            build_clicked = st.button("Build protected execution plan", width="stretch", key=f"{key_prefix}_build_plan")
            if build_clicked:
                try:
                    plan = build_protein_design_plan(
                        backend,
                        run_directory=staged["run_directory"],
                        input_path=staged["input_path"],
                        parameters=params,
                    )
                    st.session_state[f"{key_prefix}_plan"] = plan
                except Exception as exc:
                    st.error(f"Plan creation failed: {exc}")

        plan = st.session_state.get(f"{key_prefix}_plan")
        if plan is not None:
            status = "Executable" if plan.executable else "Blocked"
            metric_cards([
                ("Plan status", status, None),
                ("Backend", plan.backend, None),
                ("Input SHA-256", plan.input_sha256[:12] + "…", None),
                ("Warnings", len(plan.warnings), None),
                ("Blockers", len(plan.blockers), None),
            ])
            if plan.blockers:
                st.error("Execution blockers: " + "; ".join(plan.blockers))
            if plan.warnings:
                st.warning("; ".join(plan.warnings))
            with st.expander("Protected plan manifest", expanded=False):
                smart_json(plan.to_dict(), key=f"{key_prefix}_plan_json")
            c1, c2 = st.columns(2)
            if c1.button("Save dry-run/checkpoint", width="stretch", key=f"{key_prefix}_dry_run"):
                try:
                    result = execute_protein_design_plan(plan, dry_run=True)
                    st.session_state[f"{key_prefix}_result"] = result
                    st.success("Dry-run manifest and resumable state saved.")
                except Exception as exc:
                    st.error(str(exc))
            confirm = st.checkbox("I verified the model licence, weights, hardware, input and experimental-use boundary", key=f"{key_prefix}_confirm")
            if c2.button("Execute real model", type="primary", disabled=not (plan.executable and confirm), width="stretch", key=f"{key_prefix}_execute"):
                try:
                    with st.spinner(f"Running {plan.label}; logs and checkpoints are written to disk..."):
                        result = execute_protein_design_plan(plan, timeout_seconds=int(params.get("timeout_hours", 48)) * 3600)
                    st.session_state[f"{key_prefix}_result"] = result
                    st.success(f"Execution status: {result.status}")
                except Exception as exc:
                    st.error(f"Model execution failed: {exc}")

        result = st.session_state.get(f"{key_prefix}_result")
        if result is not None:
            if not result.outputs.empty:
                smart_dataframe(result.outputs, height=320, key=f"{key_prefix}_outputs")
            if not result.candidates.empty:
                smart_dataframe(result.candidates.drop(columns=["sequence"], errors="ignore"), height=420, key=f"{key_prefix}_candidates")
                st.download_button("Export parsed candidates", result.candidates.to_csv(index=False).encode(), "protein_design_model_candidates.csv", "text/csv", key=f"{key_prefix}_candidate_download")
            smart_json(result.release_gate, key=f"{key_prefix}_release_gate")
            manifest = Path(result.manifest_path)
            if manifest.is_file():
                st.download_button("Download run manifest", manifest.read_bytes(), manifest.name, "application/json", key=f"{key_prefix}_manifest_download")

    with history_tab:
        history = discover_protein_design_runs(workspace)
        if history.empty:
            st.info("No persistent protein-design runs have been staged yet.")
        else:
            smart_dataframe(history, height=420, key=f"{key_prefix}_history")
        st.caption(f"Persistent run workspace: {workspace}")

    with assets_tab:
        backend_asset = st.selectbox("Backend asset", list(BACKENDS), format_func=lambda value: _BACKEND_LABELS[value], key=f"{key_prefix}_asset_backend")
        asset_path = st.text_input("Local model-parameter/database path", "", key=f"{key_prefix}_asset_path")
        expected_hash = st.text_input("Expected SHA-256 (recommended)", "", key=f"{key_prefix}_asset_hash")
        license_accepted = st.checkbox("I am authorised to use these model parameters/data under their licence", key=f"{key_prefix}_asset_license")
        if st.button("Register and verify asset", type="primary", disabled=not (asset_path.strip() and license_accepted), width="stretch", key=f"{key_prefix}_asset_register"):
            try:
                record = register_model_asset(
                    backend_asset,
                    asset_path,
                    workspace=workspace,
                    expected_sha256=expected_hash,
                    license_accepted=license_accepted,
                )
                st.success("Model asset registered and hashed.")
                smart_json(record, key=f"{key_prefix}_asset_record")
            except Exception as exc:
                st.error(f"Asset registration failed: {exc}")
        insight_callout(
            "No bundled fake weights",
            "BioIntel does not redistribute restricted model weights or mark an unverified path as ready. Register official/local assets and preserve their checksum and licence evidence.",
            tone="warning",
        )


__all__ = ["render_protein_design_execution_upgrade"]
