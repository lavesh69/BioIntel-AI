from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from biointel.ui.components import metric_cards, smart_dataframe, smart_json
from biointel.scientific_depth import assess_evidence_readiness, profile_for, render_depth_upgrade_panel
from biointel.ui.theme import apply_theme, section_title
from biointel.ui.scientific_visuals import render_generic_visual_explorer, render_scientific_visual_suite
from biointel.ui.nextgen_specialist_canvases import render_nextgen_specialist_canvas
from biointel.ui.nextgen_intelligence import render_nextgen_intelligence_workspace
from biointel.peak_potential.catalog import is_peak_target
from biointel.peak_potential.ui import render_peak_assurance_workspace
from biointel.ui.workbench import (
    apply_analysis_filters,
    compact_module_header,
    render_analysis_controls,
    render_column_mapping,
    render_data_readiness,
    render_export_panel,
    render_results_workbench,
    render_source_selector,
    run_analysis_once,
)

from .catalog import MODULE_BY_KEY, NextGenModule
from .biomedical_expansion import NEW_BIOMEDICAL_KEYS
from .module_upgrade_v133 import MODULE_ONLY_KEYS, render_module_upgrade_panel
from .module_scientific_v135 import render_module_scientific_v135_panel
from .native_execution_v136 import render_native_execution_v136_panel
from .scientific import analyse, demo_frame, evidence_manifest, normalise, read_upload
from .services import (
    LocalCopilot,
    NextGenStore,
    ProvenanceLedger,
    build_report_bundle,
    inspect_file_bytes,
    runtime_environment,
    sha256_bytes,
    state_root,
)

# Shared workbench defaults to upload mode and preserves the Step 105 contract:
# ["Upload scientific data", "Deterministic demonstration data"]

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TABLE_UPLOADS = ["csv", "tsv", "txt", "json", "xlsx", "xls"]
MODULE_UPLOADS: dict[str, list[str]] = {
    "population_gwas": ["vcf", "gz"],
    "structural_variant_repeat": ["vcf", "gz", "bed", "bedpe"],
    "rna_isoform_splicing": ["gtf", "gff", "gff3", "bed"],
    "epitranscriptomics": ["gtf", "gff", "gff3", "bed"],
    "strain_microbiome": ["fa", "fasta", "faa", "fna"],
    "cell_atlas_mapping": ["h5ad"],
    "phenotypic_screening": ["png", "jpg", "jpeg", "tif", "tiff"],
    "organoid_3d": ["png", "jpg", "jpeg", "tif", "tiff"],
    "protein_language_design": ["fa", "fasta", "faa", "fna"],
    "enzyme_pathway_design": ["fa", "fasta", "faa", "fna"],
    "host_pathogen_interaction": ["fa", "fasta", "faa", "fna"],
    "virology_evolution": ["fa", "fasta", "fna", "vcf", "gz"],
    "rare_variant_family": ["vcf", "gz", "bed", "bedpe"],
    "digital_pathology_foundation": ["svs", "ndpi", "mrxs", "scn", "png", "jpg", "jpeg", "tif", "tiff", "ome.tif", "ome.tiff"],
    "long_read_epigenome": ["bam", "cram", "bed", "bed.gz", "bedmethyl", "bedmethyl.gz", "vcf", "vcf.gz", "tsv", "txt"],
    "single_cell_long_read_isoforms": ["bam", "cram", "gtf", "gff", "gff3", "h5ad", "mtx", "mtx.gz"],
    "amr_surveillance": ["fastq", "fq", "fastq.gz", "fq.gz", "fa", "fasta", "fna", "faa", "gff", "gff3", "vcf", "vcf.gz"],
    "spatial_medicine_tme": ["h5ad", "mtx", "mtx.gz", "h5", "hdf5", "png", "jpg", "jpeg", "tif", "tiff", "ome.tif", "ome.tiff"],
    "gene_therapy_vector": ["fa", "fasta", "fna", "gb", "gbk", "genbank", "vcf"],
    "cell_therapy_cart": ["fa", "fasta", "faa", "fna", "gb", "gbk", "genbank"],
    "protein_ligand_codesign": ["pdb", "cif", "mmcif", "sdf", "mol", "mol2", "pdbqt"],
    "pangenome_population_medicine": ["gfa", "gfa1", "gfa2", "vcf", "vcf.gz", "bcf", "fa", "fasta", "fna"],
    "biomedical_foundation_model_hub": ["onnx", "safetensors", "pt", "pth", "bin", "gguf", "yaml", "yml"],
    "federated_biomedical_ai": ["jsonl", "parquet", "feather"],
    "clinical_biomarker_survival": ["jsonl", "parquet", "feather"],
    "pharmacovigilance_intelligence": ["jsonl", "xml", "parquet", "feather"],
    "synthetic_cohort_trial": ["jsonl", "yaml", "yml", "parquet", "feather"],
    "autonomous_lab_planner": ["jsonl", "yaml", "yml"],
}


def _supported_uploads(module_key: str) -> list[str]:
    return list(dict.fromkeys(TABLE_UPLOADS + MODULE_UPLOADS.get(module_key, [])))


SUPPORTED_UPLOADS = sorted(
    {extension for values in [TABLE_UPLOADS, *MODULE_UPLOADS.values()] for extension in values}
)


