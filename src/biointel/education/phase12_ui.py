from __future__ import annotations

from pathlib import Path
from typing import Any

from ._streamlit_compat import st
from .experience import render_app_header, render_app_navigation, render_role_snapshot, render_workspace_context
from .phase11 import ADMIN_ROLES, TEACHER_ROLES
from .phase12 import EducationPhase12Service
from .ui import _actor, _demo_controls, _identity_input, _institution, _page_platform, _run
from biointel.ui.frontend_v10 import empty_state, kpi_grid, section_header


def _roles(platform: Any, actor: str, institution_id: str) -> set[str]:
    return {str(row["role"]) for row in platform.membership(actor, institution_id)}


def _overview(service: EducationPhase12Service, platform: Any, actor: str, institution_id: str) -> None:
    posture = _run(lambda: service.final_completion_posture(actor, institution_id)) or {}
    kpi_grid([
        (":material/verified_user:", "Local completion", f"{posture.get('local_code_completion_score', 0)}%", "Code-level institution posture"),
        (":material/fact_check:", "Governed exams", posture.get("governed_exams", 0), "Independent approvals and moderation"),
        (":material/plagiarism:", "Originality records", posture.get("originality_fingerprints", 0), "Human-reviewed similarity evidence"),
        (":material/model_training:", "AI profiles", posture.get("ai_model_profiles", 0), "Model and RAG governance"),
    ])
    st.markdown(
        """
        <div class="edu-platform-grid">
          <article class="edu-module-card"><div class="edu-kicker">IDENTITY & INFRASTRUCTURE</div><h3>OIDC PKCE, migration exports and external storage</h3><p>Real provider handshakes remain credential-bound, while the application now supplies secure state/nonce handling, signed token validation, portable database exports and verified S3/MinIO transfer contracts.</p></article>
          <article class="edu-module-card"><div class="edu-kicker">ACADEMIC ASSURANCE</div><h3>Originality, double evaluation and appeals</h3><p>Submission fingerprints never auto-punish learners. Examination papers, answer keys, controller approval, independent evaluation, moderation and appeals preserve human governance.</p></article>
          <article class="edu-module-card"><div class="edu-kicker">SHIRO & OPERATIONS</div><h3>Model profiles, RAG safety and provider delivery</h3><p>Hardware posture, local/remote model qualification, prompt-injection quarantine, retrieval evaluation and signed provider delivery are represented as inspectable evidence.</p></article>
        </div>
        """,
        unsafe_allow_html=True,
    )
    remaining = posture.get("external_qualification_still_required", [])
    if remaining:
        st.warning("Code completion is not a substitute for external qualification.", icon=":material/warning:")
        st.dataframe([{"External gate": item, "Status": "External system required"} for item in remaining], width="stretch", hide_index=True)


