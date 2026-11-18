from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from biointel.nextgen.interaction_v131 import progressive_sample


@dataclass(frozen=True)
class ScientificVisual:
    title: str
    interpretation: str
    method: str
    figure: Any
    data: pd.DataFrame


def _frame(value: Any) -> pd.DataFrame:
    if value is None:
        return pd.DataFrame()
    if isinstance(value, pd.DataFrame):
        return value.copy()
    try:
        return pd.DataFrame(value)
    except Exception:
        return pd.DataFrame()


def _clean_numeric(frame: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    out = frame.copy()
    for column in columns:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    return out


def _first_existing(frame: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    return next((column for column in candidates if column in frame.columns), None)


def _safe_log10(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").clip(lower=1e-300, upper=1)
    return -np.log10(values)


def _top(frame: pd.DataFrame, score: str, count: int = 30, ascending: bool = False) -> pd.DataFrame:
    if score not in frame.columns:
        return frame.head(count).copy()
    out = frame.copy()
    out[score] = pd.to_numeric(out[score], errors="coerce")
    return out.sort_values(score, ascending=ascending, na_position="last").head(count)


def _scatter(
    frame: pd.DataFrame,
    *,
    x: str,
    y: str,
    title: str,
    interpretation: str,
    method: str,
    color: str | None = None,
    size: str | None = None,
    hover: list[str] | None = None,
    log_x: bool = False,
    log_y: bool = False,
) -> ScientificVisual | None:
    if frame.empty or x not in frame.columns or y not in frame.columns:
        return None
    source = _clean_numeric(frame, [x, y, *( [size] if size else [])]).dropna(subset=[x, y])
    data, _manifest = progressive_sample(source, limit=8000, score_column=size if size else y)
    if data.empty:
        return None
    kwargs: dict[str, Any] = {
        "x": x, "y": y, "title": title, "opacity": 0.78, "log_x": log_x, "log_y": log_y,
        "render_mode": "webgl",
    }
    if color and color in data.columns:
        kwargs["color"] = color
    if size and size in data.columns and pd.to_numeric(data[size], errors="coerce").notna().any():
        size_key = size
        numeric_size = pd.to_numeric(data[size], errors="coerce").abs().fillna(0.0)
        if float(numeric_size.max()) <= 0:
            numeric_size = pd.Series(1.0, index=data.index)
        if (numeric_size != pd.to_numeric(data[size], errors="coerce")).any():
            size_key = f"__size_{size}"
            data[size_key] = numeric_size
        kwargs["size"] = size_key
    hover_fields = [column for column in (hover or []) if column in data.columns]
    if hover_fields:
        kwargs["hover_data"] = hover_fields
    fig = px.scatter(data, **kwargs)
    fig.update_layout(legend_title_text=(color or "").replace("_", " ").title())
    return ScientificVisual(title, interpretation, method, fig, data)


def _line(
    frame: pd.DataFrame,
    *,
    x: str,
    y: str,
    title: str,
    interpretation: str,
    method: str,
    color: str | None = None,
    group: str | None = None,
    markers: bool = True,
) -> ScientificVisual | None:
    if frame.empty or x not in frame.columns or y not in frame.columns:
        return None
    data = _clean_numeric(frame, [x, y]).dropna(subset=[x, y]).sort_values(x).head(12000)
    if data.empty:
        return None
    kwargs: dict[str, Any] = {"x": x, "y": y, "markers": markers, "title": title}
    if color and color in data.columns:
        kwargs["color"] = color
    if group and group in data.columns:
        kwargs["line_group"] = group
    fig = px.line(data, **kwargs)
    return ScientificVisual(title, interpretation, method, fig, data)


def _histogram(
    frame: pd.DataFrame,
    *,
    x: str,
    title: str,
    interpretation: str,
    method: str,
    color: str | None = None,
    nbins: int = 32,
) -> ScientificVisual | None:
    if frame.empty or x not in frame.columns:
        return None
    data = _clean_numeric(frame, [x]).dropna(subset=[x]).head(20000)
    if data.empty:
        return None
    kwargs: dict[str, Any] = {"x": x, "nbins": nbins, "title": title, "marginal": "box"}
    if color and color in data.columns and data[color].nunique(dropna=True) <= 20:
        kwargs["color"] = color
    fig = px.histogram(data, **kwargs)
    return ScientificVisual(title, interpretation, method, fig, data)


def _box(
    frame: pd.DataFrame,
    *,
    x: str,
    y: str,
    title: str,
    interpretation: str,
    method: str,
    color: str | None = None,
) -> ScientificVisual | None:
    if frame.empty or x not in frame.columns or y not in frame.columns:
        return None
    data = _clean_numeric(frame, [y]).dropna(subset=[y]).head(12000)
    if data.empty:
        return None
    kwargs: dict[str, Any] = {"x": x, "y": y, "points": "outliers", "title": title}
    if color and color in data.columns:
        kwargs["color"] = color
    fig = px.box(data, **kwargs)
    return ScientificVisual(title, interpretation, method, fig, data)


def _bar(
    frame: pd.DataFrame,
    *,
    x: str,
    y: str,
    title: str,
    interpretation: str,
    method: str,
    color: str | None = None,
    orientation: str = "v",
    top_n: int = 30,
    ascending: bool = False,
) -> ScientificVisual | None:
    if frame.empty or x not in frame.columns or y not in frame.columns:
        return None
    data = _clean_numeric(frame, [y]).dropna(subset=[y]).sort_values(y, ascending=ascending).head(top_n)
    if data.empty:
        return None
    kwargs: dict[str, Any] = {"x": x, "y": y, "title": title, "orientation": orientation}
    if color and color in data.columns:
        kwargs["color"] = color
    fig = px.bar(data, **kwargs)
    return ScientificVisual(title, interpretation, method, fig, data)


def _group_bar(
    frame: pd.DataFrame,
    *,
    category: str,
    value: str,
    title: str,
    interpretation: str,
    method: str,
    agg: str = "mean",
    color: str | None = None,
    top_n: int = 25,
) -> ScientificVisual | None:
    if frame.empty or category not in frame.columns or value not in frame.columns:
        return None
    data = frame.copy()
    group_cols = [category] + ([color] if color and color in data.columns else [])
    if agg == "count":
        data = data.dropna(subset=[category])
        grouped = data.groupby(group_cols, as_index=False, observed=True).size().rename(columns={"size": value})
    else:
        data = _clean_numeric(data, [value]).dropna(subset=[value])
        if agg == "sum":
            grouped = data.groupby(group_cols, as_index=False, observed=True)[value].sum()
        else:
            grouped = data.groupby(group_cols, as_index=False, observed=True)[value].mean()
    grouped = grouped.sort_values(value, ascending=False).head(top_n)
    kwargs: dict[str, Any] = {"x": category, "y": value, "title": title}
    if color and color in grouped.columns:
        kwargs["color"] = color
    fig = px.bar(grouped, **kwargs)
    return ScientificVisual(title, interpretation, method, fig, grouped)


def _heatmap(
    frame: pd.DataFrame,
    *,
    row: str,
    column: str,
    value: str,
    title: str,
    interpretation: str,
    method: str,
    agg: str = "mean",
    max_rows: int = 35,
    max_columns: int = 30,
) -> ScientificVisual | None:
    if frame.empty or not {row, column, value}.issubset(frame.columns):
        return None
    data = _clean_numeric(frame, [value]).dropna(subset=[value])
    if data.empty:
        return None
    pivot = data.pivot_table(index=row, columns=column, values=value, aggfunc=agg)
    if pivot.empty:
        return None
    if len(pivot) > max_rows:
        keep_rows = pivot.abs().mean(axis=1).sort_values(ascending=False).head(max_rows).index
        pivot = pivot.loc[keep_rows]
    if len(pivot.columns) > max_columns:
        keep_cols = pivot.abs().mean(axis=0).sort_values(ascending=False).head(max_columns).index
        pivot = pivot[keep_cols]
    fig = px.imshow(pivot, aspect="auto", title=title, labels={"x": column, "y": row, "color": value})
    plot_data = pivot.reset_index().melt(id_vars=row, var_name=column, value_name=value)
    return ScientificVisual(title, interpretation, method, fig, plot_data)


def _correlation_heatmap(
    frame: pd.DataFrame,
    *,
    columns: list[str],
    title: str,
    interpretation: str,
    method: str,
) -> ScientificVisual | None:
    valid = [column for column in columns if column in frame.columns]
    if len(valid) < 2:
        return None
    data = frame[valid].apply(pd.to_numeric, errors="coerce")
    corr = data.corr(min_periods=3)
    if corr.empty:
        return None
    fig = px.imshow(corr, zmin=-1, zmax=1, color_continuous_midpoint=0, text_auto=".2f", title=title)
    plot_data = corr.reset_index(names="feature").melt(id_vars="feature", var_name="paired_feature", value_name="correlation")
    return ScientificVisual(title, interpretation, method, fig, plot_data)


def _radar(
    frame: pd.DataFrame,
    *,
    label: str,
    metrics: list[str],
    title: str,
    interpretation: str,
    method: str,
    top_n: int = 5,
    ranking: str | None = None,
) -> ScientificVisual | None:
    valid = [metric for metric in metrics if metric in frame.columns]
    if not valid or label not in frame.columns or frame.empty:
        return None
    data = frame.copy()
    for metric in valid:
        data[metric] = pd.to_numeric(data[metric], errors="coerce")
        low, high = data[metric].min(), data[metric].max()
        data[f"__norm_{metric}"] = 0.5 if not np.isfinite(low) or not np.isfinite(high) or high == low else (data[metric] - low) / (high - low)
    if ranking and ranking in data.columns:
        data = _top(data, ranking, top_n)
    else:
        data = data.head(top_n)
    fig = go.Figure()
    rows: list[dict[str, Any]] = []
    for _, record in data.iterrows():
        values = [float(record.get(f"__norm_{metric}", 0) or 0) for metric in valid]
        values.append(values[0])
        theta = [metric.replace("_", " ").title() for metric in valid]
        theta.append(theta[0])
        name = str(record[label])
        fig.add_trace(go.Scatterpolar(r=values, theta=theta, fill="toself", name=name, opacity=0.55))
        for metric, value in zip(valid, values[:-1]):
            rows.append({"candidate": name, "metric": metric, "normalized_value": value})
    fig.update_layout(title=title, polar={"radialaxis": {"visible": True, "range": [0, 1]}}, legend={"orientation": "h"})
    return ScientificVisual(title, interpretation, method, fig, pd.DataFrame(rows))


def _manhattan(frame: pd.DataFrame, *, title: str, interpretation: str, method: str) -> ScientificVisual | None:
    if frame.empty or not {"chrom", "position", "p_value"}.issubset(frame.columns):
        return None
    data = _clean_numeric(frame, ["position", "p_value"]).dropna(subset=["position", "p_value"]).copy()
    if data.empty:
        return None
    data["minus_log10_p"] = _safe_log10(data["p_value"])
    chromosomes = list(dict.fromkeys(data["chrom"].astype(str).tolist()))
    offsets: dict[str, float] = {}
    cursor = 0.0
    ticks: list[float] = []
    labels: list[str] = []
    for chrom in chromosomes:
        subset = data[data["chrom"].astype(str) == chrom]
        offsets[chrom] = cursor
        maximum = float(subset["position"].max()) if not subset.empty else 0.0
        ticks.append(cursor + maximum / 2)
        labels.append(chrom)
        cursor += maximum + max(maximum * 0.04, 1.0)
    data["genome_position"] = data.apply(lambda row: float(row["position"]) + offsets[str(row["chrom"])], axis=1)
    fig = px.scatter(data, x="genome_position", y="minus_log10_p", color=data["chrom"].astype(str), hover_data=[column for column in ["variant", "effect", "maf", "q_value"] if column in data.columns], title=title)
    fig.update_xaxes(tickmode="array", tickvals=ticks, ticktext=labels, title="Chromosome")
    fig.add_hline(y=-np.log10(5e-8), line_dash="dash", annotation_text="Genome-wide threshold")
    return ScientificVisual(title, interpretation, method, fig, data)


def _roc(frame: pd.DataFrame, *, title: str, interpretation: str, method: str) -> ScientificVisual | None:
    fpr = _first_existing(frame, ["false_positive_rate", "fpr"])
    tpr = _first_existing(frame, ["true_positive_rate", "sensitivity", "recall"])
    if not fpr or not tpr:
        return None
    data = _clean_numeric(frame, [fpr, tpr]).dropna(subset=[fpr, tpr]).sort_values(fpr)
    if data.empty:
        return None
    fig = px.line(data, x=fpr, y=tpr, markers=True, title=title)
    fig.add_shape(type="line", x0=0, y0=0, x1=1, y1=1, line={"dash": "dash"})
    fig.update_xaxes(range=[0, 1]); fig.update_yaxes(range=[0, 1])
    return ScientificVisual(title, interpretation, method, fig, data)


def _survival(frame: pd.DataFrame, *, title: str, interpretation: str, method: str) -> ScientificVisual | None:
    if frame.empty or not {"time", "survival"}.issubset(frame.columns):
        return None
    data = _clean_numeric(frame, ["time", "survival"]).dropna(subset=["time", "survival"])
    color = _first_existing(data, ["biomarker_group", "arm", "group"])
    group_columns = [column for column in ["arm", "biomarker_group"] if column in data.columns]
    if len(group_columns) > 1:
        data["stratum"] = data[group_columns].astype(str).agg(" · ".join, axis=1)
        color = "stratum"
    fig = px.line(data.sort_values("time"), x="time", y="survival", color=color, line_shape="hv", title=title)
    fig.update_yaxes(range=[0, 1])
    return ScientificVisual(title, interpretation, method, fig, data)


def _network(
    frame: pd.DataFrame,
    *,
    source: str,
    target: str,
    weight: str | None,
    title: str,
    interpretation: str,
    method: str,
    max_edges: int = 80,
) -> ScientificVisual | None:
    if frame.empty or source not in frame.columns or target not in frame.columns:
        return None
    data = frame[[source, target] + ([weight] if weight and weight in frame.columns else [])].dropna().head(max_edges).copy()
    if data.empty:
        return None
    nodes = list(dict.fromkeys(data[source].astype(str).tolist() + data[target].astype(str).tolist()))
    angles = np.linspace(0, 2 * np.pi, len(nodes), endpoint=False)
    positions = {node: (float(np.cos(angle)), float(np.sin(angle))) for node, angle in zip(nodes, angles)}
    edge_x: list[float | None] = []
    edge_y: list[float | None] = []
    for _, row in data.iterrows():
        x0, y0 = positions[str(row[source])]; x1, y1 = positions[str(row[target])]
        edge_x.extend([x0, x1, None]); edge_y.extend([y0, y1, None])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=edge_x, y=edge_y, mode="lines", line={"width": 0.8}, hoverinfo="none", name="Interactions"))
    fig.add_trace(go.Scatter(x=[positions[node][0] for node in nodes], y=[positions[node][1] for node in nodes], text=nodes, mode="markers+text", textposition="top center", marker={"size": 12}, name="Nodes"))
    fig.update_layout(title=title, showlegend=False, xaxis={"visible": False}, yaxis={"visible": False})
    return ScientificVisual(title, interpretation, method, fig, data)


def _spatial(frame: pd.DataFrame, *, title: str, interpretation: str, method: str) -> ScientificVisual | None:
    if frame.empty or not {"x", "y"}.issubset(frame.columns):
        return None
    value = _first_existing(frame, ["expression", "priority_score", "regional_enrichment"])
    color = value or _first_existing(frame, ["region", "cluster", "condition"])
    kwargs: dict[str, Any] = {"x": "x", "y": "y", "title": title}
    if color:
        kwargs["color"] = color
    hover = [column for column in ["spot", "gene", "region"] if column in frame.columns]
    if hover:
        kwargs["hover_data"] = hover
    data = frame.head(15000).copy()
    fig = px.scatter(data, **kwargs)
    fig.update_yaxes(autorange="reversed", scaleanchor="x", scaleratio=1)
    return ScientificVisual(title, interpretation, method, fig, data)


def _waterfall(
    frame: pd.DataFrame,
    *,
    label: str,
    value: str,
    title: str,
    interpretation: str,
    method: str,
    top_n: int = 25,
) -> ScientificVisual | None:
    if frame.empty or label not in frame.columns or value not in frame.columns:
        return None
    data = _clean_numeric(frame, [value]).dropna(subset=[value]).sort_values(value).tail(top_n)
    if data.empty:
        return None
    fig = go.Figure(go.Waterfall(x=data[label].astype(str), y=data[value], measure=["relative"] * len(data)))
    fig.update_layout(title=title, xaxis_title=label.replace("_", " ").title(), yaxis_title=value.replace("_", " ").title())
    return ScientificVisual(title, interpretation, method, fig, data)


def _visuals_for_expansion(
    key: str,
    data: pd.DataFrame,
    result: pd.DataFrame,
    secondary: pd.DataFrame,
    extras: Mapping[str, pd.DataFrame],
) -> list[ScientificVisual | None]:
    from .scientific_visual_domain import _visuals_for_expansion as implementation
    return implementation(key, data, result, secondary, extras)


def _visuals_for_nextgen(
    key: str,
    data: pd.DataFrame,
    result: pd.DataFrame,
    secondary: pd.DataFrame,
    extras: Mapping[str, pd.DataFrame],
) -> list[ScientificVisual | None]:
    from .scientific_visual_domain import _visuals_for_nextgen as implementation
    return implementation(key, data, result, secondary, extras)


def _category_count_visual(frame: pd.DataFrame, column: str) -> ScientificVisual | None:
    if frame.empty or column not in frame.columns:
        return None
    data = frame[column].fillna("Missing").astype(str).value_counts().head(30).rename_axis(column).reset_index(name="records")
    if data.empty:
        return None
    fig = px.bar(data, x=column, y="records", title=f"{column.replace('_', ' ').title()} composition")
    return ScientificVisual(
        f"{column.replace('_', ' ').title()} composition",
        "Shows the record distribution across the main categorical field.",
        "Category-frequency summary",
        fig,
        data,
    )


def _missingness_visual(frame: pd.DataFrame) -> ScientificVisual | None:
    if frame.empty:
        return None
    data = pd.DataFrame({
        "column": frame.columns.astype(str),
        "missing_values": [int(frame[column].isna().sum()) for column in frame.columns],
        "missing_percent": [100.0 * float(frame[column].isna().mean()) for column in frame.columns],
    }).sort_values("missing_percent", ascending=False).head(40)
    fig = px.bar(data, x="column", y="missing_percent", title="Column missingness profile")
    return ScientificVisual(
        "Column missingness profile",
        "Highlights fields requiring mapping, imputation or source-data repair.",
        "Column-level missing-value audit",
        fig,
        data,
    )


def _row_completeness_visual(frame: pd.DataFrame) -> ScientificVisual | None:
    if frame.empty or len(frame.columns) == 0:
        return None
    data = pd.DataFrame({
        "row": np.arange(1, len(frame) + 1),
        "completeness_percent": 100.0 * (1.0 - frame.isna().mean(axis=1)),
    }).head(20000)
    fig = px.histogram(data, x="completeness_percent", nbins=20, marginal="box", title="Record completeness distribution")
    return ScientificVisual(
        "Record completeness distribution",
        "Shows how consistently required and optional fields are populated across records.",
        "Row-level completeness audit",
        fig,
        data,
    )


def _string_length_visual(frame: pd.DataFrame, column: str) -> ScientificVisual | None:
    if frame.empty or column not in frame.columns:
        return None
    values = frame[column].dropna().astype(str)
    if values.empty:
        return None
    data = pd.DataFrame({"text_length": values.str.len().head(20000)})
    fig = px.histogram(data, x="text_length", nbins=30, marginal="box", title=f"{column.replace('_', ' ').title()} length distribution")
    return ScientificVisual(
        f"{column.replace('_', ' ').title()} length distribution",
        "Shows the size distribution of identifiers or textual records and can expose truncation or malformed values.",
        "String-length quality diagnostic",
        fig,
        data,
    )


def _generic_visuals(data: pd.DataFrame, result: pd.DataFrame, secondary: pd.DataFrame) -> list[ScientificVisual | None]:
    combined = result if not result.empty else data
    numeric = [column for column in combined.columns if pd.api.types.is_numeric_dtype(combined[column])]
    categorical = [column for column in combined.columns if not pd.api.types.is_numeric_dtype(combined[column]) and 1 < combined[column].nunique(dropna=True) <= 40]
    visuals: list[ScientificVisual | None] = []
    if numeric:
        visuals.append(_histogram(combined, x=numeric[0], color=categorical[0] if categorical else None, title=f"{numeric[0].replace('_', ' ').title()} distribution", interpretation="Shows the central tendency, spread and potential outliers.", method="Distribution diagnostic"))
    if len(numeric) >= 2:
        visuals.append(_scatter(combined, x=numeric[0], y=numeric[1], color=categorical[0] if categorical else None, title="Primary numeric relationship", interpretation="Shows the relationship between the first two available numerical measures.", method="Exploratory scatter"))
        visuals.append(_correlation_heatmap(combined, columns=numeric[:8], title="Numeric correlation heatmap", interpretation="Shows linear associations across available numerical measures.", method="Pearson correlation"))
    if categorical and numeric:
        visuals.append(_group_bar(combined, category=categorical[0], value=numeric[0], title="Group comparison", interpretation="Compares average values across the main available category.", method="Group-level aggregation"))
    if categorical:
        visuals.append(_category_count_visual(combined, categorical[0]))
    visuals.append(_missingness_visual(combined))
    visuals.append(_row_completeness_visual(combined))
    if categorical:
        visuals.append(_string_length_visual(combined, categorical[0]))
    if not secondary.empty:
        secondary_numeric = [column for column in secondary.columns if pd.api.types.is_numeric_dtype(secondary[column])]
        secondary_cat = [column for column in secondary.columns if not pd.api.types.is_numeric_dtype(secondary[column])]
        if secondary_numeric and secondary_cat:
            visuals.append(_bar(_top(secondary, secondary_numeric[0]), x=secondary_cat[0], y=secondary_numeric[0], title="Secondary summary ranking", interpretation="Displays the leading grouped results.", method="Secondary-table ranking"))
    return visuals


def build_scientific_visuals(
    module_key: str,
    *,
    data: pd.DataFrame | None,
    result: pd.DataFrame | None,
    secondary: pd.DataFrame | None = None,
    extras: Mapping[str, pd.DataFrame] | None = None,
) -> list[ScientificVisual]:
    source = _frame(data)
    primary = _frame(result)
    grouped = _frame(secondary)
    extra_tables = dict(extras or {})
    if module_key in {
        "epigenomics_chromatin", "metabolomics_lipidomics", "immunoinformatics_vaccine",
        "antibody_biologics", "docking_dynamics", "pharmacogenomics", "spatial_omics_pathology",
        "single_cell_trajectory", "bioimage_microscopy", "biostatistics_design",
        "clinical_trial_biomarker", "genome_editing_safety", "proteogenomics_neoantigen",
        "bioprocess_fermentation", "lims_eln_chain", "causal_perturbation",
        "explainable_ai_assurance", "multiomics_harmonization", "glycomics_glycoproteomics",
        "one_health_environmental", "synthetic_data_privacy",
    }:
        candidates = _visuals_for_expansion(module_key, source, primary, grouped, extra_tables)
    else:
        candidates = _visuals_for_nextgen(module_key, source, primary, grouped, extra_tables)
    visuals = [visual for visual in candidates if visual is not None]
    if len(visuals) < 4:
        for visual in _generic_visuals(source, primary, grouped):
            if visual is not None and visual.title not in {item.title for item in visuals}:
                visuals.append(visual)
            if len(visuals) >= 5:
                break
    return visuals[:5]


def render_scientific_visual_suite(
    module_key: str,
    *,
    data: pd.DataFrame | None,
    result: pd.DataFrame | None,
    secondary: pd.DataFrame | None = None,
    extras: Mapping[str, pd.DataFrame] | None = None,
    key: str,
) -> None:
    import streamlit as st

    from biointel.ui.components import scientific_chart_card

    visuals = build_scientific_visuals(
        module_key,
        data=data,
        result=result,
        secondary=secondary,
        extras=extras,
    )
    if not visuals:
        st.info("No scientifically meaningful visual can be generated from the current columns.")
        return
    st.markdown("#### Scientific visual explorer")
    st.caption(
        f"{len(visuals)} module-specific visuals are available. Single mode renders one chart; "
        "comparison mode is intentionally limited to two charts to protect responsiveness."
    )
    labels = [visual.title for visual in visuals]
    mode = st.radio(
        "Visual layout",
        ["Single visual", "Compare two visuals"],
        horizontal=True,
        key=f"{key}_visual_layout",
    )
    source_count = max(len(_frame(data)), len(_frame(result)), len(_frame(secondary)))
    if mode == "Single visual":
        selected = st.selectbox(
            "Visual",
            labels,
            key=f"{key}_visual_choice",
            help="Switch visuals without rerunning the scientific analysis.",
        )
        index = labels.index(selected)
        visual = visuals[index]
        scientific_chart_card(
            visual.figure,
            title=visual.title,
            interpretation=visual.interpretation,
            data=visual.data,
            method=visual.method,
            key=f"{key}_{index}",
            module_key=module_key,
            source_record_count=source_count,
            aggregation_note="module-specific aggregation or bounded plotting" if source_count > len(visual.data) else None,
            configuration={"visual_index": index, "module_key": module_key},
        )
    else:
        first_col, second_col = st.columns(2, gap="large")
        first = first_col.selectbox("Left visual", labels, key=f"{key}_left_choice")
        second_options = [label for label in labels if label != first] or labels
        second = second_col.selectbox("Right visual", second_options, key=f"{key}_right_choice")
        for container, selected, side in ((first_col, first, "left"), (second_col, second, "right")):
            index = labels.index(selected)
            visual = visuals[index]
            with container:
                scientific_chart_card(
                    visual.figure,
                    title=visual.title,
                    interpretation=visual.interpretation,
                    data=visual.data,
                    method=visual.method,
                    key=f"{key}_{side}_{index}",
                    module_key=module_key,
                    source_record_count=source_count,
                    aggregation_note="module-specific aggregation or bounded plotting" if source_count > len(visual.data) else None,
                    configuration={"visual_index": index, "module_key": module_key, "comparison_side": side},
                )
    with st.expander("Visual catalogue", expanded=False):
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Visual": item.title,
                        "Scientific purpose": item.interpretation,
                        "Method": item.method,
                        "Records": len(item.data),
                    }
                    for item in visuals
                ]
            ),
            width="stretch",
            hide_index=True,
        )


