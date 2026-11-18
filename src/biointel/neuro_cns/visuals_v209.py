from __future__ import annotations

from typing import Iterable

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .catalog import NeuroModuleSpec


def portfolio_figures(modules: Iterable[NeuroModuleSpec]) -> dict[str, go.Figure]:
    rows = []
    for module in modules:
        rows.append(
            {
                "number": module.number,
                "module": module.title,
                "workspace": module.workspace,
                "readiness": module.readiness,
                "input_types": len(module.inputs),
                "output_types": len(module.outputs),
                "basis": module.basis,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return {}
    figures: dict[str, go.Figure] = {}
    workspace = frame.groupby("workspace", as_index=False).agg(modules=("module", "count"), input_types=("input_types", "sum"), output_types=("output_types", "sum"))
    figures["workspace_coverage"] = px.bar(
        workspace,
        x="workspace",
        y=["modules", "input_types", "output_types"],
        barmode="group",
        title="Neuro/CNS workspace coverage",
    )
    figures["module_io_depth"] = px.scatter(
        frame,
        x="input_types",
        y="output_types",
        color="workspace",
        size="number",
        hover_name="module",
        hover_data={"number": True, "readiness": True, "basis": True},
        title="Module input/output workflow depth",
    )
    readiness = frame.assign(readiness_group=frame["readiness"].str.replace(r"\s+", " ", regex=True)).groupby(["workspace", "readiness_group"], as_index=False).size()
    figures["readiness_map"] = px.bar(
        readiness,
        x="workspace",
        y="size",
        color="readiness_group",
        title="Documented module readiness by workspace",
        labels={"size": "Modules", "readiness_group": "Readiness"},
    )
    return figures


__all__ = ["portfolio_figures"]
