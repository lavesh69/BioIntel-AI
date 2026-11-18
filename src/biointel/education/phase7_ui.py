from __future__ import annotations

import html
import json
import math
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from ._streamlit_compat import st
from .experience import render_app_header, render_role_snapshot, render_workspace_context
from biointel.ui.frontend_v10 import empty_state
from .phase7 import ADMIN_ROLES, TEACHER_ROLES, EducationPhase7Service
from .platform import EducationError, parse_time
from .ui import _actor, _demo_controls, _page_platform, _run

Run = Callable[[Callable[[], Any]], Any]
STUDENT_ROLES = {"school_student", "college_student", "university_student"}


def _subjects(platform: Any, actor: str, institution_id: str) -> list[dict[str, Any]]:
    roles = {row["role"] for row in platform.membership(actor, institution_id)}
    if roles & STUDENT_ROLES:
        return platform._all(
            """SELECT DISTINCT s.id,s.code,s.name FROM subjects s JOIN enrollments e ON e.subject_id=s.id
            WHERE s.institution_id=? AND e.student_id=? AND e.state='active' ORDER BY s.code""",
            (institution_id, actor),
        )
    if roles & ADMIN_ROLES:
        return platform._all("SELECT id,code,name FROM subjects WHERE institution_id=? AND state='active' ORDER BY code", (institution_id,))
    return platform._all(
        """SELECT DISTINCT s.id,s.code,s.name FROM subjects s JOIN teacher_assignments t ON t.subject_id=s.id
        WHERE s.institution_id=? AND t.teacher_id=? AND t.state='active' ORDER BY s.code""",
        (institution_id, actor),
    )


def _courses(platform: Any, actor: str, institution_id: str) -> list[dict[str, Any]]:
    roles = {row["role"] for row in platform.membership(actor, institution_id)}
    if roles & (ADMIN_ROLES | TEACHER_ROLES):
        return platform._all("SELECT * FROM courses WHERE institution_id=? ORDER BY updated_at DESC", (institution_id,))
    return platform._all(
        """SELECT c.* FROM courses c JOIN academy_enrollments e ON e.course_id=c.id
        WHERE c.institution_id=? AND e.student_id=? AND e.state='active' ORDER BY c.updated_at DESC""",
        (institution_id, actor),
    )


def render_playback_evidence_controls(
    service: EducationPhase7Service,
    platform: Any,
    actor: str,
    lecture: dict[str, Any],
) -> float:
    """Capture durable playback events and return the current player position."""
    from .phase15 import EducationPhase15Service

    lecture_id = str(lecture["id"])
    telemetry = EducationPhase15Service(platform, root=service.root)
    session_key = f"academy-playback-session-{lecture_id}"
    st.session_state.setdefault(session_key, uuid4().hex)
    summary = _run(lambda: telemetry.playback_summary(actor, lecture_id)) or {}
    duration = float(lecture.get("duration_seconds") or 0)
    position = st.number_input(
        "Current player position (seconds)",
        min_value=0.0,
        max_value=duration if duration > 0 else 86400.0,
        value=min(float(summary.get("max_position_seconds") or 0), duration or 86400.0),
        step=5.0,
        key=f"academy-playback-position-{lecture_id}",
    )
    event_type = st.selectbox(
        "Playback event",
        ["play", "progress", "pause", "seek", "ended"],
        key=f"academy-playback-event-{lecture_id}",
        help="Submit seek before a manual jump. Seek-only movement never counts as watched time.",
    )
    playback_rate = st.select_slider(
        "Playback rate",
        options=[0.5, 0.75, 1.0, 1.25, 1.5, 2.0],
        value=1.0,
        key=f"academy-playback-rate-{lecture_id}",
    )
    if st.button(
        "Record playback event",
        type="primary",
        icon=":material/timeline:",
        key=f"academy-record-playback-{lecture_id}",
        width="stretch",
    ):
        result = _run(lambda: telemetry.record_playback_event(
            actor,
            lecture_id,
            event_type=event_type,
            position_seconds=float(position),
            session_id=str(st.session_state[session_key]),
            client_event_id=uuid4().hex,
            playback_rate=float(playback_rate),
        ))
        if result:
            summary = result
            st.toast("Playback evidence recorded", icon=":material/check_circle:")
    if summary:
        c1, c2, c3 = st.columns(3)
        c1.metric("Observed watch", f"{float(summary.get('observed_watch_seconds') or 0):.1f}s")
        c2.metric("Events", int(summary.get("event_count") or 0))
        c3.metric("Complete", "Yes" if summary.get("completed") else "No")
        st.caption(str(summary.get("policy") or "Completion is derived from server-validated playback events."))
    else:
        st.caption("No playback evidence yet. Start with a play event; completion has no manual override.")
    return float(position)


def _desktop_css() -> None:
    st.markdown(
        """
<a class="edu7-skip" href="#edu7-main">Skip to workspace</a>
<style>
.edu7-skip{position:fixed;left:1rem;top:-5rem;z-index:99999;padding:.7rem 1rem;border-radius:10px;background:#fff;color:#07111f;font-weight:800;transition:top .15s}
.edu7-skip:focus{top:1rem}
.edu7-workspace-bar{position:sticky;top:.35rem;z-index:40;padding:.55rem .7rem;border:1px solid var(--edu-border);border-radius:16px;background:rgba(7,17,31,.94);backdrop-filter:blur(18px);box-shadow:0 12px 30px rgba(0,0,0,.22);margin:.5rem 0 1rem}
.edu7-board{display:grid;grid-template-columns:repeat(7,minmax(11rem,1fr));gap:.65rem;overflow-x:auto;padding:.25rem 0 .8rem}
.edu7-lane{min-height:17rem;border:1px solid var(--edu-border);border-radius:16px;background:rgba(10,25,44,.72);padding:.65rem}
.edu7-lane h4{margin:.1rem 0 .6rem;color:var(--edu-text);font-size:.83rem;text-transform:uppercase;letter-spacing:.07em}
.edu7-task{padding:.7rem;margin:.45rem 0;border:1px solid rgba(148,184,224,.16);border-radius:13px;background:linear-gradient(145deg,rgba(24,45,73,.95),rgba(12,28,48,.94));box-shadow:0 8px 24px rgba(0,0,0,.16)}
.edu7-task strong{display:block;color:var(--edu-text);font-size:.86rem}.edu7-task small{display:block;color:var(--edu-muted);margin-top:.25rem}
.edu7-status-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.75rem}.edu7-status{padding:.9rem;border:1px solid var(--edu-border);border-radius:16px;background:rgba(12,28,48,.74)}
.edu7-status strong{display:block;color:var(--edu-text)}.edu7-status small{color:var(--edu-muted)}
.edu7-chat-shell{min-height:30rem;padding:.5rem;border:1px solid var(--edu-border);border-radius:18px;background:rgba(9,22,39,.72)}
.edu7-citation{display:inline-flex;padding:.22rem .46rem;margin:.14rem;border-radius:999px;border:1px solid rgba(79,228,255,.3);background:rgba(79,228,255,.08);font-size:.72rem;color:#c7f8ff}
.edu7-login{max-width:44rem;margin:1.2rem auto;padding:1.2rem;border:1px solid var(--edu-border);border-radius:22px;background:rgba(12,28,48,.9);box-shadow:var(--edu-shadow)}
.edu7-detail{padding:.75rem;border:1px solid var(--edu-border);border-radius:14px;background:rgba(255,255,255,.025)}
[data-testid="stDataEditor"]{border:1px solid var(--edu-border);border-radius:16px;overflow:hidden}
[data-testid="stChatMessage"]{border:1px solid rgba(148,184,224,.12);border-radius:16px;padding:.45rem .7rem;background:rgba(255,255,255,.025)}
[data-testid="stPlotlyChart"]{border:1px solid var(--edu-border);border-radius:18px;overflow:hidden;background:rgba(9,22,39,.55)}
@media (max-width:1100px){.edu7-status-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>
<div id="edu7-main"></div>
        """,
        unsafe_allow_html=True,
    )


def _chart_layout(fig: go.Figure, title: str = "") -> go.Figure:
    fig.update_layout(
        title=title,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#dcecff"),
        margin=dict(l=20, r=20, t=55 if title else 20, b=25),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor="#10243d", font_color="#eff7ff"),
    )
    fig.update_xaxes(gridcolor="rgba(148,184,224,.12)", zerolinecolor="rgba(148,184,224,.16)")
    fig.update_yaxes(gridcolor="rgba(148,184,224,.12)", zerolinecolor="rgba(148,184,224,.16)")
    return fig


def _restore_session(service: EducationPhase7Service) -> dict[str, Any] | None:
    token = str(st.session_state.get("education_phase7_token", "") or "")
    if not token:
        return None
    try:
        session = service.validate_session(token)
    except EducationError:
        st.session_state.pop("education_phase7_token", None)
        st.session_state.pop("education_authenticated", None)
        return None
    st.session_state.education_actor = session["user_id"]
    st.session_state.education_institution = session["institution_id"]
    st.session_state.education_authenticated = True
    return session


