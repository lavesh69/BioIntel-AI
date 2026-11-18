from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ._streamlit_compat import st
from .experience import render_app_header, render_role_snapshot, render_workspace_context
from biointel.ui.frontend_v10 import empty_state
from .phase6 import EducationPhase6Service
from .phase6_visuals import (
    activity_timeline,
    assignment_funnel,
    attendance_heatmap,
    blueprint_matrix,
    chat_messages,
    exam_lifecycle,
    exam_monitor_grid,
    histogram,
    integration_topology,
    mastery_graph,
    metric_cards,
    organization_tree,
    queue_board,
    timetable_calendar,
)
from .platform import EducationError
from .universe import EducationUniverse
from .ui import _actor, _demo_controls, _identity_input, _institution, _page_platform, _run


def _subjects(platform: Any, actor: str, institution_id: str) -> list[dict[str, Any]]:
    roles = {row["role"] for row in platform.membership(actor, institution_id)}
    if roles & {"school_student", "college_student", "university_student"}:
        return platform._all(
            """SELECT DISTINCT s.id,s.code,s.name FROM subjects s JOIN enrollments e ON e.subject_id=s.id
            WHERE s.institution_id=? AND e.student_id=? AND e.state='active' ORDER BY s.code""",
            (institution_id, actor),
        )
    if roles & {"platform_administrator", "institution_administrator", "principal", "dean", "registrar", "department_head"}:
        return platform._all("SELECT id,code,name FROM subjects WHERE institution_id=? AND state='active' ORDER BY code", (institution_id,))
    return platform._all(
        """SELECT DISTINCT s.id,s.code,s.name FROM subjects s JOIN teacher_assignments t ON t.subject_id=s.id
        WHERE s.institution_id=? AND t.teacher_id=? AND t.state='active' ORDER BY s.code""",
        (institution_id, actor),
    )


def _students(platform: Any, institution_id: str, subject_id: str | None = None) -> list[str]:
    if subject_id:
        rows = platform._all("SELECT student_id FROM enrollments WHERE institution_id=? AND subject_id=? AND state='active' ORDER BY student_id", (institution_id, subject_id))
    else:
        rows = platform._all(
            """SELECT DISTINCT m.user_id student_id FROM memberships m
            WHERE m.institution_id=? AND m.role IN ('school_student','college_student','university_student') AND m.state='active' ORDER BY m.user_id""",
            (institution_id,),
        )
    return [row["student_id"] for row in rows]


def _dashboard(service: EducationPhase6Service, platform: Any, actor: str, institution_id: str) -> None:
    data = _run(lambda: service.visual_dashboard(actor, institution_id)) or {}
    calendar = data.get("calendar", {"days": [], "by_day": {}})
    assignments = platform._all("SELECT state,COUNT(*) n FROM assignments WHERE institution_id=? GROUP BY state", (institution_id,))
    submission = platform._one("SELECT COUNT(*) n FROM submissions WHERE institution_id=? AND state='submitted'", (institution_id,)) or {"n": 0}
    late = platform._one("SELECT COUNT(*) n FROM submissions WHERE institution_id=? AND late=1", (institution_id,)) or {"n": 0}
    graded = platform._one("SELECT COUNT(*) n FROM grades WHERE institution_id=?", (institution_id,)) or {"n": 0}
    counts = {row["state"]: int(row["n"]) for row in assignments}
    counts.update({"submitted": int(submission["n"]), "late": int(late["n"]), "graded": int(graded["n"])})
    st.markdown(metric_cards([
        ("This week", len(calendar.get("entries", [])), "Visible classes and labs", "▦"),
        ("Unread", data.get("unread_notifications", 0), "Notifications needing attention", "●"),
        ("Assignments", sum(int(row["n"]) for row in assignments), "Institution assignment records", "✓"),
        ("Recent activity", len(data.get("recent_activity", [])), "Audited institutional events", "⌁"),
    ]), unsafe_allow_html=True)
    st.subheader("Week at a glance")
    st.markdown(timetable_calendar(calendar), unsafe_allow_html=True)
    left, right = st.columns([1, 1], gap="medium")
    with left:
        st.subheader("Assignment lifecycle")
        st.markdown(assignment_funnel(counts), unsafe_allow_html=True)
    with right:
        st.subheader("Recent institutional activity")
        st.markdown(activity_timeline(data.get("recent_activity", [])), unsafe_allow_html=True)