def _render_chart(
    module: NextGenModule,
    data: pd.DataFrame,
    result: pd.DataFrame,
    secondary: pd.DataFrame | None,
    extras: dict[str, pd.DataFrame] | None = None,
) -> None:
    render_nextgen_specialist_canvas(module.key, result=result, secondary=secondary)
    render_scientific_visual_suite(
        module.key,
        data=data,
        result=result,
        secondary=secondary,
        extras=extras,
        key=f"ng_visuals_{module.key}",
    )

def render_scientific_module(module_key: str) -> None:
    module = MODULE_BY_KEY[module_key]
    compact_module_header(
        title=module.title,
        summary=module.summary,
        icon=module.icon,
        category=module.category,
        tags=("Raw-file aware", "Cached analysis", "Reproducible export"),
        boundary=module.boundary,
    )
    has_depth = profile_for(module.key) is not None
    has_module_upgrade = module.key in MODULE_ONLY_KEYS
    has_native_pipeline = module.key in NEW_BIOMEDICAL_KEYS
    has_peak = is_peak_target(page_key=module.key, category=module.category, title=module.title)
    labels = ["1 · Prepare & run", "2 · Explore results", "3 · Export", "4 · Scientific intelligence"]
    next_index = 5
    if has_peak:
        labels.append(f"{next_index} · Peak assurance")
        next_index += 1
    if has_module_upgrade:
        labels.append(f"{next_index} · Module upgrade")
        next_index += 1
    if has_native_pipeline:
        labels.append(f"{next_index} · Native pipeline")
        next_index += 1
    if has_depth:
        labels.append(f"{next_index} · Scientific depth")
        next_index += 1
    labels.append(f"{next_index} · Guide")
    tabs = st.tabs(labels)
    tab_prepare, tab_results, tab_export, tab_intelligence = tabs[:4]
    cursor = 4
    tab_peak = tabs[cursor] if has_peak else None
    cursor += int(has_peak)
    tab_module_upgrade = tabs[cursor] if has_module_upgrade else None
    cursor += int(has_module_upgrade)
    tab_native_pipeline = tabs[cursor] if has_native_pipeline else None
    cursor += int(has_native_pipeline)
    tab_depth = tabs[cursor] if has_depth else None
    cursor += int(has_depth)
    tab_guide = tabs[cursor]

    with tab_prepare:
        section_title("Prepare data and run analysis", "▤")
        source = render_source_selector(
            key=f"ngwb_{module.key}",
            module_key=module.key,
            extensions=_supported_uploads(module.key),
            required_columns=module.required_columns,
            project_root=PROJECT_ROOT,
            demo_min=60,
            demo_max=360,
            demo_default=120,
            demo_step=30,
        )
        raw = pd.DataFrame(columns=module.required_columns)
        if source.mode == "demo":
            raw = demo_frame(module, source.demo_size)
        elif source.upload is not None and not source.is_large_upload:
            try:
                raw = read_upload(source.upload, module.key)
            except Exception as exc:
                st.error(f"Input failed safely: {exc}")
        elif source.is_large_upload:
            st.info("The file is staged through large-file mode. Use the Background Job Center for bounded processing and validation.")

        raw = render_column_mapping(raw, module.required_columns, key=f"ngwb_{module.key}") if not raw.empty else raw
        try:
            data = normalise(raw, module) if not raw.empty else raw
        except Exception as exc:
            st.error(f"Schema normalisation failed safely: {exc}")
            data = pd.DataFrame(columns=module.required_columns)

        readiness = render_data_readiness(data, module.required_columns, key=f"ngwb_{module.key}")
        if not data.empty:
            with st.expander("Preview imported records", expanded=True):
                smart_dataframe(data.head(1000), height=360, key=f"ngwb_{module.key}_preview")

        st.markdown("#### Analysis configuration")
        parameters = render_analysis_controls(data, module_key=module.key, key=f"ngwb_{module.key}")
        filtered_data = apply_analysis_filters(data, parameters)
        if len(filtered_data) != len(data):
            st.caption(f"Advanced filters retain {len(filtered_data):,} of {len(data):,} records.")
        if readiness["missing_required"]:
            st.warning("Map or repair the required fields before relying on the analysis result.")

        run_state = run_analysis_once(
            state_key=f"ngwb_{module.key}_run_state",
            data=data,
            parameters=parameters,
            analyser=lambda frame, threshold: analyse(frame, module, threshold),
            module_key=module.key,
        )
        if run_state is not None:
            smart_json(
                run_state.summary,
                title="Current run summary",
                download_name=f"{module.key}_summary.json",
                key=f"ngwb_{module.key}_summary",
            )

    with tab_results:
        section_title("Explore current results", "📊")
        render_results_workbench(
            run_state=run_state,
            key=f"ngwb_{module.key}",
            chart_renderer=lambda result, secondary, extras: _render_chart(module, data, result, secondary, extras),
            boundary=module.boundary,
            module_key=module.key,
        )

    with tab_export:
        section_title("Reproducible result package", "📦")
        manifest = None
        if run_state is not None:
            manifest = evidence_manifest(
                module,
                data,
                run_state.summary,
                {**run_state.parameters, "engine": "biointel.nextgen.scientific.v3"},
            )
            depth_profile = profile_for(module.key)
            readiness_report = assess_evidence_readiness(
                module.key,
                data,
                required_columns=module.required_columns,
                profile_references=depth_profile.references if depth_profile else (),
                profile_validations=depth_profile.validations if depth_profile else (),
                source_mode=source.mode,
                run_summary=run_state.summary,
            )
            manifest["scientific_readiness"] = readiness_report.manifest
            manifest["completed_at_utc"] = run_state.completed_at_utc
        render_export_panel(
            module_key=module.key,
            run_state=run_state,
            manifest=manifest,
            key=f"ngwb_{module.key}",
        )

    with tab_intelligence:
        section_title("Cross-module scientific intelligence", "🧠")
        render_nextgen_intelligence_workspace(
            module=module,
            data=data,
            run_state=run_state,
            analyser=lambda frame, threshold: analyse(frame, module, threshold),
            key=f"ngwb_{module.key}_intelligence",
        )

    if tab_peak is not None:
        with tab_peak:
            section_title("Peak scientific assurance", "✓")
            render_peak_assurance_workspace(
                page_key=module.key,
                title=module.title,
                category=module.category,
                input_frame=data,
                result_frame=run_state.result if run_state is not None else None,
                secondary_frame=run_state.secondary if run_state is not None else None,
                extra_tables=run_state.extras if run_state is not None else None,
                run_manifest=(
                    {
                        "summary": run_state.summary,
                        "parameters": run_state.parameters,
                        "completed_at_utc": run_state.completed_at_utc,
                    }
                    if run_state is not None
                    else None
                ),
            )

    if tab_module_upgrade is not None:
        with tab_module_upgrade:
            render_module_upgrade_panel(
                module.key,
                data,
                run_state,
                key_prefix=f"ngwb_module_upgrade_{module.key}",
            )
            render_module_scientific_v135_panel(
                module.key,
                data,
                run_state,
                key_prefix=f"ngwb_module_science_v135_{module.key}",
            )

    if tab_native_pipeline is not None:
        with tab_native_pipeline:
            render_native_execution_v136_panel(
                module.key,
                key_prefix=f"ngwb_native_v136_{module.key}",
            )

    if tab_depth is not None:
        with tab_depth:
            render_depth_upgrade_panel(
                module.key,
                data,
                key_prefix=f"ngwb_depth_{module.key}",
                expanded=True,
                source_mode=source.mode,
                run_summary=run_state.summary if run_state is not None else None,
            )

    with tab_guide:
        section_title("Purpose and safe operating guide", "📘")
        st.markdown(f"**Purpose:** {module.purpose}")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Accepted inputs**")
            for item in module.accepted_inputs:
                st.markdown(f"- {item}")
        with c2:
            st.markdown("**Generated outputs**")
            for item in module.outputs:
                st.markdown(f"- {item}")
        st.markdown("**Recommended workflow**")
        for index, step in enumerate(module.workflow, start=1):
            st.markdown(f"{index}. {step}")
        with st.expander("Scientific boundary", expanded=False):
            st.warning(module.boundary, icon="⚠️")