def _sign_in(service: EducationPhase7Service, platform: Any) -> dict[str, Any] | None:
    session = _restore_session(service)
    if session:
        return session
    institutions = platform._all("SELECT id,name,kind FROM institutions ORDER BY name")
    if not institutions:
        st.info("Create an institution in the existing Education setup before enabling desktop sign-in.")
        return None
    institution_by_id = {row["id"]: row for row in institutions}
    with st.container(border=True):
        st.markdown('<div class="edu7-login">', unsafe_allow_html=True)
        st.subheader(":material/lock: BioIntel Education Desktop sign-in")
        st.caption("Local-first session security with scrypt PIN hashing, lockout protection and revocable device sessions.")
        institution_id = st.selectbox(
            "Institution",
            list(institution_by_id),
            format_func=lambda value: institution_by_id[value]["name"],
            key="edu7-login-institution",
        )
        accounts = service.identity_accounts(institution_id)
        if accounts:
            with st.form("edu7-sign-in"):
                login = st.text_input("User ID or email", autocomplete="username")
                pin = st.text_input("PIN or passphrase", type="password", autocomplete="current-password")
                device = st.text_input("Device label", value="BioIntel Windows Desktop")
                submit = st.form_submit_button("Sign in securely", type="primary", icon=":material/login:")
            if submit:
                result = _run(lambda: service.authenticate(institution_id, login, pin, device_label=device))
                if result:
                    st.session_state.education_phase7_token = result["token"]
                    st.session_state.education_actor = result["user_id"]
                    st.session_state.education_institution = institution_id
                    st.session_state.education_authenticated = True
                    st.rerun()
        else:
            st.warning("First-time local setup: enroll one existing institution administrator. Further accounts can be created after sign-in.")
            admins = platform._all(
                """SELECT DISTINCT user_id FROM memberships WHERE institution_id=? AND state='active'
                AND role IN ('platform_administrator','institution_administrator','principal','dean','registrar','department_head') ORDER BY user_id""",
                (institution_id,),
            )
            if not admins:
                st.error("No administrator membership is available for first-time desktop setup.")
            else:
                choices = [row["user_id"] for row in admins]
                with st.form("edu7-first-account"):
                    user_id = st.selectbox("Administrator", choices)
                    display_name = st.text_input("Display name", value=user_id.replace("_", " ").title())
                    email = st.text_input("Email (optional)")
                    pin = st.text_input("Create PIN/passphrase", type="password")
                    confirm = st.text_input("Confirm PIN/passphrase", type="password")
                    create = st.form_submit_button("Create first desktop account", type="primary")
                if create:
                    if pin != confirm:
                        st.error("PIN confirmation does not match.")
                    else:
                        result = _run(lambda: service.enroll_identity(user_id, institution_id, user_id, pin, display_name=display_name, email=email))
                        if result:
                            st.success("Desktop account created. Sign in above.")
                            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
    return None


def _overview(service: EducationPhase7Service, platform: Any, actor: str, institution_id: str) -> None:
    data = _run(lambda: service.visual_dashboard(actor, institution_id)) or {}
    calendar = data.get("calendar", {})
    roles = {row["role"] for row in platform.membership(actor, institution_id)}
    cards = [
        ("Classes this week", len(calendar.get("entries", [])), "Scheduled academic events"),
        ("Unread notices", data.get("unread_notifications", 0), "Actions requiring attention"),
        ("Active role", next(iter(sorted(roles)), "member").replace("_", " ").title(), "Permission-aware workspace"),
        ("Recent activity", len(data.get("recent_activity", [])), "Audited institution events"),
    ]
    html = '<div class="edu7-status-grid">' + "".join(
        f'<article class="edu7-status"><strong>{value}</strong><small>{label}<br>{detail}</small></article>'
        for label, value, detail in cards
    ) + "</div>"
    st.markdown(html, unsafe_allow_html=True)
    if calendar.get("entries"):
        df = pd.DataFrame(calendar["entries"])
        df["starts_at"] = pd.to_datetime(df["starts_at"])
        df["ends_at"] = pd.to_datetime(df["ends_at"])
        fig = px.timeline(df, x_start="starts_at", x_end="ends_at", y="subject_code", color="room", hover_data=["subject_name", "teacher_id", "student_group"])
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(_chart_layout(fig, "Desktop timetable overview"), width="stretch", config={"displaylogo": False})
    else:
        empty_state("No timetable entries this week", "No permission-visible classes are scheduled in the selected week.", icon="▦", action_hint="Create or adjust the timetable from the scheduling workspace.")
    left, right = st.columns([1.15, .85], gap="large")
    with left:
        st.subheader("Priority notifications")
        notifications = data.get("notifications", [])
        if notifications:
            st.dataframe(pd.DataFrame(notifications[:12]), hide_index=True, width="stretch")
        else:
            st.caption("No active notifications.")
    with right:
        st.subheader("Quick launch")
        st.page_link("pages/340_BioIntel_Classroom.py", label="Open Classroom", icon=":material/school:", width="stretch")
        st.page_link("pages/342_BioIntel_Academy_and_Lecture_Studio.py", label="Open Academy", icon=":material/play_circle:", width="stretch")
        st.page_link("pages/344_BioIntel_Examination_Command_Center.py", label="Open Examinations", icon=":material/assignment_turned_in:", width="stretch")


def _timetable_planner(service: EducationPhase7Service, platform: Any, actor: str, institution_id: str, subjects: list[dict[str, Any]], roles: set[str]) -> None:
    start_day = st.date_input("Planner week", value=datetime.now(timezone.utc).date(), key="edu7-planner-week")
    data = _run(lambda: service.timetable_calendar(actor, institution_id, start_day=start_day, days=7)) or {"entries": []}
    entries = data.get("entries", [])
    if entries:
        df = pd.DataFrame(entries)
        df["starts_at"] = pd.to_datetime(df["starts_at"])
        df["ends_at"] = pd.to_datetime(df["ends_at"])
        fig = px.timeline(
            df,
            x_start="starts_at",
            x_end="ends_at",
            y="student_group",
            color="subject_code",
            hover_data=["subject_name", "teacher_id", "room", "state"],
        )
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(_chart_layout(fig, "Weekly timetable planner"), width="stretch", config={"displaylogo": False, "scrollZoom": True})
    else:
        empty_state("No calendar events", "The selected week has no visible timetable or academic events.", icon="▦", action_hint="Choose another week or create the first scheduled event.")
    if not roles & (ADMIN_ROLES | TEACHER_ROLES) or not subjects:
        return
    create_tab, edit_tab = st.tabs(["Create event", "Edit or cancel"])
    subject_by_id = {row["id"]: row for row in subjects}
    with create_tab:
        with st.form("edu7-create-timetable"):
            subject_id = st.selectbox("Subject", list(subject_by_id), format_func=lambda value: f"{subject_by_id[value]['code']} · {subject_by_id[value]['name']}")
            c1, c2, c3 = st.columns(3)
            event_day = c1.date_input("Date", value=start_day)
            start_time = c2.time_input("Start", value=time(9, 0))
            end_time = c3.time_input("End", value=time(10, 0))
            c4, c5, c6 = st.columns(3)
            teacher_id = c4.text_input("Teacher", value=actor)
            group = c5.text_input("Student group", value="Class A")
            room = c6.text_input("Room", value="Room 101")
            meeting = st.text_input("Meeting/link reference (optional)")
            create = st.form_submit_button("Create conflict-checked event", type="primary")
        if create:
            starts = datetime.combine(event_day, start_time, tzinfo=timezone.utc).isoformat()
            ends = datetime.combine(event_day, end_time, tzinfo=timezone.utc).isoformat()
            result = _run(lambda: platform.create_timetable(actor, institution_id, subject_id, teacher_id, group, room, starts, ends, meeting))
            if result:
                st.success("Timetable event created.")
                st.rerun()
    with edit_tab:
        active = [row for row in entries if row.get("state") == "scheduled"]
        if not active:
            st.caption("No scheduled event is available to edit.")
        else:
            entry_by_id = {row["id"]: row for row in active}
            entry_id = st.selectbox("Event", list(entry_by_id), format_func=lambda value: f"{entry_by_id[value].get('subject_code')} · {entry_by_id[value]['starts_at']} · {entry_by_id[value]['room']}")
            entry = entry_by_id[entry_id]
            start_dt, end_dt = parse_time(entry["starts_at"]), parse_time(entry["ends_at"])
            with st.form(f"edu7-edit-event-{entry_id}"):
                c1, c2, c3 = st.columns(3)
                event_day = c1.date_input("Date", value=start_dt.date(), key=f"edit-day-{entry_id}")
                start_time = c2.time_input("Start", value=start_dt.time().replace(tzinfo=None), key=f"edit-start-{entry_id}")
                end_time = c3.time_input("End", value=end_dt.time().replace(tzinfo=None), key=f"edit-end-{entry_id}")
                c4, c5, c6 = st.columns(3)
                teacher_id = c4.text_input("Teacher", value=entry["teacher_id"], key=f"edit-teacher-{entry_id}")
                group = c5.text_input("Student group", value=entry["student_group"], key=f"edit-group-{entry_id}")
                room = c6.text_input("Room", value=entry["room"], key=f"edit-room-{entry_id}")
                meeting = st.text_input("Meeting/link", value=entry.get("meeting_id", ""), key=f"edit-meeting-{entry_id}")
                update = st.form_submit_button("Update event", type="primary")
            if update:
                starts = datetime.combine(event_day, start_time, tzinfo=timezone.utc).isoformat()
                ends = datetime.combine(event_day, end_time, tzinfo=timezone.utc).isoformat()
                result = _run(lambda: service.update_timetable_entry(actor, institution_id, entry_id, starts_at=starts, ends_at=ends, teacher_id=teacher_id, student_group=group, room=room, meeting_id=meeting))
                if result:
                    st.success("Event updated.")
                    st.rerun()
            with st.form(f"edu7-cancel-event-{entry_id}"):
                reason = st.text_input("Cancellation reason")
                cancel = st.form_submit_button("Cancel event", icon=":material/event_busy:")
            if cancel:
                result = _run(lambda: service.cancel_timetable_entry(actor, institution_id, entry_id, reason))
                if result:
                    st.warning("Event cancelled with audit evidence.")
                    st.rerun()


