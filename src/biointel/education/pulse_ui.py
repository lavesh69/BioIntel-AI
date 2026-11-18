from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from ._streamlit_compat import st
from biointel.ui.frontend_v10 import empty_state

ALLOWED_TABLES = {
    "publications", "news_items", "saved_research", "alerts",
    "alert_deliveries", "pulse_sources", "source_sync_jobs",
}
SOURCE_MANAGER_ROLES = {
    "platform_administrator", "institution_administrator", "principal", "dean",
    "registrar", "department_head", "examination_controller",
}
WORKSPACE_VIEWS = ["Discover", "Saved research", "Alerts", "Sources"]
RunAction = Callable[[Callable[[], Any]], Any]


@dataclass(frozen=True)
class PulseSummary:
    database_ready: bool
    publications: int
    news: int
    saved: int
    active_alerts: int
    sources: int
    configured_sources: int
    completed_syncs: int
    configuration_required_jobs: int
    preprints: int
    corrected: int
    retracted: int
    latest_sync_state: str

    @property
    def records(self) -> int:
        return self.publications + self.news


def _count(platform: Any, table: str, where: str = "", args: tuple[Any, ...] = ()) -> int:
    if table not in ALLOWED_TABLES:
        raise ValueError(f"Unsupported Science Pulse table: {table}")
    row = platform._one(
        f"SELECT COUNT(*) AS n FROM {table}" + (f" WHERE {where}" if where else ""),
        args,
    )
    return int(row["n"] if row else 0)


def _decode(value: Any, fallback: Any) -> Any:
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _http_url(value: Any) -> bool:
    return str(value or "").strip().lower().startswith(("https://", "http://"))


def _status(label: str, state: str, *, help_text: str | None = None) -> None:
    palette = {
        "active": ("green", ":material/check_circle:"),
        "completed": ("green", ":material/check_circle:"),
        "configured": ("green", ":material/check_circle:"),
        "source_linked": ("green", ":material/link:"),
        "current": ("gray", ":material/info:"),
        "preprint": ("orange", ":material/pending:"),
        "corrected": ("orange", ":material/published_with_changes:"),
        "configuration_required": ("orange", ":material/settings:"),
        "running": ("blue", ":material/sync:"),
        "retracted": ("red", ":material/report:"),
        "external_service_unavailable": ("red", ":material/cloud_off:"),
        "failed": ("red", ":material/error:"),
    }
    color, icon = palette.get(state, ("gray", ":material/info:"))
    st.badge(label, color=color, icon=icon, help=help_text)


def _last_sync_state(platform: Any) -> str:
    row = platform._one("SELECT state FROM source_sync_jobs ORDER BY created_at DESC LIMIT 1")
    return str(row["state"] if row else "not_run")


def _summary(platform: Any, actor: str) -> PulseSummary:
    try:
        database_ready = bool(platform.db.quick_check())
    except Exception:
        database_ready = False
    return PulseSummary(
        database_ready=database_ready,
        publications=_count(platform, "publications"),
        news=_count(platform, "news_items"),
        saved=_count(platform, "saved_research", "user_id=?", (actor,)),
        active_alerts=_count(platform, "alerts", "user_id=? AND state='active'", (actor,)),
        sources=_count(platform, "pulse_sources", "state='active'"),
        configured_sources=_count(platform, "pulse_sources", "state='active' AND configured=1"),
        completed_syncs=_count(platform, "source_sync_jobs", "state='completed'"),
        configuration_required_jobs=_count(platform, "source_sync_jobs", "state='configuration_required'"),
        preprints=_count(platform, "publications", "record_type='preprint'"),
        corrected=_count(platform, "publications", "retraction_state='corrected'"),
        retracted=_count(platform, "publications", "retraction_state='retracted'"),
        latest_sync_state=_last_sync_state(platform),
    )


def _source_manager(platform: Any, actor: str) -> bool:
    rows = platform._all(
        "SELECT role FROM memberships WHERE user_id=? AND state='active'", (actor,)
    )
    return any(str(row.get("role", "")) in SOURCE_MANAGER_ROLES for row in rows)


def _set_workspace(view: str) -> None:
    st.session_state["pulse-workspace-view"] = view


