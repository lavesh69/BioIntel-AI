from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any, Callable, Iterable, Mapping

import pandas as pd
from ._streamlit_compat import st

from .components.cards import identity_card, metric_grid
from biointel.ui.product_experience_v8 import course_card_markup
from .components.charts import count_rows, dated_counts, render_bar, render_heatmap, render_line, render_metric_explanation
from .components.empty_states import render_empty_state
from .components.navigation import breadcrumbs, command_palette
from .components.status import friendly, provider_status, status_badge
from .components.themes import reduced_motion_enabled
from .components.timelines import render_timeline
from .components.workflows import render_workflow
from .phase2 import DASHBOARD_WIDGETS, REPORT_TYPES, EducationPhase2
from .platform import ADMIN, TEACHER
from .universe import MODULES

Run = Callable[[Callable[[], Any]], Any]
WIDGET_LABELS: Mapping[str, tuple[str, str]] = {
    "today_timeline": ("Today and recent timeline", ":material/today:"),
    "pending_actions": ("Pending-action queue", ":material/pending_actions:"),
    "attendance_trend": ("Attendance intelligence", ":material/calendar_month:"),
    "assignment_deadlines": ("Assignment deadlines", ":material/assignment:"),
    "course_progress": ("Course progress", ":material/play_lesson:"),
    "research_activity": ("Research activity", ":material/biotech:"),
    "shiro_recommendations": ("Shiro recommendations", ":material/smart_toy:"),
    "connect_meetings": ("Connect meetings", ":material/video_call:"),
    "lecture_status": ("Lecture-processing status", ":material/subtitles:"),
    "pulse_alerts": ("Science Pulse alerts", ":material/notifications_active:"),
    "portfolio_progress": ("Portfolio progress", ":material/workspace_premium:"),
    "opportunity_deadlines": ("Opportunity deadlines", ":material/work:"),
    "system_health": ("System health", ":material/monitor_heart:"),
}
MODULE_PHASE2: Mapping[str, tuple[str, str, tuple[str, ...]]] = {
    "adaptive_learning": (":material/route:", "Explainable learning-path intelligence", ("Evidence", "Mastery", "Recommendation", "Teacher adjustment", "Learner choice")),
    "virtual_science_lab": (":material/science:", "Safe interactive scientific simulations", ("Objective", "Safety briefing", "Parameters", "Observation", "Review")),
    "bioinformatics_sandbox": (":material/data_object:", "Bounded visual bioinformatics workflows", ("Dataset", "Quality", "Method", "Result", "Provenance")),
    "shiro_tutor": (":material/smart_toy:", "Grounded AI learning workspace", ("Request", "Evidence", "AI draft", "Human review", "Approved use")),
    "academic_erp": (":material/account_balance:", "Institution-controlled academic lifecycle", ("Admission", "Enrollment", "Progress", "Completion", "Alumni")),
    "digital_library": (":material/local_library:", "Licensed scientific knowledge collections", ("Discover", "Access", "Read", "Cite", "Curate")),
    "research_hub": (":material/biotech:", "Evidence-led student research lifecycle", ("Idea", "Proposal", "Mentor review", "Ethics review", "Active research", "Data collection", "Analysis", "Draft report", "Final review", "Completed", "Published to portfolio")),
    "competition_hub": (":material/emoji_events:", "Auditable science events and scorecards", ("Event", "Registration", "Submission", "Review", "Scorecard")),
    "career_hub": (":material/work:", "Verified and explainable opportunity workflows", ("Discover", "Eligibility", "Checklist", "Application", "Decision")),
    "academic_portfolio": (":material/workspace_premium:", "Evidence-backed skills and credentials", ("Evidence", "Review", "Credential request", "Approval", "Share")),
    "laboratory_management": (":material/lab_panel:", "Safe practical-laboratory readiness", ("Inventory", "Eligibility", "Booking", "Use", "Maintenance")),
    "question_bank": (":material/quiz:", "Protected assessment intelligence", ("Author", "Blueprint", "Review", "Approve", "Secure export")),
    "lecture_intelligence": (":material/subtitles:", "Review-gated multilingual media processing", ("Upload", "Validation", "Audio extraction", "Speech recognition", "Segmentation", "Chapters", "Summary", "Captions", "Translation", "Quiz", "Review", "Publication")),
    "learning_analytics": (":material/monitoring:", "Explainable early-support analytics", ("Define", "Collect", "Calculate", "Human review", "Intervention")),
    "collaboration_network": (":material/hub:", "Consent-led institutional collaboration", ("Proposal", "Source approval", "Partner approval", "Agreement", "Shared work")),
    "open_science": (":material/public:", "Reproducibility and privacy readiness", ("Method", "Dataset metadata", "Environment", "Privacy scan", "Package")),
    "offline_learning": (":material/offline_bolt:", "Explicit offline sync and conflict handling", ("Cache", "Offline draft", "Queue", "Conflict review", "Sync")),
    "safety_moderation": (":material/health_and_safety:", "Private safety cases and accountable review", ("Report", "Triage", "Assignment", "Resolution", "Appeal")),
    "quality_support": (":material/fact_check:", "Evidence organization for quality improvement", ("Outcome", "Evidence", "Review", "Action", "Follow-up")),
    "gamified_learning": (":material/military_tech:", "Evidence-backed, private-by-default motivation", ("Goal", "Quest", "Evidence", "Review", "Achievement")),
}

def _scope(actor: str, institution_id: str) -> str:
    clean = lambda value: "".join(char if char.isalnum() else "_" for char in value)
    return f"education_phase2_{clean(actor)}_{clean(institution_id)}"

def _roles(service: EducationPhase2, actor: str, institution_id: str) -> set[str]:
    return {str(item["role"]) for item in service.platform.membership(actor, institution_id)}