def _gradebook(service: EducationPhase7Service, actor: str, institution_id: str, subject_id: str) -> None:
    data = _run(lambda: service.editable_gradebook(actor, institution_id, subject_id))
    if not data:
        return
    rows = data["rows"]
    if not rows:
        st.info("Final submissions will appear in the editable gradebook.")
        return
    editor_df = pd.DataFrame(rows)[["submission_id", "student_id", "assignment_title", "max_marks", "late", "marks", "feedback"]]
    edited = st.data_editor(
        editor_df,
        hide_index=True,
        width="stretch",
        disabled=["submission_id", "student_id", "assignment_title", "max_marks", "late"],
        column_config={
            "submission_id": None,
            "student_id": st.column_config.TextColumn("Student", width="medium"),
            "assignment_title": st.column_config.TextColumn("Assessment", width="large"),
            "max_marks": st.column_config.NumberColumn("Max", format="%.1f"),
            "late": st.column_config.CheckboxColumn("Late"),
            "marks": st.column_config.NumberColumn("Marks", min_value=0.0, step=0.5),
            "feedback": st.column_config.TextColumn("Feedback", width="large"),
        },
        key=f"edu7-gradebook-{subject_id}",
    )
    reason = st.text_input("Revision reason for changed released grades", value="Bulk gradebook review", key=f"edu7-grade-reason-{subject_id}")
    if st.button("Save gradebook changes", type="primary", icon=":material/save:", key=f"edu7-save-grades-{subject_id}"):
        payload = edited.replace({np.nan: None}).to_dict(orient="records")
        result = _run(lambda: service.save_gradebook_rows(actor, institution_id, payload, reason=reason))
        if result:
            st.success(f"Saved {result['updated']} grade change(s); {result['skipped']} unchanged row(s).")
            st.rerun()
    released = [float(row["marks"]) / float(row["max_marks"]) * 100 for row in rows if row.get("marks") is not None and float(row["max_marks"]) > 0]
    if released:
        fig = px.histogram(x=released, nbins=10, labels={"x": "Percentage", "y": "Learners"})
        st.plotly_chart(_chart_layout(fig, "Grade distribution"), width="stretch", config={"displaylogo": False})


def _attendance_editor(service: EducationPhase7Service, platform: Any, actor: str, institution_id: str, subject_id: str) -> None:
    sessions = platform._all(
        "SELECT * FROM attendance_sessions WHERE institution_id=? AND subject_id=? ORDER BY session_date DESC,period DESC LIMIT 50",
        (institution_id, subject_id),
    )
    create_col, existing_col = st.columns([.42, .58], gap="large")
    with create_col:
        with st.form(f"edu7-new-attendance-{subject_id}"):
            session_day = st.date_input("Session date", value=date.today())
            period = st.text_input("Period", value="P1")
            create = st.form_submit_button("Create roster", type="primary")
        if create:
            result = _run(lambda: platform.attendance_session(actor, institution_id, subject_id, session_day.isoformat(), period))
            if result:
                st.session_state.edu7_attendance_session = result["id"]
                st.rerun()
    with existing_col:
        if not sessions:
            st.caption("Create the first attendance roster.")
            return
        session_by_id = {row["id"]: row for row in sessions}
        current = st.session_state.get("edu7_attendance_session")
        index = list(session_by_id).index(current) if current in session_by_id else 0
        session_id = st.selectbox("Attendance session", list(session_by_id), index=index, format_func=lambda value: f"{session_by_id[value]['session_date']} · {session_by_id[value]['period']} · {session_by_id[value]['state']}")
        st.session_state.edu7_attendance_session = session_id
    data = _run(lambda: service.attendance_roster(actor, institution_id, subject_id, session_id))
    if not data:
        return
    locked = data["session"]["state"] != "open"
    editor = st.data_editor(
        pd.DataFrame(data["rows"]),
        hide_index=True,
        width="stretch",
        disabled=True if locked else ["student_id"],
        column_config={
            "student_id": st.column_config.TextColumn("Student", width="medium"),
            "status": st.column_config.SelectboxColumn("Status", options=["present", "absent", "late", "excused"], required=True),
            "note": st.column_config.TextColumn("Note", width="large"),
        },
        key=f"edu7-attendance-editor-{session_id}",
    )
    c1, c2 = st.columns(2)
    if c1.button("Save roster", type="primary", disabled=locked, key=f"save-roster-{session_id}"):
        result = _run(lambda: service.save_attendance_roster(actor, session_id, editor.to_dict(orient="records"), lock=False))
        if result:
            st.success("Attendance roster saved.")
            st.rerun()
    if c2.button("Save and lock session", disabled=locked, key=f"lock-roster-{session_id}"):
        result = _run(lambda: service.save_attendance_roster(actor, session_id, editor.to_dict(orient="records"), lock=True))
        if result:
            st.success("Attendance session locked.")
            st.rerun()


def _assignment_kanban(service: EducationPhase7Service, actor: str, institution_id: str, subject_id: str) -> None:
    board = _run(lambda: service.assignment_board(actor, institution_id, subject_id)) or {"buckets": {}}
    labels = [
        ("draft", "Draft"), ("published", "Published"), ("due_soon", "Due soon"),
        ("submitted", "Submitted"), ("late", "Late"), ("under_review", "Review"), ("graded", "Graded"),
    ]
    lanes = []
    for key, label in labels:
        cards = []
        for row in board["buckets"].get(key, []):
            cards.append(
                '<article class="edu7-task"><strong>' + html.escape(str(row["title"])) + '</strong>'
                f'<small>{row.get("subject_code", "")} · due {str(row.get("due_at", ""))[:10]}</small>'
                f'<small>{int(row.get("submitted_count") or 0)} submitted · {int(row.get("graded_count") or 0)} graded · {int(row.get("late_count") or 0)} late</small></article>'
            )
        lanes.append(f'<section class="edu7-lane"><h4>{label} · {len(cards)}</h4>{"".join(cards) or "<small>No items</small>"}</section>')
    st.markdown('<div class="edu7-board">' + "".join(lanes) + "</div>", unsafe_allow_html=True)


