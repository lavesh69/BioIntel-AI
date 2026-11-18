from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from ._streamlit_compat import st

from .examination import SecureExaminationService
from .experience import render_role_snapshot, render_workspace_context
from biointel.ui.frontend_v10 import empty_state
from .permissions import PermissionService
from .platform import ADMIN, STUDENT, TEACHER

Run = Callable[[Callable[[], Any]], Any]


def _friendly(value: Any) -> str:
    return str(value or "").replace("_", " ").title()


def _today_timeline(platform: Any, actor: str, institution_id: str, roles: set[str]) -> list[dict[str, Any]]:
    today = datetime.now(timezone.utc).date().isoformat()
    if roles & STUDENT:
        rows = platform._all(
            """SELECT t.starts_at,t.ends_at,s.code,s.name,t.room,t.student_group,t.state
            FROM timetable_entries t JOIN subjects s ON s.id=t.subject_id
            JOIN enrollments e ON e.subject_id=s.id
            WHERE t.institution_id=? AND e.student_id=? AND substr(t.starts_at,1,10)=?
            ORDER BY t.starts_at""",
            (institution_id, actor, today),
        )
    elif roles & TEACHER and not roles & ADMIN:
        rows = platform._all(
            """SELECT t.starts_at,t.ends_at,s.code,s.name,t.room,t.student_group,t.state
            FROM timetable_entries t JOIN subjects s ON s.id=t.subject_id
            WHERE t.institution_id=? AND t.teacher_id=? AND substr(t.starts_at,1,10)=?
            ORDER BY t.starts_at""",
            (institution_id, actor, today),
        )
    else:
        rows = platform._all(
            """SELECT t.starts_at,t.ends_at,s.code,s.name,t.room,t.student_group,t.state
            FROM timetable_entries t JOIN subjects s ON s.id=t.subject_id
            WHERE t.institution_id=? AND substr(t.starts_at,1,10)=?
            ORDER BY t.starts_at LIMIT 100""",
            (institution_id, today),
        )
    return [
        {
            "Starts": row["starts_at"],
            "Ends": row["ends_at"],
            "Subject": f"{row['code']} · {row['name']}",
            "Group": row["student_group"] or "—",
            "Room": row["room"] or "—",
            "State": _friendly(row["state"]),
        }
        for row in rows
    ]


