from __future__ import annotations

from typing import Any

import streamlit as st

_COPY: dict[str, dict[str, str]] = {
    "workspace": {"English": "Workspace", "Hinglish": "Workspace"},
    "task_lanes": {"English": "Task lanes", "Hinglish": "Kaam ke shortcuts"},
    "browse_domain": {"English": "Browse a domain", "Hinglish": "Domain browse karein"},
    "find_modules": {"English": "Find modules", "Hinglish": "Modules dhundhein"},
    "search_note": {
        "English": "Search by task, scientific domain, file type or workflow. Typo-tolerant matching is enabled.",
        "Hinglish": "Task, scientific domain, file type ya workflow se search karein. Typo-tolerant matching enabled hai.",
    },
    "all_domains": {"English": "All domains", "Hinglish": "Saare domains"},
    "no_match": {
        "English": "No matching module. Try a broader keyword or select All domains.",
        "Hinglish": "Koi matching module nahi mila. Broader keyword try karein ya Saare domains select karein.",
    },
    "system_status": {"English": "System status", "Hinglish": "System status"},
    "notifications": {"English": "Notifications", "Hinglish": "Notifications"},
    "workspace_healthy": {"English": "Workspace healthy", "Hinglish": "Workspace healthy hai"},
    "workspace_review": {"English": "Workspace review needed", "Hinglish": "Workspace review chahiye"},
    "no_notifications": {"English": "No new notifications.", "Hinglish": "Koi nayi notification nahi hai."},
    "clear_notifications": {"English": "Clear notifications", "Hinglish": "Notifications clear karein"},
    "view": {"English": "View", "Hinglish": "View"},
    "interface": {"English": "Interface", "Hinglish": "Interface"},
    "appearance": {"English": "Appearance", "Hinglish": "Appearance"},
    "theme": {"English": "Theme", "Hinglish": "Theme"},
    "text_font": {"English": "Text font", "Hinglish": "Text font"},
    "compact": {"English": "Compact", "Hinglish": "Compact"},
    "contrast": {"English": "Contrast", "Hinglish": "Contrast"},
    "reduce_motion": {"English": "Reduce motion", "Hinglish": "Motion kam karein"},
    "text_scale": {"English": "Text scale", "Hinglish": "Text size"},
    "language": {"English": "Language", "Hinglish": "Language"},
    "role": {"English": "Workspace role", "Hinglish": "Workspace role"},
    "save": {"English": "Save", "Hinglish": "Save karein"},
    "reset": {"English": "Reset", "Hinglish": "Reset karein"},
    "preferences_saved": {"English": "Interface preferences saved", "Hinglish": "Interface preferences save ho gayi"},
    "retry": {"English": "Retry", "Hinglish": "Dobara try karein"},
    "reset_parameters": {"English": "Reset parameters", "Hinglish": "Parameters reset karein"},
    "download_failed": {"English": "Download failed rows", "Hinglish": "Failed rows download karein"},
    "search_records": {"English": "Search records", "Hinglish": "Records dhundhein"},
    "download_table": {"English": "Export CSV", "Hinglish": "CSV export karein"},
    "no_records": {"English": "No records are available for this view.", "Hinglish": "Is view ke liye koi record available nahi hai."},
}


def text(key: str, default: str | None = None, **values: Any) -> str:
    language = str(st.session_state.get("ui_language", "English"))
    entries = _COPY.get(key, {})
    template = str(entries.get(language) or entries.get("English") or default or key)
    try:
        return template.format(**values)
    except (KeyError, ValueError):
        return template


def languages() -> tuple[str, ...]:
    return ("English", "Hinglish")
