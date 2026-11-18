from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import html

import streamlit as st

from .service import CONTEXTUAL_ACTIONS, SciencePulseService


NEWS_CATEGORIES = (
    "All Science News",
    "Biology",
    "Biotechnology",
    "Biomedical",
    "Bioinformatics",
    "Genetics & Genomics",
    "Molecular Biology",
    "Cell Biology",
    "Microbiology",
    "Virology",
    "Immunology",
    "Neuroscience",
    "Cancer Research",
    "Drug Discovery",
    "Pharmacology",
    "Diagnostics",
    "Precision Medicine",
    "Synthetic Biology",
    "Structural Biology",
    "Systems Biology",
    "Ecology & Environment",
    "Evolution",
    "Marine Biology",
    "Plant Science",
    "Agricultural Science",
    "Food Biotechnology",
    "Public Health Research",
    "Scientific Policy",
    "Research Funding News",
    "India Science",
    "Asia Science",
    "Global Science",
    "General Science",
)

CATEGORY_ALIASES: dict[str, tuple[str, ...]] = {
    "Biology": ("General Biology",),
    "Biomedical": ("Clinical research", "Diagnostics"),
    "Bioinformatics": ("Computational Biology", "AI for biology"),
    "Genetics & Genomics": ("Genetics", "Genomics"),
    "Cancer Research": ("Cancer Biology", "Oncology"),
    "Ecology & Environment": ("Ecology", "Environmental Biology"),
    "Agricultural Science": ("Agricultural biotech",),
    "Research Funding News": ("Research Funding",),
}

NEWS_VIEWS = (
    "Featured",
    "Latest",
    "Breaking",
    "For You",
    "Trending",
    "Story Clusters",
    "Compact Headlines",
    "Timeline",
)

ACTION_LABELS = {
    "ask_shiro": "Ask Shiro AI",
    "add_classroom": "Add to Classroom",
    "classroom_discussion": "Create Classroom Discussion Draft",
    "classroom_assignment": "Create Assignment Draft",
    "academy_lecture": "Create Academy Lecture Draft",
    "studio_asset": "Send to BioIntel Studio",
    "connect_share": "Share through BioIntel Connect",
    "research_project": "Add to Research Project",
    "evidence_collection": "Add to Evidence Collection",
    "research_copilot": "Add to Research Copilot",
    "classification_review": "Report Incorrect Classification",
}


def _text(value: Any, fallback: str = "Not supplied") -> str:
    cleaned = str(value or "").strip()
    return cleaned if cleaned else fallback


def _date_label(value: Any) -> str:
    cleaned = str(value or "").strip()
    return cleaned.replace("T", " ").replace("Z", " UTC") if cleaned else "time unavailable"


def _region(item: dict[str, Any]) -> str:
    provenance = item.get("provenance") or {}
    return _text(provenance.get("region") or provenance.get("country"), "Global / unspecified")


def _source(item: dict[str, Any]) -> str:
    return _text(item.get("source_name") or item.get("provider_key"), "Unknown source")


