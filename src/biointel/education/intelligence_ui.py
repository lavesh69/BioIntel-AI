from __future__ import annotations

import html
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from biointel.ui.frontend_v10 import empty_state

from ._streamlit_compat import st
from .experience import render_app_header, render_role_snapshot, render_workspace_context
from .phase4 import EducationPhase4Service
from .platform import ADMIN, STUDENT, TEACHER, EducationError
from .ui import (
    _actor,
    _identity_input,
    _institution,
    _platform,
    _production_only_context,
    _run,
)


def _subjects(platform: Any, actor: str, institution_id: str, roles: set[str]) -> list[dict[str, Any]]:
    if roles & TEACHER:
        if roles & ADMIN:
            return platform._all("SELECT id,code,name FROM subjects WHERE institution_id=? AND state='active' ORDER BY code", (institution_id,))
        return platform._all(
            """SELECT DISTINCT s.id,s.code,s.name FROM subjects s JOIN teacher_assignments t ON t.subject_id=s.id
            WHERE s.institution_id=? AND t.teacher_id=? AND t.state='active' AND s.state='active' ORDER BY s.code""",
            (institution_id, actor),
        )
    return platform._all(
        """SELECT DISTINCT s.id,s.code,s.name FROM subjects s JOIN enrollments e ON e.subject_id=s.id
        WHERE s.institution_id=? AND e.student_id=? AND e.state='active' AND s.state='active' ORDER BY s.code""",
        (institution_id, actor),
    )


def _student_options(platform: Any, institution_id: str, subject_id: str | None = None) -> list[str]:
    if subject_id:
        rows = platform._all("SELECT student_id FROM enrollments WHERE institution_id=? AND subject_id=? AND state='active' ORDER BY student_id", (institution_id, subject_id))
    else:
        rows = platform._all(
            """SELECT DISTINCT user_id student_id FROM memberships WHERE institution_id=?
            AND role IN ('school_student','college_student','university_student') AND state='active' ORDER BY user_id""",
            (institution_id,),
        )
    return [str(row["student_id"]) for row in rows]


def _metric_cards(items: list[tuple[str, Any, str]]) -> None:
    body = "".join(
        f'<div class="edu-stat-card"><div class="label">{html.escape(str(label))}</div>'
        f'<div class="value">{html.escape(str(value))}</div><div class="detail">{html.escape(str(detail))}</div></div>'
        for label, value, detail in items
    )
    st.markdown(f'<div class="edu-card-grid">{body}</div>', unsafe_allow_html=True)


