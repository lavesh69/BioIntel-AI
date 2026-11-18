from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json
from biointel.ui.navigation import PAGE_CATALOG
from biointel.ui.theme import hero, section_title
from biointel.ui.workflow import render_upload_preflight

from .catalog import PlanningModule, get_module
from .export import build_bundle
from .io import SUPPORTED_SUFFIXES, read_upload
from .review_store import PlanningReviewStore
from .scientific import PlanningResult, analyse, dataframe_sha256, demo_frame
from .visuals import build_figure
from .advanced_renderer import render_connected_planning_os
from .feature_density_renderer import render_peak_feature_lab
from .lifecycle_renderer import render_lifecycle_readiness_panel

PROJECT_ROOT = Path(__file__).resolve().parents[3]
STORE_PATH = PROJECT_ROOT / "UserData" / "research_planning" / "research_planning.sqlite"


def _map_columns(frame: pd.DataFrame, module: PlanningModule, key: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    missing = [column for column in module.required_columns if column not in frame.columns]
    if not missing:
        return frame
    st.warning("Map the missing required fields before analysis: " + ", ".join(missing))
    mapping: dict[str, str] = {}
    choices = ["— Not mapped —", *map(str, frame.columns)]
    columns = st.columns(min(3, len(missing)))
    for index, required in enumerate(missing):
        selected = columns[index % len(columns)].selectbox(
            required.replace("_", " ").title(), choices, key=f"{key}_map_{required}"
        )
        if selected != "— Not mapped —":
            mapping[required] = selected
    selected_sources = list(mapping.values())
    if len(selected_sources) != len(set(selected_sources)):
        st.error("One source column cannot be mapped to multiple scientific meanings.")
        return frame
    mapped = frame.copy()
    for required, source in mapping.items():
        mapped[required] = mapped[source]
    return mapped


def _record_column(frame: pd.DataFrame) -> str:
    preferred = ["participant_id", "item", "risk", "task", "analysis", "endpoint", "biomarker", "section", "scenario", "run", "cohort", "variable", "site", "sample_type", "question"]
    for column in preferred:
        if column in frame.columns:
            return column
    return str(frame.columns[0])


def _summary_cards(result: PlanningResult) -> None:
    scalar = [(str(key).replace("_", " ").title(), value, None) for key, value in result.summary.items() if isinstance(value, (int, float, str)) and "sha256" not in key]
    metric_cards(scalar[:4])


def _interpretation(result: PlanningResult) -> None:
    st.markdown("### Scientific interpretation")
    st.success(result.main_finding)
    c1, c2 = st.columns([1, 2])
    c1.metric("Confidence", result.confidence)
    with c2:
        st.markdown("**Recommended next step**")
        st.write(result.next_step)
    with st.expander("Limitations and confounders", expanded=False):
        for limitation in result.limitations:
            st.markdown(f"- {limitation}")


def _handoff_pages(module: PlanningModule) -> list[tuple[str, str]]:
    by_title = {page.title: page.path for page in PAGE_CATALOG}
    return [(title, by_title[title]) for title in module.handoffs if title in by_title]


def render_planning_module(module_key: str) -> None:
    module = get_module(module_key)
    key = f"rp_{module.key}"
    hero(
        module.title,
        module.summary,
        eyebrow="BioIntel Research Planning",
        chips=["Guided + Expert", "8+ scientific visuals", "Connected Planning OS", "Specialist engines", "Reproducible export"],
    )
    scientific_boundary_banner(source_kind="reference", release_eligible=False, message=module.boundary)

    mode = st.radio("Workspace mode", ["Guided", "Expert"], horizontal=True, key=f"{key}_mode")
    tabs = st.tabs(["1 · Input & design", "2 · Analysis & visuals", "3 · Review & versions", "4 · Export & handoff", "5 · Connected Planning OS", "6 · Specialist Engine Lab", "7 · Lifecycle & governance", "8 · Guide"])

    with tabs[0]:
        section_title("Prepare the planning dataset", "input")
        source_mode = st.radio("Data source", ["Starter dataset", "Upload planning table"], horizontal=True, key=f"{key}_source")
        template = demo_frame(module.key, 60)
        st.download_button(
            "Download module template",
            template.to_csv(index=False).encode("utf-8"),
            f"{module.key}_template.csv",
            "text/csv",
            key=f"{key}_template",
        )
        raw = template
        if source_mode == "Upload planning table":
            uploaded = st.file_uploader(
                "Upload CSV, TSV, JSON or Excel",
                type=[suffix.lstrip(".") for suffix in sorted(SUPPORTED_SUFFIXES)],
                key=f"{key}_upload",
            )
            if uploaded is None:
                st.info("Upload a planning table or switch to the starter dataset.")
                raw = pd.DataFrame(columns=module.required_columns)
            else:
                try:
                    render_upload_preflight(
                        uploaded,
                        key=f"{key}_upload_preflight",
                        allowed_extensions=SUPPORTED_SUFFIXES,
                        soft_limit_mb=100,
                        hard_limit_mb=1024,
                        module_key=module.key,
                    )
                    raw = read_upload(uploaded.name, uploaded.getvalue())
                except Exception as exc:
                    st.error(f"Input failed safely: {exc}")
                    raw = pd.DataFrame(columns=module.required_columns)
        mapped = _map_columns(raw, module, key)
        if not mapped.empty and mode == "Expert" and st.toggle("Edit imported planning rows", value=False, key=f"{key}_edit"):
            edited = st.data_editor(mapped.head(1000), width="stretch", num_rows="dynamic", key=f"{key}_editor")
            mapped = pd.DataFrame(edited)
        st.session_state[f"{key}_data"] = mapped
        if not mapped.empty:
            missing = [column for column in module.required_columns if column not in mapped.columns]
            quality = 100 * mapped[list(module.required_columns)].notna().mean().mean() if not missing else 0
            metric_cards([
                ("Rows", f"{len(mapped):,}", "Interactive analysis is bounded to 250,000 rows"),
                ("Columns", len(mapped.columns), None),
                ("Required fields", f"{len(module.required_columns)-len(missing)}/{len(module.required_columns)}", None),
                ("Cell completeness", f"{quality:.1f}%", None),
            ])
            smart_dataframe(mapped.head(500), height=360, key=f"{key}_preview")

        section_title("Analysis controls", "settings")
        with st.form(f"{key}_run_form"):
            c1, c2, c3 = st.columns(3)
            scenario_name = c1.text_input("Scenario / plan name", value="Primary planning scenario")
            confidence_policy = c2.selectbox("Planning confidence policy", ["Conservative", "Balanced", "Exploratory"], index=1)
            seed = c3.number_input("Reproducibility seed", min_value=0, max_value=2_147_483_647, value=141, step=1)
            if mode == "Expert":
                st.text_area("Expert assumptions and rationale", value="Document source, justification and uncertainty for all planning assumptions.", key=f"{key}_rationale")
            submitted = st.form_submit_button("Run planning analysis", type="primary", width="stretch")
        if submitted:
            try:
                if mapped.empty:
                    raise ValueError("No planning records are available.")
                result = analyse(module.key, mapped)
                st.session_state[f"{key}_result"] = result
                st.session_state[f"{key}_run_meta"] = {
                    "scenario_name": scenario_name,
                    "confidence_policy": confidence_policy,
                    "seed": int(seed),
                    "input_sha256": dataframe_sha256(mapped),
                }
                st.success("Planning analysis completed.")
            except Exception as exc:
                recovery_id = sha256(f"{module.key}|{type(exc).__name__}|{exc}".encode()).hexdigest()[:12].upper()
                st.session_state.pop(f"{key}_result", None)
                st.error(f"Analysis stopped safely · RP-{recovery_id}\n\n{exc}")

    result = st.session_state.get(f"{key}_result")

    with tabs[1]:
        section_title("Scientific planning results", "results")
        if not isinstance(result, PlanningResult):
            st.info("Run the planning analysis in the first tab to generate results.")
        else:
            _summary_cards(result)
            _interpretation(result)
            visual_lookup = {visual.title: visual for visual in module.visuals}
            selected_title = st.selectbox("Scientific visual", list(visual_lookup), key=f"{key}_visual")
            spec = visual_lookup[selected_title]
            try:
                figure, visual_data = build_figure(spec, result)
                st.plotly_chart(figure, width="stretch", key=f"{key}_chart_{spec.key}")
                st.caption(spec.description or "Interactive planning visual generated from the current analysis result.")
                c1, c2 = st.columns(2)
                c1.download_button("Download visual data", visual_data.to_csv(index=False).encode("utf-8"), f"{module.key}_{spec.key}.csv", "text/csv", key=f"{key}_visual_csv_{spec.key}")
                c2.download_button("Download Plotly JSON", figure.to_json().encode("utf-8"), f"{module.key}_{spec.key}.plotly.json", "application/json", key=f"{key}_visual_json_{spec.key}")
                with st.expander("Underlying visual data", expanded=False):
                    smart_dataframe(visual_data.head(2000), height=390, key=f"{key}_visual_data_{spec.key}")
            except Exception as exc:
                recovery_id = sha256(f"visual|{module.key}|{spec.key}|{exc}".encode()).hexdigest()[:12].upper()
                st.error(f"This visual could not be rendered · VIS-{recovery_id}. Other module functions remain available.")
            st.markdown("### Result tables")
            table_name = st.selectbox("Table", list(result.all_tables()), key=f"{key}_table_name")
            smart_dataframe(result.all_tables()[table_name].head(5000), height=440, key=f"{key}_table_{table_name}")

    with tabs[2]:
        section_title("Scientific review and plan versions", "review")
        if not isinstance(result, PlanningResult):
            st.info("Run an analysis before reviewing records or saving plan versions.")
        else:
            try:
                store = PlanningReviewStore(STORE_PATH)
                primary = result.primary
                id_column = _record_column(primary)
                identifiers = primary[id_column].astype(str).drop_duplicates().tolist()[:5000]
                c1, c2 = st.columns(2)
                record_id = c1.selectbox("Record to review", identifiers, key=f"{key}_review_record")
                decision = c2.selectbox("Decision", ["Needs review", "Accepted", "Rejected", "Needs confirmation", "Escalated"], key=f"{key}_review_decision")
                reviewer = st.text_input("Reviewer", value="Local reviewer", key=f"{key}_reviewer")
                note = st.text_area("Review note and reason", key=f"{key}_review_note")
                if st.button("Save review decision", type="primary", key=f"{key}_save_review"):
                    store.upsert_review(module.key, record_id, decision, reviewer, note)
                    st.success("Review decision saved with timestamp.")
                reviews = store.reviews(module.key)
                smart_dataframe(reviews, height=300, key=f"{key}_reviews")
                st.divider()
                c3, c4 = st.columns(2)
                status = c3.selectbox("Plan version status", ["Draft", "Reviewed", "Locked", "Superseded", "Retracted"], key=f"{key}_version_status")
                reason = c4.text_input("Version reason", value="Planning analysis review", key=f"{key}_version_reason")
                if st.button("Save plan version", key=f"{key}_save_version"):
                    payload = {"summary": result.summary, "run_meta": st.session_state.get(f"{key}_run_meta", {}), "main_finding": result.main_finding}
                    digest = sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
                    version_id = store.save_version(module.key, status, digest, payload, reviewer, reason)
                    st.success(f"Saved version {version_id} as {status}.")
                smart_dataframe(store.versions(module.key), height=300, key=f"{key}_versions")
            except Exception as exc:
                st.error(f"Review store unavailable: {exc}")

    with tabs[3]:
        section_title("Reproducible export and cross-module handoff", "export")
        if not isinstance(result, PlanningResult):
            st.info("Run an analysis before creating the reproducibility package.")
        else:
            reviews = pd.DataFrame()
            try:
                reviews = PlanningReviewStore(STORE_PATH).reviews(module.key)
            except Exception:
                pass
            specialist_payload = st.session_state.get(f"{key}_peak_specialist_payload", {})
            package, manifest = build_bundle(module, result, reviews, specialist_payload=specialist_payload)
            metric_cards([
                ("Bundle size", f"{len(package)/1024:.1f} KB", None),
                ("Tables", len(result.all_tables()), None),
                ("Visual contracts", len(module.visuals), None),
                ("Bundle SHA-256", manifest["bundle_sha256"][:16] + "…", None),
            ])
            st.download_button("Download complete planning package", package, f"{module.key}_reproducibility_bundle.zip", "application/zip", type="primary", width="stretch", key=f"{key}_bundle")
            smart_json(manifest, title="Export manifest", download_name=f"{module.key}_manifest.json", key=f"{key}_manifest")
            st.markdown("### Send current context to related modules")
            selected_ids: list[str] = []
            if not result.primary.empty:
                id_col = _record_column(result.primary)
                selected_ids = st.multiselect("Preserve selected records", result.primary[id_col].astype(str).drop_duplicates().tolist()[:500], key=f"{key}_handoff_records")
            if st.button("Prepare cross-module handoff", key=f"{key}_handoff"):
                st.session_state["biointel_research_planning_context"] = {
                    "source_module": module.key,
                    "source_title": module.title,
                    "selected_record_ids": selected_ids,
                    "summary": result.summary,
                    "input_sha256": result.summary.get("input_sha256"),
                }
                st.success("Planning context prepared. Open a related module below.")
            for title, path in _handoff_pages(module):
                st.page_link(path, label=title)

    with tabs[4]:
        section_title("Connected research planning operating system", "network")
        render_connected_planning_os(module.key, result, key_prefix=f"{key}_connected")

    with tabs[5]:
        section_title("Specialist execution, validation and linked visuals", "analysis")
        render_peak_feature_lab(module.key, result, key_prefix=f"{key}_peak")

    with tabs[6]:
        section_title("Full research lifecycle and governance readiness", "network")
        render_lifecycle_readiness_panel(
            module.key,
            context=st.session_state.get("biointel_master_research_plan", {}),
            key_prefix=f"{key}_lifecycle",
        )

    with tabs[7]:
        section_title("Purpose and safe operating guide", "guide")
        st.markdown(f"**Purpose:** {module.purpose}")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### Core features")
            for feature in module.features:
                st.markdown(f"- {feature}")
        with c2:
            st.markdown("#### Generated outputs")
            for output in module.outputs:
                st.markdown(f"- {output}")
        st.markdown("#### Recommended workflow")
        for index, step in enumerate(module.workflow, start=1):
            st.markdown(f"{index}. {step}")
        with st.expander("Accepted inputs and required fields", expanded=False):
            st.markdown("**Accepted inputs**")
            for item in module.accepted_inputs:
                st.markdown(f"- {item}")
            st.markdown("**Required columns**")
            st.code(", ".join(module.required_columns))
        st.warning(module.boundary)
