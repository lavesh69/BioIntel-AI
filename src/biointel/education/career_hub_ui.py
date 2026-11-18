"""BioIntel Career, Internship & Scholarship Hub.

The module keeps opportunity discovery, application tracking, preparation and
institution workspaces inside the shared BioIntel visual shell. External
opportunities are never presented as guaranteed or automatically verified;
users are directed to confirm details at the official source before applying.
"""
from __future__ import annotations

import datetime as dt
import html
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping
from urllib.parse import urlparse

from ._streamlit_compat import st

DB_DIR = Path.home() / ".biointel" / "education"
DB_DIR.mkdir(parents=True, exist_ok=True)
CAREER_DB_PATH = DB_DIR / "career_hub.sqlite3"


@contextmanager
def _career_connection():
    conn = sqlite3.connect(CAREER_DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


APPLICATION_STATUSES: tuple[str, ...] = (
    "Saved",
    "Preparing",
    "Applied",
    "Interviewing",
    "Offer received",
    "Accepted",
    "Declined",
)

PREPARATION_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("profile", "BioIntel profile updated", "Education, skills, research interests and contact details are current."),
    ("cv", "CV or résumé prepared", "Use a role-specific version with measurable scientific or project evidence."),
    ("statement", "Statement of purpose prepared", "Explain fit, motivation and the value you can contribute."),
    ("evidence", "Portfolio evidence attached", "Link projects, reports, code, posters, publications or laboratory work."),
    ("references", "References confirmed", "Ask referees early and share the opportunity deadline."),
    ("source", "Official source rechecked", "Confirm eligibility, deadline, funding and application route at the source."),
)


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_column_if_missing(conn: sqlite3.Connection, table: str, definition: str) -> None:
    column = definition.split()[0]
    if column not in _table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def init_career_db() -> None:
    """Create/migrate the local career database and seed clearly labelled demo records."""
    with _career_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS opportunities (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                organization TEXT NOT NULL,
                opp_type TEXT NOT NULL,
                domain TEXT NOT NULL,
                stipend_funding TEXT NOT NULL,
                eligibility TEXT NOT NULL,
                deadline TEXT NOT NULL,
                location TEXT NOT NULL,
                source_url TEXT NOT NULL,
                description TEXT NOT NULL,
                verified_by TEXT DEFAULT 'Pending review',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        _add_column_if_missing(conn, "opportunities", "verification_status TEXT DEFAULT 'Demo record — verify at source'")
        _add_column_if_missing(conn, "opportunities", "last_checked TEXT DEFAULT ''")
        _add_column_if_missing(conn, "opportunities", "source_kind TEXT DEFAULT 'Official source'")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                opportunity_id TEXT NOT NULL,
                applicant_id TEXT NOT NULL,
                status TEXT DEFAULT 'Saved',
                notes TEXT,
                applied_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS application_checklist (
                applicant_id TEXT NOT NULL,
                item_key TEXT NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (applicant_id, item_key)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_career_opportunities_type ON opportunities(opp_type)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_career_applications_user ON user_applications(applicant_id)"
        )
        conn.commit()

        if conn.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0] == 0:
            seed_data = [
                (
                    "OPP-001",
                    "ICMR Junior Research Fellowship — demonstration record",
                    "Indian Council of Medical Research",
                    "Scholarship",
                    "Genomics & Oncology",
                    "Confirm on official source",
                    "Life-science postgraduate applicants; confirm the current notice before applying",
                    "2026-09-30",
                    "India",
                    "https://icmr.gov.in/",
                    "Demonstration record for the BioIntel workflow. Open the official source and confirm the active call, funding, eligibility and deadline.",
                ),
                (
                    "OPP-002",
                    "Computational Biology Summer Internship — demonstration record",
                    "Indian Institute of Science",
                    "Internship",
                    "Bioinformatics & AI",
                    "Confirm on official source",
                    "Undergraduate or postgraduate applicants; confirm programme-specific requirements",
                    "2026-08-31",
                    "Bengaluru, India",
                    "https://iisc.ac.in/",
                    "Demonstration record showing how a research internship can be discovered, saved and prepared for inside BioIntel.",
                ),
                (
                    "OPP-003",
                    "International Research Mobility Grant — demonstration record",
                    "European Molecular Biology Organization",
                    "Scholarship",
                    "Molecular Biology",
                    "Confirm on official source",
                    "Researchers should confirm the current mobility-grant criteria",
                    "2026-10-15",
                    "Europe / international",
                    "https://www.embo.org/",
                    "Demonstration mobility-funding record. Availability and terms must be checked on the official programme page.",
                ),
                (
                    "OPP-004",
                    "Bioinformatics Data Engineering Placement — demonstration record",
                    "Biotechnology industry employer",
                    "Job",
                    "Clinical Genomics",
                    "Confirm on official source",
                    "Bioinformatics, computational biology or computer-science background",
                    "2026-09-15",
                    "Hybrid / location varies",
                    "https://www.gene.com/careers",
                    "Demonstration industry-placement record focused on scientific data pipelines and reproducible genomic analysis.",
                ),
                (
                    "OPP-005",
                    "Biotechnology Summer Fellowship — demonstration record",
                    "Indian Institute of Technology Madras",
                    "Internship",
                    "Biotechnology & Systems Biology",
                    "Confirm on official source",
                    "Undergraduate applicants; confirm the current fellowship notice",
                    "2026-08-25",
                    "Chennai, India",
                    "https://www.iitm.ac.in/",
                    "Demonstration fellowship record for application planning and deadline tracking.",
                ),
                (
                    "OPP-006",
                    "Structural Biology Research Fellowship — demonstration record",
                    "CSIR research institute",
                    "Research Fellowship",
                    "Structural Biology",
                    "Confirm on official source",
                    "Postgraduate research applicants; confirm the advertised project requirements",
                    "2026-11-01",
                    "India",
                    "https://www.ccmb.res.in/",
                    "Demonstration research-fellowship record. The live vacancy, project and funding must be verified at source.",
                ),
            ]
            conn.executemany(
                """
                INSERT INTO opportunities (
                    id, title, organization, opp_type, domain, stipend_funding,
                    eligibility, deadline, location, source_url, description,
                    verified_by, verification_status, source_kind
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'BioIntel demo catalogue',
                          'Demo record — verify at source', 'Official source')
                """,
                seed_data,
            )
            conn.commit()


