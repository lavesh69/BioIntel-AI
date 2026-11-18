from __future__ import annotations

import html
import inspect
import json
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from biointel.intelligence.data_intelligence import all_database_health
from biointel.runtime_paths import runtime_database_path
from biointel.ui.aesthetic import apply_premium_aesthetic
from biointel.ui.appearance_engine import (
    chart_profile_for,
    pairing_for,
    theme_variable_override_css,
)
from biointel.ui.brand import (
    about_brand_html,
    brand_header_html,
    compact_module_name,
    product_family_for_category,
    sidebar_brand_html,
)
from biointel.ui.experience_themes import experience_for, experience_theme_css
from biointel.ui.information_architecture_v217 import page_surface
from biointel.ui.motion import (
    MOTION_MODES,
    configure_figure_motion,
    normalize_motion_mode,
    plotly_transition_for,
)
from biointel.ui.navigation import (
    CATEGORIES,
    CATEGORY_META,
    PAGE_BY_KEY,
    PAGE_BY_PATH,
    SIDEBAR_PRIMARY,
    SIDEBAR_WORK_MODES,
    adjacent_pages,
    search_pages,
)
from biointel.ui.performance import read_text_cached
from biointel.ui.preferences import (
    UiPreferences,
    load_preferences,
    record_recent_page,
    save_preferences,
)
from biointel.ui.style_catalog import (
    DEFAULT_FONT,
    DEFAULT_THEME,
    FONTS,
    THEMES,
    FontSpec,
    ThemeSpec,
)
from biointel.ui.theme_intelligence import (
    DENSITY_MODES,
    PERFORMANCE_MODES,
    sanitise_custom_tokens,
    theme_runtime_css,
)

Palette = ThemeSpec
PALETTES = THEMES


PROJECT_ROOT = Path(__file__).resolve().parents[3]
_NAVIGATION_HISTORY_LIMIT = 48
_NAVIGATION_HISTORY_KEY = "_bio_navigation_history"
_NAVIGATION_FORWARD_KEY = "_bio_navigation_forward"
_NAVIGATION_CURRENT_KEY = "_bio_navigation_current"
_NAVIGATION_PENDING_KEY = "_bio_navigation_pending"

_LAYOUT_RESIZE_OBSERVER_HTML = (
    '<span data-bio-layout-observer aria-hidden="true" style="display:none"></span>'
)
_LAYOUT_RESIZE_OBSERVER_JS = r"""
export default function ({ parentElement }) {
  const appView = parentElement.closest('[data-testid="stAppViewContainer"]')
  const sidebar = appView?.querySelector(':scope > [data-testid="stSidebar"]')
  const main = appView?.querySelector('[data-testid="stMain"]')
  const mainWrapper = main?.parentElement

  if (!appView || !sidebar || !mainWrapper) return

  // --- ULTRA-PREMIUM HOLOGRAPHIC SPOTLIGHT & GLASSMORPHIC INTERACTION ENGINE ---
  const doc = appView.ownerDocument || document

  // Clean up any old canvas elements
  const oldCanvas = doc.getElementById("bio-3d-live-matrix-canvas")
  if (oldCanvas) oldCanvas.remove()
  doc.querySelectorAll(".bio-3d-dna-canvas").forEach((el) => el.remove())

  // Inject Subtle Mouse-Following Holographic Spotlight
  let spotlight = doc.getElementById("bio-holographic-spotlight")
  if (!spotlight) {
    spotlight = doc.createElement("div")
    spotlight.id = "bio-holographic-spotlight"
    spotlight.style.position = "fixed"
    spotlight.style.top = "0"
    spotlight.style.left = "0"
    spotlight.style.width = "100vw"
    spotlight.style.height = "100vh"
    spotlight.style.pointerEvents = "none"
    spotlight.style.zIndex = "0"
    spotlight.style.transition = "background 0.15s ease-out"
    doc.body.insertBefore(spotlight, doc.body.firstChild)

    doc.addEventListener("mousemove", (e) => {
      const x = e.clientX
      const y = e.clientY
      spotlight.style.background = `radial-gradient(750px circle at ${x}px ${y}px, rgba(56, 189, 248, 0.08), rgba(168, 85, 247, 0.04) 40%, transparent 70%)`
    })
  }

  let resizeTimer


  let previousWidth = -1

  const notifyResponsiveChildren = () => {
    window.dispatchEvent(new Event("resize"))

    // Touch isolation for 3D molecular viewers & mobile table responsive scrolling
    for (const canvas of appView.querySelectorAll("canvas, iframe, [data-testid='stDataFrame']")) {
      canvas.style.touchAction = "manipulation"
    }
    for (const tbl of appView.querySelectorAll("[data-testid='stTable'], [data-testid='stDataFrame']")) {
      tbl.style.overflowX = "auto"
      tbl.style.webkitOverflowScrolling = "touch"
    }

    const plotly = window.Plotly
    if (plotly?.Plots?.resize) {
      for (const chart of appView.querySelectorAll(
        '[data-testid="stPlotlyChart"] .js-plotly-plot'
      )) {
        plotly.Plots.resize(chart)
      }
    }
  }


  const scheduleResize = () => {
    window.requestAnimationFrame(notifyResponsiveChildren)
    window.clearTimeout(resizeTimer)
    resizeTimer = window.setTimeout(notifyResponsiveChildren, 240)
  }

  const sidebarObserver = new MutationObserver(scheduleResize)
  sidebarObserver.observe(sidebar, {
    attributes: true,
    attributeFilter: ["aria-expanded", "class", "style"],
  })

  const widthObserver = new ResizeObserver((entries) => {
    const width = Math.round(entries[0]?.contentRect?.width ?? 0)
    if (width !== previousWidth) {
      previousWidth = width
      scheduleResize()
    }
  })
  widthObserver.observe(mainWrapper)
  scheduleResize()

  return () => {
    sidebarObserver.disconnect()
    widthObserver.disconnect()
    window.clearTimeout(resizeTimer)
  }
}
"""


def _declare_layout_resize_observer():
    return st.components.v2.component(
        "biointel_layout_resize_observer",
        html=_LAYOUT_RESIZE_OBSERVER_HTML,
        js=_LAYOUT_RESIZE_OBSERVER_JS,
        isolate_styles=False,
    )


_LAYOUT_RESIZE_OBSERVER = _declare_layout_resize_observer()


def _mount_layout_resize_observer() -> None:
    """Recover when an isolated AppTest resets the component registry."""

    global _LAYOUT_RESIZE_OBSERVER
    options = {
        "key": "biointel-global-layout-resize-observer",
        "width": "stretch",
        "height": 0,
    }
    try:
        _LAYOUT_RESIZE_OBSERVER(**options)
    except ValueError as exc:
        if "is not registered" not in str(exc):
            raise
        _LAYOUT_RESIZE_OBSERVER = _declare_layout_resize_observer()
        _LAYOUT_RESIZE_OBSERVER(**options)


def current_page_key() -> str | None:
    """Infer the active page with a fast frame walk and bounded fallback.

    ``inspect.stack`` is intentionally avoided on the normal path because it is
    expensive on every Streamlit rerun. The fallback only runs when Streamlit
    hides the page frame from ``f_back``.
    """

    def resolve(filename: str | None) -> tuple[str | None, bool]:
        if not filename:
            return None, False
        try:
            relative = Path(filename).resolve().relative_to(PROJECT_ROOT).as_posix()
        except (OSError, TypeError, ValueError):
            return None, False
        page = PAGE_BY_PATH.get(relative)
        if page is None:
            return None, False
        return page.key, relative.startswith("pages/")

    fallback_key: str | None = None
    try:
        frame = sys._getframe()
    except (AttributeError, ValueError):  # pragma: no cover
        frame = None
    depth = 0
    seen: set[str] = set()
    while frame is not None and depth < 48:
        filename = frame.f_code.co_filename
        frame = frame.f_back
        depth += 1
        if not filename or filename in seen:
            continue
        seen.add(filename)
        key, exact = resolve(filename)
        if exact:
            return key
        fallback_key = fallback_key or key

    # Rare compatibility fallback for Streamlit runners that hide the page frame.
    if fallback_key is None:
        for item in inspect.stack(context=0)[:16]:
            key, exact = resolve(item.filename)
            if exact:
                return key
            fallback_key = fallback_key or key

    main_module = sys.modules.get("__main__")
    key, _ = resolve(getattr(main_module, "__file__", None))
    return fallback_key or key


def _normalise_navigation_keys(value: object, *, exclude: str | None = None) -> list[str]:
    """Keep history bounded and discard stale page keys after a release update."""
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    for item in value:
        key = str(item)
        if key not in PAGE_BY_KEY or key == exclude or key in cleaned:
            continue
        cleaned.append(key)
    return cleaned[-_NAVIGATION_HISTORY_LIMIT:]


def _track_navigation_history(active_key: str | None) -> None:
    """Record real page transitions without treating Streamlit reruns as navigation.

    Standard ``st.page_link`` controls do not expose a click callback. Tracking
    the active page at render time keeps sidebar, finder and direct page links
    in one history, while the explicit Back/Forward controls below use a small
    pending marker to avoid creating a duplicate loop.
    """
    if active_key not in PAGE_BY_KEY:
        return
    previous = str(st.session_state.get(_NAVIGATION_CURRENT_KEY, "") or "")
    history = _normalise_navigation_keys(st.session_state.get(_NAVIGATION_HISTORY_KEY), exclude=active_key)
    forward = _normalise_navigation_keys(st.session_state.get(_NAVIGATION_FORWARD_KEY), exclude=active_key)
    pending = st.session_state.get(_NAVIGATION_PENDING_KEY)
    if isinstance(pending, dict) and pending.get("target") == active_key:
        st.session_state.pop(_NAVIGATION_PENDING_KEY, None)
        st.session_state[_NAVIGATION_HISTORY_KEY] = history
        st.session_state[_NAVIGATION_FORWARD_KEY] = forward
        st.session_state[_NAVIGATION_CURRENT_KEY] = active_key
        return
    if previous and previous != active_key and previous in PAGE_BY_KEY:
        history = _normalise_navigation_keys([*history, previous], exclude=active_key)
        forward = []
    st.session_state[_NAVIGATION_HISTORY_KEY] = history
    st.session_state[_NAVIGATION_FORWARD_KEY] = forward
    st.session_state[_NAVIGATION_CURRENT_KEY] = active_key


def _history_targets(active_key: str) -> tuple[str | None, str | None]:
    history = _normalise_navigation_keys(st.session_state.get(_NAVIGATION_HISTORY_KEY), exclude=active_key)
    forward = _normalise_navigation_keys(st.session_state.get(_NAVIGATION_FORWARD_KEY), exclude=active_key)
    return (history[-1] if history else None, forward[0] if forward else None)


def _navigate_history(active_key: str, direction: str) -> None:
    """Move through session history using a controlled Streamlit page switch."""
    history = _normalise_navigation_keys(st.session_state.get(_NAVIGATION_HISTORY_KEY), exclude=active_key)
    forward = _normalise_navigation_keys(st.session_state.get(_NAVIGATION_FORWARD_KEY), exclude=active_key)
    if direction == "back":
        if not history:
            return
        target = history[-1]
        history = history[:-1]
        forward = _normalise_navigation_keys([active_key, *forward], exclude=target)
    elif direction == "forward":
        if not forward:
            return
        target = forward[0]
        forward = forward[1:]
        history = _normalise_navigation_keys([*history, active_key], exclude=target)
    else:
        raise ValueError(f"Unknown history direction: {direction}")
    page = PAGE_BY_KEY.get(target)
    if page is None:
        return
    st.session_state[_NAVIGATION_HISTORY_KEY] = history
    st.session_state[_NAVIGATION_FORWARD_KEY] = forward
    st.session_state[_NAVIGATION_PENDING_KEY] = {"direction": direction, "target": target}
    st.switch_page(page.path)


def _ui_preference_defaults(stored: UiPreferences | None = None) -> dict[str, object]:
    """Return normalized UI defaults used to heal incomplete Streamlit sessions.

    Streamlit removes widget-backed keys when navigating between pages in some
    execution paths.  The old one-time ``ui_preferences_loaded`` guard could
    therefore remain present while keys such as ``ui_palette`` had already
    disappeared, causing a global KeyError before the page rendered.
    """

    preferences = stored or UiPreferences()
    palette = preferences.palette if preferences.palette in PALETTES else DEFAULT_THEME
    font_family = preferences.font_family if preferences.font_family in FONTS else DEFAULT_FONT
    appearance = (
        preferences.appearance_mode
        if preferences.appearance_mode in {"Dark", "Light", "System"}
        else "Dark"
    )
    color_vision = (
        preferences.color_vision
        if preferences.color_vision in {"Standard", "Deuteranopia", "Tritanopia", "Monochrome"}
        else "Standard"
    )
    return {
        "ui_palette": palette,
        "ui_font_family": font_family,
        "ui_heading_font_family": (
            preferences.heading_font_family
            if preferences.heading_font_family in FONTS
            else font_family
        ),
        "ui_data_font_family": (
            preferences.data_font_family if preferences.data_font_family in FONTS else font_family
        ),
        "ui_typography_preset": preferences.typography_preset,
        "ui_density_mode": preferences.density_mode if preferences.density_mode in DENSITY_MODES else ("Dense" if preferences.compact else "Professional"),
        "ui_compact": bool(preferences.compact or preferences.density_mode == "Dense"),
        "ui_reduce_motion": bool(preferences.reduce_motion),
        "ui_motion_mode": normalize_motion_mode(
            preferences.motion_mode, reduce_motion=preferences.reduce_motion
        ),
        "ui_reduce_effects": bool(preferences.reduce_effects),
        "ui_performance_mode": preferences.performance_mode if preferences.performance_mode in PERFORMANCE_MODES else "Adaptive",
        "ui_high_contrast": bool(preferences.high_contrast),
        "ui_appearance_mode": appearance,
        "ui_font_scale": min(1.25, max(0.85, float(preferences.font_scale))),
        "ui_color_vision": color_vision,
        "ui_language": str(preferences.language or "English"),
        "ui_apply_appearance_to_reports": bool(preferences.apply_appearance_to_reports),
        "ui_report_style": str(preferences.report_style or "Print light"),
        "ui_favourites": [key for key in preferences.favourites if key in PAGE_BY_KEY],
        "ui_recent_pages": [key for key in preferences.recent_pages if key in PAGE_BY_KEY],
        "ui_theme_favourites": [name for name in preferences.theme_favourites if name in PALETTES],
        "ui_recent_themes": [name for name in preferences.recent_themes if name in PALETTES],
        "ui_project_theme_overrides": {str(key): value for key, value in preferences.project_theme_overrides.items() if value in PALETTES},
        "ui_module_theme_overrides": {key: value for key, value in preferences.module_theme_overrides.items() if key in PAGE_BY_KEY and value in PALETTES},
        "ui_custom_theme_tokens": sanitise_custom_tokens(preferences.custom_theme_tokens),
        "ui_onboarding_dismissed": bool(preferences.onboarding_dismissed),
    }


def session_preferences() -> UiPreferences:
    init_ui_preferences()
    defaults = _ui_preference_defaults()
    return UiPreferences(
        palette=str(st.session_state.get("ui_palette", defaults["ui_palette"])),
        font_family=str(st.session_state.get("ui_font_family", defaults["ui_font_family"])),
        heading_font_family=str(
            st.session_state.get("ui_heading_font_family", defaults["ui_heading_font_family"])
        ),
        data_font_family=str(
            st.session_state.get("ui_data_font_family", defaults["ui_data_font_family"])
        ),
        typography_preset=str(
            st.session_state.get("ui_typography_preset", defaults["ui_typography_preset"])
        ),
        compact=str(st.session_state.get("ui_density_mode", defaults["ui_density_mode"])) == "Dense",
        density_mode=str(st.session_state.get("ui_density_mode", defaults["ui_density_mode"])),
        reduce_motion=bool(st.session_state.get("ui_reduce_motion", defaults["ui_reduce_motion"])),
        motion_mode=normalize_motion_mode(
            st.session_state.get("ui_motion_mode", defaults["ui_motion_mode"]),
            reduce_motion=bool(
                st.session_state.get("ui_reduce_motion", defaults["ui_reduce_motion"])
            ),
        ),
        reduce_effects=bool(
            st.session_state.get("ui_reduce_effects", defaults["ui_reduce_effects"])
        ),
        performance_mode=str(st.session_state.get("ui_performance_mode", defaults["ui_performance_mode"])),
        high_contrast=bool(st.session_state.get("ui_high_contrast", defaults["ui_high_contrast"])),
        appearance_mode=str(
            st.session_state.get("ui_appearance_mode", defaults["ui_appearance_mode"])
        ),
        font_scale=float(st.session_state.get("ui_font_scale", defaults["ui_font_scale"])),
        color_vision=str(st.session_state.get("ui_color_vision", defaults["ui_color_vision"])),
        language=str(st.session_state.get("ui_language", defaults["ui_language"])),
        apply_appearance_to_reports=bool(
            st.session_state.get(
                "ui_apply_appearance_to_reports", defaults["ui_apply_appearance_to_reports"]
            )
        ),
        report_style=str(st.session_state.get("ui_report_style", defaults["ui_report_style"])),
        favourites=list(st.session_state.get("ui_favourites", defaults["ui_favourites"])),
        recent_pages=list(st.session_state.get("ui_recent_pages", defaults["ui_recent_pages"])),
        theme_favourites=list(st.session_state.get("ui_theme_favourites", defaults["ui_theme_favourites"])),
        recent_themes=list(st.session_state.get("ui_recent_themes", defaults["ui_recent_themes"])),
        project_theme_overrides=dict(st.session_state.get("ui_project_theme_overrides", defaults["ui_project_theme_overrides"])),
        module_theme_overrides=dict(st.session_state.get("ui_module_theme_overrides", defaults["ui_module_theme_overrides"])),
        custom_theme_tokens=sanitise_custom_tokens(st.session_state.get("ui_custom_theme_tokens", defaults["ui_custom_theme_tokens"])),
        onboarding_dismissed=bool(
            st.session_state.get("ui_onboarding_dismissed", defaults["ui_onboarding_dismissed"])
        ),
    )


def persist_ui_preferences() -> Path:
    """Persist non-sensitive UI preferences to the local reports folder."""

    preferences = session_preferences()
    saved = save_preferences(PROJECT_ROOT, preferences)
    st.session_state["ui_preferences_saved_path"] = str(saved)
    return saved


