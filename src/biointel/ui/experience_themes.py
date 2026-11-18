from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from textwrap import dedent

from biointel.ui.appearance_engine import (
    layout_archetype_css,
    light_theme_for,
    theme_button_foreground,
)
from biointel.ui.style_catalog import ThemeSpec


@dataclass(frozen=True)
class ExperienceSpec:
    """Desktop visual-language profile layered on top of a colour palette."""

    title: str
    archetype: str
    audience: str
    summary: str
    max_width: str
    sidebar_width: str
    hero_radius: str
    card_radius: str
    control_radius: str
    chip_radius: str
    border_width: str
    card_padding: str
    grid_gap: str
    blur: str
    shadow: str
    hover_shadow: str
    heading_tracking: str
    heading_transform: str
    pattern_css: str
    surface_css: str
    hero_css: str
    button_css: str
    nav_active_css: str
    extra_css: str = ""


# These profiles intentionally change composition and interaction language, not
# only colour tokens. Rose/Sakura provide two feminine professional options;
# Midnight/Ember provide two masculine professional options without changing
# the scientific functionality or typography catalogue.
EXPERIENCES: dict[str, ExperienceSpec] = {
    "BioIntel Signature": ExperienceSpec(
        title="BioIntel Signature",
        archetype="Scientific intelligence",
        audience="Research and life-science teams",
        summary="Calm cyan-blue scientific workspace with evidence violet and restrained motion.",
        max_width="1480px",
        sidebar_width="274px",
        hero_radius="18px",
        card_radius="16px",
        control_radius="10px",
        chip_radius="999px",
        border_width="1px",
        card_padding="1.05rem",
        grid_gap=".84rem",
        blur="8px",
        shadow="0 14px 36px rgba(2,6,23,.22)",
        hover_shadow="0 20px 46px rgba(2,6,23,.30)",
        heading_tracking="-.035em",
        heading_transform="none",
        pattern_css="linear-gradient(rgba(34,211,238,.024) 1px,transparent 1px),linear-gradient(90deg,rgba(59,130,246,.024) 1px,transparent 1px)",
        surface_css="linear-gradient(150deg,color-mix(in srgb,var(--bio-surface-strong) 96%,transparent),color-mix(in srgb,var(--bio-surface) 90%,transparent))",
        hero_css="linear-gradient(112deg,color-mix(in srgb,#22D3EE 10%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-surface-strong) 96%,transparent) 58%,color-mix(in srgb,#3B82F6 8%,var(--bio-surface-strong)))",
        button_css="linear-gradient(105deg,#22D3EE,#3B82F6)",
        nav_active_css="linear-gradient(90deg,color-mix(in srgb,#22D3EE 18%,transparent),transparent)",
        extra_css=".bio-card,.bio-kpi,.bio-db-card{border-top-color:color-mix(in srgb,#22D3EE 34%,var(--bio-border))!important}.bio-hero::after{content:'';position:absolute;right:1.4rem;top:1.25rem;width:76px;height:2px;background:linear-gradient(90deg,#22D3EE,#3B82F6,#8B5CF6);border-radius:999px;opacity:.72}",
    ),
    "Executive": ExperienceSpec(
        title="Corporate Command",
        archetype="Executive dashboard",
        audience="Universal professional",
        summary="Structured command-centre layout with disciplined grids and decisive blue actions.",
        max_width="1460px",
        sidebar_width="274px",
        hero_radius="18px",
        card_radius="14px",
        control_radius="9px",
        chip_radius="8px",
        border_width="1px",
        card_padding="1.08rem",
        grid_gap="0.82rem",
        blur="10px",
        shadow="0 14px 34px rgba(2,6,23,.25)",
        hover_shadow="0 20px 48px rgba(2,6,23,.36)",
        heading_tracking="-.035em",
        heading_transform="none",
        pattern_css="linear-gradient(rgba(148,163,184,.032) 1px,transparent 1px),linear-gradient(90deg,rgba(148,163,184,.032) 1px,transparent 1px)",
        surface_css="linear-gradient(150deg,color-mix(in srgb,var(--bio-surface-strong) 94%,transparent),color-mix(in srgb,var(--bio-surface) 84%,transparent))",
        hero_css="linear-gradient(112deg,color-mix(in srgb,var(--bio-primary) 18%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-surface-strong) 92%,transparent) 58%,color-mix(in srgb,var(--bio-secondary) 12%,var(--bio-surface-strong)))",
        button_css="linear-gradient(105deg,var(--bio-primary),color-mix(in srgb,var(--bio-primary) 72%,var(--bio-secondary)))",
        nav_active_css="linear-gradient(90deg,color-mix(in srgb,var(--bio-primary) 28%,transparent),transparent)",
        extra_css=".bio-card,.bio-kpi,.bio-db-card{border-left:3px solid color-mix(in srgb,var(--bio-primary) 55%,transparent)!important}.bio-hero::after{content:'';position:absolute;right:1.4rem;top:1.25rem;width:72px;height:5px;background:linear-gradient(90deg,var(--bio-primary),var(--bio-secondary));border-radius:2px}",
    ),
    "Clinical": ExperienceSpec(
        title="Clinical Cleanroom",
        archetype="Sterile minimal",
        audience="Clinical and laboratory",
        summary="Bright, calm and low-decoration workspace inspired by validated clinical systems.",
        max_width="1380px",
        sidebar_width="258px",
        hero_radius="12px",
        card_radius="10px",
        control_radius="7px",
        chip_radius="999px",
        border_width="1px",
        card_padding="1rem",
        grid_gap="1rem",
        blur="2px",
        shadow="0 8px 22px rgba(2,6,23,.14)",
        hover_shadow="0 12px 30px rgba(2,6,23,.20)",
        heading_tracking="-.018em",
        heading_transform="none",
        pattern_css="radial-gradient(circle at 16% 10%,color-mix(in srgb,var(--bio-primary) 8%,transparent),transparent 28%)",
        surface_css="color-mix(in srgb,var(--bio-surface-strong) 97%,transparent)",
        hero_css="linear-gradient(180deg,color-mix(in srgb,var(--bio-primary) 8%,var(--bio-surface-strong)),var(--bio-surface-strong))",
        button_css="var(--bio-primary)",
        nav_active_css="color-mix(in srgb,var(--bio-primary) 14%,transparent)",
        extra_css=".bio-hero::before,.bio-card::before,.bio-kpi::after,.bio-db-card::after{display:none!important}.bio-eyebrow{text-transform:none!important;letter-spacing:.02em!important}.bio-card,.bio-kpi,.bio-db-card,[data-testid='stMetric']{box-shadow:none!important}",
    ),
    "Regulatory": ExperienceSpec(
        title="Compliance Ledger",
        archetype="Formal governance",
        audience="Quality and regulatory",
        summary="Squared audit-led layout with ledger rules, formal labels and high information hierarchy.",
        max_width="1420px",
        sidebar_width="282px",
        hero_radius="6px",
        card_radius="5px",
        control_radius="4px",
        chip_radius="4px",
        border_width="1px",
        card_padding="1.1rem",
        grid_gap=".7rem",
        blur="0px",
        shadow="0 10px 24px rgba(2,6,23,.22)",
        hover_shadow="0 14px 30px rgba(2,6,23,.30)",
        heading_tracking=".005em",
        heading_transform="uppercase",
        pattern_css="repeating-linear-gradient(0deg,rgba(148,163,184,.035) 0 1px,transparent 1px 28px)",
        surface_css="linear-gradient(180deg,color-mix(in srgb,var(--bio-surface-strong) 98%,transparent),color-mix(in srgb,var(--bio-surface) 94%,transparent))",
        hero_css="linear-gradient(90deg,color-mix(in srgb,var(--bio-primary) 15%,var(--bio-surface-strong)) 0 12px,var(--bio-surface-strong) 12px)",
        button_css="linear-gradient(90deg,var(--bio-primary),var(--bio-primary) 78%,var(--bio-secondary))",
        nav_active_css="linear-gradient(90deg,var(--bio-primary) 0 4px,color-mix(in srgb,var(--bio-primary) 13%,transparent) 4px)",
        extra_css=".bio-hero-title,.bio-section-label{font-variant-caps:all-small-caps}.bio-card,.bio-kpi,.bio-db-card{border-top:2px solid color-mix(in srgb,var(--bio-secondary) 70%,transparent)!important}[data-testid='stDataFrame']{border-radius:3px!important}",
    ),
    "Aurora": ExperienceSpec(
        title="Fluid Aurora",
        archetype="Creative fluid",
        audience="Exploration and ideation",
        summary="Organic gradients, floating cards and energetic motion for exploratory scientific work.",
        max_width="1500px",
        sidebar_width="270px",
        hero_radius="34px 12px 34px 12px",
        card_radius="24px 10px 24px 10px",
        control_radius="16px 6px 16px 6px",
        chip_radius="999px",
        border_width="1px",
        card_padding="1.22rem",
        grid_gap="1.05rem",
        blur="24px",
        shadow="0 26px 72px rgba(30,27,75,.38)",
        hover_shadow="0 34px 86px color-mix(in srgb,var(--bio-primary) 24%,rgba(2,6,23,.44))",
        heading_tracking="-.055em",
        heading_transform="none",
        pattern_css="radial-gradient(circle at 10% 18%,color-mix(in srgb,var(--bio-primary) 20%,transparent),transparent 24%),radial-gradient(circle at 88% 12%,color-mix(in srgb,var(--bio-secondary) 18%,transparent),transparent 22%),radial-gradient(circle at 68% 88%,color-mix(in srgb,var(--bio-accent) 14%,transparent),transparent 26%)",
        surface_css="linear-gradient(135deg,color-mix(in srgb,var(--bio-surface-strong) 74%,transparent),color-mix(in srgb,var(--bio-primary) 9%,var(--bio-surface)) 56%,color-mix(in srgb,var(--bio-secondary) 7%,var(--bio-surface)))",
        hero_css="linear-gradient(125deg,color-mix(in srgb,var(--bio-primary) 26%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-secondary) 18%,var(--bio-surface-strong)) 52%,color-mix(in srgb,var(--bio-accent) 18%,var(--bio-surface-strong)))",
        button_css="linear-gradient(115deg,var(--bio-primary),var(--bio-secondary),var(--bio-accent))",
        nav_active_css="linear-gradient(105deg,color-mix(in srgb,var(--bio-primary) 28%,transparent),color-mix(in srgb,var(--bio-secondary) 16%,transparent))",
        extra_css=".bio-card:nth-child(even),.bio-kpi:nth-child(even){transform:translateY(6px)}.bio-card:hover,.bio-kpi:hover{transform:translateY(-5px) rotate(.2deg)!important}",
    ),
    "Ocean": ExperienceSpec(
        title="Oceanic Panels",
        archetype="Layered wave",
        audience="Data analysis",
        summary="Deep layered panels, wave-like sections and calm blue navigation for sustained analysis.",
        max_width="1470px",
        sidebar_width="268px",
        hero_radius="28px 28px 60px 28px",
        card_radius="18px 18px 34px 18px",
        control_radius="12px",
        chip_radius="999px",
        border_width="1px",
        card_padding="1.16rem",
        grid_gap=".9rem",
        blur="18px",
        shadow="0 24px 58px rgba(2,20,45,.36)",
        hover_shadow="0 30px 72px rgba(2,30,70,.46)",
        heading_tracking="-.04em",
        heading_transform="none",
        pattern_css="radial-gradient(ellipse at 50% -10%,color-mix(in srgb,var(--bio-secondary) 19%,transparent),transparent 42%),repeating-radial-gradient(ellipse at 50% 110%,rgba(56,189,248,.03) 0 2px,transparent 2px 38px)",
        surface_css="linear-gradient(160deg,color-mix(in srgb,var(--bio-secondary) 7%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-surface) 88%,transparent))",
        hero_css="linear-gradient(145deg,color-mix(in srgb,var(--bio-primary) 22%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-secondary) 15%,var(--bio-surface-strong)))",
        button_css="linear-gradient(100deg,var(--bio-primary),var(--bio-secondary))",
        nav_active_css="linear-gradient(90deg,color-mix(in srgb,var(--bio-secondary) 28%,transparent),transparent)",
        extra_css=".bio-hero::after{content:'';position:absolute;left:-5%;right:-5%;bottom:-34px;height:58px;border-radius:50%;background:color-mix(in srgb,var(--bio-secondary) 13%,transparent)}.bio-card,.bio-kpi{border-bottom-width:3px!important}",
    ),
    "Emerald": ExperienceSpec(
        title="Bio Organic",
        archetype="Organic biotech",
        audience="Biotechnology and assays",
        summary="Leaf-like geometry, soft depth and living-system patterns for biotechnology workflows.",
        max_width="1450px",
        sidebar_width="266px",
        hero_radius="36px 12px 36px 12px",
        card_radius="22px 8px 22px 8px",
        control_radius="14px 5px 14px 5px",
        chip_radius="999px",
        border_width="1px",
        card_padding="1.18rem",
        grid_gap=".92rem",
        blur="16px",
        shadow="0 22px 58px rgba(1,35,24,.34)",
        hover_shadow="0 28px 70px rgba(1,52,35,.46)",
        heading_tracking="-.032em",
        heading_transform="none",
        pattern_css="radial-gradient(ellipse at 8% 12%,color-mix(in srgb,var(--bio-primary) 16%,transparent),transparent 30%),radial-gradient(ellipse at 90% 84%,color-mix(in srgb,var(--bio-accent) 12%,transparent),transparent 26%)",
        surface_css="linear-gradient(145deg,color-mix(in srgb,var(--bio-primary) 8%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-surface) 90%,transparent))",
        hero_css="linear-gradient(130deg,color-mix(in srgb,var(--bio-primary) 25%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-accent) 12%,var(--bio-surface-strong)))",
        button_css="linear-gradient(110deg,var(--bio-primary),var(--bio-accent))",
        nav_active_css="linear-gradient(90deg,color-mix(in srgb,var(--bio-primary) 30%,transparent),color-mix(in srgb,var(--bio-accent) 10%,transparent))",
        extra_css=".bio-card::after,.bio-kpi::after{content:'';position:absolute;right:12px;top:12px;width:18px;height:28px;border:1px solid color-mix(in srgb,var(--bio-accent) 35%,transparent);border-radius:100% 0 100% 0;transform:rotate(22deg)}",
    ),
    "Rose": ExperienceSpec(
        title="Rose Atelier",
        archetype="Feminine professional",
        audience="Elegant presentation",
        summary="Refined rose-gold editorial workspace with graceful cards and polished scientific presentation.",
        max_width="1440px",
        sidebar_width="270px",
        hero_radius="30px",
        card_radius="22px",
        control_radius="14px",
        chip_radius="999px",
        border_width="1px",
        card_padding="1.2rem",
        grid_gap="1rem",
        blur="22px",
        shadow="0 24px 70px rgba(68,10,36,.32)",
        hover_shadow="0 32px 82px rgba(91,14,52,.42)",
        heading_tracking="-.045em",
        heading_transform="none",
        pattern_css="radial-gradient(circle at 16% 8%,color-mix(in srgb,var(--bio-primary) 18%,transparent),transparent 24%),radial-gradient(circle at 86% 26%,color-mix(in srgb,var(--bio-secondary) 14%,transparent),transparent 20%)",
        surface_css="linear-gradient(145deg,color-mix(in srgb,var(--bio-primary) 8%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-secondary) 6%,var(--bio-surface)))",
        hero_css="linear-gradient(125deg,color-mix(in srgb,var(--bio-primary) 25%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-secondary) 14%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-accent) 11%,var(--bio-surface-strong)))",
        button_css="linear-gradient(110deg,var(--bio-primary),var(--bio-secondary))",
        nav_active_css="linear-gradient(90deg,color-mix(in srgb,var(--bio-primary) 28%,transparent),color-mix(in srgb,var(--bio-secondary) 10%,transparent))",
        extra_css=".bio-hero-title{font-weight:780!important}.bio-card,.bio-kpi,.bio-db-card{outline:1px solid color-mix(in srgb,var(--bio-secondary) 12%,transparent);outline-offset:-5px}.bio-eyebrow{letter-spacing:.14em!important}",
    ),
    "Midnight Graphite": ExperienceSpec(
        title="Obsidian Executive",
        archetype="Masculine professional",
        audience="Executive and engineering",
        summary="Sharp graphite surfaces, metallic rules and powerful compact hierarchy for serious operations.",
        max_width="1510px",
        sidebar_width="286px",
        hero_radius="5px",
        card_radius="4px",
        control_radius="3px",
        chip_radius="3px",
        border_width="1px",
        card_padding="1.05rem",
        grid_gap=".68rem",
        blur="4px",
        shadow="12px 16px 0 rgba(0,0,0,.24)",
        hover_shadow="16px 20px 0 rgba(0,0,0,.32)",
        heading_tracking="-.018em",
        heading_transform="uppercase",
        pattern_css="repeating-linear-gradient(135deg,rgba(148,163,184,.025) 0 1px,transparent 1px 16px)",
        surface_css="linear-gradient(145deg,color-mix(in srgb,var(--bio-surface-strong) 98%,black),color-mix(in srgb,var(--bio-surface) 90%,black))",
        hero_css="linear-gradient(90deg,var(--bio-surface-strong),color-mix(in srgb,var(--bio-primary) 14%,var(--bio-surface-strong)))",
        button_css="linear-gradient(90deg,color-mix(in srgb,var(--bio-primary) 84%,#111827),var(--bio-primary))",
        nav_active_css="linear-gradient(90deg,var(--bio-primary) 0 5px,color-mix(in srgb,var(--bio-primary) 15%,transparent) 5px)",
        extra_css=".bio-hero,.bio-card,.bio-kpi,.bio-db-card{clip-path:polygon(0 0,calc(100% - 12px) 0,100% 12px,100% 100%,12px 100%,0 calc(100% - 12px))}.bio-gradient-text{background:none!important;color:var(--bio-text)!important}",
    ),
    "Nordic Frost": ExperienceSpec(
        title="Nordic Minimal",
        archetype="Minimalist",
        audience="Focused daily work",
        summary="Airy spacing, flat surfaces and restrained decoration for calm long-form scientific work.",
        max_width="1320px",
        sidebar_width="248px",
        hero_radius="8px",
        card_radius="8px",
        control_radius="6px",
        chip_radius="999px",
        border_width="1px",
        card_padding="1.25rem",
        grid_gap="1.25rem",
        blur="0px",
        shadow="0 6px 16px rgba(2,6,23,.10)",
        hover_shadow="0 10px 24px rgba(2,6,23,.16)",
        heading_tracking="-.025em",
        heading_transform="none",
        pattern_css="linear-gradient(180deg,color-mix(in srgb,var(--bio-secondary) 4%,transparent),transparent 38%)",
        surface_css="color-mix(in srgb,var(--bio-surface-strong) 99%,transparent)",
        hero_css="linear-gradient(180deg,color-mix(in srgb,var(--bio-secondary) 7%,var(--bio-surface-strong)),var(--bio-surface-strong))",
        button_css="var(--bio-primary)",
        nav_active_css="color-mix(in srgb,var(--bio-primary) 12%,transparent)",
        extra_css=".bio-hero::before,.bio-card::before,.bio-card::after,.bio-kpi::after,.bio-db-card::after{display:none!important}.bio-hero-title{font-weight:730!important}.bio-card:hover,.bio-kpi:hover{transform:none!important}",
    ),
    "Solarized Lab": ExperienceSpec(
        title="Scientific Editorial",
        archetype="Editorial research",
        audience="Reports and manuscripts",
        summary="Warm journal-inspired structure with editorial rules and readable long-form sections.",
        max_width="1360px",
        sidebar_width="262px",
        hero_radius="2px",
        card_radius="2px",
        control_radius="2px",
        chip_radius="2px",
        border_width="1px",
        card_padding="1.28rem",
        grid_gap="1.05rem",
        blur="0px",
        shadow="0 7px 18px rgba(2,6,23,.18)",
        hover_shadow="0 11px 24px rgba(2,6,23,.24)",
        heading_tracking="-.012em",
        heading_transform="none",
        pattern_css="repeating-linear-gradient(0deg,transparent 0 31px,rgba(245,158,11,.035) 31px 32px)",
        surface_css="linear-gradient(180deg,color-mix(in srgb,var(--bio-surface-strong) 98%,transparent),color-mix(in srgb,var(--bio-surface) 96%,transparent))",
        hero_css="linear-gradient(90deg,var(--bio-secondary) 0 6px,var(--bio-surface-strong) 6px)",
        button_css="linear-gradient(90deg,var(--bio-primary),color-mix(in srgb,var(--bio-primary) 78%,var(--bio-secondary)))",
        nav_active_css="linear-gradient(90deg,color-mix(in srgb,var(--bio-primary) 18%,transparent),transparent)",
        extra_css=".bio-hero-title{font-weight:760!important}.bio-section-label{border-bottom:1px solid color-mix(in srgb,var(--bio-secondary) 45%,transparent);padding-bottom:.45rem}.bio-card,.bio-kpi,.bio-db-card{border-top:3px double color-mix(in srgb,var(--bio-secondary) 45%,transparent)!important}",
    ),
    "Deep Space": ExperienceSpec(
        title="Modern Tech",
        archetype="Futuristic technology",
        audience="AI and modelling",
        summary="Neon technical grid, clipped corners and luminous controls for advanced computational work.",
        max_width="1530px",
        sidebar_width="288px",
        hero_radius="0px",
        card_radius="0px",
        control_radius="0px",
        chip_radius="0px",
        border_width="1px",
        card_padding="1.12rem",
        grid_gap=".72rem",
        blur="8px",
        shadow="0 0 0 1px color-mix(in srgb,var(--bio-primary) 20%,transparent),0 18px 52px rgba(2,3,18,.42)",
        hover_shadow="0 0 0 1px color-mix(in srgb,var(--bio-secondary) 55%,transparent),0 0 32px color-mix(in srgb,var(--bio-primary) 22%,transparent)",
        heading_tracking=".015em",
        heading_transform="uppercase",
        pattern_css="linear-gradient(rgba(99,102,241,.055) 1px,transparent 1px),linear-gradient(90deg,rgba(34,211,238,.045) 1px,transparent 1px)",
        surface_css="linear-gradient(135deg,color-mix(in srgb,var(--bio-primary) 7%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-surface) 94%,black))",
        hero_css="linear-gradient(110deg,color-mix(in srgb,var(--bio-primary) 20%,black),var(--bio-surface-strong) 52%,color-mix(in srgb,var(--bio-secondary) 13%,black))",
        button_css="linear-gradient(90deg,var(--bio-primary),var(--bio-secondary))",
        nav_active_css="linear-gradient(90deg,var(--bio-primary) 0 2px,color-mix(in srgb,var(--bio-primary) 18%,transparent) 2px)",
        extra_css=".bio-hero,.bio-card,.bio-kpi,.bio-db-card,[data-testid='stMetric'],[data-testid='stPlotlyChart']{clip-path:polygon(0 0,calc(100% - 16px) 0,100% 16px,100% 100%,0 100%)}.bio-hero::after{content:'SYSTEM // ACTIVE';position:absolute;right:1.2rem;bottom:.8rem;color:var(--bio-secondary);font-size:.62rem;letter-spacing:.18em}",
    ),
    "BioMatrix": ExperienceSpec(
        title="Bio Terminal",
        archetype="Scientific terminal",
        audience="Bioinformatics power users",
        summary="Dense data-terminal language with scan lines, framed metrics and command-focused controls.",
        max_width="1540px",
        sidebar_width="292px",
        hero_radius="2px",
        card_radius="2px",
        control_radius="2px",
        chip_radius="2px",
        border_width="1px",
        card_padding=".96rem",
        grid_gap=".58rem",
        blur="0px",
        shadow="0 0 22px rgba(34,197,94,.10)",
        hover_shadow="0 0 30px rgba(34,197,94,.18)",
        heading_tracking=".04em",
        heading_transform="uppercase",
        pattern_css="repeating-linear-gradient(0deg,rgba(34,197,94,.025) 0 1px,transparent 1px 4px),linear-gradient(90deg,rgba(34,197,94,.025) 1px,transparent 1px)",
        surface_css="color-mix(in srgb,var(--bio-surface-strong) 97%,black)",
        hero_css="linear-gradient(90deg,color-mix(in srgb,var(--bio-primary) 12%,black),var(--bio-surface-strong))",
        button_css="linear-gradient(90deg,color-mix(in srgb,var(--bio-primary) 78%,black),var(--bio-primary))",
        nav_active_css="linear-gradient(90deg,color-mix(in srgb,var(--bio-primary) 25%,transparent),transparent)",
        extra_css=".bio-eyebrow,.bio-kpi-label,.bio-status-chip,.bio-chip{font-family:var(--bio-data-font)!important}.bio-card,.bio-kpi,.bio-db-card{box-shadow:inset 0 0 0 1px rgba(34,197,94,.08)!important}.bio-hero-title{text-shadow:0 0 20px color-mix(in srgb,var(--bio-primary) 28%,transparent)}",
    ),
    "Royal Amethyst": ExperienceSpec(
        title="Luxury Glass",
        archetype="Luxury glassmorphism",
        audience="Premium presentations",
        summary="Layered jewel glass, luminous borders and elevated cards for executive scientific storytelling.",
        max_width="1480px",
        sidebar_width="278px",
        hero_radius="32px",
        card_radius="26px",
        control_radius="18px",
        chip_radius="999px",
        border_width="1px",
        card_padding="1.28rem",
        grid_gap="1.1rem",
        blur="34px",
        shadow="0 34px 90px rgba(31,5,52,.44)",
        hover_shadow="0 42px 110px color-mix(in srgb,var(--bio-primary) 22%,rgba(20,4,36,.54))",
        heading_tracking="-.058em",
        heading_transform="none",
        pattern_css="radial-gradient(circle at 12% 6%,color-mix(in srgb,var(--bio-primary) 22%,transparent),transparent 26%),radial-gradient(circle at 90% 24%,color-mix(in srgb,var(--bio-secondary) 18%,transparent),transparent 24%)",
        surface_css="linear-gradient(145deg,color-mix(in srgb,var(--bio-primary) 12%,transparent),color-mix(in srgb,var(--bio-surface-strong) 64%,transparent))",
        hero_css="linear-gradient(125deg,color-mix(in srgb,var(--bio-primary) 28%,transparent),color-mix(in srgb,var(--bio-secondary) 16%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-accent) 13%,transparent))",
        button_css="linear-gradient(110deg,var(--bio-primary),var(--bio-secondary),var(--bio-accent))",
        nav_active_css="linear-gradient(105deg,color-mix(in srgb,var(--bio-primary) 34%,transparent),color-mix(in srgb,var(--bio-secondary) 18%,transparent))",
        extra_css=".bio-card,.bio-kpi,.bio-db-card,.bio-hero{border-color:color-mix(in srgb,var(--bio-secondary) 28%,transparent)!important}.bio-card::before,.bio-kpi::before{content:'';position:absolute;inset:1px;border-radius:inherit;border-top:1px solid rgba(255,255,255,.25);pointer-events:none}",
    ),
    "Ember Forge": ExperienceSpec(
        title="Industrial Forge",
        archetype="Masculine industrial",
        audience="Operations and engineering",
        summary="Heavy industrial geometry, ember accents and robust controls for operational dashboards.",
        max_width="1510px",
        sidebar_width="286px",
        hero_radius="4px",
        card_radius="4px",
        control_radius="4px",
        chip_radius="4px",
        border_width="2px",
        card_padding="1.06rem",
        grid_gap=".7rem",
        blur="2px",
        shadow="0 16px 0 rgba(0,0,0,.22)",
        hover_shadow="0 20px 0 rgba(0,0,0,.30)",
        heading_tracking=".01em",
        heading_transform="uppercase",
        pattern_css="repeating-linear-gradient(135deg,rgba(249,115,22,.032) 0 2px,transparent 2px 22px)",
        surface_css="linear-gradient(135deg,color-mix(in srgb,var(--bio-surface-strong) 98%,black),color-mix(in srgb,var(--bio-primary) 5%,black))",
        hero_css="linear-gradient(90deg,var(--bio-primary) 0 8px,var(--bio-surface-strong) 8px 100%)",
        button_css="linear-gradient(90deg,var(--bio-primary),var(--bio-secondary))",
        nav_active_css="linear-gradient(90deg,var(--bio-primary) 0 5px,color-mix(in srgb,var(--bio-primary) 14%,transparent) 5px)",
        extra_css=".bio-card,.bio-kpi,.bio-db-card{border-bottom:4px solid color-mix(in srgb,var(--bio-primary) 48%,black)!important}.bio-hero-title{font-weight:950!important}.bio-chip,.bio-status-chip{border-style:dashed!important}",
    ),
    "Arctic Glass": ExperienceSpec(
        title="Pure Glass",
        archetype="Modern glass",
        audience="Modern universal",
        summary="Transparent floating layers, frosted controls and luminous cyan depth across the full interface.",
        max_width="1490px",
        sidebar_width="276px",
        hero_radius="30px",
        card_radius="24px",
        control_radius="15px",
        chip_radius="999px",
        border_width="1px",
        card_padding="1.22rem",
        grid_gap="1rem",
        blur="42px",
        shadow="0 28px 84px rgba(1,18,30,.42)",
        hover_shadow="0 36px 100px color-mix(in srgb,var(--bio-secondary) 17%,rgba(1,18,30,.52))",
        heading_tracking="-.045em",
        heading_transform="none",
        pattern_css="radial-gradient(circle at 12% 8%,color-mix(in srgb,var(--bio-secondary) 18%,transparent),transparent 28%),radial-gradient(circle at 92% 82%,color-mix(in srgb,var(--bio-accent) 13%,transparent),transparent 28%)",
        surface_css="linear-gradient(145deg,rgba(255,255,255,.075),color-mix(in srgb,var(--bio-surface-strong) 56%,transparent))",
        hero_css="linear-gradient(125deg,color-mix(in srgb,var(--bio-primary) 18%,transparent),color-mix(in srgb,var(--bio-surface-strong) 55%,transparent),color-mix(in srgb,var(--bio-secondary) 15%,transparent))",
        button_css="linear-gradient(110deg,color-mix(in srgb,var(--bio-primary) 88%,white 4%),var(--bio-secondary))",
        nav_active_css="linear-gradient(100deg,color-mix(in srgb,var(--bio-secondary) 25%,transparent),color-mix(in srgb,var(--bio-primary) 15%,transparent))",
        extra_css=".bio-card,.bio-kpi,.bio-db-card,.bio-hero,[data-testid='stMetric'],[data-testid='stPlotlyChart'],div[data-testid='stForm']{backdrop-filter:blur(42px) saturate(155%)!important;-webkit-backdrop-filter:blur(42px) saturate(155%)!important;border-color:rgba(255,255,255,.16)!important}",
    ),
    "Sakura Research": ExperienceSpec(
        title="Sakura Studio",
        archetype="Feminine modern",
        audience="Soft modern professional",
        summary="Soft structured panels, subtle floral geometry and contemporary pink-violet scientific styling.",
        max_width="1430px",
        sidebar_width="268px",
        hero_radius="26px 26px 8px 26px",
        card_radius="20px 20px 7px 20px",
        control_radius="13px 13px 5px 13px",
        chip_radius="999px",
        border_width="1px",
        card_padding="1.18rem",
        grid_gap=".96rem",
        blur="20px",
        shadow="0 24px 64px rgba(65,9,39,.30)",
        hover_shadow="0 30px 78px rgba(91,11,55,.40)",
        heading_tracking="-.04em",
        heading_transform="none",
        pattern_css="radial-gradient(circle at 14% 12%,color-mix(in srgb,var(--bio-primary) 16%,transparent),transparent 20%),radial-gradient(circle at 86% 18%,color-mix(in srgb,var(--bio-secondary) 12%,transparent),transparent 18%)",
        surface_css="linear-gradient(150deg,color-mix(in srgb,var(--bio-primary) 7%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-secondary) 5%,var(--bio-surface)))",
        hero_css="linear-gradient(130deg,color-mix(in srgb,var(--bio-primary) 22%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-secondary) 12%,var(--bio-surface-strong)))",
        button_css="linear-gradient(105deg,var(--bio-primary),var(--bio-secondary))",
        nav_active_css="linear-gradient(90deg,color-mix(in srgb,var(--bio-primary) 28%,transparent),transparent)",
        extra_css=".bio-hero::after{content:'✦';position:absolute;right:1.4rem;top:1rem;color:color-mix(in srgb,var(--bio-secondary) 70%,white);font-size:1.6rem;opacity:.72}.bio-card:nth-child(3n+1){border-top-color:color-mix(in srgb,var(--bio-secondary) 45%,transparent)!important}",
    ),
    "Monochrome Pro": ExperienceSpec(
        title="Monochrome Brutalist",
        archetype="Brutalist minimal",
        audience="Maximum restraint",
        summary="Black-and-white block system with hard hierarchy, strong typography and zero decorative colour noise.",
        max_width="1400px",
        sidebar_width="260px",
        hero_radius="0px",
        card_radius="0px",
        control_radius="0px",
        chip_radius="0px",
        border_width="2px",
        card_padding="1.12rem",
        grid_gap=".62rem",
        blur="0px",
        shadow="8px 8px 0 rgba(0,0,0,.45)",
        hover_shadow="12px 12px 0 rgba(0,0,0,.55)",
        heading_tracking="-.028em",
        heading_transform="uppercase",
        pattern_css="none",
        surface_css="var(--bio-surface-strong)",
        hero_css="linear-gradient(90deg,var(--bio-text) 0 8px,var(--bio-surface-strong) 8px)",
        button_css="var(--bio-text)",
        nav_active_css="var(--bio-text)",
        extra_css=".bio-hero,.bio-card,.bio-kpi,.bio-db-card,[data-testid='stMetric'],[data-testid='stPlotlyChart'],div[data-testid='stForm']{border-color:var(--bio-text)!important}.bio-hero-title,.bio-gradient-text{background:none!important;color:var(--bio-text)!important}[data-testid='stButton'] button[kind='primary']{color:var(--bio-bg)!important}.bio-chip,.bio-status-chip{border-color:var(--bio-text)!important}",
    ),
    'Genomic Noir': ExperienceSpec(
        title='Genome Command',
        archetype='Genomic precision',
        audience='Genomics and sequence intelligence',
        summary='Carbon laboratory geometry with teal locus markers and audit-grade hierarchy.',
        max_width='1512px',
        sidebar_width='278px',
        hero_radius='10px',
        card_radius='8px',
        control_radius='6px',
        chip_radius='6px',
        border_width='1px',
        card_padding='1.04rem',
        grid_gap='.72rem',
        blur='0px',
        shadow='0 14px 34px rgba(0,0,0,.34)',
        hover_shadow='0 20px 44px rgba(0,194,168,.15)',
        heading_tracking='-.032em',
        heading_transform='none',
        pattern_css='linear-gradient(rgba(0,194,168,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(56,189,248,.028) 1px,transparent 1px)',
        surface_css='linear-gradient(155deg,color-mix(in srgb,var(--bio-primary) 7%,var(--bio-surface-strong)),var(--bio-surface-strong))',
        hero_css='linear-gradient(110deg,color-mix(in srgb,var(--bio-primary) 20%,var(--bio-surface-strong)),var(--bio-surface-strong) 58%,color-mix(in srgb,var(--bio-secondary) 8%,var(--bio-surface-strong)))',
        button_css='linear-gradient(95deg,var(--bio-primary),color-mix(in srgb,var(--bio-primary) 70%,var(--bio-secondary)))',
        nav_active_css='linear-gradient(90deg,var(--bio-primary) 0 3px,color-mix(in srgb,var(--bio-primary) 15%,transparent) 3px)',
        extra_css=".bio-card,.bio-kpi,.bio-db-card{border-left:2px solid color-mix(in srgb,var(--bio-primary) 52%,transparent)!important}.bio-section-label:before{content:'//';color:var(--bio-primary);margin-right:.4rem}",
    ),
    'Helix Quantum': ExperienceSpec(
        title='Quantum Helix Grid',
        archetype='Quantum helix technology',
        audience='AI bioinformatics and modelling',
        summary='Angular quantum panels, helix rails and clipped computational surfaces.',
        max_width='1540px',
        sidebar_width='286px',
        hero_radius='2px',
        card_radius='2px',
        control_radius='2px',
        chip_radius='2px',
        border_width='1px',
        card_padding='1.08rem',
        grid_gap='.68rem',
        blur='4px',
        shadow='0 18px 48px rgba(3,1,20,.40)',
        hover_shadow='0 24px 60px rgba(124,58,237,.22)',
        heading_tracking='-.015em',
        heading_transform='uppercase',
        pattern_css='linear-gradient(rgba(124,58,237,.055) 1px,transparent 1px),linear-gradient(90deg,rgba(34,211,238,.045) 1px,transparent 1px)',
        surface_css='linear-gradient(135deg,color-mix(in srgb,var(--bio-primary) 9%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-secondary) 5%,var(--bio-surface)))',
        hero_css='linear-gradient(120deg,color-mix(in srgb,var(--bio-primary) 24%,black),var(--bio-surface-strong) 50%,color-mix(in srgb,var(--bio-secondary) 15%,black))',
        button_css='linear-gradient(90deg,var(--bio-primary),var(--bio-secondary))',
        nav_active_css='linear-gradient(90deg,var(--bio-primary) 0 2px,color-mix(in srgb,var(--bio-primary) 18%,transparent) 2px)',
        extra_css='.bio-hero,.bio-card,.bio-kpi,.bio-db-card{clip-path:polygon(0 0,calc(100% - 13px) 0,100% 13px,100% 100%,13px 100%,0 calc(100% - 13px))}.bio-hero-title{letter-spacing:-.025em!important}',
    ),
    'CRISPR Cyan': ExperienceSpec(
        title='CRISPR Cleanroom',
        archetype='Gene-editing cleanroom',
        audience='CRISPR and molecular design',
        summary='Sterile cyan editing surfaces with guide-track accents and low visual latency.',
        max_width='1390px',
        sidebar_width='258px',
        hero_radius='12px',
        card_radius='10px',
        control_radius='8px',
        chip_radius='999px',
        border_width='1px',
        card_padding='.98rem',
        grid_gap='.92rem',
        blur='0px',
        shadow='0 8px 20px rgba(2,20,25,.18)',
        hover_shadow='0 12px 26px rgba(6,182,212,.14)',
        heading_tracking='-.022em',
        heading_transform='none',
        pattern_css='radial-gradient(circle at 86% 8%,color-mix(in srgb,var(--bio-primary) 9%,transparent),transparent 24%)',
        surface_css='color-mix(in srgb,var(--bio-surface-strong) 98%,transparent)',
        hero_css='linear-gradient(180deg,color-mix(in srgb,var(--bio-primary) 9%,var(--bio-surface-strong)),var(--bio-surface-strong))',
        button_css='var(--bio-primary)',
        nav_active_css='color-mix(in srgb,var(--bio-primary) 14%,transparent)',
        extra_css='.bio-hero::before,.bio-card::before,.bio-card::after{display:none!important}.bio-card,.bio-kpi,.bio-db-card{box-shadow:none!important;border-top:2px solid color-mix(in srgb,var(--bio-primary) 38%,transparent)!important}',
    ),
    'Proteome Platinum': ExperienceSpec(
        title='Platinum Proteome',
        archetype='Metallic proteome executive',
        audience='Proteomics and executive review',
        summary='Metallic restrained surfaces, protein-band dividers and premium compact hierarchy.',
        max_width='1478px',
        sidebar_width='276px',
        hero_radius='7px',
        card_radius='6px',
        control_radius='5px',
        chip_radius='5px',
        border_width='1px',
        card_padding='1.06rem',
        grid_gap='.78rem',
        blur='0px',
        shadow='0 12px 30px rgba(0,0,0,.30)',
        hover_shadow='0 17px 38px rgba(148,163,184,.13)',
        heading_tracking='-.028em',
        heading_transform='none',
        pattern_css='repeating-linear-gradient(90deg,transparent 0 79px,rgba(226,232,240,.025) 79px 80px)',
        surface_css='linear-gradient(160deg,color-mix(in srgb,var(--bio-secondary) 4%,var(--bio-surface-strong)),var(--bio-surface-strong))',
        hero_css='linear-gradient(105deg,color-mix(in srgb,var(--bio-secondary) 10%,var(--bio-surface-strong)),var(--bio-surface-strong))',
        button_css='linear-gradient(90deg,var(--bio-primary),var(--bio-secondary))',
        nav_active_css='linear-gradient(90deg,color-mix(in srgb,var(--bio-secondary) 18%,transparent),transparent)',
        extra_css='.bio-card,.bio-kpi,.bio-db-card{border-top:3px double color-mix(in srgb,var(--bio-secondary) 30%,transparent)!important}.bio-eyebrow{letter-spacing:.16em!important}',
    ),
    'Cell Atlas': ExperienceSpec(
        title='Cell Atlas Mosaic',
        archetype='Cellular mosaic',
        audience='Single-cell and atlas workflows',
        summary='Rounded cellular islands, lineage markers and asymmetric atlas composition.',
        max_width='1502px',
        sidebar_width='270px',
        hero_radius='28px 12px',
        card_radius='24px 10px',
        control_radius='14px 7px',
        chip_radius='999px',
        border_width='1px',
        card_padding='1.18rem',
        grid_gap='1rem',
        blur='5px',
        shadow='0 20px 48px rgba(2,25,22,.30)',
        hover_shadow='0 27px 62px rgba(20,184,166,.17)',
        heading_tracking='-.046em',
        heading_transform='none',
        pattern_css='radial-gradient(circle at 10% 12%,color-mix(in srgb,var(--bio-primary) 13%,transparent),transparent 25%),radial-gradient(circle at 90% 18%,color-mix(in srgb,var(--bio-secondary) 10%,transparent),transparent 22%)',
        surface_css='linear-gradient(145deg,color-mix(in srgb,var(--bio-primary) 7%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-secondary) 4%,var(--bio-surface)))',
        hero_css='linear-gradient(125deg,color-mix(in srgb,var(--bio-primary) 18%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-secondary) 10%,var(--bio-surface-strong)))',
        button_css='linear-gradient(105deg,var(--bio-primary),var(--bio-secondary))',
        nav_active_css='linear-gradient(100deg,color-mix(in srgb,var(--bio-primary) 22%,transparent),color-mix(in srgb,var(--bio-secondary) 9%,transparent))',
        extra_css='.bio-board>*:nth-child(3n+2){border-radius:10px 24px 10px 24px!important}.bio-kpi-value{font-variant-numeric:tabular-nums}',
    ),
    'Neural Biotech': ExperienceSpec(
        title='Neural Bio Stack',
        archetype='Neural biotech stack',
        audience='ML, DTI and predictive biology',
        summary='Layered neural cards, model-state rails and focused blue-violet computation.',
        max_width='1532px',
        sidebar_width='284px',
        hero_radius='14px',
        card_radius='12px',
        control_radius='8px',
        chip_radius='8px',
        border_width='1px',
        card_padding='1.08rem',
        grid_gap='.74rem',
        blur='3px',
        shadow='0 18px 46px rgba(2,8,32,.36)',
        hover_shadow='0 24px 58px rgba(59,130,246,.19)',
        heading_tracking='-.035em',
        heading_transform='none',
        pattern_css='linear-gradient(rgba(59,130,246,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(139,92,246,.038) 1px,transparent 1px)',
        surface_css='linear-gradient(145deg,color-mix(in srgb,var(--bio-primary) 8%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-secondary) 5%,var(--bio-surface)))',
        hero_css='linear-gradient(112deg,color-mix(in srgb,var(--bio-primary) 20%,var(--bio-surface-strong)),var(--bio-surface-strong) 55%,color-mix(in srgb,var(--bio-secondary) 12%,var(--bio-surface-strong)))',
        button_css='linear-gradient(100deg,var(--bio-primary),var(--bio-secondary))',
        nav_active_css='linear-gradient(90deg,color-mix(in srgb,var(--bio-primary) 25%,transparent),transparent)',
        extra_css='.bio-card,.bio-kpi,.bio-db-card{box-shadow:6px 6px 0 color-mix(in srgb,var(--bio-primary) 5%,transparent),var(--bio-exp-shadow)!important}.bio-card:hover{transform:translate(-1px,-1px)!important}',
    ),
    'Quantum Enzyme': ExperienceSpec(
        title='Catalytic Ledger',
        archetype='Catalytic scientific ledger',
        audience='Enzyme kinetics and assays',
        summary='Warm catalytic ledger with rate-line dividers and editorial scientific rhythm.',
        max_width='1418px',
        sidebar_width='264px',
        hero_radius='4px',
        card_radius='3px',
        control_radius='3px',
        chip_radius='3px',
        border_width='1px',
        card_padding='1.15rem',
        grid_gap='.88rem',
        blur='0px',
        shadow='0 9px 24px rgba(20,13,2,.25)',
        hover_shadow='0 14px 30px rgba(245,158,11,.13)',
        heading_tracking='-.012em',
        heading_transform='none',
        pattern_css='repeating-linear-gradient(0deg,transparent 0 29px,rgba(245,158,11,.035) 29px 30px)',
        surface_css='linear-gradient(180deg,color-mix(in srgb,var(--bio-surface-strong) 98%,transparent),color-mix(in srgb,var(--bio-primary) 3%,var(--bio-surface)))',
        hero_css='linear-gradient(90deg,var(--bio-secondary) 0 6px,var(--bio-surface-strong) 6px)',
        button_css='linear-gradient(90deg,var(--bio-primary),var(--bio-secondary))',
        nav_active_css='linear-gradient(90deg,var(--bio-primary) 0 3px,color-mix(in srgb,var(--bio-primary) 13%,transparent) 3px)',
        extra_css='.bio-section-label{border-bottom:1px solid color-mix(in srgb,var(--bio-primary) 36%,transparent);padding-bottom:.4rem}.bio-card{border-bottom:2px solid color-mix(in srgb,var(--bio-primary) 30%,transparent)!important}',
    ),
    'Botanical Circuit': ExperienceSpec(
        title='Botanical Circuitry',
        archetype='Botanical systems design',
        audience='Plant biology and bioengineering',
        summary='Leaf-node geometry, circuit rails and organic but disciplined biotechnology panels.',
        max_width='1492px',
        sidebar_width='272px',
        hero_radius='30px 8px',
        card_radius='20px 7px',
        control_radius='12px 5px',
        chip_radius='999px',
        border_width='1px',
        card_padding='1.12rem',
        grid_gap='.86rem',
        blur='2px',
        shadow='0 16px 42px rgba(2,25,10,.31)',
        hover_shadow='0 22px 54px rgba(34,197,94,.17)',
        heading_tracking='-.038em',
        heading_transform='none',
        pattern_css='radial-gradient(ellipse at 10% 10%,color-mix(in srgb,var(--bio-secondary) 12%,transparent),transparent 27%),linear-gradient(90deg,transparent 97%,rgba(34,197,94,.035) 97%)',
        surface_css='linear-gradient(150deg,color-mix(in srgb,var(--bio-primary) 8%,var(--bio-surface-strong)),var(--bio-surface-strong))',
        hero_css='linear-gradient(130deg,color-mix(in srgb,var(--bio-primary) 21%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-secondary) 9%,var(--bio-surface-strong)))',
        button_css='linear-gradient(105deg,var(--bio-primary),var(--bio-secondary))',
        nav_active_css='linear-gradient(90deg,color-mix(in srgb,var(--bio-primary) 25%,transparent),transparent)',
        extra_css='.bio-card:nth-child(odd){border-radius:22px 7px 22px 7px!important}.bio-card:nth-child(even){border-radius:7px 22px 7px 22px!important}',
    ),
    'Clinical Sapphire': ExperienceSpec(
        title='Sapphire Clinical',
        archetype='Clinical sapphire system',
        audience='Clinical and regulated review',
        summary='Clean sapphire hierarchy, consistent table surfaces and validation-focused controls.',
        max_width='1402px',
        sidebar_width='260px',
        hero_radius='10px',
        card_radius='8px',
        control_radius='6px',
        chip_radius='999px',
        border_width='1px',
        card_padding='1rem',
        grid_gap='.94rem',
        blur='0px',
        shadow='0 8px 22px rgba(2,15,35,.17)',
        hover_shadow='0 12px 28px rgba(37,99,235,.13)',
        heading_tracking='-.019em',
        heading_transform='none',
        pattern_css='linear-gradient(180deg,color-mix(in srgb,var(--bio-primary) 4%,transparent),transparent 35%)',
        surface_css='color-mix(in srgb,var(--bio-surface-strong) 98%,transparent)',
        hero_css='linear-gradient(180deg,color-mix(in srgb,var(--bio-primary) 8%,var(--bio-surface-strong)),var(--bio-surface-strong))',
        button_css='var(--bio-primary)',
        nav_active_css='color-mix(in srgb,var(--bio-primary) 13%,transparent)',
        extra_css=".bio-card,.bio-kpi,.bio-db-card,[data-testid='stMetric']{box-shadow:none!important}.bio-card{border-left:3px solid color-mix(in srgb,var(--bio-primary) 35%,transparent)!important}",
    ),
    'Molecular Carbon': ExperienceSpec(
        title='Carbon Molecular',
        archetype='Carbon molecular brutalism',
        audience='Molecular structure and low-light work',
        summary='Hard carbon grid, sharp molecular panels and maximum-contrast analytical restraint.',
        max_width='1520px',
        sidebar_width='280px',
        hero_radius='0px',
        card_radius='0px',
        control_radius='0px',
        chip_radius='0px',
        border_width='2px',
        card_padding='1rem',
        grid_gap='0px',
        blur='0px',
        shadow='0 10px 0 rgba(255,255,255,.035)',
        hover_shadow='0 14px 0 rgba(34,211,238,.075)',
        heading_tracking='0em',
        heading_transform='uppercase',
        pattern_css='repeating-linear-gradient(0deg,rgba(255,255,255,.025) 0 1px,transparent 1px 32px)',
        surface_css='var(--bio-surface-strong)',
        hero_css='linear-gradient(90deg,var(--bio-surface-strong) 0 82%,color-mix(in srgb,var(--bio-accent) 12%,var(--bio-surface-strong)) 82%)',
        button_css='linear-gradient(90deg,var(--bio-primary),var(--bio-accent))',
        nav_active_css='linear-gradient(90deg,var(--bio-accent) 0 4px,rgba(255,255,255,.06) 4px)',
        extra_css='.bio-board,.bio-db-grid{gap:0!important}.bio-card,.bio-kpi,.bio-db-card{margin:-1px 0 0 -1px!important;box-shadow:none!important}.bio-hero-title{font-weight:800!important}',
    ),
    'Spatial Omics': ExperienceSpec(
        title='Spatial Tissue Map',
        archetype='Spatial tissue cartography',
        audience='Spatial omics and tissue analysis',
        summary='Coordinate-grid composition with tissue-region cards and layered expression zones.',
        max_width='1518px',
        sidebar_width='274px',
        hero_radius='22px 6px',
        card_radius='16px 5px',
        control_radius='10px 4px',
        chip_radius='999px',
        border_width='1px',
        card_padding='1.12rem',
        grid_gap='.8rem',
        blur='4px',
        shadow='0 19px 48px rgba(25,3,28,.34)',
        hover_shadow='0 25px 60px rgba(217,70,239,.18)',
        heading_tracking='-.043em',
        heading_transform='none',
        pattern_css='linear-gradient(rgba(217,70,239,.042) 1px,transparent 1px),linear-gradient(90deg,rgba(6,182,212,.038) 1px,transparent 1px)',
        surface_css='linear-gradient(145deg,color-mix(in srgb,var(--bio-primary) 7%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-secondary) 5%,var(--bio-surface)))',
        hero_css='linear-gradient(125deg,color-mix(in srgb,var(--bio-primary) 20%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-secondary) 11%,var(--bio-surface-strong)))',
        button_css='linear-gradient(110deg,var(--bio-primary),var(--bio-secondary),var(--bio-accent))',
        nav_active_css='linear-gradient(95deg,color-mix(in srgb,var(--bio-primary) 23%,transparent),color-mix(in srgb,var(--bio-secondary) 9%,transparent))',
        extra_css='.bio-card:nth-child(4n+1){grid-row:span 1;border-top:3px solid color-mix(in srgb,var(--bio-primary) 40%,transparent)!important}.bio-section-label{display:inline-flex!important}',
    ),
    'BioLuminescence': ExperienceSpec(
        title='Luminescent Bio Terminal',
        archetype='Bioluminescent terminal',
        audience='Bioinformatics monitoring and marine biology',
        summary='Dark bio-terminal with restrained luminous signals and scan-line data surfaces.',
        max_width='1544px',
        sidebar_width='288px',
        hero_radius='6px',
        card_radius='5px',
        control_radius='4px',
        chip_radius='4px',
        border_width='1px',
        card_padding='1.02rem',
        grid_gap='.62rem',
        blur='0px',
        shadow='0 16px 44px rgba(0,20,15,.38)',
        hover_shadow='0 21px 54px rgba(16,185,129,.19)',
        heading_tracking='-.010em',
        heading_transform='uppercase',
        pattern_css='repeating-linear-gradient(0deg,transparent 0 3px,rgba(16,185,129,.018) 3px 4px)',
        surface_css='linear-gradient(180deg,color-mix(in srgb,var(--bio-primary) 6%,var(--bio-surface-strong)),var(--bio-surface-strong))',
        hero_css='linear-gradient(100deg,color-mix(in srgb,var(--bio-primary) 19%,black),var(--bio-surface-strong))',
        button_css='linear-gradient(90deg,var(--bio-primary),var(--bio-secondary))',
        nav_active_css='linear-gradient(90deg,var(--bio-primary) 0 2px,color-mix(in srgb,var(--bio-primary) 15%,transparent) 2px)',
        extra_css='.bio-card-title,.bio-section-label,.bio-eyebrow{text-transform:uppercase;letter-spacing:.08em!important}.bio-card,.bio-kpi,.bio-db-card{outline:1px solid color-mix(in srgb,var(--bio-primary) 10%,transparent);outline-offset:-5px}',
    ),
    'Pathway Gold': ExperienceSpec(
        title='Golden Pathway Journal',
        archetype='Pathway editorial gold',
        audience='Pathway networks and scientific reports',
        summary='Journal-like pathway sections with gold rules and manuscript-friendly cards.',
        max_width='1388px',
        sidebar_width='262px',
        hero_radius='2px',
        card_radius='2px',
        control_radius='2px',
        chip_radius='2px',
        border_width='1px',
        card_padding='1.22rem',
        grid_gap='1rem',
        blur='0px',
        shadow='0 8px 20px rgba(20,14,2,.20)',
        hover_shadow='0 12px 27px rgba(212,160,23,.12)',
        heading_tracking='-.009em',
        heading_transform='none',
        pattern_css='repeating-linear-gradient(0deg,transparent 0 32px,rgba(212,160,23,.032) 32px 33px)',
        surface_css='color-mix(in srgb,var(--bio-surface-strong) 99%,transparent)',
        hero_css='linear-gradient(90deg,var(--bio-primary) 0 7px,var(--bio-surface-strong) 7px)',
        button_css='linear-gradient(90deg,var(--bio-primary),color-mix(in srgb,var(--bio-primary) 72%,var(--bio-secondary)))',
        nav_active_css='linear-gradient(90deg,color-mix(in srgb,var(--bio-primary) 17%,transparent),transparent)',
        extra_css='.bio-hero-title{font-weight:740!important}.bio-section-label{border-bottom:3px double color-mix(in srgb,var(--bio-primary) 40%,transparent);padding-bottom:.45rem}.bio-card{box-shadow:none!important}',
    ),
    'Cryo-EM Frost': ExperienceSpec(
        title='Cryo-EM Frosted Lab',
        archetype='Cryogenic structural glass',
        audience='Structural biology and cryo-EM',
        summary='Frosted structural panels with chain-track borders and restrained translucency.',
        max_width='1468px',
        sidebar_width='268px',
        hero_radius='20px',
        card_radius='16px',
        control_radius='10px',
        chip_radius='999px',
        border_width='1px',
        card_padding='1.1rem',
        grid_gap='.9rem',
        blur='6px',
        shadow='0 16px 40px rgba(2,20,30,.27)',
        hover_shadow='0 21px 52px rgba(125,211,252,.15)',
        heading_tracking='-.034em',
        heading_transform='none',
        pattern_css='radial-gradient(circle at 82% 8%,color-mix(in srgb,var(--bio-secondary) 10%,transparent),transparent 27%)',
        surface_css='linear-gradient(135deg,color-mix(in srgb,var(--bio-surface-strong) 88%,transparent),color-mix(in srgb,var(--bio-secondary) 4%,var(--bio-surface)))',
        hero_css='linear-gradient(135deg,color-mix(in srgb,var(--bio-primary) 15%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-secondary) 9%,var(--bio-surface-strong)))',
        button_css='linear-gradient(100deg,var(--bio-primary),var(--bio-secondary))',
        nav_active_css='linear-gradient(90deg,color-mix(in srgb,var(--bio-primary) 20%,transparent),transparent)',
        extra_css=".bio-card,.bio-kpi,.bio-db-card{border-bottom:2px solid color-mix(in srgb,var(--bio-secondary) 25%,transparent)!important}.bio-hero::after{content:'CRYO • STRUCTURE';position:absolute;right:1rem;bottom:.7rem;font-size:.58rem;letter-spacing:.14em;color:var(--bio-secondary)}",
    ),
    'Synthetic Biology': ExperienceSpec(
        title='Synthetic Design Studio',
        archetype='Synthetic biology atelier',
        audience='Synthetic biology and circuit design',
        summary='Circuit-studio composition with modular design cards and synthetic magenta accents.',
        max_width='1498px',
        sidebar_width='276px',
        hero_radius='26px 8px',
        card_radius='18px 6px',
        control_radius='12px 5px',
        chip_radius='999px',
        border_width='1px',
        card_padding='1.14rem',
        grid_gap='.82rem',
        blur='4px',
        shadow='0 20px 50px rgba(30,3,25,.34)',
        hover_shadow='0 26px 64px rgba(236,72,153,.18)',
        heading_tracking='-.047em',
        heading_transform='none',
        pattern_css='radial-gradient(circle at 14% 14%,color-mix(in srgb,var(--bio-primary) 14%,transparent),transparent 24%),linear-gradient(90deg,transparent 97%,rgba(139,92,246,.035) 97%)',
        surface_css='linear-gradient(140deg,color-mix(in srgb,var(--bio-primary) 7%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-secondary) 5%,var(--bio-surface)))',
        hero_css='linear-gradient(125deg,color-mix(in srgb,var(--bio-primary) 20%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-secondary) 13%,var(--bio-surface-strong)))',
        button_css='linear-gradient(110deg,var(--bio-primary),var(--bio-secondary),var(--bio-accent))',
        nav_active_css='linear-gradient(100deg,color-mix(in srgb,var(--bio-primary) 25%,transparent),color-mix(in srgb,var(--bio-secondary) 10%,transparent))',
        extra_css='.bio-board>*:first-child{grid-column:span 2}.bio-card:nth-child(4n+1){border-top:3px solid color-mix(in srgb,var(--bio-primary) 43%,transparent)!important}.bio-eyebrow{text-transform:none!important}',
    ),
}