def _persona(roles: Iterable[str]) -> str:
    values = set(roles)
    return "Administrator" if values & ADMIN else "Educator" if values & TEACHER else "Learner"

def _summary(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {"Metric": "Attendance records", "Value": sum(int(row.get("records") or 0) for row in snapshot.get("attendance", []))},
        {"Metric": "Assignments", "Value": len(snapshot.get("assignments", []))},
        {"Metric": "Courses", "Value": len(snapshot.get("courses", []))},
        {"Metric": "Universe records", "Value": sum(int(row.get("records") or 0) for row in snapshot.get("universe", []))},
        {"Metric": "Lecture jobs", "Value": sum(int(row.get("records") or 0) for row in snapshot.get("lectures", []))},
        {"Metric": "Pulse alerts", "Value": sum(int(row.get("records") or 0) for row in snapshot.get("alerts", []))},
    ]

def _customize(service: EducationPhase2, actor: str, institution_id: str, preference: Mapping[str, Any], run: Run, scope: str) -> None:
    with st.popover("Customize dashboard", icon=":material/tune:"):
        selected = list(preference.get("widgets") or [])
        ordered = [*selected, *[key for key in DASHBOARD_WIDGETS if key not in selected]]
        frame = pd.DataFrame([{"Widget": WIDGET_LABELS[key][0], "Widget ID": key, "Order": position + 1, "Show": key in selected} for position, key in enumerate(ordered)])
        edited = st.data_editor(frame, hide_index=True, disabled=["Widget", "Widget ID"], column_config={"Widget": st.column_config.TextColumn(pinned=True), "Widget ID": None, "Order": st.column_config.NumberColumn(min_value=1, max_value=len(DASHBOARD_WIDGETS), step=1), "Show": st.column_config.CheckboxColumn()}, key=f"{scope}_editor")
        preset = st.text_input("Preset name", value=str(preference.get("preset_name") or "Default"), key=f"{scope}_preset")
        density = st.segmented_control("Density", ["compact", "expanded"], default=str(preference.get("density") or "compact"), format_func=str.title, key=f"{scope}_density")
        today = date.today()
        dates = st.date_input("Date range", value=(today - timedelta(days=90), today), key=f"{scope}_dates")
        session = st.text_input("Academic session", value=str(preference.get("academic_session") or "Current"), key=f"{scope}_session")
        with st.container(horizontal=True):
            if st.button("Save preset", type="primary", icon=":material/save:", key=f"{scope}_save"):
                visible = edited[edited["Show"] == True].sort_values("Order")["Widget ID"].tolist()
                start, end = dates if isinstance(dates, tuple) and len(dates) == 2 else (today - timedelta(days=90), today)
                if run(lambda: service.save_preferences(actor, institution_id, preset, visible, str(density), session, start.isoformat(), end.isoformat())):
                    st.toast("Dashboard preset saved.", icon=":material/check_circle:")
                    st.rerun()
            if st.button("Reset default", icon=":material/restart_alt:", key=f"{scope}_reset"):
                if run(lambda: service.reset_preferences(actor, institution_id, str(preference.get("preset_name") or "Default"))):
                    st.rerun()

def _widget_title(key: str) -> None:
    label, icon = WIDGET_LABELS[key]
    st.subheader(f"{icon} {label}")