def _render_hero(summary: PulseSummary) -> None:
    with st.container(border=True):
        st.subheader("Verified-source scientific intelligence", anchor=False)
        st.write(
            "Search and organize locally persisted publication metadata and biotechnology news. "
            "Every displayed record retains its original source link; no synthetic feed is generated."
        )
        with st.container(horizontal=True, gap="small"):
            _status(
                "Database ready" if summary.database_ready else "Database check failed",
                "active" if summary.database_ready else "failed",
            )
            if summary.sources == 0:
                _status("No source registered", "configuration_required")
            elif summary.configured_sources:
                _status(f"{summary.configured_sources}/{summary.sources} adapters configured", "configured")
            else:
                _status(f"{summary.sources} registered · configuration required", "configuration_required")
            if summary.latest_sync_state == "not_run":
                _status("External sync not run", "configuration_required")
            else:
                _status(
                    "Latest sync: " + summary.latest_sync_state.replace("_", " "),
                    summary.latest_sync_state,
                )
            _status(f"{summary.records:,} source-linked records", "source_linked")
        with st.container(horizontal=True, gap="small"):
            st.metric(
                "Publications", f"{summary.publications:,}",
                help="Persisted records requiring a DOI or PMID plus an original source URL.", border=True,
            )
            st.metric(
                "News records", f"{summary.news:,}",
                help="Persisted news metadata with an original report URL.", border=True,
            )
            st.metric(
                "Saved by you", f"{summary.saved:,}",
                help="Your durable local Science Pulse library.", border=True,
            )
            st.metric(
                "Active alerts", f"{summary.active_alerts:,}",
                help="Local title-match alerts evaluated during future ingestion.", border=True,
            )
        if summary.retracted or summary.corrected or summary.preprints:
            with st.container(horizontal=True, gap="small"):
                if summary.preprints:
                    _status(f"{summary.preprints:,} preprints", "preprint")
                if summary.corrected:
                    _status(f"{summary.corrected:,} corrected records", "corrected")
                if summary.retracted:
                    _status(f"{summary.retracted:,} retracted records", "retracted")
        if summary.sources == 0:
            st.caption(
                "Onboarding: register a legitimate provider, configure its adapter, then sync or ingest source-linked metadata."
            )
        elif summary.configured_sources == 0:
            st.caption(
                "Registered URLs remain disabled until provider configuration is completed. Registration alone does not enable synchronization."
            )


def _activity_rows(platform: Any) -> list[dict[str, Any]]:
    rows = platform._all(
        """
        SELECT substr(created_at,1,10) AS day,
               'Publication' AS record_type,
               COUNT(*) AS records
        FROM publications
        WHERE created_at IS NOT NULL AND created_at<>''
        GROUP BY substr(created_at,1,10)
        UNION ALL
        SELECT substr(created_at,1,10) AS day,
               'News' AS record_type,
               COUNT(*) AS records
        FROM news_items
        WHERE created_at IS NOT NULL AND created_at<>''
        GROUP BY substr(created_at,1,10)
        ORDER BY day,record_type
        """
    )
    return [
        {
            "day": str(row.get("day") or ""),
            "record_type": str(row.get("record_type") or "Record"),
            "records": int(row.get("records") or 0),
        }
        for row in rows
        if row.get("day")
    ]


def _render_empty_journey(summary: PulseSummary) -> None:
    with st.container(border=True):
        st.subheader("Evidence workspace journey", anchor=False)
        st.caption(
            "Each checkpoint reflects persisted local state. It is a readiness path, not a conversion funnel."
        )
        checkpoints = [
            (
                "Registered providers", summary.sources,
                "Provider endpoint records", "configured" if summary.sources else "configuration_required",
            ),
            (
                "Configured adapters", summary.configured_sources,
                "Adapters enabled for synchronization",
                "configured" if summary.configured_sources else "configuration_required",
            ),
            (
                "Source-linked records", summary.records,
                "Persisted publications + news", "source_linked" if summary.records else "current",
            ),
            (
                "Saved + active alerts", summary.saved + summary.active_alerts,
                f"{summary.saved:,} saved · {summary.active_alerts:,} active alerts",
                "active" if summary.saved or summary.active_alerts else "current",
            ),
        ]
        columns = st.columns(4, gap="small", border=True)
        for column, (label, value, detail, state) in zip(columns, checkpoints):
            with column:
                _status("Recorded" if value else "Next checkpoint", state)
                st.metric(label, f"{value:,}")
                st.caption(detail)


def _render_evidence_graphics(platform: Any, summary: PulseSummary) -> None:
    activity = _activity_rows(platform)
    with st.container(border=True):
        st.subheader("Evidence-flow activity", anchor=False)
        st.caption(
            "Actual local creation dates show when source-linked metadata entered this workspace."
        )
        timeline, checkpoint = st.columns([1.6, 1], gap="large")
        with timeline:
            st.markdown("#### Source-linked ingestion activity")
            if activity:
                st.line_chart(
                    activity,
                    x="day",
                    y="records",
                    color="record_type",
                    x_label="Local record date",
                    y_label="Records added",
                    width="stretch",
                    height=250,
                )
                st.caption("Persisted creation dates only; this is not a forecast or provider-coverage estimate.")
            else:
                st.info(
                    "No ingestion activity has been persisted yet.",
                    icon=":material/monitoring:",
                )
        with checkpoint:
            st.markdown("#### Current evidence checkpoint")
            with st.container(horizontal=True, gap="small"):
                _status(
                    f"{summary.configured_sources:,} configured adapters",
                    "configured" if summary.configured_sources else "configuration_required",
                )
                _status(
                    f"{summary.records:,} linked records",
                    "source_linked" if summary.records else "current",
                )
            st.metric(
                "Persisted evidence records",
                f"{summary.records:,}",
                help="Publications plus biotechnology news stored in the local repository.",
                border=True,
            )
            st.metric(
                "Completed provider sync jobs",
                f"{summary.completed_syncs:,}",
                help="Only jobs whose persisted outcome is completed.",
                border=True,
            )
            st.caption(
                "These are operational counts with different units; they are not a completion percentage."
            )


