from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable

from ._streamlit_compat import st

from .examination import BLOOM_LEVELS, DIFFICULTIES, QUESTION_TYPES, SecureExaminationService
from .experience import render_role_snapshot, render_workspace_context
from biointel.ui.frontend_v10 import empty_state
from .permissions import DEFAULT_ROLE_PERMISSIONS, PERMISSIONS
from .platform import ADMIN, STUDENT, TEACHER, EducationError

Run = Callable[[Callable[[], Any]], Any]


def _iso(day: date, clock: time) -> str:
    return datetime.combine(day, clock, tzinfo=timezone.utc).isoformat()


def _friendly(value: str) -> str:
    return str(value or "").replace("_", " ").title()


def _subjects(service: SecureExaminationService, actor: str, institution_id: str) -> list[dict[str, Any]]:
    roles = service.permissions.roles(actor, institution_id)
    if roles & ADMIN:
        return service.platform._all("SELECT id,code,name FROM subjects WHERE institution_id=? AND state='active' ORDER BY code,name", (institution_id,))
    return service.platform._all(
        """SELECT s.id,s.code,s.name FROM subjects s JOIN teacher_assignments t ON t.subject_id=s.id
        WHERE s.institution_id=? AND t.teacher_id=? AND t.state='active' AND s.state='active' ORDER BY s.code,s.name""",
        (institution_id, actor),
    )


def _exam_cards(exams: list[dict[str, Any]]) -> None:
    if not exams:
        empty_state("No examinations match", "No examination satisfies the selected filters and permission context.", icon="◉", action_hint="Create a secure exam or broaden the current filters.")
        return
    for exam in exams[:12]:
        with st.container(border=True):
            left, middle, right = st.columns([2.1, 1, 1], vertical_alignment="center")
            left.markdown(f"**{exam['title']}**")
            left.caption(f"{exam.get('subject_code','')} · {exam.get('subject_name','')} · {exam.get('question_count',0)} questions")
            middle.metric("Maximum", f"{float(exam['max_marks']):g}")
            right.badge(_friendly(exam.get("state", "draft")), color="green" if exam.get("state") == "published" else "orange")
            st.caption(f"Window: {exam['starts_at']} → {exam['ends_at']} · Duration: {exam.get('duration_minutes') or '—'} min · Attempts: {exam.get('attempts_allowed') or '—'}")


def _overview(service: SecureExaminationService, actor: str, institution_id: str) -> None:
    render_role_snapshot(service.platform, actor, institution_id)
    exams = service.list_exams(actor, institution_id)
    sessions = service.platform._one("SELECT COUNT(*) n FROM education_exam_sessions WHERE institution_id=?", (institution_id,)) or {"n": 0}
    active = service.platform._one("SELECT COUNT(*) n FROM education_exam_sessions WHERE institution_id=? AND state='active'", (institution_id,)) or {"n": 0}
    submitted = service.platform._one("SELECT COUNT(*) n FROM education_exam_sessions WHERE institution_id=? AND state IN ('submitted','expired')", (institution_id,)) or {"n": 0}
    released = service.platform._one("SELECT COUNT(*) n FROM education_exam_scores WHERE institution_id=? AND released=1", (institution_id,)) or {"n": 0}
    cols = st.columns(4)
    cols[0].metric("Examinations", len(exams))
    cols[1].metric("Active sessions", int(active["n"]))
    cols[2].metric("Submitted attempts", int(submitted["n"]))
    cols[3].metric("Released scores", int(released["n"]))
    st.subheader("Examination pipeline")
    st.caption("Draft → validated blueprint → published window → server-timed attempts → grading → locked results")
    _exam_cards(exams)


