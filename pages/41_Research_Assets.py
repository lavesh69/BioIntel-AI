from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.assets.research_assets import (
    add_asset_note,
    asset_health,
    asset_notes,
    asset_summary,
    get_asset,
    list_collections,
    search_assets,
    toggle_favourite,
)
from biointel.ui.components import smart_json
from biointel.ui.theme import (
    apply_theme,
    badge,
    command_bar,
    database_cards,
    executive_kpis,
    hero,
    insight_callout,
    section_title,
)

st.set_page_config(
    page_title="Research Assets · BioIntel AI",
    page_icon="📚",
    layout="wide",
)

apply_theme()
database = ROOT / "reports" / "assets.sqlite3"


@st.cache_data(ttl=60, show_spinner=False)
def _asset_overview(path_text: str, modification_ns: int):
    del modification_ns
    path = Path(path_text)
    summary = asset_summary(path)
    return summary, asset_health(path, summary=summary), list_collections(path)


summary, health, collections = _asset_overview(str(database), database.stat().st_mtime_ns)

hero(
    "A professional library for every research asset.",
    (
        "Search files, datasets, models, reports, modules, bookmarks, "
        "tags, notes and executive favourites in one curated local catalogue."
    ),
    eyebrow="Quality-Hardened · Research Assets & Collections",
    chips=[
        f"{summary.assets:,} assets",
        f"{summary.tags:,} tags",
        f"{summary.notes:,} notes",
        f"{summary.collections} collections",
    ],
)

badge(
    "● Asset database healthy" if health["healthy"] else "● Asset database requires review",
    "success" if health["healthy"] else "warning",
)

executive_kpis(
    [
        (
            "Assets",
            f"{summary.assets:,}",
            "Files, models, datasets, modules and bookmarks",
        ),
        (
            "Collections",
            f"{summary.collections:,}",
            "Curated research and executive groups",
        ),
        (
            "Favourites",
            f"{summary.favourites:,}",
            "Pinned high-value assets",
        ),
        (
            "Indexed size",
            f"{summary.total_bytes / (1024 * 1024):.1f} MB",
            "Referenced local project content",
        ),
    ]
)

research_assets_view = st.radio(
    "Research assets view",
    ["Asset Library", "Collections", "Asset Details & Notes"],
    horizontal=True,
    key="research_assets_view",
    label_visibility="collapsed",
)

if research_assets_view == "Asset Library":
    command_bar(
        "Search the complete local asset catalogue",
        "Filter by type, collection and executive favourites.",
    )
    controls = st.columns([3, 1.2, 1.5, 1])
    query = controls[0].text_input(
        "Search assets",
        value="model",
        placeholder="Try: report, sequence, model, database, governance…",
    )
    asset_type = controls[1].selectbox(
        "Asset type",
        ["all", *summary.asset_types.keys()],
    )
    collection_options = {
        "all": "All collections",
        **{str(item["collection_id"]): str(item["name"]) for item in collections},
    }
    collection_id = controls[2].selectbox(
        "Collection",
        list(collection_options),
        format_func=lambda value: collection_options[value],
    )
    favourites_only = controls[3].toggle(
        "Favourites",
        value=False,
    )

    results = search_assets(
        database,
        query,
        asset_type=asset_type,
        collection_id=collection_id,
        favourites_only=favourites_only,
        limit=500,
    )
    frame = pd.DataFrame(results)
    st.caption(f"{len(frame):,} asset(s) found")
    if frame.empty:
        insight_callout(
            "No matching assets",
            "Try a broader search or clear the collection filter.",
            "🔎",
        )
    else:
        display = frame[
            [
                column
                for column in [
                    "asset_type",
                    "title",
                    "path",
                    "status",
                    "size_bytes",
                    "is_favourite",
                    "source",
                ]
                if column in frame.columns
            ]
        ]
        st.dataframe(
            display,
            width="stretch",
            hide_index=True,
        )
        st.download_button(
            "Download asset search CSV",
            frame.to_csv(index=False),
            "research_asset_search.csv",
            "text/csv",
        )

