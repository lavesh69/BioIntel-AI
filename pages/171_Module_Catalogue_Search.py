from __future__ import annotations

import html
import json
import math
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.ui.module_catalogue import catalogue_counts, complete_catalogue, search_catalogue
from biointel.ui.navigation import CATEGORIES, catalogue_integrity
from biointel.ui.premium_visuals import svg_icon_html
from biointel.ui.theme import apply_theme, hero, section_title
from biointel.ui.visual_polish import render_metric_board

st.set_page_config(
    page_title="Complete Module Catalogue & Search · BioIntel AI",
    page_icon=str(ROOT / "assets" / "brand" / "biointel-icon-256.png"),
    layout="wide",
)
apply_theme()


def module_icon(item, *, size: int = 20) -> str:
    return svg_icon_html(
        page_key=item.key,
        category=item.category,
        title=item.title,
        hint=item.icon,
        size=size,
        css_class="bio-svg-icon bio-catalogue-module-icon",
    )

counts = catalogue_counts(ROOT)
integrity = catalogue_integrity(ROOT)

hero(
    "Every BioIntel module, in one searchable catalogue.",
    "Browse all registered Streamlit pages and the embedded scientific workspaces introduced by recent upgrades. Pagination keeps the interface fast without hiding modules.",
    eyebrow="BioIntel AI · Complete Module Catalogue",
    chips=[
        f"{counts['module_pages']} module pages",
        f"{counts['embedded_workspaces']} embedded workspaces",
        f"{counts['enhanced_pages']} enhanced parent pages",
        "Typo-tolerant search",
        "No ten-result limit",
    ],
)

if not integrity["healthy"]:
    st.warning(
        "Catalogue integrity needs review. Missing or duplicate page metadata is listed in the Diagnostics tab."
    )

render_metric_board(
    [
        ("Module pages", counts["module_pages"], "Registered Streamlit surfaces.", "info"),
        ("Embedded workspaces", counts["embedded_workspaces"], "Linked interactive workspaces.", "success"),
        ("Searchable items", counts["total_searchable_items"], "Pages and workspaces in this catalogue.", "neutral"),
        ("Enhanced parent pages", counts["enhanced_pages"], "Pages with focused interactive support.", "info"),
        ("Auto-discovered", counts["auto_discovered_pages"], "Metadata discovered from the local release.", "warning"),
    ]
)

search_tab, browse_tab, diagnostic_tab = st.tabs(
    ["Search & browse", "Domain directory", "Catalogue diagnostics"]
)

