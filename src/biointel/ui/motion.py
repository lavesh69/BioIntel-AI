from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

MOTION_MODES: tuple[str, ...] = ("Full", "Balanced", "Reduced")
DEFAULT_MOTION_MODE = "Balanced"
LARGE_CHART_POINT_THRESHOLD = 5000


@dataclass(frozen=True)
class MotionProfile:
    name: str
    duration_fast_ms: int
    duration_normal_ms: int
    duration_slow_ms: int
    hover_lift_px: float
    ambient_motion: bool
    stagger_ms: int


_BASE_PROFILES: dict[str, MotionProfile] = {
    "minimal": MotionProfile("Minimal", 110, 170, 260, 1.0, False, 34),
    "technical": MotionProfile("Technical", 90, 150, 230, 1.5, False, 28),
    "executive": MotionProfile("Executive", 120, 190, 300, 2.0, False, 38),
    "fluid": MotionProfile("Fluid", 140, 230, 380, 3.0, True, 52),
    "organic": MotionProfile("Organic", 130, 220, 350, 2.5, True, 46),
}

_MINIMAL_THEMES = {
    "Clinical",
    "Nordic Frost",
    "Ivory Editorial",
    "Minimal Slate",
    "Bronze Anatomy",
}
_TECHNICAL_THEMES = {
    "Regulatory",
    "Cyber",
    "Graphite",
    "Midnight Lab",
    "Quantum",
    "Obsidian Engineering",
    "Ink & Blueprint",
    "Black Diamond",
    "Electric Lime",
    "Crimson Genome",
}
_FLUID_THEMES = {"Aurora", "Ocean", "Rose", "Violet", "Lavender Genome", "Rose Quartz Laboratory", "Velvet Neon", "Solar Helix"}
_ORGANIC_THEMES = {"Emerald", "Sunset", "Nature", "Emerald Muse", "Copper Eclipse"}


def normalize_motion_mode(value: object, *, reduce_motion: bool = False) -> str:
    if reduce_motion:
        return "Reduced"
    text = str(value or DEFAULT_MOTION_MODE).strip().title()
    return text if text in MOTION_MODES else DEFAULT_MOTION_MODE


def motion_profile_for(theme_name: str, mode: str) -> MotionProfile:
    normalized_mode = normalize_motion_mode(mode)
    if theme_name in _MINIMAL_THEMES:
        base = _BASE_PROFILES["minimal"]
    elif theme_name in _TECHNICAL_THEMES:
        base = _BASE_PROFILES["technical"]
    elif theme_name in _FLUID_THEMES:
        base = _BASE_PROFILES["fluid"]
    elif theme_name in _ORGANIC_THEMES:
        base = _BASE_PROFILES["organic"]
    else:
        base = _BASE_PROFILES["executive"]

    if normalized_mode == "Reduced":
        return MotionProfile("Reduced", 1, 1, 1, 0.0, False, 0)
    if normalized_mode == "Balanced":
        return MotionProfile(
            name=f"Balanced {base.name}",
            duration_fast_ms=max(80, round(base.duration_fast_ms * 0.88)),
            duration_normal_ms=max(130, round(base.duration_normal_ms * 0.84)),
            duration_slow_ms=max(210, round(base.duration_slow_ms * 0.78)),
            hover_lift_px=min(2.0, base.hover_lift_px),
            ambient_motion=False,
            stagger_ms=min(42, base.stagger_ms),
        )
    return base


def estimate_figure_points(figure: Any) -> int:
    """Best-effort count used to disable expensive chart transitions."""

    total = 0
    for trace in getattr(figure, "data", ()) or ():
        candidates: Iterable[Any] = (
            getattr(trace, "x", None),
            getattr(trace, "y", None),
            getattr(trace, "z", None),
            getattr(trace, "values", None),
            getattr(trace, "lat", None),
            getattr(trace, "lon", None),
        )
        lengths: list[int] = []
        for value in candidates:
            if value is None:
                continue
            try:
                lengths.append(len(value))
            except TypeError:
                continue
        total += max(lengths, default=0)
    return total


def plotly_transition_for(
    mode: str,
    *,
    point_count: int = 0,
    threshold: int = LARGE_CHART_POINT_THRESHOLD,
) -> dict[str, Any]:
    normalized = normalize_motion_mode(mode)
    if normalized == "Reduced" or point_count > threshold:
        return {"duration": 0}
    duration = 260 if normalized == "Full" else 190
    return {
        "duration": duration,
        "easing": "cubic-in-out",
        "ordering": "traces first",
    }


def configure_figure_motion(
    figure: Any,
    *,
    mode: str = DEFAULT_MOTION_MODE,
    preserve_view: bool = True,
    revision_key: str = "biointel-view",
) -> Any:
    """Apply safe Plotly transitions and preserve zoom/camera state.

    Large figures automatically receive zero-duration transitions so scientific
    visualisations remain responsive on lower-power devices.
    """

    point_count = estimate_figure_points(figure)
    transition = plotly_transition_for(mode, point_count=point_count)
    update: dict[str, Any] = {"transition": transition}
    if preserve_view:
        update.update(
            {
                "uirevision": revision_key,
                "selectionrevision": revision_key,
                "editrevision": revision_key,
            }
        )
    try:
        figure.update_layout(**update)
    except (AttributeError, TypeError, ValueError):
        return figure
    return figure