def _records_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    cleaned = []
    for record in records:
        cleaned.append({key: json.dumps(value, default=str) if isinstance(value, (dict, list)) else value for key, value in record.items()})
    return pd.DataFrame(cleaned)


def _render_file_inspector(module: NextGenModule) -> None:
    upload = st.file_uploader("Select a file for bounded inspection", key="ng_inspector_upload")
    if upload is not None:
        try:
            report = inspect_file_bytes(upload.getvalue(), upload.name)
            metric_cards([("Size", f"{report.size_bytes / 1024:.1f} KB", "File bytes"), ("Format", report.detected_format, f"Confidence {report.confidence:.0%}"), ("SHA-256", report.sha256[:16] + "…", "Content identity"), ("Risks", len(report.risks), "Review indicators")])
            smart_json(asdict(report), title="Inspection manifest", download_name=f"{Path(upload.name).stem}_inspection.json", key="ng_inspection_json")
            if report.preview_kind == "records" and report.preview:
                smart_dataframe(pd.DataFrame(report.preview), height=360, key="ng_inspection_preview")
            elif report.preview:
                st.code("\n".join(map(str, report.preview[:50])))
            if report.risks:
                for risk in report.risks:
                    st.warning(risk)
        except Exception as exc:
            st.error(f"Inspection failed safely: {exc}")


def _render_project_workspace(store: NextGenStore) -> None:
    c1, c2 = st.columns([1, 2])
    with c1:
        with st.form("ng_project_create"):
            name = st.text_input("Project name")
            description = st.text_area("Description")
            submitted = st.form_submit_button("Create project", width="stretch")
        if submitted:
            try:
                st.success(f"Created {store.create_project(name, description)['project_id']}")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    projects = store.list_projects()
    with c2:
        if not projects:
            st.info("Create the first project.")
            return
        options = {f"{p['name']} · {p['project_id'][-8:]}": p["project_id"] for p in projects}
        selected = st.selectbox("Active project", list(options), key="ng_project_select")
        project_id = options[selected]
        upload = st.file_uploader("Attach a content-addressed project asset", key="ng_project_asset")
        module_key = st.text_input("Producing module key", value="manual_import")
        if st.button("Attach asset", width="stretch", disabled=upload is None):
            try:
                asset = store.attach_asset(project_id, upload.getvalue(), upload.name, module_key=module_key, media_type=upload.type or "")
                st.success(f"Attached {asset['logical_name']}")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
        label = st.text_input("Snapshot label", value="Milestone snapshot")
        if st.button("Create immutable snapshot", width="stretch"):
            snap = store.create_snapshot(project_id, label); st.success(f"Snapshot {snap['manifest_sha256'][:16]}… created")
        assets = store.list_assets(project_id); snapshots = store.list_snapshots(project_id)
        st.markdown("**Project assets**")
        smart_dataframe(_records_frame(assets), height=300, key="ng_project_assets") if assets else st.caption("No assets attached.")
        st.markdown("**Snapshots**")
        smart_dataframe(_records_frame(snapshots), height=260, key="ng_project_snapshots") if snapshots else st.caption("No snapshots yet.")


