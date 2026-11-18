"""BioIntel-branded UI for the local Education Suite."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ._streamlit_compat import st
from .education_suite import EducationSuiteError, EducationSuiteService
from .platform import ADMIN, STUDENT, TEACHER


def _is_teacher(roles: set[str]) -> bool:
    return bool(roles & (set(ADMIN) | set(TEACHER)))


def _is_student(roles: set[str]) -> bool:
    return bool(roles & set(STUDENT))


def _safe(action, success: str = ""):
    try:
        result = action()
    except EducationSuiteError as exc:
        st.error(str(exc), icon=":material/error:")
        return None
    except Exception as exc:
        st.error(f"Education Suite action failed: {exc}", icon=":material/error:")
        return None
    if success:
        st.toast(success, icon=":material/check_circle:")
    return result


def _subject_options(subjects: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    options = {"": "All subjects / general workspace"}
    for subject in subjects:
        sid = str(subject.get("id", ""))
        if sid:
            options[sid] = f"{subject.get('code', 'SUB')} · {subject.get('name', 'Subject')}"
    return options


def _json_field(label: str, value: Any, key: str, help_text: str = "") -> Any:
    raw = st.text_area(label, value=json.dumps(value, indent=2, ensure_ascii=False), key=key, help=help_text, height=150)
    try:
        return json.loads(raw)
    except Exception:
        st.warning("JSON is not valid yet.", icon=":material/warning:")
        return None


def _render_whiteboard() -> None:
    st.subheader("BioIntel Whiteboard", anchor=False)
    st.caption("Browser-local drawing board. Export PNG to preserve a board or attach it to classroom notes.")
    try:
        import streamlit.components.v1 as components
    except Exception:
        st.info("Whiteboard rendering requires the packaged Streamlit runtime.", icon=":material/draw:")
        return
    board = r"""
    <div style="font-family:system-ui;color:#e5e7eb;background:linear-gradient(135deg,#0f172a,#111827);padding:12px;border-radius:16px;border:1px solid rgba(148,163,184,.25)">
      <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px;flex-wrap:wrap">
        <strong>BioIntel Whiteboard</strong>
        <label>Pen <input id="pen" type="color" value="#38bdf8"></label>
        <label>Width <input id="width" type="range" min="1" max="18" value="4"></label>
        <button onclick="eraser()">Eraser</button><button onclick="clearBoard()">Clear</button>
        <button onclick="saveBoard()">Export PNG</button>
      </div>
      <canvas id="board" width="1200" height="520" style="width:100%;height:520px;background:#fff;border-radius:12px;touch-action:none"></canvas>
    </div>
    <script>
      const canvas=document.getElementById('board'),ctx=canvas.getContext('2d'); let drawing=false,last=null,erase=false;
      function point(e){const r=canvas.getBoundingClientRect();const x=(e.clientX-r.left)*(canvas.width/r.width);const y=(e.clientY-r.top)*(canvas.height/r.height);return [x,y]}
      canvas.addEventListener('pointerdown',e=>{drawing=true;last=point(e);canvas.setPointerCapture(e.pointerId)});
      canvas.addEventListener('pointermove',e=>{if(!drawing)return;const p=point(e);ctx.beginPath();ctx.moveTo(...last);ctx.lineTo(...p);ctx.lineCap='round';ctx.lineJoin='round';ctx.lineWidth=document.getElementById('width').value;ctx.strokeStyle=erase?'#ffffff':document.getElementById('pen').value;ctx.stroke();last=p});
      canvas.addEventListener('pointerup',()=>drawing=false);canvas.addEventListener('pointercancel',()=>drawing=false);
      function eraser(){erase=!erase;event.target.textContent=erase?'Pen mode':'Eraser'}
      function clearBoard(){ctx.clearRect(0,0,canvas.width,canvas.height)}
      function saveBoard(){const a=document.createElement('a');a.download='BioIntel-Whiteboard.png';a.href=canvas.toDataURL('image/png');a.click()}
    </script>
    """
    components.html(board, height=610, scrolling=False)


def _lesson_builder(service: EducationSuiteService, actor: str, institution_id: str, subject_id: str, teacher: bool) -> None:
    st.subheader("Interactive Lesson Studio", anchor=False)
    st.caption("Build local lessons with text, MCQ, multi-select, true/false, short-answer, numeric, checklist and link activities.")
    draft_key = f"biointel_lesson_draft::{institution_id}::{actor}"
    st.session_state.setdefault(draft_key, [])
    if teacher:
        with st.expander("Build a lesson", expanded=not bool(st.session_state[draft_key])):
            activity_type = st.selectbox("Activity type", ["text", "mcq", "multi_select", "true_false", "short", "numeric", "checklist", "link"], key="suite-lesson-type")
            prompt = st.text_area("Activity prompt/content", key="suite-lesson-prompt")
            options_text = st.text_area("Options (one per line)", key="suite-lesson-options", disabled=activity_type not in {"mcq", "multi_select", "checklist"})
            answer_text = st.text_input("Correct answer", key="suite-lesson-answer", disabled=activity_type in {"text", "link", "checklist"}, help="For multi-select, separate values with |. Numeric answers accept a number.")
            points = st.number_input("Points", min_value=0.0, value=0.0 if activity_type in {"text", "link", "checklist"} else 1.0, step=0.5, key="suite-lesson-points")
            if st.button("Add activity to draft", icon=":material/add:", key="suite-add-activity"):
                if not prompt.strip():
                    st.error("Activity prompt/content is required.")
                else:
                    options = [line.strip() for line in options_text.splitlines() if line.strip()]
                    if activity_type == "multi_select":
                        answer: Any = [item.strip() for item in answer_text.split("|") if item.strip()]
                    elif activity_type == "numeric":
                        try:
                            answer = float(answer_text)
                        except ValueError:
                            st.error("Numeric activity requires a numeric answer.")
                            answer = None
                    elif activity_type in {"text", "link", "checklist"}:
                        answer = None
                    else:
                        answer = answer_text
                    if activity_type != "numeric" or answer is not None:
                        st.session_state[draft_key].append({"type": activity_type, "prompt": prompt.strip(), "options": options, "answer": answer, "points": points})
                        st.rerun()
        draft = list(st.session_state[draft_key])
        if draft:
            st.dataframe([{"#": index + 1, "Type": item["type"], "Prompt": item["prompt"][:100], "Points": item.get("points", 0)} for index, item in enumerate(draft)], hide_index=True, width="stretch")
            with st.form("suite-save-lesson"):
                title = st.text_input("Lesson title")
                description = st.text_area("Lesson description")
                publish = st.checkbox("Publish immediately", value=True)
                save = st.form_submit_button("Save BioIntel lesson", type="primary", icon=":material/publish:")
            if save:
                result = _safe(lambda: service.create_lesson(institution_id, subject_id, title, description, draft, actor, publish), "Lesson saved")
                if result:
                    st.session_state[draft_key] = []
                    st.rerun()
            if st.button("Clear lesson draft", icon=":material/delete_sweep:", key="suite-clear-lesson"):
                st.session_state[draft_key] = []
                st.rerun()

    lessons = service.list_lessons(institution_id, subject_id, include_drafts=teacher)
    if not lessons:
        st.info("No lessons are available in this scope.", icon=":material/menu_book:")
        return
    labels = {item["id"]: f"{item['title']} · {item['state']} · {len(item['activities'])} activities" for item in lessons}
    lesson_id = st.selectbox("Open lesson", list(labels), format_func=labels.get, key="suite-open-lesson")
    lesson = next(item for item in lessons if item["id"] == lesson_id)
    with st.container(border=True):
        st.markdown(f"### {lesson['title']}")
        st.caption(lesson.get("description", ""))
        if teacher and lesson["state"] != "published" and st.button("Publish lesson", key="suite-publish-lesson", icon=":material/publish:"):
            if _safe(lambda: service.publish_lesson(lesson_id, actor), "Lesson published"):
                st.rerun()
        responses: dict[str, Any] = {}
        for index, activity in enumerate(lesson["activities"], 1):
            kind = activity.get("type", "text")
            prompt = str(activity.get("prompt", ""))
            st.markdown(f"**{index}. {html.escape(prompt)}**" if kind not in {"text", "link"} else f"#### {html.escape(prompt)}")
            key = f"suite-lesson-response-{lesson_id}-{activity['id']}"
            if kind == "text":
                st.markdown(prompt)
            elif kind == "link":
                st.link_button("Open lesson resource", prompt, icon=":material/open_in_new:")
            elif kind == "mcq":
                responses[activity["id"]] = st.radio("Choose one", activity.get("options", []), key=key, label_visibility="collapsed")
            elif kind == "multi_select":
                responses[activity["id"]] = st.multiselect("Choose all that apply", activity.get("options", []), key=key, label_visibility="collapsed")
            elif kind == "true_false":
                responses[activity["id"]] = st.radio("True or false", ["True", "False"], key=key, label_visibility="collapsed")
            elif kind == "short":
                responses[activity["id"]] = st.text_input("Answer", key=key, label_visibility="collapsed")
            elif kind == "numeric":
                responses[activity["id"]] = st.number_input("Numeric answer", key=key, label_visibility="collapsed")
            elif kind == "checklist":
                responses[activity["id"]] = [option for option in activity.get("options", []) if st.checkbox(option, key=f"{key}-{option}")]
        if lesson["state"] == "published" and st.button("Complete lesson", type="primary", icon=":material/task_alt:", key="suite-complete-lesson"):
            result = _safe(lambda: service.submit_lesson_attempt(lesson_id, actor, responses))
            if result:
                st.success(f"Lesson completed · score {result['score']:.1f}/{result['max_score']:.1f}")


def _notes_workspace(service: EducationSuiteService, actor: str, institution_id: str, subject_id: str) -> None:
    st.subheader("Collaborative Notes", anchor=False)
    st.caption("Versioned local notes with revision history and comments. Multiple users can contribute through the shared institution database.")
    notes = service.list_notes(institution_id, subject_id)
    options = {"": "Create new note", **{item["id"]: f"{item['title']} · revision {item['revision']}" for item in notes}}
    note_id = st.selectbox("Note", list(options), format_func=options.get, key="suite-note-select")
    current = service.get_note(note_id) if note_id else None
    with st.form("suite-note-editor"):
        title = st.text_input("Title", value=current["title"] if current else "")
        body = st.text_area("Shared note", value=current["body"] if current else "", height=260)
        submitted = st.form_submit_button("Save revision", type="primary", icon=":material/save:")
    if submitted:
        if _safe(lambda: service.save_note(institution_id, subject_id, title, body, actor, note_id), "Note revision saved"):
            st.rerun()
    if current:
        with st.expander("Revision history"):
            st.dataframe([{"Revision": item["revision"], "Editor": item["editor_id"], "Saved": item["created_at"]} for item in current["revisions"]], hide_index=True, width="stretch")
        with st.form("suite-note-comment"):
            comment = st.text_input("Add comment")
            add = st.form_submit_button("Comment", icon=":material/add_comment:")
        if add and _safe(lambda: service.add_note_comment(note_id, actor, comment), "Comment added"):
            st.rerun()
        if current["comments"]:
            st.dataframe([{"Author": item["author_id"], "Comment": item["body"], "Time": item["created_at"]} for item in current["comments"]], hide_index=True, width="stretch")


def _assessment_workspace(service: EducationSuiteService, actor: str, institution_id: str, subject_id: str, teacher: bool) -> None:
    st.subheader("Smart Assessment Engine", anchor=False)
    if teacher:
        with st.expander("Add question to bank"):
            with st.form("suite-question-form"):
                qtype = st.selectbox("Question type", ["mcq", "multi_select", "true_false", "short", "numeric"])
                prompt = st.text_area("Question")
                options_text = st.text_area("Options (one per line)")
                answer_text = st.text_input("Answer", help="Multi-select: separate answers with |. Short answer: separate accepted forms with |.")
                points = st.number_input("Points", min_value=0.5, value=1.0, step=0.5)
                explanation = st.text_area("Feedback/explanation")
                create = st.form_submit_button("Add question", type="primary")
            if create:
                options = [item.strip() for item in options_text.splitlines() if item.strip()]
                if qtype in {"multi_select", "short"}:
                    answer: Any = [item.strip() for item in answer_text.split("|") if item.strip()]
                elif qtype == "numeric":
                    try:
                        answer = float(answer_text)
                    except ValueError:
                        answer = None
                        st.error("Numeric question requires a numeric answer.")
                else:
                    answer = answer_text
                if answer is not None and _safe(lambda: service.create_question(institution_id, subject_id, qtype, prompt, answer, actor, options, explanation, points), "Question added"):
                    st.rerun()
    questions = service.list_questions(institution_id, subject_id)
    if questions:
        st.dataframe([{"ID": item["id"], "Type": item["question_type"], "Question": item["prompt"], "Points": item["points"]} for item in questions], hide_index=True, width="stretch")
    if teacher and questions:
        with st.expander("Create assessment"):
            with st.form("suite-assessment-create"):
                title = st.text_input("Assessment title")
                instructions = st.text_area("Instructions")
                qmap = {item["id"]: f"{item['question_type']} · {item['prompt'][:100]}" for item in questions}
                selected = st.multiselect("Question bank", list(qmap), format_func=qmap.get)
                publish = st.checkbox("Publish immediately", value=True)
                create = st.form_submit_button("Create assessment", type="primary")
            if create and _safe(lambda: service.create_assessment(institution_id, subject_id, title, selected, actor, instructions, {"randomize": True}, publish), "Assessment created"):
                st.rerun()
    assessments = service.list_assessments(institution_id, subject_id, published_only=not teacher)
    if not assessments:
        st.info("No assessments are available.", icon=":material/quiz:")
        return
    amap = {item["id"]: f"{item['title']} · {item['state']} · {item['question_count']} questions" for item in assessments}
    assessment_id = st.selectbox("Assessment", list(amap), format_func=amap.get, key="suite-assessment-select")
    assessment = service.get_assessment(assessment_id)
    if assessment["state"] != "published":
        st.info("Draft assessment. Publish it from the assessment creator before students attempt it.")
        return
    responses: dict[str, Any] = {}
    for index, question in enumerate(assessment["questions"], 1):
        st.markdown(f"**{index}. {question['prompt']}** · {question['points']} point(s)")
        key = f"suite-assessment-{assessment_id}-{question['id']}"
        qtype = question["question_type"]
        if qtype == "mcq":
            responses[question["id"]] = st.radio("Answer", question["options"], key=key, label_visibility="collapsed")
        elif qtype == "multi_select":
            responses[question["id"]] = st.multiselect("Answer", question["options"], key=key, label_visibility="collapsed")
        elif qtype == "true_false":
            responses[question["id"]] = st.radio("Answer", ["True", "False"], key=key, label_visibility="collapsed")
        elif qtype == "numeric":
            responses[question["id"]] = st.number_input("Answer", key=key, label_visibility="collapsed")
        else:
            responses[question["id"]] = st.text_input("Answer", key=key, label_visibility="collapsed")
    if st.button("Submit assessment", type="primary", icon=":material/quiz:", key="suite-assessment-submit"):
        result = _safe(lambda: service.submit_assessment(assessment_id, actor, responses))
        if result:
            st.success(f"Assessment submitted · {result['score']:.1f}/{result['max_score']:.1f}")
            st.json(result["feedback"], expanded=False)


def _coding_workspace(service: EducationSuiteService, actor: str, institution_id: str, subject_id: str, teacher: bool) -> None:
    st.subheader("Browser Coding & Notebook Lab", anchor=False)
    st.warning("The local runner blocks high-risk imports/functions and enforces a timeout, but untrusted institutional exams should use the optional isolated BioIntel Code Sandbox connector.", icon=":material/security:")
    code = st.text_area("Python code", value="print('BioIntel classroom ready')", height=220, key="suite-code-playground")
    stdin_text = st.text_area("Standard input", key="suite-code-stdin")
    if st.button("Run locally", icon=":material/play_arrow:", key="suite-run-code"):
        result = _safe(lambda: service.run_python(code, stdin_text))
        if result:
            st.code(result.stdout or result.stderr or "(no output)")
            st.caption(f"Return code {result.returncode} · {'timed out' if result.timed_out else 'completed'}")
    if teacher:
        with st.expander("Create auto-graded code task"):
            with st.form("suite-code-task-create"):
                title = st.text_input("Task title")
                prompt = st.text_area("Task prompt")
                tests = _json_field("Tests JSON", [{"stdin": "2\n3\n", "expected_stdout": "5", "timeout": 4}], "suite-code-tests")
                create = st.form_submit_button("Create task", type="primary")
            if create and isinstance(tests, list) and _safe(lambda: service.create_code_task(institution_id, subject_id, title, prompt, tests, actor), "Code task created"):
                st.rerun()
    tasks = service.list_code_tasks(institution_id, subject_id)
    if tasks:
        tmap = {item["id"]: item["title"] for item in tasks}
        task_id = st.selectbox("Auto-graded task", list(tmap), format_func=tmap.get, key="suite-code-task")
        task = next(item for item in tasks if item["id"] == task_id)
        st.info(task["prompt"])
        submission = st.text_area("Submission", height=220, key="suite-code-submission")
        if st.button("Submit code", type="primary", key="suite-code-submit"):
            result = _safe(lambda: service.submit_code(task_id, actor, submission))
            if result:
                st.metric("Score", f"{result['score']:.1f}%")
                st.dataframe(result["tests"], hide_index=True, width="stretch")
    with st.expander("Notebook grader"):
        notebook = st.file_uploader("Upload .ipynb", type=["ipynb"], key="suite-notebook-upload")
        tests = _json_field("Notebook tests JSON", [{"stdin": "", "expected_stdout": "BioIntel"}], "suite-notebook-tests")
        if st.button("Grade notebook", key="suite-grade-notebook", disabled=not notebook):
            result = _safe(lambda: service.grade_notebook(notebook.getvalue(), tests or []))
            if result:
                st.json(result)
    with st.expander("Code integrity review"):
        left = st.text_area("Submission A", key="suite-sim-a")
        right = st.text_area("Submission B", key="suite-sim-b")
        if st.button("Compare similarity", key="suite-sim-compare"):
            st.json(service.code_similarity(left, right))


def _qa_workspace(service: EducationSuiteService, actor: str, institution_id: str, subject_id: str) -> None:
    st.subheader("Classroom Q&A", anchor=False)
    with st.form("suite-qa-create"):
        title = st.text_input("Question title")
        body = st.text_area("Question details")
        tags = st.text_input("Tags (comma separated)")
        create = st.form_submit_button("Post question", type="primary", icon=":material/help:")
    if create and _safe(lambda: service.create_qa_question(institution_id, subject_id, title, body, actor, [item.strip() for item in tags.split(",") if item.strip()]), "Question posted"):
        st.rerun()
    search = st.text_input("Search Q&A", key="suite-qa-search")
    questions = service.list_qa_questions(institution_id, subject_id, search)
    if not questions:
        st.info("No matching questions.", icon=":material/forum:")
        return
    qmap = {item["id"]: f"{item['title']} · {item['answer_count']} answers · {item['state']}" for item in questions}
    question_id = st.selectbox("Open thread", list(qmap), format_func=qmap.get, key="suite-qa-thread")
    thread = service.get_qa_question(question_id)
    st.markdown(f"### {thread['title']}")
    st.write(thread["body"])
    st.caption(f"Asked by {thread['author_id']} · {', '.join(thread['tags']) or 'no tags'}")
    for answer in thread["answers"]:
        accepted = answer["id"] == thread["accepted_answer_id"]
        with st.container(border=True):
            st.markdown(("✅ **Accepted answer**\n\n" if accepted else "") + answer["body"])
            st.caption(f"{answer['author_id']} · votes {answer['votes']}")
            if actor == thread["author_id"] and not accepted and st.button("Accept", key=f"suite-accept-{answer['id']}"):
                if _safe(lambda: service.accept_qa_answer(question_id, answer["id"], actor), "Answer accepted"):
                    st.rerun()
    with st.form("suite-qa-answer"):
        answer_body = st.text_area("Your answer")
        answer = st.form_submit_button("Post answer", type="primary")
    if answer and _safe(lambda: service.answer_qa_question(question_id, answer_body, actor), "Answer posted"):
        st.rerun()


def _library_search_workspace(service: EducationSuiteService, actor: str, institution_id: str, subject_id: str) -> None:
    st.subheader("Offline Library & Education Search", anchor=False)
    upload = st.file_uploader("Add offline learning resource", key="suite-resource-upload")
    title = st.text_input("Resource title", key="suite-resource-title")
    description = st.text_area("Resource description", key="suite-resource-description")
    if st.button("Add to offline library", type="primary", key="suite-resource-add", disabled=not upload):
        result = _safe(lambda: service.add_offline_resource(institution_id, subject_id, title or upload.name, description, upload.getvalue(), upload.name, actor, upload.type or "application/octet-stream"), "Resource stored locally")
        if result:
            st.rerun()
    resources = service.list_offline_resources(institution_id, subject_id)
    if resources:
        st.dataframe([{"Title": item["title"], "File": item["file_name"], "Size": item["size_bytes"], "SHA-256": item["sha256"][:16] + "…"} for item in resources], hide_index=True, width="stretch")
    query = st.text_input("Search lessons, notes, question bank, Q&A and resources", key="suite-unified-search")
    if query:
        results = service.search(institution_id, query)
        st.dataframe(results, hide_index=True, width="stretch") if results else st.info("No matching education records.")


def _services_workspace(service: EducationSuiteService, actor: str, institution_id: str, teacher: bool) -> None:
    st.subheader("Education Services & Institutional Connectors", anchor=False)
    st.caption("Heavy multi-user systems remain isolated services. BioIntel stores only institution-approved endpoints and health state; no external product branding is exposed in the normal classroom UI.")
    catalog = [
        ("live_class", "BioIntel Live Classroom", "Video class, screen sharing, chat and moderation"),
        ("virtual_classroom", "BioIntel Virtual Classroom Pro", "Breakouts, polling, recordings and advanced teaching controls"),
        ("whiteboard", "BioIntel Collaborative Board Service", "Multi-user synchronized whiteboards"),
        ("collaborative_notes", "BioIntel Real-Time Notes Service", "Simultaneous note editing and revision playback"),
        ("multi_user_lab", "BioIntel Multi-User Scientific Lab", "Institution-managed notebook servers"),
        ("assessment_worker", "BioIntel Assessment Worker", "Large randomized assessments and grading workers"),
        ("code_sandbox", "BioIntel Code Sandbox", "Isolated untrusted-code execution"),
        ("learning_record_store", "BioIntel Learning Record Store", "Institution-wide activity statement storage"),
        ("education_search", "BioIntel Education Search Service", "Fast searchable course and opportunity index"),
        ("lms_bridge", "BioIntel LMS Bridge", "Roster, assignment and grade interchange"),
        ("offline_library_sync", "BioIntel Offline Library Sync", "Low-connectivity content distribution"),
    ]
    existing = {item["connector_type"]: item for item in service.list_connectors(institution_id)}
    for connector_type, display_name, description in catalog:
        item = existing.get(connector_type, {})
        with st.expander(display_name, expanded=False):
            st.caption(description)
            endpoint = st.text_input("Endpoint", value=item.get("endpoint", ""), key=f"suite-connector-endpoint-{connector_type}", placeholder="https://institution-service.example")
            enabled = st.checkbox("Enabled for this institution", value=bool(item.get("enabled", 0)), key=f"suite-connector-enable-{connector_type}")
            cols = st.columns(2)
            if cols[0].button("Save configuration", key=f"suite-connector-save-{connector_type}", disabled=not teacher):
                if _safe(lambda: service.configure_connector(institution_id, connector_type, display_name, endpoint, actor, enabled), "Connector saved"):
                    st.rerun()
            if cols[1].button("Check health", key=f"suite-connector-health-{connector_type}"):
                health = service.connector_health(endpoint)
                (st.success if health["ok"] else st.warning)(f"{health['status']} · {health['detail']}")
            if endpoint:
                st.link_button(f"Open {display_name}", endpoint, icon=":material/open_in_new:")


def _analytics_workspace(service: EducationSuiteService, actor: str, institution_id: str, teacher: bool) -> None:
    st.subheader("Learning Analytics & Portable Records", anchor=False)
    summary = service.analytics_summary(institution_id, "" if teacher else actor)
    cols = st.columns(3)
    cols[0].metric("Learning events", summary["events"])
    cols[1].metric("Active learners", summary["actors"])
    cols[2].metric("Tracked objects", summary["objects"])
    if summary["by_type"]:
        st.dataframe(summary["by_type"], hide_index=True, width="stretch")
    statements = service.export_learning_records(institution_id)
    st.download_button("Export BioIntel learning records", json.dumps(statements, indent=2).encode("utf-8"), file_name="biointel-learning-records.json", mime="application/json", icon=":material/download:")


def render_classroom_suite(
    service: EducationSuiteService,
    actor: str,
    institution_id: str,
    roles: Iterable[str],
    subjects: Sequence[Mapping[str, Any]],
) -> None:
    """Render the unified Education Suite inside BioIntel Classroom."""
    role_set = set(roles)
    teacher = _is_teacher(role_set)
    options = _subject_options(subjects)
    subject_id = st.selectbox("Education Suite subject scope", list(options), format_func=options.get, key="suite-subject-scope")
    with st.container(border=True):
        st.markdown("### :material/auto_stories: BioIntel Education Suite")
        st.caption("Interactive learning, assessment, collaboration, coding, offline access, analytics and institutional connectors in one local-first classroom workspace.")
        badges = ["Local-first", "Institution scoped", "BioIntel identity", "Optional isolated services"]
        with st.container(horizontal=True):
            for label in badges:
                st.badge(label, color="blue")
    tabs = st.tabs(["Lessons", "Notes & board", "Assessments", "Coding lab", "Q&A", "Library & search", "Analytics", "Services"])
    with tabs[0]:
        _lesson_builder(service, actor, institution_id, subject_id, teacher)
    with tabs[1]:
        note_tab, board_tab = st.tabs(["Versioned notes", "Whiteboard"])
        with note_tab:
            _notes_workspace(service, actor, institution_id, subject_id)
        with board_tab:
            _render_whiteboard()
    with tabs[2]:
        _assessment_workspace(service, actor, institution_id, subject_id, teacher)
    with tabs[3]:
        _coding_workspace(service, actor, institution_id, subject_id, teacher)
    with tabs[4]:
        _qa_workspace(service, actor, institution_id, subject_id)
    with tabs[5]:
        _library_search_workspace(service, actor, institution_id, subject_id)
    with tabs[6]:
        _analytics_workspace(service, actor, institution_id, teacher)
    with tabs[7]:
        _services_workspace(service, actor, institution_id, teacher)


def render_career_application_studio(service: EducationSuiteService, owner_id: str, institution_id: str = "personal") -> None:
    """Render résumé, application-document and credential tools inside Career Hub."""
    st.subheader("BioIntel Application Studio", anchor=False)
    st.caption("Create role-specific résumés, statements and evidence-backed credentials without sending private application data to a cloud service.")
    resume_tab, docs_tab, credentials_tab, interview_tab = st.tabs(["Résumé builder", "Application documents", "Credentials", "Interview preparation"])
    with resume_tab:
        resumes = service.list_resumes(owner_id)
        rmap = {"": "Create new résumé", **{item["id"]: f"{item['name']} · {item['headline']}" for item in resumes}}
        resume_id = st.selectbox("Résumé", list(rmap), format_func=rmap.get, key="suite-career-resume-select")
        current = next((item for item in resumes if item["id"] == resume_id), None)
        profile = current["profile"] if current else {}
        with st.form("suite-career-resume-form"):
            name = st.text_input("Name", value=current["name"] if current else "")
            headline = st.text_input("Professional headline", value=current["headline"] if current else "")
            summary = st.text_area("Summary", value=str(profile.get("summary", "")))
            education = st.text_area("Education (one item per line)", value="\n".join(profile.get("education", [])))
            skills = st.text_area("Skills (one item per line)", value="\n".join(profile.get("skills", [])))
            projects = st.text_area("Projects (one item per line)", value="\n".join(profile.get("projects", [])))
            experience = st.text_area("Experience (one item per line)", value="\n".join(profile.get("experience", [])))
            publications = st.text_area("Publications (one item per line)", value="\n".join(profile.get("publications", [])))
            save = st.form_submit_button("Save résumé", type="primary")
        if save:
            payload = {"summary": summary, "education": [x for x in education.splitlines() if x.strip()], "skills": [x for x in skills.splitlines() if x.strip()], "projects": [x for x in projects.splitlines() if x.strip()], "experience": [x for x in experience.splitlines() if x.strip()], "publications": [x for x in publications.splitlines() if x.strip()]}
            if _safe(lambda: service.save_resume(owner_id, name, headline, payload, resume_id), "Résumé saved"):
                st.rerun()
        if current:
            markdown = service.resume_markdown(current)
            st.download_button("Download résumé Markdown", markdown.encode("utf-8"), file_name="BioIntel-Resume.md", mime="text/markdown")
            st.markdown(markdown)
    with docs_tab:
        docs = service.list_application_documents(owner_id)
        with st.form("suite-career-doc-form"):
            dtype = st.selectbox("Document type", ["Statement of purpose", "Cover letter", "Research statement", "Scholarship essay", "Interview notes", "Reference brief"])
            title = st.text_input("Document title")
            opportunity = st.text_input("Opportunity ID/reference")
            body = st.text_area("Document", height=320)
            save = st.form_submit_button("Save document", type="primary")
        if save and _safe(lambda: service.save_application_document(owner_id, dtype, title, body, opportunity), "Application document saved"):
            st.rerun()
        if docs:
            st.dataframe([{"Type": item["document_type"], "Title": item["title"], "Opportunity": item["opportunity_id"], "Updated": item["updated_at"]} for item in docs], hide_index=True, width="stretch")
    with credentials_tab:
        credentials = service.list_credentials(institution_id, owner_id)
        with st.form("suite-career-credential-form"):
            title = st.text_input("Credential/badge title")
            ctype = st.selectbox("Type", ["Course completion", "Skill badge", "Internship", "Research project", "Publication", "Laboratory competency", "Award"])
            evidence = st.text_input("Evidence link or local evidence reference")
            issuer = st.text_input("Issuer", value="BioIntel Education")
            issue = st.form_submit_button("Issue local credential", type="primary")
        if issue and _safe(lambda: service.issue_credential(institution_id, owner_id, title, ctype, evidence, issuer), "Credential issued"):
            st.rerun()
        if credentials:
            st.dataframe([{"Credential": item["title"], "Type": item["credential_type"], "Issuer": item["issuer"], "Evidence": item["evidence"], "Issued": item["issued_at"]} for item in credentials], hide_index=True, width="stretch")
    with interview_tab:
        role = st.text_input("Target role/program", key="suite-interview-role")
        evidence = st.text_area("Your strongest evidence", key="suite-interview-evidence", placeholder="Projects, lab work, publications, leadership, measurable outcomes")
        if st.button("Build interview practice set", key="suite-interview-build", type="primary"):
            prompts = [
                f"Why are you a strong fit for {role or 'this opportunity'}?",
                "Describe a scientific or technical problem you solved and how you validated the result.",
                "Explain one project to a non-specialist without losing scientific accuracy.",
                "Describe a setback, what changed in your approach and what evidence showed improvement.",
                "What would you aim to learn or deliver in the first 90 days?",
            ]
            st.session_state["suite-interview-prompts"] = prompts
        for index, prompt in enumerate(st.session_state.get("suite-interview-prompts", []), 1):
            st.text_area(f"{index}. {prompt}", key=f"suite-interview-answer-{index}")
        if evidence:
            st.info("Use specific evidence, measurable outcomes and honest limitations. Do not claim qualifications or results you cannot verify.")


__all__ = ["render_career_application_studio", "render_classroom_suite"]