def _rubric_workspace(service: EducationPhase7Service, platform: Any, actor: str, institution_id: str, subject_id: str) -> None:
    assignments = platform._all(
        "SELECT * FROM assignments WHERE institution_id=? AND subject_id=? ORDER BY due_at DESC,created_at DESC",
        (institution_id, subject_id),
    )
    if not assignments:
        st.info("Create an assignment before building a rubric.")
        return
    by_id = {row["id"]: row for row in assignments}
    assignment_id = st.selectbox(
        "Assignment",
        list(by_id),
        format_func=lambda value: f"{by_id[value]['title']} · {float(by_id[value]['max_marks']):g} marks",
        key="edu7-rubric-assignment",
    )
    assignment = by_id[assignment_id]
    rubric_data = _run(lambda: service.assignment_rubric(actor, assignment_id)) or {"rubric": None, "criteria": []}
    mode = st.segmented_control("Rubric workspace", ["Builder", "Grade submissions"], default="Builder", key="edu7-rubric-mode")
    if mode == "Builder":
        existing = rubric_data.get("criteria") or []
        rows = [
            {
                "title": row.get("title", ""),
                "description": row.get("description", ""),
                "max_marks": float(row.get("max_marks") or 0),
            }
            for row in existing
        ] or [
            {"title": "Scientific accuracy", "description": "Correct concepts and evidence.", "max_marks": float(assignment["max_marks"]) * .6},
            {"title": "Clarity and reasoning", "description": "Clear, structured explanation.", "max_marks": float(assignment["max_marks"]) * .4},
        ]
        title = st.text_input(
            "Rubric title",
            value=(rubric_data.get("rubric") or {}).get("title") or f"{assignment['title']} rubric",
            key=f"rubric-title-{assignment_id}",
        )
        edited = st.data_editor(
            pd.DataFrame(rows),
            hide_index=True,
            width="stretch",
            num_rows="dynamic",
            column_config={
                "title": st.column_config.TextColumn("Criterion", required=True, width="medium"),
                "description": st.column_config.TextColumn("Evidence description", width="large"),
                "max_marks": st.column_config.NumberColumn("Maximum marks", min_value=0.01, step=.5, required=True),
            },
            key=f"rubric-builder-{assignment_id}",
        )
        total = float(pd.to_numeric(edited.get("max_marks", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
        c1, c2 = st.columns(2)
        c1.metric("Rubric total", f"{total:g}")
        c2.metric("Assignment maximum", f"{float(assignment['max_marks']):g}", delta=f"{total-float(assignment['max_marks']):+.1f}")
        if st.button("Save rubric", type="primary", key=f"save-rubric-{assignment_id}"):
            criteria = edited.fillna("").to_dict(orient="records")
            result = _run(lambda: service.save_assignment_rubric(actor, assignment_id, title, criteria))
            if result:
                st.success("Rubric saved with auditable criterion weights.")
                st.rerun()
        return
    if not rubric_data.get("rubric"):
        st.warning("Save a rubric before criterion-based grading.")
        return
    submissions = platform._all(
        """SELECT s.*,COALESCE(g.marks,0) current_marks,COALESCE(g.feedback,'') current_feedback
        FROM submissions s LEFT JOIN grades g ON g.submission_id=s.id
        WHERE s.assignment_id=? AND s.state IN ('submitted','graded') ORDER BY s.submitted_at DESC""",
        (assignment_id,),
    )
    if not submissions:
        empty_state("Grading queue is clear", "No sealed final submissions currently require a grade.", icon="✓", action_hint="New final submissions will appear here automatically.")
        return
    sub_by_id = {row["id"]: row for row in submissions}
    submission_id = st.selectbox(
        "Submission",
        list(sub_by_id),
        format_func=lambda value: f"{sub_by_id[value]['student_id']} · {sub_by_id[value]['state']}",
        key=f"rubric-submission-{assignment_id}",
    )
    submission = sub_by_id[submission_id]
    with st.expander("Submission evidence", expanded=True):
        st.write(submission.get("body") or "No text response.")
        if submission.get("file_name"):
            st.caption(f"Attachment: {submission['file_name']} · SHA-256 {submission.get('sha256','')[:16]}…")
    current_scores = {
        row["criterion_id"]: row
        for row in platform._all("SELECT * FROM education_rubric_scores WHERE submission_id=?", (submission_id,))
    }
    score_rows = []
    for criterion in rubric_data["criteria"]:
        prior = current_scores.get(criterion["id"], {})
        score_rows.append(
            {
                "criterion_id": criterion["id"],
                "criterion": criterion["title"],
                "maximum": float(criterion["max_marks"]),
                "marks": float(prior.get("marks") or 0),
                "feedback": prior.get("feedback") or "",
            }
        )
    scored = st.data_editor(
        pd.DataFrame(score_rows),
        hide_index=True,
        width="stretch",
        disabled=["criterion_id", "criterion", "maximum"],
        column_config={
            "criterion_id": None,
            "criterion": st.column_config.TextColumn("Criterion", width="medium"),
            "maximum": st.column_config.NumberColumn("Maximum"),
            "marks": st.column_config.NumberColumn("Awarded", min_value=0.0, step=.5),
            "feedback": st.column_config.TextColumn("Criterion feedback", width="large"),
        },
        key=f"rubric-score-{submission_id}",
    )
    total = float(pd.to_numeric(scored["marks"], errors="coerce").fillna(0).sum())
    st.metric("Calculated score", f"{total:g} / {float(assignment['max_marks']):g}")
    overall = st.text_area("Overall feedback", value=submission.get("current_feedback") or "", key=f"rubric-overall-{submission_id}")
    reason = st.text_input("Revision reason (required when changing an existing grade)", key=f"rubric-reason-{submission_id}")
    if st.button("Save rubric grade", type="primary", key=f"save-rubric-grade-{submission_id}"):
        payload = scored[["criterion_id", "marks", "feedback"]].fillna("").to_dict(orient="records")
        result = _run(lambda: service.grade_with_rubric(actor, submission_id, payload, overall_feedback=overall, reason=reason))
        if result:
            st.success(f"Rubric grade saved: {result['total_marks']:g}/{float(result['max_marks']):g}.")
            st.rerun()


def _classroom(service: EducationPhase7Service, platform: Any, actor: str, institution_id: str) -> None:
    roles = {row["role"] for row in platform.membership(actor, institution_id)}
    subjects = _subjects(platform, actor, institution_id)
    mode = st.segmented_control("Classroom workspace", ["Timetable", "Gradebook", "Attendance", "Assignments"], default="Timetable", key="edu7-classroom-mode")
    if mode == "Timetable":
        _timetable_planner(service, platform, actor, institution_id, subjects, roles)
        return
    if not subjects:
        empty_state("No visible subjects", "Your current role has no active subject workspace in this institution.", icon="▤", action_hint="Ask an administrator to assign a subject or switch institution context.")
        return
    subject_by_id = {row["id"]: row for row in subjects}
    subject_id = st.selectbox("Subject", list(subject_by_id), format_func=lambda value: f"{subject_by_id[value]['code']} · {subject_by_id[value]['name']}", key="edu7-classroom-subject")
    if mode == "Gradebook":
        if roles & (ADMIN_ROLES | TEACHER_ROLES):
            _gradebook(service, actor, institution_id, subject_id)
        else:
            data = _run(lambda: service.gradebook(actor, institution_id, subject_id))
            if data:
                st.dataframe(pd.DataFrame(data["rows"]), hide_index=True, width="stretch")
    elif mode == "Attendance":
        if roles & (ADMIN_ROLES | TEACHER_ROLES):
            _attendance_editor(service, platform, actor, institution_id, subject_id)
        else:
            heat = _run(lambda: service.attendance_heatmap(actor, institution_id, subject_id=subject_id))
            if heat:
                st.dataframe(pd.DataFrame(heat["summary"]), hide_index=True, width="stretch")
    elif mode == "Assignments":
        assignment_mode = st.segmented_control("Assignment workspace", ["Board", "Rubrics"], default="Board", key="edu7-assignment-mode")
        if assignment_mode == "Board":
            _assignment_kanban(service, actor, institution_id, subject_id)
        elif roles & (ADMIN_ROLES | TEACHER_ROLES):
            _rubric_workspace(service, platform, actor, institution_id, subject_id)
        else:
            st.info("Rubric authoring and grading are available to authorized teaching staff.")


def _curriculum_tree(data: dict[str, Any]) -> str:
    sections = data.get("sections", [])
    if not sections:
        return '<div class="edu7-detail">No curriculum items yet.</div>'
    children: dict[str | None, list[dict[str, Any]]] = {}
    for row in sections:
        children.setdefault(row.get("parent_id"), []).append(row)
    def render(parent: str | None) -> str:
        parts = []
        for row in sorted(children.get(parent, []), key=lambda item: (int(item.get("position") or 0), item["title"])):
            parts.append(f'<li><span class="edu-chip">{row["section_type"]}</span> <strong>{row["title"]}</strong>{render(row["id"])}</li>')
        return "<ul>" + "".join(parts) + "</ul>" if parts else ""
    return '<div class="edu7-detail">' + render(None) + "</div>"


def _academy(service: EducationPhase7Service, platform: Any, actor: str, institution_id: str) -> None:
    roles = {row["role"] for row in platform.membership(actor, institution_id)}
    courses = _courses(platform, actor, institution_id)
    if not courses:
        empty_state("No Academy courses", "No published or role-visible course is available in this workspace.", icon="▷", action_hint="Publish a course or enroll the learner to begin.")
        return
    course_by_id = {row["id"]: row for row in courses}
    course_id = st.selectbox("Course", list(course_by_id), format_func=lambda value: course_by_id[value]["title"], key="edu7-course")
    data = _run(lambda: service.curriculum(actor, course_id))
    if not data:
        return
    course = data["course"]
    st.markdown(f"### {course['title']}")
    st.caption(course.get("description") or "No course description.")
    mode = st.segmented_control("Academy workspace", ["Curriculum", "Learning player", "Course progress"], default="Curriculum", key="edu7-academy-mode")
    if mode == "Curriculum":
        st.markdown(_curriculum_tree(data), unsafe_allow_html=True)
        can_edit = actor == course["educator_id"] or bool(roles & ADMIN_ROLES)
        if can_edit:
            with st.form(f"edu7-add-section-{course_id}"):
                title = st.text_input("Item title")
                section_type = st.selectbox("Item type", ["section", "lesson", "assessment", "resource"])
                parent_options = [None] + [row["id"] for row in data["sections"]]
                parent_id = st.selectbox("Parent", parent_options, format_func=lambda value: "Top level" if value is None else next(row["title"] for row in data["sections"] if row["id"] == value))
                position = st.number_input("Position", min_value=0, value=len(data["sections"]), step=1)
                add = st.form_submit_button("Add curriculum item", type="primary")
            if add:
                result = _run(lambda: service.create_course_section(actor, course_id, title, section_type=section_type, parent_id=parent_id, position=int(position)))
                if result:
                    st.success("Curriculum item added.")
                    st.rerun()
            if data["sections"]:
                order_df = pd.DataFrame([{"id": row["id"], "title": row["title"], "type": row["section_type"], "position": int(row["position"])} for row in data["sections"]])
                edited = st.data_editor(order_df, hide_index=True, width="stretch", disabled=["id", "title", "type"], column_config={"id": None, "position": st.column_config.NumberColumn("Order", min_value=0, step=1)})
                if st.button("Apply curriculum order", key=f"apply-course-order-{course_id}"):
                    ordered = edited.sort_values(["position", "title"])["id"].tolist()
                    result = _run(lambda: service.reorder_course_sections(actor, course_id, ordered))
                    if result:
                        st.success("Curriculum reordered.")
                        st.rerun()
    elif mode == "Learning player":
        lectures = [row for row in data["lectures"] if row["state"] == "published" or actor == row["educator_id"] or roles & ADMIN_ROLES]
        if not lectures:
            empty_state("No available lectures", "This course does not yet contain a permission-visible published lecture.", icon="▶", action_hint="Add and publish a lecture from the curriculum builder.")
            return
        lecture_by_id = {row["id"]: row for row in lectures}
        lecture_id = st.selectbox("Lecture", list(lecture_by_id), format_func=lambda value: lecture_by_id[value]["title"], key="edu7-lecture")
        lecture = lecture_by_id[lecture_id]
        can_edit = actor == lecture["educator_id"] or bool(roles & ADMIN_ROLES)
        player, notebook = st.columns([1.35, .65], gap="large")
        with player:
            media = Path(lecture.get("video_path") or "")
            if media.is_file():
                st.video(str(media))
            else:
                st.warning("Lecture media is not available on this machine.")
            position = render_playback_evidence_controls(service, platform, actor, lecture)
            if st.button("Bookmark current position", key=f"bookmark-position-{lecture_id}"):
                result = _run(lambda: service.add_lecture_bookmark(actor, lecture_id, position, f"Bookmark at {int(position)}s"))
                if result:
                    st.toast("Bookmark saved.")
        with notebook:
            st.subheader("Lecture notebook")
            notebook_data = _run(lambda: service.lecture_notebook(actor, lecture_id)) or {"chapters": [], "notes": [], "bookmarks": []}
            if notebook_data["chapters"]:
                st.dataframe(pd.DataFrame(notebook_data["chapters"])[["title", "start_seconds"]], hide_index=True, width="stretch")
            note = st.text_area("Note", key=f"lecture-note-{lecture_id}")
            if st.button("Save note", key=f"save-note-{lecture_id}"):
                result = _run(lambda: service.save_lecture_note(actor, lecture_id, note, position_seconds=position))
                if result:
                    st.toast("Note saved.")
                    st.rerun()
            if notebook_data["notes"]:
                st.dataframe(pd.DataFrame(notebook_data["notes"])[["position_seconds", "body", "created_at"]], hide_index=True, width="stretch")
            if can_edit:
                with st.form(f"add-chapter-{lecture_id}"):
                    chapter_title = st.text_input("Chapter title")
                    chapter_start = st.number_input("Start second", min_value=0.0, step=10.0)
                    add = st.form_submit_button("Add chapter")
                if add:
                    result = _run(lambda: service.add_lecture_chapter(actor, lecture_id, chapter_title, chapter_start))
                    if result:
                        st.success("Chapter added.")
                        st.rerun()
        st.divider()
        st.subheader("Searchable lecture transcript")
        transcripts = _run(lambda: service.lecture_transcripts(actor, lecture_id)) or []
        if can_edit:
            with st.expander("Transcript editor", expanded=not bool(transcripts)):
                language = st.selectbox("Transcript language", ["English", "Hindi", "Hinglish"], key=f"transcript-language-{lecture_id}")
                existing = next((row for row in transcripts if row.get("language") == language), None)
                body = st.text_area("Transcript", value=(existing or {}).get("body", ""), height=220, key=f"transcript-body-{lecture_id}-{language}")
                if st.button("Save transcript", type="primary", key=f"save-transcript-{lecture_id}-{language}"):
                    if _run(lambda: service.save_lecture_transcript(actor, lecture_id, body, language=language)):
                        st.success("Transcript saved and indexed for desktop search.")
                        st.rerun()
        if transcripts:
            by_language = {row["language"]: row for row in transcripts}
            selected_language = st.selectbox("View language", list(by_language), key=f"view-transcript-{lecture_id}")
            transcript_text = str(by_language[selected_language].get("body") or "")
            query = st.text_input("Search transcript", placeholder="Search a concept, term or phrase", key=f"search-transcript-{lecture_id}")
            chunks = [part.strip() for part in transcript_text.replace("\r", "").split("\n") if part.strip()]
            if not chunks:
                chunks = [part.strip() for part in transcript_text.split(". ") if part.strip()]
            matches = chunks if not query.strip() else [part for part in chunks if query.casefold() in part.casefold()]
            st.caption(f"{len(matches)} matching transcript segments")
            for idx, part in enumerate(matches[:100], start=1):
                escaped = html.escape(part)
                if query.strip():
                    # Highlight without allowing transcript HTML to execute.
                    escaped_query = html.escape(query.strip())
                    escaped = escaped.replace(escaped_query, f"<mark>{escaped_query}</mark>")
                st.markdown(f'<div class="edu7-detail"><small>Segment {idx}</small><br>{escaped}</div>', unsafe_allow_html=True)
        else:
            empty_state("Transcript not published", "Searchable lecture evidence is not available for this lecture yet.", icon="⌕", action_hint="An educator can publish a reviewed transcript in the lecture workspace.")
    else:
        lectures = data["lectures"]
        progress_rows = platform._all(
            """SELECT l.title,w.seconds,w.completed,l.duration_seconds FROM lectures l
            LEFT JOIN watch_progress w ON w.lecture_id=l.id AND w.user_id=? WHERE l.course_id=? ORDER BY l.created_at""",
            (actor, course_id),
        )
        if progress_rows:
            df = pd.DataFrame(progress_rows)
            df["percent"] = np.where(df["duration_seconds"].astype(float) > 0, np.minimum(100, df["seconds"].fillna(0).astype(float) / df["duration_seconds"].astype(float) * 100), 0)
            fig = px.bar(df, x="title", y="percent", color="completed", labels={"percent": "Completion %", "title": "Lecture"})
            st.plotly_chart(_chart_layout(fig, "Lecture progress"), width="stretch", config={"displaylogo": False})
        st.dataframe(pd.DataFrame(progress_rows), hide_index=True, width="stretch")


def render_academy_intelligence_workspace(
    root: Path, platform: Any, actor: str, institution_id: str
) -> None:
    """Render the production lecture player, transcripts and verified media pipeline."""
    player, telemetry, processing = st.tabs(
        ["Player, chapters & transcripts", "Playback evidence", "Media processing"]
    )
    with player:
        _academy(EducationPhase7Service(platform, root=root), platform, actor, institution_id)
    with telemetry:
        from .phase15_ui import render_academy_media_telemetry

        render_academy_media_telemetry(root, platform, actor, institution_id)
    with processing:
        from .phase16_ui import render_academy_media_pipeline

        render_academy_media_pipeline(root, platform, actor, institution_id)


def _knowledge_graph_figure(graph: dict[str, Any]) -> go.Figure:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    if not nodes:
        return _chart_layout(go.Figure(), "Concept knowledge graph")
    positions: dict[str, tuple[float, float]] = {}
    count = len(nodes)
    for idx, node in enumerate(nodes):
        angle = 2 * math.pi * idx / max(1, count)
        radius = 1.0 + 0.16 * (idx % 3)
        positions[str(node["id"])] = (math.cos(angle) * radius, math.sin(angle) * radius)
    edge_x, edge_y = [], []
    for edge in edges:
        source, target = positions.get(str(edge.get("source"))), positions.get(str(edge.get("target")))
        if source and target:
            edge_x += [source[0], target[0], None]
            edge_y += [source[1], target[1], None]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=edge_x, y=edge_y, mode="lines", line=dict(width=1), hoverinfo="skip", name="Prerequisite"))
    fig.add_trace(go.Scatter(
        x=[positions[str(node["id"])][0] for node in nodes],
        y=[positions[str(node["id"])][1] for node in nodes],
        mode="markers+text",
        text=[str(node.get("code") or node.get("label", ""))[:14] for node in nodes],
        textposition="top center",
        customdata=[[node.get("label"), node.get("mastery", 0), node.get("confidence", 0)] for node in nodes],
        hovertemplate="<b>%{customdata[0]}</b><br>Mastery %{customdata[1]:.0%}<br>Confidence %{customdata[2]:.0%}<extra></extra>",
        marker=dict(size=[24 + 22 * float(node.get("confidence", 0)) for node in nodes], color=[float(node.get("mastery", 0)) for node in nodes], colorscale="Turbo", cmin=0, cmax=1, showscale=True, colorbar=dict(title="Mastery")),
        name="Concepts",
    ))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, scaleanchor="x", scaleratio=1)
    return _chart_layout(fig, "Interactive concept mastery graph")


