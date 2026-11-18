from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ._streamlit_compat import st
from .experience import render_app_header, render_app_navigation, render_role_snapshot, render_workspace_context
from .phase11 import ADMIN_ROLES, TEACHER_ROLES, EducationPhase11Service, _totp
from .platform import EducationError
from .ui import _actor, _demo_controls, _identity_input, _institution, _page_platform, _run
from biointel.ui.frontend_v10 import empty_state, kpi_grid, section_header


def _roles(platform: Any, actor: str, institution_id: str) -> set[str]:
    return {str(row["role"]) for row in platform.membership(actor, institution_id)}


def _cards(items: list[tuple[str, str, Any, str]]) -> None:
    kpi_grid(items)


def _overview(service: EducationPhase11Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    counts = {
        "questions": platform._one("SELECT COUNT(*) count FROM education_questions WHERE institution_id=?", (institution_id,))["count"],
        "credentials": platform._one("SELECT COUNT(*) count FROM education_credentials WHERE institution_id=? AND state='active'", (institution_id,))["count"],
        "notifications": platform._one("SELECT COUNT(*) count FROM education_notification_outbox WHERE institution_id=? AND state IN ('queued','processing')", (institution_id,))["count"],
        "incidents": platform._one("SELECT COUNT(*) count FROM education_incidents WHERE institution_id=? AND status<>'resolved'", (institution_id,))["count"],
    }
    _cards([
        (":material/quiz:", "Question assets", counts["questions"], "Versioned and review-governed"),
        (":material/workspace_premium:", "Active credentials", counts["credentials"], "Signed and publicly verifiable"),
        (":material/notifications_active:", "Queued notifications", counts["notifications"], "Durable multi-channel outbox"),
        (":material/health_and_safety:", "Open incidents", counts["incidents"], "Operational response queue"),
    ])
    st.markdown(
        """
        <div class="edu-platform-grid">
          <article class="edu-module-card"><div class="edu-kicker">SECURITY</div><h3>Real TOTP and recovery authentication</h3><p>Encrypted authenticator secrets, single-use recovery codes, rate limits, tamper-evident security events and revocable sessions.</p></article>
          <article class="edu-module-card"><div class="edu-kicker">ACADEMIC GOVERNANCE</div><h3>Question bank, grade policy and credentials</h3><p>Independent reviews, item analytics, weighted grade schemes, transcripts and signed credentials with revocation evidence.</p></article>
          <article class="edu-module-card"><div class="edu-kicker">OPERATIONS</div><h3>Notifications, reports and incidents</h3><p>Durable notification outbox, governed exports, database/storage health snapshots, incident timelines and privacy requests.</p></article>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if roles & ADMIN_ROLES:
        posture = _run(lambda: service.external_dependency_posture(actor, institution_id)) or {}
        deps = posture.get("dependencies", {})
        available = sum(1 for value in deps.values() if value.get("available"))
        st.info(f"External dependency posture: {available}/{len(deps)} optional production adapters available. Configured records are never treated as live verification.", icon=":material/fact_check:")


def _security(service: EducationPhase11Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    section_header("Identity assurance", "Enroll real TOTP, issue recovery codes and verify the tamper-evident security-event chain.", icon=":material/passkey:")
    if roles & ADMIN_ROLES:
        posture = _run(lambda: service.mfa_posture(actor, institution_id)) or {"accounts": [], "total": 0, "enabled": 0, "coverage_percent": 0}
        _cards([
            (":material/account_circle:", "Desktop accounts", posture.get("total", 0), "Local identities eligible for MFA"),
            (":material/security:", "MFA enabled", posture.get("enabled", 0), "Verified TOTP enrollments"),
            (":material/donut_large:", "Coverage", f"{posture.get('coverage_percent', 0)}%", "Institution account coverage"),
            (":material/key:", "Recovery policy", "Single use", "Scrypt-hashed recovery codes"),
        ])
        if posture.get("accounts"):
            st.dataframe(posture["accounts"], width="stretch", hide_index=True)
    enrollment_tab, auth_tab, audit_tab = st.tabs(["TOTP enrollment", "Secure sign-in test", "Security chain"])
    with enrollment_tab:
        accounts = platform._all("SELECT user_id,display_name,email FROM education_identity_accounts WHERE institution_id=? AND state='active' ORDER BY display_name,user_id", (institution_id,))
        if not accounts:
            empty_state("No desktop identities", "Create an Education Desktop identity before enabling MFA.", icon="🔐", action_hint="Open Education Desktop and enroll the first local account.")
        else:
            account_ids = [row["user_id"] for row in accounts]
            target = st.selectbox("Account", account_ids, format_func=lambda value: next((row["display_name"] or row["email"] or row["user_id"]) for row in accounts if row["user_id"] == value))
            if st.button("Begin TOTP enrollment", type="primary", icon=":material/qr_code_2:"):
                result = _run(lambda: service.begin_totp_enrollment(actor, institution_id, target))
                if result:
                    st.session_state.phase11_mfa_pending = result
            pending = st.session_state.get("phase11_mfa_pending")
            if pending and pending.get("user_id") == target:
                st.code(pending["secret"], language=None)
                st.caption("Scan the otpauth URI in an authenticator application. The secret is shown only for enrollment.")
                st.text_area("Authenticator URI", pending["otpauth_uri"], disabled=True)
                code = st.text_input("Six-digit authenticator code", max_chars=6, key="phase11-confirm-code")
                if st.button("Confirm and issue recovery codes", icon=":material/verified_user:"):
                    result = _run(lambda: service.confirm_totp_enrollment(actor, institution_id, target, code))
                    if result:
                        st.success("MFA enabled. Store these recovery codes securely; each code can be used once.")
                        st.code("\n".join(result["recovery_codes"]), language=None)
                        st.session_state.pop("phase11_mfa_pending", None)
    with auth_tab:
        with st.form("phase11-secure-auth"):
            login = st.text_input("User ID or email")
            pin = st.text_input("PIN/passphrase", type="password")
            device = st.text_input("Device label", value="BioIntel Phase 11 qualification")
            begin = st.form_submit_button("Begin secure authentication", type="primary")
        if begin:
            result = _run(lambda: service.begin_secure_authentication(institution_id, login, pin, device_label=device))
            if result:
                st.session_state.phase11_auth_result = result
        challenge = st.session_state.get("phase11_auth_result") or {}
        if challenge.get("status") == "mfa_required":
            code = st.text_input("Authenticator or recovery code", type="password", key="phase11-auth-code")
            use_recovery = st.checkbox("This is a recovery code")
            if st.button("Complete sign-in", type="primary"):
                result = _run(lambda: service.complete_secure_authentication(challenge["challenge_token"], recovery_code=code if use_recovery else "", code="" if use_recovery else code))
                if result:
                    st.success(f"Secure session created for {result['user_id']} until {result['expires_at']}.")
                    st.session_state.pop("phase11_auth_result", None)
        elif challenge.get("status") == "authenticated":
            st.success("Authentication completed without MFA because the account has no enabled enrollment.")
    with audit_tab:
        if roles & ADMIN_ROLES:
            if st.button("Verify security-event chain", icon=":material/verified:"):
                result = _run(lambda: service.verify_security_chain(actor, institution_id))
                if result:
                    st.success(f"Chain passed across {result['event_count']} events.") if result["passed"] else st.error("Security-event chain failed verification.")
            events = platform._all("SELECT event_type,severity,actor_id,source,created_at FROM education_security_events WHERE institution_id=? ORDER BY created_at DESC LIMIT 100", (institution_id,))
            if events:
                st.dataframe(events, width="stretch", hide_index=True)
        else:
            st.info("Security-chain verification is restricted to institution administrators.")


def _question_bank(service: EducationPhase11Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    section_header("Assessment asset governance", "Build, independently review, publish and analyze reusable academic questions.", icon=":material/quiz:")
    banks = platform._all("SELECT * FROM education_question_banks WHERE institution_id=? AND state='active' ORDER BY updated_at DESC", (institution_id,))
    subjects = platform._all("SELECT id,code,name FROM subjects WHERE institution_id=? AND state='active' ORDER BY code", (institution_id,))
    create_bank_tab, create_question_tab, catalog_tab, blueprint_tab = st.tabs(["Banks", "Question editor", "Review catalog", "Blueprint"])
    with create_bank_tab:
        if roles & TEACHER_ROLES:
            with st.form("phase11-bank"):
                name = st.text_input("Bank name")
                subject_id = st.selectbox("Subject", [""] + [row["id"] for row in subjects], format_func=lambda value: "Institution-wide" if not value else next(f"{row['code']} · {row['name']}" for row in subjects if row["id"] == value))
                description = st.text_area("Description")
                visibility = st.selectbox("Visibility", ["restricted", "department", "institution"])
                create = st.form_submit_button("Create question bank", type="primary")
            if create:
                result = _run(lambda: service.create_question_bank(actor, institution_id, name, subject_id=subject_id or None, description=description, visibility=visibility))
                if result:
                    st.success("Question bank created.")
                    st.rerun()
        if banks:
            st.dataframe(banks, width="stretch", hide_index=True)
    with create_question_tab:
        if not banks:
            empty_state("No question bank", "Create a governed bank before adding questions.", icon="❓", action_hint="Use the Banks tab to create the first repository.")
        elif roles & TEACHER_ROLES:
            bank_id = st.selectbox("Question bank", [row["id"] for row in banks], format_func=lambda value: next(row["name"] for row in banks if row["id"] == value))
            with st.form("phase11-question"):
                qtype = st.selectbox("Question type", ["single_choice", "multiple_choice", "true_false", "short_answer", "long_answer", "numeric"])
                title = st.text_input("Question title")
                body = st.text_area("Question body", height=140)
                options = st.text_area("Options, one per line", help="Used for choice questions.")
                answer = st.text_input("Expected answer or answer key")
                c1, c2, c3, c4 = st.columns(4)
                bloom = c1.selectbox("Bloom level", ["remember", "understand", "apply", "analyze", "evaluate", "create"])
                difficulty = c2.selectbox("Difficulty", ["foundation", "easy", "medium", "hard", "advanced"])
                marks = c3.number_input("Marks", min_value=0.25, value=1.0, step=0.25)
                negative = c4.number_input("Negative marks", min_value=0.0, value=0.0, step=0.25)
                outcome = st.text_input("Course outcome code")
                create = st.form_submit_button("Save draft question", type="primary")
            if create:
                option_values = [line.strip() for line in options.splitlines() if line.strip()]
                result = _run(lambda: service.create_question(actor, bank_id, question_type=qtype, title=title, body=body, options=option_values, answer={"value": answer}, bloom_level=bloom, difficulty=difficulty, outcome_code=outcome, marks=float(marks), negative_marks=float(negative)))
                if result:
                    st.success("Draft question created with version 1 evidence.")
                    st.rerun()
    with catalog_tab:
        catalog = _run(lambda: service.question_catalog(actor, institution_id)) or []
        if catalog:
            st.dataframe(catalog, width="stretch", hide_index=True)
            question_id = st.selectbox("Selected question", [row["id"] for row in catalog], format_func=lambda value: next(row["title"] for row in catalog if row["id"] == value))
            c1, c2, c3 = st.columns(3)
            decision = c1.selectbox("Review decision", ["approve", "request_changes", "reject"])
            comments = c2.text_input("Review comments")
            if c3.button("Record review"):
                result = _run(lambda: service.review_question(actor, question_id, decision, comments=comments))
                if result:
                    st.success(f"Question moved to {result['state']}.")
                    st.rerun()
            if roles & ADMIN_ROLES and st.button("Publish approved current version", type="primary"):
                result = _run(lambda: service.publish_question(actor, question_id))
                if result:
                    st.success("Question published.")
                    st.rerun()
            analysis = _run(lambda: service.question_item_analysis(actor, question_id))
            if analysis:
                st.json(analysis)
        else:
            empty_state("No question assets", "No questions are available in the governed catalog.", icon="🧪", action_hint="Create a draft question and send it for independent review.")
    with blueprint_tab:
        published_subjects = [row for row in subjects if platform._one("SELECT id FROM education_questions WHERE subject_id=? AND state='published' LIMIT 1", (row["id"],))]
        if published_subjects:
            subject_id = st.selectbox("Blueprint subject", [row["id"] for row in published_subjects], format_func=lambda value: next(f"{row['code']} · {row['name']}" for row in published_subjects if row["id"] == value), key="phase11-blueprint-subject")
            total_marks = st.number_input("Total marks", min_value=1.0, value=20.0)
            if st.button("Generate balanced blueprint"):
                result = _run(lambda: service.generate_question_blueprint(actor, institution_id, subject_id=subject_id, total_marks=float(total_marks), bloom_distribution={"remember": 20, "understand": 30, "apply": 30, "analyze": 20}, difficulty_distribution={"easy": 30, "medium": 50, "hard": 20}))
                if result:
                    st.json(result)
        else:
            st.info("Publish at least one independently approved question to generate a blueprint.")


def _grades_credentials(service: EducationPhase11Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    section_header("Grades, transcripts and credentials", "Apply versioned grade policy, issue transcript evidence and verify signed academic credentials.", icon=":material/workspace_premium:")
    subjects = platform._all("SELECT id,code,name FROM subjects WHERE institution_id=? AND state='active' ORDER BY code", (institution_id,))
    schemes = platform._all("SELECT * FROM education_grade_schemes WHERE institution_id=? ORDER BY updated_at DESC", (institution_id,))
    scheme_tab, transcript_tab, credential_tab = st.tabs(["Grade policy", "Transcript", "Credentials"])
    with scheme_tab:
        if roles & ADMIN_ROLES:
            with st.form("phase11-grade-scheme"):
                name = st.text_input("Scheme name", value="Institution weighted scheme")
                subject_id = st.selectbox("Subject scope", [""] + [row["id"] for row in subjects], format_func=lambda value: "Institution-wide" if not value else next(f"{row['code']} · {row['name']}" for row in subjects if row["id"] == value))
                assignment_weight = st.slider("Assignment weight", 0, 100, 40)
                examination_weight = 100 - assignment_weight
                st.caption(f"Examination weight: {examination_weight}%")
                create = st.form_submit_button("Create grade scheme", type="primary")
            if create:
                result = _run(lambda: service.create_grade_scheme(actor, institution_id, name, subject_id=subject_id or None, categories=[{"name": "Assignments", "source_type": "assignment", "weight_percent": assignment_weight}, {"name": "Examination", "source_type": "examination", "weight_percent": examination_weight}], bands=[{"label": "A+", "minimum_percent": 90, "grade_points": 10}, {"label": "A", "minimum_percent": 80, "grade_points": 9}, {"label": "B", "minimum_percent": 70, "grade_points": 8}, {"label": "C", "minimum_percent": 60, "grade_points": 7}, {"label": "P", "minimum_percent": 40, "grade_points": 5}, {"label": "F", "minimum_percent": 0, "grade_points": 0}]))
                if result:
                    st.success("Grade policy created.")
                    st.rerun()
        if schemes:
            st.dataframe(schemes, width="stretch", hide_index=True)
    with transcript_tab:
        student_id = st.text_input("Student ID", key="phase11-transcript-student")
        if student_id and st.button("Load transcript"):
            result = _run(lambda: service.transcript(actor, institution_id, student_id))
            if result:
                _cards([
                    (":material/school:", "Transcript rows", len(result["entries"]), "Final subject records"),
                    (":material/credit_score:", "Credits", result["total_credits"], "Accumulated academic credit"),
                    (":material/grade:", "CGPA", result["cgpa"], "Credit-weighted grade points"),
                    (":material/verified:", "Evidence state", "Final", "Institution-governed entries"),
                ])
                st.dataframe(result["entries"], width="stretch", hide_index=True)
        if roles & ADMIN_ROLES and student_id:
            with st.expander("Add or revise transcript entry"):
                with st.form("phase11-transcript-entry"):
                    c1, c2 = st.columns(2)
                    year = c1.text_input("Academic year", value="2026-27")
                    term = c2.text_input("Term", value="Semester 1")
                    c3, c4 = st.columns(2)
                    code = c3.text_input("Subject code")
                    subject_name = c4.text_input("Subject name")
                    c5, c6, c7 = st.columns(3)
                    credits = c5.number_input("Credits", min_value=0.0, value=4.0)
                    percent = c6.number_input("Marks percent", min_value=0.0, max_value=100.0, value=75.0)
                    points = c7.number_input("Grade points", min_value=0.0, value=8.0)
                    label = st.text_input("Grade label", value="B")
                    save = st.form_submit_button("Save final transcript entry", type="primary")
                if save:
                    result = _run(lambda: service.upsert_transcript_entry(actor, institution_id, student_id, academic_year=year, term=term, subject_code=code, subject_name=subject_name, credits=float(credits), marks_percent=float(percent), grade_label=label, grade_points=float(points)))
                    if result:
                        st.success("Transcript entry saved with audit evidence.")
                        st.rerun()
    with credential_tab:
        serial = st.text_input("Credential serial number")
        if serial and st.button("Verify credential"):
            result = service.verify_credential(serial)
            if result["valid"]:
                st.success("Credential signature and active state are valid.")
            else:
                st.error(f"Credential is not valid: {result.get('reason') or result.get('state')}")
            st.json(result)
        if roles & ADMIN_ROLES:
            with st.form("phase11-credential"):
                student = st.text_input("Student ID", key="phase11-credential-student")
                credential_type = st.selectbox("Credential type", ["course_certificate", "transcript_award", "micro_credential", "laboratory_badge"])
                title = st.text_input("Credential title")
                evidence = st.text_area("Evidence JSON", value="{}")
                issue = st.form_submit_button("Issue signed credential", type="primary")
            if issue:
                try:
                    evidence_value = json.loads(evidence or "{}")
                except json.JSONDecodeError:
                    st.error("Evidence must be valid JSON.")
                else:
                    result = _run(lambda: service.issue_credential(actor, institution_id, student, credential_type=credential_type, title=title, evidence=evidence_value))
                    if result:
                        st.success(f"Credential issued: {result['serial_number']}")
                        st.json(service.verify_credential(result["serial_number"]))


def _communications_reports(service: EducationPhase11Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    section_header("Notifications and governed reporting", "Queue idempotent messages and generate auditable local exports.", icon=":material/notifications:")
    notification_tab, report_tab = st.tabs(["Notification outbox", "Report center"])
    with notification_tab:
        if roles & ADMIN_ROLES:
            with st.expander("Create notification template"):
                with st.form("phase11-template"):
                    key = st.text_input("Template key")
                    channel = st.selectbox("Channel", ["in_app", "email", "desktop", "sms", "whatsapp"])
                    subject = st.text_input("Subject template")
                    body = st.text_area("Body template", value="Hello {{name}}, your BioIntel update is ready.")
                    save = st.form_submit_button("Save template", type="primary")
                if save:
                    result = _run(lambda: service.save_notification_template(actor, institution_id, key, channel=channel, subject_template=subject, body_template=body))
                    if result:
                        st.success("Notification template saved.")
                        st.rerun()
        templates = platform._all("SELECT * FROM education_notification_templates WHERE institution_id=? AND state='active' ORDER BY template_key,channel", (institution_id,))
        if roles & TEACHER_ROLES:
            with st.form("phase11-notification"):
                recipient = st.text_input("Recipient user ID")
                if templates:
                    template_id = st.selectbox("Template", [row["id"] for row in templates], format_func=lambda value: next(f"{row['template_key']} · {row['channel']}" for row in templates if row["id"] == value))
                    selected = next(row for row in templates if row["id"] == template_id)
                    template_key = selected["template_key"]
                    channel = selected["channel"]
                else:
                    template_key = ""
                    channel = "in_app"
                destination = st.text_input("External destination (email/phone only)")
                context = st.text_area("Template context JSON", value='{"name":"Learner"}')
                idempotency = st.text_input("Idempotency key", value="manual-notification")
                queue = st.form_submit_button("Queue notification", type="primary")
            if queue:
                try:
                    context_value = json.loads(context or "{}")
                except json.JSONDecodeError:
                    st.error("Context must be valid JSON.")
                else:
                    result = _run(lambda: service.queue_notification(actor, institution_id, recipient, channel=channel, destination=destination, template_key=template_key, context=context_value, idempotency_key=idempotency))
                    if result:
                        st.success(f"Notification queued as {result['id']}.")
                        st.rerun()
        if roles & ADMIN_ROLES:
            operations = _run(lambda: service.notification_operations(actor, institution_id)) or {"states": [], "recent": []}
            if operations["states"]:
                st.dataframe(operations["states"], width="stretch", hide_index=True)
            if operations["recent"]:
                st.dataframe(operations["recent"], width="stretch", hide_index=True)
    with report_tab:
        if roles & TEACHER_ROLES:
            with st.form("phase11-report"):
                report_type = st.selectbox("Report type", ["attendance", "gradebook", "question_bank", "audit", "transcript"])
                output_format = st.selectbox("Output format", ["json", "csv"])
                student_id = st.text_input("Student ID for transcript report")
                generate = st.form_submit_button("Generate governed report", type="primary")
            if generate:
                result = _run(lambda: service.generate_report(actor, institution_id, report_type, parameters={"student_id": student_id} if student_id else {}, output_format=output_format))
                if result:
                    st.success(f"Report generated with SHA-256 {result['sha256'][:16]}…")
                    path = Path(result["output_path"])
                    if path.is_file():
                        st.download_button("Download report", path.read_bytes(), file_name=path.name, mime="application/json" if output_format == "json" else "text/csv")
        reports = platform._all("SELECT report_type,output_format,row_count,sha256,state,created_at FROM education_report_runs WHERE institution_id=? ORDER BY created_at DESC LIMIT 100", (institution_id,))
        if reports:
            st.dataframe(reports, width="stretch", hide_index=True)


def _operations_privacy(service: EducationPhase11Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    section_header("Operations, incidents and privacy", "Measure local health, manage incidents and govern data-subject requests.", icon=":material/monitor_heart:")
    operations_tab, privacy_tab, external_tab = st.tabs(["Operations posture", "Privacy governance", "External qualification"])
    with operations_tab:
        if roles & ADMIN_ROLES:
            if st.button("Record health snapshot", type="primary", icon=":material/health_metrics:"):
                result = _run(lambda: service.record_health_snapshot(actor, institution_id))
                if result:
                    st.success("Database, storage, queue and backup posture captured.")
                    st.rerun()
            posture = _run(lambda: service.operations_posture(actor, institution_id)) or {}
            latest = posture.get("latest_health")
            if latest:
                _cards([
                    (":material/database:", "Database", "Healthy" if latest["database_ok"] else "Failed", "SQLite quick_check"),
                    (":material/folder_open:", "Storage", "Writable" if latest["storage_ok"] else "Failed", "Governed data root"),
                    (":material/queue:", "Pending jobs", latest["queue_pending"], "Queued or running work"),
                    (":material/error:", "Failed jobs", latest["queue_failed"], "Requires operations review"),
                ])
            with st.expander("Encrypted full backup"):
                full_backups = platform._all("SELECT id,label,state,size_bytes,created_at,verified_at FROM education_full_backups WHERE institution_id=? ORDER BY created_at DESC", (institution_id,))
                label = st.text_input("Full backup label", value="phase11-checkpoint", key="phase11-full-backup-label")
                if st.button("Create encrypted full backup", type="primary", icon=":material/encrypted:"):
                    result = _run(lambda: service.create_full_backup(actor, institution_id, label))
                    if result:
                        st.success(f"Encrypted full backup verified across {result['file_count']} files.")
                        st.rerun()
                if full_backups:
                    st.dataframe(full_backups, width="stretch", hide_index=True)
                    selected_backup = st.selectbox("Backup for restore rehearsal", [row["id"] for row in full_backups], format_func=lambda value: next(row["label"] for row in full_backups if row["id"] == value), key="phase11-full-backup-selected")
                    if st.button("Run non-destructive restore rehearsal", icon=":material/restore:"):
                        result = _run(lambda: service.full_backup_restore_rehearsal(actor, selected_backup))
                        if result:
                            st.success(f"Restore rehearsal passed: {result['integrity']}. Live data was not replaced.")
                            st.code(result["rehearsal_path"], language=None)
            with st.expander("Open incident"):
                with st.form("phase11-incident"):
                    title = st.text_input("Incident title")
                    severity = st.selectbox("Severity", ["low", "medium", "high", "critical"])
                    summary = st.text_area("Summary")
                    create = st.form_submit_button("Open incident", type="primary")
                if create:
                    result = _run(lambda: service.open_incident(actor, institution_id, title, severity=severity, summary=summary, owner_id=actor))
                    if result:
                        st.success("Incident opened with security-event evidence.")
                        st.rerun()
            if posture.get("incidents"):
                st.dataframe(posture["incidents"], width="stretch", hide_index=True)
        else:
            st.info("Operational health and incident controls are restricted to institution administrators.")
    with privacy_tab:
        with st.form("phase11-privacy"):
            subject_user = st.text_input("Data subject user ID", value=actor)
            request_type = st.selectbox("Request type", ["access", "correction", "export", "deletion", "anonymization", "consent_withdrawal"])
            reason = st.text_area("Reason")
            create = st.form_submit_button("Create privacy request", type="primary")
        if create:
            result = _run(lambda: service.create_privacy_request(actor, institution_id, subject_user, request_type=request_type, reason=reason))
            if result:
                st.success("Privacy request created for governed review.")
                st.rerun()
        requests = platform._all("SELECT * FROM education_privacy_requests WHERE institution_id=? ORDER BY created_at DESC LIMIT 100", (institution_id,)) if roles & ADMIN_ROLES else platform._all("SELECT * FROM education_privacy_requests WHERE institution_id=? AND requester_id=? ORDER BY created_at DESC", (institution_id, actor))
        if requests:
            st.dataframe(requests, width="stretch", hide_index=True)
        if roles & ADMIN_ROLES:
            with st.expander("Retention policy"):
                with st.form("phase11-retention"):
                    data_class = st.text_input("Data class", value="education_records")
                    days = st.number_input("Retention days", min_value=1, max_value=36500, value=2555)
                    action = st.selectbox("End-of-retention action", ["archive", "anonymize", "delete"])
                    legal_hold = st.checkbox("Legal hold")
                    save = st.form_submit_button("Save retention policy")
                if save:
                    result = _run(lambda: service.save_retention_policy(actor, institution_id, data_class, retention_days=int(days), action=action, legal_hold=legal_hold))
                    if result:
                        st.success("Retention policy saved.")
    with external_tab:
        if roles & ADMIN_ROLES:
            posture = _run(lambda: service.external_dependency_posture(actor, institution_id)) or {}
            st.warning("Configured does not mean live verified. Provider credentials, network access, dependency installation and provider-side qualification remain mandatory.", icon=":material/warning:")
            if posture.get("dependencies"):
                rows = [{"capability": key, **value} for key, value in posture["dependencies"].items()]
                st.dataframe(rows, width="stretch", hide_index=True)
            with st.expander("Database, storage and integration profiles"):
                st.json({"database_profiles": posture.get("database_profiles"), "storage_profiles": posture.get("storage_profiles"), "integrations": posture.get("integrations")})


def render_phase11_mega_center(root: Path) -> None:
    render_app_header(
        "mega",
        "BioIntel Mega Production & Academic Center",
        "Real MFA, governed question assets, institutional grade policy, signed credentials, durable notifications, reports, monitoring, incidents and privacy controls.",
        eyebrow="BIOINTEL PHASE 11 · MEGA CORE",
    )
    demo_mode = _demo_controls(root)
    platform = _page_platform(root, demo_mode)
    _identity_input("Mega Center user ID", demo_mode)
    actor = _actor()
    institution_id = _institution(platform)
    if not institution_id:
        return
    service = EducationPhase11Service(platform, root=root)
    roles = _roles(platform, actor, institution_id)
    render_workspace_context(platform, actor, institution_id)
    render_role_snapshot(platform, actor, institution_id)
    render_app_navigation("mega", platform, actor, institution_id)
    workspace = st.segmented_control(
        "Mega upgrade workspace",
        ["Overview", "Security", "Question Bank", "Grades & Credentials", "Communications & Reports", "Operations & Privacy"],
        default="Overview",
        key=f"phase11-workspace-{actor}-{institution_id}",
    )
    if workspace == "Security":
        _security(service, platform, actor, institution_id, roles)
    elif workspace == "Question Bank":
        _question_bank(service, platform, actor, institution_id, roles)
    elif workspace == "Grades & Credentials":
        _grades_credentials(service, platform, actor, institution_id, roles)
    elif workspace == "Communications & Reports":
        _communications_reports(service, platform, actor, institution_id, roles)
    elif workspace == "Operations & Privacy":
        _operations_privacy(service, platform, actor, institution_id, roles)
    else:
        _overview(service, platform, actor, institution_id, roles)