def reset_ui_preferences() -> None:
    defaults = UiPreferences()
    st.session_state["ui_palette"] = defaults.palette
    st.session_state["ui_font_family"] = defaults.font_family
    st.session_state["ui_heading_font_family"] = defaults.heading_font_family
    st.session_state["ui_data_font_family"] = defaults.data_font_family
    st.session_state["ui_typography_preset"] = defaults.typography_preset
    st.session_state["ui_density_mode"] = defaults.density_mode
    st.session_state["ui_compact"] = defaults.compact
    st.session_state["ui_reduce_motion"] = defaults.reduce_motion
    st.session_state["ui_motion_mode"] = defaults.motion_mode
    st.session_state["ui_reduce_effects"] = defaults.reduce_effects
    st.session_state["ui_performance_mode"] = defaults.performance_mode
    st.session_state["ui_high_contrast"] = defaults.high_contrast
    st.session_state["ui_appearance_mode"] = defaults.appearance_mode
    st.session_state["ui_font_scale"] = defaults.font_scale
    st.session_state["ui_color_vision"] = defaults.color_vision
    st.session_state["ui_language"] = defaults.language
    st.session_state["ui_apply_appearance_to_reports"] = defaults.apply_appearance_to_reports
    st.session_state["ui_report_style"] = defaults.report_style
    st.session_state["ui_favourites"] = defaults.favourites
    st.session_state["ui_recent_pages"] = defaults.recent_pages
    st.session_state["ui_theme_favourites"] = defaults.theme_favourites
    st.session_state["ui_recent_themes"] = defaults.recent_themes
    st.session_state["ui_project_theme_overrides"] = defaults.project_theme_overrides
    st.session_state["ui_module_theme_overrides"] = defaults.module_theme_overrides
    st.session_state["ui_custom_theme_tokens"] = defaults.custom_theme_tokens
    st.session_state["ui_onboarding_dismissed"] = defaults.onboarding_dismissed
    persist_ui_preferences()


def init_ui_preferences() -> None:
    """Initialize and self-heal UI state on every page execution.

    Do not return early solely because a loaded flag exists: widget cleanup during
    multipage navigation can remove one or more preference keys while preserving
    that flag.  Missing keys are restored without overwriting live widget values.
    """

    try:
        stored = load_preferences(PROJECT_ROOT)
    except Exception:
        stored = UiPreferences()
    defaults = _ui_preference_defaults(stored)
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    st.session_state["ui_preferences_loaded"] = True


def _current_palette() -> Palette:
    init_ui_preferences()
    selected = str(st.session_state.get("ui_palette", DEFAULT_THEME))
    project_key = str(st.session_state.get("active_project_name") or st.session_state.get("active_project") or "").strip()
    project_overrides = st.session_state.get("ui_project_theme_overrides", {})
    if project_key and isinstance(project_overrides, dict) and project_overrides.get(project_key) in PALETTES:
        selected = str(project_overrides[project_key])
    module_key = current_page_key()
    module_overrides = st.session_state.get("ui_module_theme_overrides", {})
    if module_key and isinstance(module_overrides, dict) and module_overrides.get(module_key) in PALETTES:
        selected = str(module_overrides[module_key])
    return PALETTES.get(selected, PALETTES[DEFAULT_THEME])


def _current_font() -> FontSpec:
    init_ui_preferences()
    return FONTS.get(
        st.session_state.get("ui_font_family", DEFAULT_FONT),
        FONTS[DEFAULT_FONT],
    )


def _current_typography() -> tuple[FontSpec, FontSpec, FontSpec]:
    """Return heading, body and data fonts with preset-aware safe fallbacks."""

    init_ui_preferences()
    preset_name = str(st.session_state.get("ui_typography_preset", "Modern Professional"))
    preset = pairing_for(preset_name)
    body_name = str(st.session_state.get("ui_font_family", preset.body_font))
    heading_name = str(st.session_state.get("ui_heading_font_family", preset.heading_font))
    data_name = str(st.session_state.get("ui_data_font_family", preset.data_font))
    return (
        FONTS.get(heading_name, FONTS[DEFAULT_FONT]),
        FONTS.get(body_name, FONTS[DEFAULT_FONT]),
        FONTS.get(data_name, FONTS[DEFAULT_FONT]),
    )


def _apply_plotly_template(palette: Palette, font: FontSpec | None = None) -> None:
    font = font or _current_font()
    color_vision = str(st.session_state.get("ui_color_vision", "Standard"))
    signature_colorway = (
        ["#3B82F6", "#22D3EE", "#22C55E", "#F59E0B", "#EF4444", "#8B5CF6", "#94A3B8"]
        if palette.name == "BioIntel Signature"
        else [palette.primary, palette.secondary, palette.accent, "#F59E0B", "#FB7185", "#A78BFA"]
    )
    colorways = {
        "Standard": signature_colorway,
        "Deuteranopia": ["#0072B2", "#E69F00", "#56B4E9", "#D55E00", "#CC79A7", "#000000"],
        "Tritanopia": ["#D55E00", "#009E73", "#F0E442", "#CC79A7", "#0072B2", "#111827"],
        "Monochrome": ["#F8FAFC", "#CBD5E1", "#94A3B8", "#64748B", "#475569", "#1E293B"],
    }
    appearance_mode = str(st.session_state.get("ui_appearance_mode", "Dark"))
    motion_mode = normalize_motion_mode(
        st.session_state.get("ui_motion_mode", "Balanced"),
        reduce_motion=bool(st.session_state.get("ui_reduce_motion", False)),
    )
    light = appearance_mode == "Light"
    text_color = "#172033" if light else "#DCE4F0"
    title_color = "#0F172A" if light else "#F8FAFC"
    experience = experience_for(palette.name)
    profile = chart_profile_for(palette.name)
    primary_rgb = tuple(int(palette.primary[index : index + 2], 16) for index in (1, 3, 5))
    grid_color = (
        f"rgba(71,85,105,{profile.grid_alpha:.3f})"
        if light
        else f"rgba({primary_rgb[0]},{primary_rgb[1]},{primary_rgb[2]},{profile.grid_alpha:.3f})"
    )
    grid_width = profile.axis_width
    legend_orientation = profile.legend_orientation
    legend_y = profile.legend_y
    plot_bg = f"rgba(2,6,23,{profile.plot_alpha:.3f})" if not light else "rgba(255,255,255,0)"
    template_name = "biointel_step33"
    pio.templates[template_name] = go.layout.Template(
        layout={
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor": plot_bg,
            "transition": plotly_transition_for(motion_mode),
            "font": {
                "color": text_color,
                "family": font.plotly_family,
            },
            "title": {
                "font": {
                    "color": title_color,
                    "size": (
                        19
                        if experience.archetype in {"Futuristic technology", "Scientific terminal"}
                        else 18
                    ),
                }
            },
            "xaxis": {
                "gridcolor": grid_color,
                "gridwidth": grid_width,
                "griddash": profile.grid_dash,
                "zerolinecolor": "rgba(148,163,184,0.16)",
                "linecolor": "rgba(148,163,184,0.18)",
            },
            "yaxis": {
                "gridcolor": grid_color,
                "gridwidth": grid_width,
                "griddash": profile.grid_dash,
                "zerolinecolor": "rgba(148,163,184,0.16)",
                "linecolor": "rgba(148,163,184,0.18)",
            },
            "colorway": colorways.get(color_vision, colorways["Standard"]),
            "legend": {
                "bgcolor": "rgba(0,0,0,0)",
                "font": {"color": text_color},
                "orientation": legend_orientation,
                "y": legend_y,
            },
            "hoverlabel": {
                "bgcolor": "#111827",
                "bordercolor": profile.hover_border,
                "font": {"color": "#F8FAFC"},
            },
            "margin": {
                "l": 36,
                "r": 24,
                "t": 58,
                "b": 36,
            },
        }
    )
    pio.templates.default = template_name


def _peak_visual_allowed(container, figure_or_data: object, revision: str) -> bool:
    """Prevent blank scientific canvases on only the selected peak domains."""

    page_key = current_page_key() or ""
    page = PAGE_BY_KEY.get(page_key)
    if page is None or not bool(st.session_state.get("_bio_peak_mode_active", True)):
        return True
    try:
        from biointel.peak_potential.catalog import is_peak_target
        from biointel.peak_potential.quality import audit_plotly_figure

        if not is_peak_target(page_key=page.key, category=page.category, title=page.title):
            return True
        audit = audit_plotly_figure(figure_or_data)
        visual_audits = dict(st.session_state.get("_bio_peak_visual_audits", {}) or {})
        visual_audits[str(revision)] = audit.to_dict()
        st.session_state["_bio_peak_visual_audits"] = visual_audits
        if audit.has_data:
            return True
        container.info(
            "No drawable values are available for this visual. Adjust filters or inspect the underlying table; "
            "BioIntel has suppressed the blank canvas rather than showing a misleading chart."
        )
        return False
    except Exception:
        # The safeguard itself must never interrupt a scientific module.
        return True


def _install_plotly_motion_adapter() -> None:
    """Apply motion policy to every Streamlit Plotly surface.

    The adapter preserves camera/zoom state and disables transitions for large
    figures or reduced-motion sessions. It is defensive so unsupported figure
    payloads continue through Streamlit unchanged.
    """

    if not getattr(st, "_biointel_plotly_motion_installed", False):
        original = st.plotly_chart

        def motion_aware_plotly_chart(figure_or_data, *args, **kwargs):
            mode = normalize_motion_mode(
                st.session_state.get("ui_motion_mode", "Balanced"),
                reduce_motion=bool(st.session_state.get("ui_reduce_motion", False)),
            )
            revision = str(kwargs.get("key") or "biointel-view")
            configure_figure_motion(
                figure_or_data,
                mode=mode,
                preserve_view=True,
                revision_key=revision,
            )
            config = dict(kwargs.get("config") or {})
            config.setdefault("displaylogo", False)
            config.setdefault("responsive", True)
            config.setdefault(
                "toImageButtonOptions",
                {"format": "svg", "filename": revision.replace(" ", "_"), "scale": 2},
            )
            kwargs["config"] = config
            kwargs.setdefault("width", "stretch")
            if not _peak_visual_allowed(st, figure_or_data, revision):
                return None
            try:
                return original(figure_or_data, *args, **kwargs)
            except Exception as exc:
                from biointel.ui.visual_workspace import record_visual_error
                error_id = record_visual_error(
                    module_key=current_page_key() or "legacy_visual",
                    chart_key=revision,
                    error=exc,
                )
                st.error(f"This visual could not be rendered safely. Error ID: {error_id}")
                return None

        st.plotly_chart = motion_aware_plotly_chart
        st._biointel_plotly_motion_installed = True

    try:
        from streamlit.delta_generator import DeltaGenerator

        if not getattr(DeltaGenerator, "_biointel_plotly_motion_installed", False):
            original_method = DeltaGenerator.plotly_chart

            def motion_aware_delta_plotly(self, figure_or_data, *args, **kwargs):
                mode = normalize_motion_mode(
                    st.session_state.get("ui_motion_mode", "Balanced"),
                    reduce_motion=bool(st.session_state.get("ui_reduce_motion", False)),
                )
                revision = str(kwargs.get("key") or "biointel-view")
                configure_figure_motion(
                    figure_or_data,
                    mode=mode,
                    preserve_view=True,
                    revision_key=revision,
                )
                config = dict(kwargs.get("config") or {})
                config.setdefault("displaylogo", False)
                config.setdefault("responsive", True)
                config.setdefault(
                    "toImageButtonOptions",
                    {"format": "svg", "filename": revision.replace(" ", "_"), "scale": 2},
                )
                kwargs["config"] = config
                kwargs.setdefault("width", "stretch")
                if not _peak_visual_allowed(self, figure_or_data, revision):
                    return None
                try:
                    return original_method(self, figure_or_data, *args, **kwargs)
                except Exception as exc:
                    from biointel.ui.visual_workspace import record_visual_error
                    error_id = record_visual_error(
                        module_key=current_page_key() or "legacy_visual",
                        chart_key=revision,
                        error=exc,
                    )
                    self.error(f"This visual could not be rendered safely. Error ID: {error_id}")
                    return None

            DeltaGenerator.plotly_chart = motion_aware_delta_plotly
            DeltaGenerator._biointel_plotly_motion_installed = True
    except (AttributeError, ImportError):  # pragma: no cover - Streamlit compatibility.
        pass


def _peak_dataframe_for_display(container, data: object, revision: str) -> object:
    """Audit and safely normalize tables only inside the requested peak domains."""

    page_key = current_page_key() or ""
    page = PAGE_BY_KEY.get(page_key)
    if page is None or not bool(st.session_state.get("_bio_peak_mode_active", True)):
        return data
    try:
        import pandas as pd
        try:
            from pandas.io.formats.style import Styler
        except ImportError:  # pragma: no cover - pandas compatibility
            Styler = ()

        from biointel.peak_potential.catalog import is_peak_target
        from biointel.peak_potential.quality import audit_frame

        if not is_peak_target(page_key=page.key, category=page.category, title=page.title):
            return data
        existing_audits = dict(st.session_state.get("_bio_peak_frame_audits", {}) or {})
        if str(revision) in existing_audits:
            return data
        if Styler and isinstance(data, Styler):
            frame = data.data
            can_replace = False
        elif isinstance(data, pd.DataFrame):
            frame = data
            can_replace = True
        elif isinstance(data, pd.Series):
            frame = data.to_frame()
            can_replace = True
        elif isinstance(data, (list, tuple, dict)):
            try:
                frame = pd.DataFrame(data)
                can_replace = True
            except (TypeError, ValueError):
                return data
        else:
            return data

        audit = audit_frame(frame)
        audits = dict(st.session_state.get("_bio_peak_frame_audits", {}) or {})
        audits[str(revision)] = audit.to_dict()
        st.session_state["_bio_peak_frame_audits"] = audits

        notices = set(st.session_state.get("_bio_peak_table_notices", []) or [])
        if str(revision) not in notices and (audit.duplicate_columns or audit.infinite_cells):
            if audit.duplicate_columns:
                container.warning(
                    "Duplicate table columns were renamed for safe display and remain a scientific export blocker."
                )
            if audit.infinite_cells:
                container.warning(
                    f"{audit.infinite_cells:,} non-finite values were detected in audited rows and are shown as missing."
                )
            notices.add(str(revision))
            st.session_state["_bio_peak_table_notices"] = sorted(notices)

        if not can_replace:
            return data
        display = frame.copy(deep=False)
        if display.columns.duplicated().any():
            counts: dict[str, int] = {}
            names: list[str] = []
            for raw in map(str, display.columns):
                count = counts.get(raw, 0)
                counts[raw] = count + 1
                names.append(raw if count == 0 else f"{raw}__{count + 1}")
            display = display.copy()
            display.columns = names
        if audit.infinite_cells:
            display = display.replace([float("inf"), float("-inf")], pd.NA)
        from biointel.ui.performance import bounded_frame_for_display
        display, display_profile = bounded_frame_for_display(display)
        if display_profile.get("sampled") and f"sample:{revision}" not in notices:
            container.info(
                f"Interactive table sampled {display_profile['display_rows']:,} evenly-spaced rows from "
                f"{display_profile['source_rows']:,} total rows to protect memory. Full data remains available in exports."
            )
            notices.add(f"sample:{revision}")
            st.session_state["_bio_peak_table_notices"] = sorted(notices)
        return display
    except Exception:
        # The table safeguard itself must never break a scientific module.
        return data


def _install_peak_dataframe_adapter() -> None:
    """Collect bounded table audits and prevent duplicate-column Arrow failures."""

    if not getattr(st, "_biointel_peak_dataframe_installed", False):
        original = st.dataframe

        def peak_aware_dataframe(data=None, *args, **kwargs):
            audits = dict(st.session_state.get("_bio_peak_frame_audits", {}) or {})
            revision = str(kwargs.get("key") or f"table_{len(audits) + 1}")
            safe_data = _peak_dataframe_for_display(st, data, revision)
            from biointel.ui.public_branding import brand_public_value
            safe_data = brand_public_value(safe_data, allow_legal=_public_branding_legal_view())
            try:
                return original(safe_data, *args, **kwargs)
            except Exception as exc:
                from biointel.peak_potential.quality import stable_error_id

                error_id = stable_error_id(exc, module_key=current_page_key() or "table")
                st.error(f"This table could not be rendered safely · {error_id}")
                return None

        st.dataframe = peak_aware_dataframe
        st._biointel_peak_dataframe_installed = True

    try:
        from streamlit.delta_generator import DeltaGenerator

        if not getattr(DeltaGenerator, "_biointel_peak_dataframe_installed", False):
            original_method = DeltaGenerator.dataframe

            def peak_aware_delta_dataframe(self, data=None, *args, **kwargs):
                audits = dict(st.session_state.get("_bio_peak_frame_audits", {}) or {})
                revision = str(kwargs.get("key") or f"table_{len(audits) + 1}")
                safe_data = _peak_dataframe_for_display(self, data, revision)
                from biointel.ui.public_branding import brand_public_value
                safe_data = brand_public_value(safe_data, allow_legal=_public_branding_legal_view())
                try:
                    return original_method(self, safe_data, *args, **kwargs)
                except Exception as exc:
                    from biointel.peak_potential.quality import stable_error_id

                    error_id = stable_error_id(exc, module_key=current_page_key() or "table")
                    self.error(f"This table could not be rendered safely · {error_id}")
                    return None

            DeltaGenerator.dataframe = peak_aware_delta_dataframe
            DeltaGenerator._biointel_peak_dataframe_installed = True
    except (AttributeError, ImportError):  # pragma: no cover - Streamlit compatibility.
        pass



def _public_branding_legal_view() -> bool:
    """Allow upstream identities only inside the dedicated legal notice page."""

    return current_page_key() == "engine_license_compliance"


