from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from biointel.projects.run_registry import compare_runs, register_run
from biointel.ui.operational_canvas import render_operational_canvas

from .engine import assess_module, format_support, release_manifest, statistical_audit
from .plans import PlanValidationError, build_protected_plan, plan_json, supported_tools
from .references import template_manifest
from .specs import PAGE_TO_MODULE, get_spec

ROOT = Path(__file__).resolve().parents[3]
RUN_DB = runtime_database_path(ROOT, "step127_scientific_runs.sqlite3")


def _streamlit():
    import streamlit as st
    return st


def _status_tone(tier: str) -> str:
    return {"A": "success", "B": "warning", "C": "info"}.get(tier, "info")


def _manifest_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def render_step127_sidebar_for_page(page_path: str | None) -> None:
    """Show an inexpensive capability summary without modifying locked page files."""
    st = _streamlit()
    normalized = str(page_path or "").replace("\\", "/")
    module_key = PAGE_TO_MODULE.get(normalized)
    if not module_key:
        return
    spec = get_spec(module_key)
    assessment = assess_module(module_key)
    with st.sidebar.expander("Scientific depth · Step 127", expanded=False):
        st.markdown(f"**{spec.title}**")
        st.caption(assessment.tier_label)
        st.progress(min(max(assessment.execution_readiness, 0.0), 1.0))
        st.caption(f"Tools available: {assessment.tools_available}/{assessment.tools_required}")
        if spec.locked_source:
            st.info("The page source remains protected; shared readiness, plans and manifests are available here and in the Step 127 center.")
        st.caption(spec.evidence_boundary)
        try:
            st.page_link("pages/172_Scientific_Depth_Command_Center.py", label="Open full depth center", width="stretch")
        except Exception:
            pass


