from __future__ import annotations

import html
import json
import math
import sys
from dataclasses import asdict, replace
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
PREFERENCES_RELATIVE_PATH = "reports/ui_profiles/<profile>/preferences.json"
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.ui.appearance_engine import (
    THEME_META,
    TYPOGRAPHY_PAIRINGS,
    font_detection_html,
    mini_theme_preview_html,
    pairing_for,
    theme_meta_for,
    theme_variable_override_css,
)
from biointel.ui.brand import BRAND, brand_mark_svg
from biointel.ui.experience_themes import experience_for, experience_theme_css
from biointel.ui.motion import MOTION_MODES
from biointel.ui.navigation import PAGE_CATALOG
from biointel.ui.theme_intelligence import (
    DENSITY_MODES,
    MODULE_PREVIEW_MODES,
    PERFORMANCE_MODES,
    preference_export_json,
    recommend_themes,
    sanitise_custom_tokens,
    theme_health,
    theme_runtime_css,
)
from biointel.ui.premium_visuals import (
    comparison_state_svg,
    premium_theme_names,
    render_before_after_comparison,
    svg_icon_html,
)
from biointel.ui.preferences import (
    UiPreferences,
    active_profile_name,
    delete_named_preset,
    delete_profile,
    list_profiles,
    load_named_presets,
    load_profile_preferences,
    preferences_from_json,
    save_named_preset,
    save_profile_copy,
)
from biointel.ui.theme import (
    FONTS,
    PALETTES,
    apply_theme,
    feature_card,
    hero,
    init_ui_preferences,
    persist_ui_preferences,
    reset_ui_preferences,
    section_title,
    session_preferences,
)
from biointel.ui.workflow import render_upload_preflight

_UI_FIELD_MAP = {
    "ui_palette": "palette",
    "ui_font_family": "font_family",
    "ui_heading_font_family": "heading_font_family",
    "ui_data_font_family": "data_font_family",
    "ui_typography_preset": "typography_preset",
    "ui_appearance_mode": "appearance_mode",
    "ui_color_vision": "color_vision",
    "ui_font_scale": "font_scale",
    "ui_compact": "compact",
    "ui_density_mode": "density_mode",
    "ui_reduce_motion": "reduce_motion",
    "ui_motion_mode": "motion_mode",
    "ui_reduce_effects": "reduce_effects",
    "ui_performance_mode": "performance_mode",
    "ui_high_contrast": "high_contrast",
    "ui_language": "language",
    "ui_apply_appearance_to_reports": "apply_appearance_to_reports",
    "ui_report_style": "report_style",
    "ui_theme_favourites": "theme_favourites",
    "ui_recent_themes": "recent_themes",
    "ui_project_theme_overrides": "project_theme_overrides",
    "ui_module_theme_overrides": "module_theme_overrides",
    "ui_custom_theme_tokens": "custom_theme_tokens",
}

_PREVIEW_FIELD_MAP = {
    "preview_palette": "palette",
    "preview_body_font": "font_family",
    "preview_heading_font": "heading_font_family",
    "preview_data_font": "data_font_family",
    "preview_typography_preset": "typography_preset",
    "preview_appearance": "appearance_mode",
    "preview_color_vision": "color_vision",
    "preview_font_scale": "font_scale",
    "preview_compact": "compact",
    "preview_density_mode": "density_mode",
    "preview_motion_mode": "motion_mode",
    "preview_reduce_effects": "reduce_effects",
    "preview_performance_mode": "performance_mode",
    "preview_high_contrast": "high_contrast",
    "preview_language": "language",
    "preview_apply_reports": "apply_appearance_to_reports",
    "preview_report_style": "report_style",
}

_PENDING_TRANSACTION_KEY = "_appearance_pending_transaction"


def _write_preference_fields(preferences: UiPreferences, mapping: dict[str, str]) -> None:
    """Write widget/session values before any matching widget is instantiated."""

    for target, source in mapping.items():
        st.session_state[target] = getattr(preferences, source)


def _consume_pending_transaction() -> str:
    """Apply a queued appearance transaction at the start of a clean rerun.

    Streamlit does not allow changing a widget-backed session key after that widget
    has been created in the current run. All Apply/Cancel/Preset/Profile actions
    therefore enqueue a transaction and rerun; this function consumes it before
    the first Appearance Studio widget is rendered.
    """

    pending = st.session_state.pop(_PENDING_TRANSACTION_KEY, None)
    if not isinstance(pending, dict):
        return ""
    mode = str(pending.get("mode", "apply"))
    if mode == "reset":
        reset_ui_preferences()
        preferences = UiPreferences()
    else:
        preferences = UiPreferences(**dict(pending.get("preferences", {})))
        if mode == "apply":
            _write_preference_fields(preferences, _UI_FIELD_MAP)
            persist_ui_preferences()
    _write_preference_fields(preferences, _PREVIEW_FIELD_MAP)
    return str(pending.get("notice", ""))


def _queue_transaction(
    preferences: UiPreferences,
    *,
    mode: str = "apply",
    notice: str = "",
) -> None:
    st.session_state[_PENDING_TRANSACTION_KEY] = {
        "mode": mode,
        "preferences": asdict(preferences),
        "notice": notice,
    }
    st.rerun()


st.set_page_config(
    page_title="Appearance & Accessibility · BioIntel AI", page_icon="🎨", layout="wide"
)
init_ui_preferences()
_pending_notice = _consume_pending_transaction()
apply_theme()

hero(
    "A professional workspace that adapts to you.",
    "Preview complete interface themes, font pairings, contrast, density and effects before saving. Preferences remain local to the active workspace profile.",
    eyebrow="BioIntel AI · Appearance Studio",
    chips=[
        "55 full-experience themes — including 6 new bold colour experiences",
        "11 preserved font options — including 10 new fonts",
        "30+ distinct layout systems",
        "Live preview + undo",
        "Dedicated dark/light palettes",
        "Accessible contrast",
    ],
)
if _pending_notice:
    st.toast(_pending_notice, icon="✅")