def _install_public_branding_adapter() -> None:
    """Apply BioIntel public names to normal Streamlit product surfaces.

    Runtime identifiers remain untouched because the adapter transforms display
    arguments immediately before rendering. The legal notice page is exempt so
    required upstream names, licences and source references remain accessible.
    """

    from functools import wraps

    from biointel.ui.public_branding import (
        brand_download_payload,
        brand_public_text,
        brand_public_value,
    )

    if getattr(st, "_biointel_public_branding_installed", False):
        return

    text_methods = {
        "title", "header", "subheader", "caption", "text", "info", "warning",
        "error", "success", "toast", "code", "json", "table",
    }
    label_methods = {
        "button", "form_submit_button", "checkbox", "toggle", "text_input",
        "text_area", "number_input", "slider", "select_slider", "date_input",
        "time_input", "color_picker", "file_uploader", "link_button", "popover",
        "status", "chat_input",
    }
    choice_methods = {"selectbox", "multiselect", "radio"}

    def install(owner, name: str, *, method: bool) -> None:
        original = getattr(owner, name, None)
        if original is None or getattr(original, "_biointel_public_branding_wrapper", False):
            return

        @wraps(original)
        def wrapped(*call_args, **call_kwargs):
            allow_legal = _public_branding_legal_view()
            args = list(call_args)
            offset = 1 if method else 0

            def transform_index(index: int) -> None:
                if len(args) > index:
                    args[index] = brand_public_value(args[index], allow_legal=allow_legal)

            for key in ("label", "help", "placeholder"):
                if key in call_kwargs:
                    call_kwargs[key] = brand_public_text(call_kwargs[key], allow_legal=allow_legal)

            if name == "markdown":
                body_value = args[offset] if len(args) > offset else call_kwargs.get("body")
                is_large_style = isinstance(body_value, str) and (
                    body_value.lstrip().startswith("<style") or len(body_value) > 50000
                )
                if not is_large_style:
                    transform_index(offset)
                    if "body" in call_kwargs:
                        call_kwargs["body"] = brand_public_text(call_kwargs["body"], allow_legal=allow_legal)
            elif name == "write":
                for index in range(offset, len(args)):
                    transform_index(index)
            elif name == "metric":
                for index in range(offset, min(len(args), offset + 3)):
                    transform_index(index)
                for key in ("label", "value", "delta", "help"):
                    if key in call_kwargs:
                        call_kwargs[key] = brand_public_value(call_kwargs[key], allow_legal=allow_legal)
            elif name == "tabs":
                transform_index(offset)
            elif name == "expander":
                transform_index(offset)
            elif name in choice_methods:
                transform_index(offset)
                original_format = call_kwargs.get("format_func")
                if original_format is None:
                    call_kwargs["format_func"] = lambda option: str(
                        brand_public_text(str(option), allow_legal=_public_branding_legal_view())
                    )
                else:
                    call_kwargs["format_func"] = lambda option, fn=original_format: str(
                        brand_public_text(fn(option), allow_legal=_public_branding_legal_view())
                    )
            elif name == "download_button":
                transform_index(offset)
                data_index = offset + 1
                mime = call_kwargs.get("mime")
                if len(args) > data_index:
                    args[data_index] = brand_download_payload(args[data_index], mime=mime, allow_legal=allow_legal)
                elif "data" in call_kwargs:
                    call_kwargs["data"] = brand_download_payload(call_kwargs["data"], mime=mime, allow_legal=allow_legal)
            elif name in text_methods or name in label_methods:
                transform_index(offset)
                if "body" in call_kwargs:
                    call_kwargs["body"] = brand_public_value(call_kwargs["body"], allow_legal=allow_legal)
            elif name == "data_editor":
                transform_index(offset)

            return original(*args, **call_kwargs)

        wrapped._biointel_public_branding_wrapper = True
        setattr(owner, name, wrapped)

    module_methods = text_methods | label_methods | choice_methods | {
        "markdown", "write", "metric", "tabs", "expander", "download_button", "data_editor"
    }
    for method_name in sorted(module_methods):
        install(st, method_name, method=False)

    try:
        from streamlit.delta_generator import DeltaGenerator

        for method_name in sorted(module_methods):
            install(DeltaGenerator, method_name, method=True)
        DeltaGenerator._biointel_public_branding_installed = True
    except (AttributeError, ImportError):  # pragma: no cover - Streamlit compatibility.
        pass

    st._biointel_public_branding_installed = True


def _install_branded_page_link_adapter() -> None:
    """Remove legacy emoji arguments from every Streamlit page link at runtime.

    Older protected pages keep their byte-identical source, while the shared
    shell guarantees that navigation renders the BioIntel vector-icon system
    instead of operating-system emoji glyphs.
    """

    if not getattr(st, "_biointel_branded_page_link_installed", False):
        original = st.page_link

        def branded_page_link(page, *args, **kwargs):
            from biointel.ui.public_branding import brand_public_text
            kwargs.pop("icon", None)
            if "label" in kwargs:
                kwargs["label"] = brand_public_text(kwargs["label"], allow_legal=_public_branding_legal_view())
            elif args:
                args = (brand_public_text(args[0], allow_legal=_public_branding_legal_view()), *args[1:])
            return original(page, *args, **kwargs)

        st.page_link = branded_page_link
        st._biointel_branded_page_link_installed = True

    try:
        from streamlit.delta_generator import DeltaGenerator

        if not getattr(DeltaGenerator, "_biointel_branded_page_link_installed", False):
            original_method = DeltaGenerator.page_link

            def branded_delta_page_link(self, page, *args, **kwargs):
                from biointel.ui.public_branding import brand_public_text
                kwargs.pop("icon", None)
                if "label" in kwargs:
                    kwargs["label"] = brand_public_text(kwargs["label"], allow_legal=_public_branding_legal_view())
                elif args:
                    args = (brand_public_text(args[0], allow_legal=_public_branding_legal_view()), *args[1:])
                return original_method(self, page, *args, **kwargs)

            DeltaGenerator.page_link = branded_delta_page_link
            DeltaGenerator._biointel_branded_page_link_installed = True
    except (AttributeError, ImportError):  # pragma: no cover - Streamlit compatibility.
        pass


@st.cache_data(ttl=300, show_spinner=False)
def _cached_workspace_health(root_text: str) -> dict[str, object]:
    try:
        return all_database_health(Path(root_text))
    except Exception as exc:  # UI must still render when a database is unavailable.
        return {"database_count": 0, "healthy_count": 0, "health_percent": 0.0, "error": str(exc)}