def _create_exam(service: SecureExaminationService, actor: str, institution_id: str, run: Run) -> None:
    subjects = _subjects(service, actor, institution_id)
    if not subjects:
        st.warning("Assign this educator to a subject before creating an examination.", icon=":material/warning:")
        return
    subject_by_id = {row["id"]: row for row in subjects}
    tomorrow = date.today() + timedelta(days=1)
    with st.form("phase3-create-secure-exam", clear_on_submit=False):
        st.subheader("Create secure examination")
        title = st.text_input("Examination title", placeholder="Semester Biology Assessment")
        subject_id = st.selectbox("Subject", list(subject_by_id), format_func=lambda value: f"{subject_by_id[value]['code']} · {subject_by_id[value]['name']}")
        c1, c2, c3 = st.columns(3)
        max_marks = c1.number_input("Maximum marks", min_value=1.0, value=100.0, step=1.0)
        duration = c2.number_input("Duration (minutes)", min_value=1, max_value=1440, value=60)
        attempts = c3.number_input("Attempts allowed", min_value=1, max_value=10, value=1)
        c4, c5 = st.columns(2)
        start_day = c4.date_input("Start date (UTC)", value=tomorrow)
        start_time = c5.time_input("Start time (UTC)", value=time(9, 0))
        c6, c7 = st.columns(2)
        end_day = c6.date_input("End date (UTC)", value=tomorrow)
        end_time = c7.time_input("End time (UTC)", value=time(12, 0))
        c8, c9, c10 = st.columns(3)
        shuffle_questions = c8.toggle("Shuffle questions", value=True)
        shuffle_options = c9.toggle("Shuffle options", value=True)
        allow_resume = c10.toggle("Allow resume", value=True)
        autosave = st.slider("Autosave interval", min_value=5, max_value=120, value=15, step=5, format="%d seconds")
        access_code = st.text_input("Optional access code", type="password", help="Only a salted hash is persisted.")
        instructions = st.text_area("Student instructions", placeholder="Read every question carefully. Integrity events are logged for review.")
        submitted = st.form_submit_button("Create examination", type="primary", icon=":material/add_task:")
    if submitted:
        result = run(lambda: service.create_exam(
            actor, institution_id, subject_id, title, max_marks,
            _iso(start_day, start_time), _iso(end_day, end_time),
            duration_minutes=int(duration), attempts_allowed=int(attempts),
            shuffle_questions=shuffle_questions, shuffle_options=shuffle_options,
            autosave_seconds=int(autosave), allow_resume=allow_resume,
            access_code=access_code, instructions=instructions,
        ))
        if result:
            st.success("Secure examination draft created.", icon=":material/check_circle:")
            st.session_state.phase3_selected_exam = result["id"]
            st.rerun()


def _question_input(question_type: str) -> tuple[list[str], Any]:
    options: list[str] = []
    correct: Any = None
    if question_type in {"single_choice", "multiple_choice"}:
        option_text = st.text_area("Options — one per line", placeholder="Option A\nOption B\nOption C\nOption D")
        options = [line.strip() for line in option_text.splitlines() if line.strip()]
        if question_type == "single_choice":
            correct = st.text_input("Correct option", placeholder="Enter the exact option text")
        else:
            correct_text = st.text_input("Correct options", placeholder="Comma-separated exact option text")
            correct = [item.strip() for item in correct_text.split(",") if item.strip()]
    elif question_type == "true_false":
        options = ["True", "False"]
        correct = st.selectbox("Correct answer", options)
    elif question_type == "short_text":
        correct = st.text_input("Expected answer", help="Comparison is case-insensitive after trimming.")
    else:
        st.caption("Long answers enter a manual grading queue.")
    return options, correct


