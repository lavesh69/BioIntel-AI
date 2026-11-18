"""Explicit one-shot browser geolocation using Streamlit Custom Components v2."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st

_HTML = """
<div class="geo-shell">
  <button id="request-location" type="button">📍 Auto-detect current location</button>
  <span id="geo-status" role="status">One-time browser permission · never continuously tracked.</span>
</div>
"""
_CSS = """
.geo-shell { display:flex; gap:.75rem; align-items:center; flex-wrap:wrap; color:var(--st-text-color); }
button { border:1px solid var(--st-primary-color); border-radius:.5rem; padding:.55rem .9rem;
  color:var(--st-text-color); background:var(--st-secondary-background-color); cursor:pointer; }
button:focus-visible { outline:3px solid var(--st-primary-color); outline-offset:2px; }
span { font-size:.88rem; opacity:.82; }
"""
_JS = """
export default function (component) {
  const { parentElement, setStateValue } = component
  const button = parentElement.querySelector("#request-location")
  const status = parentElement.querySelector("#geo-status")
  if (!button || !status) return
  button.onclick = () => {
    if (!navigator.geolocation) {
      status.textContent = "Browser geolocation is unavailable."
      setStateValue("error", "Browser geolocation is unavailable.")
      return
    }
    status.textContent = "Waiting for browser permission…"
    button.disabled = true
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const value = {
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy_m: position.coords.accuracy,
          captured_at_ms: position.timestamp
        }
        status.textContent = "Location received for this session."
        setStateValue("location", value)
        setStateValue("error", "")
        button.disabled = false
      },
      (error) => {
        const messages = {
          1: "Location permission was denied. Manual entry remains available.",
          2: "Current position is unavailable. Manual entry remains available.",
          3: "Location request timed out. Manual entry remains available."
        }
        const message = messages[error.code] || "Browser geolocation failed. Manual entry remains available."
        status.textContent = message
        setStateValue("error", message)
        button.disabled = false
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }
    )
  }
}
"""

_GEOLOCATION = st.components.v2.component(
    "biointel_one_shot_geolocation",
    html=_HTML,
    css=_CSS,
    js=_JS,
)


def one_shot_geolocation(
    *,
    key: str = "biointel_current_location",
    on_location_change: Callable[[], None] | None = None,
    on_error_change: Callable[[], None] | None = None,
) -> Any:
    """Mount a permission-gated, non-tracking browser location control."""
    return _GEOLOCATION(
        key=key,
        on_location_change=on_location_change or (lambda: None),
        on_error_change=on_error_change or (lambda: None),
        height=62,
    )