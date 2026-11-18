from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import streamlit as st

from biointel.nextgen.catalog import MODULE_BY_KEY
from biointel.nextgen.scientific import analyse, demo_frame, normalise
from biointel.nextgen.visual_intelligence_v132 import (
    VISUAL_BY_KEY,
    VISUAL_CATALOG,
    build_visual_artifact,
    database_summary,
    list_bookmarks,
    list_workspace_layouts,
    record_replay_events,
    record_visual_command,
    save_bookmark,
    save_presenter_session,
    save_workspace_layout,
    visuals_for_module,
)
from biointel.ui.components import metric_cards, scientific_chart_card, scientific_table, smart_dataframe


PROJECT_ROOT = Path(__file__).resolve().parents[3]
STEP128_MODULE_KEYS = (
    "digital_pathology_foundation",
    "long_read_epigenome",
    "single_cell_long_read_isoforms",
    "biomedical_foundation_model_hub",
    "amr_surveillance",
    "spatial_medicine_tme",
    "gene_therapy_vector",
    "cell_therapy_cart",
    "federated_biomedical_ai",
    "clinical_biomarker_survival",
    "protein_ligand_codesign",
    "pangenome_population_medicine",
    "pharmacovigilance_intelligence",
    "synthetic_cohort_trial",
    "autonomous_lab_planner",
)


def _frame(value: Any) -> pd.DataFrame:
    if value is None:
        return pd.DataFrame()
    return pd.DataFrame(value).copy()


def _run_id(run_state: Any) -> str | None:
    if run_state is None:
        return None
    summary = getattr(run_state, "summary", {}) or {}
    return str(summary.get("run_id")) if summary.get("run_id") else None


@st.cache_data(show_spinner=False, ttl=900, max_entries=30)
def _cached_demo_analysis(module_key: str, size: int, threshold: float) -> dict[str, Any]:
    module = MODULE_BY_KEY[module_key]
    data = normalise(demo_frame(module, size), module)
    result, summary, secondary, extras = analyse(data, module, threshold)
    return {
        "data": data,
        "result": result,
        "summary": summary,
        "secondary": secondary,
        "extras": extras,
    }


def _artifact(
    visual_key: str,
    *, module_key: str,
    data: pd.DataFrame,
    result: pd.DataFrame,
    secondary: pd.DataFrame | None,
    extras: Mapping[str, pd.DataFrame] | None,
    key: str,
) -> tuple[pd.DataFrame, str]:
    definition = VISUAL_BY_KEY[visual_key]
    try:
        figure, source, interpretation, limitation = build_visual_artifact(
            visual_key,
            module_key=module_key,
            data=data,
            result=result,
            secondary=secondary,
            extras=extras,
        )
    except MemoryError:
        st.error("Visual generation stopped safely because the available memory boundary was reached.")
        return pd.DataFrame(), ""
    except Exception as exc:
        error_id = f"VIS-{abs(hash((visual_key, str(exc)))):010d}"
        st.error(f"Visual failed safely · {error_id}")
        with st.expander("Recovery details", expanded=False):
            st.write("Reduce filters or switch to a smaller result preview, then retry. Scientific result tables remain available.")
            st.code(type(exc).__name__)
        return pd.DataFrame(), ""

    if figure is not None:
        scientific_chart_card(
            figure,
            title=f"{definition.icon} {definition.title}",
            interpretation=interpretation,
            data=source,
            method="BioIntel AI Step 132 bounded deterministic visual transformation",
            units="Module-dependent",
            key=f"{key}_{visual_key}",
            module_key=module_key,
            configuration={"visual_key": visual_key, "step": 132},
        )
    st.caption(limitation)
    return source, interpretation


def _render_bookmark_controls(
    *,
    module_key: str,
    visual_key: str,
    source: pd.DataFrame,
    interpretation: str,
    key: str,
) -> None:
    c1, c2 = st.columns([3, 1])
    title = c1.text_input(
        "Bookmark title",
        value=VISUAL_BY_KEY[visual_key].title,
        key=f"{key}_bookmark_title",
        label_visibility="collapsed",
    )
    if c2.button("Save visual state", key=f"{key}_save_bookmark", width="stretch"):
        bookmark_id = save_bookmark(
            PROJECT_ROOT,
            module_key=module_key,
            visual_key=visual_key,
            title=title,
            state={
                "interpretation": interpretation,
                "rows": len(source),
                "columns": list(map(str, source.columns)),
                "preview": source.head(25).to_dict(orient="records"),
            },
        )
        st.success(f"Visual bookmark saved: {bookmark_id}")


