from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from .core import (
    CONTROL_PRESETS,
    MODULE_SPECS,
    SIZE_PRESETS,
    SYNTHETIC_BANNER_TEXT,
    SYNTHETIC_BANNER_TITLE,
    SYNTHETIC_WATERMARK,
    SyntheticGeneratedDataset,
    SyntheticGenerationConfig,
    SyntheticSafetyError,
)
from .service import PROJECT_TYPES, SyntheticWorkspaceService

_STATE_PREFIX = "step219_synthetic_"


def _key(name: str) -> str:
    return f"{_STATE_PREFIX}{name}"


@st.cache_resource(show_spinner=False)
def _service(project_root: str) -> SyntheticWorkspaceService:
    return SyntheticWorkspaceService(project_root)


@st.cache_resource(show_spinner=False)
def _executor() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=1, thread_name_prefix="biointel-synthetic")


def _background_generate(project_root: str, project_id: str, config: SyntheticGenerationConfig):
    return SyntheticWorkspaceService(project_root).generate_dataset(
        project_id,
        config,
        actor="streamlit-demo-user",
    )


def _current_project(service: SyntheticWorkspaceService) -> dict[str, Any] | None:
    project_id = st.session_state.get(_key("project_id"))
    return service.registry.get_project(project_id) if project_id else None


def _reset_session_result() -> None:
    for name in ("dataset", "saved", "recommendation", "generation_error", "comparison"):
        st.session_state.pop(_key(name), None)


@st.fragment(run_every="2s")
def _render_generation_status(project_root: str, project_id: str) -> None:
    future: Future[Any] | None = st.session_state.get(_key("future"))
    if future is None:
        return
    service = _service(project_root)
    if future.done():
        try:
            dataset, saved = future.result()
            st.session_state[_key("dataset")] = dataset
            st.session_state[_key("saved")] = saved
            st.session_state.pop(_key("generation_error"), None)
        except Exception as exc:  # surfaced in the controlled demo workspace
            st.session_state[_key("generation_error")] = str(exc)
        finally:
            st.session_state.pop(_key("future"), None)
        st.rerun()

    jobs = service.registry.list_generation_jobs(project_id, limit=1)
    job = jobs[0] if jobs else None
    status = str(job.get("status", "starting")) if job else "starting"
    st.info(f"Synthetic generation status: {status}", icon=":material/progress_activity:")
    if job and status in {"queued", "running", "starting"}:
        if st.button(
            "Cancel generation",
            key=_key("cancel_generation"),
            icon=":material/cancel:",
            width="stretch",
        ):
            service.registry.cancel_generation_job(str(job["job_id"]), actor="streamlit-demo-user")
            future.cancel()
            st.warning("Cancellation requested. The generator will stop at the next chunk boundary.")


def _module_for_project(project: dict[str, Any]) -> str:
    if project["project_type"] == "Complete Bioinformatics Research Workflow Demo":
        return str(st.session_state.get(_key("workflow_module"), "differential_expression"))
    return str(project["module_id"])


