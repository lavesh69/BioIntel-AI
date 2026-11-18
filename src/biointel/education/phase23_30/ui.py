from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import streamlit as st

from ..paths import education_paths
from ..platform import EducationError, EducationPlatform
from .service import EducationEnterprisePlatform


@st.cache_resource(show_spinner=False)
def _service(root_text: str, demo: bool) -> EducationEnterprisePlatform:
    database, media = education_paths(root_text, demo=demo)
    platform = EducationPlatform(database, media)
    return EducationEnterprisePlatform(platform, root=root_text)


def _run(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except EducationError as exc:
        st.error(str(exc), icon=":material/error:")
        return None


def _identity(
    service: EducationEnterprisePlatform,
) -> tuple[str, str] | None:
    actor = str(st.session_state.get("education_actor") or "local-operator")
    memberships = service.platform._all(
        """SELECT DISTINCT i.id,i.name FROM institutions i
        JOIN memberships m ON m.institution_id=i.id
        WHERE m.user_id=? AND m.state='active' AND i.state='active'
        ORDER BY i.name""",
        (actor,),
    )
    if not memberships:
        st.info(
            "Open Education Home first and select an institution identity.",
            icon=":material/domain:",
        )
        try:
            st.page_link(
                "pages/339_BioIntel_Education_Home.py",
                label="Open Education Home",
                icon=":material/dashboard:",
            )
        except (KeyError, ValueError):
            # Streamlit's isolated AppTest runner has no multipage URL map.
            # The app remains usable and the normal multipage runtime keeps
            # the direct navigation control above.
            st.caption("Use the sidebar to open **BioIntel Education Home**.")
        return None
    by_id = {row["id"]: row for row in memberships}
    institution_id = st.selectbox(
        "Institution",
        list(by_id),
        format_func=lambda value: by_id[value]["name"],
        key="p30-institution",
    )
    st.caption(f"Authenticated actor: `{actor}`")
    return actor, institution_id


def _overview(
    service: EducationEnterprisePlatform,
    actor: str,
    institution_id: str,
) -> None:
    snapshot = _run(lambda: service.platform_snapshot(actor, institution_id))
    if not snapshot:
        return
    with st.container(horizontal=True):
        st.metric(
            "Active mastery records",
            len(snapshot["mastery"]),
            border=True,
        )
        st.metric(
            "Adaptive recommendations",
            len(snapshot["recommendations"]),
            border=True,
        )
        st.metric(
            "Virtual Lab attempts",
            len(snapshot["virtual_labs"]),
            border=True,
        )
        st.metric(
            "Credentials",
            len(snapshot["credentials"]),
            border=True,
        )
    if "pilots" in snapshot:
        with st.container(horizontal=True):
            st.metric("Institution pilots", len(snapshot["pilots"]), border=True)
            st.metric("Agent tasks", len(snapshot["agent_tasks"]), border=True)
            st.metric("Support tickets", len(snapshot["support_tickets"]), border=True)
            st.metric("Background jobs", len(snapshot["jobs"]), border=True)
    with st.container(border=True):
        st.subheader("Current adaptive recommendations", anchor=False)
        st.dataframe(
            snapshot["recommendations"],
            hide_index=True,
            width="stretch",
        )


def _pilots(
    service: EducationEnterprisePlatform,
    actor: str,
    institution_id: str,
) -> None:
    st.subheader("Controlled institution pilots", anchor=False)
    with st.form("p30-pilot-create"):
        name = st.text_input("Pilot name")
        starts_on = st.text_input("Start date/time (ISO-8601)", placeholder="2026-08-01T09:00:00+05:30")
        ends_on = st.text_input("End date/time (ISO-8601)", placeholder="2026-12-01T17:00:00+05:30")
        user_limit = st.number_input("Allowed users", min_value=1, max_value=100000, value=500)
        terms_version = st.text_input("Pilot terms version")
        accept_terms = st.checkbox("I am authorized to record acceptance of these pilot terms")
        submitted = st.form_submit_button(
            "Register pilot",
            type="primary",
            icon=":material/add_business:",
        )
    if submitted:
        result = _run(
            lambda: service.register_pilot(
                actor,
                institution_id,
                name=name,
                starts_on=starts_on,
                ends_on=ends_on,
                user_limit=int(user_limit),
                terms_version=terms_version,
                terms_accepted=accept_terms,
                administrator_ids=[actor],
            )
        )
        if result:
            st.success(f"Pilot registered: {result['id']}")
            st.rerun()
    pilots = service._all(
        """SELECT id,name,status,onboarding_percent,health_score,blocker_count,
        consent_state,readiness_decision,updated_at
        FROM education_p30_pilots WHERE institution_id=? ORDER BY updated_at DESC""",
        (institution_id,),
    )
    st.dataframe(pilots, hide_index=True, width="stretch")
    if pilots:
        by_id = {row["id"]: row for row in pilots}
        pilot_id = st.selectbox(
            "Pilot workflow",
            list(by_id),
            format_func=lambda value: f"{by_id[value]['name']} — {by_id[value]['status']}",
        )
        with st.form("p30-pilot-transition"):
            next_status = st.selectbox(
                "Next status",
                [
                    "technical_validation",
                    "institution_onboarding",
                    "data_import",
                    "staff_training",
                    "student_activation",
                    "controlled_live_pilot",
                    "pilot_review",
                    "acceptance_or_remediation",
                    "production_readiness_decision",
                ],
            )
            reason = st.text_area("Transition reason")
            readiness = st.selectbox(
                "Readiness decision",
                ["", "accepted", "remediation_required", "not_ready"],
            )
            move = st.form_submit_button(
                "Apply guarded transition",
                icon=":material/arrow_forward:",
            )
        if move:
            moved = _run(
                lambda: service.transition_pilot(
                    actor,
                    pilot_id,
                    next_status,
                    reason=reason,
                    readiness_decision=readiness,
                )
            )
            if moved:
                st.success(f"Pilot is now {moved['status']}.")
                st.rerun()
        with st.form("p30-import-dry-run"):
            entity_type = st.selectbox(
                "Import entity",
                [
                    "departments",
                    "programs",
                    "semesters",
                    "courses",
                    "subjects",
                    "batches",
                    "staff",
                    "students",
                    "parents",
                    "enrolments",
                    "timetables",
                    "previous_attendance",
                    "historical_marks",
                    "course_materials",
                ],
            )
            source_path = st.text_input("CSV/XLSX path")
            dry_run = st.form_submit_button(
                "Validate import",
                icon=":material/fact_check:",
            )
        if dry_run:
            result = _run(
                lambda: service.dry_run_import(
                    actor,
                    institution_id,
                    entity_type,
                    source_path,
                    pilot_id=pilot_id,
                )
            )
            if result:
                st.success(
                    f"Dry-run {result['state']}: {result['valid_count']} valid, "
                    f"{result['invalid_count']} invalid."
                )
                st.code(str(result["confirmation_digest"]))


def _agents(
    service: EducationEnterprisePlatform,
    actor: str,
    institution_id: str,
) -> None:
    st.subheader("Approval-controlled Shiro agent ecosystem", anchor=False)
    registry = service.agent_registry(actor, institution_id)
    by_key = {row["key"]: row for row in registry}
    with st.form("p30-agent-create"):
        agent_key = st.selectbox(
            "Agent",
            list(by_key),
            format_func=lambda value: by_key[value]["name"],
        )
        topic = st.text_input("Topic or request")
        citations_text = st.text_area(
            "Evidence citations JSON",
            value="[]",
            help="List of source_id/citation dictionaries. Research agents remain partial without evidence.",
        )
        idempotency_key = st.text_input("Idempotency key")
        submitted = st.form_submit_button(
            "Create controlled task",
            type="primary",
            icon=":material/neurology:",
        )
    if submitted:
        try:
            citations = json.loads(citations_text)
            if not isinstance(citations, list):
                raise ValueError("Citations must be a list.")
        except (ValueError, json.JSONDecodeError) as exc:
            st.error(f"Invalid citations JSON: {exc}")
        else:
            result = _run(
                lambda: service.create_agent_task(
                    actor,
                    institution_id,
                    agent_key=agent_key,
                    task_input={"topic": topic, "citations": citations},
                    idempotency_key=idempotency_key,
                )
            )
            if result:
                st.success(
                    f"Task {result['id']} created in state {result['state']}."
                )
                st.rerun()
    tasks = service._all(
        """SELECT id,agent_key,state,approval_state,requested_by,depth,
        resource_seconds,updated_at FROM education_p30_agent_tasks
        WHERE institution_id=? ORDER BY updated_at DESC LIMIT 100""",
        (institution_id,),
    )
    st.dataframe(tasks, hide_index=True, width="stretch")
    if tasks:
        by_id = {row["id"]: row for row in tasks}
        task_id = st.selectbox(
            "Task",
            list(by_id),
            format_func=lambda value: f"{by_id[value]['agent_key']} — {by_id[value]['state']}",
        )
        with st.container(horizontal=True):
            if st.button("Approve", icon=":material/approval:"):
                if _run(
                    lambda: service.approve_agent_task(
                        actor,
                        task_id,
                        decision="approved",
                    )
                ):
                    st.rerun()
            if st.button("Execute", icon=":material/play_arrow:"):
                if _run(lambda: service.execute_agent_task(actor, task_id)):
                    st.rerun()


def _labs(
    service: EducationEnterprisePlatform,
    actor: str,
    institution_id: str,
) -> None:
    st.subheader("BioIntel Virtual Science Laboratory", anchor=False)
    catalog = service.lab_catalog(actor, institution_id)
    with st.container(horizontal=True):
        st.metric("Experiments", len(catalog), border=True)
        st.metric(
            "Calculation simulations",
            sum(row["capability_class"] == "calculation_simulation" for row in catalog),
            border=True,
        )
        st.metric(
            "Guided practicals",
            sum(row["capability_class"] == "structured_guided_workflow" for row in catalog),
            border=True,
        )
    st.dataframe(
        [
            {
                "Experiment": row["title"],
                "Discipline": row["discipline"],
                "Capability": row["capability_class"],
                "Version": row["current_version"],
            }
            for row in catalog
        ],
        hide_index=True,
        width="stretch",
    )
    by_id = {row["id"]: row for row in catalog}
    experiment_id = st.selectbox(
        "Experiment",
        list(by_id),
        format_func=lambda value: by_id[value]["title"],
    )
    if st.button(
        "Start persistent attempt",
        type="primary",
        icon=":material/science:",
    ):
        result = _run(
            lambda: service.start_lab_attempt(
                actor,
                institution_id,
                experiment_id,
            )
        )
        if result:
            st.success(f"Attempt started: {result['id']}")
            st.rerun()
    attempts = service._all(
        """SELECT a.id,e.title,a.state,a.current_step,a.invalid_actions,
        a.safety_violations,a.updated_at
        FROM education_p30_lab_attempts a
        JOIN education_p30_lab_experiments e ON e.id=a.experiment_id
        WHERE a.institution_id=? AND a.student_id=?
        ORDER BY a.updated_at DESC LIMIT 50""",
        (institution_id, actor),
    )
    st.dataframe(attempts, hide_index=True, width="stretch")
    if attempts:
        attempt_by_id = {row["id"]: row for row in attempts}
        attempt_id = st.selectbox(
            "Active attempt",
            list(attempt_by_id),
            format_func=lambda value: f"{attempt_by_id[value]['title']} — {attempt_by_id[value]['state']}",
        )
        with st.form("p30-lab-step"):
            action = st.selectbox(
                "Action",
                ["review", "confirm_safety", "prepare", "perform", "measure", "interpret", "cleanup"],
            )
            measurement = st.number_input("Measurement value", value=0.0)
            unit = st.text_input("Unit")
            safety = st.checkbox("Safety requirements acknowledged")
            record = st.form_submit_button(
                "Record validated step",
                icon=":material/checklist:",
            )
        if record:
            step = _run(
                lambda: service.record_lab_step(
                    actor,
                    attempt_id,
                    action=action,
                    values={"value": measurement, "unit": unit},
                    safety_acknowledged=safety,
                )
            )
            if step:
                st.success(
                    "Step accepted." if step["valid"] else f"Step rejected: {step['feedback']}"
                )
                st.rerun()


def _learning_research(
    service: EducationEnterprisePlatform,
    actor: str,
    institution_id: str,
) -> None:
    mode = st.segmented_control(
        "Workspace",
        ["Adaptive learning", "Research pipeline"],
        default="Adaptive learning",
        key="p30-learning-research-mode",
    )
    if mode == "Adaptive learning":
        st.subheader("Explainable adaptive learning", anchor=False)
        with st.form("p30-concept-create"):
            key = st.text_input("Concept key")
            name = st.text_input("Concept name")
            description = st.text_area("Description")
            create = st.form_submit_button(
                "Create concept",
                icon=":material/account_tree:",
            )
        if create:
            if _run(
                lambda: service.create_concept(
                    actor,
                    institution_id,
                    key=key,
                    name=name,
                    description=description,
                )
            ):
                st.rerun()
        concepts = service._all(
            """SELECT id,key,name,subject_id,state,updated_at
            FROM education_p30_concepts WHERE institution_id=?
            ORDER BY name LIMIT 200""",
            (institution_id,),
        )
        st.dataframe(concepts, hide_index=True, width="stretch")
        if concepts:
            by_id = {row["id"]: row for row in concepts}
            concept_id = st.selectbox(
                "Concept",
                list(by_id),
                format_func=lambda value: by_id[value]["name"],
            )
            with st.form("p30-mastery-evidence"):
                correctness = st.slider("Correctness", 0.0, 1.0, 0.6, 0.05)
                confidence = st.slider("Confidence", 0.0, 1.0, 0.5, 0.05)
                add = st.form_submit_button(
                    "Add mastery evidence",
                    icon=":material/add_chart:",
                )
            if add:
                if _run(
                    lambda: service.record_mastery_evidence(
                        actor,
                        institution_id,
                        actor,
                        concept_id,
                        evidence_type="practice",
                        correctness=correctness,
                        confidence=confidence,
                    )
                ):
                    st.rerun()
            if st.button("Explain next recommendation", icon=":material/route:"):
                recommendation = _run(
                    lambda: service.recommend_next(
                        actor,
                        institution_id,
                        actor,
                        concept_id,
                    )
                )
                if recommendation:
                    st.info(recommendation["explanation"], icon=":material/info:")
    else:
        st.subheader("Research-to-education pipeline", anchor=False)
        with st.form("p30-paper-ingest"):
            title = st.text_input("Paper title")
            doi = st.text_input("DOI")
            pmid = st.text_input("PMID")
            abstract = st.text_area("Abstract")
            ingest = st.form_submit_button(
                "Ingest evidence record",
                icon=":material/library_books:",
            )
        if ingest:
            if _run(
                lambda: service.ingest_research_paper(
                    actor,
                    institution_id,
                    title=title,
                    doi=doi,
                    pmid=pmid,
                    abstract=abstract,
                )
            ):
                st.rerun()
        papers = service._all(
            """SELECT id,doi,pmid,title,retraction_state,verification_state,updated_at
            FROM education_p30_research_papers WHERE institution_id=?
            ORDER BY updated_at DESC LIMIT 100""",
            (institution_id,),
        )
        st.dataframe(papers, hide_index=True, width="stretch")


def _credentials_integrations(
    service: EducationEnterprisePlatform,
    actor: str,
    institution_id: str,
) -> None:
    mode = st.segmented_control(
        "Workspace",
        ["Portfolio", "Integrations", "Release qualification"],
        default="Portfolio",
        key="p30-credentials-integrations-mode",
    )
    if mode == "Portfolio":
        portfolio = _run(
            lambda: service.get_or_create_portfolio(actor, institution_id)
        )
        if not portfolio:
            return
        st.metric("Portfolio visibility", portfolio["visibility"], border=True)
        items = service._all(
            """SELECT id,item_type,title,evidence_type,verification_state,
            selected_for_showcase,created_at
            FROM education_p30_portfolio_items WHERE portfolio_id=?
            ORDER BY created_at DESC""",
            (portfolio["id"],),
        )
        credentials = service._all(
            """SELECT id,credential_type,title,issued_at,expires_at,state,certificate_path
            FROM education_p30_credentials WHERE institution_id=? AND owner_id=?
            ORDER BY issued_at DESC""",
            (institution_id, actor),
        )
        st.dataframe(items, hide_index=True, width="stretch")
        st.dataframe(credentials, hide_index=True, width="stretch")
    elif mode == "Integrations":
        st.dataframe(service.adapter_catalog(), hide_index=True, width="stretch")
        with st.form("p30-integration-create"):
            adapter_type = st.selectbox(
                "Adapter",
                [row["adapter_type"] for row in service.adapter_catalog()],
            )
            name = st.text_input("Connection name")
            config_text = st.text_area("Configuration JSON", value="{}")
            secret_reference = st.text_input(
                "Secret reference",
                help="Raw passwords/tokens are rejected.",
            )
            enabled = st.checkbox("Enable after saving")
            save = st.form_submit_button(
                "Save adapter configuration",
                icon=":material/cable:",
            )
        if save:
            try:
                configuration = json.loads(config_text)
                if not isinstance(configuration, dict):
                    raise ValueError("Configuration must be an object.")
            except (ValueError, json.JSONDecodeError) as exc:
                st.error(f"Invalid configuration JSON: {exc}")
            else:
                if _run(
                    lambda: service.configure_integration(
                        actor,
                        institution_id,
                        adapter_type=adapter_type,
                        name=name,
                        configuration=configuration,
                        secret_reference=secret_reference,
                        enabled=enabled,
                    )
                ):
                    st.rerun()
        rows = service._all(
            """SELECT id,adapter_type,name,state,last_test_state,last_test_detail,updated_at
            FROM education_p30_integrations WHERE institution_id=?
            ORDER BY name""",
            (institution_id,),
        )
        st.dataframe(rows, hide_index=True, width="stretch")
    else:
        qualification = _run(
            lambda: service.release_qualification(actor, institution_id)
        )
        if not qualification:
            return
        with st.container(horizontal=True):
            st.metric(
                "Phase 23–30 tables",
                qualification["phase30_tables"],
                border=True,
            )
            st.metric(
                "Indexes",
                qualification["phase30_indexes"],
                border=True,
            )
            st.metric(
                "Database",
                "Healthy" if qualification["database_quick_check"] else "Failed",
                border=True,
            )
            st.metric(
                "Audit chain",
                "Valid" if qualification["audit_chain"]["passed"] else "Invalid",
                border=True,
            )
        st.dataframe(
            [
                {
                    "Capability": key,
                    "Classification": value["status"],
                    "Evidence or reason": value.get("evidence") or value.get("reason"),
                }
                for key, value in qualification["capabilities"].items()
            ],
            hide_index=True,
            width="stretch",
        )


def render_phase23_30_platform(
    root: Path,
    *,
    default_view: str = "Overview",
) -> None:
    st.title("BioIntel Education & Research Enterprise", anchor=False)
    st.caption(
        "Phases 23–30 — controlled institution pilots, approval-governed agents, "
        "Virtual Lab, adaptive mastery, evidence-preserving research, credentials, "
        "integrations, MCP and production-readiness controls."
    )
    demo = bool(st.session_state.get("education_demo_mode", False))
    service = _service(str(root), demo)
    identity = _identity(service)
    if not identity:
        return
    actor, institution_id = identity
    options = [
        "Overview",
        "Pilots & imports",
        "Shiro agents",
        "Virtual Lab",
        "Learning & research",
        "Portfolio & platform",
    ]
    view = st.segmented_control(
        "Workspace",
        options,
        default=default_view if default_view in options else "Overview",
        key=f"p30-view-{default_view}",
    )
    if view == "Overview":
        _overview(service, actor, institution_id)
    elif view == "Pilots & imports":
        _pilots(service, actor, institution_id)
    elif view == "Shiro agents":
        _agents(service, actor, institution_id)
    elif view == "Virtual Lab":
        _labs(service, actor, institution_id)
    elif view == "Learning & research":
        _learning_research(service, actor, institution_id)
    else:
        _credentials_integrations(service, actor, institution_id)