def _classroom(service: EducationPhase6Service, platform: Any, actor: str, institution_id: str) -> None:
    subjects = _subjects(platform, actor, institution_id)
    start = st.date_input("Calendar starts", value=datetime.now(timezone.utc).date(), key="phase6-calendar-start")
    calendar = _run(lambda: service.timetable_calendar(actor, institution_id, start_day=start, days=7)) or {"days": [], "by_day": {}}
    st.markdown(timetable_calendar(calendar), unsafe_allow_html=True)
    if not subjects:
        st.info("Create or join a subject to unlock gradebook and attendance visuals.")
        return
    subject_id = st.selectbox("Subject", [row["id"] for row in subjects], format_func=lambda value: next(f"{row['code']} · {row['name']}" for row in subjects if row["id"] == value), key="phase6-class-subject")
    grade_tab, attendance_tab = st.tabs(["Gradebook", "Attendance"])
    with grade_tab:
        gradebook = _run(lambda: service.gradebook(actor, institution_id, subject_id))
        if gradebook:
            stats = gradebook["assignment_stats"]
            st.markdown(metric_cards([
                ("Learners", len(gradebook["rows"]), "Visible subject roster", "◎"),
                ("Assessments", len(gradebook["assignments"]), "Assignment columns", "▤"),
                ("Graded", sum(int(item["graded"]) for item in stats), "Released grade records", "✓"),
                ("Average", f"{round(sum(item['average_percent'] or 0 for item in stats)/len(stats),1) if stats else 0}%", "Across graded assessments", "↗"),
            ]), unsafe_allow_html=True)
            st.dataframe(gradebook["rows"], width="stretch", hide_index=True)
            if stats:
                labels = [item["title"][:12] for item in stats]
                values = [round(item["average_percent"] or 0) for item in stats]
                st.markdown(histogram(values, labels, title="Assignment average percentage"), unsafe_allow_html=True)
    with attendance_tab:
        heat = _run(lambda: service.attendance_heatmap(actor, institution_id, subject_id=subject_id)) or {"summary": []}
        st.markdown(attendance_heatmap(heat["summary"]), unsafe_allow_html=True)
        if heat["summary"]:
            st.dataframe(heat["summary"], width="stretch", hide_index=True)


