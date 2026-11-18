from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from biointel.nextgen.intelligence import (
    HANDOFF_TARGETS,
    add_evidence_items,
    audit_visuals,
    build_evidence_items,
    build_publication_bundle,
    build_scientific_story,
    compare_run_snapshots,
    create_handoff,
    evaluate_threshold_scenarios,
    infer_entity_column,
    list_evidence_board,
    list_handoffs,
    list_review_decisions,
    list_run_snapshots,
    list_scenarios,
    list_validation_cohorts,
    register_validation_cohort,
    save_review_decision,
    save_scenario_run,
)
from biointel.ui.components import metric_cards, scientific_chart_card, scientific_table, smart_dataframe, smart_json
from biointel.ui.scientific_visuals import build_scientific_visuals
from biointel.ui.visual_workspace import get_linked_selection, clear_linked_selection
from biointel.ui.reactive_scientific_workspace import render_reactive_scientific_workspace
from biointel.ui.visual_intelligence_v132 import render_module_visual_intelligence


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _run_id(run_state: Any) -> str | None:
    if run_state is None:
        return None
    summary = getattr(run_state, "summary", {}) or {}
    value = summary.get("run_id")
    return str(value) if value else None


def _frame(value: Any) -> pd.DataFrame:
    if value is None:
        return pd.DataFrame()
    return pd.DataFrame(value).copy()


def _entity_options(frame: pd.DataFrame) -> tuple[str | None, list[str]]:
    column = infer_entity_column(frame)
    if not column:
        return None, []
    values = frame[column].dropna().astype(str).drop_duplicates().head(5000).tolist()
    return column, values