def _render_widget(service: EducationPhase2, key: str, actor: str, institution_id: str, snapshot: Mapping[str, Any], density: str) -> None:
    if key == "today_timeline":
        render_timeline(snapshot.get("activity", [])[:6 if density == "compact" else 15], title=f"{WIDGET_LABELS[key][1]} {WIDGET_LABELS[key][0]}")
    elif key == "pending_actions":
        rows = [{"Module": friendly(row.get("module_key")), "Records": int(row.get("records") or 0)} for row in snapshot.get("universe", []) if row.get("state") in {"open", "submitted", "under_review"}]
        render_bar(rows, "Module", "Records", title=f"{WIDGET_LABELS[key][1]} {WIDGET_LABELS[key][0]}", horizontal=True, empty_detail="No pending role-permitted records.")
    elif key == "attendance_trend":
        daily: defaultdict[str, int] = defaultdict(int)
        for row in snapshot.get("attendance", []):
            daily[str(row.get("date"))] += int(row.get("records") or 0)
        render_line([{"Date": day, "Records": daily[day]} for day in sorted(daily)], "Date", "Records", title=f"{WIDGET_LABELS[key][1]} {WIDGET_LABELS[key][0]}")
    elif key == "assignment_deadlines":
        rows = []
        for item in snapshot.get("assignments", []):
            submissions = int(item.get("submissions") or 0)
            rows.append({"Assignment": item.get("title"), "Subject": item.get("subject"), "Deadline": item.get("due_at"), "State": friendly(item.get("state")), "Grading": int(item.get("graded") or 0) / max(1, submissions)})
        with st.container(border=True):
            _widget_title(key)
            if rows:
                st.dataframe(rows[:8 if density == "compact" else 30], hide_index=True, column_config={"Assignment": st.column_config.TextColumn(pinned=True), "Deadline": st.column_config.DatetimeColumn(format="MMM DD, YYYY, h:mm a"), "Grading": st.column_config.ProgressColumn(min_value=0, max_value=1, format="percent")})
            else:
                render_empty_state("No assignments", "Persisted assignment deadlines appear here.", icon=":material/assignment:")
    elif key == "course_progress":
        rows = []
        for item in snapshot.get("courses", []):
            progress = int(item.get("progress_rows") or 0)
            rows.append({"Course": item.get("title"), "Lectures": int(item.get("lectures") or 0), "Enrollments": int(item.get("enrollments") or 0), "Completion": int(item.get("completed_lecture_views") or 0) / max(1, progress)})
        with st.container(border=True):
            _widget_title(key)
            if rows:
                st.dataframe(rows[:8 if density == "compact" else 30], hide_index=True, column_config={"Course": st.column_config.TextColumn(pinned=True), "Completion": st.column_config.ProgressColumn(min_value=0, max_value=1, format="percent")})
            else:
                render_empty_state("No course progress", "Progress appears after stored watch activity.", icon=":material/play_lesson:")
    elif key in {"research_activity", "portfolio_progress"}:
        module = "research_hub" if key == "research_activity" else "academic_portfolio"
        rows = [{"State": friendly(row.get("state")), "Records": int(row.get("records") or 0)} for row in snapshot.get("universe", []) if row.get("module_key") == module]
        render_bar(rows, "State", "Records", title=f"{WIDGET_LABELS[key][1]} {WIDGET_LABELS[key][0]}", empty_detail=f"No {friendly(module)} records are visible.")
    elif key == "shiro_recommendations":
        records = service.module_records(actor, institution_id, "adaptive_learning") + service.module_records(actor, institution_id, "shiro_tutor")
        with st.container(border=True):
            _widget_title(key)
            if records:
                for record in records[:3 if density == "compact" else 8]:
                    st.markdown(f"**{record['title']}**")
                    status_badge(record.get("state"))
                    payload = record.get("payload") or {}
                    st.caption(str(payload.get("rationale") or payload.get("request") or "Stored evidence is available in the source record."))
                st.caption("Provider output is not inferred; AI drafts remain visibly AI-generated until reviewed.")
            else:
                render_empty_state("No recommendations", "Evidence-backed recommendations appear after a stored record exists.", icon=":material/smart_toy:")
    elif key == "connect_meetings":
        rows = service.platform._all("SELECT student_group,room,starts_at,state FROM timetable_entries WHERE institution_id=? AND meeting_id<>'' ORDER BY starts_at LIMIT 50", (institution_id,))
        with st.container(border=True):
            _widget_title(key)
            if rows:
                st.dataframe([{"Class or group": row["student_group"], "Room": row["room"], "Starts": row["starts_at"], "State": friendly(row["state"])} for row in rows], hide_index=True)
            else:
                render_empty_state("No linked meetings", "Only records with a persisted Connect meeting ID are shown.", icon=":material/video_call:")
    elif key in {"lecture_status", "pulse_alerts"}:
        source = snapshot.get("lectures" if key == "lecture_status" else "alerts", [])
        state_field = "processing_state" if key == "lecture_status" else "state"
        value_label = "Jobs" if key == "lecture_status" else "Alerts"
        rows = [{"State": friendly(row.get(state_field)), value_label: int(row.get("records") or 0)} for row in source]
        render_bar(rows, "State", value_label, title=f"{WIDGET_LABELS[key][1]} {WIDGET_LABELS[key][0]}")
    elif key == "opportunity_deadlines":
        records = service.module_records(actor, institution_id, "career_hub")
        with st.container(border=True):
            _widget_title(key)
            if records:
                st.dataframe([{"Opportunity": row["title"], "Deadline": (row.get("payload") or {}).get("deadline", "Not recorded"), "Eligibility": (row.get("payload") or {}).get("eligibility", "Not recorded"), "Source": (row.get("payload") or {}).get("source_url", "")} for row in records], hide_index=True, column_config={"Opportunity": st.column_config.TextColumn(pinned=True), "Source": st.column_config.LinkColumn()})
            else:
                render_empty_state("No verified opportunities", "Source-linked opportunities appear here.", icon=":material/work:")
    elif key == "system_health":
        configured = service.platform._one("SELECT COUNT(*) n FROM pulse_sources WHERE configured=1") or {"n": 0}
        sync = service.platform._one("SELECT COUNT(*) n FROM education_universe_sync_operations WHERE institution_id=? AND state IN ('queued','conflict')", (institution_id,)) or {"n": 0}
        with st.container(border=True):
            _widget_title(key)
            metric_grid([
                {"label": "Education database", "value": "Healthy" if service.db.quick_check() else "Error"},
                {"label": "Universe definitions", "value": len(MODULES)},
                {"label": "Configured sources", "value": int(configured["n"])},
                {"label": "Sync actions", "value": int(sync["n"])},
            ])
            st.caption("Real database/configuration state only; provider success is never inferred.")