def _default_workflow() -> dict[str, Any]:
    return {
        "name": "QC to report",
        "nodes": [
            {"id": "upload", "module": "file_inspector", "input_type": "file", "output_type": "table"},
            {"id": "analyse", "module": "population_gwas", "input_type": "table", "output_type": "results"},
            {"id": "report", "module": "unified_report_builder", "input_type": "results", "output_type": "report"},
        ],
        "edges": [
            {"source": "upload", "target": "analyse", "output_type": "table", "input_type": "table"},
            {"source": "analyse", "target": "report", "output_type": "results", "input_type": "results"},
        ],
    }


def _render_workflow(store: NextGenStore) -> None:
    default = _default_workflow()
    tab_visual, tab_json = st.tabs(["Visual node/edge editor", "Raw workflow JSON"])
    with tab_visual:
        node_frame = pd.DataFrame(default["nodes"])
        edge_frame = pd.DataFrame(default["edges"])
        nodes = st.data_editor(node_frame, num_rows="dynamic", width="stretch", key="ng_workflow_nodes")
        edges = st.data_editor(edge_frame, num_rows="dynamic", width="stretch", key="ng_workflow_edges")
        name = st.text_input("Workflow name", value=default["name"], key="ng_workflow_name")
        definition = {"name": name, "nodes": nodes.replace({np.nan: None}).to_dict("records"), "edges": edges.replace({np.nan: None}).to_dict("records")}
        validation = store.validate_workflow(definition)
        smart_json(validation, title="Typed DAG validation", key="ng_workflow_visual_validation")
        if validation["topological_order"]:
            plot = pd.DataFrame({"node": validation["topological_order"], "order": range(len(validation["topological_order"])), "lane": [0] * len(validation["topological_order"])})
            st.plotly_chart(px.scatter(plot, x="order", y="lane", text="node", title="Validated execution order").update_traces(marker_size=24, textposition="top center"), width="stretch")
        if validation["valid"] and st.button("Save visual workflow version", width="stretch"):
            record = store.save_workflow(name or "Workflow", definition)
            st.success(f"Saved {record['workflow_id']} v{record['version']}")
    with tab_json:
        raw = st.text_area("Workflow JSON", value=json.dumps(default, indent=2), height=420, key="ng_workflow_json")
        try:
            raw_definition = json.loads(raw)
            raw_validation = store.validate_workflow(raw_definition)
            smart_json(raw_validation, title="DAG validation", key="ng_workflow_json_validation")
            if raw_validation["valid"] and st.button("Save JSON workflow version", width="stretch"):
                record = store.save_workflow(str(raw_definition.get("name", "Workflow")), raw_definition)
                st.success(f"Saved {record['workflow_id']} v{record['version']}")
        except Exception as exc:
            st.error(f"Invalid JSON: {exc}")
    workflows = store.list_workflows()
    if workflows:
        smart_dataframe(_records_frame(workflows), height=320, key="ng_workflows")


def _run_one_demo_job(queue: Any) -> str:
    job = queue.claim_next(worker_id="step104-ui-worker")
    if job is None:
        return "No queued job was available."
    queue.update_progress(job.job_id, progress_percent=10, current_stage="prepare", message="Validated bounded payload")
    control = queue.control_state(job.job_id)
    if control.get("cancel_requested"):
        queue.fail(job.job_id, "Cancelled before execution", retry=False); return f"Cancelled {job.job_id}"
    queue.update_progress(job.job_id, progress_percent=55, current_stage="execute", message="Executed deterministic local demonstration")
    queue.save_checkpoint(job.job_id, {"stage": "execute", "progress": 55}, stage="execute")
    queue.update_progress(job.job_id, progress_percent=90, current_stage="validate", message="Validated output schema")
    queue.complete(job.job_id, {"status": "ok", "payload_sha256": sha256_bytes(json.dumps(job.payload, sort_keys=True).encode()), "completed_by": "step104-ui-worker"})
    return f"Completed {job.job_id}"


def _render_jobs(store: NextGenStore) -> None:
    queue = store.job_queue()
    queue.recover_orphaned_jobs(stale_after_seconds=180)
    c1, c2, c3 = st.columns(3)
    with c1:
        job_type = st.text_input("Job type", value="bounded_demo")
    with c2:
        priority = st.number_input("Priority", min_value=1, max_value=1000, value=100)
    with c3:
        max_attempts = st.number_input("Max attempts", min_value=1, max_value=10, value=3)
    payload_text = st.text_area("Payload JSON", value='{"module":"step104","records":100}', height=120)
    if st.button("Submit persistent job", width="stretch"):
        try:
            job = queue.submit(job_type, json.loads(payload_text), priority=int(priority), max_attempts=int(max_attempts), resources={"max_memory_mb": 2048, "max_runtime_seconds": 900}, estimated_seconds=5)
            st.success(f"Submitted {job.job_id}")
        except Exception as exc:
            st.error(str(exc))
    if st.button("Run one queued bounded job", width="stretch"):
        try: st.success(_run_one_demo_job(queue))
        except Exception as exc: st.error(str(exc))
    summary = queue.orchestration_summary(); metric_cards([("Jobs", summary["jobs"], "Persistent records"), ("Events", summary["events"], "Lifecycle events"), ("Artifacts", summary["artifacts"], "Output records"), ("Workers", summary["workers"], "Known heartbeats")])
    jobs = [job.__dict__ for job in queue.list(limit=200)]
    job_frame = _records_frame(jobs)
    if jobs:
        smart_dataframe(job_frame, height=420, key="ng_jobs_table")
        render_generic_visual_explorer(
            job_frame,
            key="ng_jobs_visuals",
            heading="Queue and execution visual analytics",
        )
    else:
        st.info("No jobs have been submitted.")
    if jobs:
        selected = st.selectbox("Inspect job", [x["job_id"] for x in jobs], key="ng_job_inspect")
        smart_json(queue.timeline(selected), title="Job timeline", key="ng_job_timeline")
        a1, a2, a3, a4 = st.columns(4)
        if a1.button("Request pause", key="ng_job_pause", width="stretch"):
            try: queue.request_pause(selected); st.success("Pause requested")
            except Exception as exc: st.error(str(exc))
        if a2.button("Resume", key="ng_job_resume", width="stretch"):
            try: queue.resume(selected); st.success("Job resumed")
            except Exception as exc: st.error(str(exc))
        if a3.button("Cancel", key="ng_job_cancel", width="stretch"):
            try: queue.request_cancel(selected); st.success("Cancellation requested")
            except Exception as exc: st.error(str(exc))
        if a4.button("Retry", key="ng_job_retry", width="stretch"):
            try: queue.retry(selected); st.success("Job returned to queue")
            except Exception as exc: st.error(str(exc))