section_title("Locked brand identity", "✦")
st.markdown(
    f"""
    <div class="bio-brand-preview-v91">
      <div class="bio-brand-preview-mark">{brand_mark_svg(size=88)}</div>
      <div><div class="bio-brand-preview-name">{html.escape(BRAND.name)}</div>
      <div class="bio-brand-preview-descriptor">{html.escape(BRAND.descriptor)}</div>
      <div class="bio-brand-preview-tagline">{html.escape(BRAND.tagline)}</div>
      <div class="bio-brand-preview-founder">Created and developed by {html.escape(BRAND.founder)}</div></div>
      <div class="bio-brand-preview-policy"><b>Brand-safe theming</b><span>Themes may change workspace surfaces and charts, but the BioIntel mark, wordmark, typography and evidence status language remain consistent.</span></div>
    </div>
    <style>
    .bio-brand-preview-v91{{display:grid;grid-template-columns:96px minmax(230px,1fr) minmax(240px,.8fr);gap:1rem;align-items:center;padding:1rem;border:1px solid color-mix(in srgb,var(--bio-primary) 34%,var(--bio-border));border-radius:18px;background:linear-gradient(135deg,color-mix(in srgb,var(--bio-primary) 10%,var(--bio-surface)),var(--bio-surface))}}
    .bio-brand-preview-mark{{width:88px;height:88px}}.bio-brand-preview-name{{font:900 1.45rem/1 Inter,Segoe UI,Arial,sans-serif;color:var(--bio-text);letter-spacing:-.03em}}.bio-brand-preview-descriptor{{margin-top:.35rem;font:.75rem Inter,Segoe UI,Arial,sans-serif;color:var(--bio-muted);letter-spacing:.09em;text-transform:uppercase}}.bio-brand-preview-tagline{{margin-top:.55rem;color:var(--bio-secondary);font-weight:800}}.bio-brand-preview-founder{{margin-top:.32rem;color:var(--bio-muted);font-size:.7rem}}.bio-brand-preview-policy{{display:grid;gap:.3rem;padding:.75rem;border-left:2px solid var(--bio-primary);color:var(--bio-muted);font-size:.72rem;line-height:1.5}}.bio-brand-preview-policy b{{color:var(--bio-text)}}
    @media(max-width:800px){{.bio-brand-preview-v91{{grid-template-columns:80px 1fr}}.bio-brand-preview-policy{{grid-column:1/-1;border-left:0;border-top:2px solid var(--bio-primary)}}}}
    </style>
    """,
    unsafe_allow_html=True,
)
brand_downloads = st.columns(4)
brand_downloads[0].download_button(
    "Download logo SVG",
    (ROOT / "assets/brand/biointel-mark.svg").read_text(encoding="utf-8"),
    "biointel-mark.svg",
    "image/svg+xml",
    width="stretch",
)
brand_downloads[1].download_button(
    "Download wordmark SVG",
    (ROOT / "assets/brand/biointel-wordmark.svg").read_text(encoding="utf-8"),
    "biointel-wordmark.svg",
    "image/svg+xml",
    width="stretch",
)
brand_downloads[2].download_button(
    "Brand guidelines PDF",
    (ROOT / "brand/BIOINTEL_BRAND_GUIDELINES.pdf").read_bytes(),
    "BioIntel-AI-Brand-Guidelines.pdf",
    "application/pdf",
    width="stretch",
)
brand_downloads[3].download_button(
    "Download brand manifest",
    (ROOT / "assets/brand/brand-manifest.json").read_text(encoding="utf-8"),
    "biointel-brand-manifest.json",
    "application/json",
    width="stretch",
)


def _option_label(name: str, *, is_new: bool) -> str:
    return f"{name} · NEW" if is_new else name


def _apply_preferences_to_session(preferences: UiPreferences) -> None:
    """Compatibility helper used only before widgets exist.

    Interactive actions use ``_queue_transaction`` instead, avoiding Streamlit's
    widget-state mutation exception.
    """

    _write_preference_fields(preferences, _UI_FIELD_MAP)


def _sync_preview_from(preferences: UiPreferences) -> None:
    _write_preference_fields(preferences, _PREVIEW_FIELD_MAP)


def _pairing_changed() -> None:
    name = str(st.session_state.get("preview_typography_preset", "Modern Professional"))
    if name == "Custom":
        return
    pairing = pairing_for(name)
    st.session_state["preview_heading_font"] = pairing.heading_font
    st.session_state["preview_body_font"] = pairing.body_font
    st.session_state["preview_data_font"] = pairing.data_font


saved_preferences = session_preferences()
if "preview_palette" not in st.session_state:
    _sync_preview_from(saved_preferences)

section_title("Live visual system", "◈")
selector_row = st.columns([1.15, 1.05, 0.8, 0.8])
preview_palette = selector_row[0].selectbox(
    "Complete UI theme",
    list(PALETTES),
    key="preview_palette",
    format_func=lambda name: _option_label(name, is_new=PALETTES[name].is_new),
    help="Changes the complete desktop experience: layout archetype, geometry, surfaces, sidebar, controls, charts and colours.",
)
preview_typography_preset = selector_row[1].selectbox(
    "Typography pairing",
    list(TYPOGRAPHY_PAIRINGS),
    key="preview_typography_preset",
    on_change=_pairing_changed,
)
preview_appearance = selector_row[2].selectbox(
    "Appearance",
    ["Dark", "Light", "System"],
    key="preview_appearance",
)
full_page_preview = selector_row[3].toggle(
    "Preview entire studio",
    value=True,
    help="Temporarily applies the selected theme to this page without saving it.",
)

font_row = st.columns(3)
preview_heading_font = font_row[0].selectbox(
    "Heading font",
    list(FONTS),
    key="preview_heading_font",
    disabled=preview_typography_preset != "Custom",
)
preview_body_font = font_row[1].selectbox(
    "Body and controls font",
    list(FONTS),
    key="preview_body_font",
    disabled=preview_typography_preset != "Custom",
)
preview_data_font = font_row[2].selectbox(
    "Data and code font",
    list(FONTS),
    key="preview_data_font",
    disabled=preview_typography_preset != "Custom",
)

access_row = st.columns([1.05, 1.0, 0.9, 0.9, 1.05, 0.85])
preview_color_vision = access_row[0].selectbox(
    "Visual accessibility",
    ["Standard", "Deuteranopia", "Tritanopia", "Monochrome"],
    key="preview_color_vision",
)
preview_font_scale = access_row[1].slider(
    "Text scale",
    min_value=0.85,
    max_value=1.25,
    step=0.05,
    key="preview_font_scale",
)
preview_density_mode = access_row[2].selectbox(
    "Density",
    list(DENSITY_MODES),
    key="preview_density_mode",
)
preview_compact = preview_density_mode == "Dense"
preview_motion_mode = access_row[3].selectbox(
    "Motion",
    list(MOTION_MODES),
    key="preview_motion_mode",
    help="Full includes theme ambience; Balanced keeps useful feedback; Reduced disables non-essential movement.",
)
# Accessibility contract: Reduce motion
preview_reduce_motion = preview_motion_mode == "Reduced"
preview_performance_mode = access_row[4].selectbox(
    "Performance",
    list(PERFORMANCE_MODES),
    key="preview_performance_mode",
    help="Adaptive chooses a balanced profile. Reduce effects with Performance mode to remove costly blur and decorative layers.",
)
preview_reduce_effects = preview_performance_mode == "Performance"
preview_high_contrast = access_row[5].toggle("Higher contrast", key="preview_high_contrast")

preview_theme_spec = PALETTES[preview_palette]
preview_experience = experience_for(preview_palette)
preview_heading_spec = FONTS[preview_heading_font]
preview_body_spec = FONTS[preview_body_font]
preview_data_spec = FONTS[preview_data_font]
preview_meta = theme_meta_for(preview_palette)

