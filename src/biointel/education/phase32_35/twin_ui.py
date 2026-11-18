from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from ..paths import education_paths
from .base import ResearchPlatformError
from .twin import BUILTIN_MODELS, DigitalTwinLab


@st.cache_resource
def _digital_twin_lab(root_text: str) -> DigitalTwinLab:
    root = Path(root_text)
    database, media = education_paths(root)
    return DigitalTwinLab(database, media)


def render_digital_twin_lab(root: str | Path) -> None:
    service = _digital_twin_lab(str(Path(root).resolve()))
    st.title("Biomedical Digital Twin Learning Lab")
    st.warning(
        "Research and education simulation only—not a clinically validated human Digital Twin, "
        "medical advice, prescription, or guaranteed outcome."
    )
    with st.form("phase33_project"):
        title = st.text_input("Project title", value="Synthetic glucose learning twin")
        purpose = st.text_area(
            "Research or education purpose",
            value="Explore how model assumptions alter a synthetic glucose trajectory.",
        )
        owner = st.text_input("Owner ID", value="local-researcher")
        create = st.form_submit_button("Create synthetic-first project")
    if create:
        try:
            project = service.create_project(
                "local-institution",
                owner,
                "local-institution",
                title=title,
                purpose=purpose,
            )
            st.session_state["phase33_project_id"] = project["project_id"]
            st.success(f"Project created: {project['project_id']}")
        except ResearchPlatformError as exc:
            st.error(str(exc))

    project_id = st.text_input(
        "Project ID",
        value=st.session_state.get("phase33_project_id", ""),
    )
    model_key = st.selectbox(
        "Versioned learning model",
        sorted(BUILTIN_MODELS),
        format_func=lambda key: BUILTIN_MODELS[key]["name"],
    )
    intervention_value = st.number_input(
        "Synthetic intervention multiplier at time 4",
        min_value=0.1,
        max_value=3.0,
        value=0.8,
        step=0.1,
    )
    if st.button("Run synthetic scenario", width="stretch", disabled=not bool(project_id)):
        try:
            model = service.register_model(project_id, owner, model_key=model_key)
            target = next(iter(model["definition"]["parameters"]))
            scenario = service.create_scenario(
                project_id,
                model["model_id"],
                owner,
                name="Interactive synthetic scenario",
                interventions=[
                    {
                        "time": 4.0,
                        "target": target,
                        "mode": "multiply",
                        "value": intervention_value,
                    }
                ],
            )
            result = service.run_scenario(scenario["scenario_id"], owner)
            st.session_state["phase33_result"] = {
                "simulation_id": result.simulation_id,
                "trajectory": result.trajectory,
                "uncertainty": result.uncertainty,
                "sensitivity": result.sensitivity,
                "warnings": result.warnings,
            }
        except ResearchPlatformError as exc:
            st.error(str(exc))

    result = st.session_state.get("phase33_result")
    if result:
        trajectory = pd.DataFrame(result["trajectory"]).set_index("time")
        st.subheader("Computed temporal trajectory")
        st.line_chart(trajectory, width="stretch")
        st.subheader("Parameter sensitivity")
        st.dataframe(result["sensitivity"], width="stretch", hide_index=True)
        st.caption("Uncertainty bands are model-assumption ranges, not clinical confidence intervals.")
        st.download_button(
            "Export simulation result bundle",
            data=service.export_result_bundle(result["simulation_id"]),
            file_name="biointel-digital-twin-result.zip",
            mime="application/zip",
            width="stretch",
        )
        with st.expander("Safety boundary and warnings"):
            st.code("\n".join(result["warnings"]), language=None)
            st.json(json.loads(json.dumps(BUILTIN_MODELS[model_key])))