def render_visual_collection(
    visuals: list[ScientificVisual],
    *,
    key: str,
    heading: str = "Scientific visual explorer",
) -> None:
    import streamlit as st

    from biointel.ui.components import scientific_chart_card

    """Render one selected visual from a pre-built collection."""
    unique: list[ScientificVisual] = []
    seen: set[str] = set()
    for visual in visuals:
        if visual.title not in seen:
            unique.append(visual)
            seen.add(visual.title)
    if not unique:
        return
    st.markdown(f"#### {heading}")
    st.caption(f"{len(unique)} responsive visuals are available. Only the selected chart is rendered.")
    labels = [visual.title for visual in unique]
    selected = st.selectbox("Visual", labels, key=f"{key}_choice")
    index = labels.index(selected)
    visual = unique[index]
    scientific_chart_card(
        visual.figure,
        title=visual.title,
        interpretation=visual.interpretation,
        data=visual.data,
        method=visual.method,
        key=f"{key}_{index}",
        module_key=key,
        source_record_count=len(visual.data),
        configuration={"visual_index": index},
    )


def render_generic_visual_explorer(
    frame: pd.DataFrame | None,
    *,
    key: str,
    secondary: pd.DataFrame | None = None,
    heading: str = "Additional visual analytics",
) -> None:
    primary = _frame(frame)
    grouped = _frame(secondary)
    visuals = [visual for visual in _generic_visuals(primary, primary, grouped) if visual is not None]
    render_visual_collection(visuals[:5], key=key, heading=heading)


