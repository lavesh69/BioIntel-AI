from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .catalog import VisualSpec
from .scientific import PlanningResult

MAX_VISUAL_ROWS = 5_000


def _table(result: PlanningResult, source: str) -> pd.DataFrame:
    if source == "primary":
        frame = result.primary
    elif source == "secondary":
        frame = result.secondary
    else:
        frame = result.tables.get(source, result.primary)
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        frame = result.primary
    return frame.head(MAX_VISUAL_ROWS).copy().replace([np.inf, -np.inf], np.nan)


def _existing(frame: pd.DataFrame, *names: str | None) -> list[str]:
    return [name for name in names if name and name in frame.columns]


def _first_numeric(frame: pd.DataFrame, exclude: Iterable[str] = ()) -> str | None:
    excluded = set(exclude)
    for column in frame.select_dtypes(include=[np.number]).columns:
        if column not in excluded:
            return str(column)
    return None


def _first_text(frame: pd.DataFrame, exclude: Iterable[str] = ()) -> str | None:
    excluded = set(exclude)
    for column in frame.columns:
        if column not in excluded and not pd.api.types.is_numeric_dtype(frame[column]):
            return str(column)
    return None


def _fallback_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame({"category": ["No data"], "value": [0.0]})
    return frame


def build_figure(spec: VisualSpec, result: PlanningResult) -> tuple[go.Figure, pd.DataFrame]:
    frame = _fallback_frame(_table(result, spec.source))
    kind = spec.kind.lower()
    x = spec.x if spec.x in frame.columns else _first_text(frame)
    y = spec.y if spec.y in frame.columns else _first_numeric(frame)
    color = spec.color if spec.color in frame.columns else None
    size = spec.size if spec.size in frame.columns else None

    if kind == "bar":
        if x is None:
            x = frame.columns[0]
        if y is None:
            counts = frame[x].astype(str).value_counts().reset_index()
            counts.columns = [x, "records"]
            frame = counts
            y = "records"
        fig = px.bar(frame, x=x, y=y, color=color, title=spec.title)

    elif kind == "line":
        if x is None:
            frame = frame.reset_index(names="index")
            x = "index"
        if y is None:
            y = _first_numeric(frame, [x])
        if y is None:
            frame["value"] = np.arange(len(frame))
            y = "value"
        fig = px.line(frame.sort_values(x), x=x, y=y, color=color, markers=True, title=spec.title)

    elif kind == "area":
        if x is None:
            frame = frame.reset_index(names="index")
            x = "index"
        if y is None:
            y = _first_numeric(frame, [x])
        if y is None:
            frame["value"] = 0
            y = "value"
        fig = px.area(frame.sort_values(x), x=x, y=y, color=color, title=spec.title)

    elif kind == "scatter":
        numeric = list(frame.select_dtypes(include=[np.number]).columns)
        if x not in frame.columns:
            x = numeric[0] if numeric else frame.columns[0]
        if y not in frame.columns:
            y = numeric[1] if len(numeric) > 1 else (numeric[0] if numeric else frame.columns[-1])
        fig = px.scatter(frame, x=x, y=y, color=color, size=size, hover_data=list(frame.columns[:8]), title=spec.title)

    elif kind == "histogram":
        if x is None:
            x = _first_numeric(frame) or frame.columns[0]
        fig = px.histogram(frame, x=x, color=color, marginal="box", title=spec.title)

    elif kind == "box":
        if y is None:
            y = _first_numeric(frame)
        if y is None:
            frame["value"] = 0
            y = "value"
        fig = px.box(frame, x=x if x in frame.columns else None, y=y, color=color, points="outliers", title=spec.title)

    elif kind == "donut":
        names = x if x in frame.columns else (_first_text(frame) or frame.columns[0])
        if y and y in frame.columns and pd.api.types.is_numeric_dtype(frame[y]):
            pie = frame.groupby(names, as_index=False)[y].sum()
            values = y
        else:
            pie = frame[names].astype(str).value_counts().reset_index()
            pie.columns = [names, "records"]
            values = "records"
        frame = pie
        fig = px.pie(frame, names=names, values=values, hole=0.48, title=spec.title)

    elif kind == "funnel":
        if x is None:
            x = _first_text(frame) or frame.columns[0]
        if y is None:
            y = _first_numeric(frame, [x])
        if y is None:
            frame["records"] = np.arange(len(frame), 0, -1)
            y = "records"
        fig = px.funnel(frame, x=y, y=x, color=color, title=spec.title)

    elif kind == "heatmap":
        row_col = spec.y if spec.y in frame.columns else (_first_text(frame) or frame.columns[0])
        col_col = spec.x if spec.x in frame.columns else _first_text(frame, [row_col])
        val_col = _first_numeric(frame)
        if col_col is None:
            frame["group"] = "All"
            col_col = "group"
        if val_col is None:
            frame["value"] = 1.0
            val_col = "value"
        pivot = frame.pivot_table(index=row_col, columns=col_col, values=val_col, aggfunc="mean", fill_value=0)
        display = pivot.reset_index()
        fig = px.imshow(pivot, aspect="auto", labels={"x": col_col, "y": row_col, "color": val_col}, title=spec.title)
        frame = display

    elif kind == "radar":
        label = spec.x if spec.x in frame.columns else (_first_text(frame) or frame.columns[0])
        value = spec.y if spec.y in frame.columns else _first_numeric(frame)
        if value is None:
            frame["score"] = 0.0
            value = "score"
        radar = frame[[label, value]].dropna().head(20)
        if radar.empty:
            radar = pd.DataFrame({label: ["No data"], value: [0]})
        fig = go.Figure(go.Scatterpolar(r=radar[value].astype(float), theta=radar[label].astype(str), fill="toself"))
        fig.update_layout(title=spec.title, polar=dict(radialaxis=dict(visible=True, range=[0, max(100, float(radar[value].max()) if len(radar) else 100)])))
        frame = radar

    elif kind == "parallel":
        numeric = list(frame.select_dtypes(include=[np.number]).columns)[:6]
        if len(numeric) < 2:
            frame = frame.reset_index(names="row")
            frame["value"] = np.arange(len(frame))
            numeric = ["row", "value"]
        color_column = numeric[-1]
        fig = px.parallel_coordinates(frame, dimensions=numeric, color=color_column, title=spec.title)

    elif kind == "sunburst":
        path = _existing(frame, spec.x, spec.y)
        if not path:
            first = _first_text(frame) or frame.columns[0]
            path = [first]
        value = size if size and pd.api.types.is_numeric_dtype(frame[size]) else _first_numeric(frame)
        if value is None:
            frame["records"] = 1
            value = "records"
        fig = px.sunburst(frame, path=path, values=value, title=spec.title)

    elif kind == "treemap":
        path = _existing(frame, spec.x, spec.y)
        if not path:
            first = _first_text(frame) or frame.columns[0]
            path = [first]
        value = size if size and pd.api.types.is_numeric_dtype(frame[size]) else _first_numeric(frame)
        if value is None:
            frame["records"] = 1
            value = "records"
        fig = px.treemap(frame, path=path, values=value, title=spec.title)

    elif kind == "timeline":
        label = "label" if "label" in frame.columns else (_first_text(frame) or frame.columns[0])
        start = "start_day" if "start_day" in frame.columns else _first_numeric(frame)
        end = "end_day" if "end_day" in frame.columns else _first_numeric(frame, [start] if start else [])
        if start is None:
            frame["start_day"] = np.arange(len(frame))
            start = "start_day"
        if end is None:
            frame["end_day"] = frame[start].astype(float) + 1
            end = "end_day"
        duration = (pd.to_numeric(frame[end], errors="coerce") - pd.to_numeric(frame[start], errors="coerce")).clip(lower=0)
        fig = go.Figure()
        group = color if color in frame.columns else None
        if group:
            for group_value, subset in frame.assign(_duration=duration).groupby(group, dropna=False):
                fig.add_trace(go.Bar(y=subset[label].astype(str), x=subset["_duration"], base=subset[start], orientation="h", name=str(group_value), hovertext=subset[label].astype(str)))
        else:
            fig.add_trace(go.Bar(y=frame[label].astype(str), x=duration, base=frame[start], orientation="h", name="Schedule"))
        fig.update_layout(title=spec.title, barmode="stack", xaxis_title="Study day", yaxis_title="")

    elif kind == "waterfall":
        label = x if x in frame.columns else (_first_text(frame) or frame.columns[0])
        value = y if y in frame.columns else _first_numeric(frame)
        if value is None:
            frame["value"] = 0
            value = "value"
        fig = go.Figure(go.Waterfall(x=frame[label].astype(str), y=frame[value].astype(float), measure=["relative"] * len(frame)))
        fig.update_layout(title=spec.title)

    elif kind == "contour":
        x_col = spec.x if spec.x in frame.columns else _first_numeric(frame)
        y_col = spec.y if spec.y in frame.columns else _first_numeric(frame, [x_col] if x_col else [])
        z_col = _first_numeric(frame, [x_col, y_col] if x_col and y_col else [])
        if x_col and y_col and z_col:
            pivot = frame.pivot_table(index=y_col, columns=x_col, values=z_col, aggfunc="mean")
            fig = go.Figure(go.Contour(z=pivot.values, x=pivot.columns, y=pivot.index, contours_coloring="heatmap"))
            fig.update_layout(title=spec.title, xaxis_title=x_col, yaxis_title=y_col)
            frame = pivot.reset_index()
        else:
            frame = frame.reset_index(names="index")
            fig = px.line(frame, x="index", y=_first_numeric(frame) or "index", title=spec.title)

    elif kind == "sankey":
        source_col = spec.x if spec.x in frame.columns else ("from" if "from" in frame.columns else _first_text(frame))
        target_col = spec.y if spec.y in frame.columns else ("to" if "to" in frame.columns else _first_text(frame, [source_col] if source_col else []))
        value_col = size if size in frame.columns else _first_numeric(frame)
        if source_col is None or target_col is None:
            frame = pd.DataFrame({"from": ["Input"], "to": ["Output"], "value": [1]})
            source_col, target_col, value_col = "from", "to", "value"
        if value_col is None:
            frame["value"] = 1
            value_col = "value"
        links = frame[[source_col, target_col, value_col]].dropna().copy()
        labels = list(dict.fromkeys([*links[source_col].astype(str), *links[target_col].astype(str)]))
        index = {label: idx for idx, label in enumerate(labels)}
        fig = go.Figure(go.Sankey(node=dict(label=labels), link=dict(source=[index[v] for v in links[source_col].astype(str)], target=[index[v] for v in links[target_col].astype(str)], value=pd.to_numeric(links[value_col], errors="coerce").fillna(1))))
        fig.update_layout(title=spec.title)
        frame = links

    elif kind == "upset":
        label = x if x in frame.columns else (_first_text(frame) or frame.columns[0])
        value = y if y in frame.columns else _first_numeric(frame)
        if value is None:
            counts = frame[label].astype(str).value_counts().reset_index()
            counts.columns = [label, "records"]
            frame = counts
            value = "records"
        fig = px.bar(frame.sort_values(value, ascending=False), x=label, y=value, title=spec.title)

    else:
        frame = frame.reset_index(names="index")
        value = _first_numeric(frame) or "index"
        fig = px.line(frame, x="index", y=value, title=spec.title)

    fig.update_layout(margin=dict(l=20, r=20, t=60, b=30), legend_title_text="", height=520)
    return fig, frame
