from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from ._streamlit_compat import st
from .experience import render_app_header, render_app_navigation, render_role_snapshot, render_workspace_context
from .phase11 import ADMIN_ROLES, TEACHER_ROLES
from .phase13 import EducationPhase13Service, SUPPORTED_DOCUMENT_SUFFIXES
from .ui import _actor, _demo_controls, _identity_input, _institution, _page_platform, _run
from biointel.ui.frontend_v10 import empty_state, kpi_grid, section_header


def _roles(platform: Any, actor: str, institution_id: str) -> set[str]:
    return {str(row["role"]) for row in platform.membership(actor, institution_id)}


def _overview(service: EducationPhase13Service, actor: str, institution_id: str) -> None:
    posture = _run(lambda: service.phase13_posture(actor, institution_id)) or {}
    counts = posture.get("counts", {})
    kpi_grid([
        (":material/library_books:", "Approved evidence", counts.get("approved_rag_documents", 0), "Human-approved RAG sources"),
        (":material/manage_search:", "Searchable chunks", counts.get("rag_chunks", 0), "Permission-filtered citations"),
        (":material/calendar_month:", "Timetable runs", counts.get("timetable_runs", 0), "Preview and atomic commits"),
        (":material/notifications_active:", "Failed deliveries", counts.get("failed_notifications", 0), "Dead-letter operations"),
    ])
    st.markdown(
        """
        <div class="edu-platform-grid">
          <article class="edu-module-card"><div class="edu-kicker">EVIDENCE AUTONOMY</div><h3>Multi-format ingestion with exact locators</h3><p>PDF, DOCX, PPTX, XLSX, HTML, JSON, CSV, Markdown and text sources become approved, permission-filtered chunks with page, slide, sheet or line citations.</p></article>
          <article class="edu-module-card"><div class="edu-kicker">ACADEMIC OPERATIONS</div><h3>Conflict-free timetable planning</h3><p>A bounded solver assigns teacher, student-group and room-safe weekly slots. Incomplete plans never partially modify the live timetable.</p></article>
          <article class="edu-module-card"><div class="edu-kicker">OPERATIONS & GOVERNANCE</div><h3>Quiet hours, retention and redacted diagnostics</h3><p>Notification policy decisions are auditable; retention execution requires exact confirmation and a verified archive; support bundles exclude personal content.</p></article>
        </div>
        """,
        unsafe_allow_html=True,
    )
    external = (posture.get("external_posture") or {}).get("external_qualification_still_required", [])
    if external:
        st.info("External credentials, code-signing reputation and independent audits remain evidence-bound gates; Phase 13 does not fabricate them.", icon=":material/fact_check:")