def get_opportunities(opp_type: str = "All", search_query: str = "", domain: str = "All") -> List[Dict[str, Any]]:
    """Return filtered opportunities ordered by the nearest parseable deadline."""
    init_career_db()
    with _career_connection() as conn:
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM opportunities WHERE 1=1"
        params: list[Any] = []
        if opp_type != "All":
            query += " AND opp_type = ?"
            params.append(opp_type)
        if domain != "All":
            query += " AND domain = ?"
            params.append(domain)
        if search_query.strip():
            query += " AND (title LIKE ? OR organization LIKE ? OR domain LIKE ? OR description LIKE ? OR eligibility LIKE ?)"
            q = f"%{search_query.strip()}%"
            params.extend([q, q, q, q, q])
        query += " ORDER BY CASE WHEN deadline GLOB '????-??-??' THEN deadline ELSE '9999-12-31' END ASC, created_at DESC"
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def get_opportunity_domains() -> List[str]:
    init_career_db()
    with _career_connection() as conn:
        return [str(row[0]) for row in conn.execute("SELECT DISTINCT domain FROM opportunities ORDER BY domain").fetchall()]


def get_user_applications(applicant_id: str = "user_default") -> List[Dict[str, Any]]:
    init_career_db()
    with _career_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT a.id AS app_id, a.status, a.notes, a.applied_date, o.*
            FROM user_applications a
            JOIN opportunities o ON a.opportunity_id = o.id
            WHERE a.applicant_id = ?
            ORDER BY a.applied_date DESC
            """,
            (applicant_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def save_application_status(
    opportunity_id: str,
    applicant_id: str = "user_default",
    status: str = "Saved",
    notes: str = "",
) -> None:
    """Create or update one applicant/opportunity tracking record."""
    if status not in APPLICATION_STATUSES:
        raise ValueError(f"Unsupported application status: {status}")
    init_career_db()
    with _career_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM user_applications WHERE opportunity_id = ? AND applicant_id = ? ORDER BY id LIMIT 1",
            (opportunity_id, applicant_id),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE user_applications SET status = ?, notes = ?, applied_date = CURRENT_TIMESTAMP WHERE id = ?",
                (status, notes, existing[0]),
            )
        else:
            conn.execute(
                "INSERT INTO user_applications (opportunity_id, applicant_id, status, notes) VALUES (?, ?, ?, ?)",
                (opportunity_id, applicant_id, status, notes),
            )
        conn.commit()


def remove_application(opportunity_id: str, applicant_id: str = "user_default") -> None:
    init_career_db()
    with _career_connection() as conn:
        conn.execute(
            "DELETE FROM user_applications WHERE opportunity_id = ? AND applicant_id = ?",
            (opportunity_id, applicant_id),
        )
        conn.commit()


def get_preparation_checklist(applicant_id: str = "user_default") -> Dict[str, bool]:
    init_career_db()
    with _career_connection() as conn:
        stored = {
            str(row[0]): bool(row[1])
            for row in conn.execute(
                "SELECT item_key, completed FROM application_checklist WHERE applicant_id = ?",
                (applicant_id,),
            ).fetchall()
        }
    return {key: stored.get(key, False) for key, _label, _copy in PREPARATION_ITEMS}


def set_preparation_item(applicant_id: str, item_key: str, completed: bool) -> None:
    allowed = {key for key, _label, _copy in PREPARATION_ITEMS}
    if item_key not in allowed:
        raise ValueError(f"Unknown preparation item: {item_key}")
    init_career_db()
    with _career_connection() as conn:
        conn.execute(
            """
            INSERT INTO application_checklist (applicant_id, item_key, completed, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(applicant_id, item_key) DO UPDATE SET
                completed = excluded.completed,
                updated_at = CURRENT_TIMESTAMP
            """,
            (applicant_id, item_key, int(bool(completed))),
        )
        conn.commit()


def add_new_opportunity(
    title: str,
    organization: str,
    opp_type: str,
    domain: str,
    stipend: str,
    eligibility: str,
    deadline: str,
    location: str,
    url: str,
    description: str,
) -> str:
    """Add an opportunity as pending review; publication does not imply verification."""
    if not _valid_http_url(url):
        raise ValueError("A valid HTTP(S) source URL is required.")
    init_career_db()
    opp_id = f"OPP-{int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)}"
    with _career_connection() as conn:
        values = (
            opp_id,
            title.strip(),
            organization.strip(),
            opp_type,
            domain.strip(),
            stipend.strip(),
            eligibility.strip(),
            deadline,
            location.strip(),
            url.strip(),
            description.strip(),
        )
        try:
            conn.execute(
                """
                INSERT INTO opportunities (
                    id, title, organization, opp_type, domain, stipend_funding,
                    eligibility, deadline, location, source_url, description,
                    verified_by, verification_status, source_kind
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending reviewer',
                          'Pending source review', 'Submitted source')
                """,
                values,
            )
            conn.commit()
            return opp_id
        except sqlite3.IntegrityError:
            existing = conn.execute(
                """
                SELECT id FROM opportunities
                WHERE lower(title) = lower(?) AND lower(organization) = lower(?)
                  AND source_url = ? AND deadline = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (title.strip(), organization.strip(), url.strip(), deadline),
            ).fetchone()
            if existing:
                return str(existing[0])
            raise


