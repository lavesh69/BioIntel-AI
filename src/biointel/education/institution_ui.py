from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from ._streamlit_compat import st
from .experience import render_app_header, render_role_snapshot, render_workspace_context
from biointel.ui.frontend_v10 import empty_state, kpi_grid
from .phase5 import EducationPhase5Service
from .platform import ADMIN, EducationError
from .ui import _actor, _demo_controls, _identity_input, _institution, _page_platform, _run


def _metric_cards(items: list[tuple[str, Any, str]]) -> None:
    icons = ("▤", "◉", "▣", "↔")
    kpi_grid((icons[index % len(icons)], str(label), value, str(detail)) for index, (label, value, detail) in enumerate(items))


def _render_overview(service: EducationPhase5Service, actor: str, institution_id: str) -> None:
    dashboard = service.dashboard(actor, institution_id)
    _metric_cards([
        ("Campuses", dashboard["campuses"], "Institution hierarchy"),
        ("Identity readiness", f"{dashboard['identity_readiness']}%", "Configuration score, not login certification"),
        ("Verified backups", dashboard["verified_backups"], "SQLite integrity checked"),
        ("Queued work", dashboard["queued_jobs"], "Durable local jobs"),
    ])
    st.markdown(
        """
        <div class="edu-platform-grid">
          <article class="edu-module-card"><div class="edu-kicker">IDENTITY</div><h3>SSO and MFA control plane</h3><p>OIDC, SAML, Google Workspace and Microsoft Entra configuration with vault-only secret references and honest external-verification status.</p></article>
          <article class="edu-module-card"><div class="edu-kicker">OPERATIONS</div><h3>Durable institution services</h3><p>Multi-campus hierarchy, background queues, governed imports, storage inventory and non-destructive restore rehearsal.</p></article>
          <article class="edu-module-card"><div class="edu-kicker">INTEGRATIONS</div><h3>LMS interoperability</h3><p>Moodle, Canvas, Classroom, Teams, OneRoster, LTI, SCORM and xAPI readiness profiles without pretending credentials were tested.</p></article>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.info("PostgreSQL, external object storage and remote SSO/LMS connections remain configuration-ready until validated against real infrastructure.", icon=":material/verified_user:")


def _render_campuses(service: EducationPhase5Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    st.subheader("Multi-campus hierarchy")
    hierarchy = service.hierarchy(actor, institution_id)
    if hierarchy["campuses"]:
        rows = [{"code": c["code"], "campus": c["name"], "timezone": c["timezone"], "units": len(c["unit_ids"]), "state": c["state"]} for c in hierarchy["campuses"]]
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        empty_state("No campus configured", "The institution hierarchy is ready but has no campus record.", icon="▤", action_hint="Create the first campus using the governance form above.")
    if not roles & ADMIN:
        return
    create_tab, mapping_tab = st.tabs(["Create campus", "Map academic unit"])
    with create_tab:
        with st.form("phase5-campus-create"):
            code = st.text_input("Campus code", placeholder="MAIN")
            name = st.text_input("Campus name", placeholder="Main Campus")
            timezone_name = st.text_input("Timezone", value="Asia/Kolkata")
            city = st.text_input("City")
            if st.form_submit_button("Create campus", type="primary", icon=":material/domain:"):
                result = _run(lambda: service.create_campus(actor, institution_id, code, name, timezone_name=timezone_name, address={"city": city}))
                if result:
                    st.success("Campus created.")
                    st.rerun()
    with mapping_tab:
        campuses = hierarchy["campuses"]
        units = hierarchy["academic_units"]
        if campuses and units:
            campus_id = st.selectbox("Campus", [c["id"] for c in campuses], format_func=lambda value: next(f"{c['code']} · {c['name']}" for c in campuses if c["id"] == value))
            unit_id = st.selectbox("Academic unit", [u["id"] for u in units], format_func=lambda value: next(f"{u['unit_type'].title()} · {u['name']}" for u in units if u["id"] == value))
            if st.button("Link unit", type="primary", icon=":material/account_tree:"):
                result = _run(lambda: service.link_unit_to_campus(actor, campus_id, unit_id))
                if result:
                    st.success("Academic unit linked.")
                    st.rerun()
        else:
            st.info("Create a campus and academic unit before mapping.")


def _render_identity(service: EducationPhase5Service, actor: str, institution_id: str, roles: set[str]) -> None:
    st.subheader("Identity, SSO and MFA")
    posture = service.identity_posture(actor, institution_id)
    _metric_cards([
        ("Readiness", f"{posture['readiness_score']}%", "Configuration completeness"),
        ("Providers", len(posture["providers"]), "OIDC/SAML provider records"),
        ("MFA policy", "Active" if posture["mfa_policy"] else "Missing", "Institution role policy"),
        ("External login", "Not verified", "Requires real identity provider"),
    ])
    if posture["providers"]:
        st.dataframe(posture["providers"], width="stretch", hide_index=True)
    if not roles & ADMIN:
        return
    provider_tab, mfa_tab = st.tabs(["Identity provider", "MFA policy"])
    with provider_tab:
        with st.form("phase5-idp"):
            provider_type = st.selectbox("Provider", ["oidc", "saml", "google_workspace", "microsoft_entra"])
            display_name = st.text_input("Display name", placeholder="University SSO")
            issuer_url = st.text_input("Issuer URL")
            metadata_url = st.text_input("SAML metadata URL")
            client_id = st.text_input("Client ID")
            secret_reference = st.text_input("Secret reference", placeholder="env:BIOINTEL_OIDC_SECRET")
            allowed_domains = st.text_input("Allowed email domains", placeholder="university.edu,students.university.edu")
            activate = st.checkbox("Mark configuration ready")
            if st.form_submit_button("Save identity provider", type="primary", icon=":material/passkey:"):
                result = _run(lambda: service.configure_identity_provider(actor, institution_id, provider_type, display_name, issuer_url=issuer_url, metadata_url=metadata_url, client_id=client_id, secret_reference=secret_reference, allowed_domains=[x.strip() for x in allowed_domains.split(",") if x.strip()], activate=activate))
                if result:
                    st.success("Identity provider configuration saved without storing a plaintext secret.")
                    st.rerun()
    with mfa_tab:
        with st.form("phase5-mfa"):
            required_roles = st.multiselect("MFA-required roles", ["platform_administrator", "institution_administrator", "principal", "dean", "registrar", "department_head", "examination_controller", "subject_teacher"], default=["institution_administrator", "registrar"])
            methods = st.multiselect("Allowed methods", ["totp", "webauthn", "email_otp"], default=["totp", "webauthn"])
            grace_hours = st.number_input("Enrollment grace hours", 0, 720, 24)
            recovery = st.checkbox("Require recovery codes", value=True)
            if st.form_submit_button("Apply MFA policy", type="primary"):
                result = _run(lambda: service.save_mfa_policy(actor, institution_id, required_roles=required_roles, methods=methods, grace_hours=int(grace_hours), recovery_codes_required=recovery))
                if result:
                    st.success("MFA policy saved.")
                    st.rerun()


def _render_storage(service: EducationPhase5Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    st.subheader("Storage, backups and restore rehearsal")
    objects = platform._all("SELECT object_key,original_name,size_bytes,sha256,state,created_at FROM education_storage_objects WHERE institution_id=? ORDER BY created_at DESC LIMIT 100", (institution_id,))
    backups = platform._all("SELECT id,label,size_bytes,state,created_at,verified_at FROM education_backup_snapshots WHERE institution_id=? ORDER BY created_at DESC LIMIT 50", (institution_id,))
    _metric_cards([
        ("Stored objects", len(objects), "Tenant-isolated registry"),
        ("Backups", len(backups), "Online SQLite snapshots"),
        ("Integrity", "SHA-256", "Database and object evidence"),
        ("Restore mode", "Rehearsal", "Live database never replaced by UI"),
    ])
    object_tab, backup_tab, backend_tab, database_tab = st.tabs(["Objects", "Backups", "Object backends", "Database readiness"])
    with object_tab:
        if objects:
            st.dataframe(objects, width="stretch", hide_index=True)
        uploaded = st.file_uploader("Store a governed local object", key="phase5-object-upload")
        if uploaded and st.button("Store uploaded object", type="primary"):
            upload_dir = service.data_root / institution_id / "incoming"
            upload_dir.mkdir(parents=True, exist_ok=True)
            temp = upload_dir / Path(uploaded.name).name
            temp.write_bytes(uploaded.getvalue())
            result = _run(lambda: service.store_local_object(actor, institution_id, temp, mime_type=getattr(uploaded, "type", "application/octet-stream") or "application/octet-stream"))
            if result:
                st.success("Object stored and hashed.")
                st.rerun()
    with backup_tab:
        if backups:
            st.dataframe(backups, width="stretch", hide_index=True)
        if roles & ADMIN:
            label = st.text_input("Backup label", placeholder="before-semester-rollover")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Create verified backup", type="primary", icon=":material/backup:"):
                    result = _run(lambda: service.create_backup(actor, institution_id, label))
                    if result:
                        st.success("Backup created and integrity checked.")
                        st.rerun()
            with col2:
                if backups:
                    selected = st.selectbox("Backup for rehearsal", [row["id"] for row in backups], format_func=lambda value: next(row["label"] for row in backups if row["id"] == value))
                    if st.button("Run restore rehearsal"):
                        result = _run(lambda: service.restore_rehearsal(actor, selected))
                        if result:
                            st.json(result)
    with backend_tab:
        backends = platform._all("SELECT id,backend_type,name,endpoint,bucket,region,state,created_at FROM education_storage_backends WHERE institution_id=? ORDER BY created_at DESC", (institution_id,))
        if backends:
            st.dataframe(backends, width="stretch", hide_index=True)
        if roles & ADMIN:
            with st.form("phase5-storage-backend"):
                backend_type = st.selectbox("Backend type", ["local", "minio", "s3"])
                name = st.text_input("Backend name", placeholder="Institution Object Store")
                endpoint = st.text_input("Endpoint")
                bucket = st.text_input("Bucket")
                region = st.text_input("Region")
                secret_reference = st.text_input("Secret reference", placeholder="vault:biointel/object-store")
                activate = st.checkbox("Mark configuration ready")
                if st.form_submit_button("Save backend", type="primary"):
                    result = _run(lambda: service.configure_storage_backend(actor, institution_id, backend_type, name, endpoint=endpoint, bucket=bucket, region=region, secret_reference=secret_reference, activate=activate))
                    if result:
                        st.success("Storage backend configuration saved.")
                        st.rerun()

    with database_tab:
        posture = service.database_posture(actor, institution_id)
        _metric_cards([
            ("Profiles", len(posture["profiles"]), "SQLite/PostgreSQL contracts"),
            ("PostgreSQL config", "Ready" if posture["postgresql_configuration_ready"] else "Missing", "Vault-reference configuration"),
            ("Network check", "Pending", "Requires real PostgreSQL host"),
            ("Production verified", "No", "No unsupported claim"),
        ])
        if posture["profiles"]:
            st.dataframe(posture["profiles"], width="stretch", hide_index=True)
        if roles & ADMIN:
            with st.form("phase5-database-profile"):
                engine = st.selectbox("Database engine", ["sqlite", "postgresql"])
                name = st.text_input("Profile name", placeholder="Production PostgreSQL")
                dsn_reference = st.text_input("DSN secret reference", placeholder="vault:biointel/postgres-dsn")
                pool_min = st.number_input("Minimum pool", 1, 100, 2)
                pool_max = st.number_input("Maximum pool", 1, 500, 30)
                ssl_mode = st.selectbox("SSL mode", ["verify-full", "verify-ca", "require", "prefer", "allow", "disable"])
                activate = st.checkbox("Mark configuration ready", key="phase5-db-ready")
                if st.form_submit_button("Save database profile", type="primary"):
                    result = _run(lambda: service.configure_database_profile(actor, institution_id, engine, name, dsn_reference=dsn_reference, pool_min=int(pool_min), pool_max=int(pool_max), ssl_mode=ssl_mode, activate=activate))
                    if result:
                        st.success("Database profile saved. PostgreSQL network and credentials remain unverified until tested externally.")
                        st.rerun()


def _render_jobs(service: EducationPhase5Service, platform: Any, actor: str, institution_id: str) -> None:
    st.subheader("Background jobs")
    jobs = platform._all("SELECT id,queue_name,job_type,state,priority,attempts,max_attempts,available_at,error_text,created_at FROM education_background_jobs WHERE institution_id=? ORDER BY created_at DESC LIMIT 200", (institution_id,))
    if jobs:
        st.dataframe(jobs, width="stretch", hide_index=True)
    else:
        empty_state("Background queue is empty", "No pending, running or failed institutional jobs are visible.", icon="⌘", action_hint="Schedule a backup, report or integration sync to create a job.")
    with st.form("phase5-job"):
        job_type = st.selectbox("Job type", ["generate_report", "sync_publications", "send_notification_digest", "transcode_lecture", "export_institution_data", "verify_backup"])
        queue_name = st.selectbox("Queue", ["default", "reports", "media", "integrations"])
        priority = st.slider("Priority", 0, 100, 50)
        payload_text = st.text_area("Payload JSON", value="{}")
        if st.form_submit_button("Queue job", type="primary", icon=":material/queue:"):
            try:
                payload = json.loads(payload_text or "{}")
            except ValueError:
                st.error("Payload must be valid JSON.")
            else:
                result = _run(lambda: service.enqueue_job(actor, institution_id, job_type, payload, queue_name=queue_name, priority=priority))
                if result:
                    st.success("Durable job queued.")
                    st.rerun()


def _render_integrations(service: EducationPhase5Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    st.subheader("Institution integrations")
    rows = platform._all("SELECT id,provider_type,name,base_url,state,last_tested_at,created_at FROM education_integrations WHERE institution_id=? ORDER BY created_at DESC", (institution_id,))
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True)
        selected = st.selectbox("Readiness check", [row["id"] for row in rows], format_func=lambda value: next(f"{row['provider_type']} · {row['name']}" for row in rows if row["id"] == value))
        if roles & ADMIN and st.button("Validate configuration readiness"):
            result = _run(lambda: service.test_integration_readiness(actor, selected))
            if result:
                st.json(result["readiness"])
    else:
        empty_state("No integration configured", "No LMS or interoperability provider is connected to this institution.", icon="↔", action_hint="Add a provider profile without storing plaintext secrets.")
    if not roles & ADMIN:
        return
    with st.form("phase5-integration"):
        provider_type = st.selectbox("Provider", ["moodle", "canvas", "google_classroom", "microsoft_teams", "oneroster", "lti_1_3", "scorm", "xapi"])
        name = st.text_input("Integration name")
        base_url = st.text_input("Base URL")
        client_id = st.text_input("Client ID")
        secret_reference = st.text_input("Secret reference", placeholder="vault:biointel/lms")
        activate = st.checkbox("Mark configuration ready")
        if st.form_submit_button("Save integration", type="primary"):
            result = _run(lambda: service.configure_integration(actor, institution_id, provider_type, name, base_url=base_url, client_id=client_id, secret_reference=secret_reference, activate=activate))
            if result:
                st.success("Integration configuration saved. Network and credentials are still unverified until tested externally.")
                st.rerun()


def _render_imports_reports(service: EducationPhase5Service, platform: Any, actor: str, institution_id: str, roles: set[str]) -> None:
    import_tab, report_tab = st.tabs(["Roster import", "Governance report"])
    with import_tab:
        batches = platform._all("SELECT id,import_type,file_name,state,total_rows,valid_rows,invalid_rows,created_at FROM education_import_batches WHERE institution_id=? ORDER BY created_at DESC LIMIT 100", (institution_id,))
        if batches:
            st.dataframe(batches, width="stretch", hide_index=True)
        if roles & ADMIN:
            import_type = st.selectbox("Import type", ["members", "subjects"])
            upload = st.file_uploader("UTF-8 CSV", type=["csv"], key="phase5-import")
            if upload and st.button("Preview import", type="primary"):
                result = _run(lambda: service.preview_import(actor, institution_id, import_type, upload.name, upload.getvalue()))
                if result:
                    st.session_state.phase5_import_batch = result["id"]
                    st.json(result)
            batch_id = st.session_state.get("phase5_import_batch")
            if batch_id and st.button("Commit validated import"):
                result = _run(lambda: service.commit_import(actor, batch_id))
                if result:
                    st.success("Import committed transactionally.")
                    st.rerun()
    with report_tab:
        st.caption("Reports explicitly distinguish locally verified controls from external infrastructure that still needs qualification.")
        if st.button("Generate institution readiness report", type="primary", icon=":material/analytics:"):
            result = _run(lambda: service.generate_governance_report(actor, institution_id))
            if result:
                st.session_state.phase5_governance_report = result
        result = st.session_state.get("phase5_governance_report")
        if result:
            payload = json.dumps(result, indent=2, default=str).encode("utf-8")
            st.download_button("Download governed JSON", payload, file_name="institution-readiness.json", mime="application/json")
            st.json(result, expanded=False)


def render_education_institution_center(root: Path) -> None:
    render_app_header(
        "institution",
        "Institution Platform Center",
        "Multi-campus governance, identity readiness, durable jobs, storage, backups, LMS integrations, imports and evidence-grade institutional reporting.",
        eyebrow="BIOINTEL EDUCATION OS · PHASE 5",
    )
    demo_mode = _demo_controls(root)
    platform = _page_platform(root, demo_mode)
    _identity_input("Institution user ID", demo_mode)
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
    service = EducationPhase5Service(platform, root=root)
    tabs = st.tabs([
        ":material/space_dashboard: Overview",
        ":material/domain: Campuses",
        ":material/passkey: Identity",
        ":material/cloud_done: Storage",
        ":material/queue: Jobs",
        ":material/hub: Integrations",
        ":material/publish: Imports & Reports",
    ])
    with tabs[0]:
        _render_overview(service, actor, institution_id)
    with tabs[1]:
        _render_campuses(service, platform, actor, institution_id, roles)
    with tabs[2]:
        _render_identity(service, actor, institution_id, roles)
    with tabs[3]:
        _render_storage(service, platform, actor, institution_id, roles)
    with tabs[4]:
        _render_jobs(service, platform, actor, institution_id)
    with tabs[5]:
        _render_integrations(service, platform, actor, institution_id, roles)
    with tabs[6]:
        _render_imports_reports(service, platform, actor, institution_id, roles)
