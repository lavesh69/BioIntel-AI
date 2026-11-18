"""Shared native Streamlit visual system for BioIntel Education.

The package keeps imports lazy so service-layer and release tests can run without
loading the Streamlit runtime. UI functions import their rendering dependency only
when called.
"""
from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    "metric_grid": ("cards", "metric_grid"),
    "identity_card": ("cards", "identity_card"),
    "count_rows": ("charts", "count_rows"),
    "dated_counts": ("charts", "dated_counts"),
    "render_bar": ("charts", "render_bar"),
    "render_line": ("charts", "render_line"),
    "render_heatmap": ("charts", "render_heatmap"),
    "render_metric_explanation": ("charts", "render_metric_explanation"),
    "render_empty_state": ("empty_states", "render_empty_state"),
    "status_badge": ("status", "status_badge"),
    "readiness_badge": ("status", "readiness_badge"),
    "render_timeline": ("timelines", "render_timeline"),
    "render_workflow": ("workflows", "render_workflow"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(f"{__name__}.{module_name}"), attribute)
    globals()[name] = value
    return value
