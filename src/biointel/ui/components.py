from __future__ import annotations

import hashlib
import html
import inspect
import json
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd
import streamlit as st

from biointel.ui.operational_canvas import render_operational_canvas
from biointel.ui.public_branding import brand_public_text, brand_public_value


def scientific_boundary_banner(
    *,
    source_kind: str,
    release_eligible: bool,
    message: str | None = None,
) -> None:
    normalized = source_kind.strip().lower()
    if release_eligible:
        tone = "success"
        label = "Scientific release eligible"
    elif normalized in {"real_public", "verified_public_reference", "external_public"}:
        tone = "info"
        label = "Verified public reference data"
    else:
        tone = "warning"
        label = "Demonstration / reference data"
    copy = message or (
        "Use this material for exploration and software validation. Confirm source licences, assay context, and independent validation before scientific release."
    )
    allow_legal = bool(st.session_state.get("_biointel_legal_notice_view", False))
    label = str(brand_public_text(label, allow_legal=allow_legal))
    copy = str(brand_public_text(copy, allow_legal=allow_legal))
    st.markdown(
        f"""
        <div class="bio-boundary bio-boundary-{tone}">
          <strong>{html.escape(label)}</strong>
          <span>{html.escape(copy)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_cards(items: Iterable[tuple[str, Any, str | None]]) -> None:
    values = list(items)
    columns = st.columns(max(1, min(len(values), 4)))
    for index, (label, value, help_text) in enumerate(values):
        columns[index % len(columns)].metric(label, value, help=help_text)


def smart_dataframe(
    frame: pd.DataFrame | list[dict[str, Any]],
    *,
    height: int = 430,
    key: str | None = None,
    columns: dict[str, Any] | None = None,
    hide_index: bool = True,
) -> None:
    allow_legal = bool(st.session_state.get("_biointel_legal_notice_view", False))
    branded_frame = brand_public_value(frame, allow_legal=allow_legal)
    data = pd.DataFrame(branded_frame)
    if data.empty:
        st.info("No records match the current filters.")
        return
    display = data.copy()
    if bool(st.session_state.get("_bio_peak_target_active", False)) and bool(
        st.session_state.get("_bio_peak_mode_active", True)
    ):
        try:
            from biointel.peak_potential.quality import audit_frame

            audit = audit_frame(data)
            audits = dict(st.session_state.get("_bio_peak_frame_audits", {}) or {})
            audit_key = str(key or f"table_{len(audits) + 1}")
            audits[audit_key] = audit.to_dict()
            st.session_state["_bio_peak_frame_audits"] = audits
            if audit.duplicate_columns:
                st.warning(
                    "Duplicate display columns were renamed safely. Resolve the source schema before scientific export."
                )
            if audit.infinite_cells:
                st.warning(
                    f"{audit.infinite_cells:,} non-finite numeric values are shown as missing and remain a quality blocker."
                )
            display = display.replace([float("inf"), float("-inf")], pd.NA)
        except Exception:
            pass
    if display.columns.duplicated().any():
        counts: dict[str, int] = {}
        unique_columns: list[str] = []
        for raw_name in map(str, display.columns):
            count = counts.get(raw_name, 0)
            counts[raw_name] = count + 1
            unique_columns.append(raw_name if count == 0 else f"{raw_name}__{count + 1}")
        display.columns = unique_columns
    for name in display.columns:
        lower = str(name).lower()
        if pd.api.types.is_object_dtype(display[name]):
            non_null = display[name].dropna()
            observed_types = {type(value) for value in non_null.head(500)}
            if len(observed_types) > 1 or any(kind in observed_types for kind in (dict, list, tuple, set)):
                display[name] = display[name].map(
                    lambda value: "—" if value is None else (
                        json.dumps(value, sort_keys=True, default=str)
                        if isinstance(value, (dict, list, tuple, set))
                        else str(value)
                    )
                )
        if "sha256" in lower or lower.endswith("_hash"):
            display[name] = display[name].astype(str).map(
                lambda value: value if len(value) <= 18 else f"{value[:10]}…{value[-6:]}"
            )
        if lower.endswith("_at_utc") or lower in {"created_at", "updated_at", "timestamp"}:
            parsed = pd.to_datetime(display[name], errors="coerce", utc=True)
            if parsed.notna().any():
                display[name] = parsed.dt.strftime("%Y-%m-%d %H:%M UTC")
        if lower.endswith("_json"):
            display[name] = display[name].map(_compact_json)
    st.dataframe(
        display,
        width="stretch",
        height=height,
        hide_index=hide_index,
        key=key,
        column_config=columns or {},
    )


def _compact_json(value: Any) -> str:
    if value in (None, "", "{}", "[]"):
        return "—"
    try:
        parsed = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return str(value)
    if isinstance(parsed, dict):
        return ", ".join(f"{key}: {parsed[key]}" for key in list(parsed)[:4])
    if isinstance(parsed, list):
        return ", ".join(map(str, parsed[:5]))
    return str(parsed)


def result_summary(payload: dict[str, Any], *, title: str = "Result summary") -> None:
    st.subheader(title)
    scalar = {
        key: value
        for key, value in payload.items()
        if isinstance(value, (str, int, float, bool)) or value is None
    }
    if scalar:
        rows = [{"Metric": key.replace("_", " ").title(), "Value": value} for key, value in scalar.items()]
        smart_dataframe(rows, height=min(430, 70 + len(rows) * 35))
    nested = {key: value for key, value in payload.items() if key not in scalar}
    if nested:
        with st.expander("Technical details", expanded=False):
            render_operational_canvas(
                "Technical result details",
                nested,
                workflow=("Source", "Processing", "Review", "Export"),
            )


@contextmanager
def workflow_status(label: str):
    if hasattr(st, "status"):
        with st.status(label, expanded=False) as status:
            try:
                yield status
                status.update(label=f"{label} — complete", state="complete", expanded=False)
            except Exception:
                status.update(label=f"{label} — failed", state="error", expanded=True)
                raise
    else:  # pragma: no cover
        with st.spinner(label):
            yield None



def _smart_json_key(payload: Any, download_name: str, explicit_key: str | None = None) -> str:
    if explicit_key:
        return explicit_key
    caller = inspect.currentframe()
    caller = caller.f_back.f_back if caller and caller.f_back and caller.f_back.f_back else None
    location = f"{getattr(caller, 'f_code', None).co_filename if caller else ''}:{caller.f_lineno if caller else 0}"
    serialized = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    digest = hashlib.sha256(f"{location}|{download_name}|{serialized}".encode("utf-8")).hexdigest()[:20]
    return f"smart_json_download_{digest}"


def smart_json(
    payload: Any,
    *,
    title: str = "Structured result",
    expanded: bool = False,
    download_name: str = "biointel_result.json",
    key: str | None = None,
) -> None:
    """Render structured results with stable, collision-resistant widget keys."""
    if payload is None:
        st.info("No structured result is available.")
        return
    allow_legal = bool(st.session_state.get("_biointel_legal_notice_view", False))
    payload = brand_public_value(payload, allow_legal=allow_legal)
    widget_key = _smart_json_key(payload, download_name, key)
    if isinstance(payload, dict):
        scalar = {
            field: value
            for field, value in payload.items()
            if isinstance(value, (str, int, float, bool)) or value is None
        }
        nested = {field: value for field, value in payload.items() if field not in scalar}
        if scalar:
            st.markdown(f"**{title}**")
            metric_rows = [
                {"Metric": str(field).replace("_", " ").title(), "Value": value}
                for field, value in scalar.items()
            ]
            smart_dataframe(metric_rows, height=min(430, 80 + len(metric_rows) * 34))
        for index, (field, value) in enumerate(nested.items()):
            label = str(field).replace("_", " ").title()
            nested_key = f"{widget_key}_{index}_{hashlib.sha1(str(field).encode()).hexdigest()[:8]}"
            if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
                with st.expander(f"{label} · {len(value)} record(s)", expanded=expanded):
                    smart_dataframe(value, height=min(520, 120 + len(value) * 30), key=f"{nested_key}_table")
            elif isinstance(value, dict):
                with st.expander(label, expanded=expanded):
                    smart_json(
                        value,
                        title=label,
                        expanded=False,
                        download_name=download_name,
                        key=nested_key,
                    )
            else:
                with st.expander(label, expanded=expanded):
                    st.code(json.dumps(value, indent=2, sort_keys=True, default=str), language="json")
    elif isinstance(payload, list) and payload and all(isinstance(item, dict) for item in payload):
        smart_dataframe(payload, key=f"{widget_key}_table")
    else:
        st.code(json.dumps(payload, indent=2, sort_keys=True, default=str), language="json")
    st.download_button(
        "Download structured result",
        data=json.dumps(payload, indent=2, sort_keys=True, default=str),
        file_name=download_name,
        mime="application/json",
        width="stretch",
        key=widget_key,
    )


def filterable_dataframe(
    frame: pd.DataFrame | list[dict[str, Any]],
    *,
    key: str,
    height: int = 460,
    search_columns: list[str] | None = None,
    status_column: str | None = None,
) -> pd.DataFrame:
    """Add compact search/status controls before rendering a professional dataframe."""
    data = pd.DataFrame(frame)
    if data.empty:
        st.info("No records match the current filters.")
        return data
    controls = st.columns([2, 1]) if status_column and status_column in data.columns else [st.container()]
    query = controls[0].text_input("Search records", key=f"{key}_query", placeholder="Type to filter this table")
    selected_status = None
    if status_column and status_column in data.columns:
        choices = ["All", *sorted({str(value) for value in data[status_column].dropna().unique()})]
        selected_status = controls[1].selectbox("Status", choices, key=f"{key}_status")
    filtered = data
    if query.strip():
        columns = [column for column in (search_columns or list(data.columns)) if column in data.columns]
        mask = pd.Series(False, index=data.index)
        for column in columns:
            mask |= data[column].astype(str).str.contains(query.strip(), case=False, na=False, regex=False)
        filtered = filtered[mask]
    if selected_status and selected_status != "All":
        filtered = filtered[filtered[status_column].astype(str) == selected_status]
    st.caption(f"Showing {len(filtered):,} of {len(data):,} records")
    smart_dataframe(filtered, height=height, key=f"{key}_table")
    return filtered

def source_badges(items: Iterable[tuple[str, str]]) -> None:
    chips = "".join(
        f'<span class="bio-source-chip"><b>{html.escape(label)}</b> {html.escape(value)}</span>'
        for label, value in items
    )
    st.markdown(f'<div class="bio-source-row">{chips}</div>', unsafe_allow_html=True)


def scientific_table(
    frame: pd.DataFrame | list[dict[str, Any]],
    *,
    key: str,
    title: str | None = None,
    search_columns: list[str] | None = None,
    status_column: str | None = None,
    selectable: bool = False,
    height: int = 480,
    file_name: str = "biointel_table.csv",
) -> pd.DataFrame:
    """Standard researcher-facing table with filtering, selection and export."""
    data = pd.DataFrame(frame)
    if title:
        st.subheader(title)
    if data.empty:
        st.info("No records are available for this view.")
        return data
    left, middle, right = st.columns([1.8, 1.0, 0.8], gap="small")
    query = left.text_input("Search", key=f"{key}_search", placeholder="Search visible records")
    status = "All"
    if status_column and status_column in data.columns:
        values = sorted({str(value) for value in data[status_column].dropna().unique()})
        status = middle.selectbox("Status", ["All", *values], key=f"{key}_status")
    else:
        middle.caption(f"{len(data):,} records")
    filtered = data.copy()
    if query.strip():
        cols = [c for c in (search_columns or list(filtered.columns)) if c in filtered.columns]
        mask = pd.Series(False, index=filtered.index)
        for column in cols:
            mask |= filtered[column].astype(str).str.contains(query.strip(), case=False, na=False, regex=False)
        filtered = filtered.loc[mask]
    if status != "All":
        filtered = filtered.loc[filtered[status_column].astype(str) == status]
    right.download_button(
        "Export CSV",
        filtered.to_csv(index=False).encode("utf-8"),
        file_name=file_name,
        mime="text/csv",
        width="stretch",
        key=f"{key}_export",
    )
    st.caption(f"Showing {len(filtered):,} of {len(data):,} records")
    if selectable:
        event = st.dataframe(
            filtered,
            width="stretch",
            height=height,
            hide_index=True,
            on_select="rerun",
            selection_mode="multi-row",
            key=f"{key}_selectable",
        )
        rows = list(getattr(getattr(event, "selection", None), "rows", []) or [])
        selected = filtered.iloc[rows] if rows else filtered.iloc[0:0]
        if not selected.empty:
            st.download_button(
                f"Export selected ({len(selected)})",
                selected.to_csv(index=False).encode("utf-8"),
                file_name=file_name.replace(".csv", "_selected.csv"),
                mime="text/csv",
                key=f"{key}_selected_export",
            )
        return selected
    smart_dataframe(filtered, height=height, key=f"{key}_table")
    return filtered


def scientific_chart_card(
    figure: Any,
    *,
    title: str,
    interpretation: str,
    data: pd.DataFrame | list[dict[str, Any]] | None = None,
    method: str | None = None,
    units: str | None = None,
    key: str,
    module_key: str | None = None,
    evidence_status: str | None = None,
    statistics: Mapping[str, Any] | None = None,
    source_record_count: int | None = None,
    aggregation_note: str | None = None,
    configuration: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Render a consistent, accessible and reproducible scientific visual card.

    The wrapper adds evidence labelling, accessibility presets, linked point-to-table
    selection, statistical context, persistent annotations/saved views and a complete
    visual report bundle.  Existing callers remain compatible because all new arguments
    are optional.
    """
    from biointel.ui.visual_workspace import (
        ACCESSIBILITY_PRESETS,
        apply_accessibility_preset,
        build_visual_report_bundle,
        evidence_label,
        infer_evidence_status,
        list_annotations,
        list_views,
        record_visual_error,
        save_annotation,
        save_view,
        visual_text_summary,
    )

    table = pd.DataFrame() if data is None else pd.DataFrame(data).reset_index(drop=True)

    # A blank Plotly canvas looks like a rendering failure and previously let
    # oversized placeholder/help glyphs dominate the page. Preserve the data,
    # but convert truly empty figures into an explicit bounded no-data state.
    figure_empty = False
    try:
        traces = tuple(getattr(figure, "data", ()) or ())
        layout = getattr(figure, "layout", None)
        annotations = tuple(getattr(layout, "annotations", ()) or ()) if layout is not None else ()
        images = tuple(getattr(layout, "images", ()) or ()) if layout is not None else ()
        shapes = tuple(getattr(layout, "shapes", ()) or ()) if layout is not None else ()
        figure_empty = not bool(traces or annotations or images or shapes)
    except Exception:
        figure_empty = figure is None
    if figure_empty:
        import plotly.graph_objects as go

        fallback = go.Figure()
        fallback.add_annotation(
            text=(
                "No plottable chart data is available for the current selection. "
                "The underlying records remain visible below."
                if not table.empty
                else "No plottable data is available for the current selection."
            ),
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            align="center",
            font={"size": 15},
        )
        fallback.update_layout(
            height=300,
            margin={"l": 24, "r": 24, "t": 28, "b": 24},
            xaxis={"visible": False},
            yaxis={"visible": False},
        )
        figure = fallback

    module = str(module_key or current_page_key_safe() or "global")
    resolved_evidence = infer_evidence_status(table, evidence_status)
    st.markdown(f"### {title}")
    badge_label = evidence_label(resolved_evidence)
    badge_tone = (
        "#047857" if resolved_evidence in {"external_validation", "prospective_validation"}
        else "#0369A1" if resolved_evidence in {"real_imported", "internal_validation"}
        else "#92400E"
    )
    st.markdown(
        f'<span style="display:inline-flex;align-items:center;padding:.2rem .55rem;border-radius:999px;'
        f'font-size:.76rem;font-weight:700;background:{badge_tone}22;border:1px solid {badge_tone}88;">'
        f'{html.escape(badge_label)}</span>',
        unsafe_allow_html=True,
    )
    st.caption(interpretation)
    if figure_empty:
        st.warning(
            "This view has no drawable traces for the current state. "
            "No records were discarded; inspect the automatically opened data table below."
        )
    metadata = [value for value in (method, units) if value]
    if metadata:
        st.markdown(" · ".join(f"`{value}`" for value in metadata))

    controls = st.columns([1.35, 1.0, 1.0], gap="small")
    preset = controls[0].selectbox(
        "Visual accessibility",
        ACCESSIBILITY_PRESETS,
        key=f"{key}_accessibility",
        help="Choose a high-contrast, colour-blind-safe or print-friendly rendering without changing the analysis.",
    )
    show_summary = controls[1].toggle("Text summary", value=True, key=f"{key}_summary_toggle")
    linked_selection = controls[2].toggle("Linked selection", value=True, key=f"{key}_linked_toggle")

    accessible_figure = apply_accessibility_preset(figure, preset)
    selected_rows: list[int] = []
    try:
        plot_args = dict(
            width="stretch",
            key=f"{key}_plot",
            config={
                "displaylogo": False,
                "responsive": True,
                "toImageButtonOptions": {"format": "svg", "filename": key, "scale": 2},
                "modeBarButtonsToAdd": ["drawline", "drawopenpath", "eraseshape"],
            },
        )
        if linked_selection:
            try:
                event = st.plotly_chart(
                    accessible_figure,
                    on_select="rerun",
                    selection_mode=("points", "box", "lasso"),
                    **plot_args,
                )
            except TypeError:  # Compatibility with older Streamlit builds.
                event = None
                st.plotly_chart(accessible_figure, **plot_args)
            selection = getattr(event, "selection", None)
            points = list(getattr(selection, "points", []) or [])
            parsed_indices: set[int] = set()
            for point in points:
                if not isinstance(point, dict):
                    continue
                raw_index = point.get("point_index", point.get("pointIndex"))
                try:
                    index_value = int(raw_index)
                except (TypeError, ValueError):
                    continue
                if index_value >= 0:
                    parsed_indices.add(index_value)
            selected_rows = sorted(parsed_indices)
        else:
            st.plotly_chart(accessible_figure, **plot_args)
    except Exception as exc:
        error_id = record_visual_error(module_key=module, chart_key=key, error=exc)
        st.error(f"This visual could not be rendered safely. Error ID: {error_id}")
        with st.expander("Recovery options", expanded=False):
            st.caption("Retry the page, switch the accessibility preset, or download the diagnostic record for support.")
            st.download_button(
                "Download visual diagnostic",
                data=json.dumps({
                    "error_id": error_id,
                    "module": module,
                    "chart": key,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(limit=8),
                }, indent=2),
                file_name=f"{error_id}.json",
                mime="application/json",
                key=f"{key}_error_download",
            )
        return table.iloc[0:0]

    if show_summary:
        st.info(visual_text_summary(table, title))

    # Step 131: uncertainty-native context and deterministic visual fingerprinting.
    try:
        from biointel.nextgen.interaction_v131 import (
            uncertainty_profile, visual_fingerprint, save_visual_fingerprint,
        )
        uncertainty = uncertainty_profile(table)
        if not uncertainty.empty:
            with st.expander("Uncertainty intervals", expanded=False):
                st.caption("Detected estimate/lower/upper interval groups are validated before publication use.")
                smart_dataframe(uncertainty, height=min(320, 90 + 36 * len(uncertainty)), key=f"{key}_uncertainty_profile")
        fingerprint = visual_fingerprint(accessible_figure, table, title=title)
        project_root = Path(__file__).resolve().parents[3]
        save_visual_fingerprint(
            project_root=project_root, module_key=module, chart_key=key, fingerprint=fingerprint,
            metadata={"title": title, "evidence_status": resolved_evidence, "rows": len(table), "preset": preset},
        )
    except Exception:
        # Fingerprinting and interval diagnostics must never interrupt visual rendering.
        pass

    displayed_count = len(table)
    total_count = max(displayed_count, int(source_record_count or displayed_count))
    if total_count > displayed_count:
        note = aggregation_note or "bounded/downsampled visual data"
        st.warning(
            f"Showing {displayed_count:,} of {total_count:,} source record(s) · {note}. "
            "Download the complete analysis output from the module export workspace."
        )

    from biointel.statistics.rigor import infer_visual_statistics

    stat_items: dict[str, Any] = {
        "Displayed n": displayed_count,
        "Evidence": badge_label,
    }
    if source_record_count is not None:
        stat_items["Source n"] = int(source_record_count)
    try:
        inferred_statistics = infer_visual_statistics(table, source_count=source_record_count)
    except Exception:
        inferred_statistics = {
            "Displayed rows": displayed_count,
            "Source rows": int(source_record_count or displayed_count),
            "Statistical footer": "Unavailable for one or more complex nested fields",
        }
    stat_items.update({str(field): value for field, value in inferred_statistics.items() if value not in (None, "")})
    if statistics:
        stat_items.update({str(field): value for field, value in statistics.items() if value not in (None, "")})
    with st.expander("Statistical context and provenance", expanded=False):
        rows = [{"Field": field, "Value": value} for field, value in stat_items.items()]
        if method:
            rows.append({"Field": "Method", "Value": method})
        if units:
            rows.append({"Field": "Units", "Value": units})
        smart_dataframe(rows, height=min(420, 90 + 34 * len(rows)), key=f"{key}_stats")

    selected = table.iloc[[index for index in selected_rows if index < len(table)]] if selected_rows else table.iloc[0:0]
    if linked_selection and selected_rows:
        st.success(f"Linked selection: {len(selected):,} underlying record(s) selected.")
        try:
            from biointel.ui.visual_workspace import publish_linked_selection
            context = publish_linked_selection(module, selected, source_chart=key)
            if context:
                st.caption(
                    f"Published linked context: {context['column']} = "
                    f"{', '.join(map(str, context['values'][:5]))}{'…' if len(context['values']) > 5 else ''}"
                )
        except Exception:
            # Visual selection must never interrupt scientific result rendering.
            pass

    if not table.empty:
        with st.expander("View underlying data", expanded=figure_empty):
            visible = selected if not selected.empty else table
            if not selected.empty:
                st.caption("The table is filtered to points selected in the chart.")
            smart_dataframe(visible, key=f"{key}_data")
            st.download_button(
                "Download selected chart data" if not selected.empty else "Download chart data",
                visible.to_csv(index=False).encode("utf-8"),
                file_name=f"{key}_{'selected_' if not selected.empty else ''}chart_data.csv",
                mime="text/csv",
                key=f"{key}_download",
            )

    with st.expander("Save, annotate and report", expanded=False):
        view_name = st.text_input("Saved view name", value=title, key=f"{key}_view_name")
        annotation = st.text_area(
            "Annotation",
            placeholder="Record a threshold, candidate decision, QC observation or reviewer comment.",
            key=f"{key}_annotation",
        )
        action_columns = st.columns(3)
        if action_columns[0].button("Save view", key=f"{key}_save_view", width="stretch"):
            view_id = save_view(
                name=view_name.strip() or title,
                module_key=module,
                chart_key=key,
                title=title,
                evidence_status=resolved_evidence,
                configuration={
                    "accessibility_preset": preset,
                    "selected_rows": selected_rows,
                    "method": method,
                    "units": units,
                    **dict(configuration or {}),
                },
            )
            st.success(f"Saved visual workspace: {view_id}")
        if action_columns[1].button("Save annotation", key=f"{key}_save_annotation", width="stretch"):
            if annotation.strip():
                annotation_id = save_annotation(
                    module_key=module,
                    chart_key=key,
                    visual_title=title,
                    note=annotation.strip(),
                    selected_rows=selected_rows,
                )
                st.success(f"Annotation saved: {annotation_id}")
            else:
                st.warning("Enter an annotation before saving.")
        if action_columns[2].button("Prepare report bundle", key=f"{key}_prepare_report", width="stretch"):
            with st.spinner("Generating PDF, DOCX, PPTX, interactive HTML and data bundle…"):
                st.session_state[f"{key}_report_bundle"] = build_visual_report_bundle(
                    title=title,
                    interpretation=interpretation,
                    method=method,
                    units=units,
                    evidence_status=resolved_evidence,
                    figure=accessible_figure,
                    data=selected if not selected.empty else table,
                    configuration={"module_key": module, "chart_key": key, "preset": preset, **dict(configuration or {})},
                )
        bundle = st.session_state.get(f"{key}_report_bundle")
        if bundle:
            st.download_button(
                "Download complete visual report ZIP",
                data=bundle,
                file_name=f"{key}_visual_report.zip",
                mime="application/zip",
                key=f"{key}_report_download",
                width="stretch",
            )
        saved = list_views(module)
        annotations = list_annotations(module, key)
        if not saved.empty:
            st.markdown("**Saved views**")
            smart_dataframe(saved.drop(columns=["configuration_json"], errors="ignore"), height=220, key=f"{key}_saved_views")
        if not annotations.empty:
            st.markdown("**Saved annotations**")
            smart_dataframe(annotations, height=220, key=f"{key}_saved_annotations")
    return selected


def current_page_key_safe() -> str | None:
    """Resolve the active page without importing the theme module at import time."""
    try:
        from biointel.ui.theme import current_page_key
        return current_page_key()
    except Exception:
        return None


def recovery_actions(
    *,
    key: str,
    retry_label: str = "Retry",
    reset_label: str = "Reset parameters",
    failed_rows: pd.DataFrame | None = None,
) -> str | None:
    """Reusable recovery controls for failed or blocked workflows."""
    columns = st.columns(3 if failed_rows is not None and not failed_rows.empty else 2)
    if columns[0].button(retry_label, width="stretch", key=f"{key}_retry"):
        return "retry"
    if columns[1].button(reset_label, width="stretch", key=f"{key}_reset"):
        return "reset"
    if failed_rows is not None and not failed_rows.empty:
        columns[2].download_button(
            "Download failed rows",
            failed_rows.to_csv(index=False).encode("utf-8"),
            file_name=f"{key}_failed_rows.csv",
            mime="text/csv",
            width="stretch",
            key=f"{key}_failed_download",
        )
    return None


def set_workspace_context(**values: Any) -> None:
    """Set cross-page project/dataset/model/target context for workflow handoff."""
    mapping = {
        "project": "active_project_name",
        "dataset": "active_dataset_name",
        "model": "active_model_name",
        "target": "active_target_name",
    }
    for field, value in values.items():
        state_key = mapping.get(field)
        if state_key and value not in (None, ""):
            st.session_state[state_key] = str(value)


def notify(
    title: str,
    message: str,
    *,
    level: str = "info",
    source: str = "application",
    action_label: str = "",
    action_target: str = "",
    dedupe_key: str = "",
    toast: bool = False,
) -> None:
    """Create a durable scientific notification and a session fallback.

    The persistent store survives page navigation and desktop restarts. The
    session copy keeps older pages/tests compatible when the user-data folder
    is temporarily unavailable.
    """

    page_key = str(st.session_state.get("_bio_active_page_key", "") or "")
    item = {
        "title": str(title),
        "message": str(message),
        "level": str(level),
        "source": str(source),
        "page_key": page_key,
        "action_label": str(action_label),
        "action_target": str(action_target),
    }
    items = list(st.session_state.get("_bio_notifications", []))
    signature = dedupe_key or "|".join((str(source), str(title), str(message), page_key, str(action_target)))
    item["dedupe_key"] = signature
    items = [existing for existing in items if str(existing.get("dedupe_key", "")) != signature]
    items.insert(0, item)
    st.session_state["_bio_notifications"] = items[:50]
    try:
        from biointel.ui.live_experience import get_live_store

        get_live_store().notify(
            title,
            message,
            level=level,
            source=source,
            page_key=page_key,
            action_label=action_label,
            action_target=action_target,
            dedupe_key=signature,
        )
    except Exception:
        # Notifications must never interrupt a scientific workflow.
        pass
    if toast and hasattr(st, "toast"):
        icon = {"success": "✅", "warning": "⚠️", "error": "❌", "critical": "🚨"}.get(level, "ℹ️")
        st.toast(f"{title}: {message}", icon=icon)
