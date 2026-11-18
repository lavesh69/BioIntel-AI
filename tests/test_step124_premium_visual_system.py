from __future__ import annotations

from pathlib import Path

from biointel.ui.appearance_engine import CHART_PROFILES, LIGHT_THEMES, THEME_META
from biointel.ui.experience_themes import EXPERIENCES
from biointel.ui.premium_visuals import (
    comparison_state_svg,
    icon_name_for,
    premium_hero_inner_html,
    premium_theme_names,
    svg_icon_html,
    workflow_ribbon_html,
)
from biointel.ui.style_catalog import THEMES

ROOT = Path(__file__).resolve().parents[1]


def test_step124_version_and_premium_theme_catalogue() -> None:
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "13.2.0"
    requested = set(premium_theme_names())
    assert len(requested) == 22
    assert requested <= set(THEMES)
    assert set(THEMES) == set(LIGHT_THEMES) == set(THEME_META) == set(CHART_PROFILES) == set(EXPERIENCES)
    assert len(THEMES) == 55
    assert len({EXPERIENCES[name].archetype for name in requested}) == 22


def test_custom_svg_icon_system_is_theme_aware_and_safe() -> None:
    assert icon_name_for(title="AI Protein Design") == "protein"
    assert icon_name_for(title="Flow Cytometry") == "microscope"
    assert icon_name_for(title="Evidence Review") == "shield"
    svg = svg_icon_html(title="Genome Variant Workbench", page_key="variant_workbench")
    assert svg.startswith("<svg")
    assert "currentColor" in svg
    assert "<script" not in svg.lower()
    assert 'viewBox="0 0 24 24"' in svg


def test_module_specific_hero_contains_icon_scene_and_workflow() -> None:
    markup = premium_hero_inner_html(
        page_key="protein_design_lab",
        category="Discovery",
        title="AI Protein Design & Mutation Engineering Lab",
        subtitle="Design and validate candidates.",
        eyebrow="BioIntel AI · v13.2.0",
        chips=["ProteinMPNN", "ColabFold"],
        active_stage=2,
    )
    for token in (
        "bio-hero-content",
        "bio-hero-icon-wrap",
        "bio-hero-scene-protein",
        "bio-workflow-ribbon",
        "bio-workflow-active",
        "ProteinMPNN",
    ):
        assert token in markup
    assert "\n" not in markup


def test_module_hero_without_optional_chips_cannot_become_markdown_code() -> None:
    markup = premium_hero_inner_html(
        page_key="sequence_analyzer",
        category="Genomics",
        title="Sequence Analyzer",
        subtitle="Validated sequence analysis.",
        eyebrow="BioIntel AI",
        chips=None,
    )
    assert "\n" not in markup
    assert '<div class="bio-hero-art"' in markup
    assert '<div class="bio-workflow-ribbon"' in markup


def test_workflow_ribbon_has_complete_active_and_pending_states() -> None:
    ribbon = workflow_ribbon_html(("Upload", "Validate", "Analyse", "Export"), active_index=2)
    assert ribbon.count("bio-workflow-step") == 4
    assert "bio-workflow-complete" in ribbon
    assert "bio-workflow-active" in ribbon
    assert "bio-workflow-pending" in ribbon


def test_before_after_visuals_are_inline_and_script_free() -> None:
    before = comparison_state_svg(title="FASTQ QC", label="Raw", after=False, motif="genomics")
    after = comparison_state_svg(title="FASTQ QC", label="Trimmed", after=True, motif="genomics")
    assert before.startswith("<svg") and after.startswith("<svg")
    assert before != after
    assert "<script" not in before.lower()
    assert "Trimmed" in after


def test_premium_css_contains_animation_glass_hover_and_accessibility_guards() -> None:
    css = (ROOT / "src/biointel/ui/premium_visuals.css").read_text(encoding="utf-8")
    for token in (
        "pv-background-drift",
        "bio-premium-hero",
        "backdrop-filter",
        "bio-workflow-ribbon",
        "translateY(-4px)",
        "prefers-reduced-motion",
        "forced-colors",
        "bio-shell-premium",
    ):
        assert token in css


def test_global_theme_layer_loads_step124_css_after_runtime_tokens() -> None:
    source = (ROOT / "src/biointel/ui/theme.py").read_text(encoding="utf-8")
    assert "premium_visuals.css" in source
    assert source.index("theme_runtime_css(") < source.index('with_name("premium_visuals.css")')
    assert "premium_hero_inner_html" in source
    assert "svg_icon_html" in source


def test_interactive_workspace_uses_real_draggable_comparison_component() -> None:
    source = (ROOT / "src/biointel/ui/module_experience_2_9.py").read_text(encoding="utf-8")
    assert "render_before_after_comparison(" in source
    assert "Interactive before / after inspector" in source
    assert "Drag the handle" in source


def test_appearance_studio_exposes_all_requested_premium_features() -> None:
    source = (ROOT / "pages/24_Appearance_Studio.py").read_text(encoding="utf-8")
    for token in (
        "Premium visual & artistic theme system",
        "premium_theme_names",
        "svg_icon_html",
        "render_before_after_comparison",
        "55 full-experience themes",
    ):
        assert token in source
