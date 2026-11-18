from __future__ import annotations

from pathlib import Path
from typing import Any

import html

import pandas as pd
import streamlit as st

from .models import utc_now
from .news_ui import render_live_news
from .service import SciencePulseService
from biointel.ui.theme import hero, section_title


PRIMARY_NAVIGATION = (
    "Overview",
    "Live Science News",
    "Publications",
    "Preprints",
    "Datasets & Protocols",
    "Trials & Regulatory",
    "Grants & Funding",
    "Patents & Translation",
    "Conferences & Events",
    "Databases & Tool Updates",
    "Canvas Studio",
    "Trends & Intelligence",
    "Saved Library",
    "Alerts",
    "Sources & Operations",
)


NAVIGATION_GROUPS: dict[str, tuple[str, ...]] = {
    "Command": ("Overview", "Live Science News", "Trends & Intelligence"),
    "Evidence": ("Publications", "Preprints", "Datasets & Protocols", "Trials & Regulatory"),
    "Opportunities": ("Grants & Funding", "Patents & Translation", "Conferences & Events", "Databases & Tool Updates"),
    "Workspace": ("Canvas Studio", "Saved Library", "Alerts"),
    "Operations": ("Sources & Operations",),
}

NAVIGATION_SYMBOLS: dict[str, str] = {
    "Overview": "01",
    "Live Science News": "LIVE",
    "Publications": "PUB",
    "Preprints": "PRE",
    "Datasets & Protocols": "DATA",
    "Trials & Regulatory": "TRIAL",
    "Grants & Funding": "GRANT",
    "Patents & Translation": "IP",
    "Conferences & Events": "EVENT",
    "Databases & Tool Updates": "TOOLS",
    "Canvas Studio": "CANVAS",
    "Trends & Intelligence": "TREND",
    "Saved Library": "SAVED",
    "Alerts": "ALERT",
    "Sources & Operations": "OPS",
}

SECTION_META: dict[str, tuple[str, str]] = {
    "Overview": ("Command center", "A single view of live intelligence, evidence, canvases and monitoring health."),
    "Live Science News": ("Live intelligence", "Source-aware biology and biotechnology reporting with provenance and evidence links."),
    "Publications": ("Evidence library", "Peer-reviewed publication metadata, identifiers and stored source provenance."),
    "Preprints": ("Early research", "Preprint discovery with explicit non-peer-reviewed labelling and provenance."),
    "Datasets & Protocols": ("Research assets", "Datasets, protocols and reproducibility-oriented scientific resources."),
    "Trials & Regulatory": ("Clinical intelligence", "Trial and regulatory records persisted from approved scientific providers."),
    "Grants & Funding": ("Opportunity intelligence", "Funding records and opportunity tracking from configured sources."),
    "Patents & Translation": ("Translation intelligence", "Patents, technology transfer and translational research signals."),
    "Conferences & Events": ("Scientific calendar", "Conference and scientific-event records from approved providers."),
    "Databases & Tool Updates": ("Tool watch", "Database releases, software updates and scientific infrastructure changes."),
    "Canvas Studio": ("Visual workspace", "Evidence-linked planning boards, timelines, graphs and governance-ready exports."),
    "Trends & Intelligence": ("Research analytics", "Persisted topic momentum and evidence-bounded digest generation."),
    "Saved Library": ("Personal library", "Bookmarked scientific records retained in the local-first workspace."),
    "Alerts": ("Monitoring center", "Topic rules, delivery preferences and a local scientific notification inbox."),
    "Sources & Operations": ("Source operations", "Provider health, approval state, synchronization and verification controls."),
}

SECTION_RULES: dict[str, dict[str, str]] = {
    "Publications": {"content_type": "publication", "empty": "No journal publication is available from the configured providers yet."},
    "Preprints": {"content_type": "preprint", "empty": "No preprint is available from the configured repositories yet."},
    "Datasets & Protocols": {"content_type": "dataset", "empty": "No dataset or protocol record is available from the configured providers yet."},
    "Trials & Regulatory": {"content_type": "clinical_trial", "empty": "No trial or regulatory record is available from the configured providers yet."},
    "Grants & Funding": {"category": "funding", "empty": "No grants provider is configured. Persisted funding records will appear here after source approval."},
    "Patents & Translation": {"category": "patent", "empty": "No patents provider is configured. Persisted translation records will appear here after source approval."},
    "Conferences & Events": {"category": "conference", "empty": "No conference provider is configured. This section does not invent event listings."},
    "Databases & Tool Updates": {"category": "database", "empty": "No database or tool-release record matches the current persisted source data."},
}


def _service(root: str) -> SciencePulseService:
    return SciencePulseService(Path(root))


def _source(item: dict[str, Any]) -> str:
    return str(item.get("source_name") or item.get("provider_key") or "Unknown source")


def _date(value: Any) -> str:
    return str(value or "date unavailable").replace("T", " ").replace("Z", " UTC")