def _generation_form(project: dict[str, Any]) -> SyntheticGenerationConfig | None:
    fixed_module = project["project_type"] != "Complete Bioinformatics Research Workflow Demo"
    module_ids = list(MODULE_SPECS)
    default_module = str(project["module_id"])
    if default_module not in module_ids:
        default_module = module_ids[0]

    with st.form(_key("generation_form"), border=False):
        st.subheader("Dataset Configuration")
        col1, col2 = st.columns(2)
        module_id = col1.selectbox(
            "Analysis module",
            module_ids,
            index=module_ids.index(default_module),
            format_func=lambda value: MODULE_SPECS[value]["title"],
            disabled=fixed_module,
            key=_key("workflow_module"),
        )
        scenarios = list(MODULE_SPECS[module_id]["scenarios"])
        scenario_default = str(project.get("scenario", scenarios[0]))
        scenario_index = scenarios.index(scenario_default) if scenario_default in scenarios else 0
        scenario = col2.selectbox(
            "Scenario",
            scenarios,
            index=scenario_index,
            format_func=lambda value: value.replace("_", " ").title(),
            key=_key("scenario"),
        )

        col3, col4, col5 = st.columns([1.4, 1, 1])
        preset_name = col3.selectbox(
            "Control preset",
            list(CONTROL_PRESETS),
            index=list(CONTROL_PRESETS).index("Typical Research Dataset"),
            key=_key("preset"),
        )
        size_preset = col4.segmented_control(
            "Dataset size",
            list(SIZE_PRESETS),
            default="small",
            format_func=str.title,
            key=_key("size"),
        ) or "small"
        seed = col5.number_input(
            "Random seed",
            min_value=0,
            max_value=2_147_483_647,
            value=int(project.get("seed", 42)),
            step=1,
            key=_key("seed"),
        )

        defaults = SIZE_PRESETS[size_preset]
        dim1, dim2, dim3 = st.columns(3)
        sample_count = dim1.number_input(
            "Samples",
            min_value=4,
            max_value=2000,
            value=int(defaults["samples"]),
            step=1,
            key=_key(f"samples_{size_preset}"),
        )
        feature_count = dim2.number_input(
            "Features",
            min_value=1,
            max_value=10000,
            value=int(defaults["features"]),
            step=1,
            key=_key(f"features_{size_preset}"),
        )
        group_count = dim3.number_input(
            "Groups",
            min_value=2,
            max_value=20,
            value=2,
            step=1,
            key=_key("groups"),
        )

        preset = CONTROL_PRESETS[preset_name]
        with st.expander("Signal and quality controls", expanded=False, icon=":material/tune:"):
            a1, a2 = st.columns(2)
            effect_size = a1.slider("Effect size", 0.0, 20.0, float(preset.get("effect_size", 1.0)), 0.05)
            noise_level = a2.slider("Noise level", 0.0, 10.0, float(preset.get("noise_level", 0.25)), 0.05)
            missing_data_rate = a1.slider("Missing data rate", 0.0, 1.0, float(preset.get("missing_data_rate", 0.02)), 0.01)
            batch_effect_strength = a2.slider("Batch effect strength", 0.0, 10.0, float(preset.get("batch_effect_strength", 0.2)), 0.05)
            duplicate_rate = a1.slider("Duplicate rate", 0.0, 1.0, float(preset.get("duplicate_rate", 0.0)), 0.01)
            outlier_rate = a2.slider("Outlier rate", 0.0, 1.0, float(preset.get("outlier_rate", 0.02)), 0.01)
            class_imbalance = a1.slider("Class imbalance", 0.0, 1.0, float(preset.get("class_imbalance", 0.5)), 0.01)
            confounding_strength = a2.slider("Confounding strength", 0.0, 1.0, float(preset.get("confounding_strength", 0.0)), 0.01)
            signal_sparsity = a1.slider("Signal sparsity", 0.0, 1.0, float(preset.get("signal_sparsity", 0.1)), 0.01)
            measurement_error = a2.slider("Measurement error", 0.0, 10.0, float(preset.get("measurement_error", 0.1)), 0.05)
            positive_control_strength = a1.slider("Positive control strength", 0.0, 20.0, float(preset.get("positive_control_strength", 1.5)), 0.05)
            negative_control_strength = a2.slider("Negative control strength", 0.0, 20.0, float(preset.get("negative_control_strength", 0.0)), 0.05)
            contradictory_evidence_level = a1.slider("Contradictory evidence", 0.0, 1.0, float(preset.get("contradictory_evidence_level", 0.0)), 0.01)
            validation_success_probability = a2.slider("Validation success probability", 0.0, 1.0, float(preset.get("validation_success_probability", 0.8)), 0.01)

        large_confirmed = True
        if size_preset == "large":
            large_confirmed = st.checkbox(
                "I understand the large preset may use substantial memory and time.",
                value=False,
                key=_key("large_confirmed"),
            )
        submitted = st.form_submit_button(
            "Generate synthetic dataset",
            icon=":material/science:",
            type="primary",
            width="stretch",
        )

    if not submitted:
        return None
    if size_preset == "large" and not large_confirmed:
        st.error("Confirm the large-generation warning before starting.")
        return None
    return SyntheticGenerationConfig.from_preset(
        module_id=module_id,
        scenario=scenario,
        size_preset=size_preset,
        preset_name=preset_name,
        seed=int(seed),
        sample_count=int(sample_count),
        feature_count=int(feature_count),
        group_count=int(group_count),
        effect_size=effect_size,
        noise_level=noise_level,
        missing_data_rate=missing_data_rate,
        duplicate_rate=duplicate_rate,
        outlier_rate=outlier_rate,
        batch_effect_strength=batch_effect_strength,
        class_imbalance=class_imbalance,
        confounding_strength=confounding_strength,
        signal_sparsity=signal_sparsity,
        measurement_error=measurement_error,
        positive_control_strength=positive_control_strength,
        negative_control_strength=negative_control_strength,
        contradictory_evidence_level=contradictory_evidence_level,
        validation_success_probability=validation_success_probability,
    )