def _render_result_graphics(
    publications: list[dict[str, Any]],
    news: list[dict[str, Any]],
) -> None:
    journal = sum(str(item.get("record_type") or "journal") != "preprint" for item in publications)
    preprint = sum(str(item.get("record_type") or "journal") == "preprint" for item in publications)
    corrected = sum(str(item.get("retraction_state") or "none") == "corrected" for item in publications)
    retracted = sum(str(item.get("retraction_state") or "none") == "retracted" for item in publications)
    no_flag = len(publications) - corrected - retracted
    with st.container(border=True):
        st.subheader("Result-set evidence profile", anchor=False)
        st.caption("Counts below describe only the current persisted search result set.")
        mix_column, stage_column, status_column = st.columns(3, gap="medium")
        with mix_column:
            st.markdown("#### Record mix")
            st.bar_chart(
                [
                    {"record_type": "Publications", "records": len(publications)},
                    {"record_type": "News", "records": len(news)},
                ],
                x="record_type", y="records", color="record_type",
                x_label="Record type", y_label="Records",
                width="stretch", height=220,
            )
        with stage_column:
            st.markdown("#### Publication stage")
            st.bar_chart(
                [
                    {"stage": "Journal", "records": journal},
                    {"stage": "Preprint", "records": preprint},
                ],
                x="stage", y="records", color="stage",
                x_label="Stage", y_label="Publications",
                width="stretch", height=220,
            )
        with status_column:
            st.markdown("#### Retraction and correction watch")
            st.bar_chart(
                [
                    {"status": "No local flag", "records": no_flag},
                    {"status": "Corrected", "records": corrected},
                    {"status": "Retracted", "records": retracted},
                ],
                x="status", y="records", color="status",
                x_label="Persisted status", y_label="Publications",
                width="stretch", height=220,
            )
            st.caption("Local metadata flags only; not a live publisher risk score.")


def _render_saved_graphic(publications: int, news: int) -> None:
    with st.container(border=True):
        st.subheader("Saved collection composition", anchor=False)
        st.bar_chart(
            [
                {"collection": "Publications", "items": publications},
                {"collection": "News", "items": news},
            ],
            x="collection", y="items", color="collection",
            x_label="Saved record type", y_label="Items",
            horizontal=True, width="stretch", height=210,
        )
        st.caption("Actual records in your durable local library.")


def _render_alert_graphic(alerts: list[dict[str, Any]]) -> None:
    rows = [
        {
            "alert": str(item.get("query") or "Untitled alert"),
            "matches": int(item.get("delivery_count") or 0),
            "scope": str(item.get("resource_type") or "all").replace("_", " ").title(),
        }
        for item in alerts
    ]
    with st.container(border=True):
        st.subheader("Alert-match delivery evidence", anchor=False)
        st.bar_chart(
            rows,
            x="alert", y="matches", color="scope",
            x_label="Alert definition", y_label="Persisted local matches",
            horizontal=True, width="stretch",
            height=max(220, min(420, 70 + len(rows) * 44)),
        )
        st.caption(
            "Bars count persisted alert-delivery rows created by ingestion; zero does not imply future provider coverage."
        )


def _render_source_graphics(
    sources: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
) -> None:
    active_sources = [item for item in sources if str(item.get("state") or "active") == "active"]
    configured = sum(bool(item.get("configured")) for item in active_sources)
    configuration_required = len(active_sources) - configured
    inactive = len(sources) - len(active_sources)
    outcomes: dict[str, int] = {}
    for job in jobs:
        state = str(job.get("state") or "unknown").replace("_", " ").title()
        outcomes[state] = outcomes.get(state, 0) + 1
    with st.container(border=True):
        st.subheader("Provider and synchronization status", anchor=False)
        source_column, job_column = st.columns(2, gap="large")
        with source_column:
            st.markdown("#### Source configuration")
            st.bar_chart(
                [
                    {"status": "Configured", "sources": configured},
                    {"status": "Configuration required", "sources": configuration_required},
                    {"status": "Inactive", "sources": inactive},
                ],
                x="status", y="sources", color="status",
                x_label="Persisted source status", y_label="Sources",
                horizontal=True, width="stretch", height=230,
            )
        with job_column:
            st.markdown("#### Synchronization outcomes")
            if outcomes:
                st.bar_chart(
                    [
                        {"outcome": state, "jobs": count}
                        for state, count in sorted(outcomes.items())
                    ],
                    x="outcome", y="jobs", color="outcome",
                    x_label="Persisted outcome", y_label="Jobs",
                    horizontal=True, width="stretch", height=230,
                )
            else:
                empty_state("No synchronization outcome", "This source has no persisted successful or failed synchronization evidence.", icon="⌁", action_hint="Run a source sync after completing safe provider configuration.")
        st.caption(
            "Status is read from local source and job records; registration alone is not provider qualification."
        )


def _source_map(platform: Any) -> dict[str, dict[str, Any]]:
    return {
        str(item["id"]): item
        for item in platform._all("SELECT * FROM pulse_sources WHERE state='active' ORDER BY name")
    }


def _saved_keys(platform: Any, actor: str) -> set[tuple[str, str]]:
    return {
        (str(row["resource_type"]), str(row["resource_id"]))
        for row in platform._all(
            "SELECT resource_type,resource_id FROM saved_research WHERE user_id=?", (actor,)
        )
    }