def render_advanced_command_center(service: EducationPhase2, actor: str, institution_id: str, run: Run) -> None:
    scope = _scope(actor, institution_id)
    preference = run(lambda: service.preferences(actor, institution_id)) or {"widgets": list(DASHBOARD_WIDGETS[:6]), "density": "compact", "preset_name": "Default"}
    snapshot = run(lambda: service.dashboard_snapshot(actor, institution_id)) or {}
    institution = service.platform._one("SELECT name,kind FROM institutions WHERE id=?", (institution_id,)) or {}
    branding = run(lambda: service.branding(actor, institution_id)) or {}
    roles = set(snapshot.get("roles", []))
    pending = sum(int(row.get("records") or 0) for row in snapshot.get("universe", []) if row.get("state") in {"open", "submitted", "under_review"})
    breadcrumbs(("Education", institution.get("name", "Institution"), "Command Center"))
    with st.container(border=True):
        left, right = st.columns([1.4, 1], vertical_alignment="center")
        with left:
            st.subheader(":material/dashboard: Education Command Center")
            st.caption(f"{branding.get('campus_name') or institution.get('name','Institution')} · {_persona(roles)} · {str(preference.get('density','compact')).title()} view")
        with right:
            with st.container(horizontal=True, horizontal_alignment="right"):
                st.badge(_persona(roles), icon=":material/person:", color="blue")
                st.badge(f"{pending} pending", icon=":material/notifications:", color="orange" if pending else "gray")
        metric_grid([{"label": item["Metric"], "value": item["Value"], "help": "Persisted Education records"} for item in _summary(snapshot)[:4]])
        with st.container(horizontal=True):
            _customize(service, actor, institution_id, preference, run, scope)
            st.download_button("Export summary", data=service.export_csv(_summary(snapshot)), file_name="biointel-education-dashboard-summary.csv", mime="text/csv", icon=":material/download:")
            reduced_motion_enabled(f"{scope}_reduced_motion")
    actions = [
        {"id": "classroom", "label": "Open Classroom", "allowed": True},
        {"id": "shiro", "label": "Ask Shiro AI", "allowed": True},
        {"id": "assignment", "label": "Create assignment", "allowed": bool(roles & TEACHER)},
        {"id": "attendance", "label": "Mark attendance", "allowed": bool(roles & TEACHER)},
        {"id": "lecture", "label": "Upload lecture", "allowed": bool(roles & TEACHER)},
        {"id": "publication", "label": "Search publication", "allowed": True},
        {"id": "research", "label": "Create research project", "allowed": True},
        {"id": "opportunity", "label": "Add verified opportunity", "allowed": bool(roles & TEACHER)},
    ]
    chosen = command_palette(actions, key=f"{scope}_commands")
    if chosen:
        page_map = {"classroom": "pages/340_BioIntel_Classroom.py", "shiro": "pages/273_Shiro_AI.py", "assignment": "pages/340_BioIntel_Classroom.py", "attendance": "pages/340_BioIntel_Classroom.py", "lecture": "pages/342_BioIntel_Academy_and_Lecture_Studio.py", "publication": "pages/341_BioIntel_Science_Pulse.py"}
        if chosen in page_map:
            try:
                st.page_link(page_map[chosen], label="Open source workspace", icon=":material/open_in_new:")
            except (KeyError, RuntimeError):
                st.caption("Open the source workspace from the application sidebar.")
        else:
            st.info("Open Visual studio or Create record below; role permission has been checked.", icon=":material/arrow_downward:")
    visible = [key for key in preference.get("widgets", []) if key in DASHBOARD_WIDGETS]
    if not visible:
        render_empty_state("No widgets selected", "Enable widgets in Customize dashboard.", icon=":material/widgets:")
    for key in visible:
        _render_widget(service, key, actor, institution_id, snapshot, str(preference.get("density") or "compact"))
def render_classroom_visuals(service: EducationPhase2, actor: str, institution_id: str, run: Run) -> None:
    snapshot = run(lambda: service.classroom_snapshot(actor, institution_id)) or {}
    attendance, assignments = snapshot.get("attendance", []), snapshot.get("assignments", [])
    st.subheader(":material/insights: Classroom visual intelligence")
    st.caption("Every visual is calculated from role-permitted persisted Classroom records.")
    metric_grid([
        {"label": "Subjects", "value": len(snapshot.get("subjects", []))},
        {"label": "Attendance records", "value": len(attendance)},
        {"label": "Assignments", "value": len(assignments)},
        {"label": "Submissions", "value": sum(int(row.get("submissions") or 0) for row in assignments)},
    ])
    view = st.segmented_control("Classroom visual", ["Attendance", "Assignment board", "Student profile", "Timeline"], default="Attendance", key=f"{_scope(actor,institution_id)}_classroom")
    if view == "Attendance":
        left, right = st.columns(2)
        with left:
            render_line(dated_counts(attendance, "date", period="day", date_label="Date", value_label="Records"), "Date", "Records", title="Attendance trend")
        with right:
            render_bar(count_rows(attendance, "status", label="Status", value_label="Records"), "Status", "Records", title="Attendance distribution")
        matrix = [{"Date": str(row.get("date")), "Student": str(row.get("student_id")), "Participating": 1 if row.get("status") in {"present", "late", "online_present", "practical_attendance", "examination_attendance"} else 0} for row in attendance]
        render_heatmap(matrix, "Date", "Student", "Participating", title="Student attendance heatmap")
        render_metric_explanation("Visible attendance records per date.", "COUNT(attendance_records)", "Role-permitted attendance events.", "Deleted and inaccessible records.", "Persisted dates shown.", 100 if attendance else 0, str(snapshot.get("calculated_at", "")), "Attendance alone cannot explain absence causes or diagnose a learner.")
    elif view == "Assignment board":
        stages = ("draft", "published", "in_progress", "submitted", "under_review", "feedback_released", "closed")
        counts = Counter(str(row.get("state")) for row in assignments)
        current = next((stage for stage in reversed(stages) if counts.get(stage)), "draft")
        render_workflow(stages, current, title="Assignment Kanban pipeline")
        render_bar([{"Column": friendly(stage), "Assignments": counts.get(stage, 0)} for stage in stages], "Column", "Assignments", title="Assignment board")
        if assignments:
            st.dataframe(assignments, hide_index=True, column_config={"title": st.column_config.TextColumn("Assignment", pinned=True), "due_at": st.column_config.DatetimeColumn("Deadline", format="MMM DD, YYYY, h:mm a")})
    elif view == "Student profile":
        students = sorted({str(row.get("student_id")) for row in attendance if row.get("student_id")})
        if not students:
            render_empty_state("No visible student profile", "A profile appears only when permitted enrollment or attendance evidence exists.", icon=":material/person:")
        else:
            selected = st.selectbox("Student", students, key=f"{_scope(actor,institution_id)}_student")
            rows = [row for row in attendance if row.get("student_id") == selected]
            participating = sum(row.get("status") in {"present", "late", "online_present", "practical_attendance", "examination_attendance"} for row in rows)
            identity_card("Learner profile", "Institution-scoped academic view", icon=":material/person:", badges=(("Guardian access not inferred", "pending"),), progress=participating / max(1, len(rows)))
            metric_grid([{"label": "Attendance records", "value": len(rows)}, {"label": "Participating", "value": participating}, {"label": "Subjects", "value": len({row.get('subject') for row in rows})}])
    else:
        render_timeline(snapshot.get("timeline", []), title="Classroom and cross-module timeline")