def _render_report_builder() -> None:
    title = st.text_input("Report title", value="BioIntel AI Scientific Report")
    methods = st.text_area("Methods and parameters", value="Describe input data, software versions, parameters and quality-control steps.", height=130)
    results = st.text_area("Results", value="Summarise validated observations without overstating evidence.", height=130)
    limitations = st.text_area("Limitations", value="State computational, experimental and external-validation limitations.", height=130)
    citations = st.text_area("Citations / evidence IDs", value="Add DOI, PMID or local evidence identifiers.", height=100)
    sections = [{"heading": "Methods and parameters", "body": methods}, {"heading": "Results", "body": results}, {"heading": "Limitations", "body": limitations}, {"heading": "Citations", "body": citations}]
    manifest = {"schema": "biointel.unified_report.v2", "environment": runtime_environment(), "claim_review_required": True, "sections": [x["heading"] for x in sections]}
    bundle = build_report_bundle(title, sections, manifest)
    c1, c2, c3, c4 = st.columns(4)
    c1.download_button("HTML", bundle["html"], "biointel_report.html", "text/html", width="stretch")
    c2.download_button("DOCX", bundle["docx"], "biointel_report.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", width="stretch")
    c3.download_button("PDF", bundle["pdf"], "biointel_report.pdf", "application/pdf", width="stretch")
    c4.download_button("Manifest", bundle["manifest"], "biointel_report_manifest.json", "application/json", width="stretch")


def _render_references(store: NextGenStore) -> None:
    upload = st.file_uploader("Select a local reference archive or database file", key="ng_reference_upload")
    c1, c2, c3 = st.columns(3)
    name = c1.text_input("Database name", value="Reference database")
    version = c2.text_input("Version", value="2026.1")
    license_name = c3.text_input("License", value="Review required")
    if st.button("Register and checksum reference", disabled=upload is None, width="stretch"):
        try:
            target_dir = state_root(PROJECT_ROOT) / "reference_files"; target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"{sha256_bytes(upload.getvalue())[:12]}-{Path(upload.name).name}"; target.write_bytes(upload.getvalue())
            record = store.register_reference(name, version, target, license_name=license_name, compatibility={"biointel": ">=11.0.0", "source_file": upload.name}); st.success(f"Registered {record['reference_id']}")
        except Exception as exc: st.error(str(exc))
    refs = store.list_references()
    if refs:
        reference_frame = _records_frame(refs)
        smart_dataframe(reference_frame, height=340, key="ng_references")
        render_generic_visual_explorer(
            reference_frame,
            key="ng_reference_visuals",
            heading="Reference database visual analytics",
        )
        selected = st.selectbox("Activate a pinned version", {f"{x['database_name']} {x['version']}": x["reference_id"] for x in refs}, key="ng_reference_select")
        if st.button("Activate selected reference"):
            store.activate_reference(selected); st.success("Reference activated and sibling versions deactivated."); st.rerun()
        verify = store.verify_references(); smart_dataframe(verify, height=260, key="ng_reference_verify")
        metric_cards([("Registered versions", len(refs), "Pinned local assets"), ("Verified now", int(verify["checksum_match"].sum()), "Checksum matches"), ("Storage", f"{sum(int(x['size_bytes']) for x in refs) / 1024 / 1024:.2f} MB", "Registered bytes"), ("Active", int(sum(bool(x['active']) for x in refs)), "Selected versions")])
    else: st.info("No reference versions registered.")


def _render_provenance() -> None:
    ledger = ProvenanceLedger(PROJECT_ROOT)
    event_type = st.text_input("Event type", value="analysis_completed")
    payload = st.text_area("Event payload JSON", value='{"module":"step104","input_sha256":"example","output_sha256":"example"}', height=140)
    if st.button("Append hash-chained event", width="stretch"):
        try: st.success(f"Appended {ledger.append(event_type, json.loads(payload))['record_hash'][:16]}…")
        except Exception as exc: st.error(str(exc))
    verification = ledger.verify(); smart_json(verification, title="Ledger integrity", key="ng_ledger_verify")
    records = ledger.records()
    if not records.empty:
        smart_dataframe(records, height=390, key="ng_ledger_records")
        render_generic_visual_explorer(
            records,
            key="ng_ledger_visuals",
            heading="Provenance ledger visual analytics",
        )
    else:
        st.info("The ledger is empty.")
    st.download_button("Download ledger", ledger.path.read_bytes(), "provenance_ledger.jsonl", "application/jsonl", width="stretch")