def _inject_science_plus_theme() -> None:
    """Layer a complete Science Plus product surface onto the active BioIntel theme."""

    st.markdown(
        """
        <style>
        .science-plus-hero {
            position:relative;isolation:isolate;overflow:hidden;
            padding:clamp(1.2rem,2.4vw,1.8rem);margin:.35rem 0 1rem;
            border:1px solid color-mix(in srgb,var(--bio-primary) 24%,var(--bio-border));
            border-radius:var(--bio-radius-xl);
            background:
                radial-gradient(circle at 88% 16%,color-mix(in srgb,var(--bio-primary) 30%,transparent),transparent 25%),
                radial-gradient(circle at 14% 112%,color-mix(in srgb,var(--bio-secondary) 19%,transparent),transparent 38%),
                linear-gradient(135deg,color-mix(in srgb,var(--bio-surface-strong) 96%,transparent),color-mix(in srgb,var(--bio-surface) 84%,var(--bio-primary) 16%));
            box-shadow:var(--bio-shadow);
        }
        .science-plus-hero::after {
            content:"";position:absolute;z-index:-1;width:340px;height:340px;right:-150px;bottom:-215px;border-radius:50%;
            border:42px solid color-mix(in srgb,var(--bio-primary) 13%,transparent);
            box-shadow:0 0 0 28px color-mix(in srgb,var(--bio-secondary) 8%,transparent),0 0 0 58px color-mix(in srgb,var(--bio-accent) 5%,transparent);
        }
        .science-plus-eyebrow,.science-plus-kicker {color:var(--bio-primary);font-size:.72rem;font-weight:900;letter-spacing:.15em;text-transform:uppercase;}
        .science-plus-hero h2 {max-width:960px;margin:.45rem 0 0;color:var(--bio-text);font-size:clamp(1.65rem,2.8vw,2.6rem);line-height:1.05;letter-spacing:-.04em;}
        .science-plus-hero p {max-width:1040px;margin:.65rem 0 0;color:var(--bio-muted);font-size:.96rem;line-height:1.65;}
        .science-plus-stat-grid {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.7rem;margin:1rem 0 0;}
        .science-plus-stat {min-height:84px;padding:.76rem .86rem;border:1px solid var(--bio-border);border-radius:var(--bio-radius-lg);background:linear-gradient(145deg,color-mix(in srgb,var(--bio-surface-strong) 87%,transparent),color-mix(in srgb,var(--bio-surface) 73%,transparent));box-shadow:inset 0 1px 0 color-mix(in srgb,white 6%,transparent);}
        .science-plus-stat strong {display:block;color:var(--bio-text);font-size:1.18rem;line-height:1.1;}
        .science-plus-stat span {display:block;margin-top:.24rem;color:var(--bio-muted);font-size:.73rem;}
        .science-plus-chip-row {display:flex;flex-wrap:wrap;gap:.46rem;margin-top:.85rem;}
        .science-plus-chip {display:inline-flex;align-items:center;min-height:28px;padding:.3rem .62rem;border:1px solid color-mix(in srgb,var(--bio-primary) 30%,var(--bio-border));border-radius:999px;color:var(--bio-text);background:color-mix(in srgb,var(--bio-surface-strong) 76%,transparent);font-size:.72rem;font-weight:760;}
        .science-plus-command-deck {margin:.2rem 0 .85rem;padding:.86rem;border:1px solid color-mix(in srgb,var(--bio-primary) 26%,var(--bio-border));border-radius:var(--bio-radius-xl);background:linear-gradient(135deg,color-mix(in srgb,var(--bio-surface-strong) 93%,transparent),color-mix(in srgb,var(--bio-surface) 82%,transparent));box-shadow:0 16px 38px color-mix(in srgb,black 20%,transparent);}
        .science-plus-command-head {display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap;margin-bottom:.68rem;padding:.05rem .08rem .62rem;border-bottom:1px solid var(--bio-border);}
        .science-plus-command-title {color:var(--bio-text);font-size:.98rem;font-weight:850;}
        .science-plus-command-copy {margin-top:.16rem;color:var(--bio-muted);font-size:.72rem;line-height:1.45;}
        .science-plus-path {display:inline-flex;align-items:center;gap:.36rem;padding:.3rem .56rem;border-radius:999px;color:var(--bio-text);background:color-mix(in srgb,var(--bio-primary) 10%,transparent);border:1px solid color-mix(in srgb,var(--bio-primary) 30%,var(--bio-border));font-size:.7rem;font-weight:800;}
        .science-plus-toolbar {display:grid;grid-template-columns:minmax(260px,1.65fr) repeat(4,minmax(110px,1fr));gap:.65rem;margin:.15rem 0 1rem;}
        .science-plus-toolbar-card {position:relative;overflow:hidden;min-height:92px;padding:.78rem .88rem;border:1px solid var(--bio-border);border-radius:var(--bio-radius-lg);background:linear-gradient(145deg,color-mix(in srgb,var(--bio-surface-strong) 91%,transparent),color-mix(in srgb,var(--bio-surface) 78%,transparent));box-shadow:0 11px 30px color-mix(in srgb,black 21%,transparent);}
        .science-plus-toolbar-card::before {content:"";position:absolute;inset:0 auto 0 0;width:3px;background:linear-gradient(var(--bio-primary),var(--bio-secondary));}
        .science-plus-toolbar-card b {display:block;color:var(--bio-text);font-size:.96rem;line-height:1.2;}
        .science-plus-toolbar-card span {display:block;margin-top:.2rem;color:var(--bio-muted);font-size:.71rem;line-height:1.42;}
        .science-plus-live-strip {display:flex;align-items:center;justify-content:space-between;gap:.8rem;flex-wrap:wrap;margin:.3rem 0 .75rem;padding:.68rem .82rem;border:1px solid var(--bio-border);border-radius:var(--bio-radius-lg);background:color-mix(in srgb,var(--bio-surface) 78%,transparent);}
        .science-plus-live-main {display:flex;align-items:center;gap:.62rem;color:var(--bio-text);font-weight:800;}
        .science-plus-live-dot {width:.65rem;height:.65rem;border-radius:999px;background:var(--bio-primary);box-shadow:0 0 0 .28rem color-mix(in srgb,var(--bio-primary) 13%,transparent);}
        .science-plus-live-dot.is-live {background:#39d98a;box-shadow:0 0 0 .28rem rgba(57,217,138,.13),0 0 18px rgba(57,217,138,.35);}
        .science-plus-live-meta {color:var(--bio-muted);font-size:.72rem;line-height:1.45;}
        .science-plus-workflow {display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.62rem;margin:.72rem 0 1.05rem;}
        .science-plus-step {min-height:82px;padding:.72rem .8rem;border:1px solid var(--bio-border);border-radius:var(--bio-radius-lg);background:color-mix(in srgb,var(--bio-surface) 78%,transparent);}
        .science-plus-step b {display:block;color:var(--bio-text);font-size:.84rem;}
        .science-plus-step span {display:block;margin-top:.18rem;color:var(--bio-muted);font-size:.7rem;line-height:1.42;}
        .science-plus-quick-card {min-height:124px;}
        .science-plus-quick-card h3 {margin:.36rem 0 .28rem;color:var(--bio-text);font-size:1rem;}
        .science-plus-quick-card p {min-height:44px;margin:0 0 .65rem;color:var(--bio-muted);font-size:.75rem;line-height:1.48;}
        .science-plus-card-index {display:inline-flex;align-items:center;justify-content:center;min-width:2rem;height:1.55rem;padding:0 .42rem;border-radius:8px;color:var(--bio-text);font-size:.64rem;font-weight:900;letter-spacing:.05em;border:1px solid color-mix(in srgb,var(--bio-primary) 34%,var(--bio-border));background:color-mix(in srgb,var(--bio-primary) 10%,transparent);}
        .science-plus-news-title {margin:.44rem 0 .2rem;color:var(--bio-text);font-size:1.18rem;font-weight:860;line-height:1.25;letter-spacing:-.018em;}
        .science-plus-news-meta {color:var(--bio-muted);font-size:.72rem;line-height:1.52;}
        .science-plus-filter-summary {display:flex;flex-wrap:wrap;gap:.42rem;margin:.2rem 0 .75rem;}
        .science-plus-callout,.science-plus-empty {margin:.72rem 0 .9rem;padding:.84rem .92rem;border:1px solid var(--bio-border);border-radius:var(--bio-radius-lg);color:var(--bio-text);background:linear-gradient(135deg,color-mix(in srgb,var(--bio-primary) 9%,var(--bio-surface)),color-mix(in srgb,var(--bio-secondary) 6%,var(--bio-surface)));}
        .science-plus-empty {border-style:dashed;}
        .science-plus-empty b {display:block;margin-bottom:.24rem;color:var(--bio-text);font-size:1rem;}
        .science-plus-empty span,.science-plus-subtle {color:var(--bio-muted);font-size:.8rem;}
        .science-plus-nav-card {min-height:68px;padding:.72rem .82rem;border:1px solid var(--bio-border);border-radius:var(--bio-radius-lg);background:linear-gradient(145deg,color-mix(in srgb,var(--bio-surface-strong) 92%,transparent),color-mix(in srgb,var(--bio-surface) 78%,transparent));}
        .science-plus-nav-card strong {display:block;color:var(--bio-text);font-size:.9rem;}
        .science-plus-nav-card span {display:block;margin-top:.16rem;color:var(--bio-muted);font-size:.7rem;line-height:1.4;}
        .science-plus-canvas-context {display:grid;grid-template-columns:minmax(240px,1.7fr) repeat(3,minmax(100px,1fr));gap:.62rem;margin:.3rem 0 .8rem;padding:.72rem;border:1px solid var(--bio-border);border-radius:var(--bio-radius-xl);background:color-mix(in srgb,var(--bio-surface) 78%,transparent);}
        .science-plus-canvas-context>div {padding:.62rem .68rem;border-radius:12px;background:color-mix(in srgb,var(--bio-surface-strong) 75%,transparent);}
        .science-plus-canvas-context strong {display:block;color:var(--bio-text);font-size:.88rem;}
        .science-plus-canvas-context span {display:block;margin-top:.15rem;color:var(--bio-muted);font-size:.68rem;line-height:1.4;}
        div[data-testid="stSegmentedControl"] {margin-bottom:.25rem;}
        :where(button,a,input,textarea,select,[tabindex]):focus-visible {outline:3px solid var(--bio-primary)!important;outline-offset:3px!important;}
        @media (max-width:1180px) {.science-plus-toolbar{grid-template-columns:repeat(2,minmax(0,1fr));}.science-plus-toolbar-card:first-child{grid-column:1/-1;}.science-plus-stat-grid,.science-plus-workflow{grid-template-columns:repeat(2,minmax(0,1fr));}.science-plus-canvas-context{grid-template-columns:repeat(2,minmax(0,1fr));}.science-plus-canvas-context>div:first-child{grid-column:1/-1;}}
        @media (max-width:680px) {.science-plus-toolbar,.science-plus-stat-grid,.science-plus-workflow,.science-plus-canvas-context{grid-template-columns:1fr;}.science-plus-hero{padding:1.05rem;border-radius:20px;}.science-plus-command-deck{padding:.68rem;border-radius:18px;}.science-plus-canvas-context>div:first-child{grid-column:auto;}}
        @media (prefers-reduced-motion:reduce) {.science-plus-live-dot{box-shadow:none;}}
        </style>
        """,
        unsafe_allow_html=True,
    )