def _shiro(service: EducationPhase7Service, platform: Any, actor: str, institution_id: str) -> None:
    subjects = _subjects(platform, actor, institution_id)
    roles = {row["role"] for row in platform.membership(actor, institution_id)}
    subject_id = None
    if subjects:
        subject_by_id = {row["id"]: row for row in subjects}
        subject_id = st.selectbox("Subject context", list(subject_by_id), format_func=lambda value: f"{subject_by_id[value]['code']} · {subject_by_id[value]['name']}", key="edu7-shiro-subject")
    graph = _run(lambda: service.knowledge_graph(actor, institution_id, student_id=actor if roles & STUDENT_ROLES else None, subject_id=subject_id))
    if graph:
        selected = st.plotly_chart(_knowledge_graph_figure(graph), width="stretch", config={"displaylogo": False, "scrollZoom": True}, on_select="rerun", selection_mode="points", key="edu7-mastery-graph")
        if graph.get("recommendations"):
            with st.expander("Learning recommendations", expanded=False):
                st.dataframe(pd.DataFrame(graph["recommendations"]), hide_index=True, width="stretch")
    st.divider()
    conversations = _run(lambda: service.conversations(actor, institution_id, limit=100)) or []
    active = [row for row in conversations if row.get("state") == "active"]
    side, main = st.columns([.28, .72], gap="large")
    with side:
        with st.form("edu7-new-chat"):
            title = st.text_input("Conversation title", value="Study session")
            mode = st.selectbox("Mode", ["guided_learning", "revision", "teacher_planning"])
            language = st.selectbox("Language", ["English", "Hindi", "Hinglish"])
            create = st.form_submit_button("New conversation", type="primary")
        if create:
            result = _run(lambda: service.create_conversation(actor, institution_id, subject_id=subject_id, title=title, mode=mode, language=language))
            if result:
                st.session_state.edu7_conversation = result["id"]
                st.rerun()
        if not active:
            st.caption("Create a grounded conversation.")
            selected_id = None
        else:
            by_id = {row["id"]: row for row in active}
            remembered = st.session_state.get("edu7_conversation")
            index = list(by_id).index(remembered) if remembered in by_id else 0
            selected_id = st.selectbox("Conversations", list(by_id), index=index, format_func=lambda value: by_id[value]["title"])
            st.session_state.edu7_conversation = selected_id
            with st.expander("Conversation actions"):
                rename = st.text_input("Rename", value=by_id[selected_id]["title"], key=f"rename-{selected_id}")
                if st.button("Apply name", key=f"apply-rename-{selected_id}"):
                    if _run(lambda: service.rename_conversation(actor, selected_id, rename)):
                        st.rerun()
                if st.button("Archive", key=f"archive-{selected_id}"):
                    if _run(lambda: service.archive_conversation(actor, selected_id)):
                        st.session_state.pop("edu7_conversation", None)
                        st.rerun()
                confirm = st.checkbox("Confirm permanent deletion", key=f"confirm-delete-{selected_id}")
                if st.button("Delete", disabled=not confirm, key=f"delete-{selected_id}"):
                    if _run(lambda: service.delete_conversation(actor, selected_id)) is None:
                        st.session_state.pop("edu7_conversation", None)
                        st.rerun()
    with main:
        st.markdown('<div class="edu7-chat-shell">', unsafe_allow_html=True)
        if selected_id:
            conversation = _run(lambda: service.conversation(actor, selected_id))
            if conversation:
                for message in conversation["messages"]:
                    avatar = ":material/person:" if message["role"] == "user" else ":material/psychology:"
                    with st.chat_message(message["role"], avatar=avatar):
                        st.markdown(message["body"])
                        citations = message.get("citations") or []
                        if citations:
                            st.markdown("".join(f'<span class="edu7-citation">{str(item.get("title") or item.get("source") or "Evidence")}</span>' for item in citations), unsafe_allow_html=True)
                            with st.expander("Evidence details"):
                                st.json(citations, expanded=False)
                prompt = st.chat_input("Ask Shiro using indexed course evidence", key=f"chat-input-{selected_id}")
                if prompt:
                    result = _run(lambda: service.ask_conversation(actor, selected_id, prompt))
                    if result:
                        st.rerun()
        else:
            st.info("Select or create a conversation.")
        st.markdown("</div>", unsafe_allow_html=True)