def _mastery_cards(snapshot: dict[str, Any]) -> None:
    concepts = snapshot.get("concepts", [])
    if not concepts:
        empty_state("No concept map published", "This subject has no prerequisite knowledge graph yet.", icon="◇", action_hint="An educator can create concepts and prerequisite relationships.")
        return
    for concept in concepts:
        mastery = max(0, min(100, round(float(concept.get("mastery", 0)) * 100)))
        confidence = round(float(concept.get("confidence", 0)) * 100)
        review = concept.get("next_review_at") or "Not scheduled"
        st.markdown(
            f"""
            <div class="edu-module-card">
              <div class="edu-kicker">{html.escape(str(concept.get('subject_code', 'SUBJECT')))} · {html.escape(str(concept.get('difficulty', 'medium')).title())}</div>
              <h3>{html.escape(str(concept.get('code')))} · {html.escape(str(concept.get('title')))}</h3>
              <div class="edu-progress-track"><div class="edu-progress-fill" style="width:{mastery}%"></div></div>
              <p><strong>{mastery}% mastery</strong> · {confidence}% evidence confidence · {int(concept.get('evidence_count') or 0)} evidence item(s)</p>
              <span class="edu-chip">Next review: {html.escape(str(review))}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_learning(service: EducationPhase4Service, platform: Any, actor: str, institution_id: str, roles: set[str], subjects: list[dict[str, Any]]) -> None:
    st.subheader("Adaptive learning workspace")
    if not subjects:
        empty_state("No accessible subjects", "The current role is not assigned or enrolled in an active subject.", icon="▤", action_hint="Ask an administrator to update subject access.")
        return
    subject_ids = [row["id"] for row in subjects]
    subject_id = st.selectbox("Subject", subject_ids, format_func=lambda value: next(f"{row['code']} · {row['name']}" for row in subjects if row["id"] == value), key="phase4-learning-subject")
    student_id = actor
    if roles & TEACHER:
        learners = _student_options(platform, institution_id, subject_id)
        if not learners:
            empty_state("No enrolled learners", "The selected subject has no active student enrollment.", icon="◎", action_hint="Enroll learners before recording mastery evidence.")
            return
        student_id = st.selectbox("Learner", learners, key="phase4-learning-student")
    snapshot = _run(lambda: service.learner_snapshot(actor, institution_id, student_id, subject_id))
    if not snapshot:
        return
    _metric_cards([
        ("Average mastery", f"{round(snapshot['average_mastery'] * 100)}%", "Recency-weighted concept evidence"),
        ("Concepts", len(snapshot["concepts"]), "Active subject knowledge nodes"),
        ("Recommendations", len(snapshot["recommendations"]), "Open guided actions"),
        ("Review model", "Spaced", "Human-overridable scheduling"),
    ])
    left, right = st.columns([1.5, 0.8], gap="large")
    with left:
        _mastery_cards(snapshot)
    with right:
        st.markdown("#### Recommended next actions")
        if not snapshot["recommendations"]:
            st.success("No priority learning intervention is currently open.", icon=":material/check_circle:")
        for recommendation in snapshot["recommendations"][:10]:
            reason = recommendation.get("reason", {})
            st.markdown(
                f"""<div class="edu-notice"><span>✦</span><div><strong>{html.escape(str(recommendation['title']))}</strong>
                <small>Priority {recommendation['priority']} · mastery {round(float(reason.get('mastery', 0))*100)}% · due {html.escape(str(recommendation.get('due_at') or 'not set'))}</small></div></div>""",
                unsafe_allow_html=True,
            )
    if roles & TEACHER:
        with st.expander("Create concept and record evidence", expanded=False):
            create_tab, evidence_tab = st.tabs(["New concept", "Mastery evidence"])
            with create_tab:
                with st.form("phase4-create-concept"):
                    code = st.text_input("Concept code", placeholder="DNA-01")
                    title = st.text_input("Concept title", placeholder="DNA structure")
                    difficulty = st.selectbox("Difficulty", ["foundation", "easy", "medium", "hard", "advanced"], index=2)
                    description = st.text_area("Description")
                    existing = snapshot["concepts"]
                    prerequisites = st.multiselect("Prerequisites", [row["concept_id"] for row in existing], format_func=lambda value: next(f"{row['code']} · {row['title']}" for row in existing if row["concept_id"] == value))
                    if st.form_submit_button("Create concept", type="primary", icon=":material/add:"):
                        result = _run(lambda: service.create_concept(actor, institution_id, subject_id, code, title, description=description, prerequisites=prerequisites, difficulty=difficulty))
                        if result:
                            st.success("Concept created.")
                            st.rerun()
            with evidence_tab:
                concept_ids = [row["concept_id"] for row in snapshot["concepts"]]
                if concept_ids:
                    with st.form("phase4-record-evidence"):
                        concept_id = st.selectbox("Concept", concept_ids, format_func=lambda value: next(f"{row['code']} · {row['title']}" for row in snapshot["concepts"] if row["concept_id"] == value))
                        score = st.slider("Evidence score", 0.0, 1.0, 0.75, 0.05)
                        evidence_type = st.selectbox("Evidence type", ["practice", "assignment", "quiz", "examination", "laboratory", "teacher_observation", "self_check"])
                        weight = st.slider("Evidence weight", 0.1, 5.0, 1.0, 0.1)
                        if st.form_submit_button("Record evidence", type="primary", icon=":material/monitoring:"):
                            result = _run(lambda: service.record_mastery_evidence(actor, institution_id, student_id, concept_id, score, evidence_type=evidence_type, weight=weight))
                            if result:
                                st.success("Mastery state recalculated.")
                                st.rerun()
    elif roles & STUDENT and snapshot["concepts"]:
        with st.expander("Record a self-practice check", expanded=False):
            with st.form("phase4-self-practice"):
                concept_id = st.selectbox("Concept practiced", [row["concept_id"] for row in snapshot["concepts"]], format_func=lambda value: next(f"{row['code']} · {row['title']}" for row in snapshot["concepts"] if row["concept_id"] == value))
                score = st.slider("Self-check result", 0.0, 1.0, 0.7, 0.05)
                if st.form_submit_button("Save self-check", type="primary"):
                    result = _run(lambda: service.record_mastery_evidence(actor, institution_id, actor, concept_id, score, evidence_type="self_check", weight=0.5))
                    if result:
                        st.success("Self-check saved as low-weight evidence.")
                        st.rerun()


def _render_tutor(service: EducationPhase4Service, platform: Any, actor: str, institution_id: str, roles: set[str], subjects: list[dict[str, Any]]) -> None:
    st.subheader("Shiro AI Course Tutor")
    st.caption("Local-first, citation-grounded answers from institution-indexed subject materials. Tutor access is locked during active subject examinations.")
    if not subjects:
        empty_state("No subject available", "Shiro Tutor requires a permission-visible subject context.", icon="✦", action_hint="Choose or request access to an active subject.")
        return
    subject_id = st.selectbox("Tutor subject", [row["id"] for row in subjects], format_func=lambda value: next(f"{row['code']} · {row['name']}" for row in subjects if row["id"] == value), key="phase4-tutor-subject")
    if roles & TEACHER:
        with st.expander("Index approved subject evidence", expanded=False):
            source_mode = st.radio("Source", ["Text or notes", "Published classroom material"], horizontal=True)
            if source_mode == "Text or notes":
                with st.form("phase4-index-text"):
                    title = st.text_input("Source title")
                    text = st.text_area("Approved subject content", height=180)
                    if st.form_submit_button("Index locally", type="primary", icon=":material/database:"):
                        result = _run(lambda: service.index_subject_text(actor, institution_id, subject_id, title, text))
                        if result:
                            st.success(f"Indexed {result['chunks_indexed']} evidence chunk(s).")
            else:
                materials = platform._all("SELECT id,title,file_name FROM materials WHERE institution_id=? AND subject_id=? AND state='published' ORDER BY created_at DESC", (institution_id, subject_id))
                if materials:
                    material_id = st.selectbox("Published material", [row["id"] for row in materials], format_func=lambda value: next(f"{row['title']} · {row['file_name']}" for row in materials if row["id"] == value))
                    if st.button("Index selected material", type="primary", icon=":material/database:"):
                        result = _run(lambda: service.index_material(actor, material_id))
                        if result:
                            st.success(f"Indexed {result['chunks_indexed']} evidence chunk(s).")
                else:
                    empty_state("No published material", "Shiro cannot build grounded course evidence until reviewed material is published.", icon="⌕", action_hint="Publish a classroom material or Academy resource.")
    with st.form("phase4-tutor-question"):
        question = st.text_area("Ask about the indexed course material", placeholder="Explain gene expression step by step.", height=120)
        policy_options = ["guided", "revision"] + (["teacher_planning"] if roles & TEACHER else [])
        policy_mode = st.selectbox("Learning mode", policy_options, format_func=lambda value: value.replace("_", " ").title())
        language = st.selectbox("Response language", ["auto", "English", "Hindi", "Hinglish"])
        ask = st.form_submit_button("Ask Shiro Tutor", type="primary", icon=":material/psychology:")
    if ask:
        response = _run(lambda: service.ask_tutor(actor, institution_id, subject_id, question, response_language=language, policy_mode=policy_mode))
        if response:
            st.session_state.phase4_tutor_response = response
    response = st.session_state.get("phase4_tutor_response")
    if response:
        st.markdown("#### Grounded response")
        st.markdown(response["answer"])
        status = response.get("evidence_status", "unknown")
        st.caption(f"Evidence status: {status} · Provider: {response.get('provider')} · Model: {response.get('model')}")
        citations = response.get("citations", [])
        if citations:
            with st.expander(f"Traceable citations ({len(citations)})", expanded=True):
                for citation in citations:
                    st.markdown(f"**{citation.get('citation_id')} · {citation.get('source_title')}**")
                    st.caption(f"{citation.get('section') or 'Source'} · relevance {round(float(citation.get('relevance_score', 0)), 3)}")
                    st.write(citation.get("excerpt", ""))
        elif status != "grounded":
            st.warning("No sufficient indexed course evidence was found. Shiro did not invent a source.")


def render_shiro_course_tutor(
    platform: Any,
    root: Path,
    actor: str,
    institution_id: str,
) -> None:
    """Render the canonical tenant-scoped Shiro tutor inside Education workspaces."""
    roles = {str(row["role"]) for row in platform.membership(actor, institution_id)}
    if not roles:
        st.error("An active institution membership is required.")
        return
    service = EducationPhase4Service(platform, root=root)
    _render_tutor(
        service,
        platform,
        actor,
        institution_id,
        roles,
        _subjects(platform, actor, institution_id, roles),
    )


def render_academy_shiro_tutor(
    platform: Any,
    root: Path,
    actor: str,
    institution_id: str,
) -> None:
    """Render a course-aware Academy tutor over approved lecture transcripts."""
    roles = {str(row["role"]) for row in platform.membership(actor, institution_id)}
    if not roles:
        st.error("An active institution membership is required.")
        return
    if roles & ADMIN:
        courses = platform._all(
            "SELECT * FROM courses WHERE institution_id=? ORDER BY updated_at DESC",
            (institution_id,),
        )
    elif roles & TEACHER:
        courses = platform._all(
            "SELECT * FROM courses WHERE institution_id=? AND educator_id=? ORDER BY updated_at DESC",
            (institution_id, actor),
        )
    else:
        courses = platform._all(
            """SELECT c.* FROM courses c JOIN academy_enrollments e ON e.course_id=c.id
               WHERE c.institution_id=? AND e.student_id=? AND e.state='active'
               ORDER BY c.updated_at DESC""",
            (institution_id, actor),
        )
    st.subheader("Shiro AI Academy Tutor")
    st.caption(
        "Course-scoped conversations retrieve only explicitly indexed, published lecture transcripts. "
        "Unsupported answers remain evidence-insufficient."
    )
    if not courses:
        empty_state(
            "No authorized Academy course",
            "Enroll in a published course or open a course you teach.",
            icon="✦",
        )
        return
    by_course = {row["id"]: row for row in courses}
    course_id = st.selectbox(
        "Academy course",
        list(by_course),
        format_func=lambda value: by_course[value]["title"],
        key="academy-shiro-course",
    )
    service = EducationPhase4Service(platform, root=root)
    transcripts = platform._all(
        """SELECT t.id,t.language,t.updated_at,l.id lecture_id,l.title lecture_title
           FROM education_lecture_transcripts t JOIN lectures l ON l.id=t.lecture_id
           WHERE l.course_id=? AND l.state='published' ORDER BY l.created_at,t.language""",
        (course_id,),
    )
    project_id = service.academy_project_id(institution_id, course_id)
    sources = platform._all(
        """SELECT title,source_id,sha256,indexed_by,updated_at FROM education_tutor_sources
           WHERE institution_id=? AND subject_id=? AND project_id=? AND state='active'
           ORDER BY updated_at DESC""",
        (institution_id, course_id, project_id),
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Published transcripts", len(transcripts))
    c2.metric("Indexed evidence", len(sources))
    c3.metric("Provider", "Local Shiro")
    if roles & (TEACHER | ADMIN):
        with st.expander("Index approved lecture transcript", expanded=False):
            if not transcripts:
                st.info("Publish a reviewed transcript in Lecture intelligence before indexing it.")
            else:
                by_transcript = {row["id"]: row for row in transcripts}
                transcript_id = st.selectbox(
                    "Transcript",
                    list(by_transcript),
                    format_func=lambda value: (
                        f"{by_transcript[value]['lecture_title']} · "
                        f"{by_transcript[value]['language']}"
                    ),
                    key="academy-shiro-transcript",
                )
                if st.button(
                    "Index transcript locally",
                    type="primary",
                    icon=":material/database:",
                    key="academy-shiro-index",
                ):
                    result = _run(lambda: service.index_academy_transcript(actor, transcript_id))
                    if result:
                        st.success(f"Indexed {result['chunks_indexed']} approved evidence chunk(s).")
                        st.rerun()
    if sources:
        with st.expander(f"Authorized evidence ({len(sources)})", expanded=False):
            st.dataframe(sources, hide_index=True, width="stretch")
    modes = ["guided", "revision"] + (["teacher_planning"] if roles & (TEACHER | ADMIN) else [])
    with st.form("academy-shiro-question"):
        question = st.text_area(
            "Ask about this course or its indexed lectures",
            placeholder="Explain the current chapter using only approved transcript evidence.",
            height=120,
        )
        language = st.selectbox("Response language", ["auto", "English", "Hindi", "Hinglish"])
        mode = st.selectbox(
            "Learning mode", modes, format_func=lambda value: value.replace("_", " ").title()
        )
        submitted = st.form_submit_button(
            "Ask Shiro Academy Tutor", type="primary", icon=":material/psychology:"
        )
    conversation_key = f"academy-shiro-conversation-{course_id}"
    response_key = f"academy-shiro-response-{course_id}"
    if submitted:
        response = _run(lambda: service.ask_academy_tutor(
            actor,
            institution_id,
            course_id,
            question,
            response_language=language,
            policy_mode=mode,
            conversation_id=st.session_state.get(conversation_key),
        ))
        if response:
            st.session_state[response_key] = response
            if response.get("conversation_id"):
                st.session_state[conversation_key] = response["conversation_id"]
    response = st.session_state.get(response_key)
    if not response:
        return
    with st.chat_message("assistant", avatar=":material/psychology:"):
        st.markdown(response["answer"])
        st.caption(
            f"Evidence: {response.get('evidence_status', 'unknown')} · "
            f"Language: {response.get('language', 'auto')} · Mode: {response.get('policy_mode')}"
        )
        if language in {"Hindi", "Hinglish"}:
            st.caption("Translation is assistance; scientific identifiers and cited source text remain unchanged.")
    citations = response.get("citations", [])
    if citations:
        with st.expander(f"Evidence inspector ({len(citations)})", expanded=True):
            for citation in citations:
                st.markdown(f"**{citation.get('citation_id')} · {citation.get('source_title')}**")
                st.caption(
                    f"Section: {citation.get('section') or 'source'} · "
                    f"relevance {float(citation.get('relevance_score') or 0):.3f} · "
                    f"source {citation.get('source_id')} · chunk {citation.get('chunk_id')}"
                )
                st.write(citation.get("excerpt", ""))
    else:
        st.warning("No authorized evidence supported this answer; Shiro did not invent a citation.")
    if transcripts:
        by_lecture = {row["lecture_id"]: row for row in transcripts}
        target_lecture = st.selectbox(
            "Save response to personal lecture notes",
            list(by_lecture),
            format_func=lambda value: by_lecture[value]["lecture_title"],
            key="academy-shiro-note-target",
        )
        if st.button("Save grounded answer to notes", icon=":material/note_add:"):
            from .phase7 import EducationPhase7Service

            saved = _run(lambda: EducationPhase7Service(platform, root=root).save_lecture_note(
                actor, target_lecture, response["answer"], position_seconds=0
            ))
            if saved:
                st.success("Shiro answer saved to your persistent lecture notebook.")

def _render_operations(service: EducationPhase4Service, platform: Any, actor: str, institution_id: str, roles: set[str], subjects: list[dict[str, Any]]) -> None:
    st.subheader("Academic operations")
    upcoming = platform._all(
        """SELECT t.*,s.code subject_code,s.name subject_name FROM timetable_entries t LEFT JOIN subjects s ON s.id=t.subject_id
        WHERE t.institution_id=? AND t.ends_at>=? AND t.state='scheduled' ORDER BY t.starts_at LIMIT 100""",
        (institution_id, datetime.now(timezone.utc).isoformat()),
    )
    _metric_cards([
        ("Upcoming sessions", len(upcoming), "Scheduled timetable entries"),
        ("Recurring engine", "Conflict-safe", "Teacher, room and group checks"),
        ("Attendance alerts", platform._one("SELECT COUNT(*) n FROM education_attendance_alerts WHERE institution_id=? AND state='open'", (institution_id,))["n"], "Human-review support flags"),
        ("Automation", "Local", "No external scheduler required"),
    ])
    if upcoming:
        st.dataframe(upcoming, width="stretch", hide_index=True)
    else:
        empty_state("No upcoming timetable entries", "No future classes are visible in the current planning window.", icon="▦", action_hint="Open Classroom to create or review the weekly timetable.")
    if not roles & TEACHER or not subjects:
        return
    schedule_tab, attendance_tab = st.tabs(["Create weekly timetable", "Attendance automation"])
    with schedule_tab:
        with st.form("phase4-weekly-timetable"):
            subject_id = st.selectbox("Subject", [row["id"] for row in subjects], format_func=lambda value: next(f"{row['code']} · {row['name']}" for row in subjects if row["id"] == value), key="phase4-ops-subject")
            assigned = platform._all("SELECT teacher_id FROM teacher_assignments WHERE institution_id=? AND subject_id=? AND state='active' ORDER BY teacher_id", (institution_id, subject_id))
            teachers = [row["teacher_id"] for row in assigned]
            teacher_id = st.selectbox("Teacher", teachers or [actor])
            student_group = st.text_input("Student group", placeholder="BSc Biotechnology A")
            room = st.text_input("Room or laboratory", placeholder="LAB-01")
            start_date = st.date_input("First class date", value=datetime.now(timezone.utc).date() + timedelta(days=1))
            start_time = st.time_input("Start time")
            duration = st.number_input("Duration in minutes", 15, 480, 60, 15)
            weeks = st.number_input("Weekly occurrences", 1, 52, 12)
            if st.form_submit_button("Create conflict-safe series", type="primary", icon=":material/calendar_add_on:"):
                start = datetime.combine(start_date, start_time, tzinfo=timezone.utc)
                end = start + timedelta(minutes=int(duration))
                result = _run(lambda: service.create_weekly_timetable(actor, institution_id, subject_id, teacher_id, student_group, room, start.isoformat(), end.isoformat(), weeks=int(weeks)))
                if result:
                    st.success(f"Created {result['occurrence_count']} timetable entries.")
                    st.rerun()
    with attendance_tab:
        entries = platform._all("SELECT id,subject_id,starts_at,room FROM timetable_entries WHERE institution_id=? AND state='scheduled' ORDER BY starts_at DESC LIMIT 200", (institution_id,))
        if entries:
            entry_id = st.selectbox("Timetable entry", [row["id"] for row in entries], format_func=lambda value: next(f"{row['starts_at']} · {row['room']}" for row in entries if row["id"] == value))
            if st.button("Create/open attendance session", type="primary", icon=":material/how_to_reg:"):
                result = _run(lambda: service.create_attendance_from_timetable(actor, entry_id))
                if result:
                    st.success(f"Attendance session ready: {result['id']}")
        threshold = st.slider("Attendance shortage threshold", 0.50, 1.00, 0.75, 0.05)
        if st.button("Refresh shortage alerts", icon=":material/warning:"):
            alerts = _run(lambda: service.attendance_shortage_alerts(actor, institution_id, threshold=threshold))
            if alerts is not None:
                st.session_state.phase4_attendance_alerts = alerts
        alerts = st.session_state.get("phase4_attendance_alerts", [])
        if alerts:
            st.dataframe(alerts, width="stretch", hide_index=True)


def _render_notifications(service: EducationPhase4Service, actor: str, institution_id: str, roles: set[str]) -> None:
    st.subheader("Notification center")
    unread_only = st.toggle("Show unread only", value=False)
    inbox = _run(lambda: service.notification_inbox(actor, institution_id, unread_only=unread_only)) or []
    _metric_cards([
        ("Inbox", len(inbox), "Visible notifications"),
        ("Unread", sum(1 for row in inbox if row["state"] == "unread"), "Actionable messages"),
        ("Delivery", "In-app", "Local reliable channel"),
        ("Preferences", "Per event", "Recipient controlled"),
    ])
    for notification in inbox:
        badge = "●" if notification["state"] == "unread" else "✓"
        left, right = st.columns([6, 1])
        with left:
            st.markdown(f"**{badge} {notification['title']}**")
            st.caption(f"{notification['event_type']} · {notification['priority']} · {notification['created_at']}")
            st.write(notification["body"])
        with right:
            if notification["state"] == "unread" and st.button("Read", key=f"read-{notification['id']}"):
                if _run(lambda n=notification: service.mark_notification_read(actor, n["id"])):
                    st.rerun()
        st.divider()
    with st.expander("Notification preferences", expanded=False):
        with st.form("phase4-notification-preference"):
            event_type = st.selectbox("Event", ["*", "assignment_due", "exam_upcoming", "attendance_shortage", "circular"])
            enabled = st.toggle("Enable in-app notifications", value=True)
            digest = st.selectbox("Delivery mode", ["instant", "daily", "weekly", "off"])
            if st.form_submit_button("Save preference"):
                if _run(lambda: service.save_notification_preference(actor, institution_id, event_type=event_type, enabled=enabled, digest_mode=digest)):
                    st.success("Preference saved.")
    if roles & ADMIN:
        if st.button("Generate upcoming assignment/exam reminders", type="primary", icon=":material/notifications_active:"):
            result = _run(lambda: service.generate_due_reminders(actor, institution_id))
            if result:
                st.success(f"Processed {result['notifications_processed']} reminder notification(s).")


def _render_reports(service: EducationPhase4Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    st.subheader("Institutional learner report")
    student_id = actor
    if roles & TEACHER:
        students = _student_options(platform, institution_id)
        if not students:
            empty_state("No student profiles", "No permission-visible learner profile is available for reporting.", icon="◎", action_hint="Enroll students or switch to an authorized institution context.")
            return
        student_id = st.selectbox("Student", students, key="phase4-report-student")
    report = _run(lambda: service.learner_progress_report(actor, institution_id, student_id))
    if not report:
        return
    summary = report["summary"]
    _metric_cards([
        ("Attendance", "—" if summary["attendance_ratio"] is None else f"{round(summary['attendance_ratio']*100)}%", "Recorded sessions"),
        ("Assignments", "—" if summary["assignment_average_percent"] is None else f"{summary['assignment_average_percent']}%", "Released assignment grades"),
        ("Concept mastery", f"{round(summary['average_concept_mastery']*100)}%", "Knowledge graph evidence"),
        ("Published results", summary["published_results"], "Locked institutional results"),
    ])
    tabs = st.tabs(["Learning", "Assignments", "Attendance", "Results", "Evidence JSON"])
    with tabs[0]:
        _mastery_cards(report["learning"])
    with tabs[1]:
        st.dataframe(report["assignments"], width="stretch", hide_index=True)
    with tabs[2]:
        st.dataframe(report["attendance"], width="stretch", hide_index=True)
    with tabs[3]:
        st.dataframe(report["results"], width="stretch", hide_index=True)
    with tabs[4]:
        payload = json.dumps(report, indent=2, default=str).encode("utf-8")
        st.download_button("Download governed JSON report", payload, file_name=f"{student_id}-education-progress.json", mime="application/json")
        st.json(report, expanded=False)


def render_education_intelligence_hub(root: Path) -> None:
    render_app_header(
        "intelligence",
        "Education Intelligence Hub",
        "Adaptive learning, Shiro AI tutoring, conflict-safe academic operations, notifications and governed learner reporting in one app workspace.",
        eyebrow="BIOINTEL EDUCATION OS · PHASE 4",
    )
    platform = _platform(str(root))
    if not _production_only_context(platform, "education-intelligence"):
        return
    _identity_input("Education user ID", False)
    institution_id = _institution(platform)
    if not institution_id:
        return
    actor = _actor()
    try:
        roles = render_workspace_context(platform, actor, institution_id)
    except EducationError as exc:
        st.error(str(exc))
        return
    render_role_snapshot(platform, actor, institution_id)
    service = EducationPhase4Service(platform, root=root)
    subjects = _subjects(platform, actor, institution_id, roles)
    tabs = st.tabs([
        ":material/route: Learning Path",
        ":material/psychology: Shiro Tutor",
        ":material/calendar_month: Operations",
        ":material/notifications: Notifications",
        ":material/analytics: Reports",
    ])
    with tabs[0]:
        _render_learning(service, platform, actor, institution_id, roles, subjects)
    with tabs[1]:
        _render_tutor(service, platform, actor, institution_id, roles, subjects)
    with tabs[2]:
        _render_operations(service, platform, actor, institution_id, roles, subjects)
    with tabs[3]:
        _render_notifications(service, actor, institution_id, roles)
    with tabs[4]:
        _render_reports(service, platform, actor, institution_id, roles)
