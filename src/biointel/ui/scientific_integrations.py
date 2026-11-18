from __future__ import annotations

"""Reusable BioIntel integration panel for relevant scientific modules."""

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from biointel.integrations import integration_status, integrations_for_page


def _status_rows(page_path: str) -> list[dict[str, Any]]:
    return [integration_status(spec).public_dict() for spec in integrations_for_page(page_path)]


def render_page_integrations(
    page_path: str | Path,
    *,
    key_prefix: str,
    expanded: bool = False,
) -> None:
    normalized = str(page_path).replace("\\", "/")
    if normalized.startswith("/"):
        normalized = normalized.lstrip("/")
    marker = normalized.find("pages/")
    if marker >= 0:
        normalized = normalized[marker:]
    rows = _status_rows(normalized)
    if not rows:
        return

    ready = sum(bool(row["ready"]) for row in rows)
    priorities = " · ".join(sorted({str(row["priority"]) for row in rows}))
    with st.expander(
        f"BioIntel integrated scientific engines · {ready}/{len(rows)} ready · {priorities}",
        expanded=expanded,
    ):
        st.caption(
            "These adapters are connected only where scientifically relevant. Missing optional runtimes do not block the module's built-in BioIntel workflow."
        )
        frame = pd.DataFrame(rows)
        display = frame.assign(
            **{
                "Capabilities": frame["capabilities"].map(lambda values: " · ".join(values)),
                "Operations": frame["operations"].map(
                    lambda values: " · ".join(
                        value.replace("_", " ").title()
                        for value in values
                        if value != "technical_diagnostic"
                    )
                ),
            }
        )
        st.dataframe(
            display[
                [
                    "public_key",
                    "name",
                    "priority",
                    "state",
                    "execution_mode",
                    "Capabilities",
                    "Operations",
                ]
            ],
            hide_index=True,
            width="stretch",
            key=f"{key_prefix}_biointel_integrations",
        )
        if hasattr(st, "page_link"):
            st.page_link(
                "pages/356_BioIntel_Scientific_Integration_Center.py",
                label="Open BioIntel Scientific Integration Center",
                icon="🧬",
            )
        st.caption(
            "Technical readiness is not scientific, clinical or regulatory validation. Model assets and reference databases remain qualification-gated."
        )
