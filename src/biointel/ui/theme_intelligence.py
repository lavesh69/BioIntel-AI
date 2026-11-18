from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from biointel.ui.appearance_engine import THEME_META, light_theme_for, theme_meta_for
from biointel.ui.style_catalog import THEMES, ThemeSpec

THEME_SCHEMA_VERSION = "2.0"
DENSITY_MODES = ("Comfortable", "Professional", "Dense")
PERFORMANCE_MODES = ("Adaptive", "Full quality", "Balanced", "Performance")
MODULE_PREVIEW_MODES = (
    "Dashboard",
    "Genomics",
    "Molecular",
    "Microscopy",
    "Wet-lab",
    "Single-cell",
    "Workflow",
    "Report",
)

_ALLOWED_CUSTOM_TOKENS = {
    "primary",
    "secondary",
    "accent",
    "background",
    "surface",
    "text",
    "muted",
    "border",
    "radius",
    "sidebar_width",
    "shadow_strength",
    "blur_strength",
}
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_LENGTH = re.compile(r"^\d+(?:\.\d+)?(?:px|rem)$")


@dataclass(frozen=True)
class ThemeHealth:
    theme: str
    accessibility: int
    performance: int
    readability: int
    scientific_clarity: int
    print_compatibility: int
    overall: int
    body_contrast: float
    muted_contrast: float
    issues: tuple[str, ...]


@dataclass(frozen=True)
class ThemeRecommendation:
    theme: str
    score: int
    reasons: tuple[str, ...]


def _hex_rgb(value: str) -> tuple[float, float, float]:
    if not _HEX.match(value):
        return (0.0, 0.0, 0.0)
    return tuple(int(value[index : index + 2], 16) / 255 for index in (1, 3, 5))  # type: ignore[return-value]


def _linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _luminance(value: str) -> float:
    red, green, blue = _hex_rgb(value)
    return 0.2126 * _linear(red) + 0.7152 * _linear(green) + 0.0722 * _linear(blue)


def contrast_ratio(foreground: str, background: str) -> float:
    lighter = max(_luminance(foreground), _luminance(background))
    darker = min(_luminance(foreground), _luminance(background))
    return (lighter + 0.05) / (darker + 0.05)


def _appearance_colors(theme: ThemeSpec, appearance: str) -> tuple[str, str, str]:
    if appearance == "Light":
        light = light_theme_for(theme.name)
        return light.text, light.muted, light.background
    return theme.text, theme.muted, theme.bg_start


def theme_health(theme_name: str, appearance: str = "Dark", *, reduce_effects: bool = True) -> ThemeHealth:
    theme = THEMES.get(theme_name, THEMES["Executive"])
    text, muted, background = _appearance_colors(theme, appearance)
    body_contrast = contrast_ratio(text, background)
    muted_contrast = contrast_ratio(muted, background)
    meta = theme_meta_for(theme.name)
    issues: list[str] = []

    accessibility = 100
    if body_contrast < 7:
        accessibility -= 8
    if body_contrast < 4.5:
        accessibility -= 28
        issues.append("Body text contrast is below WCAG AA.")
    if muted_contrast < 4.5:
        accessibility -= 16
        issues.append("Muted text needs stronger contrast.")
    if muted_contrast < 3:
        accessibility -= 18
    if meta.category in {"Creative", "Glass"}:
        accessibility -= 4

    performance_map = {"Fast": 96, "Balanced": 84, "Effects-heavy": 66}
    performance = performance_map.get(meta.performance, 80)
    if reduce_effects:
        performance = min(100, performance + 8)

    readability = round(max(58, min(100, 72 + body_contrast * 4 + muted_contrast * 2)))
    clarity = 92 if meta.category in {"Professional", "Clinical", "Scientific", "High contrast"} else 84
    if meta.category in {"Creative", "Glass"}:
        clarity -= 5
    print_compatibility = 94 if meta.category in {"Professional", "Clinical", "Editorial", "High contrast"} else 80
    if appearance == "Light":
        print_compatibility = min(100, print_compatibility + 4)

    overall = round(
        accessibility * 0.30
        + performance * 0.20
        + readability * 0.20
        + clarity * 0.20
        + print_compatibility * 0.10
    )
    return ThemeHealth(
        theme=theme.name,
        accessibility=max(0, min(100, accessibility)),
        performance=max(0, min(100, performance)),
        readability=max(0, min(100, readability)),
        scientific_clarity=max(0, min(100, clarity)),
        print_compatibility=max(0, min(100, print_compatibility)),
        overall=max(0, min(100, overall)),
        body_contrast=round(body_contrast, 2),
        muted_contrast=round(muted_contrast, 2),
        issues=tuple(issues),
    )