def render_module_visual_intelligence(
    *,
    module: Any,
    data: pd.DataFrame,
    run_state: Any,
    key: str,
) -> None:
    st.caption(
        "Step 132 visual-intelligence layer: multi-scale navigation, causal/evidence views, temporal replay, "
        "domain-specific scientific canvases, portfolio intelligence and presentation workspaces."
    )
    if run_state is None:
        st.info("Complete an analysis to activate data-linked Step 132 visuals. A bounded demonstration preview is available below.")
        payload = _cached_demo_analysis(module.key, 120, 0.70)
        result = _frame(payload["result"])
        secondary = _frame(payload["secondary"])
        extras = {name: _frame(table) for name, table in payload["extras"].items()}
        source_data = _frame(payload["data"])
    else:
        result = _frame(run_state.result)
        secondary = None if run_state.secondary is None else _frame(run_state.secondary)
        extras = {name: _frame(table) for name, table in dict(run_state.extras or {}).items()}
        source_data = _frame(data)

    visual_keys = visuals_for_module(module.key)
    tabs = st.tabs(["Scientific visuals", "Workspace & presenter", "Bookmarks & replay", "Visual commands"])
    with tabs[0]:
        options = list(visual_keys)
        selected = st.selectbox(
            "Visual intelligence view",
            options,
            format_func=lambda item: f"{VISUAL_BY_KEY[item].icon} {VISUAL_BY_KEY[item].title}",
            key=f"{key}_visual_select",
        )
        definition = VISUAL_BY_KEY[selected]
        st.info(definition.summary)
        source, interpretation = _artifact(
            selected,
            module_key=module.key,
            data=source_data,
            result=result,
            secondary=secondary,
            extras=extras,
            key=f"{key}_artifact",
        )
        if not source.empty:
            _render_bookmark_controls(
                module_key=module.key,
                visual_key=selected,
                source=source,
                interpretation=interpretation,
                key=f"{key}_{selected}",
            )
            with st.expander("Visual source table", expanded=False):
                smart_dataframe(source.head(5_000), height=360, key=f"{key}_{selected}_source")

    with tabs[1]:
        st.markdown("#### Multi-monitor scientific workspace")
        monitor_defaults = [
            ("Monitor 1", "Raw data"),
            ("Monitor 2", "Scientific analysis"),
            ("Monitor 3", "Evidence & review"),
            ("Monitor 4", "Timeline & jobs"),
        ]
        monitors = []
        columns = st.columns(4)
        choices = ["Raw data", "Scientific analysis", "Evidence & review", "Timeline & jobs", "Visual canvas", "Report preview"]
        for index, (label, default) in enumerate(monitor_defaults):
            with columns[index]:
                selected_monitor = st.selectbox(label, choices, index=choices.index(default), key=f"{key}_monitor_{index}")
                monitors.append({"monitor": index + 1, "workspace": selected_monitor})
        layout_name = st.text_input("Layout name", value=f"{module.title} research layout", key=f"{key}_layout_name")
        if st.button("Save multi-monitor layout", key=f"{key}_save_layout", width="stretch"):
            layout_id = save_workspace_layout(PROJECT_ROOT, module_key=module.key, name=layout_name, monitors=monitors)
            st.success(f"Workspace layout saved: {layout_id}")

        st.markdown("#### Scientific presenter mode")
        audience = st.selectbox("Audience mode", ["Research", "Executive", "Clinical review", "Methods review"], key=f"{key}_audience")
        slides = [
            {"title": "Input quality", "visual": visual_keys[0]},
            {"title": "Primary finding", "visual": visual_keys[1] if len(visual_keys) > 1 else visual_keys[0]},
            {"title": "Evidence and uncertainty", "visual": "scientific_contradiction_map"},
            {"title": "Next action", "visual": "experiment_replay"},
        ]
        scientific_table(pd.DataFrame(slides), key=f"{key}_slides", height=260, file_name=f"{module.key}_presenter_slides.csv")
        if st.button("Save presenter session", key=f"{key}_save_presenter", width="stretch"):
            session_id = save_presenter_session(
                PROJECT_ROOT,
                module_key=module.key,
                title=f"{module.title} scientific review",
                slides=slides,
                audience_mode=audience,
            )
            st.success(f"Presenter session saved: {session_id}")

    with tabs[2]:
        bookmarks = list_bookmarks(PROJECT_ROOT, module.key)
        layouts = list_workspace_layouts(PROJECT_ROOT, module.key)
        metric_cards([
            ("Bookmarks", len(bookmarks), "Restorable visual states"),
            ("Layouts", len(layouts), "Saved monitor arrangements"),
            ("Module visuals", len(visual_keys), "Curated Step 132 collection"),
            ("Run ID", _run_id(run_state) or "Demo", "Replay source"),
        ])
        if not bookmarks.empty:
            scientific_table(bookmarks.drop(columns=["state_json"], errors="ignore"), key=f"{key}_bookmarks", height=320, file_name=f"{module.key}_visual_bookmarks.csv")
        if not layouts.empty:
            scientific_table(layouts.drop(columns=["monitors_json"], errors="ignore"), key=f"{key}_layouts", height=280, file_name=f"{module.key}_workspace_layouts.csv")
        replay_source, _ = _artifact(
            "experiment_replay",
            module_key=module.key,
            data=source_data,
            result=result,
            secondary=secondary,
            extras=extras,
            key=f"{key}_replay",
        )
        if st.button("Persist replay events", key=f"{key}_persist_replay", disabled=replay_source.empty, width="stretch"):
            event_ids = record_replay_events(PROJECT_ROOT, module_key=module.key, run_id=_run_id(run_state), replay=replay_source)
            st.success(f"Persisted {len(event_ids)} replay event(s).")

    with tabs[3]:
        commands = {
            "Open biological scale navigator": "biological_scale_navigator",
            "Show causal intervention assumptions": "causal_intervention_graph",
            "Inspect scientific contradictions": "scientific_contradiction_map",
            "Replay the current experiment": "experiment_replay",
            "Open scientific risk heatmap": "scientific_risk_heatmap",
            "Build research portfolio view": "research_portfolio_bubble",
            "Open journal figure builder": "figure_builder",
            "Compare recent runs": "run_comparison",
            "Export selected evidence": "evidence_export",
        }
        command = st.selectbox("Scientific visual command", list(commands), key=f"{key}_command")
        action = commands[command]
        st.code(f"Ctrl+K → {command}", language="text")
        if st.button("Run visual command", key=f"{key}_run_command", width="stretch"):
            command_id = record_visual_command(PROJECT_ROOT, module_key=module.key, command=command, action={"action": action, "run_id": _run_id(run_state)})
            st.session_state[f"{key}_last_command"] = action
            st.success(f"Command recorded: {command_id}")
        last = st.session_state.get(f"{key}_last_command")
        if last in VISUAL_BY_KEY:
            _artifact(
                last,
                module_key=module.key,
                data=source_data,
                result=result,
                secondary=secondary,
                extras=extras,
                key=f"{key}_command_artifact",
            )
        elif last:
            st.info(f"Command routed to the existing {last.replace('_', ' ')} workflow.")