def render_academy_visuals(service: EducationPhase2, actor: str, institution_id: str, run: Run) -> None:
    snapshot = run(lambda: service.academy_snapshot(actor, institution_id)) or {}
    courses, lectures = snapshot.get("courses", []), snapshot.get("lectures", [])
    st.subheader(":material/play_lesson: Academy premium learning experience")
    st.caption("Course identity and engagement use persisted enrollments and watch progress.")
    metric_grid([
        {"label": "Courses", "value": len(courses)},
        {"label": "Lectures", "value": len(lectures)},
        {"label": "Enrollments", "value": sum(int(row.get("enrollments") or 0) for row in courses)},
        {"label": "Completed views", "value": sum(int(row.get("completed") or 0) for row in courses)},
    ])
    view = st.segmented_control("Academy visual", ["Course gallery", "Learning path", "Engagement", "Lecture pipeline"], default="Course gallery", key=f"{_scope(actor,institution_id)}_academy")
    if view == "Course gallery":
        if not courses:
            render_empty_state("No courses", "Course cards appear after a persisted Academy course exists.", icon=":material/play_lesson:")
        cards: list[str] = []
        for index, course in enumerate(courses):
            progress = int(course.get("completed") or 0) / max(1, int(course.get("progress_rows") or 0))
            cards.append(course_card_markup(
                title=str(course.get("title") or "Untitled course"),
                difficulty=friendly(course.get("difficulty")),
                lectures=int(course.get("lectures") or 0),
                state=str(course.get("state") or "draft"),
                progress=progress,
                enrollments=int(course.get("enrollments") or 0),
                index=index,
            ))
        st.markdown('<div class="bx-course-grid">' + ''.join(cards) + '</div>', unsafe_allow_html=True)
    elif view == "Learning path":
        if not courses:
            render_empty_state("No learning path", "A node path requires a course and lectures.", icon=":material/route:")
        else:
            selected = st.selectbox("Course", [str(row["id"]) for row in courses], format_func=lambda value: next(str(row["title"]) for row in courses if row["id"] == value), key=f"{_scope(actor,institution_id)}_course")
            stages = [str(row.get("title")) for row in lectures if row.get("course_id") == selected] or ["Course orientation"]
            render_workflow(stages, stages[-1], title="Interactive learning path")
            st.caption("Locked and optional states are not fabricated because the current course schema does not store them.")
    elif view == "Engagement":
        rows = [{"Course": row.get("title"), "Progress rows": int(row.get("progress_rows") or 0), "Completed views": int(row.get("completed") or 0)} for row in courses]
        render_bar(rows, "Course", "Progress rows", title="Course engagement distribution")
        if rows:
            st.dataframe(rows, hide_index=True)
    else:
        render_bar(count_rows(lectures, "processing_state", label="State", value_label="Lectures"), "State", "Lectures", title="Lecture-processing status")
        if lectures:
            state = str(lectures[0].get("processing_state") or "not_uploaded")
            stages = ("not_uploaded", "original_ready", "processing_dependency_required", "processing", "output_ready", "reviewed", "published")
            render_workflow(stages, state, title="Qualified processing pipeline")
            info = provider_status(state not in {"not_uploaded", "processing_dependency_required"}, state in {"output_ready", "reviewed", "published"}, "failed" in state)
            status_badge(info["state"], label=info["label"])
            st.caption(info["detail"] + " No fabricated time estimate is shown.")

def render_pulse_visuals(service: EducationPhase2, actor: str, run: Run) -> None:
    snapshot = run(lambda: service.pulse_snapshot(actor)) or {}
    publications, news = snapshot.get("publications", []), snapshot.get("news", [])
    st.subheader(":material/biotech: Science Pulse research intelligence")
    st.caption("Charts use persisted source metadata or labelled synthetic demo metadata.")
    metric_grid([
        {"label": "Publications", "value": len(publications)},
        {"label": "News items", "value": len(news)},
        {"label": "Configured sources", "value": sum(int(row.get("configured") or 0) for row in snapshot.get("sources", []))},
        {"label": "Saved by user", "value": len(snapshot.get("saved", []))},
    ])
    view = st.segmented_control("Research visual", ["Trends", "Evidence quality", "Collections", "Source health"], default="Trends", key=f"education_pulse_phase2_{actor}")
    if view == "Trends":
        left, right = st.columns(2)
        with left:
            render_line(dated_counts(publications, "published_at", period="month", date_label="Month", value_label="Publications"), "Month", "Publications", title="Publication timeline")
        with right:
            render_bar(count_rows(publications, "record_type", label="Record type", value_label="Publications"), "Record type", "Publications", title="Source distribution")
        topics: Counter[str] = Counter()
        for row in news:
            topics.update(str(topic) for topic in row.get("topics", []) if topic)
        render_bar([{"Topic": name, "Items": count} for name, count in topics.most_common(20)], "Topic", "Items", title="Topic-growth evidence", empty_detail="No structured topic metadata is available.")
    elif view == "Evidence quality":
        rows = []
        for item in publications:
            state = "Retraction warning" if item.get("retraction_state") not in {"", "none"} else "Preprint" if item.get("record_type") == "preprint" else "Metadata available"
            rows.append({"Publication": item.get("title"), "Evidence state": state, "Source": item.get("source_url")})
        if rows:
            st.dataframe(rows, hide_index=True, column_config={"Publication": st.column_config.TextColumn(pinned=True), "Source": st.column_config.LinkColumn()})
        else:
            render_empty_state("No evidence metadata", "Indicators appear after lawful source metadata is stored.", icon=":material/fact_check:")
    elif view == "Collections":
        saved = {(row.get("resource_type"), row.get("resource_id")) for row in snapshot.get("saved", [])}
        rows = [{"Publication": item.get("title"), "Saved": ("publication", item.get("id")) in saved, "Published": item.get("published_at"), "Source": item.get("source_url")} for item in publications]
        if rows:
            st.dataframe(rows, hide_index=True, column_config={"Publication": st.column_config.TextColumn(pinned=True), "Saved": st.column_config.CheckboxColumn(), "Source": st.column_config.LinkColumn()})
        else:
            render_empty_state("No collection", "Save a persisted publication to build a collection.", icon=":material/bookmarks:")
    else:
        sources = snapshot.get("sources", [])
        if sources:
            st.dataframe([{"Source": row.get("name"), "Type": friendly(row.get("source_type")), "Configured": bool(row.get("configured")), "State": friendly(row.get("state"))} for row in sources], hide_index=True, column_config={"Configured": st.column_config.CheckboxColumn()})
        else:
            render_empty_state("No source configuration", "Unavailable providers remain explicitly unavailable.", icon=":material/cloud_off:")
