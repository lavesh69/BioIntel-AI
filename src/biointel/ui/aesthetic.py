from __future__ import annotations

from functools import lru_cache
from textwrap import dedent

try:
    import streamlit as st
except ImportError:
    st = None

from biointel.ui.motion import motion_profile_for, normalize_motion_mode
from biointel.ui.style_catalog import FontSpec, ThemeSpec

AESTHETIC_LAYER_ID = "biointel-premium-aesthetic-v58"


def _motion_css(
    reduce_motion: bool,
    *,
    motion_mode: str = "Balanced",
    intro_motion: bool = True,
    theme_name: str = "Executive",
) -> str:
    mode = normalize_motion_mode(motion_mode, reduce_motion=reduce_motion)
    profile = motion_profile_for(theme_name, mode)
    if mode == "Reduced":
        return dedent(
            """
            html { scroll-behavior: auto !important; }
            *, *::before, *::after {
                animation-name: none !important;
                animation-duration: 0.001ms !important;
                animation-iteration-count: 1 !important;
                scroll-behavior: auto !important;
                transition-duration: 0.001ms !important;
            }
            .bio-card:hover,.bio-kpi:hover,.bio-db-card:hover,
            [data-testid="stMetric"]:hover,[data-testid="stFileUploaderDropzone"]:hover,
            button:hover,button:active,[role="button"]:hover,[role="button"]:active,
            .bio-status-running,.bio-progress-indeterminate::after {
                transform: none !important;
                animation: none !important;
            }
            [data-testid="stProgressBar"] > div > div > div {
                background-position: 0 0 !important;
            }
            """
        )

    ambient_keyframes = ""
    ambient_rule = ""
    if profile.ambient_motion and mode == "Full":
        ambient_keyframes = dedent(
            """
            @keyframes bio58-hero-shift {
                0%, 100% { transform: translate3d(0, 0, 0) scale(1); }
                50% { transform: translate3d(-1.2%, .8%, 0) scale(1.025); }
            }
            """
        )
        ambient_rule = ".bio-hero::before { animation: bio58-hero-shift 16s var(--ease-standard) infinite; }"

    reveal_rule = ""
    if intro_motion:
        reveal_rule = dedent(
            f"""
            .bio-page-context,.bio-hero,.bio-board,.bio-db-grid,
            .bio-status-row,.bio-professional-strip {{
                animation: bio58-reveal var(--motion-slow) var(--ease-enter) both;
            }}
            .bio-board > *:nth-child(2),.bio-db-grid > *:nth-child(2) {{ animation-delay: {profile.stagger_ms}ms; }}
            .bio-board > *:nth-child(3),.bio-db-grid > *:nth-child(3) {{ animation-delay: {profile.stagger_ms * 2}ms; }}
            .bio-board > *:nth-child(4),.bio-db-grid > *:nth-child(4) {{ animation-delay: {profile.stagger_ms * 3}ms; }}
            .bio-board > *:nth-child(n+5),.bio-db-grid > *:nth-child(n+5) {{ animation-delay: {profile.stagger_ms * 4}ms; }}
            """
        )

    return dedent(
        f"""
        html {{ scroll-behavior: smooth; }}
        @keyframes bio58-reveal {{
            from {{ opacity: 0; transform: translateY(7px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        @keyframes bio58-status-pulse {{
            0%, 100% {{ opacity: .68; transform: scale(1); }}
            50% {{ opacity: 1; transform: scale(1.07); }}
        }}
        @keyframes bio58-indeterminate {{
            from {{ transform: translateX(-105%); }}
            to {{ transform: translateX(305%); }}
        }}
        @keyframes bio58-skeleton {{
            from {{ background-position: 180% 0; }}
            to {{ background-position: -180% 0; }}
        }}
        {ambient_keyframes}
        {reveal_rule}
        {ambient_rule}
        .bio-status-running,.bio-status-chip[data-state="running"] {{
            animation: bio58-status-pulse 2.4s var(--ease-standard) infinite;
        }}
        .bio-progress-shell {{
            display: grid; gap: .48rem; padding: .72rem .82rem;
            border: 1px solid var(--bio58-border); border-radius: 12px;
            background: var(--bio58-surface-muted);
        }}
        .bio-progress-label {{ color: var(--bio58-copy); font-size: .78rem; font-weight: 700; }}
        .bio-progress-indeterminate {{
            position: relative; overflow: hidden; height: .55rem;
            border: 1px solid var(--bio58-border); border-radius: 999px;
            background: var(--bio58-surface-solid);
        }}
        .bio-progress-indeterminate::after {{
            content: ""; position: absolute; inset: 0 auto 0 0; width: 34%;
            border-radius: inherit; background: var(--bio58-gradient);
            animation: bio58-indeterminate 1.35s var(--ease-standard) infinite;
        }}
        .bio-skeleton-line,.bio-skeleton-block,.bio-skeleton-chart,.bio-skeleton-table-row {{
            background: linear-gradient(90deg,
                color-mix(in srgb,var(--bio58-surface-muted) 92%,transparent) 22%,
                color-mix(in srgb,var(--bio-secondary) 12%,var(--bio58-surface-muted)) 45%,
                color-mix(in srgb,var(--bio58-surface-muted) 92%,transparent) 68%);
            background-size: 220% 100%;
            animation: bio58-skeleton 1.7s linear infinite;
        }}
        """
    )