# Step 124 maps each premium palette to a distinct full-experience geometry.
# Existing profiles are reused as audited foundations and receive a dedicated
# title/summary/finishing rule rather than falling back to Executive.
EXPERIENCES.update({
    "Genomic Aurora": replace(
        EXPERIENCES["Aurora"], title="Genomic Aurora",
        summary="Aurora helix surfaces with animated genomic depth and floating scientific glass.",
        max_width="1517px", sidebar_width="276px", hero_radius="38px 14px 38px 14px",
        card_radius="26px 12px 26px 12px", control_radius="17px 7px 17px 7px",
        shadow="0 28px 76px rgba(45,27,110,.39)",
        hero_css="linear-gradient(126deg,color-mix(in srgb,var(--bio-primary) 30%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-secondary) 20%,var(--bio-surface-strong)) 54%,color-mix(in srgb,var(--bio-accent) 20%,var(--bio-surface-strong)))",
        extra_css=EXPERIENCES["Aurora"].extra_css + ".bio-hero-scene-helix{filter:drop-shadow(0 0 24px var(--bio-glow))}",
    ),
    "Midnight Laboratory": replace(
        EXPERIENCES["Midnight Graphite"], title="Midnight Laboratory",
        summary="Low-light instrument workspace with precise laboratory surfaces and restrained motion.",
        max_width="1452px", sidebar_width="266px", hero_radius="16px 26px 16px 26px",
        card_radius="12px 20px 12px 20px", control_radius="8px",
        shadow="0 18px 46px rgba(1,10,18,.43)",
        hero_css="linear-gradient(118deg,color-mix(in srgb,var(--bio-primary) 18%,#06131f),color-mix(in srgb,var(--bio-secondary) 10%,#071824))",
    ),
    "Clinical White": replace(
        EXPERIENCES["Clinical"], title="Clinical White",
        summary="Sterile bright clinical surfaces with maximum readability and minimal decoration.",
        max_width="1368px", sidebar_width="252px", hero_radius="10px", card_radius="8px",
        control_radius="6px", card_padding="1.04rem", grid_gap="1.04rem",
        shadow="0 5px 18px rgba(14,62,70,.10)", hover_shadow="0 9px 25px rgba(14,62,70,.16)",
        hero_css="linear-gradient(180deg,color-mix(in srgb,var(--bio-primary) 6%,#ffffff),#ffffff)",
    ),
    "Molecular Glass": replace(
        EXPERIENCES["Arctic Glass"], title="Molecular Glass",
        summary="Translucent molecular layers with premium frosted depth and spectral accents.",
        max_width="1496px", sidebar_width="280px", hero_radius="30px 12px 30px 12px",
        card_radius="22px 10px 22px 10px", control_radius="14px", blur="30px",
        shadow="0 30px 82px rgba(3,39,53,.36)", hover_shadow="0 38px 96px rgba(6,182,212,.22)",
        hero_css="linear-gradient(128deg,color-mix(in srgb,var(--bio-primary) 22%,transparent),color-mix(in srgb,var(--bio-secondary) 14%,var(--bio-surface-strong)))",
    ),
    "Cyber Biotech": replace(
        EXPERIENCES["BioMatrix"], title="Cyber Biotech",
        summary="Grid-driven biotech command interface with luminous workflow states and technical density.",
        max_width="1564px", sidebar_width="294px", hero_radius="4px 24px 4px 24px",
        card_radius="3px 16px 3px 16px", control_radius="3px", chip_radius="3px",
        border_width="2px", grid_gap=".62rem", shadow="0 20px 54px rgba(0,245,160,.16)",
        hero_css="linear-gradient(110deg,color-mix(in srgb,var(--bio-primary) 22%,#02120d),#031d17 58%,color-mix(in srgb,var(--bio-secondary) 12%,#02120d))",
    ),
    "Oceanic Research": replace(
        EXPERIENCES["Ocean"], title="Oceanic Research",
        summary="Calm layered research panels for sustained scientific exploration.",
        max_width="1486px", sidebar_width="272px", hero_radius="34px 34px 72px 34px",
        card_radius="20px 20px 42px 20px", control_radius="13px", grid_gap=".94rem",
        shadow="0 26px 66px rgba(1,35,64,.40)",
        hero_css="linear-gradient(150deg,color-mix(in srgb,var(--bio-primary) 24%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-secondary) 18%,var(--bio-surface-strong)))",
    ),
    "Cellular Green": replace(
        EXPERIENCES["Emerald"], title="Cellular Green",
        summary="Organic cellular surfaces for microscopy, assays and biological analysis.",
        max_width="1438px", sidebar_width="264px", hero_radius="28px 18px 28px 18px",
        card_radius="18px 12px 18px 12px", control_radius="12px", chip_radius="999px",
        blur="15px", shadow="0 20px 54px rgba(3,60,30,.31)",
        hero_css="radial-gradient(circle at 82% 18%,color-mix(in srgb,var(--bio-secondary) 18%,transparent),transparent 30%),linear-gradient(132deg,color-mix(in srgb,var(--bio-primary) 19%,var(--bio-surface-strong)),var(--bio-surface-strong))",
    ),
    "Protein Violet": replace(
        EXPERIENCES["Royal Amethyst"], title="Protein Violet",
        summary="Violet protein-ribbon presentation language for structure and design workflows.",
        max_width="1528px", sidebar_width="284px", hero_radius="42px 12px 20px 12px",
        card_radius="24px 8px 18px 8px", control_radius="15px 6px 15px 6px",
        blur="26px", shadow="0 30px 84px rgba(71,27,120,.40)",
        hero_css="linear-gradient(124deg,color-mix(in srgb,var(--bio-primary) 28%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-secondary) 18%,var(--bio-surface-strong)) 60%,color-mix(in srgb,var(--bio-accent) 13%,var(--bio-surface-strong)))",
    ),
    "Minimal Scientific": replace(
        EXPERIENCES["Clinical"], title="Minimal Scientific",
        summary="Publication-oriented scientific workspace with crisp hierarchy and low decoration.",
        max_width="1326px", sidebar_width="246px", card_radius="6px", hero_radius="8px",
        control_radius="5px", chip_radius="5px", border_width="1px", card_padding=".92rem",
        grid_gap="1.12rem", blur="0px", shadow="0 4px 16px rgba(2,6,23,.10)",
        hover_shadow="0 8px 22px rgba(2,6,23,.16)",
        hero_css="linear-gradient(180deg,var(--bio-surface-strong),color-mix(in srgb,var(--bio-primary) 3%,var(--bio-surface-strong)))",
    ),
    "High-Contrast Research": replace(
        EXPERIENCES["Monochrome Pro"], title="High-Contrast Research",
        summary="Accessibility-first scientific interface with maximum contrast and non-colour status cues.",
        max_width="1406px", sidebar_width="288px", hero_radius="0px", card_radius="0px",
        control_radius="0px", chip_radius="0px", border_width="2px", grid_gap=".5rem",
        shadow="6px 6px 0 rgba(255,214,10,.22)", hover_shadow="9px 9px 0 rgba(0,229,255,.24)",
        hero_css="linear-gradient(90deg,#000 0 8px,color-mix(in srgb,var(--bio-primary) 12%,#000) 8px)",
    ),
})