def _render_dataset(dataset: SyntheticGeneratedDataset, saved: dict[str, Any]) -> None:
    st.subheader("Generated Dataset")
    st.badge("Synthetic Demo Data", icon=":material/science:", color="red")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Origin", "Synthetic")
    c2.metric("Scenario", dataset.config.scenario.replace("_", " ").title())
    c3.metric("Seed", str(dataset.config.seed))
    c4.metric("Tables", str(len(dataset.tables)))

    table_name = st.selectbox("Table preview", list(dataset.tables), key=_key("table_preview"))
    frame = pd.DataFrame(dataset.tables[table_name])
    st.dataframe(frame.head(200), width="stretch", height=370, hide_index=True)
    if len(frame) > 200:
        st.caption(f"Showing 200 of {len(frame):,} rows.")

    package_path = Path(str(saved["package_path"]))
    if package_path.is_file():
        st.download_button(
            "Download synthetic dataset package",
            data=package_path.read_bytes(),
            file_name=package_path.name,
            mime="application/zip",
            icon=":material/download:",
            width="stretch",
            key=_key("download_package"),
        )
    st.code(f"SHA-256  {saved['package_sha256']}", language="text")


def _render_analysis(service: SyntheticWorkspaceService, project: dict[str, Any], dataset: SyntheticGeneratedDataset, saved: dict[str, Any]) -> None:
    st.subheader("Demo Analysis")
    if st.button(
        "Run analysis and generate recommendations",
        key=_key("run_recommendation"),
        icon=":material/analytics:",
        type="primary",
        width="stretch",
    ):
        with st.spinner("Running the production recommendation framework on synthetic inputs..."):
            recommendation = service.run_production_recommendation(
                str(project["project_id"]),
                str(saved["dataset_id"]),
                dataset,
                actor="streamlit-demo-user",
            )
        st.session_state[_key("recommendation")] = recommendation
        st.session_state[_key("comparison")] = service.compare_expected_observed(dataset, recommendation)

    recommendation = st.session_state.get(_key("recommendation"))
    if recommendation:
        st.badge("Synthetic Recommendation", icon=":material/warning:", color="orange")
        a1, a2, a3, a4 = st.columns(4)
        a1.metric("Priority", str(recommendation.get("priority", "Not calculated")))
        confidence = recommendation.get("confidence_score")
        a2.metric("Confidence", "Not calculated" if confidence is None else f"{float(confidence):.1f}%")
        a3.metric("Evidence", str(recommendation.get("evidence_grade", "Unassigned")))
        a4.metric("Validation", "Demo only")
        st.warning(str(recommendation.get("scientific_summary", SYNTHETIC_WATERMARK)))
        evidence = list(recommendation.get("evidence", [])) + list(recommendation.get("contradictory_evidence", []))
        if evidence:
            st.dataframe(pd.DataFrame(evidence), width="stretch", height=300, hide_index=True)


def _render_expected_observed(dataset: SyntheticGeneratedDataset) -> None:
    st.subheader("Expected vs Observed")
    comparison = st.session_state.get(_key("comparison"))
    if comparison:
        st.dataframe(pd.DataFrame(comparison), width="stretch", height=430, hide_index=True)
    else:
        st.info("Run the demo analysis to populate observed findings.")

    developer_view = st.toggle(
        "Developer/testing view",
        value=False,
        key=_key("developer_view"),
        help="Controls access to the hidden synthetic ground-truth manifest.",
    )
    if developer_view:
        show_truth = st.toggle(
            "Show hidden ground truth",
            value=False,
            key=_key("show_truth"),
        )
        if show_truth:
            st.dataframe(
                pd.DataFrame([record.to_dict() for record in dataset.ground_truth]),
                width="stretch",
                height=430,
                hide_index=True,
            )
        st.markdown("**Expected QC findings**")
        st.dataframe(pd.DataFrame(dataset.expected_qc_findings), width="stretch", hide_index=True)
        st.markdown("**Expected recommendations**")
        st.dataframe(pd.DataFrame(dataset.expected_recommendations), width="stretch", hide_index=True)