def render_step127_upgrade_panel(module_key: str, *, expanded: bool = False) -> None:
    st = _streamlit()
    spec = get_spec(module_key)
    assessment = assess_module(module_key)
    with st.expander(f"Step 127 · {spec.title} scientific-depth upgrade", expanded=expanded):
        metrics = st.columns(4)
        metrics[0].metric("Execution tier", assessment.tier)
        metrics[1].metric("Pipeline readiness", f"{assessment.execution_readiness * 100:.0f}%")
        metrics[2].metric("Tools", f"{assessment.tools_available}/{assessment.tools_required}")
        metrics[3].metric("New capabilities", len(spec.features_added))
        if assessment.tier == "A":
            st.success(assessment.tier_label)
        elif assessment.tier == "B":
            st.warning(assessment.tier_label)
        else:
            st.info(assessment.tier_label)
        st.caption(spec.summary)

        pipeline_tab, features_tab, qc_tab, plan_tab, provenance_tab = st.tabs(
            ["Pipeline", "Features & blockers", "Scientific QC", "Protected plan", "Provenance"]
        )
        with pipeline_tab:
            frame = assessment.stage_frame().copy()
            if not frame.empty:
                frame["readiness"] = (frame["readiness"] * 100).round(0).astype(int).astype(str) + "%"
                st.dataframe(
                    frame[["label", "mode", "status", "readiness", "tools", "missing_tools", "validation_gate", "purpose"]],
                    width="stretch", hide_index=True,
                )
            st.info(spec.evidence_boundary)

        with features_tab:
            left, right = st.columns(2)
            with left:
                st.markdown("**Added/standardized capabilities**")
                for item in spec.features_added:
                    st.markdown(f"- {item}")
                st.markdown("**Accepted native/scientific formats**")
                st.caption(" · ".join(spec.native_formats))
            with right:
                st.markdown("**Statistical requirements**")
                for item in spec.statistical_requirements:
                    st.markdown(f"- {item}")
                st.markdown("**Release blockers**")
                for item in assessment.blockers[:18]:
                    st.markdown(f"- {item}")

        with qc_tab:
            st.caption("Optional preflight for a harmonized CSV/TSV table. It does not replace the module's own parser or specialist QC.")
            uploaded = st.file_uploader(
                "Upload a small table for statistical preflight",
                type=["csv", "tsv", "txt"],
                key=f"step127_qc_{module_key}",
            )
            if uploaded is not None:
                try:
                    separator = "\t" if uploaded.name.lower().endswith((".tsv", ".txt")) else ","
                    frame = pd.read_csv(uploaded, sep=separator, nrows=250_000)
                    options = ["None", *map(str, frame.columns)]
                    columns = st.columns(2)
                    group = columns[0].selectbox("Group column", options, key=f"step127_group_{module_key}")
                    replicate = columns[1].selectbox("Replicate/unit column", options, key=f"step127_rep_{module_key}")
                    audit = statistical_audit(
                        frame,
                        group_column=None if group == "None" else group,
                        replicate_column=None if replicate == "None" else replicate,
                    )
                    summary = pd.DataFrame([audit.to_dict()]).drop(columns=["blockers", "recommendations", "constant_numeric_columns"])
                    st.dataframe(summary, width="stretch", hide_index=True)
                    if audit.blockers:
                        for blocker in audit.blockers:
                            st.error(blocker)
                    if audit.recommendations:
                        for recommendation in audit.recommendations:
                            st.warning(recommendation)
                    st.download_button(
                        "Download QC audit",
                        json.dumps(audit.to_dict(), indent=2, sort_keys=True, default=str),
                        f"{module_key}_step127_qc.json",
                        "application/json",
                        key=f"step127_qc_download_{module_key}",
                    )
                except Exception as exc:
                    st.error(f"Preflight failed: {exc}")
            filename = st.text_input("Inspect native-format support by filename", key=f"step127_format_{module_key}")
            if filename.strip():
                render_operational_canvas(
                    title="Format-support canvas",
                    subtitle="Detected format support and safe next action.",
                    payload=format_support(filename.strip()),
                    stages=("Inspect filename", "Detect format", "Choose parser", "Validate"),
                    key=f"step127_format_canvas_{module_key}",
                )

        with plan_tab:
            tools = supported_tools(module_key)
            if not tools:
                st.info("This module currently uses built-in or Python-package workflows; no protected external command is required.")
            else:
                selected = st.selectbox("External tool", tools, key=f"step127_tool_{module_key}")
                raw_inputs = st.text_area(
                    "Input paths · one per line",
                    key=f"step127_inputs_{module_key}",
                    placeholder="C:\\BioIntelData\\input.fastq.gz",
                )
                output = st.text_input(
                    "Output directory",
                    value=str((ROOT / "workspace" / "step127" / module_key / selected).resolve()),
                    key=f"step127_output_{module_key}",
                )
                thread_count = st.slider("Threads", 1, 32, 4, key=f"step127_threads_{module_key}")
                reference = st.text_input("Reference/assembly/database identifier when required", key=f"step127_reference_{module_key}")
                if st.button("Build protected execution plan", key=f"step127_plan_{module_key}", width="stretch"):
                    paths = [line.strip() for line in raw_inputs.splitlines() if line.strip()]
                    parameters: dict[str, Any] = {"threads": thread_count}
                    if selected == "bcftools" and reference:
                        parameters["reference"] = reference
                    elif selected == "vep" and reference:
                        parameters["assembly"] = reference
                    elif selected == "snpEff" and reference:
                        parameters["genome"] = reference
                    elif selected == "busco" and reference:
                        parameters["lineage"] = reference
                    elif selected in {"mageck"} and reference:
                        parts = [part.strip() for part in reference.split(",")]
                        if len(parts) >= 2:
                            parameters.update({"treatment": parts[0], "control": parts[1]})
                    try:
                        plan = build_protected_plan(module_key, selected, paths, output, parameters=parameters)
                        st.session_state[f"step127_plan_payload_{module_key}"] = plan.to_dict()
                    except PlanValidationError as exc:
                        st.error(str(exc))
                payload = st.session_state.get(f"step127_plan_payload_{module_key}")
                if payload:
                    if payload.get("available"):
                        st.success(f"Tool detected via {payload.get('backend')}")
                    else:
                        st.warning("Plan is valid, but the executable is not installed/configured.")
                    st.code(" ".join(map(str, payload.get("argv", []))), language=None)
                    st.download_button(
                        "Download protected plan",
                        json.dumps(payload, indent=2, sort_keys=True, default=str),
                        f"{module_key}_{payload.get('tool', 'tool')}_plan.json",
                        "application/json",
                        key=f"step127_plan_download_{module_key}",
                    )

        with provenance_tab:
            manifest = release_manifest(module_key)
            render_operational_canvas(
                title="Readiness-provenance canvas",
                subtitle="Module identity, release posture and local readiness facts.",
                payload=manifest,
                stages=("Collect", "Fingerprint", "Review", "Export"),
                key=f"step127_provenance_{module_key}",
            )
            register_col, export_col = st.columns(2)
            if register_col.button("Register readiness snapshot", key=f"step127_register_{module_key}", width="stretch"):
                fingerprint = _manifest_fingerprint(manifest)
                register_run(
                    RUN_DB,
                    run_fingerprint=fingerprint,
                    project_code=f"STEP127-{module_key.upper()}",
                    project_name=spec.title,
                    status="readiness_snapshot",
                    quality_score=assessment.execution_readiness * 100,
                    input_rows=0,
                    output_rows=len(spec.features_added),
                    parameters={"tier": assessment.tier, "locked_source": spec.locked_source},
                    metrics={"tool_coverage": assessment.tools_available / max(assessment.tools_required, 1), "features": len(spec.features_added)},
                )
                st.success("Readiness snapshot registered locally.")
            export_col.download_button(
                "Download module manifest",
                json.dumps(manifest, indent=2, sort_keys=True, default=str),
                f"{module_key}_step127_manifest.json",
                "application/json",
                key=f"step127_manifest_download_{module_key}",
                width="stretch",
            )
            st.download_button(
                "Download reference-database contract",
                json.dumps(template_manifest(module_key), indent=2, sort_keys=True, default=str),
                f"{module_key}_reference_manifest_template.json",
                "application/json",
                key=f"step127_reference_template_{module_key}",
                width="stretch",
            )
            history = compare_runs(RUN_DB, project_code=f"STEP127-{module_key.upper()}", limit=10)
            if not history.empty:
                st.dataframe(history, width="stretch", hide_index=True)