def _record_source(source: dict[str, Any] | None, source_url: Any) -> None:
    if source and _http_url(source_url):
        _status("Source linked", "source_linked")
        if bool(source.get("configured")):
            _status("Adapter configured", "configured")
        else:
            _status("Registered source", "configuration_required")
    else:
        _status("Source unavailable", "failed")

def _save_action(
    platform: Any,
    actor: str,
    resource_type: str,
    resource_id: str,
    already_saved: bool,
    run: RunAction,
) -> None:
    if already_saved:
        st.button(
            "Saved", key=f"saved-{resource_type}-{resource_id}",
            icon=":material/bookmark_added:", disabled=True, width="stretch",
        )
        return
    if st.button(
        "Save to library", key=f"save-{resource_type}-{resource_id}",
        icon=":material/bookmark_add:", width="stretch",
    ):
        saved = run(lambda: platform.save_research(actor, resource_type, resource_id))
        if saved:
            st.toast("Saved to your research library", icon=":material/bookmark_added:")
            st.rerun()


def _publication_card(
    platform: Any,
    actor: str,
    item: dict[str, Any],
    source: dict[str, Any] | None,
    already_saved: bool,
    run: RunAction,
) -> None:
    with st.container(border=True, height="stretch"):
        with st.container(horizontal=True, gap="small"):
            _record_source(source, item.get("source_url"))
            record_type = str(item.get("record_type") or "journal")
            if record_type == "preprint":
                _status("Preprint · not peer reviewed", "preprint")
            else:
                _status("Journal record", "current")
            retraction = str(item.get("retraction_state") or "none")
            if retraction == "retracted":
                _status("Retracted", "retracted")
            elif retraction == "corrected":
                _status("Corrected", "corrected")
            else:
                _status(
                    "No local retraction flag", "current",
                    help_text="This reflects local metadata, not a live publisher guarantee.",
                )
        st.subheader(str(item.get("title") or "Untitled publication"), anchor=False)
        identifier = ""
        if item.get("doi"):
            identifier = f"DOI {item['doi']}"
        elif item.get("pmid"):
            identifier = f"PMID {item['pmid']}"
        metadata = [
            str(item.get("published_at") or "Date unavailable"),
            str(source.get("name")) if source else "Provider unavailable",
            identifier,
        ]
        st.caption(" · ".join(part for part in metadata if part))
        authors = _decode(item.get("authors_json"), [])
        if authors:
            st.write("**Authors:** " + ", ".join(str(author) for author in authors[:8]))
        if item.get("abstract_excerpt"):
            st.write(str(item["abstract_excerpt"]))
        else:
            st.caption("No abstract excerpt was included in the ingested metadata.")
        if _http_url(item.get("source_url")):
            st.link_button(
                "Open original source", str(item["source_url"]),
                icon=":material/open_in_new:", width="stretch",
            )
        else:
            st.warning("Original source URL is unavailable.", icon=":material/link_off:")
        _save_action(
            platform, actor, "publication", str(item["id"]), already_saved, run
        )


def _news_card(
    platform: Any,
    actor: str,
    item: dict[str, Any],
    source: dict[str, Any] | None,
    already_saved: bool,
    run: RunAction,
) -> None:
    with st.container(border=True, height="stretch"):
        with st.container(horizontal=True, gap="small"):
            _record_source(source, item.get("source_url"))
            _status("Biotechnology news", "current")
        st.subheader(str(item.get("title") or "Untitled news record"), anchor=False)
        metadata = [
            str(item.get("published_at") or "Date unavailable"),
            str(source.get("name")) if source else "Provider unavailable",
        ]
        st.caption(" · ".join(metadata))
        topics = _decode(item.get("topics_json"), [])
        if topics:
            with st.container(horizontal=True, gap="small"):
                for topic in topics[:4]:
                    st.badge(str(topic), color="blue")
        if item.get("summary_excerpt"):
            st.write(str(item["summary_excerpt"]))
        else:
            st.caption("No summary excerpt was included in the ingested metadata.")
        if _http_url(item.get("source_url")):
            st.link_button(
                "Read original report", str(item["source_url"]),
                icon=":material/open_in_new:", width="stretch",
            )
        else:
            st.warning("Original report URL is unavailable.", icon=":material/link_off:")
        _save_action(platform, actor, "news", str(item["id"]), already_saved, run)


def _publication_grid(
    platform: Any,
    actor: str,
    records: list[dict[str, Any]],
    sources: dict[str, dict[str, Any]],
    saved: set[tuple[str, str]],
    run: RunAction,
) -> None:
    for start in range(0, len(records), 2):
        columns = st.columns(2, gap="medium")
        for column, item in zip(columns, records[start : start + 2]):
            with column:
                _publication_card(
                    platform, actor, item,
                    sources.get(str(item.get("source_id") or "")),
                    ("publication", str(item["id"])) in saved, run,
                )


def _news_grid(
    platform: Any,
    actor: str,
    records: list[dict[str, Any]],
    sources: dict[str, dict[str, Any]],
    saved: set[tuple[str, str]],
    run: RunAction,
) -> None:
    for start in range(0, len(records), 2):
        columns = st.columns(2, gap="medium")
        for column, item in zip(columns, records[start : start + 2]):
            with column:
                _news_card(
                    platform, actor, item,
                    sources.get(str(item.get("source_id") or "")),
                    ("news", str(item["id"])) in saved, run,
                )