def _intelligence(service: EducationPhase6Service, platform: Any, actor: str, institution_id: str) -> None:
    subjects = _subjects(platform, actor, institution_id)
    roles = {row["role"] for row in platform.membership(actor, institution_id)}
    subject_id = None
    if subjects:
        subject_id = st.selectbox("Subject context", [row["id"] for row in subjects], format_func=lambda value: next(f"{row['code']} · {row['name']}" for row in subjects if row["id"] == value), key="phase6-intelligence-subject")
    student_id = actor
    if roles & {"platform_administrator", "institution_administrator", "principal", "dean", "registrar", "department_head", "subject_teacher", "class_teacher", "lecturer", "professor", "assistant_professor"}:
        students = _students(platform, institution_id, subject_id)
        if students:
            student_id = st.selectbox("Learner", students, key="phase6-intelligence-student")
    graph = _run(lambda: service.knowledge_graph(actor, institution_id, student_id=student_id, subject_id=subject_id))
    if graph:
        st.subheader("Concept mastery and prerequisites")
        st.markdown(mastery_graph(graph), unsafe_allow_html=True)
        if graph.get("recommendations"):
            st.dataframe(graph["recommendations"], width="stretch", hide_index=True)
    st.divider()
    st.subheader("Shiro grounded conversation studio")
    conversations = _run(lambda: service.conversations(actor, institution_id)) or []
    sidebar, thread = st.columns([.34, .66], gap="medium")
    selected_id = ""
    with sidebar:
        with st.form("phase6-new-conversation"):
            title = st.text_input("Conversation title", value="Study session")
            mode = st.selectbox("Mode", ["guided_learning", "revision", "teacher_planning"])
            language = st.selectbox("Language", ["English", "Hindi", "Hinglish"])
            create = st.form_submit_button("New conversation", type="primary")
        if create:
            created = _run(lambda: service.create_conversation(actor, institution_id, subject_id=subject_id, title=title, mode=mode, language=language))
            if created:
                st.session_state.phase6_conversation_id = created["id"]
                st.rerun()
        if conversations:
            ids = [row["id"] for row in conversations]
            current = st.session_state.get("phase6_conversation_id")
            index = ids.index(current) if current in ids else 0
            selected_id = st.selectbox("Conversations", ids, index=index, format_func=lambda value: next(row["title"] for row in conversations if row["id"] == value))
            st.session_state.phase6_conversation_id = selected_id
    with thread:
        if selected_id:
            conversation = _run(lambda: service.conversation(actor, selected_id))
            if conversation:
                st.markdown(chat_messages(conversation["messages"]), unsafe_allow_html=True)
                with st.form("phase6-chat-prompt", clear_on_submit=True):
                    question = st.text_area("Ask Shiro", placeholder="Explain the concept using only indexed course evidence.")
                    ask = st.form_submit_button("Send", type="primary")
                if ask:
                    if _run(lambda: service.ask_conversation(actor, selected_id, question)):
                        st.rerun()
        else:
            st.info("Create a conversation to begin.")


def _examinations(service: EducationPhase6Service, platform: Any, actor: str, institution_id: str) -> None:
    exams = _run(lambda: service.exams.list_exams(actor, institution_id)) or []
    st.markdown(exam_lifecycle(exams), unsafe_allow_html=True)
    if not exams or not service.permissions.has(actor, institution_id, "exam.monitor"):
        st.info("Exam analytics appear for authorized examination staff after an exam is created.")
        return
    exam_id = st.selectbox("Examination", [row["id"] for row in exams], format_func=lambda value: next(row["title"] for row in exams if row["id"] == value), key="phase6-exam-select")
    analytics = _run(lambda: service.exam_analytics(actor, exam_id))
    if not analytics:
        return
    summary = analytics["summary"]
    st.markdown(metric_cards([
        ("Candidates", summary["candidates"], "Started attempts", "◉"),
        ("Submitted", summary["submitted"], "Sealed attempts", "✓"),
        ("Average", "—" if summary["average_percent"] is None else f"{summary['average_percent']}%", "Score percentage", "↗"),
        ("Pass rate", f"{summary['pass_rate']}%", "Current 40% analytical threshold", "◎"),
    ]), unsafe_allow_html=True)
    st.subheader("Live candidate grid")
    st.markdown(exam_monitor_grid(analytics["sessions"]), unsafe_allow_html=True)
    left, right = st.columns(2, gap="medium")
    with left:
        st.markdown(histogram(analytics["histogram"], [f"{i*10}-{i*10+9}%" for i in range(10)], title="Score distribution"), unsafe_allow_html=True)
    with right:
        st.markdown(blueprint_matrix(analytics["question_rows"]), unsafe_allow_html=True)
    st.subheader("Question response diagnostics")
    st.dataframe(analytics["question_rows"], width="stretch", hide_index=True)