def render_global_visual_intelligence_studio() -> None:
    st.markdown("### Multi-Scale Scientific Visual Intelligence Studio")
    summary = database_summary(PROJECT_ROOT)
    metric_cards([
        ("Visual concepts", len(VISUAL_CATALOG), "Step 132 catalog"),
        ("New biomedical modules", len(STEP128_MODULE_KEYS), "Curated integration"),
        ("Saved bookmarks", summary["bookmarks"], "Persistent visual states"),
        ("Workspace layouts", summary["layouts"], "Multi-monitor arrangements"),
        ("Presenter sessions", summary["presenter_sessions"], "Audience-specific stories"),
    ])

    left, middle, right = st.columns([2, 1, 1])
    module_key = left.selectbox(
        "Scientific module",
        STEP128_MODULE_KEYS,
        format_func=lambda item: MODULE_BY_KEY[item].title,
        key="step132_global_module",
    )
    size = middle.slider("Demo records", 60, 360, 120, 30, key="step132_global_size")
    threshold = right.slider("Threshold", 0.10, 0.95, 0.70, 0.05, key="step132_global_threshold")
    payload = _cached_demo_analysis(module_key, size, threshold)

    categories = sorted({item.category for item in VISUAL_CATALOG})
    category = st.selectbox("Visual category", ["All", *categories], key="step132_global_category")
    definitions = [item for item in VISUAL_CATALOG if category == "All" or item.category == category]
    visual_key = st.selectbox(
        "Visual",
        [item.key for item in definitions],
        format_func=lambda item: f"{VISUAL_BY_KEY[item].icon} {VISUAL_BY_KEY[item].title}",
        key="step132_global_visual",
    )
    st.info(VISUAL_BY_KEY[visual_key].summary)
    source, interpretation = _artifact(
        visual_key,
        module_key=module_key,
        data=payload["data"],
        result=payload["result"],
        secondary=payload["secondary"],
        extras=payload["extras"],
        key="step132_global_artifact",
    )
    if not source.empty:
        _render_bookmark_controls(
            module_key=module_key,
            visual_key=visual_key,
            source=source,
            interpretation=interpretation,
            key="step132_global",
        )

    with st.expander("Complete Step 132 visual catalog", expanded=False):
        catalog = pd.DataFrame([
            {
                "visual": item.title,
                "category": item.category,
                "summary": item.summary,
                "specialised_modules": len(item.module_keys),
            }
            for item in VISUAL_CATALOG
        ])
        scientific_table(catalog, key="step132_visual_catalog", height=620, file_name="step132_visual_catalog.csv")

    st.markdown("### Optimization architecture")
    st.write(
        "Visuals are generated lazily—only the selected concept is computed. Demonstration analyses use bounded Streamlit caching, "
        "browser payloads are limited, high-density plots use WebGL where compatible, and persistence uses indexed local SQLite tables."
    )