def _empty_discovery(summary: PulseSummary, query: str) -> None:
    with st.container(border=True):
        st.subheader("No source-linked records found", anchor=False)
        if query:
            st.write(
                f"No locally indexed publication or news title matches “{query}”. "
                "Try a broader term or review source synchronization."
            )
        elif summary.sources == 0:
            st.write(
                "Science Pulse starts empty by design. Add a legitimate source before ingesting metadata."
            )
            _render_empty_journey(summary)
        else:
            st.write(
                "Sources are registered, but no matching metadata is stored. Configuration may still be required."
            )
        st.button(
            "Review sources", icon=":material/cable:", on_click=_set_workspace,
            args=("Sources",), width="stretch",
        )


def _discover(platform: Any, actor: str, run: RunAction, summary: PulseSummary) -> None:
    st.subheader("Discover source-linked research", anchor=False)
    st.caption(
        "Searches locally persisted titles. Publisher links, identifiers and status flags remain visible on every card."
    )
    _render_evidence_graphics(platform, summary)
    st.session_state.setdefault("pulse_query", "")
    with st.form("pulse-search", border=False):
        columns = st.columns([4, 1], vertical_alignment="bottom")
        with columns[0]:
            query = st.text_input(
                "Search publications and biotechnology news",
                value=str(st.session_state.get("pulse_query", "")),
                placeholder="Search a title, topic, DOI-linked paper or news record",
            )
        with columns[1]:
            submitted = st.form_submit_button(
                "Search", icon=":material/search:", type="primary", width="stretch",
            )
    if submitted:
        st.session_state["pulse_query"] = query.strip()
        st.rerun()
    active = str(st.session_state.get("pulse_query", "")).strip()
    if active:
        result = platform.pulse_search(active)
        st.caption(f"Local title matches for “{active}”")
    else:
        result = {
            "publications": platform._all(
                "SELECT * FROM publications ORDER BY published_at DESC,created_at DESC LIMIT 12"
            ),
            "news": platform._all(
                "SELECT * FROM news_items ORDER BY published_at DESC,created_at DESC LIMIT 12"
            ),
        }
        st.caption("Latest locally indexed records")
    publications = list(result.get("publications") or [])
    news = list(result.get("news") or [])
    view = st.segmented_control(
        "Result type", ["All", "Publications", "Biotechnology news"],
        default="All", key="pulse-result-type", width="stretch",
    )
    visible_publications = publications if view in {"All", "Publications"} else []
    visible_news = news if view in {"All", "Biotechnology news"} else []
    with st.container(horizontal=True, gap="small"):
        st.metric("Publication matches", len(publications), border=True)
        st.metric("News matches", len(news), border=True)
        st.metric(
            "Status-sensitive records",
            sum(
                str(item.get("record_type")) == "preprint"
                or str(item.get("retraction_state")) in {"corrected", "retracted"}
                for item in publications
            ),
            help="Preprint, corrected or retracted records in this result set.", border=True,
        )
    if publications or news:
        _render_result_graphics(publications, news)
    if not visible_publications and not visible_news:
        _empty_discovery(summary, active)
        return
    sources = _source_map(platform)
    saved = _saved_keys(platform, actor)
    if visible_publications:
        st.markdown("#### Publications")
        _publication_grid(platform, actor, visible_publications, sources, saved, run)
    if visible_news:
        st.markdown("#### Biotechnology news")
        _news_grid(platform, actor, visible_news, sources, saved, run)

def _saved(platform: Any, actor: str) -> None:
    rows = platform._all(
        """
        SELECT s.id,s.resource_type,s.resource_id,s.created_at,
               COALESCE(p.title,n.title,'Unavailable record') AS title,
               COALESCE(p.source_url,n.source_url,'') AS source_url,
               COALESCE(ps.name,'Provider unavailable') AS source_name,
               COALESCE(p.record_type,'news') AS record_type,
               COALESCE(p.retraction_state,'none') AS retraction_state
        FROM saved_research AS s
        LEFT JOIN publications AS p
          ON s.resource_type='publication' AND p.id=s.resource_id
        LEFT JOIN news_items AS n
          ON s.resource_type='news' AND n.id=s.resource_id
        LEFT JOIN pulse_sources AS ps ON ps.id=COALESCE(p.source_id,n.source_id)
        WHERE s.user_id=?
        ORDER BY s.created_at DESC
        """,
        (actor,),
    )
    publications = sum(str(row["resource_type"]) == "publication" for row in rows)
    news = sum(str(row["resource_type"]) == "news" for row in rows)
    st.subheader("Saved research library", anchor=False)
    st.caption("Your durable local collection; source links and publication status remain visible.")
    with st.container(horizontal=True, gap="small"):
        st.metric("Saved items", len(rows), border=True)
        st.metric("Publications", publications, border=True)
        st.metric("News records", news, border=True)
    if not rows:
        with st.container(border=True):
            st.subheader("Your library is ready", anchor=False)
            st.write(
                "Save a source-linked publication or news record from Discover to build a reading list."
            )
            st.button(
                "Explore research", icon=":material/travel_explore:",
                on_click=_set_workspace, args=("Discover",), width="stretch",
            )
        return
    _render_saved_graphic(publications, news)
    for start in range(0, len(rows), 2):
        columns = st.columns(2, gap="medium")
        for column, item in zip(columns, rows[start : start + 2]):
            with column:
                with st.container(border=True, height="stretch"):
                    with st.container(horizontal=True, gap="small"):
                        _status(
                            "Publication" if item["resource_type"] == "publication" else "News",
                            "current",
                        )
                        if item["record_type"] == "preprint":
                            _status("Preprint", "preprint")
                        if item["retraction_state"] == "retracted":
                            _status("Retracted", "retracted")
                        elif item["retraction_state"] == "corrected":
                            _status("Corrected", "corrected")
                    st.subheader(str(item["title"]), anchor=False)
                    st.caption(f"{item['source_name']} · saved {item['created_at']}")
                    if _http_url(item["source_url"]):
                        st.link_button(
                            "Open original source", str(item["source_url"]),
                            icon=":material/open_in_new:", width="stretch",
                        )
                    else:
                        st.warning("Original source is unavailable.", icon=":material/link_off:")