def build_sequence_alignment_visuals(result: Mapping[str, Any], events: pd.DataFrame | None = None) -> list[ScientificVisual]:
    aligned_query = str(result.get("aligned_query", ""))
    aligned_target = str(result.get("aligned_target", ""))
    n = min(len(aligned_query), len(aligned_target))
    rows: list[dict[str, Any]] = []
    cumulative_identity = 0
    cumulative_gap = 0
    window = 20
    for index in range(n):
        q = aligned_query[index]
        t = aligned_target[index]
        identity = int(q == t and q != "-" and t != "-")
        gap = int(q == "-" or t == "-")
        cumulative_identity += identity
        cumulative_gap += gap
        start = max(0, index - window + 1)
        q_window = aligned_query[start:index + 1]
        t_window = aligned_target[start:index + 1]
        window_identity = sum(1 for a, b in zip(q_window, t_window) if a == b and a != "-") / max(len(q_window), 1)
        rows.append({
            "alignment_position": index + 1,
            "query_symbol": q,
            "target_symbol": t,
            "identity": identity,
            "gap": gap,
            "cumulative_identity_percent": 100 * cumulative_identity / (index + 1),
            "cumulative_gap_percent": 100 * cumulative_gap / (index + 1),
            "window_identity_percent": 100 * window_identity,
            "event": "Gap" if gap else ("Match" if identity else "Mismatch"),
        })
    frame = pd.DataFrame(rows)
    if frame.empty:
        return []
    visuals: list[ScientificVisual | None] = [
        _line(frame, x="alignment_position", y="window_identity_percent", title="Sliding-window identity", interpretation="Shows local conservation changes along the displayed alignment.", method=f"{window}-column rolling identity"),
        _line(frame, x="alignment_position", y="cumulative_identity_percent", title="Cumulative alignment identity", interpretation="Shows how overall identity stabilises across the alignment.", method="Cumulative identity proportion"),
        _line(frame, x="alignment_position", y="cumulative_gap_percent", title="Cumulative gap burden", interpretation="Tracks insertion/deletion burden across the alignment.", method="Cumulative gap proportion"),
        _group_bar(frame, category="event", value="alignment_position", agg="count", title="Alignment event composition", interpretation="Counts matches, mismatches and gap columns.", method="Alignment-column classification"),
    ]
    event_frame = _frame(events)
    if not event_frame.empty:
        event_position = _first_existing(event_frame, ["alignment_position", "position", "query_position", "target_position"])
        event_type = _first_existing(event_frame, ["event", "event_type", "type"])
        if event_position and event_type:
            visuals.append(_group_bar(event_frame, category=event_type, value=event_position, agg="count", title="Mapped substitution and indel events", interpretation="Summarises coordinate-mapped event classes.", method="Event-table aggregation"))
    return [visual for visual in visuals if visual is not None][:5]