def _institution(service: EducationPhase6Service, platform: Any, actor: str, institution_id: str) -> None:
    if not service.permissions.has(actor, institution_id, "institution.manage"):
        st.info("Institution operations visuals require institution management permission.")
        return
    hierarchy = _run(lambda: service.phase5.hierarchy(actor, institution_id)) or {"campuses": []}
    institution = platform._one("SELECT id,name,kind FROM institutions WHERE id=?", (institution_id,)) or {"id": institution_id, "name": "Institution"}
    unit_by_id = {row["id"]: row for row in hierarchy.get("academic_units", [])}
    for campus in hierarchy.get("campuses", []):
        campus["units"] = [unit_by_id[unit_id] for unit_id in campus.get("unit_ids", []) if unit_id in unit_by_id]
    hierarchy["institution"] = institution
    operations = _run(lambda: service.job_operations(actor, institution_id)) or {"jobs": [], "workers": []}
    integrations = _run(lambda: service.integration_operations(actor, institution_id)) or {"integrations": [], "runs": []}
    st.subheader("Institution organization")
    st.markdown(organization_tree(hierarchy), unsafe_allow_html=True)
    st.subheader("Background operations")
    st.markdown(queue_board(operations), unsafe_allow_html=True)
    controls = st.columns(3)
    with controls[0]:
        with st.form("phase6-worker-register"):
            worker_id = st.text_input("Worker ID", value="local-worker-01")
            queues = st.multiselect("Queues", ["default", "reports", "backup", "integrations", "media"], default=["default"])
            if st.form_submit_button("Register worker"):
                if _run(lambda: service.register_worker(actor, institution_id, worker_id, queues=queues, version="phase6")):
                    st.rerun()
    with controls[1]:
        with st.form("phase6-backup-schedule"):
            name = st.text_input("Backup schedule", value="Daily institutional backup")
            frequency = st.selectbox("Frequency", ["daily", "weekly"])
            hour = st.number_input("UTC hour", 0, 23, 2)
            retention = st.number_input("Retention copies", 1, 365, 14)
            if st.form_submit_button("Save schedule"):
                if _run(lambda: service.create_backup_schedule(actor, institution_id, name, frequency=frequency, hour_utc=int(hour), weekday=0 if frequency == "weekly" else None, retention_count=int(retention))):
                    st.success("Backup schedule saved.")
    with controls[2]:
        if st.button("Enqueue due backups", type="primary"):
            result = _run(lambda: service.enqueue_due_backups(actor, institution_id))
            if result:
                st.success(f"Enqueued {result['scheduled']} scheduled backup(s).")
    st.subheader("Integration topology")
    st.markdown(integration_topology(integrations["integrations"], integrations["runs"]), unsafe_allow_html=True)
    if integrations["integrations"]:
        integration_id = st.selectbox("Integration to synchronize", [row["id"] for row in integrations["integrations"]], format_func=lambda value: next(row["name"] for row in integrations["integrations"] if row["id"] == value))
        direction = st.selectbox("Sync direction", ["pull", "push", "bidirectional"])
        entity = st.selectbox("Entity", ["courses", "roster", "assignments", "grades", "attendance"])
        if st.button("Queue governed sync"):
            if _run(lambda: service.start_integration_sync(actor, integration_id, direction=direction, entity_type=entity)):
                st.success("Sync run queued. External completion remains provider-dependent.")
                st.rerun()
    if integrations["runs"]:
        st.dataframe(integrations["runs"], width="stretch", hide_index=True)
    st.subheader("External qualification laboratory")
    st.caption("Runs bounded public-network or runtime connection checks. Secrets must use env:VARIABLE references and are never returned to the UI.")
    qtabs = st.tabs(["Identity", "Database", "Storage", "Integrations", "History"])
    with qtabs[0]:
        providers = platform._all("SELECT id,display_name,provider_type,state FROM education_identity_providers WHERE institution_id=? ORDER BY created_at DESC", (institution_id,))
        if providers:
            provider_id = st.selectbox("OIDC provider", [row["id"] for row in providers], format_func=lambda value: next(row["display_name"] for row in providers if row["id"] == value), key="phase6-qual-idp")
            if st.button("Verify public OIDC metadata"):
                st.json(_run(lambda: service.external.verify_identity_provider(actor, provider_id)) or {})
        else:
            st.info("Configure an identity provider first.")
    with qtabs[1]:
        profiles = platform._all("SELECT id,name,engine,state FROM education_database_profiles WHERE institution_id=? ORDER BY created_at DESC", (institution_id,))
        if profiles:
            profile_id = st.selectbox("Database profile", [row["id"] for row in profiles], format_func=lambda value: next(f"{row['name']} · {row['engine']}" for row in profiles if row["id"] == value), key="phase6-qual-db")
            if st.button("Run database connection qualification"):
                st.json(_run(lambda: service.external.verify_database_profile(actor, profile_id)) or {})
        else:
            st.info("Configure a database profile first.")
    with qtabs[2]:
        backends = platform._all("SELECT id,name,backend_type,state FROM education_storage_backends WHERE institution_id=? ORDER BY created_at DESC", (institution_id,))
        if backends:
            backend_id = st.selectbox("Storage backend", [row["id"] for row in backends], format_func=lambda value: next(f"{row['name']} · {row['backend_type']}" for row in backends if row["id"] == value), key="phase6-qual-storage")
            if st.button("Run storage qualification"):
                st.json(_run(lambda: service.external.verify_storage_backend(actor, backend_id)) or {})
        else:
            st.info("Configure a storage backend first.")
    with qtabs[3]:
        if integrations["integrations"]:
            qualification_integration = st.selectbox("Provider", [row["id"] for row in integrations["integrations"]], format_func=lambda value: next(row["name"] for row in integrations["integrations"] if row["id"] == value), key="phase6-qual-integration")
            if st.button("Run provider connection qualification"):
                st.json(_run(lambda: service.external.verify_integration(actor, qualification_integration)) or {})
        else:
            st.info("Configure an integration first.")
    with qtabs[4]:
        history = _run(lambda: service.external.history(actor, institution_id)) or []
        if history:
            st.dataframe(history, width="stretch", hide_index=True)
        else:
            empty_state("No qualification evidence", "No external database, storage, identity or integration check has been persisted.", icon="✓", action_hint="Run a bounded qualification check from Institution operations.")



