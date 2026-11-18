from __future__ import annotations
from typing import Any

_SUCCESS = {"active", "available", "completed", "configured", "healthy", "locked", "published", "ready", "released", "resolved", "verified"}
_WARNING = {"configuration_required", "dependency_required", "draft", "open", "pending", "processing", "queued", "submitted", "under_review"}
_FAILURE = {"blocked", "denied", "error", "failed", "rejected", "retracted", "revoked", "unavailable"}

def friendly(value: Any) -> str:
    return str(value or "unknown").replace("_", " ").strip().capitalize()

def status_style(value: Any) -> tuple[str, str]:
    state = str(value or "unknown").lower()
    if state in _SUCCESS:
        return "green", ":material/check_circle:"
    if state in _WARNING:
        return "orange", ":material/schedule:"
    if state in _FAILURE:
        return "red", ":material/error:"
    return "gray", ":material/info:"

def status_badge(value: Any, *, label: str | None = None) -> None:
    from .._streamlit_compat import st
    color, icon = status_style(value)
    st.badge(label or friendly(value), color=color, icon=icon)

def readiness_badge(ready: bool, ready_label: str = "Ready", missing_label: str = "Setup required") -> None:
    from .._streamlit_compat import st
    st.badge(ready_label if ready else missing_label, color="green" if ready else "orange", icon=":material/check_circle:" if ready else ":material/settings:")

def provider_status(configured: bool, output_ready: bool = False, failed: bool = False) -> dict[str, str]:
    if failed:
        return {"state": "failed", "label": "Provider error", "detail": "The qualified provider reported an error."}
    if output_ready:
        return {"state": "ready", "label": "Qualified output ready", "detail": "A real provider output artifact is available."}
    if configured:
        return {"state": "configured", "label": "Provider configured", "detail": "Configuration exists; output is not implied."}
    return {"state": "configuration_required", "label": "Configuration required", "detail": "No provider result is claimed."}