def build_dti_prediction_visuals(
    prediction: Mapping[str, Any],
    descriptors: Mapping[str, Any] | None = None,
) -> list[ScientificVisual]:
    payload = dict(prediction)
    descriptor_map = dict(descriptors or {})
    numeric_descriptor_rows = []
    for name, value in descriptor_map.items():
        if isinstance(value, (int, float, np.number)) and np.isfinite(float(value)):
            numeric_descriptor_rows.append({"descriptor": str(name), "value": float(value)})
    descriptor_frame = pd.DataFrame(numeric_descriptor_rows)
    visuals: list[ScientificVisual | None] = []
    if not descriptor_frame.empty:
        display = descriptor_frame.copy()
        low = display["value"].min(); high = display["value"].max()
        display["normalised_value"] = 0.5 if high == low else (display["value"] - low) / (high - low)
        fig = go.Figure(go.Bar(x=display["descriptor"], y=display["normalised_value"]))
        fig.update_layout(title="Molecular descriptor profile", xaxis_tickangle=-35, yaxis_title="Normalised value")
        visuals.append(ScientificVisual("Molecular descriptor profile", "Compares the molecule's numerical descriptors on a common scale.", "Min–max normalised descriptor bar chart", fig, display))
        visuals.append(_histogram(descriptor_frame, x="value", title="Descriptor-value distribution", interpretation="Shows the spread of calculated molecular properties.", method="Descriptor distribution"))
    confidence_rows = []
    for label, key in [
        ("Positive probability", "positive_probability"),
        ("Decision threshold", "decision_threshold"),
        ("Nearest training similarity", "nearest_training_drug_similarity"),
    ]:
        value = payload.get(key)
        if isinstance(value, (int, float)) and np.isfinite(float(value)):
            confidence_rows.append({"metric": label, "value": float(value)})
    confidence = pd.DataFrame(confidence_rows)
    if not confidence.empty:
        visuals.append(_bar(confidence, x="metric", y="value", title="Prediction confidence context", interpretation="Places probability, threshold and training-set similarity side by side.", method="Model-output context bar"))
    interval_rows = []
    lower = payload.get("prediction_interval_lower")
    upper = payload.get("prediction_interval_upper")
    point = payload.get("predicted_p_activity")
    if all(isinstance(value, (int, float)) for value in [lower, upper, point]):
        interval_rows = pd.DataFrame([{"estimate": float(point), "lower": float(lower), "upper": float(upper)}])
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[float(lower), float(upper)], y=["pActivity", "pActivity"], mode="lines", line={"width": 8}, name="Interval"))
        fig.add_trace(go.Scatter(x=[float(point)], y=["pActivity"], mode="markers", marker={"size": 14}, name="Estimate"))
        fig.update_layout(title="Conformal prediction interval", xaxis_title="Predicted pActivity")
        visuals.append(ScientificVisual("Conformal prediction interval", "Shows the point estimate and uncertainty interval when available.", "Conformal interval display", fig, interval_rows))
    applicability_rows = []
    for name, key in [
        ("Training similarity", "nearest_training_drug_similarity"),
        ("Protein length", "protein_length"),
        ("Canonical SMILES length", "canonical_smiles"),
    ]:
        value = payload.get(key)
        if key == "canonical_smiles" and value is not None:
            value = len(str(value))
        if isinstance(value, (int, float)) and np.isfinite(float(value)):
            applicability_rows.append({"dimension": name, "value": float(value)})
    applicability = pd.DataFrame(applicability_rows)
    if not applicability.empty:
        visuals.append(_bar(applicability, x="dimension", y="value", title="Applicability-domain indicators", interpretation="Summarises basic molecule and target context used in the applicability review.", method="Input-domain indicator chart"))
    return [visual for visual in visuals if visual is not None][:5]
