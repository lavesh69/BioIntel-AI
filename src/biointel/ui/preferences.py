from __future__ import annotations

from biointel.runtime_paths import runtime_report_path

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from biointel.ui.appearance_engine import TYPOGRAPHY_PAIRINGS
from biointel.ui.theme_intelligence import DENSITY_MODES, PERFORMANCE_MODES, sanitise_custom_tokens
from biointel.ui.navigation import PAGE_BY_KEY
from biointel.ui.style_catalog import DEFAULT_FONT, DEFAULT_THEME, FONTS, THEMES
from biointel.utils.atomic_io import atomic_write_json

PREFERENCE_VERSION = "2.0"
MAX_RECENT_PAGES = 12
SAFE_PREFERENCE_THEME = "Executive"




def active_profile_name() -> str:
    raw = os.getenv("BIOINTEL_UI_PROFILE", "default").strip() or "default"
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", raw)[:64].strip("._")
    return cleaned or "default"


@dataclass
class UiPreferences:
    preference_version: str = PREFERENCE_VERSION
    palette: str = SAFE_PREFERENCE_THEME
    font_family: str = DEFAULT_FONT
    heading_font_family: str = DEFAULT_FONT
    data_font_family: str = DEFAULT_FONT
    typography_preset: str = "Modern Professional"
    compact: bool = False
    density_mode: str = "Professional"
    reduce_motion: bool = False
    motion_mode: str = "Full"
    reduce_effects: bool = False
    performance_mode: str = "Adaptive"
    high_contrast: bool = False
    appearance_mode: str = "Dark"

    font_scale: float = 1.0
    color_vision: str = "Standard"
    language: str = "English"
    role: str = "Researcher"
    usage_analytics: bool = False
    apply_appearance_to_reports: bool = False
    report_style: str = "Print light"
    favourites: list[str] = field(default_factory=list)
    recent_pages: list[str] = field(default_factory=list)
    theme_favourites: list[str] = field(default_factory=list)
    recent_themes: list[str] = field(default_factory=list)
    project_theme_overrides: dict[str, str] = field(default_factory=dict)
    module_theme_overrides: dict[str, str] = field(default_factory=dict)
    custom_theme_tokens: dict[str, str] = field(default_factory=dict)
    onboarding_dismissed: bool = False


def default_preferences_path(project_root: str | Path) -> Path:
    profile = active_profile_name()
    return runtime_report_path(Path(project_root).resolve(), "ui_profiles") / profile / "preferences.json"


def profile_root(project_root: str | Path) -> Path:
    return runtime_report_path(Path(project_root).resolve(), "ui_profiles")


def list_profiles(project_root: str | Path) -> tuple[str, ...]:
    root = profile_root(project_root)
    if not root.is_dir():
        return (active_profile_name(),)
    names = [
        path.name
        for path in root.iterdir()
        if path.is_dir() and (path / "preferences.json").is_file()
    ]
    names.append(active_profile_name())
    return tuple(sorted(dict.fromkeys(names)))


def load_profile_preferences(project_root: str | Path, profile_name: str) -> UiPreferences:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", profile_name).strip("._")[:64]
    if not cleaned:
        raise ValueError("Profile name is required")
    path = profile_root(project_root) / cleaned / "preferences.json"
    if not path.is_file():
        raise ValueError(f"Profile does not exist: {cleaned}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Profile is unreadable: {cleaned}") from exc
    return _normalise(payload if isinstance(payload, dict) else {})


def save_profile_copy(
    project_root: str | Path,
    profile_name: str,
    preferences: UiPreferences,
) -> Path:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", profile_name).strip("._")[:64]
    if not cleaned:
        raise ValueError("Profile name is required")
    path = profile_root(project_root) / cleaned / "preferences.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return atomic_write_json(path, asdict(_normalise(asdict(preferences))))


def delete_profile(project_root: str | Path, profile_name: str) -> None:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", profile_name).strip("._")[:64]
    if not cleaned:
        raise ValueError("Profile name is required")
    if cleaned == active_profile_name():
        raise ValueError("The active profile cannot be deleted")
    directory = profile_root(project_root) / cleaned
    if not directory.is_dir():
        return
    for child in directory.iterdir():
        if child.is_file():
            child.unlink()
    directory.rmdir()