def _builder(service: SecureExaminationService, actor: str, institution_id: str, run: Run) -> None:
    exams = service.list_exams(actor, institution_id)
    drafts = [row for row in exams if row["state"] == "draft"]
    _create_exam(service, actor, institution_id, run)
    st.divider()
    if not drafts:
        st.info("Create a draft examination to open the question builder.")
        return
    exam_by_id = {row["id"]: row for row in drafts}
    selected = st.selectbox(
        "Draft examination",
        list(exam_by_id),
        index=list(exam_by_id).index(st.session_state.phase3_selected_exam) if st.session_state.get("phase3_selected_exam") in exam_by_id else 0,
        format_func=lambda value: f"{exam_by_id[value]['title']} · {exam_by_id[value]['subject_code']}",
        key="phase3_exam_builder_selection",
    )
    exam = exam_by_id[selected]
    questions = run(lambda: service.questions(actor, selected, include_answers=True)) or []
    total = sum(float(row["marks"]) for row in questions)
    c1, c2, c3 = st.columns(3)
    c1.metric("Questions", len(questions))
    c2.metric("Blueprint marks", f"{total:g}")
    c3.metric("Required marks", f"{float(exam['max_marks']):g}", delta=f"{total-float(exam['max_marks']):g}")
    with st.form(f"phase3-add-question-{selected}", clear_on_submit=True):
        st.subheader("Add blueprint question")
        question_type = st.selectbox("Question type", sorted(QUESTION_TYPES), format_func=_friendly)
        prompt = st.text_area("Question prompt", height=120)
        c4, c5, c6, c7 = st.columns(4)
        marks = c4.number_input("Marks", min_value=0.5, value=1.0, step=0.5)
        negative = c5.number_input("Negative marks", min_value=0.0, value=0.0, step=0.25)
        difficulty = c6.selectbox("Difficulty", sorted(DIFFICULTIES), index=1)
        bloom = c7.selectbox("Bloom level", sorted(BLOOM_LEVELS), index=1, format_func=_friendly)
        options, correct = _question_input(question_type)
        add = st.form_submit_button("Add question", type="primary", icon=":material/add:")
    if add:
        result = run(lambda: service.add_question(actor, selected, question_type, prompt, marks, options=options, correct_answer=correct, negative_marks=negative, difficulty=difficulty, bloom_level=bloom))
        if result:
            st.toast("Question added to the secure blueprint.", icon=":material/check_circle:")
            st.rerun()
    if questions:
        st.dataframe([
            {"#": row["position"], "Type": _friendly(row["question_type"]), "Prompt": row["prompt"], "Marks": row["marks"], "Negative": row["negative_marks"], "Difficulty": _friendly(row["difficulty"]), "Bloom": _friendly(row["bloom_level"])}
            for row in questions
        ], hide_index=True, width="stretch")
    blueprint_valid = abs(total - float(exam["max_marks"])) <= 1e-6 and bool(questions)
    can_publish = blueprint_valid and service.permissions.has(actor, institution_id, "exam.publish")
    if st.button("Validate and publish examination", type="primary", icon=":material/publish:", disabled=not can_publish, key=f"publish-{selected}"):
        result = run(lambda: service.publish_exam(actor, selected))
        if result:
            st.success("Examination published. Structural editing is now locked.")
            st.rerun()
    if not blueprint_valid:
        st.caption("Publication unlocks only when active question marks exactly equal examination maximum marks.")
    elif not can_publish:
        st.info("Blueprint is valid and awaiting an examination controller or administrator to publish it.", icon=":material/approval:")


def _student_question(service: SecureExaminationService, actor: str, session_id: str, question: dict[str, Any], run: Run) -> None:
    qid = question["id"]
    with st.container(border=True):
        st.markdown(f"**Question {question['number']} · {float(question['marks']):g} marks**")
        st.write(question["prompt"])
        if float(question.get("negative_marks") or 0) > 0:
            st.caption(f"Incorrect response penalty: −{float(question['negative_marks']):g}")
        key = f"exam-answer-{session_id}-{qid}"
        current = question.get("answer")
        qtype = question["question_type"]
        if qtype in {"single_choice", "true_false"}:
            choices = ["— Select —", *question["options"]]
            index = choices.index(current) if current in choices else 0
            answer = st.radio("Select answer", choices, index=index, key=key, horizontal=qtype == "true_false")
            answer = None if answer == "— Select —" else answer
        elif qtype == "multiple_choice":
            default = current if isinstance(current, list) else []
            answer = st.multiselect("Select all correct answers", question["options"], default=[item for item in default if item in question["options"]], key=key)
        elif qtype == "short_text":
            answer = st.text_input("Answer", value=str(current or ""), key=key)
        else:
            answer = st.text_area("Answer", value=str(current or ""), height=160, key=key)
        if st.button("Save answer", icon=":material/save:", key=f"save-{key}"):
            result = run(lambda: service.save_answer(actor, session_id, qid, answer))
            if result:
                st.toast(f"Question {question['number']} saved · version {result['version']}", icon=":material/cloud_done:")