def _academy(service: EducationPhase6Service, platform: Any, actor: str, institution_id: str) -> None:
    roles = {row["role"] for row in platform.membership(actor, institution_id)}
    if roles & {"school_student", "college_student", "university_student"}:
        courses = platform._all(
            """SELECT c.* FROM courses c JOIN academy_enrollments e ON e.course_id=c.id
            WHERE c.institution_id=? AND e.student_id=? AND e.state='active' ORDER BY c.updated_at DESC""",
            (institution_id, actor),
        )
    elif roles & {"platform_administrator", "institution_administrator", "principal", "dean", "department_head"}:
        courses = platform._all("SELECT * FROM courses WHERE institution_id=? ORDER BY updated_at DESC", (institution_id,))
    else:
        courses = platform._all("SELECT * FROM courses WHERE institution_id=? AND educator_id=? ORDER BY updated_at DESC", (institution_id, actor))
    lecture_count = platform._one("SELECT COUNT(*) n FROM lectures WHERE institution_id=?", (institution_id,)) or {"n": 0}
    enrollment_count = platform._one("SELECT COUNT(*) n FROM academy_enrollments WHERE institution_id=? AND state='active'", (institution_id,)) or {"n": 0}
    certificates = platform._one("SELECT COUNT(*) n FROM certificates WHERE institution_id=? AND revoked=0", (institution_id,)) or {"n": 0}
    st.markdown(metric_cards([
        ("Courses", len(courses), "Visible Academy courses", "▶"),
        ("Lectures", lecture_count["n"], "Stored lecture records", "▤"),
        ("Enrollments", enrollment_count["n"], "Active learner enrollments", "◎"),
        ("Credentials", certificates["n"], "Active signed certificates", "◆"),
    ]), unsafe_allow_html=True)
    if not courses:
        empty_state("No visible Academy courses", "This role has no published or managed courses in the current institution.", icon="▷", action_hint="Enroll in a course or publish one from Academy.")
        return
    cards = []
    for course in courses[:12]:
        lectures = platform._all("SELECT id,title,state,duration_seconds FROM lectures WHERE course_id=? ORDER BY created_at", (course["id"],))
        sections = platform._all("SELECT id,parent_id,title,section_type,position FROM course_sections WHERE course_id=? ORDER BY position", (course["id"],))
        progress = 0
        if roles & {"school_student", "college_student", "university_student"} and lectures:
            done = platform._one(
                """SELECT COUNT(*) n FROM watch_progress w JOIN lectures l ON l.id=w.lecture_id
                WHERE l.course_id=? AND w.user_id=? AND w.completed=1""", (course["id"], actor),
            ) or {"n": 0}
            progress = round(int(done["n"]) / len(lectures) * 100)
        cards.append(
            f'<article class="edu-module-card"><div class="edu-kicker">{course["difficulty"]} · {course["state"]}</div>'
            f'<h3>{course["title"]}</h3><p>{course["description"] or "Scientific course workspace"}</p>'
            f'<div class="edu-progress-track"><div class="edu-progress-fill" style="width:{progress}%"></div></div>'
            f'<span class="edu-chip">{len(sections)} sections</span> <span class="edu-chip">{len(lectures)} lectures</span> <span class="edu-chip">{progress}% complete</span></article>'
        )
    st.markdown('<div class="edu-platform-grid">' + ''.join(cards) + '</div>', unsafe_allow_html=True)
    course_id = st.selectbox("Course curriculum", [row["id"] for row in courses], format_func=lambda value: next(row["title"] for row in courses if row["id"] == value), key="phase6-academy-course")
    sections = platform._all("SELECT id,parent_id,title,section_type,position FROM course_sections WHERE course_id=? ORDER BY position", (course_id,))
    lectures = platform._all("SELECT id,title,state,duration_seconds,processing_state FROM lectures WHERE course_id=? ORDER BY created_at", (course_id,))
    left, right = st.columns([.55, .45], gap="medium")
    with left:
        st.subheader("Curriculum tree")
        if sections:
            for section in sections:
                prefix = "↳" if section.get("parent_id") else "▦"
                st.markdown(f"**{prefix} {section['title']}** · `{section['section_type']}`")
        else:
            empty_state("No curriculum sections", "The selected course has no section hierarchy yet.", icon="▤", action_hint="Create a section in the curriculum builder.")
    with right:
        st.subheader("Lecture media readiness")
        if lectures:
            st.dataframe(lectures, width="stretch", hide_index=True)
        else:
            empty_state("No lectures yet", "The selected course does not contain a lecture record.", icon="▶", action_hint="Add the first lecture and publish it when reviewed.")