def _render_evidence(store: NextGenStore) -> None:
    tab1, tab2 = st.tabs(["Register evidence", "Claim matrix"])
    with tab1:
        c1, c2 = st.columns(2)
        identifier = c1.text_input("DOI / PMID / local ID")
        kind = c2.selectbox("Identifier type", ["DOI", "PMID", "LOCAL"])
        title = st.text_input("Title")
        c3, c4, c5 = st.columns(3)
        year = c3.number_input("Year", min_value=1800, max_value=2100, value=2026)
        status = c4.selectbox("Status", ["unverified", "active", "retracted", "corrected", "conflicting"])
        level = c5.selectbox("Evidence level", ["Unrated", "Low", "Moderate", "High"])
        if st.button("Register citation", width="stretch"):
            try: st.success(f"Registered {store.register_citation(identifier, kind, title, year=int(year), status=status, evidence_level=level)['citation_id']}")
            except Exception as exc: st.error(str(exc))
        claim = st.text_area("Claim text")
        if st.button("Create claim", width="stretch"):
            try: st.session_state["ng_last_claim"] = store.create_claim(claim)["claim_id"]; st.success(st.session_state["ng_last_claim"])
            except Exception as exc: st.error(str(exc))
        citation_records = store.list_citations()
        if st.session_state.get("ng_last_claim") and citation_records:
            options = {f"{x['title']} · {x['citation_id'][-8:]}": x["citation_id"] for x in citation_records}
            selection = st.selectbox("Link latest claim to citation", options)
            support = st.selectbox("Relationship", ["supports", "contradicts", "context"])
            if st.button("Link claim and citation"):
                store.link_claim(st.session_state["ng_last_claim"], options[selection], support); st.success("Linked")
    with tab2:
        matrix = store.evidence_matrix()
        smart_dataframe(matrix, height=500, key="ng_evidence_matrix") if not matrix.empty else st.info("No claims or citations registered.")


def _render_model_registry(store: NextGenStore) -> None:
    upload = st.file_uploader("Model file", key="ng_model_upload")
    c1, c2, c3 = st.columns(3)
    name = c1.text_input("Model name", value="Research model")
    version = c2.text_input("Model version", value="1.0.0")
    framework = c3.text_input("Framework", value="Unknown")
    protocol = st.text_area("Locked evaluation protocol", value="Specify dataset split, metrics, thresholds and external-validation requirements.")
    metrics_text = st.text_area("Metrics JSON", value='{"roc_auc":0.0,"calibration_status":"not_evaluated"}', height=100)
    if st.button("Register immutable model version", disabled=upload is None, width="stretch"):
        try:
            target_dir = state_root(PROJECT_ROOT) / "model_files"; target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"{sha256_bytes(upload.getvalue())[:12]}-{Path(upload.name).name}"; target.write_bytes(upload.getvalue())
            model = store.register_model(name, version, target, framework=framework, evaluation_protocol=protocol, metrics=json.loads(metrics_text), dataset_manifest={"status": "required"}); st.success(model["model_id"])
        except Exception as exc: st.error(str(exc))
    models = store.list_models()
    if models:
        model_frame = _records_frame(models)
        smart_dataframe(model_frame, height=400, key="ng_models")
        render_generic_visual_explorer(
            model_frame,
            key="ng_model_registry_visuals",
            heading="Model lifecycle visual analytics",
        )
        selected = st.selectbox("Model lifecycle action", {f"{x['name']} {x['version']}": x["model_id"] for x in models}, key="ng_model_selected")
        c1, c2 = st.columns(2); status = c1.selectbox("Status", ["registered", "review", "approved", "deployed", "retired", "rejected"]); reviewer = c2.text_input("Reviewer")
        note = st.text_input("Decision note")
        if st.button("Apply gated status change"):
            try: store.set_model_status(selected, status, reviewer=reviewer, note=note); st.success("Lifecycle status updated"); st.rerun()
            except Exception as exc: st.error(str(exc))
    else: st.info("No models registered.")


def _render_instruments(store: NextGenStore) -> None:
    c1, c2 = st.columns(2)
    name = c1.text_input("Connector name", value="Local instrument export")
    folder = c2.text_input("Watched folder path", value=str(PROJECT_ROOT / "data" / "instrument_inbox"))
    patterns = st.text_input("File patterns, comma separated", value="*.csv,*.tsv,*.fcs,*.mzML,*.fastq.gz")
    if st.button("Register watched folder", width="stretch"):
        try:
            Path(folder).mkdir(parents=True, exist_ok=True)
            st.success(store.add_connector(name, folder, patterns=[x.strip() for x in patterns.split(",") if x.strip()])["connector_id"])
        except Exception as exc: st.error(str(exc))
    connectors = store.list_connectors()
    if connectors:
        smart_dataframe(_records_frame(connectors), height=300, key="ng_connectors")
        options = {f"{x['name']} · {x['folder_path']}": x["connector_id"] for x in connectors}; choice = st.selectbox("Connector to scan", options)
        if st.button("Scan stable files and deduplicate", width="stretch"):
            try: smart_json(store.scan_connector(options[choice]), title="Scan result", key="ng_connector_scan")
            except Exception as exc: st.error(str(exc))