def _safe_simulation(scope: str) -> None:
    st.subheader(":material/science: Safe visual simulation")
    simulation = st.selectbox("Simulation", ["Population growth", "Mendelian genetics", "Enzyme kinetics"], key=f"{scope}_simulation")
    st.warning("Conceptual simulation only. It is not a physical laboratory protocol.", icon=":material/health_and_safety:")
    if simulation == "Population growth":
        capacity = st.slider("Carrying capacity", 100, 2000, 1000, key=f"{scope}_capacity")
        rate = st.slider("Growth rate", 0.05, 1.0, 0.25, key=f"{scope}_rate")
        initial = st.slider("Initial population", 1, min(200, capacity - 1), 20, key=f"{scope}_initial")
        rows, value = [], float(initial)
        for step in range(31):
            rows.append({"Time step": step, "Population": value})
            value += rate * value * (1 - value / capacity)
        render_line(rows, "Time step", "Population", title="Logistic population model")
        st.caption("Model: N(t+1) = N(t) + rN(t)(1 - N(t)/K). Parameters are visible.")
    elif simulation == "Mendelian genetics":
        rows = [{"Genotype": "AA", "Expected proportion": 0.25}, {"Genotype": "Aa", "Expected proportion": 0.5}, {"Genotype": "aa", "Expected proportion": 0.25}]
        render_bar(rows, "Genotype", "Expected proportion", title="Aa × Aa expected genotype distribution")
        st.caption("Deterministic conceptual proportions; no physical experiment is instructed.")
    else:
        vmax = st.slider("Vmax", 0.5, 10.0, 5.0, key=f"{scope}_vmax")
        km = st.slider("Km", 0.1, 10.0, 2.0, key=f"{scope}_km")
        rows = [{"Substrate": n / 2, "Velocity": vmax * (n / 2) / (km + n / 2)} for n in range(1, 41)]
        render_line(rows, "Substrate", "Velocity", title="Michaelis-Menten model")
        st.caption("Model: v = Vmax[S] / (Km + [S]). Mathematical visualization only.")

def render_module_visual_studio(service: EducationPhase2, actor: str, institution_id: str, run: Run) -> None:
    by_key = {module.key: module for module in MODULES}
    selected = st.selectbox("Visual module", list(by_key), format_func=lambda key: by_key[key].name, key=f"{_scope(actor,institution_id)}_module")
    definition = by_key[selected]
    icon, identity, stages = MODULE_PHASE2[selected]
    records = run(lambda: service.module_records(actor, institution_id, selected)) or []
    breadcrumbs(("Education", "Visual studio", definition.name))
    identity_card(definition.name, identity, icon=icon, badges=((f"{len(records)} persisted records", "available" if records else "pending"),), caption=definition.boundary)
    metric_grid([
        {"label": "Persisted records", "value": len(records)},
        {"label": "Workflow states", "value": len({row.get("state") for row in records})},
        {"label": "Demo-labelled", "value": sum(str(row.get("source_status")) == "synthetic_demo" for row in records)},
        {"label": "Latest version", "value": max([int(row.get("version") or 0) for row in records] or [0])},
    ])
    render_bar(count_rows(records, "state", label="State", value_label="Records"), "State", "Records", title="Stored workflow-state distribution", empty_detail=f"No {definition.name} records are visible.")
    normalized = {stage.lower().replace(" ", "_"): stage for stage in stages}
    current = str(records[0].get("state") if records else stages[0]).lower()
    render_workflow(stages, normalized.get(current, stages[0]), title="Professional workflow")
    if records:
        evidence = []
        for record in records:
            payload = record.get("payload") or {}
            populated = sum(value not in (None, "", [], {}) for value in payload.values())
            evidence.append({"Record": record.get("title"), "Type": friendly(record.get("record_type")), "State": friendly(record.get("state")), "Evidence fields": populated, "Updated": record.get("updated_at")})
        st.dataframe(evidence, hide_index=True, column_config={"Record": st.column_config.TextColumn(pinned=True), "Updated": st.column_config.DatetimeColumn(format="MMM DD, YYYY, h:mm a")})
        render_timeline([{"title": row.get("title"), "detail": friendly(row.get("record_type")), "state": row.get("state"), "when": row.get("updated_at"), "page": "pages/343_BioIntel_Education_Universe.py"} for row in records], title="Module activity timeline")
    if selected == "virtual_science_lab":
        _safe_simulation(_scope(actor, institution_id))
    elif selected == "learning_analytics":
        payload = (records[0].get("payload") if records else {}) or {}
        render_metric_explanation(str(payload.get("metric_definition") or "No definition stored."), "Defined by persisted metric record", str(payload.get("source_events") or "No events stored."), "Events outside date/permission boundaries.", str(payload.get("date_range") or "Not recorded"), 100 if payload.get("source_events") else 0, str(records[0].get("updated_at") if records else "Not calculated"), "Risk scores require a definition and human review.")
    elif selected == "bioinformatics_sandbox":
        payload = (records[0].get("payload") if records else {}) or {}
        rows = [{"Field": label, "Value": payload.get(key, "Not recorded")} for key, label in (("dataset_label", "Dataset"), ("method", "Method"), ("parameters", "Parameters"), ("resource_limit_seconds", "Resource limit"), ("limitations", "Limitations"))]
        st.dataframe(rows, hide_index=True)
        st.caption("Unrestricted command execution is not exposed.")
    elif selected == "lecture_intelligence":
        payload = (records[0].get("payload") if records else {}) or {}
        st.caption(f"Persisted processing state: {payload.get('processing_status','Not started')}. No fabricated duration or completion estimate is displayed.")
    elif selected == "offline_learning":
        operations = service.platform._all("SELECT state,COUNT(*) records FROM education_universe_sync_operations WHERE institution_id=? GROUP BY state", (institution_id,))
        render_bar([{"State": friendly(row["state"]), "Operations": int(row["records"])} for row in operations], "State", "Operations", title="Offline sync queue", empty_detail="No offline sync operations exist.")