def _pulse(service: EducationPhase6Service, platform: Any, actor: str, institution_id: str) -> None:
    if not service.permissions.has(actor, institution_id, "pulse.view"):
        st.info("Science Pulse is not available for this role.")
        return
    publications = platform._all(
        """SELECT p.*,s.name source_name FROM publications p LEFT JOIN pulse_sources s ON s.id=p.source_id
        WHERE COALESCE(s.institution_id,'') IN ('',?) ORDER BY p.published_at DESC LIMIT 500""",
        (institution_id,),
    )
    news = platform._all(
        """SELECT n.*,s.name source_name FROM news_items n LEFT JOIN pulse_sources s ON s.id=n.source_id
        WHERE COALESCE(s.institution_id,'') IN ('',?) ORDER BY n.published_at DESC LIMIT 500""",
        (institution_id,),
    ) if platform._one("SELECT name FROM sqlite_master WHERE type='table' AND name='news_items'") else []
    sources = platform._all("SELECT * FROM pulse_sources WHERE institution_id IN ('',?) ORDER BY name", (institution_id,))
    retracted = sum(1 for row in publications if str(row.get("retraction_state", "none")) != "none")
    st.markdown(metric_cards([
        ("Publications", len(publications), "Visible indexed papers", "⌁"),
        ("Science news", len(news), "Visible trusted news records", "◫"),
        ("Sources", len(sources), "Registered providers", "◎"),
        ("Corrections", retracted, "Retraction/correction flags", "!"),
    ]), unsafe_allow_html=True)
    month_counts: dict[str, int] = {}
    for row in publications:
        month = str(row.get("published_at") or row.get("created_at") or "")[:7] or "unknown"
        month_counts[month] = month_counts.get(month, 0) + 1
    recent_months = sorted(month_counts)[-12:]
    left, right = st.columns([.58, .42], gap="medium")
    with left:
        st.markdown(histogram([month_counts[m] for m in recent_months], recent_months, title="Publication volume by month"), unsafe_allow_html=True)
    with right:
        state_counts: dict[str, int] = {}
        for row in publications:
            state = str(row.get("retraction_state") or "none")
            state_counts[state] = state_counts.get(state, 0) + 1
        st.dataframe([{"status": key, "records": value} for key, value in state_counts.items()], width="stretch", hide_index=True)
    st.subheader("Recent research evidence")
    st.dataframe([{key: row.get(key) for key in ("title", "source_name", "doi", "pmid", "published_at", "retraction_state")} for row in publications[:100]], width="stretch", hide_index=True)


