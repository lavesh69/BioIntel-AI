from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from biointel.internet.network_policy import internet_policy_from_environment

from .catalog import resources_for_module
from .service import probe_resources


@st.cache_data(show_spinner=False, ttl=300)
def _cached_probe(module_key: str, title: str, category: str) -> dict[str, object]:
    resources = resources_for_module(module_key, title, category, limit=6)
    return probe_resources(resources)


def _render_links(module_key: str, title: str, category: str, *, prefix: str) -> None:
    resources = resources_for_module(module_key, title, category, limit=6)
    query = st.text_input(
        "Scientific search term (optional)",
        key=f"{prefix}_query",
        placeholder="Gene, compound, disease, accession, pathway or study term",
        max_chars=500,
    )
    columns = st.columns(min(3, max(1, len(resources))))
    for index, resource in enumerate(resources):
        columns[index % len(columns)].link_button(
            resource.name,
            resource.url(query),
            width="stretch",
            help=resource.purpose,
        )
    with st.popover("Why these sources?", width="stretch"):
        for resource in resources:
            st.markdown(f"- **{resource.name}:** {resource.purpose}")
    st.caption(
        "Links open official public scientific websites. Raw uploads are never sent automatically. "
        "Do not enter patient identifiers, confidential sequences or proprietary project terms."
    )


def render_scientific_resources_panel(
    module_key: str,
    title: str,
    category: str,
    *,
    prefix: str | None = None,
    expanded: bool = False,
) -> None:
    key_prefix = prefix or f"v209_resources_{module_key}"
    with st.expander("Scientific websites & online evidence", expanded=expanded):
        policy = internet_policy_from_environment()
        if not policy.enabled:
            st.info("Internet access is disabled. The module remains fully usable with local demos, uploads and reports.")
        _render_links(module_key, title, category, prefix=key_prefix)
        c1, c2 = st.columns([1, 1])
        if c1.button("Check website availability", key=f"{key_prefix}_probe", width="stretch"):
            _cached_probe.clear()
            with st.spinner("Checking optional official websites…"):
                st.session_state[f"{key_prefix}_availability"] = _cached_probe(module_key, title, category)
        if c2.button("Clear availability result", key=f"{key_prefix}_clear", width="stretch"):
            st.session_state.pop(f"{key_prefix}_availability", None)
        report = st.session_state.get(f"{key_prefix}_availability")
        if isinstance(report, dict):
            rows = report.get("resources", [])
            if rows:
                frame = pd.DataFrame(rows)
                st.dataframe(
                    frame[[column for column in ("resource", "state", "latency_ms", "error") if column in frame]],
                    hide_index=True,
                    width="stretch",
                    height=min(300, 38 + 35 * len(frame)),
                )
            checked = int(report.get("checked_count", 0))
            available = int(report.get("available_count", 0))
            if checked and available == checked:
                st.success(f"{available}/{checked} optional scientific websites responded.")
            elif checked:
                st.warning(f"{available}/{checked} websites responded. Unavailable websites do not block offline analysis.")
            st.download_button(
                "Download availability report",
                json.dumps(report, indent=2, default=str).encode("utf-8"),
                f"BioIntel-{module_key}-website-availability.json",
                "application/json",
                key=f"{key_prefix}_download",
                width="stretch",
            )


def render_scientific_resources_sidebar(module_key: str, title: str, category: str) -> None:
    with st.sidebar.expander("Scientific websites", expanded=False):
        _render_links(module_key, title, category, prefix=f"v209_sidebar_resources_{module_key}")
        st.info("Optional websites never block the local module and no online result is claimed unless a request succeeds.")


__all__ = ["render_scientific_resources_panel", "render_scientific_resources_sidebar"]