def render_report_center(service: EducationPhase2, actor: str, institution_id: str, run: Run) -> None:
    st.subheader(":material/description: Professional report center")
    st.caption("Role-permitted persisted records only. Scheduled delivery remains configuration-required until a scheduler is connected.")
    report_type = st.selectbox("Report", list(REPORT_TYPES), format_func=friendly, key=f"{_scope(actor,institution_id)}_report")
    rows = run(lambda: service.report_rows(actor, institution_id, report_type))
    if rows is None:
        return
    metric_grid([{"label": "Matching rows", "value": len(rows)}, {"label": "Report type", "value": friendly(report_type)}, {"label": "Data source", "value": "Persisted"}])
    if rows:
        st.dataframe(rows[:500], hide_index=True)
    else:
        render_empty_state("No report rows", "No role-permitted records match this report.", icon=":material/description:")
    title = st.text_input("Saved report title", value=f"{friendly(report_type)} report", key=f"{_scope(actor,institution_id)}_title")
    schedule = st.toggle("Request scheduled delivery", key=f"{_scope(actor,institution_id)}_schedule")
    frequency = st.selectbox("Requested frequency", ["Weekly", "Monthly"], disabled=not schedule, key=f"{_scope(actor,institution_id)}_frequency")
    with st.container(horizontal=True):
        if st.button("Save report", type="primary", icon=":material/save:", key=f"{_scope(actor,institution_id)}_save_report"):
            saved = run(lambda: service.save_report(actor, institution_id, report_type, title, {}, {"frequency": frequency} if schedule else None))
            if saved:
                st.success("Report saved." if not schedule else "Report saved; scheduler configuration is required.", icon=":material/check_circle:")
        st.download_button("CSV", data=service.export_csv(rows), file_name=f"biointel-{report_type}.csv", mime="text/csv", icon=":material/download:")
        st.download_button("XLSX", data=service.export_xlsx(rows, friendly(report_type)), file_name=f"biointel-{report_type}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", icon=":material/download:")
        st.download_button("PDF", data=service.export_pdf(rows, title), file_name=f"biointel-{report_type}.pdf", mime="application/pdf", icon=":material/picture_as_pdf:")
    saved_reports = run(lambda: service.list_reports(actor, institution_id)) or []
    if saved_reports:
        st.dataframe([{"Title": row["title"], "Type": friendly(row["report_type"]), "Schedule": friendly(row["schedule_state"]), "Updated": row["updated_at"]} for row in saved_reports], hide_index=True)
def render_branding_center(service: EducationPhase2, actor: str, institution_id: str, run: Run) -> None:
    st.subheader(":material/palette: Institution branding")
    branding = run(lambda: service.branding(actor, institution_id)) or {}
    identity_card(
        str(branding.get("campus_name") or "Institution identity"),
        str(branding.get("login_welcome_text") or "A restrained institutional layer across Education experiences."),
        icon=":material/domain:",
        badges=((str(branding.get("course_cover_style") or "scientific-grid").replace("-", " ").title(), "info"),),
        caption=str(branding.get("footer_information") or "No footer information configured."),
    )
    logo_path = str(branding.get("logo_storage_path") or "")
    if logo_path and service.logo_path(branding):
        st.image(service.logo_path(branding), width=144)
    roles = _roles(service, actor, institution_id)
    if not roles & ADMIN:
        st.info("Branding settings are visible here and editable by institution administrators.", icon=":material/lock:")
        return
    with st.form(f"{_scope(actor,institution_id)}_branding"):
        campus = st.text_input("Campus display name", value=str(branding.get("campus_name") or ""))
        accent = st.color_picker("Institution accent", value=str(branding.get("accent_color") or "#22D3EE"))
        welcome = st.text_area("Welcome message", value=str(branding.get("login_welcome_text") or ""), max_chars=240)
        footer = st.text_area("Footer information", value=str(branding.get("footer_information") or ""), max_chars=300)
        certificate = st.text_input("Certificate footer", value=str(branding.get("certificate_footer") or ""), max_chars=180)
        cover = st.selectbox("Course-cover style", ["scientific-grid", "molecular-lines", "clean-academic"], index=max(0, ["scientific-grid", "molecular-lines", "clean-academic"].index(str(branding.get("course_cover_style") or "scientific-grid"))) if str(branding.get("course_cover_style") or "scientific-grid") in ["scientific-grid", "molecular-lines", "clean-academic"] else 0)
        logo = st.file_uploader("Institution logo (PNG or JPEG, max 2 MB)", type=["png", "jpg", "jpeg"])
        submitted = st.form_submit_button("Save institution branding", type="primary", icon=":material/save:")
    if submitted:
        saved = run(lambda: service.save_branding(actor, institution_id, campus_name=campus, accent_color=accent, login_welcome_text=welcome, footer_information=footer, certificate_footer=certificate, course_cover_style=cover, logo_name=logo.name if logo else "", logo_mime=logo.type if logo else "", logo_bytes=logo.getvalue() if logo else None))
        if saved:
            st.success("Institution branding saved.", icon=":material/check_circle:")
            st.rerun()