def _exam_figures(data: dict[str, Any]) -> tuple[go.Figure, go.Figure]:
    scores = data.get("scores", [])
    exam = data.get("exam", {})
    values = [float(row["final_score"]) for row in scores]
    percentages = [value / float(exam.get("max_marks") or 1) * 100 for value in values]
    histogram = px.histogram(x=percentages, nbins=10, labels={"x": "Score %", "y": "Candidates"})
    questions = pd.DataFrame(data.get("question_rows", []))
    if questions.empty:
        matrix = go.Figure()
    else:
        pivot = questions.pivot_table(index="difficulty", columns="bloom_level", values="id", aggfunc="count", fill_value=0)
        matrix = px.imshow(pivot, text_auto=True, aspect="auto", labels=dict(x="Bloom level", y="Difficulty", color="Questions"))
    return _chart_layout(histogram, "Score distribution"), _chart_layout(matrix, "Question blueprint")


def _live_monitor(service: EducationPhase7Service, actor: str, exam_id: str) -> None:
    monitor = _run(lambda: service.exams.monitor(actor, exam_id))
    if not monitor:
        return
    sessions = monitor.get("sessions", [])
    cards = '<div class="edu7-status-grid">' + "".join(
        f'<article class="edu7-status"><strong>{row["student_id"]}</strong><small>Attempt {row.get("attempt_number",1)} · {row.get("state")}<br>Answered {row.get("answered",0)} · events {row.get("integrity_events",0)}<br>Last save {str(row.get("last_seen_at") or "")[-8:]}</small></article>'
        for row in sessions[:24]
    ) + "</div>"
    st.markdown(cards if sessions else '<div class="edu7-detail">No candidate sessions.</div>', unsafe_allow_html=True)


def _examinations(service: EducationPhase7Service, actor: str, institution_id: str) -> None:
    exams = _run(lambda: service.exams.list_exams(actor, institution_id)) or []
    if not exams:
        empty_state("No visible examinations", "No examination currently matches this role, subject and institution context.", icon="◉", action_hint="Create, publish or select an examination to continue.")
        return
    exam_by_id = {row["id"]: row for row in exams}
    exam_id = st.selectbox("Examination", list(exam_by_id), format_func=lambda value: f"{exam_by_id[value]['title']} · {exam_by_id[value]['state']}", key="edu7-exam")
    mode = st.segmented_control("Examination workspace", ["Analytics", "Live monitor", "Moderation"], default="Analytics", key="edu7-exam-mode")
    if mode == "Analytics":
        data = _run(lambda: service.exam_analytics_phase7(actor, exam_id))
        if data:
            summary = data["summary"]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Candidates", summary["candidates"])
            c2.metric("Average", f"{summary.get('average_percent') or 0:.1f}%")
            c3.metric("Pass rate", f"{summary.get('pass_rate') or 0:.1f}%")
            c4.metric("Live", summary["active"])
            with st.expander("Passing policy", expanded=False):
                passing = st.number_input("Passing percentage", min_value=1.0, max_value=100.0, value=float(summary.get("passing_percent") or 40), step=1.0, key=f"passing-{exam_id}")
                if st.button("Save passing threshold", key=f"save-passing-{exam_id}"):
                    if _run(lambda: service.set_exam_passing_percent(actor, exam_id, passing)):
                        st.rerun()
            left, right = st.columns(2, gap="large")
            hist, matrix = _exam_figures(data)
            left.plotly_chart(hist, width="stretch", config={"displaylogo": False})
            right.plotly_chart(matrix, width="stretch", config={"displaylogo": False})
            st.dataframe(pd.DataFrame(data["question_rows"]), hide_index=True, width="stretch")
    elif mode == "Live monitor":
        top = st.container(horizontal=True)
        top.caption("Desktop control-room view. Server state remains authoritative.")
        auto = st.toggle("Auto-refresh every 10 seconds", value=False, key=f"auto-monitor-{exam_id}")
        if st.button("Refresh monitor", icon=":material/refresh:", key=f"refresh-monitor-{exam_id}"):
            st.rerun()
        def draw_monitor() -> None:
            _live_monitor(service, actor, exam_id)
        fragment = getattr(st, "fragment", None)
        if auto and callable(fragment):
            rendered = fragment(run_every=timedelta(seconds=10))(draw_monitor)
            if callable(rendered):
                rendered()
            else:
                draw_monitor()
        else:
            draw_monitor()
    else:
        events = _run(lambda: service.moderation_timeline(actor, exam_id)) or []
        with st.form(f"moderation-{exam_id}"):
            event_type = st.selectbox("Event", ["review_started", "review_completed", "score_flagged", "revaluation_requested", "revaluation_resolved", "publication_approved"])
            reason = st.text_area("Reason/evidence")
            record = st.form_submit_button("Record moderation event", type="primary")
        if record:
            result = _run(lambda: service.record_moderation_event(actor, exam_id, event_type, reason=reason))
            if result:
                st.success("Moderation event recorded.")
                st.rerun()
        if events:
            st.dataframe(pd.DataFrame(events), hide_index=True, width="stretch")