def _appearance_css(appearance_mode: str) -> str:
    light_rules = dedent(
        """
        :root {
            --bio58-page: #F4F7FB;
            --bio58-page-alt: #EDF3F9;
            --bio58-surface: rgba(255,255,255,.86);
            --bio58-surface-solid: #FFFFFF;
            --bio58-surface-muted: rgba(248,250,252,.92);
            --bio58-border: rgba(15,23,42,.11);
            --bio58-border-strong: rgba(15,23,42,.18);
            --bio58-text: #0F172A;
            --bio58-copy: #475569;
            --bio58-subtle: #64748B;
            --bio58-shadow: 0 18px 48px rgba(15,23,42,.10);
            --bio58-shadow-hover: 0 24px 64px rgba(15,23,42,.15);
            --bio58-input: rgba(255,255,255,.94);
            --bio58-code: #F8FAFC;
        }
        .stApp, [data-testid="stAppViewContainer"] {
            color: var(--bio58-text) !important;
            background:
                radial-gradient(circle at 8% -4%, color-mix(in srgb,var(--bio-primary) 12%,transparent), transparent 31%),
                radial-gradient(circle at 92% 4%, color-mix(in srgb,var(--bio-secondary) 10%,transparent), transparent 28%),
                linear-gradient(145deg,var(--bio58-page),var(--bio58-page-alt)) !important;
        }
        [data-testid="stHeader"] {
            background: rgba(248,250,252,.76) !important;
            border-bottom-color: rgba(15,23,42,.08) !important;
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg,rgba(255,255,255,.98),rgba(246,249,253,.99)) !important;
            border-right-color: var(--bio58-border) !important;
            box-shadow: 16px 0 52px rgba(15,23,42,.07) !important;
        }
        .bio-shell-bar,.bio-shell-status,.bio-page-context,.bio-card,.bio-kpi,.bio-db-card,
        .bio-surface,.bio-professional-strip,.bio-insight,.bio-command-bar,
        [data-testid="stMetric"],[data-testid="stPlotlyChart"],[data-testid="stDataFrame"],
        [data-testid="stTable"],div[data-testid="stForm"],[data-testid="stExpander"] {
            color: var(--bio58-text) !important;
            background: var(--bio58-surface) !important;
            border-color: var(--bio58-border) !important;
            box-shadow: var(--bio58-shadow) !important;
        }
        .bio-shell-title,.bio-shell-status-copy strong,.bio-page-name,.bio-card-title,
        .bio-kpi-value,.bio-db-title,.bio-section-label,.bio-empty-title,
        [data-testid="stMetricValue"],[data-testid="stMetricLabel"] {
            color: var(--bio58-text) !important;
        }
        .bio-shell-kicker,.bio-shell-status-copy span,.bio-shell-search-note,.bio-settings-note,
        .bio-page-description,.bio-card-copy,.bio-kpi-copy,.bio-db-copy,.bio-category-copy,
        .bio-empty-copy,.bio-timeline-copy,.bio-timeline-meta {
            color: var(--bio58-copy) !important;
        }
        [data-baseweb="input"] > div,[data-baseweb="select"] > div,
        [data-testid="stTextArea"] textarea,[data-testid="stNumberInput"] input,
        [data-testid="stDateInput"] input,[data-testid="stTimeInput"] input {
            color: var(--bio58-text) !important;
            background: var(--bio58-input) !important;
            border-color: var(--bio58-border) !important;
        }
        [data-baseweb="popover"],[data-baseweb="menu"],[role="listbox"],
        [data-testid="stPopoverBody"],[data-testid="stDialog"] > div {
            color: var(--bio58-text) !important;
            background: rgba(255,255,255,.98) !important;
            border-color: var(--bio58-border) !important;
        }
        [role="option"] { color: var(--bio58-copy) !important; }
        [role="option"]:hover,[aria-selected="true"][role="option"] {
            color: var(--bio58-text) !important;
            background: color-mix(in srgb,var(--bio-primary) 11%,white) !important;
        }
        [data-baseweb="tab-list"] { background: rgba(241,245,249,.82) !important; }
        [data-baseweb="tab"] { color: #64748B !important; }
        [aria-selected="true"][data-baseweb="tab"] { color: #0F172A !important; }
        pre, code, [data-testid="stCodeBlock"] { background: var(--bio58-code) !important; }
        .js-plotly-plot .plotly text { fill: #475569 !important; }
        .js-plotly-plot .gtitle { fill: #0F172A !important; }
        """
    )
    if appearance_mode == "Light":
        return light_rules
    if appearance_mode == "System":
        return f"@media (prefers-color-scheme: light) {{\n{light_rules}\n}}"
    return ""