def recommend_themes(
    *,
    role: str,
    module_context: str,
    performance_preference: str,
    accessibility_priority: bool,
    appearance: str,
) -> list[ThemeRecommendation]:
    role_terms = {
        "Researcher": {"Scientific", "Professional", "Editorial"},
        "Bioinformatician": {"Scientific", "Technology", "High contrast"},
        "Drug-discovery scientist": {"Scientific", "Technology", "Professional"},
        "Lab analyst": {"Clinical", "Scientific", "Professional"},
        "ML engineer": {"Technology", "Professional", "High contrast"},
        "Quality reviewer": {"Clinical", "Professional", "High contrast", "Editorial"},
        "Administrator": {"Professional", "High contrast", "Minimal"},
    }
    context_words = {word.lower() for word in re.split(r"[^A-Za-z0-9]+", module_context) if word}
    recommendations: list[ThemeRecommendation] = []
    for name in THEMES:
        meta = THEME_META[name]
        health = theme_health(name, appearance, reduce_effects=performance_preference != "Full quality")
        score = health.overall
        reasons: list[str] = []
        if meta.category in role_terms.get(role, set()):
            score += 7
            reasons.append(f"Fits {role.lower()} workflows")
        best_for_words = {word.lower() for phrase in meta.best_for for word in re.split(r"[^A-Za-z0-9]+", phrase) if word}
        overlap = context_words & best_for_words
        if overlap:
            score += min(12, len(overlap) * 4)
            reasons.append("Matches module context")
        if performance_preference == "Performance" and meta.performance == "Fast":
            score += 10
            reasons.append("Fast rendering profile")
        elif performance_preference == "Full quality" and meta.performance == "Effects-heavy":
            score += 7
            reasons.append("Premium visual effects")
        if accessibility_priority and health.accessibility >= 92:
            score += 10
            reasons.append("Strong contrast score")
        recommendations.append(ThemeRecommendation(name, min(100, score), tuple(reasons or ("Balanced default",))))
    recommendations.sort(key=lambda item: (-item.score, item.theme))
    return recommendations[:6]


def sanitise_custom_tokens(payload: Mapping[str, Any] | None) -> dict[str, str]:
    if not payload:
        return {}
    cleaned: dict[str, str] = {}
    for key, raw in payload.items():
        if key not in _ALLOWED_CUSTOM_TOKENS:
            continue
        value = str(raw).strip()
        if key in {"primary", "secondary", "accent", "background", "surface", "text", "muted", "border"}:
            if _HEX.match(value):
                cleaned[key] = value.upper()
        elif key in {"radius", "sidebar_width"} and _LENGTH.match(value):
            cleaned[key] = value
        elif key in {"shadow_strength", "blur_strength"}:
            try:
                numeric = max(0.0, min(1.0, float(value)))
            except ValueError:
                continue
            cleaned[key] = f"{numeric:.2f}"
    return cleaned