def _pulse_network(publications: list[dict[str, Any]]) -> go.Figure:
    author_counts: dict[str, int] = {}
    links: dict[tuple[str, str], int] = {}
    for row in publications[:250]:
        try:
            authors = json.loads(row.get("authors_json") or "[]")
        except (TypeError, ValueError):
            authors = []
        names = [str(item.get("name") if isinstance(item, dict) else item).strip() for item in authors if str(item).strip()][:8]
        for name in names:
            author_counts[name] = author_counts.get(name, 0) + 1
        for i, source in enumerate(names):
            for target in names[i + 1:]:
                key = tuple(sorted((source, target)))
                links[key] = links.get(key, 0) + 1
    names = sorted(author_counts, key=author_counts.get, reverse=True)[:35]
    positions = {name: (math.cos(2 * math.pi * idx / max(1, len(names))), math.sin(2 * math.pi * idx / max(1, len(names)))) for idx, name in enumerate(names)}
    edge_x, edge_y = [], []
    for (source, target), weight in links.items():
        if source in positions and target in positions:
            edge_x += [positions[source][0], positions[target][0], None]
            edge_y += [positions[source][1], positions[target][1], None]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=edge_x, y=edge_y, mode="lines", line=dict(width=1), hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=[positions[name][0] for name in names], y=[positions[name][1] for name in names],
        mode="markers+text", text=[name[:16] for name in names], textposition="top center",
        marker=dict(size=[12 + 4 * author_counts[name] for name in names], color=[author_counts[name] for name in names], colorscale="Viridis", showscale=True),
        customdata=[[name, author_counts[name]] for name in names], hovertemplate="%{customdata[0]}<br>papers %{customdata[1]}<extra></extra>",
    ))
    fig.update_xaxes(visible=False); fig.update_yaxes(visible=False, scaleanchor="x", scaleratio=1)
    return _chart_layout(fig, "Author collaboration network")


def _scientific_viewers() -> None:
    mode = st.segmented_control("Scientific viewer", ["Sequence", "Expression matrix", "Volcano"], default="Sequence", key="edu7-science-viewer")
    if mode == "Sequence":
        text = st.text_area("Paste FASTA sequence", value=">example\nATGCGTACGTAGCTAGCTAGCTAGCTAGCATCGATCGATCGATCG", height=150)
        sequence = "".join(line.strip() for line in text.splitlines() if not line.startswith(">") and line.strip()).upper()
        sequence = "".join(base for base in sequence if base in "ACGTN")
        if sequence:
            counts = {base: sequence.count(base) for base in "ACGTN"}
            gc = (counts["G"] + counts["C"]) / max(1, len(sequence)) * 100
            c1, c2, c3 = st.columns(3); c1.metric("Length", len(sequence)); c2.metric("GC", f"{gc:.1f}%"); c3.metric("Ambiguous N", counts["N"])
            fig = px.bar(x=list(counts), y=list(counts.values()), labels={"x": "Base", "y": "Count"})
            st.plotly_chart(_chart_layout(fig, "Nucleotide composition"), width="stretch", config={"displaylogo": False})
            st.code(" ".join(sequence[i:i+10] for i in range(0, min(len(sequence), 1000), 10)), language=None)
    elif mode == "Expression matrix":
        uploaded = st.file_uploader("Upload CSV: rows=features, columns=samples", type=["csv"], key="edu7-expression-upload")
        if uploaded:
            df = pd.read_csv(uploaded, index_col=0)
            numeric = df.select_dtypes(include=[np.number]).iloc[:100, :40]
            if numeric.empty:
                st.error("No numeric matrix columns found.")
            else:
                fig = px.imshow(numeric, aspect="auto", color_continuous_scale="RdBu_r")
                st.plotly_chart(_chart_layout(fig, "Expression heatmap"), width="stretch", config={"displaylogo": False})
                centered = numeric.T - numeric.T.mean(axis=0)
                u, s, _ = np.linalg.svd(centered.fillna(0).to_numpy(), full_matrices=False)
                pca = pd.DataFrame({"PC1": u[:, 0] * s[0], "PC2": u[:, 1] * s[1] if len(s) > 1 else 0, "Sample": centered.index})
                fig2 = px.scatter(pca, x="PC1", y="PC2", hover_name="Sample")
                st.plotly_chart(_chart_layout(fig2, "Sample PCA"), width="stretch", config={"displaylogo": False})
    else:
        uploaded = st.file_uploader("Upload CSV with log2FC and pvalue columns", type=["csv"], key="edu7-volcano-upload")
        if uploaded:
            df = pd.read_csv(uploaded)
            if not {"log2FC", "pvalue"}.issubset(df.columns):
                st.error("CSV must contain log2FC and pvalue columns.")
            else:
                df = df.copy(); df["-log10p"] = -np.log10(np.clip(df["pvalue"].astype(float), 1e-300, None)); df["significant"] = (df["pvalue"] < .05) & (df["log2FC"].abs() >= 1)
                fig = px.scatter(df, x="log2FC", y="-log10p", color="significant", hover_data=list(df.columns[:4]))
                st.plotly_chart(_chart_layout(fig, "Volcano plot"), width="stretch", config={"displaylogo": False})


def _research(service: EducationPhase7Service, platform: Any, actor: str, institution_id: str) -> None:
    mode = st.segmented_control("Research workspace", ["Science Pulse", "Universe map", "Scientific viewers"], default="Science Pulse", key="edu7-research-mode")
    if mode == "Science Pulse":
        publications = platform._all("SELECT * FROM publications ORDER BY published_at DESC,created_at DESC LIMIT 500")
        if not publications:
            empty_state("No indexed publications", "Science Pulse has no permission-visible publication records for this workspace.", icon="⌁", action_hint="Configure a source or ingest the first governed publication record.")
            return
        df = pd.DataFrame(publications)
        df["month"] = pd.to_datetime(df["published_at"], errors="coerce").dt.to_period("M").astype(str)
        trend = df.groupby("month", dropna=False).size().reset_index(name="publications")
        fig = px.line(trend.tail(36), x="month", y="publications", markers=True)
        st.plotly_chart(_chart_layout(fig, "Publication trend"), width="stretch", config={"displaylogo": False})
        left, right = st.columns([.55, .45], gap="large")
        left.plotly_chart(_pulse_network(publications), width="stretch", config={"displaylogo": False, "scrollZoom": True})
        filters = right.multiselect("Retraction state", sorted(df["retraction_state"].fillna("none").unique()), default=[])
        visible = df if not filters else df[df["retraction_state"].isin(filters)]
        right.dataframe(visible[["title", "record_type", "published_at", "retraction_state", "doi", "pmid"]].head(100), hide_index=True, width="stretch")
    elif mode == "Universe map":
        rows = platform._all(
            "SELECT module_key,state,visibility,COUNT(*) records,MAX(updated_at) updated_at FROM education_universe_records WHERE institution_id=? GROUP BY module_key,state,visibility ORDER BY module_key",
            (institution_id,),
        )
        if not rows:
            empty_state("No Universe records", "The selected Education Universe view has no persisted records yet.", icon="◎", action_hint="Open a module and create the first versioned record.")
        else:
            df = pd.DataFrame(rows)
            df["module_index"] = pd.factorize(df["module_key"])[0]
            fig = px.scatter(df, x="module_index", y="state", size="records", color="visibility", hover_name="module_key", hover_data=["records", "updated_at"])
            st.plotly_chart(_chart_layout(fig, "Universe module activity map"), width="stretch", config={"displaylogo": False})
            st.dataframe(df.drop(columns=["module_index"]), hide_index=True, width="stretch")
    else:
        _scientific_viewers()


def _qualification_card(row: dict[str, Any]) -> str:
    state = str(row.get("state") or "not tested")
    evidence = row.get("evidence") or {}
    summary = evidence.get("summary") or evidence.get("message") or row.get("error_text") or "No diagnostic summary."
    return f'<article class="edu7-status"><strong>{row.get("target_type", "Qualification").replace("_", " ").title()} · {state}</strong><small>{summary}<br>Last verified {row.get("finished_at") or row.get("created_at") or "Not run"}</small></article>'


