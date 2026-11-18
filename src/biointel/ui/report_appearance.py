from __future__ import annotations

from html import escape

from biointel.ui.appearance_engine import light_theme_for, theme_button_foreground
from biointel.ui.preferences import UiPreferences
from biointel.ui.style_catalog import DEFAULT_THEME, FONTS, THEMES


def report_theme_css(preferences: UiPreferences) -> str:
    theme = THEMES.get(preferences.palette, THEMES[DEFAULT_THEME])
    heading = FONTS.get(preferences.heading_font_family, FONTS["Inter"])
    body = FONTS.get(preferences.font_family, FONTS["Inter"])
    data = FONTS.get(preferences.data_font_family, FONTS["Inter"])
    style = preferences.report_style
    if style == "Screen theme":
        background = theme.bg_start
        surface = theme.surface_strong
        text = theme.text
        muted = theme.muted
        border = "rgba(148,163,184,.22)"
    elif style == "Journal monochrome":
        background, surface, text, muted, border = "#FFFFFF", "#FFFFFF", "#111111", "#4B5563", "#111111"
    elif style == "Executive presentation":
        light = light_theme_for(theme.name)
        background, surface, text, muted, border = light.background, light.surface_strong, light.text, light.muted, light.border
    else:
        background, surface, text, muted, border = "#F8FAFC", "#FFFFFF", "#0F172A", "#475569", "#CBD5E1"
    button_text = theme_button_foreground(theme)
    return f"""
    <style id="biointel-report-appearance-v67">
      :root{{--report-primary:{theme.primary};--report-secondary:{theme.secondary};--report-bg:{background};--report-surface:{surface};--report-text:{text};--report-muted:{muted};--report-border:{border};--report-heading:{heading.css_stack};--report-body:{body.css_stack};--report-data:{data.css_stack};}}
      html,body{{background:var(--report-bg)!important;color:var(--report-text)!important;font-family:var(--report-body)!important}}
      h1,h2,h3,h4,h5,h6{{font-family:var(--report-heading)!important;color:var(--report-text)!important}}
      code,pre,kbd,samp,td.numeric{{font-family:var(--report-data)!important}}
      section,.card,.panel,table{{background:var(--report-surface)!important;border-color:var(--report-border)!important}}
      p,small,.muted{{color:var(--report-muted)!important}}
      th{{background:color-mix(in srgb,var(--report-primary) 10%,var(--report-surface))!important;color:var(--report-text)!important}}
      a,.accent{{color:var(--report-primary)!important}}
      button,.button{{background:linear-gradient(100deg,var(--report-primary),var(--report-secondary))!important;color:{button_text}!important}}
      @media print{{html,body{{background:#fff!important;color:#111!important}}section,.card,.panel,table{{box-shadow:none!important;background:#fff!important}}}}
    </style>
    """


def apply_report_appearance(html: str, preferences: UiPreferences) -> str:
    """Inject the selected report style without changing the report evidence content."""

    if not preferences.apply_appearance_to_reports:
        return html
    css = report_theme_css(preferences)
    marker = "</head>"
    if marker in html:
        return html.replace(marker, css + marker, 1)
    return css + html


def report_appearance_summary(preferences: UiPreferences) -> str:
    return escape(
        f"{preferences.report_style} · {preferences.palette} · "
        f"{preferences.heading_font_family}/{preferences.font_family}/{preferences.data_font_family}"
    )