def _render_reviews(store: NextGenStore) -> None:
    with st.form("ng_review_create"):
        c1, c2, c3 = st.columns(3)
        result_ref = c1.text_input("Result reference", value="project/result.csv")
        version = c2.text_input("Result version", value="sha256:...")
        reviewer = c3.text_input("Reviewer", value="Scientific reviewer")
        submit = st.form_submit_button("Create version-linked review", width="stretch")
    if submit:
        try: st.success(store.create_review(result_ref, version, reviewer)["review_id"])
        except Exception as exc: st.error(str(exc))
    reviews = store.list_reviews()
    if not reviews:
        st.info("No reviews registered."); return
    review_frame = _records_frame(reviews)
    smart_dataframe(review_frame, height=300, key="ng_reviews")
    render_generic_visual_explorer(
        review_frame,
        key="ng_review_visuals",
        heading="Scientific review visual analytics",
    )
    choice = st.selectbox("Open review", {f"{x['result_ref']} · {x['review_id'][-8:]}": x["review_id"] for x in reviews})
    review_id = choice
    if isinstance(choice, str) and not choice.startswith("review-"):
        review_id = {f"{x['result_ref']} · {x['review_id'][-8:]}": x["review_id"] for x in reviews}[choice]
    review = store.get_review(review_id); smart_json(review, title="Review record", key="ng_review_record")
    author = st.text_input("Comment author", value="Reviewer"); body = st.text_area("Version-linked comment")
    if st.button("Add comment", disabled=bool(review["locked"])):
        try: store.add_review_comment(review_id, author, body); st.success("Comment added"); st.rerun()
        except Exception as exc: st.error(str(exc))
    decision = st.selectbox("Final decision", ["approved", "rejected", "changes_requested"])
    if st.button("Record decision and lock review", disabled=bool(review["locked"])):
        try: store.decide_review(review_id, decision, lock=True); st.success("Review locked"); st.rerun()
        except Exception as exc: st.error(str(exc))


def _render_copilot() -> None:
    question = st.text_area("Ask about local BioIntel documentation or project evidence", value="How should I validate a scientific result before reporting it?", height=120)
    if st.button("Retrieve local evidence", width="stretch"):
        with st.spinner("Searching approved local sources..."):
            result = LocalCopilot(PROJECT_ROOT).answer(question)
        if result["blocked"]: st.warning(result["answer"])
        else:
            st.markdown(result["answer"])
            smart_dataframe(pd.DataFrame(result["sources"]), height=360, key="ng_copilot_sources") if result["sources"] else None
            st.caption(f"Uncertainty: {result['uncertainty']}")


def _render_lakehouse(store: NextGenStore) -> None:
    folder = st.text_input("Bounded folder to index", value=str(PROJECT_ROOT / "data"))
    c1, c2 = st.columns(2)
    max_files = c1.number_input("Maximum files", 10, 10000, 1000)
    max_gb = c2.number_input("Maximum bytes to hash (GB)", 0.1, 20.0, 2.0)
    if st.button("Index or refresh metadata", width="stretch"):
        try: smart_json(store.index_folder(folder, max_files=int(max_files), max_hash_bytes=int(max_gb * 1_000_000_000)), title="Index result", key="ng_index_result")
        except Exception as exc: st.error(str(exc))
    c1, c2, c3 = st.columns(3); query = c1.text_input("Search"); extension = c2.text_input("Extension filter"); duplicates = c3.checkbox("Duplicates only")
    results = store.search_files(query, extension=extension, duplicates_only=duplicates)
    if not results.empty:
        smart_dataframe(results, height=500, key="ng_lakehouse_results")
        render_generic_visual_explorer(
            results,
            key="ng_lakehouse_visuals",
            heading="Data lakehouse visual analytics",
        )
    else:
        st.info("No indexed files match the current filters.")


def _render_benchmarks(store: NextGenStore) -> None:
    definition_text = st.text_area("Locked benchmark definition JSON", value=json.dumps({"expected": {"accuracy": 0.9, "runtime_seconds": 10}, "tolerances": {"accuracy": 0.02, "runtime_seconds": 2}, "scope": "demonstration"}, indent=2), height=220)
    c1, c2 = st.columns(2); name = c1.text_input("Benchmark name", value="Deterministic validation check"); version = c2.text_input("Version", value="1.0")
    if st.button("Register locked benchmark", width="stretch"):
        try: st.success(store.register_benchmark(name, version, json.loads(definition_text))["benchmark_id"])
        except Exception as exc: st.error(str(exc))
    benchmarks = store.list_benchmarks()
    if benchmarks:
        benchmark_frame = _records_frame(benchmarks)
        smart_dataframe(benchmark_frame, height=280, key="ng_benchmarks")
        render_generic_visual_explorer(
            benchmark_frame,
            key="ng_benchmark_visuals",
            heading="Benchmark catalogue visual analytics",
        )
        options = {f"{x['name']} {x['version']}": x["benchmark_id"] for x in benchmarks}; choice = st.selectbox("Benchmark to run", options)
        candidate = st.text_area("Candidate metrics JSON", value='{"accuracy":0.91,"runtime_seconds":11}', height=100)
        if st.button("Run tolerance-aware comparison", width="stretch"):
            try: smart_json(store.run_benchmark(options[choice], json.loads(candidate)), title="Benchmark result", key="ng_benchmark_run")
            except Exception as exc: st.error(str(exc))