if research_assets_view == "Collections":
    cards = []
    for item in collections[:12]:
        cards.append(
            {
                "icon": "📁",
                "title": item["name"],
                "copy": item["description"],
                "status": ("pinned" if item["pinned"] else "active"),
                "stats": [
                    ("Assets", f"{item['asset_count']:,}"),
                    (
                        "Size",
                        f"{item['total_bytes'] / (1024 * 1024):.1f} MB",
                    ),
                    ("Category", item["category"]),
                ],
            }
        )
    database_cards(cards)

if research_assets_view == "Asset Details & Notes":
    candidates = search_assets(
        database,
        "",
        limit=1000,
    )
    if not candidates:
        st.info("No research assets are indexed.")
    else:
        candidate_map = {
            f"{item['title']} · {item['asset_type']}": item["asset_id"] for item in candidates
        }
        selected_label = st.selectbox(
            "Select an asset",
            list(candidate_map),
        )
        asset_id = candidate_map[selected_label]
        asset = get_asset(database, asset_id)

        top = st.columns([3, 1])
        with top[0]:
            st.markdown(f"## {asset['title']}")
            st.write(asset["description"])
            st.caption(f"Source: {asset['source']}")
        with top[1]:
            st.metric(
                "Type",
                str(asset["asset_type"]),
            )
            st.metric(
                "Status",
                str(asset["status"]),
            )

        detail_table = pd.DataFrame(
            [
                {
                    "Field": "Path",
                    "Value": asset.get("path") or "Virtual asset",
                },
                {
                    "Field": "Size",
                    "Value": f"{int(asset['size_bytes']):,} bytes",
                },
                {
                    "Field": "MIME",
                    "Value": asset["mime_type"],
                },
                {
                    "Field": "Favourite",
                    "Value": ("Yes" if asset["is_favourite"] else "No"),
                },
                {
                    "Field": "Tags",
                    "Value": ", ".join(asset["tags"]),
                },
                {
                    "Field": "Collections",
                    "Value": ", ".join(item["name"] for item in asset["collections"]),
                },
            ]
        )
        st.dataframe(
            detail_table,
            width="stretch",
            hide_index=True,
        )

        actions = st.columns(2)
        if actions[0].button(
            ("Remove favourite" if asset["is_favourite"] else "Add favourite"),
            type="primary",
            width="stretch",
        ):
            is_favourite = toggle_favourite(
                database,
                asset_id,
            )
            st.success("Added to favourites." if is_favourite else "Removed from favourites.")
            st.rerun()

        project_path = ROOT / str(asset["path"]) if asset.get("path") else None
        if (
            project_path is not None
            and project_path.is_file()
            and project_path.stat().st_size <= 25 * 1024 * 1024
        ):
            actions[1].download_button(
                "Download selected asset",
                project_path.read_bytes(),
                project_path.name,
                asset["mime_type"],
                width="stretch",
            )
        elif project_path is not None:
            actions[1].info("Large asset: use its local path instead of loading it into UI memory.")

        section_title("Asset notes", "📝")
        notes = pd.DataFrame(asset_notes(database, asset_id))
        if not notes.empty:
            st.dataframe(
                notes,
                width="stretch",
                hide_index=True,
            )

        with st.form("asset_note_form"):
            note = st.text_area(
                "Add a professional note",
                placeholder=(
                    "Record provenance, review findings, limitations " "or the next action."
                ),
            )
            author = st.text_input(
                "Author label",
                value="Local researcher",
            )
            submitted = st.form_submit_button(
                "Save note",
                type="primary",
            )
            if submitted:
                try:
                    add_asset_note(
                        database,
                        asset_id,
                        note,
                        author_label=author,
                    )
                except Exception as exc:
                    st.error(str(exc))
                else:
                    st.success("Asset note saved.")
                    st.rerun()

        try:
            metadata = json.loads(str(asset["metadata_json"]))
            with st.expander("Technical metadata"):
                smart_json(metadata)
        except json.JSONDecodeError:
            pass

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='research_assets', title='Research Assets', category='Intelligence')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