def _alerts(platform: Any, actor: str, run: RunAction) -> None:
    alerts = platform._all(
        """
        SELECT a.*,COUNT(d.id) AS delivery_count,MAX(d.delivered_at) AS last_delivery
        FROM alerts AS a
        LEFT JOIN alert_deliveries AS d ON d.alert_id=a.id
        WHERE a.user_id=?
        GROUP BY a.id
        ORDER BY a.created_at DESC
        """,
        (actor,),
    )
    total_deliveries = sum(int(item.get("delivery_count") or 0) for item in alerts)
    st.subheader("Local research alerts", anchor=False)
    st.caption(
        "Alerts match titles during future local ingestion. Email, push or external delivery is not claimed."
    )
    with st.container(horizontal=True, gap="small"):
        st.metric(
            "Active alerts", sum(str(item.get("state")) == "active" for item in alerts),
            border=True,
        )
        st.metric("Persisted matches", total_deliveries, border=True)
        st.metric("Alert definitions", len(alerts), border=True)
    if alerts:
        _render_alert_graphic(alerts)
    create_column, list_column = st.columns([1, 1.6], gap="large")
    with create_column:
        with st.container(border=True):
            st.subheader("Create an alert", anchor=False)
            st.caption("Use a precise title keyword or phrase.")
            with st.form("pulse-alert-create"):
                query = st.text_input(
                    "Keywords", placeholder="e.g. single-cell genomics", max_chars=240,
                )
                kind = st.segmented_control(
                    "Watch", ["all", "publication", "news"],
                    default="all", key="pulse-alert-type",
                )
                submitted = st.form_submit_button(
                    "Create alert", icon=":material/add_alert:",
                    type="primary", width="stretch",
                )
            if submitted:
                if not query.strip():
                    st.error("Alert keywords are required.", icon=":material/error:")
                else:
                    created = run(
                        lambda: platform.create_alert(actor, query.strip(), kind or "all")
                    )
                    if created:
                        st.toast("Alert saved", icon=":material/notifications_active:")
                        st.rerun()
    with list_column:
        st.subheader("Your alert definitions", anchor=False)
        if not alerts:
            with st.container(border=True):
                st.write("No alerts yet. Create one to match titles ingested in the future.")
                st.caption("Existing records are not retroactively fabricated as alert deliveries.")
        for alert in alerts:
            with st.container(border=True):
                with st.container(horizontal=True, gap="small"):
                    _status(
                        str(alert.get("state") or "unknown").title(),
                        str(alert.get("state") or "unknown"),
                    )
                    st.badge(
                        str(alert.get("resource_type") or "all").replace("_", " ").title(),
                        color="blue",
                    )
                st.subheader(str(alert.get("query") or "Untitled alert"), anchor=False)
                st.caption(
                    f"{int(alert.get('delivery_count') or 0):,} persisted matches · created {alert.get('created_at')}"
                )
                if alert.get("last_delivery"):
                    st.caption(f"Latest local match: {alert['last_delivery']}")

def _source_card(
    platform: Any,
    actor: str,
    source: dict[str, Any],
    latest_job: dict[str, Any] | None,
    manager: bool,
    run: RunAction,
) -> None:
    with st.container(border=True, height="stretch"):
        with st.container(horizontal=True, gap="small"):
            _status(
                "Configured" if bool(source.get("configured")) else "Configuration required",
                "configured" if bool(source.get("configured")) else "configuration_required",
            )
            _status(
                str(source.get("state") or "unknown").title(),
                str(source.get("state") or "unknown"),
            )
        st.subheader(str(source.get("name") or "Unnamed provider"), anchor=False)
        st.caption(
            str(source.get("source_type") or "Unknown adapter").replace("_", " ").title()
        )
        if _http_url(source.get("base_url")):
            st.link_button(
                "Review endpoint", str(source["base_url"]),
                icon=":material/open_in_new:", width="stretch",
            )
        else:
            st.warning("Endpoint is not a valid HTTP(S) URL.", icon=":material/link_off:")
        if latest_job:
            state = str(latest_job.get("state") or "unknown")
            with st.container(horizontal=True, gap="small"):
                _status("Latest sync: " + state.replace("_", " "), state)
                st.badge(
                    f"{int(latest_job.get('items_received') or 0):,} records", color="blue"
                )
            if latest_job.get("error"):
                st.caption(str(latest_job["error"]))
        else:
            st.caption("No synchronization attempt recorded.")
        can_sync = manager and bool(source.get("configured"))
        if st.button(
            "Run provider sync", key=f"sync-source-{source['id']}",
            icon=":material/sync:", disabled=not can_sync,
            help=None if can_sync else "An administrator and a configured adapter are required.",
            width="stretch",
        ):
            job = run(lambda: platform.sync_pulse_source(actor, source["id"], limit=20))
            if job:
                st.toast(
                    "Synchronization state: " + str(job["state"]).replace("_", " "),
                    icon=":material/sync:",
                )
                st.rerun()