def render_presentation_launcher(service: EducationPhase2, actor: str, institution_id: str, run: Run) -> None:
    st.subheader(":material/co_present: Presentation mode")
    st.caption("A focused, read-only demonstration route. Synthetic-data disclosure remains permanently visible.")
    if not st.session_state.get("education_demo_mode", False):
        render_empty_state("Demo workspace required", "Load the isolated Education demo workspace before starting presentation mode.", icon=":material/science:")
        return
    from .demo import manifest
    data = manifest()
    personas = [item for item in data.get("personas", []) if item.get("institution_id") == institution_id]
    scenarios = [item for item in data.get("scenarios", []) if item.get("institution_id") == institution_id]
    persona_by_id = {str(item["id"]): item for item in personas}
    scenario_by_id = {str(item["id"]): item for item in scenarios}
    if not persona_by_id or not scenario_by_id:
        render_empty_state("No presentation routes", "This demo institution has no configured persona-and-scenario route.")
        return
    persona_id = st.selectbox("Presentation persona", list(persona_by_id), format_func=lambda value: str(persona_by_id[value].get("switch_label") or value), key=f"{_scope(actor,institution_id)}_present_persona")
    matching = [key for key, value in scenario_by_id.items() if value.get("persona_id") == persona_id]
    scenario_options = matching or list(scenario_by_id)
    scenario_id = st.selectbox("Scenario", scenario_options, format_func=lambda value: str(scenario_by_id[value].get("title") or value), key=f"{_scope(actor,institution_id)}_present_scenario")
    scenario = scenario_by_id[scenario_id]
    st.caption("Route: " + " → ".join(str(item).replace("_", " ").title() for item in scenario.get("modules", [])))
    acknowledged = st.checkbox("I acknowledge that every record shown in this presentation is synthetic demonstration data.", key=f"{_scope(actor,institution_id)}_present_ack")
    if st.button("Start presentation", type="primary", icon=":material/slideshow:", disabled=not acknowledged, key=f"{_scope(actor,institution_id)}_present_start"):
        started = run(lambda: service.start_presentation(actor, institution_id, persona_id, scenario_id, acknowledged))
        if started:
            st.session_state.education_presentation_mode = True
            st.session_state.education_presentation_run = started["id"]
            st.session_state.education_presentation_owner = actor
            st.session_state.education_presentation_persona = persona_id
            st.session_state.education_presentation_scenario = scenario_id
            st.session_state.education_actor = persona_id
            st.rerun()


def render_presentation_mode(service: EducationPhase2, actor: str, institution_id: str, run: Run) -> None:
    from .demo import DEMO_BADGE, manifest
    data = manifest()
    personas = {str(item["id"]): item for item in data.get("personas", [])}
    scenarios = {str(item["id"]): item for item in data.get("scenarios", [])}
    persona_id = str(st.session_state.get("education_presentation_persona") or actor)
    scenario_id = str(st.session_state.get("education_presentation_scenario") or "")
    persona = personas.get(persona_id, {})
    scenario = scenarios.get(scenario_id, {})
    st.warning(DEMO_BADGE, icon=":material/science:")
    branding = run(lambda: service.branding(actor, institution_id)) or {}
    st.title(str(branding.get("campus_name") or "BioIntel Education Universe"))
    st.caption(f"Presentation persona: {persona.get('name', persona_id)} · {scenario.get('title', 'Guided Education scenario')}")
    with st.container(horizontal=True):
        st.badge("SYNTHETIC DEMO", icon=":material/science:", color="violet")
        st.badge(str(persona.get("persona_type") or "Education persona"), icon=":material/person:", color="blue")
        for module in scenario.get("modules", []):
            st.badge(str(module).replace("_", " ").title(), color="gray")
    snapshot = run(lambda: service.dashboard_snapshot(actor, institution_id)) or {}
    metric_grid([{"label": item["Metric"], "value": item["Value"]} for item in _summary(snapshot)[:4]])
    activity = run(lambda: service.activity_stream(actor, institution_id, limit=12)) or []
    render_timeline(activity, title="Scenario evidence trail", empty_detail="No role-permitted persisted activity is available for this persona.")
    st.info("Presentation mode is read-only. Development controls, raw identifiers and configuration forms are hidden.", icon=":material/visibility:")
    if st.button("Exit presentation", type="primary", icon=":material/logout:", key="education_presentation_exit"):
        owner = str(st.session_state.get("education_presentation_owner") or actor)
        run_id = str(st.session_state.get("education_presentation_run") or "")
        if run_id:
            run(lambda: service.finish_presentation(owner, run_id))
        st.session_state.education_actor = owner
        for key in ("education_presentation_mode", "education_presentation_run", "education_presentation_owner", "education_presentation_persona", "education_presentation_scenario"):
            st.session_state.pop(key, None)
        st.rerun()


__all__ = [
    "render_advanced_command_center", "render_classroom_visuals", "render_academy_visuals",
    "render_pulse_visuals", "render_module_visual_studio", "render_report_center",
    "render_branding_center", "render_presentation_launcher", "render_presentation_mode",
]