def apply_linked_context(
    module_key: str,
    result: pd.DataFrame,
    secondary: pd.DataFrame | None,
    extras: Mapping[str, pd.DataFrame] | None,
) -> tuple[pd.DataFrame, pd.DataFrame | None, dict[str, pd.DataFrame], dict[str, Any] | None]:
    result_frame = _frame(result)
    secondary_frame = None if secondary is None else _frame(secondary)
    extra_frames = {str(name): _frame(table) for name, table in dict(extras or {}).items()}
    context = get_linked_selection(module_key)
    if not context:
        return result_frame, secondary_frame, extra_frames, None
    column = str(context.get("column", ""))
    values = {str(value) for value in context.get("values", [])}
    if not column or not values:
        return result_frame, secondary_frame, extra_frames, None

    def filtered(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty or column not in frame.columns:
            return frame
        mask = frame[column].astype(str).isin(values)
        return frame.loc[mask].copy() if mask.any() else frame

    result_frame = filtered(result_frame)
    secondary_frame = filtered(secondary_frame) if secondary_frame is not None else None
    extra_frames = {name: filtered(table) for name, table in extra_frames.items()}
    return result_frame, secondary_frame, extra_frames, context


def render_linked_context_banner(module_key: str, *, key: str) -> None:
    context = get_linked_selection(module_key)
    if not context:
        return
    values = [str(value) for value in context.get("values", [])]
    left, right = st.columns([5, 1])
    left.info(
        f"Linked selection active · {context.get('column', 'entity')} = "
        f"{', '.join(values[:5])}{'…' if len(values) > 5 else ''}. "
        "All compatible result tables and visuals use this context."
    )
    if right.button("Clear link", key=f"{key}_clear_link", width="stretch"):
        clear_linked_selection(module_key)
        st.rerun()


def render_manual_linked_selector(module_key: str, result: pd.DataFrame, *, key: str) -> None:
    frame = _frame(result)
    column, values = _entity_options(frame)
    if not column or not values:
        return
    with st.expander("Linked scientific selection", expanded=False):
        selected = st.multiselect(
            f"Link all compatible visuals by {column.replace('_', ' ')}",
            values,
            key=f"{key}_manual_link",
            help="This selection persists across visual cards in the current module until cleared.",
        )
        c1, c2 = st.columns(2)
        if c1.button("Apply linked selection", key=f"{key}_apply_link", disabled=not selected, width="stretch"):
            st.session_state[f"biointel_linked_selection_{module_key}"] = {
                "column": column,
                "values": selected,
                "source": "manual_result_selector",
            }
            st.rerun()
        if c2.button("Clear linked selection", key=f"{key}_manual_clear", width="stretch"):
            clear_linked_selection(module_key)
            st.rerun()


def render_run_history_comparison(module_key: str, *, key: str) -> None:
    st.markdown("#### Multi-run comparison")
    history = list_run_snapshots(PROJECT_ROOT, module_key, limit=50)
    if history.empty or len(history) < 2:
        st.info("At least two completed runs are required for a persistent run comparison.")
        return
    labels = {
        f"{row['completed_at_utc']} · {row['run_id']} · {row['result_rows']} rows": index
        for index, row in history.iterrows()
    }
    left, right = st.columns(2)
    label_a = left.selectbox("Run A", list(labels), index=0, key=f"{key}_run_a")
    remaining = [label for label in labels if label != label_a]
    label_b = right.selectbox("Run B", remaining, index=0, key=f"{key}_run_b")
    run_a = history.loc[labels[label_a]].to_dict()
    run_b = history.loc[labels[label_b]].to_dict()
    comparison = compare_run_snapshots(run_a, run_b)
    metric_cards([
        ("Run A rows", int(run_a.get("result_rows", 0)), run_a.get("run_id")),
        ("Run B rows", int(run_b.get("result_rows", 0)), run_b.get("run_id")),
        ("Changed fields", int(comparison["changed"].fillna(False).astype(bool).sum()), "Parameters, summary and outputs"),
        ("Same result hash", "Yes" if run_a.get("result_sha256") == run_b.get("result_sha256") else "No", "Deterministic output comparison"),
    ])
    scientific_table(comparison, key=f"{key}_run_diff", height=360, file_name=f"{module_key}_run_comparison.csv")
    preview_a = pd.DataFrame(run_a.get("preview", []))
    preview_b = pd.DataFrame(run_b.get("preview", []))
    if not preview_a.empty or not preview_b.empty:
        c1, c2 = st.columns(2)
        with c1:
            st.caption("Run A bounded preview")
            smart_dataframe(preview_a.head(100), height=300, key=f"{key}_preview_a")
        with c2:
            st.caption("Run B bounded preview")
            smart_dataframe(preview_b.head(100), height=300, key=f"{key}_preview_b")


def render_scenario_simulator(
    *,
    module_key: str,
    data: pd.DataFrame,
    analyser: Callable[[pd.DataFrame, float], tuple[pd.DataFrame, dict[str, Any], pd.DataFrame | None, dict[str, pd.DataFrame]]],
    baseline: float,
    run_id: str | None,
    key: str,
) -> None:
    st.markdown("#### Scenario & sensitivity simulator")
    if data.empty:
        st.info("Prepare a dataset before running sensitivity scenarios.")
        return
    c1, c2, c3 = st.columns(3)
    low = c1.slider("Minimum threshold", 0.10, 0.90, max(0.10, round(baseline - 0.20, 2)), 0.05, key=f"{key}_scenario_low")
    high = c2.slider("Maximum threshold", 0.20, 0.99, min(0.99, round(baseline + 0.20, 2)), 0.05, key=f"{key}_scenario_high")
    steps = c3.slider("Scenarios", 3, 9, 5, 1, key=f"{key}_scenario_steps")
    name = st.text_input("Scenario name", value=f"{module_key.replace('_', ' ').title()} threshold sensitivity", key=f"{key}_scenario_name")
    if low >= high:
        st.warning("Minimum threshold must be lower than maximum threshold.")
        return
    signature = hashlib.sha256(
        f"{module_key}|{len(data)}|{low}|{high}|{steps}|{baseline}".encode("utf-8")
    ).hexdigest()[:16]
    if st.button("Run bounded sensitivity analysis", key=f"{key}_run_scenarios", type="primary", width="stretch"):
        with st.status("Evaluating threshold scenarios…", expanded=True) as status:
            thresholds = np.linspace(low, high, steps).round(4).tolist()
            result = evaluate_threshold_scenarios(data=data, analyser=analyser, thresholds=thresholds)
            st.session_state[f"{key}_scenario_{signature}"] = result
            status.update(label="Scenario analysis completed", state="complete", expanded=False)
    scenario = st.session_state.get(f"{key}_scenario_{signature}")
    if not isinstance(scenario, pd.DataFrame) or scenario.empty:
        history = list_scenarios(PROJECT_ROOT, module_key)
        if not history.empty:
            with st.expander("Saved scenario history", expanded=False):
                smart_dataframe(history.drop(columns=["values_json", "results_json"], errors="ignore"), height=280, key=f"{key}_scenario_history")
        return
    completed = scenario[scenario["status"] == "completed"].copy()
    if not completed.empty:
        fig = px.line(completed, x="threshold", y="result_rows", markers=True, title="Candidate count sensitivity")
        scientific_chart_card(
            fig,
            title="Candidate count sensitivity",
            interpretation="Shows how the selected scientific threshold changes the number of result records.",
            data=completed,
            method="Repeated bounded reruns of the same deterministic analysis",
            key=f"{key}_scenario_chart",
            module_key=module_key,
            configuration={"scenario": name, "baseline": baseline},
        )
        if completed["mean_score"].notna().any():
            score_fig = px.line(completed, x="threshold", y="mean_score", markers=True, title="Mean result score sensitivity")
            scientific_chart_card(
                score_fig,
                title="Mean score sensitivity",
                interpretation="Tests whether the average prioritisation score is stable across plausible threshold choices.",
                data=completed,
                method="Repeated bounded reruns",
                key=f"{key}_scenario_score_chart",
                module_key=module_key,
            )
    scientific_table(scenario, key=f"{key}_scenario_table", height=330, file_name=f"{module_key}_sensitivity.csv")
    if st.button("Save scenario", key=f"{key}_save_scenario", width="stretch"):
        scenario_id = save_scenario_run(
            project_root=PROJECT_ROOT,
            module_key=module_key,
            name=name,
            baseline=baseline,
            results=scenario,
            run_id=run_id,
        )
        st.success(f"Scenario saved: {scenario_id}")


def render_review_layer(module_key: str, run_state: Any, *, key: str) -> None:
    st.markdown("#### Scientific annotation and review")
    if run_state is None:
        st.info("Complete an analysis before recording candidate decisions.")
        return
    result = _frame(run_state.result)
    entity_column, values = _entity_options(result)
    if not entity_column or not values:
        st.info("No stable entity identifier is available in this result.")
        return
    c1, c2, c3 = st.columns(3)
    entity = c1.selectbox("Entity", values, key=f"{key}_review_entity")
    decision = c2.selectbox("Decision", ["Review", "Shortlist", "Approve", "Reject", "Needs more evidence"], key=f"{key}_review_decision")
    reviewer = c3.text_input("Reviewer", value="local-scientist", key=f"{key}_reviewer")
    note = st.text_area("Decision note", placeholder="Record the scientific reason, limitation, threshold or follow-up experiment.", key=f"{key}_review_note")
    selected = result[result[entity_column].astype(str) == str(entity)].head(20)
    if not selected.empty:
        smart_dataframe(selected, height=260, key=f"{key}_review_selected")
    if st.button("Record version-linked decision", key=f"{key}_save_review", width="stretch"):
        decision_id = save_review_decision(
            project_root=PROJECT_ROOT,
            module_key=module_key,
            run_id=_run_id(run_state),
            entity_id=entity,
            decision=decision,
            note=note,
            reviewer=reviewer,
            evidence={"entity_column": entity_column, "records": selected.to_dict(orient="records")},
        )
        st.success(f"Review decision saved: {decision_id}")
    history = list_review_decisions(PROJECT_ROOT, module_key)
    if not history.empty:
        with st.expander("Review history", expanded=False):
            smart_dataframe(history.drop(columns=["evidence_json"], errors="ignore"), height=320, key=f"{key}_review_history")


def render_evidence_board_panel(module_key: str, run_state: Any, *, key: str) -> None:
    st.markdown("#### Cross-module evidence board")
    if run_state is None:
        st.info("Complete an analysis to create evidence-board items.")
        return
    board_id = st.text_input("Evidence board", value="primary-research-board", key=f"{key}_board_id")
    items = build_evidence_items(
        module_key=module_key,
        result=run_state.result,
        run_id=_run_id(run_state),
        max_items=50,
    )
    if not items.empty:
        smart_dataframe(items.drop(columns=["payload"], errors="ignore"), height=300, key=f"{key}_board_preview")
    if st.button("Add current candidates to evidence board", key=f"{key}_add_board", disabled=items.empty, width="stretch"):
        ids = add_evidence_items(project_root=PROJECT_ROOT, board_id=board_id, items=items)
        st.success(f"Added {len(ids)} evidence item(s) to {board_id}.")
    board = list_evidence_board(PROJECT_ROOT, board_id)
    if not board.empty:
        with st.expander("Current board", expanded=False):
            scientific_table(board.drop(columns=["payload_json"], errors="ignore"), key=f"{key}_board_table", height=360, file_name=f"{board_id}_evidence_board.csv")


def render_handoff_panel(module_key: str, run_state: Any, *, key: str) -> None:
    st.markdown("#### Cross-module handoff")
    targets = HANDOFF_TARGETS.get(module_key, ())
    if not targets:
        st.caption("No curated handoff target is registered for this module.")
        return
    target = st.selectbox("Target module", targets, format_func=lambda value: value.replace("_", " ").title(), key=f"{key}_handoff_target")
    note = st.text_area("Handoff note", placeholder="Describe the selected candidates and the question for the receiving module.", key=f"{key}_handoff_note")
    if run_state is None:
        st.info("Complete an analysis before creating a handoff.")
        return
    result = _frame(run_state.result)
    entity_column, values = _entity_options(result)
    selected_entities = st.multiselect("Entities to hand off", values[:500] if values else [], default=(values[:3] if values else []), key=f"{key}_handoff_entities")
    selected_rows = result[result[entity_column].astype(str).isin(selected_entities)].head(200) if entity_column and selected_entities else result.head(20)
    if st.button("Create auditable handoff", key=f"{key}_create_handoff", width="stretch"):
        handoff_id = create_handoff(
            project_root=PROJECT_ROOT,
            source_module=module_key,
            target_module=target,
            run_id=_run_id(run_state),
            payload={
                "note": note,
                "entity_column": entity_column,
                "selected_entities": selected_entities,
                "records": selected_rows.to_dict(orient="records"),
                "summary": run_state.summary,
            },
        )
        st.success(f"Handoff created: {handoff_id}")
    recent = list_handoffs(PROJECT_ROOT, source_module=module_key)
    if not recent.empty:
        with st.expander("Recent outgoing handoffs", expanded=False):
            smart_dataframe(recent.drop(columns=["payload_json"], errors="ignore"), height=280, key=f"{key}_handoff_history")


def render_story_and_publication(module: Any, run_state: Any, *, key: str) -> None:
    st.markdown("#### Scientific story and publication figure package")
    if run_state is None:
        st.info("Complete an analysis before generating a scientific story.")
        return
    story = build_scientific_story(
        module_title=module.title,
        boundary=module.boundary,
        run_id=_run_id(run_state),
        summary=run_state.summary,
        result=run_state.result,
        extras=run_state.extras,
    )
    story_frame = pd.DataFrame(story)
    smart_dataframe(story_frame, height=300, key=f"{key}_story")
    for item in story:
        with st.container(border=True):
            st.markdown(f"**{item['stage']}**")
            st.write(item["message"])
    bundle_key = f"{key}_publication_bundle"
    if st.button("Build SVG/PDF/DOCX/PPTX publication package", key=f"{key}_build_publication", width="stretch"):
        with st.spinner("Building vector figure and reproducible report package…"):
            st.session_state[bundle_key] = build_publication_bundle(
                module_key=module.key,
                module_title=module.title,
                boundary=module.boundary,
                run_id=_run_id(run_state),
                result=run_state.result,
                summary=run_state.summary,
                story=story,
                extras=run_state.extras,
            )
    bundle = st.session_state.get(bundle_key)
    if bundle:
        st.download_button(
            "Download publication figure package",
            bundle,
            f"{module.key}_publication_figure_package.zip",
            "application/zip",
            key=f"{key}_publication_download",
            width="stretch",
        )
        st.caption("The package is publication-ready for figure editing and reporting; it does not claim journal acceptance or external validation.")


def render_visual_quality_inspector(module_key: str, data: pd.DataFrame, run_state: Any, *, key: str) -> None:
    st.markdown("#### Automated visual quality inspector")
    if run_state is None:
        st.info("Complete an analysis before auditing its visual collection.")
        return
    visuals = build_scientific_visuals(
        module_key,
        data=data,
        result=run_state.result,
        secondary=run_state.secondary,
        extras=run_state.extras,
    )
    audit = audit_visuals(visuals)
    if audit.empty:
        st.warning("No visual definitions were available for inspection.")
        return
    blocked = int((audit["status"] == "Blocked").sum())
    review = int((audit["status"] == "Review").sum())
    metric_cards([
        ("Visuals audited", len(audit), "Module-specific collection"),
        ("Passed", int((audit["status"] == "Passed").sum()), "No detected issue"),
        ("Review", review, "Manual visual review recommended"),
        ("Blocked", blocked, "Fix before report use"),
    ])
    scientific_table(audit, key=f"{key}_visual_audit", height=360, file_name=f"{module_key}_visual_quality_audit.csv")


def render_nextgen_intelligence_workspace(
    *,
    module: Any,
    data: pd.DataFrame,
    run_state: Any,
    analyser: Callable[[pd.DataFrame, float], tuple[pd.DataFrame, dict[str, Any], pd.DataFrame | None, dict[str, pd.DataFrame]]],
    key: str,
) -> None:
    st.caption(
        "Shared Step 131 intelligence layer: persistent run comparison, linked selection, scenario simulation, "
        "review decisions, evidence boards, cross-module handoffs, story mode and publication figures."
    )
    if run_state is not None:
        render_manual_linked_selector(module.key, run_state.result, key=f"{key}_linked")
        render_linked_context_banner(module.key, key=f"{key}_linked_banner")
    tabs = st.tabs([
        "Run comparison",
        "Scenario simulator",
        "Review & annotation",
        "Evidence board",
        "Handoff",
        "Story & figures",
        "Visual QA",
        "Live interaction & collaboration",
        "Multi-scale visual intelligence",
    ])
    with tabs[0]:
        render_run_history_comparison(module.key, key=f"{key}_history")
    with tabs[1]:
        baseline = float((getattr(run_state, "parameters", {}) or {}).get("threshold", 0.70))
        render_scenario_simulator(
            module_key=module.key,
            data=data,
            analyser=analyser,
            baseline=baseline,
            run_id=_run_id(run_state),
            key=f"{key}_scenario",
        )
    with tabs[2]:
        render_review_layer(module.key, run_state, key=f"{key}_review")
    with tabs[3]:
        render_evidence_board_panel(module.key, run_state, key=f"{key}_evidence")
    with tabs[4]:
        render_handoff_panel(module.key, run_state, key=f"{key}_handoff")
    with tabs[5]:
        render_story_and_publication(module, run_state, key=f"{key}_story")
    with tabs[6]:
        render_visual_quality_inspector(module.key, data, run_state, key=f"{key}_quality")
    with tabs[7]:
        render_reactive_scientific_workspace(
            module=module, data=data, run_state=run_state, key=f"{key}_reactive"
        )
    with tabs[8]:
        render_module_visual_intelligence(
            module=module, data=data, run_state=run_state, key=f"{key}_visual132"
        )


def render_global_evidence_board() -> None:
    st.markdown("### Cross-Module Evidence Board")
    board_id = st.text_input("Board ID", value="primary-research-board", key="global_board_id")
    board = list_evidence_board(PROJECT_ROOT, board_id)
    if board.empty:
        st.info("No evidence items have been added to this board yet.")
        return
    c1, c2, c3 = st.columns(3)
    module_filter = c1.multiselect("Modules", sorted(board["module_key"].dropna().astype(str).unique().tolist()))
    status_filter = c2.multiselect("Evidence status", sorted(board["evidence_status"].dropna().astype(str).unique().tolist()))
    min_confidence = c3.slider("Minimum confidence", 0.0, 1.0, 0.0, 0.05)
    filtered = board.copy()
    if module_filter:
        filtered = filtered[filtered["module_key"].astype(str).isin(module_filter)]
    if status_filter:
        filtered = filtered[filtered["evidence_status"].astype(str).isin(status_filter)]
    confidence = pd.to_numeric(filtered["confidence"], errors="coerce")
    filtered = filtered[(confidence.isna()) | (confidence >= min_confidence)]
    confidence = pd.to_numeric(filtered["confidence"], errors="coerce")
    metric_cards([
        ("Evidence items", len(filtered), board_id),
        ("Modules", filtered["module_key"].nunique(), "Cross-module coverage"),
        ("Entities", filtered["entity_id"].nunique(), "Unique evidence subjects"),
        ("Mean confidence", f"{confidence.mean():.3f}" if confidence.notna().any() else "N/A", "Normalised screening confidence"),
    ])
    scientific_table(filtered.drop(columns=["payload_json"], errors="ignore"), key="global_evidence_table", height=520, file_name=f"{board_id}_cross_module_evidence.csv")
    if confidence.notna().any():
        chart_data = filtered.assign(confidence_numeric=confidence).dropna(subset=["confidence_numeric"])
        fig = px.box(chart_data, x="module_key", y="confidence_numeric", points="all", title="Evidence confidence by module")
        scientific_chart_card(
            fig,
            title="Evidence confidence by module",
            interpretation="Compares the normalised confidence attached to evidence-board items across source modules.",
            data=chart_data,
            method="Board-level grouped distribution",
            key="global_evidence_confidence",
            module_key="cross_module_evidence_board",
        )


def render_validation_cohort_manager() -> None:
    st.markdown("### Validation Cohort Manager")
    st.caption("Register internal, external, temporal, site, locked-test, blinded and prospective cohort manifests without copying the source data into the registry.")
    roles = ["internal", "external", "temporal", "site", "locked_test", "blinded_outcome", "prospective"]
    upload = st.file_uploader("Cohort table", type=["csv", "tsv", "txt"], key="validation_cohort_upload")
    c1, c2, c3 = st.columns(3)
    name = c1.text_input("Cohort name", value="Validation cohort")
    module_key = c2.text_input("Target module", value="clinical_biomarker_survival")
    role = c3.selectbox("Cohort role", roles)
    c4, c5 = st.columns(2)
    locked = c4.checkbox("Lock cohort identity", value=True)
    blinded = c5.checkbox("Outcome blinded", value=role == "blinded_outcome")
    notes = st.text_area("Notes", placeholder="Source, inclusion criteria, endpoint state, site and intended validation purpose.")
    if upload is not None:
        payload = upload.getvalue()
        if len(payload) > 250 * 1024 * 1024:
            st.error("Validation cohort registration is capped at 250 MB. Stage larger cohorts through the background data workflow.")
            return
        sep = "\t" if upload.name.lower().endswith((".tsv", ".txt")) else ","
        try:
            frame = pd.read_csv(io.BytesIO(payload), sep=sep, nrows=1_000_000)
            metric_cards([
                ("Rows", len(frame), "Bounded parsed rows"),
                ("Columns", len(frame.columns), "Detected fields"),
                ("SHA-256", hashlib.sha256(payload).hexdigest()[:16] + "…", "Immutable source identity"),
                ("Blinded", "Yes" if blinded else "No", "Registry state"),
            ])
            smart_dataframe(frame.head(100), height=300, key="validation_cohort_preview")
            if st.button("Register cohort manifest", type="primary", width="stretch"):
                cohort_id = register_validation_cohort(
                    project_root=PROJECT_ROOT,
                    name=name,
                    module_key=module_key,
                    cohort_role=role,
                    source_bytes=payload,
                    row_count=len(frame),
                    column_count=len(frame.columns),
                    locked=locked,
                    blinded=blinded,
                    notes=notes,
                    metadata={"filename": upload.name, "columns": list(map(str, frame.columns))},
                )
                st.success(f"Cohort registered: {cohort_id}")
        except Exception as exc:
            st.error(f"Cohort file failed safely: {exc}")
    cohorts = list_validation_cohorts(PROJECT_ROOT)
    if not cohorts.empty:
        st.markdown("#### Registered cohorts")
        scientific_table(cohorts.drop(columns=["metadata_json"], errors="ignore"), key="validation_cohorts", height=460, file_name="validation_cohort_registry.csv")


def render_visual_review_center() -> None:
    st.markdown("### Visual Review & Approval Center")
    from biointel.ui.visual_workspace import list_all_annotations, list_all_views, list_visual_errors

    views = list_all_views()
    annotations = list_all_annotations()
    errors = list_visual_errors()
    reviews = list_review_decisions(PROJECT_ROOT)
    metric_cards([
        ("Saved views", len(views), "Persistent visual configurations"),
        ("Visual annotations", len(annotations), "Chart-level reviewer notes"),
        ("Candidate decisions", len(reviews), "Run-linked scientific reviews"),
        ("Visual errors", len(errors), "Recorded rendering incidents"),
    ])
    tabs = st.tabs(["Saved views", "Annotations", "Candidate decisions", "Visual errors"])
    with tabs[0]:
        smart_dataframe(views.drop(columns=["configuration_json"], errors="ignore"), height=460, key="review_center_views") if not views.empty else st.info("No saved views.")
    with tabs[1]:
        smart_dataframe(annotations, height=460, key="review_center_annotations") if not annotations.empty else st.info("No visual annotations.")
    with tabs[2]:
        smart_dataframe(reviews.drop(columns=["evidence_json"], errors="ignore"), height=460, key="review_center_decisions") if not reviews.empty else st.info("No candidate decisions.")
    with tabs[3]:
        smart_dataframe(errors, height=460, key="review_center_errors") if not errors.empty else st.success("No visual rendering errors are currently recorded.")