if full_page_preview:
    st.markdown(
        experience_theme_css(
            preview_theme_spec,
            appearance_mode=preview_appearance,
            compact=preview_compact,
            reduce_motion=preview_reduce_motion,
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        theme_variable_override_css(
            preview_theme_spec,
            heading_font=preview_heading_spec,
            body_font=preview_body_spec,
            data_font=preview_data_spec,
            appearance_mode=preview_appearance,
            reduce_effects=preview_reduce_effects,
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        theme_runtime_css(
            density_mode=preview_density_mode,
            performance_mode=preview_performance_mode,
            custom_tokens=st.session_state.get("preview_custom_theme_tokens", {}),
        ),
        unsafe_allow_html=True,
    )

st.caption(
    f"Experience: {preview_experience.title} · {preview_experience.archetype} · "
    f"{preview_experience.summary} · Designed for: {', '.join(preview_meta.best_for)} · "
    f"Theme cost: {preview_meta.performance} · Runtime: {preview_performance_mode} · Density: {preview_density_mode} · Motion: {preview_motion_mode}"
)

button_row = st.columns([1.3, 1, 1, 1])
apply_changes = button_row[0].button(
    "Apply theme and typography",
    type="primary",
    width="stretch",
)
cancel_preview = button_row[1].button("Cancel preview", width="stretch")
undo_available = isinstance(st.session_state.get("appearance_undo"), dict)
undo_changes = button_row[2].button("Undo last apply", disabled=not undo_available, width="stretch")
button_row[3].caption("Preview is temporary until Apply is pressed.")

if apply_changes:
    st.session_state["appearance_undo"] = asdict(saved_preferences)
    selected_preferences = replace(
        saved_preferences,
        palette=preview_palette,
        font_family=preview_body_font,
        heading_font_family=preview_heading_font,
        data_font_family=preview_data_font,
        typography_preset=preview_typography_preset,
        appearance_mode=preview_appearance,
        color_vision=preview_color_vision,
        font_scale=float(preview_font_scale),
        compact=bool(preview_compact),
        density_mode=str(preview_density_mode),
        reduce_motion=bool(preview_reduce_motion),
        motion_mode=str(preview_motion_mode),
        reduce_effects=bool(preview_reduce_effects),
        performance_mode=str(preview_performance_mode),
        high_contrast=bool(preview_high_contrast),
        language=str(st.session_state.get("preview_language", "English")),
        apply_appearance_to_reports=bool(st.session_state.get("preview_apply_reports", False)),
        report_style=str(st.session_state.get("preview_report_style", "Print light")),
        theme_favourites=list(st.session_state.get("preview_theme_favourites", [])),
        recent_themes=list(dict.fromkeys([preview_palette, *saved_preferences.recent_themes]))[:12],
        project_theme_overrides=dict(st.session_state.get("preview_project_theme_overrides", {})),
        module_theme_overrides=dict(st.session_state.get("preview_module_theme_overrides", {})),
        custom_theme_tokens=sanitise_custom_tokens(st.session_state.get("preview_custom_theme_tokens", {})),
    )
    _queue_transaction(
        selected_preferences,
        notice="Theme and typography saved locally",
    )

if cancel_preview:
    _queue_transaction(saved_preferences, mode="preview", notice="Preview cancelled")

if undo_changes:
    previous = UiPreferences(**st.session_state.pop("appearance_undo"))
    _queue_transaction(previous, notice="Previous appearance restored")

section_title("Premium visual & artistic theme system", "◇")
premium_names = premium_theme_names()
st.caption("Twenty-two premium full-interface themes are available globally: ten Step 124 scientific identities, six Step 126 aesthetic and art directions, and six Step 148 bold colour experiences. SVG icons, animated heroes, glass workspaces, workflow ribbons and interactive before/after surfaces remain shared across the app.")

icon_samples = [
    ("Genomics", "chromosome"),
    ("Protein", "protein"),
    ("Chemistry", "molecule"),
    ("Imaging", "microscope"),
    ("AI models", "brain"),
    ("Laboratory", "flask"),
    ("Data", "database"),
    ("Evidence", "shield"),
]
icon_cards = "".join(
    f'<div class="bio-card bio-glass-card"><div class="bio-card-icon">{svg_icon_html(icon_name, title=label, size=24)}</div><div class="bio-card-title">{html.escape(label)}</div><div class="bio-card-copy">Shared vector icon · theme aware</div></div>'
    for label, icon_name in icon_samples
)
st.markdown(f'<div class="bio-board">{icon_cards}</div>', unsafe_allow_html=True)

st.markdown("**Premium theme collection**")
st.markdown(" ".join(f'<span class="bio-chip">{html.escape(name)}</span>' for name in premium_names), unsafe_allow_html=True)
st.markdown("**Step 148 creative colour collection**")
st.caption("Solar Helix · Black Diamond · Crimson Genome · Electric Lime · Velvet Neon · Copper Eclipse — each changes palette, geometry, materials, navigation, cards, buttons and chart identity.")

render_before_after_comparison(
    before_svg=comparison_state_svg(title="Workspace surface", label="Legacy flat presentation", after=False, motif="Appearance Studio"),
    after_svg=comparison_state_svg(title="Workspace surface", label="Step 126 premium artistic visual language", after=True, motif="Appearance Studio"),
    key="appearance_step126_before_after",
    before_label="Before",
    after_label="Premium",
    height=420,
    caption="This local preview demonstrates the draggable comparison component used by interactive scientific workspaces.",
)

section_title("Complete interface preview", "✦")
st.markdown(
    f"""
    <div class="bio-live-preview">
      <aside>
        <strong>BioIntel AI</strong><span>Workspace</span>
        <a class="active">Overview</a><a>Datasets</a><a>Discovery</a><a>Quality</a>
      </aside>
      <main>
        <header><small>{html.escape(preview_experience.title)} · {html.escape(preview_palette)}</small>
          <h2>Scientific intelligence, presented clearly.</h2>
          <p>Variant confidence 98.4% · calibrated probability 0.91 · evidence status reviewed.</p>
          <button>Run analysis</button>
        </header>
        <div class="bio-live-kpis"><article><b>98.4%</b><span>Confidence</span></article><article><b>24</b><span>Datasets</span></article><article><b>PASS</b><span>Release gate</span></article></div>
        <section><div class="bio-live-chart"><i></i><i></i><i></i><i></i><i></i></div><div class="bio-live-table"><b>Scientific results</b><span>BRCA1 · Reviewed · 0.91</span><span>EGFR · Qualified · 0.87</span><span>TP53 · Review · 0.74</span></div></section>
        <code>ΔΔCt · IC₅₀ · R² · p &lt; 0.001 · A→G · 10⁻⁶</code>
      </main>
    </div>
    <style>
      .bio-live-preview{{display:grid;grid-template-columns:180px 1fr;min-height:440px;border:1px solid var(--bio-border);border-radius:var(--bio-exp-card-radius,18px);overflow:hidden;background:var(--bio-bg);box-shadow:var(--bio-exp-shadow,var(--bio-shadow));font-family:var(--bio-body-font)}}
      .bio-live-preview aside{{padding:1.15rem;background:var(--bio-surface-strong);border-right:1px solid var(--bio-border);display:flex;flex-direction:column;gap:.48rem}}
      .bio-live-preview aside strong{{font-family:var(--bio-heading-font);color:var(--bio-text);font-size:1rem}} .bio-live-preview aside span{{color:var(--bio-muted);font-size:.72rem;margin-bottom:.8rem}}
      .bio-live-preview aside a{{padding:.55rem .65rem;border-radius:var(--bio-exp-control-radius,9px);color:var(--bio-muted);font-size:.76rem}} .bio-live-preview aside a.active{{background:color-mix(in srgb,var(--bio-primary) 22%,transparent);color:var(--bio-text);border-left:3px solid var(--bio-primary)}}
      .bio-live-preview main{{padding:1.25rem;background-image:linear-gradient(135deg,color-mix(in srgb,var(--bio-primary) 5%,transparent),transparent)}}
      .bio-live-preview header{{padding:1.3rem;border:1px solid var(--bio-border);border-radius:var(--bio-exp-hero-radius,18px);background:var(--bio-surface-strong);box-shadow:var(--bio-exp-shadow,var(--bio-shadow))}}
      .bio-live-preview header small{{color:var(--bio-secondary);font-weight:800;text-transform:uppercase;letter-spacing:.08em}} .bio-live-preview h2{{font-family:var(--bio-heading-font);color:var(--bio-text);margin:.45rem 0;font-size:1.55rem}} .bio-live-preview p{{color:var(--bio-muted);font-size:.82rem}}
      .bio-live-preview button{{margin-top:.65rem;padding:.58rem .9rem;border:0;border-radius:var(--bio-exp-control-radius,9px);background:linear-gradient(110deg,var(--bio-primary),var(--bio-secondary));color:var(--bio-button-foreground,#fff);font-weight:800}}
      .bio-live-kpis{{display:grid;grid-template-columns:repeat(3,1fr);gap:.65rem;margin:.75rem 0}} .bio-live-kpis article{{padding:.8rem;border:1px solid var(--bio-border);border-radius:var(--bio-exp-card-radius,14px);background:var(--bio-surface)}} .bio-live-kpis b{{font-family:var(--bio-data-font);display:block;color:var(--bio-text)}} .bio-live-kpis span{{color:var(--bio-muted);font-size:.7rem}}
      .bio-live-preview section{{display:grid;grid-template-columns:1.2fr 1fr;gap:.65rem}} .bio-live-chart,.bio-live-table{{min-height:120px;padding:.8rem;border:1px solid var(--bio-border);border-radius:var(--bio-exp-card-radius,14px);background:var(--bio-surface)}}
      .bio-live-chart{{display:flex;gap:.35rem;align-items:end}} .bio-live-chart i{{width:16%;border-radius:6px 6px 0 0;background:linear-gradient(var(--bio-secondary),var(--bio-primary))}} .bio-live-chart i:nth-child(1){{height:35%}} .bio-live-chart i:nth-child(2){{height:58%}} .bio-live-chart i:nth-child(3){{height:82%}} .bio-live-chart i:nth-child(4){{height:65%}} .bio-live-chart i:nth-child(5){{height:92%}}
      .bio-live-table{{display:flex;flex-direction:column;gap:.45rem}} .bio-live-table b{{font-family:var(--bio-heading-font);color:var(--bio-text)}} .bio-live-table span{{padding:.35rem;border-bottom:1px solid var(--bio-border);color:var(--bio-muted);font-size:.72rem}}
      .bio-live-preview code{{display:block;margin-top:.65rem;padding:.55rem;border:1px solid var(--bio-border);border-radius:var(--bio-exp-control-radius,9px);color:var(--bio-text);background:var(--bio-surface-strong);font-family:var(--bio-data-font)}}
    </style>
    """,
    unsafe_allow_html=True,
)

preview_cards = st.columns(3)
with preview_cards[0]:
    feature_card(
        "Theme-aware navigation",
        "Sidebar, hero, cards and controls share the selected layout language.",
        "⌘",
    )
with preview_cards[1]:
    feature_card(
        "Scientific typography", "Heading, body and data fonts are independently controlled.", "Aa"
    )
with preview_cards[2]:
    feature_card("Accessible effects", "Motion and transparency can be reduced independently.", "◉")

section_title("Browser font availability", "Aa")
st.iframe(font_detection_html(FONTS), height=360)
st.caption(
    "The detector runs in the active desktop browser/WebView. No font files are downloaded or bundled."
)

section_title("Theme Intelligence Studio", "🎨")

if "preview_theme_favourites" not in st.session_state:
    st.session_state["preview_theme_favourites"] = list(saved_preferences.theme_favourites)
if "preview_custom_theme_tokens" not in st.session_state:
    st.session_state["preview_custom_theme_tokens"] = dict(saved_preferences.custom_theme_tokens)
if "preview_project_theme_overrides" not in st.session_state:
    st.session_state["preview_project_theme_overrides"] = dict(saved_preferences.project_theme_overrides)
if "preview_module_theme_overrides" not in st.session_state:
    st.session_state["preview_module_theme_overrides"] = dict(saved_preferences.module_theme_overrides)


def _module_preview_html(mode: str) -> str:
    safe_mode = html.escape(mode)
    body = {
        "Dashboard": "<div class='tv2-kpis'><i></i><i></i><i></i></div><div class='tv2-surface'><b>Project readiness</b><span>Evidence reviewed</span><span>Workflow running</span></div>",
        "Genomics": "<div class='tv2-ruler'>chr7 · 55,086,724–55,275,031</div><div class='tv2-track'><i style='left:6%;width:22%'></i><i style='left:36%;width:13%'></i><i style='left:58%;width:29%'></i></div><div class='tv2-variants'><b>A→G</b><b>DEL</b><b>SNV</b></div>",
        "Molecular": "<div class='tv2-molecule'><i></i><i></i><i></i><i></i><i></i><span></span><span></span><span></span></div><div class='tv2-surface'><b>Residue inspector</b><span>Chain A · TYR42</span></div>",
        "Microscopy": "<div class='tv2-image'>" + "".join(f"<i style='left:{8+(n%6)*15}%;top:{12+(n//6)*33}%;width:{18+n%4}px;height:{18+n%4}px'></i>" for n in range(18)) + "</div><div class='tv2-toolbar'>Mask · Split · Merge · Review</div>",
        "Wet-lab": "<div class='tv2-plate'>" + "".join(f"<i class='w{n%4}'></i>" for n in range(48)) + "</div><div class='tv2-toolbar'>96-well assay layout</div>",
        "Single-cell": "<div class='tv2-cells'>" + "".join(f"<i class='c{n%4}' style='left:{5+(n*17)%88}%;top:{8+(n*29)%75}%'></i>" for n in range(34)) + "</div><div class='tv2-toolbar'>Lasso selection · Cell passport</div>",
        "Workflow": "<div class='tv2-flow'><i>Input</i><b>→</b><i>QC</i><b>→</b><i>Analyse</i><b>→</b><i>Review</i></div><div class='tv2-surface'><span>Typed ports · Checkpointed state</span></div>",
        "Report": "<div class='tv2-report'><h4>Scientific report</h4><p>Methods and evidence</p><i></i><i></i><i></i><small>Page 1 of 8</small></div>",
    }.get(mode, "")
    return f"<div class='tv2-module-preview'><div class='tv2-label'>{safe_mode} preview</div>{body}</div>"


gallery_controls = st.columns([1.35, 0.85, 0.85, 0.75])
gallery_query = gallery_controls[0].text_input(
    "Search themes",
    placeholder="Search by name, category or best use…",
    key="step117_theme_search",
)
theme_categories = sorted({meta.category for meta in THEME_META.values()})
gallery_category = gallery_controls[1].selectbox(
    "Category", ["All", *theme_categories], key="step117_theme_category"
)
gallery_performance = gallery_controls[2].selectbox(
    "Theme cost", ["All", "Fast", "Balanced", "Effects-heavy"], key="step117_theme_cost"
)
favourites_only = gallery_controls[3].toggle(
    "Favourites only", value=False, key="step117_theme_favourites_only"
)

st.multiselect(
    "Favourite themes",
    list(PALETTES),
    key="preview_theme_favourites",
    help="Favourites appear first in the shell and remain local to the active profile.",
)

query_norm = gallery_query.strip().lower()
filtered_themes = []
for name in PALETTES:
    meta = THEME_META[name]
    searchable = " ".join((name, meta.category, meta.performance, *meta.best_for)).lower()
    if query_norm and query_norm not in searchable:
        continue
    if gallery_category != "All" and meta.category != gallery_category:
        continue
    if gallery_performance != "All" and meta.performance != gallery_performance:
        continue
    if favourites_only and name not in st.session_state.get("preview_theme_favourites", []):
        continue
    filtered_themes.append(name)
filtered_themes.sort(
    key=lambda name: (
        name not in st.session_state.get("preview_theme_favourites", []),
        -theme_health(name, preview_appearance if preview_appearance != "System" else "Dark").overall,
        name,
    )
)

gallery_page_size = 9
gallery_pages = max(1, math.ceil(len(filtered_themes) / gallery_page_size))
current_gallery_page = min(max(int(st.session_state.get("step117_theme_gallery_page", 1) or 1), 1), gallery_pages)
if st.session_state.get("step117_theme_gallery_page") != current_gallery_page:
    st.session_state["step117_theme_gallery_page"] = current_gallery_page
gallery_page = st.number_input(
    "Theme gallery page",
    min_value=1,
    max_value=gallery_pages,
    step=1,
    key="step117_theme_gallery_page",
)
gallery_start = (int(gallery_page) - 1) * gallery_page_size
visible_themes = filtered_themes[gallery_start : gallery_start + gallery_page_size]
st.caption(
    f"{len(filtered_themes)} matching themes · showing {gallery_start + 1 if visible_themes else 0}–{gallery_start + len(visible_themes)}"
)

gallery_columns = st.columns(3, gap="small")
for index, name in enumerate(visible_themes):
    theme = PALETTES[name]
    experience = experience_for(name)
    health = theme_health(
        name,
        preview_appearance if preview_appearance != "System" else "Dark",
        reduce_effects=preview_performance_mode != "Full quality",
    )
    with gallery_columns[index % 3]:
        st.markdown(
            f"""
            <div class='bio-theme-card-v117'>
              {mini_theme_preview_html(theme, appearance=preview_appearance if preview_appearance != "System" else "Dark")}
              <div class='bio-theme-title-v117'>{html.escape(name)} · {html.escape(experience.title)}</div>
              <div class='bio-theme-score-v117'>Health {health.overall}/100 · Accessibility {health.accessibility} · Performance {health.performance}</div>
              <div class='bio-theme-copy-v117'>{html.escape(experience.summary)}</div>
              <div class='bio-theme-copy-v117'>Designed for: {html.escape(" · ".join(THEME_META[name].best_for))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Preview this theme", key=f"step117_preview_theme_{name}", width="stretch"):
            preview_preferences = replace(
                session_preferences(),
                palette=name,
                theme_favourites=list(st.session_state.get("preview_theme_favourites", [])),
                recent_themes=list(dict.fromkeys([name, *saved_preferences.recent_themes]))[:12],
            )
            _queue_transaction(preview_preferences, mode="preview", notice=f"Previewing {name}")

st.markdown(
    """
    <style>
    .bio-theme-card-v117{min-height:315px;padding:.75rem;border:1px solid var(--bio-border);border-radius:var(--bio-exp-card-radius,14px);background:var(--bio-surface);margin-bottom:.45rem}
    .bio-theme-title-v117{font-family:var(--bio-heading-font);color:var(--bio-text);font-weight:850;font-size:.82rem;margin-top:.6rem}.bio-theme-score-v117{color:var(--bio-secondary);font-size:.67rem;font-weight:780;margin-top:.25rem}.bio-theme-copy-v117{color:var(--bio-muted);font-size:.7rem;line-height:1.45;margin-top:.35rem}
    .bio-mini-theme{height:150px;display:grid;grid-template-columns:46px 1fr;border-radius:12px;overflow:hidden;background:var(--m-bg);border:1px solid var(--m-border);color:var(--m-text)}.bio-mini-sidebar{padding:8px 6px;background:var(--m-surface);display:flex;flex-direction:column;gap:7px}.bio-mini-sidebar span{height:8px;border-radius:4px;background:var(--m-border)}.bio-mini-sidebar .active{background:var(--m-primary)}.bio-mini-main{padding:8px}.bio-mini-hero{padding:7px;border:1px solid var(--m-border);border-radius:7px;background:var(--m-surface)}.bio-mini-hero b{display:block;font-size:9px}.bio-mini-hero small{display:block;color:var(--m-muted);font-size:6px}.bio-mini-kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:4px;margin:5px 0}.bio-mini-kpis i{height:17px;border-radius:5px;background:var(--m-surface);border:1px solid var(--m-border)}.bio-mini-row{display:grid;grid-template-columns:1.2fr 1fr;gap:4px}.bio-mini-chart{height:36px;background:linear-gradient(145deg,var(--m-primary),var(--m-secondary));opacity:.72;border-radius:5px}.bio-mini-table{height:36px;padding:4px;background:var(--m-surface);border-radius:5px}.bio-mini-table em{display:block;height:3px;margin:3px;background:var(--m-border)}.bio-mini-main button{font-size:6px;border:0;border-radius:4px;padding:4px 7px;background:linear-gradient(90deg,var(--m-primary),var(--m-secondary));margin-top:5px}.bio-mini-main p{font-size:5px;color:var(--m-muted);margin:4px 0 0}
    </style>
    """,
    unsafe_allow_html=True,
)

section_title("Theme compare and health score", "⚖")
compare_cols = st.columns([1, 1])
compare_a = compare_cols[0].selectbox("Theme A", list(PALETTES), index=list(PALETTES).index(preview_palette), key="step117_compare_a")
compare_b = compare_cols[1].selectbox("Theme B", list(PALETTES), index=(list(PALETTES).index(preview_palette) + 1) % len(PALETTES), key="step117_compare_b")
health_a = theme_health(compare_a, preview_appearance if preview_appearance != "System" else "Dark", reduce_effects=preview_performance_mode != "Full quality")
health_b = theme_health(compare_b, preview_appearance if preview_appearance != "System" else "Dark", reduce_effects=preview_performance_mode != "Full quality")
comparison = st.columns(2)
for column, name, health in ((comparison[0], compare_a, health_a), (comparison[1], compare_b, health_b)):
    with column:
        st.markdown(mini_theme_preview_html(PALETTES[name], appearance=preview_appearance if preview_appearance != "System" else "Dark"), unsafe_allow_html=True)
        st.metric(name, f"{health.overall}/100")
        st.dataframe(
            [
                {"Metric": "Accessibility", "Score": health.accessibility},
                {"Metric": "Performance", "Score": health.performance},
                {"Metric": "Readability", "Score": health.readability},
                {"Metric": "Scientific clarity", "Score": health.scientific_clarity},
                {"Metric": "Print compatibility", "Score": health.print_compatibility},
            ],
            hide_index=True,
            width="stretch",
        )
        st.caption(f"Body contrast {health.body_contrast}:1 · Muted contrast {health.muted_contrast}:1")
        for issue in health.issues:
            st.warning(issue)

section_title("Smart theme assistant", "✦")
assistant_cols = st.columns([1, 1.3, 1, .8])
assistant_role = assistant_cols[0].selectbox(
    "Role",
    ["Researcher", "Bioinformatician", "Drug-discovery scientist", "Lab analyst", "ML engineer", "Quality reviewer", "Administrator"],
    index=0,
    key="step117_assistant_role",
)
assistant_module = assistant_cols[1].selectbox(
    "Module context",
    [page.title for page in PAGE_CATALOG],
    key="step117_assistant_module",
)
assistant_performance = assistant_cols[2].selectbox(
    "Priority", ["Adaptive", "Full quality", "Performance"], key="step117_assistant_performance"
)
assistant_accessibility = assistant_cols[3].toggle(
    "Accessibility", value=True, key="step117_assistant_accessibility"
)
recommendations = recommend_themes(
    role=assistant_role,
    module_context=assistant_module,
    performance_preference=assistant_performance,
    accessibility_priority=assistant_accessibility,
    appearance=preview_appearance if preview_appearance != "System" else "Dark",
)
recommendation_columns = st.columns(3)
for index, recommendation in enumerate(recommendations):
    with recommendation_columns[index % 3]:
        st.markdown(
            f"**{recommendation.theme} — {recommendation.score}/100**\n\n" + " · ".join(recommendation.reasons)
        )

section_title("Module Preview Lab", "▣")
preview_lab_cols = st.columns([.8, 1.8])
module_preview_mode = preview_lab_cols[0].radio(
    "Preview workspace",
    list(MODULE_PREVIEW_MODES),
    key="step117_module_preview_mode",
)
with preview_lab_cols[1]:
    st.markdown(_module_preview_html(module_preview_mode), unsafe_allow_html=True)

section_title("Safe custom theme builder", "🛠")
current_custom = dict(st.session_state.get("preview_custom_theme_tokens", {}))
custom_color_cols = st.columns(4)
custom_primary = custom_color_cols[0].color_picker("Primary", current_custom.get("primary", preview_theme_spec.primary), key="step117_custom_primary")
custom_secondary = custom_color_cols[1].color_picker("Secondary", current_custom.get("secondary", preview_theme_spec.secondary), key="step117_custom_secondary")
custom_accent = custom_color_cols[2].color_picker("Accent", current_custom.get("accent", preview_theme_spec.accent), key="step117_custom_accent")
custom_background = custom_color_cols[3].color_picker("Background", current_custom.get("background", preview_theme_spec.bg_start), key="step117_custom_background")
custom_surface_cols = st.columns(4)
custom_surface = custom_surface_cols[0].color_picker("Surface", current_custom.get("surface", "#111827"), key="step117_custom_surface")
custom_text = custom_surface_cols[1].color_picker("Text", current_custom.get("text", preview_theme_spec.text), key="step117_custom_text")
custom_muted = custom_surface_cols[2].color_picker("Muted text", current_custom.get("muted", preview_theme_spec.muted), key="step117_custom_muted")
custom_border = custom_surface_cols[3].color_picker("Border", current_custom.get("border", "#64748B"), key="step117_custom_border")
custom_metric_cols = st.columns(4)
custom_radius = custom_metric_cols[0].slider("Radius", 4, 28, int(str(current_custom.get("radius", "18px")).replace("px", "") or 18), key="step117_custom_radius")
custom_sidebar = custom_metric_cols[1].slider("Sidebar width", 240, 360, int(str(current_custom.get("sidebar_width", "286px")).replace("px", "") or 286), key="step117_custom_sidebar")
custom_shadow = custom_metric_cols[2].slider("Shadow", 0.0, 1.0, float(current_custom.get("shadow_strength", ".45")), .05, key="step117_custom_shadow")
custom_blur = custom_metric_cols[3].slider("Blur", 0.0, 1.0, float(current_custom.get("blur_strength", ".35")), .05, key="step117_custom_blur")
custom_tokens = sanitise_custom_tokens(
    {
        "primary": custom_primary,
        "secondary": custom_secondary,
        "accent": custom_accent,
        "background": custom_background,
        "surface": custom_surface,
        "text": custom_text,
        "muted": custom_muted,
        "border": custom_border,
        "radius": f"{custom_radius}px",
        "sidebar_width": f"{custom_sidebar}px",
        "shadow_strength": custom_shadow,
        "blur_strength": custom_blur,
    }
)
custom_buttons = st.columns(2)
if custom_buttons[0].button("Use custom tokens in preview", type="primary", width="stretch"):
    st.session_state["preview_custom_theme_tokens"] = custom_tokens
    st.rerun()
if custom_buttons[1].button("Clear custom overrides", width="stretch"):
    st.session_state["preview_custom_theme_tokens"] = {}
    st.rerun()
st.caption("Only allow-listed colours, lengths and bounded effect values are saved. Invalid CSS and unknown tokens are rejected.")

section_title("Project and module theme overrides", "↳")
override_cols = st.columns(2)
with override_cols[0]:
    project_name = st.text_input("Project name", placeholder="default-project", key="step117_override_project_name")
    project_theme = st.selectbox("Project theme", list(PALETTES), key="step117_override_project_theme")
    if st.button("Save project override", width="stretch", disabled=not project_name.strip()):
        updated = dict(st.session_state.get("preview_project_theme_overrides", {}))
        updated[project_name.strip()[:96]] = project_theme
        st.session_state["preview_project_theme_overrides"] = updated
        st.success("Project override staged. Press Apply theme and typography to persist it.")
with override_cols[1]:
    module_title_by_key = {page.title: page.key for page in PAGE_CATALOG}
    module_title = st.selectbox("Module", list(module_title_by_key), key="step117_override_module")
    module_theme = st.selectbox("Module theme", list(PALETTES), key="step117_override_module_theme")
    if st.button("Save module override", width="stretch"):
        updated = dict(st.session_state.get("preview_module_theme_overrides", {}))
        updated[module_title_by_key[module_title]] = module_theme
        st.session_state["preview_module_theme_overrides"] = updated
        st.success("Module override staged. Press Apply theme and typography to persist it.")
st.caption(
    f"Staged project overrides: {len(st.session_state.get('preview_project_theme_overrides', {}))} · "
    f"module overrides: {len(st.session_state.get('preview_module_theme_overrides', {}))}"
)

section_title("Live theme diagnostics", "✓")
active_health = theme_health(
    preview_palette,
    preview_appearance if preview_appearance != "System" else "Dark",
    reduce_effects=preview_performance_mode != "Full quality",
)
diagnostic_cols = st.columns(5)
diagnostic_cols[0].metric("Theme health", f"{active_health.overall}/100")
diagnostic_cols[1].metric("Body contrast", f"{active_health.body_contrast}:1")
diagnostic_cols[2].metric("Muted contrast", f"{active_health.muted_contrast}:1")
diagnostic_cols[3].metric("Density", preview_density_mode)
diagnostic_cols[4].metric("Custom tokens", len(st.session_state.get("preview_custom_theme_tokens", {})))
if active_health.issues:
    for issue in active_health.issues:
        st.warning(issue)
else:
    st.success("No critical contrast issue detected for the selected base theme and appearance.")

st.markdown(
    """
    <style>
    .tv2-module-preview{min-height:330px;padding:1rem;border:1px solid var(--bio-border);border-radius:18px;background:linear-gradient(145deg,var(--bio-surface-strong),var(--bio-surface));position:relative;overflow:hidden}.tv2-label{color:var(--bio-secondary);font-weight:850;text-transform:uppercase;letter-spacing:.08em;font-size:.7rem;margin-bottom:1rem}.tv2-kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:.6rem}.tv2-kpis i{height:72px;border:1px solid var(--bio-border);border-radius:14px;background:color-mix(in srgb,var(--bio-primary) 16%,var(--bio-surface))}.tv2-surface{margin-top:.8rem;padding:.8rem;border:1px solid var(--bio-border);border-radius:14px;display:grid;gap:.45rem;color:var(--bio-muted)}.tv2-surface b{color:var(--bio-text)}.tv2-ruler,.tv2-toolbar{padding:.55rem;border:1px solid var(--bio-border);border-radius:9px;color:var(--bio-muted);font-family:var(--bio-data-font);font-size:.72rem}.tv2-track{height:70px;margin:.7rem 0;position:relative;border-radius:12px;background:color-mix(in srgb,var(--bio-primary) 8%,var(--bio-surface))}.tv2-track i{position:absolute;top:22px;height:26px;border-radius:7px;background:linear-gradient(90deg,var(--bio-primary),var(--bio-secondary))}.tv2-variants{display:flex;gap:.5rem}.tv2-variants b{padding:.35rem .55rem;border-radius:8px;background:color-mix(in srgb,var(--bio-accent) 16%,var(--bio-surface));color:var(--bio-text);font-size:.7rem}.tv2-molecule,.tv2-cells,.tv2-image{height:220px;position:relative;border:1px solid var(--bio-border);border-radius:16px;background:radial-gradient(circle at 40% 30%,color-mix(in srgb,var(--bio-primary) 14%,transparent),transparent 45%),var(--bio-bg)}.tv2-molecule i{position:absolute;width:42px;height:42px;border-radius:50%;background:var(--bio-primary);box-shadow:0 0 24px color-mix(in srgb,var(--bio-primary) 50%,transparent)}.tv2-molecule i:nth-child(1){left:18%;top:42%}.tv2-molecule i:nth-child(2){left:34%;top:22%;background:var(--bio-secondary)}.tv2-molecule i:nth-child(3){left:52%;top:38%;background:var(--bio-accent)}.tv2-molecule i:nth-child(4){left:68%;top:18%}.tv2-molecule i:nth-child(5){left:73%;top:58%;background:var(--bio-secondary)}.tv2-image i,.tv2-cells i{position:absolute;border-radius:50%;background:color-mix(in srgb,var(--bio-secondary) 65%,transparent);border:1px solid var(--bio-text)}.tv2-cells i{width:9px;height:9px}.tv2-cells .c1{background:var(--bio-primary)}.tv2-cells .c2{background:var(--bio-secondary)}.tv2-cells .c3{background:var(--bio-accent)}.tv2-plate{display:grid;grid-template-columns:repeat(12,1fr);gap:5px;padding:.7rem;border:1px solid var(--bio-border);border-radius:16px}.tv2-plate i{aspect-ratio:1;border-radius:50%;background:var(--bio-primary);border:1px solid var(--bio-border)}.tv2-plate .w1{background:var(--bio-secondary)}.tv2-plate .w2{background:var(--bio-accent)}.tv2-plate .w3{background:var(--bio-muted)}.tv2-flow{display:flex;gap:.55rem;align-items:center;justify-content:center;min-height:180px;overflow:auto}.tv2-flow i{padding:.8rem 1rem;border:1px solid var(--bio-border);border-radius:12px;background:var(--bio-surface);color:var(--bio-text);font-style:normal}.tv2-flow b{color:var(--bio-secondary)}.tv2-report{width:70%;margin:auto;padding:1rem;min-height:250px;background:#fff;color:#1f2937;border-radius:4px;box-shadow:0 15px 45px rgba(0,0,0,.25)}.tv2-report h4{margin:0}.tv2-report i{display:block;height:7px;background:#cbd5e1;margin:.8rem 0}.tv2-report small{display:block;text-align:right;color:#64748b}
    </style>
    """,
    unsafe_allow_html=True,
)

section_title("Theme regression matrix", "🧪")
regression_matrix = {
    "themes": list(PALETTES),
    "appearances": ["Dark", "Light", "System"],
    "density_modes": list(DENSITY_MODES),
    "performance_modes": list(PERFORMANCE_MODES),
    "screen_widths": [768, 1024, 1280, 1440, 1920, 2560],
    "representative_previews": list(MODULE_PREVIEW_MODES),
    "checks": [
        "text clipping",
        "contrast",
        "focus visibility",
        "overflow",
        "sidebar width",
        "canvas readability",
        "modal placement",
        "performance budget",
    ],
}
regression_total = (
    len(regression_matrix["themes"])
    * len(regression_matrix["appearances"])
    * len(regression_matrix["density_modes"])
    * len(regression_matrix["performance_modes"])
    * len(regression_matrix["screen_widths"])
    * len(regression_matrix["representative_previews"])
)
regression_cols = st.columns(4)
regression_cols[0].metric("Themes", len(regression_matrix["themes"]))
regression_cols[1].metric("Responsive widths", len(regression_matrix["screen_widths"]))
regression_cols[2].metric("Preview families", len(regression_matrix["representative_previews"]))
regression_cols[3].metric("Defined combinations", f"{regression_total:,}")
st.download_button(
    "Download theme regression matrix",
    json.dumps(regression_matrix, indent=2),
    "biointel_theme_regression_matrix_v2.json",
    "application/json",
    width="stretch",
)
st.caption(
    "The release verifier executes catalogue, contrast, token, preference-migration and representative Streamlit runtime checks. The full combination matrix is defined for staged/nightly screenshot automation rather than falsely claimed as executed on every local launch."
)

section_title("Typography catalogue", "Aa")
font_cards = []
for font in FONTS.values():
    font_cards.append(
        f"""
        <div class='bio-font-card-v67' style='font-family:{font.css_stack};'>
          <div class='bio-font-heading-v67'>{html.escape(font.name)} · Scientific intelligence</div>
          <div class='bio-font-body-v67'>Readable paragraph: validated evidence, calibrated confidence and reproducible analysis.</div>
          <div class='bio-font-data-v67'>α β γ Δ μ Å °C ± × 10⁻⁶ · ΔΔCt · IC₅₀ · R² · A→G</div>
          <div class='bio-font-meta-v67'>{html.escape(font.category)} · {html.escape(font.description)}</div>
        </div>
        """
    )
st.markdown(
    "<div class='bio-font-grid-v67'>" + "".join(font_cards) + "</div>"
    "<style>.bio-font-grid-v67{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:.75rem}.bio-font-card-v67{padding:.9rem;border:1px solid var(--bio-border);border-radius:var(--bio-exp-card-radius,14px);background:var(--bio-surface)}.bio-font-heading-v67{font-size:1rem;font-weight:700;color:var(--bio-text)}.bio-font-body-v67{font-size:.76rem;line-height:1.55;color:var(--bio-muted);margin:.35rem 0}.bio-font-data-v67{font-size:.72rem;color:var(--bio-secondary);overflow-wrap:anywhere}.bio-font-meta-v67{font-size:.66rem;color:var(--bio-muted);margin-top:.45rem}</style>",
    unsafe_allow_html=True,
)

section_title("Reports and preference portability", "⚙️")
report_cols = st.columns([1, 1, 1])
preview_apply_reports = report_cols[0].toggle(
    "Apply appearance to reports", key="preview_apply_reports"
)
preview_report_style = report_cols[1].selectbox(
    "Report style",
    ["Screen theme", "Print light", "Journal monochrome", "Executive presentation"],
    key="preview_report_style",
    disabled=not preview_apply_reports,
)
preview_language = report_cols[2].radio(
    "Guidance language",
    ["English", "Hinglish"],
    key="preview_language",
    horizontal=True,
)

current = session_preferences()
portability = st.columns([1, 1, 1])
portability[0].download_button(
    "Export preferences",
    preference_export_json(current),
    "biointel_ui_preferences_v2.json",
    "application/json",
    width="stretch",
)
uploaded = portability[1].file_uploader(
    "Import preferences", type=["json"], label_visibility="collapsed"
)
if uploaded is not None:
    render_upload_preflight(
        uploaded,
        key="appearance_preferences_import",
        allowed_extensions=["json"],
        soft_limit_mb=1,
        hard_limit_mb=5,
        preserve_requested_limit=True,
        block_large_files=False,
        module_key="appearance_preferences",
    )
    try:
        imported = preferences_from_json(uploaded.getvalue().decode("utf-8"))
        st.success(f"Valid preference file: {imported.palette} · {imported.typography_preset}")
        if portability[1].button("Apply imported preferences", width="stretch"):
            st.session_state["appearance_undo"] = asdict(current)
            _queue_transaction(imported, notice="Imported preferences applied")
    except (UnicodeDecodeError, ValueError) as exc:
        st.error(str(exc))

if portability[2].button("Save current session", width="stretch"):
    path = persist_ui_preferences()
    st.success(f"Saved locally: {path.relative_to(ROOT).as_posix()}")

section_title("Named appearance presets", "◇")
presets = load_named_presets(ROOT)
preset_cols = st.columns([1.2, 1, 1, 1])
preset_name = preset_cols[0].text_input("Preset name", placeholder="My Lab Setup")
if preset_cols[1].button("Save named preset", width="stretch"):
    try:
        path = save_named_preset(ROOT, preset_name, session_preferences())
        st.success(f"Preset saved: {path.relative_to(ROOT).as_posix()}")
        st.rerun()
    except ValueError as exc:
        st.error(str(exc))
selected_named = preset_cols[2].selectbox("Saved presets", ["—"] + sorted(presets))
if preset_cols[3].button("Apply preset", disabled=selected_named == "—", width="stretch"):
    imported = UiPreferences(**presets[selected_named])
    st.session_state["appearance_undo"] = asdict(session_preferences())
    _queue_transaction(imported, notice=f"Preset applied: {selected_named}")
if selected_named != "—" and st.button("Delete selected preset"):
    delete_named_preset(ROOT, selected_named)
    st.rerun()

section_title("Local appearance profiles", "👤")
profiles = list_profiles(ROOT)
profile_cols = st.columns([1.1, 1, 1, 1])
new_profile_name = profile_cols[0].text_input("New profile name", placeholder="Lab-Analyst")
if profile_cols[1].button("Save current as profile", width="stretch"):
    try:
        path = save_profile_copy(ROOT, new_profile_name, session_preferences())
        st.success(f"Profile saved: {path.relative_to(ROOT).as_posix()}")
        st.rerun()
    except ValueError as exc:
        st.error(str(exc))
selected_profile = profile_cols[2].selectbox("Available profiles", profiles)
if profile_cols[3].button("Load profile into session", width="stretch"):
    try:
        imported = load_profile_preferences(ROOT, selected_profile)
        st.session_state["appearance_undo"] = asdict(session_preferences())
        _queue_transaction(imported, notice=f"Loaded profile: {selected_profile}")
    except ValueError as exc:
        st.error(str(exc))
st.caption(
    f"Active persistence profile: `{active_profile_name()}`. Loading another profile copies its appearance into the active session without changing environment configuration."
)
if selected_profile != active_profile_name() and st.button("Delete selected profile"):
    try:
        delete_profile(ROOT, selected_profile)
        st.rerun()
    except ValueError as exc:
        st.error(str(exc))

confirm = st.checkbox("Confirm reset to Executive defaults")
if st.button("Reset to Executive defaults", disabled=not confirm):
    st.session_state[_PENDING_TRANSACTION_KEY] = {
        "mode": "reset",
        "preferences": asdict(UiPreferences()),
        "notice": "Appearance reset to Executive defaults",
    }
    st.rerun()

if preview_font_scale < 0.95:
    st.warning(
        "Text scale below 0.95× can make captions difficult to read. Essential controls remain clamped, but 1.0× is recommended."
    )

st.info(
    f"Preferences are stored locally in `{PREFERENCES_RELATIVE_PATH}`. Font rendering depends on locally available system fonts; the browser detector exposes active fallbacks."
)

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='appearance', title='Appearance Studio', category='Settings')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