def _register_source(platform: Any, actor: str, manager: bool, run: RunAction) -> None:
    st.subheader("Register a provider", anchor=False)
    st.caption(
        "Registration stores an endpoint in disabled mode. Credentials and provider qualification must be configured separately."
    )
    with st.form("pulse-source-create"):
        name = st.text_input("Provider name", max_chars=160)
        source_type = st.selectbox("Adapter", ["publication_api", "rss", "news_api"])
        url = st.text_input("HTTPS endpoint", placeholder="https://provider.example/api")
        submitted = st.form_submit_button(
            "Register disabled source", icon=":material/add_link:", disabled=not manager,
            help=None if manager else "Institution administrator role required.",
            width="stretch",
        )
    if submitted:
        if not name.strip():
            st.error("Provider name is required.", icon=":material/error:")
        elif not url.strip().lower().startswith("https://"):
            st.error("A legitimate HTTPS provider endpoint is required.", icon=":material/https:")
        else:
            created = run(
                lambda: platform.add_pulse_source(
                    actor, name.strip(), source_type, url.strip(), False,
                )
            )
            if created:
                st.toast(
                    "Source registered as configuration required", icon=":material/link:"
                )
                st.rerun()


def _ingest_publication(
    platform: Any,
    sources: list[dict[str, Any]],
    manager: bool,
    run: RunAction,
) -> None:
    st.caption("Requires a registered source, original source URL, and DOI or PMID.")
    if not sources:
        st.info("Register a legitimate source first.", icon=":material/cable:")
        return
    source_ids = [str(item["id"]) for item in sources]
    labels = {str(item["id"]): str(item["name"]) for item in sources}
    with st.form("pulse-publication-ingest"):
        source_id = st.selectbox(
            "Registered source", source_ids, format_func=lambda value: labels[value],
        )
        title = st.text_input("Publication title", max_chars=500)
        doi = st.text_input("DOI")
        pmid = st.text_input("PMID")
        source_url = st.text_input("Original source URL", placeholder="https://doi.org/…")
        published_at = st.text_input("Published date", placeholder="YYYY-MM-DD")
        authors = st.text_input("Authors", placeholder="Comma-separated names")
        abstract = st.text_area("Abstract excerpt", max_chars=2000)
        record_type = st.segmented_control(
            "Publication stage", ["Journal", "Preprint"],
            default="Journal", key="pulse-ingest-stage",
        )
        retraction_state = st.selectbox(
            "Publisher status flag", ["No local flag", "Corrected", "Retracted"],
        )
        submitted = st.form_submit_button(
            "Validate and ingest publication", icon=":material/library_add:",
            type="primary", disabled=not manager,
            help=None if manager else "Institution administrator role required.",
            width="stretch",
        )
    if submitted:
        if not title.strip():
            st.error("Publication title is required.", icon=":material/error:")
        elif not doi.strip() and not pmid.strip():
            st.error("A DOI or PMID is required.", icon=":material/fingerprint:")
        elif not _http_url(source_url):
            st.error(
                "A legitimate original HTTP(S) source URL is required.", icon=":material/link:"
            )
        else:
            metadata = {
                "title": title.strip(), "doi": doi.strip(), "pmid": pmid.strip(),
                "source_url": source_url.strip(), "published_at": published_at.strip(),
                "authors": [part.strip() for part in authors.split(",") if part.strip()],
                "abstract_excerpt": abstract.strip(),
                "preprint": record_type == "Preprint",
                "corrected": retraction_state == "Corrected",
                "retracted": retraction_state == "Retracted",
            }
            created = run(lambda: platform.ingest_publication(source_id, metadata))
            if created:
                st.toast(
                    "Source-linked publication stored", icon=":material/check_circle:"
                )
                st.rerun()