def _identity_infrastructure(service: EducationPhase12Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    section_header("Identity and infrastructure completion", "Configure real provider flows without exposing secrets in the application database.", icon=":material/cloud_done:")
    idp_tab, db_tab, storage_tab = st.tabs(["OIDC PKCE", "Database migration", "Object storage"])
    with idp_tab:
        providers = platform._all("SELECT id,display_name,provider_type,state,issuer_url,client_id FROM education_identity_providers WHERE institution_id=? ORDER BY created_at DESC", (institution_id,))
        if not providers:
            empty_state("No OIDC provider configured", "Create an OIDC, Google Workspace or Microsoft Entra provider in Institution Center first.", icon="🔑", action_hint="Use env: secret references and run the provider qualification check.")
        else:
            st.dataframe(providers, width="stretch", hide_index=True)
            provider_id = st.selectbox("Provider", [row["id"] for row in providers], format_func=lambda value: next(row["display_name"] for row in providers if row["id"] == value), key="phase12-oidc-provider")
            redirect_uri = st.text_input("Redirect URI", "http://localhost:8501/oidc/callback", key="phase12-oidc-redirect")
            login_hint = st.text_input("Login hint", key="phase12-oidc-hint")
            if st.button("Create PKCE authorization request", type="primary", icon=":material/login:"):
                result = _run(lambda: service.begin_oidc_authorization(provider_id, redirect_uri, login_hint=login_hint))
                if result:
                    st.session_state.phase12_oidc_request = result
            if st.session_state.get("phase12_oidc_request"):
                st.code(st.session_state.phase12_oidc_request["authorization_url"], language=None)
                st.caption("Open this URL in the browser. Callback completion requires a real provider authorization code and the returned nonce.")
    with db_tab:
        profiles = platform._all("SELECT id,name,engine,state,ssl_mode FROM education_database_profiles WHERE institution_id=? ORDER BY created_at DESC", (institution_id,))
        st.dataframe(profiles, width="stretch", hide_index=True) if profiles else empty_state("No database profile", "Configure a PostgreSQL profile in Institution Center before creating a migration bundle.", icon="🗄️")
        profile_id = st.selectbox("Target profile", [""] + [row["id"] for row in profiles if row["engine"] == "postgresql"], format_func=lambda value: "Portable export only" if not value else next(row["name"] for row in profiles if row["id"] == value), key="phase12-db-profile")
        if st.button("Generate portable PostgreSQL migration export", type="primary", icon=":material/database:"):
            result = _run(lambda: service.create_database_migration_export(actor, institution_id, profile_id=profile_id))
            if result:
                st.success(f"Export ready: {result['row_count']} tenant-scoped rows across {result['table_count']} tables.")
                st.code(result["output_path"], language=None)
        exports = platform._all("SELECT id,profile_id,row_count,table_count,state,created_at FROM education_database_migration_exports WHERE institution_id=? ORDER BY created_at DESC LIMIT 20", (institution_id,))
        if exports and roles & ADMIN_ROLES:
            export_id = st.selectbox("Migration export", [row["id"] for row in exports], format_func=lambda value: next(f"{row['created_at']} · {row['row_count']} rows · {row['state']}" for row in exports if row["id"] == value), key="phase12-db-export")
            validate_col, apply_col = st.columns(2)
            if validate_col.button("Validate against live PostgreSQL", icon=":material/fact_check:"):
                result = _run(lambda: service.apply_database_migration_export(actor, export_id, dry_run=True))
                if result:
                    st.success(f"PostgreSQL validation passed for {result['rows_examined']} rows across {result['tables']} tables.")
            confirm_apply = apply_col.checkbox("I confirm target schema and backup are ready", key="phase12-db-apply-confirm")
            if apply_col.button("Apply idempotent migration", type="primary", disabled=not confirm_apply, icon=":material/cloud_upload:"):
                result = _run(lambda: service.apply_database_migration_export(actor, export_id, dry_run=False))
                if result:
                    st.success(f"Migration applied: {result['rows_inserted']} new rows; retries remain idempotent.")
    with storage_tab:
        backends = platform._all("SELECT id,name,backend_type,bucket,region,state FROM education_storage_backends WHERE institution_id=? ORDER BY created_at DESC", (institution_id,))
        st.dataframe(backends, width="stretch", hide_index=True) if backends else empty_state("No storage backend", "Configure S3 or MinIO using an env: JSON credentials reference.", icon="☁")
        st.info("Live upload requires boto3 from requirements-production.txt and real provider credentials. The application verifies remote size and SHA-256 metadata after upload.", icon=":material/info:")


def _academic_assurance(service: EducationPhase12Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    originality_tab, governance_tab, monitor_tab = st.tabs(["Originality", "Exam governance", "Live monitoring"])
    with originality_tab:
        section_header("Originality review", "Local text fingerprints surface evidence for human review; no automatic academic penalty is applied.", icon=":material/plagiarism:")
        submissions = platform._all("""SELECT s.id,s.student_id,s.state,a.title assignment,subj.name subject
            FROM submissions s JOIN assignments a ON a.id=s.assignment_id JOIN subjects subj ON subj.id=a.subject_id
            WHERE s.institution_id=? AND s.state='final' ORDER BY s.submitted_at DESC LIMIT 200""", (institution_id,))
        if not submissions:
            empty_state("No sealed submissions", "Final assignment submissions will appear here for originality analysis.", icon="📄")
        else:
            submission_id = st.selectbox("Submission", [row["id"] for row in submissions], format_func=lambda value: next(f"{row['assignment']} · {row['student_id']}" for row in submissions if row["id"] == value))
            threshold = st.slider("Similarity review threshold", .10, .90, .35, .05)
            if st.button("Analyze originality", type="primary", icon=":material/search:"):
                result = _run(lambda: service.analyze_submission_originality(actor, submission_id, threshold=threshold))
                if result:
                    st.session_state.phase12_originality = result
            if st.session_state.get("phase12_originality"):
                result = st.session_state.phase12_originality
                kpi_grid([
                    (":material/token:", "Tokens", result.get("token_count", 0), "Normalized text tokens"),
                    (":material/compare:", "Compared", result.get("comparison_count", 0), "Same-subject prior fingerprints"),
                    (":material/warning:", "Review matches", len(result.get("matches", [])), "Human review only"),
                    (":material/gavel:", "Automatic penalty", "No", "Decision remains human-governed"),
                ])
                st.dataframe(result.get("matches", []), width="stretch", hide_index=True)
    with governance_tab:
        section_header("Examination approval chain", "Separate paper review, answer-key review and controller approval before an examination can be scheduled.", icon=":material/account_tree:")
        exams = platform._all("SELECT id,title,state,created_by FROM examinations WHERE institution_id=? ORDER BY created_at DESC", (institution_id,))
        if not exams:
            empty_state("No examination", "Create an examination before configuring its governance chain.", icon="📝")
        else:
            exam_id = st.selectbox("Examination", [row["id"] for row in exams], format_func=lambda value: next(row["title"] for row in exams if row["id"] == value), key="phase12-governance-exam")
            existing = platform._one("SELECT * FROM education_exam_governance WHERE exam_id=?", (exam_id,))
            if existing:
                governance = _run(lambda: service.exam_governance(actor, exam_id))
                if governance:
                    st.json(governance)
            elif roles & ADMIN_ROLES:
                people = [row["user_id"] for row in platform._all("SELECT DISTINCT user_id FROM institution_memberships WHERE institution_id=? AND state='active' ORDER BY user_id", (institution_id,))]
                cols = st.columns(3)
                paper = cols[0].selectbox("Paper reviewer", people, key="phase12-paper-reviewer")
                answer = cols[1].selectbox("Answer-key reviewer", people, key="phase12-answer-reviewer")
                controller = cols[2].selectbox("Controller", people, key="phase12-controller")
                tolerance = st.number_input("Moderation tolerance (percentage points)", 0.0, 25.0, 5.0)
                if st.button("Configure independent governance", type="primary"):
                    _run(lambda: service.configure_exam_governance(actor, exam_id, paper_reviewer_id=paper, answer_key_reviewer_id=answer, controller_id=controller, moderation_tolerance=tolerance))
    with monitor_tab:
        section_header("Candidate heartbeat monitor", "Server-owned exam sessions expose last heartbeat, answered count, connection state and integrity events.", icon=":material/monitor_heart:")
        exams = platform._all("SELECT id,title FROM examinations WHERE institution_id=? ORDER BY created_at DESC", (institution_id,))
        if exams and roles & TEACHER_ROLES:
            exam_id = st.selectbox("Monitored examination", [row["id"] for row in exams], format_func=lambda value: next(row["title"] for row in exams if row["id"] == value), key="phase12-monitor-exam")
            monitor = _run(lambda: service.live_exam_monitor(actor, exam_id)) or {}
            kpi_grid([
                (":material/wifi:", "Online", monitor.get("online", 0), "Fresh heartbeat"),
                (":material/wifi_off:", "Offline", monitor.get("offline", 0), "Stale or disconnected"),
                (":material/group:", "Candidates", len(monitor.get("candidates", [])), "Exam sessions"),
                (":material/update:", "Generated", str(monitor.get("generated_at", ""))[-14:], "Server monitor snapshot"),
            ])
            st.dataframe(monitor.get("candidates", []), width="stretch", hide_index=True)
        else:
            empty_state("No monitored exam", "Exam sessions and educator access are required for live monitoring.", icon="📡")


def _shiro_operations(service: EducationPhase12Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    models_tab, rag_tab, delivery_tab = st.tabs(["Model manager", "RAG governance", "Delivery providers"])
    with models_tab:
        section_header("Model management center", "Register local or provider-backed models and record live qualification evidence separately from configuration.", icon=":material/model_training:")
        hardware = service.runtime_hardware_posture()
        kpi_grid([
            (":material/memory:", "CPU threads", hardware.get("cpu_count", 0), "Detected runtime"),
            (":material/storage:", "Memory", f"{round(hardware.get('memory_bytes', 0)/1024**3, 1)} GiB" if hardware.get("memory_bytes") else "Unknown", "Physical memory estimate"),
            (":material/developer_board:", "GPUs", len(hardware.get("gpus", [])), "NVIDIA discovery"),
            (":material/compress:", "Quantization", hardware.get("recommended_quantization", "Q4/Q5"), "Runtime recommendation"),
        ])
        profiles = platform._all("SELECT id,name,provider_type,model_name,state,context_window FROM education_ai_model_profiles WHERE institution_id=? ORDER BY created_at DESC", (institution_id,))
        st.dataframe(profiles, width="stretch", hide_index=True) if profiles else empty_state("No AI model profile", "Register an Ollama, OpenAI-compatible or local-file model profile.", icon="🤖")
        if roles & ADMIN_ROLES:
            with st.form("phase12-model-form"):
                name = st.text_input("Profile name")
                provider = st.selectbox("Provider", ["ollama", "openai_compatible", "local_file", "disabled"])
                model_name = st.text_input("Model name")
                endpoint = st.text_input("Endpoint or local model path")
                embedding = st.text_input("Embedding model")
                secret = st.text_input("Secret reference", placeholder="env:BIOINTEL_AI_SECRET")
                context = st.number_input("Context window", 512, 2_000_000, 8192)
                submitted = st.form_submit_button("Save model profile", type="primary")
            if submitted:
                _run(lambda: service.register_ai_model_profile(actor, institution_id, name, provider_type=provider, model_name=model_name, endpoint=endpoint, embedding_model=embedding, secret_reference=secret, context_window=int(context), activate=True))
    with rag_tab:
        section_header("RAG source safety", "Documents are hash-deduplicated, permission-scoped and quarantined when prompt-injection patterns require human review.", icon=":material/document_scanner:")
        docs = platform._all("SELECT id,title,source_name,mime_type,size_bytes,state,created_by,created_at FROM education_rag_documents WHERE institution_id=? ORDER BY created_at DESC", (institution_id,))
        st.dataframe(docs, width="stretch", hide_index=True) if docs else empty_state("No governed RAG sources", "Register institution-approved course or research evidence for Shiro.", icon="📚")
        if roles & TEACHER_ROLES:
            with st.form("phase12-rag-form"):
                project_id = st.text_input("Shiro project ID")
                source_path = st.text_input("Local source path")
                title = st.text_input("Title")
                submitted = st.form_submit_button("Register and scan source", type="primary")
            if submitted:
                result = _run(lambda: service.register_rag_document(actor, institution_id, project_id, source_path, title=title))
                if result:
                    st.json(result)
    with delivery_tab:
        section_header("Notification provider registry", "Provider secrets stay in environment variables; HTTP channels use signed payloads and idempotency keys.", icon=":material/outgoing_mail:")
        providers = platform._all("SELECT id,channel,name,endpoint,sender,state,created_at FROM education_delivery_providers WHERE institution_id=? ORDER BY created_at DESC", (institution_id,))
        st.dataframe(providers, width="stretch", hide_index=True) if providers else empty_state("No delivery provider", "Configure SMTP, webhook, SMS or WhatsApp adapters with env: secret references.", icon="📨")
        if roles & ADMIN_ROLES:
            with st.form("phase12-provider-form"):
                channel = st.selectbox("Channel", ["smtp", "webhook", "sms", "whatsapp", "desktop", "in_app"])
                name = st.text_input("Provider name")
                endpoint = st.text_input("Endpoint")
                sender = st.text_input("Sender")
                secret = st.text_input("Secret reference", placeholder="env:BIOINTEL_PROVIDER_SECRET")
                submitted = st.form_submit_button("Save provider", type="primary")
            if submitted:
                _run(lambda: service.configure_delivery_provider(actor, institution_id, channel, name, endpoint=endpoint, sender=sender, secret_reference=secret, activate=True))


def render_phase12_completion_center(root: Path) -> None:
    render_app_header(
        "completion",
        "BioIntel Final Completion & Qualification Center",
        "OIDC PKCE, migration exports, S3/MinIO transfer contracts, originality review, examination governance, Shiro model/RAG safety and production provider evidence.",
        eyebrow="BIOINTEL PHASE 12 · FINAL CODE COMPLETION",
    )
    demo_mode = _demo_controls(root)
    platform = _page_platform(root, demo_mode)
    _identity_input("Completion Center user ID", demo_mode)
    actor = _actor()
    institution_id = _institution(platform)
    if not institution_id:
        return
    service = EducationPhase12Service(platform, root=root)
    roles = _roles(platform, actor, institution_id)
    render_workspace_context(platform, actor, institution_id)
    render_role_snapshot(platform, actor, institution_id)
    render_app_navigation("completion", platform, actor, institution_id)
    workspace = st.segmented_control(
        "Completion workspace",
        ["Overview", "Identity & Infrastructure", "Academic Assurance", "Shiro & Operations"],
        default="Overview",
        key=f"phase12-workspace-{actor}-{institution_id}",
    )
    if workspace == "Identity & Infrastructure":
        _identity_infrastructure(service, platform, actor, institution_id, roles)
    elif workspace == "Academic Assurance":
        _academic_assurance(service, platform, actor, institution_id, roles)
    elif workspace == "Shiro & Operations":
        _shiro_operations(service, platform, actor, institution_id, roles)
    else:
        _overview(service, platform, actor, institution_id)