def apply_theme() -> None:
    """Apply the professional visual system and enforce production UI access."""

    from biointel.ui.runtime_guard import install_runtime_guard

    install_runtime_guard()
    init_ui_preferences()
    from biointel.ui.access_control import require_ui_access

    require_ui_access()
    st.session_state["_biointel_legal_notice_view"] = _public_branding_legal_view()
    palette = _current_palette()
    heading_font, font, data_font = _current_typography()
    plotly_signature = (
        palette.name,
        data_font.name,
        str(st.session_state.get("ui_appearance_mode", "Dark")),
        str(st.session_state.get("ui_color_vision", "Standard")),
        str(st.session_state.get("ui_motion_mode", "Balanced")),
    )
    if st.session_state.get("_bio_plotly_template_signature") != plotly_signature:
        _apply_plotly_template(palette, data_font)
        st.session_state["_bio_plotly_template_signature"] = plotly_signature
    _install_public_branding_adapter()
    _install_plotly_motion_adapter()
    _install_peak_dataframe_adapter()
    _install_branded_page_link_adapter()
    density_mode = str(st.session_state.get("ui_density_mode", "Professional"))
    if density_mode not in DENSITY_MODES:
        density_mode = "Professional"
    compact = density_mode == "Dense"
    st.session_state["ui_compact"] = compact
    performance_mode = str(st.session_state.get("ui_performance_mode", "Adaptive"))
    if performance_mode not in PERFORMANCE_MODES:
        performance_mode = "Adaptive"
    reduce_motion = bool(st.session_state.get("ui_reduce_motion"))
    motion_mode = normalize_motion_mode(
        st.session_state.get("ui_motion_mode", "Balanced"),
        reduce_motion=reduce_motion,
    )
    st.session_state["ui_motion_mode"] = motion_mode
    st.session_state["ui_reduce_motion"] = motion_mode == "Reduced"
    reduce_motion = motion_mode == "Reduced"
    reduce_effects = bool(st.session_state.get("ui_reduce_effects")) or performance_mode == "Performance"
    if performance_mode == "Full quality":
        reduce_effects = False
    high_contrast = bool(st.session_state.get("ui_high_contrast"))
    appearance_mode = str(st.session_state.get("ui_appearance_mode", "Dark"))
    font_scale = float(st.session_state.get("ui_font_scale", 1.0))
    content_padding = "1.35rem" if compact else "2.25rem"
    root_font_size = f"{font_scale:.2f}rem"
    card_padding = "0.95rem" if compact else "1.25rem"
    border_alpha = "0.28" if high_contrast else "0.16"
    text_muted = "#D1D5DB" if high_contrast else palette.muted
    animation_css = """
    @keyframes bioSlideUpFade {
        0% { opacity: 0; transform: translateY(18px) scale(0.985); }
        100% { opacity: 1; transform: translateY(0) scale(1); }
    }

    @keyframes bioPulseGlow {
        0%, 100% { box-shadow: 0 10px 30px -10px var(--bio-glow); border-color: var(--bio-border); }
        50% { box-shadow: 0 20px 45px -8px var(--bio-glow); border-color: var(--bio-primary); }
    }

    .bio-card, .bio-kpi, .bio-hero, [data-testid="stMetric"], [data-testid="stExpander"] {
        animation: bioSlideUpFade 0.45s cubic-bezier(0.16, 1, 0.3, 1) both;
        transition: transform 0.28s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.28s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.28s ease-out !important;
    }

    .bio-card:hover, .bio-kpi:hover, [data-testid="stMetric"]:hover {
        transform: translateY(-4px) scale(1.008) !important;
        box-shadow: 0 20px 50px -12px var(--bio-glow), 0 0 0 1px var(--bio-primary) !important;
        border-color: var(--bio-primary) !important;
    }

    .stButton > button, .stDownloadButton > button {
        transition: all 0.22s cubic-bezier(0.34, 1.56, 0.64, 1) !important;
    }

    .stButton > button:hover, .stDownloadButton > button:hover {
        transform: translateY(-2px) scale(1.03) !important;
        box-shadow: 0 12px 28px -6px var(--bio-glow) !important;
    }
    """ if not reduce_motion else ""


    st.markdown(
        f"""
        <style>
        :root {{
            font-size: {root_font_size};
            --bio-primary: {palette.primary};
            --bio-secondary: {palette.secondary};
            --bio-accent: {palette.accent};
            --bio-glow: {palette.glow};
            --bio-bg: {palette.bg_start};
            --bio-bg-soft: {palette.bg_soft};
            --bio-surface: {palette.surface};
            --bio-surface-strong: {palette.surface_strong};
            --bio-font-family: {font.css_stack};
            --bio-heading-font: {heading_font.css_stack};
            --bio-body-font: {font.css_stack};
            --bio-data-font: {data_font.css_stack};
            --bio-border: rgba(148, 163, 184, {border_alpha});
            --bio-text: {palette.text};
            --bio-muted: {text_muted};
            --bio-success: #34D399;
            --bio-warning: #FBBF24;
            --bio-danger: #FB7185;
            --bio-radius-xl: 24px;
            --bio-radius-lg: 18px;
            --bio-radius-md: 13px;
            --bio-shadow: 0 24px 80px rgba(2, 6, 23, 0.52);
        }}

        html, body, [class*="css"], .stMarkdown, label, button, input, textarea, select {{
            font-family: var(--bio-body-font);
        }}
        h1,h2,h3,h4,h5,h6,.bio-hero-title,.bio-card-title,.bio-section-label,.bio-shell-title {{
            font-family: var(--bio-heading-font);
        }}
        code, pre, kbd, samp {{
            font-family: var(--bio-data-font);
        }}

        .stApp {{
            color: var(--bio-text);
            background:
                radial-gradient(
                    circle at 10% 0%,
                    color-mix(in srgb, var(--bio-primary) 22%, transparent),
                    transparent 34%
                ),
                radial-gradient(
                    circle at 92% 10%,
                    color-mix(in srgb, var(--bio-secondary) 18%, transparent),
                    transparent 32%
                ),
                radial-gradient(
                    circle at 50% 100%,
                    color-mix(in srgb, var(--bio-accent) 11%, transparent),
                    transparent 34%
                ),
                linear-gradient(145deg, {palette.bg_start} 0%, {palette.bg_mid} 48%, {palette.bg_end} 100%);
            background-attachment: scroll;
        }}

        .main .block-container {{
            max-width: 1440px;
            padding-top: 1.25rem;
            padding-bottom: 4rem;
            padding-left: {content_padding};
            padding-right: {content_padding};
        }}

        [data-testid="stHeader"] {{
            background: rgba(5, 8, 20, 0.46);
            backdrop-filter: blur(18px);
            border-bottom: 1px solid rgba(148, 163, 184, 0.08);
        }}

        [data-testid="stSidebar"] {{
            background:
                linear-gradient(
                    180deg,
                    {palette.sidebar_start},
                    {palette.sidebar_end}
                );
            border-right: 1px solid var(--bio-border);
        }}

        [data-testid="stSidebar"] > div:first-child {{
            padding-top: 0.7rem;
        }}

        [data-testid="stSidebarNav"] {{
            display: none !important;
        }}

        [data-testid="stSidebarNav"] a {{
            border-radius: 12px;
            margin: 0.14rem 0.45rem;
            padding: 0.56rem 0.72rem;
            color: #CBD5E1;
            transition:
                background 160ms ease,
                color 160ms ease,
                transform 160ms ease;
        }}

        [data-testid="stSidebarNav"] a:hover {{
            color: white;
            background:
                linear-gradient(
                    90deg,
                    color-mix(in srgb, var(--bio-primary) 22%, transparent),
                    color-mix(in srgb, var(--bio-secondary) 10%, transparent)
                );
            transform: translateX(3px);
        }}

        [data-testid="stSidebarNav"] a[aria-current="page"] {{
            color: white;
            background:
                linear-gradient(
                    105deg,
                    color-mix(in srgb, var(--bio-primary) 32%, transparent),
                    color-mix(in srgb, var(--bio-secondary) 20%, transparent)
                );
            border: 1px solid
                color-mix(in srgb, var(--bio-primary) 44%, transparent);
            box-shadow: 0 10px 34px var(--bio-glow);
        }}

        h1, h2, h3 {{
            color: var(--bio-text);
            letter-spacing: -0.025em;
        }}

        h1 {{
            font-size: clamp(2rem, 4vw, 3.55rem);
            line-height: 1.04;
        }}

        h2 {{
            margin-top: 1.3rem;
        }}

        p, label, .stMarkdown {{
            color: var(--bio-text);
        }}

        .bio-brand {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.45rem 0 1.05rem;
        }}

        .bio-brand-mark {{
            width: 42px;
            height: 42px;
            display: grid;
            place-items: center;
            border-radius: 14px;
            font-size: 1.25rem;
            background:
                linear-gradient(
                    135deg,
                    var(--bio-primary),
                    var(--bio-secondary)
                );
            box-shadow: 0 12px 34px var(--bio-glow);
        }}

        .bio-brand-title {{
            color: white;
            font-weight: 800;
            line-height: 1.05;
            font-size: 1.03rem;
        }}

        .bio-brand-subtitle {{
            color: var(--bio-muted);
            font-size: 0.74rem;
            margin-top: 0.2rem;
        }}

        .bio-hero {{
            position: relative;
            overflow: hidden;
            padding: clamp(1.45rem, 4vw, 2.55rem);
            margin: 0.4rem 0 1.4rem;
            border-radius: 28px;
            border: 1px solid var(--bio-border);
            background:
                linear-gradient(
                    135deg,
                    {palette.hero_start},
                    {palette.hero_end}
                );
            box-shadow: var(--bio-shadow);
            backdrop-filter: blur(24px);
        }}

        .bio-hero::before {{
            content: "";
            position: absolute;
            inset: -1px;
            pointer-events: none;
            background:
                radial-gradient(
                    circle at 90% 10%,
                    color-mix(in srgb, var(--bio-secondary) 30%, transparent),
                    transparent 30%
                ),
                radial-gradient(
                    circle at 10% 90%,
                    color-mix(in srgb, var(--bio-primary) 28%, transparent),
                    transparent 34%
                );
            opacity: 0.78;
        }}

        .bio-hero > * {{
            position: relative;
            z-index: 1;
        }}

        .bio-eyebrow {{
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.36rem 0.72rem;
            border-radius: 999px;
            color: #EDE9FE;
            background:
                color-mix(in srgb, var(--bio-primary) 20%, transparent);
            border: 1px solid
                color-mix(in srgb, var(--bio-primary) 36%, transparent);
            font-size: 0.76rem;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }}

        .bio-hero-title {{
            max-width: 920px;
            margin: 0.95rem 0 0.65rem;
            color: white;
            font-size: clamp(2rem, 5vw, 4rem);
            line-height: 1.02;
            font-weight: 900;
            letter-spacing: -0.055em;
        }}

        .bio-gradient-text {{
            color: transparent;
            background:
                linear-gradient(
                    95deg,
                    #FFFFFF 10%,
                    var(--bio-secondary) 52%,
                    var(--bio-accent) 100%
                );
            -webkit-background-clip: text;
            background-clip: text;
        }}

        .bio-hero-subtitle {{
            max-width: 880px;
            color: #BCC9DA;
            font-size: clamp(0.98rem, 2vw, 1.18rem);
            line-height: 1.7;
        }}

        .bio-chip-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-top: 1.1rem;
        }}

        .bio-chip {{
            padding: 0.42rem 0.72rem;
            border-radius: 999px;
            color: #E2E8F0;
            border: 1px solid var(--bio-border);
            background: rgba(15, 23, 42, 0.62);
            font-size: 0.78rem;
            font-weight: 700;
        }}

        .bio-card {{
            height: 100%;
            padding: {card_padding};
            border-radius: var(--bio-radius-lg);
            border: 1px solid var(--bio-border);
            background:
                linear-gradient(
                    145deg,
                    rgba(18, 27, 49, 0.82),
                    rgba(10, 17, 32, 0.72)
                );
            box-shadow: 0 16px 44px rgba(2, 6, 23, 0.28);
            backdrop-filter: blur(18px);
        }}

        .bio-card:hover {{
            border-color:
                color-mix(in srgb, var(--bio-primary) 48%, transparent);
            transform: translateY(-2px);
            box-shadow: 0 22px 54px rgba(2, 6, 23, 0.42);
        }}

        .bio-card-icon {{
            width: 42px;
            height: 42px;
            display: grid;
            place-items: center;
            border-radius: 13px;
            margin-bottom: 0.85rem;
            background:
                linear-gradient(
                    135deg,
                    color-mix(in srgb, var(--bio-primary) 44%, transparent),
                    color-mix(in srgb, var(--bio-secondary) 30%, transparent)
                );
            border: 1px solid var(--bio-border);
            font-size: 1.15rem;
        }}

        .bio-card-kicker {{ color: var(--bio-secondary); font-size: .68rem; font-weight: 800; letter-spacing: .14em; text-transform: uppercase; margin-bottom: .45rem; }}
        .bio-card-title {{
            color: white;
            font-weight: 820;
            font-size: 1rem;
            margin-bottom: 0.35rem;
        }}

        .bio-card-copy {{
            color: var(--bio-muted);
            line-height: 1.55;
            font-size: 0.88rem;
        }}

        .bio-section-label {{
            display: flex;
            align-items: center;
            gap: 0.55rem;
            margin: 1.6rem 0 0.85rem;
            color: white;
            font-size: 1.16rem;
            font-weight: 850;
            letter-spacing: -0.02em;
        }}

        .bio-section-label::after {{
            content: "";
            height: 1px;
            flex: 1;
            background:
                linear-gradient(
                    90deg,
                    var(--bio-border),
                    transparent
                );
        }}

        .bio-badge {{
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.32rem 0.58rem;
            border-radius: 999px;
            font-size: 0.72rem;
            font-weight: 800;
            border: 1px solid var(--bio-border);
            background: rgba(15, 23, 42, 0.65);
        }}

        .bio-badge-success {{
            color: #A7F3D0;
            border-color: rgba(52, 211, 153, 0.30);
            background: rgba(16, 185, 129, 0.12);
        }}

        .bio-badge-warning {{
            color: #FDE68A;
            border-color: rgba(251, 191, 36, 0.30);
            background: rgba(245, 158, 11, 0.12);
        }}

        .bio-badge-danger {{
            color: #FECDD3;
            border-color: rgba(251, 113, 133, 0.30);
            background: rgba(244, 63, 94, 0.12);
        }}

        .bio-empty {{
            text-align: center;
            padding: 2rem 1.2rem;
            border: 1px dashed rgba(148, 163, 184, 0.28);
            border-radius: var(--bio-radius-lg);
            background: rgba(15, 23, 42, 0.48);
        }}

        .bio-empty-icon {{
            font-size: 2rem;
            margin-bottom: 0.45rem;
        }}

        .bio-empty-title {{
            color: white;
            font-weight: 800;
            margin-bottom: 0.25rem;
        }}

        .bio-empty-copy {{
            color: var(--bio-muted);
        }}

        [data-testid="stMetric"] {{
            padding: 1rem 1.05rem;
            border-radius: var(--bio-radius-lg);
            border: 1px solid var(--bio-border);
            background:
                linear-gradient(
                    145deg,
                    rgba(16, 25, 47, 0.86),
                    rgba(9, 15, 29, 0.76)
                );
            box-shadow: 0 15px 42px rgba(2, 6, 23, 0.26);
        }}

        [data-testid="stMetricLabel"] {{
            color: var(--bio-muted);
            font-weight: 700;
        }}

        [data-testid="stMetricValue"] {{
            color: white;
            font-weight: 880;
            letter-spacing: -0.04em;
        }}

        div[data-testid="stForm"],
        [data-testid="stExpander"],
        [data-testid="stDataFrame"],
        [data-testid="stTable"] {{
            border-radius: var(--bio-radius-lg);
            border: 1px solid var(--bio-border);
            background: rgba(10, 17, 32, 0.70);
            box-shadow: 0 14px 40px rgba(2, 6, 23, 0.22);
            overflow: hidden;
        }}

        div[data-testid="stForm"] {{
            padding: 1rem;
        }}

        [data-baseweb="tab-list"] {{
            gap: 0.45rem;
            padding: 0.35rem;
            border-radius: 15px;
            background: rgba(7, 12, 25, 0.72);
            border: 1px solid var(--bio-border);
        }}

        [data-baseweb="tab"] {{
            border-radius: 11px;
            color: #A8B4C5;
            font-weight: 750;
            padding: 0.5rem 0.86rem;
        }}

        [aria-selected="true"][data-baseweb="tab"] {{
            color: white;
            background:
                linear-gradient(
                    105deg,
                    color-mix(in srgb, var(--bio-primary) 32%, transparent),
                    color-mix(in srgb, var(--bio-secondary) 20%, transparent)
                );
        }}

        .stButton > button,
        .stDownloadButton > button,
        [data-testid="stLinkButton"] a {{
            min-height: 2.65rem;
            border-radius: 13px;
            border: 1px solid var(--bio-border);
            color: #F8FAFC;
            font-weight: 800;
            background:
                linear-gradient(
                    135deg,
                    rgba(30, 41, 69, 0.94),
                    rgba(17, 24, 43, 0.94)
                );
            box-shadow: 0 10px 30px rgba(2, 6, 23, 0.26);
            transition:
                transform 150ms ease,
                box-shadow 150ms ease,
                border-color 150ms ease;
        }}

        .stButton > button:hover,
        .stDownloadButton > button:hover,
        [data-testid="stLinkButton"] a:hover {{
            transform: translateY(-1px);
            border-color:
                color-mix(in srgb, var(--bio-secondary) 58%, transparent);
            box-shadow: 0 16px 38px var(--bio-glow);
        }}

        .stButton > button[kind="primary"],
        .stDownloadButton > button[kind="primary"] {{
            border-color: transparent;
            background:
                linear-gradient(
                    110deg,
                    var(--bio-primary),
                    var(--bio-secondary)
                );
            box-shadow: 0 14px 38px var(--bio-glow);
        }}

        [data-baseweb="input"] > div,
        [data-baseweb="select"] > div,
        textarea,
        input {{
            border-radius: 12px !important;
        }}

        [data-baseweb="input"] > div,
        [data-baseweb="select"] > div,
        [data-testid="stTextArea"] textarea {{
            color: white;
            background: rgba(7, 12, 25, 0.78);
            border-color: var(--bio-border);
        }}

        [data-testid="stFileUploaderDropzone"] {{
            border-radius: var(--bio-radius-lg);
            border: 1px dashed
                color-mix(in srgb, var(--bio-secondary) 42%, transparent);
            background:
                linear-gradient(
                    135deg,
                    rgba(14, 23, 43, 0.68),
                    rgba(8, 14, 28, 0.68)
                );
        }}

        [data-testid="stAlert"] {{
            border-radius: 15px;
            border: 1px solid var(--bio-border);
            backdrop-filter: blur(14px);
        }}

        [data-testid="stPlotlyChart"] {{
            padding: 0.35rem;
            border-radius: var(--bio-radius-lg);
            border: 1px solid var(--bio-border);
            background: rgba(8, 14, 27, 0.54);
        }}

        code {{
            color: #C4B5FD;
            border-radius: 6px;
        }}

        ::-webkit-scrollbar {{
            width: 10px;
            height: 10px;
        }}

        ::-webkit-scrollbar-track {{
            background: #070B16;
        }}

        ::-webkit-scrollbar-thumb {{
            border: 2px solid #070B16;
            border-radius: 999px;
            background:
                linear-gradient(
                    var(--bio-primary),
                    var(--bio-secondary)
                );
        }}

        .stApp::before {{
            content: "";
            position: fixed;
            inset: 0;
            pointer-events: none;
            opacity: 0.035;
            z-index: 0;
            background-image:
                url("data:image/svg+xml,%3Csvg viewBox='0 0 180 180' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.82' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.72'/%3E%3C/svg%3E");
        }}

        :focus-visible {{
            outline: 3px solid
                color-mix(in srgb, var(--bio-secondary) 74%, white);
            outline-offset: 3px;
            border-radius: 8px;
        }}

        [data-testid="stProgressBar"] > div > div > div {{
            background:
                linear-gradient(
                    90deg,
                    var(--bio-primary),
                    var(--bio-secondary),
                    var(--bio-accent)
                );
        }}

        [data-testid="stToggle"] label,
        [data-testid="stRadio"] label {{
            color: #DCE4F0;
        }}

        .bio-sidebar-dock {{
            margin: 0.55rem 0.45rem 0.2rem;
            padding: 0.72rem;
            border-radius: 15px;
            border: 1px solid var(--bio-border);
            background:
                linear-gradient(
                    145deg,
                    rgba(18, 27, 49, 0.78),
                    rgba(8, 14, 28, 0.72)
                );
        }}

        .bio-sidebar-dock-title {{
            color: white;
            font-weight: 850;
            font-size: 0.78rem;
            margin-bottom: 0.15rem;
        }}

        .bio-sidebar-dock-copy {{
            color: var(--bio-muted);
            font-size: 0.68rem;
            line-height: 1.4;
        }}

        .bio-local-pill {{
            display: inline-flex;
            align-items: center;
            gap: 0.36rem;
            margin: 0.55rem 0.45rem;
            padding: 0.34rem 0.58rem;
            border-radius: 999px;
            color: #A7F3D0;
            border: 1px solid rgba(52, 211, 153, 0.24);
            background: rgba(16, 185, 129, 0.10);
            font-size: 0.67rem;
            font-weight: 800;
        }}

        .bio-board {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.85rem;
            margin: 0.9rem 0 1.25rem;
        }}

        .bio-kpi {{
            position: relative;
            overflow: hidden;
            padding: 1.05rem 1.1rem;
            min-height: 126px;
            border-radius: 17px;
            border: 1px solid var(--bio-border);
            background:
                linear-gradient(
                    150deg,
                    rgba(17, 28, 52, 0.92),
                    rgba(8, 15, 30, 0.78)
                );
            box-shadow: 0 18px 50px rgba(2, 6, 23, 0.30);
        }}

        .bio-kpi::after {{
            content: "";
            position: absolute;
            width: 86px;
            height: 86px;
            border-radius: 999px;
            right: -28px;
            bottom: -32px;
            background:
                color-mix(in srgb, var(--bio-primary) 22%, transparent);
            filter: blur(2px);
        }}

        .bio-kpi-label {{
            color: var(--bio-muted);
            font-size: 0.72rem;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }}

        .bio-kpi-value {{
            margin-top: 0.62rem;
            color: white;
            font-size: clamp(1.55rem, 3vw, 2.25rem);
            line-height: 1;
            font-weight: 900;
            letter-spacing: -0.055em;
        }}

        .bio-kpi-copy {{
            margin-top: 0.5rem;
            color: #AEBED2;
            font-size: 0.76rem;
            line-height: 1.45;
        }}

        .bio-status-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.48rem;
            margin: 0.65rem 0 0.9rem;
        }}

        .bio-status-chip {{
            display: inline-flex;
            align-items: center;
            gap: 0.38rem;
            padding: 0.38rem 0.62rem;
            border-radius: 10px;
            border: 1px solid var(--bio-border);
            background: rgba(15, 23, 42, 0.60);
            color: #DCE6F4;
            font-size: 0.72rem;
            font-weight: 780;
        }}

        .bio-timeline {{
            position: relative;
            padding-left: 1.45rem;
        }}

        .bio-timeline::before {{
            content: "";
            position: absolute;
            left: 0.4rem;
            top: 0.35rem;
            bottom: 0.35rem;
            width: 1px;
            background:
                linear-gradient(
                    var(--bio-primary),
                    var(--bio-secondary),
                    transparent
                );
        }}

        .bio-timeline-item {{
            position: relative;
            margin-bottom: 0.75rem;
            padding: 0.82rem 0.92rem;
            border-radius: 14px;
            border: 1px solid var(--bio-border);
            background: rgba(10, 17, 32, 0.72);
        }}

        .bio-timeline-item::before {{
            content: "";
            position: absolute;
            left: -1.24rem;
            top: 1.05rem;
            width: 9px;
            height: 9px;
            border-radius: 999px;
            background: var(--bio-secondary);
            box-shadow: 0 0 0 5px rgba(34, 211, 238, 0.10);
        }}

        .bio-timeline-title {{
            color: white;
            font-weight: 820;
            font-size: 0.88rem;
        }}

        .bio-timeline-meta {{
            margin-top: 0.2rem;
            color: var(--bio-muted);
            font-size: 0.68rem;
        }}

        .bio-timeline-copy {{
            margin-top: 0.38rem;
            color: #B8C5D6;
            font-size: 0.76rem;
            line-height: 1.5;
        }}

        .bio-professional-strip {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            margin: 0.7rem 0 1rem;
            padding: 0.72rem 0.85rem;
            border-radius: 13px;
            border: 1px solid var(--bio-border);
            background:
                linear-gradient(
                    90deg,
                    rgba(37, 99, 235, 0.12),
                    rgba(15, 23, 42, 0.64),
                    rgba(20, 184, 166, 0.08)
                );
        }}

        .bio-professional-strip strong {{
            color: white;
        }}

        .bio-professional-strip span {{
            color: var(--bio-muted);
            font-size: 0.74rem;
        }}

        @media (max-width: 980px) {{
            .bio-board {{
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }}
        }}

        @media (max-width: 620px) {{
            .bio-board {{
                grid-template-columns: 1fr;
            }}

            .bio-professional-strip {{
                align-items: flex-start;
                flex-direction: column;
            }}
        }}

        @media (max-width: 780px) {{
            .main .block-container {{
                padding-left: 1rem;
                padding-right: 1rem;
            }}

            .bio-hero {{
                border-radius: 20px;
                padding: 1.25rem;
            }}

            .bio-hero-title {{
                font-size: 2.2rem;
            }}
        }}

        {animation_css}
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <style>
        .bio-command-bar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            padding: 0.82rem 1rem;
            margin: 0.55rem 0 1rem;
            border-radius: 16px;
            border: 1px solid var(--bio-border);
            background:
                linear-gradient(
                    120deg,
                    rgba(15, 23, 42, 0.92),
                    rgba(11, 19, 36, 0.74)
                );
            box-shadow: 0 14px 42px rgba(2, 6, 23, 0.26);
        }

        .bio-command-bar strong {
            color: white;
            font-size: 0.86rem;
            letter-spacing: -0.01em;
        }

        .bio-command-bar span {
            color: var(--bio-muted);
            font-size: 0.75rem;
        }

        .bio-db-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.9rem;
            margin: 0.9rem 0 1.25rem;
        }

        .bio-db-card {
            position: relative;
            overflow: hidden;
            min-height: 210px;
            padding: 1.15rem;
            border-radius: 20px;
            border: 1px solid var(--bio-border);
            background:
                linear-gradient(
                    150deg,
                    rgba(18, 29, 54, 0.96),
                    rgba(7, 13, 27, 0.84)
                );
            box-shadow: 0 20px 55px rgba(2, 6, 23, 0.34);
            transition:
                transform 160ms ease,
                border-color 160ms ease,
                box-shadow 160ms ease;
        }

        .bio-db-card:hover {
            transform: translateY(-3px);
            border-color:
                color-mix(in srgb, var(--bio-secondary) 55%, transparent);
            box-shadow: 0 28px 64px rgba(2, 6, 23, 0.46);
        }

        .bio-db-card::after {
            content: "";
            position: absolute;
            width: 130px;
            height: 130px;
            right: -48px;
            top: -50px;
            border-radius: 999px;
            background:
                color-mix(in srgb, var(--bio-primary) 22%, transparent);
            filter: blur(3px);
        }

        .bio-db-top {
            position: relative;
            z-index: 1;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
        }

        .bio-db-icon {
            width: 44px;
            height: 44px;
            display: grid;
            place-items: center;
            border-radius: 14px;
            font-size: 1.2rem;
            color: white;
            background:
                linear-gradient(
                    135deg,
                    var(--bio-primary),
                    var(--bio-secondary)
                );
            box-shadow: 0 12px 34px var(--bio-glow);
        }

        .bio-db-status {
            display: inline-flex;
            align-items: center;
            gap: 0.34rem;
            padding: 0.31rem 0.55rem;
            border-radius: 999px;
            color: #A7F3D0;
            border: 1px solid rgba(52, 211, 153, 0.28);
            background: rgba(16, 185, 129, 0.11);
            font-size: 0.68rem;
            font-weight: 850;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .bio-db-title {
            position: relative;
            z-index: 1;
            margin-top: 1rem;
            color: white;
            font-size: 1.02rem;
            font-weight: 880;
            letter-spacing: -0.025em;
        }

        .bio-db-copy {
            position: relative;
            z-index: 1;
            margin-top: 0.35rem;
            min-height: 42px;
            color: #AEBED2;
            font-size: 0.78rem;
            line-height: 1.5;
        }

        .bio-db-stats {
            position: relative;
            z-index: 1;
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.45rem;
            margin-top: 0.9rem;
        }

        .bio-db-stat {
            padding: 0.58rem;
            border-radius: 12px;
            border: 1px solid rgba(148, 163, 184, 0.13);
            background: rgba(7, 12, 25, 0.56);
        }

        .bio-db-stat strong {
            display: block;
            color: white;
            font-size: 0.92rem;
            font-weight: 900;
        }

        .bio-db-stat span {
            display: block;
            margin-top: 0.15rem;
            color: var(--bio-muted);
            font-size: 0.62rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            font-weight: 780;
        }

        .bio-insight {
            display: grid;
            grid-template-columns: auto 1fr;
            gap: 0.85rem;
            align-items: start;
            padding: 1rem 1.05rem;
            margin: 0.75rem 0 1rem;
            border-radius: 17px;
            border: 1px solid
                color-mix(in srgb, var(--bio-secondary) 28%, transparent);
            background:
                linear-gradient(
                    125deg,
                    color-mix(in srgb, var(--bio-primary) 13%, rgba(8, 14, 28, 0.9)),
                    rgba(8, 14, 28, 0.70)
                );
        }

        .bio-insight-icon {
            width: 38px;
            height: 38px;
            display: grid;
            place-items: center;
            border-radius: 12px;
            background:
                color-mix(in srgb, var(--bio-secondary) 20%, transparent);
            border: 1px solid
                color-mix(in srgb, var(--bio-secondary) 30%, transparent);
        }

        .bio-insight-title {
            color: white;
            font-weight: 860;
            font-size: 0.9rem;
        }

        .bio-insight-copy {
            margin-top: 0.25rem;
            color: #B8C5D6;
            font-size: 0.78rem;
            line-height: 1.55;
        }

        .bio-density {
            margin: 0.6rem 0 0.75rem;
        }

        .bio-density-head {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            margin-bottom: 0.35rem;
            color: #CBD5E1;
            font-size: 0.72rem;
            font-weight: 760;
        }

        .bio-density-track {
            height: 9px;
            overflow: hidden;
            border-radius: 999px;
            border: 1px solid rgba(148, 163, 184, 0.16);
            background: rgba(7, 12, 25, 0.72);
        }

        .bio-density-fill {
            height: 100%;
            border-radius: inherit;
            background:
                linear-gradient(
                    90deg,
                    var(--bio-primary),
                    var(--bio-secondary),
                    var(--bio-accent)
                );
            box-shadow: 0 0 18px var(--bio-glow);
        }

        .bio-surface {
            padding: 1rem;
            border-radius: 18px;
            border: 1px solid var(--bio-border);
            background: rgba(8, 14, 27, 0.68);
            box-shadow: 0 16px 48px rgba(2, 6, 23, 0.26);
        }

        [data-testid="stDataFrame"] {
            box-shadow: 0 18px 54px rgba(2, 6, 23, 0.30);
        }

        [data-testid="stDataFrame"] thead tr th {
            font-weight: 850 !important;
            letter-spacing: 0.015em;
        }

        [data-testid="stHorizontalBlock"] {
            gap: 0.85rem;
        }

        @media (max-width: 980px) {
            .bio-db-grid {
                grid-template-columns: 1fr;
            }

            .bio-board {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }

            .bio-command-bar {
                align-items: flex-start;
                flex-direction: column;
            }
        }

        @media (max-width: 640px) {
            .bio-board {
                grid-template-columns: 1fr;
            }

            .bio-db-stats {
                grid-template-columns: repeat(3, minmax(0, 1fr));
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <style>
        .bio-page-context {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 1rem;
            margin: 0.1rem 0 0.75rem;
            padding: 0.72rem 0.9rem;
            border-radius: 15px;
            border: 1px solid var(--bio-border);
            background: linear-gradient(120deg, rgba(15,23,42,.76), rgba(8,15,30,.58));
            box-shadow: 0 12px 36px rgba(2,6,23,.22);
        }
        .bio-page-breadcrumb { color: var(--bio-muted); font-size: .68rem; font-weight: 760; }
        .bio-page-name { color: white; font-size: .95rem; font-weight: 880; margin-top: .16rem; }
        .bio-page-description { color: #AEBED2; font-size: .72rem; margin-top: .18rem; line-height: 1.45; max-width: 820px; }
        .bio-page-position { flex: 0 0 auto; color: #C4B5FD; font-size: .68rem; font-weight: 850; padding: .32rem .55rem; border-radius: 999px; border: 1px solid var(--bio-border); background: rgba(139,92,246,.10); }
        .bio-nav-section { color: #94A3B8; font-size: .64rem; font-weight: 900; letter-spacing: .09em; text-transform: uppercase; margin: .75rem .2rem .32rem; }
        .bio-sidebar-status { margin: .7rem .1rem .15rem; padding: .7rem; border-radius: 14px; border: 1px solid var(--bio-border); background: rgba(15,23,42,.58); }
        .bio-sidebar-status strong { display:block; color:white; font-size:.76rem; }
        .bio-sidebar-status span { color:var(--bio-muted); font-size:.65rem; line-height:1.45; }
        [data-testid="stSidebar"] [data-testid="stTextInput"] { margin-bottom: -.25rem; }
        [data-testid="stSidebar"] .stButton > button, [data-testid="stSidebar"] [data-testid="stPageLink"] a { min-height: 2.28rem; font-size: .76rem; }
        [data-testid="stDataFrame"] { max-width: 100%; }
        [data-testid="stDataFrame"] [role="columnheader"] { position: sticky; top: 0; z-index: 2; background: #111827 !important; }
        [data-baseweb="tab-list"] { overflow-x: auto; scrollbar-width: thin; }
        [data-testid="stFileUploaderDropzone"] { min-height: 132px; }
        .stCaptionContainer { color: var(--bio-muted); }

        .bio-boundary { display:flex; flex-direction:column; gap:.2rem; margin:.35rem 0 1rem; padding:.72rem .9rem; border-radius:14px; border:1px solid var(--bio-border); font-size:.74rem; line-height:1.45; }
        .bio-boundary strong { color:white; font-size:.78rem; }
        .bio-boundary span { color:#B9C7D8; }
        .bio-boundary-warning { background:rgba(245,158,11,.10); border-color:rgba(245,158,11,.28); }
        .bio-boundary-info { background:rgba(56,189,248,.10); border-color:rgba(56,189,248,.28); }
        .bio-boundary-success { background:rgba(16,185,129,.10); border-color:rgba(16,185,129,.28); }
        .bio-source-row { display:flex; flex-wrap:wrap; gap:.42rem; margin:.45rem 0 .85rem; }
        .bio-source-chip { display:inline-flex; gap:.35rem; align-items:center; padding:.34rem .56rem; border-radius:999px; border:1px solid var(--bio-border); background:rgba(15,23,42,.55); color:#CBD5E1; font-size:.68rem; }
        @media (max-width: 720px) {
            .bio-page-context { flex-direction: column; }
            .bio-page-position { align-self: flex-start; }
            [data-testid="stMetric"] { padding: .78rem .82rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Professional application shell.  These rules intentionally override the
    # older presentation-heavy styling above without changing any workflow code.
    st.markdown(
        """
        <style>
        /* ---------- Application shell ---------- */
        [data-testid="stAppViewContainer"] {
            background: transparent;
        }

        .main .block-container {
            max-width: 1560px;
            padding-top: .9rem;
        }

        [data-testid="stHeader"] {
            height: 3.25rem;
            background: rgba(5, 9, 20, .76);
            border-bottom: 1px solid rgba(148, 163, 184, .10);
            box-shadow: 0 8px 24px rgba(2, 6, 23, .16);
        }

        [data-testid="stSidebar"] {
            min-width: 286px;
            max-width: 286px;
            background: linear-gradient(180deg, #0A1020 0%, #070C18 100%);
            border-right: 1px solid rgba(148, 163, 184, .13);
            box-shadow: 14px 0 40px rgba(2, 6, 23, .22);
        }

        [data-testid="stSidebar"] > div:first-child {
            padding: .8rem .72rem 1rem;
        }

        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
            gap: .35rem;
        }

        [data-testid="stSidebar"] hr {
            margin: .55rem 0;
            border-color: rgba(148, 163, 184, .10);
        }

        /* ---------- Compact product identity ---------- */
        .bio-brand {
            gap: .68rem;
            margin: 0 0 .4rem;
            padding: .25rem .18rem .82rem;
            border-bottom: 1px solid rgba(148, 163, 184, .10);
        }

        .bio-brand-mark {
            width: 38px;
            height: 38px;
            border-radius: 11px;
            font-size: 1.05rem;
            box-shadow: 0 9px 26px var(--bio-glow);
        }

        .bio-brand-title {
            font-size: .94rem;
            letter-spacing: -.018em;
        }

        .bio-brand-subtitle {
            margin-top: .14rem;
            font-size: .64rem;
        }

        .bio-edition-pill {
            display: inline-flex;
            align-items: center;
            margin-top: .28rem;
            padding: .16rem .4rem;
            border: 1px solid rgba(56, 189, 248, .22);
            border-radius: 999px;
            color: #BAE6FD;
            background: rgba(14, 165, 233, .08);
            font-size: .54rem;
            font-weight: 850;
            letter-spacing: .055em;
            text-transform: uppercase;
        }

        .bio-nav-section {
            margin: .62rem .32rem .25rem;
            color: #7F8DA3;
            font-size: .57rem;
            letter-spacing: .105em;
        }

        .bio-nav-hint {
            margin: -.08rem .32rem .32rem;
            color: #64748B;
            font-size: .58rem;
            line-height: 1.35;
        }

        /* ---------- Sidebar navigation ---------- */
        [data-testid="stSidebar"] [data-testid="stPageLink"] {
            margin: .06rem 0;
        }

        [data-testid="stSidebar"] [data-testid="stPageLink"] a {
            min-height: 2.24rem;
            padding: .48rem .62rem;
            border: 1px solid transparent;
            border-radius: 10px;
            color: #B8C3D4;
            background: transparent;
            font-size: .72rem;
            font-weight: 690;
            transition: background 140ms ease, border-color 140ms ease, color 140ms ease;
        }

        [data-testid="stSidebar"] [data-testid="stPageLink"] a:hover {
            color: #F8FAFC;
            border-color: rgba(148, 163, 184, .12);
            background: rgba(30, 41, 59, .52);
            transform: none;
        }

        [data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] {
            color: #FFFFFF;
            border-color: color-mix(in srgb, var(--bio-primary) 46%, transparent);
            background: linear-gradient(90deg,
                color-mix(in srgb, var(--bio-primary) 25%, rgba(15, 23, 42, .84)),
                rgba(15, 23, 42, .72));
            box-shadow: inset 3px 0 0 var(--bio-secondary), 0 8px 22px rgba(2, 6, 23, .20);
        }

        [data-testid="stSidebar"] [data-testid="stExpander"] {
            margin: .22rem 0 0;
            border: 1px solid rgba(148, 163, 184, .10);
            border-radius: 11px;
            overflow: hidden;
            background: rgba(15, 23, 42, .30);
        }

        [data-testid="stSidebar"] [data-testid="stExpander"] details summary {
            min-height: 2.2rem;
            padding: .48rem .58rem;
            color: #CBD5E1;
            font-size: .68rem;
            font-weight: 760;
        }

        [data-testid="stSidebar"] [data-testid="stExpander"] details[open] summary {
            border-bottom: 1px solid rgba(148, 163, 184, .09);
            background: rgba(30, 41, 59, .30);
        }

        [data-testid="stSidebar"] [data-testid="stExpanderDetails"] {
            padding: .44rem .52rem .58rem;
        }

        [data-testid="stSidebar"] [data-baseweb="input"] > div,
        [data-testid="stSidebar"] [data-baseweb="select"] > div {
            min-height: 2.15rem;
            border-color: rgba(148, 163, 184, .14) !important;
            border-radius: 9px !important;
            background: rgba(8, 15, 29, .76) !important;
            box-shadow: none !important;
        }

        [data-testid="stSidebar"] input {
            font-size: .68rem !important;
        }

        [data-testid="stSidebar"] .stCaptionContainer,
        [data-testid="stSidebar"] small {
            color: #718096 !important;
            font-size: .58rem !important;
        }

        .bio-sidebar-status {
            margin: .48rem 0 0;
            padding: .62rem .68rem;
            border-radius: 11px;
            border-color: rgba(148, 163, 184, .11);
            background: rgba(8, 15, 29, .68);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, .02);
        }

        .bio-sidebar-status strong {
            font-size: .67rem;
        }

        .bio-sidebar-status span {
            font-size: .56rem;
            line-height: 1.5;
        }

        /* ---------- In-page application header ---------- */
        .bio-page-context {
            position: sticky;
            top: 3.55rem;
            z-index: 30;
            align-items: center;
            margin: 0 0 .85rem;
            padding: .62rem .82rem;
            border-radius: 13px;
            border-color: rgba(148, 163, 184, .13);
            background: rgba(8, 15, 29, .88);
            box-shadow: 0 10px 30px rgba(2, 6, 23, .22);
            backdrop-filter: blur(18px);
        }

        .bio-page-breadcrumb {
            font-size: .59rem;
            letter-spacing: .035em;
        }

        .bio-page-name {
            margin-top: .08rem;
            font-size: .84rem;
        }

        .bio-page-description {
            margin-top: .1rem;
            font-size: .63rem;
            line-height: 1.38;
        }

        .bio-page-position {
            padding: .28rem .5rem;
            color: #BAE6FD;
            border-color: rgba(56, 189, 248, .20);
            background: rgba(14, 165, 233, .07);
            font-size: .58rem;
        }

        /* ---------- Software-style content surfaces ---------- */
        .bio-hero {
            margin: .15rem 0 1rem;
            padding: 1.35rem 1.45rem;
            border-radius: 18px;
            box-shadow: 0 18px 54px rgba(2, 6, 23, .30);
        }

        .bio-eyebrow {
            padding: .27rem .55rem;
            font-size: .61rem;
        }

        .bio-hero-title {
            max-width: 1020px;
            margin: .65rem 0 .45rem;
            font-size: clamp(1.65rem, 3vw, 2.65rem);
            line-height: 1.08;
            letter-spacing: -.042em;
        }

        .bio-hero-subtitle {
            max-width: 980px;
            font-size: .86rem;
            line-height: 1.6;
        }

        .bio-chip-row {
            gap: .42rem;
            margin-top: .78rem;
        }

        .bio-chip {
            padding: .32rem .56rem;
            font-size: .63rem;
        }

        .bio-card, .bio-db-card, .bio-surface,
        [data-testid="stMetric"], [data-testid="stPlotlyChart"] {
            border-color: rgba(148, 163, 184, .13);
            box-shadow: 0 12px 34px rgba(2, 6, 23, .22);
        }

        .bio-card:hover, .bio-db-card:hover {
            transform: translateY(-1px);
        }

        [data-testid="stMetric"] {
            padding: .82rem .9rem;
            border-radius: 13px;
            background: rgba(15, 23, 42, .62);
        }

        [data-testid="stMetricLabel"] {
            color: #8FA0B7;
            font-size: .68rem;
            font-weight: 720;
        }

        [data-testid="stMetricValue"] {
            color: #F8FAFC;
            font-size: 1.4rem;
            font-weight: 850;
            letter-spacing: -.03em;
        }

        .stButton > button,
        .stDownloadButton > button,
        [data-testid="baseButton-primary"],
        [data-testid="baseButton-secondary"] {
            min-height: 2.45rem;
            border-radius: 10px;
            font-size: .73rem;
            font-weight: 760;
            box-shadow: none;
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover {
            transform: translateY(-1px);
        }

        [data-baseweb="input"] > div,
        [data-baseweb="select"] > div,
        [data-testid="stTextArea"] textarea,
        [data-testid="stFileUploaderDropzone"] {
            border-color: rgba(148, 163, 184, .15) !important;
            border-radius: 11px !important;
            background: rgba(10, 17, 32, .64) !important;
            box-shadow: none !important;
        }

        [data-testid="stForm"] {
            padding: 1rem;
            border: 1px solid rgba(148, 163, 184, .13);
            border-radius: 14px;
            background: rgba(10, 17, 32, .42);
        }

        [data-baseweb="tab-list"] {
            gap: .22rem;
            padding: .24rem;
            border: 1px solid rgba(148, 163, 184, .11);
            border-radius: 11px;
            background: rgba(8, 15, 29, .55);
        }

        [data-baseweb="tab"] {
            min-height: 2.25rem;
            padding: .42rem .68rem;
            border-radius: 8px;
            font-size: .69rem;
            font-weight: 720;
        }

        [data-baseweb="tab"][aria-selected="true"] {
            background: rgba(37, 99, 235, .16);
        }

        [data-testid="stDataFrame"] {
            overflow: hidden;
            border: 1px solid rgba(148, 163, 184, .12);
            border-radius: 13px;
        }

        [data-testid="stAlert"] {
            border-radius: 12px;
            border-color: rgba(148, 163, 184, .13);
        }

        @media (max-width: 900px) {
            [data-testid="stSidebar"] {
                min-width: 270px;
                max-width: 270px;
            }
            .bio-page-context {
                position: static;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if appearance_mode == "Light":
        st.markdown(
            """<style>
            .stApp, [data-testid="stAppViewContainer"] { background:#F5F7FB !important; color:#0F172A !important; }
            [data-testid="stHeader"] { background:rgba(248,250,252,.88) !important; border-bottom-color:#E2E8F0 !important; }
            [data-testid="stSidebar"] { background:#FFFFFF !important; border-right-color:#E2E8F0 !important; box-shadow:12px 0 34px rgba(15,23,42,.06) !important; }
            [data-testid="stSidebar"] [data-testid="stPageLink"] a { color:#475569 !important; }
            [data-testid="stSidebar"] [data-testid="stPageLink"] a:hover { color:#0F172A !important; background:#F1F5F9 !important; }
            [data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] { color:#0F172A !important; background:#EFF6FF !important; }
            [data-testid="stSidebar"] [data-testid="stExpander"] { background:#F8FAFC !important; border-color:#E2E8F0 !important; }
            [data-testid="stSidebar"] [data-testid="stExpander"] details summary { color:#334155 !important; }
            .bio-brand { border-bottom-color:#E2E8F0 !important; }
            .bio-brand-title { color:#0F172A !important; }
            .bio-brand-subtitle,.bio-nav-hint { color:#64748B !important; }
            .bio-card,.bio-page-context,.bio-sidebar-status,.bio-kpi,.bio-surface,[data-testid="stMetric"],[data-testid="stPlotlyChart"] { background:rgba(255,255,255,.96) !important; color:#0F172A !important; border-color:#E2E8F0 !important; box-shadow:0 12px 32px rgba(15,23,42,.08) !important; }
            .bio-page-name,.bio-card-title,.bio-kpi-value,.bio-sidebar-status strong,.bio-boundary strong { color:#0F172A !important; }
            .bio-page-description,.bio-card-copy,.bio-kpi-copy,.bio-boundary span { color:#475569 !important; }
            [data-baseweb="input"] > div,[data-baseweb="select"] > div,[data-testid="stTextArea"] textarea { background:white !important; color:#0F172A !important; }
            </style>""",
            unsafe_allow_html=True,
        )

    # Step 46 application shell: a restrained scientific SaaS layout with
    # task-based navigation, searchable modules, durable favourites and responsive controls.
    # Backward-compatible semantic anchors for Step 45 checks:
    # Step 45 distributed application shell · ⌕ Find a workspace · ⚙ Settings ·
    # Browse by category · Search all modules from the centre · Quick Dock (legacy name).
    st.markdown(
        '<a class="bio-skip-link" href="#bio-main-content">Skip to workspace content</a>'
        '<div id="bio-main-content"></div>',
        unsafe_allow_html=True,
    )
    # ``st.html`` is the supported CSS injection path in current Streamlit.
    # Keeping the style tag separate from Markdown prevents the browser from
    # displaying the stylesheet as visible page text.
    st.html(
        """
        <style>
        /* ---------- Step 46 professional UI excellence shell ---------- */
        :root {
            --bio-control-height: 2.55rem;
            --bio-space-1: .25rem;
            --bio-space-2: .5rem;
            --bio-space-3: .75rem;
            --bio-space-4: 1rem;
            --bio-space-5: 1.25rem;
            --bio-space-6: 1.5rem;
        }

        .bio-skip-link {
            position: fixed;
            left: 1rem;
            top: -5rem;
            z-index: 1000000;
            padding: .7rem 1rem;
            border-radius: 10px;
            color: white !important;
            background: var(--bio-primary);
            font-weight: 800;
            text-decoration: none;
            box-shadow: 0 12px 32px rgba(2,6,23,.35);
        }
        .bio-skip-link:focus { top: .75rem; }

        [data-testid="stSidebar"] {
            min-width: 260px !important;
            max-width: 260px !important;
        }
        [data-testid="stSidebar"] > div:first-child {
            padding: .55rem .7rem 1rem !important;
        }
        .bio-brand {
            padding: .35rem .22rem .9rem !important;
            margin-bottom: .1rem;
            border-bottom: 1px solid rgba(148,163,184,.10);
        }
        .bio-brand-mark {
            width: 38px !important;
            height: 38px !important;
            border-radius: 12px !important;
            font-size: 1.05rem !important;
        }
        .bio-nav-section {
            margin: .82rem .36rem .34rem !important;
            color: var(--bio-muted);
            font-size: .62rem;
            font-weight: 900;
            letter-spacing: .12em;
            text-transform: uppercase;
        }
        .bio-category-copy {
            margin: -.1rem .08rem .45rem;
            color: var(--bio-muted);
            font-size: .65rem;
            line-height: 1.45;
        }
        .bio-shell-bar {
            display: flex;
            align-items: center;
            min-height: 2.65rem;
            padding: .52rem .72rem;
            border: 1px solid rgba(148,163,184,.14);
            border-radius: 14px;
            background: linear-gradient(135deg, rgba(15,23,42,.88), rgba(8,15,30,.78));
            box-shadow: 0 12px 32px rgba(2,6,23,.18);
            backdrop-filter: blur(18px);
        }
        .bio-shell-kicker {
            color: var(--bio-muted);
            font-size: .59rem;
            font-weight: 900;
            letter-spacing: .095em;
            text-transform: uppercase;
        }
        .bio-shell-title {
            color: white;
            font-size: .79rem;
            font-weight: 850;
            margin-top: .1rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .bio-shell-search-note,
        .bio-settings-note {
            color: var(--bio-muted);
            font-size: .67rem;
            line-height: 1.5;
            margin: -.1rem 0 .55rem;
        }
        .bio-shell-status {
            display: flex;
            align-items: center;
            gap: .5rem;
            padding: .5rem .58rem;
            border-radius: 12px;
            border: 1px solid rgba(148,163,184,.13);
            background: rgba(15,23,42,.54);
            margin: .55rem .04rem 0;
        }
        .bio-shell-status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            box-shadow: 0 0 0 4px rgba(52,211,153,.10);
            flex: 0 0 auto;
        }
        .bio-shell-status-copy strong {
            display: block;
            color: white;
            font-size: .69rem;
            line-height: 1.25;
        }
        .bio-shell-status-copy span {
            display: block;
            color: var(--bio-muted);
            font-size: .6rem;
            margin-top: .08rem;
        }
        .bio-result-label {
            color: var(--bio-muted);
            font-size: .62rem;
            font-weight: 850;
            letter-spacing: .08em;
            text-transform: uppercase;
            margin: .45rem 0 .24rem;
        }

        /* Compact, polished module context. */
        .bio-page-context {
            position: relative !important;
            top: auto !important;
            margin: .62rem 0 1rem !important;
            padding: .75rem .9rem !important;
            border-radius: 14px !important;
            border-color: rgba(148,163,184,.13) !important;
            background: linear-gradient(135deg, rgba(15,23,42,.70), rgba(8,15,30,.54)) !important;
            box-shadow: 0 10px 28px rgba(2,6,23,.16) !important;
        }
        .bio-page-breadcrumb { font-size: .59rem !important; letter-spacing: .08em; }
        .bio-page-name { font-size: .86rem !important; }
        .bio-page-description { font-size: .68rem !important; max-width: 900px; }
        .bio-page-position { font-size: .61rem !important; }

        /* Restraint over decoration: compact hero, stronger hierarchy. */
        .bio-hero {
            padding: clamp(1.25rem, 3vw, 1.9rem) !important;
            margin: .35rem 0 1.15rem !important;
            border-radius: 20px !important;
            border-color: rgba(148,163,184,.14) !important;
            box-shadow: 0 18px 54px rgba(2,6,23,.30) !important;
        }
        .bio-hero-title {
            max-width: 1060px !important;
            margin: .72rem 0 .5rem !important;
            font-size: clamp(1.75rem, 4vw, 3.05rem) !important;
            line-height: 1.04 !important;
            letter-spacing: -.045em !important;
        }
        .bio-hero-subtitle {
            max-width: 980px !important;
            font-size: clamp(.91rem, 1.7vw, 1.05rem) !important;
            line-height: 1.6 !important;
        }
        .bio-eyebrow {
            padding: .3rem .62rem !important;
            font-size: .67rem !important;
        }
        .bio-chip-row { margin-top: .82rem !important; gap: .42rem !important; }
        .bio-chip { padding: .34rem .58rem !important; font-size: .69rem !important; }

        .bio-section-label {
            margin: 1.35rem 0 .72rem !important;
            font-size: 1.02rem !important;
        }
        .bio-card,
        .bio-db-card,
        .bio-kpi,
        .bio-surface,
        [data-testid="stMetric"],
        [data-testid="stPlotlyChart"] {
            border-radius: 15px !important;
            border-color: rgba(148,163,184,.13) !important;
            box-shadow: 0 12px 32px rgba(2,6,23,.18) !important;
        }
        .bio-card:hover,
        .bio-db-card:hover {
            transform: translateY(-1px) !important;
            box-shadow: 0 18px 40px rgba(2,6,23,.26) !important;
        }
        .bio-card-icon { width: 38px !important; height: 38px !important; border-radius: 11px !important; }
        .bio-card-title { font-size: .93rem !important; }
        .bio-card-copy { font-size: .79rem !important; line-height: 1.5 !important; }

        /* Consistent controls and interaction states. */
        [data-testid="stButton"] > button,
        [data-testid="stDownloadButton"] > button,
        [data-testid="stPageLink"] a,
        [data-testid="stPopover"] > button {
            min-height: var(--bio-control-height) !important;
            border-radius: 11px !important;
            font-size: .76rem !important;
            font-weight: 760 !important;
            transition: border-color 140ms ease, background 140ms ease, transform 140ms ease, box-shadow 140ms ease !important;
        }
        [data-testid="stButton"] > button:hover,
        [data-testid="stDownloadButton"] > button:hover,
        [data-testid="stPageLink"] a:hover,
        [data-testid="stPopover"] > button:hover {
            transform: translateY(-1px);
        }
        [data-testid="stSidebar"] [data-testid="stPageLink"] a {
            min-height: 2.15rem !important;
            padding: .45rem .58rem !important;
            margin: .07rem 0 !important;
            font-size: .72rem !important;
        }
        [data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] {
            background: linear-gradient(90deg, color-mix(in srgb, var(--bio-primary) 24%, transparent), color-mix(in srgb, var(--bio-secondary) 8%, transparent)) !important;
            border-color: color-mix(in srgb, var(--bio-primary) 38%, transparent) !important;
            box-shadow: none !important;
        }
        [data-testid="stPopover"] > button {
            border: 1px solid rgba(148,163,184,.14) !important;
            background: linear-gradient(135deg, rgba(15,23,42,.86), rgba(8,15,30,.74)) !important;
            box-shadow: 0 10px 26px rgba(2,6,23,.15) !important;
        }
        [data-testid="stPopoverBody"] {
            border: 1px solid rgba(148,163,184,.15) !important;
            border-radius: 16px !important;
            background: rgba(8,13,27,.985) !important;
            box-shadow: 0 28px 80px rgba(2,6,23,.56) !important;
        }
        [data-baseweb="input"] > div,
        [data-baseweb="select"] > div,
        [data-testid="stTextArea"] textarea,
        [data-testid="stFileUploaderDropzone"] {
            min-height: var(--bio-control-height);
            border-radius: 10px !important;
        }
        [data-testid="stForm"] {
            padding: 1rem !important;
            border-radius: 14px !important;
            border-color: rgba(148,163,184,.13) !important;
        }
        [data-testid="stExpander"] {
            border-radius: 13px !important;
            border-color: rgba(148,163,184,.12) !important;
        }
        [data-testid="stAlert"] {
            border-radius: 12px !important;
            font-size: .79rem;
        }
        [data-testid="stDataFrame"] {
            border-radius: 13px !important;
            border-color: rgba(148,163,184,.13) !important;
            box-shadow: 0 10px 26px rgba(2,6,23,.13);
        }
        [data-testid="stDataFrame"] [role="columnheader"] {
            font-weight: 800 !important;
        }
        [data-baseweb="tab-list"] {
            position: sticky;
            top: 0;
            z-index: 2;
            border-radius: 11px !important;
            backdrop-filter: blur(16px);
        }

        :where(button, a, input, textarea, select, [tabindex]):focus-visible {
            outline: 3px solid color-mix(in srgb, var(--bio-secondary) 72%, white 10%) !important;
            outline-offset: 2px !important;
            box-shadow: 0 0 0 5px color-mix(in srgb, var(--bio-primary) 18%, transparent) !important;
        }

        @media (max-width: 1100px) {
            [data-testid="stSidebar"] { min-width: 244px !important; max-width: 244px !important; }
            .main .block-container { padding-left: 1.15rem !important; padding-right: 1.15rem !important; }
            .bio-page-description { display: none; }
        }
        @media (max-width: 760px) {
            .main .block-container { padding: .75rem .75rem 3rem !important; }
            .bio-hero { padding: 1.05rem !important; border-radius: 16px !important; }
            .bio-hero-title { font-size: 1.72rem !important; }
            .bio-hero-subtitle { font-size: .88rem !important; }
            .bio-page-context { padding: .65rem .72rem !important; }
            .bio-page-position { display: none; }
            [data-baseweb="tab-list"] { position: static; overflow-x: auto; }
        }
        </style>
        """
    )

    # System mode follows the operating-system preference without requiring a rerun.
    if appearance_mode == "System":
        st.markdown(
            """
            <style>
            @media (prefers-color-scheme: light) {
                .stApp, [data-testid="stAppViewContainer"] { background:#F5F7FB !important; color:#0F172A !important; }
                [data-testid="stHeader"] { background:rgba(248,250,252,.90) !important; border-bottom-color:#E2E8F0 !important; }
                [data-testid="stSidebar"] { background:#FFFFFF !important; border-right-color:#E2E8F0 !important; box-shadow:12px 0 34px rgba(15,23,42,.06) !important; }
                .bio-shell-bar,.bio-shell-status,[data-testid="stPopover"] > button,.bio-page-context,.bio-card,.bio-kpi,.bio-db-card,[data-testid="stMetric"],[data-testid="stPlotlyChart"] { background:rgba(255,255,255,.96) !important; color:#0F172A !important; border-color:#E2E8F0 !important; box-shadow:0 12px 30px rgba(15,23,42,.08) !important; }
                .bio-shell-title,.bio-shell-status-copy strong,.bio-page-name,.bio-card-title,.bio-kpi-value,.bio-db-title { color:#0F172A !important; }
                .bio-shell-kicker,.bio-shell-status-copy span,.bio-shell-search-note,.bio-settings-note,.bio-page-description,.bio-card-copy,.bio-kpi-copy,.bio-db-copy,.bio-category-copy { color:#64748B !important; }
                [data-testid="stPopoverBody"] { background:#FFFFFF !important; border-color:#E2E8F0 !important; }
                [data-baseweb="input"] > div,[data-baseweb="select"] > div,[data-testid="stTextArea"] textarea { background:#FFFFFF !important; color:#0F172A !important; }
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

    desktop_ux = Path(__file__).with_name("desktop_ux.css")
    if desktop_ux.is_file():
        st.markdown(f"<style>{read_text_cached(desktop_ux)}</style>", unsafe_allow_html=True)

    intro_motion = not bool(st.session_state.get("_bio_motion_intro_seen", False))
    apply_premium_aesthetic(
        palette,
        font,
        appearance_mode=appearance_mode,
        compact=compact,
        reduce_motion=reduce_motion,
        motion_mode=motion_mode,
        intro_motion=intro_motion,
        high_contrast=high_contrast,
    )
    st.session_state["_bio_motion_intro_seen"] = True

    # Final desktop-only experience layer: each palette now changes the full
    # visual language (geometry, surfaces, hero, navigation, controls and data
    # presentation), while mobile behavior and the font catalogue stay intact.
    st.markdown(
        experience_theme_css(
            palette,
            appearance_mode=appearance_mode,
            compact=compact,
            reduce_motion=reduce_motion,
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        theme_variable_override_css(
            palette,
            heading_font=heading_font,
            body_font=font,
            data_font=data_font,
            appearance_mode=appearance_mode,
            reduce_effects=reduce_effects,
        ),
        unsafe_allow_html=True,
    )

    # Final scientific-workbench layer. It is loaded last so uploader, module-header,
    # table and tab styling remain consistent across every palette.
    workbench_css = Path(__file__).with_name("workbench.css")
    if workbench_css.is_file():
        st.markdown(f"<style>{read_text_cached(workbench_css)}</style>", unsafe_allow_html=True)

    # Theme Intelligence v2 is intentionally the final token layer so density,
    # responsive rules, semantic status colours and validated custom overrides
    # cannot be silently overwritten by legacy theme stylesheets.
    st.markdown(
        theme_runtime_css(
            density_mode=density_mode,
            performance_mode=performance_mode,
            custom_tokens=st.session_state.get("ui_custom_theme_tokens", {}),
        ),
        unsafe_allow_html=True,
    )

    # Step 124 premium visual layer is intentionally last: animated scientific
    # atmosphere, glass surfaces, SVG icon treatment and workflow ribbons must
    # remain consistent across every legacy and modern module.
    premium_visual_css = Path(__file__).with_name("premium_visuals.css")
    if premium_visual_css.is_file():
        st.markdown(f"<style>{read_text_cached(premium_visual_css)}</style>", unsafe_allow_html=True)

    # The application shell is loaded last so every page, palette and density
    # mode shares one authoritative sidebar/main-width contract.
    responsive_layout_css = Path(__file__).with_name("responsive_layout.css")
    if responsive_layout_css.is_file():
        st.html(f"<style>{read_text_cached(responsive_layout_css)}</style>")
    _mount_layout_resize_observer()

    version_path = PROJECT_ROOT / "VERSION"
    version = read_text_cached(version_path).strip() if version_path.is_file() else "local"
    st.markdown(brand_header_html(version), unsafe_allow_html=True)

    active_key = current_page_key()
    st.session_state["_bio_active_page_key"] = active_key or ""
    _track_navigation_history(active_key)
    preferences = session_preferences()
    if active_key:
        record_recent_page(preferences, active_key)
        st.session_state["ui_recent_pages"] = list(preferences.recent_pages)

    active_page = PAGE_BY_KEY.get(active_key) if active_key else None
    st.session_state["_bio_peak_target_active"] = False
    st.session_state["_bio_peak_mode_active"] = False
    st.session_state["_bio_peak_visual_audits"] = {}
    st.session_state["_bio_peak_frame_audits"] = {}
    st.session_state["_bio_peak_table_notices"] = []
    try:
        from biointel.step127.ui import render_step127_sidebar_for_page

        render_step127_sidebar_for_page(active_page.path if active_page is not None else "")
    except Exception:
        # Scientific depth status must never interrupt a module page.
        pass
    try:
        if active_page is not None:
            from biointel.peak_potential.ui import render_peak_sidebar_for_page

            render_peak_sidebar_for_page(
                page_key=active_page.key,
                title=active_page.title,
                category=active_page.category,
                path=active_page.path,
            )
    except Exception:
        # Peak assurance is additive and may never block the underlying module.
        pass
    favourites = {key for key in st.session_state.get("ui_favourites", []) if key in PAGE_BY_KEY}
    health = _cached_workspace_health(str(PROJECT_ROOT))
    db_count = int(health.get("database_count", 0) or 0)
    healthy_count = int(health.get("healthy_count", 0) or 0)
    is_healthy = db_count > 0 and healthy_count == db_count

    def _page_link(page_key: str, label: str | None = None) -> None:
        page = PAGE_BY_KEY.get(page_key)
        if page is None:
            return
        try:
            st.page_link(
                page.path,
                label=label or compact_module_name(page.key, page.title),
                width="stretch",
            )
        except (KeyError, RuntimeError):
            st.caption(label or compact_module_name(page.key, page.title))

    def _category_label(category: str) -> str:
        return str(category)

    def _workflow_group(page) -> str:
        text = " ".join((page.key, page.title, *page.keywords)).lower()
        category = page.category
        if category in {"Bioinformatics", "Sequence"}:
            if any(token in text for token in ("single cell", "spatial", "cell atlas", "trajectory")):
                return "Single-cell & spatial"
            if any(token in text for token in ("microbi", "metagen", "pathogen", "viral", "outbreak", "one health")):
                return "Microbes & pathogens"
            if any(token in text for token in ("transcript", "rna", "splicing", "epitranscript")):
                return "RNA & transcriptomics"
            if any(token in text for token in ("variant", "genome", "gwas", "pangenome", "rare", "crispr")):
                return "Genomics & variants"
            if any(token in text for token in ("protein", "structural", "proteom", "glyco")):
                return "Proteins & structures"
            return "Sequence & quality control"
        if category in {"Discovery", "Chemistry"}:
            if any(token in text for token in ("docking", "structure", "protein design", "antibody")):
                return "Structure & biologics"
            if any(token in text for token in ("admet", "smiles", "compound", "chembl")):
                return "Compounds & developability"
            return "Targets & evidence"
        if category == "Lab Analytics":
            if any(token in text for token in ("instrument", "lims", "eln", "chain")):
                return "Lab operations"
            if any(token in text for token in ("bioprocess", "fermentation", "enzyme", "synthetic")):
                return "Bioprocess & engineering"
            return "Assays & imaging"
        if category in {"AI Lab", "Modelling", "Modeling"}:
            if any(token in text for token in ("registry", "lifecycle", "qualification", "assurance")):
                return "Model governance"
            if any(token in text for token in ("evaluation", "benchmark", "validation", "drift")):
                return "Evaluation & validation"
            return "Training & prediction"
        if category == "Research Planning":
            if any(token in text for token in ("protocol", "analysis plan", "preregistration", "evidence gap", "literature")):
                return "Protocol & reproducibility"
            if any(token in text for token in ("sample size", "power", "randomization", "blinding", "experimental design", "doe", "trial design")):
                return "Design & statistics"
            if any(token in text for token in ("cohort", "endpoint", "biomarker", "synthetic cohort")):
                return "Cohorts & outcomes"
            return "Execution planning"
        if category == "Operations":
            if any(token in text for token in ("install", "recovery", "backup", "diagnostic", "reliability")):
                return "Reliability & recovery"
            if any(token in text for token in ("workflow", "job", "queue", "execution")):
                return "Execution & automation"
            return "Projects & deployment"
        if category in {"Data", "Data & Governance"}:
            if any(token in text for token in ("reference", "provider", "database")):
                return "Reference data"
            if any(token in text for token in ("lineage", "quality", "readiness", "curation")):
                return "Quality & lineage"
            return "Data access & search"
        return "All tools"

    with st.sidebar:
        st.markdown(sidebar_brand_html(version), unsafe_allow_html=True)

        st.markdown('<div class="bio-nav-section">Workspace</div>', unsafe_allow_html=True)
        for page_key in SIDEBAR_PRIMARY:
            _page_link(page_key)

        st.markdown('<div class="bio-nav-section">Task lanes</div>', unsafe_allow_html=True)
        for page_key, label in SIDEBAR_WORK_MODES:
            _page_link(page_key, label)

        with st.expander("▦ Browse a domain", expanded=False):
            active_category = active_page.category if active_page else "Start"
            # Keep the domain browser aligned with the active page. This avoids
            # stale sidebar context after direct links or cross-workflow handoffs.
            if (
                active_category in CATEGORIES
                and st.session_state.get("_bio_sidebar_category") != active_category
            ):
                st.session_state["_bio_sidebar_category"] = active_category
            elif st.session_state.get("_bio_sidebar_category") not in CATEGORIES:
                st.session_state["_bio_sidebar_category"] = CATEGORIES[0]
            sidebar_category = st.selectbox(
                "Workspace",
                CATEGORIES,
                format_func=_category_label,
                label_visibility="collapsed",
                key="_bio_sidebar_category",
            )
            _, category_copy = CATEGORY_META.get(
                sidebar_category, ("▦", "Related workspace modules")
            )
            st.markdown(
                f'<div class="bio-category-copy">{html.escape(category_copy)}</div>',
                unsafe_allow_html=True,
            )
            category_pages = [
                page
                for page in search_pages("", sidebar_category, favourites)
                if page.key != active_key
            ]
            groups = sorted({_workflow_group(page) for page in category_pages})
            selected_group = "All focus areas"
            if len(category_pages) > 10 and len(groups) > 1:
                selected_group = st.selectbox(
                    "Focus area",
                    ["All focus areas", *groups],
                    key=f"_bio_sidebar_focus_{sidebar_category}",
                )
            visible_pages = (
                category_pages
                if selected_group == "All focus areas"
                else [page for page in category_pages if _workflow_group(page) == selected_group]
            )
            current_group = None
            for page in visible_pages:
                group = _workflow_group(page)
                if selected_group == "All focus areas" and len(groups) > 1 and group != current_group:
                    st.caption(group.upper())
                    current_group = group
                _page_link(page.key)

        favourite_keys = [
            key
            for key in st.session_state.get("ui_favourites", [])
            if key in PAGE_BY_KEY and key != active_key
        ][:4]
        recent_keys = [
            key
            for key in st.session_state.get("ui_recent_pages", [])
            if key in PAGE_BY_KEY and key != active_key and key not in favourite_keys
        ][:4]
        if favourite_keys or recent_keys:
            with st.expander("★ Pinned & recent", expanded=False):
                if favourite_keys:
                    st.caption("PINNED")
                    for page_key in favourite_keys:
                        _page_link(page_key)
                if recent_keys:
                    st.caption("RECENT")
                    for page_key in recent_keys:
                        _page_link(page_key)

        from biointel.ui.starter_kits import render_module_starter_kit_sidebar

        render_module_starter_kit_sidebar(active_key, PROJECT_ROOT)

        status_detail = (
            f"{healthy_count}/{db_count} databases online"
            if db_count
            else "Database health unavailable"
        )
        status_color = "#34D399" if is_healthy else "#FBBF24"
        st.markdown(
            f"""
            <div class="bio-shell-status">
              <div class="bio-shell-status-dot" style="background:{status_color}"></div>
              <div class="bio-shell-status-copy">
                <strong>{"Workspace healthy" if is_healthy else "Workspace review needed"}</strong>
                <span>{html.escape(status_detail)}</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.expander("About BioIntel AI", expanded=False):
            st.markdown(about_brand_html(version), unsafe_allow_html=True)

    from biointel.ui.premium_visuals import svg_icon_html

    # Allocate enough space to status/timeline/alerts/view controls. The previous
    # earlier narrow right-column ratios squeezed the four right controls into character-wide
    # columns on common 1366–1600 px desktop windows.
    shell_left, shell_center, shell_right = st.columns(
        [1.00, 1.62, 1.78], gap="small", vertical_alignment="center"
    )
    with shell_left:
        shell_category = active_page.category if active_page else "Workspace"
        shell_title = (
            compact_module_name(active_page.key, active_page.title)
            if active_page
            else "BioIntel AI"
        )
        shell_family = product_family_for_category(shell_category)
        shell_icon = svg_icon_html(
            page_key=active_key,
            category=shell_category,
            title=shell_title,
            size=22,
            css_class="bio-svg-icon bio-shell-module-icon",
        )
        st.markdown(
            f"""
            <div class="bio-shell-bar bio-shell-premium" data-module-key="{html.escape(active_key or 'workspace')}">
              <div class="bio-shell-icon-wrap">{shell_icon}</div>
              <div>
                <div class="bio-shell-kicker">{html.escape(shell_category)} · {html.escape(shell_family)}</div>
                <div class="bio-shell-title">{html.escape(shell_title)}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with shell_center:
        with st.popover("⌕  Find modules · Ctrl K", width="stretch"):
            st.markdown(
                '<div class="bio-shell-search-note">Search every module page and every embedded scientific workspace. Typo-tolerant matching is enabled. Pagination exposes the complete catalogue without rendering hundreds of controls at once.</div>',
                unsafe_allow_html=True,
            )
            finder_left, finder_right = st.columns([1.75, 1.0], gap="small")
            with finder_left:
                nav_query = st.text_input(
                    "Find a module",
                    placeholder="Try: RNA-seq, VCF, ADMET, release, PDF…",
                    label_visibility="collapsed",
                    key="_bio_global_nav_search",
                )
            with finder_right:
                category_options = ["All", *CATEGORIES]
                if st.session_state.get("_bio_global_nav_category") not in category_options:
                    st.session_state["_bio_global_nav_category"] = "All"
                nav_category = st.selectbox(
                    "Search domain",
                    category_options,
                    format_func=lambda value: (
                        "All domains" if value == "All" else _category_label(value)
                    ),
                    label_visibility="collapsed",
                    key="_bio_global_nav_category",
                )

            browse_col, size_col = st.columns([1.25, 0.75], gap="small")
            with browse_col:
                browse_mode = st.segmented_control(
                    "Catalogue view",
                    ["All modules", "Recommended"],
                    default="Recommended",
                    label_visibility="collapsed",
                    key="_bio_global_nav_mode",
                )
            with size_col:
                nav_page_size = st.selectbox(
                    "Results per page",
                    [12, 24, 48],
                    index=1,
                    label_visibility="collapsed",
                    key="_bio_global_nav_page_size",
                )

            surface_view = st.segmented_control(
                "Workspace surface",
                ["Operational", "Platform", "Assurance", "Internal", "All"],
                default="Operational",
                key="_bio_global_nav_surface",
            )

            from biointel.ui.module_catalogue import search_catalogue

            catalogue_matches = search_catalogue(PROJECT_ROOT, nav_query, sort_mode="Relevance")
            if nav_category != "All":
                catalogue_matches = [
                    match
                    for match in catalogue_matches
                    if match.item.category == nav_category
                    or (
                        match.item.page_key in PAGE_BY_KEY
                        and PAGE_BY_KEY[match.item.page_key].category == nav_category
                    )
                ]
            if surface_view != "All":
                catalogue_matches = [
                    match
                    for match in catalogue_matches
                    if (
                        page_surface(PAGE_BY_KEY[match.item.page_key])
                        if match.item.page_key in PAGE_BY_KEY
                        else "Operational"
                    ) == surface_view
                ]

            if nav_query.strip():
                corrected = next(
                    (
                        match.corrected_query
                        for match in catalogue_matches
                        if match.corrected_query
                        and match.corrected_query != " ".join(nav_query.lower().split())
                    ),
                    "",
                )
                if corrected:
                    st.caption(f"Typo correction: **{corrected}**")

            excluded_page_keys = {active_key} if active_key else set()
            eligible = [
                match
                for match in catalogue_matches
                if not (
                    match.item.item_type == "Module page"
                    and match.item.page_key in excluded_page_keys
                )
            ]
            recommended_view = (
                browse_mode == "Recommended"
                and not nav_query.strip()
                and nav_category == "All"
            )
            if recommended_view:
                preferred_keys = [
                    key
                    for key in [
                        *st.session_state.get("ui_favourites", []),
                        *st.session_state.get("ui_recent_pages", []),
                    ]
                    if key in PAGE_BY_KEY and key not in excluded_page_keys
                ]
                page_match_by_key = {
                    match.item.page_key: match
                    for match in eligible
                    if match.item.item_type == "Module page"
                }
                preferred_matches = [
                    page_match_by_key[key]
                    for key in dict.fromkeys(preferred_keys)
                    if key in page_match_by_key
                ]
                featured_matches = [
                    match
                    for match in eligible
                    if match.item.item_type == "Module page"
                    and match.item.page_key in PAGE_BY_KEY
                    and PAGE_BY_KEY[match.item.page_key].featured
                ]
                results = list(dict.fromkeys([*preferred_matches, *featured_matches]))[:12]
                page_number = 1
                total_pages = 1
                result_start = 0
            else:
                import math

                search_signature = f"{nav_query.strip().lower()}|{nav_category}|{surface_view}|{browse_mode}|{nav_page_size}"
                if st.session_state.get("_bio_global_nav_signature") != search_signature:
                    st.session_state["_bio_global_nav_signature"] = search_signature
                    st.session_state["_bio_global_nav_page"] = 1
                total_pages = max(1, math.ceil(len(eligible) / int(nav_page_size)))
                requested_page = int(st.session_state.get("_bio_global_nav_page", 1) or 1)
                requested_page = min(max(requested_page, 1), total_pages)
                if st.session_state.get("_bio_global_nav_page") != requested_page:
                    st.session_state["_bio_global_nav_page"] = requested_page
                page_number = st.number_input(
                    "Result page",
                    min_value=1,
                    max_value=total_pages,
                    step=1,
                    key="_bio_global_nav_page",
                )
                result_start = (int(page_number) - 1) * int(nav_page_size)
                results = eligible[result_start : result_start + int(nav_page_size)]

            range_start = result_start + 1 if results else 0
            range_end = result_start + len(results)
            st.markdown(
                f'<div class="bio-result-label">{len(eligible)} catalogue items · showing {range_start}–{range_end} · page {int(page_number)} of {total_pages}</div>',
                unsafe_allow_html=True,
            )
            if not results:
                st.info("No matching module or embedded workspace. Try a broader keyword or select All domains.")
            else:
                result_columns = st.columns(2, gap="small")
                for index, match in enumerate(results):
                    item = match.item
                    with result_columns[index % 2]:
                        finder_icon = svg_icon_html(
                            page_key=item.page_key or item.key,
                            category=item.category,
                            title=item.title,
                            hint=item.description,
                            size=22,
                            css_class="bio-svg-icon bio-finder-result-svg",
                        )
                        icon_column, link_column = st.columns(
                            [0.16, 0.84], gap="small", vertical_alignment="center"
                        )
                        with icon_column:
                            st.markdown(
                                f'<div class="bio-finder-result-icon" aria-hidden="true">{finder_icon}</div>',
                                unsafe_allow_html=True,
                            )
                        with link_column:
                            if item.page_path:
                                try:
                                    st.page_link(
                                        item.page_path,
                                        label=item.title,
                                        width="stretch",
                                    )
                                except (KeyError, RuntimeError):
                                    st.caption(item.title)
                            else:
                                st.button(
                                    item.title,
                                    disabled=True,
                                    width="stretch",
                                    key=f"_bio_unlinked_{item.key}",
                                )
                        if item.item_type == "Embedded workspace":
                            st.caption(f"Embedded workspace · opens in {item.page_title}")
                        elif nav_query.strip() and match.reasons:
                            st.caption(f"↳ {' · '.join(match.reasons[:2])}")
            st.divider()
            _page_link("module_catalogue_search", "Open complete module catalogue")

    # Step 125: durable live-analysis timeline and scientific notification center.
    live_store = None
    live_runs = []
    persistent_notifications = []
    unread_notifications = 0
    background_jobs = []
    queue = None
    try:
        from biointel.ui.live_experience import get_live_store

        live_store = get_live_store()
        live_store.mark_stale_runs(after_minutes=180)
        live_runs = live_store.recent_runs(limit=20)
        persistent_notifications = live_store.notifications(limit=50)
        unread_notifications = live_store.unread_count()
    except Exception:
        live_store = None

    try:
        from biointel.jobs.local_queue import LocalJobQueue

        queue = LocalJobQueue(runtime_database_path(PROJECT_ROOT, "jobs.sqlite3"))
        background_jobs = queue.list(limit=25)
        if live_store is not None:
            recent_cutoff = datetime.now(UTC) - timedelta(hours=8)
            for job in background_jobs:
                stamp = job.updated_at_utc or job.completed_at_utc or job.created_at_utc
                try:
                    observed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
                except (TypeError, ValueError):
                    continue
                if observed.tzinfo is None:
                    observed = observed.replace(tzinfo=UTC)
                if observed < recent_cutoff or job.status not in {"completed", "failed", "cancelled"}:
                    continue
                level = "success" if job.status == "completed" else ("warning" if job.status == "cancelled" else "error")
                live_store.notify(
                    f"Background job {job.status}",
                    f"{job.job_type} · {job.current_stage or job.status}",
                    level=level, source="background-job",
                    action_label="Open job center", action_target="performance_jobs",
                    dedupe_key=f"job:{job.job_id}:{job.status}", reopen=False,
                )
            persistent_notifications = live_store.notifications(limit=50)
            unread_notifications = live_store.unread_count()
    except Exception:
        queue = None
        background_jobs = []

    with shell_right:
        status_col, timeline_col, notice_col, settings_col = st.columns(
            [1.18, 1.18, 1.02, 0.92], gap="small"
        )
        with status_col:
            with st.popover(
                f"● {healthy_count}/{db_count}" if db_count else "● Status",
                width="stretch",
            ):
                st.markdown("#### System status")
                st.metric(
                    "Databases online", f"{healthy_count}/{db_count}" if db_count else "Unavailable"
                )
                if health.get("error"):
                    st.warning(str(health["error"]))
                else:
                    st.caption("Cached local database and index health snapshot.")
                latest_run = st.session_state.get("_bio_latest_run")
                if isinstance(latest_run, dict):
                    st.divider()
                    st.markdown("#### Latest analysis")
                    st.caption(
                        f"{latest_run.get('workflow', 'Analysis')} · "
                        f"{latest_run.get('status', 'unknown')} · "
                        f"{float(latest_run.get('elapsed_seconds') or 0):.2f}s"
                    )
                    st.download_button(
                        "Download latest run trace",
                        json.dumps(latest_run, indent=2, sort_keys=True, default=str),
                        "biointel_latest_run_trace.json",
                        "application/json",
                        width="stretch",
                        key="_bio_latest_run_download",
                    )
                _page_link("platform_quality", "Quality center")
                _page_link("diagnostics", "Diagnostics")

        with timeline_col:
            interactive_active = [item for item in live_runs if item.status in {"running", "queued", "paused"}]
            job_active = [item for item in background_jobs if item.status in {"running", "queued", "paused", "blocked"}]
            active_count = len(interactive_active) + len(job_active)
            with st.popover(f"◉ Live {active_count}" if active_count else "◉ Timeline", width="stretch"):
                st.markdown("#### Live Analysis Timeline")
                st.caption("Persistent stages survive navigation and desktop restarts.")
                live_tab, recent_tab = st.tabs(["Live", "Recent"] )
                with live_tab:
                    if not interactive_active and not job_active:
                        st.info("No analysis is currently running.")
                    for run in interactive_active[:5]:
                        st.markdown(f"**{html.escape(run.workflow)}**")
                        st.progress(min(max(float(run.progress), 0.0), 1.0), text=run.current_stage or run.status.title())
                        if run.detail:
                            st.caption(run.detail)
                        if run.page_key:
                            _page_link(run.page_key, "Open module")
                    for job in job_active[:5]:
                        st.markdown(f"**{html.escape(job.job_type)}**")
                        st.progress(min(max(float(job.progress_percent) / 100.0, 0.0), 1.0), text=job.current_stage or job.status.title())
                        action_columns = st.columns(2, gap="small")
                        if queue is not None and job.status == "running":
                            if action_columns[0].button("Pause", key=f"_live_pause_{job.job_id}", width="stretch"):
                                queue.request_pause(job.job_id)
                                st.rerun()
                            if action_columns[1].button("Cancel", key=f"_live_cancel_{job.job_id}", width="stretch"):
                                queue.request_cancel(job.job_id)
                                st.rerun()
                        elif queue is not None and job.status == "paused":
                            if action_columns[0].button("Resume", key=f"_live_resume_{job.job_id}", width="stretch"):
                                queue.resume(job.job_id)
                                st.rerun()
                            if action_columns[1].button("Cancel", key=f"_live_cancel_{job.job_id}", width="stretch"):
                                queue.request_cancel(job.job_id)
                                st.rerun()
                    _page_link("performance_jobs", "Open full Job Center")
                with recent_tab:
                    recent_items = [item for item in live_runs if item.status not in {"running", "queued", "paused"}][:8]
                    if not recent_items:
                        st.caption("No completed analysis timeline is available yet.")
                    for run in recent_items:
                        status_icon = {"completed": "✓", "failed": "!", "cancelled": "×"}.get(run.status, "•")
                        with st.expander(f"{status_icon} {run.workflow} · {run.status}", expanded=False):
                            stages = live_store.stages(run.run_id) if live_store is not None else []
                            for stage in stages:
                                progress_text = f" · {float(stage.progress) * 100:.0f}%" if stage.progress is not None else ""
                                st.markdown(f"**{html.escape(stage.label)}**{progress_text}")
                                if stage.detail:
                                    st.caption(stage.detail)
                            if run.error:
                                st.error(run.error)
                            if run.page_key:
                                _page_link(run.page_key, "Open source module")
                    if live_store is not None:
                        st.download_button(
                            "Export timeline state",
                            json.dumps(live_store.export_state(), indent=2, sort_keys=True, default=str),
                            "biointel_live_analysis_timeline.json",
                            "application/json", width="stretch", key="_bio_live_timeline_export",
                        )
                if st.button("Refresh timeline", width="stretch", key="_bio_refresh_live_timeline"):
                    st.rerun()

        with notice_col:
            session_notifications = list(st.session_state.get("_bio_notifications", []))
            persistent_keys = {item.dedupe_key for item in persistent_notifications}
            fallback_notifications = [
                item for item in session_notifications
                if str(item.get("dedupe_key", "")) not in persistent_keys
            ]
            total_visible = len(persistent_notifications) + len(fallback_notifications)
            label_count = unread_notifications or len(fallback_notifications)
            with st.popover(f"Alerts {label_count}" if label_count else "Alerts", width="stretch"):
                st.markdown("#### Scientific Notification Center")
                st.caption(f"{unread_notifications} unread · {total_visible} active")
                filter_mode = st.selectbox(
                    "Show", ["Unread", "All", "Warnings & errors"],
                    key="_bio_notification_filter", label_visibility="collapsed",
                )
                if live_store is not None:
                    if filter_mode == "Unread":
                        shown = live_store.notifications(limit=30, include_read=False)
                    elif filter_mode == "Warnings & errors":
                        shown = live_store.notifications(limit=30, include_read=True, levels=("warning", "error", "critical"))
                    else:
                        shown = live_store.notifications(limit=30, include_read=True)
                else:
                    shown = []
                if not shown and not fallback_notifications:
                    st.caption("No scientific notifications match this filter.")
                level_icons = {"success": "✓", "warning": "⚠", "error": "!", "critical": "‼", "info": "i"}
                for item in shown[:15]:
                    unread = item.read_at_utc is None
                    st.markdown(
                        f"**{level_icons.get(item.level, 'i')} {html.escape(item.title)}**"
                        + (" · **new**" if unread else "")
                    )
                    st.caption(item.message)
                    meta = f"{item.source} · {item.updated_at_utc.replace('T', ' ')[:16]} UTC"
                    if item.occurrence_count > 1:
                        meta += f" · repeated {item.occurrence_count}×"
                    st.caption(meta)
                    action_cols = st.columns([0.62, 0.38], gap="small")
                    with action_cols[0]:
                        if item.action_target:
                            _page_link(item.action_target, item.action_label or "Open")
                    with action_cols[1]:
                        if st.button("Dismiss", key=f"_bio_dismiss_{item.notification_id}", width="stretch"):
                            live_store.dismiss(item.notification_id)
                            st.rerun()
                    st.divider()
                for index, item in enumerate(fallback_notifications[:5]):
                    st.markdown(f"**{html.escape(str(item.get('title', 'Update')))}**")
                    st.caption(str(item.get("message", "")))
                    if index < min(len(fallback_notifications), 5) - 1:
                        st.divider()
                control_cols = st.columns(2, gap="small")
                if live_store is not None and control_cols[0].button("Mark read", width="stretch", key="_bio_mark_notifications_read"):
                    live_store.mark_read()
                    st.session_state["_bio_notifications"] = []
                    st.rerun()
                if control_cols[1].button("Clear", width="stretch", key="_bio_clear_notifications"):
                    if live_store is not None:
                        live_store.clear()
                    st.session_state["_bio_notifications"] = []
                    st.rerun()
                if live_store is not None:
                    st.download_button(
                        "Export notifications",
                        json.dumps([item.__dict__ for item in persistent_notifications], indent=2, sort_keys=True, default=str),
                        "biointel_scientific_notifications.json",
                        "application/json", width="stretch", key="_bio_notifications_export",
                    )
        with settings_col:
            with st.popover("View", width="stretch"):
                st.markdown("#### Interface")
                st.markdown(
                    '<div class="bio-settings-note">Use a restrained theme for daily work or open Appearance Studio for advanced accessibility controls.</div>',
                    unsafe_allow_html=True,
                )
                st.selectbox("Appearance", ["Dark", "Light", "System"], key="ui_appearance_mode")
                theme_options = list(
                    dict.fromkeys(
                        [
                            *st.session_state.get("ui_theme_favourites", []),
                            *st.session_state.get("ui_recent_themes", []),
                            *PALETTES.keys(),
                        ]
                    )
                )
                st.selectbox("Theme", theme_options, key="ui_palette")
                st.selectbox("Text font", list(FONTS), key="ui_font_family")
                density_col, contrast_col = st.columns(2)
                with density_col:
                    st.selectbox("Density", list(DENSITY_MODES), key="ui_density_mode")
                with contrast_col:
                    st.toggle("Contrast", key="ui_high_contrast")
                st.selectbox(
                    "Performance",
                    list(PERFORMANCE_MODES),
                    key="ui_performance_mode",
                    help="Adaptive selects a balanced profile; Performance removes expensive blur and decoration.",
                )
                st.session_state["ui_reduce_effects"] = st.session_state.get("ui_performance_mode") == "Performance"
                st.selectbox(
                    "Motion",
                    list(MOTION_MODES),
                    key="ui_motion_mode",
                    help="Balanced removes ambient loops; Reduced also disables transforms, shimmer and smooth scrolling.",
                )
                st.session_state["ui_reduce_motion"] = (
                    st.session_state.get("ui_motion_mode") == "Reduced"
                )
                st.slider(
                    "Text scale",
                    min_value=0.85,
                    max_value=1.25,
                    step=0.05,
                    format="%.2f×",
                    key="ui_font_scale",
                )
                save_col, reset_col = st.columns(2)
                with save_col:
                    if st.button("Save", width="stretch", key="_bio_save_shell_preferences"):
                        selected_theme = str(st.session_state.get("ui_palette", DEFAULT_THEME))
                        st.session_state["ui_recent_themes"] = list(
                            dict.fromkeys([selected_theme, *st.session_state.get("ui_recent_themes", [])])
                        )[:12]
                        persist_ui_preferences()
                        st.toast("Interface preferences saved")
                with reset_col:
                    if st.button("Reset", width="stretch", key="_bio_reset_shell_preferences"):
                        reset_ui_preferences()
                        st.rerun()
                _page_link("appearance", "Advanced appearance")

    if active_page:
        is_pinned = active_page.key in favourites
        previous_page, next_page = adjacent_pages(active_page.key)
        history_back_key, history_forward_key = _history_targets(active_page.key)
        history_back = PAGE_BY_KEY.get(history_back_key) if history_back_key else None
        history_forward = PAGE_BY_KEY.get(history_forward_key) if history_forward_key else None
        context_col, action_col = st.columns([0.72, 0.28], gap="small", vertical_alignment="center")
        with context_col:
            # Keep only a compact hierarchy line here; the page hero owns the title
            # and description. This removes the previous triple-heading repetition.
            st.markdown(
                f"""
                <nav class="bio-compact-breadcrumb" aria-label="Breadcrumb">
                  <span>BioIntel AI</span><span aria-hidden="true">›</span>
                  <span>{html.escape(active_page.category)}</span><span aria-hidden="true">›</span>
                  <strong>{html.escape(active_page.title)}</strong>
                </nav>
                """,
                unsafe_allow_html=True,
            )
            active_context = []
            for label, key in (
                ("Project", "active_project_name"),
                ("Dataset", "active_dataset_name"),
                ("Model", "active_model_name"),
                ("Target", "active_target_name"),
            ):
                value = st.session_state.get(key)
                if value:
                    active_context.append(
                        f"<span><b>{html.escape(label)}:</b> {html.escape(str(value))}</span>"
                    )
            if active_context:
                st.markdown(
                    '<div class="bio-workspace-context">' + "".join(active_context) + "</div>",
                    unsafe_allow_html=True,
                )
        with action_col:
            pin_col, move_col, help_col = st.columns(3, gap="small")
            with pin_col:
                if st.button(
                    "Pinned" if is_pinned else "Pin",
                    width="stretch",
                    key=f"_bio_pin_{active_page.key}",
                    help=(
                        "Remove this module from Pinned & recent."
                        if is_pinned
                        else "Keep this module in Pinned & recent."
                    ),
                ):
                    updated = [
                        key
                        for key in st.session_state.get("ui_favourites", [])
                        if key in PAGE_BY_KEY
                    ]
                    if is_pinned:
                        updated = [key for key in updated if key != active_page.key]
                    else:
                        updated = [
                            active_page.key,
                            *[key for key in updated if key != active_page.key],
                        ]
                    st.session_state["ui_favourites"] = updated[:12]
                    persist_ui_preferences()
                    st.rerun()
            with move_col:
                with st.popover("Navigate", width="stretch"):
                    st.markdown("#### Visit history")
                    history_back_col, history_forward_col = st.columns(2, gap="small")
                    with history_back_col:
                        if st.button(
                            "← Back",
                            disabled=history_back is None,
                            width="stretch",
                            key=f"_bio_history_back_{active_page.key}",
                        ):
                            _navigate_history(active_page.key, "back")
                    with history_forward_col:
                        if st.button(
                            "Forward →",
                            disabled=history_forward is None,
                            width="stretch",
                            key=f"_bio_history_forward_{active_page.key}",
                        ):
                            _navigate_history(active_page.key, "forward")
                    if history_back is not None:
                        st.caption(f"Back: {history_back.title}")
                    if history_forward is not None:
                        st.caption(f"Forward: {history_forward.title}")
                    st.divider()
                    st.markdown(f"#### Move within {html.escape(active_page.category)}")
                    if previous_page is not None:
                        _page_link(previous_page.key, f"← {previous_page.title}")
                    else:
                        st.caption("This is the first module in this domain.")
                    if next_page is not None:
                        _page_link(next_page.key, f"{next_page.title} →")
                    else:
                        st.caption("This is the last module in this domain.")
                    st.divider()
                    _page_link("command_center", "Open all modules")
            with help_col:
                with st.popover("Help", width="stretch"):
                    st.markdown("#### About this module")
                    st.write(active_page.description)
                    st.caption("Workflow keywords: " + ", ".join(active_page.keywords[:8]))
                    st.divider()
                    _page_link("quick_start", "Open guided analysis")
                    _page_link("command_center", "Find another module")


    # Step207: shared stability, provenance and data-readiness controls for
    # Bioinformatics, Discovery, Lab Analytics and Neuro/CNS pages. Protected
    # DTI/LIMS/instrument pages are filtered inside the renderer.
    try:
        from biointel.module_runtime_v207.ui import render_module_runtime_sidebar

        active_key = current_page_key()
        active_page = PAGE_BY_KEY.get(active_key) if active_key else None
        if active_page is not None:
            render_module_runtime_sidebar(
                page_key=active_page.key,
                page_path=active_page.path,
                title=active_page.title,
                category=active_page.category,
            )
    except Exception as exc:
        # The shared assistant must never prevent a scientific page from loading.
        logging.getLogger(__name__).warning("Step207 module runtime sidebar unavailable: %s", exc)


def _brand_component_value(value):
    from biointel.ui.public_branding import brand_public_value

    return brand_public_value(value, allow_legal=_public_branding_legal_view())


def hero(
    title: str,
    subtitle: str,
    eyebrow: str = "BioIntel AI",
    chips: list[str] | None = None,
) -> None:
    """Render the global module-specific premium hero and workflow ribbon."""
    from biointel.ui.premium_visuals import premium_hero_inner_html

    title = str(_brand_component_value(title))
    subtitle = str(_brand_component_value(subtitle))
    eyebrow = str(_brand_component_value(eyebrow))
    chips = list(_brand_component_value(chips or []))
    active_key = current_page_key()
    active_page = PAGE_BY_KEY.get(active_key) if active_key else None
    # Callers may include a legacy emoji in the visible title. Preserve the
    # wording while removing only a leading symbol now represented by SVG.
    clean_title = title.strip()
    clean_title = clean_title.lstrip("🧬✨🚀💊🧩🧠🔬📊🧹✅🧰🧵🧫✂️🦠🔎🕸️📈🔗🏆🗄️🛡️🧾🔌⚡🧪🌐🗂️🌉⚖️ ") or title
    stage_key = f"_bio_workflow_stage_{active_key or 'global'}"
    active_stage = int(st.session_state.get(stage_key, 0) or 0)
    inner = premium_hero_inner_html(
        page_key=active_key,
        category=active_page.category if active_page else None,
        title=clean_title,
        subtitle=subtitle,
        eyebrow=eyebrow,
        chips=chips,
        active_stage=active_stage,
    )
    st.markdown(
        f'<section class="bio-hero bio-premium-hero" data-module-key="{html.escape(active_key or "unknown")}">{inner}</section>',
        unsafe_allow_html=True,
    )


def section_title(title: str, icon: str = "section") -> None:
    from biointel.ui.premium_visuals import svg_icon_html
    title = str(_brand_component_value(title))

    icon_html = svg_icon_html(title=title, hint=icon, size=18, css_class="bio-svg-icon bio-section-svg")
    st.markdown(
        f'<div class="bio-section-label">{icon_html}<span>{html.escape(title)}</span></div>',
        unsafe_allow_html=True,
    )


def feature_card(
    title: str,
    copy: str,
    icon: str,
) -> None:
    from biointel.ui.premium_visuals import svg_icon_html
    title = str(_brand_component_value(title))
    copy = str(_brand_component_value(copy))

    icon_html = svg_icon_html(title=title, hint=icon, size=24, css_class="bio-svg-icon")
    st.markdown(
        f"""
        <div class="bio-card bio-glass-card">
          <div class="bio-card-icon">{icon_html}</div>
          <div class="bio-card-title">{html.escape(title)}</div>
          <div class="bio-card-copy">{html.escape(copy)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def badge(
    text: str,
    tone: str = "success",
) -> None:
    text = str(_brand_component_value(text))
    safe_tone = (
        tone
        if tone
        in {
            "success",
            "warning",
            "danger",
        }
        else "success"
    )
    st.markdown(
        f'<span class="bio-badge bio-badge-{safe_tone}">{html.escape(text)}</span>',
        unsafe_allow_html=True,
    )


def empty_state(
    title: str,
    copy: str,
    icon: str = "empty state",
) -> None:
    from biointel.ui.premium_visuals import svg_icon_html
    title = str(_brand_component_value(title))
    copy = str(_brand_component_value(copy))

    icon_html = svg_icon_html(title=title, hint=icon, size=32, css_class="bio-svg-icon bio-empty-svg")
    st.markdown(
        f"""
        <div class="bio-empty">
          <div class="bio-empty-icon">{icon_html}</div>
          <div class="bio-empty-title">{html.escape(title)}</div>
          <div class="bio-empty-copy">{html.escape(copy)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def executive_kpis(
    items: list[tuple[str, str, str]],
) -> None:
    items = list(_brand_component_value(items))
    cards = []
    for label, value, copy in items:
        cards.append(
            f"""
            <div class="bio-kpi">
              <div class="bio-kpi-label">{html.escape(label)}</div>
              <div class="bio-kpi-value">{html.escape(value)}</div>
              <div class="bio-kpi-copy">{html.escape(copy)}</div>
            </div>
            """
        )
    st.markdown(
        '<div class="bio-board">' + "".join(cards) + "</div>",
        unsafe_allow_html=True,
    )


def status_chips(
    items: list[tuple[str, str]],
) -> None:
    items = list(_brand_component_value(items))
    running_terms = ("running", "syncing", "processing", "loading", "connecting", "training")
    chips: list[str] = []
    for icon, label in items:
        state = "running" if any(term in label.casefold() for term in running_terms) else "idle"
        chips.append(
            f'<span class="bio-status-chip" data-state="{state}">'
            f"{html.escape(icon)} {html.escape(label)}</span>"
        )
    content = "".join(chips)
    st.markdown(
        f'<div class="bio-status-row">{content}</div>',
        unsafe_allow_html=True,
    )


def professional_strip(
    title: str,
    copy: str,
) -> None:
    title = str(_brand_component_value(title))
    copy = str(_brand_component_value(copy))
    st.markdown(
        f"""
        <div class="bio-professional-strip">
          <strong>{html.escape(title)}</strong>
          <span>{html.escape(copy)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def timeline(
    items: list[dict[str, str]],
) -> None:
    items = list(_brand_component_value(items))
    if not items:
        empty_state(
            "No activity yet",
            "Project, experiment and audit events will appear here.",
            "◌",
        )
        return
    rendered = []
    for item in items:
        rendered.append(
            f"""
            <div class="bio-timeline-item">
              <div class="bio-timeline-title">
                {html.escape(item.get("title", "Activity"))}
              </div>
              <div class="bio-timeline-meta">
                {html.escape(item.get("meta", ""))}
              </div>
              <div class="bio-timeline-copy">
                {html.escape(item.get("copy", ""))}
              </div>
            </div>
            """
        )
    st.markdown(
        '<div class="bio-timeline">' + "".join(rendered) + "</div>",
        unsafe_allow_html=True,
    )


def plotly_layout() -> dict[str, object]:
    palette = _current_palette()
    return {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"color": "#DCE4F0"},
        "title": {
            "font": {
                "color": "#F8FAFC",
                "size": 18,
            }
        },
        "xaxis": {
            "gridcolor": "rgba(148,163,184,0.12)",
            "zerolinecolor": "rgba(148,163,184,0.16)",
        },
        "yaxis": {
            "gridcolor": "rgba(148,163,184,0.12)",
            "zerolinecolor": "rgba(148,163,184,0.16)",
        },
        "colorway": (
            ["#3B82F6", "#22D3EE", "#22C55E", "#F59E0B", "#EF4444", "#8B5CF6", "#94A3B8"]
            if palette.name == "BioIntel Signature"
            else [palette.primary, palette.secondary, palette.accent, "#F59E0B", "#FB7185", "#A78BFA"]
        ),
        "legend": {
            "bgcolor": "rgba(0,0,0,0)",
        },
        "margin": {
            "l": 28,
            "r": 20,
            "t": 54,
            "b": 28,
        },
    }


def command_bar(
    title: str,
    copy: str,
) -> None:
    title = str(_brand_component_value(title))
    copy = str(_brand_component_value(copy))
    st.markdown(
        f"""
        <div class="bio-command-bar">
          <strong>{html.escape(title)}</strong>
          <span>{html.escape(copy)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def database_cards(
    items: list[dict[str, object]],
) -> None:
    from biointel.ui.premium_visuals import svg_icon_html

    items = list(_brand_component_value(items))
    cards = []
    for item in items:
        stats = item.get("stats", [])
        item_title = str(item.get("title", "Database"))
        icon_html = svg_icon_html(
            title=item_title,
            hint=str(item.get("icon", item_title)),
            size=24,
            css_class="bio-svg-icon bio-db-svg",
        )
        stats_html = "".join(
            f"""
            <div class="bio-db-stat">
              <strong>{html.escape(str(value))}</strong>
              <span>{html.escape(str(label))}</span>
            </div>
            """
            for label, value in stats
        )
        cards.append(
            f"""
            <div class="bio-db-card">
              <div class="bio-db-top">
                <div class="bio-db-icon">
                  {icon_html}
                </div>
                <div class="bio-db-status">
                  ● {html.escape(str(item.get("status", "healthy")))}
                </div>
              </div>
              <div class="bio-db-title">
                {html.escape(str(item.get("title", "Database")))}
              </div>
              <div class="bio-db-copy">
                {html.escape(str(item.get("copy", "")))}
              </div>
              <div class="bio-db-stats">{stats_html}</div>
            </div>
            """
        )
    st.markdown(
        '<div class="bio-db-grid">' + "".join(cards) + "</div>",
        unsafe_allow_html=True,
    )


def insight_callout(
    title: str,
    copy: str,
    icon: str = "insight",
    *,
    tone: str = "default",
) -> None:
    title = str(_brand_component_value(title))
    copy = str(_brand_component_value(copy))
    # `tone` was added by later workspace pages. Keep this renderer backward
    # compatible so a page-level styling option can never become a runtime crash.
    safe_tone = str(tone or "default").strip().lower()
    if safe_tone not in {"default", "info", "success", "warning", "danger"}:
        safe_tone = "default"
    from biointel.ui.premium_visuals import svg_icon_html
    icon_html = svg_icon_html(title=title, hint=icon, size=22, css_class="bio-svg-icon bio-insight-svg")
    st.markdown(
        f"""
        <div class="bio-insight bio-insight-{html.escape(safe_tone)}">
          <div class="bio-insight-icon">
            {icon_html}
          </div>
          <div>
            <div class="bio-insight-title">
              {html.escape(title)}
            </div>
            <div class="bio-insight-copy">
              {html.escape(copy)}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def density_bar(
    label: str,
    value: float,
    maximum: float,
    *,
    display_value: str | None = None,
) -> None:
    safe_maximum = max(float(maximum), 1.0)
    percent = min(
        max(float(value) / safe_maximum * 100.0, 0.0),
        100.0,
    )
    rendered_value = display_value if display_value is not None else f"{value:,.0f}"
    st.markdown(
        f"""
        <div class="bio-density">
          <div class="bio-density-head">
            <span>{html.escape(label)}</span>
            <span>{html.escape(rendered_value)}</span>
          </div>
          <div class="bio-density-track">
            <div
              class="bio-density-fill"
              style="width:{percent:.2f}%"
            ></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