def _render_safeguards(service: SyntheticWorkspaceService, project: dict[str, Any]) -> None:
    st.subheader("Origin Safeguards")
    destination = st.selectbox(
        "Workflow destination",
        ("Synthetic demo project", "Real project", "Mixed-Origin Evaluation"),
        key=_key("copy_destination"),
    )
    confirmed = st.checkbox(
        "Confirm synthetic provenance will remain attached",
        value=False,
        key=_key("copy_confirmed"),
    )
    if st.button(
        "Check workflow copy",
        icon=":material/content_copy:",
        width="stretch",
        key=_key("check_copy"),
    ):
        destination_origin = "synthetic" if destination == "Synthetic demo project" else "real"
        try:
            label = service.confirm_workflow_copy(
                project,
                {"data_origin": destination_origin, "is_synthetic": destination_origin == "synthetic"},
                confirmed=confirmed and destination == "Mixed-Origin Evaluation",
            )
            st.success(f"Destination classification: {label}")
        except SyntheticSafetyError as exc:
            st.error(str(exc))

    with st.expander("Reset demo project", expanded=False, icon=":material/delete_sweep:"):
        reset_confirmed = st.checkbox(
            "Delete only this synthetic project's generated datasets, runs and recommendations.",
            value=False,
            key=_key("reset_confirmed"),
        )
        if st.button(
            "Reset synthetic project",
            icon=":material/delete_forever:",
            disabled=not reset_confirmed,
            width="stretch",
            key=_key("reset_project"),
        ):
            result = service.registry.reset_project(str(project["project_id"]), actor="streamlit-demo-user")
            _reset_session_result()
            st.success(f"Synthetic project reset. Reset count: {result['reset_count']}")
            st.rerun()