def _set_section(section: str, *, tenant_id: str, user_id: str) -> None:
    st.session_state[f"sp-primary-navigation-pending-{tenant_id}-{user_id}"] = section
    st.session_state[f"sp-navigation-group-{tenant_id}-{user_id}"] = _section_group(section)
    st.rerun()


def _section_group(section: str) -> str:
    for group, entries in NAVIGATION_GROUPS.items():
        if section in entries:
            return group
    return "Command"


def _render_workspace_navigation(*, tenant_id: str, user_id: str, nav_key: str) -> str:
    current = str(st.session_state.get(nav_key) or "Live Science News")
    if current not in PRIMARY_NAVIGATION:
        current = "Live Science News"
        st.session_state[nav_key] = current
    group_key = f"sp-navigation-group-{tenant_id}-{user_id}"
    current_group = _section_group(current)
    group_default = current_group if group_key not in st.session_state else None

    st.markdown('<div class="science-plus-kicker">Workspace families</div>', unsafe_allow_html=True)
    selected_group = st.segmented_control(
        "Science Plus workspace family",
        tuple(NAVIGATION_GROUPS),
        key=group_key,
        default=group_default,
        label_visibility="collapsed",
        width="stretch",
    ) or current_group
    entries = NAVIGATION_GROUPS[str(selected_group)]
    if current not in entries:
        current = entries[0]
        st.session_state[nav_key] = current

    title, copy = SECTION_META[current]
    st.markdown(
        f"""
        <section class="science-plus-command-deck">
            <div class="science-plus-command-head">
                <div>
                    <div class="science-plus-kicker">Workspace command deck</div>
                    <div class="science-plus-command-title">{html.escape(title)}</div>
                    <div class="science-plus-command-copy">{html.escape(copy)}</div>
                </div>
                <div class="science-plus-path">Science Plus · {html.escape(str(selected_group))} · {html.escape(current)}</div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    section = st.selectbox(
        "Workspace surface",
        entries,
        key=nav_key,
        format_func=lambda value: f"{NAVIGATION_SYMBOLS.get(str(value), 'VIEW')}  ·  {value}",
        label_visibility="collapsed",
    )
    return str(section)


def _section_toolbar(section: str, *, status: dict[str, Any], saved_canvases: int, records: int) -> None:
    state = str(status.get("state") or "OFFLINE")
    title, copy = SECTION_META.get(section, ("Science Plus", "Evidence-aware intelligence workspace."))
    live_class = " is-live" if state == "LIVE" else ""
    st.markdown(
        f"""
        <div class="science-plus-live-strip">
            <div class="science-plus-live-main">
                <span class="science-plus-live-dot{live_class}"></span>
                <span>{html.escape(title)} · {html.escape(section)}</span>
            </div>
            <div class="science-plus-live-meta">
                {html.escape(copy)}<br/>
                {html.escape(state)} feed · {int(status.get('live_count') or 0)} live stories ·
                {saved_canvases} saved canvases · {records} scientific records
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def _quick_navigation_grid(*, tenant_id: str, user_id: str) -> None:
    st.markdown('<div class="science-plus-kicker">Priority workspaces</div>', unsafe_allow_html=True)
    action_cards = [
        ("LIVE", "Live Science News", "Track current biology reporting with source-aware filters and provenance.", "Open live feed", "Live Science News", ":material/newspaper:"),
        ("PUB", "Publications", "Browse journal records, source identifiers and evidence metadata.", "Open publications", "Publications", ":material/library_books:"),
        ("CANVAS", "Canvas Studio", "Build visual scientific plans and link them to persisted evidence.", "Open Canvas Studio", "Canvas Studio", ":material/space_dashboard:"),
        ("ALERT", "Alerts", "Create topic watches, delivery rules and digest workflows.", "Open monitoring", "Alerts", ":material/notifications_active:"),
    ]
    cols = st.columns(len(action_cards))
    for col, (index, title, desc, cta, section, icon) in zip(cols, action_cards):
        with col.container(border=True):
            st.markdown(
                f'<div class="science-plus-quick-card"><span class="science-plus-card-index">{html.escape(index)}</span><h3>{html.escape(title)}</h3><p>{html.escape(desc)}</p></div>',
                unsafe_allow_html=True,
            )
            if st.button(cta,key=f"sp-nav-quick-{section}-{tenant_id}-{user_id}",width="stretch",icon=icon):
                _set_section(section, tenant_id=tenant_id, user_id=user_id)

def _overview_workflow_strip() -> None:
    steps = [
        ("Discover", "Scan live science news, publications and preprints."),
        ("Screen", "Filter by source, region, evidence and topic."),
        ("Map", "Link records into structured scientific canvases."),
        ("Review", "Check provenance, quality and blockers."),
        ("Export", "Share JSON, Markdown and table outputs."),
    ]
    html_steps = ''.join(
        f'<div class="science-plus-step"><b>{html.escape(title)}</b><span>{html.escape(detail)}</span></div>'
        for title, detail in steps
    )
    st.markdown('<div class="science-plus-workflow">' + html_steps + '</div>', unsafe_allow_html=True)


def _science_plus_hero(title: str, subtitle: str, *, eyebrow: str = "Science Plus", stats: list[tuple[str, str]] | None = None, chips: list[str] | None = None) -> None:
    stat_html = ""
    if stats:
        stat_html = '<div class="science-plus-stat-grid">' + ''.join(
            f'<div class="science-plus-stat"><strong>{html.escape(value)}</strong><span>{html.escape(label)}</span></div>'
            for label, value in stats
        ) + '</div>'
    chip_html = ""
    if chips:
        chip_html = '<div class="science-plus-chip-row">' + ''.join(
            f'<span class="science-plus-chip">{html.escape(chip)}</span>' for chip in chips if chip
        ) + '</div>'
    st.markdown(
        f"""
        <section class="science-plus-hero">
            <div class="science-plus-eyebrow">{html.escape(eyebrow)}</div>
            <h2>{html.escape(title)}</h2>
            <p>{html.escape(subtitle)}</p>
            {stat_html}
            {chip_html}
        </section>
        """,
        unsafe_allow_html=True,
    )


def _scientific_card(
    service: SciencePulseService,
    item: dict[str, Any],
    *,
    user_id: str,
    tenant_id: str,
    suffix: str,
) -> None:
    with st.container(border=True):
        badges = st.container(horizontal=True)
        with badges:
            st.badge(str(item.get("content_type") or "record").replace("_", " ").upper(), color="blue")
            st.badge(str(item.get("live_state") or "CACHED"), color="green")
            if str(item.get("trust_state") or "normal") != "normal":
                st.badge("CORRECTION / RETRACTION NOTICE", color="red")
        st.markdown(f"### {item.get('title') or 'Untitled scientific record'}")
        st.caption(f"{_source(item)} · {_date(item.get('published_at'))} · provider: {item.get('provider_key') or 'not supplied'}")
        if item.get("authors"):
            st.caption("Authors: " + ", ".join(str(value) for value in item["authors"][:10]))
        if item.get("abstract"):
            excerpt = str(item["abstract"])
            st.write(excerpt[:650] + ("…" if len(excerpt) > 650 else ""))
        identifiers = [
            f"DOI: {item['doi']}" if item.get("doi") else "",
            f"PMID: {item['pmid']}" if item.get("pmid") else "",
            f"PMCID: {item['pmcid']}" if item.get("pmcid") else "",
        ]
        if any(identifiers):
            st.caption(" · ".join(value for value in identifiers if value))
        actions = st.container(horizontal=True)
        with actions:
            if item.get("canonical_url"):
                st.link_button("Open original record", str(item["canonical_url"]), icon=":material/open_in_new:")
            if st.button("Save", key=f"sp-record-save-{suffix}-{item['item_id']}", icon=":material/bookmark:"):
                saved = service.store.toggle_bookmark(user_id, str(item["item_id"]), tenant_id=tenant_id)
                st.toast("Saved to library." if saved else "Removed from library.")
                st.rerun()
            if st.button("Ask Shiro", key=f"sp-record-shiro-{suffix}-{item['item_id']}"):
                result = service.perform_contextual_action(
                    str(item["item_id"]), user_id=user_id, action_key="ask_shiro", tenant_id=tenant_id
                )
                st.success(f"Evidence-summary draft {result['integration_id']} persisted for approval.")


def _content_section(
    service: SciencePulseService,
    title: str,
    *,
    user_id: str,
    tenant_id: str,
    saved: bool = False,
) -> None:
    rule = SECTION_RULES.get(title, {})
    preview_rows = service.store.search_items("", tenant_id=tenant_id, content_type=rule.get("content_type", ""), category=rule.get("category", ""), saved_by=user_id if saved else "", limit=50)
    preview_rows = [row for row in preview_rows if str(row.get("live_state")) != "DEMO"]
    _science_plus_hero(
        title,
        rule.get("empty") or "Source-aware scientific records, filters and evidence-aware browsing.",
        eyebrow="Science Plus Library",
        stats=[("Records", str(len(preview_rows))), ("Saved", str(sum(1 for row in preview_rows if row.get("is_saved"))))],
        chips=["Source-aware", "Stored provenance", "Local-first workspace"],
    )
    query = st.text_input(
        f"Search {title.lower()}",
        placeholder="Title, abstract, author, gene, disease or identifier",
        key=f"sp-section-search-{title}-{tenant_id}-{user_id}",
    )
    rows = service.store.search_items(
        query,
        tenant_id=tenant_id,
        content_type=rule.get("content_type", ""),
        category=rule.get("category", ""),
        saved_by=user_id if saved else "",
        limit=50,
    )
    rows = [row for row in rows if str(row.get("live_state")) != "DEMO"]
    if title == "Preprints":
        st.info("Preprints are not peer-reviewed unless an explicit peer-reviewed match is supplied in provenance.")
    if not rows:
        st.info(rule.get("empty") or "No persisted scientific record matches this view.")
        return
    st.caption(f"Showing {len(rows)} persisted record(s). No demo records are included.")
    for index, row in enumerate(rows):
        _scientific_card(service, row, user_id=user_id, tenant_id=tenant_id, suffix=f"{title}-{index}")


def _overview(service: SciencePulseService, *, user_id: str, tenant_id: str) -> None:
    news = service.news_status(tenant_id)
    health = service.health(tenant_id)
    section_title("Science Plus command center", "science")
    _quick_navigation_grid(tenant_id=tenant_id, user_id=user_id)
    _overview_workflow_strip()
    section_title("Live research intelligence", "science")
    metrics = st.container(horizontal=True)
    with metrics:
        st.metric("Live science news", int(news["live_count"]), border=True)
        st.metric("New in 24h", int(news["new_count"]), border=True)
        st.metric("Scientific records", int(health["items"]), border=True)
        st.metric("Source issues", int(news["failed_sources"]), border=True)
    st.subheader("Top Live Science Stories", anchor=False)
    stories = service.news_feed(tenant_id=tenant_id, user_id=user_id, sort="featured", limit=5)["items"]
    if not stories:
        st.info("No live or cached science story is available yet.")
    for story in stories:
        with st.container(border=True):
            st.markdown(f"**{story['title']}**")
            st.caption(f"{_source(story)} · {_date(story.get('published_at'))} · {story.get('live_state') or 'CACHED'}")
            if story.get("canonical_url"):
                st.link_button("Read full story", str(story["canonical_url"]))
    publication_col, preprint_col = st.columns(2)
    for column, heading, content_type in (
        (publication_col, "Latest Publications", "publication"),
        (preprint_col, "Latest Preprints", "preprint"),
    ):
        with column:
            st.subheader(heading, anchor=False)
            rows = service.store.search_items("", tenant_id=tenant_id, content_type=content_type, limit=5)
            rows = [row for row in rows if str(row.get("live_state")) != "DEMO"]
            if not rows:
                st.caption("No persisted record yet.")
            for row in rows:
                st.markdown(f"- {row['title']} · {_source(row)}")
    trend_col, saved_col = st.columns(2)
    with trend_col:
        st.subheader("Trending Topics", anchor=False)
        trends = service.trends(tenant_id, limit=8)
        if trends:
            st.bar_chart(pd.DataFrame(trends).set_index("topic"), horizontal=True)
        else:
            st.caption("Insufficient persisted data for trend analysis.")
    with saved_col:
        st.subheader("Saved Items & Alerts", anchor=False)
        saved = service.store.search_items("", tenant_id=tenant_id, saved_by=user_id, limit=100)
        with service.store.connect() as connection:
            active_alerts = int(connection.execute(
                "SELECT COUNT(*) FROM sp_alert_rules WHERE tenant_id=? AND user_id=? AND enabled=1",
                (tenant_id, user_id),
            ).fetchone()[0])
        st.metric("Saved scientific records", len(saved), border=True)
        st.metric("Active alerts", active_alerts, border=True)
    st.subheader("Opportunity and release intelligence", anchor=False)
    st.caption(
        "Upcoming Grants · Trial Changes · Database Releases · Tool Releases · Daily Digest. "
        "Panels remain empty until approved providers persist matching records."
    )


def _alerts(service: SciencePulseService, user_id: str, tenant_id: str) -> None:
    _science_plus_hero(
        "Alerts & digests",
        "Create persisted topic alerts, delivery preferences and a local notification inbox.",
        eyebrow="Science Plus Monitoring",
        chips=["Topic rules", "Local inbox", "Delivery preferences"],
    )
    rules_tab, delivery_tab, inbox_tab = st.tabs(["Alert rules", "Delivery", "Inbox"])
    with rules_tab:
        with st.form(f"sp-alert-form-{tenant_id}-{user_id}", border=True):
            name = st.text_input("Alert name")
            query = st.text_input("Keywords")
            categories = st.multiselect(
                "Categories", ["Biology", "Biotechnology", "Biomedical", "Bioinformatics", "Genetics & Genomics", "Cancer Research"]
            )
            content_types = st.multiselect("Content types", ["news", "publication", "preprint", "dataset", "clinical_trial"])
            frequency = st.selectbox("Frequency", ["immediate", "hourly", "three_hour", "daily", "weekly"])
            if st.form_submit_button("Create alert", type="primary"):
                if not name.strip():
                    st.error("Alert name is required.")
                else:
                    rule_id = service.store.create_alert(
                        user_id, name=name, query=query, categories=categories, content_types=content_types,
                        channels=["in_app"], frequency=frequency, tenant_id=tenant_id,
                    )
                    st.success(f"Alert {rule_id} persisted and is active.")
    with delivery_tab:
        current = service.store.preferences(user_id, tenant_id)
        with st.form(f"sp-delivery-{tenant_id}-{user_id}", border=True):
            choices = ["instant", "hourly", "three_hour", "morning", "evening", "daily", "weekly", "in_app_only", "paused"]
            frequency = st.selectbox("Default delivery", choices, index=choices.index(str(current.get("frequency") or "in_app_only")))
            timezone_name = st.text_input("Timezone", value=str(current.get("timezone") or "UTC"))
            if st.form_submit_button("Save delivery preferences"):
                service.store.save_preferences(
                    user_id, {**current, "frequency": frequency, "timezone": timezone_name, "max_notifications_per_sync": 50}, tenant_id
                )
                st.success("Delivery preferences persisted.")
        st.caption("In-app delivery is local and confirmed. External channels require a configured dispatcher and destination approval.")
    with inbox_tab:
        notifications = service.store.notifications(user_id, tenant_id, 100)
        if not notifications:
            st.info("No Science Pulse notifications.")
        for notification in notifications:
            with st.container(border=True):
                st.markdown(f"**{notification['title']}**")
                st.caption(f"{notification['channel']} · {notification['delivery_state']} · {_date(notification['created_at'])}")
                st.write(notification["body"])


def _trends(service: SciencePulseService, user_id: str, tenant_id: str) -> None:
    _science_plus_hero(
        "Trends & Intelligence",
        "Explore persisted topic momentum and generate evidence-bounded scientific digests.",
        eyebrow="Science Plus Analytics",
        chips=["Topic momentum", "Stored evidence", "Digest builder"],
    )
    trend_tab, digest_tab = st.tabs(["Persisted trends", "Digests"])
    with trend_tab:
        rows = service.trends(tenant_id)
        if rows:
            st.bar_chart(pd.DataFrame(rows).set_index("topic"), horizontal=True)
            st.dataframe(rows, width="stretch", hide_index=True)
        else:
            st.info("Insufficient persisted data for trend intelligence.")
    with digest_tab:
        frequency = st.selectbox("Digest period", ["hourly", "three_hour", "daily", "weekly"])
        if st.button("Generate from persisted records", icon=":material/article:"):
            result = service.generate_digest(user_id, frequency=frequency, tenant_id=tenant_id)
            if result["status"] == "ready":
                st.success(f"Digest {result['digest_id']} persisted from {result['item_count']} records.")
            else:
                st.info("Insufficient cached records for this digest period.")


def _sources(service: SciencePulseService, *, user_id: str, tenant_id: str, can_administer: bool) -> None:
    _science_plus_hero(
        "Sources & Operations",
        "Review source health, approval state and safely queued background synchronization.",
        eyebrow="Science Plus Operations",
        chips=["Source health", "Approval gates", "Background sync"],
    )
    st.caption("Source health is read-only for members. Approved administrators can register and queue source operations.")
    if can_administer:
        with st.expander("Register managed RSS / Atom source"):
            with st.form(f"sp-source-register-{tenant_id}"):
                name = st.text_input("Source name")
                url = st.text_input("HTTPS feed URL")
                hours = st.number_input("Synchronization interval (hours)", 1, 168, 3)
                approved = st.checkbox("Approve and enable after security validation")
                if st.form_submit_button("Validate and register"):
                    try:
                        key = service.register_feed(name, url, schedule_seconds=int(hours) * 3600, approved=approved, tenant_id=tenant_id)
                        service.store.audit(user_id, "feed_registered", "science_pulse_source", key, {"approved": approved}, tenant_id)
                        st.success(f"Source {key} persisted.")
                    except ValueError as exc:
                        st.error(str(exc))
    for source in service.source_status(tenant_id):
        with st.container(border=True):
            st.markdown(f"**{source['name']}** · `{source['status']}`")
            st.caption(
                f"{source['kind'].upper()} · last: {_date(source.get('last_sync_at'))} · "
                f"next: {_date(source.get('next_sync_at'))} · approved: {bool(source['approved'])}"
            )
            if source.get("last_error"):
                st.error(str(source["last_error"]))
            if can_administer and st.button(
                "Queue safe sync", key=f"sp-source-queue-{tenant_id}-{source['source_key']}",
                disabled=not bool(source["enabled"]), icon=":material/sync:",
            ):
                with service.store.connect() as connection:
                    connection.execute(
                        "UPDATE sp_sources SET next_sync_at=?,circuit_open_until='',updated_at=? WHERE tenant_id=? AND source_key=?",
                        (utc_now(), utc_now(), tenant_id, source["source_key"]),
                    )
                service.store.audit(user_id, "source_sync_queued", "science_pulse_source", str(source["source_key"]), {}, tenant_id)
                st.success("Synchronization persisted as due for the background worker.")
            if can_administer and st.button(
                "Queue live verification",
                key=f"sp-source-verify-{tenant_id}-{source['source_key']}",
                icon=":material/network_check:",
            ):
                with service.store.connect() as connection:
                    connection.execute(
                        """UPDATE sp_sources SET next_sync_at=?,circuit_open_until='',
                        status='VERIFICATION_QUEUED',last_error='',updated_at=?
                        WHERE tenant_id=? AND source_key=?""",
                        (utc_now(), utc_now(), tenant_id, source["source_key"]),
                    )
                service.store.audit(
                    user_id, "source_live_verification_queued", "science_pulse_source",
                    str(source["source_key"]), {}, tenant_id,
                )
                st.success("Live verification persisted for the background worker.")


def render_science_pulse(
    root: str | Path,
    *,
    user_id: str = "local-user",
    tenant_id: str = "local",
    can_administer: bool = False,
) -> None:
    _inject_science_plus_theme()
    service = _service(str(Path(root).resolve()))
    status = service.news_status(tenant_id)
    health = service.health(tenant_id)
    try:
        from .canvas_studio import SciencePlusCanvasStore

        store = SciencePlusCanvasStore(root, tenant_id=tenant_id, user_id=user_id)
        saved_canvases = store.list()
    except Exception:
        saved_canvases = []

    nav_key = f"sp-primary-navigation-{tenant_id}-{user_id}"
    pending_key = f"sp-primary-navigation-pending-{tenant_id}-{user_id}"
    if pending_key in st.session_state:
        st.session_state[nav_key] = st.session_state.pop(pending_key)
    elif nav_key not in st.session_state:
        st.session_state[nav_key] = "Live Science News"

    hero(
        "Science Plus — live scientific intelligence.",
        "Discover current life-science reporting, inspect source-linked publications, build evidence-aware alerts and map research decisions in a local-first canvas workspace.",
        eyebrow="BioIntel Science Plus · Evidence-aware research workspace",
        chips=[
            f"{status.get('state') or 'OFFLINE'} feed",
            f"{int(status.get('active_sources') or 0)} active sources",
            f"{int(health.get('items') or 0)} scientific records",
            f"{len(saved_canvases)} saved canvases",
        ],
    )


    section = _render_workspace_navigation(
        tenant_id=tenant_id,
        user_id=user_id,
        nav_key=nav_key,
    )

    _section_toolbar(
        section,
        status=status,
        saved_canvases=len(saved_canvases),
        records=int(health.get("items") or 0),
    )
    if section == "Overview":
        _overview(service, user_id=user_id, tenant_id=tenant_id)
    elif section == "Live Science News":
        render_live_news(service, user_id=user_id, tenant_id=tenant_id)
    elif section in SECTION_RULES:
        _content_section(service, str(section), user_id=user_id, tenant_id=tenant_id)
    elif section == "Canvas Studio":
        from .canvas_studio import render_canvas_studio

        render_canvas_studio(
            root, service, user_id=user_id, tenant_id=tenant_id, can_administer=can_administer
        )
    elif section == "Trends & Intelligence":
        _trends(service, user_id, tenant_id)
    elif section == "Saved Library":
        _content_section(service, "Saved Library", user_id=user_id, tenant_id=tenant_id, saved=True)
    elif section == "Alerts":
        _alerts(service, user_id, tenant_id)
    elif section == "Sources & Operations":
        _sources(service, user_id=user_id, tenant_id=tenant_id, can_administer=can_administer)


__all__ = ["NAVIGATION_GROUPS", "PRIMARY_NAVIGATION", "render_science_pulse"]
