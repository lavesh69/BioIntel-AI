from __future__ import annotations

from html import escape
from typing import Iterable, Mapping

from .theme_manager import DRAGON_PALETTE, generate_dragon_universe_css


def apply_dragon_universe_theme(*, reduced_motion: bool = False) -> None:
    import streamlit as st
    st.markdown(generate_dragon_universe_css(reduced_motion=reduced_motion), unsafe_allow_html=True)


def render_dragon_universe(title: str = "BioIntel Dragon Universe", subtitle: str = "Biology, Engineered into Intelligence.", metrics: Iterable[Mapping[str, object]] | None = None) -> None:
    import streamlit as st
    cards = "".join(
        f'<div class="bio-dragon-card"><div class="bio-dragon-kicker">{escape(str(item.get("label", "Metric")))}</div><strong>{escape(str(item.get("value", "—")))}</strong><div>{escape(str(item.get("detail", "")))}</div></div>'
        for item in (metrics or [])
    )
    st.markdown(
        f'<section class="bio-dragon-shell"><div class="bio-dragon-kicker">Dragon Universe</div><h1 class="bio-dragon-title">{escape(title)}</h1><p>{escape(subtitle)}</p><hr class="bio-dragon-divider"><div class="bio-dragon-grid">{cards}</div></section>',
        unsafe_allow_html=True,
    )


def render_dragon_theme_settings_sidebar() -> dict[str, bool]:
    import streamlit as st
    with st.sidebar.expander("Dragon Universe", icon=":material/auto_awesome:"):
        enabled = st.toggle("Enable cinematic theme", value=True, key="dragon-universe-enabled")
        reduced_motion = st.toggle("Reduce motion", value=False, key="dragon-universe-reduced-motion")
    if enabled:
        apply_dragon_universe_theme(reduced_motion=reduced_motion)
    return {"enabled": enabled, "reduced_motion": reduced_motion}


__all__ = ["DRAGON_PALETTE", "apply_dragon_universe_theme", "render_dragon_universe", "render_dragon_theme_settings_sidebar"]