# Unique semantic archetypes keep the theme catalogue auditable and ensure the
# ten premium additions are not merely colour aliases.
for _premium_name, _premium_archetype in {
    "Genomic Aurora": "Aurora genomic helix",
    "Midnight Laboratory": "Midnight instrument laboratory",
    "Clinical White": "Sterile clinical white",
    "Molecular Glass": "Spectral molecular glass",
    "Cyber Biotech": "Cyber biotechnology grid",
    "Oceanic Research": "Oceanic research layers",
    "Cellular Green": "Cellular organic microscopy",
    "Protein Violet": "Violet protein ribbon",
    "Minimal Scientific": "Publication scientific minimal",
    "High-Contrast Research": "Accessible high-contrast research",
}.items():
    EXPERIENCES[_premium_name] = replace(EXPERIENCES[_premium_name], archetype=_premium_archetype)

# Step 126 artistic experience profiles. They alter geometry, materials,
# background art and interaction language in addition to colour tokens.
EXPERIENCES.update({
    "Lavender Genome": replace(
        EXPERIENCES["Royal Amethyst"], title="Lavender Genome",
        archetype="Lavender genomic atelier", audience="Universal aesthetic",
        summary="Pearl lavender glass, organic genomic curves and calm floating depth for extended research sessions.",
        max_width="1492px", sidebar_width="274px", hero_radius="38px 18px 38px 18px",
        card_radius="24px 14px 24px 14px", control_radius="16px", chip_radius="999px",
        blur="27px", shadow="0 30px 82px rgba(43,28,91,.37)",
        hover_shadow="0 40px 104px color-mix(in srgb,var(--bio-primary) 24%,rgba(31,18,69,.55))",
        pattern_css="radial-gradient(circle at 14% 8%,color-mix(in srgb,var(--bio-primary) 19%,transparent),transparent 27%),radial-gradient(circle at 88% 32%,color-mix(in srgb,var(--bio-secondary) 15%,transparent),transparent 23%),repeating-radial-gradient(ellipse at 50% 120%,transparent 0 39px,color-mix(in srgb,var(--bio-secondary) 3%,transparent) 40px 41px)",
        hero_css="linear-gradient(127deg,color-mix(in srgb,var(--bio-primary) 26%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-secondary) 17%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-accent) 10%,var(--bio-surface-strong)))",
        extra_css=EXPERIENCES["Royal Amethyst"].extra_css + ".bio-hero{border-top-color:color-mix(in srgb,var(--bio-secondary) 45%,white 4%)!important}.bio-hero-scene{filter:drop-shadow(0 0 22px color-mix(in srgb,var(--bio-primary) 38%,transparent))}.bio-card::after{content:'';position:absolute;inset:auto 18% -1px 18%;height:1px;background:linear-gradient(90deg,transparent,var(--bio-secondary),transparent);opacity:.44}",
    ),
    "Rose Quartz Laboratory": replace(
        EXPERIENCES["Sakura Research"], title="Rose Quartz Laboratory",
        archetype="Rose quartz laboratory glass", audience="Universal aesthetic",
        summary="Blush crystal surfaces, pearl borders and delicate cellular line art without compromising scientific readability.",
        max_width="1468px", sidebar_width="268px", hero_radius="34px",
        card_radius="22px", control_radius="15px", chip_radius="999px", blur="25px",
        shadow="0 28px 74px rgba(76,34,59,.34)", hover_shadow="0 38px 96px rgba(231,167,196,.22)",
        pattern_css="radial-gradient(circle at 12% 14%,color-mix(in srgb,var(--bio-primary) 17%,transparent),transparent 22%),radial-gradient(circle at 82% 8%,color-mix(in srgb,var(--bio-secondary) 12%,transparent),transparent 25%),linear-gradient(125deg,transparent 0 48%,color-mix(in srgb,var(--bio-primary) 3%,transparent) 49% 50%,transparent 51%)",
        surface_css="linear-gradient(145deg,color-mix(in srgb,var(--bio-primary) 10%,transparent),color-mix(in srgb,var(--bio-surface-strong) 72%,transparent))",
        hero_css="linear-gradient(132deg,color-mix(in srgb,var(--bio-primary) 24%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-secondary) 18%,var(--bio-surface-strong)) 56%,color-mix(in srgb,var(--bio-accent) 12%,var(--bio-surface-strong)))",
        extra_css=EXPERIENCES["Sakura Research"].extra_css + ".bio-card,.bio-kpi,.bio-db-card{border-color:color-mix(in srgb,var(--bio-primary) 25%,rgba(255,255,255,.18))!important}.bio-hero::after{content:'◇';position:absolute;right:1.4rem;bottom:.7rem;color:color-mix(in srgb,var(--bio-secondary) 70%,white);font-size:2rem;opacity:.36}",
    ),
    "Emerald Muse": replace(
        EXPERIENCES["Emerald"], title="Emerald Muse",
        archetype="Emerald botanical molecular atelier", audience="Universal aesthetic",
        summary="Organic emerald layers, botanical molecular marks and controlled gold evidence accents.",
        max_width="1454px", sidebar_width="270px", hero_radius="30px 12px 30px 12px",
        card_radius="20px 10px 20px 10px", control_radius="13px", chip_radius="999px",
        blur="17px", shadow="0 25px 68px rgba(3,51,35,.36)", hover_shadow="0 34px 84px rgba(95,209,161,.21)",
        pattern_css="radial-gradient(ellipse at 9% 6%,color-mix(in srgb,var(--bio-primary) 15%,transparent),transparent 27%),repeating-linear-gradient(115deg,transparent 0 48px,color-mix(in srgb,var(--bio-accent) 3.2%,transparent) 49px 50px)",
        hero_css="radial-gradient(circle at 82% 18%,color-mix(in srgb,var(--bio-accent) 14%,transparent),transparent 27%),linear-gradient(130deg,color-mix(in srgb,var(--bio-primary) 22%,var(--bio-surface-strong)),var(--bio-surface-strong))",
        button_css="linear-gradient(105deg,var(--bio-primary),color-mix(in srgb,var(--bio-primary) 62%,var(--bio-accent)))",
        extra_css=EXPERIENCES["Emerald"].extra_css + ".bio-eyebrow,.bio-status-chip{border-color:color-mix(in srgb,var(--bio-accent) 45%,transparent)!important}.bio-card:nth-child(3n+1){border-top:2px solid color-mix(in srgb,var(--bio-accent) 45%,transparent)!important}",
    ),
    "Bronze Anatomy": replace(
        EXPERIENCES["Solarized Lab"], title="Bronze Anatomy",
        archetype="Bronze anatomical sketchbook", audience="Universal art",
        summary="Museum-like bronze surfaces, anatomical sketch lines and sepia drafting texture for scientific storytelling.",
        max_width="1418px", sidebar_width="270px", hero_radius="6px",
        card_radius="4px", control_radius="3px", chip_radius="3px", border_width="1px",
        blur="0px", shadow="0 14px 30px rgba(15,9,4,.34)", hover_shadow="0 20px 42px rgba(185,133,78,.23)",
        heading_tracking="-.008em", heading_transform="none",
        pattern_css="repeating-linear-gradient(0deg,transparent 0 30px,color-mix(in srgb,var(--bio-secondary) 3.4%,transparent) 31px 32px),repeating-linear-gradient(90deg,transparent 0 30px,color-mix(in srgb,var(--bio-primary) 2.8%,transparent) 31px 32px)",
        surface_css="linear-gradient(155deg,color-mix(in srgb,var(--bio-surface-strong) 96%,#3b291b),color-mix(in srgb,var(--bio-primary) 5%,#20160f))",
        hero_css="linear-gradient(90deg,var(--bio-primary) 0 5px,color-mix(in srgb,var(--bio-surface-strong) 94%,#3b291b) 5px)",
        button_css="linear-gradient(90deg,var(--bio-primary),var(--bio-secondary))",
        extra_css=EXPERIENCES["Solarized Lab"].extra_css + ".bio-hero::after{content:'ANATOMIA • SCIENTIA';position:absolute;right:1.2rem;bottom:.75rem;font-family:var(--bio-data-font);font-size:.58rem;letter-spacing:.18em;color:var(--bio-secondary);opacity:.58}.bio-card,.bio-kpi,.bio-db-card{border-style:double!important}.bio-section-label::before{content:'§ ';color:var(--bio-primary)}",
    ),
    "Obsidian Engineering": replace(
        EXPERIENCES["Ember Forge"], title="Obsidian Engineering",
        archetype="Obsidian scientific engineering", audience="Universal art",
        summary="Matte obsidian panels, steel geometry and blueprint signals for operational scientific work.",
        max_width="1540px", sidebar_width="292px", hero_radius="2px 20px 2px 20px",
        card_radius="2px 12px 2px 12px", control_radius="2px", chip_radius="2px", border_width="1px",
        blur="3px", shadow="0 18px 0 rgba(0,0,0,.25),0 24px 60px rgba(0,0,0,.34)",
        hover_shadow="0 23px 0 rgba(0,0,0,.32),0 32px 78px rgba(59,130,246,.17)",
        pattern_css="linear-gradient(rgba(110,131,154,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(110,131,154,.045) 1px,transparent 1px),repeating-linear-gradient(135deg,transparent 0 42px,rgba(59,130,246,.025) 43px 44px)",
        surface_css="linear-gradient(135deg,color-mix(in srgb,var(--bio-surface-strong) 98%,black),color-mix(in srgb,var(--bio-primary) 5%,black))",
        hero_css="linear-gradient(90deg,var(--bio-primary) 0 6px,color-mix(in srgb,var(--bio-surface-strong) 94%,black) 6px 100%)",
        button_css="linear-gradient(90deg,var(--bio-primary),var(--bio-secondary))",
        nav_active_css="linear-gradient(90deg,var(--bio-primary) 0 4px,color-mix(in srgb,var(--bio-primary) 16%,transparent) 4px)",
        extra_css=EXPERIENCES["Ember Forge"].extra_css + ".bio-hero,.bio-card,.bio-kpi,.bio-db-card{clip-path:polygon(0 0,calc(100% - 13px) 0,100% 13px,100% 100%,0 100%)}.bio-hero::after{content:'ENG // VERIFIED';position:absolute;right:1rem;bottom:.7rem;color:var(--bio-secondary);font-size:.58rem;letter-spacing:.15em}",
    ),
    "Ink & Blueprint": replace(
        EXPERIENCES["Deep Space"], title="Ink & Blueprint",
        archetype="Ink technical blueprint", audience="Universal art",
        summary="Drafting-grid structure, ink linework and measured scientific geometry with a restrained orange annotation accent.",
        max_width="1510px", sidebar_width="286px", hero_radius="0px",
        card_radius="0px", control_radius="0px", chip_radius="0px", border_width="1px",
        blur="2px", shadow="0 18px 46px rgba(2,10,25,.39)", hover_shadow="0 26px 64px rgba(40,120,200,.24)",
        heading_tracking=".012em", heading_transform="uppercase",
        pattern_css="linear-gradient(rgba(101,183,232,.065) 1px,transparent 1px),linear-gradient(90deg,rgba(101,183,232,.065) 1px,transparent 1px),linear-gradient(rgba(101,183,232,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(101,183,232,.025) 1px,transparent 1px)",
        surface_css="linear-gradient(135deg,color-mix(in srgb,var(--bio-primary) 8%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-surface) 95%,#071324))",
        hero_css="linear-gradient(112deg,color-mix(in srgb,var(--bio-primary) 18%,#08172b),color-mix(in srgb,var(--bio-secondary) 8%,#0b1c33))",
        button_css="linear-gradient(90deg,var(--bio-primary),var(--bio-secondary))",
        nav_active_css="linear-gradient(90deg,var(--bio-primary) 0 2px,color-mix(in srgb,var(--bio-primary) 17%,transparent) 2px)",
        extra_css=EXPERIENCES["Deep Space"].extra_css + ".bio-hero::after{content:'SCALE 1:1  •  BIOINTEL DRAFT';position:absolute;right:1rem;bottom:.65rem;color:var(--bio-accent);font-family:var(--bio-data-font);font-size:.54rem;letter-spacing:.13em}.bio-card::after,.bio-kpi::after{content:'+';position:absolute;right:7px;top:3px;color:var(--bio-secondary);font-size:.75rem;opacity:.55}",
    ),
})