def _ingest_news(
    platform: Any,
    sources: list[dict[str, Any]],
    manager: bool,
    run: RunAction,
) -> None:
    st.caption("Requires a registered source and an original report URL.")
    if not sources:
        st.info("Register a legitimate source first.", icon=":material/cable:")
        return
    source_ids = [str(item["id"]) for item in sources]
    labels = {str(item["id"]): str(item["name"]) for item in sources}
    with st.form("pulse-news-ingest"):
        source_id = st.selectbox(
            "Registered source", source_ids,
            format_func=lambda value: labels[value], key="pulse-news-source",
        )
        external_id = st.text_input("Provider record ID", max_chars=240)
        title = st.text_input("News title", max_chars=500)
        summary = st.text_area("Source summary excerpt", max_chars=1000)
        source_url = st.text_input("Original report URL")
        published_at = st.text_input(
            "Published date", placeholder="YYYY-MM-DD", key="pulse-news-date"
        )
        topics = st.text_input("Topics", placeholder="Comma-separated topics")
        submitted = st.form_submit_button(
            "Validate and ingest news", icon=":material/newspaper:",
            type="primary", disabled=not manager,
            help=None if manager else "Institution administrator role required.",
            width="stretch",
        )
    if submitted:
        if not external_id.strip() or not title.strip():
            st.error("Provider record ID and title are required.", icon=":material/error:")
        elif not _http_url(source_url):
            st.error(
                "A legitimate original HTTP(S) report URL is required.", icon=":material/link:"
            )
        else:
            created = run(
                lambda: platform.ingest_news(
                    source_id, external_id.strip(), title.strip(), summary.strip(),
                    source_url.strip(), published_at.strip(),
                    [part.strip() for part in topics.split(",") if part.strip()],
                )
            )
            if created:
                st.toast("Source-linked news stored", icon=":material/check_circle:")
                st.rerun()


def _sync_history(platform: Any) -> None:
    jobs = platform._all(
        """
        SELECT j.id,s.name AS source,j.state,j.items_received,j.error,j.created_at
        FROM source_sync_jobs AS j
        JOIN pulse_sources AS s ON s.id=j.source_id
        ORDER BY j.created_at DESC
        LIMIT 50
        """
    )
    st.subheader("Synchronization evidence", anchor=False)
    st.caption("Provider outcomes are displayed exactly as persisted.")
    if not jobs:
        empty_state("No synchronization attempt", "Science Pulse has not recorded an ingestion attempt for this source.", icon="⌁", action_hint="Start a source sync to create auditable evidence.")
        return
    st.dataframe(
        jobs, hide_index=True, width="stretch",
        column_config={
            "id": None,
            "source": st.column_config.TextColumn("Provider", pinned=True),
            "state": st.column_config.TextColumn("Outcome"),
            "items_received": st.column_config.NumberColumn("Records", format="%d"),
            "error": st.column_config.TextColumn("Provider detail"),
            "created_at": st.column_config.DatetimeColumn(
                "Started", format="MMM DD, YYYY · HH:mm"
            ),
        },
    )


def _sources(
    platform: Any,
    actor: str,
    run: RunAction,
    summary: PulseSummary,
) -> None:
    sources = platform._all("SELECT * FROM pulse_sources ORDER BY created_at DESC")
    jobs = platform._all("SELECT * FROM source_sync_jobs ORDER BY created_at DESC")
    latest_by_source: dict[str, dict[str, Any]] = {}
    for job in jobs:
        latest_by_source.setdefault(str(job["source_id"]), job)
    manager = _source_manager(platform, actor)
    st.subheader("Source trust and synchronization", anchor=False)
    st.warning(
        "Registration is not provider qualification. External synchronization is complete only after a configured adapter returns and its persisted job state is completed.",
        icon=":material/verified_user:",
    )
    with st.container(horizontal=True, gap="small"):
        st.metric("Registered sources", summary.sources, border=True)
        st.metric("Configured adapters", summary.configured_sources, border=True)
        st.metric("Completed syncs", summary.completed_syncs, border=True)
        st.metric(
            "Configuration-required jobs", summary.configuration_required_jobs, border=True
        )
    if sources or jobs:
        _render_source_graphics(sources, jobs)
    if not manager:
        st.info(
            "Source registration, synchronization and manual ingestion require an institution administrator role.",
            icon=":material/admin_panel_settings:",
        )
    if not sources:
        with st.container(border=True):
            st.subheader("No providers registered", anchor=False)
            st.write("Register a legitimate HTTPS publication or news provider to begin.")
            st.caption("The new source will remain disabled until configuration is completed.")
    else:
        for start in range(0, len(sources), 2):
            columns = st.columns(2, gap="medium")
            for column, source in zip(columns, sources[start : start + 2]):
                with column:
                    _source_card(
                        platform, actor, source,
                        latest_by_source.get(str(source["id"])), manager, run,
                    )
    register_tab, ingest_tab, history_tab = st.tabs(
        ["Register", "Ingest verified metadata", "Sync history"]
    )
    with register_tab:
        _register_source(platform, actor, manager, run)
    with ingest_tab:
        publication_tab, news_tab = st.tabs(["Publication", "News"])
        with publication_tab:
            _ingest_publication(platform, sources, manager, run)
        with news_tab:
            _ingest_news(platform, sources, manager, run)
    with history_tab:
        _sync_history(platform)


def render_pulse_workspace(
    platform: Any,
    actor: str,
    run: RunAction,
) -> None:
    summary = _summary(platform, actor)
    _render_hero(summary)
    st.session_state.setdefault("pulse-workspace-view", "Discover")
    view = st.segmented_control(
        "Science Pulse workspace", WORKSPACE_VIEWS,
        key="pulse-workspace-view", width="stretch",
    )
    if view == "Saved research":
        _saved(platform, actor)
    elif view == "Alerts":
        _alerts(platform, actor, run)
    elif view == "Sources":
        _sources(platform, actor, run, summary)
    else:
        _discover(platform, actor, run, summary)
