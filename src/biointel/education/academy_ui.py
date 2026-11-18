from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Callable

from ._streamlit_compat import st

from .platform import TEACHER
from biointel.ui.product_experience_v8 import course_cover_markup
from biointel.ui.frontend_v10 import empty_state

RunAction = Callable[[Callable[[], Any]], Any]


def _all(p: Any, sql: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return p._all(sql, args)


def _roles(p: Any, actor: str, iid: str) -> set[str]:
    return {row["role"] for row in p.membership(actor, iid)}


def _label(course: dict[str, Any]) -> str:
    return f"{course['title']} · {course['difficulty'].title()}"


def _set_view(view: str, course_id: str = "") -> None:
    st.session_state["academy_workspace_view"] = view
    if course_id:
        st.session_state["academy_learning_course"] = course_id


def _institution(p: Any, iid: str) -> dict[str, Any]:
    return p._one("SELECT name,kind FROM institutions WHERE id=?", (iid,)) or {"name": "Institution", "kind": "education"}


def _empty(title: str, body: str, icon: str) -> None:
    with st.container(border=True, horizontal_alignment="center"):
        st.markdown(icon)
        st.subheader(title, anchor=False)
        st.caption(body, text_alignment="center")


def _pathway(title: str, caption: str, stages: list[dict[str, Any]]) -> None:
    colors = {"complete": "green", "active": "blue", "attention": "orange", "waiting": "gray"}
    with st.container(border=True):
        st.subheader(title, anchor=False)
        st.caption(caption)
        columns = st.columns(min(len(stages), 4), gap="small")
        for column, stage in zip(columns, stages):
            with column.container(border=True, height="stretch"):
                st.markdown(str(stage["icon"]))
                st.badge(str(stage["status"]), color=colors.get(str(stage["state"]), "gray"))
                st.markdown(f"**{stage['label']}**")
                st.caption(str(stage["detail"]))
                if "progress" in stage:
                    st.progress(float(stage["progress"]), text=str(stage.get("progress_text", "")), width="stretch")


def _learning_pathway(p: Any, actor: str, course: dict[str, Any] | None) -> None:
    if not course:
        _pathway("Academy pathway", "A course enrollment starts a persisted learning journey.", [
            {"icon": ":material/library_books:", "label": "Choose", "status": "Ready", "state": "active", "detail": "Browse institution-published courses."},
            {"icon": ":material/play_lesson:", "label": "Learn", "status": "Waiting", "state": "waiting", "detail": "Lecture progress begins after enrollment."},
            {"icon": ":material/quiz:", "label": "Assess", "status": "Waiting", "state": "waiting", "detail": "Published course quizzes provide scored evidence."},
            {"icon": ":material/workspace_premium:", "label": "Verify", "status": "Waiting", "state": "waiting", "detail": "Completion rules gate certificate issuance."},
        ])
        return
    total, done = int(course.get("lecture_count") or 0), int(course.get("completed_count") or 0)
    assessment = p._one("""
        SELECT COUNT(DISTINCT q.id) quizzes,COUNT(a.id) attempts,
               SUM(CASE WHEN a.passed=1 THEN 1 ELSE 0 END) passed,MAX(a.score) best_score
        FROM quizzes q LEFT JOIN quiz_attempts a ON a.quiz_id=q.id AND a.student_id=?
        WHERE q.course_id=? AND q.state='published'
    """, (actor, course["id"])) or {}
    credential = p._one("SELECT revoked FROM certificates WHERE course_id=? AND student_id=?", (course["id"], actor))
    passed = int(assessment.get("passed") or 0)
    progress = done / total if total else 0.0
    _pathway(f"Learning journey · {course['title']}", "Every stage below is derived from persisted enrollment, progress, assessment and credential records.", [
        {"icon": ":material/how_to_reg:", "label": "Enrolled", "status": "Complete", "state": "complete", "detail": "Active institution enrollment."},
        {"icon": ":material/play_lesson:", "label": "Learn", "status": "Complete" if total and done >= total else ("In progress" if total else "Waiting for lectures"), "state": "complete" if total and done >= total else ("active" if total else "waiting"), "detail": f"{done} of {total} published lectures complete.", "progress": progress, "progress_text": f"{int(round(progress * 100))}%"},
        {"icon": ":material/quiz:", "label": "Assess", "status": "Passed" if passed else ("Available" if assessment.get("quizzes") else "Waiting"), "state": "complete" if passed else ("active" if assessment.get("quizzes") else "waiting"), "detail": f"{int(assessment.get('attempts') or 0)} attempts · {passed} passed."},
        {"icon": ":material/workspace_premium:", "label": "Verify", "status": "Issued" if credential and not credential["revoked"] else ("Revoked" if credential else "Not issued"), "state": "complete" if credential and not credential["revoked"] else ("attention" if credential else "waiting"), "detail": "Current durable credential state."},
    ])


def _production_pathway(course: dict[str, Any], readiness: dict[str, Any]) -> None:
    rights = int(readiness.get("rights_count") or 0)
    lectures = int(course.get("lecture_count") or 0)
    ready = int(readiness.get("ready_media") or 0)
    dependency = int(readiness.get("dependency_media") or 0)
    _pathway("Lecture production pipeline", "Rights and processing indicators come from stored course, declaration and lecture records.", [
        {"icon": ":material/menu_book:", "label": "Course", "status": course["state"].title(), "state": "complete" if course["state"] == "published" else "active", "detail": f"{course['difficulty'].title()} course record."},
        {"icon": ":material/copyright:", "label": "Rights", "status": "Confirmed" if rights else "Required", "state": "complete" if rights else "attention", "detail": f"{rights} confirmed declaration{'s' if rights != 1 else ''}."},
        {"icon": ":material/video_file:", "label": "Originals", "status": f"{lectures} stored" if lectures else "No lecture", "state": "complete" if lectures else "waiting", "detail": "Uploaded originals retain SHA-256 evidence."},
        {"icon": ":material/movie_edit:", "label": "Processing", "status": "Ready" if ready and not dependency else ("Dependency required" if dependency else "Waiting"), "state": "complete" if ready and not dependency else ("attention" if dependency else "waiting"), "detail": f"{ready} ready · {dependency} require an external processing dependency."},
    ])


def _owned(p: Any, actor: str, iid: str) -> list[dict[str, Any]]:
    return _all(p, """
        SELECT c.*,COUNT(DISTINCT l.id) lecture_count,COUNT(DISTINCT q.id) quiz_count,
               COUNT(DISTINCT e.id) learner_count
        FROM courses c LEFT JOIN lectures l ON l.course_id=c.id
        LEFT JOIN quizzes q ON q.course_id=c.id
        LEFT JOIN academy_enrollments e ON e.course_id=c.id AND e.state='active'
        WHERE c.institution_id=? AND c.educator_id=? GROUP BY c.id ORDER BY c.updated_at DESC
    """, (iid, actor))


def _catalog(p: Any, actor: str, iid: str) -> list[dict[str, Any]]:
    return _all(p, """
        SELECT c.*,COUNT(DISTINCT l.id) lecture_count,COUNT(DISTINCT q.id) quiz_count,
               CASE WHEN mine.id IS NULL THEN 0 ELSE 1 END enrolled
        FROM courses c LEFT JOIN lectures l ON l.course_id=c.id AND l.state='published'
        LEFT JOIN quizzes q ON q.course_id=c.id AND q.state='published'
        LEFT JOIN academy_enrollments mine ON mine.course_id=c.id AND mine.student_id=? AND mine.state='active'
        WHERE c.institution_id=? AND c.state='published' GROUP BY c.id ORDER BY c.updated_at DESC
    """, (actor, iid))


def _learning(p: Any, actor: str, iid: str) -> list[dict[str, Any]]:
    return _all(p, """
        SELECT c.*,COUNT(DISTINCT l.id) lecture_count,
               COUNT(DISTINCT CASE WHEN w.completed=1 THEN l.id END) completed_count
        FROM academy_enrollments e JOIN courses c ON c.id=e.course_id
        LEFT JOIN lectures l ON l.course_id=c.id AND l.state='published'
        LEFT JOIN watch_progress w ON w.lecture_id=l.id AND w.user_id=e.student_id
        WHERE e.institution_id=? AND e.student_id=? AND e.state='active'
        GROUP BY c.id ORDER BY MAX(COALESCE(w.updated_at,e.updated_at)) DESC
    """, (iid, actor))


def _overview(p: Any, actor: str, iid: str, roles: set[str], run: RunAction) -> None:
    owned, learning, catalogue = _owned(p, actor, iid), _learning(p, actor, iid), _catalog(p, actor, iid)
    institution = _institution(p, iid)
    certificates = _all(p, "SELECT * FROM certificates WHERE institution_id=? AND student_id=?", (iid, actor))
    readiness = p._one("""
        SELECT COUNT(DISTINCT r.id) rights_count,
               COUNT(DISTINCT CASE WHEN l.processing_state='original_ready' THEN l.id END) ready_media,
               COUNT(DISTINCT CASE WHEN l.processing_state='processing_dependency_required' THEN l.id END) dependency_media
        FROM content_rights r
        LEFT JOIN lectures l ON l.educator_id=r.educator_id AND l.institution_id=r.institution_id
        WHERE r.institution_id=? AND r.educator_id=? AND r.rights_confirmed=1
    """, (iid, actor)) or {}

    with st.container(border=True):
        lead, status = st.columns([1.55, .45], vertical_alignment="center")
        with lead:
            st.markdown(":material/auto_stories: **Your learning command centre**")
            st.subheader(institution["name"])
            st.caption("Move from course design to evidence-backed completion without leaving the institution boundary.")
        with status:
            st.badge(institution["kind"].replace("_", " ").title(), color="blue")
            st.badge("Local-first records", color="green")
        with st.container(horizontal=True):
            if roles & TEACHER:
                st.button("Open educator studio", icon=":material/design_services:", type="primary",
                          on_click=_set_view, args=("Educator studio",), key="academy-quick-studio")
            st.button("Browse learning", icon=":material/play_circle:",
                      on_click=_set_view, args=("Learn",), key="academy-quick-learn")
            st.button("View credentials", icon=":material/workspace_premium:",
                      on_click=_set_view, args=("Credentials & safety",), key="academy-quick-credentials")

    with st.container(horizontal=True):
        st.metric("Published courses", sum(x["state"] == "published" for x in owned), border=True)
        st.metric("Available catalogue", len(catalogue), border=True)
        st.metric("Active learning", len(learning), border=True)
        st.metric("Credentials", sum(not x["revoked"] for x in certificates), border=True)

    _learning_pathway(p, actor, learning[0] if learning else None)

    left, right = st.columns([1.35, .85], gap="medium")
    with left.container(border=True):
        st.subheader("Continue learning")
        st.caption("Progress is calculated from your stored lecture completion records.")
        if not learning:
            _empty("Nothing in progress", "Enroll from the catalogue to build your learning queue.", ":material/play_circle:")
        else:
            cards = st.columns(2, gap="small")
            for index, course in enumerate(learning[:4]):
                total, done = int(course["lecture_count"] or 0), int(course["completed_count"] or 0)
                percent = int(round(100 * done / total)) if total else 0
                with cards[index % 2].container(border=True, height="stretch"):
                    st.badge(course["difficulty"].title(), color="blue")
                    st.markdown(f"**{course['title']}**")
                    st.progress(done / total if total else 0.0, text=f"{percent}% complete", width="stretch")
                    st.caption(f"{done} of {total} lectures complete" if total else "Awaiting published lectures")
                    st.button("Continue", icon=":material/arrow_forward:", key=f"continue-{course['id']}",
                              on_click=_set_view, args=("Learn", course["id"]), width="stretch")
    with right.container(border=True):
        st.subheader("Studio readiness")
        st.badge(f"{int(readiness.get('rights_count') or 0)} rights declarations", color="green" if readiness.get("rights_count") else "orange")
        st.badge(f"{int(readiness.get('ready_media') or 0)} original-ready lectures", color="green")
        if int(readiness.get("dependency_media") or 0):
            st.badge(f"{int(readiness['dependency_media'])} need processing dependency", color="orange")
        config = (run(lambda: p.dashboard(actor, iid)) or {}).get("configuration", {})
        video = config.get("video_processing", "PROCESSING DEPENDENCY REQUIRED")
        st.caption(f"Video processing: {video.replace('_', ' ').title()}.")
        st.info("Bundled offline lecture transcription is available. TURN/SFU and server-side live-class recording still require verified deployment infrastructure.", icon=":material/info:")

    with st.container(border=True):
        st.subheader("Access & trust")
        st.markdown(" ".join(f":blue-badge[{role.replace('_', ' ')}]" for role in sorted(roles)))
        st.caption("Course, learner and credential queries are scoped to this institution and authenticated membership.")

def _course_setup(p: Any, actor: str, iid: str, run: RunAction) -> None:
    profile = p._one("SELECT * FROM educator_profiles WHERE institution_id=? AND user_id=?", (iid, actor))
    left, right = st.columns(2, gap="medium")
    with left.container(border=True):
        st.subheader("Educator profile")
        if profile:
            st.badge("Profile active", color="green")
        with st.form("academy-profile", border=False):
            bio = st.text_area("Educator bio", value=(profile or {}).get("bio", ""),
                               placeholder="Teaching experience and research focus")
            save = st.form_submit_button("Save profile", icon=":material/save:", width="stretch")
        if save and run(lambda: p.create_educator(actor, iid, bio)):
            st.toast("Educator profile saved", icon=":material/check_circle:")
    with right.container(border=True):
        st.subheader("Create a course")
        with st.form("academy-course"):
            title = st.text_input("Course title", placeholder="Molecular genetics foundations")
            description = st.text_area("Description", placeholder="Learning goals, prerequisites and scope")
            difficulty = st.segmented_control("Difficulty", ["beginner", "intermediate", "advanced"], default="beginner")
            publish = st.toggle("Publish to the institution catalogue")
            create = st.form_submit_button("Create course", type="primary", icon=":material/school:", width="stretch")
        if create:
            if not title.strip():
                st.error("Course title is required.")
            else:
                item = run(lambda: p.create_course(actor, iid, title.strip(), description.strip(), difficulty or "beginner", publish))
                if item:
                    st.session_state["academy_studio_course"] = item["id"]
                    st.toast("Course created", icon=":material/check_circle:")


def _rights_upload(p: Any, actor: str, iid: str, course: dict[str, Any], run: RunAction, root: Path) -> None:
    rights = _all(p, "SELECT * FROM content_rights WHERE institution_id=? AND educator_id=? AND rights_confirmed=1 ORDER BY updated_at DESC", (iid, actor))
    left, right = st.columns(2, gap="medium")
    with left.container(border=True):
        st.subheader("Rights declaration")
        st.caption("Every lecture must reference explicit ownership or licence evidence.")
        with st.form(f"rights-{course['id']}"):
            owner = st.text_input("Content owner")
            licence = st.text_input("Licence", placeholder="Owned, CC BY 4.0, institutional licence…")
            declaration = st.text_area("Third-party material declaration")
            download = st.checkbox("Learners may download the original")
            confirm = st.form_submit_button("Confirm rights", type="primary", icon=":material/verified:", width="stretch")
        if confirm:
            if not owner.strip() or not licence.strip():
                st.error("Content owner and licence are required.")
            elif run(lambda: p.confirm_rights(actor, iid, owner.strip(), licence.strip(), declaration.strip(), download)):
                st.toast("Rights declaration stored", icon=":material/check_circle:")
    with right.container(border=True):
        st.subheader("Lecture upload")
        if not rights:
            st.warning("Create a rights declaration, then reopen this workspace to upload.")
            return
        by_id = {x["id"]: x for x in rights}
        rights_id = st.selectbox("Rights declaration", list(by_id),
                                 format_func=lambda key: f"{by_id[key]['owner_name']} · {by_id[key]['license']}")
        title = st.text_input("Lecture title", key=f"lecture-title-{course['id']}")
        description = st.text_area("Lecture description", key=f"lecture-desc-{course['id']}")
        upload = st.file_uploader("Video file", type=["mp4", "webm", "mov", "m4v"],
                                  help="Original is SHA-256 hashed. Renditions require FFmpeg.",
                                  key=f"lecture-file-{course['id']}", width="stretch")
        if upload:
            st.caption(f"{upload.name} · {upload.size / 1024 ** 2:.1f} MiB")
        if st.button("Validate and publish lecture", type="primary", icon=":material/upload:",
                     disabled=not bool(upload and title.strip()), key=f"upload-{course['id']}", width="stretch"):
            temp_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(prefix="biointel-lecture-", suffix=Path(upload.name).suffix, delete=False) as temp:
                    temp.write(upload.getbuffer())
                    temp_path = Path(temp.name)
                item = run(lambda: p.upload_lecture(actor, course["id"], title.strip(), temp_path, rights_id, description.strip()))
            finally:
                if temp_path:
                    temp_path.unlink(missing_ok=True)
            if item:
                from .phase15 import EducationPhase15Service
                from .phase16 import EducationPhase16Service

                asset = run(lambda: EducationPhase15Service(p, root=root).register_media_asset(
                    actor, item["id"], item["video_path"], probe=True
                ))
                job = None
                transcription_job = None
                if asset:
                    phase16 = EducationPhase16Service(p, root=root)
                    job = run(lambda: phase16.plan_media_processing(
                        actor, asset["id"], profile="thumbnail"
                    ))
                    transcription_job = run(lambda: phase16.plan_lecture_transcription(
                        actor, item["id"], language="auto"
                    ))
                if job and job["state"] == "configuration_required":
                    st.warning(
                        f"Lecture stored and governed processing job {job['id']} created. "
                        "FFmpeg configuration is required before execution."
                    )
                elif job:
                    st.success(
                        f"Lecture stored · governed media asset {asset['id']} · "
                        f"processing job {job['id']} ({job['state']})"
                    )
                else:
                    st.warning("Lecture stored, but the governed media job could not be created. Review the error above.")
                if transcription_job and transcription_job["state"] == "planned":
                    st.success(
                        f"Offline multilingual transcription job {transcription_job['id']} planned. "
                        "Run it from Lecture intelligence, then review the transcript before Shiro indexing."
                    )
                elif transcription_job:
                    st.warning(
                        f"Transcription job {transcription_job['id']} · {transcription_job['state']}. "
                        f"{transcription_job['error_text']}"
                    )


def _studio(p: Any, actor: str, iid: str, roles: set[str], run: RunAction, root: Path) -> None:
    if not roles & TEACHER:
        _empty("Educator access required", "A teacher, lecturer or institution-admin role is required.", ":material/lock:")
        return
    courses = _owned(p, actor, iid)
    with st.expander("Educator profile & new course", icon=":material/add_circle:", expanded=not bool(courses)):
        _course_setup(p, actor, iid, run)
    courses = _owned(p, actor, iid)
    if not courses:
        _empty("No courses yet", "Create a course above to open the content studio.", ":material/school:")
        return
    by_id = {x["id"]: x for x in courses}
    remembered = st.session_state.get("academy_studio_course")
    index = list(by_id).index(remembered) if remembered in by_id else 0
    course_id = st.selectbox("Course workspace", list(by_id), index=index, format_func=lambda key: _label(by_id[key]))
    course = by_id[course_id]
    readiness = p._one("""
        SELECT COUNT(DISTINCT r.id) rights_count,
               COUNT(DISTINCT CASE WHEN l.processing_state='original_ready' THEN l.id END) ready_media,
               COUNT(DISTINCT CASE WHEN l.processing_state='processing_dependency_required' THEN l.id END) dependency_media
        FROM courses c LEFT JOIN content_rights r
          ON r.institution_id=c.institution_id AND r.educator_id=c.educator_id AND r.rights_confirmed=1
        LEFT JOIN lectures l ON l.course_id=c.id WHERE c.id=?
    """, (course_id,)) or {}
    with st.container(border=True):
        heading, state = st.columns([4, 1], vertical_alignment="center")
        with heading:
            st.markdown(":material/design_services: **Educator workspace**")
            st.subheader(course["title"])
        with state:
            st.badge(course["state"].title(), color="green" if course["state"] == "published" else "gray")
            st.badge(course["difficulty"].title(), color="blue")
        st.caption(course["description"] or "Add a description so learners understand this course's goals.")
        with st.container(horizontal=True):
            st.metric("Lectures", int(course["lecture_count"] or 0), border=True)
            st.metric("Quizzes", int(course["quiz_count"] or 0), border=True)
            st.metric("Learners", int(course["learner_count"] or 0), border=True)
            st.metric("Rights records", int(readiness.get("rights_count") or 0), border=True)
        with st.container(horizontal=True):
            st.badge(f"{int(readiness.get('ready_media') or 0)} original-ready", color="green")
            if int(readiness.get("dependency_media") or 0):
                st.badge(f"{int(readiness['dependency_media'])} processing dependency required", color="orange")
            st.caption("All lecture media must retain a rights declaration and SHA-256 evidence.")
    _production_pathway(course, readiness)
    summary, media, assessment = st.tabs(["Course summary", "Rights & lectures", "Quiz & credentials"])
    with summary.container(border=True):
        st.subheader("Publishing boundary")
        st.write("Published courses are institution-scoped; Academy does not syndicate content externally.")
        st.markdown(f"**Difficulty:** {course['difficulty'].title()}  \n**Created:** {course['created_at']}")
    with media:
        _rights_upload(p, actor, iid, course, run, root)
        lectures = _all(p, "SELECT title,mime_type,size_bytes,processing_state,created_at FROM lectures WHERE course_id=? ORDER BY created_at DESC", (course_id,))
        if lectures:
            st.dataframe(
                lectures,
                hide_index=True,
                width="stretch",
                column_config={
                    "title": st.column_config.TextColumn("Lecture", pinned=True),
                    "mime_type": st.column_config.TextColumn("Media type"),
                    "size_bytes": st.column_config.NumberColumn("Size", format="%d bytes"),
                    "processing_state": st.column_config.TextColumn("Processing readiness"),
                    "created_at": st.column_config.DatetimeColumn("Published", format="MMM DD, YYYY"),
                },
            )
    with assessment:
        draft_key = f"quiz-draft-{course_id}"
        st.session_state.setdefault(draft_key, [])
        draft = st.session_state[draft_key]
        left, right = st.columns(2, gap="medium")
        with left.container(border=True):
            st.subheader("Quiz builder")
            with st.form(f"question-{course_id}", clear_on_submit=True):
                prompt = st.text_area("Question")
                answer = st.text_input("Correct answer")
                alternatives = st.text_area("Alternative choices", placeholder="One per line; optional")
                add = st.form_submit_button("Add question", icon=":material/add:", width="stretch")
            if add:
                if not prompt.strip() or not answer.strip():
                    st.error("Question and correct answer are required.")
                else:
                    others = [x.strip() for x in alternatives.splitlines() if x.strip() and x.strip() != answer.strip()]
                    draft.append({"prompt": prompt.strip(), "answer": answer.strip(), "options": [answer.strip(), *others]})
                    st.toast("Question added", icon=":material/check:")
            if draft:
                st.dataframe([{"Question": x["prompt"], "Type": "Choice" if len(x["options"]) > 1 else "Free response"} for x in draft], hide_index=True, width="stretch")
                quiz_title = st.text_input("Quiz title", key=f"quiz-title-{course_id}")
                if st.button("Publish quiz", type="primary", icon=":material/publish:", key=f"publish-quiz-{course_id}", width="stretch"):
                    if not quiz_title.strip():
                        st.error("Quiz title is required.")
                    elif run(lambda: p.create_quiz(actor, course_id, quiz_title.strip(), list(draft), True)):
                        st.session_state[draft_key] = []
                        st.toast("Quiz published", icon=":material/check_circle:")
            else:
                st.caption("Add a question to begin a scored assessment.")
        with right.container(border=True):
            st.subheader("Completion & credentials")
            learners = _all(p, """
                SELECT e.student_id,COUNT(DISTINCT l.id) lecture_count,
                       COUNT(DISTINCT CASE WHEN w.completed=1 THEN l.id END) completed_count,
                       COUNT(DISTINCT CASE WHEN a.passed=1 THEN a.id END) passed_attempts,
                       MAX(cert.id) certificate_id
                FROM academy_enrollments e
                LEFT JOIN lectures l ON l.course_id=e.course_id AND l.state='published'
                LEFT JOIN watch_progress w ON w.lecture_id=l.id AND w.user_id=e.student_id
                LEFT JOIN quizzes q ON q.course_id=e.course_id AND q.state='published'
                LEFT JOIN quiz_attempts a ON a.quiz_id=q.id AND a.student_id=e.student_id
                LEFT JOIN certificates cert ON cert.course_id=e.course_id AND cert.student_id=e.student_id
                WHERE e.course_id=? AND e.state='active' GROUP BY e.student_id
            """, (course_id,))
            if not learners:
                st.caption("Learner completion evidence will appear here.")
            else:
                by_student = {x["student_id"]: x for x in learners}
                student = st.selectbox("Learner", list(by_student), key=f"credential-{course_id}")
                row = by_student[student]
                total, done, passed = int(row["lecture_count"] or 0), int(row["completed_count"] or 0), int(row["passed_attempts"] or 0)
                st.progress(done / total if total else 0.0, text=f"{done} of {total} lectures complete", width="stretch")
                st.metric("Passed attempts", passed, border=True)
                eligible = total > 0 and done >= total and passed > 0
                st.caption("Eligible for a certificate." if eligible else "Completion rules are not met yet.")
                if st.button("Issue verifiable certificate", type="primary", icon=":material/verified:",
                             disabled=not eligible or bool(row["certificate_id"]), key=f"issue-{course_id}", width="stretch"):
                    item = run(lambda: p.issue_certificate(actor, course_id, student))
                    if item:
                        st.success(f"Certificate issued · {item['verification_code']}")


def _catalog_view(p: Any, actor: str, iid: str, run: RunAction) -> None:
    courses = _catalog(p, actor, iid)
    if not courses:
        _empty("Catalogue is empty", "Published institution courses will appear here.", ":material/library_books:")
        return
    levels = st.pills("Difficulty", ["beginner", "intermediate", "advanced"], selection_mode="multi")
    visible = [course for course in courses if not levels or course["difficulty"] in levels]
    if not visible:
        _empty("No matching courses", "Clear a difficulty filter to see the full catalogue.", ":material/filter_list:")
        return
    st.caption(f"{len(visible)} published course{'s' if len(visible) != 1 else ''} in this institution")
    cards = st.columns(3, gap="medium")
    for index, course in enumerate(visible[:6]):
        with cards[index % 3].container(border=True, height="stretch"):
            st.markdown(course_cover_markup(
                title=str(course["title"]),
                difficulty=str(course["difficulty"]),
                index=index,
                label="BIOINTEL ACADEMY COURSE",
            ), unsafe_allow_html=True)
            with st.container(horizontal=True):
                st.badge("Enrolled", color="green") if course["enrolled"] else st.badge("Open", color="gray")
                st.badge(f"{int(course['lecture_count'] or 0)} lectures", color="blue")
                st.badge(f"{int(course['quiz_count'] or 0)} quizzes", color="violet")
            st.caption(course["description"] or "Evidence-led institution course with governed learning progress.")
            if course["enrolled"]:
                st.button("Continue learning", icon=":material/play_arrow:", type="primary", key=f"catalog-open-{course['id']}",
                          on_click=_set_view, args=("Learn", course["id"]), width="stretch")
            elif st.button("Enroll in course", type="primary", icon=":material/add_task:", key=f"enroll-{course['id']}", width="stretch"):
                if run(lambda course_id=course["id"]: p.enroll_course(actor, course_id)):
                    st.toast("Enrollment active", icon=":material/check_circle:")
    if len(visible) > 6:
        st.caption(f"Showing 6 of {len(visible)} courses. Use the difficulty filter to narrow the catalogue.")

def _learn(p: Any, actor: str, iid: str, run: RunAction, root: Path) -> None:
    catalogue, learning = st.tabs(["Course catalogue", "My learning"])
    with catalogue:
        _catalog_view(p, actor, iid, run)
    with learning:
        courses = _learning(p, actor, iid)
        if not courses:
            _empty("No active enrollments", "Choose a course from the catalogue.", ":material/auto_stories:")
            return
        by_id = {x["id"]: x for x in courses}
        remembered = st.session_state.get("academy_learning_course")
        index = list(by_id).index(remembered) if remembered in by_id else 0
        course_id = st.selectbox("Learning workspace", list(by_id), index=index,
                                 format_func=lambda key: _label(by_id[key]), key="academy-learning-course")
        course = by_id[course_id]
        total, done = int(course["lecture_count"] or 0), int(course["completed_count"] or 0)
        passed = p._one("""
            SELECT COUNT(*) count FROM quiz_attempts a JOIN quizzes q ON q.id=a.quiz_id
            WHERE q.course_id=? AND a.student_id=? AND a.passed=1
        """, (course_id, actor)) or {"count": 0}
        credential = p._one("SELECT revoked FROM certificates WHERE course_id=? AND student_id=?", (course_id, actor))
        with st.container(border=True):
            heading, status = st.columns([3, 1], vertical_alignment="center")
            with heading:
                st.markdown(":material/play_lesson: **Learning workspace**")
                st.subheader(course["title"])
                st.caption(course["description"] or "No course description provided.")
            with status:
                st.badge(course["difficulty"].title(), color="blue")
                st.badge("Credential issued", color="green") if credential and not credential["revoked"] else st.badge("In progress", color="orange")
            st.progress(done / total if total else 0.0,
                        text=f"{done} of {total} lectures complete" if total else "Awaiting lectures",
                        width="stretch")
            with st.container(horizontal=True):
                st.metric("Lectures remaining", max(total - done, 0), border=True)
                st.metric("Passed assessments", int(passed["count"] or 0), border=True)
                st.metric("Completion", f"{int(round(100 * done / total)) if total else 0}%", border=True)
        _learning_pathway(p, actor, course)
        lecture_tab, quiz_tab = st.tabs(["Lectures", "Assessments"])
        with lecture_tab:
            lectures = _all(p, "SELECT * FROM lectures WHERE course_id=? AND state='published' ORDER BY created_at", (course_id,))
            if not lectures:
                _empty("No published lectures", "Your educator has not published lecture media yet.", ":material/video_library:")
            else:
                by_lecture = {x["id"]: x for x in lectures}
                lecture_id = st.selectbox("Lecture", list(by_lecture), format_func=lambda key: by_lecture[key]["title"])
                lecture = by_lecture[lecture_id]
                left, right = st.columns([1.3, .7], gap="medium")
                with left.container(border=True):
                    st.subheader(lecture["title"])
                    media = Path(lecture["video_path"])
                    st.video(str(media)) if media.is_file() else st.error("Stored lecture file is unavailable.")
                    st.caption(f"{lecture['mime_type']} · SHA-256 {lecture['sha256'][:12]}…")
                with right.container(border=True):
                    from .phase7 import EducationPhase7Service
                    from .phase7_ui import render_playback_evidence_controls

                    render_playback_evidence_controls(
                        EducationPhase7Service(p, root=root), p, actor, lecture
                    )
        with quiz_tab:
            quizzes = _all(p, "SELECT * FROM quizzes WHERE course_id=? AND state='published' ORDER BY created_at", (course_id,))
            if not quizzes:
                _empty("No assessments", "Published quizzes will appear here.", ":material/quiz:")
            else:
                by_quiz = {x["id"]: x for x in quizzes}
                quiz_id = st.selectbox("Assessment", list(by_quiz), format_func=lambda key: by_quiz[key]["title"])
                quiz = by_quiz[quiz_id]
                try:
                    questions = [x for x in json.loads(quiz["questions_json"]) if isinstance(x, dict)]
                except (TypeError, json.JSONDecodeError):
                    questions = []
                with st.form(f"attempt-{quiz_id}"):
                    answers = []
                    for number, question in enumerate(questions, 1):
                        prompt = str(question.get("prompt") or f"Question {number}")
                        options = [str(x) for x in question.get("options", []) if str(x)]
                        if len(options) > 1:
                            answer = st.selectbox(f"{number}. {prompt}", options, index=None, placeholder="Choose an answer")
                            answers.append(answer or "")
                        else:
                            answers.append(st.text_input(f"{number}. {prompt}"))
                    submit = st.form_submit_button("Submit assessment", type="primary", icon=":material/task_alt:", width="stretch")
                if submit:
                    result = run(lambda: p.attempt_quiz(actor, quiz_id, answers))
                    if result:
                        (st.success if result["passed"] else st.warning)(f"{'Passed' if result['passed'] else 'Not passed'} · {result['score']:.1f}%")


def _live(p: Any, actor: str, iid: str, run: RunAction) -> None:
    config = (run(lambda: p.dashboard(actor, iid)) or {}).get("configuration", {})
    video = config.get("video_processing", "PROCESSING DEPENDENCY REQUIRED")
    calls = config.get("calls", "CONFIGURATION REQUIRED")
    with st.container(border=True):
        lead, boundary = st.columns([1.25, .75], gap="medium")
        with lead:
            st.markdown(":material/video_call: **Live classroom handoff**")
            st.subheader("Teach live through BioIntel Calls")
            st.write("Academy owns courses, rights and learner progress. BioIntel Calls owns authenticated rooms and media signaling. No meeting is created silently from this page.")
            try:
                st.page_link("pages/322_Connect_Live_and_Calls.py", label="Open BioIntel live and calls",
                             icon=":material/open_in_new:", width="stretch")
            except KeyError:
                st.caption("Open ‘BioIntel Live & Calls’ from the Connect section in the sidebar.")
        with boundary.container(border=True):
            st.markdown("**Session boundary**")
            st.badge(f"Calls: {calls.replace('_', ' ').title()}", color="orange" if "REQUIRED" in calls else "green")
            st.badge("No automatic recording", color="gray")
            st.caption("A course enrollment never grants access to an unrelated Calls room.")
    _pathway("Live-class readiness", "This graphic separates verified local capability from services that still need external evidence.", [
        {"icon": ":material/school:", "label": "Academy context", "status": "Operational", "state": "complete", "detail": "Course and membership records are stored locally."},
        {"icon": ":material/video_call:", "label": "Calls workspace", "status": calls.replace("_", " ").title(), "state": "attention" if "REQUIRED" in calls else "complete", "detail": "Open the authenticated Calls workspace explicitly."},
        {"icon": ":material/router:", "label": "Media relay", "status": "Configuration required", "state": "attention", "detail": "No TURN or SFU availability is asserted here."},
        {"icon": ":material/fact_check:", "label": "Evidence services", "status": "Not asserted", "state": "waiting", "detail": "No server recording or transcript is claimed."},
    ])
    left, right = st.columns(2, gap="medium")
    with left.container(border=True):
        st.subheader("What is stored here")
        st.markdown("- Course and educator ownership\n- Rights declarations and lecture hashes\n- Learner-confirmed progress\n- Quiz attempts and credentials")
    with right.container(border=True):
        st.subheader("What needs external evidence")
        st.markdown("- Relay or SFU availability\n- Server-side media files\n- Optional live-call provider transcription (uploaded lectures use bundled offline transcription)\n- Provider retention and consent controls")
        st.caption(f"Lecture rendition status: {video.replace('_', ' ').title()}.")

def _credentials_safety(p: Any, actor: str, iid: str, run: RunAction) -> None:
    credentials, safety = st.tabs(["Credentials", "Trust & safety"])
    with credentials:
        rows = _all(p, """
            SELECT c.title course,cert.issued_at,cert.revoked,cert.verification_code
            FROM certificates cert JOIN courses c ON c.id=cert.course_id
            WHERE cert.institution_id=? AND cert.student_id=? ORDER BY cert.issued_at DESC
        """, (iid, actor))
        active = sum(not row["revoked"] for row in rows)
        assessment = p._one("""
            SELECT COUNT(a.id) attempts,SUM(CASE WHEN a.passed=1 THEN 1 ELSE 0 END) passed,
                   AVG(a.score) average_score
            FROM quiz_attempts a JOIN quizzes q ON q.id=a.quiz_id
            JOIN courses c ON c.id=q.course_id
            WHERE c.institution_id=? AND a.student_id=?
        """, (iid, actor)) or {}
        attempts, passed = int(assessment.get("attempts") or 0), int(assessment.get("passed") or 0)
        with st.container(border=True):
            st.markdown(":material/workspace_premium: **Verified learning record**")
            st.subheader("Credentials")
            st.caption("Certificates are issued only after every published lecture is complete and at least one course quiz is passed.")
            with st.container(horizontal=True):
                st.metric("Active", active, border=True)
                st.metric("Revoked", len(rows) - active, border=True)
                st.metric("Total issued", len(rows), border=True)
        _pathway("Assessment & credential evidence", "Only persisted quiz attempts and certificate records are represented.", [
            {"icon": ":material/assignment:", "label": "Attempts", "status": f"{attempts} stored" if attempts else "None yet", "state": "complete" if attempts else "waiting", "detail": "Durable scored assessment attempts."},
            {"icon": ":material/task_alt:", "label": "Pass evidence", "status": f"{passed} passed" if passed else "Not recorded", "state": "complete" if passed else ("attention" if attempts else "waiting"), "detail": f"Best available evidence across {attempts} attempt{'s' if attempts != 1 else ''}."},
            {"icon": ":material/analytics:", "label": "Average score", "status": f"{float(assessment.get('average_score') or 0):.1f}%" if attempts else "No score", "state": "active" if attempts else "waiting", "detail": "Calculated from stored attempt scores."},
            {"icon": ":material/verified:", "label": "Credentials", "status": f"{active} active" if active else "None active", "state": "complete" if active else ("attention" if rows else "waiting"), "detail": f"{len(rows) - active} revoked · {len(rows)} total issued."},
        ])
        if rows:
            display = [{**row, "status": "Revoked" if row["revoked"] else "Active"} for row in rows]
            st.dataframe(display, hide_index=True, width="stretch", column_config={
                "course": st.column_config.TextColumn("Course", pinned=True),
                "issued_at": st.column_config.DatetimeColumn("Issued", format="MMM DD, YYYY"),
                "revoked": None,
                "status": st.column_config.TextColumn("Status"),
                "verification_code": st.column_config.TextColumn("Verification code"),
            })
            st.caption("Verification codes identify durable local credential records; validity also depends on the current revocation state.")
        else:
            _empty("No credentials issued", "Complete every lecture and pass a quiz to qualify.", ":material/workspace_premium:")
    with safety:
        courses = _catalog(p, actor, iid)
        targets = {f"course:{x['id']}": x for x in courses}
        policy, report = st.columns([.8, 1.2], gap="medium")
        with policy.container(border=True):
            st.markdown(":material/shield: **Safety boundary**")
            st.badge("Human review required", color="orange")
            st.markdown("- Reports are durable and reporter-scoped\n- Submission does not auto-remove content\n- Do not include sensitive personal data\n- Emergency issues need the appropriate local service")
            st.caption("Scientific, laboratory, copyright, accessibility and minor-safety concerns can be reported.")
        with report.container(border=True):
            st.subheader("Report course content")
            if not targets:
                empty_state("No published learning content", "There is no permission-visible course content available for this report.", icon="▷", action_hint="Publish a reviewed lecture, assessment or course resource.")
            else:
                with st.form("academy-report"):
                    target_key = st.selectbox("Course", list(targets), format_func=lambda key: targets[key]["title"])
                    category = st.selectbox("Concern", ["Scientific misinformation", "Dangerous laboratory instruction", "Copyright or licensing", "Harassment or minor safety", "Accessibility", "Other"])
                    detail = st.text_area("Details", placeholder="Describe the concern without sensitive personal data.")
                    submit = st.form_submit_button("Submit moderation report", type="primary", icon=":material/report:", width="stretch")
                if submit:
                    reason = category if not detail.strip() else f"{category}: {detail.strip()}"
                    if run(lambda: p.report_content(actor, "course", targets[target_key]["id"], reason)):
                        st.success("Report stored in the moderation queue.")
        reports = _all(p, "SELECT target_type,reason,state,created_at FROM content_reports WHERE reporter_id=? ORDER BY created_at DESC LIMIT 25", (actor,))
        if reports:
            st.subheader("My recent reports")
            st.dataframe(reports, hide_index=True, width="stretch", column_config={
                "target_type": st.column_config.TextColumn("Content type"),
                "reason": st.column_config.TextColumn("Concern", pinned=True),
                "state": st.column_config.TextColumn("Review state"),
                "created_at": st.column_config.DatetimeColumn("Submitted", format="MMM DD, YYYY"),
            })

def render_academy_workspace(
    p: Any,
    actor: str,
    institution_id: str,
    run: RunAction,
    *,
    root: Path | None = None,
) -> None:
    """Render a role-aware Academy and Lecture Studio over durable platform records."""
    roles = _roles(p, actor, institution_id)
    if not roles:
        st.error("An active institution membership is required.")
        return
    institution = _institution(p, institution_id)
    with st.container(border=True):
        title, identity = st.columns([3, 1], vertical_alignment="center")
        with title:
            st.markdown(":material/school: **BIOINTEL EDUCATION**")
            st.subheader("Academy & Lecture Studio", anchor=False)
            st.caption("Build rights-aware scientific courses, teach with evidence and turn learner progress into verifiable completion.")
        with identity:
            st.badge(institution["name"], icon=":material/account_balance:", color="blue")
            st.badge(actor, icon=":material/person:", color="gray")
            st.caption(f"{len(roles)} active role{'s' if len(roles) != 1 else ''}")
    project_root = Path(root).resolve() if root else Path.cwd().resolve()
    options = [
        "Overview",
        "Educator studio",
        "Learn",
        "Lecture intelligence",
        "Shiro tutor",
        "Live classes",
        "Credentials & safety",
    ]
    selector_key = "academy_workspace_view"
    view = st.selectbox(
        "Workspace",
        options,
        key=selector_key,
        label_visibility="collapsed",
        width="stretch",
    ) or "Overview"
    if view == "Educator studio":
        _studio(p, actor, institution_id, roles, run, project_root)
    elif view == "Learn":
        _learn(p, actor, institution_id, run, project_root)
    elif view == "Lecture intelligence":
        from .phase7_ui import render_academy_intelligence_workspace

        render_academy_intelligence_workspace(project_root, p, actor, institution_id)
    elif view == "Shiro tutor":
        from .intelligence_ui import render_academy_shiro_tutor

        render_academy_shiro_tutor(p, project_root, actor, institution_id)
    elif view == "Live classes":
        _live(p, actor, institution_id, run)
    elif view == "Credentials & safety":
        _credentials_safety(p, actor, institution_id, run)
    else:
        _overview(p, actor, institution_id, roles, run)