# Step 148 six bold colour experiences. Geometry, materials, background motifs
# and interaction language are intentionally unique—not colour-only aliases.
EXPERIENCES.update({
    "Solar Helix": ExperienceSpec(
        title="Solar Helix", archetype="Solar kinetic helix", audience="Bold scientific presentations",
        summary="Radiant yellow energy bands, carbon surfaces and cyan telemetry for striking research dashboards.",
        max_width="1522px", sidebar_width="280px", hero_radius="28px 6px 28px 6px",
        card_radius="18px 5px 18px 5px", control_radius="12px 4px", chip_radius="999px",
        border_width="1px", card_padding="1.12rem", grid_gap=".78rem", blur="8px",
        shadow="0 24px 66px rgba(14,10,0,.46)", hover_shadow="0 32px 86px rgba(255,214,10,.20)",
        heading_tracking="-.041em", heading_transform="none",
        pattern_css="repeating-linear-gradient(118deg,transparent 0 52px,rgba(255,214,10,.045) 53px 54px),radial-gradient(circle at 88% 10%,rgba(255,214,10,.16),transparent 24%)",
        surface_css="linear-gradient(145deg,color-mix(in srgb,var(--bio-primary) 8%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-surface) 94%,black))",
        hero_css="linear-gradient(116deg,color-mix(in srgb,var(--bio-primary) 27%,#151000),color-mix(in srgb,var(--bio-secondary) 16%,var(--bio-surface-strong)) 58%,color-mix(in srgb,var(--bio-accent) 9%,var(--bio-surface-strong)))",
        button_css="linear-gradient(100deg,var(--bio-primary),var(--bio-secondary))",
        nav_active_css="linear-gradient(90deg,var(--bio-primary) 0 5px,color-mix(in srgb,var(--bio-primary) 19%,transparent) 5px)",
        extra_css=".bio-hero::after{content:'SOLAR // ACTIVE';position:absolute;right:1.1rem;bottom:.7rem;color:var(--bio-primary);font-size:.58rem;letter-spacing:.16em}.bio-card:nth-child(3n+1){border-top:2px solid color-mix(in srgb,var(--bio-primary) 52%,transparent)!important}",
    ),
    "Black Diamond": ExperienceSpec(
        title="Black Diamond", archetype="Faceted black diamond", audience="Luxury low-light research",
        summary="True-black faceted panels, platinum edges and restrained ice-blue scientific signals.",
        max_width="1488px", sidebar_width="286px", hero_radius="2px 26px 2px 26px",
        card_radius="2px 18px 2px 18px", control_radius="2px 10px 2px 10px", chip_radius="2px",
        border_width="1px", card_padding="1.08rem", grid_gap=".72rem", blur="3px",
        shadow="0 22px 0 rgba(0,0,0,.46),0 30px 82px rgba(0,0,0,.58)", hover_shadow="0 28px 0 rgba(0,0,0,.55),0 40px 100px rgba(56,189,248,.14)",
        heading_tracking=".006em", heading_transform="uppercase",
        pattern_css="linear-gradient(135deg,rgba(255,255,255,.026) 0 1px,transparent 1px 50%),linear-gradient(45deg,rgba(56,189,248,.02) 0 1px,transparent 1px 50%)",
        surface_css="linear-gradient(135deg,#07080a,color-mix(in srgb,var(--bio-surface-strong) 96%,#171a1f))",
        hero_css="linear-gradient(128deg,#020203 0%,#1b1e24 46%,#050607 70%,color-mix(in srgb,var(--bio-accent) 8%,#020203))",
        button_css="linear-gradient(90deg,#F8FAFC,#9CA3AF)",
        nav_active_css="linear-gradient(90deg,#F8FAFC 0 3px,rgba(248,250,252,.10) 3px)",
        extra_css=".bio-hero,.bio-card,.bio-kpi,.bio-db-card{clip-path:polygon(0 0,calc(100% - 18px) 0,100% 18px,100% 100%,18px 100%,0 calc(100% - 18px))}.bio-gradient-text{background:none!important;color:#fff!important}.bio-hero::after{content:'◆';position:absolute;right:1.2rem;bottom:.55rem;color:var(--bio-accent);font-size:1.8rem;opacity:.34}",
    ),
    "Crimson Genome": ExperienceSpec(
        title="Crimson Genome", archetype="Crimson genomic pulse", audience="Critical scientific review",
        summary="Crimson pulse tracks, asymmetric genomic surfaces and warm-gold evidence markers.",
        max_width="1536px", sidebar_width="282px", hero_radius="8px 34px 8px 34px",
        card_radius="7px 22px 7px 22px", control_radius="6px 14px 6px 14px", chip_radius="999px",
        border_width="1px", card_padding="1.13rem", grid_gap=".74rem", blur="10px",
        shadow="0 26px 72px rgba(52,2,10,.43)", hover_shadow="0 36px 94px rgba(239,35,60,.22)",
        heading_tracking="-.032em", heading_transform="none",
        pattern_css="repeating-linear-gradient(90deg,transparent 0 70px,rgba(239,35,60,.038) 71px 72px),linear-gradient(0deg,transparent 49%,rgba(255,77,109,.04) 50%,transparent 51%)",
        surface_css="linear-gradient(138deg,color-mix(in srgb,var(--bio-primary) 9%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-secondary) 4%,var(--bio-surface)))",
        hero_css="linear-gradient(102deg,var(--bio-primary) 0 6px,color-mix(in srgb,var(--bio-primary) 21%,var(--bio-surface-strong)) 6px 42%,color-mix(in srgb,var(--bio-secondary) 13%,var(--bio-surface-strong)))",
        button_css="linear-gradient(100deg,var(--bio-primary),var(--bio-secondary))",
        nav_active_css="linear-gradient(90deg,var(--bio-primary) 0 4px,color-mix(in srgb,var(--bio-primary) 18%,transparent) 4px)",
        extra_css=".bio-card::after,.bio-kpi::after{content:'';position:absolute;left:12%;right:12%;bottom:-1px;height:1px;background:linear-gradient(90deg,transparent,var(--bio-primary),transparent);opacity:.55}.bio-hero::after{content:'GENOME • PULSE';position:absolute;right:1rem;bottom:.72rem;color:var(--bio-accent);font-size:.57rem;letter-spacing:.15em}",
    ),
    "Electric Lime": ExperienceSpec(
        title="Electric Lime", archetype="Electric lime circuit", audience="Technical bioinformatics operations",
        summary="Neon lime circuit traces, compact technical panels and cyan live-state telemetry.",
        max_width="1572px", sidebar_width="296px", hero_radius="0px",
        card_radius="0px 14px 0px 14px", control_radius="0px 8px 0px 8px", chip_radius="0px",
        border_width="1px", card_padding="1.02rem", grid_gap=".60rem", blur="4px",
        shadow="0 0 0 1px rgba(183,255,0,.09),0 20px 58px rgba(0,0,0,.44)", hover_shadow="0 0 0 1px rgba(0,229,255,.44),0 0 38px rgba(183,255,0,.18)",
        heading_tracking=".018em", heading_transform="uppercase",
        pattern_css="linear-gradient(rgba(183,255,0,.052) 1px,transparent 1px),linear-gradient(90deg,rgba(0,229,255,.042) 1px,transparent 1px)",
        surface_css="linear-gradient(135deg,color-mix(in srgb,var(--bio-primary) 7%,#081004),color-mix(in srgb,var(--bio-surface-strong) 96%,black))",
        hero_css="linear-gradient(110deg,color-mix(in srgb,var(--bio-primary) 19%,#061003),#0b1704 56%,color-mix(in srgb,var(--bio-accent) 12%,#061003))",
        button_css="linear-gradient(90deg,var(--bio-primary),var(--bio-secondary))",
        nav_active_css="linear-gradient(90deg,var(--bio-primary) 0 2px,color-mix(in srgb,var(--bio-primary) 17%,transparent) 2px)",
        extra_css=".bio-hero,.bio-card,.bio-kpi,.bio-db-card{clip-path:polygon(0 0,calc(100% - 12px) 0,100% 12px,100% 100%,0 100%)}.bio-hero::after{content:'CIRCUIT // LIVE';position:absolute;right:1rem;bottom:.65rem;color:var(--bio-accent);font-family:var(--bio-data-font);font-size:.56rem;letter-spacing:.16em}",
    ),
    "Velvet Neon": ExperienceSpec(
        title="Velvet Neon", archetype="Velvet neon scientific lounge", audience="Creative discovery and presentations",
        summary="Soft velvet-black depth, neon magenta glass and cyan highlights with luxurious rounded geometry.",
        max_width="1506px", sidebar_width="278px", hero_radius="44px 18px 44px 18px",
        card_radius="28px 12px 28px 12px", control_radius="18px", chip_radius="999px",
        border_width="1px", card_padding="1.18rem", grid_gap=".88rem", blur="30px",
        shadow="0 34px 92px rgba(45,3,53,.44)", hover_shadow="0 46px 118px rgba(255,43,214,.23)",
        heading_tracking="-.052em", heading_transform="none",
        pattern_css="radial-gradient(circle at 14% 8%,rgba(255,43,214,.18),transparent 26%),radial-gradient(circle at 86% 22%,rgba(34,211,238,.11),transparent 24%)",
        surface_css="linear-gradient(145deg,color-mix(in srgb,var(--bio-primary) 11%,transparent),color-mix(in srgb,var(--bio-surface-strong) 76%,transparent))",
        hero_css="linear-gradient(130deg,color-mix(in srgb,var(--bio-primary) 28%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-secondary) 20%,var(--bio-surface-strong)) 58%,color-mix(in srgb,var(--bio-accent) 12%,var(--bio-surface-strong)))",
        button_css="linear-gradient(105deg,var(--bio-primary),var(--bio-secondary),var(--bio-accent))",
        nav_active_css="linear-gradient(95deg,color-mix(in srgb,var(--bio-primary) 24%,transparent),color-mix(in srgb,var(--bio-secondary) 10%,transparent))",
        extra_css=".bio-card,.bio-kpi,.bio-db-card{border-color:color-mix(in srgb,var(--bio-primary) 22%,rgba(255,255,255,.12))!important}.bio-card::after{content:'';position:absolute;inset:auto 20% -1px 20%;height:1px;background:linear-gradient(90deg,transparent,var(--bio-accent),transparent);opacity:.55}",
    ),
    "Copper Eclipse": ExperienceSpec(
        title="Copper Eclipse", archetype="Copper eclipse scientific atelier", audience="Scientific storytelling and reports",
        summary="Metallic copper layers, eclipse rings and turquoise analytical accents for sophisticated research narratives.",
        max_width="1436px", sidebar_width="272px", hero_radius="50% 10px 10px 10px / 28px 10px 10px 10px",
        card_radius="20px 6px 20px 6px", control_radius="12px 4px 12px 4px", chip_radius="999px",
        border_width="1px", card_padding="1.22rem", grid_gap="1.02rem", blur="9px",
        shadow="0 24px 64px rgba(30,12,5,.42)", hover_shadow="0 34px 84px rgba(217,119,69,.22)",
        heading_tracking="-.015em", heading_transform="none",
        pattern_css="radial-gradient(circle at 88% 10%,transparent 0 52px,rgba(217,119,69,.075) 53px 55px,transparent 56px),repeating-linear-gradient(0deg,transparent 0 33px,rgba(242,166,90,.028) 34px 35px)",
        surface_css="linear-gradient(155deg,color-mix(in srgb,var(--bio-primary) 8%,var(--bio-surface-strong)),color-mix(in srgb,var(--bio-surface) 96%,#150b07))",
        hero_css="radial-gradient(circle at 84% 24%,color-mix(in srgb,var(--bio-accent) 14%,transparent),transparent 27%),linear-gradient(125deg,color-mix(in srgb,var(--bio-primary) 22%,var(--bio-surface-strong)),var(--bio-surface-strong))",
        button_css="linear-gradient(95deg,var(--bio-primary),var(--bio-secondary))",
        nav_active_css="linear-gradient(90deg,color-mix(in srgb,var(--bio-primary) 22%,transparent),transparent)",
        extra_css=".bio-section-label{border-bottom:1px solid color-mix(in srgb,var(--bio-primary) 40%,transparent);padding-bottom:.42rem}.bio-hero::after{content:'ECLIPSE • RESEARCH';position:absolute;right:1rem;bottom:.7rem;color:var(--bio-accent);font-size:.56rem;letter-spacing:.14em}",
    ),
})