def _institution(service: EducationPhase7Service, platform: Any, actor: str, institution_id: str) -> None:
    roles = {row["role"] for row in platform.membership(actor, institution_id)}
    if not roles & ADMIN_ROLES:
        st.warning("Institution operations require an administrative role.")
        return
    mode = st.segmented_control("Institution workspace", ["Hierarchy", "Jobs", "Integrations", "Backups", "Qualification"], default="Hierarchy", key="edu7-institution-mode")
    if mode == "Hierarchy":
        campuses = service.phase5.hierarchy(actor, institution_id)
        campus_rows = campuses.get("campuses", []) if isinstance(campuses, dict) else []
        tree_rows = []
        for campus in campus_rows:
            units = campus.get("units") or []
            if not units:
                tree_rows.append({"Campus": campus.get("name"), "Code": campus.get("code"), "Unit": "Unmapped", "Kind": "—"})
            for unit in units:
                tree_rows.append({"Campus": campus.get("name"), "Code": campus.get("code"), "Unit": unit.get("name") if isinstance(unit, dict) else str(unit), "Kind": unit.get("unit_type", "") if isinstance(unit, dict) else ""})
        st.dataframe(pd.DataFrame(tree_rows), hide_index=True, width="stretch")
    elif mode == "Jobs":
        operations = _run(lambda: service.job_operations(actor, institution_id))
        if operations:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Workers", len(operations["workers"])); c2.metric("Queued", operations["counts"].get("queued", 0)); c3.metric("Running", operations["counts"].get("running", 0)); c4.metric("Failed", operations["counts"].get("failed", 0))
            st.dataframe(pd.DataFrame(operations["workers"]), hide_index=True, width="stretch")
            if operations["jobs"]:
                jobs_df = pd.DataFrame(operations["jobs"])
                st.dataframe(jobs_df[[column for column in ["id", "job_type", "queue_name", "state", "progress_percent", "progress_message", "error_text", "created_at"] if column in jobs_df.columns]], hide_index=True, width="stretch")
                job_by_id = {row["id"]: row for row in operations["jobs"]}
                job_id = st.selectbox("Job action", list(job_by_id), format_func=lambda value: f"{job_by_id[value]['job_type']} · {job_by_id[value]['state']}")
                c1, c2 = st.columns(2)
                if c1.button("Cancel", disabled=job_by_id[job_id]["state"] not in {"queued", "running"}, key=f"cancel-job-{job_id}"):
                    if _run(lambda: service.cancel_job(actor, institution_id, job_id)):
                        st.rerun()
                if c2.button("Requeue", disabled=job_by_id[job_id]["state"] not in {"failed", "cancelled"}, key=f"requeue-job-{job_id}"):
                    if _run(lambda: service.requeue_job(actor, institution_id, job_id)):
                        st.rerun()
    elif mode == "Integrations":
        operations = _run(lambda: service.integration_operations(actor, institution_id))
        if operations:
            integrations = operations["integrations"]
            runs = operations["runs"]
            st.dataframe(pd.DataFrame(integrations), hide_index=True, width="stretch")
            if integrations:
                by_id = {row["id"]: row for row in integrations}
                integration_id = st.selectbox("Integration", list(by_id), format_func=lambda value: f"{by_id[value]['provider_type']} · {by_id[value]['name']}")
                direction = st.selectbox("Direction", ["pull", "push", "bidirectional"])
                entity = st.selectbox("Entity", ["courses", "users", "enrollments", "assignments", "grades"])
                if st.button("Start governed sync", type="primary"):
                    if _run(lambda: service.start_integration_sync(actor, integration_id, direction=direction, entity_type=entity)):
                        st.rerun()
            if runs:
                st.dataframe(pd.DataFrame(runs), hide_index=True, width="stretch")
    elif mode == "Backups":
        schedules = platform._all("SELECT * FROM education_backup_schedules WHERE institution_id=? ORDER BY next_run_at", (institution_id,))
        backups = platform._all("SELECT * FROM education_backup_snapshots WHERE institution_id=? ORDER BY created_at DESC LIMIT 100", (institution_id,))
        if schedules:
            st.dataframe(pd.DataFrame(schedules), hide_index=True, width="stretch")
        with st.form("edu7-backup-schedule"):
            name = st.text_input("Schedule name", value="Nightly desktop backup")
            frequency = st.selectbox("Frequency", ["daily", "weekly"])
            hour = st.number_input("UTC hour", min_value=0, max_value=23, value=2)
            retention = st.number_input("Restore points", min_value=1, max_value=365, value=14)
            create = st.form_submit_button("Save schedule", type="primary")
        if create:
            if _run(lambda: service.create_backup_schedule(actor, institution_id, name, frequency=frequency, hour_utc=int(hour), weekday=0 if frequency == "weekly" else None, retention_count=int(retention))):
                st.rerun()
        if st.button("Enqueue due backups", icon=":material/backup:"):
            result = _run(lambda: service.enqueue_due_backups(actor, institution_id))
            if result:
                st.success(f"Enqueued {result['scheduled']} backup job(s).")
                st.rerun()
        if backups:
            st.dataframe(pd.DataFrame(backups), hide_index=True, width="stretch")
    else:
        history = _run(lambda: service.external.history(actor, institution_id)) or []
        cards = '<div class="edu7-status-grid">' + "".join(_qualification_card(row) for row in history[:12]) + "</div>"
        st.markdown(cards if history else '<div class="edu7-detail">No external qualification runs recorded.</div>', unsafe_allow_html=True)
        with st.expander("Technical evidence", expanded=False):
            st.dataframe(pd.DataFrame(history), hide_index=True, width="stretch") if history else st.caption("No evidence.")


def _sessions(service: EducationPhase7Service, actor: str, institution_id: str) -> None:
    st.subheader("Desktop sessions")
    sessions = _run(lambda: service.sessions(actor, institution_id)) or []
    if sessions:
        st.dataframe(pd.DataFrame(sessions), hide_index=True, width="stretch")
        by_id = {row["id"]: row for row in sessions if row["state"] == "active"}
        if by_id:
            session_id = st.selectbox("Revoke session", list(by_id), format_func=lambda value: f"{by_id[value]['device_label']} · {by_id[value]['last_seen_at']}")
            if st.button("Revoke selected session", key=f"revoke-session-{session_id}"):
                if _run(lambda: service.revoke_session(actor, institution_id, session_id)):
                    if str(st.session_state.get("education_phase7_session_id", "")) == session_id:
                        st.session_state.pop("education_phase7_token", None)
                    st.rerun()
    else:
        st.caption("No sessions found.")
    roles = {row["role"] for row in service.platform.membership(actor, institution_id)}
    with st.expander("Enroll or reset a desktop account", expanded=False):
        members = service.platform._all("SELECT DISTINCT user_id FROM memberships WHERE institution_id=? AND state='active' ORDER BY user_id", (institution_id,))
        options = [row["user_id"] for row in members]
        if options:
            with st.form("edu7-enroll-account"):
                user_id = st.selectbox("Member", options, disabled=not bool(roles & ADMIN_ROLES), index=options.index(actor) if actor in options else 0)
                display = st.text_input("Display name", value=user_id.replace("_", " ").title())
                email = st.text_input("Email")
                pin = st.text_input("New PIN/passphrase", type="password")
                save = st.form_submit_button("Enroll/reset account", type="primary")
            if save:
                if _run(lambda: service.enroll_identity(actor, institution_id, user_id, pin, display_name=display, email=email)):
                    st.success("Desktop account updated.")
                    st.rerun()
    if st.button("Sign out this browser", icon=":material/logout:"):
        st.session_state.pop("education_phase7_token", None)
        st.session_state.pop("education_authenticated", None)
        st.session_state.education_actor = "local-operator"
        st.session_state.education_institution = ""
        st.rerun()


def _desktop_command_palette(workspaces: list[str]) -> None:
    with st.expander(":material/search: Command palette", expanded=False):
        query = st.text_input("Find a workspace", placeholder="Classroom, gradebook, Academy, Shiro, exams…", key="edu7-command-query")
        aliases = {
            "Overview": "home today dashboard timeline notifications",
            "Classroom": "classroom timetable calendar gradebook attendance assignments rubric",
            "Academy": "academy course curriculum lecture player transcript notebook",
            "Shiro & Mastery": "shiro ai chat tutor evidence mastery knowledge graph",
            "Examinations": "exam live monitor analytics moderation results",
            "Research": "science pulse publications universe bioinformatics scientific viewers",
            "Institution": "campus workers backups integrations storage governance",
            "Sessions": "login accounts devices sessions security sign out",
        }
        visible = [name for name in workspaces if not query.strip() or query.casefold() in (name + " " + aliases.get(name, "")).casefold()]
        cols = st.columns(min(4, max(1, len(visible))))
        for idx, name in enumerate(visible):
            if cols[idx % len(cols)].button(name, key=f"command-{name}", width="stretch"):
                st.session_state.edu7_workspace = name
                st.rerun()
        if not visible:
            st.caption("No matching desktop workspace.")


def render_education_phase7_desktop(root: Path) -> None:
    render_app_header(
        "desktop",
        "BioIntel Education Desktop",
        "Lazy-loaded academic workspaces for timetable planning, editable gradebooks, attendance rosters, Academy learning, Shiro evidence chat, examination intelligence, research visuals and institution operations.",
        eyebrow="BIOINTEL EDUCATION OS · PHASE 7 DESKTOP",
    )
    _desktop_css()
    demo_mode = _demo_controls(root)
    platform = _page_platform(root, demo_mode)
    service = EducationPhase7Service(platform, root=root)
    if demo_mode:
        actor = _actor()
        institution_id = str(st.session_state.get("education_institution", ""))
    else:
        session = _sign_in(service, platform)
        if not session:
            st.stop()
            return
        actor = session["user_id"]
        institution_id = session["institution_id"]
        st.session_state.education_phase7_session_id = session["id"]
    try:
        render_workspace_context(platform, actor, institution_id)
    except EducationError as exc:
        st.error(str(exc))
        return
    render_role_snapshot(platform, actor, institution_id)
    workspaces = ["Overview", "Classroom", "Academy", "Shiro & Mastery", "Examinations", "Research", "Institution", "Sessions"]
    _desktop_command_palette(workspaces)
    st.markdown('<div class="edu7-workspace-bar">', unsafe_allow_html=True)
    selected = st.segmented_control("Desktop workspace", workspaces, default=st.session_state.get("edu7_workspace", "Overview"), key="edu7-workspace")
    st.session_state.edu7_workspace = selected
    st.markdown("</div>", unsafe_allow_html=True)
    # Only the selected branch executes: this replaces the Phase 6 all-tabs-at-once page.
    if selected == "Overview":
        _overview(service, platform, actor, institution_id)
    elif selected == "Classroom":
        _classroom(service, platform, actor, institution_id)
    elif selected == "Academy":
        _academy(service, platform, actor, institution_id)
    elif selected == "Shiro & Mastery":
        _shiro(service, platform, actor, institution_id)
    elif selected == "Examinations":
        _examinations(service, actor, institution_id)
    elif selected == "Research":
        _research(service, platform, actor, institution_id)
    elif selected == "Institution":
        _institution(service, platform, actor, institution_id)
    elif selected == "Sessions":
        _sessions(service, actor, institution_id)