def _evidence(service: EducationPhase13Service, platform: Any, actor: str, institution_id: str, roles: set[str], root: Path) -> None:
    section_header("Evidence ingestion and citation retrieval", "Register, approve, extract and search institution-governed evidence without sending content to external services.", icon=":material/library_books:")
    register_tab, ingest_tab, search_tab = st.tabs(["Register source", "Approve & ingest", "Search evidence"])
    with register_tab:
        if not roles & TEACHER_ROLES:
            empty_state("Educator access required", "Only academic staff can register evidence sources.", icon="🔒")
        else:
            project_id = st.text_input("Evidence project", value="institution-evidence", key="p13-rag-project")
            title = st.text_input("Source title", key="p13-rag-title")
            uploaded = st.file_uploader(
                "Evidence file",
                type=sorted(suffix.lstrip(".") for suffix in SUPPORTED_DOCUMENT_SUFFIXES),
                key="p13-rag-upload",
                help="Scanned-image PDFs require a separately approved OCR adapter; no fake OCR completion is reported.",
            )
            permitted_roles = st.multiselect(
                "Permitted roles",
                ["university_student", "college_student", "school_student", "subject_teacher", "professor", "assistant_professor", "institution_administrator"],
                default=["subject_teacher", "university_student"],
                key="p13-rag-roles",
            )
            if st.button("Register and safety-scan", type="primary", icon=":material/upload_file:", disabled=uploaded is None or not project_id.strip()):
                upload_root = root / "education" / "rag_uploads" / institution_id
                upload_root.mkdir(parents=True, exist_ok=True)
                safe_name = Path(uploaded.name).name
                destination = upload_root / safe_name
                destination.write_bytes(uploaded.getbuffer())
                result = _run(lambda: service.register_rag_document(actor, institution_id, project_id, destination, title=title, permissions={"roles": permitted_roles}))
                if result:
                    st.success(f"Registered as {result['state']}. Human approval is required before ingestion.")
                    st.json({key: result.get(key) for key in ("id", "title", "source_name", "sha256", "state", "safety") if key in result})
    with ingest_tab:
        documents = platform._all(
            "SELECT id,title,source_name,mime_type,size_bytes,state,created_by,created_at FROM education_rag_documents WHERE institution_id=? ORDER BY created_at DESC",
            (institution_id,),
        )
        if not documents:
            empty_state("No evidence registered", "Upload an institution-owned evidence file first.", icon="📚")
        else:
            st.dataframe(documents, width="stretch", hide_index=True)
            document_id = st.selectbox("Document", [row["id"] for row in documents], format_func=lambda value: next(f"{row['title']} · {row['state']}" for row in documents if row["id"] == value), key="p13-doc")
            selected = next(row for row in documents if row["id"] == document_id)
            if roles & ADMIN_ROLES and selected["state"] in {"registered", "quarantined", "rejected"}:
                reason = st.text_input("Approval reason", value="Institution-approved evidence source", key="p13-approval-reason")
                approve_col, reject_col = st.columns(2)
                if approve_col.button("Approve source", type="primary", icon=":material/verified:"):
                    _run(lambda: service.approve_rag_document(actor, document_id, approve=True, reason=reason))
                    st.rerun()
                if reject_col.button("Reject source", icon=":material/block:"):
                    _run(lambda: service.approve_rag_document(actor, document_id, approve=False, reason=reason or "Rejected by administrator"))
                    st.rerun()
            chunk_chars = st.slider("Chunk size (characters)", 300, 4000, 1400, 100)
            overlap = st.slider("Chunk overlap", 0, 800, 180, 20)
            if st.button("Extract and index approved source", type="primary", icon=":material/document_scanner:", disabled=selected["state"] != "approved"):
                result = _run(lambda: service.ingest_rag_document(actor, document_id, chunk_chars=chunk_chars, overlap_chars=overlap))
                if result:
                    st.success(f"Indexed {result['chunk_count']} chunks from {result['locator_count']} source locations using {result['parser']}.")
            ingestions = platform._all("SELECT id,document_id,parser,state,chunk_count,character_count,error_text,created_at,completed_at FROM education_rag_ingestion_runs WHERE institution_id=? ORDER BY created_at DESC LIMIT 100", (institution_id,))
            if ingestions:
                st.dataframe(ingestions, width="stretch", hide_index=True)
    with search_tab:
        projects = [row["project_id"] for row in platform._all("SELECT DISTINCT project_id FROM education_rag_chunks WHERE institution_id=? AND state='active' ORDER BY project_id", (institution_id,))]
        if not projects:
            empty_state("No searchable evidence", "Approve and ingest at least one evidence source.", icon="🔎")
        else:
            project = st.selectbox("Evidence project", projects, key="p13-search-project")
            query = st.text_area("Question or search query", placeholder="What evidence explains DNA inheritance?", key="p13-search-query")
            if st.button("Search approved evidence", type="primary", icon=":material/search:", disabled=len(query.strip()) < 2):
                st.session_state.phase13_search = _run(lambda: service.search_rag(actor, institution_id, project, query, limit=12))
            result = st.session_state.get("phase13_search") or {}
            if result:
                kpi_grid([
                    (":material/search:", "Matches", result.get("result_count", 0), result.get("evidence_status", "")),
                    (":material/security:", "Policy", "Local", "Approved and permission-filtered"),
                    (":material/source:", "Citations", len(result.get("results", [])), "Exact page, slide, sheet or line locators"),
                ])
                for item in result.get("results", []):
                    with st.expander(f"{item['citation']} · score {item['score']}"):
                        st.write(item["excerpt"])
                        st.caption(f"Matched: {', '.join(item['matched_terms']) or 'phrase'} · SHA-256 {item['document_sha256'][:16]}…")