def _normalise(payload: dict[str, Any]) -> UiPreferences:
    favourites = [key for key in payload.get("favourites", []) if key in PAGE_BY_KEY][:20]
    recent_pages = [key for key in payload.get("recent_pages", []) if key in PAGE_BY_KEY][
        :MAX_RECENT_PAGES
    ]
    palette = str(payload.get("palette", SAFE_PREFERENCE_THEME))
    if palette not in THEMES:
        palette = SAFE_PREFERENCE_THEME
    font_family = str(payload.get("font_family", DEFAULT_FONT))
    if font_family not in FONTS:
        font_family = DEFAULT_FONT
    heading_font_family = str(payload.get("heading_font_family", font_family))
    if heading_font_family not in FONTS:
        heading_font_family = font_family
    data_font_family = str(payload.get("data_font_family", font_family))
    if data_font_family not in FONTS:
        data_font_family = font_family
    typography_preset = str(payload.get("typography_preset", "Modern Professional"))
    if typography_preset not in TYPOGRAPHY_PAIRINGS:
        typography_preset = "Custom"
    density_mode = str(payload.get("density_mode", "Dense" if payload.get("compact") else "Professional"))
    # Preserve the legacy compact flag when older callers serialise both the
    # flag and the newer default density field. Explicit non-default density
    # choices still take precedence.
    if bool(payload.get("compact", False)) and density_mode == "Professional":
        density_mode = "Dense"
    if density_mode not in DENSITY_MODES:
        density_mode = "Professional"
    performance_mode = str(payload.get("performance_mode", "Adaptive"))
    if performance_mode not in PERFORMANCE_MODES:
        performance_mode = "Adaptive"
    theme_favourites = [name for name in payload.get("theme_favourites", []) if name in THEMES][:20]
    recent_themes = [name for name in payload.get("recent_themes", []) if name in THEMES][:12]
    project_theme_overrides = {
        str(key)[:96]: str(value)
        for key, value in dict(payload.get("project_theme_overrides", {})).items()
        if str(value) in THEMES
    }
    module_theme_overrides = {
        str(key): str(value)
        for key, value in dict(payload.get("module_theme_overrides", {})).items()
        if str(key) in PAGE_BY_KEY and str(value) in THEMES
    }
    custom_theme_tokens = sanitise_custom_tokens(
        payload.get("custom_theme_tokens", {}) if isinstance(payload.get("custom_theme_tokens", {}), dict) else {}
    )

    return UiPreferences(
        preference_version=PREFERENCE_VERSION,
        palette=palette,
        font_family=font_family,
        heading_font_family=heading_font_family,
        data_font_family=data_font_family,
        typography_preset=typography_preset,
        compact=density_mode == "Dense",
        density_mode=density_mode,
        reduce_motion=bool(payload.get("reduce_motion", False))
        or str(payload.get("motion_mode", "Balanced")).title() == "Reduced",
        motion_mode=(
            "Reduced"
            if bool(payload.get("reduce_motion", False))
            else str(payload.get("motion_mode", "Balanced")).title()
            if str(payload.get("motion_mode", "Balanced")).title()
            in {"Full", "Balanced", "Reduced"}
            else "Balanced"
        ),
        reduce_effects=bool(payload.get("reduce_effects", True)),
        performance_mode=performance_mode,
        high_contrast=bool(payload.get("high_contrast", False)),
        appearance_mode=str(payload.get("appearance_mode", "Dark"))
        if str(payload.get("appearance_mode", "Dark")) in {"Dark", "Light", "System"}
        else "Dark",
        font_scale=max(0.85, min(1.25, float(payload.get("font_scale", 1.0)))),
        color_vision=str(payload.get("color_vision", "Standard"))
        if str(payload.get("color_vision", "Standard"))
        in {"Standard", "Deuteranopia", "Tritanopia", "Monochrome"}
        else "Standard",
        language=str(payload.get("language", "English"))
        if str(payload.get("language", "English")) in {"English", "Hinglish"}
        else "English",
        role=str(payload.get("role", "Researcher"))
        if str(payload.get("role", "Researcher"))
        in {
            "Researcher",
            "Bioinformatician",
            "Drug-discovery scientist",
            "Lab analyst",
            "ML engineer",
            "Quality reviewer",
            "Administrator",
        }
        else "Researcher",
        usage_analytics=bool(payload.get("usage_analytics", False)),
        apply_appearance_to_reports=bool(payload.get("apply_appearance_to_reports", False)),
        report_style=str(payload.get("report_style", "Print light"))
        if str(payload.get("report_style", "Print light"))
        in {"Screen theme", "Print light", "Journal monochrome", "Executive presentation"}
        else "Print light",
        favourites=list(dict.fromkeys(favourites)),
        recent_pages=list(dict.fromkeys(recent_pages)),
        theme_favourites=list(dict.fromkeys(theme_favourites)),
        recent_themes=list(dict.fromkeys(recent_themes)),
        project_theme_overrides=project_theme_overrides,
        module_theme_overrides=module_theme_overrides,
        custom_theme_tokens=custom_theme_tokens,
        onboarding_dismissed=bool(payload.get("onboarding_dismissed", False)),
    )


