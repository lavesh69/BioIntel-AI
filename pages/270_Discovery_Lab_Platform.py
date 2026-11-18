from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.discovery_platform.analysis import analysis_catalog
from biointel.discovery_platform.constants import (
    CANDIDATE_TYPES,
    EVIDENCE_TYPES,
    MODULE_LABELS,
    PROJECT_STAGES,
)
from biointel.discovery_platform.models import ProjectCreate
from biointel.discovery_platform.reports import EXPORT_FORMATS, REPORT_SECTIONS
from biointel.discovery_platform.service import DiscoveryPlatformService
from biointel.synthetic import (
    MODULE_SPECS,
    SYNTHETIC_WATERMARK,
    SyntheticDatasetGenerator,
    SyntheticGenerationConfig,
)
from biointel.ui.theme import apply_theme

st.set_page_config(
    page_title="Discovery lab platform | BioIntel AI",
    page_icon=":material/biotech:",
    layout="wide",
)
apply_theme()


@st.cache_resource(show_spinner=False)
def platform_service(root_text: str) -> DiscoveryPlatformService:
    return DiscoveryPlatformService(
        project_root=Path(root_text), actor="streamlit_local_user", role="Administrator"
    )


def records_frame(records: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in records:
        row = {}
        for key, value in record.items():
            row[key] = (
                json.dumps(value, sort_keys=True, default=str)
                if isinstance(value, (dict, list, tuple))
                else value
            )
        rows.append(row)
    return pd.DataFrame(rows)


def read_uploaded_table(uploaded: Any) -> pd.DataFrame:
    suffix = Path(uploaded.name).suffix.lower()
    payload = uploaded.getvalue()
    if suffix == ".csv":
        return pd.read_csv(io.BytesIO(payload))
    if suffix in {".tsv", ".txt"}:
        return pd.read_csv(io.BytesIO(payload), sep="\t")
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(io.BytesIO(payload))
    if suffix in {".json", ".jsonl"}:
        return pd.read_json(io.BytesIO(payload), lines=suffix == ".jsonl")
    raise ValueError("Supported table formats: CSV, TSV, XLSX, XLS, JSON, JSONL")


def show_error(exc: Exception) -> None:
    st.error(str(exc), icon=":material/error:")


def project_form(service: DiscoveryPlatformService) -> None:
    with st.expander("New research project", icon=":material/add:"):
        with st.form("step220_create_project"):
            first, second = st.columns(2)
            with first:
                title = st.text_input("Project title")
                question = st.text_area("Research question", height=100)
                objective = st.text_area("Scientific objective", height=100)
                owner = st.text_input("Owner", value="local_user")
            with second:
                synthetic = st.toggle("Synthetic project")
                disease = st.text_input("Disease context")
                organism = st.text_input("Organism")
                assays = st.multiselect(
                    "Assay types",
                    ["RNA-seq", "WGS", "WES", "Single-cell", "Proteomics", "Metabolomics", "Microbiome", "Imaging"],
                    accept_new_options=True,
                )
            submitted = st.form_submit_button(
                "Create project", type="primary", icon=":material/add:"
            )
        if submitted:
            try:
                created = service.create_project(
                    ProjectCreate(
                        title=title,
                        research_question=question,
                        scientific_objective=objective,
                        disease_context=disease,
                        organism=organism,
                        assay_types=tuple(assays),
                        owner=owner,
                        data_origin=(
                            "synthetic_demo_output"
                            if synthetic
                            else "user_entered_interpretation"
                        ),
                        is_synthetic=synthetic,
                    )
                )
                st.session_state["step220_project_id"] = created["project_id"]
                st.toast("Project created", icon=":material/check_circle:")
                st.rerun()
            except Exception as exc:
                show_error(exc)


def render_overview(service: DiscoveryPlatformService, project: dict[str, Any]) -> None:
    summary = service.dashboard_summary(project["project_id"])
    counts = summary["counts"]
    with st.container(horizontal=True):
        st.metric("Datasets", counts["datasets"], border=True)
        st.metric("Completed runs", counts["runs"], border=True)
        st.metric("Candidates", counts["candidates"], border=True)
        st.metric("Evidence records", counts["evidence"], border=True)
        st.metric("Reports", counts["reports"], border=True)

    left, right = st.columns([1.15, 1])
    with left:
        st.subheader("Lifecycle")
        stage_index = PROJECT_STAGES.index(project["current_stage"])
        st.progress((stage_index + 1) / len(PROJECT_STAGES), text=project["current_stage"])
        gate = project["stage_gate"]
        gate_rows = [
            {"criterion": key, "complete": bool(value)}
            for key, value in gate.get("checks", {}).items()
        ]
        if gate_rows:
            st.dataframe(records_frame(gate_rows), hide_index=True, width="stretch")
        with st.container(horizontal=True):
            if st.button(
                "Approve current gate",
                icon=":material/fact_check:",
                disabled=not gate.get("complete"),
            ):
                try:
                    service.set_stage_gate(
                        project["project_id"],
                        project["current_stage"],
                        status="Approved",
                        note="Approved from Discovery Lab Platform",
                    )
                    st.rerun()
                except Exception as exc:
                    show_error(exc)
            if st.button(
                "Advance stage",
                icon=":material/arrow_forward:",
                type="primary",
                disabled=not gate.get("complete"),
            ):
                try:
                    service.advance_stage(project["project_id"])
                    st.rerun()
                except Exception as exc:
                    show_error(exc)
    with right:
        st.subheader("Project record")
        st.dataframe(
            records_frame(
                [
                    {"field": "Project ID", "value": project["project_id"]},
                    {"field": "Owner", "value": project["owner"]},
                    {"field": "Organism", "value": project["organism"] or "Not set"},
                    {"field": "Disease context", "value": project["disease_context"] or "Not set"},
                    {"field": "Data origin", "value": project["data_origin"]},
                    {"field": "Updated", "value": project["updated_at_utc"]},
                ]
            ),
            hide_index=True,
            width="stretch",
        )

    st.subheader("Recent activity")
    activity = service.activity_feed(project["project_id"], limit=100)
    if activity:
        st.dataframe(
            records_frame(activity),
            hide_index=True,
            width="stretch",
            column_config={
                "occurred_at_utc": st.column_config.DatetimeColumn("Occurred", format="YYYY-MM-DD HH:mm"),
                "event_type": st.column_config.TextColumn("Event", pinned=True),
            },
        )
    else:
        st.caption("No project activity recorded")


def render_data(service: DiscoveryPlatformService, project: dict[str, Any]) -> None:
    project_id = project["project_id"]
    datasets = service.list_datasets(project_id, limit=1000)
    st.subheader("Dataset registry")
    if datasets:
        st.dataframe(records_frame(datasets), hide_index=True, width="stretch")

    with st.expander("Register dataset", icon=":material/database:"):
        with st.form("step220_register_dataset"):
            left, right = st.columns(2)
            with left:
                name = st.text_input("Dataset name")
                description = st.text_area("Description")
                assay = st.text_input("Assay type")
                omics = st.text_input("Omics type")
            with right:
                sample_count = st.number_input("Sample count", min_value=0, step=1)
                feature_count = st.number_input("Feature count", min_value=0, step=1)
                reference = st.text_input("Reference build")
                annotation = st.text_input("Annotation release")
            submit = st.form_submit_button(
                "Register dataset", type="primary", icon=":material/save:"
            )
        if submit:
            try:
                service.register_dataset(
                    project_id,
                    name=name,
                    description=description,
                    assay_type=assay,
                    omics_type=omics,
                    organism=project["organism"],
                    sample_count=int(sample_count),
                    feature_count=int(feature_count),
                    reference_build=reference,
                    annotation_release=annotation,
                    data_origin=(
                        "synthetic_demo_output"
                        if project["is_synthetic"]
                        else "imported_external_result"
                    ),
                    is_synthetic=bool(project["is_synthetic"]),
                )
                st.toast("Dataset registered", icon=":material/check_circle:")
                st.rerun()
            except Exception as exc:
                show_error(exc)

    if project["is_synthetic"]:
        st.subheader("Synthetic generator")
        module_id = st.selectbox(
            "Module", list(MODULE_SPECS), format_func=lambda item: MODULE_LABELS[item]
        )
        scenarios = list(MODULE_SPECS[module_id]["scenarios"])
        scenario = st.selectbox("Scenario", scenarios)
        size = st.segmented_control("Size preset", ["small", "medium", "large"], default="small")
        seed = st.number_input("Random seed", min_value=0, max_value=2_147_483_647, value=42)
        if st.button("Generate dataset", type="primary", icon=":material/science:"):
            try:
                config = SyntheticGenerationConfig(
                    module_id=module_id,
                    scenario=scenario,
                    size_preset=str(size or "small"),
                    seed=int(seed),
                )
                generated = SyntheticDatasetGenerator().generate(config)
                samples, features = config.dimensions
                dataset = service.register_dataset(
                    project_id,
                    name=f"{MODULE_LABELS[module_id]} - {scenario}",
                    description=SYNTHETIC_WATERMARK,
                    assay_type=module_id,
                    sample_count=samples,
                    feature_count=features,
                    file_formats=("in-memory synthetic tables",),
                    data_origin="synthetic_demo_output",
                    provenance={"origin": "synthetic_demo_output", "seed": int(seed)},
                    is_synthetic=True,
                )
                manifest = service.synthetic.register_generated_dataset(
                    project_id=project_id,
                    dataset_id=dataset["dataset_id"],
                    generated=generated,
                )
                analysis_result = service.synthetic.run_generated_analysis(
                    project_id=project_id,
                    dataset_id=dataset["dataset_id"],
                    generated=generated,
                )
                st.session_state["step220_synthetic_preview"] = {
                    name: table.head(20)
                    for name, table in generated.tables.items()
                    if isinstance(table, pd.DataFrame)
                }
                st.session_state["step220_synthetic_analysis"] = analysis_result
                st.success(
                    f"Registered {manifest['module_id']} / {manifest['scenario']} "
                    f"| production analysis: {analysis_result['status']}"
                )
            except Exception as exc:
                show_error(exc)
        for table_name, table in st.session_state.get("step220_synthetic_preview", {}).items():
            st.caption(table_name)
            st.dataframe(table, hide_index=True, width="stretch")

    datasets = service.list_datasets(project_id, limit=1000)
    if datasets:
        dataset_map = {item["dataset_id"]: item for item in datasets}
        selected_id = st.selectbox(
            "Selected dataset",
            list(dataset_map),
            format_func=lambda item: f"{dataset_map[item]['name']} | {item}",
        )
        metadata_file = st.file_uploader(
            "Sample metadata", type=["csv", "tsv", "txt", "xlsx", "json", "jsonl"]
        )
        if metadata_file is not None:
            try:
                metadata = read_uploaded_table(metadata_file)
                st.dataframe(metadata.head(100), hide_index=True, width="stretch")
                if st.button("Add samples", icon=":material/upload:", type="primary"):
                    result = service.add_samples(
                        selected_id, metadata.where(pd.notna(metadata), None).to_dict("records")
                    )
                    st.success(
                        f"Inserted {result['inserted_count']} samples; {result['failure_count']} failed"
                    )
            except Exception as exc:
                show_error(exc)
        samples = service.search_samples(selected_id, limit=1000)
        if samples:
            st.subheader("Sample registry")
            st.dataframe(records_frame(samples), hide_index=True, width="stretch")


def render_analysis(service: DiscoveryPlatformService, project: dict[str, Any]) -> None:
    st.subheader("Scientific analysis")
    module_id = st.selectbox(
        "Analysis module", list(MODULE_LABELS), format_func=lambda item: MODULE_LABELS[item]
    )
    catalog_item = next(item for item in analysis_catalog() if item["module_id"] == module_id)
    st.caption(catalog_item["native_method"])
    upload = st.file_uploader(
        "Analysis table", type=["csv", "tsv", "txt", "xlsx", "xls", "json", "jsonl"]
    )
    parameters_text = st.text_area("Parameters (JSON)", value="{}", height=110)
    seed = st.number_input("Random seed", min_value=0, max_value=2_147_483_647, value=42)
    frame = None
    if upload is not None:
        try:
            frame = read_uploaded_table(upload)
            st.dataframe(frame.head(100), hide_index=True, width="stretch")
        except Exception as exc:
            show_error(exc)
    datasets = service.list_datasets(project["project_id"], limit=1000)
    dataset_id = st.selectbox(
        "Linked dataset",
        [None, *[item["dataset_id"] for item in datasets]],
        format_func=lambda item: "No linked dataset" if item is None else item,
    )
    if st.button(
        "Run analysis",
        type="primary",
        icon=":material/play_arrow:",
        disabled=frame is None,
    ):
        try:
            parameters = json.loads(parameters_text or "{}")
            if not isinstance(parameters, dict):
                raise ValueError("Parameters JSON must be an object")
            run = service.analysis.run_and_persist(
                project_id=project["project_id"],
                module_id=module_id,
                frame=frame,
                parameters=parameters,
                dataset_id=dataset_id,
                is_synthetic=bool(project["is_synthetic"]),
                seed=int(seed),
            )
            st.session_state["step220_run"] = run
            st.success(f"Run completed: {run['run_id']}")
        except Exception as exc:
            show_error(exc)
    if st.session_state.get("step220_run"):
        with st.expander("Latest result", expanded=True, icon=":material/analytics:"):
            st.json(st.session_state["step220_run"])
    runs = service.store.rows(
        "runs",
        filters={"project_id": project["project_id"]},
        order_by="started_at_utc",
        limit=500,
    )
    if runs:
        st.subheader("Run history")
        st.dataframe(records_frame(runs), hide_index=True, width="stretch")


def render_discovery(service: DiscoveryPlatformService, project: dict[str, Any]) -> None:
    project_id = project["project_id"]
    st.subheader("Candidate registry")
    with st.form("step220_candidate"):
        first, second = st.columns(2)
        with first:
            identity = st.text_input("Candidate identity")
            candidate_type = st.selectbox("Candidate type", CANDIDATE_TYPES)
            source = st.text_input("Data source")
        with second:
            confidence = st.slider("Confidence", 0.0, 1.0, 0.5, 0.01)
            priority = st.number_input("Priority score", 0.0, 1.0, 0.5, 0.01)
            evidence_score = st.number_input("Evidence score", 0.0, 1.0, 0.5, 0.01)
        submit = st.form_submit_button("Add candidate", icon=":material/add:")
    if submit:
        try:
            service.create_candidate(
                project_id,
                candidate_type=candidate_type,
                identity=identity,
                data_source=source,
                scores={"priority": float(priority), "evidence": float(evidence_score)},
                confidence=float(confidence),
                origin=("synthetic_demo_output" if project["is_synthetic"] else "real_calculation"),
            )
            st.rerun()
        except Exception as exc:
            show_error(exc)

    candidates = service.list_candidates(project_id, limit=2000)
    if candidates:
        st.dataframe(records_frame(candidates), hide_index=True, width="stretch")
        with st.container(horizontal=True):
            priority_weight = st.number_input("Priority weight", 0.0, 10.0, 1.0)
            evidence_weight = st.number_input("Evidence weight", 0.0, 10.0, 1.0)
            if st.button("Rank candidates", icon=":material/sort:", type="primary"):
                try:
                    ranked = service.rank_candidates(
                        project_id,
                        {"priority": priority_weight, "evidence": evidence_weight},
                    )
                    st.session_state["step220_ranked"] = ranked
                except Exception as exc:
                    show_error(exc)
        if st.session_state.get("step220_ranked"):
            st.dataframe(
                records_frame(st.session_state["step220_ranked"]),
                hide_index=True,
                width="stretch",
            )


def render_evidence(service: DiscoveryPlatformService, project: dict[str, Any]) -> None:
    project_id = project["project_id"]
    mode = st.segmented_control(
        "Record type", ["Evidence", "Hypothesis", "Validation"], default="Evidence"
    )
    if mode == "Evidence":
        with st.form("step220_evidence"):
            source = st.text_input("Source")
            title = st.text_input("Evidence title")
            allowed_types = ["Synthetic fixture"] if project["is_synthetic"] else list(EVIDENCE_TYPES)
            evidence_type = st.selectbox("Evidence type", allowed_types)
            direction = st.selectbox("Direction", ["Supporting", "Contradictory", "Neutral"])
            strength = st.selectbox("Strength", ["Unrated", "Weak", "Moderate", "Strong"])
            submitted = st.form_submit_button("Add evidence", icon=":material/library_add:")
        if submitted:
            try:
                service.add_evidence(
                    project_id,
                    source=source,
                    title=title,
                    evidence_type=evidence_type,
                    direction=direction,
                    strength=strength,
                    origin=("synthetic_demo_output" if project["is_synthetic"] else "imported_external_result"),
                )
                st.rerun()
            except Exception as exc:
                show_error(exc)
        rows = service.list_evidence(project_id, limit=2000)
    elif mode == "Hypothesis":
        with st.form("step220_hypothesis"):
            statement = st.text_area("Hypothesis statement")
            null_hypothesis = st.text_area("Null hypothesis")
            observations = st.text_area("Supporting observations", placeholder="One observation per line")
            falsification = st.text_area("Falsification criteria", placeholder="One criterion per line")
            submitted = st.form_submit_button("Add hypothesis", icon=":material/science:")
        if submitted:
            try:
                service.create_hypothesis(
                    project_id,
                    statement=statement,
                    null_hypothesis=null_hypothesis,
                    supporting_observations=tuple(line.strip() for line in observations.splitlines() if line.strip()),
                    falsification_criteria=tuple(line.strip() for line in falsification.splitlines() if line.strip()),
                    origin=("synthetic_demo_output" if project["is_synthetic"] else "hypothesis"),
                )
                st.rerun()
            except Exception as exc:
                show_error(exc)
        rows = service.list_hypotheses(project_id, limit=2000)
    else:
        rows = service.list_experiments(project_id, limit=1000)
        validations = service.list_validations(project_id, limit=1000)
        st.caption(f"Validation results: {len(validations)}")
        if validations:
            st.dataframe(records_frame(validations), hide_index=True, width="stretch")
    if rows:
        st.dataframe(records_frame(rows), hide_index=True, width="stretch")
    contradictions = service.evidence_contradictions(project_id)
    if contradictions:
        st.warning(f"Contradiction groups: {len(contradictions)}", icon=":material/warning:")
        st.dataframe(records_frame(contradictions), hide_index=True, width="stretch")


def render_reports(service: DiscoveryPlatformService, project: dict[str, Any]) -> None:
    project_id = project["project_id"]
    st.subheader("Scientific reports")
    with st.form("step220_report"):
        title = st.text_input("Report title", value=f"{project['title']} research report")
        sections = st.multiselect("Sections", REPORT_SECTIONS, default=list(REPORT_SECTIONS))
        submitted = st.form_submit_button(
            "Create draft report", type="primary", icon=":material/description:"
        )
    if submitted:
        try:
            service.reports.create_report(project_id, title=title, selected_sections=sections)
            st.rerun()
        except Exception as exc:
            show_error(exc)
    reports = service.store.rows(
        "reports", filters={"project_id": project_id}, order_by="updated_at_utc", limit=1000
    )
    if not reports:
        st.caption("No reports")
        return
    st.dataframe(records_frame(reports), hide_index=True, width="stretch")
    report_map = {item["report_id"]: item for item in reports}
    report_id = st.selectbox(
        "Selected report", list(report_map), format_func=lambda item: report_map[item]["title"]
    )
    output_format = st.selectbox(
        "Export format", EXPORT_FORMATS, index=0
    )
    if st.button("Prepare download", icon=":material/download:", type="primary"):
        try:
            content, filename, media_type = service.reports.render(
                report_id, str(output_format or "pdf")
            )
            st.session_state["step220_report_download"] = (content, filename, media_type)
        except Exception as exc:
            show_error(exc)
    download = st.session_state.get("step220_report_download")
    if download:
        st.download_button(
            "Download report",
            data=download[0],
            file_name=download[1],
            mime=download[2],
            icon=":material/download:",
            type="primary",
        )


def render_operations(service: DiscoveryPlatformService, project: dict[str, Any]) -> None:
    st.subheader("System health")
    health = service.health.snapshot()
    cpu = health.get("cpu", {})
    memory = health.get("memory", {})
    disk = health.get("disk", {})
    audit = service.store.verify_audit_chain()
    available_gib = float(memory.get("available_bytes") or 0) / (1024 ** 3)
    with st.container(horizontal=True):
        st.metric("CPU", f"{cpu.get('utilization_percent', 0) or 0:.1f}%", border=True)
        st.metric("Memory available", f"{available_gib:.2f} GiB", border=True)
        st.metric("Database", health.get("database", {}).get("quick_check", "unknown"), border=True)
        st.metric("Audit chain", "Valid" if audit.get("valid") else "Review", border=True)
    st.json({"disk": disk, "gpu": health.get("gpu", {}), "jobs": health.get("jobs", {})})
    st.subheader("Dependency health")
    dependencies = service.health.dependency_health()
    if not dependencies:
        dependencies = service.health.dependency_health(refresh=True)
    st.dataframe(records_frame(dependencies), hide_index=True, width="stretch")
    st.subheader("Operations queue")
    queue = service.lab_operations.queue_snapshot()
    st.json(queue)
    status = service.synthetic.project_status(project["project_id"])
    if not status["boundary_valid"]:
        st.error("Synthetic boundary validation failed", icon=":material/error:")
    else:
        st.success("Data-origin boundary valid", icon=":material/verified:")


service = platform_service(str(ROOT))
st.session_state.setdefault("step220_project_id", "")
st.session_state.setdefault("step220_view", "Portfolio")

st.header("BioIntel discovery lab platform")
st.caption("Research-only lifecycle, analysis, evidence, validation, and reproducibility workspace")

projects = service.list_projects(limit=1000)
project_form(service)
if not projects:
    summary = service.dashboard_summary()
    with st.container(horizontal=True):
        st.metric("Projects", 0, border=True)
        st.metric("Datasets", summary["counts"]["datasets"], border=True)
        st.metric("Runs", summary["counts"]["runs"], border=True)
        st.metric("Candidates", summary["counts"]["candidates"], border=True)
    st.stop()

project_map = {item["project_id"]: item for item in projects}
selected_default = st.session_state.get("step220_project_id")
if selected_default not in project_map:
    selected_default = projects[0]["project_id"]
selected_index = list(project_map).index(selected_default)
with st.sidebar:
    project_id = st.selectbox(
        "Research project",
        list(project_map),
        index=selected_index,
        format_func=lambda item: project_map[item]["title"],
    )
    st.session_state["step220_project_id"] = project_id
    view = st.selectbox(
        "Workspace view",
        [
            "Portfolio",
            "Data and samples",
            "Analysis",
            "Discovery",
            "Evidence and validation",
            "Reports",
            "Operations",
        ],
        key="step220_view",
    )
    st.caption("BioIntel AI Step220")

project = service.get_project(project_id)
with st.container(horizontal=True, vertical_alignment="center"):
    st.subheader(project["title"])
    st.badge(project["current_stage"], color="blue")
    st.badge("Synthetic" if project["is_synthetic"] else "Research data", color="red" if project["is_synthetic"] else "green")

if project["is_synthetic"]:
    st.error(SYNTHETIC_WATERMARK, icon=":material/science:")
else:
    st.warning(
        "Research use only. Scientific outputs require qualified review and independent validation.",
        icon=":material/fact_check:",
    )

if view == "Portfolio":
    render_overview(service, project)
elif view == "Data and samples":
    render_data(service, project)
elif view == "Analysis":
    render_analysis(service, project)
elif view == "Discovery":
    render_discovery(service, project)
elif view == "Evidence and validation":
    render_evidence(service, project)
elif view == "Reports":
    render_reports(service, project)
else:
    render_operations(service, project)