def _pending_actions(platform: Any, actor: str, institution_id: str, roles: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if roles & STUDENT:
        assignments = platform._all(
            """SELECT a.title,a.due_at,s.code,s.name FROM assignments a
            JOIN subjects s ON s.id=a.subject_id JOIN enrollments e ON e.subject_id=a.subject_id
            LEFT JOIN submissions x ON x.assignment_id=a.id AND x.student_id=?
            WHERE a.institution_id=? AND e.student_id=? AND a.state='published'
            AND (x.id IS NULL OR x.state<>'submitted') ORDER BY a.due_at LIMIT 20""",
            (actor, institution_id, actor),
        )
        rows.extend({"Type": "Assignment", "Title": row["title"], "Due": row["due_at"], "Context": f"{row['code']} · {row['name']}"} for row in assignments)
    if roles & TEACHER:
        grading = platform._all(
            """SELECT a.title,COUNT(*) records,s.code,s.name FROM submissions x
            JOIN assignments a ON a.id=x.assignment_id JOIN subjects s ON s.id=a.subject_id
            JOIN teacher_assignments t ON t.subject_id=s.id
            WHERE a.institution_id=? AND t.teacher_id=? AND x.state='submitted'
            AND NOT EXISTS(SELECT 1 FROM grades g WHERE g.submission_id=x.id)
            GROUP BY a.id ORDER BY records DESC LIMIT 20""",
            (institution_id, actor),
        )
        rows.extend({"Type": "Grading", "Title": row["title"], "Due": f"{row['records']} submissions", "Context": f"{row['code']} · {row['name']}"} for row in grading)
    if roles & ADMIN:
        consents = platform._one("SELECT COUNT(*) n FROM guardian_links WHERE institution_id=? AND state='pending'", (institution_id,)) or {"n": 0}
        if int(consents["n"]):
            rows.append({"Type": "Consent", "Title": "Guardian link approvals", "Due": f"{consents['n']} pending", "Context": "Privacy workflow"})
    return rows


def _quick_launch() -> None:
    st.subheader("Launch workspace")
    paths = (
        ("pages/340_BioIntel_Classroom.py", "Classroom", ":material/school:"),
        ("pages/356_BioIntel_Education_Suite.py", "Education Suite", ":material/auto_stories:"),
        ("pages/342_BioIntel_Academy_and_Lecture_Studio.py", "Academy", ":material/video_library:"),
        ("pages/344_BioIntel_Examination_Command_Center.py", "Examinations", ":material/assignment_turned_in:"),
        ("pages/341_BioIntel_Science_Pulse.py", "Science Pulse", ":material/biotech:"),
        ("pages/343_BioIntel_Education_Universe.py", "Education Universe", ":material/hub:"),
    )
    columns = st.columns(len(paths), gap="small")
    for column, (path, label, icon) in zip(columns, paths):
        with column:
            try:
                st.page_link(path, label=label, icon=icon, width="stretch")
            except (KeyError, RuntimeError, TypeError):
                st.caption(label)


def _overview(platform: Any, actor: str, institution_id: str, roles: set[str], run: Run) -> None:
    render_role_snapshot(platform, actor, institution_id)
    _quick_launch()
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        st.subheader("Today")
        timeline = _today_timeline(platform, actor, institution_id, roles)
        if timeline:
            st.dataframe(timeline, hide_index=True, width="stretch")
        else:
            empty_state("No classes scheduled today", "Your visible timetable has no entries for the current UTC date.", icon="▦", action_hint="Review the weekly calendar or create a timetable entry.")
    with right:
        st.subheader("Needs attention")
        actions = _pending_actions(platform, actor, institution_id, roles)
        if actions:
            st.dataframe(actions, hide_index=True, width="stretch")
        else:
            st.success("No pending actions were found in your permitted records.", icon=":material/check_circle:")
    exams = run(lambda: SecureExaminationService(platform).list_exams(actor, institution_id)) or []
    if exams:
        st.subheader("Examination status")
        st.dataframe([
            {
                "Examination": row["title"],
                "Subject": f"{row.get('subject_code','')} · {row.get('subject_name','')}",
                "State": _friendly(row["state"]),
                "Window opens": row["starts_at"],
                "Questions": row.get("question_count", 0),
                "Attempts": row.get("session_count", 0),
            }
            for row in exams[:20]
        ], hide_index=True, width="stretch")


def _activity(platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    st.subheader("Recent institutional activity")
    if roles & ADMIN:
        events = platform._all(
            """SELECT created_at,actor_id,action,target_type,target_id,detail_json
            FROM education_audit_events WHERE institution_id=? ORDER BY created_at DESC LIMIT 100""",
            (institution_id,),
        )
    else:
        events = platform._all(
            """SELECT created_at,actor_id,action,target_type,target_id,detail_json
            FROM education_audit_events WHERE institution_id=? AND actor_id=? ORDER BY created_at DESC LIMIT 100""",
            (institution_id, actor),
        )
    if events:
        st.dataframe(events, hide_index=True, width="stretch")
    else:
        empty_state("No recent audit activity", "No permission-visible academic events have been recorded in this view.", icon="✓", action_hint="Activity will appear after governed classroom or institution actions.")


def _governance(platform: Any, actor: str, institution_id: str, roles: set[str], run: Run) -> None:
    if not roles & ADMIN:
        st.info("Governance metrics are available to institution administrators.", icon=":material/admin_panel_settings:")
        return
    permissions = PermissionService(platform)
    audits = platform._one("SELECT COUNT(*) n FROM education_audit_events WHERE institution_id=?", (institution_id,)) or {"n": 0}
    overrides = platform._one("SELECT COUNT(*) n FROM education_permission_overrides WHERE institution_id=?", (institution_id,)) or {"n": 0}
    pending = platform._one("SELECT COUNT(*) n FROM guardian_links WHERE institution_id=? AND state='pending'", (institution_id,)) or {"n": 0}
    locked = platform._one("SELECT COUNT(*) n FROM results WHERE institution_id=? AND locked=1", (institution_id,)) or {"n": 0}
    cols = st.columns(4)
    cols[0].metric("Audit events", int(audits["n"]))
    cols[1].metric("Permission overrides", int(overrides["n"]))
    cols[2].metric("Pending consents", int(pending["n"]))
    cols[3].metric("Locked results", int(locked["n"]))
    st.caption("The permission matrix is managed in Examination Command Center → Permissions.")
    rows = run(lambda: permissions.matrix(actor, institution_id, roles=["institution_administrator", "subject_teacher", "university_student"])) or []
    st.dataframe(rows, hide_index=True, width="stretch")


def render_education_home_workspace(platform: Any, actor: str, institution_id: str, run: Run) -> None:
    roles = render_workspace_context(platform, actor, institution_id)
    tabs = ["Overview", "Today", "Activity"]
    if roles & ADMIN:
        tabs.append("Governance")
    selected = st.segmented_control("Education home", tabs, default="Overview", key=f"education-home-{actor}-{institution_id}")
    if selected == "Overview":
        _overview(platform, actor, institution_id, roles, run)
    elif selected == "Today":
        st.subheader("Today's academic timeline")
        timeline = _today_timeline(platform, actor, institution_id, roles)
        if timeline:
            st.dataframe(timeline, hide_index=True, width="stretch")
        else:
            empty_state("No classes scheduled today", "The current role has no visible timetable entry today.", icon="▦", action_hint="Open Classroom to review another date or schedule a class.")
        st.subheader("Pending actions")
        actions = _pending_actions(platform, actor, institution_id, roles)
        if actions:
            st.dataframe(actions, hide_index=True, width="stretch")
        else:
            st.success("You are caught up.")
    elif selected == "Activity":
        _activity(platform, actor, institution_id, roles)
    elif selected == "Governance":
        _governance(platform, actor, institution_id, roles, run)
