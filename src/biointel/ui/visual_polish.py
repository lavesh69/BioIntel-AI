from __future__ import annotations

"""Responsive visual building blocks for dense BioIntel command surfaces.

The shared theme styles core Streamlit widgets. These components add intentional
information hierarchy where legacy pages previously used long, flat tables or
five-to-eight narrow metric columns.
"""

import html
from collections.abc import Iterable, Sequence
from typing import Any

import streamlit as st


_STYLE_ID = "biointel-visual-polish-v13"
_TONES = {"info", "success", "warning", "danger", "neutral"}


def _install_style() -> None:
    """Install scoped, responsive CSS without overriding the global theme."""
    renderer = getattr(st, "html", None)
    css = f"""
    <style id="{_STYLE_ID}">
      .bio13-metric-board {{
        display:grid;
        grid-template-columns:repeat(auto-fit,minmax(185px,1fr));
        gap:.78rem;
        margin:.25rem 0 1.3rem;
      }}
      .bio13-metric-card {{
        position:relative;
        min-height:122px;
        overflow:hidden;
        padding:1rem 1.05rem .95rem;
        border:1px solid var(--bio58-border,var(--bio-border));
        border-radius:18px;
        background:
          radial-gradient(circle at 92% 4%,color-mix(in srgb,var(--bio-secondary) 15%,transparent),transparent 42%),
          linear-gradient(135deg,color-mix(in srgb,var(--bio-primary) 8%,transparent),var(--bio58-surface,var(--bio-surface)));
        box-shadow:0 16px 42px rgba(2,6,23,.16);
        isolation:isolate;
      }}
      .bio13-metric-card::before {{
        content:"";
        position:absolute;
        inset:0 auto 0 0;
        width:3px;
        background:var(--bio13-tone,var(--bio-primary));
        box-shadow:0 0 20px var(--bio13-tone,var(--bio-primary));
      }}
      .bio13-metric-card::after {{
        content:"";
        position:absolute;
        width:105px;
        height:105px;
        right:-42px;
        bottom:-58px;
        border-radius:50%;
        z-index:-1;
        background:color-mix(in srgb,var(--bio13-tone,var(--bio-primary)) 15%,transparent);
      }}
      .bio13-metric-card[data-tone="success"] {{ --bio13-tone:var(--bio-success); }}
      .bio13-metric-card[data-tone="warning"] {{ --bio13-tone:var(--bio-warning); }}
      .bio13-metric-card[data-tone="danger"] {{ --bio13-tone:var(--bio-danger); }}
      .bio13-metric-card[data-tone="info"] {{ --bio13-tone:var(--bio-secondary); }}
      .bio13-metric-label {{
        color:var(--bio58-copy,var(--bio-muted));
        font-size:.72rem;
        font-weight:780;
        letter-spacing:.065em;
        line-height:1.2;
        text-transform:uppercase;
      }}
      .bio13-metric-value {{
        margin:.42rem 0 .28rem;
        color:var(--bio58-text,var(--bio-text));
        font-family:var(--bio-heading-font,var(--bio-body-font));
        font-size:clamp(1.3rem,2.4vw,2rem);
        font-weight:830;
        letter-spacing:-.035em;
        line-height:1.04;
        overflow-wrap:anywhere;
      }}
      .bio13-metric-detail {{
        color:var(--bio58-copy,var(--bio-muted));
        font-size:.77rem;
        line-height:1.38;
      }}
      .bio13-action-grid {{
        display:grid;
        grid-template-columns:repeat(auto-fit,minmax(205px,1fr));
        gap:.78rem;
        margin:.15rem 0 1.05rem;
      }}
      .bio13-action-card {{
        min-height:126px;
        padding:.92rem .96rem;
        border:1px solid var(--bio58-border,var(--bio-border));
        border-radius:16px;
        background:var(--bio58-surface,var(--bio-surface));
        box-shadow:0 12px 30px rgba(2,6,23,.13);
      }}
      .bio13-action-icon {{
        display:grid;
        place-items:center;
        width:34px;
        height:34px;
        margin-bottom:.58rem;
        border:1px solid color-mix(in srgb,var(--bio-primary) 32%,transparent);
        border-radius:11px;
        background:var(--bio58-gradient-soft);
        font-size:1rem;
      }}
      .bio13-action-title {{ color:var(--bio58-text,var(--bio-text)); font-weight:790; line-height:1.28; }}
      .bio13-action-copy {{
        margin-top:.32rem;
        color:var(--bio58-copy,var(--bio-muted));
        font-size:.76rem;
        line-height:1.43;
      }}
      @media (max-width:720px) {{
        .bio13-metric-board,.bio13-action-grid {{ grid-template-columns:1fr; }}
        .bio13-metric-card {{ min-height:104px; }}
      }}
    </style>
    """
    if callable(renderer):
        renderer(css)
    else:  # pragma: no cover - fallback for supported Streamlit releases.
        st.markdown(css, unsafe_allow_html=True)


def render_metric_board(items: Iterable[tuple[str, Any, str, str]]) -> None:
    """Render an adaptive metric grid that remains readable on narrow windows."""
    _install_style()
    cards: list[str] = []
    for label, value, detail, tone in items:
        safe_tone = str(tone).lower() if str(tone).lower() in _TONES else "neutral"
        cards.append(
            f'<article class="bio13-metric-card" data-tone="{safe_tone}">'
            f'<div class="bio13-metric-label">{html.escape(str(label))}</div>'
            f'<div class="bio13-metric-value">{html.escape(str(value))}</div>'
            f'<div class="bio13-metric-detail">{html.escape(str(detail))}</div>'
            "</article>"
        )
    if cards:
        st.markdown(
            f'<section class="bio13-metric-board">{"".join(cards)}</section>',
            unsafe_allow_html=True,
        )


def render_action_grid(items: Sequence[tuple[str, str, str, str]], *, key: str) -> None:
    """Render concise launch cards followed by resilient internal page links."""
    _install_style()
    if not items:
        return
    cards = "".join(
        '<article class="bio13-action-card">'
        f'<div class="bio13-action-icon">{html.escape(icon)}</div>'
        f'<div class="bio13-action-title">{html.escape(title)}</div>'
        f'<div class="bio13-action-copy">{html.escape(copy)}</div>'
        "</article>"
        for _, title, icon, copy in items
    )
    st.markdown(f'<section class="bio13-action-grid">{cards}</section>', unsafe_allow_html=True)
    for row_start in range(0, len(items), 4):
        row = items[row_start : row_start + 4]
        columns = st.columns(len(row), gap="small")
        for column, (page_path, title, _, _) in zip(columns, row):
            with column:
                try:
                    st.page_link(page_path, label=f"Open {title}", width="stretch")
                except (KeyError, RuntimeError):
                    st.button(
                        f"Open {title}",
                        key=f"{key}_{row_start}_{title}",
                        disabled=True,
                        width="stretch",
                    )


__all__ = ["render_action_grid", "render_metric_board"]
