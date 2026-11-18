from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ._streamlit_compat import st
from .experience import render_app_header, render_app_navigation, render_role_snapshot, render_workspace_context
from .phase11 import ADMIN_ROLES, TEACHER_ROLES
from .phase14 import BLOOM_LEVELS, EVIDENCE_TYPES, EducationPhase14Service
from .ui import _actor, _demo_controls, _identity_input, _institution, _page_platform, _run
from biointel.ui.frontend_v10 import empty_state, kpi_grid, section_header


def _roles(platform: Any, actor: str, institution_id: str) -> set[str]:
    return {str(row["role"]) for row in platform.membership(actor, institution_id)}


def _overview(service: EducationPhase14Service, actor: str, institution_id: str) -> None:
    posture = _run(lambda: service.phase14_posture(actor, institution_id)) or {}
    counts = posture.get("counts", {})
    kpi_grid([
        (":material/target:", "Learning outcomes", counts.get("outcomes", 0), "Course, program and institution outcomes"),
        (":material/verified:", "Approved evidence", counts.get("approved_evidence", 0), "Independently reviewed evidence"),
        (":material/analytics:", "Psychometric runs", counts.get("psychometric_runs", 0), "Classical test-theory evidence"),
        (":material/volunteer_activism:", "Open support cases", counts.get("open_interventions", 0), "Human-reviewed learner support"),
    ])
    st.markdown(
        """
        <div class="edu-platform-grid">
          <article class="edu-module-card"><div class="edu-kicker">QUALITY EVIDENCE</div><h3>Outcome mapping and attainment</h3><p>Map assessments to learning outcomes, approve evidence independently, calculate bounded attainment and preserve improvement actions without claiming external accreditation.</p></article>
          <article class="edu-module-card"><div class="edu-kicker">ASSESSMENT SCIENCE</div><h3>Psychometrics with sample warnings</h3><p>Difficulty, omission, discrimination, point-biserial and reliability metrics remain explainable and require expert interpretation.</p></article>
          <article class="edu-module-card"><div class="edu-kicker">LEARNER SUPPORT</div><h3>Transparent intervention signals</h3><p>Attendance, assignments, mastery and examination evidence are combined through published thresholds; sensitive attributes and automatic penalties are excluded.</p></article>
        </div>
        """,
        unsafe_allow_html=True,
    )
    for boundary in posture.get("qualification_boundaries", []):
        st.info(boundary, icon=":material/fact_check:")