def render_synthetic_demo_workspace(project_root: str | Path) -> None:
    root = str(Path(project_root).resolve())
    service = _service(root)
    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"] { border-top: 6px solid #b42318; }
        section[data-testid="stSidebar"],
        [data-testid="stSidebarCollapseButton"],
        [data-testid="stSidebarCollapsedControl"] {
            display: none !important;
        }
        section[data-testid="stMain"] {
            left: 0 !important;
            margin-left: 0 !important;
            width: 100vw !important;
            max-width: 100vw !important;
        }
        [data-testid="stMainBlockContainer"] {
            width: 100% !important;
            max-width: 100% !important;
            padding-left: 1.25rem !important;
            padding-right: 1.25rem !important;
        }
        h1 {
            font-size: 2.25rem !important;
            line-height: 1.15 !important;
            word-break: normal !important;
            overflow-wrap: break-word !important;
        }
        .synthetic-origin-strip {
            border: 1px solid #d92d20; border-left: 6px solid #b42318;
            background: #fff4ed; color: #7a271a; padding: 12px 14px;
            margin: 0 0 14px 0; font-weight: 700;
        }
        @media (max-width: 700px) {
            section[data-testid="stSidebar"] {
                display: none !important;
                width: 0 !important;
                min-width: 0 !important;
            }
            section[data-testid="stMain"] {
                left: 0 !important;
                margin-left: 0 !important;
                width: 100vw !important;
                max-width: 100vw !important;
            }
            [data-testid="stMainBlockContainer"] {
                width: 100% !important;
                max-width: 100% !important;
                padding: 0.75rem 1rem 3rem !important;
            }
            [data-testid="stHorizontalBlock"] {
                flex-wrap: wrap !important;
            }
            [data-testid="stColumn"] {
                flex: 1 1 100% !important;
                min-width: min(100%, 240px) !important;
                width: 100% !important;
            }
            h1 {
                font-size: 2rem !important;
                line-height: 1.15 !important;
                word-break: normal !important;
                overflow-wrap: break-word !important;
            }
            button, label, p, [role="alert"] {
                word-break: normal !important;
                overflow-wrap: break-word !important;
            }
            .synthetic-origin-strip {
                font-size: 0.88rem;
                line-height: 1.35;
            }
        }
        </style>
        <div class="synthetic-origin-strip">SYNTHETIC ORIGIN IS LOCKED FOR THIS WORKSPACE AND ALL DERIVED OUTPUTS</div>
        """,
        unsafe_allow_html=True,
    )
    st.title("Synthetic Demo Data Workspace")
    st.error(f"**{SYNTHETIC_BANNER_TITLE}**\n\n{SYNTHETIC_BANNER_TEXT}", icon=":material/warning:")

    projects = service.registry.list_projects(limit=100)
    if projects:
        st.badge("Synthetic Project List", icon=":material/science:", color="red")
        project_ids = [str(item["project_id"]) for item in projects]
        current = st.session_state.get(_key("project_id"))
        index = project_ids.index(current) if current in project_ids else 0
        selected = st.selectbox(
            "Demo project",
            project_ids,
            index=index,
            format_func=lambda value: next(
                f"{item['title']} | {value}" for item in projects if item["project_id"] == value
            ),
            key=_key("project_selector"),
        )
        if selected != current:
            st.session_state[_key("project_id")] = selected
            _reset_session_result()

    with st.expander("Create Demo Project", expanded=not bool(projects), icon=":material/create_new_folder:"):
        with st.form(_key("create_project_form"), border=False):
            project_type = st.selectbox("Project type", PROJECT_TYPES, key=_key("project_type"))
            module_id = next(
                (key for key, value in MODULE_SPECS.items() if value["title"] == project_type),
                "differential_expression",
            )
            project_scenario = st.selectbox(
                "Starting scenario",
                list(MODULE_SPECS[module_id]["scenarios"]),
                format_func=lambda value: value.replace("_", " ").title(),
                key=_key("project_scenario"),
            )
            project_seed = st.number_input("Project seed", 0, 2_147_483_647, 42, 1, key=_key("project_seed"))
            create = st.form_submit_button(
                "Create Demo Project",
                icon=":material/add:",
                type="primary",
                width="stretch",
            )
        if create:
            created = service.create_demo_project(
                project_type,
                project_scenario,
                int(project_seed),
                actor="streamlit-demo-user",
            )
            st.session_state[_key("project_id")] = created["project_id"]
            _reset_session_result()
            st.rerun()

    project = _current_project(service)
    if project is None:
        st.info("Create a synthetic demo project to begin.")
        return

    st.caption(
        f"{project['project_id']} | {project['project_type']} | Origin: Synthetic Demo Data"
    )
    config = _generation_form(project)
    if config is not None:
        if st.session_state.get(_key("future")) is not None:
            st.warning("A synthetic generation job is already active.")
        else:
            _reset_session_result()
            st.session_state[_key("future")] = _executor().submit(
                _background_generate,
                root,
                str(project["project_id"]),
                config,
            )
            st.rerun()

    _render_generation_status(root, str(project["project_id"]))
    generation_error = st.session_state.get(_key("generation_error"))
    if generation_error:
        st.error(generation_error)

    dataset: SyntheticGeneratedDataset | None = st.session_state.get(_key("dataset"))
    saved: dict[str, Any] | None = st.session_state.get(_key("saved"))
    if dataset is None or saved is None:
        existing = service.registry.list_datasets(str(project["project_id"]))
        if existing:
            latest = existing[0]
            st.info(
                f"This project already contains {len(existing)} generated package(s). Latest dataset: {latest['dataset_id']}."
            )
            package = Path(str(latest["package_path"]))
            if package.is_file():
                st.download_button(
                    "Download latest stored package",
                    package.read_bytes(),
                    package.name,
                    "application/zip",
                    icon=":material/download:",
                    width="stretch",
                    key=_key("download_existing"),
                )
        _render_safeguards(service, project)
        return

    view = st.segmented_control(
        "Workspace view",
        ("Dataset", "Analysis", "Expected vs Observed", "Safeguards"),
        default="Dataset",
        key=_key("view"),
        width="stretch",
    ) or "Dataset"
    if view == "Dataset":
        _render_dataset(dataset, saved)
    elif view == "Analysis":
        _render_analysis(service, project, dataset, saved)
    elif view == "Expected vs Observed":
        _render_expected_observed(dataset)
    else:
        _render_safeguards(service, project)

    st.warning(SYNTHETIC_WATERMARK)


__all__ = ["render_synthetic_demo_workspace"]