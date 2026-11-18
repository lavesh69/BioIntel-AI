from __future__ import annotations

from pathlib import Path

from biointel.ui.aesthetic import premium_aesthetic_css
from biointel.ui.motion import (
    LARGE_CHART_POINT_THRESHOLD,
    configure_figure_motion,
    motion_profile_for,
    normalize_motion_mode,
    plotly_transition_for,
)
from biointel.ui.style_catalog import FONTS, THEMES

ROOT = Path(__file__).resolve().parents[1]


class _FakeFigure:
    def __init__(self, points: int) -> None:
        self.data = [type("Trace", (), {"x": list(range(points)), "y": list(range(points))})()]
        self.layout_update: dict[str, object] = {}

    def update_layout(self, **kwargs) -> None:
        self.layout_update.update(kwargs)


def test_motion_modes_are_normalised_and_theme_aware() -> None:
    assert normalize_motion_mode("full") == "Full"
    assert normalize_motion_mode("unknown") == "Balanced"
    assert normalize_motion_mode("Full", reduce_motion=True) == "Reduced"
    assert motion_profile_for("Aurora", "Full").ambient_motion is True
    assert motion_profile_for("Clinical", "Balanced").ambient_motion is False
    assert motion_profile_for("Executive", "Reduced").hover_lift_px == 0


def test_reduced_motion_disables_transforms_shimmer_and_smooth_scroll() -> None:
    css = premium_aesthetic_css(
        THEMES["Executive"],
        FONTS["Inter"],
        motion_mode="Reduced",
    )
    assert "scroll-behavior: auto !important" in css
    assert "transform: none !important" in css
    assert "animation-name: none !important" in css
    assert "bio58-hero-shift" not in css


def test_balanced_motion_has_tokens_without_ambient_loop() -> None:
    css = premium_aesthetic_css(
        THEMES["Aurora"],
        FONTS["Inter"],
        motion_mode="Balanced",
    )
    assert "--motion-fast:" in css
    assert "--motion-normal:" in css
    assert "--ease-enter:" in css
    assert "bio58-hero-shift" not in css
    assert "bio58-indeterminate" in css


def test_full_fluid_theme_can_use_restrained_ambient_motion() -> None:
    css = premium_aesthetic_css(
        THEMES["Aurora"],
        FONTS["Inter"],
        motion_mode="Full",
    )
    assert "@keyframes bio58-hero-shift" in css
    assert "16s var(--ease-standard) infinite" in css


def test_large_plotly_figures_disable_transitions_and_preserve_view() -> None:
    figure = _FakeFigure(LARGE_CHART_POINT_THRESHOLD + 1)
    configure_figure_motion(figure, mode="Full", revision_key="large-chart")
    assert figure.layout_update["transition"] == {"duration": 0}
    assert figure.layout_update["uirevision"] == "large-chart"

    assert plotly_transition_for("Balanced", point_count=100)["duration"] > 0
    assert plotly_transition_for("Reduced", point_count=100) == {"duration": 0}


def test_desktop_and_mobile_shells_expose_real_loading_states() -> None:
    desktop = (ROOT / "platform" / "desktop" / "src" / "main.cjs").read_text(encoding="utf-8")
    mobile = (ROOT / "platform" / "mobile" / "src" / "main.ts").read_text(encoding="utf-8")
    mobile_css = (ROOT / "platform" / "mobile" / "src" / "style.css").read_text(encoding="utf-8")

    assert "createSplashWindow" in desktop
    assert "Starting scientific engine" in desktop
    assert "Loading visualisation runtime" in desktop
    assert "setBusy" in mobile
    assert "aria-busy" in mobile
    assert "Connection timed out after 10 seconds" in mobile
    assert "prefers-reduced-motion" in mobile_css


def test_shared_workflow_has_progress_skeleton_and_cooperative_cancel() -> None:
    source = (ROOT / "src" / "biointel" / "ui" / "workflow.py").read_text(encoding="utf-8")
    assert "render_skeleton" in source
    assert "indeterminate_loader" in source
    assert "render_cancel_control" in source
    assert "check_cancelled" in source
    assert "Completed {len(run.stages)} stages" in source