def _timetable(service: EducationPhase13Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    section_header("Automatic timetable generator", "Build a conflict-free weekly plan, preview unscheduled requirements, then commit all series atomically.", icon=":material/calendar_month:")
    if not roles & TEACHER_ROLES:
        empty_state("Academic staff access required", "Students can view published timetables from Classroom.", icon="📅")
        return
    subjects = platform._all("SELECT id,code,name FROM subjects WHERE institution_id=? AND state='active' ORDER BY code", (institution_id,))
    teachers = platform._all("SELECT DISTINCT teacher_id FROM teacher_assignments WHERE institution_id=? AND state='active' ORDER BY teacher_id", (institution_id,))
    if not subjects or not teachers:
        empty_state("Subjects or teacher assignments missing", "Create subjects and assign teachers before generating a timetable.", icon="🧩")
        return
    cols = st.columns(4)
    term_start = cols[0].date_input("Term start", value=date.today() + timedelta(days=1), key="p13-term-start")
    weeks = cols[1].number_input("Weeks", 1, 52, 12, key="p13-weeks")
    day_start = cols[2].text_input("Day starts", "09:00", key="p13-day-start")
    day_end = cols[3].text_input("Day ends", "17:00", key="p13-day-end")
    subject_id = st.selectbox("Subject", [row["id"] for row in subjects], format_func=lambda value: next(f"{row['code']} · {row['name']}" for row in subjects if row["id"] == value), key="p13-subject")
    assigned = [row["teacher_id"] for row in platform._all("SELECT teacher_id FROM teacher_assignments WHERE institution_id=? AND subject_id=? AND state='active' ORDER BY teacher_id", (institution_id, subject_id))]
    teacher_id = st.selectbox("Assigned teacher", assigned, key="p13-teacher") if assigned else ""
    grid = st.columns(4)
    student_group = grid[0].text_input("Student group", "BIO-A", key="p13-group")
    rooms = grid[1].text_input("Room candidates", "LAB-1, ROOM-2", key="p13-rooms")
    sessions = grid[2].number_input("Sessions/week", 1, 20, 3, key="p13-sessions")
    duration = grid[3].selectbox("Duration", [30, 45, 60, 75, 90, 120, 180], index=2, key="p13-duration")
    requirement = [{
        "subject_id": subject_id, "teacher_id": teacher_id, "student_group": student_group,
        "room_candidates": [item.strip() for item in rooms.split(",") if item.strip()],
        "sessions_per_week": int(sessions), "duration_minutes": int(duration), "priority": 80,
    }]
    preview_col, commit_col = st.columns(2)
    if preview_col.button("Generate preview", type="primary", icon=":material/preview:", disabled=not teacher_id or not student_group.strip()):
        st.session_state.phase13_timetable = _run(lambda: service.generate_timetable_plan(actor, institution_id, term_start=term_start.isoformat(), weeks=int(weeks), requirements=requirement, day_start=day_start, day_end=day_end, commit=False))
    confirmation = commit_col.checkbox("Commit only if every session is scheduled", key="p13-commit-confirm")
    if commit_col.button("Generate and commit", type="primary", icon=":material/event_available:", disabled=not confirmation or not teacher_id or not student_group.strip()):
        st.session_state.phase13_timetable = _run(lambda: service.generate_timetable_plan(actor, institution_id, term_start=term_start.isoformat(), weeks=int(weeks), requirements=requirement, day_start=day_start, day_end=day_end, commit=True))
    result = st.session_state.get("phase13_timetable") or {}
    if result:
        kpi_grid([
            (":material/event:", "Weekly sessions", result.get("planned_sessions_per_week", 0), "Conflict-free plan"),
            (":material/warning:", "Unscheduled", len(result.get("unscheduled", [])), "Commit blocked when non-zero"),
            (":material/date_range:", "Weeks", result.get("weeks", 0), result.get("state", "")),
        ])
        st.dataframe(result.get("plan", []), width="stretch", hide_index=True)
        if result.get("unscheduled"):
            st.error("Some sessions could not be scheduled; no live timetable changes were committed.")
            st.dataframe(result["unscheduled"], width="stretch", hide_index=True)


def _notifications(service: EducationPhase13Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    section_header("Notification policy and delivery operations", "Apply user preferences, quiet hours, digests, idempotency and dead-letter recovery before provider delivery.", icon=":material/notifications_active:")
    digest_tab, queue_tab, operations_tab = st.tabs(["My digest", "Policy-aware queue", "Dead-letter operations"])
    with digest_tab:
        digest = _run(lambda: service.build_in_app_digest(actor, institution_id, actor)) or {}
        kpi_grid([
            (":material/mark_email_unread:", "Unread", digest.get("total", 0), "Last seven days"),
            (":material/category:", "Event groups", len(digest.get("groups", [])), "Grouped for review"),
        ])
        for group in digest.get("groups", []):
            with st.expander(f"{group['event_type']} · {group['count']}"):
                st.dataframe(group["items"], width="stretch", hide_index=True)
        if digest.get("total") and st.button("Mark digest items read", icon=":material/done_all:"):
            _run(lambda: service.build_in_app_digest(actor, institution_id, actor, mark_read=True))
            st.rerun()
    with queue_tab:
        if roles & TEACHER_ROLES:
            people = [row["user_id"] for row in platform._all("SELECT DISTINCT user_id FROM institution_memberships WHERE institution_id=? AND state='active' ORDER BY user_id", (institution_id,))]
            with st.form("p13-notification"):
                recipient = st.selectbox("Recipient", people)
                event_type = st.text_input("Event type", "academic_update")
                channel = st.selectbox("Channel", ["in_app", "desktop", "email", "sms", "whatsapp"])
                destination = st.text_input("Destination", help="Required for external channels")
                subject = st.text_input("Subject")
                body = st.text_area("Message")
                idempotency = st.text_input("Idempotency key")
                submitted = st.form_submit_button("Apply policy and queue", type="primary")
            if submitted:
                result = _run(lambda: service.queue_policy_notification(actor, institution_id, recipient, event_type=event_type, channel=channel, destination=destination, subject=subject, body=body, idempotency_key=idempotency))
                if result:
                    st.json(result)
        else:
            empty_state("Staff queue access required", "Students manage their own preferences and digest from the notification center.", icon="🔔")
    with operations_tab:
        if roles & ADMIN_ROLES:
            posture = service.notification_operations(actor, institution_id)
            st.dataframe(posture.get("states", []), width="stretch", hide_index=True)
            failed = platform._one("SELECT COUNT(*) count FROM education_notification_outbox WHERE institution_id=? AND state='failed'", (institution_id,)) or {"count": 0}
            if st.button(f"Requeue {failed['count']} failed deliveries", disabled=not failed["count"], icon=":material/replay:"):
                result = _run(lambda: service.requeue_failed_notifications(actor, institution_id))
                if result:
                    st.success(f"Requeued {result['requeued']} deliveries.")
        else:
            empty_state("Administrator access required", "Dead-letter recovery is a governed administrative action.", icon="📨")


def _lifecycle(service: EducationPhase13Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    section_header("Lifecycle, retention and support diagnostics", "Preview destructive scope, create a verified archive, require exact confirmation and generate a redacted support bundle.", icon=":material/health_and_safety:")
    if not roles & ADMIN_ROLES:
        empty_state("Administrator access required", "Retention execution and diagnostics export are restricted.", icon="🔐")
        return
    retention_tab, support_tab = st.tabs(["Retention execution", "Support diagnostics"])
    with retention_tab:
        policies = platform._all("SELECT * FROM education_retention_policies WHERE institution_id=? AND state='active' ORDER BY data_class", (institution_id,))
        if not policies:
            empty_state("No retention policy", "Define a policy in Mega Production & Academic Center first.", icon="🗂️")
        else:
            st.dataframe(policies, width="stretch", hide_index=True)
            supported = [row for row in policies if row["data_class"] in {"notifications", "sessions", "reports", "rag_chunks"}]
            if supported:
                data_class = st.selectbox("Automated data class", [row["data_class"] for row in supported], key="p13-retention-class")
                if st.button("Preview retention candidates", type="primary", icon=":material/preview:"):
                    st.session_state.phase13_retention = _run(lambda: service.execute_retention_policy(actor, institution_id, data_class, dry_run=True))
                preview = st.session_state.get("phase13_retention") or {}
                if preview:
                    st.json(preview)
                    confirmation = st.text_input("Exact confirmation phrase", placeholder=f"EXECUTE {data_class} {preview.get('candidate_count', 0)}")
                    if st.button("Archive and execute policy", type="primary", disabled=not preview.get("candidate_count"), icon=":material/policy:"):
                        result = _run(lambda: service.execute_retention_policy(actor, institution_id, data_class, dry_run=False, confirmation=confirmation))
                        if result:
                            st.success(f"Policy executed with verified archive: {result['archive_path']}")
    with support_tab:
        st.info("The support bundle contains health, incident, qualification, migration and aggregated security metadata—not message bodies, assignment content, passwords or secrets.", icon=":material/privacy_tip:")
        if st.button("Create redacted support bundle", type="primary", icon=":material/folder_zip:"):
            result = _run(lambda: service.create_support_bundle(actor, institution_id))
            if result:
                st.session_state.phase13_support = result
        result = st.session_state.get("phase13_support") or {}
        if result:
            st.success(f"Support bundle ready · {result['size_bytes']} bytes · SHA-256 {result['sha256'][:20]}…")
            st.code(result["output_path"], language=None)
            if st.button("Verify bundle", icon=":material/verified:"):
                verification = _run(lambda: service.verify_support_bundle(actor, result["id"]))
                if verification:
                    st.json(verification)


def render_phase13_autonomy_center(root: Path) -> None:
    render_app_header(
        "autonomy",
        "BioIntel Local Autonomy & Operations Center",
        "Multi-format evidence ingestion, citation-grade local retrieval, automatic timetable generation, governed notification policy, retention execution and redacted support diagnostics.",
        eyebrow="BIOINTEL PHASE 13 · LOCAL AUTONOMY",
    )
    demo_mode = _demo_controls(root)
    platform = _page_platform(root, demo_mode)
    _identity_input("Autonomy Center user ID", demo_mode)
    actor = _actor()
    institution_id = _institution(platform)
    if not institution_id:
        return
    service = EducationPhase13Service(platform, root=root)
    roles = _roles(platform, actor, institution_id)
    render_workspace_context(platform, actor, institution_id)
    render_role_snapshot(platform, actor, institution_id)
    render_app_navigation("autonomy", platform, actor, institution_id)
    workspace = st.segmented_control(
        "Autonomy workspace",
        ["Overview", "Evidence Library", "Timetable Automation", "Notifications", "Lifecycle & Support"],
        default="Overview",
        key=f"phase13-workspace-{actor}-{institution_id}",
    )
    if workspace == "Evidence Library":
        _evidence(service, platform, actor, institution_id, roles, root)
    elif workspace == "Timetable Automation":
        _timetable(service, platform, actor, institution_id, roles)
    elif workspace == "Notifications":
        _notifications(service, platform, actor, institution_id, roles)
    elif workspace == "Lifecycle & Support":
        _lifecycle(service, platform, actor, institution_id, roles)
    else:
        _overview(service, actor, institution_id)