@lru_cache(maxsize=128)
def premium_aesthetic_css(
    palette: ThemeSpec,
    font: FontSpec,
    *,
    appearance_mode: str = "Dark",
    compact: bool = False,
    reduce_motion: bool = False,
    motion_mode: str = "Balanced",
    intro_motion: bool = True,
    high_contrast: bool = False,
) -> str:
    """Return the final, theme-aware application-wide aesthetic layer.

    The CSS intentionally comes after historical compatibility styles. It does
    not remove old selectors; it normalizes them into one visual language so
    legacy and new pages render consistently across web, desktop and mobile.
    """

    density = ".82rem" if compact else "1rem"
    control_height = "2.32rem" if compact else "2.68rem"
    radius = "14px" if compact else "18px"
    border_alpha = ".27" if high_contrast else ".14"
    strong_border_alpha = ".38" if high_contrast else ".23"
    normalized_motion_mode = normalize_motion_mode(motion_mode, reduce_motion=reduce_motion)
    motion_profile = motion_profile_for(palette.name, normalized_motion_mode)
    motion_css = _motion_css(
        reduce_motion,
        motion_mode=normalized_motion_mode,
        intro_motion=intro_motion,
        theme_name=palette.name,
    )
    appearance_css = _appearance_css(appearance_mode)
    contrast_css = (
        """
        .bio-card,.bio-kpi,.bio-db-card,.bio-surface,.bio-insight,
        [data-testid="stMetric"],[data-testid="stPlotlyChart"],
        div[data-testid="stForm"],[data-testid="stExpander"] {
            border-width: 2px !important;
            background: var(--bio58-surface-solid) !important;
        }
        """
        if high_contrast
        else ""
    )

    return dedent(
        f"""
        <style id="{AESTHETIC_LAYER_ID}">
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=Outfit:wght@300;400;500;600;700;800&display=swap');
        /* Step 58 · premium adaptive visual system */

        :root {{
            --bio58-font: {font.css_stack};
            --bio58-page: {palette.bg_start};
            --bio58-page-alt: {palette.bg_mid};
            --bio58-surface: color-mix(in srgb,{palette.surface_strong} 88%,transparent);
            --bio58-surface-solid: {palette.bg_soft};
            --bio58-surface-muted: color-mix(in srgb,{palette.surface} 86%,transparent);
            --bio58-border: rgba(148,163,184,{border_alpha});
            --bio58-border-strong: rgba(148,163,184,{strong_border_alpha});
            --bio58-text: {palette.text};
            --bio58-copy: {palette.muted};
            --bio58-subtle: color-mix(in srgb,{palette.muted} 78%,transparent);
            --bio58-shadow: 0 20px 54px rgba(2,6,23,.30);
            --bio58-shadow-hover: 0 30px 78px rgba(2,6,23,.46);
            --bio58-input: rgba(5,10,22,.66);
            --bio58-code: rgba(4,8,18,.82);
            --bio58-radius: {radius};
            --bio58-control-height: {control_height};
            --bio58-density: {density};
            --motion-instant: 80ms;
            --motion-fast: {motion_profile.duration_fast_ms}ms;
            --motion-normal: {motion_profile.duration_normal_ms}ms;
            --motion-slow: {motion_profile.duration_slow_ms}ms;
            --motion-hover-lift: {motion_profile.hover_lift_px}px;
            --ease-standard: cubic-bezier(.2,.8,.2,1);
            --ease-enter: cubic-bezier(.16,1,.3,1);
            --ease-exit: cubic-bezier(.4,0,1,1);
            --bio58-gradient: linear-gradient(105deg,var(--bio-primary),var(--bio-secondary) 54%,var(--bio-accent));
            --bio58-gradient-soft: linear-gradient(135deg,
                color-mix(in srgb,var(--bio-primary) 17%,transparent),
                color-mix(in srgb,var(--bio-secondary) 9%,transparent) 55%,
                color-mix(in srgb,var(--bio-accent) 12%,transparent));
        }}

        html, body, .stApp, [data-testid="stAppViewContainer"] {{
            font-family: var(--bio58-font) !important;
            text-rendering: optimizeLegibility;
            -webkit-font-smoothing: antialiased;
        }}
        .main .block-container > [data-testid="stVerticalBlock"] {{ gap: var(--bio58-density); }}

        body {{ overflow-x: hidden; }}
        ::selection {{
            color: #FFFFFF;
            background: color-mix(in srgb,var(--bio-primary) 72%,var(--bio-secondary));
        }}

        .stApp, [data-testid="stAppViewContainer"] {{
            min-height: 100vh;
            isolation: isolate;
        }}
        .stApp::after {{
            content: "";
            position: fixed;
            inset: 0;
            z-index: 0;
            pointer-events: none;
            opacity: .22;
            background-image:
                linear-gradient(rgba(148,163,184,.035) 1px, transparent 1px),
                linear-gradient(90deg,rgba(148,163,184,.035) 1px, transparent 1px);
            background-size: 56px 56px;
            mask-image: radial-gradient(circle at 50% 24%,black,transparent 74%);
        }}
        [data-testid="stAppViewContainer"] > section,
        [data-testid="stAppViewContainer"] > div {{ position: relative; z-index: 1; }}

        .main .block-container {{
            max-width: 1480px !important;
            padding-top: clamp(.9rem,2vw,1.45rem) !important;
            padding-bottom: 5rem !important;
        }}

        [data-testid="stHeader"] {{
            background: color-mix(in srgb,var(--bio58-page) 68%,transparent) !important;
            border-bottom: 1px solid var(--bio58-border) !important;
            backdrop-filter: blur(22px) saturate(150%);
            -webkit-backdrop-filter: blur(22px) saturate(150%);
        }}
        [data-testid="stToolbar"] button {{
            border-radius: 12px !important;
            transition: transform var(--motion-fast) var(--ease-standard), background var(--motion-fast) var(--ease-standard) !important;
        }}
        [data-testid="stToolbar"] button:hover {{
            transform: translateY(-1px);
            background: color-mix(in srgb,var(--bio-primary) 12%,transparent) !important;
        }}

        [data-testid="stSidebar"] {{
            backdrop-filter: blur(28px) saturate(135%);
            -webkit-backdrop-filter: blur(28px) saturate(135%);
            box-shadow: 18px 0 68px rgba(2,6,23,.22);
        }}
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{ gap: .36rem; }}
        [data-testid="stSidebar"] [data-testid="stPageLink"] a {{
            position: relative;
            min-height: 2.42rem;
            border: 1px solid transparent;
            border-radius: 12px !important;
            color: var(--bio58-copy) !important;
            transition: transform var(--motion-fast) var(--ease-standard),border-color var(--motion-fast) var(--ease-standard),background var(--motion-fast) var(--ease-standard),color var(--motion-fast) var(--ease-standard) !important;
        }}
        [data-testid="stSidebar"] [data-testid="stPageLink"] a::before {{
            content: "";
            position: absolute;
            left: 0;
            top: 22%;
            width: 3px;
            height: 56%;
            border-radius: 999px;
            background: var(--bio58-gradient);
            opacity: 0;
            transform: scaleY(.5);
            transition: opacity var(--motion-fast) var(--ease-standard),transform var(--motion-fast) var(--ease-standard);
        }}
        [data-testid="stSidebar"] [data-testid="stPageLink"] a:hover {{
            color: var(--bio58-text) !important;
            border-color: var(--bio58-border);
            background: var(--bio58-gradient-soft) !important;
            transform: translateX(2px);
        }}
        [data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] {{
            color: var(--bio58-text) !important;
            border-color: color-mix(in srgb,var(--bio-primary) 42%,transparent) !important;
            background: var(--bio58-gradient-soft) !important;
            box-shadow: 0 12px 34px color-mix(in srgb,var(--bio-glow) 66%,transparent);
        }}
        [data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"]::before {{
            opacity: 1;
            transform: scaleY(1);
        }}

        .bio-shell-bar {{
            position: sticky;
            top: .55rem;
            z-index: 998;
            border-radius: calc(var(--bio58-radius) + 2px) !important;
            border: 1px solid var(--bio58-border-strong) !important;
            background: color-mix(in srgb,var(--bio58-surface) 88%,transparent) !important;
            box-shadow: 0 18px 58px rgba(2,6,23,.28) !important;
            backdrop-filter: blur(24px) saturate(155%);
            -webkit-backdrop-filter: blur(24px) saturate(155%);
        }}
        .bio-shell-status-dot {{
            box-shadow: 0 0 0 5px rgba(52,211,153,.09),0 0 24px rgba(52,211,153,.38);
            animation: none;
        }}

        .bio-page-context {{
            position: relative;
            overflow: hidden;
            border-radius: var(--bio58-radius) !important;
            border: 1px solid var(--bio58-border) !important;
            background: var(--bio58-surface-muted) !important;
            box-shadow: 0 12px 36px rgba(2,6,23,.18) !important;
            backdrop-filter: blur(18px);
        }}
        .bio-page-context::after {{
            content: "";
            position: absolute;
            right: -28px;
            top: -52px;
            width: 160px;
            height: 160px;
            border-radius: 50%;
            background: radial-gradient(circle,color-mix(in srgb,var(--bio-secondary) 16%,transparent),transparent 66%);
            pointer-events: none;
        }}
        .bio-page-name {{ letter-spacing: -.025em; }}
        .bio-page-position {{
            border: 1px solid var(--bio58-border);
            border-radius: 999px;
            background: color-mix(in srgb,var(--bio-primary) 8%,transparent);
        }}

        .bio-hero {{
            isolation: isolate;
            min-height: 220px;
            padding: clamp(1.55rem,4vw,3rem) !important;
            border-radius: clamp(20px,3vw,32px) !important;
            border: 1px solid var(--bio58-border-strong) !important;
            background:
                linear-gradient(128deg,color-mix(in srgb,{palette.hero_start} 92%,transparent),color-mix(in srgb,{palette.hero_end} 90%,transparent)) !important;
            box-shadow: 0 34px 100px rgba(2,6,23,.44),inset 0 1px 0 rgba(255,255,255,.07) !important;
            backdrop-filter: blur(30px) saturate(145%);
            -webkit-backdrop-filter: blur(30px) saturate(145%);
        }}
        .bio-hero::before {{
            inset: -20% !important;
            opacity: .82 !important;
            background:
                radial-gradient(circle at 78% 18%,color-mix(in srgb,var(--bio-secondary) 30%,transparent),transparent 28%),
                radial-gradient(circle at 20% 84%,color-mix(in srgb,var(--bio-primary) 26%,transparent),transparent 34%),
                conic-gradient(from 210deg at 72% 45%,transparent,color-mix(in srgb,var(--bio-accent) 10%,transparent),transparent 36%) !important;
            animation: none;
        }}
        .bio-hero::after {{
            content: "";
            position: absolute;
            inset: 0;
            z-index: 0;
            pointer-events: none;
            opacity: .24;
            background-image:
                linear-gradient(115deg,transparent 0 48%,rgba(255,255,255,.055) 49% 50%,transparent 51%),
                radial-gradient(circle at center,rgba(255,255,255,.07) 1px,transparent 1.5px);
            background-size: 100% 100%,22px 22px;
            mask-image: linear-gradient(90deg,transparent 8%,black 42%,black 100%);
        }}
        .bio-eyebrow {{
            border-color: color-mix(in srgb,var(--bio-primary) 44%,transparent) !important;
            background: color-mix(in srgb,var(--bio-primary) 15%,transparent) !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.08);
            backdrop-filter: blur(12px);
        }}
        .bio-hero-title {{
            max-width: 1050px !important;
            text-wrap: balance;
            text-shadow: 0 12px 46px rgba(2,6,23,.36);
        }}
        .bio-gradient-text {{
            background-size: 180% 100% !important;
            filter: saturate(1.08);
        }}
        .bio-hero-subtitle {{ max-width: 980px !important; text-wrap: pretty; }}
        .bio-chip {{
            border-color: var(--bio58-border) !important;
            background: color-mix(in srgb,var(--bio58-surface) 76%,transparent) !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.055);
            backdrop-filter: blur(12px);
            transition: transform var(--motion-fast) var(--ease-standard),border-color var(--motion-fast) var(--ease-standard) !important;
        }}
        .bio-chip:hover {{
            transform: translateY(-1px);
            border-color: color-mix(in srgb,var(--bio-secondary) 42%,transparent) !important;
        }}

        .bio-card,.bio-kpi,.bio-db-card,.bio-surface,.bio-insight,
        [data-testid="stMetric"],[data-testid="stPlotlyChart"],
        div[data-testid="stForm"],[data-testid="stExpander"],
        [data-testid="stDataFrame"],[data-testid="stTable"] {{
            position: relative;
            border-radius: var(--bio58-radius) !important;
            border: 1px solid var(--bio58-border) !important;
            background: var(--bio58-surface) !important;
            box-shadow: var(--bio58-shadow) !important;
            backdrop-filter: blur(20px) saturate(130%);
            -webkit-backdrop-filter: blur(20px) saturate(130%);
        }}
        .bio-card,.bio-kpi,.bio-db-card {{ overflow: hidden; }}
        .bio-card::before,.bio-kpi::before,.bio-db-card::before {{
            content: "";
            position: absolute;
            left: 0;
            right: 0;
            top: 0;
            height: 2px;
            opacity: .7;
            background: var(--bio58-gradient);
        }}
        .bio-card,.bio-kpi,.bio-db-card,[data-testid="stMetric"] {{
            transition: transform var(--motion-normal) var(--ease-standard),border-color var(--motion-normal) var(--ease-standard),box-shadow var(--motion-normal) var(--ease-standard) !important;
        }}
        .bio-card:hover,.bio-kpi:hover,.bio-db-card:hover,[data-testid="stMetric"]:hover {{
            transform: translateY(-3px);
            border-color: color-mix(in srgb,var(--bio-primary) 36%,transparent) !important;
            box-shadow: var(--bio58-shadow-hover) !important;
        }}
        .bio-card-icon,.bio-db-icon,.bio-insight-icon {{
            box-shadow: inset 0 1px 0 rgba(255,255,255,.10),0 12px 28px color-mix(in srgb,var(--bio-glow) 60%,transparent);
        }}
        .bio-card-title,.bio-db-title,.bio-kpi-value {{ text-wrap: balance; }}
        .bio-card-copy,.bio-db-copy,.bio-kpi-copy {{ text-wrap: pretty; }}
        [data-testid="stMetricValue"] {{
            background: linear-gradient(100deg,var(--bio58-text),color-mix(in srgb,var(--bio-secondary) 78%,var(--bio58-text)));
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent !important;
        }}
        [data-testid="stMetricDelta"] {{
            width: fit-content;
            padding: .2rem .46rem;
            border-radius: 999px;
            background: color-mix(in srgb,var(--bio-success) 10%,transparent);
        }}

        .bio-section-label {{
            margin-top: clamp(1.45rem,3vw,2.15rem) !important;
            font-size: clamp(1.02rem,2vw,1.24rem) !important;
        }}
        .bio-section-label::before {{
            content: "";
            width: 7px;
            height: 7px;
            flex: 0 0 7px;
            border-radius: 50%;
            background: var(--bio58-gradient);
            box-shadow: 0 0 20px var(--bio-glow);
        }}

        div.stButton > button,div.stDownloadButton > button,
        [data-testid="stFormSubmitButton"] > button,[data-testid="stPopover"] > button,
        [data-testid="stPageLink"] a {{
            min-height: var(--bio58-control-height);
            border-radius: 12px !important;
            border: 1px solid var(--bio58-border-strong) !important;
            color: var(--bio58-text) !important;
            background: color-mix(in srgb,var(--bio58-surface-solid) 72%,transparent) !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.055),0 8px 22px rgba(2,6,23,.12);
            font-weight: 760 !important;
            transition: transform var(--motion-fast) var(--ease-standard),border-color var(--motion-fast) var(--ease-standard),box-shadow var(--motion-fast) var(--ease-standard),filter var(--motion-fast) var(--ease-standard) !important;
        }}
        div.stButton > button:hover,div.stDownloadButton > button:hover,
        [data-testid="stFormSubmitButton"] > button:hover,[data-testid="stPopover"] > button:hover {{
            transform: translateY(-1px);
            border-color: color-mix(in srgb,var(--bio-primary) 50%,transparent) !important;
            box-shadow: 0 14px 34px rgba(2,6,23,.22),0 0 24px color-mix(in srgb,var(--bio-glow) 38%,transparent);
            filter: brightness(1.05);
        }}
        div.stButton > button:active,div.stDownloadButton > button:active,
        [data-testid="stFormSubmitButton"] > button:active {{ transform: translateY(0) scale(.99); }}
        div.stButton > button[kind="primary"],
        [data-testid="stFormSubmitButton"] > button[kind="primary"] {{
            color: #FFFFFF !important;
            border-color: color-mix(in srgb,var(--bio-primary) 62%,white 12%) !important;
            background: var(--bio58-gradient) !important;
            box-shadow: 0 13px 34px var(--bio-glow),inset 0 1px 0 rgba(255,255,255,.22) !important;
        }}
        button:disabled,[aria-disabled="true"] {{
            cursor: not-allowed !important;
            opacity: .48 !important;
            filter: grayscale(.18) !important;
            transform: none !important;
            box-shadow: none !important;
        }}

        [data-baseweb="input"] > div,[data-baseweb="select"] > div,
        [data-testid="stTextArea"] textarea,[data-testid="stNumberInput"] input,
        [data-testid="stDateInput"] input,[data-testid="stTimeInput"] input {{
            min-height: var(--bio58-control-height);
            border: 1px solid var(--bio58-border) !important;
            border-radius: 12px !important;
            color: var(--bio58-text) !important;
            background: var(--bio58-input) !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.035) !important;
            transition: border-color var(--motion-fast) var(--ease-standard),box-shadow var(--motion-fast) var(--ease-standard),background var(--motion-fast) var(--ease-standard) !important;
        }}
        [data-baseweb="input"] > div:focus-within,[data-baseweb="select"] > div:focus-within,
        [data-testid="stTextArea"] textarea:focus {{
            border-color: color-mix(in srgb,var(--bio-secondary) 62%,transparent) !important;
            box-shadow: 0 0 0 3px color-mix(in srgb,var(--bio-secondary) 14%,transparent),inset 0 1px 0 rgba(255,255,255,.05) !important;
        }}
        input::placeholder,textarea::placeholder {{ color: var(--bio58-subtle) !important; opacity: .82; }}
        [data-baseweb="popover"],[data-baseweb="menu"],[role="listbox"],
        [data-testid="stPopoverBody"] {{
            border: 1px solid var(--bio58-border-strong) !important;
            border-radius: 14px !important;
            background: color-mix(in srgb,var(--bio58-surface-solid) 96%,transparent) !important;
            box-shadow: 0 26px 78px rgba(2,6,23,.46) !important;
            backdrop-filter: blur(24px) saturate(145%);
        }}
        [role="option"] {{ border-radius: 9px !important; margin: 2px 5px; }}
        [role="option"]:hover,[aria-selected="true"][role="option"] {{
            background: var(--bio58-gradient-soft) !important;
        }}

        [data-baseweb="tab-list"] {{
            gap: .34rem !important;
            padding: .32rem !important;
            border: 1px solid var(--bio58-border) !important;
            border-radius: 14px !important;
            background: color-mix(in srgb,var(--bio58-surface-solid) 56%,transparent) !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.035);
        }}
        [data-baseweb="tab"] {{
            min-height: 2.3rem;
            border-radius: 10px !important;
            transition: color var(--motion-fast) var(--ease-standard),background var(--motion-fast) var(--ease-standard),transform var(--motion-fast) var(--ease-standard) !important;
        }}
        [data-baseweb="tab"]:hover {{ color: var(--bio58-text) !important; transform: translateY(-1px); }}
        [aria-selected="true"][data-baseweb="tab"] {{
            color: var(--bio58-text) !important;
            background: var(--bio58-gradient-soft) !important;
            box-shadow: 0 8px 24px rgba(2,6,23,.14);
        }}

        [data-testid="stExpander"] details summary {{
            min-height: 2.7rem;
            border-radius: 12px;
            color: var(--bio58-text) !important;
            font-weight: 760;
            transition: background var(--motion-fast) var(--ease-standard) !important;
        }}
        [data-testid="stExpander"] details summary:hover {{ background: var(--bio58-gradient-soft); }}
        [data-testid="stExpander"] details[open] summary {{
            border-bottom: 1px solid var(--bio58-border);
            border-bottom-left-radius: 0;
            border-bottom-right-radius: 0;
        }}

        [data-testid="stFileUploaderDropzone"] {{
            min-height: 112px;
            border: 1.5px dashed color-mix(in srgb,var(--bio-secondary) 42%,var(--bio58-border)) !important;
            border-radius: var(--bio58-radius) !important;
            background:
                radial-gradient(circle at 82% 20%,color-mix(in srgb,var(--bio-secondary) 11%,transparent),transparent 32%),
                var(--bio58-surface-muted) !important;
            transition: border-color var(--motion-fast) var(--ease-standard),background var(--motion-fast) var(--ease-standard),transform var(--motion-fast) var(--ease-standard) !important;
        }}
        [data-testid="stFileUploaderDropzone"]:hover {{
            transform: translateY(-1px);
            border-color: color-mix(in srgb,var(--bio-secondary) 68%,transparent) !important;
            background: var(--bio58-gradient-soft) !important;
        }}
        [data-testid="stFileUploaderFile"] {{
            border-radius: 12px;
            border: 1px solid var(--bio58-border);
            background: var(--bio58-surface-muted);
        }}

        [data-testid="stDataFrame"],[data-testid="stTable"] {{
            overflow: hidden;
            border-color: var(--bio58-border-strong) !important;
        }}
        [data-testid="stDataFrame"] canvas {{ border-radius: calc(var(--bio58-radius) - 2px); }}
        [data-testid="stPlotlyChart"] {{
            overflow: hidden;
            padding: .45rem !important;
        }}
        [data-testid="stPlotlyChart"] .modebar {{
            padding: .2rem .3rem !important;
            border: 1px solid var(--bio58-border);
            border-radius: 10px;
            background: color-mix(in srgb,var(--bio58-surface-solid) 82%,transparent) !important;
            opacity: .55;
            transition: opacity var(--motion-fast) var(--ease-standard);
        }}
        [data-testid="stPlotlyChart"]:hover .modebar {{ opacity: 1; }}

        [data-testid="stAlert"] {{
            overflow: hidden;
            border: 1px solid var(--bio58-border-strong) !important;
            border-radius: 14px !important;
            box-shadow: 0 12px 34px rgba(2,6,23,.15);
            backdrop-filter: blur(16px);
        }}
        [data-testid="stToast"] {{
            border: 1px solid var(--bio58-border-strong) !important;
            border-radius: 14px !important;
            background: color-mix(in srgb,var(--bio58-surface-solid) 95%,transparent) !important;
            box-shadow: 0 22px 64px rgba(2,6,23,.42) !important;
            backdrop-filter: blur(22px);
        }}
        [data-testid="stDialog"] > div {{
            border: 1px solid var(--bio58-border-strong) !important;
            border-radius: 22px !important;
            background: color-mix(in srgb,var(--bio58-surface-solid) 96%,transparent) !important;
            box-shadow: 0 38px 120px rgba(2,6,23,.62) !important;
            backdrop-filter: blur(28px);
        }}

        [data-testid="stProgressBar"] > div {{
            overflow: hidden;
            border: 1px solid var(--bio58-border);
            border-radius: 999px;
            background: color-mix(in srgb,var(--bio58-surface-solid) 70%,transparent) !important;
        }}
        [data-testid="stProgressBar"] > div > div > div {{
            background: linear-gradient(90deg,var(--bio-primary),var(--bio-secondary),var(--bio-accent)) !important;
            background-size: 100% 100% !important;
            transition: width var(--motion-normal) var(--ease-standard) !important;
        }}
        [data-testid="stSpinner"] {{ color: var(--bio-secondary) !important; }}

        [data-testid="stChatMessage"] {{
            border: 1px solid var(--bio58-border);
            border-radius: var(--bio58-radius);
            background: var(--bio58-surface-muted);
            box-shadow: 0 12px 34px rgba(2,6,23,.15);
        }}
        pre,[data-testid="stCodeBlock"] {{
            border: 1px solid var(--bio58-border) !important;
            border-radius: 14px !important;
            background: var(--bio58-code) !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.035);
        }}
        kbd {{
            padding: .14rem .38rem;
            border: 1px solid var(--bio58-border-strong);
            border-bottom-width: 2px;
            border-radius: 6px;
            background: var(--bio58-surface-muted);
            box-shadow: 0 2px 0 rgba(2,6,23,.18);
        }}

        [data-testid="stCheckbox"],[data-testid="stToggle"],[data-testid="stRadio"] {{
            border-radius: 10px;
        }}
        [data-baseweb="slider"] [role="slider"] {{
            border-color: color-mix(in srgb,var(--bio-secondary) 52%,white 12%) !important;
            box-shadow: 0 0 0 5px color-mix(in srgb,var(--bio-secondary) 11%,transparent);
        }}

        .bio-badge,.bio-status-chip,.bio-source-chip,.bio-local-pill,.bio-edition-pill {{
            box-shadow: inset 0 1px 0 rgba(255,255,255,.055);
            backdrop-filter: blur(10px);
        }}
        .bio-professional-strip {{
            border-left: 3px solid var(--bio-primary) !important;
            background: linear-gradient(90deg,color-mix(in srgb,var(--bio-primary) 9%,transparent),var(--bio58-surface)) !important;
        }}
        .bio-density-fill {{
            background: var(--bio58-gradient) !important;
            box-shadow: 0 0 18px var(--bio-glow);
        }}
        .bio-timeline-item::before {{
            box-shadow: 0 0 0 5px color-mix(in srgb,var(--bio-primary) 10%,transparent),0 0 22px var(--bio-glow);
        }}
        .bio-empty {{
            background:
                radial-gradient(circle at 50% 0,color-mix(in srgb,var(--bio-primary) 10%,transparent),transparent 48%),
                var(--bio58-surface-muted) !important;
        }}

        :focus-visible {{
            outline: 3px solid color-mix(in srgb,var(--bio-secondary) 70%,white 14%) !important;
            outline-offset: 3px !important;
        }}
        a {{ text-underline-offset: .2em; }}
        a:hover {{ text-decoration-thickness: 2px; }}

        ::-webkit-scrollbar {{ width: 10px; height: 10px; }}
        ::-webkit-scrollbar-track {{ background: color-mix(in srgb,var(--bio58-page) 90%,black); }}
        ::-webkit-scrollbar-thumb {{
            border: 2px solid color-mix(in srgb,var(--bio58-page) 90%,black);
            border-radius: 999px;
            background: linear-gradient(var(--bio-primary),var(--bio-secondary));
        }}
        ::-webkit-scrollbar-thumb:hover {{ filter: brightness(1.16); }}

        /* Purposeful interaction states: charts remain stable while controls communicate action. */
        [data-testid="stPlotlyChart"] {{
            transform: none !important;
            transition: border-color var(--motion-fast) var(--ease-standard),
                        box-shadow var(--motion-normal) var(--ease-standard) !important;
        }}
        [data-testid="stPlotlyChart"]:hover {{ transform: none !important; }}
        button,[role="button"],[data-testid="stDownloadButton"] button {{
            transition: transform var(--motion-fast) var(--ease-standard),
                        box-shadow var(--motion-normal) var(--ease-standard),
                        border-color var(--motion-fast) var(--ease-standard),
                        background var(--motion-normal) var(--ease-standard) !important;
        }}
        button:active,[role="button"]:active {{
            transform: translateY(1px) scale(.992) !important;
        }}
        button:disabled,[aria-disabled="true"] {{
            transform: none !important; cursor: not-allowed !important;
        }}
        .bio-action-success {{ animation: bio58-reveal var(--motion-normal) var(--ease-enter) both; }}
        .bio-action-error {{ animation: bio58-reveal var(--motion-normal) var(--ease-enter) both; }}
        .bio-card:hover,.bio-kpi:hover,.bio-db-card:hover,[data-testid="stMetric"]:hover {{
            transform: translateY(calc(var(--motion-hover-lift) * -1)) !important;
        }}
        .bio-skeleton {{
            display: grid; gap: .7rem; padding: 1rem; min-height: 130px;
            border: 1px solid var(--bio58-border); border-radius: var(--bio58-radius);
            background: var(--bio58-surface);
        }}
        .bio-skeleton-line {{ height: .8rem; border-radius: 999px; }}
        .bio-skeleton-line.short {{ width: 46%; }}
        .bio-skeleton-block {{ min-height: 72px; border-radius: 12px; }}
        .bio-skeleton-chart {{ min-height: 220px; border-radius: 14px; }}
        .bio-skeleton-table-row {{ height: 2rem; border-radius: 8px; }}

        /* Legacy pages sometimes use five or more native Streamlit columns.
           Preserve the desktop layout when it fits, but let those rows wrap
           before labels, metrics and primary actions collapse into slivers. */
        @media (max-width: 1460px) {{
            [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]:nth-child(5)) {{
                align-items: stretch;
                flex-wrap: wrap !important;
            }}
            [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]:nth-child(5)) > [data-testid="stColumn"] {{
                flex: 1 1 205px !important;
                min-width: 205px !important;
            }}
        }}
        @media (max-width: 1100px) {{
            .bio-shell-bar {{ position: static; }}
            .bio-hero {{ min-height: 0; }}
            .bio-board,.bio-db-grid {{ grid-template-columns: repeat(2,minmax(0,1fr)) !important; }}
        }}
        @supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {{
            .bio-shell-bar,.bio-page-context,.bio-hero,.bio-card,.bio-kpi,.bio-db-card,
            .bio-surface,.bio-insight,[data-testid="stMetric"],[data-testid="stPlotlyChart"],
            div[data-testid="stForm"],[data-testid="stExpander"] {{
                background: var(--bio58-surface-solid) !important;
            }}
        }}
        @media (prefers-reduced-motion: reduce) {{
            html {{ scroll-behavior: auto !important; }}
            *,*::before,*::after {{
                animation-name: none !important;
                animation-duration: .001ms !important;
                animation-iteration-count: 1 !important;
                transition-duration: .001ms !important;
            }}
            .bio-card:hover,.bio-kpi:hover,.bio-db-card:hover,[data-testid="stMetric"]:hover,
            button:hover,button:active,[role="button"]:hover,[role="button"]:active {{
                transform: none !important;
            }}
        }}
        @media (prefers-contrast: more) {{
            :root {{ --bio58-border: rgba(148,163,184,.34); --bio58-border-strong: rgba(148,163,184,.52); }}
            :focus-visible {{ outline-width: 4px !important; }}
        }}
        @media (forced-colors: active) {{
            .bio-card,.bio-kpi,.bio-db-card,.bio-hero,.bio-page-context,
            [data-testid="stMetric"],[data-testid="stPlotlyChart"] {{
                forced-color-adjust: auto;
                border: 1px solid CanvasText !important;
                box-shadow: none !important;
            }}
        }}
        @media (max-width: 760px) {{
            :root {{ --bio58-radius: 15px; --bio58-control-height: 2.55rem; }}
            .main .block-container {{ padding: .7rem .72rem 3.5rem !important; }}
            .bio-shell-bar {{ border-radius: 15px !important; }}
            .bio-page-context {{ padding: .72rem .78rem !important; }}
            .bio-hero {{ padding: 1.2rem !important; border-radius: 18px !important; }}
            .bio-hero-title {{ font-size: clamp(1.65rem,9vw,2.35rem) !important; letter-spacing: -.045em !important; }}
            .bio-hero-subtitle {{ font-size: .9rem !important; line-height: 1.55 !important; }}
            .bio-chip-row {{ gap: .36rem !important; }}
            .bio-chip {{ padding: .32rem .52rem !important; font-size: .68rem !important; }}
            .bio-board,.bio-db-grid {{ grid-template-columns: 1fr !important; }}
            [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]:nth-child(5)) > [data-testid="stColumn"] {{
                flex-basis: 100% !important;
                min-width: 0 !important;
            }}
            [data-baseweb="tab-list"] {{ overflow-x: auto; flex-wrap: nowrap; scrollbar-width: thin; }}
            [data-baseweb="tab"] {{ flex: 0 0 auto; }}
            .bio-card:hover,.bio-kpi:hover,.bio-db-card:hover,[data-testid="stMetric"]:hover {{ transform: none; }}
            .bio-shell-bar,.bio-page-context,.bio-card,.bio-kpi,.bio-db-card,.bio-surface,
            [data-testid="stMetric"],[data-testid="stPlotlyChart"] {{
                backdrop-filter: none !important;
                -webkit-backdrop-filter: none !important;
            }}
        }}

        {motion_css}
        {contrast_css}
        {appearance_css}
        </style>
        """
    )


def apply_premium_aesthetic(
    palette: ThemeSpec,
    font: FontSpec,
    *,
    appearance_mode: str,
    compact: bool,
    reduce_motion: bool,
    motion_mode: str = "Balanced",
    intro_motion: bool = True,
    high_contrast: bool,
) -> None:
    """Render the final UI layer with a safe fallback for supported Streamlit versions."""

    css = premium_aesthetic_css(
        palette,
        font,
        appearance_mode=appearance_mode,
        compact=compact,
        reduce_motion=reduce_motion,
        motion_mode=motion_mode,
        intro_motion=intro_motion,
        high_contrast=high_contrast,
    )
    if st is None:
        return
    html_renderer = getattr(st, "html", None)
    if callable(html_renderer):
        html_renderer(css)
    else:
        st.markdown(css, unsafe_allow_html=True)