def _outcomes(service: EducationPhase14Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    section_header("Outcome and accreditation evidence matrix", "Create outcomes, map assessments, review evidence and calculate attainment with an explicit no-accreditation-claim boundary.", icon=":material/target:")
    subjects = platform._all("SELECT id,code,name FROM subjects WHERE institution_id=? AND state='active' ORDER BY code", (institution_id,))
    outcomes = platform._all("SELECT * FROM education_learning_outcomes WHERE institution_id=? AND state='active' ORDER BY outcome_level,code", (institution_id,))
    create_tab, map_tab, evidence_tab, matrix_tab = st.tabs(["Create outcomes", "Map assessments", "Evidence review", "Matrix & attainment"])
    with create_tab:
        if not roles & TEACHER_ROLES:
            empty_state("Academic staff access required", "Only academic staff can define learning outcomes.", icon="🎯")
        else:
            with st.form("phase14-create-outcome"):
                col1, col2, col3 = st.columns(3)
                code = col1.text_input("Outcome code", placeholder="CO1")
                level = col2.selectbox("Outcome level", ["course", "program", "institution"])
                bloom = col3.selectbox("Bloom level", sorted(BLOOM_LEVELS))
                title = st.text_input("Outcome title")
                description = st.text_area("Description")
                subject_id = st.selectbox("Subject", [""] + [row["id"] for row in subjects], format_func=lambda value: "Not subject-specific" if not value else next(f"{row['code']} · {row['name']}" for row in subjects if row["id"] == value))
                target = st.number_input("Target attainment %", 1.0, 100.0, 60.0)
                submitted = st.form_submit_button("Create governed outcome", type="primary", icon=":material/add_task:")
            if submitted:
                result = _run(lambda: service.create_learning_outcome(actor, institution_id, code=code, title=title, description=description, outcome_level=level, subject_id=subject_id or None, bloom_level=bloom, target_percent=target))
                if result:
                    st.success(f"Created {result['code']} · {result['title']}")
                    st.rerun()
        if outcomes:
            st.dataframe(outcomes, width="stretch", hide_index=True)
    with map_tab:
        if not outcomes:
            empty_state("No learning outcomes", "Create a learning outcome before mapping assessments.", icon="🧭")
        elif not roles & TEACHER_ROLES:
            empty_state("Academic staff access required", "Assessment mappings are governed academic records.", icon="🔒")
        else:
            outcome_id = st.selectbox("Learning outcome", [row["id"] for row in outcomes], format_func=lambda value: next(f"{row['code']} · {row['title']}" for row in outcomes if row["id"] == value), key="p14-map-outcome")
            selected = next(row for row in outcomes if row["id"] == outcome_id)
            mapping_type = st.selectbox("Assessment type", ["assignment", "exam_question", "rubric_criterion"], key="p14-map-type")
            options: list[dict[str, Any]] = []
            if mapping_type == "assignment":
                options = platform._all("SELECT id,title FROM assignments WHERE institution_id=? AND (? IS NULL OR subject_id=?) ORDER BY created_at DESC", (institution_id, selected.get("subject_id"), selected.get("subject_id")))
            elif mapping_type == "exam_question":
                options = platform._all("SELECT q.id,q.prompt title FROM education_exam_questions q JOIN examinations e ON e.id=q.exam_id WHERE q.institution_id=? AND (? IS NULL OR e.subject_id=?) ORDER BY q.created_at DESC", (institution_id, selected.get("subject_id"), selected.get("subject_id")))
            else:
                options = platform._all("SELECT c.id,c.title FROM education_rubric_criteria c JOIN education_assignment_rubrics r ON r.id=c.rubric_id JOIN assignments a ON a.id=r.assignment_id WHERE a.institution_id=? AND (? IS NULL OR a.subject_id=?) ORDER BY c.created_at DESC", (institution_id, selected.get("subject_id"), selected.get("subject_id")))
            if not options:
                empty_state("No compatible assessments", "Create an assessment in the selected subject first.", icon="📝")
            else:
                assessment_id = st.selectbox("Assessment", [row["id"] for row in options], format_func=lambda value: next(str(row["title"])[:120] for row in options if row["id"] == value), key="p14-assessment")
                weight = st.number_input("Mapping weight", 0.1, 100.0, 1.0)
                rationale = st.text_area("Mapping rationale")
                if st.button("Save assessment mapping", type="primary", icon=":material/link:"):
                    result = _run(lambda: service.map_assessment_to_outcome(actor, outcome_id, assessment_type=mapping_type, assessment_id=assessment_id, weight=weight, rationale=rationale))
                    if result:
                        st.success("Assessment mapping saved.")
            mappings = platform._all("SELECT * FROM education_outcome_assessment_mappings WHERE institution_id=? ORDER BY created_at DESC", (institution_id,))
            if mappings:
                st.dataframe(mappings, width="stretch", hide_index=True)
    with evidence_tab:
        if not outcomes:
            empty_state("No learning outcomes", "Create outcomes before submitting evidence.", icon="📚")
        else:
            outcome_id = st.selectbox("Outcome for evidence", [row["id"] for row in outcomes], format_func=lambda value: next(f"{row['code']} · {row['title']}" for row in outcomes if row["id"] == value), key="p14-evidence-outcome")
            if roles & TEACHER_ROLES:
                with st.form("phase14-evidence"):
                    evidence_type = st.selectbox("Evidence type", sorted(EVIDENCE_TYPES))
                    evidence_title = st.text_input("Evidence title")
                    target_type = st.text_input("Linked record type", placeholder="assignment, report, meeting…")
                    target_id = st.text_input("Linked record ID")
                    description = st.text_area("Evidence description")
                    evidence_submitted = st.form_submit_button("Submit for independent review", type="primary", icon=":material/upload_file:")
                if evidence_submitted:
                    result = _run(lambda: service.submit_outcome_evidence(actor, outcome_id, evidence_type=evidence_type, title=evidence_title, description=description, target_type=target_type, target_id=target_id))
                    if result:
                        st.success("Evidence submitted for independent review.")
                        st.rerun()
            evidence_rows = platform._all("SELECT * FROM education_outcome_evidence WHERE institution_id=? ORDER BY created_at DESC", (institution_id,))
            if evidence_rows:
                st.dataframe(evidence_rows, width="stretch", hide_index=True)
                if roles & ADMIN_ROLES:
                    pending = [row for row in evidence_rows if row["review_decision"] == "pending"]
                    if pending:
                        evidence_id = st.selectbox("Pending evidence", [row["id"] for row in pending], format_func=lambda value: next(row["title"] for row in pending if row["id"] == value))
                        decision = st.selectbox("Decision", ["approve", "request_changes", "reject"])
                        note = st.text_area("Review note")
                        if st.button("Record independent review", type="primary", icon=":material/verified:"):
                            result = _run(lambda: service.review_outcome_evidence(actor, evidence_id, decision=decision, note=note))
                            if result:
                                st.success(f"Evidence {result['review_decision']}.")
                                st.rerun()
            else:
                empty_state("No outcome evidence", "Submit the first outcome evidence record.", icon="🗂️")
    with matrix_tab:
        subject_filter = st.selectbox("Matrix subject", [""] + [row["id"] for row in subjects], format_func=lambda value: "All outcomes" if not value else next(f"{row['code']} · {row['name']}" for row in subjects if row["id"] == value), key="p14-matrix-subject")
        matrix = _run(lambda: service.accreditation_evidence_matrix(actor, institution_id, subject_id=subject_filter or None)) or {"summary": {}, "outcomes": []}
        summary = matrix.get("summary", {})
        kpi_grid([
            (":material/target:", "Outcomes", summary.get("outcomes", 0), "Active outcomes"),
            (":material/link:", "Mapped", summary.get("mapped", 0), "Assessment-linked outcomes"),
            (":material/verified:", "Approved evidence", summary.get("with_approved_evidence", 0), "Independent evidence review"),
            (":material/trending_up:", "Target met", summary.get("target_met", 0), "Latest attainment result"),
        ])
        if matrix.get("outcomes"):
            st.dataframe(matrix["outcomes"], width="stretch", hide_index=True)
            eligible = [row for row in matrix["outcomes"] if row.get("subject_id")]
            if eligible and roles & TEACHER_ROLES:
                attainment_outcome = st.selectbox("Calculate attainment", [row["id"] for row in eligible], format_func=lambda value: next(f"{row['code']} · {row['title']}" for row in eligible if row["id"] == value), key="p14-attain-outcome")
                if st.button("Calculate bounded attainment", type="primary", icon=":material/calculate:"):
                    result = _run(lambda: service.calculate_outcome_attainment(actor, attainment_outcome))
                    if result:
                        st.json(result)
        st.caption(matrix.get("qualification_statement", ""))


def _psychometrics(service: EducationPhase14Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    section_header("Assessment psychometrics", "Calculate item difficulty, omission, discrimination, point-biserial and reliability with sample-size warnings and expert-review boundaries.", icon=":material/analytics:")
    if not roles & TEACHER_ROLES:
        empty_state("Academic staff access required", "Psychometric evidence is restricted to academic staff.", icon="📊")
        return
    exams = platform._all("SELECT id,title,state FROM examinations WHERE institution_id=? ORDER BY created_at DESC", (institution_id,))
    if not exams:
        empty_state("No examinations", "Create and complete an examination before running psychometrics.", icon="🧪")
        return
    exam_id = st.selectbox("Examination", [row["id"] for row in exams], format_func=lambda value: next(f"{row['title']} · {row['state']}" for row in exams if row["id"] == value))
    if st.button("Run psychometric analysis", type="primary", icon=":material/science:"):
        st.session_state.phase14_psych = _run(lambda: service.run_exam_psychometrics(actor, exam_id))
    result = st.session_state.get("phase14_psych") or {}
    if result:
        alpha = result.get("reliability_alpha")
        kpi_grid([
            (":material/groups:", "Sessions", result.get("session_count", 0), "Submitted attempts"),
            (":material/quiz:", "Objective items", result.get("question_count", 0), "Analyzed questions"),
            (":material/analytics:", "Reliability α", "N/A" if alpha is None else round(float(alpha), 3), "Interpret with sample size"),
            (":material/percent:", "Mean score", round(float(result.get("mean_score_percent") or 0), 2), "Percent"),
        ])
        st.warning("Small samples and negative/low discrimination flags require expert review; these statistics must not automatically punish learners or retire questions.")
        st.dataframe(result.get("questions", []), width="stretch", hide_index=True)
    history = platform._all("SELECT * FROM education_psychometric_runs WHERE institution_id=? ORDER BY created_at DESC LIMIT 100", (institution_id,))
    if history:
        st.dataframe(history, width="stretch", hide_index=True)


def _student_success(service: EducationPhase14Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    section_header("Transparent learner-support workflow", "Generate explainable support snapshots from permitted academic evidence, then require a human-authored intervention plan.", icon=":material/volunteer_activism:")
    if not roles & TEACHER_ROLES:
        empty_state("Academic staff access required", "Students can see their learning reports elsewhere; support-case creation is staff governed.", icon="🤝")
        return
    subjects = platform._all("SELECT id,code,name FROM subjects WHERE institution_id=? AND state='active' ORDER BY code", (institution_id,))
    if not subjects:
        empty_state("No subjects", "Create a subject and enroll learners first.", icon="📘")
        return
    subject_id = st.selectbox("Subject", [row["id"] for row in subjects], format_func=lambda value: next(f"{row['code']} · {row['name']}" for row in subjects if row["id"] == value), key="p14-support-subject")
    learners = platform._all("SELECT student_id FROM enrollments WHERE subject_id=? AND state='active' ORDER BY student_id", (subject_id,))
    if not learners:
        empty_state("No enrolled learners", "Enroll learners before calculating support evidence.", icon="👥")
        return
    student_id = st.selectbox("Learner", [row["student_id"] for row in learners], key="p14-support-student")
    if st.button("Calculate transparent support snapshot", type="primary", icon=":material/insights:"):
        st.session_state.phase14_snapshot = _run(lambda: service.calculate_student_success_snapshot(actor, institution_id, student_id, subject_id))
    snapshot = st.session_state.get("phase14_snapshot") or {}
    if snapshot:
        kpi_grid([
            (":material/how_to_reg:", "Attendance", "N/A" if snapshot.get("attendance_percent") is None else f"{snapshot['attendance_percent']:.1f}%", "Permitted attendance records"),
            (":material/assignment:", "Assignments", "N/A" if snapshot.get("assignment_percent") is None else f"{snapshot['assignment_percent']:.1f}%", "Released grades"),
            (":material/psychology:", "Mastery", "N/A" if snapshot.get("mastery_percent") is None else f"{snapshot['mastery_percent']:.1f}%", "Evidence-weighted mastery"),
            (":material/flag:", "Support state", snapshot.get("risk_level", ""), "Transparent rule output"),
        ])
        st.json(snapshot.get("explanation", {}))
        with st.form("phase14-intervention"):
            reason = st.text_area("Human-reviewed reason")
            action_plan = st.text_area("Support action plan")
            assigned_to = st.text_input("Assigned staff member", value=actor)
            priority = st.selectbox("Priority", ["low", "medium", "high", "critical"], index=1)
            due = st.date_input("Review due date", value=date.today() + timedelta(days=14))
            submitted = st.form_submit_button("Create support case", type="primary", icon=":material/add_task:")
        if submitted:
            due_at = datetime.combine(due, datetime.min.time(), tzinfo=timezone.utc).isoformat()
            result = _run(lambda: service.create_intervention_case(actor, snapshot["id"], reason=reason, action_plan=action_plan, assigned_to=assigned_to, due_at=due_at, priority=priority))
            if result:
                st.success("Human-reviewed support case created.")
    cases = platform._all("SELECT * FROM education_intervention_cases WHERE institution_id=? ORDER BY created_at DESC", (institution_id,))
    if cases:
        st.dataframe(cases, width="stretch", hide_index=True)


def _calendar(service: EducationPhase14Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    section_header("Academic calendar and portable ICS", "Combine institution events and timetable entries, then export a standards-based calendar without requiring external credentials.", icon=":material/calendar_month:")
    start = st.date_input("Calendar start", value=date.today(), key="p14-calendar-start")
    end = st.date_input("Calendar end", value=date.today() + timedelta(days=30), key="p14-calendar-end")
    start_at = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc).isoformat()
    end_at = datetime.combine(end, datetime.max.time(), tzinfo=timezone.utc).isoformat()
    calendar = _run(lambda: service.academic_calendar(actor, institution_id, start_at=start_at, end_at=end_at)) or {"events": []}
    kpi_grid([
        (":material/event:", "Events", calendar.get("event_count", 0), "Academic events and timetable"),
        (":material/date_range:", "From", start.isoformat(), "UTC export range"),
        (":material/date_range:", "To", end.isoformat(), "UTC export range"),
    ])
    if calendar.get("events"):
        st.dataframe(calendar["events"], width="stretch", hide_index=True)
    else:
        empty_state("No calendar events", "Create an event or timetable entry in this date range.", icon="📅")
    if roles & TEACHER_ROLES:
        with st.expander("Create academic event", expanded=False):
            with st.form("phase14-calendar-event"):
                title = st.text_input("Event title")
                event_type = st.text_input("Event type", value="academic")
                event_date = st.date_input("Event date", value=date.today() + timedelta(days=1))
                start_time = st.time_input("Start time", value=datetime.strptime("10:00", "%H:%M").time())
                end_time = st.time_input("End time", value=datetime.strptime("11:00", "%H:%M").time())
                location = st.text_input("Location")
                description = st.text_area("Description")
                event_submitted = st.form_submit_button("Create event", type="primary", icon=":material/event_available:")
            if event_submitted:
                starts = datetime.combine(event_date, start_time, tzinfo=timezone.utc).isoformat()
                ends = datetime.combine(event_date, end_time, tzinfo=timezone.utc).isoformat()
                result = _run(lambda: service.create_calendar_event(actor, institution_id, title=title, event_type=event_type, starts_at=starts, ends_at=ends, description=description, location=location))
                if result:
                    st.success("Academic event created.")
                    st.rerun()
    if st.button("Generate verified ICS export", type="primary", icon=":material/download:"):
        result = _run(lambda: service.export_calendar_ics(actor, institution_id, start_at=start_at, end_at=end_at))
        if result:
            st.success(f"ICS export ready · {result['event_count']} events · SHA-256 {result['sha256'][:20]}…")
            st.code(result["output_path"], language=None)


def render_phase14_academic_intelligence_center(root: Path) -> None:
    render_app_header(
        "quality",
        "BioIntel Academic Quality & Intelligence Center",
        "Learning outcomes, evidence matrices, bounded attainment, exam psychometrics, transparent learner support and portable academic calendar operations.",
        eyebrow="BIOINTEL PHASE 14 · ACADEMIC INTELLIGENCE",
    )
    demo_mode = _demo_controls(root)
    platform = _page_platform(root, demo_mode)
    _identity_input("Academic Quality user ID", demo_mode)
    actor = _actor()
    institution_id = _institution(platform)
    if not institution_id:
        return
    service = EducationPhase14Service(platform, root=root)
    roles = _roles(platform, actor, institution_id)
    render_workspace_context(platform, actor, institution_id)
    render_role_snapshot(platform, actor, institution_id)
    render_app_navigation("quality", platform, actor, institution_id)
    workspace = st.segmented_control(
        "Academic intelligence workspace",
        ["Overview", "Outcomes & Evidence", "Psychometrics", "Learner Support", "Calendar & ICS"],
        default="Overview",
        key=f"phase14-workspace-{actor}-{institution_id}",
    )
    if workspace == "Outcomes & Evidence":
        _outcomes(service, platform, actor, institution_id, roles)
    elif workspace == "Psychometrics":
        _psychometrics(service, platform, actor, institution_id, roles)
    elif workspace == "Learner Support":
        _student_success(service, platform, actor, institution_id, roles)
    elif workspace == "Calendar & ICS":
        _calendar(service, platform, actor, institution_id, roles)
    else:
        _overview(service, actor, institution_id)