def _render_plugins(store: NextGenStore) -> None:
    upload = st.file_uploader("Plugin ZIP for static inspection", type=["zip"], key="ng_plugin_upload")
    inspection = None
    if upload:
        try:
            inspection = store.inspect_plugin(upload.getvalue(), upload.name)
            smart_json({k: v for k, v in inspection.items() if k != "entries"}, title="Plugin safety inspection", key="ng_plugin_inspection")
            if inspection["entries"]:
                smart_dataframe(pd.DataFrame(inspection["entries"]).head(1000), height=340, key="ng_plugin_entries")
            c1, c2 = st.columns(2)
            if c1.button("Register inspection record", width="stretch"):
                st.success(store.register_plugin_inspection(inspection)["plugin_id"])
            trust = c2.checkbox("I manually trust this unverified signer", value=False, help="BioIntel does not claim a cryptographic signature unless an external verifier has confirmed it.")
            if st.button("Install into disabled isolated registry", disabled=bool(inspection["findings"]) or not trust, width="stretch"):
                record = store.install_plugin_archive(upload.getvalue(), inspection, trust_unverified=trust)
                st.success(f"Installed as disabled: {record['plugin_id']}")
        except Exception as exc:
            st.error(str(exc))
    plugins = store.list_plugins()
    if plugins:
        smart_dataframe(_records_frame(plugins), height=340, key="ng_plugins")
        options = {f"{x['name']} {x['version']} · {x['status']}": x["plugin_id"] for x in plugins}
        label = st.selectbox("Plugin lifecycle", list(options), key="ng_plugin_lifecycle")
        status = st.selectbox("New status", ["installed_disabled", "enabled", "disabled", "removed"], key="ng_plugin_status")
        if st.button("Apply plugin status", width="stretch"):
            try:
                store.set_plugin_status(options[label], status); st.success("Plugin status updated"); st.rerun()
            except Exception as exc:
                st.error(str(exc))
    else:
        st.info("No plugins inspected.")


def render_platform_module(module_key: str) -> None:
    module = MODULE_BY_KEY[module_key]
    compact_module_header(
        title=module.title,
        summary=module.summary,
        icon=module.icon,
        category=module.category,
        tags=("Persistent state", "Safety limits", "Auditable operations"),
        boundary=module.boundary,
    )
    store = NextGenStore(PROJECT_ROOT)
    has_depth = profile_for(module.key) is not None
    platform_tabs = ["1 · Workspace", "2 · Records & status", "3 · Guide"]
    if has_depth:
        platform_tabs.append("4 · Depth & security")
    tabs = st.tabs(platform_tabs)
    tab_workspace, tab_records, tab_guide = tabs[:3]
    tab_depth = tabs[3] if has_depth else None
    with tab_workspace:
        renderers = {
            "universal_file_inspector": lambda: _render_file_inspector(module),
            "cross_module_workspace": lambda: _render_project_workspace(store),
            "workflow_builder_v2": lambda: _render_workflow(store),
            "background_job_engine": lambda: _render_jobs(store),
            "unified_report_builder": _render_report_builder,
            "reference_lifecycle_v2": lambda: _render_references(store),
            "provenance_ledger_v2": _render_provenance,
            "evidence_citation_engine": lambda: _render_evidence(store),
            "model_registry_v2": lambda: _render_model_registry(store),
            "instrument_integration_v2": lambda: _render_instruments(store),
            "collaboration_review_v2": lambda: _render_reviews(store),
            "offline_scientific_copilot_v2": _render_copilot,
            "data_lakehouse_v2": lambda: _render_lakehouse(store),
            "benchmark_validation_v2": lambda: _render_benchmarks(store),
            "plugin_marketplace_v2": lambda: _render_plugins(store),
        }
        try:
            renderers[module.key]()
        except Exception as exc:
            st.error(f"Workspace failed safely: {exc}")
    with tab_records:
        section_title("Operational status", "📈")
        state = state_root(PROJECT_ROOT)
        files = [path for path in state.rglob("*") if path.is_file()]
        metric_cards([
            ("State files", len(files), "Persistent local records"),
            ("State size", f"{sum(path.stat().st_size for path in files) / 1024 / 1024:.2f} MB", "Workspace storage"),
            ("Database", "Ready", "WAL and indexes enabled"),
            ("Runtime", runtime_environment()["python"], "Python environment"),
        ])
        smart_json(
            {"module": asdict(module), "state_root": str(state), "environment": runtime_environment()},
            title="Operational manifest",
            key=f"ng_{module.key}_status",
        )
    with tab_guide:
        section_title("Purpose and safe operating guide", "📘")
        st.markdown(f"**Purpose:** {module.purpose}")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Accepted inputs**")
            for item in module.accepted_inputs:
                st.markdown(f"- {item}")
        with c2:
            st.markdown("**Generated outputs**")
            for item in module.outputs:
                st.markdown(f"- {item}")
        st.markdown("**Recommended workflow**")
        for index, step in enumerate(module.workflow, start=1):
            st.markdown(f"{index}. {step}")
        with st.expander("Operating boundary", expanded=False):
            st.warning(module.boundary, icon="⚠️")
    if tab_depth is not None:
        with tab_depth:
            render_depth_upgrade_panel(
                module.key,
                None,
                key_prefix=f"ng_platform_depth_{module.key}",
                expanded=True,
            )

def render_nextgen_module(module_key: str) -> None:
    module = MODULE_BY_KEY[module_key]
    if module.kind == "scientific":
        render_scientific_module(module_key)
    else:
        render_platform_module(module_key)