def _student_exam(service: SecureExaminationService, actor: str, institution_id: str, run: Run) -> None:
    active_session_id = st.session_state.get("phase3_active_exam_session")
    if active_session_id:
        view = run(lambda: service.session_view(actor, active_session_id))
        if view and view["state"] == "active":
            minutes, seconds = divmod(int(view["remaining_seconds"]), 60)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Time remaining", f"{minutes:02d}:{seconds:02d}")
            c2.metric("Answered", f"{view['answered']}/{len(view['questions'])}")
            c3.metric("Attempt", view["attempt_number"])
            c4.metric("Autosave policy", f"{view['autosave_seconds']} sec")
            st.subheader(view["exam_title"])
            if view.get("instructions"):
                st.info(view["instructions"], icon=":material/info:")
            st.warning("The server clock is authoritative. Save each response before final submission.", icon=":material/timer:")
            for question in view["questions"]:
                _student_question(service, actor, active_session_id, question, run)
            confirm = st.checkbox("I am ready to submit this attempt. I understand submission is final.", key=f"confirm-submit-{active_session_id}")
            if st.button("Submit examination", type="primary", icon=":material/task_alt:", disabled=not confirm, key=f"submit-{active_session_id}"):
                score = run(lambda: service.submit_exam(actor, active_session_id))
                if score:
                    st.session_state.pop("phase3_active_exam_session", None)
                    st.success("Attempt submitted and sealed. Results appear after grading and publication.")
                    st.rerun()
            return
        st.session_state.pop("phase3_active_exam_session", None)
    exams = service.list_exams(actor, institution_id, state="published")
    if not exams:
        empty_state("No published examinations", "Your enrolled subjects have no active examination window right now.", icon="✓", action_hint="Published assessments will appear here when their access window opens.")
    else:
        st.subheader("Available examinations")
        for exam in exams:
            with st.container(border=True):
                left, right = st.columns([2.2, 1], vertical_alignment="center")
                left.markdown(f"**{exam['title']}**")
                left.caption(f"{exam['subject_code']} · {exam['subject_name']} · {exam['question_count']} questions · {exam['duration_minutes']} minutes")
                access_code = right.text_input("Access code", type="password", key=f"access-{exam['id']}", label_visibility="collapsed", placeholder="Access code (if required)")
                if right.button("Start / Resume", type="primary", key=f"start-{exam['id']}"):
                    session = run(lambda: service.start_exam(actor, exam["id"], access_code=access_code))
                    if session:
                        st.session_state.phase3_active_exam_session = session["id"]
                        st.rerun()
    history = run(lambda: service.student_history(actor, institution_id)) or []
    if history:
        st.subheader("Attempt history")
        st.dataframe(history, hide_index=True, width="stretch")