with search_tab:
    section_title("Find a module or scientific workspace", "🔎")
    query_col, sort_col, size_col = st.columns([2.1, 0.8, 0.65])
    query = query_col.text_input(
        "Search",
        placeholder="Try: RNA-seq, VCF, plate map, genome browser, evidence, PDF…",
        key="step117_catalogue_query",
    )
    sort_mode = sort_col.selectbox(
        "Sort",
        ["Relevance", "A–Z", "Domain", "Newest first"],
        key="step117_catalogue_sort",
    )
    page_size = size_col.selectbox(
        "Items per page",
        [24, 48, 96],
        index=1,
        key="step117_catalogue_page_size",
    )

    filter_col, type_col, enhanced_col = st.columns([1.4, 1.0, 0.8])
    all_items = complete_catalogue(str(ROOT))
    available_categories = sorted({item.category for item in all_items})
    selected_categories = filter_col.multiselect(
        "Domains / capability groups",
        available_categories,
        placeholder="All domains",
        key="step117_catalogue_categories",
    )
    selected_types = type_col.multiselect(
        "Item type",
        ["Module page", "Embedded workspace"],
        default=["Module page", "Embedded workspace"],
        key="step117_catalogue_types",
    )
    enhanced_only = enhanced_col.toggle(
        "Enhanced only",
        value=False,
        help="Show module pages with embedded interactive workspaces and the workspaces themselves.",
        key="step117_catalogue_enhanced_only",
    )

    matches = search_catalogue(
        ROOT,
        query,
        categories=selected_categories,
        item_types=selected_types,
        enhanced_only=enhanced_only,
        sort_mode=sort_mode,
    )
    total_pages = max(1, math.ceil(len(matches) / int(page_size)))
    current_catalogue_page = min(max(int(st.session_state.get("step117_catalogue_page", 1) or 1), 1), total_pages)
    if st.session_state.get("step117_catalogue_page") != current_catalogue_page:
        st.session_state["step117_catalogue_page"] = current_catalogue_page
    page_number = st.number_input(
        "Catalogue page",
        min_value=1,
        max_value=total_pages,
        step=1,
        key="step117_catalogue_page",
    )
    start = (int(page_number) - 1) * int(page_size)
    visible = matches[start : start + int(page_size)]

    st.markdown(
        f"**{len(matches)} matching items** · showing {start + 1 if visible else 0}–{start + len(visible)} · page {int(page_number)} of {total_pages}"
    )

    if not visible:
        st.info("No result matched the current filters. Clear one or more filters to restore the full catalogue.")
    else:
        columns = st.columns(3, gap="small")
        for index, match in enumerate(visible):
            item = match.item
            with columns[index % 3]:
                status = "Enhanced" if item.enhanced_workspace else "Standard"
                linked = bool(item.page_path)
                st.markdown(
                    f"""
                    <div class="bio117-module-card">
                      <div class="bio117-module-card-head"><span>{module_icon(item)}</span><b>{html.escape(item.title)}</b></div>
                      <div class="bio117-module-card-meta">{html.escape(item.item_type)} · {html.escape(item.category)} · {status}</div>
                      <p>{html.escape(item.description)}</p>
                      <small>{html.escape('Opens: ' + item.page_title if linked else 'Workspace is not linked to a page')}</small>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if linked:
                    st.page_link(
                        item.page_path,
                        label=f"Open {item.page_title}",
                        width="stretch",
                    )
                else:
                    st.button("Not linked", disabled=True, key=f"unlinked_{item.key}", width="stretch")
                if query and match.reasons:
                    st.caption("Matched: " + " · ".join(match.reasons[:2]))

with browse_tab:
    section_title("Full domain directory", "▦")
    page_items = [item for item in complete_catalogue(str(ROOT)) if item.item_type == "Module page"]
    for category in [*CATEGORIES, *[value for value in sorted({item.category for item in page_items}) if value not in CATEGORIES]]:
        group = [item for item in page_items if item.category == category]
        if not group:
            continue
        with st.expander(f"{category} · {len(group)} modules", expanded=category in {"Start", "Bioinformatics"}):
            grid = st.columns(3, gap="small")
            for index, item in enumerate(group):
                with grid[index % 3]:
                    st.page_link(
                        item.page_path,
                        label=item.title,
                        width="stretch",
                    )
                    if item.enhanced_workspace:
                        st.caption("Interactive workspace enabled")

with diagnostic_tab:
    section_title("Catalogue integrity", "✓")
    st.code(json.dumps(integrity, indent=2, default=str), language="json")
    unlinked = [
        item
        for item in complete_catalogue(str(ROOT))
        if item.item_type == "Embedded workspace" and not item.page_path
    ]
    if unlinked:
        st.error(f"{len(unlinked)} embedded workspaces are not mounted on a page.")
        st.dataframe(
            [{"Workspace": item.title, "Key": item.key, "Group": item.category} for item in unlinked],
            width="stretch",
            hide_index=True,
        )
    else:
        st.success("Every embedded workspace is linked to an existing module page.")

st.markdown(
    """
    <style>
    .bio117-module-card{min-height:168px;padding:.9rem;border:1px solid var(--bio-border);border-radius:var(--bio-radius-lg);background:var(--bio-surface);box-shadow:0 8px 24px rgba(2,6,23,.12);margin-bottom:.45rem}
    .bio117-module-card-head{display:flex;gap:.55rem;align-items:flex-start;color:var(--bio-text)}
    .bio117-module-card-head span{font-size:1.15rem}.bio117-module-card-head b{line-height:1.25}
    .bio117-module-card-meta{margin:.45rem 0;color:var(--bio-secondary);font-size:.69rem;font-weight:780;text-transform:uppercase;letter-spacing:.05em}
    .bio117-module-card p{margin:.25rem 0 .55rem;color:var(--bio-muted);font-size:.76rem;line-height:1.45}
    .bio117-module-card small{color:var(--bio-muted);font-size:.67rem}
    @media(max-width:1200px){.bio117-module-card{min-height:150px}}
    @media(max-width:900px){.bio117-module-card{min-height:auto}}
    </style>
    """,
    unsafe_allow_html=True,
)

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='module_catalogue_search', title='Complete Module Catalogue & Search', category='Start')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