def preferences_from_payload(payload: dict[str, Any]) -> UiPreferences:
    """Validate imported preferences and migrate schema-wrapped v2 files."""

    if not isinstance(payload, dict):
        raise ValueError("Preference payload must be a JSON object")
    if isinstance(payload.get("preferences"), dict):
        payload = dict(payload["preferences"])
    return _normalise(payload)


def preferences_from_json(text: str) -> UiPreferences:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid preference JSON: {exc.msg}") from exc
    return preferences_from_payload(payload)


def preset_store_path(project_root: str | Path) -> Path:
    profile = active_profile_name()
    return (
        runtime_report_path(Path(project_root).resolve(), "ui_profiles")
        / profile
        / "appearance_presets.json"
    )


def load_named_presets(project_root: str | Path) -> dict[str, dict[str, Any]]:
    path = preset_store_path(project_root)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    presets: dict[str, dict[str, Any]] = {}
    for name, value in payload.items():
        if isinstance(name, str) and isinstance(value, dict):
            presets[name[:80]] = asdict(_normalise(value))
    return presets


def save_named_preset(
    project_root: str | Path,
    name: str,
    preferences: UiPreferences,
) -> Path:
    cleaned = re.sub(r"\s+", " ", name).strip()[:80]
    if not cleaned:
        raise ValueError("Preset name is required")
    path = preset_store_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    presets = load_named_presets(project_root)
    presets[cleaned] = asdict(_normalise(asdict(preferences)))
    return atomic_write_json(path, presets)


def delete_named_preset(project_root: str | Path, name: str) -> Path:
    path = preset_store_path(project_root)
    presets = load_named_presets(project_root)
    presets.pop(name, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    return atomic_write_json(path, presets)


def load_preferences(
    project_root: str | Path,
) -> UiPreferences:
    path = default_preferences_path(project_root)
    if not path.is_file():
        return UiPreferences()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return UiPreferences()
    return _normalise(payload if isinstance(payload, dict) else {})


def save_preferences(
    project_root: str | Path,
    preferences: UiPreferences,
) -> Path:
    path = default_preferences_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalised = _normalise(asdict(preferences))
    return atomic_write_json(path, asdict(normalised))


def toggle_favourite(
    preferences: UiPreferences,
    page_key: str,
) -> UiPreferences:
    if page_key not in PAGE_BY_KEY:
        raise ValueError(f"Unknown page key: {page_key}")
    favourites = list(preferences.favourites)
    if page_key in favourites:
        favourites.remove(page_key)
    else:
        favourites.insert(0, page_key)
    preferences.favourites = favourites[:20]
    return preferences


def record_recent_page(
    preferences: UiPreferences,
    page_key: str,
) -> UiPreferences:
    if page_key not in PAGE_BY_KEY:
        return preferences
    recent = [key for key in preferences.recent_pages if key != page_key]
    preferences.recent_pages = [
        page_key,
        *recent,
    ][:MAX_RECENT_PAGES]
    return preferences