def _universe(service: EducationPhase6Service, platform: Any, actor: str, institution_id: str) -> None:
    if not service.permissions.has(actor, institution_id, "universe.view"):
        st.info("Education Universe is not available for this role.")
        return
    universe = EducationUniverse(platform)
    modules = _run(lambda: universe.modules(actor, institution_id)) or []
    records = _run(lambda: universe.list_records(actor, institution_id, limit=500)) or []
    dashboard = _run(lambda: universe.dashboard(actor, institution_id)) or {}
    counts: dict[str, int] = {}
    states: dict[str, int] = {}
    for record in records:
        counts[record["module_key"]] = counts.get(record["module_key"], 0) + 1
        states[record["state"]] = states.get(record["state"], 0) + 1
    st.markdown(metric_cards([
        ("Modules", len(modules), "Role-visible Universe modules", "✦"),
        ("Records", len(records), "Visible governed records", "▤"),
        ("Pending sync", dashboard.get("pending_sync", 0), "Offline conflict-aware queue", "⇄"),
        ("Workflow states", len(states), "Active record lifecycle states", "◇"),
    ]), unsafe_allow_html=True)
    cards = []
    maximum = max(counts.values(), default=1)
    for module in modules:
        count = counts.get(module["key"], 0)
        maturity = round(count / maximum * 100) if maximum else 0
        cards.append(
            f'<article class="edu-module-card"><div class="edu-kicker">{module["key"].replace("_", " ")}</div>'
            f'<h3>{module["name"]}</h3><p>{module["purpose"]}</p>'
            f'<div class="edu-progress-track"><div class="edu-progress-fill" style="width:{maturity}%"></div></div>'
            f'<span class="edu-chip">{count} records</span> <span class="edu-chip">{len(module.get("record_types", []))} types</span></article>'
        )
    st.markdown('<div class="edu-platform-grid">' + ''.join(cards) + '</div>', unsafe_allow_html=True)
    if states:
        st.subheader("Workflow distribution")
        st.markdown(histogram(list(states.values()), list(states.keys()), title="Universe records by state"), unsafe_allow_html=True)