def _valid_http_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def days_until_deadline(value: str, today: dt.date | None = None) -> int | None:
    try:
        deadline = dt.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return (deadline - (today or dt.date.today())).days


def deadline_label(value: str, today: dt.date | None = None) -> tuple[str, str]:
    remaining = days_until_deadline(value, today=today)
    if remaining is None:
        return "Deadline not normalized", "warning"
    if remaining < 0:
        return f"Closed {abs(remaining)} day(s) ago", "danger"
    if remaining == 0:
        return "Deadline today", "danger"
    if remaining <= 7:
        return f"{remaining} day(s) left", "warning"
    return f"{remaining} day(s) left", "success"


def application_progress(applicant_id: str = "user_default") -> int:
    checklist = get_preparation_checklist(applicant_id)
    return round(sum(checklist.values()) / max(len(checklist), 1) * 100)


def _status_tone(status: str) -> str:
    return {
        "Accepted": "success",
        "Offer received": "success",
        "Interviewing": "info",
        "Applied": "info",
        "Preparing": "warning",
        "Declined": "danger",
    }.get(status, "default")


def _pill(text: str, tone: str = "default") -> str:
    return f'<span class="career-pill career-pill-{html.escape(tone)}">{html.escape(text)}</span>'


def _inject_career_css() -> None:
    st.markdown(
        """
        <style>
        .career-command-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.85rem;margin:.9rem 0 1.25rem}
        .career-command-card,.career-opportunity-card,.career-tool-card{background:linear-gradient(145deg,color-mix(in srgb,var(--bio-surface) 92%,transparent),color-mix(in srgb,var(--bio-bg-soft) 76%,transparent));border:1px solid var(--bio-border);border-radius:var(--bio-radius-lg);box-shadow:0 16px 46px rgba(2,6,23,.22);padding:1rem;backdrop-filter:blur(16px)}
        .career-command-label{color:var(--bio-muted);font-size:.72rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase}
        .career-command-value{font-family:var(--bio-heading-font);font-size:1.65rem;font-weight:850;color:var(--bio-text);margin:.2rem 0}
        .career-command-copy{color:var(--bio-muted);font-size:.78rem;line-height:1.45}
        .career-opportunity-card{padding:1.15rem;margin:.75rem 0;position:relative;overflow:hidden}
        .career-opportunity-card:before{content:"";position:absolute;inset:0 auto 0 0;width:4px;background:linear-gradient(180deg,var(--bio-primary),var(--bio-secondary))}
        .career-card-kicker{color:var(--bio-secondary);font-size:.68rem;font-weight:850;letter-spacing:.12em;text-transform:uppercase;margin-bottom:.35rem}
        .career-card-title{color:var(--bio-text);font-family:var(--bio-heading-font);font-size:1.08rem;font-weight:800;line-height:1.3;margin-bottom:.45rem}
        .career-card-meta{color:var(--bio-muted);font-size:.78rem;line-height:1.55;margin:.25rem 0}
        .career-card-copy{color:var(--bio-text);font-size:.86rem;line-height:1.58;margin-top:.6rem}
        .career-pill{display:inline-flex;align-items:center;border-radius:999px;padding:.22rem .56rem;margin:.12rem .18rem .12rem 0;font-size:.68rem;font-weight:800;border:1px solid var(--bio-border);background:color-mix(in srgb,var(--bio-surface-strong) 86%,transparent);color:var(--bio-text)}
        .career-pill-success{border-color:color-mix(in srgb,var(--bio-success) 55%,transparent);color:var(--bio-success)}
        .career-pill-warning{border-color:color-mix(in srgb,var(--bio-warning) 58%,transparent);color:var(--bio-warning)}
        .career-pill-danger{border-color:color-mix(in srgb,var(--bio-danger) 60%,transparent);color:var(--bio-danger)}
        .career-pill-info{border-color:color-mix(in srgb,var(--bio-primary) 58%,transparent);color:var(--bio-primary)}
        .career-trust-strip{display:flex;gap:.55rem;flex-wrap:wrap;margin:.55rem 0 .15rem}
        .career-progress{height:10px;border-radius:999px;background:color-mix(in srgb,var(--bio-surface-strong) 82%,transparent);overflow:hidden;border:1px solid var(--bio-border)}
        .career-progress>span{display:block;height:100%;background:linear-gradient(90deg,var(--bio-primary),var(--bio-secondary));border-radius:inherit}
        .career-tool-card{min-height:142px}
        .career-tool-title{font-family:var(--bio-heading-font);font-size:.96rem;font-weight:800;color:var(--bio-text);margin-bottom:.35rem}
        .career-tool-copy{font-size:.8rem;line-height:1.5;color:var(--bio-muted)}
        @media(max-width:1050px){.career-command-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
        @media(max-width:650px){.career-command-grid{grid-template-columns:1fr}.career-opportunity-card{padding:.95rem}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_summary(opportunities: Iterable[Mapping[str, Any]], applicant_id: str) -> None:
    rows = list(opportunities)
    tracked = get_user_applications(applicant_id)
    open_deadlines = sum(
        1
        for row in rows
        if (remaining := days_until_deadline(str(row.get("deadline", "")))) is not None
        and remaining >= 0
    )
    progress = application_progress(applicant_id)
    st.markdown(
        f"""
        <div class="career-command-grid">
          <div class="career-command-card"><div class="career-command-label">Opportunity catalogue</div><div class="career-command-value">{len(rows)}</div><div class="career-command-copy">Searchable local records with official-source links.</div></div>
          <div class="career-command-card"><div class="career-command-label">Open deadlines</div><div class="career-command-value">{open_deadlines}</div><div class="career-command-copy">Deadline status is calculated from each stored record.</div></div>
          <div class="career-command-card"><div class="career-command-label">Tracked applications</div><div class="career-command-value">{len(tracked)}</div><div class="career-command-copy">Saved, preparing, applied and decision stages.</div></div>
          <div class="career-command-card"><div class="career-command-label">Preparation readiness</div><div class="career-command-value">{progress}%</div><div class="career-progress" aria-label="Preparation progress"><span style="width:{progress}%"></span></div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_ecosystem_links() -> None:
    from biointel.ui.theme import feature_card, section_title

    section_title("Connected BioIntel education ecosystem", "hub")
    cols = st.columns(4)
    cards = (
        ("Education Home", "Return to the learner command centre and continue guided education workflows.", "education", "pages/339_BioIntel_Education_Home.py"),
        ("Education Intelligence", "Review institution and learner evidence through the wider intelligence workspace.", "analytics", "pages/345_BioIntel_Education_Intelligence_Hub.py"),
        ("Academic Portfolio", "Build credential and project evidence that can support applications.", "portfolio", "pages/169_Academic_Portfolio_Credentials.py"),
        ("Collaboration Network", "Connect mentorship, research collaboration and professional-development records.", "network", "pages/178_Collaboration_Network.py"),
    )
    for col, (title, copy, icon, path) in zip(cols, cards):
        with col:
            feature_card(title, copy, icon)
            try:
                st.page_link(path, label=f"Open {title}", use_container_width=True)
            except (KeyError, RuntimeError, TypeError):
                st.caption(f"Available from the BioIntel module catalogue: {title}")


def _render_opportunity_card(opp: Mapping[str, Any], applicant_id: str) -> None:
    deadline_copy, deadline_tone = deadline_label(str(opp.get("deadline", "")))
    verification = str(opp.get("verification_status") or "Verify at source")
    verification_tone = "success" if verification.lower().startswith("verified") else "warning"
    st.markdown(
        f"""
        <article class="career-opportunity-card">
          <div class="career-card-kicker">{html.escape(str(opp.get('opp_type', 'Opportunity')))} · {html.escape(str(opp.get('domain', 'General')))}</div>
          <div class="career-card-title">{html.escape(str(opp.get('title', 'Untitled opportunity')))}</div>
          <div class="career-card-meta"><strong>Organisation:</strong> {html.escape(str(opp.get('organization', '')))} &nbsp;·&nbsp; <strong>Location:</strong> {html.escape(str(opp.get('location', '')))}</div>
          <div class="career-card-meta"><strong>Funding:</strong> {html.escape(str(opp.get('stipend_funding', 'Confirm at source')))} &nbsp;·&nbsp; <strong>Deadline:</strong> {html.escape(str(opp.get('deadline', '')))}</div>
          <div class="career-trust-strip">{_pill(deadline_copy, deadline_tone)}{_pill(verification, verification_tone)}{_pill(str(opp.get('source_kind') or 'Source link'), 'info')}</div>
          <div class="career-card-meta"><strong>Eligibility:</strong> {html.escape(str(opp.get('eligibility', '')))}</div>
          <div class="career-card-copy">{html.escape(str(opp.get('description', '')))}</div>
        </article>
        """,
        unsafe_allow_html=True,
    )
    action_col, status_col, save_col = st.columns([1.25, 1.25, .85])
    with action_col:
        st.link_button("Open official source", str(opp.get("source_url", "")), use_container_width=True)
    with status_col:
        status = st.selectbox(
            "Tracking stage",
            APPLICATION_STATUSES,
            key=f"career_status_{opp['id']}",
            label_visibility="collapsed",
        )
    with save_col:
        if st.button("Track", key=f"career_track_{opp['id']}", use_container_width=True):
            save_application_status(str(opp["id"]), applicant_id=applicant_id, status=status)
            st.toast("Application tracker updated.", icon="✅")
            st.rerun()


def _render_tracker(applicant_id: str) -> None:
    from biointel.ui.theme import insight_callout, section_title

    section_title("Application pipeline", "timeline")
    apps = get_user_applications(applicant_id)
    if not apps:
        insight_callout(
            "No applications tracked yet",
            "Open Discover, choose a stage and add an opportunity to your BioIntel tracker.",
            "bookmark",
            tone="info",
        )
        return

    counts: Dict[str, int] = {status: 0 for status in APPLICATION_STATUSES}
    for app in apps:
        counts[str(app.get("status", "Saved"))] = counts.get(str(app.get("status", "Saved")), 0) + 1
    st.caption(" · ".join(f"{status}: {count}" for status, count in counts.items() if count))

    for app in apps:
        with st.expander(f"{app['title']} — {app['status']}", expanded=False):
            deadline_copy, deadline_tone = deadline_label(str(app.get("deadline", "")))
            st.markdown(
                f"{_pill(str(app.get('status', 'Saved')), _status_tone(str(app.get('status', 'Saved'))))}"
                f"{_pill(deadline_copy, deadline_tone)}",
                unsafe_allow_html=True,
            )
            st.write(f"**Organisation:** {app['organization']}")
            st.write(f"**Eligibility:** {app['eligibility']}")
            next_status = st.selectbox(
                "Update stage",
                APPLICATION_STATUSES,
                index=APPLICATION_STATUSES.index(app["status"]) if app["status"] in APPLICATION_STATUSES else 0,
                key=f"tracker_status_{app['app_id']}",
            )
            notes = st.text_area(
                "Application notes",
                value=str(app.get("notes") or ""),
                placeholder="Documents, contact person, interview preparation or next action",
                key=f"tracker_notes_{app['app_id']}",
            )
            c1, c2, c3 = st.columns([1, 1, 1])
            with c1:
                if st.button("Save changes", key=f"tracker_save_{app['app_id']}", use_container_width=True):
                    save_application_status(str(app["id"]), applicant_id, next_status, notes)
                    st.toast("Tracker saved.", icon="✅")
                    st.rerun()
            with c2:
                st.link_button("Official source", str(app["source_url"]), use_container_width=True)
            with c3:
                if st.button("Remove", key=f"tracker_remove_{app['app_id']}", use_container_width=True):
                    remove_application(str(app["id"]), applicant_id)
                    st.rerun()


def _render_preparation(applicant_id: str) -> None:
    from biointel.ui.theme import feature_card, insight_callout, section_title

    checklist = get_preparation_checklist(applicant_id)
    progress = application_progress(applicant_id)
    section_title("Application preparation workspace", "checklist")
    st.markdown(
        f'<div class="career-tool-card"><div class="career-tool-title">Readiness: {progress}%</div><div class="career-progress"><span style="width:{progress}%"></span></div><div class="career-tool-copy" style="margin-top:.65rem">This checklist supports preparation only. Admission, selection, funding and employment are never guaranteed.</div></div>',
        unsafe_allow_html=True,
    )

    left, right = st.columns([1.4, 1])
    with left:
        for item_key, label, copy in PREPARATION_ITEMS:
            checked = st.checkbox(
                label,
                value=checklist[item_key],
                help=copy,
                key=f"career_check_{applicant_id}_{item_key}",
            )
            if checked != checklist[item_key]:
                set_preparation_item(applicant_id, item_key, checked)
                checklist[item_key] = checked
        if st.button("Save preparation checklist", use_container_width=True, key="career_save_checklist"):
            for item_key, _label, _copy in PREPARATION_ITEMS:
                set_preparation_item(
                    applicant_id,
                    item_key,
                    bool(st.session_state.get(f"career_check_{applicant_id}_{item_key}", False)),
                )
            st.toast("Preparation checklist saved.", icon="✅")
            st.rerun()
    with right:
        feature_card("Evidence-first applications", "Use project outcomes, reports, posters and reproducible work rather than generic claims.", "evidence")
        feature_card("Deadline control", "Track source checks, document dependencies and the next concrete action for every application.", "timeline")
        insight_callout(
            "Privacy boundary",
            "Store only the notes needed for your application. Avoid sensitive identity, health or financial documents in free-text fields.",
            "privacy",
            tone="warning",
        )


def _render_workspace_records() -> None:
    """Preserve the earlier Education Universe workspace-record functionality."""
    from biointel.education.universe_workspaces_service import UniverseWorkspacesService
    from biointel.ui.theme import insight_callout, section_title

    section_title("Career workspace records", "workspace")
    service = UniverseWorkspacesService()
    records = service.list_records("career_hub")
    st.caption("Private local planning records carried forward from the Education Universe workspace.")
    if not records:
        insight_callout(
            "No workspace records",
            "Create a planning record for a target role, scholarship shortlist, mentor discussion or application campaign.",
            "workspace",
            tone="info",
        )
    for record in records:
        with st.expander(str(record["title"]), expanded=False):
            st.json(record.get("payload", {}))
            if st.button("Delete workspace record", key=f"career_delete_workspace_{record['record_id']}"):
                service.delete_record(str(record["record_id"]))
                st.rerun()

    with st.form("career_workspace_record_form"):
        title = st.text_input("Workspace title", placeholder="Example: Computational genomics internship shortlist")
        category = st.selectbox("Planning type", ["Career plan", "Internship shortlist", "Scholarship shortlist", "Placement plan", "Mentorship follow-up"])
        objective = st.text_area("Objective and next actions", placeholder="Target roles, evidence gaps, deadlines and next steps")
        priority = st.selectbox("Priority", ["High", "Medium", "Low"])
        submitted = st.form_submit_button("Save BioIntel workspace record")
        if submitted:
            if not title.strip():
                st.error("Enter a workspace title.")
            else:
                service.save_record(
                    "career_hub",
                    title.strip(),
                    {"category": category, "objective": objective.strip(), "priority": priority, "status": "active"},
                )
                st.success("Workspace record saved.")
                st.rerun()


def _render_publish() -> None:
    from biointel.ui.theme import insight_callout, section_title

    section_title("Submit an opportunity for review", "publish")
    insight_callout(
        "Source-review boundary",
        "A submitted record is labelled Pending source review. BioIntel does not treat a posting as verified merely because a URL was provided.",
        "verified",
        tone="warning",
    )
    with st.form("new_opportunity_form"):
        col1, col2 = st.columns(2)
        with col1:
            title = st.text_input("Opportunity title", placeholder="Example: Bioinformatics research internship")
            organization = st.text_input("Organisation or university")
            opp_type = st.selectbox("Category", ["Internship", "Scholarship", "Research Fellowship", "Job"])
            domain = st.text_input("Domain or field", placeholder="Computational genomics")
            stipend = st.text_input("Funding or stipend", placeholder="State 'Not specified' when unknown")
        with col2:
            deadline = st.date_input("Deadline", value=dt.date.today() + dt.timedelta(days=30))
            location = st.text_input("Location", placeholder="City, country, remote or hybrid")
            source_url = st.text_input("Official HTTP(S) source URL", placeholder="https://institution.example/opportunity")
            eligibility = st.text_area("Eligibility criteria")
            description = st.text_area("Description and objectives")
        submitted = st.form_submit_button("Submit for BioIntel review")
        if submitted:
            if not title.strip() or not organization.strip() or not _valid_http_url(source_url):
                st.error("Enter a title, organisation and valid HTTP(S) source URL.")
            else:
                new_id = add_new_opportunity(
                    title,
                    organization,
                    opp_type,
                    domain,
                    stipend or "Not specified",
                    eligibility,
                    str(deadline),
                    location,
                    source_url,
                    description,
                )
                st.success(f"Submitted as {new_id}. Status: Pending source review.")
                st.rerun()


def render_career_hub_page() -> None:
    """Render the canonical BioIntel-themed career hub."""
    from biointel.ui.theme import hero, insight_callout, section_title
    from .education_suite import EducationSuiteService
    from .education_suite_ui import render_career_application_studio

    init_career_db()
    _inject_career_css()
    applicant_id = "user_default"

    hero(
        "Career, Internship & Scholarship Hub",
        "Discover opportunities, verify the official source, prepare evidence and manage every application from one BioIntel education workspace.",
        eyebrow="BioIntel Education · Student Growth",
        chips=["Opportunity discovery", "Application tracker", "Preparation workspace", "Source-aware"],
    )
    insight_callout(
        "Opportunity information requires source confirmation",
        "Deadlines, funding and eligibility can change. BioIntel provides organization and tracking; always confirm the live notice at the official source before acting.",
        "verified",
        tone="warning",
    )

    all_opportunities = get_opportunities()
    _render_summary(all_opportunities, applicant_id)
    _render_ecosystem_links()

    tabs = st.tabs(
        [
            "Discover",
            "Application tracker",
            "Preparation",
            "Career workspace",
            "Submit opportunity",
            "Application studio",
        ]
    )

    with tabs[0]:
        section_title("Discover opportunities", "search")
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            search_query = st.text_input(
                "Search opportunities",
                placeholder="Genomics, research fellowship, organisation or skill",
                key="career_search",
            )
        with c2:
            type_filter = st.selectbox(
                "Category",
                ["All", "Internship", "Scholarship", "Research Fellowship", "Job"],
                key="career_type_filter",
            )
        with c3:
            domain_filter = st.selectbox(
                "Domain",
                ["All", *get_opportunity_domains()],
                key="career_domain_filter",
            )
        opportunities = get_opportunities(type_filter, search_query, domain_filter)
        st.caption(f"{len(opportunities)} matching record(s). Demo and pending records must be verified at source.")
        if not opportunities:
            insight_callout("No matching records", "Change the search, category or domain filter.", "search", tone="info")
        for opportunity in opportunities:
            _render_opportunity_card(opportunity, applicant_id)

    with tabs[1]:
        _render_tracker(applicant_id)

    with tabs[2]:
        _render_preparation(applicant_id)

    with tabs[3]:
        _render_workspace_records()

    with tabs[4]:
        _render_publish()

    with tabs[5]:
        render_career_application_studio(EducationSuiteService(), applicant_id, "personal")