def experience_for(theme_name: str) -> ExperienceSpec:
    return EXPERIENCES.get(theme_name, EXPERIENCES["Executive"])


@lru_cache(maxsize=128)
def experience_theme_css(
    palette: ThemeSpec,
    *,
    appearance_mode: str = "Dark",
    compact: bool = False,
    reduce_motion: bool = False,
) -> str:
    """Return a desktop-only complete visual-language override for a theme."""

    spec = experience_for(palette.name)
    light = light_theme_for(palette.name)
    button_foreground = theme_button_foreground(palette)
    layout_css = layout_archetype_css(palette.name)
    card_padding = ".86rem" if compact else spec.card_padding
    grid_gap = ".56rem" if compact else spec.grid_gap
    motion = (
        "transition:none!important;animation:none!important"
        if reduce_motion
        else "transition:transform var(--motion-normal) var(--ease-standard),box-shadow var(--motion-normal) var(--ease-standard),border-color var(--motion-fast) var(--ease-standard),background var(--motion-normal) var(--ease-standard)"
    )
    reduced_rules = (
        """
        .bio-card:hover,.bio-kpi:hover,.bio-db-card:hover,[data-testid='stMetric']:hover,
        [data-testid='stButton'] button:hover,[data-testid='stDownloadButton'] button:hover,
        [data-testid='stButton'] button:active,[data-testid='stDownloadButton'] button:active,
        [data-testid='stFormSubmitButton'] button:active {
          transform:none!important;animation:none!important;
        }
        """
        if reduce_motion
        else ""
    )
    light_rules = dedent(
        f"""
        .stApp,[data-testid="stAppViewContainer"] {{
          background-image:{spec.pattern_css},linear-gradient(145deg,{light.background},{light.background_soft} 52%,{light.background})!important;
        }}
        [data-testid="stSidebar"] {{
          background:linear-gradient(180deg,{light.sidebar_start},{light.sidebar_end})!important;
        }}
        .bio-hero {{
          background:linear-gradient(125deg,color-mix(in srgb,var(--bio-primary) 9%,{light.surface_strong}),{light.surface_strong},color-mix(in srgb,var(--bio-secondary) 7%,{light.surface_strong}))!important;
          box-shadow:0 18px 48px rgba(15,23,42,.10)!important;
        }}
        .bio-card,.bio-kpi,.bio-db-card,.bio-surface,.bio-insight,.bio-command-bar,
        .bio-professional-strip,[data-testid="stMetric"],[data-testid="stPlotlyChart"],
        [data-testid="stDataFrame"],[data-testid="stTable"],div[data-testid="stForm"],
        [data-testid="stExpander"] {{
          background:linear-gradient(145deg,{light.surface_strong},color-mix(in srgb,var(--bio-primary) 2.5%,{light.surface}))!important;
          border-color:{light.border}!important;
          box-shadow:0 12px 34px rgba(15,23,42,.09)!important;
        }}
        .bio-hero-title,.bio-gradient-text,.bio-card-title,.bio-kpi-value,.bio-db-title,
        .bio-section-label,.bio-empty-title {{ color:{light.text}!important;background:none!important; }}
        .bio-hero-subtitle,.bio-card-copy,.bio-kpi-copy,.bio-db-copy,.bio-theme-copy {{ color:{light.muted}!important; }}
        .bio-chip,.bio-status-chip,.bio-workspace-context span {{
          color:{light.text}!important;background:{light.surface}!important;border-color:{light.border}!important;
        }}
        [data-testid="stButton"] button[kind="primary"],
        [data-testid="stFormSubmitButton"] button[kind="primary"] {{ color:{button_foreground}!important; }}
        """
    )
    if palette.name == "Monochrome Pro":
        light_rules += dedent(
            """
            [data-testid="stButton"] button[kind="primary"],
            [data-testid="stFormSubmitButton"] button[kind="primary"] {
              color:#FFFFFF!important;background:#111827!important;
            }
            .bio-hero,.bio-card,.bio-kpi,.bio-db-card,[data-testid="stMetric"],
            [data-testid="stPlotlyChart"],div[data-testid="stForm"] { border-color:#111827!important; }
            """
        )
    if appearance_mode == "Light":
        appearance_rules = light_rules
    elif appearance_mode == "System":
        appearance_rules = f"@media (prefers-color-scheme: light) {{\n{light_rules}\n}}"
    else:
        appearance_rules = ""
    return dedent(
        f"""
        <style id="biointel-experience-theme-v67">
        @media (min-width: 761px) {{
          :root {{
            --bio-exp-max-width:{spec.max_width};
            --bio-exp-sidebar-width:{spec.sidebar_width};
            --bio-exp-hero-radius:{spec.hero_radius};
            --bio-exp-card-radius:{spec.card_radius};
            --bio-exp-control-radius:{spec.control_radius};
            --bio-exp-chip-radius:{spec.chip_radius};
            --bio-exp-border-width:{spec.border_width};
            --bio-exp-card-padding:{card_padding};
            --bio-exp-grid-gap:{grid_gap};
            --bio-exp-blur:{spec.blur};
            --bio-exp-shadow:{spec.shadow};
            --bio-exp-hover-shadow:{spec.hover_shadow};
          }}

          .stApp,[data-testid="stAppViewContainer"] {{
            background-image:{spec.pattern_css},linear-gradient(145deg,{palette.bg_start},{palette.bg_mid} 48%,{palette.bg_end})!important;
            background-size:56px 56px,auto!important;
            background-attachment:fixed!important;
          }}
          .stApp::after {{ opacity:.12!important; }}
          .main .block-container {{ max-width:var(--bio-exp-max-width)!important; }}
          [data-testid="stSidebar"] {{
            min-width:var(--bio-exp-sidebar-width)!important;
            max-width:var(--bio-exp-sidebar-width)!important;
            backdrop-filter:blur(var(--bio-exp-blur)) saturate(145%)!important;
            -webkit-backdrop-filter:blur(var(--bio-exp-blur)) saturate(145%)!important;
          }}

          h1,h2,h3,.bio-hero-title,.bio-card-title,.bio-kpi-value,.bio-db-title {{
            letter-spacing:{spec.heading_tracking}!important;
            text-transform:{spec.heading_transform};
          }}

          .bio-hero {{
            border-radius:var(--bio-exp-hero-radius)!important;
            border-width:var(--bio-exp-border-width)!important;
            background:{spec.hero_css}!important;
            box-shadow:var(--bio-exp-shadow)!important;
            backdrop-filter:blur(var(--bio-exp-blur)) saturate(145%)!important;
            -webkit-backdrop-filter:blur(var(--bio-exp-blur)) saturate(145%)!important;
          }}

          .bio-card,.bio-kpi,.bio-db-card,.bio-surface,.bio-insight,.bio-command-bar,
          .bio-professional-strip,[data-testid="stMetric"],[data-testid="stPlotlyChart"],
          [data-testid="stDataFrame"],[data-testid="stTable"],div[data-testid="stForm"],
          [data-testid="stExpander"] {{
            position:relative;
            border-radius:var(--bio-exp-card-radius)!important;
            border-width:var(--bio-exp-border-width)!important;
            background:{spec.surface_css}!important;
            box-shadow:var(--bio-exp-shadow)!important;
            backdrop-filter:blur(var(--bio-exp-blur)) saturate(135%)!important;
            -webkit-backdrop-filter:blur(var(--bio-exp-blur)) saturate(135%)!important;
            {motion};
          }}
          .bio-card,.bio-kpi,.bio-db-card {{ padding:var(--bio-exp-card-padding)!important; }}
          .bio-board,.bio-db-grid,.bio-theme-grid,.bio-font-grid {{ gap:var(--bio-exp-grid-gap)!important; }}
          .bio-card:hover,.bio-kpi:hover,.bio-db-card:hover,[data-testid="stMetric"]:hover {{
            transform:translateY(calc(var(--motion-hover-lift) * -1));
            box-shadow:var(--bio-exp-hover-shadow)!important;
            border-color:color-mix(in srgb,var(--bio-secondary) 42%,transparent)!important;
          }}
          [data-testid="stPlotlyChart"],[data-testid="stPlotlyChart"]:hover {{
            transform:none!important;
          }}

          [data-testid="stButton"] button,[data-testid="stDownloadButton"] button,
          [data-testid="stFormSubmitButton"] button {{
            border-radius:var(--bio-exp-control-radius)!important;
            {motion};
          }}
          [data-testid="stButton"] button[kind="primary"],
          [data-testid="stFormSubmitButton"] button[kind="primary"] {{
            background:{spec.button_css}!important;
            color:{button_foreground}!important;
            box-shadow:0 10px 28px var(--bio-glow)!important;
            border-color:color-mix(in srgb,var(--bio-secondary) 28%,transparent)!important;
          }}
          [data-testid="stButton"] button:hover,[data-testid="stDownloadButton"] button:hover {{
            transform:translateY(calc(var(--motion-hover-lift) * -.5));
          }}
          [data-testid="stButton"] button:active,[data-testid="stDownloadButton"] button:active,
          [data-testid="stFormSubmitButton"] button:active {{
            transform:translateY(1px) scale(.992);
          }}
          [data-baseweb="input"] > div,[data-baseweb="select"] > div,
          [data-testid="stTextArea"] textarea,[data-testid="stNumberInput"] input,
          [data-testid="stDateInput"] input,[data-testid="stTimeInput"] input {{
            border-radius:var(--bio-exp-control-radius)!important;
          }}
          .bio-chip,.bio-status-chip,.bio-eyebrow,.bio-workspace-context span,
          [data-baseweb="tag"] {{ border-radius:var(--bio-exp-chip-radius)!important; }}

          [data-testid="stSidebar"] [data-testid="stPageLink"] a {{
            border-radius:var(--bio-exp-control-radius)!important;
          }}
          [data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] {{
            background:{spec.nav_active_css}!important;
            box-shadow:0 8px 24px color-mix(in srgb,var(--bio-primary) 16%,transparent)!important;
          }}
          [data-baseweb="tab-list"] {{
            border-radius:var(--bio-exp-control-radius)!important;
            padding:.2rem!important;
          }}
          [data-baseweb="tab"] {{ border-radius:var(--bio-exp-control-radius)!important; }}
          [data-testid="stDataFrame"] {{ border-radius:var(--bio-exp-card-radius)!important; }}
          [data-testid="stDataFrame"] [role="columnheader"] {{
            background:color-mix(in srgb,var(--bio-primary) 10%,var(--bio-surface-strong))!important;
          }}
          [data-testid="stSlider"] [role="slider"] {{
            background:var(--bio-primary)!important;
            border:2px solid color-mix(in srgb,var(--bio-secondary) 62%,white 8%)!important;
            box-shadow:0 4px 16px var(--bio-glow)!important;
          }}
          [data-testid="stToggle"] [role="switch"],
          [data-testid="stCheckbox"] span,[data-testid="stRadio"] span {{
            border-radius:var(--bio-exp-control-radius)!important;
          }}
          [data-testid="stFileUploaderDropzone"], [data-testid="stPopoverBody"],
          [data-testid="stDialog"], [data-testid="stToast"], [data-testid="stAlert"],
          [data-testid="stStatusWidget"], [data-testid="stCodeBlock"], [data-testid="stProgress"] {{
            border-radius:var(--bio-exp-card-radius)!important;
            border-color:color-mix(in srgb,var(--bio-primary) 25%,var(--bio-border))!important;
          }}
          [data-testid="stProgress"] > div > div {{
            background:linear-gradient(90deg,var(--bio-primary),var(--bio-secondary))!important;
          }}
          [data-testid="stToast"] {{
            background:{spec.surface_css}!important;
            box-shadow:var(--bio-exp-shadow)!important;
          }}

          {spec.extra_css}
          {layout_css}
          {reduced_rules}
          {appearance_rules}
        }}
        </style>
        """
    )