def _personalize(service: EducationPhase6Service, actor: str, institution_id: str) -> None:
    current = _run(lambda: service.preferences(actor, institution_id)) or {}
    with st.form("phase6-ui-preferences"):
        theme = st.selectbox("Theme", ["dark", "light", "system"], index=["dark", "light", "system"].index(current.get("theme", "dark")))
        density = st.selectbox("Density", ["comfortable", "compact"], index=["comfortable", "compact"].index(current.get("density", "comfortable")))
        scale = st.slider("Font scale", .85, 1.5, float(current.get("font_scale", 1.0)), .05)
        high = st.toggle("High contrast", value=bool(current.get("high_contrast")))
        reduced = st.toggle("Reduced motion", value=bool(current.get("reduced_motion")))
        dyslexia = st.toggle("Dyslexia-friendly text", value=bool(current.get("dyslexia_mode")))
        if st.form_submit_button("Save application preferences", type="primary"):
            result = _run(lambda: service.save_preferences(actor, institution_id, theme=theme, density=density, font_scale=scale, high_contrast=high, reduced_motion=reduced, dyslexia_mode=dyslexia))
            if result:
                st.session_state.education_theme = result["theme"]
                st.session_state.education_density = result["density"]
                st.session_state.education_font_scale = result["font_scale"]
                st.session_state.education_high_contrast = bool(result["high_contrast"])
                st.session_state.education_reduced_motion = bool(result["reduced_motion"])
                st.session_state.education_dyslexia_mode = bool(result["dyslexia_mode"])
                st.success("Preferences saved across Education OS.")
                st.rerun()
    navigation = _run(lambda: service.navigation_state(actor, institution_id)) or {"favorites": [], "recent": []}
    st.subheader("Personal navigation")
    st.write("Favorites:", ", ".join(navigation["favorites"]) or "None")
    st.write("Recently visited:", ", ".join(navigation["recent"]) or "None")


def render_education_visual_command_center(root: Path) -> None:
    render_app_header(
        "visuals",
        "Education Visual Command Center",
        "Calendar, gradebook, mastery graph, Shiro conversation studio, exam intelligence and institution operations rendered as task-oriented app workspaces.",
        eyebrow="BIOINTEL EDUCATION OS · PHASE 6",
    )
    demo_mode = _demo_controls(root)
    platform = _page_platform(root, demo_mode)
    _identity_input("Education user ID", demo_mode)
    institution_id = _institution(platform)
    if not institution_id:
        return
    actor = _actor()
    try:
        render_workspace_context(platform, actor, institution_id)
    except EducationError as exc:
        st.error(str(exc))
        return
    render_role_snapshot(platform, actor, institution_id)
    service = EducationPhase6Service(platform, root=root)
    tabs = st.tabs([
        ":material/dashboard: Dashboard",
        ":material/calendar_month: Classroom",
        ":material/play_circle: Academy",
        ":material/biotech: Science Pulse",
        ":material/hub: Universe",
        ":material/psychology: Shiro & Mastery",
        ":material/monitoring: Examinations",
        ":material/domain: Institution",
        ":material/accessibility_new: Personalize",
    ])
    with tabs[0]:
        _dashboard(service, platform, actor, institution_id)
    with tabs[1]:
        _classroom(service, platform, actor, institution_id)
    with tabs[2]:
        _academy(service, platform, actor, institution_id)
    with tabs[3]:
        _pulse(service, platform, actor, institution_id)
    with tabs[4]:
        _universe(service, platform, actor, institution_id)
    with tabs[5]:
        _intelligence(service, platform, actor, institution_id)
    with tabs[6]:
        _examinations(service, platform, actor, institution_id)
    with tabs[7]:
        _institution(service, platform, actor, institution_id)
    with tabs[8]:
        _personalize(service, actor, institution_id)