def _monitor(service: SecureExaminationService, actor: str, institution_id: str, run: Run) -> None:
    exams = service.list_exams(actor, institution_id)
    if not exams:
        empty_state("No live examinations", "There are no permission-visible examination attempts to monitor.", icon="◉", action_hint="Publish an exam and wait for candidate attempts to begin.")
        return
    exam_by_id = {row["id"]: row for row in exams}
    selected = st.selectbox("Examination", list(exam_by_id), format_func=lambda value: f"{exam_by_id[value]['title']} · {_friendly(exam_by_id[value]['state'])}", key="phase3-monitor-exam")
    data = run(lambda: service.monitor(actor, selected))
    if not data:
        return
    sessions = data["sessions"]
    active = sum(1 for row in sessions if row["state"] == "active")
    pending = sum(1 for row in sessions if row.get("grading_state") == "pending_manual")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Attempts", len(sessions))
    c2.metric("Live", active)
    c3.metric("Manual grading", pending)
    c4.metric("Integrity events", sum(int(row.get("integrity_events") or 0) for row in sessions))
    if sessions:
        st.dataframe([
            {"Student": row["student_id"], "Attempt": row["attempt_number"], "State": _friendly(row["state"]), "Answered": row.get("answered", 0), "Events": row.get("integrity_events", 0), "Score": row.get("final_score"), "Grading": _friendly(row.get("grading_state", "not submitted"))}
            for row in sessions
        ], hide_index=True, width="stretch")
    if data["event_counts"]:
        st.subheader("Integrity event summary")
        st.dataframe(data["event_counts"], hide_index=True, width="stretch")
    manual_sessions = [row for row in sessions if row.get("grading_state") == "pending_manual"]
    if manual_sessions:
        st.subheader("Manual grading queue")
        session_by_id = {row["id"]: row for row in manual_sessions}
        sid = st.selectbox("Attempt", list(session_by_id), format_func=lambda value: f"{session_by_id[value]['student_id']} · attempt {session_by_id[value]['attempt_number']}")
        view = run(lambda: service.session_view(actor, sid))
        if view:
            manual_questions = [row for row in view["questions"] if row["question_type"] == "long_answer"]
            for question in manual_questions:
                with st.form(f"manual-grade-{sid}-{question['id']}"):
                    st.markdown(f"**Question {question['number']}** · {float(question['marks']):g} marks")
                    st.write(question["prompt"])
                    st.text_area("Student answer", value=str(question.get("answer") or ""), disabled=True)
                    marks = st.number_input("Awarded marks", min_value=0.0, max_value=float(question["marks"]), step=0.5)
                    feedback = st.text_area("Feedback")
                    if st.form_submit_button("Save manual grade", type="primary"):
                        result = run(lambda: service.grade_manual_answer(actor, sid, question["id"], marks, feedback))
                        if result:
                            st.success("Manual grade saved and score recalculated.")
                            st.rerun()
    all_completed = bool(sessions) and all(row.get("grading_state") == "completed" for row in sessions if row["state"] in {"submitted", "expired"})
    if st.button("Publish and lock examination results", type="primary", icon=":material/verified:", disabled=not all_completed, key=f"publish-scores-{selected}"):
        result = run(lambda: service.publish_scores(actor, selected))
        if result:
            st.success(f"{result['result_count']} result(s) published and locked.")
            st.rerun()


def _rbac(service: SecureExaminationService, actor: str, institution_id: str, run: Run) -> None:
    st.subheader("Institution permission policy")
    st.caption("Explicit deny has priority over allow. Changes are tenant-scoped and audited.")
    roles = sorted(DEFAULT_ROLE_PERMISSIONS)
    with st.form("phase3-permission-override"):
        c1, c2, c3 = st.columns(3)
        role = c1.selectbox("Role", roles, format_func=_friendly)
        permission = c2.selectbox("Permission", list(PERMISSIONS))
        effect = c3.selectbox("Override", ["allow", "deny"])
        if st.form_submit_button("Save permission override", type="primary"):
            result = run(lambda: service.permissions.set_override(actor, institution_id, role, permission, effect))
            if result:
                st.success("Permission override saved.")
                st.rerun()
    matrix = run(lambda: service.permissions.matrix(actor, institution_id)) or []
    role_filter = st.multiselect("Filter roles", roles, default=["institution_administrator", "subject_teacher", "university_student"])
    filtered = [row for row in matrix if row["role"] in role_filter]
    st.dataframe(filtered, hide_index=True, width="stretch")


def render_examination_workspace(platform: Any, actor: str, institution_id: str, run: Run) -> None:
    service = SecureExaminationService(platform)
    roles = render_workspace_context(platform, actor, institution_id)
    tabs: list[str] = ["Command Center"]
    if service.permissions.has(actor, institution_id, "exam.create"):
        tabs.append("Exam Builder")
    if service.permissions.has(actor, institution_id, "exam.take"):
        tabs.append("Take Exam")
    if service.permissions.has(actor, institution_id, "exam.monitor"):
        tabs.append("Monitor & Grade")
    if service.permissions.has(actor, institution_id, "rbac.manage"):
        tabs.append("Permissions")
    selected = st.segmented_control("Examination workspace", tabs, default=tabs[0], key=f"phase3-exam-workspace-{actor}-{institution_id}")
    if selected == "Command Center":
        _overview(service, actor, institution_id)
    elif selected == "Exam Builder":
        _builder(service, actor, institution_id, run)
    elif selected == "Take Exam":
        _student_exam(service, actor, institution_id, run)
    elif selected == "Monitor & Grade":
        _monitor(service, actor, institution_id, run)
    elif selected == "Permissions":
        _rbac(service, actor, institution_id, run)