def theme_runtime_css(
    *,
    density_mode: str,
    performance_mode: str,
    custom_tokens: Mapping[str, Any] | None = None,
) -> str:
    density = density_mode if density_mode in DENSITY_MODES else "Professional"
    performance = performance_mode if performance_mode in PERFORMANCE_MODES else "Adaptive"
    density_values = {
        "Comfortable": ("1.15rem", "1.25rem", "2.35rem", "44px"),
        "Professional": (".95rem", "1.05rem", "1.85rem", "40px"),
        "Dense": (".72rem", ".82rem", "1.25rem", "34px"),
    }
    control_gap, card_padding, page_padding, control_height = density_values[density]
    effective_performance = "Balanced" if performance == "Adaptive" else performance
    if effective_performance == "Full quality":
        blur, shadow, transition = "18px", "0 22px 60px rgba(2,6,23,.38)", "180ms"
    elif effective_performance == "Performance":
        blur, shadow, transition = "0px", "0 1px 4px rgba(2,6,23,.16)", "0ms"
    else:
        blur, shadow, transition = "7px", "0 10px 26px rgba(2,6,23,.24)", "110ms"

    custom = sanitise_custom_tokens(custom_tokens)
    override_lines: list[str] = []
    variable_map = {
        "primary": "--bio-primary",
        "secondary": "--bio-secondary",
        "accent": "--bio-accent",
        "background": "--bio-bg",
        "surface": "--bio-surface",
        "text": "--bio-text",
        "muted": "--bio-muted",
        "border": "--bio-border-solid",
        "radius": "--bio-radius-lg",
        "sidebar_width": "--bio-sidebar-width",
    }
    for key, css_variable in variable_map.items():
        if key in custom:
            override_lines.append(f"{css_variable}:{custom[key]};")
            if key == "border":
                override_lines.append(f"--bio-border:{custom[key]};")
    if "shadow_strength" in custom:
        strength = float(custom["shadow_strength"])
        override_lines.append(f"--bio-runtime-shadow:0 18px 55px rgba(2,6,23,{0.08 + strength * 0.42:.2f});")
    if "blur_strength" in custom:
        override_lines.append(f"--bio-runtime-blur:{round(float(custom['blur_strength']) * 20)}px;")

    return f"""
<style id="bio-theme-intelligence-v2">
:root{{
  --bio-density-gap:{control_gap};--bio-density-card-padding:{card_padding};--bio-density-page-padding:{page_padding};--bio-control-height:{control_height};
  --bio-runtime-blur:{blur};--bio-runtime-shadow:{shadow};--bio-runtime-transition:{transition};
  --bio-status-success:#22C55E;--bio-status-warning:#F59E0B;--bio-status-error:#EF4444;--bio-status-review:#3B82F6;--bio-status-unknown:#64748B;--bio-status-blocked:#7C3AED;
  --bio-focus-ring:0 0 0 3px color-mix(in srgb,var(--bio-primary) 42%,transparent);--bio-border-solid:#64748B;
  {''.join(override_lines)}
}}
[data-testid="stAppViewContainer"] .main .block-container{{padding-left:var(--bio-density-page-padding)!important;padding-right:var(--bio-density-page-padding)!important}}
.bio-card,.bio-kpi,.bio-db-card,[data-testid="stExpander"]{{padding:var(--bio-density-card-padding)}}
.stButton>button,.stDownloadButton>button,[data-testid="stSelectbox"]>div>div,[data-testid="stTextInput"] input{{min-height:var(--bio-control-height)}}
[data-testid="stSidebar"]{{width:var(--bio-sidebar-width,auto)}}
.bio-card,[data-testid="stExpander"],button,input,textarea,select{{transition-duration:var(--bio-runtime-transition)!important}}
.bio-card,[data-testid="stExpander"]{{box-shadow:var(--bio-runtime-shadow)}}
.bio-status-success{{color:var(--bio-status-success)}}.bio-status-warning{{color:var(--bio-status-warning)}}.bio-status-error{{color:var(--bio-status-error)}}.bio-status-review{{color:var(--bio-status-review)}}.bio-status-unknown{{color:var(--bio-status-unknown)}}.bio-status-blocked{{color:var(--bio-status-blocked)}}
:where(button,a,input,textarea,select,[tabindex]):focus-visible{{outline:none!important;box-shadow:var(--bio-focus-ring)!important}}
@media(max-width:1280px){{[data-testid="stAppViewContainer"] .main .block-container{{padding-left:1.05rem!important;padding-right:1.05rem!important}}.bio-shell-bar .bio-shell-title{{max-width:26ch;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}}}
@media(max-width:1024px){{.bio-shell-bar{{display:none!important}}[data-testid="column"]{{min-width:0!important}}.bio-live-preview{{grid-template-columns:1fr!important}}.bio-live-preview aside{{display:none!important}}}}
@media(max-width:768px){{[data-testid="stAppViewContainer"] .main .block-container{{padding-left:.72rem!important;padding-right:.72rem!important}}.bio-result-label{{font-size:.68rem!important}}}}
@media(min-resolution:1.5dppx){{body{{text-rendering:optimizeLegibility}}.bio-card,.bio-kpi{{border-width:1px!important}}}}
@media(forced-colors:active){{*{{forced-color-adjust:auto}}.bio-card,.bio-kpi,[data-testid="stExpander"]{{border:1px solid CanvasText!important;background:Canvas!important;color:CanvasText!important}}button{{border:1px solid ButtonText!important}}}}
@media(prefers-reduced-motion:reduce){{*,*::before,*::after{{animation-duration:.001ms!important;animation-iteration-count:1!important;scroll-behavior:auto!important;transition-duration:.001ms!important}}}}
</style>
"""


def preference_export_payload(preferences: Any) -> dict[str, Any]:
    data = asdict(preferences) if hasattr(preferences, "__dataclass_fields__") else dict(preferences)
    return {
        "theme_schema_version": THEME_SCHEMA_VERSION,
        "app_version": data.pop("app_version", None),
        "preferences": data,
    }


def preference_export_json(preferences: Any) -> str:
    return json.dumps(preference_export_payload(preferences), indent=2, sort_keys=True)