def _hero_banner(status: dict[str, Any]) -> None:
    st.markdown(
        f"""
        <section class="science-plus-hero">
            <div class="science-plus-eyebrow">Live intelligence feed</div>
            <h2>Live Science News</h2>
            <p>Live biology, biotechnology, biomedical and bioinformatics reporting with stored provenance, source comparison and evidence links.</p>
            <div class="science-plus-stat-grid">
                <div class="science-plus-stat"><strong>{html.escape(str(status.get('state') or 'OFFLINE'))}</strong><span>Feed state</span></div>
                <div class="science-plus-stat"><strong>{int(status.get('active_sources') or 0)}</strong><span>Active sources</span></div>
                <div class="science-plus-stat"><strong>{int(status.get('new_count') or 0)}</strong><span>New in 24h</span></div>
                <div class="science-plus-stat"><strong>{int(status.get('live_count') or 0)} / {int(status.get('cached_count') or 0)}</strong><span>Live / cached</span></div>
            </div>
            <div class="science-plus-chip-row">
                <span class="science-plus-chip">Stored provenance</span>
                <span class="science-plus-chip">Source comparison</span>
                <span class="science-plus-chip">Evidence links</span>
                <span class="science-plus-chip">Background sync aware</span>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _empty_state(message: str, detail: str) -> None:
    st.markdown(
        f"""
        <div class="science-plus-empty">
            <b>{html.escape(message)}</b>
            <span>{html.escape(detail)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _run_action(
    service: SciencePulseService,
    item_id: str,
    *,
    user_id: str,
    tenant_id: str,
    action_key: str,
) -> None:
    result = service.perform_contextual_action(
        item_id,
        user_id=user_id,
        action_key=action_key,
        tenant_id=tenant_id,
    )
    st.success(
        f"Persisted approval draft {result['integration_id']}. Human approval is required before publishing."
    )


@st.dialog("Science story details", width="large")
def _detail_dialog(
    service: SciencePulseService,
    item_id: str,
    user_id: str,
    tenant_id: str,
) -> None:
    item = service.news_detail(
        item_id,
        user_id=user_id,
        tenant_id=tenant_id,
        mark_read=True,
    )
    st.title(_text(item.get("title"), "Untitled science story"), anchor=False)
    badges = st.container(horizontal=True)
    with badges:
        st.badge("NEWS", color="blue")
        st.badge(_text(item.get("live_state"), "CACHED"), color="green")
        if item.get("research_backed"):
            st.badge("RESEARCH-BACKED", color="violet")
        if item.get("official_announcement"):
            st.badge("OFFICIAL ANNOUNCEMENT", color="gray")
        if str(item.get("trust_state") or "normal") != "normal":
            st.badge("CORRECTION / TRUST NOTICE", color="red")

    st.caption(
        f"Original publisher: {_text(item.get('original_source') or item.get('publisher'))} · "
        f"Source: {_source(item)} · Published: {_date_label(item.get('published_at'))} · "
        f"Discovered: {_date_label(item.get('first_seen_at'))}"
    )
    authors = item.get("authors") or []
    if authors:
        st.caption("Authors: " + ", ".join(str(author) for author in authors))
    if item.get("canonical_url"):
        st.link_button(
            "Original Source",
            str(item["canonical_url"]),
            icon=":material/open_in_new:",
        )

    st.subheader("Source Summary", anchor=False)
    st.write(_text(item.get("abstract"), "No permitted source excerpt was supplied."))
    st.caption(
        "BioIntel stores source metadata and permitted excerpts only. This view does not claim access to a full copyrighted article."
    )

    st.subheader("AI-Generated Summary", anchor=False)
    summaries = item.get("summaries") or []
    if summaries:
        latest = summaries[0]
        st.write(_text(latest.get("text")))
        st.caption(
            f"Model label: {_text(latest.get('model_label'))} · Generated: {_date_label(latest.get('created_at'))}"
        )
    else:
        st.info("No AI summary has been generated for this source record.")

    st.subheader("BioIntel Analysis", anchor=False)
    left, right = st.columns(2)
    with left:
        st.markdown("**Primary category**")
        categories = item.get("categories") or []
        st.write(categories[0] if categories else "Unclassified")
        st.markdown("**Secondary categories**")
        st.write(", ".join(str(value) for value in categories[1:]) or "None")
        st.markdown("**Entities**")
        st.write(", ".join(str(value) for value in item.get("entities") or []) or "None detected")
        st.markdown("**Genes / proteins**")
        st.write(", ".join(str(value) for value in item.get("genes") or []) or "None detected")
    with right:
        st.markdown("**Diseases**")
        st.write(", ".join(str(value) for value in item.get("diseases") or []) or "None detected")
        st.markdown("**Organisms**")
        st.write(", ".join(str(value) for value in item.get("organisms") or []) or "None detected")
        st.markdown("**Technologies**")
        st.write(", ".join(str(value) for value in item.get("technologies") or []) or "None detected")
        st.markdown("**Language / region**")
        st.write(f"{_text(item.get('language'), 'und')} · {_region(item)}")

    st.subheader("Related Scientific Evidence", anchor=False)
    evidence_state = _text(item.get("evidence_state"), "No Primary Research Linked")
    if item.get("research_backed"):
        st.success(evidence_state)
        for evidence_type, evidence_link in (item.get("evidence_links") or {}).items():
            st.write(f"{evidence_type.replace('_', ' ').title()}: {evidence_link}")
        st.caption(
            "Evidence relationship comes from explicit source provenance. Peer-review and study limitations are shown only when supplied."
        )
    elif item.get("official_announcement"):
        st.info("Official Institution Announcement — not labeled research-backed without a linked primary record.")
    else:
        st.warning(evidence_state)

    st.subheader("Story sources and provenance", anchor=False)
    sources = item.get("sources") or []
    if sources:
        for source in sources:
            with st.container(border=True):
                st.write(_text(source.get("provider_key"), "Source record"))
                st.caption(
                    f"First seen: {_date_label(source.get('first_seen_at'))} · "
                    f"Last verified: {_date_label(source.get('last_seen_at'))}"
                )
                if source.get("source_url"):
                    st.link_button("Open source record", str(source["source_url"]))
    else:
        st.info("No additional reporting sources are attached to this story.")
    trust_events = item.get("trust_events") or []
    if trust_events:
        with st.expander("Correction and verification history"):
            for event in trust_events:
                st.write(
                    f"{_text(event.get('event_type'))} · {_date_label(event.get('observed_at'))} · "
                    f"{_text(event.get('note'), 'No note')}"
                )



@st.fragment(run_every=30)
def _status_header(
    service: SciencePulseService,
    *,
    user_id: str,
    tenant_id: str,
) -> None:
    status = service.news_status(tenant_id)
    state = str(status.get("state") or "OFFLINE")
    live_class = " is-live" if state == "LIVE" else ""
    copy_col, action_col = st.columns([5, 1], gap="small", vertical_alignment="center")
    with copy_col:
        st.markdown(
            f"""
            <div class="science-plus-live-strip">
                <div class="science-plus-live-main">
                    <span class="science-plus-live-dot{live_class}"></span>
                    <span>{html.escape(state)} scientific feed</span>
                </div>
                <div class="science-plus-live-meta">
                    {int(status.get('active_sources') or 0)} active sources ·
                    {int(status.get('failed_sources') or 0)} source issues ·
                    last sync {_date_label(status.get('last_sync'))} ·
                    next {_date_label(status.get('next_sync'))} ·
                    {html.escape(str(status.get('automatic_updates') or 'background status unavailable'))}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with action_col:
        if st.button(
            "Refresh",
            key=f"sp-news-refresh-{tenant_id}-{user_id}",
            icon=":material/sync:",
            width="stretch",
            help="Queue safe refresh for approved news sources through the background worker; this page makes no direct network call.",
        ):
            queued = service.queue_news_refresh(user_id=user_id, tenant_id=tenant_id)
            st.success(f"Refresh queued for {queued['queued_sources']} approved news source(s).")

def _more_menu(
    service: SciencePulseService,
    item: dict[str, Any],
    *,
    user_id: str,
    tenant_id: str,
    suffix: str,
) -> None:
    item_id = str(item["item_id"])
    with st.popover("More", icon=":material/more_horiz:"):
        if st.button(
            "Open BioIntel detail",
            key=f"sp-detail-{suffix}-{item_id}",
            icon=":material/article:",
            width="stretch",
        ):
            _detail_dialog(service, item_id, user_id, tenant_id)
        for action_key, label in ACTION_LABELS.items():
            if st.button(
                label,
                key=f"sp-action-{action_key}-{suffix}-{item_id}",
                width="stretch",
            ):
                _run_action(
                    service,
                    item_id,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    action_key=action_key,
                )
        if st.button(
            "Create Topic Alert",
            key=f"sp-alert-item-{suffix}-{item_id}",
            width="stretch",
        ):
            result = service.create_item_alert(item_id, user_id=user_id, tenant_id=tenant_id)
            st.success(f"Alert persisted: {result['name']}")
        for kind, label in (("source", "Follow Source"), ("topic", "Follow Topic")):
            if st.button(
                label,
                key=f"sp-follow-{kind}-{suffix}-{item_id}",
                width="stretch",
            ):
                result = service.follow_item(
                    item_id,
                    user_id=user_id,
                    kind=kind,
                    tenant_id=tenant_id,
                )
                st.success(f"Following {result['value']}")
        citation = (
            f"{_text(item.get('title'))}. {_source(item)}. "
            f"{_date_label(item.get('published_at'))}. {_text(item.get('canonical_url'), '')}"
        )
        st.download_button(
            "Export Citation or Source",
            citation,
            file_name=f"science-pulse-{item_id}.txt",
            mime="text/plain",
            key=f"sp-export-{suffix}-{item_id}",
            width="stretch",
        )



def _news_card(
    service: SciencePulseService,
    item: dict[str, Any],
    *,
    user_id: str,
    tenant_id: str,
    suffix: str,
    compact: bool = False,
    recommendation_reason: str = "",
) -> None:
    item_id = str(item["item_id"])
    categories = [str(value) for value in item.get("categories") or []]
    source_count = int(item.get("source_count") or len(item.get("sources") or []) or 1)
    excerpt = _text(item.get("abstract"), "No permitted excerpt supplied.")
    reading_minutes = max(1, round(len(excerpt.split()) / 220))
    verification = "verified source" if item.get("source_verified") else "source verification pending"
    quality_value = item.get("quality")
    quality_label = f"quality {float(quality_value):.0%}" if isinstance(quality_value, (int, float)) else "quality not scored"

    with st.container(border=True):
        badge_row = st.container(horizontal=True)
        with badge_row:
            st.badge("NEWS", color="blue")
            if categories:
                st.badge(categories[0], color="gray")
            st.badge(_text(item.get("live_state"), "CACHED"), color="green")
            if item.get("breaking"):
                st.badge("BREAKING", color="red")
            if source_count > 1:
                st.badge("STORY CLUSTER", color="orange")
            if item.get("research_backed"):
                st.badge("RESEARCH-BACKED", color="violet")
            elif item.get("official_announcement"):
                st.badge("OFFICIAL", color="gray")
            if not item.get("is_read"):
                st.badge("UNREAD", color="blue")
            if item.get("is_saved"):
                st.badge("SAVED", color="green")

        st.markdown(
            f"""
            <div class="science-plus-news-title">{html.escape(_text(item.get('title'), 'Untitled science story'))}</div>
            <div class="science-plus-news-meta">
                {html.escape(_source(item))} · original publisher {html.escape(_text(item.get('original_source'), _source(item)))} ·
                published {html.escape(_date_label(item.get('published_at')))} · discovered {html.escape(_date_label(item.get('first_seen_at')))} ·
                {html.escape(verification)} · {reading_minutes} min read
            </div>
            """,
            unsafe_allow_html=True,
        )
        if recommendation_reason:
            st.info(recommendation_reason)
        if not compact:
            st.write(excerpt[:520] + ("…" if len(excerpt) > 520 else ""))
            if item.get("summary"):
                st.markdown("**BioIntel summary**")
                summary = str(item["summary"])
                st.write(summary[:360] + ("…" if len(summary) > 360 else ""))
            summary_state = "BioIntel summary available" if item.get("summary") else "AI summary not generated"
            st.caption(
                f"{source_count} source{'s' if source_count != 1 else ''} · "
                f"{_text(item.get('language'), 'und')} · {_region(item)} · {quality_label} · "
                f"{summary_state} · correction: {_text(item.get('trust_state'), 'normal')}"
            )
        actions = st.container(horizontal=True, vertical_alignment="center")
        with actions:
            if item.get("canonical_url"):
                st.link_button("Read Full Story", str(item["canonical_url"]), icon=":material/open_in_new:")
            else:
                st.button(
                    "Read Full Story",
                    key=f"sp-no-source-{suffix}-{item_id}",
                    disabled=True,
                    help="No original source URL was supplied.",
                )
            if st.button(
                "Saved" if item.get("is_saved") else "Save",
                key=f"sp-save-{suffix}-{item_id}",
                icon=":material/bookmark:",
            ):
                saved = service.store.toggle_bookmark(user_id, item_id, tenant_id=tenant_id)
                st.toast("Saved to library." if saved else "Removed from library.")
                st.rerun()
            if st.button("Share", key=f"sp-share-{suffix}-{item_id}", icon=":material/share:"):
                _run_action(
                    service,
                    item_id,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    action_key="connect_share",
                )
            _more_menu(service, item, user_id=user_id, tenant_id=tenant_id, suffix=suffix)


def _filters(
    service: SciencePulseService,
    *,
    user_id: str,
    tenant_id: str,
) -> tuple[dict[str, Any], str]:
    facets = service.news_status(tenant_id)
    category_counts = {
        str(row["category"]).casefold(): int(row["count"])
        for row in facets["categories"]
    }
    all_count = int(facets["total"])
    source_options = [""] + [str(row["source"]) for row in facets["sources"]]
    language_options = [""] + [str(row["language"]) for row in facets["languages"]]
    state_key = f"sp-news-applied-{tenant_id}-{user_id}"
    defaults: dict[str, Any] = {
        "query": "",
        "selected_category": "All Science News",
        "source": "",
        "region": "",
        "language": "",
        "date_range": "All time",
        "minimum_quality": 0.0,
        "live_only": False,
        "research_backed": False,
        "unread_only": False,
        "saved_only": False,
        "configured": False,
    }
    state = {**defaults, **dict(st.session_state.get(state_key) or {})}
    if state["source"] and state["source"] not in source_options:
        source_options.append(str(state["source"]))
    if state["language"] and state["language"] not in language_options:
        language_options.append(str(state["language"]))

    def category_label(value: str) -> str:
        if value == "All Science News":
            return f"{value} ({all_count})"
        aliases = CATEGORY_ALIASES.get(value, (value,))
        count = sum(category_counts.get(alias.casefold(), 0) for alias in aliases)
        return f"{value} ({count})"

    widget_prefix = f"sp-news-filter-{tenant_id}-{user_id}"
    with st.expander("Search, category and advanced filters", expanded=not bool(state.get("configured"))):
        with st.form(f"{widget_prefix}-form", border=False):
            query = st.text_input(
                "Search live science news",
                value=str(state["query"]),
                placeholder="Headline, source, gene, disease, organism, technology or identifier",
                key=f"{widget_prefix}-query",
            )
            first = st.columns([1.45, 1, 1], gap="small")
            selected_category = first[0].selectbox(
                "Category",
                NEWS_CATEGORIES,
                index=NEWS_CATEGORIES.index(str(state["selected_category"])) if str(state["selected_category"]) in NEWS_CATEGORIES else 0,
                format_func=category_label,
                key=f"{widget_prefix}-category",
            )
            source = first[1].selectbox(
                "Source",
                source_options,
                index=source_options.index(str(state["source"])) if str(state["source"]) in source_options else 0,
                format_func=lambda value: value or "All sources",
                key=f"{widget_prefix}-source",
            )
            region = first[2].selectbox(
                "Country / region",
                ["", "India", "Asia", "Global"],
                index=["", "India", "Asia", "Global"].index(str(state["region"])) if str(state["region"]) in {"", "India", "Asia", "Global"} else 0,
                format_func=lambda value: value or "All regions",
                key=f"{widget_prefix}-region",
            )
            second = st.columns(3, gap="small")
            language = second[0].selectbox(
                "Language",
                language_options,
                index=language_options.index(str(state["language"])) if str(state["language"]) in language_options else 0,
                format_func=lambda value: value or "All languages",
                key=f"{widget_prefix}-language",
            )
            date_range = second[1].selectbox(
                "Date range",
                ["All time", "24 hours", "7 days", "30 days"],
                index=["All time", "24 hours", "7 days", "30 days"].index(str(state["date_range"])) if str(state["date_range"]) in {"All time", "24 hours", "7 days", "30 days"} else 0,
                key=f"{widget_prefix}-date",
            )
            quality = second[2].selectbox(
                "Content quality",
                [0.0, 0.5, 0.75],
                index=[0.0, 0.5, 0.75].index(float(state["minimum_quality"])) if float(state["minimum_quality"]) in {0.0, 0.5, 0.75} else 0,
                format_func=lambda value: {0.0: "All quality", 0.5: "Quality 50%+", 0.75: "Quality 75%+"}[value],
                key=f"{widget_prefix}-quality",
            )
            flags = st.columns(4, gap="small")
            live_only = flags[0].checkbox("Live only", value=bool(state["live_only"]), key=f"{widget_prefix}-live")
            research_backed = flags[1].checkbox("Research-backed", value=bool(state["research_backed"]), key=f"{widget_prefix}-research")
            unread_only = flags[2].checkbox("Unread only", value=bool(state["unread_only"]), key=f"{widget_prefix}-unread")
            saved_only = flags[3].checkbox("Saved only", value=bool(state["saved_only"]), key=f"{widget_prefix}-saved")
            submit_col, reset_col = st.columns([1, 1], gap="small")
            applied = submit_col.form_submit_button("Apply filters", type="primary", icon=":material/filter_alt:", width="stretch")
            reset = reset_col.form_submit_button("Reset", icon=":material/restart_alt:", width="stretch")

    if reset:
        st.session_state[state_key] = defaults
        for suffix in ("query", "category", "source", "region", "language", "date", "quality", "live", "research", "unread", "saved"):
            st.session_state.pop(f"{widget_prefix}-{suffix}", None)
        st.session_state[f"sp-news-page-{tenant_id}-{user_id}"] = 0
        st.rerun()
    if applied or state_key not in st.session_state:
        state = {
            "query": query,
            "selected_category": selected_category,
            "source": source,
            "region": region,
            "language": language,
            "date_range": date_range,
            "minimum_quality": quality,
            "live_only": live_only,
            "research_backed": research_backed,
            "unread_only": unread_only,
            "saved_only": saved_only,
            "configured": True,
        }
        st.session_state[state_key] = state
        st.session_state[f"sp-news-page-{tenant_id}-{user_id}"] = 0
    else:
        state = {**defaults, **dict(st.session_state[state_key])}

    selected_category = str(state["selected_category"])
    region_from_category = {"India Science": "India", "Asia Science": "Asia", "Global Science": "Global"}.get(selected_category, "")
    category = "" if selected_category in {"All Science News", "India Science", "Asia Science", "Global Science"} else "|".join(CATEGORY_ALIASES.get(selected_category, (selected_category,)))
    days = {"24 hours": 1, "7 days": 7, "30 days": 30}.get(str(state["date_range"]))
    filters = {
        "query": str(state["query"]),
        "source": str(state["source"]),
        "region": region_from_category or str(state["region"]),
        "language": str(state["language"]),
        "date_start": (date.today() - timedelta(days=days)).isoformat() if days else "",
        "minimum_quality": float(state["minimum_quality"]),
        "live_only": bool(state["live_only"]),
        "research_backed": bool(state["research_backed"]),
        "unread_only": bool(state["unread_only"]),
        "saved_only": bool(state["saved_only"]),
        "category": category,
    }
    chips = [selected_category]
    if filters["query"]:
        chips.append(f"Search: {filters['query']}")
    for key, label in (("source", "Source"), ("region", "Region"), ("language", "Language")):
        if filters[key]:
            chips.append(f"{label}: {filters[key]}")
    if state["date_range"] != "All time":
        chips.append(str(state["date_range"]))
    if filters["minimum_quality"]:
        chips.append(f"Quality {filters['minimum_quality']:.0%}+")
    chips.extend(label for enabled, label in (
        (filters["live_only"], "Live only"),
        (filters["research_backed"], "Research-backed"),
        (filters["unread_only"], "Unread"),
        (filters["saved_only"], "Saved"),
    ) if enabled)
    st.markdown(
        '<div class="science-plus-filter-summary">' + ''.join(
            f'<span class="science-plus-chip">{html.escape(chip)}</span>' for chip in chips
        ) + '</div>',
        unsafe_allow_html=True,
    )
    return filters, selected_category

def render_live_news(
    service: SciencePulseService,
    *,
    user_id: str,
    tenant_id: str,
) -> None:
    status = service.news_status(tenant_id)
    _hero_banner(status)
    _status_header(service, user_id=user_id, tenant_id=tenant_id)
    filters, selected_category = _filters(service, user_id=user_id, tenant_id=tenant_id)
    view = st.segmented_control(
        "News view",
        NEWS_VIEWS,
        default="Latest",
        key=f"sp-news-view-{tenant_id}-{user_id}",
    ) or "Latest"
    sort_map = {
        "Featured": "featured",
        "Latest": "latest",
        "Breaking": "latest",
        "For You": "featured",
        "Trending": "trending",
        "Story Clusters": "trending",
        "Compact Headlines": "latest",
        "Timeline": "oldest",
    }
    filters.update(
        {
            "sort": sort_map[str(view)],
            "breaking_only": view == "Breaking",
            "minimum_source_count": 2 if view == "Story Clusters" else 0,
        }
    )
    recommendation_reason = ""
    if view == "For You":
        preferences = service.store.preferences(user_id, tenant_id)
        topics = [str(value) for value in preferences.get("followed_topics") or []]
        sources = [str(value) for value in preferences.get("followed_sources") or []]
        if topics:
            filters["category"] = topics[0]
            recommendation_reason = f"Recommended because you follow {topics[0]}."
        elif sources:
            filters["source"] = sources[0]
            recommendation_reason = f"Recommended because you follow {sources[0]}."
        else:
            st.info("Follow a topic or source from a story's More menu to build your personalized feed.")
            return
    page_key = f"sp-news-page-{tenant_id}-{user_id}"
    page = int(st.session_state.get(page_key, 0))
    page_size = 12
    result = service.news_feed(
        tenant_id=tenant_id,
        user_id=user_id,
        limit=page_size,
        offset=page * page_size,
        **filters,
    )
    st.markdown(
        f"""
        <div class="science-plus-callout">
            <b>Current view:</b> {html.escape(view)} &nbsp;·&nbsp; <b>Category:</b> {html.escape(selected_category)} &nbsp;·&nbsp; <b>Matched items:</b> {int(result['total'])}
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not result["items"]:
        if status["state"] == "OFFLINE":
            _empty_state("Science news is offline.", "No cached record matches these filters right now. Try broader filters or queue a safe refresh.")
        elif filters.get("research_backed"):
            _empty_state("No research-backed item found.", "No item has an explicit linked primary-research record for these filters.")
        else:
            _empty_state("No persisted news record matches these filters.", "Try a broader category, wider date range, or remove one or more filters.")
        return
    compact = view == "Compact Headlines"
    for index, item in enumerate(result["items"]):
        _news_card(
            service,
            item,
            user_id=user_id,
            tenant_id=tenant_id,
            suffix=f"{view}-{page}-{index}",
            compact=compact,
            recommendation_reason=recommendation_reason,
        )
    controls = st.container(horizontal=True, horizontal_alignment="center")
    with controls:
        if st.button("Previous", disabled=page == 0, key=f"sp-news-prev-{tenant_id}-{user_id}"):
            st.session_state[page_key] = max(0, page - 1)
            st.rerun()
        st.write(f"Page {page + 1} of {max(1, (int(result['total']) + page_size - 1) // page_size)}")
        if st.button(
            "Next",
            disabled=(page + 1) * page_size >= int(result["total"]),
            key=f"sp-news-next-{tenant_id}-{user_id}",
        ):
            st.session_state[page_key] = page + 1
            st.rerun()


__all__ = ["ACTION_LABELS", "CATEGORY_ALIASES", "NEWS_CATEGORIES", "NEWS_VIEWS", "render_live_news"]
